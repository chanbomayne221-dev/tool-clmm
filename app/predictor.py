"""Combine logic + ML. Output prediction with bounded confidence."""
from typing import List, Dict, Tuple

from .logic_engine import logic_predict
from .ml_model import ml_predict
from .config import MIN_CONFIDENCE, MAX_CONFIDENCE


def predict_next(history_newest_first: List[str]) -> Tuple[str, float]:
    """Return (label 'TAI'|'XIU', confidence in [MIN_CONFIDENCE, MAX_CONFIDENCE])."""
    logic = logic_predict(history_newest_first)
    ml = ml_predict(history_newest_first)

    if ml is None:
        # 100% logic when not enough samples for ML
        p_tai = logic["TAI"]
    else:
        # Ensemble weights: RF 35%, XGB 35%, Logic 30% (ML output already RF+XGB+LR blend)
        # We approximate: combined = 0.7 * ml + 0.3 * logic
        p_tai = 0.7 * ml["TAI"] + 0.3 * logic["TAI"]

    label = "TAI" if p_tai >= 0.5 else "XIU"
    conf = p_tai if label == "TAI" else 1 - p_tai
    conf = max(MIN_CONFIDENCE, min(MAX_CONFIDENCE, conf))
    return label, float(conf)
