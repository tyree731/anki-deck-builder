"""Render the Jinja templates that ship in each package's templates/ folder.

Template files are named <output name>.jinja (e.g. study_guide.html.jinja) so they are
never mistaken for the file they produce. HTML templates autoescape: pass trusted HTML
(card fields, rendered cards) as Markup, and everything else is escaped.
"""

from functools import cache

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape
from markupsafe import Markup

__all__ = ["Markup", "render"]


@cache
def _env(package: str) -> Environment:
    return Environment(
        loader=PackageLoader(package),
        autoescape=select_autoescape(["html.jinja"]),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def render(package: str, name: str, **context) -> str:
    """Render a template from a package's templates/ folder.

    Args:
        package: The package that ships the template, e.g. "adb_deck".
        name: The template file name, e.g. "study_guide.html.jinja".
        **context: The template's variables.

    Returns:
        The rendered text.

    Raises:
        jinja2.UndefinedError: The template uses a variable that was not passed.
    """
    return _env(package).get_template(name).render(**context)
