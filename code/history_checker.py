"""
history_checker.py
Reads user_history.csv and returns risk flags for a given user_id.
NEVER changes the verdict — only adds flags.
"""

import csv
from pathlib import Path
from functools import lru_cache


@lru_cache(maxsize=1)
def _load_history(csv_path: str) -> dict:
    history = {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            history[row["user_id"]] = row
    return history


def get_history_flags(user_id: str, history_csv_path: str) -> list[str]:
    """
    Returns a list of risk flag strings for the user.
    e.g. ["user_history_risk", "manual_review_required"]
    Returns [] if user is unknown or low-risk.
    """
    history = _load_history(history_csv_path)

    if user_id not in history:
        return []

    row = history[user_id]
    raw_flags = row.get("history_flags", "none").strip()

    if raw_flags.lower() == "none" or not raw_flags:
        return []

    flags = [f.strip() for f in raw_flags.split(";") if f.strip() and f.strip().lower() != "none"]
    return flags


def get_history_summary(user_id: str, history_csv_path: str) -> str:
    history = _load_history(history_csv_path)
    if user_id not in history:
        return "No history found."
    return history[user_id].get("history_summary", "")