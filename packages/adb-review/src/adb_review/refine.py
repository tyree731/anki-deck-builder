"""Refine-phase rounds: render and screenshot every card, then prove that every card
in the round's review set was looked at and that every finding got a decision.

A round's review set is every card in round 1 and only the changed cards
(new, or different text or media) in later rounds. Signoff is tied to the exact
deck bytes: if build/deck.apkg changes after signoff, the Refine gate fails again.

`adb refine --help` lists the commands.

Review files in refine/round_N/: findings_*.json (review workers), personal_review.json
(the orchestrator's own look at changed cards), mechanical.json (adb render).
All use adb_core/schemas/findings.schema.json; triage.json uses triage.schema.json.
"""

import datetime as _dt
import sys
from pathlib import Path

import click

from adb_core import validate
from adb_core.common import EXIT_FAIL, EXIT_OK, load_config, read_json, run_paths, sha256_file, write_json
from adb_review import render_cards, shoot


def round_dir(run_dir: Path, n: int) -> Path:
    """Directory of a refine round.

    Args:
        run_dir: The run directory.
        n: Round number.

    Returns:
        <run_dir>/refine/round_<n>.
    """
    return run_paths(run_dir)["refine"] / f"round_{n}"


def last_round(run_dir: Path) -> int:
    """Highest round rendered so far.

    Args:
        run_dir: The run directory.

    Returns:
        The round number, or 0 before the first round.
    """
    rounds = [int(d.name.split("_")[1]) for d in run_paths(run_dir)["refine"].glob("round_*") if d.is_dir()]
    return max(rounds) if rounds else 0


def review_set(rdir: Path, n: int) -> list[str]:
    """Cards that must be reviewed in a round.

    Args:
        rdir: The round directory.
        n: Round number.

    Returns:
        Every card id in round 1; the ids in changed.txt in later rounds.
    """
    if n == 1:
        return [r["card_id"] for r in read_json(rdir / "index.json")]
    return [ln.strip() for ln in (rdir / "changed.txt").read_text().splitlines() if ln.strip()]


def review_files(rdir: Path) -> list[Path]:
    """Files that count as reviews in a round (mechanical.json does not).

    Args:
        rdir: The round directory.

    Returns:
        findings_*.json files, then personal_review.json if present.
    """
    files = sorted(rdir.glob("findings_*.json"))
    if (rdir / "personal_review.json").exists():
        files.append(rdir / "personal_review.json")
    return files


def render_round(run_dir: Path, n: int) -> int:
    """Render and screenshot a round, recording the deck hash it was rendered from.

    Args:
        run_dir: The run directory.
        n: Round number; rounds after 1 screenshot only changed cards and pack them into sheets.

    Returns:
        0 on success, 1 when the previous round is missing or a screenshot failed.
    """
    cfg = load_config()["refine"]
    p = run_paths(run_dir)
    apkg = p["build"] / "deck.apkg"
    rdir = round_dir(run_dir, n)
    prev: Path | None = None
    if n > 1:
        prev = round_dir(run_dir, n - 1) / "index.json"
        if not prev.exists():
            click.echo(f"round {n - 1} has not been rendered", err=True)
            return EXIT_FAIL
    info = render_cards.render(apkg, rdir, n, prev)
    changed: list[str] = info["changed"] or []
    only = None if n == 1 else set(changed)
    shots = shoot.shoot_round(rdir, only, sheet_prefix=None if n == 1 else "changed")
    write_json(
        rdir / "round.json",
        {
            "round": n,
            "deck_sha256": sha256_file(apkg),
            "cards": info["cards"],
            "review_set": "all" if n == 1 else "changed",
            "review_set_size": info["cards"] if n == 1 else len(changed),
            "rendered_at": _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds"),
        },
    )
    click.echo(f"round {n}: {info['cards']} card(s) rendered; mechanical issues: {info['mechanical_issues']}")
    if n == 1:
        click.echo(f"review set: all {info['cards']} card(s); screenshots in {rdir / 'shots'}")
    else:
        click.echo(f"review set: {len(changed)} changed card(s); sheets: {', '.join(shots['sheets']) or '(none)'}")
        prev_triage = round_dir(run_dir, n - 1) / "triage.json"
        if (
            not changed
            and prev_triage.exists()
            and any(d["decision"] == "fix" for d in read_json(prev_triage)["decisions"])
        ):
            click.echo(
                "WARNING: the previous round decided fixes but no card changed. Were the fixes applied and "
                "adb make-deck re-run?"
            )
    if shots["failed"]:
        click.echo(f"screenshot failures: {shots['failed']}", err=True)
        return EXIT_FAIL
    if n > cfg["max_rounds"]:
        click.echo(f"NOTE: round {n} exceeds refine.max_rounds={cfg['max_rounds']}: check in with the user")
    return EXIT_OK


