"""Render every card of an .apkg with Anki's own engine into review pages: the
question side on the left, the revealed answer side on the right, at tablet width.

Also writes:
  index.json        one row per card: n, card_id ("<key>:<ord>"), deck, note type,
                    plain question/answer text, media used (+ content hashes), page file
  mechanical.json   findings (adb_core/schemas/findings.schema.json) for problems a script
                    can see: empty fronts, cloze blanks missing, hidden answer visible
                    elsewhere on the front, raw markup showing
  changed.txt       (with --previous) card_ids that are new or whose text or media changed

"""

import hashlib
import html as htmlmod
import re
import shutil
import tempfile
from pathlib import Path

import click
from anki.collection import Collection, ImportAnkiPackageOptions, ImportAnkiPackageRequest

from adb_core import templating
from adb_core.common import load_config, read_json, write_json

TAG_RE = re.compile(r"<[^>]+>")
IMG_RE = re.compile(r'<img[^>]+src="([^"]+)"')
CLOZE_RE = re.compile(r"\{\{c(\d+)::(.*?)(?:::([^}]*))?\}\}", re.S)


def plain(s: str) -> str:
    """Visible text of rendered card HTML: styles and tags removed, line breaks kept.

    Args:
        s: Rendered question or answer HTML.

    Returns:
        Plain text.
    """
    s = re.sub(r"<style.*?</style>", "", s, flags=re.S)
    s = re.sub(r"<br\s*/?>|</div>|<hr[^>]*>", "\n", s)
    return re.sub(r"[ \t]+", " ", htmlmod.unescape(TAG_RE.sub("", s))).strip()


def phrase_in(phrase: str, text: str) -> bool:
    """Whole-word, case-insensitive containment, ignoring phrases under 3 characters.

    Args:
        phrase: Text to look for (HTML allowed).
        text: Plain text to search.

    Returns:
        True when phrase occurs in text as whole words.
    """
    phrase = plain(phrase).lower()
    if len(phrase) < 3:
        return False
    return re.search(rf"(?<![\w-]){re.escape(phrase)}(?![\w-])", text.lower()) is not None


def page_html(css: str, q: str, a: str, label: str, width: int, img_max_h: int) -> str:
    """Review page for one card: question on the left, revealed answer on the right.

    Args:
        css: The note type's CSS.
        q: Rendered question HTML.
        a: Rendered answer HTML.
        label: Header line (card number, id, deck).
        width: Width of each side in CSS pixels (tablet viewport).
        img_max_h: Image height cap in pixels (the template's 70vh on a tablet).

    Returns:
        A complete HTML document.
    """
    return templating.render(
        "adb_review",
        "card_page.html.jinja",
        css=templating.Markup(css),
        question=templating.Markup(q),
        answer=templating.Markup(a),
        label=label,
        width=width,
        img_max_h=img_max_h,
    )


