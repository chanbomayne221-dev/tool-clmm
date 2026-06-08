"""Build prediction for the next session from DB state.

Predictions are DETERMINISTIC + CACHED per target_session:
the first time we predict for #N we save it; every subsequent call
for the same #N returns the exact same prediction.
"""
import logging
from typing import Optional, Tuple

from .database import db
from .predictor import predict_next
from .formatter import format_prediction
from .telethon_client import fetch_latest_sessions

log = logging.getLogger(__name__)


async def build_next_prediction_message(
    refresh_from_source: bool = False,
) -> Optional[Tuple[int, str, str, float]]:
    """Return (next_session, message, label, confidence) or None.

    If refresh_from_source=True, fetches latest results from the source
    Telegram room first (used when the user presses the button).
    """
    # 1. Try to refresh history from source room in realtime.
    if refresh_from_source:
        await fetch_latest_sessions(limit=30)

    last = await db.last_session()

    # 2. If DB still empty, do a bigger backfill scan and try again.
    if not last:
        await fetch_latest_sessions(limit=50)
        last = await db.last_session()
        if not last:
            return None

    target = int(last["session_number"]) + 1

    # 3. CACHED: if we already predicted for this target session, reuse it.
    existing = await db.get_prediction(target)
    if existing:
        label = existing["prediction"]
        conf = float(existing["confidence"])
    else:
        history = await db.recent_sessions(limit=300)
        seq = [h["tai_xiu"] for h in history]  # newest first
        label, conf = predict_next(seq)
        # Save immediately so subsequent calls return the same answer.
        await db.insert_prediction(target, label, conf)

    history = await db.recent_sessions(limit=10)
    seq = [h["tai_xiu"] for h in history]
    recent5 = seq[:5]
    outcomes = await db.recent_prediction_outcomes(limit=20)
    wins = sum(1 for x in outcomes if x == 1)
    losses = sum(1 for x in outcomes if x == 0)

    msg = format_prediction(
        next_session=target,
        prev=last,
        recent5=recent5,
        pred_label=label,
        confidence=conf,
        wins=wins,
        losses=losses,
    )
    return target, msg, label, conf


async def record_prediction_outcome_if_any(new_session: dict):
    """When a new session arrives, grade the prediction we made for it."""
    pred = await db.get_prediction(new_session["session_number"])
    if not pred or pred.get("prediction_correct") is not None:
        return
    correct = pred["prediction"] == new_session["tai_xiu"]
    await db.update_prediction_outcome(new_session["session_number"], correct)
    log.info(
        "Graded #%s: predicted=%s actual=%s correct=%s",
        new_session["session_number"], pred["prediction"],
        new_session["tai_xiu"], correct,
    )
