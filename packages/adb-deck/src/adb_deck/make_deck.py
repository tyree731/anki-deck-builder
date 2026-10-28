"""One command for the whole build: validate every card file, assemble, lint, build
the .apkg and import-validate it. Synthesize runs it once all authors finish; Refine
runs it after every round of fixes. Stops at the first failing step.

Outputs build/cards.json, build/card_owners.json, build/lint.json, build/deck.apkg,
build/validate.json. --allow-lint-errors still builds (so the deck can be inspected)
but exits 1; the Synthesize gate will not pass until lint is clean or waived.
"""

import sys
from pathlib import Path

import click

from adb_core import validate
from adb_core.common import EXIT_FAIL, EXIT_OK, read_json, run_paths, write_json
from adb_deck import assemble_cards, build_deck, lint_cards, validate_deck


def make(run_dir: Path, allow_lint_errors: bool = False) -> int:
    """Validate card files, assemble, lint, build and import-validate, stopping at the first failure.

    Args:
        run_dir: The run directory; outputs go to build/.
        allow_lint_errors: Build even when lint has errors (the result still counts as failed).

    Returns:
        0 when every step passes, 1 otherwise.
    """
    p = run_paths(run_dir)
    plan = read_json(p["subsets"] / "synthesize.json")["subsets"]
    files = [p["cards"] / f"{s['id']}.json" for s in plan]
    files += sorted(set(p["cards"].glob("*.json")) - set(files))
    schema_errors = []
    for f in files:
        if f.exists():
            schema_errors += validate.validate_cards_file(f, run_dir)
        else:
            schema_errors.append(f"missing card file {f}")
    if schema_errors:
        click.echo("\n".join(schema_errors), err=True)
        click.echo(f"step 1/5 validate card files: FAIL ({len(schema_errors)})")
        return EXIT_FAIL
    click.echo(f"step 1/5 validate card files: ok ({len(files)} file(s))")

    cards, _, errors = assemble_cards.assemble_into_build(run_dir)
    if errors:
        click.echo("\n".join(errors), err=True)
        click.echo("step 2/5 assemble: FAIL")
        return EXIT_FAIL
    click.echo(f"step 2/5 assemble: ok ({len(cards)} note(s))")

    report = lint_cards.lint_into_build(run_dir)
    for item in report["errors"]:
        click.echo(f"  ERROR {item['rule']} {item['key']}: {item['message']}")
    for item in report["warnings"]:
        click.echo(f"  warn  {item['rule']} {item['key']}: {item['message']}")
    lint_failed = bool(report["errors"])
    click.echo(
        f"step 3/5 lint: {'FAIL' if lint_failed else 'ok'} ({len(report['errors'])} error(s), "
        f"{len(report['warnings'])} warning(s), {len(report['waived'])} waived)"
    )
    if lint_failed and not allow_lint_errors:
        return EXIT_FAIL

    info = build_deck.build(run_dir, p["build"] / "deck.apkg")
    click.echo(f"step 4/5 build: ok ({info['notes']} note(s), {info['media']} media)")

    vr = validate_deck.validate(p["build"] / "deck.apkg", p["build"] / "cards.json")
    write_json(p["build"] / "validate.json", vr)
    click.echo(
        f"step 5/5 import-validate: {'ok' if vr['ok'] else 'FAIL'}, {vr['notes']} note(s), {vr['cards']} card(s)"
    )
    for name, n in sorted(vr["decks"].items()):
        click.echo(f"  {name}: {n} card(s)")
    for prob in vr["problems"]:
        click.echo(f"  PROBLEM: {prob}")
    return EXIT_OK if vr["ok"] and not lint_failed else EXIT_FAIL


@click.command(name="make-deck")
@click.argument("run_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--allow-lint-errors", is_flag=True, help="Build anyway so the deck can be inspected (still exits 1).")
def cli(run_dir: Path, allow_lint_errors: bool) -> None:
    """Validate card files, assemble, lint, build and import-validate, stopping at the first failure."""
    sys.exit(make(run_dir, allow_lint_errors))


if __name__ == "__main__":
    cli()