def render(apkg: Path, out_dir: Path, rnd: int, previous: Path | None = None) -> dict:
    """Render every card of a package into review pages, an index and mechanical findings.

    Args:
        apkg: The package to render.
        out_dir: The round directory (html/ is recreated).
        rnd: Round number, recorded in mechanical.json.
        previous: An earlier round's index.json; when given, changed cards go to changed.txt.

    Returns:
        {"cards", "mechanical_issues", "changed"}; changed is None without previous.
    """
    cfg = load_config()["refine"]
    html_dir = out_dir / "html"
    if html_dir.exists():
        shutil.rmtree(html_dir)
    html_dir.mkdir(parents=True)
    index, issues = [], []
    with tempfile.TemporaryDirectory() as tmp:
        col = Collection(str(Path(tmp) / "c.anki2"))
        try:
            col.import_anki_package(
                ImportAnkiPackageRequest(package_path=str(apkg.resolve()), options=ImportAnkiPackageOptions())
            )
            media_dir = Path(col.media.dir())
            hashes = {}
            for f in media_dir.iterdir():
                shutil.copy(f, html_dir / f.name)
                hashes[f.name] = hashlib.sha256(f.read_bytes()).hexdigest()[:16]
            rows = []
            for cid in col.find_cards(""):
                card = col.get_card(cid)
                rows.append((col.decks.name(card.did), card.note()["Key"], card.ord, card))
            rows.sort(key=lambda r: (r[0], r[1], r[2]))
            for n, (deck, key, ord_, card) in enumerate(rows, 1):
                out = card.render_output()
                q, a = out.question_text, out.answer_text
                card_id = f"{key}:{ord_ + 1}"
                fname = f"{n:04d}_{key}_{ord_ + 1}"
                label = f"#{n} | {card_id} | {deck}"
                (html_dir / f"{fname}.html").write_text(
                    page_html(out.css, q, a, label, cfg["viewport_width_px"], int(cfg["viewport_height_px"] * 0.7)),
                    encoding="utf-8",
                )
                media = sorted(set(IMG_RE.findall(q) + IMG_RE.findall(a)))
                qt, at = plain(q), plain(a)
                notetype = card.note_type()["name"]
                index.append(
                    {
                        "n": n,
                        "card_id": card_id,
                        "key": key,
                        "ord": ord_ + 1,
                        "deck": deck,
                        "notetype": notetype,
                        "question": qt,
                        "answer": at,
                        "media": media,
                        "media_sha": {m: hashes.get(m) for m in media},
                        "page": f"{fname}.png",
                    }
                )

                def issue(category, severity, problem, fix, card_id=card_id):
                    issues.append(
                        {
                            "card_id": card_id,
                            "severity": severity,
                            "category": category,
                            "problem": problem,
                            "suggested_fix": fix,
                        }
                    )

                if not qt and "<img" not in q:
                    issue("rendering", "high", "question side is empty", "check the note's fields")
                if re.search(r"\{\{|\}\}|&lt;|&gt;|</?[a-z]+>", qt + at):
                    issue("rendering", "high", "raw markup or template syntax is visible", "fix the field HTML/macros")
                if notetype.endswith("Cloze"):
                    if not re.search(r"\[[^\]]*\]", qt):
                        issue("rendering", "high", "cloze front shows no blank", "check the {{cN::...}} syntax")
                    for m in CLOZE_RE.finditer(card.note()["Text"]):
                        if int(m.group(1)) == ord_ + 1 and phrase_in(m.group(2), qt):
                            issue(
                                "giveaway",
                                "high",
                                f"hidden answer '{plain(m.group(2))}' is visible elsewhere on the front",
                                "reword the other occurrence or give it the same cN",
                            )
        finally:
            col.close()
    write_json(out_dir / "index.json", index)
    write_json(
        out_dir / "mechanical.json",
        {"reviewer": "mechanical", "round": rnd, "reviewed": [r["card_id"] for r in index], "issues": issues},
    )
    changed = None
    if previous is not None:
        old = {r["card_id"]: r for r in read_json(previous)}
        changed = [
            r["card_id"]
            for r in index
            if r["card_id"] not in old
            or (old[r["card_id"]]["question"], old[r["card_id"]]["answer"], old[r["card_id"]]["media_sha"])
            != (r["question"], r["answer"], r["media_sha"])
        ]
        (out_dir / "changed.txt").write_text("".join(c + "\n" for c in changed), encoding="utf-8")
    return {"cards": len(index), "mechanical_issues": len(issues), "changed": changed}


@click.command(name="render")
@click.argument("apkg", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("out_dir", type=click.Path(file_okay=False, path_type=Path))
@click.option("--round", "rnd", type=click.IntRange(min=1), required=True, help="Round number.")
@click.option(
    "--previous",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="An earlier round's index.json; changed cards go to changed.txt.",
)
def cli(apkg: Path, out_dir: Path, rnd: int, previous: Path | None) -> None:
    """Render every card of APKG into review pages, an index and mechanical findings."""
    info = render(apkg, out_dir, rnd, previous)
    click.echo(
        f"rendered {info['cards']} card(s); mechanical issues: {info['mechanical_issues']}"
        + ("" if info["changed"] is None else f"; changed since previous round: {len(info['changed'])}")
    )


if __name__ == "__main__":
    cli()
