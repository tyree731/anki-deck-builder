"""Tests for adb_ingest/organize.py."""

import json
import shutil
import zipfile
from pathlib import Path

from adb_ingest import organize


def _run(corpus: Path) -> tuple[Path, dict]:
    run_dir = corpus / ".anki-build"
    assert organize.inventory(corpus, run_dir) == 0
    return run_dir, json.loads((run_dir / "manifest.json").read_text())


def test_inventory_inventories_every_supported_kind(corpus: Path):
    """test_inventory_inventories_every_supported_kind: images, PDF pages and text files each become units in
    natural file order."""
    _, manifest = _run(corpus)
    assert [(u["id"], u["kind"], u["source_file"], u["page"]) for u in manifest["units"]] == [
        ("p001", "image", "IMG_0002.jpg", None),
        ("p002", "image", "IMG_0010.png", None),
        ("p003", "pdf_page", "packet.pdf", 1),
        ("p004", "pdf_page", "packet.pdf", 2),
        ("p005", "text", "vocab.txt", None),
    ]


def test_inventory_applies_exif_rotation_and_flattens_alpha(corpus: Path):
    """test_inventory_applies_exif_rotation_and_flattens_alpha: the sideways JPEG is stored upright and the RGBA
    PNG becomes an RGB JPEG."""
    run_dir, manifest = _run(corpus)
    first, second = manifest["units"][0], manifest["units"][1]
    assert (first["width"], first["height"]) == (1200, 1600)
    assert second["image"].endswith(".jpg") and (run_dir / second["image"]).exists()


def test_inventory_skips_hidden_unsupported_and_its_own_dirs(corpus: Path):
    """test_inventory_skips_hidden_unsupported_and_its_own_dirs: .DS_Store is ignored, data.bin is reported as
    skipped, and a second run does not inventory the run directory itself."""
    _run(corpus)
    _, manifest = _run(corpus)
    assert [s["file"] for s in manifest["skipped"]] == ["data.bin"]
    assert len(manifest["units"]) == 5
    assert not any(u["source_file"].startswith(".") for u in manifest["units"])


def test_inventory_marks_duplicate_images(corpus: Path):
    """test_inventory_marks_duplicate_images: a byte-identical copy of a photo is marked duplicate_of the first."""
    shutil.copy(corpus / "IMG_0002.jpg", corpus / "IMG_0003.jpg")
    _, manifest = _run(corpus)
    dup = next(u for u in manifest["units"] if u["source_file"] == "IMG_0003.jpg")
    assert dup["duplicate_of"] == "p001"


def test_inventory_extracts_office_text(tmp_path: Path):
    """test_inventory_extracts_office_text: .docx paragraphs become one text unit and each .pptx slide its own."""
    src = tmp_path / "docs"
    src.mkdir()
    w = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    with zipfile.ZipFile(src / "notes.docx", "w") as z:
        z.writestr(
            "word/document.xml",
            f"<w:document {w}><w:body><w:p><w:r><w:t>Cell theory</w:t></w:r></w:p>"
            "<w:p><w:r><w:t>All cells come from cells</w:t></w:r></w:p></w:body></w:document>",
        )
    a = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
    with zipfile.ZipFile(src / "deck.pptx", "w") as z:
        for i, text in ((1, "Slide one"), (2, "Slide two")):
            z.writestr(
                f"ppt/slides/slide{i}.xml", f"<p:sld xmlns:p='p' {a}><a:p><a:r><a:t>{text}</a:t></a:r></a:p></p:sld>"
            )
    run_dir = src / ".anki-build"
    assert organize.inventory(src, run_dir) == 0
    units = json.loads((run_dir / "manifest.json").read_text())["units"]
    texts = [(run_dir / u["text"]).read_text() for u in units]
    assert texts == ["Slide one", "Slide two", "Cell theory\nAll cells come from cells"]
    assert [u["page"] for u in units] == [1, 2, None]


def test_html_to_text_strips_markup():
    """test_html_to_text_strips_markup: scripts and styles vanish, block tags become line breaks, entities decode."""
    text = organize._html_to_text("<style>x{}</style><h1>Cells</h1><p>A &amp; B</p><script>evil()</script>")
    assert "evil" not in text and "x{}" not in text
    assert "Cells" in text and "A & B" in text


def test_set_excluded_excludes_and_includes(corpus: Path):
    """test_set_excluded_excludes_and_includes: exclude records a reason; include clears it."""
    run_dir, _ = _run(corpus)
    assert organize.set_excluded(run_dir, "p003", True, "cover page") == 0
    unit = json.loads((run_dir / "manifest.json").read_text())["units"][2]
    assert unit["excluded"] and unit["exclude_reason"] == "cover page"
    assert organize.set_excluded(run_dir, "p003", False, None) == 0
    assert not json.loads((run_dir / "manifest.json").read_text())["units"][2]["excluded"]
    assert organize.set_excluded(run_dir, "p999", True, "x") == 1


def test_make_sheets_writes_contact_sheets(corpus: Path):
    """test_make_sheets_writes_contact_sheets: one labeled contact sheet covers all units, text units included."""
    run_dir, manifest = _run(corpus)
    sheets = organize.make_sheets(run_dir, manifest)
    assert [s.name for s in sheets] == ["contact_01.jpg"]
