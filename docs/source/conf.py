# Configuration file for the Sphinx documentation builder.

import sys
from importlib import import_module
from pathlib import Path

_source_root = Path(__file__).resolve().parent
if _source_root.as_posix() not in sys.path:
    sys.path.insert(0, _source_root.as_posix())

from conf_helper import get_display_version, get_version

# -- Project information

project = "FABulous: An easy-to-use, silicon-proven (e)FPGA generator with an integrated CAD toolchain 🏗️"
copyright = "2021, University of Manchester"
author = "Jing, Nguyen, Bea, Bardia, Dirk"

version = get_version()
release = version
display_version = get_display_version(version)
project_name = "FABulous"
project_tagline = "An easy-to-use, silicon-proven (e)FPGA generator with an integrated CAD toolchain 🏗️"


# -- General configuration

# Ensure the repository root is importable so the `fabulous` package and the
# docs helper modules (`docs.source.*`) resolve as proper packages.
_repo_root = Path(__file__).resolve().parents[2].as_posix()
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

# Add _ext directory to path for custom extensions
_ext_dir = Path(__file__).resolve().parent / "_ext"
if _ext_dir.as_posix() not in sys.path:
    sys.path.insert(0, _ext_dir.as_posix())

prepare_autoapi_jinja_env = import_module(
    "docstring_renderer"
).prepare_autoapi_jinja_env
format_annotation_for_rst = import_module(
    "docstring_renderer"
).format_annotation_for_rst

extensions = [
    # Core Sphinx extensions (scikit-learn style)
    "sphinx.ext.autodoc",
    "sphinx.ext.duration",
    "sphinx.ext.doctest",
    "sphinx.ext.intersphinx",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.imgconverter",
    # Modern documentation automation
    "autoapi.extension",  # Keep existing AutoAPI
    # Enhanced documentation features (scikit-learn additions)
    "myst_parser",  # Markdown support
    "sphinx_design",  # Modern UI components
    "sphinxext.opengraph",  # Social media cards
    "sphinx_copybutton",  # Copy code button
    "sphinx_remove_toctrees",  # Clean up AutoAPI navigation noise
    "sphinx_prompt",
    # Utility extensions
    "sphinxcontrib.bibtex",
    "sphinx_llm.txt",
    "sphinxcontrib.mermaid",
    # Custom FABulous extensions
    "generate_cli_docs",
    "generate_configvar_docs",
    "generate_gds_variable_docs",
]

myst_enable_extensions = [
    "colon_fence",
]

intersphinx_mapping = {
    "python": ("https://docs.python.org/3/", None),
    "sphinx": ("https://www.sphinx-doc.org/en/master/", None),
    "cmd2": ("https://cmd2.readthedocs.io/en/latest/", None),
    "numpy": ("https://numpy.org/doc/stable/", None),
    "pandas": ("https://pandas.pydata.org/docs/", None),
    "requests": ("https://docs.python-requests.org/en/master/", None),
    "pydantic": ("https://docs.pydantic.dev/latest/", None),
    # Additional scikit-learn style mappings
    "scipy": ("https://docs.scipy.org/doc/scipy/", None),
    "matplotlib": ("https://matplotlib.org/stable/", None),
    # GDS-flow dependencies whose types appear in the gds_generator docstrings.
    "librelane": ("https://librelane.readthedocs.io/en/latest/", None),
    "packaging": ("https://packaging.pypa.io/en/stable/", None),
    "networkx": ("https://networkx.org/documentation/stable/", None),
}

# Enable cross-references within the project
autodoc_typehints_format = "short"
intersphinx_disabled_domains = ["std"]

# Make Sphinx resolve all cross-references
nitpicky = False  # Disabled to avoid noisy warnings, type aliases still work
python_use_unqualified_type_names = True

# Type alias mappings for common types that cause reference warnings
autodoc_type_aliases = {
    "optional": "typing.Optional",
    "Path": "pathlib.Path",
    "Object": "object",
    "callable": "typing.Callable",
    "Ellipsis": "type(Ellipsis)",
}

# Add additional paths for module resolution
add_module_names = False

templates_path = ["_templates"]

# FABulous package is installed as a dependency in the docs environment

napoleon_google_docstring = False
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = False
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = True
napoleon_use_admonition_for_examples = False
napoleon_use_admonition_for_notes = False
napoleon_use_admonition_for_references = False
napoleon_use_ivar = (
    True  # Use :ivar: instead of .. attribute:: to avoid duplicate warnings
)
napoleon_use_param = True
napoleon_use_rtype = True
napoleon_preprocess_types = False
napoleon_type_aliases = None
napoleon_attr_annotations = True
napoleon_custom_sections = [
    ("Command line arguments", "Parameters"),
    ("Params", "Parameters"),
    ("Verilog", "Other"),
    ("VHDL", "Other"),
]

