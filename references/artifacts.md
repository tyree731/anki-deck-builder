# Run directory and artifact contracts

A run lives in `<input folder>/.anki-build/` (the "run dir"). Deliverables go to
`<input folder>/anki-output/` (the "output dir"). Both names are set in `config.toml`
`paths`. The user's own files are never modified.

```
.anki-build/
  state.json              phases, batch statuses, deck name/audience (written only by `adb state`)
  manifest.json           one unit per page (organize)                         schema: manifest
  pages/                  normalized page images p001.jpg... and text p003.txt...
  sheets/contact_NN.jpg   labeled thumbnails of every unit
  organize_notes.md       orchestrator's notes on documents, rotations, hard pages
  subsets/                extract.json, synthesize.json, review.json (work split per phase)
  work/                   worker scratch (zooms, grids, mask specs, review sheets)
  transcripts/pNNN.md     one per active page (extract)
  figures/pNNN.json       figure sidecar per active page (extract)              schema: figures
  media/                  crops, masked figures, redraws (extract; patched in refine)
  digest.md               one row per page (categorize)
  categories.json         deck shape (categorize)                               schema: categories
  cards/SNN.json          one card file per author subset (+ fixups.json)       schema: card
  build/                  cards.json, card_owners.json, lint.json, waivers.json, deck.apkg, validate.json
  refine/
    round_N/              index.json, mechanical.json, html/, shots/, sheets/, changed.txt (N>=2),
                          findings_*.json, personal_review.json, triage.json, round.json
    signoff.json
```

Schemas live in `packages/adb-core/src/adb_core/schemas/<name>.schema.json`.

## Phase gates (`adb state verify <run_dir> <phase>`)

`adb state advance` runs the same checks and refuses to mark a phase done until they pass.

| Phase | Gate checks |
|-------|-------------|
| organize | `manifest.json` validates, and every page/text file it names exists; at least one contact sheet; `subsets/extract.json` lists every active unit exactly once |
| extract | every active unit has a valid transcript and a valid figure sidecar whose files exist in `media/`; every extract subset is `done` |
| categorize | `categories.json` validates; every active unit has a source; every non-skipped unit has topics; no unknown sources, topics or pages |
| synthesize | every planned card file exists and validates; `build/lint.json` is current (hash of `build/cards.json`) with no unwaived errors; `build/validate.json` is current (hash of `build/deck.apkg`) and ok |
| refine | `refine/signoff.json` exists with status `clean` or `accepted_by_user`, and its `deck_sha256` equals the current `build/deck.apkg` |
| complete | output `summary.json` exists, its `.apkg` exists with the recorded hash, and the import validation passed |

"Active unit" means not excluded and not a duplicate.

## Batch states (`adb state batch` / `pending`)

`pending`, then `dispatched`, then `done`, or `failed` (with a note). `adb state pending` lists every
subset of a stage that isn't `done`; on resume, re-dispatch exactly those.

## Refine round contract (`adb refine ...`)

- **Review set:** every card in round 1. In later rounds, only the cards in `changed.txt`:
  new cards, or cards whose question text, answer text or image bytes changed.
- **coverage:** the union of `reviewed` across `findings_*.json` and `personal_review.json`
  contains the whole review set. `mechanical.json` doesn't count as a review.
- **triage-check:** every issue in `mechanical.json`, `findings_*.json` and
  `personal_review.json` has a decision in `triage.json` (`<file>#<index>`) with matching
  severity. `defer` is allowed only for low severity.
- **signoff:**
  - the deck is unchanged since the last round was rendered
  - coverage and triage pass
  - the last round has no `fix` decisions, unless the user accepted known issues
  - signoff writes the deck hash
