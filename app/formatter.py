"""Format prediction messages."""
from typing import Dict, List, Any


TAI_EMOJI = "🩵"
XIU_EMOJI = "❤️"


def label_emoji(lbl: str) -> str:
    return TAI_EMOJI if lbl == "TAI" else XIU_EMOJI


def label_text(lbl: str) -> str:
    return "TÀI" if lbl == "TAI" else "XỈU"


def chan_le_text(cl: str) -> str:
    return "CHẴN" if cl == "CHAN" else "LẺ"


def confidence_bar(conf: float, width: int = 10) -> str:
    filled = max(1, min(width, round(conf * width)))
    return "[" + "█" * filled + "░" * (width - filled) + "]"


def format_prediction(
    next_session: int,
    prev: Dict[str, Any],
    recent5: List[str],
    pred_label: str,
    confidence: float,
    wins: int,
    losses: int,
) -> str:
    dice = list(map(int, prev["dice_values"].split(",")))
    prev_line = f"{dice[0]} • {dice[1]} • {dice[2]} = {prev['total']}"
    prev_tx = f"{label_emoji(prev['tai_xiu'])} {label_text(prev['tai_xiu'])} {chan_le_text(prev['chan_le'])}"

    recent_emojis = " ➔ ".join(label_emoji(x) for x in recent5) if recent5 else "—"
    bar = confidence_bar(confidence)
    conf_pct = f"{confidence * 100:.1f}%"

    msg = (
        f"🎰 PHIÊN #{next_session}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📊 Phiên trước:\n"
        f"{prev_line}\n"
        f"{prev_tx}\n\n"
        "📊 5 phiên gần:\n"
        f"{recent_emojis}\n\n"
        "🎯 Dự đoán:\n"
        f"{label_emoji(pred_label)} {label_text(pred_label)} ({conf_pct})\n\n"
        "⚡ Lực cầu:\n"
        f"{bar}\n\n"
        "📈 Gần nhất:\n"
        f"✅ Thắng {wins} | ❌ Thua {losses}\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ NÊN CHƠI - ĐẶT {label_text(pred_label)}\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    return msg
