"""Rule-based engine: cau 1-1, bet, streak, dao cau, momentum, rolling pattern."""
from typing import List, Dict


def _to_bin(seq: List[str]) -> List[int]:
    # TAI -> 1, XIU -> 0 ; newest LAST
    return [1 if s == "TAI" else 0 for s in seq]


def logic_predict(history_newest_first: List[str]) -> Dict[str, float]:
    """
    history_newest_first: list of 'TAI'/'XIU', newest first.
    Returns probabilities {'TAI': p, 'XIU': 1-p}.
    """
    if not history_newest_first:
        return {"TAI": 0.5, "XIU": 0.5}

    seq = list(reversed(history_newest_first))  # newest last
    bits = _to_bin(seq)
    n = len(bits)

    score_tai = 0.0
    weight = 0.0

    # 1) Cau bet (streak): if last k same -> trend continues with decay
    last = bits[-1]
    streak = 1
    for b in reversed(bits[:-1]):
        if b == last:
            streak += 1
        else:
            break
    # Continuation prob proportional to streak (cap at 6)
    cont = min(streak, 6) / 6.0  # 0.16 .. 1
    # but very long streak -> mean reversion
    if streak >= 5:
        cont = max(0.2, 1.0 - (streak - 4) * 0.15)
    score_tai += (cont if last == 1 else 1 - cont) * 1.2
    weight += 1.2

    # 2) Cau 1-1 (alternating)
    if n >= 4:
        alt = all(bits[-i - 1] != bits[-i - 2] for i in range(min(4, n - 1)))
        if alt:
            nxt = 1 - last
            score_tai += (1.0 if nxt == 1 else 0.0) * 1.0
            weight += 1.0

    # 3) Dao cau (reversal after short streak 2-3)
    if 2 <= streak <= 3 and n >= streak + 1:
        # mild reversal bias
        nxt = 1 - last
        score_tai += (0.6 if nxt == 1 else 0.4) * 0.6
        weight += 0.6

    # 4) Momentum: count last 10
    window = bits[-10:]
    if window:
        ratio_tai = sum(window) / len(window)
        score_tai += ratio_tai * 0.8
        weight += 0.8

    # 5) Rolling pattern: match last 3 occurrences in history
    if n >= 6:
        pat = tuple(bits[-3:])
        nxts = []
        for i in range(n - 3):
            if tuple(bits[i:i + 3]) == pat and i + 3 < n:
                nxts.append(bits[i + 3])
        if nxts:
            r = sum(nxts) / len(nxts)
            score_tai += r * 1.0
            weight += 1.0

    p_tai = score_tai / weight if weight > 0 else 0.5
    p_tai = max(0.0, min(1.0, p_tai))
    return {"TAI": p_tai, "XIU": 1 - p_tai}
