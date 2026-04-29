"""Fetch the Buffett indicator: broad equity market / GDP.

Originally used FRED's WILL5000PR (Wilshire 5000) but FRED removed
Wilshire data on June 3, 2024. We now use the S&P 500 (^GSPC) from
yfinance as a market proxy. For z-scoring purposes this is fine — the
S&P 500 and Wilshire 5000 are 99%+ correlated over the 20-year window
we use.

GDP still comes from FRED (no key required).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from . import fetch_fred
from .common import HISTORY_DIR, write_csv

HISTORY_PATH = HISTORY_DIR / "buffett.csv"


def _fetch_market_monthly() -> tuple[dict[str, float], str, float]:
    """Return ({YYYY-MM: last close}, ticker_used, scale_factor).

    Tries broad market indices in priority order and returns the first
    that yields data. Scale factor maps the index level to an
    approximate "total US market cap" magnitude:
      - ^DWCF (Dow Jones US Total Stock Market Index)  ~ full market, scale 1.0
      - ^GSPC (S&P 500)                                 ~ 80% of mkt, scale 1.25
    """
    try:
        import yfinance as yf  # type: ignore
    except Exception as e:
        print(f"  [Buffett debug] yfinance import failed: {e}")
        return {}, "", 1.0

    candidates = [
        ("^DWCF", 1.00),
        ("^GSPC", 1.25),
    ]

    for ticker, scale in candidates:
        try:
            df = yf.Ticker(ticker).history(period="25y", auto_adjust=True)
        except Exception as e:
            print(f"  [Buffett debug] {ticker} fetch failed: {e}")
            continue

        if df is None or df.empty or "Close" not in df.columns:
            print(f"  [Buffett debug] {ticker} returned empty / unexpected schema")
            continue

        df = df.dropna(subset=["Close"])
        by_month: dict[str, tuple[str, float]] = {}
        for ts, row in df.iterrows():
            d = ts.date().isoformat() if hasattr(ts, "date") else str(ts)[:10]
            ym = d[:7]
            if ym not in by_month or d > by_month[ym][0]:
                by_month[ym] = (d, float(row["Close"]))

        if by_month:
            print(f"  [Buffett debug] using {ticker} (scale x{scale}); {len(by_month)} months")
            return ({ym: v for ym, (_, v) in by_month.items()}, ticker, scale)

    return {}, "", 1.0


def _to_monthly_last(rows: list[dict[str, str]]) -> dict[str, float]:
    """Reduce FRED rows to month -> last value within that month."""
    by_month: dict[str, tuple[str, float]] = {}
    for r in rows:
        d = r["date"]
        try:
            v = float(r["value"])
        except ValueError:
            continue
        ym = d[:7]
        if ym not in by_month or d > by_month[ym][0]:
            by_month[ym] = (d, v)
    return {ym: v for ym, (_, v) in by_month.items()}


def _carry_forward(by_month: dict[str, float], months: list[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    last: float | None = None
    for ym in sorted(months):
        if ym in by_month:
            last = by_month[ym]
        if last is not None:
            out[ym] = last
    return out


def fetch() -> dict:
    market_m, ticker, scale = _fetch_market_monthly()
    gdp_rows = fetch_fred.fetch("GDP")
    if not market_m:
        return {"error": "Buffett: market index unavailable", "history": []}
    if not gdp_rows:
        return {"error": "Buffett: GDP unavailable from FRED", "history": []}

    gdp_m = _to_monthly_last(gdp_rows)
    months = sorted(set(list(market_m.keys()) + list(gdp_m.keys())))
    gdp_ff = _carry_forward(gdp_m, months)

    rows: list[dict[str, str]] = []
    for ym in months:
        m = market_m.get(ym)
        g = gdp_ff.get(ym)
        if m is None or g is None or g == 0:
            continue
        # Scale market index to a total-market-cap-ish magnitude, divide by GDP.
        # Constants don't affect the z-score sub-score, but make the displayed
        # raw value resemble the canonical Buffett indicator (~150-200).
        ratio = (m * scale / g) * 100
        rows.append({"date": f"{ym}-01", "value": f"{ratio:.4f}"})

    if not rows:
        return {"error": "Buffett: no rows after merge", "history": []}

    write_csv(HISTORY_PATH, rows, ("date", "value"))
    latest = rows[-1]
    src = f"yfinance {ticker} / FRED GDP" + (f" (×{scale})" if scale != 1.0 else "")
    return {
        "asof": latest["date"],
        "value": float(latest["value"]),
        "source": src,
        "source_url": f"https://finance.yahoo.com/quote/{ticker.replace('^', '%5E')}",
        "history": rows,
    }


if __name__ == "__main__":
    import json
    out = fetch()
    print(json.dumps({k: v for k, v in out.items() if k != "history"}, indent=2))
    print(f"history points: {len(out.get('history', []))}")
