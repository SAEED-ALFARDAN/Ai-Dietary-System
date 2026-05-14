import os
import time
import gdown

MODEL_PATH = os.path.join(os.path.dirname(__file__), "models", "last.pt")

if not os.path.exists(MODEL_PATH):
    print("Model not found — downloading from Google Drive...")
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    gdown.download(
        f"https://drive.google.com/uc?id={os.getenv('MODEL_FILE_ID')}",
        MODEL_PATH,
        quiet=False,
    )
    print("Model downloaded successfully.")

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from statistics import median
import logging
import io

import cv2
import numpy as np
from ultralytics import YOLO
from PIL import Image
from sqlalchemy.orm import Session

from database import init_db, get_db, Food
import importlib.util

seed_path = os.path.join(os.path.dirname(__file__), "seed.py")
spec = importlib.util.spec_from_file_location("seed_local", seed_path)
seed_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed_module)


# ── logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ── app & db ──────────────────────────────────────────────────────────────────
app = FastAPI()
init_db()
seed_module.seed_food_data()
print("SEED MODULE PATH:", seed_path)


# ── models ────────────────────────────────────────────────────────────────────
FOOD_MODEL_PATH = os.getenv(
    "FOOD_MODEL_PATH",
    os.path.join(os.path.dirname(__file__), "models", "last.pt"),
)
food_model = YOLO(FOOD_MODEL_PATH)

# Pretrained COCO YOLOv8n — used only for cutlery/bowl reference detection
ref_model = YOLO("yolov8n.pt")

logger.info("Food model classes:      %s", food_model.names)
logger.info("Reference model classes: %s", ref_model.names)


# ── inference / portion config ────────────────────────────────────────────────
MIN_CONF_FOOD             = float(os.getenv("MIN_CONF_FOOD",             "0.20"))
MIN_CONF_REF              = float(os.getenv("MIN_CONF_REF",              "0.30"))
MIN_PORTION_RATIO         = float(os.getenv("MIN_PORTION_RATIO",         "0.5"))
MAX_PORTION_RATIO         = float(os.getenv("MAX_PORTION_RATIO",         "2.0"))
BASE_FOOD_AREA_CM2        = float(os.getenv("BASE_FOOD_AREA_CM2",        "100.0"))
FALLBACK_BASE_IMAGE_RATIO = float(os.getenv("FALLBACK_BASE_IMAGE_RATIO", "0.16"))
OUTLIER_RATIO_THRESHOLD   = float(os.getenv("OUTLIER_RATIO_THRESHOLD",   "1.4"))

# When the same food label appears multiple times (e.g. 3 chicken pieces),
# this is the IoU threshold below which we treat them as SEPARATE pieces.
# Set high (0.80) so only heavily overlapping boxes are collapsed.
FOOD_DEDUP_IOU_THRESHOLD  = float(os.getenv("FOOD_DEDUP_IOU_THRESHOLD",  "0.80"))


# ── Hough / ellipse plate detection config ────────────────────────────────────
HOUGH_WORK_SIZE          = int(os.getenv("HOUGH_WORK_SIZE",           "640"))
PLATE_REAL_AREA_CM2      = float(os.getenv("PLATE_REAL_AREA_CM2",     "615.0"))
PLATE_RELIABILITY        = float(os.getenv("PLATE_RELIABILITY",         "0.45"))
HOUGH_PARAM1             = float(os.getenv("HOUGH_PARAM1",             "60.0"))
HOUGH_PARAM2             = float(os.getenv("HOUGH_PARAM2",             "38.0"))
PLATE_MIN_IMAGE_FRACTION = float(os.getenv("PLATE_MIN_IMAGE_FRACTION", "0.12"))
PLATE_MAX_IMAGE_FRACTION = float(os.getenv("PLATE_MAX_IMAGE_FRACTION", "0.80"))

