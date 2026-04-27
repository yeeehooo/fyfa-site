"""Score helpers: convert raw indicator values into 0-100 sub-scores.

Convention: 100 = expensive / greedy / hot, 0 = cheap / fearful / cold.

We use a 20-year rolling z-score for the structural valuation indicators
(Shiller PE, Buffett, Margin Debt) and a 10-year rolling window for the
shorter-cycle indicators (AAII cash, etc.). The z-score is then mapped to
0-100 via a simple linear mapping clipped at +/-2 sigma.

For indicators where high = fear (e.g. AAII retail cash allocation), pass
``invert=True``: a high raw value yields a low score.

For percent-based indicators that are already on a 0-100 scale (CNN F&G,
Google Trends), use ``passthrough_score`` instead.
"""
from __future__ import annotations

from datetime import date
from typing import Iterable, Sequence

import math


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs)


def _std(xs: Sequence[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    var = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(var)


def rolling_zscore(values: Sequence[float], window: int) -> float:
    """Z-score of the last value vs the previous ``window`` values.

    Uses up to ``window`` of the most recent prior observations (excluding
    the latest value itself). If fewer than 24 prior observations exist we
    return 0.0 so the score lands at 50 — neutral until we've seen enough
    data.
    """
    if len(values) < 25:
        return 0.0
    latest = values[-1]
    history = values[-(window + 1):-1] if len(values) > window + 1 else values[:-1]
    mu = _mean(history)
    sigma = _std(history)
    if sigma == 0:
        return 0.0
    return (latest - mu) / sigma


def zscore_to_score(z: float, *, invert: bool = False, clip: float = 2.0) -> int:
    """Map a z-score to an integer 0-100 sub-score.

    z = -clip -> 0, z = 0 -> 50, z = +clip -> 100. Linear, clipped.
    With ``invert=True``, the mapping is reversed.
    """
    z_clipped = max(-clip, min(clip, z))
    score = 50 + (z_clipped / clip) * 50
    if invert:
        score = 100 - score
    return int(round(score))


def passthrough_score(value: float, *, invert: bool = False) -> int:
    """For values already on 0-100 (CNN F&G, Google Trends)."""
    score = max(0, min(100, value))
    if invert:
        score = 100 - score
    return int(round(score))


def composite_score(subscores: dict[str, int], weights: dict[str, float]) -> int:
    """Weighted average of sub-scores, returns int 0-100.

    Missing / None sub-scores are skipped and weights renormalized.
    """
    total_w = 0.0
    total = 0.0
    for key, w in weights.items():
        s = subscores.get(key)
        if s is None:
            continue
        total += s * w
        total_w += w
    if total_w == 0:
        return 50
    return int(round(total / total_w))


def band_label(score: int) -> str:
    if score < 20:
        return "fear"
    if score < 40:
        return "leaning_fear"
    if score < 60:
        return "normal"
    if score < 80:
        return "leaning_greed"
    return "greed"


def today_iso() -> str:
    return date.today().isoformat()
