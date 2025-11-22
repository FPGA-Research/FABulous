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


def extract_fabulous_settings() -> dict:
    """Extract configuration variables from FABulousSettings class using AST parsing.

    Returns a dictionary with categorized settings variables with descriptions.
    """
    import ast
    import re

    # Parse the FABulousSettings file using AST (use absolute path)
    ext_file = Path(__file__).resolve()
    settings_file = ext_file.parent.parent.parent.parent / "FABulous" / "FABulous_settings.py"
    source = settings_file.read_text()
    tree = ast.parse(source)

    # Extract field information from class definition
    field_info_map = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "FABulousSettings":
            for item in node.body:
                if isinstance(item, ast.AnnAssign):
                    # Get field name
                    if isinstance(item.target, ast.Name):
                        field_name = item.target.id

                        # Get type annotation as string
                        field_type = ast.unparse(item.annotation) if hasattr(ast, 'unparse') else str(item.annotation)
                        # Simplify complex types - handle unions first
                        if " | None" in field_type or "Union" in field_type:
                            # Remove " | None" or just keep the main type
                            field_type = field_type.replace(" | None", "").replace("Optional[", "").rstrip("]")
                        # Now apply simple type mappings
                        if "Path" in field_type:
                            field_type = "Path"
                        elif "Version" in field_type:
                            field_type = "Version"
                        elif "HDLType" in field_type:
                            field_type = "HDLType"
                        elif "tuple" in field_type or "Tuple" in field_type:
                            field_type = "tuple"
                        elif field_type not in ("int", "bool", "str"):
                            # Keep as is if it's a basic type already
                            if "int" not in field_type and "bool" not in field_type and "str" not in field_type:
                                pass

                        # Get default value if it exists
                        default = ""
                        if item.value:
                            if isinstance(item.value, ast.Constant):
                                default = str(item.value.value)
                            elif isinstance(item.value, ast.Call):
                                # Handle Field() calls - extract the 'default' keyword arg
                                for keyword in item.value.keywords:
                                    if keyword.arg == "default" and isinstance(keyword.value, ast.Constant):
                                        default = str(keyword.value.value)
                                        break
                                # If no default found in keywords, check positional args (unlikely for Field)
                                if not default and item.value.args:
                                    if isinstance(item.value.args[0], ast.Constant):
                                        default = str(item.value.args[0].value)
                                # If still no default, leave empty (will show as "-")
                                if not default:
                                    default = ""

                        # Extract description from Field() call
                        description = ""
                        if isinstance(item.value, ast.Call):
                            # Look for description keyword argument
                            for keyword in item.value.keywords:
                                if keyword.arg == "description" and isinstance(keyword.value, ast.Constant):
                                    description = keyword.value.value
                                    break

                        field_info_map[field_name] = {
                            "type": field_type,
                            "description": description,
                            "default": default,
                        }

    # Get field information from pydantic model
    settings = {}

    # Categorize settings
    categories = {
        "Tool Paths": [
            "yosys_path", "nextpnr_path", "iverilog_path", "vvp_path",
            "ghdl_path", "openroad_path", "klayout_path", "fabulator_root",
            "oss_cad_suite"
        ],
        "Project Settings": [
            "proj_dir", "proj_lang", "models_pack", "proj_version",
            "proj_version_created", "user_config_dir"
        ],
        "GDS Settings": [
            "pdk_root", "pdk", "fabric_die_area", "switch_matrix_debug_signal"
        ],
        "CLI Settings": [
            "editor", "verbose", "debug"
        ],
    }

    for category, field_names in categories.items():
        settings[category] = []
        for field_name in field_names:
            if field_name not in field_info_map:
                continue

            info = field_info_map[field_name]

            # Environment variable name (FAB_ prefix)
            env_var = f"FAB_{field_name.upper()}"

            settings[category].append({
                "name": field_name,
                "env_var": env_var,
                "type": info["type"],
                "description": info["description"],
                "default": info["default"],
            })

    return settings


def extract_cli_settables() -> list:
    """Extract settable variables from FABulous_CLI.

    These are variables that can be set interactively using the `set` command.
    """
    # Define the known settables from FABulous_CLI.__init__
    # These are added via self.add_settable(Settable(...))
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
