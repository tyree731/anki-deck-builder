"""Tests for adb_deck/build_deck.py."""

import json
import sqlite3
import zipfile
from pathlib import Path

import pytest

from adb_deck import assemble_cards, build_deck


def test_expand_macros():
    """test_expand_macros: {{img:..}} becomes a prefixed <img> and {{chem:..}} gets subscripts."""
    out = build_deck.expand("See {{img: fig.jpg}} and {{chem:H2O}}", "deck_")
    assert out == 'See <img src="deck_fig.jpg"> and H<sub>2</sub>O'


def test_note_types_are_stable_per_deck():
    """test_note_types_are_stable_per_deck: the same deck name gives the same note-type ids; another deck gets
    different ones, so two decks never fight over a note type."""
    a1, a2, b = build_deck.note_types("Biology"), build_deck.note_types("Biology"), build_deck.note_types("Chemistry")
    assert [m.model_id for m in a1] == [m.model_id for m in a2]
    assert {m.model_id for m in a1}.isdisjoint({m.model_id for m in b})


def test_media_prefix_slugs_deck_name():
    """test_media_prefix_slugs_deck_name: media files are prefixed with a slug of the deck name."""
    assert build_deck.media_prefix("Grade 7: Cells") == "grade_7_cells_"


def test_referenced_media_collects_every_field():
    """test_referenced_media_collects_every_field: images, diagram files and inline {{img:}} macros are all found."""
    card = {
        "images": ["a.jpg"],
        "masked": "m.jpg",
        "answer_image": "b.jpg",
        "back": "x {{img:c.jpg}}",
        "extra": "{{img: d.jpg}}",
    }
    assert sorted(build_deck.referenced_media(card)) == ["a.jpg", "b.jpg", "c.jpg", "d.jpg", "m.jpg"]


@pytest.mark.integration
def test_build_writes_subdecks_media_and_labels(run_dir: Path, tmp_path: Path):
    """test_build_writes_subdecks_media_and_labels: the package holds both subdecks, prefixed media, provenance
    labels from `origin`, and a footer with no internal ids."""
    assemble_cards.assemble_into_build(run_dir)
    info = build_deck.build(run_dir, tmp_path / "deck.apkg")
    assert info["decks"] == {"Test Deck::1 Class Notes": 4, "Test Deck::2 Review Packet": 3}
    with zipfile.ZipFile(tmp_path / "deck.apkg") as z:
        assert sorted(json.loads(z.read("media")).values()) == [
            "test_deck_p002_box.jpg",
            "test_deck_p002_box_masked.jpg",
        ]
        z.extract("collection.anki2", tmp_path)
    joined = "\n".join(
        row[0] for row in sqlite3.connect(tmp_path / "collection.anki2").execute("select flds from notes")
    )
    assert "✎ Model answer" in joined and "⚠ Careful: the packet swapped the products." in joined
    assert "C<sub>6</sub>H<sub>12</sub>O<sub>6</sub>" in joined
    assert "Class notes · Cells" in joined


def test_build_fails_on_missing_media(run_dir: Path, tmp_path: Path):
    """test_build_fails_on_missing_media: a card pointing at an absent image stops the build."""
    assemble_cards.assemble_into_build(run_dir)
    (run_dir / "media" / "p002_box.jpg").unlink()
    with pytest.raises(FileNotFoundError):
        build_deck.build(run_dir, tmp_path / "deck.apkg")
