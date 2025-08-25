# Configuration file for the Sphinx documentation builder.

# -- Project information

project = "FABulous Documentation"
copyright = "2021, University of Manchester"
author = "Jing, Nguyen, Bea, Bardia, Dirk"

# Automated version management from git
def get_version():
    """Get version from git tags or fallback to default."""
    try:
        import subprocess
        result = subprocess.run(['git', 'describe', '--tags', '--abbrev=0'],
                              capture_output=True, text=True, cwd=Path(__file__).parent)
        if result.returncode == 0:
            return result.stdout.strip()
    except:
        pass
    return "0.1.0"

version = get_version()
release = version

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
    # Core Sphinx extensions
    "sphinx.ext.duration",
    "sphinx.ext.doctest",
    "sphinx.ext.intersphinx",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",

    # Modern documentation automation
    "autoapi.extension",  # Replaces autodoc + autosummary
    "sphinx_autodoc_typehints",  # Automatic type hint processing

    # Enhanced documentation features
    "myst_parser",  # Markdown support
    "sphinx_design",  # Modern UI components
    "sphinxext.opengraph",  # Social media cards

    # Utility extensions
    "sphinxcontrib.bibtex",
    "sphinx_prompt",
    "sphinx_copybutton",
    "sphinx.ext.imgconverter",
]

intersphinx_mapping = {
    "python": ("https://docs.python.org/3/", None),
    "sphinx": ("https://www.sphinx-doc.org/en/master/", None),
}

# Enable cross-references within the project
autodoc_typehints_format = 'short'
intersphinx_disabled_domains = ["std"]

# Make Sphinx resolve all cross-references
nitpicky = False  # Disabled to avoid noisy warnings, type aliases still work
python_use_unqualified_type_names = True


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
napoleon_use_ivar = False
napoleon_use_param = True
napoleon_use_rtype = True
napoleon_preprocess_types = False
napoleon_type_aliases = None
napoleon_attr_annotations = True

# -- Mock imports for documentation build
autodoc_mock_imports = [
    # External dependencies that aren't available in docs environment
    'numpy',
    'pandas',
    'matplotlib',
    'networkx',
    'lxml',
    'typing_extensions',
    'loguru',
    'cmd2',
    'dotenv',
    'bitarray',
    'requests',
    'pydantic',
    'pydantic_settings',
    'rich',
    'textx',
    'arpeggio',
]

# Configure autodoc to avoid dataclass field duplication
autodoc_default_options = {
    'members': True,
    'undoc-members': False,
    'show-inheritance': True,
    'special-members': False,
    'inherited-members': False,
}

# Prevent autodoc from automatically documenting modules
autodoc_member_order = 'alphabetical'

# Prevent duplicate object warnings from autosummary
autodoc_typehints = 'description'
autodoc_preserve_defaults = True
autodoc_member_order = 'alphabetical'
autodoc_class_signature = 'mixed'
autodoc_inherit_docstrings = True

# Configuration for sphinx-autodoc-typehints extension
typehints_fully_qualified = False  # Use short names when possible
typehints_document_rtype = True    # Document return types
typehints_use_signature = True     # Show types in signature
typehints_use_rtype = True         # Show return types in docstring
always_document_param_types = True # Always show parameter types

# Enhanced intersphinx mapping for better cross-references
intersphinx_mapping.update({
    'numpy': ('https://numpy.org/doc/stable/', None),
    'pandas': ('https://pandas.pydata.org/docs/', None),
})

# Modern Sphinx configuration
html_title = f"{project} v{version}"
html_short_title = project

# OpenGraph configuration for social media previews
ogp_site_url = "https://fpga-research.github.io/FABulous/"
ogp_description_length = 200
ogp_image = "_static/figs/FABulouslogo_wide_2.png"
ogp_social_cards = {
    "enable": True,
    "image": "_static/figs/FABulouslogo_wide_2.png"
}

# -- AutoAPI Configuration (Modern replacement for autosummary)
autoapi_type = 'python'
autoapi_dirs = ['../../FABulous']  # Path to source code
autoapi_root = 'generated_doc'  # Directory name for generated docs (consistent with existing setup)
autoapi_keep_files = True  # Keep generated .rst files for debugging
autoapi_generate_api_docs = True
autoapi_template_dir = '_templates/autoapi'
autoapi_ignore = [
    '**/fabric_files/**',  # Exclude fabric_files directory and all contents
]

# Ensure AutoAPI runs before other documentation generation to avoid duplicates
def autoapi_skip_member(app, what, name, obj, skip, options):
    """Control which members AutoAPI documents to avoid duplicates."""
    # Skip dataclass fields that cause duplicate attribute documentation
    if what == 'attribute':
        # Try multiple ways to get the parent class
        parent_class = None

        # Method 1: Check __objclass__ attribute
        if hasattr(obj, '__objclass__'):
            parent_class = obj.__objclass__
        # Method 2: Check from the options/context
        elif 'autoapi_object' in options:
            autoapi_obj = options['autoapi_object']
            if hasattr(autoapi_obj, 'obj'):
                parent_class = autoapi_obj.obj

        # If we found a parent class and it's a dataclass with this field
        if parent_class and hasattr(parent_class, '__dataclass_fields__'):
            if name in parent_class.__dataclass_fields__:
                return True

    return skip
autoapi_options = [
    'members',
    'undoc-members',
    'show-inheritance',
    'show-module-summary',
]

# Custom AutoAPI configuration
autoapi_python_class_content = 'class'  # Only class docstring to avoid duplicates
autoapi_member_order = 'alphabetical'
autoapi_own_page_level = 'module'  # Each module gets its own page


def setup(app):
    """Custom Sphinx setup to ensure proper AutoAPI execution order."""
    # Connect AutoAPI skip member hook to avoid duplicates
    app.connect('autoapi-skip-member', autoapi_skip_member)
    return {'version': '0.1', 'parallel_read_safe': True}

# Only suppress warnings that are definitely safe to ignore
suppress_warnings = [
    # These are genuinely noisy and don't indicate real issues
    'autosummary.import_error',  # Expected when modules aren't importable in docs
    'app.add_node',  # Extension internal warnings
]

# Note: ~60 duplicate warnings are expected from AutoAPI's handling of dataclass attributes
# These are cosmetic only - AutoAPI generates both class docstring attributes AND separate
# attribute entries for dataclasses. The documentation content is complete and correct.


# Exclude patterns to prevent conflicts
exclude_patterns = [
    '_build',
    'Thumbs.db',
    '.DS_Store',
]

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
    "development": [],
}

# -- Options for EPUB output
epub_show_urls = "footnote"

bibtex_bibfiles = ["publications.bib"]
copybutton_prompt_text = r"\$ |FABulous> |\(venv\)\$ "
copybutton_prompt_is_regexp = True
