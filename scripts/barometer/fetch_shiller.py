"""Fetch Shiller PE (CAPE) monthly history.

Source: multpl.com — they publish monthly history at /shiller-pe/table/by-month.
The page format is:
    <tr>
      <td class="left">Mar 1, 2026</td>
      <td class="right">36.82</td>
    </tr>

We try a couple of regexes because their markup changes occasionally,
and log to stdout on failure so the GHA log tells us what's broken.

If multpl.com returns 403 / blocks the runner, we fall through to the
Yale Excel as a last resort (no Excel parsing dep — we just don't have
that path implemented yet; for now we just log and return).
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

import requests

from .common import HEADERS, HISTORY_DIR, write_csv

URL = "https://www.multpl.com/shiller-pe/table/by-month"
HISTORY_PATH = HISTORY_DIR / "shiller_pe.csv"

# Multiple regex strategies, tried in order. First one that yields rows wins.
ROW_REGEXES = [
    # Strict: <td>Date</td><td> &#x2002; Value </td> — handles HTML entities
    # and arbitrary whitespace inside the value cell.
    re.compile(
        r"<td[^>]*>\s*(?:<a[^>]*>)?\s*"
        r"([A-Z][a-z]{2,8}\s+\d{1,2},\s*\d{4})"
        r"\s*(?:</a>)?\s*</td>\s*"
        r"<td[^>]*>[^<\d-]*(-?\d{1,3}\.\d{1,2})\s*</td>",
        re.IGNORECASE | re.DOTALL,
    ),
    # Looser: any consecutive Date / number cells, allowing newlines & extra tags
    re.compile(
        r"([A-Z][a-z]{2,8}\s+\d{1,2},\s*\d{4})"
        r"[^<>0-9]{0,300}"
        r"(\d{1,3}\.\d{1,2})",
        re.IGNORECASE | re.DOTALL,
    ),
]


def _parse_date(s: str) -> Optional[str]:
    for fmt in ("%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(s.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _fetch_html() -> tuple[int, str, str]:
    try:
        r = requests.get(URL, headers=HEADERS, timeout=30, allow_redirects=True)
        return r.status_code, r.headers.get("content-type", ""), r.text
    except Exception as e:
        return 0, "", f"<exception: {e!r}>"


def fetch() -> dict:
    status, ctype, html = _fetch_html()
    if status != 200:
        print(
            f"  [Shiller debug] {URL}: status={status} content-type={ctype!r} "
            f"len={len(html)} body[:200]={html[:200]!r}"
        )
        return {"error": f"shiller HTTP {status}", "history": []}

    rows: list[dict[str, str]] = []
    for i, regex in enumerate(ROW_REGEXES):
        seen: dict[str, str] = {}
        for m in regex.finditer(html):
            iso = _parse_date(m.group(1))
            if not iso:
                continue
            try:
                v = float(m.group(2))
            except ValueError:
                continue
            # Sanity: Shiller PE has been roughly 4..50 historically
            if not (3 <= v <= 80):
                continue
            seen[iso] = f"{v:.2f}"
        if len(seen) >= 60:  # need at least 5 years of monthly data to trust
            rows = sorted(
                ({"date": d, "value": v} for d, v in seen.items()),
                key=lambda r: r["date"],
            )
            print(f"  [Shiller debug] regex #{i} matched {len(rows)} rows")
            break
        if seen:
            print(f"  [Shiller debug] regex #{i} matched only {len(seen)} rows; trying next")

    if not rows:
        # Find a section of the body that contains a recent year so we can see
        # how multpl.com is actually rendering the data table now.
        m = re.search(r"(202[0-9]|201[5-9])", html)
        if m:
            start = max(0, m.start() - 200)
            snippet = html[start:start + 800].replace("\n", " ")
            print(f"  [Shiller debug] body near year match (offset {m.start()}): {snippet!r}")
        else:
            print(f"  [Shiller debug] no recent year in body. head: {html[:500]!r}")
        return {"error": "no rows parsed from multpl.com", "history": []}

    write_csv(HISTORY_PATH, rows, ("date", "value"))
    latest = rows[-1]
    return {
        "asof": latest["date"],
        "value": float(latest["value"]),
        "source": "Robert Shiller / multpl.com",
        "source_url": URL,
        "history": rows,
    }


if __name__ == "__main__":
    import json
    out = fetch()
    print(json.dumps({k: v for k, v in out.items() if k != "history"}, indent=2))
    print(f"history points: {len(out.get('history', []))}")
