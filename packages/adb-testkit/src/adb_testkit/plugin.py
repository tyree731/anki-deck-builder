"""pytest plugin for the anki-deck-builder workspace, loaded with `-p adb_testkit.plugin` (root pyproject addopts).

- Enforces the docstring convention: every test's docstring starts with `<test name>: <description>`.
- Fixtures: `corpus` (input folder with every file kind), `run_dir` (lint-clean run dir at the end of
  Synthesize), `built_run_dir` (the same with build/deck.apkg built and import-validated).
"""

import re
from pathlib import Path

import pytest
from PIL import Image

from adb_testkit.images import page_image
from adb_testkit.runs import make_run_dir


def pytest_collection_modifyitems(session, config, items):
    """Fail collection when a test's docstring doesn't start with '<test name>: <description>'.

    Args:
        session: The pytest session.
        config: The pytest config.
        items: Collected test items.

    Raises:
        pytest.UsageError: One or more tests break the convention (all are listed).
    """
    bad = []
    for item in items:
        fn = getattr(item, "function", None)
        name = getattr(item, "originalname", item.name)
        doc = (fn.__doc__ or "").strip() if fn else ""
        if not re.match(rf"^{re.escape(name)}: \S", doc):
            bad.append(f"  {item.nodeid}: docstring must start with '{name}: <brief description>'")
    if bad:
        raise pytest.UsageError("test docstring convention violated:\n" + "\n".join(bad))


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    """Input folder with every file kind organize handles.

    Contents: an EXIF-rotated JPEG, an RGBA PNG, a 2-page PDF, a text file, an unsupported
    file and a hidden file.

    Args:
        tmp_path: pytest's per-test temporary directory.

    Returns:
        The input folder.
    """
    src = tmp_path / "materials"
    src.mkdir()
    exif = Image.Exif()
    exif[0x0112] = 6  # stored sideways; organize must apply the EXIF rotation
    page_image(["Cell theory notes"]).rotate(90, expand=True).save(src / "IMG_0002.jpg", exif=exif)
    page_image(["Microscope parts"]).convert("RGBA").save(src / "IMG_0010.png")
    page_image(["Review packet page 1"]).save(
        src / "packet.pdf", save_all=True, append_images=[page_image(["Review packet page 2"])]
    )
    (src / "vocab.txt").write_text("Organelle: a specialized part of a cell.\n", encoding="utf-8")
    (src / "data.bin").write_bytes(b"\x00\x01")
    (src / ".DS_Store").write_bytes(b"junk")
    return src


@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    """A lint-clean run directory at the end of Synthesize, before the deck is built.

    Args:
        tmp_path: pytest's per-test temporary directory.

    Returns:
        The run directory.
    """
    return make_run_dir(tmp_path)


@pytest.fixture
def built_run_dir(tmp_path: Path) -> Path:
    """A run directory whose build/deck.apkg has been built and import-validated.

    Args:
        tmp_path: pytest's per-test temporary directory.

    Returns:
        The run directory.
    """
    from adb_deck import make_deck

    rd = make_run_dir(tmp_path)
    assert make_deck.make(rd) == 0
    return rd