# Rim color: loosened for cream/beige/shadowed white plates
PLATE_RIM_MAX_SATURATION = int(os.getenv("PLATE_RIM_MAX_SATURATION",   "85"))
PLATE_RIM_MIN_VALUE      = int(os.getenv("PLATE_RIM_MIN_VALUE",        "100"))
PLATE_RIM_MIN_RATIO      = float(os.getenv("PLATE_RIM_MIN_RATIO",      "0.20"))

# Ellipse fallback config
ELLIPSE_THRESH_BRIGHT    = int(os.getenv("ELLIPSE_THRESH_BRIGHT",      "185"))
ELLIPSE_MAX_ASPECT       = float(os.getenv("ELLIPSE_MAX_ASPECT",       "2.8"))
ELLIPSE_MIN_COVERAGE     = float(os.getenv("ELLIPSE_MIN_COVERAGE",     "0.06"))


# ── COCO reference object registry ───────────────────────────────────────────
@dataclass
class ReferenceObject:
    area_cm2: float
    reliability: float
    min_image_fraction: float


REFERENCE_REGISTRY: Dict[str, ReferenceObject] = {
    "bowl":  ReferenceObject(area_cm2=250.0, reliability=0.90, min_image_fraction=0.020),
    "fork":  ReferenceObject(area_cm2=16.0,  reliability=0.60, min_image_fraction=0.001),
    "knife": ReferenceObject(area_cm2=18.0,  reliability=0.60, min_image_fraction=0.001),
    "spoon": ReferenceObject(area_cm2=14.0,  reliability=0.55, min_image_fraction=0.001),
}

# Per-label confidence floors — thin objects score low in COCO YOLOv8n
REF_CONF_OVERRIDES: Dict[str, float] = {
    "knife": 0.18,
    "spoon": 0.20,
    "fork":  0.20,
    "bowl":  0.30,
}

# Fork→knife reclassification: a fork with aspect ratio > this is a knife
FORK_TO_KNIFE_ASPECT = float(os.getenv("FORK_TO_KNIFE_ASPECT", "5.5"))


# ── per-food top-view baseline areas (cm²) ────────────────────────────────────
FOOD_BASE_AREAS_CM2: Dict[str, float] = {
    "burger":        100.0,
    "fries":         140.0,
    "pizza":         180.0,
    "rice":          150.0,
    "salad":         170.0,
    "shawarma":      120.0,
    "fried_chicken": 130.0,
    "soft_drinks":    80.0,
}
FOOD_MAX_RATIOS: Dict[str, float] = {
    "burger":        1.8,
    "fried_chicken": 1.7,
    "pizza":         2.0,
    "fries":         2.2,
    "shawarma":      1.8,
    "soft_drinks":   3.0,
    "rice":          2.0,
    "salad":         2.3,
}

# ── label aliases ─────────────────────────────────────────────────────────────
FOOD_ALIASES: Dict[str, str] = {
    "soft drinks":   "soft_drinks",
    "soft drink":    "soft_drinks",
    "soft_drink":    "soft_drinks",
    "softdrinks":    "soft_drinks",
    "softdrink":     "soft_drinks",
    "soft-drinks":   "soft_drinks",
    "soft-drink":    "soft_drinks",
    "soda":          "soft_drinks",
    "fried chicken": "fried_chicken",
    "fried-chicken": "fried_chicken",
    "friedchicken":  "fried_chicken",
    "french_fries":  "fries",
    "french-fries":  "fries",
    "french fries":  "fries",
    "shawerma":      "shawarma",
}


# ── generic helpers ───────────────────────────────────────────────────────────

def _box_area_px(box) -> float:
    x1, y1, x2, y2 = box.xyxy[0].tolist()
    return max(x2 - x1, 0.0) * max(y2 - y1, 0.0)


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
    seen, ordered = set(), []
    for k in keys:
        if k not in seen:
            seen.add(k)
            ordered.append(k)
    return ordered


def _fallback_portion_ratio(
    box_area: float,
    img_area: float,
    max_ratio: float,
) -> float:
    if img_area <= 0 or FALLBACK_BASE_IMAGE_RATIO <= 0:
        return 1.0

    raw_ratio = (box_area / img_area) / FALLBACK_BASE_IMAGE_RATIO

    # Nonlinear compression prevents huge calorie explosions
    ratio = raw_ratio ** 0.65

    return max(MIN_PORTION_RATIO, min(max_ratio, ratio))


