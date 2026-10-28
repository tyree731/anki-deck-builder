"""Mechanical card checks that run before a deck is built (rule IDs from
references/card-writing-rules.md). Errors block the Synthesize gate; warnings are
for the author or orchestrator to judge. An error can be waived only through
build/waivers.json, with a reason:

    {"waivers": [{"rule": "L13", "key": "p014", "reason": "title page, nothing to learn"}]}

(for L13 the "key" is the page id; for every other rule it is the card key).

Exit 0 when there are no unwaived errors, 1 otherwise.
"""

import html as htmlmod
import re
import sys
from pathlib import Path

import click

from adb_core.common import (
    EXIT_FAIL,
    chem_html,
    load_config,
    read_json,
    run_paths,
    sha256_file,
    write_json,
)

CLOZE_RE = re.compile(r"\{\{c(\d+)::(.*?)(?:::([^}]*))?\}\}", re.S)
IMG_RE = re.compile(r"\{\{img:([^}]+)\}\}")
MACRO_RE = re.compile(r"\{\{(?!c\d+::)(?!img:)(?!chem:)")
NUMBER_WORDS = r"\b(\d+|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|both)\b"
INSTRUCTION_START = re.compile(
    r"^\s*(<[^>]+>\s*)*(define|name|list|give|explain|describe|what|which|why|how|"
    r"when|where|who|compare|identify|order|label|is|are|does|do|can|observation)\b",
    re.I,
)
REQUIRED = {"basic": ("front", "back"), "cloze": ("text",), "diagram": ("prompt", "masked", "answer", "answer_image")}
STUDENT_FIELDS = ("front", "back", "text", "prompt", "answer", "extra", "section", "correction")


