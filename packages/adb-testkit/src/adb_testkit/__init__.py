"""adb-testkit: shared test support for every anki-deck-builder workspace member.

Fixtures live in `adb_testkit.plugin`, loaded by the root pyproject's pytest `addopts`
(`-p adb_testkit.plugin`). Helpers and sample data are re-exported here.
"""

from adb_core.common import SKILL_ROOT, write_json
from adb_testkit.cli import invoke, run_adb
from adb_testkit.images import page_image
from adb_testkit.runs import make_run_dir
from adb_testkit.samples import CATEGORIES, GOOD_HEADER, NOTES_CARDS, PACKET_CARDS, TRANSCRIPT

__all__ = [
    "CATEGORIES",
    "GOOD_HEADER",
    "NOTES_CARDS",
    "PACKET_CARDS",
    "SKILL_ROOT",
    "TRANSCRIPT",
    "invoke",
    "make_run_dir",
    "page_image",
    "run_adb",
    "write_json",
]
