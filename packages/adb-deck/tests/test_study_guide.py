"""Tests for adb_deck/study_guide.py."""

import json
from pathlib import Path

from adb_deck import assemble_cards, study_guide
from adb_testkit import write_json


def test_render_guide_structure_and_highlights(run_dir: Path):
    """test_render_guide_structure_and_highlights: one part per source, cloze answers highlighted, chem subscripts,
    corrections listed up top, and each figure embedded once."""
    assemble_cards.assemble_into_build(run_dir)
    page = study_guide.render_guide(run_dir)
    assert page.index("Part 1 · Class notes") < page.index("Part 2 · Review packet")
    assert "<mark>Vacuole</mark>" in page
    assert "C<sub>6</sub>H<sub>12</sub>O<sub>6</sub>" in page
    assert "Spots worth a second look" in page and "the packet swapped the products." in page
    assert page.count('alt="p002_box.jpg"') == 1
    assert "#1 = LABEL-A<br>#2 = LABEL-B" in page
    assert "IMG_" not in page and "{{" not in page


def test_render_guide_escapes_text_but_keeps_card_html(run_dir: Path):
    """test_render_guide_escapes_text_but_keeps_card_html: plain-text labels from categories.json are escaped,
    while card fields, which are HTML by design, render as markup."""
    cats = json.loads((run_dir / "categories.json").read_text())
    cats["sources"][0]["label"] = "Notes & <drafts>"
    write_json(run_dir / "categories.json", cats)
    assemble_cards.assemble_into_build(run_dir)
    page = study_guide.render_guide(run_dir)
    assert "Part 1 · Notes &amp; &lt;drafts&gt;" in page
    assert "<mark>Vacuole</mark>" in page and "&lt;mark&gt;" not in page
