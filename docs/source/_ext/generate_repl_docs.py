#!/usr/bin/env python3
"""Sphinx extension to auto-generate REPL command documentation from FABulousREPL.

Command metadata is read by importing the live REPL classes and introspecting the
objects cmd2 already builds: the `@with_category` category string and the
`@with_annotated` argument parser attached to each `do_*` method. This uses
cmd2's own resolved values (required-ness, defaults, choices, flag spellings)
rather than re-deriving them, so the docs cannot drift from what the REPL
actually accepts.
"""

import argparse
import importlib
import inspect
import logging
import pkgutil
import types
import typing
from pathlib import Path

import jinja2
from cmd2 import constants
from sphinx.application import Sphinx
from sphinx.config import Config

logger = logging.getLogger(__name__)


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
    app.connect("config-inited", generate_repl_docs)
    return {"version": "1.0"}


def generate_repl_docs(app: Sphinx, conf: Config) -> None:  # noqa: ARG001
    """Generate REPL command documentation from the live REPL classes.

    Parameters
    ----------
    app : Sphinx
        The Sphinx application object.
    conf : Config
        The Sphinx configuration object.

    Raises
    ------
    SystemExit
        If documentation generation fails.
    """
    try:
        conf_py_path: str = conf._raw_config["__file__"]  # noqa: SLF001
        doc_root_dir: Path = Path(conf_py_path).parent

        template_relpath: str = conf.templates_path[0]
        all_templates_path = doc_root_dir / template_relpath

        lookup = jinja2.FileSystemLoader(searchpath=all_templates_path)
        env = jinja2.Environment(loader=lookup)

        commands_by_category = _collect_commands()
        commands_by_category = _sort_categories(commands_by_category, _category_order())

        # Render documentation
        template = env.get_template("cli_commands.md.jinja")
        output = template.render(
            commands_by_category=commands_by_category,
        )

        # Write output to generated_doc folder (gitignored)
        output_file = doc_root_dir / "generated_doc" / "interactive_repl_commands.md"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(output)

        logger.info("Generated REPL command documentation: %s", output_file)

    except (OSError, jinja2.TemplateError, ImportError):
        logger.exception("Failed to generate REPL command documentation")
        raise SystemExit(-1) from None


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


def _command_classes() -> list[type]:
    """Import the REPL command modules and return the classes that define commands.

    The concrete command providers are `FABulousREPL` itself and every
    `ReplCommandSet` subclass. The `cmd_*.py` submodules are imported first so
    those subclasses are registered before they are enumerated.

    Returns
    -------
    list[type]
        `FABulousREPL` followed by every `ReplCommandSet` subclass.
    """
    repl_pkg = importlib.import_module("fabulous.fabulous_repl")
    for module in pkgutil.iter_modules(repl_pkg.__path__):
        if module.name.startswith("cmd_"):
            importlib.import_module(f"{repl_pkg.__name__}.{module.name}")

    from fabulous.fabulous_repl.command_set_base import ReplCommandSet
    from fabulous.fabulous_repl.fabulous_repl import FABulousREPL

    return [FABulousREPL, *_all_subclasses(ReplCommandSet)]


def _all_subclasses(cls: type) -> list[type]:
    """Return every direct and indirect subclass of `cls` (deduplicated).

    Parameters
    ----------
    cls : type
        The base class to walk.

    Returns
    -------
    list[type]
        All descendant classes, each appearing once.
    """
    seen: dict[type, None] = {}
    stack = list(cls.__subclasses__())
    while stack:
        subclass = stack.pop()
        if subclass not in seen:
            seen[subclass] = None
            stack.extend(subclass.__subclasses__())
    return list(seen)


def _collect_commands() -> dict:
    """Collect all `do_*` commands, grouped by their cmd2 help category.

    Returns
    -------
    dict
        Mapping of category name to a list of command doc entries.
    """
    commands_by_category: dict = {}
    for cls in _command_classes():
        for name, member in vars(cls).items():
            if not name.startswith("do_") or not callable(member):
                continue
            category = getattr(member, constants.COMMAND_ATTR_HELP_CATEGORY, "Other")
            commands_by_category.setdefault(category, []).append(
                _command_entry(name, member)
            )
    return commands_by_category


def _command_entry(method_name: str, fn: types.FunctionType) -> dict:
    """Build a command doc entry from a `do_*` method.

    Parameters
    ----------
    method_name : str
        The method name, e.g. `do_load_fabric`.
    fn : types.FunctionType
        The (possibly `@with_annotated`-wrapped) method object.

    Returns
    -------
    dict
        A `{name, short_desc, full_desc, arguments}` record.
    """
    docstring = inspect.getdoc(fn) or "No documentation available"
    cleaned_docstring = clean_docstring(docstring)
    return {
        "name": method_name[3:],
        "short_desc": cleaned_docstring.split("\n")[0].strip(),
        "full_desc": cleaned_docstring,
        "arguments": _extract_arguments(fn),
    }


def _extract_arguments(fn: types.FunctionType) -> list[dict]:
    """Build the argument list for a `do_*` method from its cmd2 parser.

    Reads the `@with_annotated` argument parser attached by cmd2 and pairs each
    argparse action with the parameter's type annotation. Methods without an
    attached parser (no `@with_annotated`) have no arguments.

    Parameters
    ----------
    fn : types.FunctionType
        The method object to inspect.

    Returns
    -------
    list[dict]
        One record per argument, each with `name`, `type`, `help`,
        `required`, `choices` and `default` keys.
    """
    spec = getattr(fn, constants.ARGPARSE_COMMAND_ATTR_SPEC, None)
    if spec is None:
        return []

    # cmd2 types parser_source as "a Cmd2ArgumentParser instance or a factory
    # that returns one" -- accept both rather than assuming either form.
    source = spec.parser_source
    parser = source if isinstance(source, argparse.ArgumentParser) else source()
    type_hints = _parameter_type_hints(fn)

    arguments: list[dict] = []
    for action in parser._actions:  # noqa: SLF001
        if isinstance(action, argparse._HelpAction):  # noqa: SLF001
            continue
        arguments.append(_argument_record(action, type_hints))
    return arguments


