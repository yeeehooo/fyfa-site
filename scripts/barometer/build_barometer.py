#!/usr/bin/env python3
"""Compose data/barometer.json from all six fetchers.

Run from repo root:
    python -m scripts.barometer.build_barometer

The output is a single JSON file the front-end fetches at runtime.

Schema:
{
  "asof": "2026-04-27",
  "score": 62,
  "band": "leaning_greed",
  "indicators": [
    {
      "key": "shiller_pe",
      "name": "Shiller PE",
      "weight": 0.25,
      "value": 36.8,
      "value_unit": "ratio",
      "score": 72,
      "asof": "2026-03-01",
      "source": "Robert Shiller / multpl.com",
      "source_url": "https://www.multpl.com/shiller-pe/table/by-month",
      "stale": false
    },
    ...
    {
      "key": "google_trends",
      "name": "Google Trends 'stock market'",
      "x_factor": true,
      "active": false,         // true when score >= 80
      "value": 42, "score": 42, ...
    }
  ],
  "errors": [...]
}
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

# Allow running as `python -m scripts.barometer.build_barometer` OR
# `python scripts/barometer/build_barometer.py`
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from scripts.barometer import (
        fetch_aaii,
        fetch_buffett,
        fetch_fear_greed,
        fetch_google_trends,
        fetch_margin_debt,
        fetch_shiller,
        scoring,
    )
    from scripts.barometer.common import DATA_DIR
else:
    from . import (
        fetch_aaii,
        fetch_buffett,
        fetch_fear_greed,
        fetch_google_trends,
        fetch_margin_debt,
        fetch_shiller,
        scoring,
    )
    from .common import DATA_DIR


OUTPUT_PATH = DATA_DIR / "barometer.json"

# Weights match the copy in index.html.
WEIGHTS: dict[str, float] = {
    "shiller_pe": 0.25,
    "buffett": 0.25,
    "margin_debt": 0.20,
    "aaii_cash": 0.20,
    "fear_greed": 0.10,
}

# Z-score window per indicator, in months. Structural valuation indicators
# get 20 years; shorter-cycle leverage/sentiment indicators get 10 (post-QE
# regime is structurally different from pre-2009 for margin/leverage data).
WINDOWS: dict[str, int] = {
    "shiller_pe": 240,
    "buffett": 240,
    "margin_debt": 120,   # 10y monthly — post-QE regime baseline
    "aaii_cash": 120,
    "fear_greed": 60,
}


def _staleness_days(asof_str: str | None) -> int:
    if not asof_str:
        return 9999
    try:
        d = datetime.fromisoformat(asof_str).date()
    except ValueError:
        return 9999
    return (date.today() - d).days


def _values_only(history: list[dict]) -> list[float]:
    out: list[float] = []
    for r in history:
        try:
            out.append(float(r["value"]))
        except (KeyError, ValueError, TypeError):
            continue
    return out


def _build_zscored(
    key: str,
    pretty_name: str,
    raw: dict,
    *,
    invert: bool = False,
    value_unit: str = "ratio",
) -> dict:
    if raw.get("error") or not raw.get("history"):
        return {
            "key": key,
            "name": pretty_name,
            "weight": WEIGHTS.get(key, 0),
            "value": None,
            "value_unit": value_unit,
            "score": None,
            "asof": None,
            "stale": True,
            "error": raw.get("error", "no data"),
        }

    values = _values_only(raw["history"])
    z = scoring.rolling_zscore(values, WINDOWS.get(key, 240))
    score = scoring.zscore_to_score(z, invert=invert)
    return {
        "key": key,
        "name": pretty_name,
        "weight": WEIGHTS.get(key, 0),
        "value": raw.get("value"),
        "value_unit": value_unit,
        "score": score,
        "zscore": round(z, 2),
        "asof": raw.get("asof"),
        "source": raw.get("source"),
        "source_url": raw.get("source_url"),
        "stale": _staleness_days(raw.get("asof")) > 90,
    }


def main() -> None:
    print("Fetching indicators...")
    shiller = fetch_shiller.fetch();           print("  · Shiller PE     ", "ok" if shiller.get("history") else "fail")
    buffett = fetch_buffett.fetch();           print("  · Buffett        ", "ok" if buffett.get("history") else "fail")
    margin = fetch_margin_debt.fetch();        print("  · Margin debt    ", "ok" if margin.get("history") else "fail")
    aaii = fetch_aaii.fetch();                 print("  · AAII cash      ", "ok" if aaii.get("history") else "fail")
    fg = fetch_fear_greed.fetch();             print("  · CNN F&G        ", "ok" if fg.get("history") else "fail")
    gt = fetch_google_trends.fetch();          print("  · Google Trends  ", "ok" if gt.get("history") else "fail")

    indicators: list[dict] = []
    indicators.append(_build_zscored("shiller_pe", "Shiller PE", shiller))
    indicators.append(_build_zscored("buffett", "Buffett indicator", buffett))
    indicators.append(_build_zscored("margin_debt", "FINRA margin debt / GDP", margin))
    indicators.append(_build_zscored(
        "aaii_cash", "AAII retail cash (inverted)", aaii,
        invert=True, value_unit="fraction",
    ))

    # CNN F&G is already 0-100 — passthrough
    if fg.get("error") or not fg.get("history"):
        indicators.append({
            "key": "fear_greed", "name": "CNN Fear & Greed Index",
            "weight": WEIGHTS["fear_greed"], "value": None, "score": None,
            "asof": None, "stale": True, "error": fg.get("error", "no data"),
        })
    else:
        indicators.append({
            "key": "fear_greed",
            "name": "CNN Fear & Greed Index",
            "weight": WEIGHTS["fear_greed"],
            "value": fg.get("value"),
            "value_unit": "index_0_100",
            "score": scoring.passthrough_score(fg.get("value", 50)),
            "asof": fg.get("asof"),
            "source": fg.get("source"),
            "source_url": fg.get("source_url"),
            "rating": fg.get("rating"),
            "stale": _staleness_days(fg.get("asof")) > 14,
        })

    # Google Trends X-factor — passthrough, only "active" when >= 80
    gt_score = None
    gt_active = False
    if not gt.get("error") and gt.get("value") is not None:
        gt_score = scoring.passthrough_score(gt["value"])
        gt_active = gt_score >= 80
    indicators.append({
        "key": "google_trends",
        "name": "Google Trends 'stock market'",
        "x_factor": True,
        "active": gt_active,
        "weight": 0.0,  # only contributes when active (handled below)
        "value": gt.get("value"),
        "value_unit": "index_0_100",
        "score": gt_score,
        "asof": gt.get("asof"),
        "source": gt.get("source"),
        "source_url": gt.get("source_url"),
        "stale": gt.get("error") is not None,
        "error": gt.get("error"),
    })

    # Composite from the five weighted indicators
    weighted = {ind["key"]: ind["score"] for ind in indicators if ind["key"] in WEIGHTS}
    composite = scoring.composite_score(weighted, WEIGHTS)

    # If Google Trends is "active" (>= 80), force at least the 80-100 band:
    # the panic search itself is the override.
    if gt_active and gt_score is not None:
        composite = max(composite, gt_score)

    band = scoring.band_label(composite)

    out = {
        "asof": scoring.today_iso(),
        "score": composite,
        "band": band,
        "indicators": indicators,
        "weights": WEIGHTS,
        "methodology": (
            "Each structural indicator (Shiller PE, Buffett, margin debt, AAII cash) "
            "is converted to a 0-100 sub-score via a rolling z-score "
            "(z=-2 -> 0, z=+2 -> 100). AAII cash is inverted: high cash = fear = low "
            "score. CNN F&G is used directly (already 0-100). Google Trends 'stock "
            "market' acts as an X-factor override: when its score reaches 80 the "
            "composite is floored at that level."
        ),
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {OUTPUT_PATH.relative_to(DATA_DIR.parent)}  ·  score={composite} ({band})")


if __name__ == "__main__":
    main()