# No autodoc_mock_imports: the docs environment installs `fabulous-fpga` with its
# full dependency set, and AutoAPI parses sources statically, so nothing needs
# mocking. (Add a name here only if a real import genuinely fails in the build.)

# Configure autodoc to avoid dataclass field duplication
autodoc_default_options = {
    "members": True,
    "undoc-members": False,
    "show-inheritance": True,
    "special-members": False,
    "inherited-members": False,
}

# Prevent autodoc from automatically documenting modules
autodoc_member_order = "alphabetical"

# Render type hints in the parameter descriptions, not the signature: keeps
# AutoAPI signatures readable and avoids unresolved fully-qualified type refs.
autodoc_typehints = "description"
autodoc_typehints_description_target = "documented"
autodoc_preserve_defaults = True
autodoc_class_signature = "mixed"
autodoc_inherit_docstrings = True

# Configuration for sphinx-autodoc-typehints extension
typehints_fully_qualified = False  # Use short names when possible
typehints_document_rtype = False  # Keep return types in the signature only
typehints_use_signature = True  # Show types in signature
typehints_use_signature_return = True  # Show return types in signature
typehints_use_rtype = False  # Do not add return types to docstring bodies
always_document_param_types = True  # Always show parameter types
typehints_formatter = format_annotation_for_rst

# Modern Sphinx configuration
html_title = f"{project} v{version}"
html_short_title = project_name
html_context = {
    "sidebar_project_name": project_name,
    "sidebar_project_tagline": project_tagline,
    "sidebar_version_tag": f"v{display_version}",
}

# OpenGraph configuration for social media previews
ogp_site_url = "https://fabulous.readthedocs.io/en/latest/"
ogp_site_name = "FABulous: Open-Source Embedded FPGA Framework"
ogp_description_length = 200
ogp_image = "_static/figs/FABulouslogo_wide_2.png"
ogp_social_cards = {"enable": True, "image": "_static/figs/FABulouslogo_wide_2.png"}

# JSON-LD structured data for search engines and LLM crawlers
_jsonld = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    "name": "FABulous",
    "description": "An open-source embedded FPGA (eFPGA) framework for generating silicon-proven FPGA fabrics, with a full-stack toolchain from CSV-based fabric definition to GDSII.",
    "applicationCategory": "DeveloperApplication",
    "operatingSystem": "Linux, macOS",
    "license": "https://opensource.org/licenses/Apache-2.0",
    "url": "https://github.com/FPGA-Research/FABulous",
    "downloadUrl": "https://pypi.org/project/fabulous-fpga/",
    "softwareRequirements": "Python >= 3.12",
    "author": {
        "@type": "Organization",
        "name": "Novel Computing Technologies Group, University of Heidelberg",
        "url": "https://github.com/FPGA-Research",
    },
}

import json as _json

html_context["jsonld"] = _json.dumps(_jsonld)

# -- AutoAPI Configuration (Modern replacement for autosummary)
autoapi_type = "python"
autoapi_dirs = ["../../fabulous"]  # Path to source code
autoapi_root = "generated_doc"  # Directory name for generated docs (consistent with existing setup)
autoapi_keep_files = True  # Keep generated .rst files for debugging
autoapi_generate_api_docs = True
autoapi_template_dir = "_templates/autoapi"
autoapi_ignore = [
    "**/fabric_files/**",  # Exclude fabric_files directory (template files, not code)
]
autoapi_add_toctree_entry = (
    True  # Auto-insert AutoAPI index into our main toctree to reduce toc.not_included
)


def autoapi_skip_member(app, what, name, obj, skip, options):
    """Skip attribute objects to avoid duplicate descriptions.

    Attributes are documented in class docstrings; methods/functions are grouped via
    template.
    """
    # NOTE: Keep this in for future use
    # # Debug: Print what's being processed
    # if 'custom_exception' in str(obj):
    #     print(f"DEBUG: Processing {what} {name} in custom_exception, skip={skip}")

    if what == "attribute":
        return True
    return skip


autoapi_options = [
    "members",
    "undoc-members",
    "show-inheritance",
    "show-module-summary",
]
autoapi_prepare_jinja_env = prepare_autoapi_jinja_env

# Custom AutoAPI configuration
autoapi_python_class_content = (
    # Only the class docstring (where this codebase documents fields/attributes).
    # "both" would also splice in the inherited Pydantic/object __init__ boilerplate
    # ("Create a new model by parsing...", "Initialize self.  See help..."), which
    # napoleon then mis-parses as cross-reference targets.
    "class"
)
autoapi_member_order = "alphabetical"
autoapi_own_page_level = (
    "module"  # Each module gets its own page (avoid nested class toctree issues)
)

# Additional configuration for better navigation integration
# remove_from_toctrees = ["generated_doc/FABulous/*/index.rst"]  # Disabled to ensure content accessibility