def _parameter_type_hints(fn: types.FunctionType) -> dict:
    """Resolve a method's parameter annotations, keyed by parameter name.

    Uses {func}`inspect.signature` rather than {func}`typing.get_type_hints` so a
    `self` parameter annotated with a not-at-runtime-importable forward reference
    (the standalone `do_*` functions write `self: "FABulousREPL"` to dodge a
    circular import) never has to resolve. Only real command parameters, whose
    types are imported at runtime, are resolved; `self` is skipped.

    Parameters
    ----------
    fn : types.FunctionType
        The method to inspect.

    Returns
    -------
    dict
        Parameter name to its (possibly `Annotated`) type object.
    """
    globalns = getattr(fn, "__globals__", {})
    hints: dict = {}
    for name, param in inspect.signature(fn).parameters.items():
        if name == "self" or param.annotation is inspect.Parameter.empty:
            continue
        annotation = param.annotation
        if isinstance(annotation, str):
            annotation = eval(annotation, globalns)  # noqa: S307
        hints[name] = annotation
    return hints


def _argument_record(action: argparse.Action, type_hints: dict) -> dict:
    """Build one argument record from an argparse action and the method's hints.

    Parameters
    ----------
    action : argparse.Action
        The action to render (a positional or an option).
    type_hints : dict
        `typing.get_type_hints(..., include_extras=True)` for the method, keyed
        by parameter name (`action.dest`).

    Returns
    -------
    dict
        A `{name, type, help, required, choices, default}` record, with markdown
        pipes escaped so values cannot break the surrounding table.
    """
    is_positional = not action.option_strings
    display_name = action.dest if is_positional else action.option_strings[0]

    hint = type_hints.get(action.dest)
    type_str = _format_type(_annotated_inner(hint)) if hint is not None else "Any"

    default_str = "" if action.default is None else str(action.default)

    choices_str = ""
    if action.choices is not None:
        choices_str = ", ".join(str(choice) for choice in action.choices)

    return {
        "name": _escape_pipe(display_name),
        "type": _escape_pipe(type_str),
        "help": _escape_pipe(action.help or ""),
        "required": action.required,
        "choices": _escape_pipe(choices_str),
        "default": _escape_pipe(default_str),
    }


def _annotated_inner(hint: object) -> object:
    """Return the underlying type of an `Annotated[T, ...]` hint, else the hint."""
    if typing.get_origin(hint) is typing.Annotated:
        return typing.get_args(hint)[0]
    return hint


def _format_type(tp: object) -> str:
    """Render a type object as a short, source-like string.

    Produces `Path`, `str | None`, `list[Path]` or `Literal[a, b]` rather
    than the fully-qualified `repr` so the doc table stays readable.

    Parameters
    ----------
    tp : object
        The type (or typing construct) to render.

    Returns
    -------
    str
        A human-readable type string.
    """
    if tp is type(None):
        return "None"
    if isinstance(tp, type):
        return tp.__name__

    origin = typing.get_origin(tp)
    if origin in (types.UnionType, typing.Union):
        return " | ".join(_format_type(arg) for arg in typing.get_args(tp))
    if origin is typing.Literal:
        return "Literal[" + ", ".join(str(arg) for arg in typing.get_args(tp)) + "]"
    if origin is not None:
        args = ", ".join(_format_type(arg) for arg in typing.get_args(tp))
        origin_name = getattr(origin, "__name__", str(origin))
        return f"{origin_name}[{args}]"

    return getattr(tp, "__name__", str(tp))


def _escape_pipe(text: str) -> str:
    """Escape `|` so a value doesn't break the surrounding markdown table."""
    return text.replace("|", r"\|")


def _category_order() -> list[str]:
    """Return category display order, following `command_set_base` definitions.

    Categories are shown in the order their `CMD_*` constants are defined in
    `command_set_base.py`, with the `"Other"` catch-all always rendered last.

    Returns
    -------
    list[str]
        Category names in display order.
    """
    command_set_base = importlib.import_module(
        "fabulous.fabulous_repl.command_set_base"
    )
    order = [
        value
        for name, value in vars(command_set_base).items()
        if name.startswith("CMD_") and isinstance(value, str)
    ]
    order = list(dict.fromkeys(order))
    if "Other" in order:
        order.remove("Other")
        order.append("Other")
    return order


def _sort_categories(commands_by_category: dict, category_order: list[str]) -> dict:
    """Sort commands within each category and order the categories.

    Parameters
    ----------
    commands_by_category : dict
        Mapping of category name to its list of command entries.
    category_order : list[str]
        Category names in the desired display order. Categories present in
        `commands_by_category` but absent here are appended afterwards.

    Returns
    -------
    dict
        New mapping with categories in display order, each command list sorted
        by command name.
    """
    for category in commands_by_category:
        commands_by_category[category].sort(key=lambda x: x["name"])

    sorted_categories: dict = {}
    for cat in category_order:
        if cat in commands_by_category:
            sorted_categories[cat] = commands_by_category[cat]
    for cat in commands_by_category:
        if cat not in sorted_categories:
            sorted_categories[cat] = commands_by_category[cat]
    return sorted_categories
