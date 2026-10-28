# Contributing

How to work on anki-deck-builder itself: setup, the conventions the code and docs follow,
and what has to change together. For what the skill does and how to use it, see
[README.md](README.md).

## Setup

You need [uv](https://docs.astral.sh/uv/). The end-to-end and screenshot tests also need
Google Chrome or Chromium.

```bash
uv sync --frozen
make check       # ruff, pyright and every test; must pass before a change is done
make test-fast   # skips the browser and integration tests while iterating
```

## Code conventions

- **Python 3.14+.** uv resolves only releases at least 3 days old (`exclude-newer`).
  Don't use `from __future__ import annotations`: 3.14 already evaluates annotations
  lazily, and ruff rejects the import.
- **All tool config** (pytest, ruff, pyright) lives in the root `pyproject.toml`. Don't add
  `pytest.ini`, `ruff.toml` or `pyrightconfig.json`.
- **Workspace members** live in `packages/<member>/` with `src/<package>/` and `tests/`. The
  root `pyproject.toml` is the workspace and depends on every member.
- **Tests** live in `packages/<member>/tests/test_<module>.py`. Every test's docstring
  starts with `<test name>: <description>`, and collection fails otherwise.
- **Shared fixtures** (`corpus`, `run_dir`, `built_run_dir`) come from `adb-testkit`,
  loaded with `-p adb_testkit.plugin`. Its `__init__.py` only re-exports.
- **Shared functions** document parameters, return values and exceptions in Google-style
  `Args:` / `Returns:` / `Raises:` sections. Ruff's `D417` enforces complete `Args:`.
- **CLIs** are click commands that wrap typed functions. Keep logic out of the command
  bodies. Tests cover the functions, not exit codes or printed output. A CLI test is worth
  writing only when it covers something the functions can't, like a file one command
  writes for another to read.
- **Generated files come from Jinja templates** in a package's `templates/` folder, rendered
  with `adb_core.templating.render`. Name a template for what it produces plus `.jinja`
  (`study_guide.html.jinja`). HTML templates autoescape, so pass trusted HTML such as card
  fields as `Markup`.

## Writing conventions

These apply to SKILL.md, the phase and worker files, the references, and code comments.

- Call it an "Agent skill". Keep instructions agent-neutral, not tied to one agent host.
- No em dashes. Use non-ASCII characters only when they are part of real input or output,
  such as the ✎ and ⚠ card labels in `config.toml`.

## Update discipline

- **Change a rule:** update the reference file, the code that enforces it (lint rule,
  validator, schema) and its tests in the same change. Rule IDs (CW-n, L0n) are the links:
  search for them.
- **Change an artifact's shape:** update its schema, the producer and consumer code, the
  `adb-testkit` sample data, and `references/artifacts.md` together.
- **Change a command's arguments:** update every example of it in SKILL.md, `phases/`,
  `workers/` and `references/`. The agent runs those examples as written.
- **Add a learned failure mode:** add it to `references/review-rubric.md` "Common
  findings". Then ask whether a lint rule (`adb_deck/lint_cards.py`) or a mechanical render
  check (`adb_review/render_cards.py`) could catch it. Catching it earlier saves a review
  round.
