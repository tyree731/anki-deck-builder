"""Pixel operations for vision-driven figure extraction and fixes.

You decide WHAT to cut by looking; these commands do the pixel work so every worker
produces consistent output. Coordinates are always pixels of the image you pass in. Get
them from a `grid` overlay of that exact image, never from a downscaled preview.
`adb imgtool --help` lists the commands.
"""

import json
import statistics
from pathlib import Path

import click
from PIL import Image, ImageDraw, ImageFont, ImageOps

Image.MAX_IMAGE_PIXELS = 300_000_000

Box = tuple[int, int, int, int]


def font(size: int):
    """The default scalable font at a given size (bitmap fallback on old Pillow).

    Args:
        size: Font size in pixels.

    Returns:
        A Pillow font.
    """
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def _load(path: Path) -> Image.Image:
    return ImageOps.exif_transpose(Image.open(path)).convert("RGB")


def _save(img: Image.Image, out: Path, quality: int = 85) -> tuple[int, int]:
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.suffix.lower() == ".png":
        img.save(out, optimize=True)
    else:
        img.save(out, quality=quality)
    return img.size


def _norm(box: Box) -> Box:
    x0, y0, x1, y1 = box
    return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


def grid(img: Path, out: Path, step: int = 100) -> tuple[int, int]:
    """Overlay labeled gridlines (red = x, blue = y) for reading coordinates.

    Args:
        img: Source image.
        out: Where to write the overlay.
        step: Gridline spacing in pixels.

    Returns:
        The output size (same as the source).
    """
    im = _load(img)
    d = ImageDraw.Draw(im)
    f = font(max(14, im.width // 70))
    for x in range(0, im.width, step):
        d.line([(x, 0), (x, im.height)], fill=(255, 0, 0), width=1)
        d.text((x + 2, 2), str(x), fill=(255, 0, 0), font=f)
    for y in range(0, im.height, step):
        d.line([(0, y), (im.width, y)], fill=(0, 0, 255), width=1)
        d.text((2, y + 2), str(y), fill=(0, 0, 255), font=f)
    return _save(im, out)


def view(
    img: Path, out: Path, rotate: float = 0, box: Box | None = None, enhance: bool = False, max_side: int = 2000
) -> tuple[int, int]:
    """Make a working copy for reading: rotate, optionally crop and enhance, downscale.

    Args:
        img: Source image.
        out: Where to write the copy.
        rotate: Counterclockwise degrees, applied before the crop.
        box: Crop box in the rotated image's pixels, or None for the whole image.
        enhance: Grayscale and autocontrast, for faint pencil.
        max_side: Longest side of the output in pixels.

    Returns:
        The output size.
    """
    im = _load(img)
    if rotate:
        im = im.rotate(rotate, expand=True)
    if box:
        im = im.crop(_norm(box))
    if enhance:
        im = ImageOps.autocontrast(ImageOps.grayscale(im), cutoff=1).convert("RGB")
    im.thumbnail((max_side, max_side))
    return _save(im, out)


def crop(
    img: Path, out: Path, box: Box, rotate: float = 0, enhance: bool = False, max_side: int = 1400, quality: int = 82
) -> tuple[int, int]:
    """Cut a flashcard figure: rotate, crop (clamped to the image), enhance, downscale.

    Args:
        img: Source image.
        out: Where to write the figure (.jpg or .png).
        box: Crop box in the rotated image's pixels.
        rotate: Counterclockwise degrees, applied before the crop.
        enhance: Light autocontrast for dark or shadowed photos.
        max_side: Longest side of the output in pixels.
        quality: JPEG quality.

    Returns:
        The output size.
    """
    im = _load(img)
    if rotate:
        im = im.rotate(rotate, expand=True)
    x0, y0, x1, y1 = _norm(box)
    im = im.crop((max(0, x0), max(0, y0), min(im.width, x1), min(im.height, y1)))
    if enhance:
        im = ImageOps.autocontrast(im, cutoff=0.5)
    im.thumbnail((max_side, max_side))
    return _save(im, out, quality)


def mask(img: Path, boxes: list[dict], out: Path, style: str = "yellow") -> tuple[int, int]:
    """Hide labels behind numbered boxes.

    Args:
        img: The figure to mask.
        boxes: [{"n": 1, "box": [x0, y0, x1, y1]}, ...] in the figure's pixels.
        out: Where to write the masked figure.
        style: "yellow" (dark numbers on yellow) or "blue" (white numbers on blue).

    Returns:
        The output size.
    """
    im = _load(img)
    fill, outline, text = {"blue": ((30, 76, 170), "white", "white")}.get(
        style, ((255, 224, 130), (60, 60, 60), "black")
    )
    d = ImageDraw.Draw(im)
    for b in boxes:
        x0, y0, x1, y1 = _norm(tuple(int(v) for v in b["box"]))  # type: ignore[arg-type]
        d.rounded_rectangle(
            (x0, y0, x1, y1), radius=max(4, min(x1 - x0, y1 - y0) // 6), fill=fill, outline=outline, width=2
        )
        f = font(max(14, min(int((y1 - y0) * 0.7), int((x1 - x0) * 0.6))))
        label = str(b["n"])
        tb = d.textbbox((0, 0), label, font=f)
        tx = x0 + (x1 - x0 - (tb[2] - tb[0])) / 2 - tb[0]
        ty = y0 + (y1 - y0 - (tb[3] - tb[1])) / 2 - tb[1]
        d.text((tx, ty), label, fill=text, font=f)
    return _save(im, out, 85)


def cover(img: Path, out: Path, boxes: list[Box], pad: int = 12) -> tuple[int, int]:
    """Paint regions with the median color of the paper around them.

    Removes a stray giveaway (a caption, an annotation) without leaving a visible patch.

    Args:
        img: Source image.
        out: Where to write the result.
        boxes: Regions to paint, in the image's pixels.
        pad: Width of the surrounding ring sampled for the color.

    Returns:
        The output size.
    """
    im = _load(img)
    d = ImageDraw.Draw(im)
    for box in boxes:
        x0, y0, x1, y1 = _norm(box)
        ring: list[tuple[int, int, int]] = []
        for bx in [
            (x0 - pad, y0 - pad, x1 + pad, y0),
            (x0 - pad, y1, x1 + pad, y1 + pad),
            (x0 - pad, y0, x0, y1),
            (x1, y0, x1 + pad, y1),
        ]:
            bx = (max(0, bx[0]), max(0, bx[1]), min(im.width, bx[2]), min(im.height, bx[3]))
            if bx[2] > bx[0] and bx[3] > bx[1]:
                raw = im.crop(bx).tobytes()  # RGB triplets
                ring.extend(zip(raw[0::3], raw[1::3], raw[2::3], strict=True))
        color = tuple(int(statistics.median(px[c] for px in ring)) for c in range(3)) if ring else (255, 255, 255)
        d.rectangle((x0, y0, x1, y1), fill=color)
    return _save(im, out, 88)


def trim(img: Path, out: Path, top: int = 0, bottom: int = 0, left: int = 0, right: int = 0) -> tuple[int, int]:
    """Cut pixels off the edges, e.g. a caption or clipped neighboring text.

    Args:
        img: Source image.
        out: Where to write the result.
        top: Pixels to remove from the top.
        bottom: Pixels to remove from the bottom.
        left: Pixels to remove from the left.
        right: Pixels to remove from the right.

    Returns:
        The output size.
    """
    im = _load(img)
    return _save(im.crop((left, top, im.width - right, im.height - bottom)), out, 88)


def sheet(out: Path, images: list[Path], cols: int = 3, tile: tuple[int, int] = (520, 420)) -> tuple[int, int]:
    """Lay images out on one labeled contact sheet, for checking several crops in one look.

    Args:
        out: Where to write the sheet.
        images: Images to include, in order.
        cols: Images per row.
        tile: (width, height) of each cell in pixels.

    Returns:
        The sheet size.
    """
    tw, th = tile
    rows = (len(images) + cols - 1) // cols
    canvas = Image.new("RGB", (cols * tw, rows * (th + 24)), "white")
    d = ImageDraw.Draw(canvas)
    f = font(14)
    for i, path in enumerate(images):
        im = _load(path)
        label = f"{path.name} {im.width}x{im.height}"
        im.thumbnail((tw - 10, th))
        x, y = (i % cols) * tw, (i // cols) * (th + 24)
        canvas.paste(im, (x + 5, y + 22))
        d.text((x + 5, y + 4), label, fill="black", font=f)
    return _save(canvas, out)


def _wrap(d: ImageDraw.ImageDraw, text: str, f, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if d.textlength(trial, font=f) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def flow(out: Path, steps: list[str], title: str = "") -> list[dict]:
    """Redraw a linear process cleanly: top-to-bottom boxes joined by arrows.

    Args:
        out: Where to write the drawing (.png recommended).
        steps: Step texts, in order.
        title: Heading above the steps.

    Returns:
        One {"n", "box"} per step, ready to use as a `mask` spec's boxes.
    """
    w, box_w, box_h, gap = 900, 560, 130, 70
    title_h = 110 if title else 30
    h = title_h + len(steps) * box_h + (len(steps) - 1) * gap + 40
    im = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(im)
    ft, fs = font(44), font(34)
    if title:
        tb = d.textbbox((0, 0), title, font=ft)
        d.text(((w - (tb[2] - tb[0])) / 2, 30), title, fill="black", font=ft)
    boxes = []
    x0 = (w - box_w) // 2
    for i, step in enumerate(steps):
        y0 = title_h + i * (box_h + gap)
        d.rounded_rectangle((x0, y0, x0 + box_w, y0 + box_h), radius=18, fill=(230, 236, 246), outline="black", width=3)
        lines = _wrap(d, step, fs, box_w - 50)
        line_h = 40
        ty = y0 + (box_h - line_h * len(lines)) / 2
        for line in lines:
            lw = d.textlength(line, font=fs)
            d.text((x0 + (box_w - lw) / 2, ty), line, fill="black", font=fs)
            ty += line_h
        boxes.append({"n": i + 1, "box": [x0 + 10, y0 + 10, x0 + box_w - 10, y0 + box_h - 10]})
        if i < len(steps) - 1:
            cx, ay0, ay1 = w // 2, y0 + box_h + 8, y0 + box_h + gap - 8
            d.line([(cx, ay0), (cx, ay1)], fill="black", width=4)
            d.polygon([(cx - 12, ay1 - 16), (cx + 12, ay1 - 16), (cx, ay1)], fill="black")
    _save(im, out)
    return boxes


# ------------------------------------------------------------------ CLI
IMG = click.Path(exists=True, dir_okay=False, path_type=Path)
OUT = click.Path(dir_okay=False, path_type=Path)
BOX = click.option("--box", nargs=4, type=int, metavar="X0 Y0 X1 Y1", help="Region in pixels.")


def _done(out: Path, size: tuple[int, int]) -> None:
    click.echo(f"{out} {size[0]}x{size[1]}")


def _parse_tile(_ctx, _param, value: str) -> tuple[int, int]:
    try:
        w, h = (int(v) for v in value.lower().split("x"))
    except ValueError as exc:
        raise click.BadParameter("use WIDTHxHEIGHT, e.g. 520x420") from exc
    return w, h


@click.group(name="imgtool")
def cli() -> None:
    """Pixel operations for figure extraction. Coordinates are pixels of the image you pass in."""


@cli.command("grid")
@click.argument("img", type=IMG)
@click.argument("out", type=OUT)
@click.option("--step", default=100, show_default=True, type=click.IntRange(min=10), help="Gridline spacing.")
def grid_cmd(img: Path, out: Path, step: int) -> None:
    """Overlay labeled gridlines (red = x, blue = y) for reading coordinates."""
    _done(out, grid(img, out, step))


@cli.command("view")
@click.argument("img", type=IMG)
@click.argument("out", type=OUT)
@click.option("--rotate", default=0.0, help="Counterclockwise degrees, applied before --box.")
@BOX
@click.option("--enhance", is_flag=True, help="Grayscale + autocontrast for faint pencil.")
@click.option("--max", "max_side", default=2000, show_default=True, help="Longest output side in pixels.")
def view_cmd(img: Path, out: Path, rotate: float, box: Box | None, enhance: bool, max_side: int) -> None:
    """Make a working copy for reading (rotate, crop, enhance, downscale)."""
    _done(out, view(img, out, rotate, box, enhance, max_side))


@cli.command("crop")
@click.argument("img", type=IMG)
@click.argument("out", type=OUT)
@click.option("--box", nargs=4, type=int, required=True, metavar="X0 Y0 X1 Y1", help="Crop box (rotated pixels).")
@click.option("--rotate", default=0.0, help="Counterclockwise degrees, applied before the crop.")
@click.option("--enhance", is_flag=True, help="Light autocontrast for dark photos.")
@click.option("--max", "max_side", default=1400, show_default=True, help="Longest output side in pixels.")
@click.option("--quality", default=82, show_default=True, type=click.IntRange(1, 100), help="JPEG quality.")
def crop_cmd(img: Path, out: Path, box: Box, rotate: float, enhance: bool, max_side: int, quality: int) -> None:
    """Cut a flashcard figure from a page."""
    _done(out, crop(img, out, box, rotate, enhance, max_side, quality))


@cli.command("mask")
@click.argument("img", type=IMG)
@click.argument("spec", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("out", type=OUT)
def mask_cmd(img: Path, spec: Path, out: Path) -> None:
    """Hide labels behind numbered boxes. SPEC: {"style": "yellow"|"blue", "boxes": [{"n": 1, "box": [...]}]}."""
    payload = json.loads(spec.read_text(encoding="utf-8"))
    _done(out, mask(img, payload["boxes"], out, payload.get("style", "yellow")))


@cli.command("cover")
@click.argument("img", type=IMG)
@click.argument("out", type=OUT)
@click.option(
    "--box",
    "boxes",
    nargs=4,
    type=int,
    multiple=True,
    required=True,
    metavar="X0 Y0 X1 Y1",
    help="Region to paint; repeat for several.",
)
@click.option("--pad", default=12, show_default=True, help="Ring width sampled for the paper color.")
def cover_cmd(img: Path, out: Path, boxes: tuple[Box, ...], pad: int) -> None:
    """Paint regions with the surrounding paper color (remove a giveaway mark)."""
    _done(out, cover(img, out, list(boxes), pad))


@cli.command("trim")
@click.argument("img", type=IMG)
@click.argument("out", type=OUT)
@click.option("--top", default=0, type=click.IntRange(min=0))
@click.option("--bottom", default=0, type=click.IntRange(min=0))
@click.option("--left", default=0, type=click.IntRange(min=0))
@click.option("--right", default=0, type=click.IntRange(min=0))
def trim_cmd(img: Path, out: Path, top: int, bottom: int, left: int, right: int) -> None:
    """Cut pixels off the edges (a caption, clipped neighboring text)."""
    _done(out, trim(img, out, top, bottom, left, right))


@cli.command("sheet")
@click.argument("out", type=OUT)
@click.argument("images", nargs=-1, required=True, type=IMG)
@click.option("--cols", default=3, show_default=True, type=click.IntRange(min=1))
@click.option("--tile", default="520x420", show_default=True, callback=_parse_tile, help="Cell size WIDTHxHEIGHT.")
def sheet_cmd(out: Path, images: tuple[Path, ...], cols: int, tile: tuple[int, int]) -> None:
    """Lay several images out on one labeled contact sheet."""
    _done(out, sheet(out, list(images), cols, tile))


@cli.command("flow")
@click.argument("out", type=OUT)
@click.option("--step", "steps", multiple=True, required=True, help="A step's text; repeat in order.")
@click.option("--title", default="", help="Heading above the steps.")
@click.option("--boxes-out", type=click.Path(dir_okay=False, path_type=Path), help="Write a mask spec for the steps.")
def flow_cmd(out: Path, steps: tuple[str, ...], title: str, boxes_out: Path | None) -> None:
    """Redraw a linear process as clean boxes and arrows."""
    boxes = flow(out, list(steps), title)
    click.echo(f"{out}")
    if boxes_out:
        boxes_out.write_text(json.dumps({"style": "yellow", "boxes": boxes}, indent=1), encoding="utf-8")
        click.echo(f"boxes -> {boxes_out}")


if __name__ == "__main__":
    cli()
