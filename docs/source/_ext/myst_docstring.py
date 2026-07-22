"""A directive that renders AutoAPI docstring content as MyST.

AutoAPI generates reST pages and nested-parses each docstring as reST, so MyST
written in a docstring would never be parsed. This directive replaces that nested
parse with a MyST one, letting docstrings use the same markup as the rest of the
documentation while AutoAPI keeps generating the surrounding page.

Napoleon has already rewritten the numpy sections into field lists by this point
(AutoAPI emits `autodoc-process-docstring`), so MyST only needs the `fieldlist`
extension to turn them into Sphinx parameter lists.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from docutils import nodes
from docutils.parsers.rst import roles
from docutils.utils import new_document
from myst_parser.sphinx_ import Parser as MystParser
from sphinx.application import Sphinx
from sphinx.util.docutils import SphinxDirective


@contextmanager
def _parsing_context() -> Iterator[None]:
    """Restore the default role, which a nested parse by another parser resets.

    Yields
    ------
    None
        With the default role captured for restoration.
    """
    blank_role = roles._roles.get("")  # noqa: SLF001
    try:
        yield
    finally:
        if blank_role is not None:
            roles._roles[""] = blank_role  # noqa: SLF001


class MystDocstring(SphinxDirective):
    """Parse the directive's content as MyST and return the resulting nodes."""

    has_content = True

    def run(self) -> list[nodes.Node]:
        """Parse the docstring content with the MyST parser.

        Returns
        -------
        list[nodes.Node]
            The nodes MyST produced, spliced into the surrounding reST page.
        """
        text = "\n".join(self.content)
        if not text.strip():
            return []

        document = new_document(
            self.state.document["source"], self.state.document.settings
        )
        with _parsing_context():
            MystParser().parse(text, document)

        return document.children or []


def setup(app: Sphinx) -> dict[str, object]:
    """Register the MyST docstring directive.

    Parameters
    ----------
    app : Sphinx
        The Sphinx application object.

    Returns
    -------
    dict[str, object]
        Extension metadata.
    """
    app.add_directive("myst-docstring", MystDocstring)
    return {"version": "1.0", "parallel_read_safe": True}
