"""Build an .apkg from build/cards.json + categories.json + media/.

Deck layout: "<deck_root>::<subdeck>" per source (just "<deck_root>" when there is
one source). Three note types, all with a hidden Key field (references/note-types.md):

  Basic    Front / Back / Image / Extra / Source / Key
  Cloze    Text / Image / Extra / Source / Key
  Diagram  Prompt / Masked / Answer / AnswerImage / Extra / Source / Key

Field macros expanded at build time: {{img:file.jpg}} -> <img>, {{chem:C6H12O6}} -> subscripts.
Provenance labels come from `origin` (model_answer / model_goal / correction) using
config.toml [labels], so authors never hand-write them. The footer shows
"<source label> · <section or topic label>" and nothing internal.

Deck, model and note IDs derive from the deck name and card keys, so rebuilding
and re-importing updates notes in place and keeps the learner's review history.

"""

import re
import shutil
import sys
import tempfile
from pathlib import Path

import click
import genanki

from adb_core.common import (
    EXIT_FAIL,
    chem_html,
    load_config,
    read_json,
    run_paths,
    slugify,
    stable_id,
)

CSS = """
.card { font-family: -apple-system, "Segoe UI", Roboto, Arial, sans-serif; font-size: 22px; line-height: 1.45;
  text-align: center; color: #1d1d1f; background: #ffffff; padding: 8px; }
.q { font-size: 24px; font-weight: 600; }
.a { margin-top: 6px; }
.a ul, .a ol, .extra ul, .extra ol { text-align: left; display: inline-block; margin: 4px 0; }
.big { font-size: 28px; font-weight: 700; }
.extra { margin-top: 14px; font-size: 18px; color: #555; text-align: left; }
.src { margin-top: 18px; font-size: 13px; color: #8a8a8e; }
.img img, .q img { max-width: 100%; max-height: 70vh; border-radius: 6px; margin-top: 10px; }
table { border-collapse: collapse; margin: 8px auto; font-size: 17px; }
td, th { border: 1px solid #c7c7cc; padding: 4px 8px; }
th { background: #f2f2f7; }
.eq { font-size: 26px; font-family: "Times New Roman", serif; white-space: nowrap; }
.cloze { font-weight: 700; color: #0a62c9; }
.flag { font-size: 15px; color: #a15c00; margin-top: 8px; }
.nightMode.card, .night_mode .card { color: #f2f2f7; background: #1c1c1e; }
.nightMode .extra, .night_mode .extra { color: #b0b0b5; }
.nightMode th, .night_mode th { background: #2c2c2e; }
.nightMode td, .nightMode th, .night_mode td, .night_mode th { border-color: #48484a; }
.nightMode .cloze, .night_mode .cloze { color: #64a8ff; }
.nightMode .flag, .night_mode .flag { color: #ffb340; }
.nightMode .img img, .nightMode .q img, .night_mode .img img, .night_mode .q img { filter: brightness(0.92); }
"""

BACK_TAIL = (
    '{{#Image}}<div class="img">{{Image}}</div>{{/Image}}'
    '{{#Extra}}<div class="extra">{{Extra}}</div>{{/Extra}}<div class="src">{{Source}}</div>'
)


def note_types(deck_root: str):
    """The deck's three note types, with IDs derived from the deck name.

    Args:
        deck_root: The deck's root name.

    Returns:
        (basic, cloze, diagram) genanki models.
    """
    short = deck_root if len(deck_root) <= 28 else deck_root[:27] + "..."
    basic = genanki.Model(
        stable_id("anki-deck-builder", deck_root, "basic"),
        f"{short} · Basic",
        fields=[{"name": n} for n in ("Front", "Back", "Image", "Extra", "Source", "Key")],
        templates=[
            {
                "name": "Card 1",
                "qfmt": '<div class="q">{{Front}}</div>',
                "afmt": '{{FrontSide}}<hr id="answer"><div class="a">{{Back}}</div>' + BACK_TAIL,
            }
        ],
        css=CSS,
        sort_field_index=0,
    )
    cloze = genanki.Model(
        stable_id("anki-deck-builder", deck_root, "cloze"),
        f"{short} · Cloze",
        fields=[{"name": n} for n in ("Text", "Image", "Extra", "Source", "Key")],
        templates=[
            {
                "name": "Cloze",
                "qfmt": '<div class="a">{{cloze:Text}}</div>',
                "afmt": '<div class="a">{{cloze:Text}}</div>' + BACK_TAIL,
            }
        ],
        css=CSS,
        model_type=genanki.Model.CLOZE,
    )
    diagram = genanki.Model(
        stable_id("anki-deck-builder", deck_root, "diagram"),
        f"{short} · Diagram",
        fields=[{"name": n} for n in ("Prompt", "Masked", "Answer", "AnswerImage", "Extra", "Source", "Key")],
        templates=[
            {
                "name": "Label",
                "qfmt": '<div class="q">{{Prompt}}</div><div class="img">{{Masked}}</div>',
                "afmt": '<div class="q">{{Prompt}}</div><hr id="answer"><div class="a big">{{Answer}}</div>'
                '<div class="img">{{AnswerImage}}</div>'
                '{{#Extra}}<div class="extra">{{Extra}}</div>{{/Extra}}<div class="src">{{Source}}</div>',
            }
        ],
        css=CSS,
        sort_field_index=0,
    )
    return basic, cloze, diagram


