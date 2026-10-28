"""Organize phase: inventory the input directory into page-sized units.

Every study page becomes one unit with a normalized image (EXIF rotation applied,
RGB JPEG) and/or a text file inside <run_dir>/pages/. Inputs are only read, never
modified. Hidden files and the skill's own run/output directories are skipped.

  images (.jpg .png .heic ...)  -> one `image` unit each
  PDFs                          -> one `pdf_page` unit per page (rendered image + text layer)
  .docx / .pptx                 -> one `text` unit (per document / per slide) + `embedded_image` units
  .txt .md .html .csv           -> one `text` unit each
  anything else                 -> listed under `skipped`

`adb organize --help` lists the commands.
"""

import datetime as _dt
import html
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import click
from PIL import Image, ImageDraw, ImageFont, ImageOps

from adb_core.common import (
    EXIT_FAIL,
    EXIT_OK,
    load_config,
    natural_key,
    read_json,
    run_paths,
    sha256_file,
    write_json,
)

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
    HEIF = True
except Exception:
    HEIF = False

Image.MAX_IMAGE_PIXELS = 300_000_000  # phone photos and 200-dpi PDF pages are large but legitimate


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def _save_page_image(img: Image.Image, dest: Path, max_side: int) -> tuple[int, int]:
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        canvas = Image.new("RGB", img.size, "white")
        canvas.paste(img, mask=img.split()[-1])
        img = canvas
    else:
        img = img.convert("RGB")
    if max(img.size) > max_side:
        img.thumbnail((max_side, max_side))
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, quality=90)
    return img.size


def _docx_text(z: zipfile.ZipFile) -> str:
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    root = ElementTree.fromstring(z.read("word/document.xml"))
    paras = []
    for p in root.iter(f"{ns}p"):
        line = "".join(t.text or "" for t in p.iter(f"{ns}t"))
        paras.append(line)
    return "\n".join(paras).strip()


def _pptx_slides(z: zipfile.ZipFile) -> list[tuple[int, str]]:
    ns = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
    names = sorted((n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)), key=natural_key)
    slides = []
    for n in names:
        root = ElementTree.fromstring(z.read(n))
        paras = ["".join(t.text or "" for t in p.iter(f"{ns}t")) for p in root.iter(f"{ns}p")]
        number = re.search(r"(\d+)", n.rsplit("/", 1)[1])
        slides.append((int(number.group(1)) if number else len(slides) + 1, "\n".join(paras).strip()))
    return slides


def _html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</h\d>", "\n", raw)
    return html.unescape(re.sub(r"<[^>]+>", " ", raw))


