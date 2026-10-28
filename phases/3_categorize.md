# Phase 3: Categorize

Goal: decide the deck's shape before any card is written. That means the deck name, the
sources (one subdeck each), the topic list, and which source and topics each page
belongs to. You do this yourself: it needs the whole corpus in view.

`adb ...` means `uv run --quiet --frozen --project "<SKILL_DIR>" adb ...`.

## Steps

**1. Build and read the digest.**

```bash
adb digest "<RUN_DIR>"
```

Read `<RUN_DIR>/digest.md` in full. It has one row per page: source guess, summary,
topics, legibility, figure count, plus every page's flags. Open individual transcripts
where a row is ambiguous.

**2. Decide the sources.** A source is a body of material the learner would recognize by
where it came from: "Class notes", "Review packet", "Chapter 4 (textbook)", "Lecture 3
slides". Group by origin, not by topic. People often want to see what came from their
own notes vs what the teacher handed out. Order the sources the way they'd study them.
Each source becomes the subdeck `<deck_root>::<subdeck>`, where `subdeck` is e.g.
`1 Class Notes`. With only one source the deck has no subdecks.

**3. Decide the topics.** Use 6 to 20 short slugs with labels, in the order the material
teaches them (e.g. `scientific_method`, `microscopes`, `cell_structures`). Topics drive
card tags, the study guide's sections, and how card-writing work is split. A page can
have several topics.

**4. Assign every active page.** Give it a source in `page_sources`, and topics in
`page_topics`, or put it in `skip_pages` with a reason. Only skip a page when it truly
has nothing to learn: an opinion warm-up, a doodle, the second photo of a page. Every
other page must end up with at least one card. Lint rule L13 enforces this.

**5. Name the deck and the learner.**
- `deck_root` takes the form "<level> <subject> <scope>", e.g. `Grade 7 Science Q1 -
  Cells`. It must not contain `::`.
- `audience` comes from the user's request if they said it. Otherwise use the materials
  (a grade level printed on a handout). Otherwise say `the learner`.
- Optional `purpose`: "Quarter 1 test", "AP Bio unit 2 exam".

**6. Note disagreements between sources.** Put them in `cross_source_notes`. For example:
"Packet: cell is the basic unit of structure and *function*; handout: structure and
*organization*." Authors will card both versions and note the difference.

**7. Write and validate `<RUN_DIR>/categories.json`.**

```json
{
  "deck_root": "Grade 7 Science Q1 - Cells",
  "audience": "7th grade",
  "purpose": "Quarter 1 test",
  "sources": [
    {"id": "notes", "label": "Class notes", "subdeck": "1 Class Notes", "description": "Her science notebook (19 pages)", "order": 1},
    {"id": "packet", "label": "Review packet", "subdeck": "2 Review Packet", "description": "Quarter 1 Study Guide (6 pages)", "order": 2}
  ],
  "topics": [{"slug": "microscopes", "label": "Microscopes", "order": 1}],
  "page_sources": {"p001": "packet"},
  "page_topics": {"p001": ["engineering_design", "experimental_design"]},
  "skip_pages": [{"page": "p044", "reason": "second photo of p043"}],
  "cross_source_notes": []
}
```

```bash
adb validate categories "<RUN_DIR>"
adb state set "<RUN_DIR>" --deck-name "Grade 7 Science Q1 - Cells" --audience "7th grade"
```

(The schema is `packages/adb-core/src/adb_core/schemas/categories.schema.json`.)

**8. Checkpoint.** This runs if `config.toml` has `after_categorize = true` under `[checkpoints]`,
which is the default. Ask with AskUserQuestion. Make the question stand on its own: state
the proposed deck name, list each subdeck with its page count, and give the audience.
Options:
- *Looks right (Recommended)*
- *Change the names*: they type the changes into the free-text option
- *Split or merge the subdecks differently*

Apply their answer, re-validate, then continue. Don't start Synthesize before they answer.

## Gate

```bash
adb state verify "<RUN_DIR>" categorize && adb state advance "<RUN_DIR>" categorize
```
