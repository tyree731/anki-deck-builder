"""Run state for anki-deck-builder: mode dispatch, phase gates, batch tracking, resume.

state.json (in the run dir) is the durable record of a run. Phase transitions go
through `advance`, which refuses to mark a phase done until its artifact contract
(references/artifacts.md) holds on disk. That is what makes resume safe and what
stops a run from skipping a phase. `adb state --help` lists the commands.
"""

import datetime as _dt
import sys
from pathlib import Path

import click

from adb_core.common import (
    EXIT_FAIL,
    EXIT_IO,
    EXIT_USAGE,
    PHASES,
    load_config,
    read_json,
    run_paths,
    sha256_file,
    write_json,
)

STAGES = ("extract", "synthesize", "review")
BATCH_STATUSES = ("pending", "dispatched", "done", "failed")


def now() -> str:
    """Current UTC time for state records.

    Returns:
        An ISO-8601 timestamp with seconds precision.
    """
    return _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds")


def dirs_for(input_dir: Path) -> tuple[Path, Path]:
    """Run and output directories for an input folder (names from config.toml).

    Args:
        input_dir: The user's input folder.

    Returns:
        (run_dir, output_dir), both inside input_dir.
    """
    cfg = load_config()["paths"]
    return input_dir / cfg["run_dir_name"], input_dir / cfg["output_dir_name"]


def load_state(run_dir: Path) -> dict:
    """Read state.json, exiting with the I/O code if the run was never initialized.

    Args:
        run_dir: The run directory.

    Returns:
        The parsed state.
    """
    path = run_paths(run_dir)["state"]
    if not path.exists():
        click.echo(f"no state.json in {run_dir}: run `adb state init` first", err=True)
        sys.exit(EXIT_IO)
    return read_json(path)


def save_state(state: dict) -> None:
    """Stamp updated_at and write state.json atomically.

    Args:
        state: The state to save; its run_dir field says where.
    """
    state["updated_at"] = now()
    write_json(Path(state["run_dir"]) / "state.json", state)


def next_phase(state: dict) -> str | None:
    """The first phase that is not done.

    Args:
        state: The parsed state.json.

    Returns:
        The phase name, or None when every phase is done.
    """
    for phase in PHASES:
        if state["phases"][phase]["status"] != "done":
            return phase
    return None


# ------------------------------------------------------------------ artifact contracts
def _subset_ids(run_dir: Path, stage: str) -> list[str]:
    f = run_paths(run_dir)["subsets"] / f"{stage}.json"
    return [s["id"] for s in read_json(f)["subsets"]] if f.exists() else []


