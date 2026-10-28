"""Synthetic page images for tests."""

from PIL import Image, ImageDraw


def page_image(lines: list[str], size: tuple[int, int] = (1200, 1600)) -> Image.Image:
    """A synthetic white page with text lines and a labeled box (LABEL-A top, LABEL-B bottom).

    Args:
        lines: Text lines drawn at the top.
        size: Page size in pixels.

    Returns:
        The page image.
    """
    img = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        d.text((80, 120 + i * 90), line, fill="black")
    d.rectangle((700, 900, 1100, 1300), outline="black", width=6)
    d.text((720, 920), "LABEL-A", fill="black")
    d.text((720, 1250), "LABEL-B", fill="black")
    return img
