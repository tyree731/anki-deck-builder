# Card author brief

You write the flashcards for one subset: one source (e.g. "Review packet") and a few
topics, over the pages named in your prompt. A learner will study these cards on a phone
or tablet, probably the night before a test. Every card must be correct, answerable from
what's on its front, and honest about where its content came from.

`adb ...` means `uv run --quiet --frozen --project "<SKILL_DIR>" adb ...`, with the literal
SKILL_DIR from your prompt.

## Read first

1. `<SKILL_DIR>/references/card-writing-rules.md`: the rules every card follows (CW-1 to CW-16).
   Most were learned from real review findings; they are not style preferences.
2. `<SKILL_DIR>/references/note-types.md`: the three note types, macros and provenance.
3. `RUN_DIR/categories.json`: deck name, sources, topic slugs, audience, cross-source notes.
4. For each of your pages: `RUN_DIR/transcripts/<page>.md` (the Flags section especially)
   and `RUN_DIR/figures/<page>.json`. Look at the figure images you'll use (`RUN_DIR/media/`).

## What to write: `RUN_DIR/cards/<subset>.json`

A JSON array of notes. Every `key` starts with your subset id in lowercase (`s03_...`), is
unique, and is stable (`s03_mito_function`, not `s03_card17`).

```json
[
  {"key": "s03_mito_function", "type": "cloze", "source": "packet", "topic": "cell_structures",
   "origin": "source", "pages": ["p004"], "section": "Section 7: Cell Structures",
   "text": "{{c1::Mitochondria}}: release usable energy from food through {{c2::cellular respiration}}."},

  {"key": "s03_controls_why", "type": "basic", "source": "packet", "topic": "experimental_design",
   "origin": "model_answer", "pages": ["p002"],
   "front": "<i>Practice:</i> Why is the container without yeast useful?",
   "back": "It's the <b>control</b>: it shows what happens without yeast, so any difference is caused by the yeast."},

  {"key": "s03_sunlight_const", "type": "basic", "source": "packet", "topic": "experimental_design",
   "origin": "correction", "pages": ["p002"],
   "correction": "your packet listed 'amount of sunlight' as a constant, but it's the <b>independent variable</b>.",
   "front": "<i>Practice:</i> Identical plants get 2, 4 or 6 hours of sunlight a day for 3 weeks. Name <b>two constants</b>.",
   "back": "The <b>type of plant</b> and the <b>growing time</b> (3 weeks)."},

  {"key": "s03_photo_eq", "type": "cloze", "source": "notes", "topic": "photosynthesis",
   "origin": "source", "pages": ["p019"], "images": ["p019_photosynthesis.jpg"],
   "text": "Photosynthesis: {{c1::{{chem:6CO2 + 6H2O}}}} → {{c2::{{chem:C6H12O6 + 6O2}}}}"},

  {"key": "s03_scope_part_6", "type": "diagram", "source": "notes", "topic": "microscopes",
   "origin": "source", "pages": ["p007"],
   "prompt": "<b>Parts of a microscope</b><br>What goes in box <b>#6</b>?",
   "masked": "p007_microscope_parts_masked.jpg", "answer": "#6 = diaphragm",
   "answer_image": "p007_microscope_parts.jpg"}
]
```

- `origin`:
  - `source`: content the materials state.
  - `derived`: a direct consequence of them, e.g. a 10X eyepiece and a 40X objective give 400X.
  - `model_answer`: your answer to a question the materials left blank.
  - `model_goal`: your answer to a learning goal ("Know how to explain...") that has no
    answer in the materials.
  - `correction`: needs a `correction` text, written kindly to the learner.
  The build adds the ✎ and ⚠ labels; don't write them yourself.
- `pages`: every page the card draws on. This is provenance, never shown on the card.
- `section`: optional footer label (e.g. the packet's section name). The footer otherwise
  shows the topic label.
- `images`: shown on the **back** only. The front gets an image only via a `diagram`'s
  `masked` file (or `{{img:...}}` of a masked figure).
- The schema is `<SKILL_DIR>/packages/adb-core/src/adb_core/schemas/card.schema.json`.

## Coverage

Turn everything test-worthy on your pages into cards:
- definitions (both directions, as separate notes)
- lists and sequences (one deletion per item or step)
- every labeled part of every masked diagram (one diagram note per box, using `mask_map`)
- equations (reactants, products, formulas and the word form)
- tables (one note per row or comparison)
- every practice question, all of its parts
- every "know how to" goal
- examples the learner worked through

Each Flag in the transcripts needs a response. A mistake becomes a `correction` card. A
blank question becomes a `model_answer` card. A disagreement between sources means you
card both versions and say they differ. A crossed-out wrong note gets no card. Every page
in your list must be cited by at least one card, unless categories.json skips it.

## Before you reply

```bash
adb validate cards "RUN_DIR/cards/<subset>.json" --run-dir "RUN_DIR"
```

It must PASS. Then re-read your file against the CW checklist in card-writing-rules.md,
looking hardest at giveaways (CW-3, CW-4), counts (CW-6) and context (CW-7). Reply in
under 120 words:
- notes by type
- pages covered
- the model answers and corrections you added
- anything on the pages you couldn't turn into a card
