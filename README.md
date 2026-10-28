# anki-deck-builder

Turn a folder of study material into a reviewed, importable Anki deck.

An Agent skill. Point it at phone photos of notebooks and handouts, scanned worksheets,
PDFs, Word or PowerPoint files, or plain text, and it produces an `.apkg` ready for
AnkiMobile, AnkiDroid or Anki desktop. Every card is rendered and looked at (question,
then revealed answer) before the deck is delivered.

```
/anki-deck-builder ~/Downloads/biology-notes
```

## What you get

In `anki-output/` inside the folder you pointed it at:

- **`<Deck>.apkg`:** one subdeck per source (for example *1 Class Notes* and *2 Review
  Packet*), with three kinds of card:
  - question and answer
  - fill-in-the-blank
  - diagram cards that hide one label at a time
- **Correct notation and honest provenance:** equations with real subscripts. Model
  answers to blank questions are labeled ✎. Corrections to the learner's own mistakes are
  labeled ⚠.
- **`Study Guide.html`:** the whole deck as one printable page, by source and topic.
- **`transcriptions/`:** a page-by-page transcription of every input.
- **`deck-source/`:** the cards, deck structure and images, for rebuilding.
- **`summary.json`:** counts per subdeck and review statistics.

Rebuilt decks keep stable note IDs, so re-importing updates cards in place without
losing review history.

## Requirements

- [uv](https://docs.astral.sh/uv/), the only tool prerequisite. uv provides Python 3.14+
  and every package.
- Google Chrome or Chromium, used headless to screenshot cards during review. Set
  `ANKI_DECK_BUILDER_CHROME` to use another Chromium-based browser.
- An agent host that supports Agent Skills, can run shell commands, and can start
  subagents for the parallel phases.

## Install

The skill is the repository root (`SKILL.md` lives there). Put it where your agent host
looks for skills, then warm uv's cache:

```bash
git clone <this repo> ~/code/anki-deck-builder

# Claude Code
ln -s ~/code/anki-deck-builder ~/.claude/skills/anki-deck-builder

# Other Agent Skills hosts: use the host's skills folder, e.g. the shared root
mkdir -p ~/.agents/skills && ln -s ~/code/anki-deck-builder ~/.agents/skills/anki-deck-builder

# Resolve and cache every dependency once (the first run otherwise does it)
uv sync --frozen --project ~/code/anki-deck-builder
```

Copying the folder instead of symlinking it works too.

## Usage

Ask in plain language, or invoke the skill by name:

- `/anki-deck-builder ~/Downloads/biology-notes`
- "Make flashcards from the photos in ~/Downloads/chem-unit-3 for my son's test on Friday."
- "Turn these lecture slides and my notes into an Anki deck."

The agent works through the phases with parallel workers. It stops once by default,
after **Categorize**, so you can confirm the deck name, the subdecks and who the deck is
for. If a run is interrupted, invoke the skill on the same folder again and it resumes
where it stopped. On a finished folder it offers to rebuild, improve the cards, or
re-export.

Working files go to a hidden `.anki-build/` inside the folder. Your own files are never
modified.

## How it works

| Phase | What happens |
|-------|--------------|
| **Organize** | Inventory the folder into page units (EXIF rotation, PDF pages, Office text and images), draw contact sheets, plan extraction batches |
| **Extract** | Workers transcribe every page and use vision to cut figures: crops, numbered label masks, clean redraws |
| **Categorize** | Decide the deck name, sources as subdecks, topics and page assignments; you confirm |
| **Synthesize** | Workers write cards under explicit rules; the deck is linted, built and imported into a fresh Anki collection |
| **Refine** | Every card is rendered by Anki's engine, screenshotted and viewed; findings are triaged and fixed, and changed cards are viewed again until a round is clean |
| **Complete** | Deliver the exact signed-off deck and its companion files, with steps for getting it onto the learner's device |

Phase transitions are gated mechanically (`adb state advance` refuses until a phase's
artifacts exist and validate). The review signoff is bound to the deck's exact bytes, so
any later change reopens review. `SKILL.md` is the agent's entry point; `phases/`,
`workers/` and `references/` hold the detailed instructions and rules.

All tools are subcommands of one CLI, `adb`, which the skill runs through uv:

```bash
uv run --quiet --frozen --project ~/.claude/skills/anki-deck-builder adb --help
```

`--project` points uv at the skill without changing the working directory, and uv reads
configuration only from the skill, never from the folder being processed.

## Configuration

`config.toml` at the repository root. Each setting is commented in the file.

| Section | Controls |
|---------|----------|
| `paths` | names of the working (`.anki-build`) and output (`anki-output`) folders |
| `organize` | accepted file types, PDF render DPI, contact sheet grid |
| `extract`, `synthesize` | pages per worker, parallel workers |
| `refine` | cards per reviewer, maximum review rounds, screenshot viewport |
| `checkpoints` | where the agent stops to ask you (default: after Categorize) |
| `labels` | the ✎ / ⚠ provenance text shown on cards |
| `lint` | internal-reference patterns and card length limits |
| `complete` | which companion files to produce |
| `models` | model for each subagent role (unset inherits the orchestrator's) |

## Project structure

A single uv workspace. The root project is virtual and depends on every member; each
member declares only its own dependencies and keeps its tests beside its code.

```
SKILL.md                 agent entry point
CONTRIBUTING.md          conventions and update discipline for changing the skill
phases/                  one instruction file per phase
workers/                 briefs for the extract, author and review subagents
references/              rules, review rubric, artifact contracts, note types, device import
config.toml              runtime configuration
pyproject.toml           workspace root, plus pytest, ruff and pyright config
uv.lock
Makefile
packages/
  adb-core/      state, validate (+ JSON schemas), subsets, digest, templating, common
  adb-ingest/    organize, imgtool
  adb-deck/      assemble, lint, build, validate-deck, make-deck, study guide, complete
  adb-review/    render, shoot, refine
  adb-cli/       the `adb` dispatcher, preflight, end-to-end pipeline test
  adb-testkit/   shared test fixtures and sample data (dev only)
```

Each member has `src/<package>/` and `tests/`.

## Development

```bash
make help        # list every target
make check       # lint + typecheck + test
make test-fast   # unit tests only, while iterating
```

Code and writing conventions, and what has to change together when you change a rule,
schema or artifact, are in [CONTRIBUTING.md](CONTRIBUTING.md).
