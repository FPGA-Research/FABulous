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

"""Sphinx extension to auto-generate GDS flow variable documentation."""

import traceback
from pathlib import Path

import jinja2
from sphinx.application import Sphinx
from sphinx.config import Config


def setup(app: Sphinx):
    app.connect("config-inited", generate_gds_variable_docs)
    return {"version": "1.0"}


def generate_gds_variable_docs(app: Sphinx, conf: Config) -> None:
    """Generate GDS flow variable documentation."""
    try:
        conf_py_path: str = conf._raw_config["__file__"]
        doc_root_dir: Path = Path(conf_py_path).parent

        template_relpath: str = conf.templates_path[0]
        all_templates_path = doc_root_dir / template_relpath

        lookup = jinja2.FileSystemLoader(searchpath=all_templates_path)
        env = jinja2.Environment(loader=lookup)

        # Extract GDS flow variables
        gds_vars = extract_gds_variables()

        # Render documentation
        template = env.get_template("gds_variable.md.jinja")
        output = template.render(gds_vars=gds_vars)

        # Write output to building_doc folder
        output_file = doc_root_dir / "user_guide" / "building_doc" / "gds_variable.md"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(output)

        print(f"Generated GDS variable documentation: {output_file}")

    except Exception:
        print(traceback.format_exc())
        exit(-1)


def shorten_path_default(default: str, type_str: str) -> str:
    """Shorten path defaults to show <resource>/[filename] format.

    Parameters
    ----------
    default : str
        The default value string.
    type_str : str
        The type string of the variable.

    Returns
    -------
    str
        Shortened path or original default.
    """
    # Check if this looks like a path (contains / or \ and type contains Path)
    if not default:
        return default

    is_path_type = "Path" in type_str or "path" in type_str.lower()
    looks_like_path = ("/" in default or "\\" in default) and len(default) > 30

    # Also check if it looks like an absolute path even without Path type
    looks_like_abs_path = (
        default.startswith("/")
        or default.startswith("~")
        or (len(default) > 2 and default[1] == ":")  # Windows path like C:\
    )

    if (is_path_type or looks_like_abs_path) and looks_like_path:
        # Extract just the filename
        from pathlib import PurePosixPath, PureWindowsPath

        try:
            # Try to parse as a path
            if "/" in default:
                path = PurePosixPath(default)
            else:
                path = PureWindowsPath(default)

            filename = path.name
            if filename:
                # Use backticks to escape <resource> so it's not interpreted as HTML
                return f"`<resource>`/{filename}"
        except Exception:
            pass

    return default


