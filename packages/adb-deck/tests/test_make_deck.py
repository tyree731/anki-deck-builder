"""Tests for adb_deck/make_deck.py."""

import json
from pathlib import Path

import pytest

from adb_deck import make_deck
from adb_testkit import NOTES_CARDS, write_json

pytestmark = pytest.mark.integration


def test_make_builds_and_validates(run_dir: Path):
    """test_make_builds_and_validates: all five steps run and leave lint, deck and import reports in build/."""
    assert make_deck.make(run_dir) == 0
    for name in ("cards.json", "card_owners.json", "lint.json", "deck.apkg", "validate.json"):
        assert (run_dir / "build" / name).exists()
    assert json.loads((run_dir / "build" / "validate.json").read_text())["ok"]


def test_make_stops_on_lint_errors_unless_allowed(run_dir: Path):
    """test_make_stops_on_lint_errors_unless_allowed: lint errors stop before building; --allow-lint-errors builds
    anyway but still fails."""
    leaky = [dict(c) for c in NOTES_CARDS]
    leaky[1]["text"] = "{{c1::Vacuole}}: the large central vacuole supports plant cells."
    write_json(run_dir / "cards" / "S01.json", leaky)
    assert make_deck.make(run_dir) == 1
    assert not (run_dir / "build" / "deck.apkg").exists()
    assert make_deck.make(run_dir, allow_lint_errors=True) == 1
    assert (run_dir / "build" / "deck.apkg").exists()


def test_make_stops_on_invalid_card_file(run_dir: Path):
    """test_make_stops_on_invalid_card_file: a schema-invalid card file fails step 1 before anything is assembled."""
    write_json(run_dir / "cards" / "S01.json", [{"key": "x", "type": "basic"}])
    assert make_deck.make(run_dir) == 1
    assert not (run_dir / "build" / "cards.json").exists()