def strip_redundant_rtype_fields(app, domain, objtype, contentnode) -> None:  # noqa: ARG001
    """Remove redundant return-type field blocks for documented callables."""
    if domain != "py" or objtype not in {"function", "method"}:
        return

    nodes = import_module("docutils.nodes")

    for field_list in [
        node for node in contentnode if isinstance(node, nodes.field_list)
    ]:
        for field in list(field_list):
            if not isinstance(field, nodes.field):
                continue
            field_name = field[0].astext().strip().lower()
            if field_name in {"rtype", "return type"}:
                field_list.remove(field)


# Type names that appear bare (or mis-qualified) in NumPy-style docstring type
# fields, rewritten to a target an intersphinx inventory can resolve so the
# cross-reference renders as a real link instead of failing under nitpicky mode.
_XREF_REWRITE = {
    "Path": "pathlib.Path",
    "Decimal": "decimal.Decimal",
    "nx.DiGraph": "networkx.DiGraph",
    "Cmd2ArgumentParser": "cmd2.argparse_utils.Cmd2ArgumentParser",
    "State": "librelane.state.State",
    "Config": "librelane.config.config.Config",
    "FlowException": "librelane.flows.flow.FlowException",
    # Re-exported by librelane.steps.magic but only documented under common.drc.
    "librelane.steps.magic.DRC": "librelane.common.drc.DRC",
}

# References with no documentation target to link to: the NumPy ``optional``
# modifier (not a type), an import-aliased stdlib callable, and library-internal
# type aliases / classes their published API docs do not expose. Rendered as
# plain text rather than warning. Anything *not* listed here still warns under
# nitpicky mode, so newly broken references are not masked.
_XREF_AS_TEXT = {
    "optional",
    "csvWriter",
    "ValidationInfo",
    "ValidationError",
    "librelane.steps.step.ViewsUpdate",
    "librelane.steps.step.MetricsUpdate",
    "librelane.steps.step.CompositeStep",
    "librelane.steps.openroad.Floorplan",
    "librelane.flows.classic.Classic",
    "pymoo.core.problem.ElementwiseProblem",
}


def resolve_known_type_refs(app, env, node, contnode):  # noqa: ARG001
    """Resolve a docstring type reference the domains cannot resolve alone.

    Rewrites a known bare/mis-qualified target so intersphinx links it, or
    returns its display text for references with no documentation target.
    Returns ``None`` for unknown targets so nitpicky mode still reports them.
    """
    target = node.get("reftarget")
    if target in _XREF_REWRITE:
        node["reftarget"] = _XREF_REWRITE[target]
        return None
    if target in _XREF_AS_TEXT:
        return contnode
    return None


def setup(app):
    """Custom Sphinx setup to ensure proper AutoAPI execution order."""
    # Connect AutoAPI skip member hook to avoid duplicates
    app.connect("autoapi-skip-member", autoapi_skip_member)
    app.connect("object-description-transform", strip_redundant_rtype_fields)
    # Priority below intersphinx's default (500) so a rewritten target is handed
    # to intersphinx for resolution within the same event dispatch.
    app.connect("missing-reference", resolve_known_type_refs, priority=400)
    return {"version": "0.1", "parallel_read_safe": True}


suppress_warnings = [
    "app.add_node",  # Sphinx extension internal node-registration noise
]


# Exclude patterns to prevent conflicts
exclude_patterns = [
    "_build",
    "Thumbs.db",
    ".DS_Store",
    "generated_doc/fabulous_variable.md",
    "generated_doc/FABulous",
    "generated_doc/FABulous/**",
] # since we alias the fabulous package with FABulous, we have to exclude the FABulous
# package from the generated_doc to avoid confusion and duplication in the documentation.

# -- Options for HTML output

html_theme = "furo"

html_logo = "figs/FABulouslogo_wide_2.png"

html_theme_options = {
    # Sidebar
    "sidebar_hide_name": False,
    # Light/dark mode
    "light_css_variables": {
        "color-brand-primary": "#336699",
        "color-brand-content": "#336699",
    },
    "dark_css_variables": {
        "color-brand-primary": "#5599dd",
        "color-brand-content": "#5599dd",
    },
    # Source code repository
    "source_repository": "https://github.com/FPGA-Research/FABulous/",
    "source_branch": "main",
    "source_directory": "docs/source/",
    # Footer
    "footer_icons": [
        {
            "name": "GitHub",
            "url": "https://github.com/FPGA-Research/FABulous",
            "html": """
                <svg stroke="currentColor" fill="currentColor" stroke-width="0" viewBox="0 0 16 16">
                    <path fill-rule="evenodd" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8z"></path>
                </svg>
            """,
            "class": "",
        },
    ],
}

# -- Over-riding theme options
html_static_path = ["_static"]
html_css_files = ["custom.css"]
html_js_files = ["toc_sidebar.js"]

# -- Options for EPUB output
epub_show_urls = "footnote"

bibtex_bibfiles = ["misc/publications.bib"]
copybutton_prompt_text = r"\$ |FABulous> |\(venv\)\$ "
copybutton_prompt_is_regexp = True
