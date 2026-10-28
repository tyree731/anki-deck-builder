"""Complete phase: deliver the signed-off deck and its companions to the output dir.

The .apkg delivered is a byte-for-byte copy of the deck that passed Refine (a
rebuild would change the file and void the review), re-validated by importing it
into a fresh collection. Also writes, per config.toml [complete]:
  <Deck Root>.apkg
  Study Guide.html            (adb study-guide)
  transcriptions/<Source>.md  (adb export-transcripts)
  deck-source/                cards.json, categories.json, manifest.json, media/ (rebuild input)
  summary.json                counts per subdeck, provenance counts, review stats

"""

import re
import shutil
import sys
from collections import Counter
from pathlib import Path

import click

from adb_core.common import EXIT_FAIL, EXIT_OK, load_config, read_json, run_paths, sha256_file, write_json
from adb_deck import build_deck, export_transcripts, study_guide, validate_deck


def complete(run_dir: Path, out_dir: Path) -> int:
    """Deliver the signed-off deck and its companions to the output folder.

    Args:
        run_dir: The run directory.
        out_dir: The output folder.

    Returns:
        0 when the delivered deck re-validates, 1 when the deck is not the signed-off one or
        fails validation.
    """
    cfg = load_config()["complete"]
    p = run_paths(run_dir)
    signoff = read_json(p["refine"] / "signoff.json")
    built = p["build"] / "deck.apkg"
    if signoff["deck_sha256"] != sha256_file(built):
        click.echo("build/deck.apkg differs from the signed-off deck: finish Refine first", err=True)
        return EXIT_FAIL
    cats = read_json(p["categories"])
    cards = read_json(p["build"] / "cards.json")
    out_dir.mkdir(parents=True, exist_ok=True)
    apkg_name = re.sub(r'[\\/:*?"<>|]+', "-", cats["deck_root"]).strip() + ".apkg"
    final = out_dir / apkg_name
    shutil.copyfile(built, final)
    report = validate_deck.validate(final, p["build"] / "cards.json")
    click.echo(
        f"deck: {final}: {report['notes']} note(s), {report['cards']} card(s); "
        f"import validation {'ok' if report['ok'] else 'FAILED'}"
    )
    outputs: dict[str, str | list[str]] = {"apkg": str(final)}
    if cfg["study_guide"]:
        guide = out_dir / "Study Guide.html"
        guide.write_text(study_guide.render_guide(run_dir), encoding="utf-8")
        outputs["study_guide"] = str(guide)
        click.echo(f"study guide: {guide}")
    if cfg["export_transcripts"]:
        files = export_transcripts.export(run_dir, out_dir / "transcriptions")
        outputs["transcriptions"] = [str(f) for f in files]
        click.echo(f"transcriptions: {len(files)} file(s) in {out_dir / 'transcriptions'}")
    if cfg["deck_source"]:
        src = out_dir / "deck-source"
        if src.exists():
            shutil.rmtree(src)
        (src / "media").mkdir(parents=True)
        for name in ("cards.json",):
            shutil.copyfile(p["build"] / name, src / name)
        shutil.copyfile(p["categories"], src / "categories.json")
        shutil.copyfile(p["manifest"], src / "manifest.json")
        used = sorted({m for c in cards for m in build_deck.referenced_media(c)})
        for m in used:
            shutil.copyfile(p["media"] / m, src / "media" / m)
        (src / "README.md").write_text(
            "# Deck source\n\nThe notes (`cards.json`), deck structure (`categories.json`) and images (`media/`) "
            "this deck was built from. To change cards, resume the skill on the original folder (its working "
            f"files are in `{run_dir.name}/`) or edit `cards.json` there and re-run Refine. Notes keep stable "
            "IDs, so importing a rebuilt deck updates cards in place and keeps review history.\n",
            encoding="utf-8",
        )
        outputs["deck_source"] = str(src)
        click.echo(f"deck source: {src} ({len(used)} media file(s))")

    origins = Counter(c["origin"] for c in cards)
    summary = {
        "deck_root": cats["deck_root"],
        "audience": cats["audience"],
        "apkg_file": apkg_name,
        "apkg_sha256": sha256_file(final),
        "validated": report["ok"],
        "validation_problems": report["problems"],
        "notes": report["notes"],
        "cards": report["cards"],
        "decks": report["decks"],
        "media": report["media"],
        "origins": dict(origins),
        "corrections": [
            {"key": c["key"], "source": c["source"], "text": c["correction"]}
            for c in cards
            if c["origin"] == "correction"
        ],
        "refine": {
            "rounds": signoff["rounds"],
            "card_reviews": signoff["card_reviews_total"],
            "status": signoff["status"],
            "deferred": len(signoff["deferred"]),
        },
        "outputs": outputs,
    }
    write_json(out_dir / "summary.json", summary)
    click.echo(f"summary: {out_dir / 'summary.json'}")
    return EXIT_OK if report["ok"] else EXIT_FAIL


@click.command(name="complete")
@click.argument("run_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.argument("output_dir", type=click.Path(file_okay=False, path_type=Path))
def cli(run_dir: Path, output_dir: Path) -> None:
    """Deliver the signed-off deck and its companion files to OUTPUT_DIR."""
    sys.exit(complete(run_dir, output_dir))


if __name__ == "__main__":
    cli()
