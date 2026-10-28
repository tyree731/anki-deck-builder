"""Tests for adb_core/digest.py."""

import json
from pathlib import Path

from adb_core import digest
from adb_testkit import GOOD_HEADER, write_json


def test_header_field_and_section_helpers():
    """test_header_field_and_section_helpers: header bullets and '## ' sections are read from a transcript."""
    text = GOOD_HEADER + "\n## Flags\nStudent mixed up IV and DV.\n"
    assert digest.header_field(text, "Source guess") == "notebook"
    assert digest.section(text, "Flags") == "Student mixed up IV and DV."
    assert digest.header_field(text, "Nope") == ""


def test_write_digest_lists_every_page_and_collects_flags(run_dir: Path):
    """test_write_digest_lists_every_page_and_collects_flags: one row per unit, figure counts, and a flags
    section."""
    text = digest.write_digest(run_dir).read_text()
    assert all(f"| p00{i} |" in text for i in range(1, 6))
    assert "| p002 | IMG_2.jpg | notebook | summary of p002 | cells | good | 2 |" in text
    assert "### p003" in text and "wrong constant" in text


def test_write_digest_shows_excluded_units_with_reason(run_dir: Path):
    """test_write_digest_shows_excluded_units_with_reason: excluded units appear with their reason instead of a
    summary."""
    manifest = json.loads((run_dir / "manifest.json").read_text())
    manifest["units"][4].update(excluded=True, exclude_reason="blank page")
    write_json(run_dir / "manifest.json", manifest)
    assert "(blank page)" in digest.write_digest(run_dir).read_text()
