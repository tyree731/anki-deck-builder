"""Pace a deck toward a test date: how many new cards a day, and when they've all been seen.

Anki introduces new cards at a fixed daily limit. The plan picks the limit that shows every
card before the test while leaving the last days for reviews only (config.toml [plan]).
The build orders new cards core first, so when the limit is capped, core cards still come
first.
"""

import math
import re
from datetime import date, timedelta

from adb_core.common import load_config

_CLOZE = re.compile(r"\{\{c(\d+)::")


def cards_in_note(card: dict) -> int:
    """How many Anki cards a note becomes.

    Args:
        card: A note from build/cards.json.

    Returns:
        One per distinct cloze number for a cloze note, otherwise one.
    """
    if card["type"] == "cloze":
        return len(set(_CLOZE.findall(card["text"]))) or 1
    return 1


def deck_counts(cards: list[dict]) -> tuple[int, int]:
    """Count a deck's cards, and how many of them are core.

    Args:
        cards: The notes from build/cards.json.

    Returns:
        (cards, core cards); a note without a priority is core.
    """
    total = sum(cards_in_note(c) for c in cards)
    core = sum(cards_in_note(c) for c in cards if c.get("priority", "core") == "core")
    return total, core


def plan(test_date: date, today: date, cards: int, core_cards: int) -> dict:
    """Pace new cards so every card is seen before the test, with review-only days at the end.

    Args:
        test_date: The day of the test.
        today: The first day of studying.
        cards: Cards in the deck.
        core_cards: How many of them are core.

    Returns:
        test_date, days_left, cards and core_cards, plus new_per_day, core_seen_by,
        all_seen_by and reviews_from (ISO dates), and fits: whether every card is seen
        before the review-only days. new_per_day is None when the test is today or past.
    """
    cfg = load_config()["plan"]
    days_left = (test_date - today).days
    result = {"test_date": test_date.isoformat(), "days_left": days_left, "cards": cards, "core_cards": core_cards}
    if days_left < 1:
        return result | {"new_per_day": None, "fits": False}
    learning_days = max(1, days_left - cfg["review_days_before_test"])
    new_per_day = min(max(math.ceil(cards / learning_days), cfg["min_new_per_day"]), cfg["max_new_per_day"])

    def seen_by(count: int) -> str:
        return (today + timedelta(days=max(1, math.ceil(count / new_per_day)) - 1)).isoformat()

    return result | {
        "new_per_day": new_per_day,
        "core_seen_by": seen_by(core_cards),
        "all_seen_by": seen_by(cards),
        "reviews_from": (today + timedelta(days=learning_days)).isoformat(),
        "fits": math.ceil(cards / new_per_day) <= learning_days,
    }
