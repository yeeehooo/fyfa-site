"""Fetch a FRED time series as a list of (date, value) rows.

Uses public CSV endpoints; no API key required. We try two URL patterns
because FRED has changed which one works for direct download over the
years:

  1. https://fred.stlouisfed.org/graph/fredgraph.csv?id=<SERIES_ID>
  2. https://fred.stlouisfed.org/series/<SERIES_ID>/downloaddata/<SERIES_ID>.csv

CSV form:
    DATE,SERIES_ID
    2024-01-01,123.4

Returns rows chronologically; missing values (".") are skipped.

This module logs to stdout on failure so the GitHub Actions log gives
us a clue when something breaks (without raising — we just return []).
"""
from __future__ import annotations

import csv
import io

import requests

from .common import HEADERS

URL_TEMPLATES = [
    "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}",
    "https://fred.stlouisfed.org/series/{sid}/downloaddata/{sid}.csv",
]


def _try_fetch(url: str) -> tuple[int, str, str]:
    """Returns (status_code, content_type, body). Empty strings on exception."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=30, allow_redirects=True)
        return r.status_code, r.headers.get("content-type", ""), r.text
    except Exception as e:
        return 0, "", f"<exception: {e!r}>"


def _parse_csv(text: str) -> list[dict[str, str]]:
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        return []
    if len(header) < 2:
        return []
    out: list[dict[str, str]] = []
    for r in reader:
        if len(r) < 2:
            continue
        d, v = r[0].strip(), r[1].strip()
        if not d or v in ("", "."):
            continue
        out.append({"date": d, "value": v})
    return out


def fetch(series_id: str) -> list[dict[str, str]]:
    for tmpl in URL_TEMPLATES:
        url = tmpl.format(sid=series_id)
        status, ctype, body = _try_fetch(url)
        # Heuristic for "looks like a CSV with our expected header"
        looks_like_csv = (
            status == 200
            and (
                "csv" in ctype.lower()
                or body[:50].upper().startswith(("DATE,", "OBSERVATION_DATE,"))
            )
        )
        if looks_like_csv:
            rows = _parse_csv(body)
            if rows:
                return rows
            print(
                f"  [FRED debug] {series_id} via {url}: 200 OK but parsed 0 rows. "
                f"body[:200]={body[:200]!r}"
            )
            continue
        print(
            f"  [FRED debug] {series_id} via {url}: status={status} "
            f"content-type={ctype!r} len={len(body)} body[:200]={body[:200]!r}"
        )
    return []


if __name__ == "__main__":
    import sys
    sid = sys.argv[1] if len(sys.argv) > 1 else "GDP"
    rows = fetch(sid)
    print(f"\n{sid}: {len(rows)} rows; latest = {rows[-1] if rows else None}")
