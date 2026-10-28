# Phase 5: Refine

Goal: every card is seen the way the learner will see it: the question, then the
revealed answer, rendered by Anki's own engine at tablet width. Problems are fixed, and
fixes are looked at again. The phase ends with a signoff bound to the deck's exact bytes.

`adb ...` means `uv run --quiet --frozen --project "<SKILL_DIR>" adb ...`.
Round files live in `<RUN_DIR>/refine/round_N/`.

## Round 1: every card

**1. Render and screenshot.**

```bash
adb refine render "<RUN_DIR>" --round 1
```

This writes:
- `html/` and `shots/`: one image per card, question on the left, revealed answer on
  the right
- `index.json`: one row per card, with its id `<key>:<card number>`
- `mechanical.json`: what a script can see, such as a hidden answer visible elsewhere
  on the front, or raw markup showing

**2. Plan and dispatch reviewers.**

```bash
adb subsets review "<RUN_DIR>" --round 1
```

This prints `R1_01: cards #1-#62 ...`. Dispatch one review worker per range, in waves of
`refine.max_parallel_reviewers`. Prompt template:

```
You are a card reviewer for the anki-deck-builder skill. Read
<SKILL_DIR>/workers/review_worker.md and follow it exactly.

- SKILL_DIR: <SKILL_DIR>
- RUN_DIR: <RUN_DIR>
- Round: 1, range R1_02, cards #63-#124 (card_ids in <RUN_DIR>/subsets/review.json)
- Write findings to: <RUN_DIR>/refine/round_1/findings_R1_02.json
- Learner: <audience>

Reply in under 150 words: cards viewed, findings by severity, the most important problems.
```

**3. Verify coverage** as findings files arrive:

```bash
adb validate findings "<RUN_DIR>/refine/round_1/findings_R1_02.json"
adb refine coverage "<RUN_DIR>" --round 1
```

Coverage must PASS: every card in the round appears in some reviewer's `reviewed` list.
Re-dispatch any range that comes back short.

**4. Triage every finding,** including the ones in `mechanical.json`. Reviewers can be
wrong, so check each finding against the transcript and your own reading of the card.
Write `triage.json`:

```json
{"round": 1, "decisions": [
  {"finding": "findings_R1_02.json#3", "card_id": "s02_eq:2", "severity": "medium",
   "decision": "fix", "reason": "sibling cloze shows the paired term"},
  {"finding": "mechanical.json#0", "card_id": "s01_terms:2", "severity": "high",
   "decision": "reject", "reason": "'dependent' only appears inside 'independent'"}
]}
```

The decision is `fix`, `reject` (always with a reason) or `defer` (low severity only).
Copy the severity from the finding. Then:

```bash
adb refine triage-check "<RUN_DIR>" --round 1
```

**5. Apply the fixes.**
- **Text changes:** edit the owning card file. `build/card_owners.json` maps each key to
  its file. Splitting a note means deleting the old key and adding the new notes,
  either in the same file or in `cards/fixups.json`.
- **Image giveaways:** patch the media file with `adb imgtool cover`, `trim` or a fresh
  `mask`, then view the result.

The fixes that come up again and again are in `references/review-rubric.md` under
"Common findings". Rebuild:

```bash
adb make-deck "<RUN_DIR>"
```

**6.** If you decided any `fix`, start the next round. Otherwise go to Signoff.

## Round N >= 2: changed cards, by you

**1. Render the changed cards.**

```bash
adb refine render "<RUN_DIR>" --round N
```

`changed.txt` lists the cards whose text or images changed since the last round, which
includes new cards. Only those are screenshotted and packed into
`sheets/changed_NN.jpg`.

**2. View every sheet yourself,** with Read on each `sheets/changed_NN.jpg`. For every
changed card ask:
- Does the front give enough context?
- Does anything on it give the answer away?
- Is the answer right, complete, and does it answer the question asked?
- Are the images right?

Write `personal_review.json` with reviewer `"orchestrator"`, round N, `reviewed` = every
id in `changed.txt`, and `issues` = what you found, using the findings schema. If more
cards changed than `refine.personal_review_limit`, also dispatch reviewers over the
changed set (`adb subsets review "<RUN_DIR>" --round N`), and still look at a spread of
cards yourself.

**3.** Run `adb refine coverage ...`, triage any findings, fix and rebuild exactly as in
round 1. Repeat until a round decides no fixes.

## Signoff

```bash
adb refine signoff "<RUN_DIR>"
```

Signoff refuses in three cases:
- the deck changed after the last round was rendered (run another round)
- some card in the round's review set wasn't viewed
- any finding lacks a decision, or the last round still has `fix` decisions

If fixes keep coming past `refine.max_rounds`, ask the user (AskUserQuestion):
*Another round (Recommended)*, or *Ship now with these known issues* (list them). On
the second answer, use `adb refine signoff "<RUN_DIR>" --accept-known-issues "<what
they approved>"`.

## Gate

```bash
adb state verify "<RUN_DIR>" refine && adb state advance "<RUN_DIR>" refine
```

Progress line: *"Looked at all 309 cards (79 again after fixes); 44 fixes over 3 rounds,
no wrong answers found."*
