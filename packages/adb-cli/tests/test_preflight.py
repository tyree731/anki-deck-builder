"""Tests for adb_cli/preflight.py."""

from pathlib import Path

from adb_cli import preflight


def test_check_flags_only_required_failures():
    """test_check_flags_only_required_failures: a failed required check counts; a passed or optional one does not."""
    assert preflight.check("ok thing", True) is False
    assert preflight.check("optional thing", False, "meh", optional=True) is False
    assert preflight.check("required thing", False, "broken") is True


def test_run_checks_counts_a_missing_folder(tmp_path: Path, monkeypatch):
    """test_run_checks_counts_a_missing_folder: with a browser available, only the missing folder fails."""
    fake = tmp_path / "chrome"
    fake.write_text("")
    monkeypatch.setenv("ANKI_DECK_BUILDER_CHROME", str(fake))
    assert preflight.run_checks(tmp_path) == 0
    assert preflight.run_checks(tmp_path / "nope") == 1
