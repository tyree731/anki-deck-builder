"""Tests for adb_review/shoot.py."""

from pathlib import Path

import pytest
from PIL import Image

from adb_review import render_cards, shoot


def test_pack_respects_max_height(tmp_path: Path):
    """test_pack_respects_max_height: shots stack into sheets no taller than the limit (unless one shot is)."""
    shots = []
    for i, h in enumerate([700, 700, 700, 2500]):
        p = tmp_path / f"s{i}.png"
        Image.new("RGB", (400, h), "white").save(p)
        shots.append(p)
    sheets = shoot.pack(shots, tmp_path / "sheets", "changed", max_h=1500)
    assert [s.name for s in sheets] == ["changed_01.jpg", "changed_02.jpg", "changed_03.jpg"]
    assert [Image.open(s).size[1] for s in sheets] == [2 * 706, 706, 2506]


@pytest.mark.integration
@pytest.mark.browser
def test_shoot_round_screenshots_and_trims(built_run_dir: Path, tmp_path: Path):
    """test_shoot_round_screenshots_and_trims: every selected card gets a trimmed screenshot and sheets are packed."""
    rd = tmp_path / "round_1"
    render_cards.render(built_run_dir / "build" / "deck.apkg", rd, 1)
    info = shoot.shoot_round(rd, only={"nt_cell:1", "nt_box_1:1"}, sheet_prefix="changed")
    assert info["shots"] == 2 and info["failed"] == []
    pngs = sorted((rd / "shots").glob("*.png"))
    assert len(pngs) == 2 and all(Image.open(p).size[1] < 2600 for p in pngs)
    assert info["sheets"]
