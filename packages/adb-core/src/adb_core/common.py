"""Shared helpers for every anki-deck-builder command: skill root and config, run-dir
paths, JSON I/O, natural sorting, slugs, chemical-formula subscripts and browser discovery.

Pure standard library, so preflight can import it before checking third-party packages.
"""

import hashlib
import json
import os
import platform
import re
import shutil
import tomllib
from pathlib import Path

from adb_core import wsl


def _find_skill_root() -> Path:
    """The skill directory (holds SKILL.md and config.toml). Workspace members are installed
    editable, so it is an ancestor of this file; ANKI_DECK_BUILDER_ROOT overrides."""
    override = os.environ.get("ANKI_DECK_BUILDER_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    for parent in Path(__file__).resolve().parents:
        if (parent / "SKILL.md").is_file() and (parent / "config.toml").is_file():
            return parent
    raise RuntimeError("cannot locate the anki-deck-builder skill root; set ANKI_DECK_BUILDER_ROOT")


SKILL_ROOT = _find_skill_root()
CONFIG_PATH = SKILL_ROOT / "config.toml"
SCHEMAS = Path(__file__).resolve().parent / "schemas"

PHASES = ["organize", "extract", "categorize", "synthesize", "refine", "complete"]

# Exit codes shared by every `adb` command (documented in references/README.md).
EXIT_OK = 0
EXIT_FAIL = 1  # check ran and found problems
EXIT_USAGE = 2  # bad command-line usage or input (click's convention)
EXIT_PARSE = 3  # a file was not valid JSON / expected format
EXIT_IO = 4  # a file could not be read or written


def load_config() -> dict:
    """Load the skill's config.toml.

    Returns:
        The parsed configuration (sections: paths, organize, extract, synthesize, refine,
        complete, checkpoints, labels, lint, models).
    """
    return tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def read_json(path: Path | str):
    """Read a UTF-8 JSON file.

    Args:
        path: File to read.

    Returns:
        The parsed JSON value.
    """
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path | str, payload) -> None:
    """Write JSON atomically (temp file + rename), creating parent directories.

    Args:
        path: Destination file.
        payload: Any JSON-serializable value; written UTF-8, indented, non-ASCII kept.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def sha256_file(path: Path | str, chunk: int = 1 << 20) -> str:
    """Hash a file without loading it into memory at once.

    Args:
        path: File to hash.
        chunk: Read size in bytes.

    Returns:
        The hex SHA-256 digest.
    """
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def natural_key(text: str):
    """Sort key that orders embedded numbers numerically, case-insensitively.

    Args:
        text: The string to sort (e.g. a relative file path).

    Returns:
        A list of int and lowercase str pieces, so 'IMG_9.jpg' sorts before 'IMG_10.jpg'.
    """
    return [int(tok) if tok.isdigit() else tok.lower() for tok in re.split(r"(\d+)", str(text))]


def slugify(text: str, max_len: int = 40) -> str:
    """Lowercase slug of letters, digits and underscores.

    Args:
        text: Text to slugify.
        max_len: Maximum slug length.

    Returns:
        The slug, or "deck" if nothing usable remains.
    """
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return (slug[:max_len].rstrip("_")) or "deck"


def stable_id(*parts: str, bits: int = 31) -> int:
    """Deterministic positive integer for Anki deck and note-type IDs.

    Args:
        *parts: Strings that identify the object; the same parts always give the same ID.
        bits: Upper bound of the ID range, as a power of two.

    Returns:
        An integer in [1_000_000, 2**bits).
    """
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
    return (int(digest[:15], 16) % ((1 << bits) - 1_000_000)) + 1_000_000


def chem_html(formula: str) -> str:
    """Write chemical formulas with real subscripts.

    Digits that follow a letter or ')' become subscripts; leading coefficients stay full size.

    Args:
        formula: Formula text, e.g. "6CO2 + C6H12O6" or "Ca(OH)2".

    Returns:
        HTML, e.g. "6CO<sub>2</sub> + C<sub>6</sub>H<sub>12</sub>O<sub>6</sub>".
    """
    out, i = [], 0
    while i < len(formula):
        ch = formula[i]
        if ch.isdigit() and i > 0 and (formula[i - 1].isalpha() or formula[i - 1] == ")"):
            j = i
            while j < len(formula) and formula[j].isdigit():
                j += 1
            out.append(f"<sub>{formula[i:j]}</sub>")
            i = j
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def run_paths(run_dir: Path | str) -> dict[str, Path]:
    """Canonical layout of a run directory (see references/artifacts.md).

    Args:
        run_dir: The run directory (normally <input folder>/.anki-build).

    Returns:
        Named paths: root, state, manifest, pages, sheets, subsets, transcripts, figures,
        media, work, digest, categories, cards, build, refine.
    """
    r = Path(run_dir)
    return {
        "root": r,
        "state": r / "state.json",
        "manifest": r / "manifest.json",
        "pages": r / "pages",
        "sheets": r / "sheets",
        "subsets": r / "subsets",
        "transcripts": r / "transcripts",
        "figures": r / "figures",
        "media": r / "media",
        "work": r / "work",
        "digest": r / "digest.md",
        "categories": r / "categories.json",
        "cards": r / "cards",
        "build": r / "build",
        "refine": r / "refine",
    }


def find_anki() -> str | None:
    """Locate the Anki desktop app, to check that a finished deck can be opened in it.

    ANKI_DECK_BUILDER_ANKI, when it points at an existing path, wins over discovery. Under
    WSL, an Anki installed on Windows counts; on Linux, so does the Flatpak.

    Returns:
        The app bundle, executable or Flatpak launcher, or None if Anki isn't installed.
    """
    override = os.environ.get("ANKI_DECK_BUILDER_ANKI")
    if override and Path(override).exists():
        return override
    system = platform.system()
    candidates: list[Path] = []
    if system == "Darwin":
        candidates += [Path("/Applications/Anki.app"), Path.home() / "Applications/Anki.app"]
    elif system == "Windows":
        # Per-user installs go to %LOCALAPPDATA%\Programs\Anki, all-users installs to %ProgramFiles%\Anki.
        candidates += [
            Path(os.environ[v]) / sub
            for v, sub in (("LOCALAPPDATA", "Programs/Anki/Anki.exe"), ("PROGRAMFILES", "Anki/Anki.exe"))
            if v in os.environ
        ]
    elif wsl.is_wsl():
        # The same Windows locations through the drive mounts, where names must match case-insensitively.
        root = wsl.mount_root()
        for pattern in ("*/Users/*/AppData/Local/Programs/Anki/Anki.exe", "*/Program Files/Anki/Anki.exe"):
            candidates += sorted(root.glob(pattern, case_sensitive=False))
    for path in candidates:
        if path.exists():
            return str(path)
    found = shutil.which("anki")
    if found:
        return found
    # Flatpak keeps a launcher for each installed app, system-wide and per user.
    for base in (Path("/var/lib/flatpak"), Path.home() / ".local/share/flatpak"):
        launcher = base / "exports/bin/net.ankiweb.Anki"
        if launcher.exists():
            return str(launcher)
    return None


def find_browser() -> str | None:
    """Locate a Chromium-family browser for headless screenshots.

    ANKI_DECK_BUILDER_CHROME, when it points at an existing file, wins over discovery.

    Returns:
        The browser executable's path, or None if none was found.
    """
    override = os.environ.get("ANKI_DECK_BUILDER_CHROME")
    if override and Path(override).exists():
        return override
    mac = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    ]
    for path in mac:
        if Path(path).exists():
            return path
    for name in (
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "microsoft-edge",
        "brave-browser",
        "chrome",
    ):
        found = shutil.which(name)
        if found:
            return found
    return None
