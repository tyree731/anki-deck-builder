"""Tests for adb_review/refine.py (round bookkeeping; rendering itself is covered by test_render_cards)."""

import json
from pathlib import Path

import pytest

from adb_core.common import sha256_file
from adb_review import refine
from adb_testkit import write_json

IDS = ["a:1", "b:1", "c:1"]


@pytest.fixture
def rounds(run_dir: Path) -> Path:
    """run_dir with a stand-in deck and a rendered round 1 over cards a, b, c."""
    deck = run_dir / "build" / "deck.apkg"
    deck.parent.mkdir(parents=True, exist_ok=True)
    deck.write_bytes(b"deck v1")
    _render(run_dir, 1, IDS)
    return run_dir


def _render(run_dir: Path, n: int, ids: list[str], changed: list[str] | None = None) -> Path:
    rd = run_dir / "refine" / f"round_{n}"
    write_json(rd / "index.json", [{"n": i, "card_id": c} for i, c in enumerate(ids, 1)])
    write_json(rd / "mechanical.json", {"reviewer": "mechanical", "round": n, "reviewed": ids, "issues": []})
    write_json(
        rd / "round.json", {"round": n, "deck_sha256": sha256_file(run_dir / "build" / "deck.apkg"), "cards": len(ids)}
    )
    if changed is not None:
        (rd / "changed.txt").write_text("".join(c + "\n" for c in changed))
    return rd


def _issue(card_id: str, severity: str = "medium") -> dict:
    return {
        "card_id": card_id,
        "severity": severity,
        "category": "ambiguous",
        "problem": "unclear prompt",
        "suggested_fix": "say how many",
    }


def test_coverage_reports_unreviewed_cards(rounds: Path):
    """test_coverage_reports_unreviewed_cards: every card in round 1 must appear in some review file."""
    rd = rounds / "refine" / "round_1"
    write_json(rd / "findings_R1_01.json", {"reviewer": "r", "round": 1, "reviewed": ["a:1", "b:1"], "issues": []})
    errors, missing = refine.coverage(rounds, 1)
    assert errors == [] and missing == ["c:1"]


def test_coverage_later_rounds_need_only_changed_cards(rounds: Path):
    """test_coverage_later_rounds_need_only_changed_cards: round 2's review set is changed.txt, not every card."""
    rd = _render(rounds, 2, IDS, changed=["b:1"])
    write_json(rd / "personal_review.json", {"reviewer": "orchestrator", "round": 2, "reviewed": ["b:1"], "issues": []})
    assert refine.coverage(rounds, 2) == ([], [])


def test_triage_check_requires_a_decision_per_finding(rounds: Path):
    """test_triage_check_requires_a_decision_per_finding: every finding (mechanical included) needs a decision."""
    rd = rounds / "refine" / "round_1"
    write_json(
        rd / "findings_R1_01.json",
        {"reviewer": "r", "round": 1, "reviewed": IDS, "issues": [_issue("a:1"), _issue("b:1", "low")]},
    )
    errors, _ = refine.triage_check(rounds, 1)
    assert errors and "no" in errors[0]
    write_json(
        rd / "triage.json",
        {
            "round": 1,
            "decisions": [
                {
                    "finding": "findings_R1_01.json#0",
                    "card_id": "a:1",
                    "severity": "medium",
                    "decision": "fix",
                    "reason": "agreed",
                }
            ],
        },
    )
    errors, fixes = refine.triage_check(rounds, 1)
    assert any("findings_R1_01.json#1" in e for e in errors) and fixes == 1


def test_signoff_blocks_pending_fixes_and_deck_changes(rounds: Path):
    """test_signoff_blocks_pending_fixes_and_deck_changes: decided fixes, or a deck rebuilt after the round, block
    signoff."""
    rd = rounds / "refine" / "round_1"
    write_json(rd / "findings_R1_01.json", {"reviewer": "r", "round": 1, "reviewed": IDS, "issues": [_issue("a:1")]})
    write_json(
        rd / "triage.json",
        {
            "round": 1,
            "decisions": [
                {
                    "finding": "findings_R1_01.json#0",
                    "card_id": "a:1",
                    "severity": "medium",
                    "decision": "fix",
                    "reason": "agreed",
                }
            ],
        },
    )
    assert refine.signoff(rounds, None) == 1
    (rounds / "build" / "deck.apkg").write_bytes(b"deck v2")
    assert refine.signoff(rounds, "user said ship it") == 1  # deck changed since the round was rendered
    assert not (rounds / "refine" / "signoff.json").exists()


def test_signoff_clean_records_deck_hash(rounds: Path):
    """test_signoff_clean_records_deck_hash: a fully reviewed round with no fixes signs off against the exact deck
    bytes."""
    rd = rounds / "refine" / "round_1"
    write_json(
        rd / "findings_R1_01.json", {"reviewer": "r", "round": 1, "reviewed": IDS, "issues": [_issue("c:1", "low")]}
    )
    write_json(
        rd / "triage.json",
        {
            "round": 1,
            "decisions": [
                {
                    "finding": "findings_R1_01.json#0",
                    "card_id": "c:1",
                    "severity": "low",
                    "decision": "defer",
                    "reason": "style only",
                }
            ],
        },
    )
    assert refine.signoff(rounds, None) == 0
    so = json.loads((rounds / "refine" / "signoff.json").read_text())
    assert so["status"] == "clean" and so["deck_sha256"] == sha256_file(rounds / "build" / "deck.apkg")
    assert len(so["deferred"]) == 1 and so["card_reviews_total"] == 3


def test_signoff_accepts_known_issues_with_user_note(rounds: Path):
    """test_signoff_accepts_known_issues_with_user_note: pending fixes can be accepted only with an explicit note."""
    rd = rounds / "refine" / "round_1"
    write_json(rd / "findings_R1_01.json", {"reviewer": "r", "round": 1, "reviewed": IDS, "issues": [_issue("a:1")]})
    write_json(
        rd / "triage.json",
        {
            "round": 1,
            "decisions": [
                {
                    "finding": "findings_R1_01.json#0",
                    "card_id": "a:1",
                    "severity": "medium",
                    "decision": "fix",
                    "reason": "agreed",
                }
            ],
        },
    )
    assert refine.signoff(rounds, "user approved shipping with this open") == 0
    assert json.loads((rounds / "refine" / "signoff.json").read_text())["status"] == "accepted_by_user"
