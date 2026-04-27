"""Fetch FINRA margin debt / GDP.

FINRA used to publish monthly Customer Debit Balances, but the page URL is
inconvenient to scrape reliably. FRED republishes the equivalent series
under several IDs; the closest stable series is BOGZ1FL073164103Q ("Net
acquisition of financial assets... brokers and dealers; security credit;
asset"), which is quarterly.

For the barometer we want margin debt as % of GDP (or simply margin debt
z-scored on its own). We use FRED's BOGZ1FL073164103Q normalised by GDP.

If FINRA's official monthly file becomes scraping-friendly, swap in here.
"""
from __future__ import annotations

from . import fetch_fred
from .common import HISTORY_DIR, write_csv

HISTORY_PATH = HISTORY_DIR / "margin_debt.csv"


def fetch() -> dict:
    margin = fetch_fred.fetch("BOGZ1FL073164103Q")
    gdp = fetch_fred.fetch("GDP")
    if not margin or not gdp:
        return {"error": "Margin debt: missing FRED data", "history": []}

    gdp_by_q: dict[str, float] = {}
    for r in gdp:
        try:
            gdp_by_q[r["date"]] = float(r["value"])
        except ValueError:
            continue

    rows: list[dict[str, str]] = []
    last_gdp: float | None = None
    for r in margin:
        try:
            m = float(r["value"])
        except ValueError:
            continue
        if r["date"] in gdp_by_q:
            last_gdp = gdp_by_q[r["date"]]
        if last_gdp is None or last_gdp == 0:
            continue
        ratio = (m / last_gdp) * 100
        rows.append({"date": r["date"], "value": f"{ratio:.4f}"})

    if not rows:
        return {"error": "Margin debt: no rows after merge", "history": []}

    write_csv(HISTORY_PATH, rows, ("date", "value"))
    latest = rows[-1]
    return {
        "asof": latest["date"],
        "value": float(latest["value"]),
        "source": "FRED (BOGZ1FL073164103Q / GDP)",
        "source_url": "https://fred.stlouisfed.org/series/BOGZ1FL073164103Q",
        "history": rows,
    }


if __name__ == "__main__":
    import json
    out = fetch()
    print(json.dumps({k: v for k, v in out.items() if k != "history"}, indent=2))
    print(f"history points: {len(out.get('history', []))}")
