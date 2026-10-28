"""Tests for adb_core/subsets.py."""

from adb_core import subsets


def _manifest(kinds_files, excluded=(), duplicates=()):
    return {
        "units": [
            {
                "id": f"p{i:03d}",
                "kind": k,
                "source_file": f,
                "excluded": f"p{i:03d}" in excluded,
                "duplicate_of": "p001" if f"p{i:03d}" in duplicates else None,
            }
            for i, (k, f) in enumerate(kinds_files, 1)
        ]
    }


def test_plan_extract_respects_size_breaks_and_file_boundaries():
    """test_plan_extract_respects_size_breaks_and_file_boundaries: batches cap at the worker size, split at
    --break-before pages, and start fresh at a new file once half full."""
    m = _manifest([("image", "a.jpg")] * 7 + [("pdf_page", "b.pdf")] * 3)
    plan = subsets.plan_extract(m, per_worker=5, text_weight=0.34, breaks={"p004"})
    assert [s["pages"] for s in plan] == [
        ["p001", "p002", "p003"],
        ["p004", "p005", "p006", "p007"],
        ["p008", "p009", "p010"],
    ]
    assert [s["id"] for s in plan] == ["E01", "E02", "E03"]


def test_plan_extract_single_photo_files_fill_batches():
    """test_plan_extract_single_photo_files_fill_batches: one-photo-per-file folders (phone pictures) fill whole
    batches, and a run cut short by --break-before is balanced (3+3, not 5+1)."""
    m = _manifest([("image", f"IMG_{i}.jpg") for i in range(25)])
    assert [len(s["pages"]) for s in subsets.plan_extract(m, 5, 0.34, set())] == [5, 5, 5, 5, 5]
    assert [len(s["pages"]) for s in subsets.plan_extract(m, 5, 0.34, {"p007"})] == [3, 3, 5, 5, 5, 4]


def test_plan_extract_weights_text_pages_lightly():
    """test_plan_extract_weights_text_pages_lightly: text units cost about a third of an image, so batches hold
    more, and the batches are balanced."""
    m = _manifest([("text", "t.txt")] * 30)
    assert [len(s["pages"]) for s in subsets.plan_extract(m, 5, 0.34, set())] == [11, 11, 8]


def test_plan_extract_skips_excluded_and_duplicates():
    """test_plan_extract_skips_excluded_and_duplicates: excluded and duplicate units never reach a worker."""
    m = _manifest([("image", "a.jpg")] * 4, excluded={"p002"}, duplicates={"p004"})
    assert [s["pages"] for s in subsets.plan_extract(m, 5, 0.34, set())] == [["p001", "p003"]]


def test_plan_synthesize_packs_topics_and_splits_big_ones():
    """test_plan_synthesize_packs_topics_and_splits_big_ones: small topics share an author; a topic over the
    page limit is split into page chunks."""
    cats = {
        "sources": [{"id": "notes", "order": 1}],
        "topics": [{"slug": "a", "order": 1}, {"slug": "b", "order": 2}, {"slug": "c", "order": 3}],
        "page_sources": {f"p{i:03d}": "notes" for i in range(1, 13)},
        "page_topics": {
            **{f"p{i:03d}": ["a"] for i in range(1, 3)},
            **{f"p{i:03d}": ["b"] for i in range(3, 5)},
            **{f"p{i:03d}": ["c"] for i in range(5, 13)},
        },
    }
    plan = subsets.plan_synthesize(cats, per_author=4)
    assert plan[0]["topics"] == ["a", "b"] and plan[0]["pages"] == ["p001", "p002", "p003", "p004"]
    assert [s["topics"] for s in plan[1:]] == [["c"], ["c"]]
    assert [s["id"] for s in plan] == ["S01", "S02", "S03"]


def test_plan_synthesize_keeps_sources_apart_and_honors_skips():
    """test_plan_synthesize_keeps_sources_apart_and_honors_skips: each subset belongs to one source; skipped pages
    are not assigned."""
    cats = {
        "sources": [{"id": "packet", "order": 2}, {"id": "notes", "order": 1}],
        "topics": [{"slug": "a", "order": 1}],
        "page_sources": {"p001": "notes", "p002": "packet", "p003": "packet"},
        "page_topics": {"p001": ["a"], "p002": ["a"], "p003": ["a"]},
        "skip_pages": [{"page": "p003", "reason": "cover"}],
    }
    plan = subsets.plan_synthesize(cats, per_author=8)
    assert [(s["source"], s["pages"]) for s in plan] == [("notes", ["p001"]), ("packet", ["p002"])]


def test_plan_review_all_cards_or_changed_only():
    """test_plan_review_all_cards_or_changed_only: round 1 chunks every card; later rounds take only changed cards."""
    index = [{"n": i, "card_id": f"k{i}:1"} for i in range(1, 11)]
    assert [len(s["card_ids"]) for s in subsets.plan_review(index, None, per_reviewer=4, rnd=1)] == [4, 4, 2]
    plan = subsets.plan_review(index, ["k3:1", "k7:1"], per_reviewer=60, rnd=2)
    assert plan == [{"id": "R2_01", "round": 2, "first": 3, "last": 7, "card_ids": ["k3:1", "k7:1"], "pages": []}]