def coverage(run_dir: Path, n: int) -> tuple[list[str], list[str]]:
    """Check that a round's reviews cover its review set.

    Args:
        run_dir: The run directory.
        n: Round number.

    Returns:
        (errors, missing): schema errors in review files, and review-set card ids nobody reviewed.
    """
    rdir = round_dir(run_dir, n)
    errors, reviewed = [], set()
    for f in review_files(rdir):
        errs = validate.validate_findings_file(f)
        errors += errs
        if not errs:
            reviewed |= set(read_json(f)["reviewed"])
    missing = [c for c in review_set(rdir, n) if c not in reviewed]
    return errors, missing


def all_findings(rdir: Path) -> list[tuple[str, dict]]:
    """Every finding in a round, with a stable reference.

    Args:
        rdir: The round directory.

    Returns:
        ("<file>#<index>", issue) pairs from mechanical.json and every review file.
    """
    out = []
    files = ([rdir / "mechanical.json"] if (rdir / "mechanical.json").exists() else []) + review_files(rdir)
    for f in files:
        for i, issue in enumerate(read_json(f)["issues"]):
            out.append((f"{f.name}#{i}", issue))
    return out


def triage_check(run_dir: Path, n: int) -> tuple[list[str], int]:
    """Check that triage.json decides every finding in a round.

    Args:
        run_dir: The run directory.
        n: Round number.

    Returns:
        (errors, fixes): problems found, and how many findings were decided "fix".
    """
    rdir = round_dir(run_dir, n)
    findings = all_findings(rdir)
    if not findings:
        return [], 0
    tfile = rdir / "triage.json"
    if not tfile.exists():
        return [f"{len(findings)} finding(s) but no {tfile}"], 0
    errors = validate.validate_triage_file(tfile)
    if errors:
        return errors, 0
    decisions = {d["finding"]: d for d in read_json(tfile)["decisions"]}
    for ref, issue in findings:
        if ref not in decisions:
            errors.append(f"no triage decision for {ref} ({issue['card_id']}: {issue['problem'][:60]})")
        elif decisions[ref]["severity"] != issue["severity"]:
            errors.append(
                f"{ref}: triage severity {decisions[ref]['severity']} differs from finding {issue['severity']}"
            )
    fixes = sum(1 for d in decisions.values() if d["decision"] == "fix")
    return errors, fixes


