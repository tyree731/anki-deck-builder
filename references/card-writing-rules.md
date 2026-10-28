# Card-writing rules

Authors follow these when writing cards. The orchestrator uses them when triaging review
findings. Most rules exist because a reviewer found the problem in a real deck: a card
that answered itself, or a prompt a student couldn't act on. The `L..` codes are the
mechanical lint checks (`adb lint`, run inside `adb make-deck`) that enforce what a
script can see.

## Content and honesty

**CW-1. One idea per card.** A list becomes one cloze deletion per item, or separate
notes. A long answer means the question asks too much at once.

**CW-2. Say where content came from** (`origin`). Use `source` for what the materials
state. Use `derived` for direct consequences of them. Use `model_answer` for answers to
questions the materials left blank, and `model_goal` for "know how to" goals with no
answer given. The build labels the last two with ✎. Never pass your own content off as
the learner's notes.

**CW-3. Correct mistakes; never teach them.** If the learner's notes or answers are
wrong, card the correct version with `origin: correction`. Add a `correction` text that
names the mistake kindly: "your packet listed amount of sunlight as a constant, but it's
the independent variable." Don't card notes the learner crossed out. A drawing that is
wrong (heads and tails reversed) can be described correctly in text, but don't use it
as a model.

**CW-4. When sources disagree, card both.** Say which source says what ("Your handout
says *organization*; your packet says *function*"). Don't silently pick one.

**CW-5. Correct at the learner's level.** Keep the classroom's terms and simplifications
unless they are wrong. Add background only where a card would otherwise mislead, and
put it in `extra` marked as background.

## Answerable, and not self-answering

**CW-6. Say how many.** If the answer is a list, the question gives the count ("Name
**the 3** structures...", "Give **4** facts about..."). For a cloze that hides a list, use a
hint: `{{c2::bacteria, viruses, fungi or parasites::4 kinds}}`. *(L08 warns.)*

**CW-7. Everything needed is on the front.** If a card refers to a picture, activity or
handout, either describe it ("About the class picture of a boy in a pond near a fallen
branch: ...") or rewrite the card so it doesn't depend on it. Never ask about "the lab
picture in your notes" if the picture isn't on the card.

**CW-8. Give an instruction.** Don't put a bare term on the front. Write "Define:
**Constants**", "What is...", "Name...". *(L09 warns.)*

**CW-9. No sibling giveaways.** Pairs and contrasts (independent/dependent,
prokaryote/eukaryote, qualitative/quantitative, unicellular/multicellular,
reactants/products) must not appear as separate deletions of one note. Each card would
show the other term, and the blank answers itself by elimination. Use one note per term,
or give both the same deletion number. *(L07 warns.)* Likewise, don't let a step's
neighbors give it away: in an ordered list, blank adjacent steps that name each other
together.

**CW-10. The hidden answer must not appear elsewhere on the front.** For example, hiding
"Vacuole" while the text says "the large central vacuole...". Reword the other occurrence.
*(L06 is an error; render's mechanical check catches what lint can't.)*

**CW-11. Masked images must not leak.** On a diagram card's front, nothing may name a
hidden label: titles and captions ("Cell membrane - model lab"), the learner's
annotations ("10X" beside the eyepiece), clipped text at an edge, or the prompt's own
title ("Prokaryote vs eukaryote" over boxes 1 and 2). Retitle the prompt neutrally
("Cell types T-chart"), and patch the image (`adb imgtool cover` or `trim`).

**CW-12. Ambiguous boxes need a precise prompt.** If two boxes point at the same thing,
ask what each box *stands for* or *is made of*. Example: the bag is "cytoplasm" (what
it models), and the liquid inside it is "cornstarch". A heading with no arrow needs its
own wording ("Box #1 is the heading above the drawing; it gives two names for..."). The
default prompt "What goes in box #n?" only works when each box is a plain label.

## Presentation

**CW-13. Short fronts, focused backs.** Aim for fronts of 60 words or fewer and backs of
120 or fewer (`config.toml` `[lint]`). Extra context goes in `extra`. *(L10 warns.)*

**CW-14. Equations use real subscripts.** Write `{{chem:C6H12O6}}`, or HTML
`<sub>`/`<sup>`. Not MathJax: it doesn't render reliably everywhere and is overkill for
chemistry.

**CW-15. Images.** Labeled figures go on the back (`images`, or `answer_image`). The
front shows only masked figures. *(L11/L12.)*

**CW-16. Nothing internal on the card.** No file names, photo numbers (IMG_...), page ids
(p012), transcript or tool references. The footer is generated as `Source · section or
topic`; make `section` match the card's content. *(L04 is an error.)*

## Lint rules (mechanical)

| Rule | Level | Check |
|------|-------|-------|
| L01 | error | duplicate key |
| L02 | error | type is missing its required fields |
| L03 | error | referenced media file not in `media/` |
| L04 | error | internal reference on a learner-facing field (patterns in `config.toml` `lint.internal_ref_patterns`) |
| L05 | error | unknown `{{...}}` macro, or a cloze note with no deletions |
| L06 | error | a cloze's hidden text appears, as whole words, elsewhere on that card's front |
| L07 | warning | paired terms in different deletions of one note |
| L08 | warning | list answer, but the question gives no count |
| L09 | warning | bare-term front without an instruction |
| L10 | warning | front or back over the word limit |
| L11 | error | diagram `masked` is not a masked figure, or equals `answer_image` |
| L12 | warning | basic front shows a labeled (unmasked) figure |
| L13 | error | an active page is cited by no card (add cards, or `skip_pages` with a reason) |
| L14 | error | unknown source or topic |

An error can be waived only in `build/waivers.json`, with a reason:
`{"waivers": [{"rule": "L13", "key": "p014", "reason": "title page"}]}`. Prefer fixing.
