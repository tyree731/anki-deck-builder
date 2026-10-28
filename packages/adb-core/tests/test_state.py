"""Tests for adb_core/state.py: mode dispatch, phase gates, batch tracking and resume."""

import json
from pathlib import Path

import pytest

from adb_core import state
from adb_testkit import write_json


def _state(run_dir: Path) -> dict:
    return json.loads((run_dir / "state.json").read_text())


def _mark_all_done(run_dir: Path) -> None:
    st = _state(run_dir)
    for ph in st["phases"].values():
        ph["status"] = "done"
    write_json(run_dir / "state.json", st)


def _plan(run_dir: Path, *pages: list[str]) -> None:
    subsets = [{"id": f"E{i:02d}", "pages": p, "weight": len(p)} for i, p in enumerate(pages, 1)]
    write_json(run_dir / "subsets" / "extract.json", {"stage": "extract", "subsets": subsets})


def test_detect_mode_none_invalid_and_new(tmp_path: Path):
    """test_detect_mode_none_invalid_and_new: no folder gives none, a non-folder invalid, and a fresh folder new
    with its run and output dirs inside it."""
    assert state.detect_mode(None) == {"mode": "none"}
    assert state.detect_mode(tmp_path / "missing")["mode"] == "invalid"
    info = state.detect_mode(tmp_path)
    assert info["mode"] == "new" and info["run_dir"] == str(tmp_path.resolve() / ".anki-build")
    assert info["output_dir"] == str(tmp_path.resolve() / "anki-output")


def test_detect_mode_resume_and_complete(run_dir: Path):
    """test_detect_mode_resume_and_complete: an existing run resumes at its first pending phase; all done is
    complete."""
    info = state.detect_mode(run_dir.parent)
    assert (info["mode"], info["next"]) == ("resume", "organize")
    _mark_all_done(run_dir)
    assert state.detect_mode(run_dir.parent)["mode"] == "complete"


def test_init_run_refuses_existing_run_without_force(run_dir: Path):
    """test_init_run_refuses_existing_run_without_force: re-initializing needs force so a run isn't lost by
    accident."""
    with pytest.raises(FileExistsError):
        state.init_run(run_dir.parent)
    state.init_run(run_dir.parent, deck_name="Bio", force=True)
    assert _state(run_dir)["deck_name"] == "Bio"


def test_advance_phase_enforces_order_and_gate(run_dir: Path):
    """test_advance_phase_enforces_order_and_gate: only the next phase can advance, and only once its gate passes;
    a blocked advance changes nothing."""
    assert "next phase to complete is 'organize'" in state.advance_phase(run_dir, "categorize")[0]
    assert any("contact sheets" in p for p in state.advance_phase(run_dir, "organize"))
    assert _state(run_dir)["phases"]["organize"]["status"] == "pending"


def test_verify_phase_organize_reports_missing_artifacts(run_dir: Path):
    """test_verify_phase_organize_reports_missing_artifacts: the organize gate needs contact sheets and a full plan."""
    problems = state.verify_phase(run_dir, "organize")
    assert any("contact sheets" in p for p in problems)
    assert any("extract subset plan" in p for p in problems)


def test_verify_phase_extract_requires_done_batches(run_dir: Path):
    """test_verify_phase_extract_requires_done_batches: transcripts alone don't pass; every subset must be done."""
    _plan(run_dir, ["p001", "p002", "p003", "p004", "p005"])
    assert any("E01" in p for p in state.verify_phase(run_dir, "extract"))
    state.set_batch(run_dir, "extract", "E01", "done")
    assert state.verify_phase(run_dir, "extract") == []


@pytest.mark.integration
def test_verify_phase_synthesize_detects_stale_lint(built_run_dir: Path):
    """test_verify_phase_synthesize_detects_stale_lint: editing cards.json after linting fails the synthesize gate."""
    assert state.verify_phase(built_run_dir, "synthesize") == []
    cards = json.loads((built_run_dir / "build" / "cards.json").read_text())
    write_json(built_run_dir / "build" / "cards.json", cards[:-1])
    assert any("stale" in p for p in state.verify_phase(built_run_dir, "synthesize"))


def test_set_batch_and_pending_subsets(run_dir: Path):
    """test_set_batch_and_pending_subsets: pending lists planned subsets, in order, until they are marked done."""
    _plan(run_dir, ["p001"], ["p002"], ["p003"])
    assert state.pending_subsets(run_dir, "extract") == ["E01", "E02", "E03"]
    state.set_batch(run_dir, "extract", "E01", "done", note="ok")
    state.set_batch(run_dir, "extract", "E03", "failed", note="timed out")
    assert state.pending_subsets(run_dir, "extract") == ["E02", "E03"]
    assert _state(run_dir)["batches"]["extract"]["E03"]["note"] == "timed out"


def test_reopen_phase_resets_later_phases(run_dir: Path):
    """test_reopen_phase_resets_later_phases: reopening a phase sets it and every later phase back to pending."""
    _mark_all_done(run_dir)
    state.reopen_phase(run_dir, "synthesize")
    st = _state(run_dir)
    assert [st["phases"][p]["status"] for p in state.PHASES] == ["done"] * 3 + ["pending"] * 3
    assert state.next_phase(st) == "synthesize"


def test_set_fields_updates_leaves_and_clears(run_dir: Path):
    """test_set_fields_updates_leaves_and_clears: given fields are saved, None leaves a field alone, "" clears it."""
    state.set_fields(run_dir, deck_name="Biology", purpose="Q1 test")
    state.set_fields(run_dir, audience="", purpose=None)
    st = _state(run_dir)
    assert (st["deck_name"], st["audience"], st["purpose"]) == ("Biology", None, "Q1 test")
