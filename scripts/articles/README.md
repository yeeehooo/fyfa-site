# Articles data pipeline

Generates `data/articles.json` from `data/articles-meta.json` on a weekly
cron. The site reads the JSON at runtime and renders the article grid.

## What it does

For each entry in `articles-meta.json`:

1. Pass through the metadata you wrote (title, ticker, pub_date, platform, summary).
2. If the entry has a `ticker`, use **yfinance** to compute:
   - `return_pct` — total return since `pub_date`
   - `spy_return_pct` — SPY total return over the same window
   - `alpha_pct` — return minus SPY return

It also rolls up averages across all articles with returns.

There's no scraping — Seeking Alpha is hostile to it, and we don't need
their hero image anyway. Cards on the site are link-out-only with the
title, ticker pill, pub date, and the two return percentages.

## Adding a new article

Edit `data/articles-meta.json` and add an object to the `articles` array:

```json
{
  "url": "https://seekingalpha.com/article/...",
  "title": "Your article title",
  "ticker": "ABCD",
  "pub_date": "2026-01-15",
  "platform": "seekingalpha"
}
```

For Fidelity / non-stock articles, use:

```json
{
  "url": "https://www.fidelity.com.sg/articles/...",
  "title": "Article title",
  "ticker": null,
  "pub_date": "2024-05-16",
  "platform": "fidelity",
  "label": "Korea Discount",
  "summary": "Optional one-line description shown under the title."
}
```

Commit + push. The next weekly run picks it up — or trigger
**Update articles data → Run workflow** in GitHub Actions for an
immediate refresh.

## Run locally

```bash
pip install -r scripts/articles/requirements.txt
python -m scripts.articles.build_articles
```

## Notes on tickers

- Use the symbol that **yfinance** recognises for that exchange. For OTC
  ADRs, that's the OTC ticker (e.g. `WPLCF` for Wise, `PROSY` for Prosus).
- The job picks the first close on or after `pub_date` (skipping weekends
  / holidays) as the baseline price.
- If yfinance returns no data for a ticker, the article still renders —
  just without the perf row.
