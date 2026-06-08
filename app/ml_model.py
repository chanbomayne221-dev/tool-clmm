"""ML ensemble: RandomForest, XGBoost, LogisticRegression."""
import logging
from typing import List, Dict, Optional, Tuple
import numpy as np

from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression

try:
    from xgboost import XGBClassifier
    HAS_XGB = True
except Exception:  # pragma: no cover
    HAS_XGB = False

from .config import ML_MIN_SAMPLES

log = logging.getLogger(__name__)

WINDOW = 8  # use last 8 outcomes as features


def _seq_to_bits(seq_oldest_first: List[str]) -> List[int]:
    return [1 if s == "TAI" else 0 for s in seq_oldest_first]


def _build_dataset(history_newest_first: List[str]) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    oldest_first = list(reversed(history_newest_first))
    bits = _seq_to_bits(oldest_first)
    if len(bits) < WINDOW + 5:
        return None
    X, y = [], []
    for i in range(len(bits) - WINDOW):
        X.append(bits[i:i + WINDOW])
        y.append(bits[i + WINDOW])
    return np.array(X), np.array(y)


def ml_predict(history_newest_first: List[str]) -> Optional[Dict[str, float]]:
    """Return {'TAI': p, 'XIU': 1-p} or None if not enough data."""
    if len(history_newest_first) < ML_MIN_SAMPLES:
        return None
    ds = _build_dataset(history_newest_first)
    if ds is None:
        return None
    X, y = ds
    if len(set(y.tolist())) < 2:
        return None

    oldest_first = list(reversed(history_newest_first))
    bits = _seq_to_bits(oldest_first)
    x_now = np.array([bits[-WINDOW:]])

    probs = []
    try:
        rf = RandomForestClassifier(n_estimators=120, max_depth=6, random_state=42, n_jobs=1)
        rf.fit(X, y)
        probs.append(("RF", rf.predict_proba(x_now)[0], 0.35))
    except Exception as e:
        log.warning("RF failed: %s", e)

    if HAS_XGB:
        try:
            xgb = XGBClassifier(
                n_estimators=150, max_depth=4, learning_rate=0.1,
                use_label_encoder=False, eval_metric="logloss", verbosity=0, n_jobs=1,
            )
            xgb.fit(X, y)
            probs.append(("XGB", xgb.predict_proba(x_now)[0], 0.35))
        except Exception as e:
            log.warning("XGB failed: %s", e)

    try:
        lr = LogisticRegression(max_iter=400)
        lr.fit(X, y)
        probs.append(("LR", lr.predict_proba(x_now)[0], 0.30))
    except Exception as e:
        log.warning("LR failed: %s", e)

    if not probs:
        return None

    # classes_ order assumed [0,1] but be safe via sklearn API
    p_tai_total = 0.0
    w_total = 0.0
    for name, p, w in probs:
        # all our models trained with labels 0/1 in order
        p_tai_total += p[1] * w
        w_total += w
    p_tai = p_tai_total / w_total if w_total else 0.5
    return {"TAI": float(p_tai), "XIU": float(1 - p_tai)}
