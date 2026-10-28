"""Build run directories at a known phase for tests."""

import hashlib
from pathlib import Path

from PIL import ImageDraw

from adb_core.common import write_json
from adb_testkit.images import page_image
from adb_testkit.samples import CATEGORIES, NOTES_CARDS, PACKET_CARDS, TRANSCRIPT


def make_run_dir(base: Path) -> Path:
    """Build a run directory that has reached the end of Synthesize, with lint-clean cards.

    Args:
        base: Folder to create the input folder ("materials") and its run directory in.

    Returns:
        The run directory.
    """
    from adb_core import state, subsets

    input_dir = base / "materials"
    input_dir.mkdir(parents=True, exist_ok=True)
    state.init_run(input_dir, deck_name="Test Deck", audience="7th grade")
    run_dir = input_dir / ".anki-build"
    kinds = [
        ("image", "IMG_1.jpg", None),
        ("image", "IMG_2.jpg", None),
        ("pdf_page", "packet.pdf", 1),
        ("pdf_page", "packet.pdf", 2),
        ("text", "vocab.txt", None),
    ]
    units = []
    for i, (kind, src, page) in enumerate(kinds, 1):
        pid = f"p{i:03d}"
        unit = {
            "id": pid,
            "kind": kind,
            "source_file": src,
            "page": page,
            "sha256": hashlib.sha256(pid.encode()).hexdigest(),
            "image": None,
            "text": None,
            "width": None,
            "height": None,
            "has_text_layer": kind == "text",
            "duplicate_of": None,
            "excluded": False,
            "exclude_reason": None,
        }
        if kind == "text":
            (run_dir / "pages" / f"{pid}.txt").write_text("Organelle: a specialized part of a cell.", encoding="utf-8")
            unit["text"] = f"pages/{pid}.txt"
        else:
            page_image([f"page {pid}"]).save(run_dir / "pages" / f"{pid}.jpg")
            unit.update(image=f"pages/{pid}.jpg", width=1200, height=1600)
        units.append(unit)
    write_json(
        run_dir / "manifest.json",
        {
            "schema_version": 1,
            "input_dir": str(input_dir),
            "generated_at": "2026-01-01T00:00:00+00:00",
            "units": units,
            "skipped": [],
        },
    )
    box = page_image(["x"]).crop((680, 880, 1120, 1320))
    box.save(run_dir / "media" / "p002_box.jpg")
    masked = box.copy()
    d = ImageDraw.Draw(masked)
    d.rectangle((30, 30, 200, 80), fill=(255, 224, 130))
    d.rectangle((30, 360, 200, 410), fill=(255, 224, 130))
    masked.save(run_dir / "media" / "p002_box_masked.jpg")
    for u in units:
        pid = u["id"]
        figs = []
        if pid == "p002":
            figs = [
                {
                    "file": "p002_box.jpg",
                    "kind": "crop",
                    "title": "Labeled box",
                    "description": "box with labels",
                    "labels": ["LABEL-A", "LABEL-B"],
                    "confidence": "high",
                },
                {
                    "file": "p002_box_masked.jpg",
                    "kind": "masked",
                    "base": "p002_box.jpg",
                    "title": "Labeled box",
                    "description": "labels hidden",
                    "labels": [],
                    "confidence": "high",
                    "mask_map": [{"n": 1, "label": "LABEL-A"}, {"n": 2, "label": "LABEL-B"}],
                },
            ]
        (run_dir / "transcripts" / f"{pid}.md").write_text(
            TRANSCRIPT.format(
                pid=pid,
                file=u["source_file"],
                guess="notebook" if pid < "p003" else "printed guide",
                summary=f"summary of {pid}",
                topics="cells",
                body="Some text.",
                figs="see sidecar" if figs else "None.",
                fact="a fact",
                flags="Student wrote the wrong constant." if pid == "p003" else "none",
            ),
            encoding="utf-8",
        )
        write_json(run_dir / "figures" / f"{pid}.json", {"page_id": pid, "figures": figs})
    write_json(run_dir / "categories.json", CATEGORIES)
    plan = subsets.plan_synthesize(CATEGORIES, per_author=8)
    write_json(run_dir / "subsets" / "synthesize.json", {"stage": "synthesize", "subsets": plan})
    write_json(run_dir / "cards" / f"{plan[0]['id']}.json", NOTES_CARDS)
    write_json(run_dir / "cards" / f"{plan[1]['id']}.json", PACKET_CARDS)
    return run_dir
