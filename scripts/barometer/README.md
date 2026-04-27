# Barometer data pipeline

Generates `data/barometer.json` from six market sentiment / valuation
indicators, on a weekly cron (with manual-dispatch override).

## Indicators

| Key             | Source                     | Weight | Window  | Notes |
|-----------------|----------------------------|-------:|---------|-------|
| `shiller_pe`    | multpl.com (scraped)       | 25%    | 240 mo  | Z-scored |
| `buffett`       | FRED `WILL5000PR / GDP`    | 25%    | 240 mo  | Z-scored |
| `margin_debt`   | FRED `BOGZ1FL073164103Q / GDP` | 20% | 80 q | Z-scored |
| `aaii_cash`     | `data/aaii-history.csv`    | 20%    | 120 mo  | Z-scored, **inverted** |
| `fear_greed`    | CNN production endpoint    | 10%    | —       | Passthrough |
| `google_trends` | pytrends "stock market"    | X-factor | — | Override at score ≥ 80 |

The composite is a weighted average of the five sub-scores. If Google
Trends panic searches breach 80, the composite is floored at that level.

Bands: 0–20 fear · 20–80 normal · 80–100 greed.

## Run locally

```bash
cd fyfa-site
pip install -r scripts/barometer/requirements.txt
python -m scripts.barometer.build_barometer
```

This writes:

- `data/barometer.json` (the page reads this at runtime)
- `data/history/*.csv` (per-indicator accumulated history)

## Run individual fetchers

Each fetcher is runnable on its own for debugging:

```bash
python -m scripts.barometer.fetch_shiller
python -m scripts.barometer.fetch_buffett
python -m scripts.barometer.fetch_margin_debt
python -m scripts.barometer.fetch_aaii
python -m scripts.barometer.fetch_fear_greed
python -m scripts.barometer.fetch_google_trends
```

## Failure modes

- A fetcher that raises is caught — its indicator gets `score: null`,
  `stale: true`, and an `error` string. The composite still computes
  from whatever indicators succeeded (weights renormalize).
- `google_trends` is rate-limited from time to time; that's expected.
  When pytrends fails the override is simply inactive.
- `aaii_cash` is the only indicator that depends on a manually-maintained
  CSV. Refresh `data/aaii-history.csv` when AAII publishes a new month.

## Schema

See the docstring of `build_barometer.py`.
