#!/usr/bin/env python3
"""Compose data/articles.json from data/articles-meta.json.

The site links straight out to the articles — we don't scrape Seeking
Alpha (or any host) for hero images or summaries. The meta file is the
source of truth for title / ticker / pub_date / platform / summary.

For each article with a `ticker`, this job uses **yfinance** to compute:
  - return since publication (latest close / first close on/after pub_date)
  - SPY return over the same window
  - alpha (article return - SPY)

It also rolls up averages across all articles with returns.

Run:
    python -m scripts.articles.build_articles
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent.parent
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

DATA_DIR = ROOT / "data"
META_PATH = DATA_DIR / "articles-meta.json"
OUTPUT_PATH = DATA_DIR / "articles.json"


def fetch_returns(ticker: str, pub_date: str) -> dict | None:
    """Return {return_pct, spy_return_pct, alpha_pct, ...} or None on failure."""
    try:
        import yfinance as yf  # type: ignore
    except Exception:
        return None

    try:
        pub_dt = datetime.fromisoformat(pub_date)
    except ValueError:
        return None

    end = (date.today() + timedelta(days=1)).isoformat()
    start = (pub_dt.date() - timedelta(days=2)).isoformat()

    def first_close_on_or_after(symbol: str) -> tuple[float, str] | None:
        try:
            df = yf.download(symbol, start=start, end=end, progress=False, auto_adjust=True)
        except Exception:
            return None
        if df is None or df.empty or "Close" not in df.columns:
            return None
        df = df.dropna(subset=["Close"])
        for ts, row in df.iterrows():
            d = ts.date() if hasattr(ts, "date") else ts
            if d >= pub_dt.date():
                return float(row["Close"]), d.isoformat()
        return None

    def latest_close(symbol: str) -> tuple[float, str] | None:
        try:
            df = yf.download(symbol, period="10d", progress=False, auto_adjust=True)
        except Exception:
            return None
        if df is None or df.empty or "Close" not in df.columns:
            return None
        df = df.dropna(subset=["Close"])
        if df.empty:
            return None
        ts = df.index[-1]
        d = ts.date() if hasattr(ts, "date") else ts
        return float(df.iloc[-1]["Close"]), d.isoformat()

    pub_t = first_close_on_or_after(ticker)
    last_t = latest_close(ticker)
    pub_s = first_close_on_or_after("SPY")
    last_s = latest_close("SPY")
    if not (pub_t and last_t and pub_s and last_s):
        return None

    pub_close, pub_close_date = pub_t
    latest, latest_date = last_t
    spy_pub, _ = pub_s
    spy_latest, _ = last_s

    if pub_close == 0 or spy_pub == 0:
        return None

    ret = (latest / pub_close - 1) * 100
    spy_ret = (spy_latest / spy_pub - 1) * 100
    return {
        "return_pct": round(ret, 1),
        "spy_return_pct": round(spy_ret, 1),
        "alpha_pct": round(ret - spy_ret, 1),
        "pub_close": round(pub_close, 4),
        "latest_close": round(latest, 4),
        "pub_close_date": pub_close_date,
        "latest_close_date": latest_date,
    }


def fmt_pub_date(iso: str) -> str:
    try:
        d = datetime.fromisoformat(iso).date()
    except ValueError:
        return iso
    # %-d isn't portable on Windows, but our runner is Ubuntu
    return d.strftime("%b %-d, %Y")


def domain_label(url: str) -> str:
    host = urlparse(url).netloc.lower()
    host = host[4:] if host.startswith("www.") else host
    if "seekingalpha" in host:
        return "Seeking Alpha"
    if "fidelity" in host:
        return "Fidelity"
    return host


def main() -> None:
    meta = json.loads(META_PATH.read_text(encoding="utf-8"))
    articles_meta = meta.get("articles") or []

    out_articles: list[dict] = []
    for entry in articles_meta:
        url = entry.get("url")
        if not url:
            continue

        record = {
            "url": url,
            "title": entry.get("title") or "",
            "ticker": entry.get("ticker"),
            "label": entry.get("label"),
            "pub_date": entry.get("pub_date"),
            "pub_date_pretty": fmt_pub_date(entry.get("pub_date") or ""),
            "platform": entry.get("platform") or "",
            "platform_label": domain_label(url),
            "summary": entry.get("summary") or "",
        }

        if entry.get("ticker"):
            perf = fetch_returns(entry["ticker"], entry.get("pub_date") or "")
            if perf:
                record.update(perf)

        out_articles.append(record)
        ticker_or_label = entry.get("ticker") or entry.get("label") or "?"
        print(
            f"  · {ticker_or_label:<14} "
            f"perf={'y' if record.get('return_pct') is not None else 'n'}"
        )

    rets = [a["return_pct"] for a in out_articles if a.get("return_pct") is not None]
    spys = [a["spy_return_pct"] for a in out_articles if a.get("spy_return_pct") is not None]
    alphas = [a["alpha_pct"] for a in out_articles if a.get("alpha_pct") is not None]

    summary = {
        "n_with_returns": len(rets),
        "avg_return_pct": round(sum(rets) / len(rets), 1) if rets else None,
        "avg_spy_pct": round(sum(spys) / len(spys), 1) if spys else None,
        "avg_alpha_pct": round(sum(alphas) / len(alphas), 1) if alphas else None,
    }

    out = {
        "asof": date.today().isoformat(),
        "summary": summary,
        "articles": out_articles,
    }

    OUTPUT_PATH.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(
        f"\nWrote data/articles.json — {len(out_articles)} articles, "
        f"{summary['n_with_returns']} with returns. "
        f"avg return = {summary['avg_return_pct']}%, "
        f"avg alpha = {summary['avg_alpha_pct']} pts"
    )


if __name__ == "__main__":
    main()
