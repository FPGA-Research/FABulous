#!/usr/bin/env python3
# Copyright 2024 Efabless Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

"""Sphinx extension to auto-generate FABulous configuration variable documentation."""

import ast
import traceback
from pathlib import Path

import jinja2
from sphinx.application import Sphinx
from sphinx.config import Config


def setup(app: Sphinx):
    app.connect("config-inited", generate_module_docs)
    return {"version": "1.0"}


def generate_module_docs(app: Sphinx, conf: Config) -> None:
    """Generate FABulous configuration variable documentation."""
    try:
        conf_py_path: str = conf._raw_config["__file__"]
        doc_root_dir: Path = Path(conf_py_path).parent

        template_relpath: str = conf.templates_path[0]
        all_templates_path = doc_root_dir / template_relpath

        lookup = jinja2.FileSystemLoader(searchpath=all_templates_path)
        env = jinja2.Environment(loader=lookup)

        # Extract FABulous settings
        settings_vars = extract_fabulous_settings()
        cli_settables = extract_cli_settables()

        # Render documentation
        template = env.get_template("flow_variable.md.jinja")
        output = template.render(
            settings_vars=settings_vars,
            cli_settables=cli_settables,
        )

        # Write output to cli_doc folder
        output_file = doc_root_dir / "user_guide" / "cli_doc" / "fabulous_variable.md"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(output)

        print(f"Generated FABulous variable documentation: {output_file}")

    except Exception:
        print(traceback.format_exc())
        exit(-1)


def extract_field_info_from_ast(item: ast.AnnAssign) -> dict | None:
    """Extract field information from an AST AnnAssign node.

    Parameters
    ----------
    item : ast.AnnAssign
        The annotated assignment node to extract info from.

    Returns
    -------
    dict | None
        Dictionary with field info or None if not a valid field.
    """
    if not isinstance(item.target, ast.Name):
        return None

    field_name = item.target.id

    # Get type annotation as string
    field_type = (
        ast.unparse(item.annotation)
        if hasattr(ast, "unparse")
        else str(item.annotation)
    )

    # Simplify complex types
    if " | None" in field_type:
        field_type = field_type.replace(" | None", "")
    if "Optional[" in field_type:
        field_type = field_type.replace("Optional[", "").rstrip("]")

    # Simplify common type names
    type_simplifications = {
        "Path": "Path",
        "Version": "Version",
        "HDLType": "HDLType",
    }
    for key, val in type_simplifications.items():
        if key in field_type:
            field_type = val
            break

    if "tuple" in field_type.lower():
        field_type = "tuple"

    # Extract default value and description from Field() or direct assignment
    default = ""
    description = ""
    title = ""
    deprecated = False

    if item.value:
        if isinstance(item.value, ast.Constant):
            default = str(item.value.value)
        elif isinstance(item.value, ast.Call):
            # Check if it's a Field() call
            func_name = ""
            if isinstance(item.value.func, ast.Name):
                func_name = (
                    item.value.func.name
                    if hasattr(item.value.func, "name")
                    else item.value.func.id
                )
            elif isinstance(item.value.func, ast.Attribute):
                func_name = item.value.func.attr

            if func_name == "Field":
                for keyword in item.value.keywords:
                    if keyword.arg == "default" and isinstance(
                        keyword.value, ast.Constant
                    ):
                        default = str(keyword.value.value)
                    elif keyword.arg == "default_factory":
                        # Handle default_factory - show as "dynamic"
                        default = "(dynamic)"
                    elif keyword.arg == "description" and isinstance(
                        keyword.value, ast.Constant
                    ):
                        description = keyword.value.value
                    elif keyword.arg == "title" and isinstance(
                        keyword.value, ast.Constant
                    ):
                        title = keyword.value.value
                    elif keyword.arg == "deprecated":
                        deprecated = True

                # Check positional args for default
                if not default and item.value.args:
                    if isinstance(item.value.args[0], ast.Constant):
                        default = str(item.value.args[0].value)
            elif func_name == "Version":
                # Handle Version() calls
                if item.value.args and isinstance(item.value.args[0], ast.Constant):
                    default = item.value.args[0].value
        elif isinstance(item.value, ast.Attribute):
            # Handle enum values like HDLType.VERILOG
            if hasattr(ast, "unparse"):
                default = ast.unparse(item.value)
        elif isinstance(item.value, ast.Tuple):
            # Handle tuple defaults
            if hasattr(ast, "unparse"):
                default = ast.unparse(item.value)

    # Clean up description - remove extra whitespace
    if description:
        description = " ".join(description.split())

    return {
        "name": field_name,
        "type": field_type,
        "default": default,
        "description": description,
        "title": title,
        "deprecated": deprecated,
    }


