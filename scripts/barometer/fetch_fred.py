"""Fetch a FRED time series as a list of (date, value) rows.

Uses the public CSV download endpoint, no API key required:

    https://fred.stlouisfed.org/graph/fredgraph.csv?id=<SERIES_ID>

The CSV has the form:
    DATE,SERIES_ID
    2024-01-01,123.4
    2024-04-01,124.8

Some series are quarterly; some monthly; some weekly. We return rows in
chronological order. Missing values (".") are skipped.
"""
from __future__ import annotations

import csv
import io

from .common import fetch_text


def fetch(series_id: str) -> list[dict[str, str]]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    try:
        text = fetch_text(url)
    except Exception:
        return []
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        return []
    if len(header) < 2:
        return []
    rows: list[dict[str, str]] = []
    for r in reader:
        if len(r) < 2:
            continue
        d, v = r[0].strip(), r[1].strip()
        if not d or v in ("", "."):
            continue
        rows.append({"date": d, "value": v})
    return rows


if __name__ == "__main__":
    import sys
    sid = sys.argv[1] if len(sys.argv) > 1 else "GDP"
    rows = fetch(sid)
    print(f"{sid}: {len(rows)} rows; latest = {rows[-1] if rows else None}")
