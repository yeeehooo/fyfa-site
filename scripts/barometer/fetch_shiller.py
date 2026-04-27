"""Fetch Shiller PE (CAPE) monthly history.

Source: multpl.com — they publish the full monthly history in a simple
HTML table at /shiller-pe/table/by-month. We scrape that, normalise to
(date, value) rows, and return the time series.

If multpl.com changes their markup or is unreachable, this returns an
empty list and the composer will mark the indicator as stale.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from .common import HISTORY_DIR, fetch_text, write_csv

URL = "https://www.multpl.com/shiller-pe/table/by-month"
HISTORY_PATH = HISTORY_DIR / "shiller_pe.csv"

# A single row of the multpl table looks like:
#   <td>Mar 1, 2026</td><td>36.82</td>
# but they sometimes wrap the date in <a href="...">. The regex tolerates
# either, plus whitespace/newlines.
ROW_RE = re.compile(
    r"<td[^>]*>\s*(?:<a[^>]*>)?\s*"
    r"([A-Z][a-z]{2,8}\s+\d{1,2},\s*\d{4})"
    r"\s*(?:</a>)?\s*</td>\s*"
    r"<td[^>]*>\s*([\d.]+)\s*</td>",
    re.IGNORECASE,
)


def _parse_date(s: str) -> Optional[str]:
    for fmt in ("%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(s.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def fetch() -> dict:
    """Return {asof, value, source, history: [{date, value}, ...]}."""
    try:
        html = fetch_text(URL)
    except Exception as e:
        return {"error": f"shiller fetch failed: {e}", "history": []}

    rows: list[dict[str, str]] = []
    for m in ROW_RE.finditer(html):
        iso = _parse_date(m.group(1))
        if not iso:
            continue
        try:
            v = float(m.group(2))
        except ValueError:
            continue
        rows.append({"date": iso, "value": f"{v:.2f}"})

    # Dedupe by date, keep last
    seen: dict[str, str] = {}
    for r in rows:
        seen[r["date"]] = r["value"]
    rows = sorted(
        ({"date": d, "value": v} for d, v in seen.items()),
        key=lambda r: r["date"],
    )

    if not rows:
        return {"error": "no rows parsed from multpl.com", "history": []}

    # Persist history for offline debugging
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
