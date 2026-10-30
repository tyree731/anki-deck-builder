"""Tests for adb_core/common.py."""

import hashlib
from pathlib import Path

from adb_core import common, wsl


def test_chem_html_subscripts_atoms_not_coefficients():
    """test_chem_html_subscripts_atoms_not_coefficients: digits after an element are subscripts; leading
    coefficients stay."""
    assert common.chem_html("6CO2 + 6H2O") == "6CO<sub>2</sub> + 6H<sub>2</sub>O"
    assert common.chem_html("C6H12O6") == "C<sub>6</sub>H<sub>12</sub>O<sub>6</sub>"


def test_chem_html_handles_parentheses():
    """test_chem_html_handles_parentheses: a count after a closing parenthesis is a subscript."""
    assert common.chem_html("Ca(OH)2") == "Ca(OH)<sub>2</sub>"


def test_natural_key_orders_numbers_numerically():
    """test_natural_key_orders_numbers_numerically: IMG_9 sorts before IMG_10, case-insensitively."""
    names = ["IMG_10.jpg", "IMG_9.jpg", "img_100.jpg"]
    assert sorted(names, key=common.natural_key) == ["IMG_9.jpg", "IMG_10.jpg", "img_100.jpg"]


def test_slugify_normalizes_and_truncates():
    """test_slugify_normalizes_and_truncates: punctuation collapses to underscores and long names are cut."""
    assert common.slugify("Grade 7 Science: Cells!") == "grade_7_science_cells"
    assert common.slugify("x" * 80, max_len=10) == "x" * 10
    assert common.slugify("!!!") == "deck"


def test_stable_id_is_deterministic_and_in_range():
    """test_stable_id_is_deterministic_and_in_range: same parts give the same id; ids fit Anki's int range."""
    assert common.stable_id("a", "b") == common.stable_id("a", "b")
    assert common.stable_id("a", "b") != common.stable_id("a", "c")
    assert 1_000_000 <= common.stable_id("anything") < 2**31


def test_write_json_roundtrip_leaves_no_temp_file(tmp_path: Path):
    """test_write_json_roundtrip_leaves_no_temp_file: write_json is readable by read_json and cleans up its temp
    file."""
    target = tmp_path / "nested" / "data.json"
    common.write_json(target, {"ok": True, "text": "✎"})
    assert common.read_json(target) == {"ok": True, "text": "✎"}
    assert not list(target.parent.glob("*.tmp"))


def test_sha256_file_matches_hashlib(tmp_path: Path):
    """test_sha256_file_matches_hashlib: the streaming hash equals hashlib's one-shot digest."""
    f = tmp_path / "blob.bin"
    f.write_bytes(b"abc" * 100_000)
    assert common.sha256_file(f) == hashlib.sha256(f.read_bytes()).hexdigest()


def test_run_paths_layout(tmp_path: Path):
    """test_run_paths_layout: the run-dir layout names every artifact location the phases use."""
    p = common.run_paths(tmp_path)
    assert p["state"] == tmp_path / "state.json"
    assert p["cards"] == tmp_path / "cards" and p["refine"] == tmp_path / "refine"
    assert set(common.PHASES) == {"organize", "extract", "categorize", "synthesize", "refine", "complete"}


def test_find_browser_honors_override(tmp_path: Path, monkeypatch):
    """test_find_browser_honors_override: ANKI_DECK_BUILDER_CHROME wins when it points at an existing file."""
    fake = tmp_path / "chrome"
    fake.write_text("")
    monkeypatch.setenv("ANKI_DECK_BUILDER_CHROME", str(fake))
    assert common.find_browser() == str(fake)


def test_find_anki_honors_override(tmp_path: Path, monkeypatch):
    """test_find_anki_honors_override: ANKI_DECK_BUILDER_ANKI wins when it points at an existing path."""
    fake = tmp_path / "Anki.app"
    fake.mkdir()
    monkeypatch.setenv("ANKI_DECK_BUILDER_ANKI", str(fake))
    assert common.find_anki() == str(fake)


def test_find_anki_sees_windows_install_from_wsl(tmp_path: Path, monkeypatch):
    """test_find_anki_sees_windows_install_from_wsl: under WSL, Anki installed for a Windows user is found on the
    mounted drive, whatever the case of its file name (older installers wrote anki.exe, current ones Anki.exe)."""
    exe = tmp_path / "c/Users/kid/AppData/Local/Programs/Anki/anki.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("")
    monkeypatch.delenv("ANKI_DECK_BUILDER_ANKI", raising=False)
    monkeypatch.setattr(common.platform, "system", lambda: "Linux")
    monkeypatch.setattr(wsl, "is_wsl", lambda: True)
    monkeypatch.setattr(wsl, "mount_root", lambda: tmp_path)
    assert common.find_anki() == str(exe)


def test_find_anki_sees_the_flatpak(tmp_path: Path, monkeypatch):
    """test_find_anki_sees_the_flatpak: on Linux, the launcher Flatpak keeps for an installed Anki counts."""
    launcher = tmp_path / ".local/share/flatpak/exports/bin/net.ankiweb.Anki"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("")
    monkeypatch.delenv("ANKI_DECK_BUILDER_ANKI", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(common.platform, "system", lambda: "Linux")
    monkeypatch.setattr(wsl, "is_wsl", lambda: False)
    monkeypatch.setattr(common.shutil, "which", lambda name: None)
    assert common.find_anki() == str(launcher)


def test_load_config_has_every_section():
    """test_load_config_has_every_section: config.toml carries the sections the scripts read."""
    cfg = common.load_config()
    for section in (
        "paths",
        "organize",
        "extract",
        "synthesize",
        "refine",
        "complete",
        "checkpoints",
        "labels",
        "lint",
        "deliver",
    ):
        assert section in cfg
