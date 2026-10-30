"""pytest plugin for the anki-deck-builder workspace, loaded with `-p adb_testkit.plugin` (root pyproject addopts).

- Enforces the docstring convention: every test's docstring starts with `<test name>: <description>`.
- Adds `--platform linux|windows|wsl`, which runs the tests marked `platform(...)` for that platform;
  without it they're skipped.
- Fixtures: `corpus` (input folder with every file kind), `run_dir` (lint-clean run dir at the end of
  Synthesize), `built_run_dir` (the same with build/deck.apkg built and import-validated),
  `ci_platform` (the --platform value) and `stand_in_anki` (a stand-in app for .apkg files).
"""

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from PIL import Image

from adb_testkit import platforms
from adb_testkit.images import page_image
from adb_testkit.runs import make_run_dir


def pytest_addoption(parser):
    """Add --platform, which runs the real-platform tests for the platform this machine is.

    Args:
        parser: pytest's option parser.
    """
    parser.addoption(
        "--platform",
        choices=platforms.PLATFORMS,
        help="run the tests marked `platform` for this platform; they change file associations, so use a CI runner",
    )


def pytest_collection_modifyitems(session, config, items):
    """Enforce the docstring convention, and skip real-platform tests meant for another platform.

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
    platform = config.getoption("platform")
    for item in items:
        marker = item.get_closest_marker("platform")
        if marker and platform not in marker.args:
            reason = f"real-platform test for {', '.join(marker.args)}; run with --platform on a CI runner"
            item.add_marker(pytest.mark.skip(reason=reason))


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
def ci_platform(request: pytest.FixtureRequest) -> str:
    """The platform this run is on, as given with --platform.

    Args:
        request: The pytest request.

    Returns:
        linux, windows or wsl.
    """
    platform = request.config.getoption("platform")
    if platform is None:
        pytest.skip("needs --platform")
    return platform


@pytest.fixture
def stand_in_anki(ci_platform: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """A stand-in for Anki, registered as this user's app for .apkg files for the test's duration.

    Args:
        ci_platform: The platform, from --platform.
        tmp_path: pytest's per-test temporary directory.
        monkeypatch: pytest's monkeypatch fixture.

    Yields:
        The file where the stand-in writes the path it was asked to open.
    """
    with platforms.stand_in_anki(ci_platform, tmp_path, monkeypatch) as marker:
        yield marker


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