def _compute_iou(b1, b2) -> float:
    """Compute IoU between two YOLO boxes."""
    x1a, y1a, x2a, y2a = b1.xyxy[0].tolist()
    x1b, y1b, x2b, y2b = b2.xyxy[0].tolist()
    inter_x = max(0.0, min(x2a, x2b) - max(x1a, x1b))
    inter_y = max(0.0, min(y2a, y2b) - max(y1a, y1b))
    inter   = inter_x * inter_y
    area_a  = max(x2a - x1a, 0) * max(y2a - y1a, 0)
    area_b  = max(x2b - x1b, 0) * max(y2b - y1b, 0)
    union   = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


# ── plate rim color check (multi-ring) ───────────────────────────────────────

def _is_plate_like(img_np: np.ndarray, cx: int, cy: int, r: int) -> bool:
    """
    Multi-ring HSV rim check at 88%, 93%, 97% of detected radius.
    Accepts if ANY ring has >= PLATE_RIM_MIN_RATIO of light pixels.

    Why multi-ring: food overhanging the plate hits inner rings.
    Only the outermost visible arc reveals the white/cream plate rim.

    Donuts have brown/glazed rings on ALL levels → still fail (S ≈ 100-180).
    """
    hsv = cv2.cvtColor(img_np, cv2.COLOR_RGB2HSV)
    h_img, w_img = hsv.shape[:2]
    total_samples = 48

    for ring_frac in (0.88, 0.93, 0.97):
        sample_r = max(1, int(r * ring_frac))
        plate_pixels = 0
        for i in range(total_samples):
            angle = 2.0 * np.pi * i / total_samples
            px = int(cx + sample_r * np.cos(angle))
            py = int(cy + sample_r * np.sin(angle))
            if 0 <= px < w_img and 0 <= py < h_img:
                _, s, v = hsv[py, px]
                if s < PLATE_RIM_MAX_SATURATION and v > PLATE_RIM_MIN_VALUE:
                    plate_pixels += 1
        ratio = plate_pixels / total_samples
        logger.debug("Plate rim ring=%.2f: %.0f%% light (need>=%.0f%%)",
                     ring_frac, ratio * 100, PLATE_RIM_MIN_RATIO * 100)
        if ratio >= PLATE_RIM_MIN_RATIO:
            logger.info("Plate rim PASSED ring=%.2f (%.0f%% light)", ring_frac, ratio * 100)
            return True

    logger.info("Plate rim FAILED all rings")
    return False


# ── ellipse fallback for angled / heavily-loaded plates ──────────────────────

