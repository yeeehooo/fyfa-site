"""Read FINRA margin debt history from a manually-maintained CSV.

FRED removed its monthly margin debt series along with the Wilshire
data, and FINRA's CSV download URL changes each month. So we let Yee
maintain ``data/margin-debt-history.csv`` directly: 2 columns,
``date,value`` where value is the customer debit balance in $ millions.

Source for refreshing:
    https://www.finra.org/investors/insights/margin-statistics
The page links to a "Historical Margin Statistics" Excel file with the
full history back to ~1997. Open it, copy the date + customer debit
balance columns into the CSV, commit, push.

Combined with FRED's GDP (still available), we compute margin debt as
% of GDP and z-score that for the sub-score.
"""
from __future__ import annotations

from . import fetch_fred
from .common import DATA_DIR, HISTORY_DIR, read_csv, write_csv

CSV_PATH = DATA_DIR / "margin-debt-history.csv"
HISTORY_PATH = HISTORY_DIR / "margin_debt.csv"


def fetch() -> dict:
    if not CSV_PATH.exists():
        return {"error": "margin-debt-history.csv missing", "history": []}

    raw_rows = read_csv(CSV_PATH)
    margin_by_month: dict[str, float] = {}
    for r in raw_rows:
        d = (r.get("date") or "").strip()
        v_raw = (r.get("value") or "").strip().replace(",", "")
        if not d or not v_raw:
            continue
        try:
            v = float(v_raw)
        except ValueError:
            continue
        margin_by_month[d[:7]] = v  # group by YYYY-MM

    if not margin_by_month:
        return {"error": "margin-debt-history.csv empty", "history": []}

    gdp_rows = fetch_fred.fetch("GDP")
    if not gdp_rows:
        return {"error": "Margin debt: GDP unavailable from FRED", "history": []}

    gdp_by_month: dict[str, float] = {}
    for r in gdp_rows:
        d = r["date"]
        try:
            gdp_by_month[d[:7]] = float(r["value"])
        except ValueError:
            continue

    # Forward-fill GDP across all margin-debt months
    months = sorted(margin_by_month.keys())
    last_gdp: float | None = None
    rows: list[dict[str, str]] = []
    for ym in months:
        # Find the latest GDP observation up to this month
        for gym in sorted(gdp_by_month):
            if gym <= ym:
                last_gdp = gdp_by_month[gym]
        if last_gdp is None or last_gdp == 0:
            continue
        # GDP is in $ billions; margin debt CSV is in $ millions.
        # ratio = (margin_millions / 1000) / gdp_billions * 100
        ratio = (margin_by_month[ym] / 1000.0) / last_gdp * 100
        rows.append({"date": f"{ym}-01", "value": f"{ratio:.4f}"})

    if not rows:
        return {"error": "Margin debt: no rows after merge", "history": []}

    write_csv(HISTORY_PATH, rows, ("date", "value"))
    latest = rows[-1]
    return {
        "asof": latest["date"],
        "value": float(latest["value"]),
        "source": "FINRA margin debt (manually maintained) / FRED GDP",
        "source_url": "https://www.finra.org/investors/insights/margin-statistics",
        "history": rows,
    }


if __name__ == "__main__":
    import json
    out = fetch()
    print(json.dumps({k: v for k, v in out.items() if k != "history"}, indent=2))
    print(f"history points: {len(out.get('history', []))}")
