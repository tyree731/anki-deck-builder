"""Render the deck's content as one self-contained, printable study guide page:
one part per source (subdeck), grouped by topic, cloze answers highlighted,
labeled diagrams shown once with their full label list, images embedded.
A "spots worth a second look" box lists every correction and counts model answers.

"""

import base64
import re
from pathlib import Path

import click

from adb_core.common import chem_html, load_config, read_json, run_paths
from adb_core.templating import Markup, render

CLOZE_RE = re.compile(r"\{\{c\d+::(.*?)(?:::[^}]*)?\}\}", re.S)
IMG_RE = re.compile(r"\{\{img:([^}]+)\}\}")


def render_guide(run_dir: Path) -> str:
    """Render build/cards.json as one self-contained, printable HTML study guide.

    Args:
        run_dir: The run directory.

    Returns:
        The page HTML: one part per source, topics in order, cloze answers highlighted,
        diagrams shown once with their labels, images embedded, corrections listed up top.
    """
    p = run_paths(run_dir)
    cards = read_json(p["build"] / "cards.json")
    cats = read_json(p["categories"])
    shown: set[str] = set()

    def image(name: str) -> dict | None:
        name = name.strip()
        if name in shown or not (p["media"] / name).exists():
            return None
        shown.add(name)
        return {
            "name": name,
            "mime": "image/png" if name.endswith(".png") else "image/jpeg",
            "data": base64.b64encode((p["media"] / name).read_bytes()).decode(),
        }

    def fmt(s: str | None) -> Markup:
        # card fields are HTML by design (they become Anki fields), so they are trusted here.
        s = IMG_RE.sub("", s or "")
        return Markup(re.sub(r"\{\{chem:([^}]+)\}\}", lambda m: chem_html(m.group(1)), s))

    def card(c: dict) -> dict:
        return {
            "cloze": Markup(CLOZE_RE.sub(r"<mark>\1</mark>", fmt(c["text"]))) if c["type"] == "cloze" else None,
            "front": fmt(c.get("front")),
            "back": fmt(c.get("back")),
            "extra": fmt(c.get("extra")),
            "origin": c["origin"],
            "correction": fmt(c.get("correction")),
            "images": [img for n in c.get("images", []) if (img := image(n))],
        }

    topic_label = {t["slug"]: t["label"] for t in cats["topics"]}
    topic_order = {t["slug"]: t["order"] for t in cats["topics"]}
    parts = []
    for src in sorted(cats["sources"], key=lambda s: s["order"]):
        mine = [c for c in cards if c["source"] == src["id"]]
        topics = []
        for slug in sorted({c["topic"] for c in mine}, key=lambda s: topic_order.get(s, 999)):
            group = [c for c in mine if c["topic"] == slug]
            diagrams: dict[str, list[dict]] = {}
            for c in group:
                if c["type"] == "diagram":
                    diagrams.setdefault(c["answer_image"], []).append(c)
            shown_diagrams = [
                {
                    "title": re.sub(r"<[^>]+>", " ", ds[0]["prompt"]).split("What goes")[0].split("?")[0].strip(),
                    "answers": [fmt(d["answer"]) for d in ds],
                    "image": image(answer_img),
                }
                for answer_img, ds in diagrams.items()
            ]
            shown_cards = [card(c) for c in group if c["type"] != "diagram"]
            topics.append({"label": topic_label.get(slug, slug), "diagrams": shown_diagrams, "cards": shown_cards})
        parts.append({"label": src["label"], "description": src["description"], "topics": topics})

    return render(
        "adb_deck",
        "study_guide.html.jinja",
        title=cats["deck_root"],
        audience=cats["audience"],
        labels=load_config()["labels"],
        parts=parts,
        corrections=[fmt(c["correction"]) for c in cards if c["origin"] == "correction"],
        model_answers=sum(c["origin"] in ("model_answer", "model_goal") for c in cards),
    )


@click.command(name="study-guide")
@click.argument("run_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.argument("out_html", type=click.Path(dir_okay=False, path_type=Path))
def cli(run_dir: Path, out_html: Path) -> None:
    """Write the deck as one printable HTML study guide."""
    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_html.write_text(render_guide(run_dir), encoding="utf-8")
    click.echo(f"wrote {out_html} ({out_html.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    cli()