def _detect_plate_ellipse(
    img_np: np.ndarray,
    orig_w: int,
    orig_h: int,
    scale_factor: float,
) -> Optional[Tuple[float, float]]:
    """
    Fallback: fit an ellipse to the largest bright contour.

    Used when HoughCircles fails because:
      (a) the plate is viewed at an angle (looks elliptical, not circular), OR
      (b) the plate rim is mostly covered by food (only small arc visible).

    Steps:
      1. Threshold at ELLIPSE_THRESH_BRIGHT (bright = white/cream rim)
      2. Morphological CLOSE with large kernel reconnects rim arcs
         broken by overhanging food
      3. Find the largest contour that fits a plausible ellipse
      4. Validate coverage and aspect ratio
      5. Return (estimated_area_px, confidence)
    """
    gray  = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
    blur  = cv2.GaussianBlur(gray, (9, 9), 2)
    _, thresh = cv2.threshold(blur, ELLIPSE_THRESH_BRIGHT, 255, cv2.THRESH_BINARY)

    # Large kernel reconnects broken rim arcs from food overhang
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (21, 21))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    # Also dilate slightly to bridge thin gaps
    dilated = cv2.dilate(closed, kernel, iterations=1)

    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        logger.debug("Ellipse fallback: no contours found")
        return None

    h_small, w_small = img_np.shape[:2]
    img_area_small   = h_small * w_small
    orig_img_area    = orig_w * orig_h

    best = None
    for cnt in contours:
        if len(cnt) < 5:
            continue
        area = cv2.contourArea(cnt)
        if area / img_area_small < ELLIPSE_MIN_COVERAGE:
            continue

        try:
            ellipse = cv2.fitEllipse(cnt)
        except cv2.error:
            continue

        (cx, cy), (ma, mi), _ = ellipse
        if mi < 1:
            continue
        aspect = ma / mi
        if aspect > ELLIPSE_MAX_ASPECT:
            continue

        a_orig = (ma / 2.0) / scale_factor
        b_orig = (mi / 2.0) / scale_factor
        plate_area_px = float(np.pi * a_orig * b_orig)
        coverage = plate_area_px / orig_img_area

        if not (PLATE_MIN_IMAGE_FRACTION <= coverage <= PLATE_MAX_IMAGE_FRACTION):
            continue

        if best is None or area > best[0]:
            best = (area, plate_area_px, aspect)

    if best is None:
        logger.debug("Ellipse fallback: no valid plate ellipse found")
        return None

    _, plate_area_px, aspect = best
    aspect_score = 1.0 - min(aspect - 1.0, 1.0)
    confidence   = round(0.55 * aspect_score + 0.45, 3)
    logger.info("Ellipse plate: area=%.0fpx  aspect=%.2f  conf=%.3f",
                plate_area_px, aspect, confidence)
    return plate_area_px, confidence


# ── Hough plate detection (primary + ellipse fallback) ───────────────────────

def detect_plate_hough(pil_img: Image.Image) -> Optional[Tuple[float, float]]:
    """
    Detect plate area in pixels using two methods in sequence:

    PRIMARY — HoughCircles (fast, works for front-on plates):
      Downscales to HOUGH_WORK_SIZE (~110ms regardless of source resolution).
      Applies geometry check (coverage) then multi-ring HSV rim color check.
      Rejects non-plate circles (donuts, cups) via color validation.

    FALLBACK — Ellipse fitting (_detect_plate_ellipse):
      Triggered when Hough fails due to:
        - Plate at an angle (elliptical silhouette, not circular)
        - Heavily loaded plate with most rim covered by food
        - HOUGH_PARAM2 too strict to detect the weak rim gradient
      Uses morphological reconnection of broken rim arcs.

    Returns (plate_area_px_original_coords, confidence) or None.
    """
    orig_w, orig_h = pil_img.size
    orig_img_area  = orig_w * orig_h

    scale_factor = HOUGH_WORK_SIZE / max(orig_w, orig_h)
    small_w = max(1, int(orig_w * scale_factor))
    small_h = max(1, int(orig_h * scale_factor))
    small   = pil_img.resize((small_w, small_h), Image.LANCZOS)

    img_np = np.array(small)
    gray   = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
    blur   = cv2.GaussianBlur(gray, (9, 9), 2)

    h, w       = gray.shape
    short_side = min(h, w)
    min_r      = int(short_side * 0.15)
    max_r      = int(short_side * 0.55)
    min_dist   = int(short_side * 0.40)

    circles = cv2.HoughCircles(
        blur,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=min_dist,
        param1=HOUGH_PARAM1,
        param2=HOUGH_PARAM2,
        minRadius=min_r,
        maxRadius=max_r,
    )

    if circles is None:
        logger.debug("Hough: no circle — trying ellipse fallback")
        return _detect_plate_ellipse(img_np, orig_w, orig_h, scale_factor)

    cx_s, cy_s, r_s = np.round(circles[0, 0]).astype(int)

    r_orig        = r_s / scale_factor
    plate_area_px = float(np.pi * r_orig * r_orig)
    coverage      = plate_area_px / orig_img_area

    if not (PLATE_MIN_IMAGE_FRACTION <= coverage <= PLATE_MAX_IMAGE_FRACTION):
        logger.debug("Hough: rejected coverage=%.3f — trying ellipse", coverage)
        return _detect_plate_ellipse(img_np, orig_w, orig_h, scale_factor)

    if not _is_plate_like(img_np, cx_s, cy_s, r_s):
        logger.info("Hough: rim color failed — trying ellipse")
        return _detect_plate_ellipse(img_np, orig_w, orig_h, scale_factor)

    dist_from_centre = float(np.sqrt((cx_s - w / 2) ** 2 + (cy_s - h / 2) ** 2))
    max_dist         = float(np.sqrt((w / 2) ** 2 + (h / 2) ** 2))
    centre_score     = 1.0 - (dist_from_centre / (max_dist + 1e-9))

    mid_r      = (min_r + max_r) / 2
    size_score = 1.0 - abs(r_s - mid_r) / ((max_r - min_r) / 2 + 1e-9)
    size_score = max(0.0, min(1.0, size_score))

    confidence = round(0.6 * centre_score + 0.4 * size_score, 3)
    logger.info("Hough plate: r=%dpx(small)→%.0fpx(orig) coverage=%.3f conf=%.3f",
                r_s, r_orig, coverage, confidence)
    return plate_area_px, confidence


