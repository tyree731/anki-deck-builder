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

**3. Offer to put it into Anki on this computer.** This writes into the user's own Anki
collection, and with sync into their AnkiWeb account, so ask in every run; an earlier
run's answer doesn't carry over. First see what this computer has:

```bash
adb deliver check
```

Then ask the user, with your host's question tool if it has one. Offer only the targets
`check` reports as available, and say what each does:

- *Just the file*: nothing more; the `.apkg` is already in the output folder.
- *Open it in Anki*: `adb deliver open "<RUN_DIR>"`. Anki desktop shows its import
  dialog; the user clicks Import there, then Sync if they use AnkiWeb.
- *Import it into Anki*: `adb deliver ankiconnect "<RUN_DIR>" --no-sync`. Needs Anki open
  with the AnkiConnect add-on.
- *Import it and sync to AnkiWeb*: `adb deliver ankiconnect "<RUN_DIR>" --sync`. Their
  phone or tablet then gets the deck on its next sync.

If AnkiConnect isn't available but the user wants it, give the setup steps from
`references/device-import.md` and offer *Open it in Anki* meanwhile. The import checks
that every note arrived. If any is missing it doesn't sync: report the missing keys and
stop. Notes it reports as "not in this build" came from an older version of this deck;
the user can delete them in Anki's browser. If Anki shows a sync dialog (for example,
asking about a full sync), the user answers it there; never try to answer it for them.

**4. Tell the user.** Read `summary.json` and lead with the result. Include:

- **Where the deck is:** the full path to the `.apkg`.
- **Counts:** a small table, one row per subdeck with its card count, plus the total.
- **What's inside,** in a sentence or two: diagram cards with hidden labels, equations,
  where you supplied model answers (✎) and where you corrected the learner's notes (⚠).
- **Review:** "Every card was rendered and looked at, question then answer," with the
  rounds and fix counts. Report it plainly, including any known issues the user accepted.
- **Worth a second look:** the corrections (from `summary.corrections`) and the number of
  model answers. These are the cards a parent or teacher should check against what was
  taught.
- **Getting it onto the device:** what step 3 did (imported, synced, or opened in Anki).
  If it isn't on AnkiWeb yet, the steps from `references/device-import.md` for their
  device if known, otherwise the iPad and Android versions briefly.
- **Pace:** if a test date is known, use the new-cards-per-day advice in
  `references/device-import.md`.
- **Changing cards later:** re-running the skill on the same folder resumes the run, and
  re-importing updates cards in place without losing review history.

Keep it scannable. Don't paste file contents. If this environment can publish shareable
pages and the study guide would be useful to share, offer that in one line.
