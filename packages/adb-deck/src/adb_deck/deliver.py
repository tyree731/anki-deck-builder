"""Put the finished deck into Anki on this computer, in addition to the .apkg in the output folder.

Two optional targets, used only after Complete and only with the user's go-ahead:

  open         open the .apkg with the app registered for it (Anki desktop), which shows its
               own import dialog; under WSL, with that app on Windows
  ankiconnect  import it through the AnkiConnect add-on while Anki is open, check that every
               note arrived, and optionally sync to AnkiWeb

AnkiWeb itself can't import a deck; a deck reaches it by syncing from an Anki app. Each
delivery is recorded in the output folder's summary.json under "deliveries".
"""

import re
import sys
from datetime import date
from pathlib import Path
from typing import Any, NoReturn

import click
import httpx2

from adb_core import wsl
from adb_core.common import (
    EXIT_FAIL,
    find_anki,
    load_config,
    read_json,
    run_paths,
    sha256_file,
    write_json,
)
from adb_core.state import load_state, now
from adb_deck import study_plan

ADDON_CODE = "2055492159"


class DeliveryError(Exception):
    """The deck can't be delivered: Complete hasn't run, the deck changed, or Anki isn't reachable."""


class AnkiConnect:
    """A small client for the AnkiConnect add-on, one method per operation.

    Every method raises DeliveryError when AnkiConnect is unreachable, answers like
    something else, or reports an error.
    """

    def __init__(self, url: str, client: httpx2.Client | None = None):
        self._url = url
        self._client = client or httpx2.Client(timeout=120.0)
        self._on_windows: bool | None = None

    @property
    def url(self) -> str:
        """AnkiConnect's address."""
        return self._url

    def version(self) -> int:
        """The AnkiConnect API version.

        Returns:
            The version number (6 for current releases).
        """
        return self._call("version")

    def import_package(self, apkg: Path) -> None:
        """Import a deck with Anki's importer, which updates notes whose packaged copy is newer.

        Under WSL, an Anki running on Windows is given the deck's Windows path.

        Args:
            apkg: The deck file.
        """
        try:
            path = wsl.windows_path(apkg) if wsl.is_wsl() and self._anki_on_windows() else str(apkg.resolve())
        except wsl.WslError as exc:
            raise DeliveryError(str(exc)) from exc
        self._call("importPackage", path=path)

    def sync(self) -> None:
        """Sync the open profile with AnkiWeb, using the login Anki already has."""
        self._call("sync")

    def deck_config(self, deck: str) -> dict:
        """The options preset a deck uses.

        Args:
            deck: The deck's full name.

        Returns:
            The preset, as AnkiConnect's dictionary (id, name, new.perDay, newGatherPriority, ...).
        """
        config = self._call("getDeckConfig", deck=deck)
        if not config:
            raise DeliveryError(f"AnkiConnect found no deck named {deck!r}")
        return config

    def clone_deck_config(self, name: str, clone_from: int) -> int:
        """Create an options preset as a copy of another.

        Args:
            name: The new preset's name.
            clone_from: The id of the preset to copy.

        Returns:
            The new preset's id.
        """
        preset = self._call("cloneDeckConfigId", name=name, cloneFrom=clone_from)
        if not preset:
            raise DeliveryError(f"AnkiConnect couldn't create the options preset {name!r}")
        return int(preset)

    def save_deck_config(self, config: dict) -> None:
        """Save changes to an options preset.

        Args:
            config: The preset, as returned by `deck_config()` and then edited.
        """
        if not self._call("saveDeckConfig", config=config):
            raise DeliveryError(f"AnkiConnect couldn't save the options preset {config.get('name')!r}")

    def set_deck_config(self, decks: list[str], config_id: int) -> None:
        """Make decks use an options preset.

        Args:
            decks: Full deck names.
            config_id: The preset's id.
        """
        if not self._call("setDeckConfigId", decks=decks, configId=config_id):
            raise DeliveryError(f"AnkiConnect couldn't assign options preset {config_id} to {decks}")

    def deck_keys(self, deck_root: str) -> set[str]:
        """The card keys of every note in a deck and its subdecks.

        Args:
            deck_root: The deck's root name.

        Returns:
            The notes' Key field values.
        """
        ids = self._call("findNotes", query=_deck_query(deck_root))
        if not ids:
            return set()
        notes = self._call("notesInfo", notes=ids)
        return {n["fields"]["Key"]["value"] for n in notes if "Key" in n.get("fields", {})}

    def _anki_on_windows(self) -> bool:
        if self._on_windows is None:
            media = str(self._call("getMediaDirPath"))
            self._on_windows = re.match(r"[A-Za-z]:[\\/]|\\\\", media) is not None
        return self._on_windows

    def _call(self, action: str, **params: Any) -> Any:
        try:
            response = self._client.post(self._url, json={"action": action, "version": 6, "params": params})
            response.raise_for_status()
            body = response.json()
        except httpx2.TransportError as exc:
            hint = f"open Anki, with the AnkiConnect add-on ({ADDON_CODE}) installed"
            if wsl.is_wsl():
                hint += "; from WSL2, Anki on Windows is at 127.0.0.1 only with networkingMode=mirrored in .wslconfig"
            raise DeliveryError(f"can't reach AnkiConnect at {self._url}: {hint}") from exc
        except (httpx2.HTTPStatusError, ValueError) as exc:
            raise DeliveryError(f"unexpected reply from {self._url}: {exc}") from exc
        if not isinstance(body, dict) or "result" not in body:
            raise DeliveryError(f"{self._url} did not answer like AnkiConnect")
        if body.get("error"):
            raise DeliveryError(f"AnkiConnect {action}: {body['error']}")
        return body["result"]


