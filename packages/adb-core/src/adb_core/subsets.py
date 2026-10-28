"""Plan the work subsets that parallel workers receive in each fan-out phase.

  extract     contiguous runs of pages (pages_per_worker, text pages weigh less),
              never straddling a --break-before page and preferring source-file boundaries
  synthesize  per source, consecutive topics packed until pages_per_author is reached;
              a topic bigger than the limit is split into page chunks
  review      card ranges of cards_per_reviewer from a Refine round's index
              (round 1: every card; later rounds: only cards in changed.txt)

Writes <run_dir>/subsets/<stage>.json and prints one line per subset.
"""

import math
import sys
from pathlib import Path

import click

from adb_core.common import EXIT_FAIL, load_config, read_json, run_paths, write_json


def plan_extract(manifest: dict, per_worker: float, text_weight: float, breaks: set[str]) -> list[dict]:
    """Plan contiguous, balanced extraction batches.

    Pages are first split into runs at every --break-before page; each run is then cut into
    ceil(weight / per_worker) batches of near-equal weight (6 pages -> 3+3, not 5+1). A
    batch also ends at the edge of a multi-page file (PDF, Office document) once it is half
    full, so one document's pages stay together. Single-photo files never force a break.

    Args:
        manifest: The parsed manifest.json.
        per_worker: Maximum page-equivalents per batch.
        text_weight: What a text-only unit counts for, relative to an image page.
        breaks: Page ids that must start a new batch.

    Returns:
        Subsets {"id": "E01", "pages": [...], "weight": float}, in page order.
    """
    active = [u for u in manifest["units"] if not u["excluded"] and not u.get("duplicate_of")]
    units_per_file: dict[str, int] = {}
    for u in active:
        units_per_file[u["source_file"]] = units_per_file.get(u["source_file"], 0) + 1

    def weight_of(u: dict) -> float:
        return text_weight if u["kind"] == "text" else 1.0

    runs: list[list[dict]] = []
    for u in active:
        if not runs or u["id"] in breaks:
            runs.append([])
        runs[-1].append(u)

    batches: list[list[dict]] = []
    for run in runs:
        total = sum(weight_of(u) for u in run)
        target = total / max(1, math.ceil(total / per_worker - 1e-9))
        cur: list[dict] = []
        weight = 0.0
        prev_file = None
        for u in run:
            w = weight_of(u)
            document_edge = (
                prev_file is not None
                and u["source_file"] != prev_file
                and (units_per_file[u["source_file"]] > 1 or units_per_file[prev_file] > 1)
            )
            too_heavy = weight + w > min(per_worker, target + 0.5) + 1e-9
            if cur and (too_heavy or (document_edge and weight >= per_worker / 2)):
                batches.append(cur)
                cur, weight = [], 0.0
            cur.append(u)
            weight += w
            prev_file = u["source_file"]
        if cur:
            batches.append(cur)
    return [
        {"id": f"E{i:02d}", "pages": [u["id"] for u in b], "weight": round(sum(weight_of(u) for u in b), 2)}
        for i, b in enumerate(batches, 1)
    ]


def plan_synthesize(categories: dict, per_author: int) -> list[dict]:
    """Plan author subsets: per source, consecutive topics packed up to a page limit.

    A topic with more pages than the limit is split into page chunks of its own, so each
    topic belongs to exactly one subset per source unless it is too big for one author.

    Args:
        categories: The parsed categories.json.
        per_author: Maximum distinct pages per subset.

    Returns:
        Subsets {"id": "S01", "source": str, "topics": [...], "pages": [...]}.
    """
    topic_order = {t["slug"]: t["order"] for t in categories["topics"]}
    skip = {s["page"] for s in categories.get("skip_pages", [])}
    out, n = [], 0
    for source in sorted(categories["sources"], key=lambda s: s["order"]):
        pages_by_topic: dict[str, list[str]] = {}
        for pid, src in sorted(categories["page_sources"].items()):
            if src != source["id"] or pid in skip:
                continue
            for slug in categories["page_topics"].get(pid, []):
                pages_by_topic.setdefault(slug, []).append(pid)
        groups, cur_topics, cur_pages = [], [], []
        for slug in sorted(pages_by_topic, key=lambda s: topic_order.get(s, 999)):
            pages = pages_by_topic[slug]
            if len(pages) > per_author:
                if cur_topics:
                    groups.append((cur_topics, cur_pages))
                    cur_topics, cur_pages = [], []
                for i in range(0, len(pages), per_author):
                    groups.append(([slug], pages[i : i + per_author]))
                continue
            merged = sorted(set(cur_pages) | set(pages))
            if cur_topics and len(merged) > per_author:
                groups.append((cur_topics, cur_pages))
                cur_topics, merged = [], sorted(pages)
            cur_topics.append(slug)
            cur_pages = merged
        if cur_topics:
            groups.append((cur_topics, cur_pages))
        for topics, pages in groups:
            n += 1
            out.append({"id": f"S{n:02d}", "source": source["id"], "topics": topics, "pages": pages})
    return out


