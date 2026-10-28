# Phase 4: Synthesize

Goal: author workers turn transcripts and figures into cards. Each worker covers one
source and a few topics. Then build the deck and get it through lint and an import into
a fresh Anki collection.

`adb ...` means `uv run --quiet --frozen --project "<SKILL_DIR>" adb ...`.

## Steps

**1. Plan the author subsets.**

```bash
adb subsets synthesize "<RUN_DIR>"
```

This prints `S01: source=... topics=... pages=...`. Each topic appears in exactly one subset
per source, so authors don't duplicate each other.

**2. Dispatch the author workers.** Dispatch one Agent per subset, in waves of
`synthesize.max_parallel_authors`, marking each `dispatched` first. Prompt template:

```
You are a card author for the anki-deck-builder skill. Read
<SKILL_DIR>/workers/author_worker.md and follow it exactly.

- SKILL_DIR: <SKILL_DIR>
- RUN_DIR: <RUN_DIR>
- Your subset: S03, source "packet" (Review packet), topics: cell_structures, cell_membrane
- Pages: p004, p005, p006
- Write to: <RUN_DIR>/cards/S03.json   (every key starts with "s03_")
- Learner: 7th grade, studying for: Quarter 1 test
- Cross-source notes: <the relevant categories.cross_source_notes, or "none">

Reply in under 120 words: note count by type, pages covered, model answers and
corrections you added, and anything in the pages you could not turn into a card.
```

**3. Verify each subset as it returns.**

```bash
adb validate cards "<RUN_DIR>/cards/S03.json" --run-dir "<RUN_DIR>"
```

If it passes, run `adb state batch "<RUN_DIR>" synthesize S03 done`. If not,
re-dispatch the subset once with the errors added. Then treat it as you would a failed
extract batch.

**4. Build.**

```bash
adb make-deck "<RUN_DIR>"
```

This runs five steps: validate every card file, assemble `build/cards.json`, lint, build
`build/deck.apkg`, and import-validate. Handle the outcome like this:

- **Lint errors** (they block the gate):
  - Fix small ones yourself in the owning file. `build/card_owners.json` maps each card
    key to its file.
  - Send bigger problems back to the author with the lint lines.
  - **L13** (a page with no cards): add the missing cards to `cards/fixups.json` (same
    schema). If the page truly has nothing to learn, move it to `skip_pages` in
    `categories.json` instead. Use `build/waivers.json` only as a last resort, and
    always with a reason.
- **Lint warnings:** read every one. L07 (paired terms that give each other away), L08
  (a list answer whose question doesn't say how many) and L09 (a bare-term front) are
  nearly always real. Fix them now, or they come back as Refine findings.
- **Import validation problems:** these are build bugs. Report them; don't work around
  them.

Re-run `adb make-deck` until it ends with `step 5/5 import-validate: ok` and no lint errors.

**5. Sanity-check the volume.** Compare notes per subdeck against content pages. Typical
pages yield 5 to 15 notes, and a dense review packet more. A subset far below that usually
skipped content. Look at its pages, and send the subset back if so.

## Gate

```bash
adb state verify "<RUN_DIR>" synthesize && adb state advance "<RUN_DIR>" synthesize
```

Progress line: *"Wrote 199 notes (306 cards: Class Notes 227, Review Packet 79); lint
clean; imports into Anki cleanly. Next: looking at every card."*