def _deck_query(deck_root: str) -> str:
    # a deck and its subdecks, with Anki's search wildcards (* and _), quotes and backslashes literal.
    return 'deck:"' + re.sub(r'([\\"*_])', r"\\\1", deck_root) + '"'


def delivered_deck(run_dir: Path) -> tuple[Path, dict]:
    """The deck Complete delivered, checked against the signed-off build.

    Args:
        run_dir: The run directory.

    Returns:
        (the .apkg in the output folder, the output folder's summary.json)

    Raises:
        DeliveryError: Complete hasn't run, or the .apkg or the build changed since.
    """
    out = Path(load_state(run_dir)["output_dir"])
    if not (out / "summary.json").exists():
        raise DeliveryError(f"no summary.json in {out}: run `adb complete` first")
    summary = read_json(out / "summary.json")
    apkg = out / summary["apkg_file"]
    if not apkg.exists() or sha256_file(apkg) != summary["apkg_sha256"]:
        raise DeliveryError(f"{apkg} is missing or differs from the deck Complete delivered: run `adb complete` again")
    built = run_paths(run_dir)["build"] / "deck.apkg"
    if not built.exists() or sha256_file(built) != summary["apkg_sha256"]:
        raise DeliveryError("the deck was rebuilt after Complete: finish Refine and Complete again first")
    return apkg, summary


def _record(out_dir: Path, record: dict) -> dict:
    path = out_dir / "summary.json"
    summary = read_json(path)
    summary.setdefault("deliveries", []).append(record)
    write_json(path, summary)
    return record


def _on_windows(app: str) -> bool:
    # under WSL, an Anki found on a Windows drive runs on Windows; one found in Linux runs in WSL.
    return app.lower().endswith(".exe") or Path(app).is_relative_to(wsl.mount_root())


def _open_file(path: Path, app: str) -> str:
    # an Anki installed on Windows, seen from WSL, gets the file through Windows. everything else
    # (macOS, Windows, Linux, Anki inside WSL) uses click.launch: the app registered for .apkg.
    if wsl.is_wsl() and _on_windows(app):
        try:
            wsl.open_on_windows(path)
        except wsl.WslError as exc:
            raise DeliveryError(str(exc)) from exc
        return "windows"
    if click.launch(str(path)) != 0:
        raise DeliveryError(f"no app opened {path}: check that .apkg files open with Anki")
    return "default app"


def open_in_anki(run_dir: Path) -> dict:
    """Open the delivered deck in Anki desktop, which asks the user to confirm the import.

    The deck opens with the app registered for .apkg files. Under WSL, an Anki installed on
    Windows gets it through Windows; an Anki installed inside WSL gets it directly.

    Args:
        run_dir: The run directory.

    Returns:
        The delivery record added to summary.json.

    Raises:
        DeliveryError: The deck isn't the delivered one, Anki desktop isn't installed, or nothing opened the deck.
    """
    apkg, _ = delivered_deck(run_dir)
    app = find_anki()
    if app is None:
        raise DeliveryError(
            "Anki desktop isn't installed (apps.ankiweb.net); set ANKI_DECK_BUILDER_ANKI if it's somewhere unusual"
        )
    via = _open_file(apkg, app)
    return _record(apkg.parent, {"target": "open", "at": now(), "app": app, "via": via})


_LOWEST_POSITION = 1  # Anki's "new card gather order: ascending position"


