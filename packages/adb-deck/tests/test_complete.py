"""Tests for adb_deck/complete.py."""

import json
from pathlib import Path

import pytest

from adb_core.common import sha256_file
from adb_deck import complete
from adb_testkit import write_json

pytestmark = pytest.mark.integration


def _sign(run_dir: Path, sha: str) -> None:
    write_json(
        run_dir / "refine" / "signoff.json",
        {
            "status": "clean",
            "round": 1,
            "rounds": 1,
            "deck_sha256": sha,
            "cards": 8,
            "card_reviews_total": 8,
            "deferred": [],
            "accepted_note": None,
            "signed_at": "2026-01-01T00:00:00+00:00",
        },
    )


def test_complete_refuses_unsigned_deck(built_run_dir: Path, tmp_path: Path):
    """test_complete_refuses_unsigned_deck: a deck whose bytes differ from the signed-off deck is not delivered."""
    _sign(built_run_dir, "0" * 64)
    assert complete.complete(built_run_dir, tmp_path / "out") == 1
    assert not (tmp_path / "out" / "Test Deck.apkg").exists()


def test_complete_delivers_signed_deck_and_companions(built_run_dir: Path, tmp_path: Path):
    """test_complete_delivers_signed_deck_and_companions: the exact signed bytes ship with a study guide,
    transcriptions, rebuild source and a summary."""
    _sign(built_run_dir, sha256_file(built_run_dir / "build" / "deck.apkg"))
    out = tmp_path / "out"
    assert complete.complete(built_run_dir, out) == 0
    assert sha256_file(out / "Test Deck.apkg") == sha256_file(built_run_dir / "build" / "deck.apkg")
    summary = json.loads((out / "summary.json").read_text())
    assert summary["validated"] and (summary["notes"], summary["cards"]) == (7, 8)
    assert summary["origins"] == {"source": 5, "model_answer": 1, "correction": 1}
    assert summary["corrections"][0]["key"] == "pk_eq"
    assert (out / "Study Guide.html").exists() and len(list((out / "transcriptions").glob("*.md"))) == 2
    assert sorted(p.name for p in (out / "deck-source" / "media").iterdir()) == ["p002_box.jpg", "p002_box_masked.jpg"]