def plan_review(index: list[dict], changed: list[str] | None, per_reviewer: int, rnd: int) -> list[dict]:
    """Plan reviewer ranges over a rendered round.

    Args:
        index: The round's index.json rows (n, card_id, ...).
        changed: Card ids to review (later rounds), or None for every card (round 1).
        per_reviewer: Maximum cards per reviewer.
        rnd: Round number, used in subset ids ("R2_01").

    Returns:
        Subsets {"id", "round", "first", "last", "card_ids", "pages"}.
    """
    rows = index if changed is None else [r for r in index if r["card_id"] in set(changed)]
    out = []
    for i in range(0, len(rows), per_reviewer):
        chunk = rows[i : i + per_reviewer]
        out.append(
            {
                "id": f"R{rnd}_{i // per_reviewer + 1:02d}",
                "round": rnd,
                "first": chunk[0]["n"],
                "last": chunk[-1]["n"],
                "card_ids": [r["card_id"] for r in chunk],
                "pages": [],
            }
        )
    return out


def _write_plan(run_dir: Path, stage: str, payload: dict) -> None:
    """Write subsets/<stage>.json and print one line per subset.

    Args:
        run_dir: The run directory.
        stage: extract, synthesize or review.
        payload: The plan, with its subsets under "subsets".
    """
    subsets = payload["subsets"]
    write_json(run_paths(run_dir)["subsets"] / f"{stage}.json", payload)
    if not subsets:
        click.echo(f"{stage}: nothing to plan", err=True)
        if stage != "review":
            sys.exit(EXIT_FAIL)
    for s in subsets:
        if stage == "review":
            click.echo(f"{s['id']}: cards #{s['first']}-#{s['last']} ({len(s['card_ids'])})")
        elif stage == "synthesize":
            click.echo(f"{s['id']}: source={s['source']} topics={','.join(s['topics'])} pages={','.join(s['pages'])}")
        else:
            click.echo(f"{s['id']}: {s['pages'][0]}-{s['pages'][-1]} ({len(s['pages'])} unit(s), weight {s['weight']})")


RUN_DIR = click.Path(exists=True, file_okay=False, path_type=Path)


@click.group(name="subsets")
def cli() -> None:
    """Plan the work subsets parallel workers receive in each fan-out phase."""


@cli.command()
@click.argument("run_dir", type=RUN_DIR)
@click.option("--break-before", default="", help="Comma-separated page ids that must start a new batch.")
def extract(run_dir: Path, break_before: str) -> None:
    """Plan extraction batches from the manifest."""
    cfg = load_config()["extract"]
    breaks = {p.strip() for p in break_before.split(",") if p.strip()}
    manifest = read_json(run_paths(run_dir)["manifest"])
    plan = plan_extract(manifest, cfg["pages_per_worker"], cfg["text_page_weight"], breaks)
    _write_plan(run_dir, "extract", {"stage": "extract", "subsets": plan})


@cli.command()
@click.argument("run_dir", type=RUN_DIR)
def synthesize(run_dir: Path) -> None:
    """Plan card-author subsets from categories.json."""
    plan = plan_synthesize(read_json(run_paths(run_dir)["categories"]), load_config()["synthesize"]["pages_per_author"])
    _write_plan(run_dir, "synthesize", {"stage": "synthesize", "subsets": plan})


@cli.command()
@click.argument("run_dir", type=RUN_DIR)
@click.option("--round", "rnd", type=click.IntRange(min=1), required=True, help="Refine round number.")
def review(run_dir: Path, rnd: int) -> None:
    """Plan reviewer ranges for a rendered refine round."""
    rdir = run_paths(run_dir)["refine"] / f"round_{rnd}"
    index = read_json(rdir / "index.json")
    changed = None
    if rnd > 1:
        changed = [ln.strip() for ln in (rdir / "changed.txt").read_text().splitlines() if ln.strip()]
    plan = plan_review(index, changed, load_config()["refine"]["cards_per_reviewer"], rnd)
    _write_plan(run_dir, "review", {"stage": "review", "round": rnd, "subsets": plan})


if __name__ == "__main__":
    cli()
