"""Shared HTTP + CSV helpers for the barometer fetchers.

Keeps the dependency surface small: just ``requests`` from the standard
ecosystem. No pandas, no yfinance — easier to install on GitHub Actions
and easier to debug when something breaks.
"""
from __future__ import annotations

import csv
import io
from datetime import date
from pathlib import Path
from typing import Iterable, Sequence

import requests


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; fyfa-barometer/1.0; "
        "+https://fyfa.ca)"
    ),
    "Accept": "*/*",
}

# Repo root: scripts/barometer/common.py -> ../../
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = REPO_ROOT / "data"
HISTORY_DIR = DATA_DIR / "history"


def fetch_text(url: str, *, timeout: int = 30) -> str:
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.text


def fetch_json(url: str, *, timeout: int = 30) -> dict:
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.json()


def fetch_bytes(url: str, *, timeout: int = 60) -> bytes:
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.content


def read_csv(path: Path) -> list[dict[str, str]]:
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def write_csv(path: Path, rows: Sequence[dict], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(fieldnames))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def append_history_row(
    path: Path,
    date_str: str,
    value: float,
    *,
    fieldnames: Sequence[str] = ("date", "value"),
) -> None:
    """Append a new (date, value) row, idempotently.

    If a row with the same date already exists, replace its value.
    """
    rows: list[dict[str, str]] = []
    if path.exists():
        rows = read_csv(path)
    found = False
    for row in rows:
        if row.get("date") == date_str:
            row["value"] = str(value)
            found = True
            break
    if not found:
        rows.append({"date": date_str, "value": str(value)})
    rows.sort(key=lambda r: r.get("date", ""))
    write_csv(path, rows, fieldnames)


def history_values(path: Path, value_col: str = "value") -> list[float]:
    """Read a 2-column history CSV and return the values column as floats."""
    if not path.exists():
        return []
    out: list[float] = []
    for row in read_csv(path):
        v = row.get(value_col, "").strip()
        if not v:
            continue
        try:
            out.append(float(v))
        except ValueError:
            continue
    return out


def today_iso() -> str:
    return date.today().isoformat()
