"""Tests for adb_deck/validate_deck.py."""

import json
from pathlib import Path

import pytest

from adb_deck import validate_deck

pytestmark = pytest.mark.integration


def test_validate_accepts_built_deck(built_run_dir: Path):
    """test_validate_accepts_built_deck: a freshly built deck imports cleanly with every card and image."""
    report = validate_deck.validate(built_run_dir / "build" / "deck.apkg", built_run_dir / "build" / "cards.json")
    assert report["ok"], report["problems"]
    assert (report["notes"], report["cards"], report["media"]) == (7, 8, 2)
    assert report["decks"] == {"Test Deck::1 Class Notes": 4, "Test Deck::2 Review Packet": 4}


def test_validate_reports_note_count_mismatch(built_run_dir: Path, tmp_path: Path):
    """test_validate_reports_note_count_mismatch: expecting more notes than the package holds is a problem."""
    cards = json.loads((built_run_dir / "build" / "cards.json").read_text())
    expected = tmp_path / "cards.json"
    expected.write_text(json.dumps([*cards, cards[0]]))
    report = validate_deck.validate(built_run_dir / "build" / "deck.apkg", expected)
    assert not report["ok"] and any("expected 8" in p for p in report["problems"])
