"""Read FINRA margin debt history from a manually-maintained CSV.

FRED removed its monthly margin debt series along with the Wilshire
data, so we maintain ``data/finra-margin.csv`` directly: download from
    https://www.finra.org/investors/insights/margin-statistics
into Numbers/Excel, export as CSV. Expected columns include some form
of "Year-Month" and "Debit Balances in Customers' Securities Margin
Accounts" — the parser below recognises a few variants.

GDP still comes from FRED to compute % of GDP. The 20y rolling z-score
of that ratio drives the sub-score.
"""
from __future__ import annotations

import re

from . import fetch_fred
from .common import DATA_DIR, HISTORY_DIR, read_csv, write_csv

CSV_PATH = DATA_DIR / "finra-margin.csv"
HISTORY_PATH = HISTORY_DIR / "margin_debt.csv"

# Recognise common FINRA-flavored column names.
DATE_HEADERS = ("year-month", "yearmonth", "date", "month", "period")
VALUE_HEADERS_PATTERNS = [
    re.compile(r"debit\s*balances?", re.IGNORECASE),
    re.compile(r"margin\s*debt", re.IGNORECASE),
    re.compile(r"^value$", re.IGNORECASE),
]


def _pick_columns(rows: list[dict[str, str]]) -> tuple[str | None, str | None]:
    if not rows:
        return None, None
    headers = list(rows[0].keys())

    date_col = None
    for h in headers:
        if h.strip().lower() in DATE_HEADERS:
            date_col = h
            break

    value_col = None
    for h in headers:
        for pat in VALUE_HEADERS_PATTERNS:
            if pat.search(h):
                value_col = h
                break
        if value_col:
            break

    return date_col, value_col


def _normalise_date(s: str) -> str | None:
    """Accept 2026-03, 2026-03-01, March 2026, 03/2026, etc. Return YYYY-MM."""
    s = s.strip()
    if not s:
        return None
    m = re.match(r"^(\d{4})[-/](\d{1,2})", s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    m = re.match(r"^(\d{1,2})[-/](\d{4})", s)
    if m:
        return f"{m.group(2)}-{int(m.group(1)):02d}"
    # "Mar 2026" / "March 2026"
    months = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }
    m = re.match(r"^([A-Za-z]+)\s+(\d{4})", s)
    if m:
        mon = months.get(m.group(1)[:3].lower())
        if mon:
            return f"{m.group(2)}-{mon:02d}"
    return None


def fetch() -> dict:
    if not CSV_PATH.exists():
        print(f"  [Margin debug] {CSV_PATH} does not exist on this runner")
        return {"error": f"{CSV_PATH.name} missing", "history": []}

    raw_rows = read_csv(CSV_PATH)
    print(f"  [Margin debug] read {len(raw_rows)} rows from {CSV_PATH.name}")
    if raw_rows:
        print(f"  [Margin debug] headers: {list(raw_rows[0].keys())}")

    date_col, value_col = _pick_columns(raw_rows)
    print(f"  [Margin debug] date_col={date_col!r}, value_col={value_col!r}")
    if not date_col or not value_col:
        headers = list(raw_rows[0].keys()) if raw_rows else []
        return {
            "error": f"finra-margin.csv: couldn't find date/value columns. headers={headers}",
            "history": [],
        }

    margin_by_month: dict[str, float] = {}
    skipped = 0
    for r in raw_rows:
        d = _normalise_date(r.get(date_col, ""))
        v_raw = (r.get(value_col, "") or "").strip().replace(",", "").replace("$", "")
        if not d or not v_raw:
            skipped += 1
            continue
        try:
            v = float(v_raw)
        except ValueError:
            skipped += 1
            continue
        margin_by_month[d] = v  # YYYY-MM -> $ millions

    print(f"  [Margin debug] parsed {len(margin_by_month)} months, skipped {skipped}")
    if margin_by_month:
        sorted_months = sorted(margin_by_month)
        print(f"  [Margin debug] range: {sorted_months[0]} to {sorted_months[-1]}")

    if not margin_by_month:
        return {"error": "finra-margin.csv parsed no rows", "history": []}

    gdp_rows = fetch_fred.fetch("GDP")
    if not gdp_rows:
        return {"error": "Margin debt: GDP unavailable from FRED", "history": []}

    gdp_by_month: dict[str, float] = {}
    for r in gdp_rows:
        try:
            gdp_by_month[r["date"][:7]] = float(r["value"])
        except (ValueError, KeyError):
            continue

    months = sorted(margin_by_month.keys())
    rows: list[dict[str, str]] = []
    last_gdp: float | None = None
    sorted_gdp_months = sorted(gdp_by_month)

    for ym in months:
        # Find the latest GDP observation up to this month
        for gym in sorted_gdp_months:
            if gym <= ym:
                last_gdp = gdp_by_month[gym]
            else:
                break
        if last_gdp is None or last_gdp == 0:
            continue
        # GDP is in $ billions; FINRA margin debt is in $ millions.
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