def verify_phase(run_dir: Path, phase: str) -> list[str]:
    """Check a phase's artifact contract (references/artifacts.md).

    Args:
        run_dir: The run directory.
        phase: One of organize, extract, categorize, synthesize, refine, complete.

    Returns:
        Unmet requirements; empty means the phase's gate passes.
    """
    from adb_core import validate as v  # local import: needs jsonschema from the venv

    p = run_paths(run_dir)
    state = load_state(run_dir)
    problems: list[str] = []

    def need(path: Path, what: str) -> bool:
        if not path.exists():
            problems.append(f"missing {what}: {path}")
            return False
        return True

    if phase == "organize":
        if need(p["manifest"], "manifest"):
            problems += v.validate_manifest(run_dir)
        if not list(p["sheets"].glob("contact_*.jpg")):
            problems.append(f"missing contact sheets: {p['sheets']}/contact_*.jpg")
        if need(p["subsets"] / "extract.json", "extract subset plan") and p["manifest"].exists():
            planned = [pid for s in read_json(p["subsets"] / "extract.json")["subsets"] for pid in s["pages"]]
            active = [u["id"] for u in v.active_units(read_json(p["manifest"]))]
            missing = sorted(set(active) - set(planned))
            doubled = sorted({x for x in planned if planned.count(x) > 1})
            if missing:
                problems.append(f"extract plan does not cover pages: {', '.join(missing)}")
            if doubled:
                problems.append(f"extract plan lists pages more than once: {', '.join(doubled)}")

    elif phase == "extract":
        active = [u["id"] for u in v.active_units(read_json(p["manifest"]))]
        problems += v.validate_transcripts(run_dir, active)
        problems += v.validate_figures(run_dir, active)
        for sid in _subset_ids(run_dir, "extract"):
            status = state["batches"]["extract"].get(sid, {}).get("status", "pending")
            if status != "done":
                problems.append(f"extract subset {sid} is '{status}', not 'done'")

    elif phase == "categorize":
        if need(p["categories"], "categories.json"):
            problems += v.validate_categories(run_dir)

    elif phase == "synthesize":
        if need(p["subsets"] / "synthesize.json", "synthesize subset plan"):
            for sid in _subset_ids(run_dir, "synthesize"):
                f = p["cards"] / f"{sid}.json"
                if need(f, f"card file for subset {sid}"):
                    problems += v.validate_cards_file(f, run_dir)
        cards = p["build"] / "cards.json"
        lint = p["build"] / "lint.json"
        apkg = p["build"] / "deck.apkg"
        report = p["build"] / "validate.json"
        if need(cards, "assembled cards") and need(lint, "lint report"):
            lr = read_json(lint)
            if lr.get("cards_sha256") != sha256_file(cards):
                problems.append("lint report is stale: re-run adb lint on the current build/cards.json")
            if lr.get("errors"):
                problems.append(f"lint report has {len(lr['errors'])} error(s); fix them or record a waiver")
        if need(apkg, "built deck") and need(report, "import validation report"):
            vr = read_json(report)
            if not vr.get("ok"):
                problems.append("adb validate-deck reported problems: " + "; ".join(vr.get("problems", [])[:5]))
            if vr.get("apkg_sha256") != sha256_file(apkg):
                problems.append("validate.json is stale: re-run adb validate-deck on the current build/deck.apkg")

    elif phase == "refine":
        signoff = p["refine"] / "signoff.json"
        if need(signoff, "refine signoff"):
            so = read_json(signoff)
            if so.get("status") not in ("clean", "accepted_by_user"):
                problems.append(f"signoff status is '{so.get('status')}'")
            apkg = p["build"] / "deck.apkg"
            if apkg.exists() and so.get("deck_sha256") != sha256_file(apkg):
                problems.append("build/deck.apkg changed after signoff: run another Refine round on the changed cards")

    elif phase == "complete":
        out = Path(state["output_dir"])
        summary = out / "summary.json"
        if need(summary, "output summary"):
            s = read_json(summary)
            apkg = out / s.get("apkg_file", "")
            if need(apkg, "final .apkg") and s.get("apkg_sha256") != sha256_file(apkg):
                problems.append("summary.json does not match the final .apkg (rebuild with adb complete)")
            if not s.get("validated"):
                problems.append("final .apkg failed import validation")
    else:
        problems.append(f"unknown phase {phase}")
    return problems


# ------------------------------------------------------------------ run operations
def detect_mode(input_dir: Path | None) -> dict[str, str]:
    """Work out how to start for the folder the user named.

    Args:
        input_dir: The input folder, or None when the user has not named one yet.

    Returns:
        "mode" (none, invalid, new, resume or complete) first, then "reason" when invalid,
        "next" when resuming, and input_dir/run_dir/output_dir when the folder exists.
    """
    if input_dir is None:
        return {"mode": "none"}
    input_dir = input_dir.expanduser().resolve()
    if not input_dir.is_dir():
        return {"mode": "invalid", "reason": f"not_a_directory:{input_dir}"}
    run_dir, out_dir = dirs_for(input_dir)
    dirs = {"input_dir": str(input_dir), "run_dir": str(run_dir), "output_dir": str(out_dir)}
    if not (run_dir / "state.json").exists():
        return {"mode": "new", **dirs}
    nxt = next_phase(read_json(run_dir / "state.json"))
    return {"mode": "complete", **dirs} if nxt is None else {"mode": "resume", "next": nxt, **dirs}


def init_run(input_dir: Path, deck_name: str | None = None, audience: str | None = None, force: bool = False) -> dict:
    """Create the run directory, its subfolders and a fresh state.json.

    Args:
        input_dir: The input folder; the run and output directories go inside it.
        deck_name: Deck root name, if the user gave one.
        audience: Who the deck is for, e.g. "7th grade".
        force: Start over even if a run already exists.

    Returns:
        The new state.

    Raises:
        FileExistsError: A run already exists and force is false.
    """
    input_dir = input_dir.expanduser().resolve()
    run_dir, out_dir = dirs_for(input_dir)
    if (run_dir / "state.json").exists() and not force:
        raise FileExistsError(f"{run_dir}/state.json exists: resume it, or pass --force to start over")
    for d in run_paths(run_dir).values():
        if d.suffix == "":
            d.mkdir(parents=True, exist_ok=True)
    state = {
        "schema_version": 1,
        "skill": "anki-deck-builder",
        "input_dir": str(input_dir),
        "run_dir": str(run_dir),
        "output_dir": str(out_dir),
        "created_at": now(),
        "updated_at": now(),
        "deck_name": deck_name,
        "audience": audience,
        "purpose": None,
        "phases": {ph: {"status": "pending", "completed_at": None} for ph in PHASES},
        "batches": {st: {} for st in STAGES},
    }
    save_state(state)
    return state


