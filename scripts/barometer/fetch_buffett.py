"""Fetch the Buffett indicator: Wilshire 5000 / GDP.

Both series are available from FRED without an API key:
  - WILL5000PR  : Wilshire 5000 Total Market Full Cap Index, daily
  - GDP         : Gross Domestic Product, quarterly

We compute the ratio at each Wilshire date by carrying forward the most
recent GDP observation. The ratio is dimensionless but commonly expressed
as Wilshire / GDP * 100 (i.e. ~150 means market cap ~ 1.5x GDP).

A 20-year rolling z-score of the monthly ratio gives the sub-score.
"""
from __future__ import annotations

from datetime import date

from . import fetch_fred
from .common import HISTORY_DIR, write_csv

HISTORY_PATH = HISTORY_DIR / "buffett.csv"


def _to_monthly_last(rows: list[dict[str, str]]) -> dict[str, float]:
    """Reduce daily/weekly rows to month -> last-of-month value."""
    by_month: dict[str, float] = {}
    for r in rows:
        d = r["date"]  # YYYY-MM-DD
        try:
            v = float(r["value"])
        except ValueError:
            continue
        ym = d[:7]  # YYYY-MM
        # Keep the latest date within the month
        if ym not in by_month or d >= getattr(_to_monthly_last, "_seen", {}).get(ym, ""):
            by_month[ym] = v
    return by_month


def _carry_forward(by_month: dict[str, float], months: list[str]) -> dict[str, float]:
    """Forward-fill values to every month in ``months`` (sorted)."""
    out: dict[str, float] = {}
    last: float | None = None
    for ym in sorted(months):
        if ym in by_month:
            last = by_month[ym]
        if last is not None:
            out[ym] = last
    return out


def fetch() -> dict:
    will = fetch_fred.fetch("WILL5000PR")
    gdp = fetch_fred.fetch("GDP")
    if not will or not gdp:
        return {"error": "Buffett: missing FRED data", "history": []}

    will_m = _to_monthly_last(will)
    gdp_m = _to_monthly_last(gdp)
    if not will_m or not gdp_m:
        return {"error": "Buffett: empty after monthly reduction", "history": []}

    months = sorted(set(list(will_m.keys()) + list(gdp_m.keys())))
    will_ff = _carry_forward(will_m, months)
    gdp_ff = _carry_forward(gdp_m, months)

    rows: list[dict[str, str]] = []
    for ym in months:
        w = will_ff.get(ym)
        g = gdp_ff.get(ym)
        if w is None or g is None or g == 0:
            continue
        ratio = (w / g) * 100  # rough convention; magnitude matters less than z-score
        rows.append({"date": f"{ym}-01", "value": f"{ratio:.4f}"})

    if not rows:
        return {"error": "Buffett: no rows after merge", "history": []}

    write_csv(HISTORY_PATH, rows, ("date", "value"))
    latest = rows[-1]
    return {
        "asof": latest["date"],
        "value": float(latest["value"]),
        "source": "FRED (WILL5000PR / GDP)",
        "source_url": "https://fred.stlouisfed.org/series/WILL5000PR",
        "history": rows,
    }


if __name__ == "__main__":
    import json
    out = fetch()
    print(json.dumps({k: v for k, v in out.items() if k != "history"}, indent=2))
    print(f"history points: {len(out.get('history', []))}")
