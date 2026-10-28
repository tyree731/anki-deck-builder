"""Screenshot rendered card pages with a headless Chromium browser, trim the empty
background, and optionally pack several cards per sheet for quick human review.

Each card becomes <round_dir>/shots/<page>.png. Exit 1 if no browser is found or any
screenshot is missing.
"""

import json
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import click
from PIL import Image, ImageChops

from adb_core.common import EXIT_FAIL, find_browser, load_config

BG = (136, 136, 136)  # page background in adb_review/templates/card_page.html.jinja


def shoot_one(browser: str, html: Path, png: Path, width: int) -> bool:
    """Screenshot one review page with a headless browser and trim the empty background.

    Args:
        browser: Browser executable.
        html: The page to load.
        png: Where to write the screenshot.
        width: Window width in pixels.

    Returns:
        True when the screenshot was written.
    """
    profile = tempfile.mkdtemp(prefix="adb-chrome-")
    try:
        subprocess.run(
            [
                browser,
                "--headless=new",
                "--disable-gpu",
                "--hide-scrollbars",
                "--no-first-run",
                f"--user-data-dir={profile}",
                f"--screenshot={png}",
                f"--window-size={width},2600",
                html.resolve().as_uri(),
            ],
            capture_output=True,
            timeout=90,
        )
    except subprocess.TimeoutExpired:
        return False
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    if not png.exists():
        return False
    im = Image.open(png).convert("RGB")
    box = ImageChops.difference(im, Image.new("RGB", im.size, BG)).getbbox()
    if box:
        im.crop((0, 0, im.width, min(im.height, box[3] + 8))).save(png, optimize=True)
    return True


def pack(pngs: list[Path], out_dir: Path, prefix: str, max_h: int = 1900) -> list[Path]:
    """Stack screenshots into sheets for quick human review.

    Args:
        pngs: Screenshots, in order.
        out_dir: Where to write sheets (old sheets with this prefix are removed).
        prefix: Sheet name prefix ("changed" -> changed_01.jpg).
        max_h: Sheet height limit; a single taller screenshot gets a sheet of its own.

    Returns:
        The sheet paths, in order.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob(f"{prefix}_*.jpg"):
        old.unlink()
    sheets, group, h = [], [], 0
    for p in pngs:
        im = Image.open(p).convert("RGB")
        if group and h + im.height > max_h:
            sheets.append(group)
            group, h = [], 0
        group.append(im)
        h += im.height + 6
    if group:
        sheets.append(group)
    out = []
    for i, g in enumerate(sheets, 1):
        width = max(im.width for im in g)
        sheet = Image.new("RGB", (width, sum(im.height + 6 for im in g)), (40, 40, 40))
        y = 0
        for im in g:
            sheet.paste(im, (0, y))
            y += im.height + 6
        dest = out_dir / f"{prefix}_{i:02d}.jpg"
        sheet.save(dest, quality=88)
        out.append(dest)
    return out


def shoot_round(round_dir: Path, only: set[str] | None = None, sheet_prefix: str | None = None) -> dict:
    """Screenshot a rendered round's pages in parallel.

    Args:
        round_dir: The round directory (needs index.json and html/).
        only: Card ids to screenshot, or None for every card.
        sheet_prefix: When given, also pack the screenshots into sheets/<prefix>_NN.jpg.

    Returns:
        {"shots", "failed", "sheets"}.

    Raises:
        RuntimeError: No Chromium-family browser was found.
    """
    cfg = load_config()["refine"]
    browser = find_browser()
    if browser is None:
        raise RuntimeError("no Chromium-family browser found (set ANKI_DECK_BUILDER_CHROME)")
    index = json.loads((round_dir / "index.json").read_text(encoding="utf-8"))
    rows = [r for r in index if only is None or r["card_id"] in only]
    shots = round_dir / "shots"
    shots.mkdir(exist_ok=True)
    width = cfg["viewport_width_px"] * 2 + 40
    jobs = [(round_dir / "html" / r["page"].replace(".png", ".html"), shots / r["page"]) for r in rows]
    with ThreadPoolExecutor(max_workers=cfg["screenshot_parallelism"]) as pool:
        results = list(pool.map(lambda j: shoot_one(browser, j[0], j[1], width), jobs))
    failed = [str(j[1].name) for j, ok in zip(jobs, results, strict=True) if not ok]
    sheets = (
        pack([j[1] for j, ok in zip(jobs, results, strict=True) if ok], round_dir / "sheets", sheet_prefix)
        if sheet_prefix
        else []
    )
    return {"shots": len(jobs) - len(failed), "failed": failed, "sheets": [str(s) for s in sheets]}


@click.command(name="shoot")
@click.argument("round_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "--only",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="File of card_ids (one per line) to screenshot; default every card.",
)
@click.option("--sheets", "sheet_prefix", help="Also pack the shots into sheets/<PREFIX>_NN.jpg.")
def cli(round_dir: Path, only: Path | None, sheet_prefix: str | None) -> None:
    """Screenshot a rendered round's pages with a headless browser."""
    ids = {ln.strip() for ln in only.read_text().splitlines() if ln.strip()} if only else None
    try:
        info = shoot_round(round_dir, ids, sheet_prefix)
    except RuntimeError as exc:
        click.echo(str(exc), err=True)
        sys.exit(EXIT_FAIL)
    click.echo(f"screenshots: {info['shots']} ok, {len(info['failed'])} failed")
    for s in info["sheets"]:
        click.echo(f"sheet: {s}")
    for f in info["failed"]:
        click.echo(f"FAILED: {f}", err=True)
    if info["failed"]:
        sys.exit(EXIT_FAIL)


if __name__ == "__main__":
    cli()