def signoff(run_dir: Path, accept: str | None) -> int:
    """Write refine/signoff.json when the last round is fully reviewed, triaged and fix-free.

    Args:
        run_dir: The run directory.
        accept: The user's approval text for shipping with open fixes, or None.

    Returns:
        0 when signed off, 1 when blocked (reasons on stderr).
    """
    p = run_paths(run_dir)
    n = last_round(run_dir)
    if n == 0:
        click.echo("no refine rounds yet", err=True)
        return EXIT_FAIL
    rdir = round_dir(run_dir, n)
    deck_sha = sha256_file(p["build"] / "deck.apkg")
    problems = []
    if read_json(rdir / "round.json")["deck_sha256"] != deck_sha:
        problems.append(f"build/deck.apkg changed after round {n} was rendered: run round {n + 1}")
    cov_err, missing = coverage(run_dir, n)
    problems += cov_err
    if missing:
        problems.append(f"{len(missing)} card(s) in round {n}'s review set were not reviewed, e.g. {missing[:5]}")
    tri_err, fixes = triage_check(run_dir, n)
    problems += tri_err
    if problems:
        click.echo("\n".join(problems), err=True)
        click.echo("signoff: BLOCKED")
        return EXIT_FAIL
    if fixes and not accept:
        click.echo(
            f"round {n} decided {fixes} fix(es): apply them, run adb make-deck, then render round {n + 1}. "
            "To stop here instead, ask the user and pass --accept-known-issues.",
            file=sys.stderr,
        )
        click.echo("signoff: BLOCKED")
        return EXIT_FAIL
    deferred, reviewed_total = [], 0
    for r in range(1, n + 1):
        rd = round_dir(run_dir, r)
        reviewed_total += len(review_set(rd, r))
        if (rd / "triage.json").exists():
            deferred += [d for d in read_json(rd / "triage.json")["decisions"] if d["decision"] == "defer"]
    status = "accepted_by_user" if fixes else "clean"
    write_json(
        p["refine"] / "signoff.json",
        {
            "status": status,
            "round": n,
            "rounds": n,
            "deck_sha256": deck_sha,
            "cards": read_json(rdir / "round.json")["cards"],
            "card_reviews_total": reviewed_total,
            "deferred": deferred,
            "accepted_note": accept,
            "signed_at": _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds"),
        },
    )
    click.echo(
        f"signoff: {status} after {n} round(s); {reviewed_total} card review(s); {len(deferred)} deferred low item(s)"
    )
    return EXIT_OK


RUN_DIR = click.Path(exists=True, file_okay=False, path_type=Path)
ROUND = click.option("--round", "rnd", type=click.IntRange(min=1), required=True, help="Round number.")


@click.group(name="refine")
def cli() -> None:
    """Review rounds: render, coverage, triage-check and signoff."""


@cli.command()
@click.argument("run_dir", type=RUN_DIR)
@ROUND
def render(run_dir: Path, rnd: int) -> None:
    """Render and screenshot a round (rounds after 1: only changed cards, packed into sheets)."""
    sys.exit(render_round(run_dir, rnd))


@cli.command("coverage")
@click.argument("run_dir", type=RUN_DIR)
@ROUND
def coverage_cmd(run_dir: Path, rnd: int) -> None:
    """Check that the round's reviews cover its review set."""
    errors, missing = coverage(run_dir, rnd)
    for e in errors:
        click.echo(e, err=True)
    for m in missing:
        click.echo(f"not reviewed: {m}")
    ok = not errors and not missing
    click.echo(f"coverage round {rnd}: {'PASS' if ok else f'FAIL ({len(missing)} unreviewed, {len(errors)} invalid)'}")
    if not ok:
        sys.exit(EXIT_FAIL)


@cli.command("triage-check")
@click.argument("run_dir", type=RUN_DIR)
@ROUND
def triage_check_cmd(run_dir: Path, rnd: int) -> None:
    """Check that triage.json decides every finding of the round."""
    errors, fixes = triage_check(run_dir, rnd)
    for e in errors:
        click.echo(e, err=True)
    click.echo(f"triage round {rnd}: {'PASS' if not errors else f'FAIL ({len(errors)})'}; fix decisions: {fixes}")
    if errors:
        sys.exit(EXIT_FAIL)


@cli.command("signoff")
@click.argument("run_dir", type=RUN_DIR)
@click.option("--accept-known-issues", "accept", help="The user's approval to ship with open fixes, in their words.")
def signoff_cmd(run_dir: Path, accept: str | None) -> None:
    """Sign off the last round (fully reviewed, triaged, fix-free), bound to the deck's bytes."""
    sys.exit(signoff(run_dir, accept))


if __name__ == "__main__":
    cli()
