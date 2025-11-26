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

"""Sphinx extension to auto-generate GDS flow variable documentation.

This extension auto-discovers all steps and flows from the gds_generator module
and extracts their configuration variables for documentation.
"""

import importlib
import inspect
import pkgutil
import re
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
    if not default:
        return default

    is_path_type = "Path" in type_str or "path" in type_str.lower()
    looks_like_path = ("/" in default or "\\" in default) and len(default) > 30

    looks_like_abs_path = (
        default.startswith("/")
        or default.startswith("~")
        or (len(default) > 2 and default[1] == ":")
    )

    if (is_path_type or looks_like_abs_path) and looks_like_path:
        from pathlib import PurePosixPath, PureWindowsPath

        try:
            if "/" in default:
                path = PurePosixPath(default)
            else:
                path = PureWindowsPath(default)

            filename = path.name
            if filename:
                return f"`<resource>`/{filename}"
        except Exception:
            pass

    return default


def class_name_to_category(class_name: str) -> str:
    """Convert a class name to a human-readable category name.

    Parameters
    ----------
    class_name : str
        The class name (e.g., 'FABulousTileIOPlacement', 'AutoEcoDiodeInsertion')

    Returns
    -------
    str
        Human-readable category name (e.g., 'Tile I/O Placement', 'Auto Eco Diode Insertion')
    """
    # Remove common prefixes
    name = class_name
    for prefix in ["FABulous", "Custom"]:
        name = name.removeprefix(prefix)

    # Insert spaces before capital letters and handle acronyms
    # First, handle known acronyms by adding markers
    acronyms = ["IO", "PDN", "ECO", "NLP", "PDK"]
    for acronym in acronyms:
        name = name.replace(acronym, f"_{acronym}_")

    # Insert spaces before remaining capital letters
    name = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)

    # Clean up markers and extra spaces
    name = name.replace("_", " ")
    name = " ".join(name.split())

    return name


def extract_variables_from_class(cls, gds_vars: dict, category: str) -> None:
    """Extract configuration variables from a class with config_vars attribute.

    Parameters
    ----------
    cls : type
        The class to extract variables from.
    gds_vars : dict
        Dictionary to store extracted variables by category.
    category : str
        The category name for the variables.
    """
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

        default = shorten_path_default(default, type_str)

        if len(default) > 50:
            default = default[:47] + "..."

        # Get description
        description = var.description or ""
        description = " ".join(description.split())

        gds_vars[category].append(
            {
                "name": var.name,
                "type": type_str,
                "default": default,
                "description": description,
            }
        )


def discover_classes_with_config_vars(package_name: str) -> list[tuple[str, type]]:
    """Discover all classes with config_vars attribute in a package.

    Parameters
    ----------
    package_name : str
        The package name to search (e.g., 'FABulous.fabric_generator.gds_generator.steps')

    Returns
    -------
    list[tuple[str, type]]
        List of (class_name, class) tuples for classes with config_vars.
    """
    classes_found = []

    try:
        package = importlib.import_module(package_name)
    except ImportError as e:
        print(f"Warning: Could not import package {package_name}: {e}")
        return classes_found

    package_path = getattr(package, "__path__", None)
    if package_path is None:
        return classes_found

    for _, module_name, _ in pkgutil.iter_modules(package_path):
        full_module_name = f"{package_name}.{module_name}"

        try:
            module = importlib.import_module(full_module_name)
        except ImportError as e:
            print(f"Warning: Could not import module {full_module_name}: {e}")
            continue

        # Find all classes in the module that have config_vars
        for name, obj in inspect.getmembers(module, inspect.isclass):
            # Only include classes defined in this module (not imported)
            if obj.__module__ != full_module_name:
                continue

            # Check if class has config_vars attribute
            if hasattr(obj, "config_vars") and obj.config_vars:
                classes_found.append((name, obj))

    return classes_found


def extract_gds_variables() -> dict:
    """Extract GDS flow configuration variables by auto-discovering all steps and flows.

    Auto-discovers all classes with config_vars from:
    - FABulous.fabric_generator.gds_generator.steps
    - FABulous.fabric_generator.gds_generator.flows

    Returns
    -------
    dict
        Dictionary with categorized GDS variables.
    """
    gds_vars: dict[str, list[dict]] = {}

    # Auto-discover from steps package
    steps_classes = discover_classes_with_config_vars(
        "FABulous.fabric_generator.gds_generator.steps"
    )
    for class_name, cls in steps_classes:
        category = class_name_to_category(class_name)
        try:
            extract_variables_from_class(cls, gds_vars, category)
        except Exception as e:
            print(f"Warning: Could not extract variables from {class_name}: {e}")

    # Auto-discover from flows package
    flows_classes = discover_classes_with_config_vars(
        "FABulous.fabric_generator.gds_generator.flows"
    )
    for class_name, cls in flows_classes:
        category = class_name_to_category(class_name)
        try:
            extract_variables_from_class(cls, gds_vars, category)
        except Exception as e:
            print(f"Warning: Could not extract variables from {class_name}: {e}")

    # Sort categories for consistent output
    sorted_vars = dict(sorted(gds_vars.items()))

    return sorted_vars
