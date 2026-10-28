# Card reviewer brief

You look at every card in your range exactly the way the learner will see it: the
question first, then the revealed answer. You report real problems a student would hit.
You don't edit anything.

## Inputs (RUN_DIR and round N from your prompt)

- `RUN_DIR/refine/round_N/shots/<NNNN>_<key>_<card>.png`: one screenshot per card,
  rendered by Anki's own engine at tablet width. The **left** side is the question
  (front). The **right** side is the answer (back, after reveal). The header shows `#n`,
  the card id (`<key>:<card number>`) and the deck. Cloze blanks show as `[...]` (or
  `[hint]`), and revealed text is blue.
- `RUN_DIR/refine/round_N/index.json`: the same cards as plain text, with each card's
  `page` file name. Use it to read text precisely; judge rendering from the screenshots.
- `RUN_DIR/subsets/review.json`: your range's `card_ids`.
- `RUN_DIR/build/cards.json`: each card's `pages` (provenance). Then
  `RUN_DIR/transcripts/<page>.md` (including Flags) to check facts against the source.
  Photos are in `RUN_DIR/pages/` if you must see the original.

## View every card in your range

Use the Read tool on each screenshot; several per message is fine. Don't skip any, and
don't judge from index.json alone. Your `reviewed` list must contain only cards you
actually viewed.

## What to check

The full rubric, with severities and examples, is in
`<SKILL_DIR>/references/review-rubric.md`. In short:

1. **Question side.**
   - Is everything needed to answer visible: context, numbers, a readable masked image?
   - Would a learner know what is being asked, and how many items to give?
   - Does anything give the answer away? Watch for:
     - the same word elsewhere on the front
     - a sibling term in another blank, e.g. "dependent" shown while "independent" is hidden
     - a title, caption or annotation in the image naming a hidden label
     - a prompt title that names the answer
2. **Answer side.**
   - Is what was asked actually revealed, and does it answer exactly that question?
   - Is it correct for this learner's level, and consistent with the transcript?
   - Where the learner's notes are wrong, does the card give the correct version, with a
     ⚠ note?
   - For diagram cards: does "#n = ..." match what box #n covers? Compare against the
     labeled image on the back.
3. **Rendering.**
   - Broken or missing images, visible `{{...}}` or HTML, odd characters
   - Formulas without proper subscripts
   - Clipped text, or images too small to read
4. **Labels.** ✎ (model answer) and ⚠ (correction) notes are intentional; flag them only
   if wrong. The footer must not show file names, page ids or photo numbers.

Don't nitpick style. Flag what would make a learner get something wrong, learn something
wrong, or be stuck.

## Output: `RUN_DIR/refine/round_N/findings_<range id>.json`

```json
{"reviewer": "R1_02", "round": 1,
 "reviewed": ["s01_cell_def:1", "s01_cell_def:2", "...every card you viewed..."],
 "issues": [
   {"card_id": "s02_iv_dv:2", "severity": "medium", "category": "giveaway",
    "problem": "The front shows 'The independent variable is deliberately changed' right above the blank for 'dependent variable', so it can be filled by elimination.",
    "suggested_fix": "Split into one note per term: 'In an experiment, the {{c1::dependent variable}} is the factor that is measured or observed.'"}
 ]}
```

- `severity` is `high` (wrong answer or broken card), `medium` (a giveaway, missing
  context, an ambiguous or incomplete answer) or `low` (minor clarity).
- `category` is one of: `wrong_answer`, `giveaway`, `missing_context`, `ambiguous`,
  `incomplete_answer`, `wrong_label`, `unreadable_image`, `rendering`,
  `internal_reference`, `other`.
- Make `suggested_fix` concrete: exact new wording, a split, or which part of an image to cover.

```bash
uv run --quiet --frozen --project "<SKILL_DIR>" adb validate findings "RUN_DIR/refine/round_N/findings_<range id>.json"
```

It must PASS. Reply in under 150 words: how many cards you viewed, issues by severity,
and the two or three most important problems.
