"""Build prediction for the next session from DB state."""
import logging
from typing import Optional, Tuple

from .database import db
from .predictor import predict_next
from .formatter import format_prediction

log = logging.getLogger(__name__)


async def build_next_prediction_message() -> Optional[Tuple[int, str, str, float]]:
    """Return (next_session, message, label, confidence) or None."""
    last = await db.last_session()
    if not last:
        return None

    next_session = int(last["session_number"]) + 1
    history = await db.recent_sessions(limit=300)
    seq = [h["tai_xiu"] for h in history]  # newest first
    label, conf = predict_next(seq)

    recent5 = seq[:5]
    stats = await db.prediction_stats()
    # last 20 outcomes for "Gần nhất"
    outcomes = await db.recent_prediction_outcomes(limit=20)
    wins = sum(1 for x in outcomes if x == 1)
    losses = sum(1 for x in outcomes if x == 0)

    msg = format_prediction(
        next_session=next_session,
        prev=last,
        recent5=recent5,
        pred_label=label,
        confidence=conf,
        wins=wins,
        losses=losses,
    )
    return next_session, msg, label, conf


async def record_prediction_outcome_if_any(new_session: dict):
    """When a new session arrives, grade the prediction we made for it."""
    pred = await db.get_prediction(new_session["session_number"])
    if not pred or pred.get("prediction_correct") is not None:
        return
    correct = pred["prediction"] == new_session["tai_xiu"]
    await db.update_prediction_outcome(new_session["session_number"], correct)
    log.info(
        "Graded #%s: predicted=%s actual=%s correct=%s",
        new_session["session_number"], pred["prediction"], new_session["tai_xiu"], correct,
    )