def advance_phase(run_dir: Path, phase: str) -> list[str]:
    """Mark a phase done, only if it is the next phase and its gate passes.

    Args:
        run_dir: The run directory.
        phase: The phase to mark done.

    Returns:
        What blocked it; empty when the phase was marked done.
    """
    state = load_state(run_dir)
    expected = next_phase(state)
    if phase != expected:
        return [f"cannot advance '{phase}': the next phase to complete is '{expected}'"]
    problems = verify_phase(run_dir, phase)
    if not problems:
        state["phases"][phase] = {"status": "done", "completed_at": now()}
        save_state(state)
    return problems


def reopen_phase(run_dir: Path, phase: str) -> None:
    """Mark a phase and every later phase pending again.

    Args:
        run_dir: The run directory.
        phase: The first phase to reopen.
    """
    state = load_state(run_dir)
    for ph in PHASES[PHASES.index(phase) :]:
        state["phases"][ph] = {"status": "pending", "completed_at": None}
    save_state(state)


def set_fields(
    run_dir: Path, deck_name: str | None = None, audience: str | None = None, purpose: str | None = None
) -> None:
    """Record the deck name, audience or purpose.

    Args:
        run_dir: The run directory.
        deck_name: Deck root name; None leaves it unchanged and "" clears it.
        audience: Who the deck is for; None leaves it unchanged and "" clears it.
        purpose: What it is for, e.g. "Quarter 1 test"; None leaves it unchanged and "" clears it.
    """
    state = load_state(run_dir)
    for key, value in (("deck_name", deck_name), ("audience", audience), ("purpose", purpose)):
        if value is not None:
            state[key] = value or None
    save_state(state)


def set_batch(run_dir: Path, stage: str, subset_id: str, status: str, note: str = "") -> None:
    """Record a work subset's status.

    Args:
        run_dir: The run directory.
        stage: extract, synthesize or review.
        subset_id: The subset, e.g. "E01".
        status: pending, dispatched, done or failed.
        note: Why, e.g. for a failed batch.
    """
    state = load_state(run_dir)
    state["batches"][stage][subset_id] = {"status": status, "updated_at": now(), "note": note}
    save_state(state)


def pending_subsets(run_dir: Path, stage: str) -> list[str]:
    """The planned subsets of a stage that are not done yet (to dispatch, or re-dispatch on resume).

    Args:
        run_dir: The run directory.
        stage: extract, synthesize or review.

    Returns:
        Subset ids in plan order.
    """
    batches = load_state(run_dir)["batches"][stage]
    return [sid for sid in _subset_ids(run_dir, stage) if batches.get(sid, {}).get("status") != "done"]


# ------------------------------------------------------------------ commands
RUN_DIR = click.Path(exists=True, file_okay=False, path_type=Path)
PHASE = click.Choice(PHASES)


@click.group(name="state")
def cli() -> None:
    """Mode dispatch, phase gates, batch tracking and resume for a run."""


@cli.command("detect")
@click.argument("input_dir", required=False, type=click.Path(path_type=Path))
def detect_cmd(input_dir: Path | None) -> None:
    """Print the run mode for INPUT_DIR: new, resume, complete, none or invalid (exit 2)."""
    info = detect_mode(input_dir)
    click.echo(" ".join(f"{k}={v}" for k, v in info.items()))
    if info["mode"] == "invalid":
        sys.exit(EXIT_USAGE)


@cli.command("init")
@click.argument("input_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--deck-name", help="Deck root name, if the user gave one.")
@click.option("--audience", help="Who the deck is for, e.g. '7th grade'.")
@click.option("--force", is_flag=True, help="Start over even if a run already exists.")
def init_cmd(input_dir: Path, deck_name: str | None, audience: str | None, force: bool) -> None:
    """Create the run directory and state.json for INPUT_DIR."""
    try:
        state = init_run(input_dir, deck_name, audience, force)
    except FileExistsError as exc:
        click.echo(str(exc), err=True)
        sys.exit(EXIT_FAIL)
    click.echo(f"initialized run_dir={state['run_dir']} output_dir={state['output_dir']}")