def media_prefix(deck_root: str) -> str:
    """Prefix that keeps this deck's media names from colliding with other decks'.

    Args:
        deck_root: The deck's root name.

    Returns:
        A short slug ending in "_".
    """
    return slugify(deck_root, 16) + "_"


def expand(text: str, prefix: str) -> str:
    """Expand {{img:file}} and {{chem:formula}} macros in a field.

    Args:
        text: Field HTML.
        prefix: Media prefix for image file names.

    Returns:
        The field HTML with macros replaced.
    """
    text = re.sub(r"\{\{img:([^}]+)\}\}", lambda m: f'<img src="{prefix}{m.group(1).strip()}">', text or "")
    return re.sub(r"\{\{chem:([^}]+)\}\}", lambda m: chem_html(m.group(1)), text)


def referenced_media(card: dict) -> list[str]:
    """Every media file a card uses.

    Args:
        card: One card record.

    Returns:
        File names from images, masked, answer_image and inline {{img:}} macros.
    """
    names = list(card.get("images", [])) + [card[k] for k in ("masked", "answer_image") if card.get(k)]
    for field in ("front", "back", "text", "extra", "prompt", "answer"):
        names += [m.strip() for m in re.findall(r"\{\{img:([^}]+)\}\}", card.get(field, ""))]
    return names


def build(run_dir: Path, out_path: Path) -> dict:
    """Build an .apkg from build/cards.json, categories.json and media/.

    Args:
        run_dir: The run directory.
        out_path: Where to write the package.

    Returns:
        {"apkg", "notes", "media", "decks"} with notes per deck name.

    Raises:
        FileNotFoundError: A card references a media file that is not in media/.
    """
    cfg = load_config()
    labels = cfg["labels"]
    p = run_paths(run_dir)
    cats = read_json(p["categories"])
    cards = read_json(p["build"] / "cards.json")
    root = cats["deck_root"]
    prefix = media_prefix(root)
    basic_m, cloze_m, diagram_m = note_types(root)
    sources = {s["id"]: s for s in cats["sources"]}
    topics = {t["slug"]: t["label"] for t in cats["topics"]}
    single = len(sources) == 1
    decks = {}
    for s in sorted(cats["sources"], key=lambda s: s["order"]):
        name = root if single else f"{root}::{s['subdeck']}"
        decks[s["id"]] = genanki.Deck(stable_id("anki-deck-builder", "deck", name), name)

    used = set()
    deck_slug = slugify(root)
    for c in cards:
        src = sources[c["source"]]
        footer = f"{src['label']} · {c.get('section') or topics.get(c['topic'], c['topic'])}"
        flag = ""
        if c["origin"] == "model_answer":
            flag = f'<div class="flag">{labels["model_answer"]}</div>'
        elif c["origin"] == "model_goal":
            flag = f'<div class="flag">{labels["model_goal"]}</div>'
        elif c["origin"] == "correction":
            flag = f'<div class="flag">{labels["correction_prefix"]}{expand(c["correction"], prefix)}</div>'
        extra = expand(c.get("extra", ""), prefix) + flag
        image_html = "".join(f'<img src="{prefix}{n}">' for n in c.get("images", []))
        used.update(referenced_media(c))
        tags = ["anki_deck_builder", c["source"], f"topic::{c['topic']}", f"origin::{c['origin']}", *c.get("tags", [])]
        common = {"guid": genanki.guid_for(deck_slug, c["key"]), "tags": tags}
        if c["type"] == "basic":
            note = genanki.Note(
                model=basic_m,
                fields=[expand(c["front"], prefix), expand(c["back"], prefix), image_html, extra, footer, c["key"]],
                **common,
            )
        elif c["type"] == "cloze":
            note = genanki.Note(
                model=cloze_m, fields=[expand(c["text"], prefix), image_html, extra, footer, c["key"]], **common
            )
        else:
            note = genanki.Note(
                model=diagram_m,
                fields=[
                    expand(c["prompt"], prefix),
                    f'<img src="{prefix}{c["masked"]}">',
                    expand(c["answer"], prefix),
                    f'<img src="{prefix}{c["answer_image"]}">',
                    extra,
                    footer,
                    c["key"],
                ],
                **common,
            )
        decks[c["source"]].add_note(note)

    missing = sorted(n for n in used if not (p["media"] / n).is_file())
    if missing:
        raise FileNotFoundError(f"media missing from {p['media']}: {missing}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        files = []
        for n in sorted(used):
            dst = Path(tmp) / (prefix + n)
            shutil.copyfile(p["media"] / n, dst)
            files.append(str(dst))
        genanki.Package([d for d in decks.values() if d.notes], media_files=files).write_to_file(str(out_path))
    return {
        "apkg": str(out_path),
        "notes": len(cards),
        "media": len(used),
        "decks": {d.name: len(d.notes) for d in decks.values()},
    }


@click.command(name="build")
@click.argument("run_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.argument("out_apkg", type=click.Path(dir_okay=False, path_type=Path))
def cli(run_dir: Path, out_apkg: Path) -> None:
    """Build an .apkg from build/cards.json, categories.json and media/."""
    try:
        info = build(run_dir, out_apkg)
    except (FileNotFoundError, KeyError) as exc:
        click.echo(f"build failed: {exc}", err=True)
        sys.exit(EXIT_FAIL)
    click.echo(f"wrote {info['apkg']}: {info['notes']} note(s), {info['media']} media; decks={info['decks']}")


if __name__ == "__main__":
    cli()
