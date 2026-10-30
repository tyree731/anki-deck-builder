"""Tests for adb_deck/deliver.py."""

import json
from pathlib import Path

import click
import httpx2
import pytest

from adb_core import wsl
from adb_core.common import sha256_file
from adb_deck import deliver
from adb_testkit import wait_for_file, write_json

KEYS = ["s01_a", "s01_b", "s02_c"]
ALL_NOTES = {1: "s01_a", 2: "s01_b", 3: "s02_c"}
WIN_DECK = "\\\\wsl.localhost\\Ubuntu\\home\\kid\\materials\\anki-output\\Test Deck.apkg"


class FakeAnki:
    """An in-memory AnkiConnect: notes by id, what an import adds, and actions that fail."""

    def __init__(
        self,
        notes: dict[int, str] | None = None,
        adds: dict[int, str] | None = None,
        errors=None,
        media_dir: str = "/home/kid/.local/share/Anki2/User 1/collection.media",
    ):
        self.media_dir = media_dir
        self.notes = dict(notes or {})
        self.adds = dict(adds or {})
        self.errors = errors or {}
        self.calls: list[tuple[str, dict]] = []

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        action, params = body["action"], body["params"]
        self.calls.append((action, params))
        if action in self.errors:
            return httpx2.Response(200, json={"result": None, "error": self.errors[action]})
        if action == "importPackage":
            self.notes.update(self.adds)
        result = {
            "version": 6,
            "findNotes": sorted(self.notes),
            "notesInfo": [
                {"noteId": i, "fields": {"Key": {"value": self.notes.get(i), "order": 5}}}
                for i in params.get("notes", [])
            ],
            "importPackage": True,
            "sync": None,
            "getMediaDirPath": self.media_dir,
        }[action]
        return httpx2.Response(200, json={"result": result, "error": None})

    def client(self) -> deliver.AnkiConnect:
        return deliver.AnkiConnect(
            "http://anki.test", client=httpx2.Client(transport=httpx2.MockTransport(self.handle))
        )

    def actions(self) -> list[str]:
        return [action for action, _ in self.calls]


@pytest.fixture
def completed(run_dir: Path) -> Path:
    """A run whose Complete phase delivered a deck with KEYS (the deck bytes are a stand-in)."""
    write_json(run_dir / "build" / "cards.json", [{"key": k} for k in KEYS])
    (run_dir / "build" / "deck.apkg").write_bytes(b"signed-off deck")
    out = run_dir.parent / "anki-output"
    out.mkdir()
    (out / "Test Deck.apkg").write_bytes(b"signed-off deck")
    write_json(
        out / "summary.json",
        {"deck_root": "Test Deck", "apkg_file": "Test Deck.apkg", "apkg_sha256": sha256_file(out / "Test Deck.apkg")},
    )
    return run_dir


@pytest.fixture
def under_wsl(monkeypatch) -> list[Path]:
    """Run as if under WSL: files handed to Windows are recorded instead of opened; wslpath answers WIN_DECK."""
    handed: list[Path] = []
    monkeypatch.setattr(wsl, "is_wsl", lambda: True)
    monkeypatch.setattr(wsl, "open_on_windows", handed.append)
    monkeypatch.setattr(wsl, "windows_path", lambda path: WIN_DECK)
    return handed


def _deliveries(run_dir: Path) -> list[dict]:
    return json.loads((run_dir.parent / "anki-output" / "summary.json").read_text())["deliveries"]


def test_deck_keys_searches_the_deck_literally():
    """test_deck_keys_searches_the_deck_literally: the deck search treats Anki's wildcards, quotes and backslashes in
    a deck name as literal characters."""
    anki = FakeAnki()
    client = anki.client()
    for name in ("Cells (trial)", 'Q1_*"x"\\'):
        assert client.deck_keys(name) == set()
    assert [params["query"] for _, params in anki.calls] == ['deck:"Cells (trial)"', 'deck:"Q1\\_\\*\\"x\\"\\\\"']