def _pace(anki: AnkiConnect, decks: list[str], new_per_day: int) -> dict:
    # a preset of the deck's own, copied from the one it uses now and named after it, so the
    # learner's other decks keep their options. new cards are gathered by position, which the
    # build sets core first.
    root = decks[0]
    current = anki.deck_config(root)
    if current["name"] != root:
        anki.set_deck_config(decks, anki.clone_deck_config(root, current["id"]))
        current = anki.deck_config(root)
    else:
        anki.set_deck_config(decks, current["id"])
    current["new"]["perDay"] = new_per_day
    current["newGatherPriority"] = _LOWEST_POSITION
    anki.save_deck_config(current)
    return {"preset": root, "new_per_day": new_per_day}


def _deck_names(summary: dict) -> list[str]:
    # the deck root first, then its subdecks
    root = summary["deck_root"]
    return [root, *sorted(d for d in summary.get("decks", {}) if d != root)]


def pace_deck(run_dir: Path, anki: AnkiConnect, new_per_day: int | None = None, test_date: date | None = None) -> dict:
    """Set the delivered deck's new cards a day in Anki, on the deck's own options preset.

    Args:
        run_dir: The run directory.
        anki: The AnkiConnect client.
        new_per_day: An exact number of new cards a day; without it, the study plan's,
            recomputed for today.
        test_date: Plan for this test date instead of the one the deck was built with.

    Returns:
        The record added to summary.json: the preset, the new cards a day, and the plan
        they came from (None for an exact number).

    Raises:
        DeliveryError: The deck isn't the delivered one or isn't in Anki, there's no test
            date and no number, the test is today or past, or AnkiConnect failed.
    """
    apkg, summary = delivered_deck(run_dir)
    plan = None
    if new_per_day is None:
        stored = summary.get("study_plan")
        when = test_date or (date.fromisoformat(stored["test_date"]) if stored else None)
        if when is None:
            raise DeliveryError("the deck has no test date: pass --test-date to plan for one, or --new-per-day")
        if stored:
            cards, core = stored["cards"], stored["core_cards"]
        else:
            cards, core = study_plan.deck_counts(read_json(run_paths(run_dir)["build"] / "cards.json"))
        plan = study_plan.plan(when, date.today(), cards, core)
        new_per_day = plan["new_per_day"]
        if not new_per_day:
            raise DeliveryError(f"the test date {plan['test_date']} is today or past: pass --new-per-day instead")
    paced = _pace(anki, _deck_names(summary), new_per_day)
    return _record(apkg.parent, {"target": "pace", "at": now(), "url": anki.url, **paced, "plan": plan})


def import_via_ankiconnect(run_dir: Path, anki: AnkiConnect, sync: bool = False, pace: bool = True) -> dict:
    """Import the delivered deck through AnkiConnect, check every note arrived, then pace and sync it.

    Args:
        run_dir: The run directory.
        anki: The AnkiConnect client.
        sync: Sync to AnkiWeb afterwards, if every note arrived.
        pace: With a test date, give the deck its own options preset with the study plan's new
            cards a day, recomputed for today, and core cards first.

    Returns:
        The delivery record added to summary.json: notes expected, added and already there,
        `missing` and `extra` card keys, the pacing applied (or None), and whether it synced.

    Raises:
        DeliveryError: The deck isn't the delivered one, or AnkiConnect failed.
    """
    apkg, summary = delivered_deck(run_dir)
    expected = {c["key"] for c in read_json(run_paths(run_dir)["build"] / "cards.json")}
    before = anki.deck_keys(summary["deck_root"])
    anki.import_package(apkg)
    after = anki.deck_keys(summary["deck_root"])
    missing = sorted(expected - after)
    paced = None
    if pace and not missing and (plan := summary.get("study_plan")):
        today = study_plan.plan(date.fromisoformat(plan["test_date"]), date.today(), plan["cards"], plan["core_cards"])
        if today["new_per_day"]:
            paced = _pace(anki, _deck_names(summary), today["new_per_day"]) | {"all_seen_by": today["all_seen_by"]}
    synced = sync and not missing
    if synced:
        anki.sync()
    return _record(
        apkg.parent,
        {
            "target": "ankiconnect",
            "at": now(),
            "url": anki.url,
            "notes": len(expected),
            "added": len(expected & (after - before)),
            "already_there": len(expected & before),
            "missing": missing,
            "extra": sorted(after - expected),
            "paced": paced,
            "synced": synced,
        },
    )


def _fail(exc: Exception) -> NoReturn:
    click.echo(str(exc), err=True)
    sys.exit(EXIT_FAIL)


RUN_DIR = click.Path(exists=True, file_okay=False, path_type=Path)
URL = click.option(
    "--url",
    default=lambda: load_config()["deliver"]["ankiconnect_url"],
    show_default="config.toml [deliver] ankiconnect_url",
    help="AnkiConnect's address.",
)


@click.group(name="deliver")
def cli() -> None:
    """Put the finished deck into Anki on this computer (after Complete, with the user's go-ahead)."""


