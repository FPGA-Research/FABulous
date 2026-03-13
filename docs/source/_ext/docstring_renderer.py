"""Helpers for rendering markdown-leaning docstrings through AutoAPI."""

from __future__ import annotations

import re
from types import UnionType
from typing import TYPE_CHECKING, Annotated, Protocol, Union, get_args, get_origin

if TYPE_CHECKING:
    from collections.abc import Iterable


class JinjaEnvironmentLike(Protocol):
    """Protocol for the subset of the Jinja environment used by this module."""

    filters: dict[str, object]


class BaseLike(Protocol):
    """Protocol for AutoAPI base-class descriptors."""

    name: str


INLINE_CODE_PATTERN = re.compile(r"(?<!`)`([^`\n]+)`(?!`)")
LIST_ITEM_PATTERN = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+")
FENCE_PATTERN = re.compile(r"^(\s*)```([\w+-]*)\s*$")
CODE_BLOCK_LANGUAGE_MAP = {
    "py": "python",
    "python": "python",
    "sv": "systemverilog",
    "systemverilog": "systemverilog",
    "verilog": "verilog",
    "vhdl": "vhdl",
    "sh": "shell",
    "bash": "shell",
    "shell": "shell",
}
PROPERTY_RETURN_FIELD_PATTERN = re.compile(
    r"^:(?:return|returns|rtype):", re.IGNORECASE
)
PROPERTY_RETURN_SECTION_PATTERN = re.compile(
    r"^(returns?|return type)\s*$", re.IGNORECASE
)
CALLABLE_RTYPE_FIELD_PATTERN = re.compile(r"^:rtype:", re.IGNORECASE)
CALLABLE_RETURN_TYPE_SECTION_PATTERN = re.compile(r"^return type\s*$", re.IGNORECASE)


def _convert_inline_markdown_code(line: str) -> str:
    """Convert single-backtick markdown spans into reST inline literals."""
    return INLINE_CODE_PATTERN.sub(r"``\1``", line)


def _convert_fenced_code_blocks(lines: Iterable[str]) -> list[str]:
    """Convert markdown fenced code blocks into reST code blocks."""
    converted: list[str] = []
    in_fence = False
    code_indent = ""

    for line in lines:
        fence_match = FENCE_PATTERN.match(line)
        if fence_match:
            indent, raw_language = fence_match.groups()
            if not in_fence:
                language = CODE_BLOCK_LANGUAGE_MAP.get(
                    raw_language.lower(), raw_language
                )
                directive = f".. code-block:: {language}" if language else "::"
                converted.append(f"{indent}{directive}")
                converted.append("")
                code_indent = indent + "   "
                in_fence = True
            else:
                in_fence = False
                code_indent = ""
            continue

        if in_fence:
            converted.append(f"{code_indent}{line.lstrip()}")
            continue

        converted.append(_convert_inline_markdown_code(line))

    return converted


def _insert_blank_lines_around_lists(lines: Iterable[str]) -> list[str]:
    """Ensure markdown-style lists become valid reST lists inside docstrings."""
    normalized: list[str] = []
    in_list = False
    list_indent = 0

    for line in lines:
        list_match = LIST_ITEM_PATTERN.match(line)
        if list_match:
            if normalized and normalized[-1].strip() and not in_list:
                normalized.append("")
            normalized.append(line)
            in_list = True
            list_indent = len(list_match.group(1))
            continue

        if in_list:
            if not line.strip():
                normalized.append(line)
                continue

            current_indent = len(line) - len(line.lstrip(" "))
            if current_indent > list_indent:
                normalized.append(line)
                continue

            if normalized and normalized[-1].strip():
                normalized.append("")
            in_list = False

        normalized.append(line)

    return normalized


def _strip_property_return_sections(lines: Iterable[str]) -> list[str]:
    """Remove redundant return sections from property docstrings."""
    normalized: list[str] = []
    skip_section = False

    line_list = list(lines)
    index = 0
    while index < len(line_list):
        line = line_list[index]
        stripped = line.strip()

        if PROPERTY_RETURN_FIELD_PATTERN.match(stripped):
            index += 1
            continue

        if PROPERTY_RETURN_SECTION_PATTERN.match(stripped):
            next_index = index + 1
            if next_index < len(line_list):
                underline = line_list[next_index].strip()
                if underline and set(underline) == {"-"}:
                    skip_section = True
                    index += 2
                    continue

        if skip_section:
            if not stripped:
                skip_section = False
            index += 1
            continue

        normalized.append(line)
        index += 1

    while normalized and not normalized[-1].strip():
        normalized.pop()

    return normalized


