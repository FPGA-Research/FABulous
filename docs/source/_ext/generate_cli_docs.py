#!/usr/bin/env python3
"""Sphinx extension to auto-generate CLI command documentation from FABulous_CLI."""

import ast
import logging
import re
from pathlib import Path

import jinja2
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
    app.connect("config-inited", generate_cli_docs)
    return {"version": "1.0"}


def generate_cli_docs(app: Sphinx, conf: Config) -> None:  # noqa: ARG001
    """Generate CLI command documentation from FABulous_CLI class.

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

        # Extract command metadata using AST parsing (no imports needed)
        repo_root = doc_root_dir.parent.parent
        cli_dir = repo_root / "fabulous" / "fabulous_cli"
        cli_file = cli_dir / "fabulous_cli.py"
        commands_by_category = extract_cli_commands_ast(cli_file)

        # Also extract commands from cmd_synthesis.py
        synthesis_file = cli_dir / "cmd_synthesis.py"
        if synthesis_file.exists():
            synthesis_commands = extract_standalone_commands_ast(synthesis_file)
            for category, cmds in synthesis_commands.items():
                if category not in commands_by_category:
                    commands_by_category[category] = []
                commands_by_category[category].extend(cmds)

        # Render documentation
        template = env.get_template("cli_commands.md.jinja")
        output = template.render(
            commands_by_category=commands_by_category,
        )

        # Write output to generated_doc folder (gitignored)
        output_file = doc_root_dir / "generated_doc" / "interactive_cli_commands.md"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(output)

        logger.info("Generated CLI command documentation: %s", output_file)

    except (OSError, jinja2.TemplateError):
        logger.exception("Failed to generate CLI command documentation")
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


def extract_cli_commands_ast(cli_file: Path) -> dict:
    """Extract CLI commands using AST parsing (no runtime imports).

    Parameters
    ----------
    cli_file : Path
        Path to the CLI file to parse.

    Returns
    -------
    dict
        Dictionary of commands by category.
    """
    source = cli_file.read_text()
    tree = ast.parse(source)

    # Find category constants
    category_map = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Name)
                    and target.id.startswith("CMD_")
                    and isinstance(node.value, ast.Constant)
                ):
                    category_map[target.id] = node.value.value

    # Find parser definitions (legacy argparse)
    parsers = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and "parser" in target.id.lower():
                    parsers[target.id] = extract_parser_args(node, source)

    # Find do_* methods
    commands_by_category: dict = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "FABulous_CLI":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name.startswith("do_"):
                    cmd_name = item.name[3:]
                    docstring = ast.get_docstring(item) or "No documentation available"
                    # Clean the docstring to remove Parameters section
                    cleaned_docstring = clean_docstring(docstring)
                    short_desc = cleaned_docstring.split("\n")[0].strip()

                    # Get category from decorators
                    category = "Other"
                    parser_name = None
                    for decorator in item.decorator_list:
                        if isinstance(decorator, ast.Call) and isinstance(
                            decorator.func, ast.Name
                        ):
                            if decorator.func.id == "with_category":
                                if decorator.args and isinstance(
                                    decorator.args[0], ast.Name
                                ):
                                    cat_var = decorator.args[0].id
                                    category = category_map.get(cat_var, "Other")
                            elif (
                                decorator.func.id == "with_argparser"
                                and decorator.args
                                and isinstance(decorator.args[0], ast.Name)
                            ):
                                parser_name = decorator.args[0].id

                    # Try Typer annotations first, then fall back to parser
                    arguments = extract_typer_arguments(item)
                    if not arguments and parser_name and parser_name in parsers:
                        arguments = parsers[parser_name]

                    if category not in commands_by_category:
                        commands_by_category[category] = []

                    commands_by_category[category].append(
                        {
                            "name": cmd_name,
                            "short_desc": short_desc,
                            "full_desc": cleaned_docstring,
                            "arguments": arguments,
                        }
                    )

    # Sort commands within each category
    for category in commands_by_category:
        commands_by_category[category].sort(key=lambda x: x["name"])

    # Sort categories
    category_order = [
        "Setup",
        "Fabric Flow",
        "User Design Flow",
        "Helper",
        "GUI",
        "Script",
        "Tools",
        "Other",
    ]

    sorted_categories: dict = {}
    for cat in category_order:
        if cat in commands_by_category:
            sorted_categories[cat] = commands_by_category[cat]

    for cat in commands_by_category:
        if cat not in sorted_categories:
            sorted_categories[cat] = commands_by_category[cat]

    return sorted_categories


def extract_typer_arguments(func_node: ast.FunctionDef) -> list:
    """Extract argument information from Typer function annotations.

    Parameters
    ----------
    func_node : ast.FunctionDef
        The function AST node to extract arguments from.

    Returns
    -------
    list
        List of argument dictionaries with name, type, help, required, etc.
    """
    arguments = []

    for arg in func_node.args.args:
        # Skip 'self' parameter
        if arg.arg == "self":
            continue

        arg_info = {
            "name": arg.arg,
            "type": "Any",
            "help": "",
            "required": True,
            "choices": "",
            "default": "",
        }

        # Extract type and metadata from annotation
        if arg.annotation:
            # Handle Annotated[type, metadata...]
            if isinstance(arg.annotation, ast.Subscript):
                # Get the base type
                if isinstance(arg.annotation.slice, ast.Tuple):
                    elts = arg.annotation.slice.elts
                    if elts:
                        arg_info["type"] = ast.unparse(elts[0])

                        # Extract help text from typer.Argument() or typer.Option()
                        for metadata in elts[1:]:
                            if isinstance(metadata, ast.Call):
                                for keyword in metadata.keywords:
                                    if keyword.arg == "help" and isinstance(
                                        keyword.value, ast.Constant
                                    ):
                                        arg_info["help"] = keyword.value.value
                else:
                    arg_info["type"] = ast.unparse(arg.annotation.slice)
            else:
                arg_info["type"] = ast.unparse(arg.annotation)

        # Check if parameter has a default value
        defaults_offset = len(func_node.args.args) - len(func_node.args.defaults)
        arg_idx = func_node.args.args.index(arg)
        if arg_idx >= defaults_offset:
            default_idx = arg_idx - defaults_offset
            default_node = func_node.args.defaults[default_idx]
            arg_info["required"] = False
            arg_info["default"] = ast.unparse(default_node)

        arguments.append(arg_info)

    return arguments


def extract_standalone_commands_ast(cmd_file: Path) -> dict:
    """Extract CLI commands from standalone command files like cmd_synthesis.py.

    These files define do_* functions at module level (not in a class) that get
    mixed into the CLI class.

    Parameters
    ----------
    cmd_file : Path
        Path to the command file to parse.

    Returns
    -------
    dict
        Dictionary of commands by category.
    """
    source = cmd_file.read_text()
    tree = ast.parse(source)

    # Find category constants
    category_map = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Name)
                    and target.id.startswith("CMD_")
                    and isinstance(node.value, ast.Constant)
                ):
                    category_map[target.id] = node.value.value

    # Find parser definitions
    parsers = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and "parser" in target.id.lower():
                    parsers[target.id] = extract_parser_args(node, source)

    # Find do_* functions at module level
    commands_by_category: dict = {}

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("do_"):
            cmd_name = node.name[3:]
            docstring = ast.get_docstring(node) or "No documentation available"
            # Clean the docstring to remove Parameters section
            cleaned_docstring = clean_docstring(docstring)
            short_desc = cleaned_docstring.split("\n")[0].strip()

            # Get category from decorators
            category = "Other"
            parser_name = None
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call) and isinstance(
                    decorator.func, ast.Name
                ):
                    if decorator.func.id == "with_category":
                        if decorator.args and isinstance(decorator.args[0], ast.Name):
                            cat_var = decorator.args[0].id
                            category = category_map.get(cat_var, "Other")
                    elif (
                        decorator.func.id == "with_argparser"
                        and decorator.args
                        and isinstance(decorator.args[0], ast.Name)
                    ):
                        parser_name = decorator.args[0].id

            # Get arguments - try Typer annotations first, then fall back to parser
            arguments = extract_typer_arguments(node)
            if not arguments and parser_name and parser_name in parsers:
                arguments = parsers[parser_name]

            if category not in commands_by_category:
                commands_by_category[category] = []

            commands_by_category[category].append(
                {
                    "name": cmd_name,
                    "short_desc": short_desc,
                    "full_desc": cleaned_docstring,
                    "arguments": arguments,
                }
            )

    return commands_by_category


def extract_parser_args(assign_node: ast.Assign, source: str) -> list:
    """Extract argument info from parser definition using regex on source.

    Parameters
    ----------
    assign_node : ast.Assign
        The AST assignment node for the parser.
    source : str
        The source code.

    Returns
    -------
    list
        List of argument dictionaries.
    """
    arguments: list = []

    # Get the parser variable name
    if not assign_node.targets:
        return arguments
    target = assign_node.targets[0]
    if not isinstance(target, ast.Name):
        return arguments

    parser_name = target.id

    # Get line range for this assignment and following add_argument calls
    start_line = assign_node.lineno
    lines = source.split("\n")

    # Search for add_argument calls after the parser definition
    in_parser_block = False
    for i, line in enumerate(lines[start_line - 1 :], start=start_line):
        if parser_name in line and "Cmd2ArgumentParser" in line:
            in_parser_block = True
            continue

        if in_parser_block:
            if f"{parser_name}.add_argument" in line:
                # Extract argument info from the add_argument call
                arg_info = parse_add_argument(lines, i - 1)
                if arg_info:
                    arguments.append(arg_info)
            elif (
                line.strip()
                and not line.strip().startswith("#")
                and not line.strip().startswith(")")
            ):
                # Check if we've moved past this parser's definitions
                if (
                    re.match(r"^\s*\w+\s*=", line)
                    or line.strip().startswith("@")
                    or line.strip().startswith("def ")
                ):
                    break

    return arguments


def parse_add_argument(lines: list, start_idx: int) -> dict | None:
    """Parse a single add_argument call.

    Parameters
    ----------
    lines : list
        List of source code lines.
    start_idx : int
        Starting line index.

    Returns
    -------
    dict | None
        Argument info dictionary or None if parsing fails.
    """
    # Collect the full add_argument call (may span multiple lines)
    call_text = ""
    paren_count = 0
    started = False

    for i in range(start_idx, min(start_idx + 20, len(lines))):
        line = lines[i]
        for char in line:
            if char == "(":
                paren_count += 1
                started = True
            elif char == ")":
                paren_count -= 1

            if started:
                call_text += char

            if started and paren_count == 0:
                break

        if started and paren_count == 0:
            break
        call_text += " "

    if not call_text:
        return None

    # Extract argument name (first string argument)
    name_match = re.search(r'["\']([^"\']+)["\']', call_text)
    if not name_match:
        return None

    arg_name = name_match.group(1).lstrip("-")

    # Extract type
    arg_type = "str"
    type_match = re.search(r"type\s*=\s*(\w+)", call_text)
    if type_match:
        arg_type = type_match.group(1)

    # Extract help text
    help_text = ""
    help_match = re.search(r'help\s*=\s*["\']([^"\']+)["\']', call_text)
    if help_match:
        help_text = help_match.group(1)

    # Extract default
    default = ""
    default_match = re.search(r"default\s*=\s*([^,\)]+)", call_text)
    if default_match:
        default = default_match.group(1).strip().strip("\"'")
        if default in ('""', "''", ""):
            default = ""

    # Check if required (no nargs=? or default)
    required = "nargs" not in call_text.lower() and "default" not in call_text.lower()

    return {
        "name": arg_name,
        "type": arg_type,
        "help": help_text,
        "required": required,
        "choices": "",
        "default": default,
    }