def plain(s: str) -> str:
    """Learner-visible text of a field: macros and tags removed, entities decoded, whitespace collapsed.

    Args:
        s: Field HTML (may contain {{img:}} and {{chem:}} macros).

    Returns:
        Plain text.
    """
    s = IMG_RE.sub(" ", s)
    s = re.sub(r"\{\{chem:([^}]*)\}\}", r"\1", s)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    return re.sub(r"\s+", " ", htmlmod.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def words(s: str) -> int:
    """Count learner-visible words in a field.

    Args:
        s: Field HTML.

    Returns:
        The word count.
    """
    return len(plain(s).split())


def cloze_front(text: str, n: int) -> str:
    """Visible front of one card of a cloze note.

    Args:
        text: The note's Text field.
        n: The card's deletion number (c1 -> 1).

    Returns:
        Plain text with deletion n blanked as "[...]" and every other deletion shown.
    """

    def repl(m):
        return "[...]" if int(m.group(1)) == n else m.group(2)

    return plain(CLOZE_RE.sub(repl, text))


def phrase_in(phrase: str, text: str) -> bool:
    """Whole-word, case-insensitive containment, ignoring phrases under 3 characters.

    Args:
        phrase: Text to look for (HTML allowed).
        text: Plain text to search.

    Returns:
        True when phrase occurs in text as whole words ("dependent" is not in "independent").
    """
    phrase = plain(phrase).lower()
    if len(phrase) < 3:
        return False
    return re.search(rf"(?<![\w-]){re.escape(phrase)}(?![\w-])", text.lower()) is not None


def complementary(a: str, b: str) -> bool:
    """Whether two short hidden terms are a pair that would give each other away.

    Args:
        a: One hidden text.
        b: Another hidden text from a different deletion of the same note.

    Returns:
        True for pairs such as prokaryotes/eukaryotes or independent/dependent variable.
    """
    a, b = plain(a).lower(), plain(b).lower()
    if not a or not b or a == b or len(a.split()) > 3 or len(b.split()) > 3:
        return False
    if a.endswith(b) or b.endswith(a):
        return True
    common = 0
    for x, y in zip(reversed(a), reversed(b), strict=False):
        if x != y:
            break
        common += 1
    return common >= 5 and common >= min(len(a), len(b)) // 2


def list_items(back: str) -> int:
    """Rough count of list items in an answer (commas, semicolons, bullets, "and").

    Args:
        back: The answer field.

    Returns:
        The number of items; parenthesized asides are ignored.
    """
    text = re.sub(r"\(.*?\)", "", plain(back))
    parts = [x for x in re.split(r"[;,·•\n]|\band\b|\d\.\s", text) if x.strip()]
    return len(parts)


def lint(run_dir: Path) -> dict:
    """Run lint rules L01-L14 over build/cards.json (see references/card-writing-rules.md).

    Args:
        run_dir: The run directory; build/waivers.json, if present, waives specific errors.

    Returns:
        A report {"cards_sha256", "notes", "errors", "warnings", "waived"}; each item is
        {"rule", "key", "message"}.
    """
    cfg = load_config()["lint"]
    p = run_paths(run_dir)
    cards = read_json(p["build"] / "cards.json")
    cats = read_json(p["categories"])
    manifest = read_json(p["manifest"])
    figures = {}
    for f in p["figures"].glob("*.json"):
        for fig in read_json(f)["figures"]:
            figures[fig["file"]] = fig
    sources = {s["id"] for s in cats["sources"]}
    topics = {t["slug"] for t in cats["topics"]}
    internal = [re.compile(pat) for pat in cfg["internal_ref_patterns"]]  # case rules live in the patterns
    waivers = read_json(p["build"] / "waivers.json")["waivers"] if (p["build"] / "waivers.json").exists() else []
    waived = {(w["rule"], w["key"]) for w in waivers}
    errors, warnings, waived_hits = [], [], []

    def err(rule, key, msg):
        (waived_hits if (rule, key) in waived else errors).append({"rule": rule, "key": key, "message": msg})

    def warn(rule, key, msg):
        warnings.append({"rule": rule, "key": key, "message": msg})

    seen = set()
    for c in cards:
        k = c.get("key", "?")
        if k in seen:
            err("L01", k, "duplicate key")
        seen.add(k)
        missing = [f for f in REQUIRED.get(c.get("type"), ()) if not c.get(f)]
        if c.get("type") not in REQUIRED or missing:
            err("L02", k, f"type {c.get('type')} missing {missing}")
            continue
        if c["source"] not in sources:
            err("L14", k, f"unknown source '{c['source']}'")
        if c["topic"] not in topics:
            err("L14", k, f"unknown topic '{c['topic']}'")

        media = list(c.get("images", [])) + [c[f] for f in ("masked", "answer_image") if c.get(f)]
        for f in STUDENT_FIELDS:
            media += IMG_RE.findall(c.get(f, ""))
        for m in media:
            if not (p["media"] / m.strip()).exists():
                err("L03", k, f"media not found: {m}")

        for f in STUDENT_FIELDS:
            val = plain(c.get(f, ""))
            for pat in internal:
                hit = pat.search(val)
                if hit:
                    err(
                        "L04",
                        k,
                        f"internal reference '{hit.group(0)}' in {f}: keep file names, page ids "
                        "and photo numbers off the card",
                    )
            if MACRO_RE.search(c.get(f, "")):
                err("L05", k, f"unknown {{{{...}}}} macro in {f} (allowed: cloze, img:, chem:)")

        if c["type"] == "cloze":
            # {{chem:...}} may sit inside a deletion; expand it first so the cloze parse sees one "}}" per deletion.
            text = re.sub(r"\{\{chem:([^}]+)\}\}", lambda m: chem_html(m.group(1)), c["text"])
            dels = [(int(m.group(1)), m.group(2), m.group(3)) for m in CLOZE_RE.finditer(text)]
            nums = sorted({d[0] for d in dels})
            if not dels:
                err("L05", k, "cloze note has no {{cN::...}} deletions")
            for n in nums:
                front = cloze_front(text, n)
                for num, hidden, _hint in dels:
                    if num == n and phrase_in(hidden, front):
                        err(
                            "L06",
                            k,
                            f"c{n} hides '{plain(hidden)}' but the same words are visible on that "
                            "card's front. Reword it, or give every occurrence the same cN",
                        )
            hidden_by_num = {}
            for num, hidden, _ in dels:
                hidden_by_num.setdefault(num, []).append(hidden)
            for i, a in enumerate(nums):
                for b in nums[i + 1 :]:
                    for ha in hidden_by_num[a]:
                        for hb in hidden_by_num[b]:
                            if complementary(ha, hb):
                                warn(
                                    "L07",
                                    k,
                                    f"c{a} '{plain(ha)}' and c{b} '{plain(hb)}' are paired terms; each "
                                    "card shows the other, so it answers itself. Split into separate notes",
                                )
        if c["type"] == "basic":
            if list_items(c["back"]) >= 3 and not re.search(NUMBER_WORDS, plain(c["front"]), re.I):
                warn("L08", k, "answer is a list but the question doesn't say how many items to give")
            fw = plain(c["front"])
            if len(fw.split()) <= 4 and "?" not in fw and not INSTRUCTION_START.search(c["front"]):
                warn("L09", k, f"front '{fw}' is a bare term. Add an instruction such as 'Define:'")
            for m in IMG_RE.findall(c["front"]):
                fig = figures.get(m.strip())
                if fig and fig["kind"] != "masked" and fig.get("labels"):
                    warn("L12", k, f"front shows labeled figure {m}; use its masked version on the front")
        if c["type"] == "diagram":
            fig = figures.get(c["masked"])
            if c["masked"] == c["answer_image"]:
                err("L11", k, "masked image and answer image are the same file")
            elif fig is not None and fig["kind"] != "masked":
                err("L11", k, f"'{c['masked']}' is a {fig['kind']}, not a masked figure")
        front_text = c.get("front") or c.get("prompt") or c.get("text", "")
        back_text = (c.get("back") or c.get("answer") or "") + " " + c.get("extra", "")
        if words(front_text) > cfg["max_front_words"]:
            warn("L10", k, f"front is {words(front_text)} words (limit {cfg['max_front_words']})")
        if words(back_text) > cfg["max_back_words"]:
            warn("L10", k, f"back is {words(back_text)} words (limit {cfg['max_back_words']})")

    active = [u["id"] for u in manifest["units"] if not u["excluded"] and not u.get("duplicate_of")]
    skip = {s["page"] for s in cats.get("skip_pages", [])}
    cited = {pid for c in cards for pid in c.get("pages", [])}
    for pid in active:
        if pid not in skip and pid not in cited:
            err("L13", pid, f"page {pid} has no cards. Add cards, or list it in categories.skip_pages with a reason")
    return {
        "cards_sha256": sha256_file(p["build"] / "cards.json"),
        "notes": len(cards),
        "errors": errors,
        "warnings": warnings,
        "waived": waived_hits,
    }


def lint_into_build(run_dir: Path) -> dict:
    """Lint build/cards.json and save the report as build/lint.json, which the synthesize gate checks.

    Args:
        run_dir: The run directory.

    Returns:
        The report, as from lint().
    """
    report = lint(run_dir)
    write_json(run_paths(run_dir)["build"] / "lint.json", report)
    return report


@click.command(name="lint")
@click.argument("run_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
def cli(run_dir: Path) -> None:
    """Lint build/cards.json into build/lint.json (exit 1 when there are unwaived errors)."""
    report = lint_into_build(run_dir)
    for item in report["errors"]:
        click.echo(f"ERROR {item['rule']} {item['key']}: {item['message']}")
    for item in report["warnings"]:
        click.echo(f"warn  {item['rule']} {item['key']}: {item['message']}")
    click.echo(
        f"lint: {len(report['errors'])} error(s), {len(report['warnings'])} warning(s), "
        f"{len(report['waived'])} waived, {report['notes']} note(s)"
    )
    if report["errors"]:
        sys.exit(EXIT_FAIL)


if __name__ == "__main__":
    cli()