def extract_fabulous_settings() -> dict:
    """Extract configuration variables from FABulousSettings class using AST parsing.

    Returns a dictionary with categorized settings variables with descriptions.
    Categories are determined by the 'title' field in Field() calls.
    Variables without a title are placed in the 'Miscellaneous' category.
    """
    # Parse the FABulousSettings file using AST (use absolute path)
    ext_file = Path(__file__).resolve()
    settings_file = (
        ext_file.parent.parent.parent.parent / "FABulous" / "FABulous_settings.py"
    )
    source = settings_file.read_text()
    tree = ast.parse(source)

    # Extract field information from class definition
    field_info_list = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "FABulousSettings":
            for item in node.body:
                if isinstance(item, ast.AnnAssign):
                    field_info = extract_field_info_from_ast(item)
                    if field_info and not field_info["deprecated"]:
                        field_info_list.append(field_info)

    # Dynamically categorize settings based on title field
    settings: dict[str, list] = {}

    for info in field_info_list:
        # Use title as category, default to "Miscellaneous" if no title
        category = info["title"] if info["title"] else "Miscellaneous"

        if category not in settings:
            settings[category] = []

        # Environment variable name (FAB_ prefix)
        env_var = f"FAB_{info['name'].upper()}"

        settings[category].append(
            {
                "name": info["name"],
                "env_var": env_var,
                "type": info["type"],
                "description": info["description"],
                "default": info["default"],
            }
        )

    # Sort categories to put Miscellaneous at the end
    sorted_settings = {}
    for key in sorted(settings.keys()):
        if key != "Miscellaneous":
            sorted_settings[key] = settings[key]
    if "Miscellaneous" in settings:
        sorted_settings["Miscellaneous"] = settings["Miscellaneous"]

    return sorted_settings


def extract_cli_settables() -> list:
    """Extract settable variables from FABulous_CLI using AST parsing.

    These are variables that can be set interactively using the `set` command.
    """
    ext_file = Path(__file__).resolve()
    cli_file = (
        ext_file.parent.parent.parent.parent
        / "FABulous"
        / "FABulous_CLI"
        / "FABulous_CLI.py"
    )

    settables = []

    try:
        source = cli_file.read_text()
        tree = ast.parse(source)

        # Look for self.add_settable(Settable(...)) calls
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Check if it's a Settable() call
                func_name = ""
                if isinstance(node.func, ast.Name):
                    func_name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    func_name = node.func.attr

                if func_name == "Settable":
                    settable_info = {"name": "", "type": "", "description": ""}

                    # Settable positional args: name, type, description, ...
                    if len(node.args) >= 1 and isinstance(node.args[0], ast.Constant):
                        settable_info["name"] = node.args[0].value
                    if len(node.args) >= 2:
                        if isinstance(node.args[1], ast.Name):
                            settable_info["type"] = node.args[1].id
                        elif isinstance(node.args[1], ast.Attribute):
                            settable_info["type"] = node.args[1].attr
                    if len(node.args) >= 3 and isinstance(node.args[2], ast.Constant):
                        settable_info["description"] = node.args[2].value

                    # Also check keyword arguments
                    for keyword in node.keywords:
                        if keyword.arg == "name":
                            if isinstance(keyword.value, ast.Constant):
                                settable_info["name"] = keyword.value.value
                        elif keyword.arg == "settable_type":
                            if isinstance(keyword.value, ast.Attribute):
                                settable_info["type"] = keyword.value.attr
                            elif isinstance(keyword.value, ast.Name):
                                settable_info["type"] = keyword.value.id
                        elif keyword.arg == "description":
                            if isinstance(keyword.value, ast.Constant):
                                settable_info["description"] = keyword.value.value

                    if settable_info["name"]:
                        settables.append(settable_info)

    except Exception as e:
        print(f"Warning: Could not parse CLI settables: {e}")
        # Fall back to hardcoded list
        settables = [
            {
                "name": "projectDir",
                "type": "Path",
                "description": "The directory of the project",
            },
            {
                "name": "csvFile",
                "type": "Path",
                "description": "The fabric CSV definition file",
            },
            {
                "name": "verbose",
                "type": "bool",
                "description": "Enable verbose output",
            },
            {
                "name": "force",
                "type": "bool",
                "description": "Force execution without confirmation",
            },
        ]

    return settables
