"""`adb`: the single entry point for every anki-deck-builder tool.

    uv run --frozen --project <skill dir> adb <command> [args...]

Each command is a module exposing a click command or group named `cli`. Modules are
imported lazily, only for the command being run, so light commands (state, subsets)
start without loading the anki/genanki stack.
"""

import importlib

import click

COMMANDS: dict[str, tuple[str, str]] = {
    # phase-agnostic
    "preflight": ("adb_cli.preflight", "check the environment, browser and input folder"),
    "state": ("adb_core.state", "mode dispatch, phase gates, batch tracking, resume"),
    "validate": ("adb_core.validate", "validate run artifacts against their schemas"),
    "subsets": ("adb_core.subsets", "plan worker subsets for extract / synthesize / review"),
    # Organize + Extract
    "organize": ("adb_ingest.organize", "inventory the input folder into page units"),
    "imgtool": ("adb_ingest.imgtool", "grid / view / crop / mask / cover / trim / sheet / flow"),
    # Categorize
    "digest": ("adb_core.digest", "one-row-per-page digest of the transcripts"),
    # Synthesize
    "assemble": ("adb_deck.assemble_cards", "merge per-subset card files into build/cards.json"),
    "lint": ("adb_deck.lint_cards", "mechanical card checks (rules L01-L14)"),
    "build": ("adb_deck.build_deck", "build an .apkg from build/cards.json"),
    "validate-deck": ("adb_deck.validate_deck", "import an .apkg into a fresh collection and check it"),
    "make-deck": ("adb_deck.make_deck", "validate, assemble, lint, build, import-validate"),
    # Refine
    "render": ("adb_review.render_cards", "render every card (question | answer) to review pages"),
    "shoot": ("adb_review.shoot", "screenshot rendered pages with headless Chrome"),
    "refine": ("adb_review.refine", "render / coverage / triage-check / signoff for review rounds"),
    # Complete
    "study-guide": ("adb_deck.study_guide", "render the deck as a printable study guide"),
    "export-transcripts": ("adb_deck.export_transcripts", "page transcriptions as one Markdown file per source"),
    "complete": ("adb_deck.complete", "deliver the signed-off deck and its companions"),
}


class LazyGroup(click.Group):
    """A click group whose subcommands are imported only when used."""

    def __init__(self, *args, lazy: dict[str, tuple[str, str]], **kwargs) -> None:
        """Create the group.

        Args:
            *args: Passed to click.Group.
            lazy: Command name -> (module path, one-line description).
            **kwargs: Passed to click.Group.
        """
        super().__init__(*args, **kwargs)
        self.lazy = lazy

    def list_commands(self, ctx: click.Context) -> list[str]:
        """Command names, in pipeline order.

        Args:
            ctx: The click context.

        Returns:
            The registered command names.
        """
        return list(self.lazy)

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        """Import a command's module and return its `cli`.

        Args:
            ctx: The click context.
            cmd_name: The command name the user typed.

        Returns:
            The command, or None when the name is unknown.
        """
        if cmd_name not in self.lazy:
            return None
        return importlib.import_module(self.lazy[cmd_name][0]).cli

    def format_commands(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        """List commands with their descriptions without importing any module.

        Args:
            ctx: The click context.
            formatter: Where help text is written.
        """
        with formatter.section("Commands"):
            formatter.write_dl([(name, desc) for name, (_module, desc) in self.lazy.items()])


cli = LazyGroup(
    name="adb",
    lazy=COMMANDS,
    help="Tools for the anki-deck-builder Agent skill. Run `adb COMMAND --help` for a command's options.",
)


if __name__ == "__main__":
    cli()
