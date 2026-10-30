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
    # A deck and its subdecks, with Anki's search wildcards (* and _), quotes and backslashes literal.
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
    # Under WSL, an Anki found on a Windows drive runs on Windows; one found in Linux runs in WSL.
    return app.lower().endswith(".exe") or Path(app).is_relative_to(wsl.mount_root())


def _open_file(path: Path, app: str) -> str:
    # An Anki installed on Windows, seen from WSL, gets the file through Windows. Everything else
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


def import_via_ankiconnect(run_dir: Path, anki: AnkiConnect, sync: bool = False) -> dict:
    """Import the delivered deck through AnkiConnect, check every note arrived, then optionally sync.

    Args:
        run_dir: The run directory.
        anki: The AnkiConnect client.
        sync: Sync to AnkiWeb afterwards, if every note arrived.

    Returns:
        The delivery record added to summary.json: notes expected, added and already there,
        `missing` and `extra` card keys, and whether it synced.

    Raises:
        DeliveryError: The deck isn't the delivered one, or AnkiConnect failed.
    """
    apkg, summary = delivered_deck(run_dir)
    expected = {c["key"] for c in read_json(run_paths(run_dir)["build"] / "cards.json")}
    before = anki.deck_keys(summary["deck_root"])
    anki.import_package(apkg)
    after = anki.deck_keys(summary["deck_root"])
    missing = sorted(expected - after)
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
@URL
def ankiconnect_cmd(run_dir: Path, sync: bool | None, url: str) -> None:
    """Import the deck through AnkiConnect, check that every note arrived, and optionally sync to AnkiWeb."""
    if sync is None:
        sync = bool(load_config()["deliver"]["sync_after_import"])
    try:
        record = import_via_ankiconnect(run_dir, AnkiConnect(url), sync=sync)
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
    click.echo("synced to AnkiWeb" if record["synced"] else "not synced (pass --sync to sync to AnkiWeb)")


if __name__ == "__main__":
    cli()
