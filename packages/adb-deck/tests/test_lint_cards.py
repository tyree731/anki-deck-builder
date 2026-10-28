"""Tests for adb_deck/lint_cards.py."""

import json
from pathlib import Path

from adb_deck import assemble_cards, lint_cards
from adb_testkit import NOTES_CARDS, PACKET_CARDS, write_json


def _lint_with(run_dir: Path, extra_cards: list[dict]) -> dict:
    cards = NOTES_CARDS + PACKET_CARDS + extra_cards
    write_json(run_dir / "build" / "cards.json", cards)
    return lint_cards.lint(run_dir)


def _rules(items: list[dict], key: str) -> set[str]:
    return {i["rule"] for i in items if i["key"] == key}


def test_phrase_in_is_word_bounded():
    """test_phrase_in_is_word_bounded: 'dependent variable' does not match inside 'independent variable'."""
    front = lint_cards.cloze_front(
        "The {{c1::independent variable}} changes; the {{c2::dependent variable}} is measured.", 2
    )
    assert not lint_cards.phrase_in("dependent variable", front)
    assert lint_cards.phrase_in("Vacuole", "[...]: the large central vacuole")


def test_complementary_detects_paired_terms():
    """test_complementary_detects_paired_terms: prokaryote/eukaryote-style pairs are flagged; unrelated terms are
    not."""
    assert lint_cards.complementary("prokaryotes", "eukaryotes")
    assert lint_cards.complementary("independent variable", "dependent variable")
    assert lint_cards.complementary("qualitative", "quantitative")
    assert not lint_cards.complementary("nucleus", "ribosomes")


def test_list_items_counts_list_answers():
    """test_list_items_counts_list_answers: comma, semicolon and 'and' separated answers count as list items."""
    assert lint_cards.list_items("Cell membrane, cytoplasm, nucleus and mitochondria") == 4
    assert lint_cards.list_items("Cells") == 1


def test_cloze_front_blanks_only_the_target_deletion():
    """test_cloze_front_blanks_only_the_target_deletion: other deletions show their answers on that card."""
    assert lint_cards.cloze_front("{{c1::A}} then {{c2::B}}", 1) == "[...] then B"


def test_lint_fixture_is_clean(run_dir: Path):
    """test_lint_fixture_is_clean: the conftest card set has no errors, including a chem macro inside a cloze."""
    assemble_cards.assemble_into_build(run_dir)
    report = lint_cards.lint(run_dir)
    assert report["errors"] == [], report["errors"]
    assert report["notes"] == len(NOTES_CARDS) + len(PACKET_CARDS)


def test_lint_flags_internal_reference_and_cloze_leak(run_dir: Path):
    """test_lint_flags_internal_reference_and_cloze_leak: photo ids on a card (L04) and a hidden word shown
    elsewhere on the front (L06) are errors."""
    report = _lint_with(
        run_dir,
        [
            {
                "key": "leak",
                "type": "cloze",
                "source": "notes",
                "topic": "cells",
                "origin": "source",
                "pages": ["p001"],
                "text": "{{c1::Vacuole}}: the large central vacuole supports the cell.",
                "extra": "(photo IMG_7235)",
            }
        ],
    )
    assert {"L04", "L06"} <= _rules(report["errors"], "leak")


def test_lint_warns_paired_terms_missing_count_and_bare_term(run_dir: Path):
    """test_lint_warns_paired_terms_missing_count_and_bare_term: L07, L08 and L09 are warnings, not errors."""
    report = _lint_with(
        run_dir,
        [
            {
                "key": "pair",
                "type": "cloze",
                "source": "notes",
                "topic": "cells",
                "origin": "source",
                "pages": ["p001"],
                "text": "{{c1::Prokaryotes}} have no nucleus; {{c2::eukaryotes}} do.",
            },
            {
                "key": "list",
                "type": "basic",
                "source": "notes",
                "topic": "cells",
                "origin": "source",
                "pages": ["p001"],
                "front": "Which structures do plant and animal cells share?",
                "back": "Membrane, cytoplasm, nucleus",
            },
            {
                "key": "bare",
                "type": "basic",
                "source": "notes",
                "topic": "cells",
                "origin": "source",
                "pages": ["p001"],
                "front": "Constants",
                "back": "Factors kept the same.",
            },
        ],
    )
    assert "L07" in _rules(report["warnings"], "pair")
    assert "L08" in _rules(report["warnings"], "list")
    assert "L09" in _rules(report["warnings"], "bare")
    assert not {e["key"] for e in report["errors"]} & {"pair", "list", "bare"}


def test_lint_rejects_unmasked_diagram_front(run_dir: Path):
    """test_lint_rejects_unmasked_diagram_front: a diagram whose 'masked' image is a plain crop is an L11 error."""
    report = _lint_with(
        run_dir,
        [
            {
                "key": "unmasked",
                "type": "diagram",
                "source": "notes",
                "topic": "microscopes",
                "origin": "source",
                "pages": ["p002"],
                "prompt": "What is #1?",
                "masked": "p002_box.jpg",
                "answer": "#1 = A",
                "answer_image": "p002_box_masked.jpg",
            }
        ],
    )
    assert "L11" in _rules(report["errors"], "unmasked")


def test_lint_requires_page_coverage_and_honors_waivers(run_dir: Path):
    """test_lint_requires_page_coverage_and_honors_waivers: an uncited page is an L13 error until waived with a
    reason."""
    cards = [c for c in NOTES_CARDS + PACKET_CARDS if "p005" not in c["pages"]]
    write_json(run_dir / "build" / "cards.json", cards)
    assert "L13" in _rules(lint_cards.lint(run_dir)["errors"], "p005")
    write_json(
        run_dir / "build" / "waivers.json",
        {"waivers": [{"rule": "L13", "key": "p005", "reason": "covered by the packet cards"}]},
    )
    report = lint_cards.lint(run_dir)
    assert not report["errors"] and report["waived"][0]["key"] == "p005"


def test_lint_rejects_unknown_macros_and_missing_media(run_dir: Path):
    """test_lint_rejects_unknown_macros_and_missing_media: only cloze/img/chem macros are allowed; media must exist."""
    report = _lint_with(
        run_dir,
        [
            {
                "key": "macro",
                "type": "basic",
                "source": "notes",
                "topic": "cells",
                "origin": "source",
                "pages": ["p001"],
                "front": "What is {{weird:thing}}?",
                "back": "x {{img:absent.jpg}}",
            }
        ],
    )
    assert {"L05", "L03"} <= _rules(report["errors"], "macro")


def test_lint_into_build_records_cards_hash(run_dir: Path):
    """test_lint_into_build_records_cards_hash: build/lint.json holds the report and the hash of the cards it
    linted, which the synthesize gate compares."""
    assemble_cards.assemble_into_build(run_dir)
    report = lint_cards.lint_into_build(run_dir)
    assert json.loads((run_dir / "build" / "lint.json").read_text()) == report
    assert report["errors"] == [] and len(report["cards_sha256"]) == 64