def extract_gds_variables() -> dict:
    """Extract GDS flow configuration variables from librelane Variable definitions.

    Returns a dictionary with categorized GDS variables.
    """
    gds_vars: dict[str, list[dict]] = {}

    # Helper function to extract variables from a step/flow class
    def extract_from_class(cls, category: str) -> None:
        if not hasattr(cls, "config_vars"):
            return

        if category not in gds_vars:
            gds_vars[category] = []

        seen_names = {v["name"] for v in gds_vars[category]}

        for var in cls.config_vars:
            if var.name in seen_names:
                continue
            seen_names.add(var.name)

            # Get type as string
            var_type = var.type
            if hasattr(var_type, "__name__"):
                type_str = var_type.__name__
            elif hasattr(var_type, "__origin__"):
                # Handle generic types like Optional, Union
                type_str = str(var_type).replace("typing.", "")
            else:
                type_str = str(var_type)

            # Clean up type string
            type_str = type_str.replace("decimal.Decimal", "Decimal")
            type_str = type_str.replace("<class '", "").replace("'>", "")

            # Get default value
            default = ""
            if var.default is not None:
                default = str(var.default)

            # Shorten path defaults to <resource>/[filename]
            default = shorten_path_default(default, type_str)

            # Truncate remaining long defaults
            if len(default) > 50:
                default = default[:47] + "..."

            # Get description
            description = var.description or ""
            # Clean up multiline descriptions
            description = " ".join(description.split())

            gds_vars[category].append(
                {
                    "name": var.name,
                    "type": type_str,
                    "default": default,
                    "description": description,
                }
            )

    # Import and extract variables from each module separately to handle import errors
    try:
        from FABulous.fabric_generator.gds_generator.steps.tile_IO_placement import (
            FABulousTileIOPlacement,
        )

        extract_from_class(FABulousTileIOPlacement, "Tile I/O Placement")
    except Exception as e:
        print(f"Warning: Could not import FABulousTileIOPlacement: {e}")

    try:
        from FABulous.fabric_generator.gds_generator.steps.custom_pdn import (
            CustomGeneratePDN,
        )

        extract_from_class(CustomGeneratePDN, "Power Distribution Network")
    except Exception as e:
        print(f"Warning: Could not import CustomGeneratePDN: {e}")

    try:
        from FABulous.fabric_generator.gds_generator.steps.add_buffer import AddBuffers

        extract_from_class(AddBuffers, "Buffer Insertion")
    except Exception as e:
        print(f"Warning: Could not import AddBuffers: {e}")

    try:
        from FABulous.fabric_generator.gds_generator.steps.fabric_IO_placement import (
            FABulousFabricIOPlacement,
        )

        extract_from_class(FABulousFabricIOPlacement, "Fabric I/O Placement")
    except Exception as e:
        print(f"Warning: Could not import FABulousFabricIOPlacement: {e}")

    # Extract tile optimisation variables directly from the var list
    try:
        # Import the variable list directly instead of the class
        # to avoid the AutoEcoDiodeInsertion import error
        import ast
        from pathlib import Path

        ext_file = Path(__file__).resolve()
        tile_opt_file = (
            ext_file.parent.parent.parent.parent
            / "FABulous"
            / "fabric_generator"
            / "gds_generator"
            / "steps"
            / "tile_optimisation.py"
        )
        source = tile_opt_file.read_text()

        # Extract Variable definitions using AST
        tree = ast.parse(source)
        tile_opt_vars = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "var":
                        if isinstance(node.value, ast.List):
                            for elt in node.value.elts:
                                if isinstance(elt, ast.Call):
                                    var_info = extract_variable_from_ast(elt)
                                    if var_info:
                                        tile_opt_vars.append(var_info)

        if tile_opt_vars:
            gds_vars["Tile Optimisation"] = tile_opt_vars
    except Exception as e:
        print(f"Warning: Could not extract tile optimisation variables: {e}")

    # Try to extract flow-level variables
    try:
        from FABulous.fabric_generator.gds_generator.flows.fabric_macro_flow import (
            FABulousFabricMacroFlow,
        )

        extract_from_class(FABulousFabricMacroFlow, "Fabric Macro Flow")
    except Exception as e:
        print(f"Warning: Could not import FABulousFabricMacroFlow: {e}")

    return gds_vars


def extract_variable_from_ast(call_node: "ast.Call") -> dict | None:
    """Extract Variable information from an AST Call node."""
    import ast

    if not call_node.args:
        return None

    # First arg is the variable name
    if isinstance(call_node.args[0], ast.Constant):
        name = call_node.args[0].value
    else:
        return None

    # Second arg is the type
    type_str = "unknown"
    if len(call_node.args) > 1:
        type_str = (
            ast.unparse(call_node.args[1]) if hasattr(ast, "unparse") else "unknown"
        )

    # Third arg is description
    description = ""
    if len(call_node.args) > 2:
        if isinstance(call_node.args[2], ast.Constant):
            description = call_node.args[2].value
            description = " ".join(description.split())

    # Extract default from keyword args
    default = ""
    for keyword in call_node.keywords:
        if keyword.arg == "default":
            if isinstance(keyword.value, ast.Constant):
                default = str(keyword.value.value)
            else:
                default = ast.unparse(keyword.value) if hasattr(ast, "unparse") else ""
            if len(default) > 50:
                default = default[:47] + "..."

    return {
        "name": name,
        "type": type_str,
        "default": default,
        "description": description,
    }
