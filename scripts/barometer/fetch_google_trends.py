"""Fetch Google Trends 'stock market' panic-search index.

Used as the X-factor / panic override on the barometer. Google Trends
returns a 0-100 normalized index over a chosen window. We query the past
12 months and read the most recent weekly bucket.

Implementation: pytrends (the unofficial but widely-used Python wrapper).
If pytrends fails (rate limit, IP block) we surface an error and the
composer marks the override as inactive — the gauge falls back to the
weighted composite.
"""
from __future__ import annotations

from datetime import date

from .common import HISTORY_DIR, append_history_row, today_iso

HISTORY_PATH = HISTORY_DIR / "google_trends.csv"


def fetch() -> dict:
    try:
        from pytrends.request import TrendReq  # type: ignore
    except Exception as e:
        return {"error": f"pytrends not installed: {e}", "history": []}

    try:
        pyt = TrendReq(hl="en-US", tz=360, retries=2, backoff_factor=0.5)
        pyt.build_payload(["stock market"], timeframe="today 12-m", geo="US")
        df = pyt.interest_over_time()
    except Exception as e:
        return {"error": f"pytrends fetch failed: {e}", "history": []}

    if df is None or df.empty or "stock market" not in df.columns:
        return {"error": "pytrends empty result", "history": []}

    # Drop the partial-week last row if flagged
    if "isPartial" in df.columns:
        df = df[df["isPartial"] == False]  # noqa: E712
    if df.empty:
        return {"error": "pytrends only partial data", "history": []}

    series = df["stock market"]
    latest_ts = series.index[-1]
    latest_iso = latest_ts.date().isoformat() if hasattr(latest_ts, "date") else str(latest_ts)
    latest_val = float(series.iloc[-1])

    for ts, val in series.items():
        d = ts.date().isoformat() if hasattr(ts, "date") else str(ts)
        try:
            append_history_row(HISTORY_PATH, d, float(val))
        except Exception:
            continue

    from .common import read_csv
    rows: list[dict[str, str]] = []
    for r in read_csv(HISTORY_PATH):
        try:
            rows.append({"date": r["date"], "value": f"{float(r['value']):.2f}"})
        except (KeyError, ValueError):
            continue

    return {
        "asof": latest_iso,
        "value": latest_val,
        "source": "Google Trends ('stock market', US, weekly)",
        "source_url": "https://trends.google.com/trends/explore?q=stock%20market&geo=US",
        "history": rows,
    }


if __name__ == "__main__":
    import json
    out = fetch()
    print(json.dumps({k: v for k, v in out.items() if k != "history"}, indent=2))
    print(f"history points: {len(out.get('history', []))}")
