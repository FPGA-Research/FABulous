"""Sphinx extension to embed draw.io diagrams directly in the documentation.

The `drawio-figure` directive takes a `.drawio` file and renders it as an ordinary
Sphinx figure, so the diagram source stays the single thing under version control and
nobody has to remember to re-export it by hand.

Every diagram produces two SVGs, one for the light page theme and one for the dark one.
Furo's `only-light` / `only-dark` classes pick between them at read time, honouring both
the theme toggle and the reader's `prefers-color-scheme`. Only the light variant reaches
non-web builders, which have no theme to switch on.

Rendering runs the draw.io CLI, but only when a render is missing or no longer matches
its source. Renders land in a `_drawio_cache` directory next to the diagram, keyed by a
hash of the source, and are committed, so builders without draw.io installed (Read the
Docs, CI) reuse them. A source with no matching render on a machine without draw.io is a
hard error, never a silently stale figure. `scripts/render_drawio.py`, wired up as a
pre-commit hook, keeps those renders in step with the diagrams as they are committed.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from docutils import nodes
from drawio_render import (
    DEFAULT_BORDER,
    DEFAULT_TIMEOUT,
    DrawioError,
    overrides_path,
    render_diagram,
)
from sphinx.directives.patches import Figure
from sphinx.errors import ExtensionError
from sphinx.util import logging

if TYPE_CHECKING:
    from sphinx.application import Sphinx
    from sphinx.environment import BuildEnvironment

logger = logging.getLogger(__name__)


def _srcdir_uri(env: BuildEnvironment, path: Path) -> str:
    """Express a path the way Sphinx wants an image URI.

    Parameters
    ----------
    env : BuildEnvironment
        The build environment, for the source directory.
    path : Path
        An absolute path inside the source directory.

    Returns
    -------
    str
        The path relative to the source directory, marked absolute so that Sphinx
        resolves it against the source directory rather than the current document.
    """
    return "/" + path.relative_to(Path(env.srcdir)).as_posix()


class DrawioFigure(Figure):
    """A figure whose image is a `.drawio` diagram rendered for both page themes."""

    option_spec: ClassVar = Figure.option_spec.copy()

    def run(self) -> list[nodes.Node]:
        """Render the diagram and build the figure around it.

        Returns
        -------
        list[nodes.Node]
            The figure, holding a light and a dark image, or whatever error node the
            underlying figure directive produced.

        Raises
        ------
        ExtensionError
            If the argument does not point at an existing file, or the diagram cannot
            be rendered.
        """
        env = self.state.document.settings.env
        relative_path, absolute_path = env.relfn2path(self.arguments[0])
        source = Path(absolute_path)
        if not source.is_file():
            raise ExtensionError(f"drawio-figure: no such diagram: {source}")
        env.note_dependency(relative_path)
        overrides = overrides_path(source)
        if overrides.is_file():
            env.note_dependency(str(overrides))

        config = env.config
        try:
            renders, rendered = render_diagram(
                source,
                binary_path=config.drawio_binary_path,
                border=config.drawio_border,
                timeout=config.drawio_export_timeout,
            )
        except DrawioError as error:
            raise ExtensionError(str(error)) from error
        if rendered:
            logger.info("[drawio] rendered %s", source.name)

        self.arguments[0] = _srcdir_uri(env, renders["light"])
        built = super().run()

        figure = built[0]
        if not isinstance(figure, nodes.figure):
            return built

        light = figure.children[0]
        light["classes"].append("only-light")
        dark = light.deepcopy()
        dark["uri"] = _srcdir_uri(env, renders["dark"])
        dark["classes"] = [
            "only-dark" if c == "only-light" else c for c in dark["classes"]
        ]
        figure.insert(1, dark)
        return built


def drop_dark_variant(app: Sphinx, doctree: nodes.document, docname: str) -> None:  # noqa: ARG001
    """Strip the dark image from builders that cannot switch themes.

    The dark variant rides on Furo's CSS. Anything that is not a themed web page — LaTeX,
    EPUB, man pages — would simply print both images.

    Parameters
    ----------
    app : Sphinx
        The Sphinx application object.
    doctree : nodes.document
        The resolved doctree.
    docname : str
        Name of the document, unused.
    """
    if app.builder.format == "html" and not app.builder.name.startswith("epub"):
        return
    for image in list(doctree.findall(nodes.image)):
        if "only-dark" in image["classes"]:
            image.parent.remove(image)


def setup(app: Sphinx) -> dict[str, str | bool]:
    """Set up the Sphinx extension.

    Parameters
    ----------
    app : Sphinx
        The Sphinx application object.

    Returns
    -------
    dict[str, str | bool]
        Extension metadata.
    """
    app.add_config_value("drawio_binary_path", None, "env", (str, type(None)))
    app.add_config_value("drawio_border", DEFAULT_BORDER, "env", int)
    app.add_config_value("drawio_export_timeout", DEFAULT_TIMEOUT, "env", int)
    app.add_directive("drawio-figure", DrawioFigure)
    app.connect("doctree-resolved", drop_dark_variant)
    return {"version": "1.0", "parallel_read_safe": True}
