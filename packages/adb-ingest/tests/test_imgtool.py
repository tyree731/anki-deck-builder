"""Tests for adb_ingest/imgtool.py."""

import json
from pathlib import Path

import pytest
from PIL import Image

from adb_ingest import imgtool
from adb_testkit import invoke, page_image


@pytest.fixture
def page(tmp_path: Path) -> Path:
    path = tmp_path / "page.jpg"
    page_image(["hello"]).save(path, quality=95)
    return path


def test_grid_keeps_size(page: Path, tmp_path: Path):
    """test_grid_keeps_size: the grid overlay has the source image's exact pixel size."""
    assert imgtool.grid(page, tmp_path / "grid.jpg", step=100) == Image.open(page).size


def test_crop_rotates_then_crops_and_downscales(page: Path, tmp_path: Path):
    """test_crop_rotates_then_crops_and_downscales: rotation happens first, the box is clamped, max_side caps size."""
    assert imgtool.crop(page, tmp_path / "crop.jpg", (0, 0, 1600, 1200), rotate=90, max_side=800) == (800, 600)


def test_view_enhances_and_downscales(page: Path, tmp_path: Path):
    """test_view_enhances_and_downscales: a reading copy can be cropped, enhanced and capped in size."""
    assert imgtool.view(page, tmp_path / "v.jpg", box=(0, 0, 600, 400), enhance=True, max_side=300) == (300, 200)


def test_mask_paints_numbered_boxes(page: Path, tmp_path: Path):
    """test_mask_paints_numbered_boxes: each box is filled with the mask color, covering the label."""
    out = tmp_path / "masked.jpg"
    imgtool.mask(page, [{"n": 1, "box": [700, 900, 900, 960]}], out)
    pixel = Image.open(out).convert("RGB").getpixel((705, 905))
    assert isinstance(pixel, tuple)
    r, g, b = pixel[:3]
    assert r > 200 and g > 180 and b < 170  # yellow fill, not white paper or black text


def test_cover_uses_surrounding_paper_color(page: Path, tmp_path: Path):
    """test_cover_uses_surrounding_paper_color: a covered label takes the median color of the paper around it."""
    out = tmp_path / "covered.jpg"
    imgtool.cover(page, out, [(80, 110, 400, 150)])
    assert min(Image.open(out).convert("L").crop((80, 110, 400, 150)).tobytes()) > 230


def test_trim_removes_edges(page: Path, tmp_path: Path):
    """test_trim_removes_edges: trim cuts the requested pixels off each side."""
    assert imgtool.trim(page, tmp_path / "t.jpg", top=100, bottom=50, left=10, right=20) == (1200 - 30, 1600 - 150)


def test_sheet_tiles_images(page: Path, tmp_path: Path):
    """test_sheet_tiles_images: a sheet lays images out in the requested columns and tile size."""
    assert imgtool.sheet(tmp_path / "s.jpg", [page, page, page], cols=2, tile=(200, 150)) == (400, 2 * (150 + 24))


def test_flow_returns_boxes_for_masking(tmp_path: Path):
    """test_flow_returns_boxes_for_masking: a redrawn flow chart comes with one numbered box per step."""
    out = tmp_path / "flow.png"
    boxes = imgtool.flow(out, ["Ask a question", "Do background research"], title="Steps")
    assert [b["n"] for b in boxes] == [1, 2]
    assert all(0 <= v <= max(Image.open(out).size) for b in boxes for v in b["box"])


def test_flow_boxes_out_is_a_mask_spec(tmp_path: Path):
    """test_flow_boxes_out_is_a_mask_spec: the spec `imgtool flow --boxes-out` writes is one `imgtool mask` reads,
    so a redrawn chart can be masked without hand-measuring boxes."""
    spec = tmp_path / "spec.json"
    invoke(imgtool.cli, "flow", tmp_path / "f.png", "--step", "One", "--step", "Two", "--boxes-out", spec)
    invoke(imgtool.cli, "mask", tmp_path / "f.png", spec, tmp_path / "fm.png")
    x0, y0, _, y1 = json.loads(spec.read_text())["boxes"][0]["box"]
    pixel = Image.open(tmp_path / "fm.png").convert("RGB").getpixel((x0 + 10, (y0 + y1) // 2))
    assert isinstance(pixel, tuple) and pixel[2] < 170  # yellow mask, not the pale blue step box
