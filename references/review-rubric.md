# Review rubric

Reviewers use this in the Refine phase, and the orchestrator uses it for triage and for
viewing changed cards.

## What to check on every card

**Question side (front)**
- Everything needed to answer is visible: context, quantities, a readable masked image
  with legible box numbers.
- It's clear what's being asked, including how many items to give.
- Nothing gives the answer away: the hidden words elsewhere on the front, a paired term
  in another blank, a title, caption or annotation in the image naming a hidden label,
  or a prompt heading that is the answer.

**Answer side (back)**
- The hidden or asked-for content is actually revealed.
- It answers exactly the question asked: the right number of items, the right dimension.
  For example, if "what does box 2 stand for" is asked, the answer is the cell part, not
  the lab material.
- It is correct for the learner's level and consistent with the transcript. Where the
  learner's materials are wrong, it gives the correct version with a ⚠ note.
- For diagrams: "#n = ..." matches what box n covers in the masked image.

**Rendering**
- No broken or missing images, visible `{{...}}`, raw HTML, odd characters, clipped text
  or unreadable images.
- Formulas have real subscripts.

**Provenance**
- ✎ appears only on model answers, and ⚠ only on corrections.
- The footer shows the source and topic. No file names, page ids or photo numbers
  appear anywhere.

## Severity

| Severity | Use for |
|----------|---------|
| **high** | wrong answer; teaches a misconception; broken or unreadable card; question unanswerable from the card |
| **medium** | answer given away (sibling, repeated word, image leak); missing context; ambiguous prompt; incomplete answer; box number doesn't match label |
| **low** | minor clarity: a count missing where the answer is short; slightly awkward wording; footer topic mismatch |

## Categories

`wrong_answer`, `giveaway`, `missing_context`, `ambiguous`, `incomplete_answer`,
`wrong_label`, `unreadable_image`, `rendering`, `internal_reference`, `other`.

## Triage (orchestrator)

Every finding gets a decision in `refine/round_N/triage.json`:

- **fix**: the card or image will change. Next round, you personally view it again.
- **reject**: not a real problem. The reason must say why: "false positive: 'dependent'
  only occurs inside 'independent'", or "checked against p014: the answer is correct".
- **defer**: low severity only, accepted as is, with a reason.

Reviewers can be wrong. Check high and medium findings against the transcript, and the
photo if needed, before accepting them.

## Common findings and their fixes

These came up repeatedly in real decks. Fix them on sight.

| Finding | Fix |
|---------|-----|
| Paired terms in one cloze note answer each other | One note per term, or the same deletion number |
| Hidden word repeated in the front text | Reword the repeat ("one large central one") |
| A step's neighbors in an ordered list name it | Blank the adjacent steps together |
| A masked image's title or caption names a box | Cover or trim the title. Retitle the prompt neutrally |
| The learner's annotation next to a box (e.g. "10X") | `imgtool cover` it in the masked version only |
| Clipped neighboring text at an image edge | `imgtool trim` the edge (both versions) |
| Two boxes point at the same thing | Ask what the box *stands for* or *is made of* |
| A heading masked as a box with no arrow | Prompt says "Box #1 is the heading above..." |
| "Describe X" / "Name the structures..." with a list answer | Give the count: "Give 4 facts...", "Name the 3..." |
| Refers to a picture or activity not on the card | Describe it in the prompt, or generalize the question |
| Bare-term front ("Constants") | "Define: Constants" |
| Model-answer note says "left blank" for a learning goal | Use `origin: model_goal` |
| The learner's wrong answer only called "incomplete" | Make it a `correction` that says what was wrong |
| Notes' errors taught as fact (e.g. "only animals respire") | Correct it, with a ⚠ note |
| Footer topic doesn't match the card | Set `section` or the right `topic` |
