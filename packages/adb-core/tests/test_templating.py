"""Tests for adb_core/templating.py."""

from collections.abc import Iterator

import pytest
from jinja2 import UndefinedError

from adb_core.templating import Markup, render

PACKAGE = "adb_templating_fixture"


@pytest.fixture(scope="module")
def package(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    root = tmp_path_factory.mktemp("templating")
    templates = root / PACKAGE / "templates"
    templates.mkdir(parents=True)
    (root / PACKAGE / "__init__.py").write_text("")
    (templates / "page.html.jinja").write_text("<p>{{ text }}</p>{{ trusted }}\n")
    (templates / "notes.txt.jinja").write_text("{{ text }}\n")
    with pytest.MonkeyPatch.context() as mp:
        mp.syspath_prepend(str(root))
        yield PACKAGE


def test_render_escapes_only_html_templates(package: str):
    """test_render_escapes_only_html_templates: .html.jinja output escapes plain strings but not Markup; other
    templates render text as-is."""
    page = render(package, "page.html.jinja", text="<b> & co", trusted=Markup("<i>ok</i>"))
    assert page == "<p>&lt;b&gt; &amp; co</p><i>ok</i>\n"
    assert render(package, "notes.txt.jinja", text="<b> & co") == "<b> & co\n"


def test_render_fails_on_missing_variable(package: str):
    """test_render_fails_on_missing_variable: a variable the caller forgot raises instead of rendering as blank."""
    with pytest.raises(UndefinedError):
        render(package, "page.html.jinja", text="x")