def _strip_callable_return_type_sections(lines: Iterable[str]) -> list[str]:
    """Remove redundant return-type sections from callable docstrings."""
    normalized: list[str] = []
    skip_section = False

    line_list = list(lines)
    index = 0
    while index < len(line_list):
        line = line_list[index]
        stripped = line.strip()

        if CALLABLE_RTYPE_FIELD_PATTERN.match(stripped):
            index += 1
            continue

        if CALLABLE_RETURN_TYPE_SECTION_PATTERN.match(stripped):
            next_index = index + 1
            if next_index < len(line_list):
                underline = line_list[next_index].strip()
                if underline and set(underline) == {"-"}:
                    skip_section = True
                    index += 2
                    continue

        if skip_section:
            if not stripped:
                skip_section = False
            index += 1
            continue

        normalized.append(line)
        index += 1

    while normalized and not normalized[-1].strip():
        normalized.pop()

    return normalized


def _normalize_base_name(base: str | BaseLike) -> str:
    """Convert an AutoAPI base entry into a concise display name."""
    name = base if isinstance(base, str) else base.name

    return name.rsplit(".", maxsplit=1)[-1].strip()


def _format_base_reference(base: str | BaseLike) -> str:
    """Render a base entry as a class reference when a full name is available."""
    full_name = (base if isinstance(base, str) else base.name).strip()
    short_name = _normalize_base_name(base)

    if not full_name or not short_name:
        return ""

    if full_name == short_name:
        return format_type_for_rst(short_name)

    return f":py:class:`{short_name} <{full_name}>`"


def _annotation_to_text(annotation: object) -> str:
    """Convert a runtime annotation object into a concise text form."""
    if isinstance(annotation, str):
        return annotation.strip()

    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin is Annotated:
        return _annotation_to_text(args[0])

    if origin in {UnionType, Union}:
        return " | ".join(_annotation_to_text(arg) for arg in args)

    if origin is not None:
        origin_name = _normalize_base_name(origin.__qualname__)
        if args:
            rendered_args = ", ".join(_annotation_to_text(arg) for arg in args)
            return f"{origin_name}[{rendered_args}]"
        return origin_name

    if annotation is None or annotation is type(None):
        return "None"

    forward_arg = getattr(annotation, "__forward_arg__", None)
    if forward_arg is not None:
        return str(forward_arg).strip()

    annotation_name = getattr(annotation, "__name__", None)
    if annotation_name is not None:
        return str(annotation_name).strip()

    return str(annotation).strip()


def format_annotation_for_rst(annotation: object, _config: object | None = None) -> str:
    """Render a runtime annotation object as a reST inline literal."""
    return format_type_for_rst(_annotation_to_text(annotation))


def format_type_for_rst(type_annotation: str) -> str:
    """Render a type annotation as a reST inline literal."""
    return f"``{type_annotation.strip()}``"


def format_option_type_for_rst(type_annotation: str) -> str:
    """Render directive option type values as plain text."""
    return type_annotation.strip()


def normalize_docstring_for_rst(docstring: str) -> str:
    """Normalize markdown-leaning docstrings so Sphinx renders them as reST."""
    if not docstring.strip():
        return docstring

    lines = docstring.splitlines()
    lines = _convert_fenced_code_blocks(lines)
    lines = _insert_blank_lines_around_lists(lines)
    return "\n".join(lines).strip("\n")


def normalize_property_docstring_for_rst(docstring: str) -> str:
    """Normalize property docstrings and drop redundant return sections."""
    normalized = normalize_docstring_for_rst(docstring)
    lines = _strip_property_return_sections(normalized.splitlines())
    return "\n".join(lines).strip("\n")


def normalize_callable_docstring_for_rst(docstring: str) -> str:
    """Normalize callable docstrings and drop redundant return-type sections."""
    normalized = normalize_docstring_for_rst(docstring)
    lines = _strip_callable_return_type_sections(normalized.splitlines())
    return "\n".join(lines).strip("\n")


def format_inheritance_for_rst(bases: Iterable[str | BaseLike], class_name: str) -> str:
    """Format class inheritance information for display in AutoAPI templates."""
    base_references = []
    for base in bases:
        base_name = _normalize_base_name(base)
        if not base_name or base_name in {"object", class_name}:
            continue
        base_references.append(_format_base_reference(base))

    if not base_references:
        return ""

    return f"**Bases:** {', '.join(base_references)}"


def prepare_autoapi_jinja_env(jinja_env: JinjaEnvironmentLike) -> None:
    """Register custom Jinja filters used by the AutoAPI templates."""
    jinja_env.filters["format_inheritance_for_rst"] = format_inheritance_for_rst
    jinja_env.filters["format_annotation_for_rst"] = format_annotation_for_rst
    jinja_env.filters["format_option_type_for_rst"] = format_option_type_for_rst
    jinja_env.filters["format_type_for_rst"] = format_type_for_rst
    jinja_env.filters["normalize_callable_docstring_for_rst"] = (
        normalize_callable_docstring_for_rst
    )
    jinja_env.filters["normalize_docstring_for_rst"] = normalize_docstring_for_rst
    jinja_env.filters["normalize_property_docstring_for_rst"] = (
        normalize_property_docstring_for_rst
    )
