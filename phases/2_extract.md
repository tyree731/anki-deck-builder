# Phase 2: Extract

Goal: a faithful transcription of every page, plus flashcard-ready figures. Figures are
tight crops, hidden-label ("masked") versions of labeled diagrams, and clean redraws
where a photo is too poor. Workers do this in parallel, using vision. You check their
work, and you look at every masked figure yourself.

`adb ...` means `uv run --quiet --frozen --project "<SKILL_DIR>" adb ...`.

## Steps

**1. Find the batches still to do.**

```bash
adb state pending "<RUN_DIR>" extract
```

On a fresh run this is every batch. On resume, only those not yet `done`.

**2. Dispatch extract workers.** Dispatch one Agent (`general-purpose`) per batch, all
in one message and in the background. Send up to `extract.max_parallel_workers` at a
time and start the next wave as workers finish. Mark each one dispatched first:
`adb state batch "<RUN_DIR>" extract E03 dispatched`. Prompt template:

```
You are an extract worker for the anki-deck-builder skill. Read
<SKILL_DIR>/workers/extract_worker.md and follow it exactly.

- SKILL_DIR: <SKILL_DIR>
- RUN_DIR: <RUN_DIR>
- Your subset: E03, pages p011, p012, p013, p014, p015
- Learner: <audience, or "unknown">
- From Organize: <the organize_notes.md lines that cover these pages>

Reply in under 150 words: one line per page (what it is, legibility), the figure files
you made, and anything you could not read.
```

**3. Verify each batch as it returns.**

```bash
adb validate transcripts "<RUN_DIR>" --subset E03
adb validate figures "<RUN_DIR>" --subset E03
```

If both pass, run `adb state batch "<RUN_DIR>" extract E03 done`. If either fails,
re-dispatch the batch once, with the validator output added to the prompt. After a
second failure, run `adb state batch ... failed --note "<why>"`, then stop and tell the user.

**4. Look at every masked figure yourself.** Find them in the `figures/*.json` sidecars
(`kind: "masked"`). Put each beside its base figure on one sheet, several per sheet:

```bash
adb imgtool sheet "<RUN_DIR>/work/masks_01.jpg" "<RUN_DIR>/media/p007_parts.jpg" "<RUN_DIR>/media/p007_parts_masked.jpg" ...
```

For each masked figure confirm three things:
- Every label is fully hidden, and the box numbers are readable.
- The numbers match the sidecar's `mask_map`.
- Nothing else in the image gives a hidden label away, for example:
  - a title or caption naming a part ("The release of energy..." hides "energy released")
  - the learner's own annotations next to a box (a "10X" by the eyepiece)
  - clipped text from the next line along an edge

Fix giveaways now: `adb imgtool cover` (paint it out) or `adb imgtool trim` (cut the edge
off). Then view the result again. Catching these here saves a Refine round. Also skim
the `## Flags` sections. They are where workers note the learner's mistakes, blank
answers and disagreements between pages, which Categorize and authors need.

## Gate

```bash
adb state verify "<RUN_DIR>" extract && adb state advance "<RUN_DIR>" extract
```

Progress line: *"Transcribed 25 pages; 31 figures (14 with hidden labels, 2 redrawn).
Couldn't read: two crossed-out words on p014."*
