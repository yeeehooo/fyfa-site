"""Fetch CNN's Fear & Greed Index.

CNN exposes a JSON endpoint at
    https://production.dataviz.cnn.io/index/fearandgreed/graphdata

It returns a payload like:
    {
      "fear_and_greed": {"score": 56.3, "rating": "Greed", "timestamp": "..."},
      "fear_and_greed_historical": {"data": [{"x": 1700000000000, "y": 42.1}, ...]}
    }

We keep our own append-only history under data/history/fear_greed.csv so
we accumulate observations even if CNN trims their public window.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .common import HISTORY_DIR, append_history_row, fetch_json, today_iso

URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
HISTORY_PATH = HISTORY_DIR / "fear_greed.csv"


def _ms_to_iso(ms: float) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date().isoformat()


def fetch() -> dict:
    try:
        data = fetch_json(URL)
    except Exception as e:
        return {"error": f"F&G fetch failed: {e}", "history": []}

    fg = data.get("fear_and_greed") or {}
    score = fg.get("score")
    if score is None:
        return {"error": "F&G missing score", "history": []}

    asof = today_iso()
    ts = fg.get("timestamp")
    if isinstance(ts, str):
        try:
            asof = datetime.fromisoformat(ts.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            pass

    # Append latest to our history
    append_history_row(HISTORY_PATH, asof, float(score))

    # Backfill any historical points CNN sent us (idempotent)
    hist_block = (data.get("fear_and_greed_historical") or {}).get("data") or []
    for pt in hist_block[-90:]:  # last 90 daily points is plenty
        try:
            d = _ms_to_iso(float(pt["x"]))
            v = float(pt["y"])
        except (KeyError, ValueError, TypeError):
            continue
        append_history_row(HISTORY_PATH, d, v)

    # Reload final history for return
    from .common import history_values, read_csv
    rows = []
    for r in read_csv(HISTORY_PATH):
        try:
            rows.append({"date": r["date"], "value": f"{float(r['value']):.2f}"})
        except (KeyError, ValueError):
            continue

    return {
        "asof": asof,
        "value": float(score),
        "rating": fg.get("rating"),
        "source": "CNN Business Fear & Greed Index",
        "source_url": "https://www.cnn.com/markets/fear-and-greed",
        "history": rows,
    }


if __name__ == "__main__":
    import json
    out = fetch()
    print(json.dumps({k: v for k, v in out.items() if k != "history"}, indent=2))
    print(f"history points: {len(out.get('history', []))}")
