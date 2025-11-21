#!/usr/bin/env python3
"""Sphinx extension to auto-generate CLI command documentation from FABulous_CLI."""

import ast
import re
import traceback
from pathlib import Path

import jinja2
from sphinx.application import Sphinx
from sphinx.config import Config


def setup(app: Sphinx):
    app.connect("config-inited", generate_cli_docs)
    return {"version": "1.0"}


def generate_cli_docs(app: Sphinx, conf: Config) -> None:
    """Generate CLI command documentation from FABulous_CLI class."""
    try:
        conf_py_path: str = conf._raw_config["__file__"]
        doc_root_dir: Path = Path(conf_py_path).parent

        template_relpath: str = conf.templates_path[0]
        all_templates_path = doc_root_dir / template_relpath

        lookup = jinja2.FileSystemLoader(searchpath=all_templates_path)
        env = jinja2.Environment(loader=lookup)

        # Extract command metadata using AST parsing (no imports needed)
        repo_root = doc_root_dir.parent.parent
        cli_file = repo_root / "FABulous" / "FABulous_CLI" / "FABulous_CLI.py"
        commands_by_category = extract_cli_commands_ast(cli_file)

        # Render documentation
        template = env.get_template("cli_commands.md.jinja")
        output = template.render(
            commands_by_category=commands_by_category,
        )

        # Write output to cli_doc folder
        output_file = doc_root_dir / "user_guide" / "cli_doc" / "interactive_cli_commands.md"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(output)

        print(f"Generated CLI command documentation: {output_file}")

    except Exception:
        print(traceback.format_exc())
        exit(-1)


def extract_cli_commands_ast(cli_file: Path) -> dict:
    """Extract CLI commands using AST parsing (no runtime imports)."""
    source = cli_file.read_text()
    tree = ast.parse(source)

    # Find category constants
    category_map = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.startswith("CMD_"):
                    if isinstance(node.value, ast.Constant):
                        category_map[target.id] = node.value.value

    # Find parser definitions
    parsers = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and "parser" in target.id.lower():
                    parsers[target.id] = extract_parser_args(node, source)

    # Find do_* methods
    commands_by_category = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "FABulous_CLI":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name.startswith("do_"):
                    cmd_name = item.name[3:]
                    docstring = ast.get_docstring(item) or "No documentation available"
                    short_desc = docstring.split("\n")[0].strip()

                    # Get category from decorators
                    category = "Other"
                    parser_name = None
                    for decorator in item.decorator_list:
                        if isinstance(decorator, ast.Call):
                            if isinstance(decorator.func, ast.Name):
                                if decorator.func.id == "with_category":
                                    if decorator.args and isinstance(decorator.args[0], ast.Name):
                                        cat_var = decorator.args[0].id
                                        category = category_map.get(cat_var, "Other")
                                elif decorator.func.id == "with_argparser":
                                    if decorator.args and isinstance(decorator.args[0], ast.Name):
                                        parser_name = decorator.args[0].id

                    # Get arguments from parser
                    arguments = []
                    if parser_name and parser_name in parsers:
                        arguments = parsers[parser_name]

                    if category not in commands_by_category:
                        commands_by_category[category] = []

                    commands_by_category[category].append({
                        "name": cmd_name,
                        "short_desc": short_desc,
                        "full_desc": docstring,
                        "arguments": arguments,
                    })

    # Sort commands within each category
    for category in commands_by_category:
        commands_by_category[category].sort(key=lambda x: x["name"])

    # Sort categories
    category_order = [
        "Setup", "Fabric Flow", "User Design Flow", "Helper",
        "GUI", "Script", "Tools", "Other"
    ]

    sorted_categories = {}
    for cat in category_order:
        if cat in commands_by_category:
            sorted_categories[cat] = commands_by_category[cat]

    for cat in commands_by_category:
        if cat not in sorted_categories:
            sorted_categories[cat] = commands_by_category[cat]

    return sorted_categories


def extract_parser_args(assign_node: ast.Assign, source: str) -> list:
    """Extract argument info from parser definition using regex on source."""
    arguments = []

    # Get the parser variable name
    if not assign_node.targets:
        return arguments
    target = assign_node.targets[0]
    if not isinstance(target, ast.Name):
        return arguments

    parser_name = target.id

    # Find all add_argument calls for this parser using regex
    pattern = rf'{parser_name}\.add_argument\s*\((.*?)\)'

    # Get line range for this assignment and following add_argument calls
    start_line = assign_node.lineno
    lines = source.split('\n')

    # Search for add_argument calls after the parser definition
    in_parser_block = False
    for i, line in enumerate(lines[start_line - 1:], start=start_line):
        if parser_name in line and 'Cmd2ArgumentParser' in line:
            in_parser_block = True
            continue

        if in_parser_block:
            if f'{parser_name}.add_argument' in line:
                # Extract argument info from the add_argument call
                arg_info = parse_add_argument(lines, i - 1)
                if arg_info:
                    arguments.append(arg_info)
            elif line.strip() and not line.strip().startswith('#') and not line.strip().startswith(')'):
                # Check if we've moved past this parser's definitions
                if re.match(r'^\s*\w+\s*=', line) or line.strip().startswith('@') or line.strip().startswith('def '):
                    break

    return arguments


def parse_add_argument(lines: list, start_idx: int) -> dict | None:
    """Parse a single add_argument call."""
    # Collect the full add_argument call (may span multiple lines)
    call_text = ""
    paren_count = 0
    started = False

    for i in range(start_idx, min(start_idx + 20, len(lines))):
        line = lines[i]
        for char in line:
            if char == '(':
                paren_count += 1
                started = True
            elif char == ')':
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

    arg_name = name_match.group(1).lstrip('-')

    # Extract type
    arg_type = "str"
    type_match = re.search(r'type\s*=\s*(\w+)', call_text)
    if type_match:
        arg_type = type_match.group(1)

    # Extract help text
    help_text = ""
    help_match = re.search(r'help\s*=\s*["\']([^"\']+)["\']', call_text)
    if help_match:
        help_text = help_match.group(1)

    # Extract default
    default = ""
    default_match = re.search(r'default\s*=\s*([^,\)]+)', call_text)
    if default_match:
        default = default_match.group(1).strip().strip('"\'')
        if default in ('""', "''", ''):
            default = ""

    # Check if required (no nargs=? or default)
    required = 'nargs' not in call_text.lower() and 'default' not in call_text.lower()

    return {
        "name": arg_name,
        "type": arg_type,
        "help": help_text,
        "required": required,
        "choices": "",
        "default": default,
    }
