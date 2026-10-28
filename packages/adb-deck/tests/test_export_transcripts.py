"""Tests for adb_deck/export_transcripts.py."""

from pathlib import Path

from adb_deck import export_transcripts


def test_export_writes_one_file_per_source(run_dir: Path, tmp_path: Path):
    """test_export_writes_one_file_per_source: pages are grouped by source, in page order, with headings demoted."""
    files = export_transcripts.export(run_dir, tmp_path / "out")
    assert [f.name for f in files] == ["Class notes.md", "Review packet.md"]
    packet = files[1].read_text()
    assert packet.startswith("# Review packet: page-by-page transcription")
    assert packet.index("## packet.pdf, page 1") < packet.index("## packet.pdf, page 2") < packet.index("## vocab.txt")
    assert "### Transcription" in packet and "\n## Transcription" not in packet
