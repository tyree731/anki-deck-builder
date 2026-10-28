"""Import an .apkg into a brand-new collection with Anki's own engine (the code the
desktop and mobile apps share) and check every card renders with its media.

Writes a JSON report ({ok, apkg_sha256, notes, cards, decks, media, problems})
when --out is given. Exit 0 when ok, 1 otherwise.
"""

import json
import re
import sys
import tempfile
import zipfile
from pathlib import Path

import click
from anki.collection import Collection, ImportAnkiPackageOptions, ImportAnkiPackageRequest
from anki.decks import DeckId

from adb_core.common import EXIT_FAIL, sha256_file, write_json

IMG_RE = re.compile(r'<img[^>]+src="([^"]+)"')


def validate(apkg: Path, cards_json: Path) -> dict:
    """Import a package into a fresh collection with Anki's engine and render every card.

    Args:
        apkg: The package to check.
        cards_json: The cards it was built from (for the expected note count).

    Returns:
        A report {"ok", "apkg_sha256", "notes", "cards", "decks", "media", "problems"}.
    """
    expected = json.loads(cards_json.read_text(encoding="utf-8"))
    problems: list[str] = []
    with zipfile.ZipFile(apkg) as z:
        names = z.namelist()
        if not any(n in names for n in ("collection.anki2", "collection.anki21", "collection.anki21b")):
            problems.append("package has no collection file")
        bad = z.testzip()
        if bad:
            problems.append(f"corrupt zip member {bad}")
    with tempfile.TemporaryDirectory() as tmp:
        col = Collection(str(Path(tmp) / "collection.anki2"))
        try:
            log = col.import_anki_package(
                ImportAnkiPackageRequest(
                    package_path=str(apkg.resolve()),
                    options=ImportAnkiPackageOptions(with_scheduling=False, with_deck_configs=False),
                )
            ).log
            if len(log.new) != len(expected):
                problems.append(f"imported {len(log.new)} notes, expected {len(expected)}")
            for field in ("missing_notetype", "missing_deck", "empty_first_field", "conflicting"):
                if len(getattr(log, field)):
                    problems.append(f"import log: {field}={len(getattr(log, field))}")
            decks = {
                d.name: col.decks.card_count(DeckId(d.id), include_subdecks=False)
                for d in col.decks.all_names_and_ids()
            }
            decks = {k: v for k, v in decks.items() if v}
            present = {p.name for p in Path(col.media.dir()).iterdir()}
            empty_q, render_err, missing = [], [], set()
            for cid in col.find_cards(""):
                card = col.get_card(cid)
                out = card.render_output()
                q, a = out.question_text, out.answer_text
                key = card.note()["Key"] if "Key" in card.note() else str(cid)
                if not re.sub(r"<[^>]+>|\s", "", q) and "<img" not in q:
                    empty_q.append(key)
                for text in (q, a):
                    low = text.lower()
                    if "template" in low and "error" in low:
                        render_err.append(key)
                    missing.update(n for n in IMG_RE.findall(text) if n not in present)
            if empty_q:
                problems.append(f"{len(empty_q)} card(s) with an empty question side: {sorted(set(empty_q))[:5]}")
            if render_err:
                problems.append(f"template errors on: {sorted(set(render_err))[:5]}")
            if missing:
                problems.append(f"cards reference missing media: {sorted(missing)[:5]}")
            check = col.media.check()
            if check.missing or check.unused:
                problems.append(f"media check: missing={list(check.missing)[:5]} unused={list(check.unused)[:5]}")
            report = {
                "ok": not problems,
                "apkg_sha256": sha256_file(apkg),
                "notes": col.note_count(),
                "cards": col.card_count(),
                "decks": decks,
                "media": len(present),
                "problems": problems,
            }
        finally:
            col.close()
    return report


@click.command(name="validate-deck")
@click.argument("apkg", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("cards_json", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--out", type=click.Path(dir_okay=False, path_type=Path), help="Also write the JSON report here.")
def cli(apkg: Path, cards_json: Path, out: Path | None) -> None:
    """Import APKG into a fresh collection and check every card renders (exit 1 on problems)."""
    report = validate(apkg, cards_json)
    if out:
        write_json(out, report)
    click.echo(f"notes={report['notes']} cards={report['cards']} media={report['media']}")
    for name, n in sorted(report["decks"].items()):
        click.echo(f"  {name}: {n} card(s)")
    for prob in report["problems"]:
        click.echo(f"PROBLEM: {prob}")
    click.echo("OK: imports cleanly and every card renders with its media" if report["ok"] else "FAIL")
    if not report["ok"]:
        sys.exit(EXIT_FAIL)


if __name__ == "__main__":
    cli()
