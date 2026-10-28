# Note types, fields and macros

`adb build` (inside `adb make-deck`) creates three note types per deck. Their IDs derive
from the deck name, so different decks never collide, and rebuilding the same deck
re-imports cleanly.

| Type | Fields | Front | Back |
|------|--------|-------|------|
| **Basic** (`type: basic`) | Front, Back, Image, Extra, Source, Key | Front | Front, then Back, Image, Extra, footer |
| **Cloze** (`type: cloze`) | Text, Image, Extra, Source, Key | Text with this card's deletion as `[...]` (or `[hint]`) | Text revealed, then Image, Extra, footer |
| **Diagram** (`type: diagram`) | Prompt, Masked, Answer, AnswerImage, Extra, Source, Key | Prompt + masked image | Prompt, **Answer (large)**, labeled image, Extra, footer |

- **Key** holds the card's `key`. It is hidden from the learner, and the review tools
  use it to identify cards.
- **Source** is the footer: `<source label> · <section, or topic label>`.
- **Diagram** cards put the answer at the top of the back, above the full labeled image,
  so it's visible without scrolling on a phone. Repeating the masked image first (as the
  Basic template's FrontSide would) pushed answers below the fold.

## Macros (expanded at build time)

| Macro | Becomes | Use |
|-------|---------|-----|
| `{{img:file.jpg}}` | `<img src="<deck prefix>file.jpg">` | an inline image in any field (front only if masked) |
| `{{chem:C6H12O6}}` | `C<sub>6</sub>H<sub>12</sub>O<sub>6</sub>` | chemical formulas; digits after an element or `)` become subscripts, and leading coefficients stay |
| `{{cN::text}}` / `{{cN::text::hint}}` | Anki cloze deletion | cloze notes only; may contain `{{chem:...}}` |

Plain HTML (`<b>`, `<i>`, `<br>`, `<sub>`, `<sup>`, small `<table>`s) is fine. Avoid
MathJax: HTML subscripts render identically in AnkiMobile, AnkiDroid, AnkiWeb and the
desktop app.

## Provenance labels (from `origin`)

| origin | Label added to Extra (text from `config.toml` `[labels]`) |
|--------|----------------------------------------------------------|
| `source`, `derived` | none |
| `model_answer` | ✎ Model answer: your materials left this blank, so check it against your notes. |
| `model_goal` | ✎ Model answer for a learning goal in your materials. Check it against your notes. |
| `correction` | ⚠ Careful: `<correction text>` |

## Tags

Every note gets the tags `anki_deck_builder`, `<source id>`, `topic::<slug>` and
`origin::<origin>`, plus any `tags` the card lists. Learners can filter in Anki's
browser, or use Custom Study by tag.

## Styling

The CSS is embedded in each note type: large type for phones, centered layout, images
capped at 70% of the viewport height, and a night-mode palette (`.nightMode` and
`.night_mode`, covering both AnkiDroid and AnkiMobile). Change it in
`packages/adb-deck/src/adb_deck/build_deck.py` (`CSS`).

## Stable IDs and re-imports

- Note GUIDs are `guid_for(<deck slug>, key)`, so a note keeps its identity across
  rebuilds.
- Re-importing an updated `.apkg` updates the existing notes and keeps the learner's
  review history.
- Renaming a key makes a new note. The old one stays in their collection until they
  delete it.
- Media files are prefixed with a slug of the deck name, so they never collide with
  other decks' media.
