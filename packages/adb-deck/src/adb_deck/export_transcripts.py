"""Write the page transcriptions as one Markdown file per source (subdeck), in page
order, so the person who supplied the materials can read exactly what was extracted.

"""

import re
from pathlib import Path

import click

from adb_core.common import natural_key, read_json, run_paths


def export(run_dir: Path, out_dir: Path) -> list[Path]:
    """Write page transcriptions as one Markdown file per source, in page order.

    Args:
        run_dir: The run directory.
        out_dir: Where to write the files (created if missing).

    Returns:
        The files written, in source order.
    """
    p = run_paths(run_dir)
    cats = read_json(p["categories"])
    units = {u["id"]: u for u in read_json(p["manifest"])["units"]}
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for src in sorted(cats["sources"], key=lambda s: s["order"]):
        pages = sorted((pid for pid, s in cats["page_sources"].items() if s == src["id"]), key=natural_key)
        lines = [f"# {src['label']}: page-by-page transcription", "", src["description"], ""]
        for pid in pages:
            t = p["transcripts"] / f"{pid}.md"
            if not t.exists():
                continue
            u = units[pid]
            where = u["source_file"] + (f", page {u['page']}" if u.get("page") else "")
            body = t.read_text(encoding="utf-8").split("\n", 1)[1] if "\n" in t.read_text(encoding="utf-8") else ""
            lines += ["---", "", f"## {where}", "", re.sub(r"^## ", "### ", body.strip(), flags=re.M), ""]
        safe = re.sub(r'[\\/:*?"<>|]+', "-", src["label"]).strip() or src["id"]
        dest = out_dir / f"{safe}.md"
        dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
        written.append(dest)
    return written


@click.command(name="export-transcripts")
@click.argument("run_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.argument("out_dir", type=click.Path(file_okay=False, path_type=Path))
def cli(run_dir: Path, out_dir: Path) -> None:
    """Write page transcriptions as one Markdown file per source."""
    for f in export(run_dir, out_dir):
        click.echo(f)


if __name__ == "__main__":
    cli()
