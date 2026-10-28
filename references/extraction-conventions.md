# Extraction conventions

These conventions govern transcripts and figures, for the extract workers. The validator
(`adb validate transcripts` / `figures`) checks structure; you are responsible for
faithfulness.

## Transcript format

```
# <page id>
- File: <source file>[, page N]
- Source guess: <printed study guide | handwritten notebook | glued-in handout | textbook page | slide | ...>
- Orientation: <upright | rotated 90 degrees clockwise to read | mixed: ... >
- Summary: <one line>
- Topics: <comma-separated, plain words>
- Legibility: <good | partial | poor> <+ which parts>

## Transcription
<everything, in reading order>

## Figures
<one line per figure file you made, or "None.">

## Equations
<exactly as shown, or "none">

## Key facts
- <self-contained, test-worthy statements grounded only in this page>

## Flags
<everything the card author must handle, or "none">
```

The first line must be `# <page id>`. The six header bullets and the five `##` headings
are required, in that order. A page with no content says `(blank page)` under
Transcription.

## Marking conventions

| Mark | Meaning |
|------|---------|
| `[illegible]` | can't be read at all |
| `[?word?]` | best guess |
| `[sic: intended]` | obvious misspelling, kept as written |
| `~~text~~` | the learner crossed it out (say whether it was marked wrong) |
| `STUDENT ANSWER: ...` | the learner's handwriting on a printed worksheet or packet |
| `STUDENT ANSWER: (blank)` | an answer space left empty |
| `[faint]`, `[smudged]` | read through difficulty; meaning still certain |

- **Printed vs handwritten:** on worksheets and packets, write the printed text normally
  and prefix the learner's handwriting with `STUDENT ANSWER:`. Never merge them. The
  author must know which words came from the teacher and which from the learner.
- **Tables:** transcribe them as Markdown tables, cell by cell. Note any strikethrough or
  hand-marks on cells.
- **Glued-in handouts:** label them `(glued-in handout)`, and transcribe both the
  printed text and the learner's additions.
- **Sideways writing and two-page spreads:** say how you rotated, then transcribe the
  left page before the right.
- **Ignore:** bleed-through from the reverse side, doodles, hand shadows. If any of them
  hide content, say so under Legibility.

## What belongs in Flags

- The learner's mistakes, each with the correct version (don't correct them in the
  Transcription).
- Blank practice questions, and "know how to" goals with no answer on the page.
- Uncertain readings that would change meaning.
- Content that only makes sense with something not on the page ("the picture shown in
  class").
- Notes the learner marked wrong or crossed out.
- Disagreements with other pages you have seen.
- Questions whose text isn't on the page (a warm-up answer with no prompt).

## Figures

- **Name files** `<page>_<slug>.jpg|png`, with lowercase slugs, all in `media/`.
- **Size:** at most 1400 px on the long side (`config.toml` `extract.crop_max_long_side_px`),
  JPEG quality about 82. `imgtool crop` applies both.
- **Crops:** tight, with a small margin, nothing clipped, upright.
- **Masked versions** (`kind: masked`, with `base` and `mask_map`): one per labeled
  diagram whose labels you can read with confidence. Boxes cover each label's text
  completely, and never the part it points at. Number them in the source's own
  numbering, otherwise in reading order, running 1..n with no gaps. Each `mask_map`
  label is the correct name; if the learner's spelling is wrong, give the correct term
  (the transcript keeps their spelling).
- **No leaks:** in the masked version, cover or trim anything else that names a hidden
  label: titles, captions, the learner's annotations, clipped neighboring text.
- **Redraws** (`kind: redraw`, with `base`): only for important figures the photo can't
  carry. Redraw only what's on the page. `imgtool flow` handles linear processes, and
  its `--boxes-out` output is a ready mask spec.
- **View every image you made** before reporting.
