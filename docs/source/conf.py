# Configuration file for the Sphinx documentation builder.

import json
import re
import sys
from importlib.metadata import version as installed_version
from pathlib import Path

# -- Project information

project = "FABulous: An easy-to-use, silicon-proven (e)FPGA generator with an integrated CAD toolchain 🏗️"
copyright = "2021, University of Manchester"
author = "Jing, Nguyen, Bea, Bardia, Dirk"

# The docs environment installs `fabulous-fpga` (editable), so the package
# metadata is the single source for the version.
version = installed_version("fabulous-fpga")
release = version
# Bare version for tagged releases, version+dev for dev builds.
display_version = re.sub(r"(\.dev.*|[+].*)$", "", version) + (
    "+dev" if ".dev" in version else ""
)
project_name = "FABulous"
project_tagline = "An easy-to-use, silicon-proven (e)FPGA generator with an integrated CAD toolchain 🏗️"


# -- General configuration

# Add _ext directory to path so Sphinx can load the custom extensions below.
_ext_dir = Path(__file__).resolve().parent / "_ext"
if _ext_dir.as_posix() not in sys.path:
    sys.path.insert(0, _ext_dir.as_posix())

extensions = [
    # Core Sphinx extensions
    "sphinx.ext.duration",
    "sphinx.ext.intersphinx",
    "sphinx.ext.imgconverter",
    # Documentation features
    "myst_parser",  # Markdown support
    "sphinxext.opengraph",  # Social media cards
    "sphinx_copybutton",  # Copy code button
    "sphinxcontrib.bibtex",
    "sphinx_llm.txt",
    "sphinxcontrib.mermaid",
    "sphinx_reredirects",  # Keep old page URLs working after restructures
    # Custom FABulous extensions
    "generate_repl_docs",
    "generate_configvar_docs",
    "generate_gds_variable_docs",
]

myst_enable_extensions = [
    "colon_fence",
]

# Redirects for pages moved or merged during docs restructures, so published
# URLs keep resolving. Targets are relative to the old page location.
redirects = {
    "getting_started/index": "quickstart.html",
    "user_guide/index": "building_doc/index.html",
    "user_guide/using_doc/synthesis/index": "../synthesis.html",
    "user_guide/using_doc/synthesis/yosys": "../synthesis.html",
    "user_guide/using_doc/synthesis/yosys_compilation": "../synthesis.html",
    "user_guide/using_doc/pnr/index": "../place_and_route.html",
    "user_guide/using_doc/pnr/nextpnr": "../place_and_route.html",
    "user_guide/using_doc/pnr/nextpnr_compilation": "../place_and_route.html",
    "user_guide/using_doc/pnr/pin_constraints": "../pin_constraints.html",
    "user_guide/using_doc/bitstream/bitstream_generation": (
        "../bitstream_generation.html"
    ),
}

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
intersphinx_disabled_domains = ["std"]

# Report every unresolved cross-reference. The missing-reference handler below
# (resolve_known_type_refs) rewrites or downgrades the known-unresolvable targets,
# so this stays quiet in a clean tree and fails the build on genuinely new breakage.
nitpicky = True

templates_path = ["_templates"]

# FABulous package is installed as a dependency in the docs environment

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

html_context["jsonld"] = json.dumps(_jsonld)

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

# References with no documentation target to link to: the NumPy `optional`
# modifier (not a type), an import-aliased stdlib callable, and library-internal
# type aliases / classes their published API docs do not expose. Handled by
# returning the reference's own content node, which renders the short display
# name as plain text. `nitpick_ignore` is deliberately not used here: it only
# silences the warning and leaves the reference rendering its fully-qualified
# target. Anything _not_ listed here still warns under nitpicky mode, so newly
# broken references are not masked.
_XREF_AS_TEXT = {
    "optional",
    "csvWriter",
    "ValidationInfo",
    "ValidationError",
    "Ellipsis",
    "pydantic.RootModel[dict[str, StdCellLibrary]]",
    "librelane.steps.step.ViewsUpdate",
    "librelane.steps.step.MetricsUpdate",
    "librelane.steps.step.CompositeStep",
    "librelane.steps.openroad.Floorplan",
    "librelane.steps.openroad.DetailedRouting",
    "librelane.steps.magic.StreamOut",
    "librelane.steps.pyosys.JsonHeader",
    "librelane.flows.classic.Classic",
    "pymoo.core.problem.ElementwiseProblem",
}


def resolve_known_type_refs(app, env, node, contnode):  # noqa: ARG001
    """Resolve a docstring type reference the domains cannot resolve alone.

    Rewrites a known bare/mis-qualified target so intersphinx links it, or
    returns its display text for references with no documentation target.
    Returns `None` for unknown targets so nitpicky mode still reports them.
    """
    target = node.get("reftarget")
    if target in _XREF_REWRITE:
        node["reftarget"] = _XREF_REWRITE[target]
        return None
    if target in _XREF_AS_TEXT:
        return contnode
    return None


def setup(app):
    """Register the cross-reference handler for the generated variable tables."""
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
    # Included into a hand-written page rather than reached through a toctree.
    "generated_doc/fabulous_variable.md",
]

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