@cli.command()
@URL
def check(url: str) -> None:
    """Show which delivery targets are available on this computer."""
    app = find_anki()
    click.echo(f"open:        {f'available ({app})' if app else 'unavailable: Anki desktop not found'}")
    try:
        click.echo(f"ankiconnect: available (API version {AnkiConnect(url).version()}) at {url}")
    except DeliveryError as exc:
        click.echo(f"ankiconnect: unavailable: {exc}")


@cli.command("open")
@click.argument("run_dir", type=RUN_DIR)
def open_cmd(run_dir: Path) -> None:
    """Hand the deck to Anki desktop, which shows its import dialog."""
    try:
        record = open_in_anki(run_dir)
    except DeliveryError as exc:
        _fail(exc)
    click.echo(f"opened in Anki ({record['app']}); the user confirms the import there")


@cli.command("ankiconnect")
@click.argument("run_dir", type=RUN_DIR)
@click.option("--sync/--no-sync", default=None, help="Sync to AnkiWeb after a complete import. [default: config.toml]")
@click.option(
    "--pace/--no-pace",
    default=None,
    help="Apply the study plan's new cards a day, if there's a test date. [default: config.toml]",
)
@URL
def ankiconnect_cmd(run_dir: Path, sync: bool | None, pace: bool | None, url: str) -> None:
    """Import the deck through AnkiConnect, check that every note arrived, pace it and optionally sync to AnkiWeb."""
    cfg = load_config()["deliver"]
    sync = bool(cfg["sync_after_import"]) if sync is None else sync
    pace = bool(cfg["apply_study_plan"]) if pace is None else pace
    try:
        record = import_via_ankiconnect(run_dir, AnkiConnect(url), sync=sync, pace=pace)
    except DeliveryError as exc:
        _fail(exc)
    click.echo(
        f"imported: {record['notes']} note(s); {record['added']} added, {record['already_there']} already in Anki"
    )
    if record["extra"]:
        click.echo(
            f"note: {len(record['extra'])} note(s) in Anki's copy of this deck aren't in this build "
            f"(removed in a rebuild): {', '.join(record['extra'][:10])}"
        )
    if record["missing"]:
        click.echo(f"MISSING {len(record['missing'])} note(s), so not synced: {', '.join(record['missing'][:10])}")
        sys.exit(EXIT_FAIL)
    if record["paced"]:
        click.echo(
            f"paced: {record['paced']['new_per_day']} new card(s) a day, core first, in options preset "
            f"{record['paced']['preset']!r}; every card seen by {record['paced']['all_seen_by']}"
        )
    click.echo("synced to AnkiWeb" if record["synced"] else "not synced (pass --sync to sync to AnkiWeb)")


@cli.command("pace")
@click.argument("run_dir", type=RUN_DIR)
@click.option("--new-per-day", type=click.IntRange(min=1), help="An exact number of new cards a day.")
@click.option(
    "--test-date", type=click.DateTime(formats=["%Y-%m-%d"]), help="Plan for this test date (YYYY-MM-DD) instead."
)
@click.option("--sync", is_flag=True, help="Sync to AnkiWeb afterwards, so other devices get the new pace.")
@URL
def pace_cmd(run_dir: Path, new_per_day: int | None, test_date, sync: bool, url: str) -> None:
    """Set the deck's new cards a day in Anki: the study plan's for today, or an exact number."""
    if new_per_day and test_date:
        raise click.UsageError("pass --new-per-day or --test-date, not both")
    anki = AnkiConnect(url)
    try:
        record = pace_deck(run_dir, anki, new_per_day, test_date.date() if test_date else None)
        if sync:
            anki.sync()
    except DeliveryError as exc:
        _fail(exc)
    click.echo(f"paced: {record['new_per_day']} new card(s) a day, core first, in options preset {record['preset']!r}")
    if plan := record["plan"]:
        click.echo(
            f"plan: test {plan['test_date']} in {plan['days_left']} day(s); every card seen by {plan['all_seen_by']}, "
            f"reviews only from {plan['reviews_from']}"
        )
        if not plan["fits"]:
            click.echo(f"not every card fits before the test; core cards are seen by {plan['core_seen_by']}")
    click.echo("synced to AnkiWeb" if sync else "not synced (pass --sync, or run `adb deliver sync`)")


@cli.command("sync")
@URL
def sync_cmd(url: str) -> None:
    """Sync this computer's Anki with AnkiWeb through AnkiConnect, using the login Anki already has."""
    try:
        AnkiConnect(url).sync()
    except DeliveryError as exc:
        _fail(exc)
    click.echo("synced to AnkiWeb")


if __name__ == "__main__":
    cli()