def inventory(input_dir: Path, run_dir: Path) -> int:
    """Inventory an input folder into page units, pages/ files, a manifest and contact sheets.

    Args:
        input_dir: The user's folder (read only).
        run_dir: Where to write; its own name and the output folder are skipped.

    Returns:
        0 on success, 1 when no usable page was found.
    """
    cfg = load_config()
    ocfg = cfg["organize"]
    paths = run_paths(run_dir)
    paths["pages"].mkdir(parents=True, exist_ok=True)
    skip_dirs = {cfg["paths"]["run_dir_name"], cfg["paths"]["output_dir_name"]}
    exts = {
        "image": set(ocfg["image_extensions"]),
        "pdf": set(ocfg["pdf_extensions"]),
        "text": set(ocfg["text_extensions"]),
        "office": set(ocfg["office_extensions"]),
    }
    files = []
    for f in input_dir.rglob("*"):
        rel = f.relative_to(input_dir)
        if any(part.startswith(".") or part in skip_dirs for part in rel.parts) or not f.is_file():
            continue
        files.append(f)
    files.sort(key=lambda f: natural_key(str(f.relative_to(input_dir))))

    units, skipped, by_hash = [], [], {}
    counter = 0

    def new_id() -> str:
        nonlocal counter
        counter += 1
        return f"p{counter:03d}" if counter < 1000 else f"p{counter:04d}"

    def add(kind, rel, digest, page=None, image=None, text=None, size=(None, None), text_layer=False):
        uid = new_id()
        dup = by_hash.get((digest, page)) if kind in ("image", "embedded_image") else None
        if kind in ("image", "embedded_image"):
            by_hash.setdefault((digest, page), uid)
        units.append(
            {
                "id": uid,
                "kind": kind,
                "source_file": rel,
                "page": page,
                "sha256": digest,
                "image": image,
                "text": text,
                "width": size[0],
                "height": size[1],
                "has_text_layer": text_layer,
                "duplicate_of": dup,
                "excluded": False,
                "exclude_reason": None,
            }
        )
        return uid

    for f in files:
        rel = str(f.relative_to(input_dir))
        ext = f.suffix.lower()
        try:
            digest = sha256_file(f)
            if ext in exts["image"]:
                if ext in (".heic", ".heif") and not HEIF:
                    skipped.append({"file": rel, "reason": "HEIC/HEIF needs pillow-heif"})
                    continue
                uid_preview = f"p{counter + 1:03d}"
                dest = paths["pages"] / f"{uid_preview}.jpg"
                with Image.open(f) as img:
                    if getattr(img, "n_frames", 1) > 1:
                        img.seek(0)
                    size = _save_page_image(img, dest, ocfg["max_page_long_side_px"])
                add("image", rel, digest, image=f"pages/{dest.name}", size=size)
            elif ext in exts["pdf"]:
                import pypdfium2 as pdfium

                pdf = pdfium.PdfDocument(str(f))
                scale = ocfg["pdf_render_dpi"] / 72
                for i in range(len(pdf)):
                    page = pdf[i]
                    uid_preview = f"p{counter + 1:03d}"
                    dest = paths["pages"] / f"{uid_preview}.jpg"
                    size = _save_page_image(page.render(scale=scale).to_pil(), dest, ocfg["max_page_long_side_px"])
                    text = page.get_textpage().get_text_range().strip()
                    tpath = None
                    if text:
                        (paths["pages"] / f"{uid_preview}.txt").write_text(text, encoding="utf-8")
                        tpath = f"pages/{uid_preview}.txt"
                    add(
                        "pdf_page",
                        rel,
                        digest,
                        page=i + 1,
                        image=f"pages/{dest.name}",
                        text=tpath,
                        size=size,
                        text_layer=bool(text),
                    )
                pdf.close()
            elif ext in exts["text"]:
                raw = f.read_text(encoding="utf-8", errors="replace")
                text = _html_to_text(raw) if ext in (".html", ".htm") else raw
                if not text.strip():
                    skipped.append({"file": rel, "reason": "empty text file"})
                    continue
                uid_preview = f"p{counter + 1:03d}"
                (paths["pages"] / f"{uid_preview}.txt").write_text(text.strip(), encoding="utf-8")
                add("text", rel, digest, text=f"pages/{uid_preview}.txt", text_layer=True)
            elif ext in exts["office"]:
                with zipfile.ZipFile(f) as z:
                    if ext == ".docx":
                        docs = [(None, _docx_text(z))]
                        media_prefix = "word/media/"
                    else:
                        docs = _pptx_slides(z)
                        media_prefix = "ppt/media/"
                    for page_no, text in docs:
                        if not text:
                            continue
                        uid_preview = f"p{counter + 1:03d}"
                        (paths["pages"] / f"{uid_preview}.txt").write_text(text, encoding="utf-8")
                        add("text", rel, digest, page=page_no, text=f"pages/{uid_preview}.txt", text_layer=True)
                    media = sorted((n for n in z.namelist() if n.startswith(media_prefix)), key=natural_key)
                    for i, name in enumerate(media, 1):
                        try:
                            with Image.open(z.open(name)) as img:
                                img.load()
                                if min(img.size) < 120:  # icons, bullets, decorations
                                    continue
                                uid_preview = f"p{counter + 1:03d}"
                                dest = paths["pages"] / f"{uid_preview}.jpg"
                                size = _save_page_image(img, dest, ocfg["max_page_long_side_px"])
                            add("embedded_image", rel, digest, page=i, image=f"pages/{dest.name}", size=size)
                        except Exception:
                            continue
            else:
                skipped.append({"file": rel, "reason": f"unsupported type {ext or '(none)'}"})
        except Exception as exc:
            skipped.append({"file": rel, "reason": f"{type(exc).__name__}: {exc}"})

    if not units:
        click.echo(f"no usable pages found in {input_dir}", err=True)
        return EXIT_FAIL
    manifest = {
        "schema_version": 1,
        "input_dir": str(input_dir),
        "generated_at": _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds"),
        "units": units,
        "skipped": skipped,
    }
    write_json(paths["manifest"], manifest)
    sheets = make_sheets(run_dir, manifest)
    kinds = {}
    for u in units:
        kinds[u["kind"]] = kinds.get(u["kind"], 0) + 1
    dups = sum(1 for u in units if u["duplicate_of"])
    click.echo(
        f"organized {len(files)} file(s) into {len(units)} unit(s): "
        + ", ".join(f"{k}={n}" for k, n in sorted(kinds.items()))
        + (f"; duplicates={dups}" if dups else "")
        + (f"; skipped={len(skipped)}" if skipped else "")
    )
    for s in skipped:
        click.echo(f"  skipped {s['file']}: {s['reason']}")
    click.echo(f"contact sheets: {', '.join(str(s) for s in sheets)}")
    return EXIT_OK


