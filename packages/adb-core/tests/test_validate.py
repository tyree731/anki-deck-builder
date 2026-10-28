"""Tests for adb_core/validate.py."""

import json
from pathlib import Path

import pytest

from adb_core import validate
from adb_testkit import TRANSCRIPT, write_json

GOOD = TRANSCRIPT.format(
    pid="p001",
    file="a.jpg",
    guess="notebook",
    summary="notes",
    topics="cells",
    body="Text",
    figs="None.",
    fact="x",
    flags="none",
)


def test_validate_transcript_text_accepts_template():
    """test_validate_transcript_text_accepts_template: the documented transcript format passes."""
    assert validate.validate_transcript_text("p001", GOOD) == []


def test_validate_transcript_text_reports_missing_and_empty():
    """test_validate_transcript_text_reports_missing_and_empty: a missing header bullet and an empty
    transcription are both reported."""
    bad = GOOD.replace("- Topics: cells\n", "").replace("## Transcription\nText\n", "## Transcription\n\n")
    errs = validate.validate_transcript_text("p001", bad)
    assert any("Topics" in e for e in errs) and any("empty" in e for e in errs)


def test_validate_transcript_text_reports_wrong_title_and_order():
    """test_validate_transcript_text_reports_wrong_title_and_order: the '# <page id>' title and heading order are
    checked."""
    swapped = (
        GOOD.replace("## Equations", "## TMP").replace("## Figures", "## Equations").replace("## TMP", "## Figures")
    )
    errs = validate.validate_transcript_text("p002", swapped)
    assert any("first line" in e for e in errs) and any("out of order" in e for e in errs)


def test_validate_manifest_accepts_fixture(run_dir: Path):
    """test_validate_manifest_accepts_fixture: a well-formed manifest whose files exist passes."""
    assert validate.validate_manifest(run_dir) == []


def test_validate_manifest_reports_missing_page_file(run_dir: Path):
    """test_validate_manifest_reports_missing_page_file: a unit pointing at a missing page image is an error."""
    (run_dir / "pages" / "p001.jpg").unlink()
    assert any("p001" in e and "missing" in e for e in validate.validate_manifest(run_dir))


def test_validate_figures_checks_names_media_and_mask_numbers(run_dir: Path):
    """test_validate_figures_checks_names_media_and_mask_numbers: figure files must be page-prefixed, exist in
    media/, and number their masks 1..n."""
    assert validate.validate_figures(run_dir, ["p002"]) == []
    sidecar = json.loads((run_dir / "figures" / "p002.json").read_text())
    sidecar["figures"][1]["mask_map"] = [{"n": 1, "label": "A"}, {"n": 3, "label": "B"}]
    sidecar["figures"].append(
        {
            "file": "p002_missing.jpg",
            "kind": "crop",
            "title": "t",
            "description": "d",
            "labels": [],
            "confidence": "low",
        }
    )
    write_json(run_dir / "figures" / "p002.json", sidecar)
    errs = validate.validate_figures(run_dir, ["p002"])
    assert any("1..2" in e for e in errs) and any("p002_missing.jpg" in e for e in errs)


def test_validate_figures_requires_sidecar(run_dir: Path):
    """test_validate_figures_requires_sidecar: every page needs a sidecar, even an empty one."""
    (run_dir / "figures" / "p001.json").unlink()
    assert any("sidecar missing" in e for e in validate.validate_figures(run_dir, ["p001"]))


def test_validate_categories_requires_every_page_assigned(run_dir: Path):
    """test_validate_categories_requires_every_page_assigned: unassigned pages and unknown topics are errors."""
    assert validate.validate_categories(run_dir) == []
    cats = json.loads((run_dir / "categories.json").read_text())
    del cats["page_sources"]["p005"]
    cats["page_topics"]["p004"] = ["nonexistent"]
    write_json(run_dir / "categories.json", cats)
    errs = validate.validate_categories(run_dir)
    assert any("p005 has no source" in e for e in errs) and any("unknown topic 'nonexistent'" in e for e in errs)


def test_validate_cards_file_schema_rules(tmp_path: Path):
    """test_validate_cards_file_schema_rules: basic needs a back, corrections need text, no extra fields."""
    f = tmp_path / "c.json"
    f.write_text(
        json.dumps(
            [
                {
                    "key": "ok_basic",
                    "type": "basic",
                    "source": "notes",
                    "topic": "cells",
                    "origin": "source",
                    "pages": ["p001"],
                    "front": "Define: cell",
                    "back": "basic unit of life",
                },
                {
                    "key": "bad_basic",
                    "type": "basic",
                    "source": "notes",
                    "topic": "cells",
                    "origin": "source",
                    "pages": ["p001"],
                    "front": "Q?",
                },
                {
                    "key": "bad_correction",
                    "type": "cloze",
                    "source": "notes",
                    "topic": "cells",
                    "origin": "correction",
                    "pages": ["p001"],
                    "text": "{{c1::x}}",
                },
                {
                    "key": "bad_extra",
                    "type": "cloze",
                    "source": "notes",
                    "topic": "cells",
                    "origin": "source",
                    "pages": ["p001"],
                    "text": "{{c1::x}}",
                    "note": "not a field",
                },
            ]
        )
    )
    errs = validate.validate_cards_file(f)
    assert any(": 1: " in e and "'back'" in e for e in errs)
    assert any(": 2: " in e and "'correction'" in e for e in errs)
    assert any(": 3: " in e and "note" in e for e in errs)
    assert not any(": 0: " in e for e in errs)


def test_validate_cards_file_checks_media_and_taxonomy(run_dir: Path):
    """test_validate_cards_file_checks_media_and_taxonomy: with a run dir, unknown topics and missing media fail."""
    f = run_dir / "cards" / "extra.json"
    write_json(
        f,
        [
            {
                "key": "x",
                "type": "basic",
                "source": "notes",
                "topic": "zzz",
                "origin": "source",
                "pages": ["p001"],
                "front": "Q?",
                "back": "A {{img:nope.jpg}}",
            }
        ],
    )
    errs = validate.validate_cards_file(f, run_dir)
    assert any("unknown topic 'zzz'" in e for e in errs) and any("nope.jpg" in e for e in errs)


def test_validate_triage_defer_only_for_low(tmp_path: Path):
    """test_validate_triage_defer_only_for_low: deferring is allowed for low-severity findings only."""
    f = tmp_path / "triage.json"
    decision = {
        "finding": "findings_R1_01.json#0",
        "card_id": "k:1",
        "severity": "high",
        "decision": "defer",
        "reason": "later please",
    }
    f.write_text(json.dumps({"round": 1, "decisions": [decision]}))
    assert validate.validate_triage_file(f)
    decision["severity"] = "low"
    f.write_text(json.dumps({"round": 1, "decisions": [decision]}))
    assert validate.validate_triage_file(f) == []


def test_unreadable_or_malformed_files_raise_load_error(tmp_path: Path):
    """test_unreadable_or_malformed_files_raise_load_error: a missing file or bad JSON raises LoadError, not a raw
    OSError or JSONDecodeError."""
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    for path in (tmp_path / "missing.json", bad):
        with pytest.raises(validate.LoadError):
            validate.validate_findings_file(path)