def test_open_in_anki_uses_the_registered_app(completed: Path, monkeypatch):
    """test_open_in_anki_uses_the_registered_app: outside WSL, click.launch opens the deck with the app registered
    for .apkg files, and the delivery is recorded."""
    monkeypatch.setattr(deliver, "find_anki", lambda: "/Applications/Anki.app")
    monkeypatch.setattr(wsl, "is_wsl", lambda: False)
    opened: list[str] = []
    monkeypatch.setattr(click, "launch", lambda url, **kwargs: opened.append(url) or 0)
    record = deliver.open_in_anki(completed)
    assert opened == [str(completed.parent / "anki-output" / "Test Deck.apkg")]
    assert (record["via"], _deliveries(completed)) == ("default app", [record])


def test_open_in_anki_reports_when_nothing_opens_the_deck(completed: Path, monkeypatch):
    """test_open_in_anki_reports_when_nothing_opens_the_deck: a failed launch is an error, and no delivery is
    recorded."""
    monkeypatch.setattr(deliver, "find_anki", lambda: "/usr/bin/anki")
    monkeypatch.setattr(wsl, "is_wsl", lambda: False)
    monkeypatch.setattr(click, "launch", lambda url, **kwargs: 1)
    with pytest.raises(deliver.DeliveryError, match="no app opened"):
        deliver.open_in_anki(completed)
    assert "deliveries" not in json.loads((completed.parent / "anki-output" / "summary.json").read_text())


def test_open_in_anki_needs_anki(completed: Path, monkeypatch):
    """test_open_in_anki_needs_anki: without Anki desktop nothing is opened and nothing is recorded."""
    monkeypatch.setattr(deliver, "find_anki", lambda: None)
    monkeypatch.setattr(click, "launch", lambda *args, **kwargs: pytest.fail("opened without Anki"))
    with pytest.raises(deliver.DeliveryError, match="isn't installed"):
        deliver.open_in_anki(completed)


def test_open_from_wsl_hands_windows_anki_the_deck(completed: Path, under_wsl: list[Path], monkeypatch):
    """test_open_from_wsl_hands_windows_anki_the_deck: under WSL, an Anki installed on Windows gets the deck through
    Windows, not through a Linux app."""
    monkeypatch.setattr(deliver, "find_anki", lambda: "/mnt/c/Users/kid/AppData/Local/Programs/Anki/Anki.exe")
    monkeypatch.setattr(click, "launch", lambda *args, **kwargs: pytest.fail("used a Linux app for Windows Anki"))
    record = deliver.open_in_anki(completed)
    assert under_wsl == [completed.parent / "anki-output" / "Test Deck.apkg"] and record["via"] == "windows"


def test_open_from_wsl_reports_what_windows_said(completed: Path, under_wsl: list[Path], monkeypatch):
    """test_open_from_wsl_reports_what_windows_said: a refusal from Windows becomes a DeliveryError with its message,
    and no delivery is recorded."""

    def refuse(path: Path) -> None:
        raise wsl.WslError(f"Windows couldn't open {path}: not found")

    monkeypatch.setattr(deliver, "find_anki", lambda: "/mnt/c/Program Files/Anki/Anki.exe")
    monkeypatch.setattr(wsl, "open_on_windows", refuse)
    with pytest.raises(deliver.DeliveryError, match="not found"):
        deliver.open_in_anki(completed)
    assert "deliveries" not in json.loads((completed.parent / "anki-output" / "summary.json").read_text())


def test_open_from_wsl_with_anki_inside_wsl_uses_the_linux_app(completed: Path, under_wsl: list[Path], monkeypatch):
    """test_open_from_wsl_with_anki_inside_wsl_uses_the_linux_app: an Anki installed inside WSL gets the deck from
    the Linux app registered for it, even though Windows is reachable."""
    monkeypatch.setattr(deliver, "find_anki", lambda: "/usr/local/bin/anki")
    opened: list[str] = []
    monkeypatch.setattr(click, "launch", lambda url, **kwargs: opened.append(url) or 0)
    assert deliver.open_in_anki(completed)["via"] == "default app"
    assert len(opened) == 1 and under_wsl == []


@pytest.mark.platform("linux", "windows", "wsl")
def test_open_in_anki_reaches_the_registered_app(completed: Path, stand_in_anki: Path, ci_platform: str):
    """test_open_in_anki_reaches_the_registered_app: on a real machine, the deck reaches the app registered for
    .apkg files (CI's stand-in, which records what it was given): directly, or through Windows under WSL."""
    record = deliver.open_in_anki(completed)
    assert "Test Deck.apkg" in wait_for_file(stand_in_anki)
    assert record["via"] == ("windows" if ci_platform == "wsl" else "default app")


