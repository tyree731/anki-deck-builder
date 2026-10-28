# Phase 6: Complete

Goal: deliver the exact deck that passed Refine, together with its companion files, and
tell the user how to get it onto their device.

`adb ...` means `uv run --quiet --frozen --project "<SKILL_DIR>" adb ...`.

## Steps

**1. Deliver.**

```bash
adb complete "<RUN_DIR>" "<OUTPUT_DIR>"
```

This copies `build/deck.apkg` byte for byte to `<OUTPUT_DIR>/<Deck Root>.apkg`, refusing
if it isn't the signed-off deck, and re-validates the copy by importing it. It also
writes the companions enabled in `config.toml` `[complete]`:
- `Study Guide.html`: the whole deck as a printable page, by source and topic, with the
  corrections listed up top
- `transcriptions/<Source>.md`: page-by-page transcriptions
- `deck-source/`: the cards, deck structure and images, for rebuilding
- `summary.json`: counts per subdeck, provenance counts and review stats

**2. Gate.**

```bash
adb state verify "<RUN_DIR>" complete && adb state advance "<RUN_DIR>" complete
```

**3. Tell the user.** Read `summary.json` and lead with the result. Include:

- **Where the deck is:** the full path to the `.apkg`.
- **Counts:** a small table, one row per subdeck with its card count, plus the total.
- **What's inside,** in a sentence or two: diagram cards with hidden labels, equations,
  where you supplied model answers (✎) and where you corrected the learner's notes (⚠).
- **Review:** "Every card was rendered and looked at, question then answer," with the
  rounds and fix counts. Report it plainly, including any known issues the user accepted.
- **Worth a second look:** the corrections (from `summary.corrections`) and the number of
  model answers. These are the cards a parent or teacher should check against what was
  taught.
- **Getting it onto the device:** the steps from `references/device-import.md` for their
  device if known, otherwise the iPad and Android versions briefly.
- **Pace:** if a test date is known, use the new-cards-per-day advice in
  `references/device-import.md`.
- **Changing cards later:** re-running the skill on the same folder resumes the run, and
  re-importing updates cards in place without losing review history.

Keep it scannable. Don't paste file contents. If this environment can publish shareable
pages and the study guide would be useful to share, offer that in one line.
