"""Categorize-phase digest: one table row per page, built from the transcript headers,
so the corpus can be grouped into sources and topics without re-reading every page.
"""

import re
from pathlib import Path

import click

from adb_core.common import read_json, run_paths


def header_field(text: str, field: str) -> str:
    """Read a "- Field: value" header bullet from a transcript.

    Args:
        text: Transcript Markdown.
        field: Bullet name, e.g. "Source guess".

    Returns:
        The value, or "" when the bullet is missing.
    """
    m = re.search(rf"^- {re.escape(field)}: (.+)$", text, flags=re.M)
    return m.group(1).strip() if m else ""


def section(text: str, heading: str) -> str:
    """Read the body of a "## Heading" section from a transcript.

    Args:
        text: Transcript Markdown.
        heading: Section name without "## ", e.g. "Flags".

    Returns:
        The stripped section body, or "" when the section is missing.
    """
    m = re.search(rf"^## {re.escape(heading)}\s*$(.*?)(?=^## |\Z)", text, flags=re.M | re.S)
    return m.group(1).strip() if m else ""


def write_digest(run_dir: Path) -> Path:
    """Write <run_dir>/digest.md: one table row per page plus every page's flags.

    Args:
        run_dir: The run directory (needs manifest.json, transcripts/ and figures/).

    Returns:
        The digest path.
    """
    p = run_paths(run_dir)
    manifest = read_json(p["manifest"])
    rows = [
        "| Page | File | Source guess | Summary | Topics | Legibility | Figures | Flags |",
        "|---|---|---|---|---|---|---|---|",
    ]
    flagged = []
    for u in manifest["units"]:
        if u["excluded"] or u.get("duplicate_of"):
            why = u.get("exclude_reason") or f"duplicate of {u['duplicate_of']}"
            rows.append(f"| {u['id']} | {u['source_file']} | - | ({why}) | | | | |")
            continue
        t = p["transcripts"] / f"{u['id']}.md"
        text = t.read_text(encoding="utf-8") if t.exists() else ""
        figs = p["figures"] / f"{u['id']}.json"
        nfig = len(read_json(figs)["figures"]) if figs.exists() else 0
        flags = section(text, "Flags")
        has_flags = bool(flags) and flags.lower() not in ("none", "none.", "(none)", "-")
        if has_flags:
            flagged.append((u["id"], flags))
        file_label = u["source_file"] + (f" p.{u['page']}" if u.get("page") else "")
        cells = [
            u["id"],
            file_label,
            header_field(text, "Source guess"),
            header_field(text, "Summary"),
            header_field(text, "Topics"),
            header_field(text, "Legibility"),
            str(nfig),
            "yes" if has_flags else "",
        ]
        rows.append("| " + " | ".join(c.replace("|", "/") for c in cells) + " |")
    out = [
        "# Corpus digest",
        "",
        f"{len(manifest['units'])} unit(s). Read this to decide sources (subdecks) and topics.",
        "",
    ]
    out += rows
    if flagged:
        out += ["", "## Flags by page", ""]
        for pid, flags in flagged:
            out += [f"### {pid}", "", flags, ""]
    p["digest"].write_text("\n".join(out) + "\n", encoding="utf-8")
    return p["digest"]


@click.command(name="digest")
@click.argument("run_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
def cli(run_dir: Path) -> None:
    """Write RUN_DIR/digest.md (one row per page) for the Categorize phase."""
    click.echo(write_digest(run_dir))


if __name__ == "__main__":
    cli()
