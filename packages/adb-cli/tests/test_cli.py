"""Tests for adb_cli/cli.py (the `adb` dispatcher), including the whole pipeline driven through `adb`."""

import importlib
import json
from pathlib import Path

import click
import pytest

from adb_cli import cli
from adb_testkit import CATEGORIES, NOTES_CARDS, PACKET_CARDS, TRANSCRIPT, run_adb, write_json


def test_every_command_module_exposes_a_click_command():
    """test_every_command_module_exposes_a_click_command: each registered module imports and has a click `cli`
    whose name matches."""
    for name, (module, _desc) in cli.COMMANDS.items():
        command = importlib.import_module(module).cli
        assert isinstance(command, click.Command) and command.name == name, name


def test_adb_runs_through_uv_from_any_directory():
    """test_adb_runs_through_uv_from_any_directory: `uv run --frozen --project <skill> adb` works outside the
    skill dir."""
    proc = run_adb("state", "detect")
    assert proc.stdout.strip() == "mode=none"


def kv(line: str) -> dict:
    return dict(tok.split("=", 1) for tok in line.split() if "=" in tok)


@pytest.mark.integration
@pytest.mark.browser
def test_adb_full_pipeline_through_every_gate(corpus: Path, tmp_path: Path):
    """test_adb_full_pipeline_through_every_gate: runs every phase through the real `adb` command on a tiny corpus,
    checking each gate blocks before its artifacts exist and passes after (worker output is simulated)."""
    info = kv(run_adb("state", "detect", corpus).stdout)
    run_dir, out_dir = Path(info["run_dir"]), Path(info["output_dir"])
    run_adb("state", "init", corpus, "--deck-name", "Test Deck", "--audience", "7th grade")
    run_adb("preflight", corpus)

    # Organize
    run_adb("organize", "run", corpus, run_dir)
    run_adb("state", "advance", run_dir, "organize", check=False)
    assert json.loads((run_dir / "state.json").read_text())["phases"]["organize"]["status"] == "pending"
    run_adb("subsets", "extract", run_dir)
    run_adb("state", "advance", run_dir, "organize")

    # Extract: crop + mask for real, transcripts simulated
    media = run_dir / "media"
    run_adb(
        "imgtool", "crop", run_dir / "pages" / "p002.jpg", media / "p002_box.jpg", "--box", "680", "880", "1120", "1320"
    )
    spec = tmp_path / "mask.json"
    write_json(spec, {"boxes": [{"n": 1, "box": [30, 30, 200, 80]}, {"n": 2, "box": [30, 360, 200, 410]}]})
    run_adb("imgtool", "mask", media / "p002_box.jpg", spec, media / "p002_box_masked.jpg")
    for u in json.loads((run_dir / "manifest.json").read_text())["units"]:
        pid = u["id"]
        figs = (
            []
            if pid != "p002"
            else [
                {
                    "file": "p002_box.jpg",
                    "kind": "crop",
                    "title": "Labeled box",
                    "description": "d",
                    "labels": ["LABEL-A", "LABEL-B"],
                    "confidence": "high",
                },
                {
                    "file": "p002_box_masked.jpg",
                    "kind": "masked",
                    "base": "p002_box.jpg",
                    "title": "Labeled box",
                    "description": "d",
                    "labels": [],
                    "confidence": "high",
                    "mask_map": [{"n": 1, "label": "LABEL-A"}, {"n": 2, "label": "LABEL-B"}],
                },
            ]
        )
        (run_dir / "transcripts" / f"{pid}.md").write_text(
            TRANSCRIPT.format(
                pid=pid,
                file=u["source_file"],
                guess="notebook",
                summary="s",
                topics="cells",
                body="Text.",
                figs="None.",
                fact="f",
                flags="none",
            ),
            encoding="utf-8",
        )
        write_json(run_dir / "figures" / f"{pid}.json", {"page_id": pid, "figures": figs})
    for sid in [s["id"] for s in json.loads((run_dir / "subsets" / "extract.json").read_text())["subsets"]]:
        run_adb("state", "batch", run_dir, "extract", sid, "done")
    run_adb("state", "advance", run_dir, "extract")

    # Categorize
    run_adb("digest", run_dir)
    write_json(run_dir / "categories.json", CATEGORIES)
    run_adb("state", "advance", run_dir, "categorize")

    # Synthesize: first attempt has a cloze leak and an internal reference; the second is clean
    run_adb("subsets", "synthesize", run_dir)
    notes = [dict(c) for c in NOTES_CARDS]
    notes[0]["extra"] = "(photo IMG_0002)"
    notes[1]["text"] = "{{c1::Vacuole}}: stores water; the large central vacuole supports plant cells."
    write_json(run_dir / "cards" / "S01.json", notes)
    write_json(run_dir / "cards" / "S02.json", PACKET_CARDS)
    run_adb("make-deck", run_dir, check=False)
    assert {"L04", "L06"} <= {e["rule"] for e in json.loads((run_dir / "build" / "lint.json").read_text())["errors"]}
    assert not (run_dir / "build" / "deck.apkg").exists()
    write_json(run_dir / "cards" / "S01.json", NOTES_CARDS)
    run_adb("make-deck", run_dir)
    run_adb("state", "advance", run_dir, "synthesize")

    # Refine round 1: every card reviewed; one fix decided
    run_adb("refine", "render", run_dir, "--round", "1")
    r1 = run_dir / "refine" / "round_1"
    ids = [r["card_id"] for r in json.loads((r1 / "index.json").read_text())]
    assert len(ids) == 8
    write_json(
        r1 / "findings_R1_01.json",
        {
            "reviewer": "R1_01",
            "round": 1,
            "reviewed": ids,
            "issues": [
                {
                    "card_id": "pk_model:1",
                    "severity": "medium",
                    "category": "incomplete_answer",
                    "problem": "Answer should name what is compared.",
                    "suggested_fix": "say 'against the test group'",
                }
            ],
        },
    )
    mech = json.loads((r1 / "mechanical.json").read_text())["issues"]
    decisions = [
        {
            "finding": f"mechanical.json#{i}",
            "card_id": m["card_id"],
            "severity": m["severity"],
            "decision": "reject",
            "reason": "checked by eye",
        }
        for i, m in enumerate(mech)
    ]
    decisions.append(
        {
            "finding": "findings_R1_01.json#0",
            "card_id": "pk_model:1",
            "severity": "medium",
            "decision": "fix",
            "reason": "agreed",
        }
    )
    write_json(r1 / "triage.json", {"round": 1, "decisions": decisions})
    run_adb("refine", "signoff", run_dir, check=False)
    assert not (run_dir / "refine" / "signoff.json").exists()
    packet = [dict(c) for c in PACKET_CARDS]
    packet[0]["back"] = "To compare against the test group."
    write_json(run_dir / "cards" / "S02.json", packet)
    run_adb("make-deck", run_dir)

    # Refine round 2: only the changed card
    run_adb("refine", "render", run_dir, "--round", "2")
    r2 = run_dir / "refine" / "round_2"
    assert (r2 / "changed.txt").read_text().split() == ["pk_model:1"]
    write_json(
        r2 / "personal_review.json", {"reviewer": "orchestrator", "round": 2, "reviewed": ["pk_model:1"], "issues": []}
    )
    run_adb("refine", "signoff", run_dir)
    run_adb("state", "advance", run_dir, "refine")

    # Complete
    run_adb("complete", run_dir, out_dir)
    summary = json.loads((out_dir / "summary.json").read_text())
    assert summary["validated"] and (summary["notes"], summary["cards"]) == (7, 8)
    run_adb("state", "advance", run_dir, "complete")
    assert kv(run_adb("state", "detect", corpus).stdout)["mode"] == "complete"
