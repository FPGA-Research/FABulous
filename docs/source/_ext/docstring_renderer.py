"""Jinja filters for the AutoAPI templates.

Docstring *markup* is not translated here: the `myst_docstring` directive parses
docstrings with the MyST parser. These filters only shape the reST page body that
AutoAPI generates around the docstring.
"""

import re
from collections.abc import Iterable
from typing import Protocol


class JinjaEnvironmentLike(Protocol):
    """Protocol for the subset of the Jinja environment used by this module."""

    filters: dict[str, object]


class BaseLike(Protocol):
    """Protocol for AutoAPI base-class descriptors."""

    name: str


# Napoleon rewrites the numpy sections into field lists before AutoAPI renders the
# templates, so a return section reaches this filter as a field. The section form is
# still matched because napoleon leaves a section it does not recognise alone.
RETURN_FIELD_PATTERN = re.compile(r"^:(?:return|returns|rtype):", re.IGNORECASE)
RETURN_SECTION_PATTERN = re.compile(r"^(returns?|return type)\s*$", re.IGNORECASE)


def strip_property_return_sections(docstring: str) -> str:
    """Drop the return sections a property's rendered type already states.

    Callables are deliberately not handled here. Their return type is removed from
    the doctree by `strip_redundant_rtype_fields` in `conf.py`, which also catches
    the one autodoc re-adds from the annotation AutoAPI records -- something a
    filter over the docstring text cannot see.

    Parameters
    ----------
    docstring : str
        The property docstring.

    Returns
    -------
    str
        The docstring without its redundant return sections.
    """
    lines = docstring.splitlines()
    kept: list[str] = []
    index = 0
    skipping = False

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if RETURN_FIELD_PATTERN.match(stripped):
            index += 1
            continue

        underline = lines[index + 1].strip() if index + 1 < len(lines) else ""
        if (
            RETURN_SECTION_PATTERN.match(stripped)
            and underline
            and set(underline) == {"-"}
        ):
            skipping = True
            index += 2
            continue

        if skipping:
            # A blank line closes the section, and is itself part of it.
            skipping = bool(stripped)
            index += 1
            continue

        kept.append(line)
        index += 1

    while kept and not kept[-1].strip():
        kept.pop()

    return "\n".join(kept).strip("\n")


def _short_name(base: str | BaseLike) -> str:
    """Convert an AutoAPI base entry into a concise display name."""
    name = base if isinstance(base, str) else base.name

    return name.rsplit(".", maxsplit=1)[-1].strip()


def _format_base_reference(base: str | BaseLike) -> str:
    """Render a base entry as a class reference when a full name is available."""
    full_name = (base if isinstance(base, str) else base.name).strip()
    short_name = _short_name(base)

    if not full_name or not short_name:
        return ""

    if full_name == short_name:
        return f"``{short_name}``"

    return f":py:class:`{short_name} <{full_name}>`"


def format_inheritance_for_rst(bases: Iterable[str | BaseLike], class_name: str) -> str:
    """Format class inheritance information for display in AutoAPI templates.

    Parameters
    ----------
    bases : Iterable[str | BaseLike]
        The class's base entries, as AutoAPI supplies them.
    class_name : str
        The name of the class being rendered.

    Returns
    -------
    str
        The `Bases:` line, or an empty string when there is nothing worth showing.
    """
    base_references = []
    for base in bases:
        base_name = _short_name(base)
        if not base_name or base_name in {"object", class_name}:
            continue
        base_references.append(_format_base_reference(base))

    if not base_references:
        return ""

    return f"**Bases:** {', '.join(base_references)}"


def prepare_autoapi_jinja_env(jinja_env: JinjaEnvironmentLike) -> None:
    """Register the custom Jinja filters the AutoAPI templates use.

    Parameters
    ----------
    jinja_env : JinjaEnvironmentLike
        The Jinja environment AutoAPI renders its templates with.
    """
    jinja_env.filters["format_inheritance_for_rst"] = format_inheritance_for_rst
    jinja_env.filters["strip_property_return_sections"] = strip_property_return_sections
