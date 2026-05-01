from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Dict

from ultralytics import YOLO
from PIL import Image
import io
from statistics import median

from sqlalchemy.orm import Session

from database import init_db, get_db, Food

app = FastAPI()

# Initialize DB
init_db()

# Load YOLOv8 model once at startup (path to your trained weights)
model = YOLO("C:\\Users\\igohs\\Desktop\\Ai-Dietary-System\\models\\last.pt")

# Real-world top-view reference areas in cm^2 for objects that can appear in scene.
REFERENCE_OBJECT_AREAS_CM2 = {
    "spoon": 14.0,
    "fork": 16.0,
    "knife": 18.0,
    "plate": 490.0,  # ~25 cm diameter plate
    "credit_card": 46.0,
}

# Approximate per-serving visible area (top view) for each food in cm^2.
# This anchors portion_ratio to physical scale instead of image-relative area.
FOOD_BASE_AREAS_CM2 = {
    "burger": 100.0,
    "fries": 140.0,
    "pizza": 180.0,
    "rice": 150.0,
    "salad": 170.0,
}


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

    MIN_CONF = 0.4
    items: List[FoodItemOut] = []

    # Build image scale from any detected reference object:
    # pixels_per_cm2 = detected_box_area_px / known_reference_area_cm2
    scale_candidates: List[float] = []
    for ref_box in results.boxes:
        ref_cls_id = int(ref_box.cls[0])
        ref_label = results.names[ref_cls_id].lower()
        ref_conf = float(ref_box.conf[0])
        if ref_conf < MIN_CONF:
            continue

        known_ref_area_cm2 = REFERENCE_OBJECT_AREAS_CM2.get(ref_label)
        if known_ref_area_cm2 is None:
            continue

        rx1, ry1, rx2, ry2 = ref_box.xyxy[0].tolist()
        ref_box_area_px = max((rx2 - rx1), 0) * max((ry2 - ry1), 0)
        if ref_box_area_px <= 0:
            continue

        scale_candidates.append(ref_box_area_px / known_ref_area_cm2)

    pixels_per_cm2 = median(scale_candidates) if scale_candidates else None

    # 4. For each detection, map to Food row and compute nutrition
    for box in results.boxes:
        cls_id = int(box.cls[0])
        label = results.names[cls_id]  # e.g., 'burger', 'fries'
        conf = float(box.conf[0])

        if conf < MIN_CONF:
            continue

        key = label.lower()

        # Look up in Food table
        food: Food | None = db.query(Food).filter(Food.name == key).first()
        if food is None:
            # Unknown class; skip this detection
            continue

        # Portion estimation by relative bounding box area (simple heuristic)
        xyxy = box.xyxy[0].tolist()  # [x1, y1, x2, y2]
        x1, y1, x2, y2 = xyxy
        box_area = max((x2 - x1), 0) * max((y2 - y1), 0)
        relative_area = box_area / img_area if img_area > 0 else 0.0

        # Portion estimation by reference-object scaling.
        # If a reference object and food baseline area are available:
        # food_area_cm2 = box_area_px / pixels_per_cm2
        # portion_ratio = food_area_cm2 / food_base_area_cm2
        food_base_area_cm2 = FOOD_BASE_AREAS_CM2.get(key)
        if pixels_per_cm2 and food_base_area_cm2:
            estimated_food_area_cm2 = box_area / pixels_per_cm2
            portion_ratio = estimated_food_area_cm2 / food_base_area_cm2
            # Keep within a practical serving range.
            portion_ratio = max(0.5, min(2.5, portion_ratio))
        else:
            # If no reference object is detected, fall back to neutral serving.
            portion_ratio = 1.0

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
