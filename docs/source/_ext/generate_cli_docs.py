#!/usr/bin/env python3
"""Sphinx extension to auto-generate CLI command documentation from FABulous_CLI."""

from __future__ import annotations

import argparse
import inspect
import logging
from typing import TYPE_CHECKING

import cmd2
from _doc_common import render_generated_doc

if TYPE_CHECKING:
    from sphinx.application import Sphinx
    from sphinx.config import Config

logger = logging.getLogger(__name__)

_CATEGORY_ORDER = [
    "Setup",
    "Fabric Flow",
    "User Design Flow",
    "Helper",
    "GUI",
    "Script",
    "Tools",
    "Other",
]


def setup(app: Sphinx) -> dict[str, str]:  # noqa: ARG001
    """Set up the Sphinx extension.

    Parameters
    ----------
    app : Sphinx
        The Sphinx application object.

    Returns
    -------
    dict[str, str]
        Extension metadata.
    """
    app.connect("config-inited", generate_cli_docs)
    return {"version": "1.0", "parallel_read_safe": True}


def generate_cli_docs(app: Sphinx, conf: Config) -> None:  # noqa: ARG001
    """Generate CLI command documentation from the live FABulous_CLI class.

    Parameters
    ----------
    app : Sphinx
        The Sphinx application object.
    conf : Config
        The Sphinx configuration object.
    """
    output_file = render_generated_doc(
        conf,
        template_name="cli_commands.md.jinja",
        output_name="interactive_cli_commands.md",
        context={"commands_by_category": extract_cli_commands()},
    )
    logger.info("Generated CLI command documentation: %s", output_file)


def clean_docstring(docstring: str) -> str:
    """Remove Parameters, Raises, and other formal sections from docstring.

    This removes numpy/scipy style parameter documentation and other formal sections
    that are already being presented in the Arguments table.

    Parameters
    ----------
    docstring : str
        The docstring to clean.

    Returns
    -------
    str
        Cleaned docstring without formal sections.
    """
    lines = docstring.split("\n")
    result = []
    skip_until_blank = False

    # Section headers we want to remove entirely
    formal_sections = {
        "Parameters",
        "Raises",
        "Returns",
        "Yields",
        "Examples",
        "Notes",
        "See Also",
    }

    for i, line in enumerate(lines):
        stripped = line.strip()
        # Check if this is the start of a formal section
        if stripped in formal_sections and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            # Check if followed by dashes (numpy style)
            if next_line == "-" * len(stripped) or next_line.startswith("-" * 5):
                skip_until_blank = True
                continue

        # Skip lines until we hit a blank line (end of section)
        if skip_until_blank:
            if line.strip() == "":
                skip_until_blank = False
            continue

        result.append(line)

    return "\n".join(result).strip()


def _argument_info(action: argparse.Action) -> dict:
    """Render one argparse action as the dict the CLI template expects.

    Parameters
    ----------
    action : argparse.Action
        A single parser action.

    Returns
    -------
    dict
        Keys: name, type, required, help, default, choices.
    """
    if action.option_strings:
        # Prefer the long ``--option`` form for the displayed name.
        name = max(action.option_strings, key=len).lstrip("-")
    else:
        name = action.dest
    if action.nargs == 0:
        # store_true / store_false flags have no value to type.
        arg_type = "bool"
    elif isinstance(action.type, type):
        arg_type = action.type.__name__
    else:
        arg_type = "str"
    default = "" if action.default in (None, argparse.SUPPRESS) else str(action.default)
    choices = ", ".join(str(c) for c in action.choices) if action.choices else ""
    return {
        "name": name,
        "type": arg_type,
        "required": bool(action.required),
        "help": action.help or "",
        "default": default,
        "choices": choices,
    }


def _command_arguments(parser: argparse.ArgumentParser | None) -> list[dict]:
    """Return argument dicts for a parser, skipping the auto-added help action.

    Parameters
    ----------
    parser : argparse.ArgumentParser | None
        The command's parser, or None if the command takes no argparser.

    Returns
    -------
    list[dict]
        One dict per argument.
    """
    if not isinstance(parser, argparse.ArgumentParser):
        return []
    return [
        _argument_info(action)
        for action in parser._actions  # noqa: SLF001
        if not isinstance(action, argparse._HelpAction)  # noqa: SLF001
    ]


def extract_cli_commands() -> dict[str, list[dict]]:
    """Collect CLI command docs by introspecting the live FABulous_CLI class.

    Returns
    -------
    dict[str, list[dict]]
        Command dicts grouped by cmd2 help category, in display order.
    """
    from fabulous.fabulous_cli.fabulous_cli import FABulous_CLI

    by_category: dict[str, list[dict]] = {}
    for attr_name in dir(FABulous_CLI):
        if not attr_name.startswith("do_"):
            continue
        method = getattr(FABulous_CLI, attr_name)
        # Skip cmd2's inherited built-ins (help, set, history, shell, ...); the
        # reference documents FABulous commands only.
        if not (getattr(method, "__module__", "") or "").startswith("fabulous"):
            continue
        category = getattr(method, cmd2.constants.CMD_ATTR_HELP_CATEGORY, "Other")
        parser = getattr(method, cmd2.constants.CMD_ATTR_ARGPARSER, None)
        docstring = inspect.getdoc(method) or "No documentation available"

        by_category.setdefault(category, []).append(
            {
                "name": attr_name[3:],
                "full_desc": clean_docstring(docstring),
                "arguments": _command_arguments(parser),
            }
        )

    for commands in by_category.values():
        commands.sort(key=lambda c: c["name"])

    ordered = {cat: by_category[cat] for cat in _CATEGORY_ORDER if cat in by_category}
    for cat, commands in by_category.items():
        ordered.setdefault(cat, commands)
    return ordered