def make_sheets(run_dir: Path, manifest: dict) -> list[Path]:
    """Draw labeled thumbnail grids of every unit so the whole corpus fits in a few looks.

    Excluded and duplicate units are marked in red; text-only units show their first lines.

    Args:
        run_dir: The run directory; sheets go to sheets/contact_NN.jpg (old ones are removed).
        manifest: The parsed manifest.json.

    Returns:
        The sheet paths, in order.
    """
    cfg = load_config()["organize"]
    paths = run_paths(run_dir)
    cols, rows = cfg["contact_sheet_columns"], cfg["contact_sheet_rows"]
    tw, th, label_h = 300, 400, 28
    per = cols * rows
    for old in paths["sheets"].glob("contact_*.jpg"):
        old.unlink()
    font, small = _font(20), _font(15)
    out = []
    units = manifest["units"]
    for s in range(0, len(units), per):
        chunk = units[s : s + per]
        nrows = (len(chunk) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * tw, nrows * (th + label_h)), "white")
        draw = ImageDraw.Draw(sheet)
        for i, u in enumerate(chunk):
            x, y = (i % cols) * tw, (i // cols) * (th + label_h)
            tag = u["id"] + (" DUP" if u["duplicate_of"] else "") + (" EXCL" if u["excluded"] else "")
            draw.text((x + 4, y + 4), tag, fill="red" if (u["duplicate_of"] or u["excluded"]) else "black", font=font)
            if u.get("image"):
                with Image.open(paths["root"] / u["image"]) as img:
                    img = img.convert("RGB")
                    img.thumbnail((tw - 6, th - 6))
                    sheet.paste(img, (x + 3, y + label_h))
            else:
                text = (paths["root"] / u["text"]).read_text(encoding="utf-8")[:600]
                draw.rectangle((x + 3, y + label_h, x + tw - 3, y + label_h + th - 6), outline="gray")
                lines = []
                for para in text.splitlines():
                    while para:
                        lines.append(para[:34])
                        para = para[34:]
                for j, line in enumerate(lines[:22]):
                    draw.text((x + 8, y + label_h + 6 + j * 17), line, fill="black", font=small)
        dest = paths["sheets"] / f"contact_{s // per + 1:02d}.jpg"
        dest.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(dest, quality=85)
        out.append(dest)
    return out


def set_excluded(run_dir: Path, page_id: str, excluded: bool, reason: str | None) -> int:
    """Exclude a unit (with a reason) or include it again, then redraw the contact sheets.

    Args:
        run_dir: The run directory.
        page_id: The unit to change.
        excluded: True to exclude, False to include.
        reason: Why it is excluded (ignored when including).

    Returns:
        0 on success, 1 when the unit does not exist.
    """
    paths = run_paths(run_dir)
    manifest = read_json(paths["manifest"])
    for u in manifest["units"]:
        if u["id"] == page_id:
            u["excluded"], u["exclude_reason"] = excluded, (reason if excluded else None)
            write_json(paths["manifest"], manifest)
            make_sheets(run_dir, manifest)
            click.echo(f"{page_id}: {'excluded' if excluded else 'included'}")
            return EXIT_OK
    click.echo(f"no unit {page_id}", err=True)
    return EXIT_FAIL


RUN_DIR = click.Path(exists=True, file_okay=False, path_type=Path)


@click.group(name="organize")
def cli() -> None:
    """Inventory the input folder into page units, and curate them."""


@cli.command()
@click.argument("input_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.argument("run_dir", type=click.Path(file_okay=False, path_type=Path))
def run(input_dir: Path, run_dir: Path) -> None:
    """Inventory INPUT_DIR into RUN_DIR: pages, manifest.json and contact sheets."""
    sys.exit(inventory(input_dir.expanduser().resolve(), run_dir.expanduser().resolve()))


@cli.command()
@click.argument("run_dir", type=RUN_DIR)
@click.argument("page_id")
@click.option("--reason", required=True, help="Why, e.g. 'blank page' or 'second photo of p012'.")
def exclude(run_dir: Path, page_id: str, reason: str) -> None:
    """Exclude a page with nothing to learn."""
    sys.exit(set_excluded(run_dir, page_id, True, reason))


@cli.command()
@click.argument("run_dir", type=RUN_DIR)
@click.argument("page_id")
def include(run_dir: Path, page_id: str) -> None:
    """Include a previously excluded page again."""
    sys.exit(set_excluded(run_dir, page_id, False, None))


@cli.command()
@click.argument("run_dir", type=RUN_DIR)
def sheets(run_dir: Path) -> None:
    """Redraw the contact sheets."""
    for sheet in make_sheets(run_dir, read_json(run_paths(run_dir)["manifest"])):
        click.echo(sheet)


if __name__ == "__main__":
    cli()
