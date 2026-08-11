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

This extension auto-discovers all steps and flows from the gds_generator module and
extracts their configuration variables for documentation.
"""

from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
import re
from typing import TYPE_CHECKING, Any

from _doc_common import render_generated_doc

if TYPE_CHECKING:
    from sphinx.application import Sphinx
    from sphinx.config import Config

logger = logging.getLogger(__name__)

# librelane's `type_repr_md` embeds MyST ``{class}`Name <module.path>``` cross
# references; in a generated table those resolve to nothing, so reduce a type to
# its bare display name. (Descriptions are left alone — they contain literal
# `{...}` placeholders that this would mangle.)
_TYPE_ROLE_RE = re.compile(r"\{[a-z]+\}`([^`<]+?)\s*(?:<[^>]+>)?`")


def setup(app: Sphinx) -> dict[str, str]:  # noqa: ARG001
    """Register the GDS variable doc generator on `config-inited`."""
    app.connect("config-inited", generate_gds_variable_docs)
    return {"version": "1.0", "parallel_read_safe": True}


def generate_gds_variable_docs(app: Sphinx, conf: Config) -> None:  # noqa: ARG001
    """Render the GDS flow variable reference into `generated_doc/`."""
    output_file = render_generated_doc(
        conf,
        template_name="gds_variable.md.jinja",
        output_name="gds_variable.md",
        context={"gds_vars": extract_gds_variables()},
    )
    logger.info("Generated GDS variable documentation: %s", output_file)


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

    looks_like_abs_path = default.startswith(("/", "~")) or (
        len(default) > 2 and default[1] == ":"
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
        except (ValueError, TypeError):
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
        Human-readable category name.
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
    return " ".join(name.split())


def extract_variables_from_class(
    cls: type, gds_vars: dict[str, list[dict[str, Any]]], category: str
) -> None:
    """Extract configuration variables from a class with config_vars attribute.

    Parameters
    ----------
    cls : type
        The class to extract variables from.
    gds_vars : dict[str, list[dict[str, Any]]]
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

        type_str = _TYPE_ROLE_RE.sub(r"\1", var.type_repr_md(for_document=True)).strip()

        # Get default value
        default = ""
        if var.default is not None:
            default = str(var.default)

        default = shorten_path_default(default, type_str)

        if len(default) > 50:
            default = default[:47] + "..."

        # Get description (left verbatim apart from whitespace: librelane
        # descriptions mix literal `{...}` placeholders with backticks, so a
        # blanket role strip would corrupt them).
        description = " ".join((var.description or "").split())

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
        The package name to search.

    Returns
    -------
    list[tuple[str, type]]
        List of (class_name, class) tuples for classes with config_vars.
    """
    classes_found: list[tuple[str, type]] = []

    package = importlib.import_module(package_name)

    package_path = getattr(package, "__path__", None)
    if package_path is None:
        return classes_found

    for _, module_name, _ in pkgutil.iter_modules(package_path):
        full_module_name = f"{package_name}.{module_name}"

        module = importlib.import_module(full_module_name)

        # Find all classes in the module that have config_vars
        for name, obj in inspect.getmembers(module, inspect.isclass):
            # Only include classes defined in this module (not imported)
            if obj.__module__ != full_module_name:
                continue

            # Check if class has config_vars attribute
            if hasattr(obj, "config_vars") and obj.config_vars:
                classes_found.append((name, obj))

    return classes_found


def extract_gds_variables() -> dict[str, list[dict[str, Any]]]:
    """Extract GDS flow configuration variables by auto-discovering all steps and flows.

    Auto-discovers all classes with config_vars from:
    - FABulous.fabric_generator.gds_generator.steps
    - FABulous.fabric_generator.gds_generator.flows

    Returns
    -------
    dict[str, list[dict[str, Any]]]
        Dictionary with categorized GDS variables.
    """
    gds_vars: dict[str, list[dict[str, Any]]] = {}

    # Auto-discover from steps package
    steps_classes = discover_classes_with_config_vars(
        "fabulous.fabric_generator.gds_generator.steps"
    )
    for class_name, cls in steps_classes:
        category = class_name_to_category(class_name)
        extract_variables_from_class(cls, gds_vars, category)

    # Auto-discover from flows package
    flows_classes = discover_classes_with_config_vars(
        "fabulous.fabric_generator.gds_generator.flows"
    )
    for class_name, cls in flows_classes:
        category = class_name_to_category(class_name)
        extract_variables_from_class(cls, gds_vars, category)

    return dict(sorted(gds_vars.items()))