# ── scale estimation ──────────────────────────────────────────────────────────

@dataclass
class ScaleEstimate:
    pixels_per_cm2: float
    confidence: float
    n_references: int
    used_labels: List[str] = field(default_factory=list)


def _reject_outliers(
    candidates: List[Tuple[float, float, str]],
) -> List[Tuple[float, float, str]]:
    if len(candidates) < 3:
        return candidates
    med = median(c[0] for c in candidates)
    kept = [
        c for c in candidates
        if (max(c[0], med) / max(min(c[0], med), 1e-9)) <= OUTLIER_RATIO_THRESHOLD
    ]
    dropped = [c[2] for c in candidates if c not in kept]
    if dropped:
        logger.info("Outlier rejection dropped: %s", dropped)
    return kept if kept else candidates


def _deduplicate_ref_boxes(boxes, names: dict) -> list:
    """
    Keep only the single highest-confidence detection per COCO label.
    Stops 4× fork detections from swamping the scale estimate.
    """
    best: Dict[str, Tuple[float, object]] = {}
    for box in boxes:
        label = _normalize_label(names[int(box.cls[0])])
        conf  = float(box.conf[0])
        if label not in best or conf > best[label][0]:
            best[label] = (conf, box)
    return [box for _, box in best.values()]


def _deduplicate_food_boxes(boxes, names: dict) -> list:
    """
    Collapse food boxes of the same label only when IoU > FOOD_DEDUP_IOU_THRESHOLD.

    CRITICAL: The threshold is intentionally HIGH (0.80) so that separate
    chicken pieces — which may touch but do not heavily overlap — are kept
    as distinct detections. Only near-duplicate boxes of the exact same
    object are removed.

    Sort order: highest confidence first, so the best box survives.
    """
    kept = []
    for box in sorted(boxes, key=lambda b: float(b.conf[0]), reverse=True):
        label = _normalize_label(names[int(box.cls[0])])
        duplicate = False
        for k in kept:
            if _normalize_label(names[int(k.cls[0])]) != label:
                continue
            if _compute_iou(box, k) > FOOD_DEDUP_IOU_THRESHOLD:
                duplicate = True
                break
        if not duplicate:
            kept.append(box)
    return kept


