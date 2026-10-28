"""Validate run-directory artifacts against the JSON schemas in adb_core/schemas/ and the
transcript format in references/extraction-conventions.md.

The same checks are importable (validate_* functions return a list of error strings)
and are what adb state uses to gate phase transitions.
"""

import json
import re
import sys
from pathlib import Path

import click
from jsonschema import Draft202012Validator

from adb_core.common import EXIT_FAIL, EXIT_IO, EXIT_PARSE, EXIT_USAGE, SCHEMAS, read_json, run_paths

TRANSCRIPT_FIELDS = ["File", "Source guess", "Orientation", "Summary", "Topics", "Legibility"]
TRANSCRIPT_HEADINGS = ["## Transcription", "## Figures", "## Equations", "## Key facts", "## Flags"]


class LoadError(Exception):
    def __init__(self, code: int, msg: str):
        super().__init__(msg)
        self.code = code


def _load(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise LoadError(EXIT_IO, f"{path}: <io>: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise LoadError(EXIT_PARSE, f"{path}: <parse>: line {exc.lineno} col {exc.colno}: {exc.msg}") from exc


def schema_errors(schema_name: str, payload, label: str) -> list[str]:
    """Validate a payload against one of the bundled JSON schemas.

    Args:
        schema_name: File name in adb_core/schemas/, e.g. "card.schema.json".
        payload: The parsed JSON to check.
        label: Prefix for each error message (usually the file path).

    Returns:
        One "<label>: <json path>: <message>" string per violation, in path order.
    """
    schema = read_json(SCHEMAS / schema_name)
    Draft202012Validator.check_schema(schema)
    errs = sorted(Draft202012Validator(schema).iter_errors(payload), key=lambda e: list(e.absolute_path))
    return [f"{label}: {'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in errs]


def active_units(manifest: dict) -> list[dict]:
    """Units that still need work: not excluded and not duplicates.

    Args:
        manifest: The parsed manifest.json.

    Returns:
        The active unit records, in manifest order.
    """
    return [u for u in manifest["units"] if not u["excluded"] and not u.get("duplicate_of")]


def resolve_pages(run_dir: Path, pages: str | None, subset: str | None) -> list[str]:
    """Turn a --pages or --subset option into page ids.

    Args:
        run_dir: The run directory.
        pages: Comma-separated page ids, or None.
        subset: A subset id from any subsets/<stage>.json, or None.

    Returns:
        The page ids to check; every active unit when neither option is given.

    Raises:
        LoadError: The subset id is not in any subset plan.
    """
    paths = run_paths(run_dir)
    if pages:
        return [p.strip() for p in pages.split(",") if p.strip()]
    if subset:
        for stage_file in sorted(paths["subsets"].glob("*.json")):
            for s in read_json(stage_file).get("subsets", []):
                if s["id"] == subset:
                    return list(s["pages"])
        raise LoadError(EXIT_USAGE, f"subset {subset} not found under {paths['subsets']}")
    return [u["id"] for u in active_units(read_json(paths["manifest"]))]


# ---------------------------------------------------------------- manifest
def validate_manifest(run_dir: Path) -> list[str]:
    """Check manifest.json against its schema and the files it references.

    Args:
        run_dir: The run directory.

    Returns:
        Error messages; empty when the manifest is valid.

    Raises:
        LoadError: manifest.json is missing or not valid JSON.
    """
    paths = run_paths(run_dir)
    payload = _load(paths["manifest"])
    errors = schema_errors("manifest.schema.json", payload, str(paths["manifest"]))
    if errors:
        return errors
    seen = set()
    for u in payload["units"]:
        if u["id"] in seen:
            errors.append(f"manifest: duplicate unit id {u['id']}")
        seen.add(u["id"])
        for key in ("image", "text"):
            if u.get(key) and not (paths["root"] / u[key]).exists():
                errors.append(f"manifest: {u['id']}: {key} file missing: {u[key]}")
        if not u.get("image") and not u.get("text"):
            errors.append(f"manifest: {u['id']}: has neither an image nor a text file")
    if not active_units(payload):
        errors.append("manifest: no active units (everything excluded or duplicate)")
    return errors


# ---------------------------------------------------------------- transcripts
def validate_transcript_text(page_id: str, text: str) -> list[str]:
    """Check one transcript's structure (title, header bullets, headings, content).

    Args:
        page_id: The page the transcript belongs to, e.g. "p007".
        text: The transcript's Markdown.

    Returns:
        Error messages; empty when the format is valid.
    """
    errors = []
    lines = text.splitlines()
    if not lines or lines[0].strip() != f"# {page_id}":
        errors.append(f"{page_id}: first line must be '# {page_id}'")
    for field in TRANSCRIPT_FIELDS:
        if not re.search(rf"^- {re.escape(field)}: \S", text, flags=re.M):
            errors.append(f"{page_id}: missing header bullet '- {field}: ...'")
    positions = []
    for heading in TRANSCRIPT_HEADINGS:
        m = re.search(rf"^{re.escape(heading)}\s*$", text, flags=re.M)
        if not m:
            errors.append(f"{page_id}: missing heading '{heading}'")
        else:
            positions.append(m.start())
    if len(positions) == len(TRANSCRIPT_HEADINGS) and positions != sorted(positions):
        errors.append(f"{page_id}: headings out of order (expected {' -> '.join(TRANSCRIPT_HEADINGS)})")
    m = re.search(r"^## Transcription\s*$(.*?)^## Figures", text, flags=re.M | re.S)
    if m and not m.group(1).strip():
        errors.append(f"{page_id}: '## Transcription' is empty (write '(blank page)' if the page has no content)")
    return errors


def validate_transcripts(run_dir: Path, page_ids: list[str]) -> list[str]:
    """Check that each page has a transcript in the documented format.

    Args:
        run_dir: The run directory.
        page_ids: Pages to check.

    Returns:
        Error messages, including missing transcripts.
    """
    paths = run_paths(run_dir)
    errors = []
    for pid in page_ids:
        f = paths["transcripts"] / f"{pid}.md"
        if not f.exists():
            errors.append(f"{pid}: transcript missing: {f}")
            continue
        errors.extend(validate_transcript_text(pid, f.read_text(encoding="utf-8")))
    return errors


# ---------------------------------------------------------------- figures
def validate_figures(run_dir: Path, page_ids: list[str]) -> list[str]:
    """Check each page's figure sidecar: schema, file naming, media present, mask numbering.

    Args:
        run_dir: The run directory.
        page_ids: Pages to check.

    Returns:
        Error messages, including missing sidecars.

    Raises:
        LoadError: A sidecar is not valid JSON.
    """
    paths = run_paths(run_dir)
    errors = []
    for pid in page_ids:
        f = paths["figures"] / f"{pid}.json"
        if not f.exists():
            errors.append(f'{pid}: figures sidecar missing: {f} (write {{"page_id": "{pid}", "figures": []}} if none)')
            continue
        payload = _load(f)
        errs = schema_errors("figures.schema.json", payload, str(f))
        if errs:
            errors.extend(errs)
            continue
        if payload["page_id"] != pid:
            errors.append(f"{f}: page_id {payload['page_id']} does not match file name")
        files = {fig["file"] for fig in payload["figures"]}
        for fig in payload["figures"]:
            if not fig["file"].startswith(f"{pid}_"):
                errors.append(f"{f}: {fig['file']}: figure files must be named '{pid}_<slug>.jpg|png'")
            if not (paths["media"] / fig["file"]).exists():
                errors.append(f"{f}: {fig['file']}: not found in media/")
            base = fig.get("base")
            if base and base not in files and not (paths["media"] / base).exists():
                errors.append(f"{f}: {fig['file']}: base {base} not found")
            numbers = [m["n"] for m in fig.get("mask_map", [])]
            if numbers and sorted(numbers) != list(range(1, len(numbers) + 1)):
                errors.append(f"{f}: {fig['file']}: mask_map numbers must run 1..{len(numbers)} with no gaps")
    return errors


# ---------------------------------------------------------------- categories
def validate_categories(run_dir: Path) -> list[str]:
    """Check categories.json: schema, unique ids, and that every active page is assigned.

    Args:
        run_dir: The run directory.

    Returns:
        Error messages; empty when every page has a known source and topics (or a skip reason).

    Raises:
        LoadError: categories.json is missing or not valid JSON.
    """
    paths = run_paths(run_dir)
    payload = _load(paths["categories"])
    errors = schema_errors("categories.schema.json", payload, str(paths["categories"]))
    if errors:
        return errors
    source_ids = [s["id"] for s in payload["sources"]]
    topic_slugs = [t["slug"] for t in payload["topics"]]
    for dupes, what in (
        (source_ids, "source id"),
        (topic_slugs, "topic slug"),
        ([s["subdeck"] for s in payload["sources"]], "subdeck"),
    ):
        for x in sorted({d for d in dupes if dupes.count(d) > 1}):
            errors.append(f"categories: duplicate {what} '{x}'")
    active = {u["id"] for u in active_units(read_json(paths["manifest"]))}
    skipped = {s["page"] for s in payload.get("skip_pages", [])}
    for pid in sorted(active):
        if pid not in payload["page_sources"]:
            errors.append(f"categories: page {pid} has no source in page_sources")
        elif payload["page_sources"][pid] not in source_ids:
            errors.append(f"categories: page {pid} assigned to unknown source '{payload['page_sources'][pid]}'")
        if pid not in skipped and not payload["page_topics"].get(pid):
            errors.append(f"categories: page {pid} has no topics (add to page_topics, or to skip_pages with a reason)")
    for pid, slugs in payload["page_topics"].items():
        for slug in slugs:
            if slug not in topic_slugs:
                errors.append(f"categories: page {pid} uses unknown topic '{slug}'")
    for pid in list(payload["page_sources"]) + list(payload["page_topics"]):
        if pid not in active:
            errors.append(f"categories: {pid} is not an active manifest unit")
    return errors


# ---------------------------------------------------------------- cards
def validate_cards_file(path: Path, run_dir: Path | None = None) -> list[str]:
    """Check one card file against the card schema, and optionally against the run.

    Args:
        path: A JSON array of cards (cards/<subset>.json).
        run_dir: When given, also check sources, topics and referenced media against the run.

    Returns:
        Error messages; empty when the file is valid.

    Raises:
        LoadError: The file is missing or not valid JSON.
    """
    payload = _load(path)
    errors = schema_errors("card.schema.json", payload, str(path))
    if errors or run_dir is None:
        return errors
    paths = run_paths(run_dir)
    cats = read_json(paths["categories"]) if paths["categories"].exists() else None
    sources = {s["id"] for s in cats["sources"]} if cats else None
    topics = {t["slug"] for t in cats["topics"]} if cats else None
    keys = set()
    for i, card in enumerate(payload):
        label = f"{path}: [{i}] {card['key']}"
        if card["key"] in keys:
            errors.append(f"{label}: duplicate key in file")
        keys.add(card["key"])
        if sources is not None and card["source"] not in sources:
            errors.append(f"{label}: unknown source '{card['source']}'")
        if topics is not None and card["topic"] not in topics:
            errors.append(f"{label}: unknown topic '{card['topic']}'")
        media = list(card.get("images", []))
        media += [card[k] for k in ("masked", "answer_image") if card.get(k)]
        for field in ("front", "back", "text", "extra", "prompt", "answer"):
            media += re.findall(r"\{\{img:([^}]+)\}\}", card.get(field, ""))
        for name in media:
            if not (paths["media"] / name.strip()).exists():
                errors.append(f"{label}: media file not found: {name}")
    return errors


def validate_findings_file(path: Path) -> list[str]:
    """Check a review findings file against findings.schema.json.

    Args:
        path: A findings_*.json or personal_review.json file.

    Returns:
        Error messages; empty when valid.

    Raises:
        LoadError: The file is missing or not valid JSON.
    """
    return schema_errors("findings.schema.json", _load(path), str(path))


def validate_triage_file(path: Path) -> list[str]:
    """Check a triage file against triage.schema.json.

    Args:
        path: A refine/round_N/triage.json file.

    Returns:
        Error messages; empty when valid.

    Raises:
        LoadError: The file is missing or not valid JSON.
    """
    return schema_errors("triage.schema.json", _load(path), str(path))


# ---------------------------------------------------------------- CLI
RUN_DIR = click.Path(exists=True, file_okay=False, path_type=Path)
JSON_FILE = click.Path(exists=True, dir_okay=False, path_type=Path)


def _report(what: str, check) -> None:
    """Run a check, print its errors and a PASS/FAIL line, and exit with the matching code.

    Args:
        what: Name shown in the summary line.
        check: Zero-argument callable returning error messages.
    """
    try:
        errors = check()
    except LoadError as exc:
        click.echo(str(exc), err=True)
        sys.exit(exc.code)
    for e in errors:
        click.echo(e, err=True)
    click.echo(f"{what}: {'PASS' if not errors else f'FAIL ({len(errors)} error(s))'}")
    if errors:
        sys.exit(EXIT_FAIL)


@click.group(name="validate")
def cli() -> None:
    """Validate run artifacts. Exit 0 pass, 1 errors (on stderr), 3 bad JSON, 4 I/O."""


@cli.command()
@click.argument("run_dir", type=RUN_DIR)
def manifest(run_dir: Path) -> None:
    """Check manifest.json and the page files it names."""
    _report("manifest", lambda: validate_manifest(run_dir))


PAGES = click.option("--pages", help="Comma-separated page ids (default: every active page).")
SUBSET = click.option("--subset", help="A subset id from subsets/<stage>.json, e.g. E03.")


@cli.command()
@click.argument("run_dir", type=RUN_DIR)
@PAGES
@SUBSET
def transcripts(run_dir: Path, pages: str | None, subset: str | None) -> None:
    """Check transcript format for the given pages."""
    _report("transcripts", lambda: validate_transcripts(run_dir, resolve_pages(run_dir, pages, subset)))


@cli.command()
@click.argument("run_dir", type=RUN_DIR)
@PAGES
@SUBSET
def figures(run_dir: Path, pages: str | None, subset: str | None) -> None:
    """Check figure sidecars and their media for the given pages."""
    _report("figures", lambda: validate_figures(run_dir, resolve_pages(run_dir, pages, subset)))


@cli.command()
@click.argument("run_dir", type=RUN_DIR)
def categories(run_dir: Path) -> None:
    """Check categories.json and that every active page is assigned."""
    _report("categories", lambda: validate_categories(run_dir))


@cli.command()
@click.argument("cards_file", type=JSON_FILE)
@click.option("--run-dir", type=RUN_DIR, help="Also check sources, topics and media against this run.")
def cards(cards_file: Path, run_dir: Path | None) -> None:
    """Check a card file against the card schema."""
    _report("cards", lambda: validate_cards_file(cards_file, run_dir))


@cli.command()
@click.argument("findings_file", type=JSON_FILE)
def findings(findings_file: Path) -> None:
    """Check a review findings file."""
    _report("findings", lambda: validate_findings_file(findings_file))


@cli.command()
@click.argument("triage_file", type=JSON_FILE)
def triage(triage_file: Path) -> None:
    """Check a refine triage file."""
    _report("triage", lambda: validate_triage_file(triage_file))


if __name__ == "__main__":
    cli()
