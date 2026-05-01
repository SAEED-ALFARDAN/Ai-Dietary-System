from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Dict
import os

from ultralytics import YOLO
from PIL import Image
import io

from sqlalchemy.orm import Session

from database import init_db, get_db, Food

app = FastAPI()

# Initialize DB
init_db()

# Load YOLOv8 model once at startup (path to your trained weights)
model = YOLO("C:\\Users\\igohs\\Desktop\\Ai-Dietary-System\\models\\last.pt")

# Portion scaling configs (override via environment variables if needed)
REFERENCE_OBJECT_LABEL = os.getenv("REFERENCE_OBJECT_LABEL", "card").lower()
REFERENCE_OBJECT_REAL_AREA_CM2 = float(os.getenv("REFERENCE_OBJECT_REAL_AREA_CM2", "46.6"))
BASE_FOOD_AREA_CM2 = float(os.getenv("BASE_FOOD_AREA_CM2", "100.0"))
FALLBACK_BASE_IMAGE_AREA_RATIO = float(os.getenv("FALLBACK_BASE_IMAGE_AREA_RATIO", "0.16"))
MIN_PORTION_RATIO = float(os.getenv("MIN_PORTION_RATIO", "0.5"))
MAX_PORTION_RATIO = float(os.getenv("MAX_PORTION_RATIO", "2.5"))
MIN_CONF = float(os.getenv("MIN_CONF", "0.25"))

# Common model-label variants mapped to DB names.
FOOD_ALIASES = {
    "softdrink": "soft_drink",
    "soft-drink": "soft_drink",
    "soft drink": "soft_drink",
    "soda": "soft_drink",
    "french_fries": "fries",
    "french-fries": "fries",
    "french fries": "fries",
    "shawerma": "shawarma",
}


def _box_area(box) -> float:
    xyxy = box.xyxy[0].tolist()  # [x1, y1, x2, y2]
    x1, y1, x2, y2 = xyxy
    return max((x2 - x1), 0.0) * max((y2 - y1), 0.0)


def _normalize_label(label: str) -> str:
    return label.strip().lower().replace("-", "_").replace(" ", "_")


def _candidate_food_keys(label: str) -> List[str]:
    normalized = _normalize_label(label)
    alias = FOOD_ALIASES.get(label.lower()) or FOOD_ALIASES.get(normalized)
    keys = [normalized]
    if alias and alias not in keys:
        keys.append(alias)
    if normalized.endswith("es") and len(normalized) > 2:
        keys.append(normalized[:-2])
    if normalized.endswith("s") and len(normalized) > 1:
        keys.append(normalized[:-1])
    # Keep order while removing duplicates.
    seen = set()
    ordered = []
    for k in keys:
        if k not in seen:
            seen.add(k)
            ordered.append(k)
    return ordered


def _fallback_portion_ratio_by_image_area(box_area: float, img_area: float) -> float:
    # Continuous fallback ratio (no categorical buckets).
    if img_area <= 0 or FALLBACK_BASE_IMAGE_AREA_RATIO <= 0:
        return 1.0
    relative_area = box_area / img_area
    portion_ratio = relative_area / FALLBACK_BASE_IMAGE_AREA_RATIO
    return max(MIN_PORTION_RATIO, min(MAX_PORTION_RATIO, portion_ratio))


class FoodItemOut(BaseModel):
    food_id: int
    name: str
    confidence: float
    portion_ratio: float
    base_serving_size_g: float
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float


class AnalyzeResponse(BaseModel):
    items: List[FoodItemOut]
    summary: Dict[str, float]


@app.get("/")
def read_root():
    return {"status": "ok", "message": "AI Dietary System backend running"}


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    # 1. Validate content type
    if image.content_type not in ["image/jpeg", "image/png"]:
        raise HTTPException(status_code=400, detail="Invalid image type")

    # 2. Read image bytes and convert to PIL
    img_bytes = await image.read()
    try:
        pil_img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="Could not read image")

    img_w, img_h = pil_img.size
    img_area = img_w * img_h

    # 3. Run YOLOv8 inference
    try:
        results = model.predict(
    pil_img, 
    conf=0.20,      # Lower confidence
    iou=0.45,       # Allow overlap
    augment=True,   # FORCE multi-scale inference (Crucial fix)
    agnostic_nms=True # Prevents overlapping boxes of different classes from canceling each other
)[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Model inference failed: {e}")

    items: List[FoodItemOut] = []
    reference_area_px = 0.0

    # Find reference object (largest high-confidence box for the configured class)
    for box in results.boxes:
        cls_id = int(box.cls[0])
        label = results.names[cls_id].lower()
        conf = float(box.conf[0])
        if conf < MIN_CONF or _normalize_label(label) != _normalize_label(REFERENCE_OBJECT_LABEL):
            continue
        area = _box_area(box)
        if area > reference_area_px:
            reference_area_px = area

    # 4. For each detection, map to Food row and compute nutrition
    for box in results.boxes:
        cls_id = int(box.cls[0])
        label = results.names[cls_id]  # e.g., 'burger', 'fries'
        conf = float(box.conf[0])

        if conf < MIN_CONF:
            continue

        # Look up in Food table
        food: Food | None = None
        for key in _candidate_food_keys(label):
            food = db.query(Food).filter(Food.name == key).first()
            if food is not None:
                break
        if food is None:
            # Unknown class; skip this detection
            continue

        # Portion estimation by reference-object scaling when available.
        box_area = _box_area(box)
        if reference_area_px > 0 and REFERENCE_OBJECT_REAL_AREA_CM2 > 0 and BASE_FOOD_AREA_CM2 > 0:
            cm2_per_px = REFERENCE_OBJECT_REAL_AREA_CM2 / reference_area_px
            estimated_food_area_cm2 = box_area * cm2_per_px
            portion_ratio = estimated_food_area_cm2 / BASE_FOOD_AREA_CM2
            portion_ratio = max(MIN_PORTION_RATIO, min(MAX_PORTION_RATIO, portion_ratio))
        else:
            # Safe fallback if reference object is not present in the image.
            portion_ratio = _fallback_portion_ratio_by_image_area(box_area, img_area)

        calories = food.calories * portion_ratio
        protein_g = food.protein_g * portion_ratio
        carbs_g = food.carbs_g * portion_ratio
        fat_g = food.fat_g * portion_ratio

        item = FoodItemOut(
            food_id=food.food_id,
            name=food.name,
            confidence=conf,
            portion_ratio=portion_ratio,
            base_serving_size_g=food.serving_size,
            calories=calories,
            protein_g=protein_g,
            carbs_g=carbs_g,
            fat_g=fat_g,
        )
        items.append(item)

    # 5. Build summary
    if not items:
        summary = {
            "total_calories": 0.0,
            "total_protein_g": 0.0,
            "total_carbs_g": 0.0,
            "total_fat_g": 0.0,
        }
        return AnalyzeResponse(items=[], summary=summary)

    summary = {
        "total_calories": sum(i.calories for i in items),
        "total_protein_g": sum(i.protein_g for i in items),
        "total_carbs_g": sum(i.carbs_g for i in items),
        "total_fat_g": sum(i.fat_g for i in items),
    }

    return AnalyzeResponse(items=items, summary=summary)
