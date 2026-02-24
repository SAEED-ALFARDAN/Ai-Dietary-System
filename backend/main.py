from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Dict

from ultralytics import YOLO
from PIL import Image
import io

from sqlalchemy.orm import Session

from database import init_db, get_db, Food

app = FastAPI()

# Initialize DB
init_db()

# Load YOLOv8 model once at startup (path to your trained weights)
model = YOLO("/home/saeed/Projects/Ai-Dietary-System/models/best.pt")


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
        results = model(pil_img)[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Model inference failed: {e}")

    MIN_CONF = 0.4
    items: List[FoodItemOut] = []

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

        if relative_area < 0.10:
            portion_ratio = 0.75  # small
        elif relative_area < 0.25:
            portion_ratio = 1.0   # medium
        else:
            portion_ratio = 1.5   # large

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
