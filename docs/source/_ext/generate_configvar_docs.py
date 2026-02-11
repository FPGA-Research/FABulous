"""Sphinx extension to auto-generate FABulous configuration variable documentation."""

import ast
import logging
from pathlib import Path

import jinja2
from sphinx.application import Sphinx
from sphinx.config import Config

logger = logging.getLogger(__name__)

# Base project directory resolved from this extension's location
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


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
    return {"version": "1.0"}


def generate_module_docs(app: Sphinx, conf: Config) -> None:  # noqa: ARG001
    """Generate FABulous configuration variable documentation.

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

        # Extract FABulous settings
        settings_vars = extract_fabulous_settings()
        cli_settables = extract_cli_settables()

        # Render documentation
        template = env.get_template("flow_variable.md.jinja")
        output = template.render(
            settings_vars=settings_vars,
            cli_settables=cli_settables,
        )

        # Write output to generated_doc folder (gitignored)
        output_file = doc_root_dir / "generated_doc" / "fabulous_variable.md"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(output)

        logger.info("Generated FABulous variable documentation: %s", output_file)

    except (OSError, jinja2.TemplateError):
        logger.exception("Failed to generate FABulous variable documentation")
        raise SystemExit(-1) from None


def _get_call_func_name(node: ast.Call) -> str:
    """Return the simple function name from a Call node.

    Handles both direct calls (``Name``) and attribute calls (``Attribute``).

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
    field_type = ast.unparse(item.annotation)

    # Simplify complex types
    if " | None" in field_type:
        field_type = field_type.replace(" | None", "")
    if "Optional[" in field_type:
        field_type = field_type.replace("Optional[", "").rstrip("]")

    # If the type contains a known domain type, simplify to just that type name
    for known_type in ("Path", "Version", "HDLType"):
        if known_type in field_type:
            field_type = known_type
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
            func_name = _get_call_func_name(item.value)

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
                if (
                    not default
                    and item.value.args
                    and isinstance(item.value.args[0], ast.Constant)
                ):
                    default = str(item.value.args[0].value)
            elif func_name == "Version":
                # Handle Version() calls
                if item.value.args and isinstance(item.value.args[0], ast.Constant):
                    default = item.value.args[0].value
        elif isinstance(item.value, ast.Attribute):
            # Handle enum values like HDLType.VERILOG
            default = ast.unparse(item.value)
        elif isinstance(item.value, ast.Tuple):
            # Handle tuple defaults
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


def extract_fabulous_settings() -> dict:
    """Extract configuration variables from FABulousSettings class using AST parsing.

    Returns a dictionary with categorized settings variables with descriptions.
    Categories are determined by the 'title' field in Field() calls. Variables without a
    title are placed in the 'Miscellaneous' category.

    Returns
    -------
    dict
        Dictionary of settings by category.
    """
    settings_file = _PROJECT_ROOT / "fabulous" / "fabulous_settings.py"
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
        category = info["title"] or "Miscellaneous"

        settings.setdefault(category, []).append(
            {
                "name": info["name"],
                "env_var": f"FAB_{info['name'].upper()}",
                "type": info["type"],
                "description": info["description"],
                "default": info["default"],
                "user_value": get_user_value_example(info["type"]),
            }
        )

    # Sort categories alphabetically, but keep "Miscellaneous" at the end
    misc = settings.pop("Miscellaneous", None)
    sorted_settings = dict(sorted(settings.items()))
    if misc is not None:
        sorted_settings["Miscellaneous"] = misc

    return sorted_settings


def extract_cli_settables() -> list:
    """Extract settable variables from FABulous_CLI using AST parsing.

    These are variables that can be set interactively using the `set` command.

    Returns
    -------
    list
        List of settable variable dictionaries.
    """
    cli_file = _PROJECT_ROOT / "fabulous" / "fabulous_cli" / "fabulous_cli.py"

    settables: list = []

    try:
        source = cli_file.read_text()
        tree = ast.parse(source)

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
                    if keyword.arg == "name" and isinstance(
                        keyword.value, ast.Constant
                    ):
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

    except (OSError, SyntaxError):
        logger.warning("Could not parse CLI settables")
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
