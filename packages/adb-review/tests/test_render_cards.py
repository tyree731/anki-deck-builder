"""Tests for adb_review/render_cards.py."""

import json
from pathlib import Path

import pytest

from adb_deck import make_deck
from adb_review import render_cards
from adb_testkit import NOTES_CARDS, write_json


def test_plain_strips_markup_and_entities():
    """test_plain_strips_markup_and_entities: tags and styles vanish, <br> becomes a newline, entities decode."""
    assert render_cards.plain("<style>.x{}</style><b>A</b><br>B &amp; C") == "A\nB & C"


def test_phrase_in_is_word_bounded():
    """test_phrase_in_is_word_bounded: matches whole words only and ignores very short phrases."""
    assert render_cards.phrase_in("vacuole", "the central vacuole")
    assert not render_cards.phrase_in("dependent", "the independent variable")
    assert not render_cards.phrase_in("is", "this is it")


def test_page_html_escapes_label_but_not_card_html_or_css():
    """test_page_html_escapes_label_but_not_card_html_or_css: the rendered card sides and the note type's CSS go
    in as-is (a child selector must survive); only the header label is escaped."""
    page = render_cards.page_html(".q > b { color: red }", "<b>Q</b>", "<i>A</i>", "#1 | k:1 | A & B", 820, 826)
    assert ".q > b { color: red }" in page and "<b>Q</b>" in page and "<i>A</i>" in page
    assert "#1 | k:1 | A &amp; B" in page and ".side { width:820px;" in page


@pytest.mark.integration
def test_render_writes_pages_index_and_clean_mechanical(built_run_dir: Path, tmp_path: Path):
    """test_render_writes_pages_index_and_clean_mechanical: one page and index row per card; a clean deck has
    no mechanical findings."""
    info = render_cards.render(built_run_dir / "build" / "deck.apkg", tmp_path / "r1", 1)
    index = json.loads((tmp_path / "r1" / "index.json").read_text())
    assert info["cards"] == len(index) == 8
    assert {r["card_id"] for r in index} >= {"nt_cell:1", "pk_eq:1", "pk_eq:2", "nt_box_2:1"}
    assert all((tmp_path / "r1" / "html" / r["page"].replace(".png", ".html")).exists() for r in index)
    assert json.loads((tmp_path / "r1" / "mechanical.json").read_text())["issues"] == []


@pytest.mark.integration
def test_render_flags_cloze_leak(run_dir: Path, tmp_path: Path):
    """test_render_flags_cloze_leak: a hidden answer visible elsewhere on the front becomes a 'giveaway' finding."""
    leaky = [dict(c) for c in NOTES_CARDS]
    leaky[1]["text"] = "{{c1::Vacuole}}: stores water; the large central vacuole supports plant cells."
    write_json(run_dir / "cards" / "S01.json", leaky)
    make_deck.make(run_dir, allow_lint_errors=True)
    render_cards.render(run_dir / "build" / "deck.apkg", tmp_path / "r1", 1)
    issues = json.loads((tmp_path / "r1" / "mechanical.json").read_text())["issues"]
    assert [(i["card_id"], i["category"]) for i in issues] == [("nt_vacuole:1", "giveaway")]


@pytest.mark.integration
def test_render_lists_changed_cards_against_previous_round(built_run_dir: Path, tmp_path: Path):
    """test_render_lists_changed_cards_against_previous_round: only cards whose text or media changed are listed."""
    render_cards.render(built_run_dir / "build" / "deck.apkg", tmp_path / "r1", 1)
    edited = [dict(c) for c in NOTES_CARDS]
    edited[0]["back"] = "Cells (one or more)"
    write_json(built_run_dir / "cards" / "S01.json", edited)
    assert make_deck.make(built_run_dir) == 0
    info = render_cards.render(
        built_run_dir / "build" / "deck.apkg", tmp_path / "r2", 2, tmp_path / "r1" / "index.json"
    )
    assert info["changed"] == ["nt_cell:1"]
    assert (tmp_path / "r2" / "changed.txt").read_text() == "nt_cell:1\n"
