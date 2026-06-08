"""Parse Telegram dice-game result messages."""
import re
from datetime import datetime
from typing import Optional, Dict, Any
import pytz

from .config import TZ

SESSION_RE = re.compile(r"#\s*(\d{3,})")
DICE_RE = re.compile(r"(?<!\d)([1-6])\s+([1-6])\s+([1-6])(?!\d)")


def classify_tai_xiu(total: int) -> str:
    # 4–10 = XỈU, 11–17 = TÀI (3 and 18 are typically bão; treat as edge)
    if 4 <= total <= 10:
        return "XIU"
    if 11 <= total <= 17:
        return "TAI"
    return "XIU" if total < 11 else "TAI"


def classify_chan_le(total: int) -> str:
    return "CHAN" if total % 2 == 0 else "LE"


def parse_result(text: str) -> Optional[Dict[str, Any]]:
    """Return parsed session dict or None if message isn't a result."""
    if not text:
        return None

    sm = SESSION_RE.search(text)
    dm = DICE_RE.search(text)
    if not sm or not dm:
        return None

    try:
        session_number = int(sm.group(1))
        dice = [int(dm.group(1)), int(dm.group(2)), int(dm.group(3))]
    except ValueError:
        return None

    total = sum(dice)
    tai_xiu = classify_tai_xiu(total)
    chan_le = classify_chan_le(total)
    tz = pytz.timezone(TZ)
    ts = datetime.now(tz).isoformat()

    return {
        "session_number": session_number,
        "dice_values": dice,
        "total": total,
        "tai_xiu": tai_xiu,
        "chan_le": chan_le,
        "timestamp": ts,
    }
