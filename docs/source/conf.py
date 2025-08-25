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

# -- Mock imports for documentation build
autodoc_mock_imports = [
    # Only mock external dependencies that aren't available in docs environment
    'numpy',
    'pandas',
    'matplotlib',
    'networkx',
    'lxml',
    'typing_extensions',
]

# Configure autodoc to avoid dataclass field duplication
autodoc_default_options = {
    'members': True,
    'undoc-members': False,
    'show-inheritance': True,
    'special-members': False,
    'inherited-members': False,
}

# Prevent duplicate object warnings from autosummary
autodoc_typehints = 'description'
autodoc_preserve_defaults = True
autodoc_member_order = 'alphabetical'

# -- Autosummary options
autosummary_generate = True
autosummary_generate_overwrite = True
autosummary_recursive = True
autosummary_imported_members = False
autosummary_ignore_module_all = True

# Suppress specific warnings for CI builds
suppress_warnings = [
    'autosummary.import_error',
    'toc.not_included',
    'myst.header',
    'autodoc.duplicate_object',
    'app.add_node',
]

# Exclude patterns to prevent conflicts
exclude_patterns = [
    '_build',
    'Thumbs.db',
    '.DS_Store',
]

# def setup(app):
#     """Custom Sphinx setup to handle duplicate object warnings."""
#     import logging

#     # Get the Sphinx logger and filter duplicate object warnings
#     sphinx_logger = logging.getLogger('sphinx')

#     class DuplicateObjectFilter(logging.Filter):
#         def filter(self, record):
#             return not ('duplicate object description' in record.getMessage())

#     sphinx_logger.addFilter(DuplicateObjectFilter())

#     return {'version': '0.1', 'parallel_read_safe': True}

# -- Options for HTML output

html_theme = "pydata_sphinx_theme"

html_logo = "figs/FABulouslogo_wide_2.png"

html_theme_options = {
    "collapse_navigation": False,
    "show_nav_level": 2,
    "show_toc_level": 2,
    "navigation_depth": 4,
    "use_edit_page_button": False,
    "show_prev_next": True,
    "article_header_start": [],
    "article_header_end": [],
    "secondary_sidebar_items": ["page-toc", "sourcelink"],
    "navbar_align": "content",
    "navbar_center": ["navbar-nav"],
    "show_version_warning_banner": True,
}

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
