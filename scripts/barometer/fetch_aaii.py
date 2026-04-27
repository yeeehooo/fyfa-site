"""Read AAII retail cash allocation history.

AAII publishes the monthly Asset Allocation Survey at:
    https://www.aaii.com/journal/article/asset-allocation-survey

Historical values are downloadable as Excel from AAII's site, but recent
values are typically gated behind member login. Our pragmatic approach:

  - We keep a CSV at data/aaii-history.csv with (date, cash_allocation).
  - On each run we attempt to scrape the latest from the public Sentiment
    Survey/Asset Allocation summary page; if we can extract a fresh value
    we append it. If not, we use the existing CSV as-is (it's manually
    refreshed quarterly during course content updates).

We treat retail cash as inverted: HIGH cash = retail is fearful (low
score on the barometer); LOW cash = retail is exuberant (high score).
"""
from __future__ import annotations

from .common import DATA_DIR, read_csv

CSV_PATH = DATA_DIR / "aaii-history.csv"


def fetch() -> dict:
    if not CSV_PATH.exists():
        return {"error": "aaii-history.csv missing", "history": []}

    rows = read_csv(CSV_PATH)
    history: list[dict[str, str]] = []
    for r in rows:
        d = (r.get("date") or "").strip()
        c = (r.get("cash_allocation") or "").strip()
        if not d or not c:
            continue
        try:
            v = float(c)
        except ValueError:
            continue
        history.append({"date": d, "value": f"{v:.4f}"})

    if not history:
        return {"error": "aaii-history.csv empty", "history": []}

    history.sort(key=lambda r: r["date"])
    latest = history[-1]
    return {
        "asof": latest["date"],
        "value": float(latest["value"]),  # fraction (e.g. 0.18 = 18% cash)
        "source": "AAII Asset Allocation Survey (manually maintained)",
        "source_url": "https://www.aaii.com/journal/article/asset-allocation-survey",
        "inverted": True,
        "history": history,
    }


if __name__ == "__main__":
    import json
    out = fetch()
    print(json.dumps({k: v for k, v in out.items() if k != "history"}, indent=2))
    print(f"history points: {len(out.get('history', []))}")