def test_import_checks_every_note_then_syncs(completed: Path):
    """test_import_checks_every_note_then_syncs: the absolute deck path is imported, every key is found, then it
    syncs."""
    anki = FakeAnki(adds={1: "s01_a", 2: "s01_b", 3: "s02_c"})
    record = deliver.import_via_ankiconnect(completed, anki.client(), sync=True)
    assert (record["missing"], record["added"], record["synced"]) == ([], 3, True)
    imported = dict(anki.calls)["importPackage"]["path"]
    assert Path(imported).is_absolute() and imported.endswith("Test Deck.apkg")
    assert anki.actions()[-1] == "sync" and _deliveries(completed) == [record]


def test_import_withholds_sync_when_notes_are_missing(completed: Path):
    """test_import_withholds_sync_when_notes_are_missing: an import that lost a note is reported and never synced."""
    anki = FakeAnki(adds={1: "s01_a", 2: "s01_b"})
    record = deliver.import_via_ankiconnect(completed, anki.client(), sync=True)
    assert (record["missing"], record["synced"]) == (["s02_c"], False)
    assert "sync" not in anki.actions()


def test_import_reports_notes_already_there_and_stale_ones(completed: Path):
    """test_import_reports_notes_already_there_and_stale_ones: a re-import counts notes already in Anki, and lists
    notes from an older build that this one no longer has."""
    anki = FakeAnki(notes={1: "s01_a", 9: "s01_old"}, adds={2: "s01_b", 3: "s02_c"})
    record = deliver.import_via_ankiconnect(completed, anki.client())
    assert (record["added"], record["already_there"], record["extra"]) == (2, 1, ["s01_old"])
    assert record["synced"] is False


def test_import_from_wsl_gives_windows_anki_a_windows_path(completed: Path, under_wsl: list[Path]):
    """test_import_from_wsl_gives_windows_anki_a_windows_path: under WSL, an Anki whose media folder is a Windows path
    gets the deck's Windows path; an Anki inside WSL gets the Linux path."""
    windows = FakeAnki(adds=ALL_NOTES, media_dir="C:\\Users\\kid\\AppData\\Roaming\\Anki2\\User 1\\collection.media")
    deliver.import_via_ankiconnect(completed, windows.client())
    assert dict(windows.calls)["importPackage"]["path"] == WIN_DECK
    linux = FakeAnki(adds=ALL_NOTES)
    deliver.import_via_ankiconnect(completed, linux.client())
    assert dict(linux.calls)["importPackage"]["path"] == str(
        (completed.parent / "anki-output" / "Test Deck.apkg").resolve()
    )


def test_ankiconnect_failures_become_delivery_errors():
    """test_ankiconnect_failures_become_delivery_errors: an action error, no listener, and a non-AnkiConnect reply
    each raise DeliveryError with a usable message."""
    with pytest.raises(deliver.DeliveryError, match="collection is not available"):
        FakeAnki(errors={"version": "collection is not available"}).client().version()

    def refuse(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("connection refused", request=request)

    down = deliver.AnkiConnect("http://anki.test", client=httpx2.Client(transport=httpx2.MockTransport(refuse)))
    with pytest.raises(deliver.DeliveryError, match=deliver.ADDON_CODE):
        down.version()
    other = httpx2.Client(transport=httpx2.MockTransport(lambda request: httpx2.Response(200, json=6)))
    with pytest.raises(deliver.DeliveryError, match="did not answer like AnkiConnect"):
        deliver.AnkiConnect("http://anki.test", client=other).version()


def test_delivery_refuses_a_deck_that_changed(completed: Path):
    """test_delivery_refuses_a_deck_that_changed: a delivered file or a build that no longer matches Complete's
    summary is never handed to Anki."""
    delivered = completed.parent / "anki-output" / "Test Deck.apkg"
    delivered.write_bytes(b"edited")
    with pytest.raises(deliver.DeliveryError, match="differs from the deck Complete delivered"):
        deliver.delivered_deck(completed)
    delivered.write_bytes(b"signed-off deck")
    (completed / "build" / "deck.apkg").write_bytes(b"rebuilt")
    with pytest.raises(deliver.DeliveryError, match="rebuilt after Complete"):
        deliver.delivered_deck(completed)
