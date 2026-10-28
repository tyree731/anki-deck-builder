"""Merge the per-subset card files (cards/<subset>.json) into build/cards.json, in
synthesize-plan order, and record which subset file owns each key
(build/card_owners.json) so Refine knows which file to edit for a fix.

Exit 1 if a key appears in more than one subset file or a planned file is missing.
"""

import sys
from pathlib import Path

import click

from adb_core.common import EXIT_FAIL, read_json, run_paths, write_json


def assemble(run_dir: Path) -> tuple[list[dict], dict[str, str], list[str]]:
    """Merge per-subset card files in plan order, then any extra files (e.g. fixups.json).

    Args:
        run_dir: The run directory.

    Returns:
        (cards, owners, errors): the merged notes, a map of card key to owning file name, and
        errors for missing planned files or duplicate keys (duplicates are left out).
    """
    p = run_paths(run_dir)
    plan = read_json(p["subsets"] / "synthesize.json")["subsets"]
    cards, owners, errors = [], {}, []
    files = [p["cards"] / f"{s['id']}.json" for s in plan]
    extra = sorted(set(p["cards"].glob("*.json")) - set(files))  # e.g. cards/fixups.json added during Refine
    for f in files + extra:
        if not f.exists():
            errors.append(f"missing card file {f}")
            continue
        for card in read_json(f):
            if card["key"] in owners:
                errors.append(f"duplicate key '{card['key']}' in {f.name} and {owners[card['key']]}")
                continue
            owners[card["key"]] = f.name
            cards.append(card)
    return cards, owners, errors


def assemble_into_build(run_dir: Path) -> tuple[list[dict], dict[str, str], list[str]]:
    """Assemble the card files and write build/cards.json and build/card_owners.json.

    Args:
        run_dir: The run directory.

    Returns:
        (cards, owners, errors) as from assemble(); nothing is written when there are errors.
    """
    cards, owners, errors = assemble(run_dir)
    if not errors:
        build = run_paths(run_dir)["build"]
        write_json(build / "cards.json", cards)
        write_json(build / "card_owners.json", owners)
    return cards, owners, errors


@click.command(name="assemble")
@click.argument("run_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
def cli(run_dir: Path) -> None:
    """Merge the per-subset card files into build/cards.json (exit 1 on duplicate keys or missing files)."""
    cards, owners, errors = assemble_into_build(run_dir)
    for e in errors:
        click.echo(e, err=True)
    if errors:
        sys.exit(EXIT_FAIL)
    click.echo(
        f"assembled {len(cards)} note(s) from {len(set(owners.values()))} file(s)"
        f" -> {run_paths(run_dir)['build'] / 'cards.json'}"
    )


if __name__ == "__main__":
    cli()
