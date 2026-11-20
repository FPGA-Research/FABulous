"""Sphinx extension to auto-generate FABulous configuration variable documentation."""

from __future__ import annotations

import ast
import logging
from importlib.metadata import version as meta_version
from pathlib import Path
from typing import TYPE_CHECKING

from _doc_common import render_generated_doc
from packaging.version import Version
from pydantic_core import PydanticUndefined

if TYPE_CHECKING:
    from sphinx.application import Sphinx
    from sphinx.config import Config

logger = logging.getLogger(__name__)

# Base project directory resolved from this extension's location
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# Scope labels used to categorize settings by their variable name prefix.
_SCOPE_GLOBAL = "Global Environment Variables"
_SCOPE_PROJECT = "Project Specific Environment Variables"

# Display order for scopes (global before project-specific).
_SCOPE_ORDER = [_SCOPE_GLOBAL, _SCOPE_PROJECT]

# Installed FABulous package version; used to detect build-specific version defaults.
_INSTALLED_VERSION = meta_version("FABulous-FPGA")


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
    app.connect("config-inited", generate_module_docs)
    return {"version": "1.0", "parallel_read_safe": True}


def generate_module_docs(app: Sphinx, conf: Config) -> None:  # noqa: ARG001
    """Render the FABulous configuration-variable reference into `generated_doc/`."""
    output_file = render_generated_doc(
        conf,
        template_name="flow_variable.md.jinja",
        output_name="fabulous_variable.md",
        context={
            "settings_vars": extract_fabulous_settings(),
            "cli_settables": extract_cli_settables(),
        },
    )
    logger.info("Generated FABulous variable documentation: %s", output_file)


def _get_call_func_name(node: ast.Call) -> str:
    """Return the simple function name from a Call node.

    Handles both direct calls (`Name`) and attribute calls (`Attribute`).

    Parameters
    ----------
    node : ast.Call
        The call node to inspect.

    Returns
    -------
    str
        The function/attribute name, or empty string if unresolvable.
    """
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def _simplify_annotation(annotation: object) -> str:
    """Return a short, example-friendly type name for a field annotation.

    Parameters
    ----------
    annotation : object
        The Pydantic field annotation.

    Returns
    -------
    str
        A simplified type label (e.g. `Path`, `str`, `tuple`).
    """
    text = str(annotation).replace(" | None", "")
    if text.startswith("Optional["):
        text = text.removeprefix("Optional[").removesuffix("]")
    for known in ("Path", "Version", "HDLType"):
        if known in text:
            return known
    if "tuple" in text.lower():
        return "tuple"
    # Use __name__ only when the annotation is a plain class (not a generic
    # alias such as Union whose str() already gives the simplified text).
    if isinstance(annotation, type):
        return annotation.__name__
    return text


def _field_default(field: object) -> str:
    """Return a display string for a Pydantic field's default.

    Parameters
    ----------
    field : object
        A Pydantic `FieldInfo`.

    Returns
    -------
    str
        The default rendered for documentation (`(dynamic)` for computed
        defaults, `None` for a `None` default, otherwise the string value).
    """
    if field.default_factory is not None:
        return "(dynamic)"
    default = field.default
    if default is PydanticUndefined:
        return ""
    if default is None:
        return "None"
    # Version defaults derived from the installed package version are build
    # specific; show them as dynamic rather than leaking a dev version string.
    if isinstance(default, Version) and str(default) == _INSTALLED_VERSION:
        return "(dynamic)"
    return str(default)


def get_user_value_example(field_type: str) -> str:
    """Return an example user value string based on field type.

    Parameters
    ----------
    field_type : str
        The type of the field.

    Returns
    -------
    str
        An example value string for the User Value column.
    """
    type_lower = field_type.lower()

    if "hdltype" in type_lower:
        return "`verilog`, `vhdl`, `sv`"
    if type_lower == "bool":
        return "`true` / `false`"
    if type_lower == "int":
        return "`1`, `2`"
    if "path" in type_lower:
        return "`/path/to/file`"
    if "version" in type_lower:
        return "`1.2.3`"
    if "tuple" in type_lower:
        return "`[0, 0, 1000, 1000]`"
    if type_lower == "str":
        return "any string"

    return "-"


def _sort_settings_by_scope(
    settings: dict[str, dict[str, list]],
) -> dict[str, dict[str, list]]:
    """Return *settings* ordered by `_SCOPE_ORDER` with sorted subcategories.

    Within each scope the subcategories are sorted alphabetically, except
    "General" which is placed last (it acts as the catch-all bucket).

    Parameters
    ----------
    settings : dict[str, dict[str, list]]
        Unsorted settings produced by the categorization loop.

    Returns
    -------
    dict[str, dict[str, list]]
        A new dictionary with deterministic ordering.
    """
    result: dict[str, dict[str, list]] = {}

    for scope in _SCOPE_ORDER:
        if scope not in settings:
            continue
        subcats = settings[scope]
        sorted_subcats = dict(
            sorted((k, v) for k, v in subcats.items() if k != "General")
        )
        general = subcats.get("General")
        if general is not None:
            sorted_subcats["General"] = general
        result[scope] = sorted_subcats

    return result


def extract_fabulous_settings() -> dict[str, dict[str, list]]:
    """Extract settings from `FABulousSettings.model_fields` (no AST parsing).

    Returns
    -------
    dict[str, dict[str, list]]
        Settings grouped by scope (global vs project) then subcategory.
    """
    from fabulous.fabulous_settings import FABulousSettings

    env_prefix = FABulousSettings.model_config.get("env_prefix", "")
    settings: dict[str, dict[str, list]] = {}

    for name, field in FABulousSettings.model_fields.items():
        if field.deprecated:
            continue
        field_type = _simplify_annotation(field.annotation)
        scope = _SCOPE_PROJECT if name.startswith("proj_") else _SCOPE_GLOBAL
        subcategory = field.title or "General"

        settings.setdefault(scope, {}).setdefault(subcategory, []).append(
            {
                "name": name,
                "env_var": f"{env_prefix}{name}".upper(),
                "type": field_type,
                "description": " ".join((field.description or "").split()),
                "default": _field_default(field),
                "user_value": get_user_value_example(field_type),
            }
        )

    return _sort_settings_by_scope(settings)


def extract_cli_settables() -> list:
    """Extract settable variables from FABulousREPL using AST parsing.

    These are variables that can be set interactively using the `set` command.

    Returns
    -------
    list
        List of settable variable dictionaries.
    """
    cli_file = _PROJECT_ROOT / "fabulous" / "fabulous_repl" / "fabulous_repl.py"

    settables: list = []

    tree = ast.parse(cli_file.read_text())

    # Look for self.add_settable(Settable(...)) calls
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _get_call_func_name(node) == "Settable":
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
                if keyword.arg == "name" and isinstance(keyword.value, ast.Constant):
                    settable_info["name"] = keyword.value.value
                elif keyword.arg == "settable_type":
                    if isinstance(keyword.value, ast.Attribute):
                        settable_info["type"] = keyword.value.attr
                    elif isinstance(keyword.value, ast.Name):
                        settable_info["type"] = keyword.value.id
                elif keyword.arg == "description" and isinstance(
                    keyword.value, ast.Constant
                ):
                    settable_info["description"] = keyword.value.value

            if settable_info["name"]:
                settables.append(settable_info)

    return settables
