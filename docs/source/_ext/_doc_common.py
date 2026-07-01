"""Shared helpers for the FABulous custom doc-generator extensions."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sphinx.config import Config


def render_generated_doc(
    conf: Config,
    *,
    template_name: str,
    output_name: str,
    context: dict[str, Any],
) -> Path:
    """Render a Jinja template into ``generated_doc/<output_name>``.

    Parameters
    ----------
    conf : Config
        The Sphinx configuration object (provides the conf.py location and
        ``templates_path``).
    template_name : str
        Filename of the Jinja template under the docs ``_templates`` directory.
    output_name : str
        Filename to write under ``generated_doc/``.
    context : dict[str, Any]
        Variables passed to the template.

    Returns
    -------
    Path
        The path of the file written.
    """
    import jinja2

    doc_root_dir = Path(conf._raw_config["__file__"]).parent  # noqa: SLF001
    templates_path = doc_root_dir / conf.templates_path[0]
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(searchpath=templates_path))

    output = env.get_template(template_name).render(**context)

    output_file = doc_root_dir / "generated_doc" / output_name
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(output)
    return output_file
