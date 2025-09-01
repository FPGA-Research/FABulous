# Configuration file for the Sphinx documentation builder.

# -- Project information

project = "FABulous Documentation"
copyright = "2021, University of Manchester"
author = "Jing, Nguyen, Bea, Bardia, Dirk"

release = "0.1"
version = "0.1.0"

# -- General configuration

import os
import sys
from pathlib import Path

# Ensure the repository root is importable so `import FABulous.*` works as a
# proper package (and doesn't get shadowed by FABulous.py).
_repo_root = Path(__file__).resolve().parents[2].as_posix()
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

extensions = [
    "sphinx.ext.duration",
    "sphinx.ext.doctest",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.intersphinx",
    "sphinxcontrib.bibtex",
    "sphinx.ext.napoleon",
    "sphinx-prompt",
    "sphinx_copybutton",
    "sphinx.ext.imgconverter",
]

intersphinx_mapping = {
    "python": ("https://docs.python.org/3/", None),
    "sphinx": ("https://www.sphinx-doc.org/en/master/", None),
}
intersphinx_disabled_domains = ["std"]

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
napoleon_use_ivar = False
napoleon_use_param = True
napoleon_use_rtype = True
napoleon_preprocess_types = False
napoleon_type_aliases = None
napoleon_attr_annotations = True

# -- Autodoc options
autodoc_typehints = "description"
autodoc_typehints_format = "short"
autodoc_type_aliases = {
    'Object': 'object',
    'optional': 'typing.Optional',
    'Path': 'pathlib.Path',
}

# Suppress warnings for missing references in type annotations
nitpicky = False
nitpick_ignore = [
    ('py:class', 'Object'),
    ('py:class', 'optional'),
    ('py:class', 'Path')
]

autodoc_mock_imports = [
    # Only mock external dependencies that aren't available in docs environment
    'numpy',
    'pandas',
    'matplotlib',
    'networkx',
    'lxml',
    'typing_extensions',
]

# -- Autosummary options
autosummary_generate = True
autosummary_generate_overwrite = True
autosummary_imported_members = True

# -- Additional autodoc options to suppress warnings
autodoc_default_options = {
    'members': True,
    'undoc-members': True,
    'show-inheritance': True,
    'ignore-module-all': True,
}

# Suppress specific warnings
suppress_warnings = [
    'autodoc.import_error',
    'autodoc.mock',
    'autodoc.mocked_object',
    'autosummary.import_error',
    'toc.not_included',
    'myst.header',
]

# Don't halt on missing references
autodoc_strict = False

# -- Options for HTML output

html_theme = "pydata_sphinx_theme"

html_logo = "figs/FABulouslogo_wide_2.png"

# -- Over-riding theme options
html_static_path = ["_static"]
html_css_files = [
    "custom.css",
]

# -- removing left side bar on pages that don't benefit
html_sidebars = {
    "Usage": [],
    "Building fabric": [],
    "fabric_definition": [],
    "fabric_automation": [],
    "FPGA_CAD-tools/index": [],
    "gallary/index": [],
    "FPGA-to-bitstream/index": [],
    "references/FABulous": [],
    "definitions": [],
    "contact": [],
    "publications": [],
    "simulation/index": [],
}

# -- Options for EPUB output
epub_show_urls = "footnote"

bibtex_bibfiles = ["publications.bib"]
copybutton_prompt_text = r"\$ |FABulous> |\(venv\)\$ "
copybutton_prompt_is_regexp = True
