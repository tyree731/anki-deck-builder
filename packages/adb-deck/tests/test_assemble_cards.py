"""Tests for adb_deck/assemble_cards.py."""

import json
from pathlib import Path

from adb_deck import assemble_cards
from adb_testkit import NOTES_CARDS, PACKET_CARDS, write_json


def test_assemble_merges_in_plan_order_and_records_owners(run_dir: Path):
    """test_assemble_merges_in_plan_order_and_records_owners: planned files come first, in order; extra files
    (e.g. fixups) follow; each key maps to its file."""
    write_json(
        run_dir / "cards" / "fixups.json",
        [
            {
                "key": "fx_one",
                "type": "basic",
                "source": "notes",
                "topic": "cells",
                "origin": "source",
                "pages": ["p001"],
                "front": "Q?",
                "back": "A",
            }
        ],
    )
    cards, owners, errors = assemble_cards.assemble(run_dir)
    assert errors == []
    assert [c["key"] for c in cards] == [c["key"] for c in NOTES_CARDS + PACKET_CARDS] + ["fx_one"]
    assert owners["fx_one"] == "fixups.json" and owners["nt_cell"] == "S01.json"


def test_assemble_reports_duplicate_keys(run_dir: Path):
    """test_assemble_reports_duplicate_keys: the same key in two files is an error naming both files."""
    write_json(run_dir / "cards" / "fixups.json", [NOTES_CARDS[0]])
    _, _, errors = assemble_cards.assemble(run_dir)
    assert errors == ["duplicate key 'nt_cell' in fixups.json and S01.json"]


def test_assemble_into_build_writes_build_files(run_dir: Path):
    """test_assemble_into_build_writes_build_files: build/cards.json and build/card_owners.json are written."""
    assemble_cards.assemble_into_build(run_dir)
    assert len(json.loads((run_dir / "build" / "cards.json").read_text())) == len(NOTES_CARDS + PACKET_CARDS)
    assert json.loads((run_dir / "build" / "card_owners.json").read_text())["pk_eq"] == "S02.json"


def test_assemble_into_build_writes_nothing_on_missing_planned_file(run_dir: Path):
    """test_assemble_into_build_writes_nothing_on_missing_planned_file: a subset in the plan without a card file
    is an error, and no build files are written."""
    (run_dir / "cards" / "S02.json").unlink()
    _, _, errors = assemble_cards.assemble_into_build(run_dir)
    assert errors == [f"missing card file {run_dir / 'cards' / 'S02.json'}"]
    assert not (run_dir / "build" / "cards.json").exists()