def build_scale_estimate(
    ref_results,
    pil_img: Image.Image,
    img_area: float,
) -> Optional[ScaleEstimate]:
    """
    Build pixels-per-cm² scale from:
      1. COCO cutlery/bowl (deduplicated, per-label conf floors, fork→knife fix)
      2. Plate area via Hough circle + ellipse fallback
    """
    candidates: List[Tuple[float, float, str]] = []

    deduped_boxes = _deduplicate_ref_boxes(ref_results.boxes, ref_results.names)

    for box in deduped_boxes:
        cls_id = int(box.cls[0])
        label  = _normalize_label(ref_results.names[cls_id])
        conf   = float(box.conf[0])

        # Reclassify elongated "fork" detections as knife
        if label == "fork":
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            w_box  = max(x2 - x1, 1.0)
            h_box  = max(y2 - y1, 1.0)
            aspect = max(w_box, h_box) / min(w_box, h_box)
            if aspect > FORK_TO_KNIFE_ASPECT:
                logger.debug("fork→knife reclassified: aspect=%.1f", aspect)
                label = "knife"

        ref = REFERENCE_REGISTRY.get(label)
        if ref is None:
            continue

        min_conf = REF_CONF_OVERRIDES.get(label, MIN_CONF_REF)
        if conf < min_conf:
            logger.debug("Skipping %s — conf=%.3f < %.3f", label, conf, min_conf)
            continue

        area_px = _box_area_px(box)
        if area_px <= 0:
            continue

        if img_area > 0 and (area_px / img_area) < ref.min_image_fraction:
            logger.debug("Skipping %s — occluded fraction=%.4f", label, area_px / img_area)
            continue

        scale  = area_px / ref.area_cm2
        weight = conf * ref.reliability
        candidates.append((scale, weight, label))
        logger.debug("COCO ref: %s | %.1f px/cm² | w=%.2f", label, scale, weight)

    plate_result = detect_plate_hough(pil_img)
    if plate_result is not None:
        plate_area_px, hough_conf = plate_result
        plate_scale  = plate_area_px / PLATE_REAL_AREA_CM2
        plate_weight = hough_conf * PLATE_RELIABILITY * 0.7
        candidates.append((plate_scale, plate_weight, "plate_hough"))
        logger.info("Plate: %.1f px/cm² | w=%.2f", plate_scale, plate_weight)

    if not candidates:
        logger.info("No reference sources — image-area fallback")
        return None

    candidates = _reject_outliers(candidates)

    total_weight   = sum(w for _, w, _ in candidates)
    weighted_scale = sum(s * w for s, w, _ in candidates) / total_weight

    mean_weight = total_weight / len(candidates)
    n_factor    = min(len(candidates) / 3.0, 1.0)
    confidence  = round(mean_weight * (0.5 + 0.5 * n_factor), 3)
    used_labels = [lbl for _, _, lbl in candidates]

    logger.info("Final scale: %.1f px/cm² | conf=%.3f | sources=%s",
                weighted_scale, confidence, used_labels)
    return ScaleEstimate(
        pixels_per_cm2=weighted_scale,
        confidence=confidence,
        n_references=len(candidates),
        used_labels=used_labels,
    )


def _compute_portion_ratio(
    box_area: float,
    img_area: float,
    food_base_cm2: float,
    scale: Optional[ScaleEstimate],
    max_ratio: float,
) -> float:

    fallback = _fallback_portion_ratio(
        box_area,
        img_area,
        max_ratio,
    )

    if scale is None:
        return fallback

    # Convert pixels -> estimated cm²
    estimated_cm2 = box_area / max(scale.pixels_per_cm2, 1e-6)

    # Raw geometric ratio
    raw_ratio = estimated_cm2 / max(food_base_cm2, 1e-6)

    # Nonlinear compression
    ref_ratio = raw_ratio ** 0.65

    ref_ratio = max(MIN_PORTION_RATIO, min(max_ratio, ref_ratio))

    # Blend trusted reference scaling with image fallback
    blended = (
        scale.confidence * ref_ratio
        + (1.0 - scale.confidence) * fallback
    )

    return max(MIN_PORTION_RATIO, min(max_ratio, blended))


# ── schema ────────────────────────────────────────────────────────────────────

class FoodItemOut(BaseModel):
    food_id: int
    name: str
    confidence: float
    portion_ratio: float
    base_serving_size_g: float
    estimated_weight_g: float
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float


class AnalyzeResponse(BaseModel):
    items: List[FoodItemOut]
    detected_count: int
    summary: Dict[str, float]
    scale_confidence: Optional[float] = None
    scale_references: Optional[List[str]] = None
    processing_time: float  # Server-side E2E latency in seconds


# ── routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def read_root():
    return {
        "status": "ok",
        "message": "AI Dietary System backend running",
        "food_model_classes": food_model.names,
        "ref_model_classes": {
            k: v for k, v in ref_model.names.items()
            if _normalize_label(v) in REFERENCE_REGISTRY
        },
    }


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    # 1. Start server-side timer
    start_server = time.time()

    # 2. Validate
    if image.content_type not in ["image/jpeg", "image/png"]:
        raise HTTPException(status_code=400, detail="Invalid image type. Use JPEG or PNG.")

    # 3. Decode
    img_bytes = await image.read()
    try:
        pil_img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="Could not decode image.")

    img_w, img_h = pil_img.size
    img_area = img_w * img_h

    # 4a. Food model — custom YOLOv8m
    try:
        food_results = food_model.predict(
            pil_img,
            conf=0.25,
            iou=0.45,
            augment=False,
            agnostic_nms=False,
        )[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Food model inference failed: {e}")

    # 4b. Reference model — COCO YOLOv8n
    try:
        ref_results = ref_model.predict(
            pil_img,
            conf=min(REF_CONF_OVERRIDES.values()),  # 0.18 — catch low-scoring knives
            iou=0.45,
            augment=False,
        )[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reference model inference failed: {e}")

    # 5. Build scale
    scale = build_scale_estimate(ref_results, pil_img, img_area)

    # 6. Score food detections
    # IoU dedup uses HIGH threshold (0.80) so separate chicken pieces
    # are kept as distinct items — only near-identical boxes are collapsed.
    items: List[FoodItemOut] = []
    deduped_food = _deduplicate_food_boxes(food_results.boxes, food_results.names)

    logger.info(
        "Food detections: raw=%d  after_dedup=%d",
        len(food_results.boxes), len(deduped_food),
    )

    for box in deduped_food:
        cls_id = int(box.cls[0])
        label  = food_results.names[cls_id]
        conf   = float(box.conf[0])

        if conf < MIN_CONF_FOOD:
            continue

        food: Optional[Food] = None
        for key in _candidate_food_keys(label):
            food = db.query(Food).filter(Food.name == key).first()
            if food is not None:
                break
        if food is None:
            logger.debug("No DB entry for '%s' — skipping", label)
            continue

        box_area = _box_area_px(box)
        norm     = _normalize_label(label)
        canon    = FOOD_ALIASES.get(label.lower()) or FOOD_ALIASES.get(norm) or norm
        base_cm2 = FOOD_BASE_AREAS_CM2.get(canon, BASE_FOOD_AREA_CM2)
        max_ratio = FOOD_MAX_RATIOS.get(canon, MAX_PORTION_RATIO)

        portion_ratio = _compute_portion_ratio(
            box_area,
            img_area,
            base_cm2,
            scale,
            max_ratio,
        )

        items.append(FoodItemOut(
            food_id=food.food_id,
            name=food.name,
            confidence=round(conf, 4),
            portion_ratio=round(portion_ratio, 4),
            base_serving_size_g=food.serving_size,
            estimated_weight_g=round(food.serving_size * portion_ratio, 1),
            calories=round(food.calories   * portion_ratio, 2),
            protein_g=round(food.protein_g * portion_ratio, 2),
            carbs_g=round(food.carbs_g     * portion_ratio, 2),
            fat_g=round(food.fat_g         * portion_ratio, 2),
        ))

    # 7. Summary
    summary = {
        "total_calories":  round(sum(i.calories  for i in items), 2),
        "total_protein_g": round(sum(i.protein_g for i in items), 2),
        "total_carbs_g":   round(sum(i.carbs_g   for i in items), 2),
        "total_fat_g":     round(sum(i.fat_g     for i in items), 2),
    }

    # 8. Stop server-side timer
    server_duration = time.time() - start_server

    return AnalyzeResponse(
        items=items,
        detected_count=len(items),
        summary=summary,
        scale_confidence=scale.confidence if scale else None,
        scale_references=scale.used_labels if scale else None,
        processing_time=round(server_duration, 3),
    )