@cli.command()
@click.argument("run_dir", type=RUN_DIR)
def show(run_dir: Path) -> None:
    """Summarize a run: paths, deck, phase statuses, batch counts, next phase."""
    state = load_state(run_dir)
    click.echo(f"input:  {state['input_dir']}\nrun:    {state['run_dir']}\noutput: {state['output_dir']}")
    click.echo(f"deck:   {state.get('deck_name') or '(not set)'}   audience: {state.get('audience') or '(not set)'}")
    for ph in PHASES:
        info = state["phases"][ph]
        click.echo(f"  {ph:<11} {info['status']:<8} {info['completed_at'] or ''}")
    for stage in STAGES:
        batches = state["batches"][stage]
        if batches:
            counts = {s: sum(1 for b in batches.values() if b["status"] == s) for s in BATCH_STATUSES}
            click.echo(f"  {stage} subsets: " + ", ".join(f"{k}={n}" for k, n in counts.items() if n))
    click.echo(f"next: {next_phase(state) or '(run complete)'}")


@cli.command("next")
@click.argument("run_dir", type=RUN_DIR)
def next_cmd(run_dir: Path) -> None:
    """Print the next phase to complete, or 'complete'."""
    click.echo(next_phase(load_state(run_dir)) or "complete")


@cli.command()
@click.argument("run_dir", type=RUN_DIR)
@click.argument("phase", type=PHASE)
def verify(run_dir: Path, phase: str) -> None:
    """Check PHASE's artifact contract; exit 1 listing what is missing."""
    problems = verify_phase(run_dir, phase)
    for prob in problems:
        click.echo(f"  - {prob}", err=True)
    click.echo(f"verify {phase}: {'PASS' if not problems else f'FAIL ({len(problems)})'}")
    if problems:
        sys.exit(EXIT_FAIL)


@cli.command("advance")
@click.argument("run_dir", type=RUN_DIR)
@click.argument("phase", type=PHASE)
def advance_cmd(run_dir: Path, phase: str) -> None:
    """Mark PHASE done, only if it is the next phase and its gate passes."""
    problems = advance_phase(run_dir, phase)
    if problems:
        for prob in problems:
            click.echo(f"  - {prob}", err=True)
        click.echo(f"advance {phase}: BLOCKED ({len(problems)} unmet requirement(s))")
        sys.exit(EXIT_FAIL)
    click.echo(f"advance {phase}: done; next={next_phase(load_state(run_dir)) or 'complete'}")


@cli.command("reopen")
@click.argument("run_dir", type=RUN_DIR)
@click.argument("phase", type=PHASE)
def reopen_cmd(run_dir: Path, phase: str) -> None:
    """Mark PHASE and every later phase pending again."""
    reopen_phase(run_dir, phase)
    click.echo(f"reopened {phase} and every later phase")


@cli.command("set")
@click.argument("run_dir", type=RUN_DIR)
@click.option("--deck-name", help="Deck root name.")
@click.option("--audience", help="Who the deck is for.")
@click.option("--purpose", help="What it is for, e.g. 'Quarter 1 test'.")
def set_cmd(run_dir: Path, deck_name: str | None, audience: str | None, purpose: str | None) -> None:
    """Record the deck name, audience or purpose."""
    set_fields(run_dir, deck_name, audience, purpose)


@cli.command("batch")
@click.argument("run_dir", type=RUN_DIR)
@click.argument("stage", type=click.Choice(STAGES))
@click.argument("subset_id")
@click.argument("status", type=click.Choice(BATCH_STATUSES))
@click.option("--note", default="", help="Why, e.g. for a failed batch.")
def batch_cmd(run_dir: Path, stage: str, subset_id: str, status: str, note: str) -> None:
    """Set a work subset's status: pending, dispatched, done or failed."""
    set_batch(run_dir, stage, subset_id, status, note)


@cli.command("pending")
@click.argument("run_dir", type=RUN_DIR)
@click.argument("stage", type=click.Choice(STAGES))
def pending_cmd(run_dir: Path, stage: str) -> None:
    """List the subsets of STAGE that are not done yet (to dispatch, or re-dispatch on resume)."""
    for sid in pending_subsets(run_dir, stage):
        click.echo(sid)


if __name__ == "__main__":
    cli()
