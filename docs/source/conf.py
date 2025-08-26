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
    # Core Sphinx extensions (scikit-learn style)
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
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
]

intersphinx_mapping = {
    "python": ("https://docs.python.org/3/", None),
    "sphinx": ("https://www.sphinx-doc.org/en/master/", None),
    "numpy": ('https://numpy.org/doc/stable/', None),
    "pandas": ('https://pandas.pydata.org/docs/', None),
    "requests": ('https://docs.python-requests.org/en/master/', None),
    "pydantic": ('https://docs.pydantic.dev/latest/', None),
    # Additional scikit-learn style mappings
    "scipy": ('https://docs.scipy.org/doc/scipy/', None),
    "matplotlib": ('https://matplotlib.org/stable/', None),
}

# Enable cross-references within the project
autodoc_typehints_format = 'short'
intersphinx_disabled_domains = ["std"]

# Make Sphinx resolve all cross-references
nitpicky = False  # Disabled to avoid noisy warnings, type aliases still work
python_use_unqualified_type_names = True

# Type alias mappings for common types that cause reference warnings
autodoc_type_aliases = {
    'optional': 'typing.Optional',
    'Path': 'pathlib.Path',
    'Object': 'object',
    'callable': 'typing.Callable',
    'Ellipsis': 'type(Ellipsis)',
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
napoleon_use_ivar = False
napoleon_use_param = True
napoleon_use_rtype = True
napoleon_preprocess_types = False
napoleon_type_aliases = None
napoleon_attr_annotations = True
napoleon_custom_sections = [
    ('Command line arguments', 'Parameters'),
    ('Params', 'Parameters'),
    ('Verilog', 'Other'),
    ('VHDL', 'Other'),
]

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
autoapi_add_toctree_entry = True  # Auto-insert AutoAPI index into our main toctree to reduce toc.not_included

def autoapi_skip_member(app, what, name, obj, skip, options):
    """Skip attribute objects to avoid duplicate descriptions.

    Attributes are documented in class docstrings; methods/functions are grouped via
    template.
    """
    # Debug: Print what's being processed
    if 'custom_exception' in str(obj):
        print(f"DEBUG: Processing {what} {name} in custom_exception, skip={skip}")

    if what == 'attribute':
        return True
    return skip
autoapi_options = [
    'members',
    'undoc-members',
    'show-inheritance',
    'show-module-summary',
]

# Custom AutoAPI configuration
autoapi_python_class_content = 'both'  # Include both class and __init__ docs (scikit-learn style)
autoapi_member_order = 'alphabetical'
autoapi_own_page_level = 'module'  # Each module gets its own page

# Additional configuration for better navigation integration
# remove_from_toctrees = ["generated_doc/FABulous/*/index.rst"]  # Disabled to ensure content accessibility


def setup(app):
    """Custom Sphinx setup to ensure proper AutoAPI execution order."""
    # Connect AutoAPI skip member hook to avoid duplicates
    app.connect('autoapi-skip-member', autoapi_skip_member)
    return {'version': '0.1', 'parallel_read_safe': True}

# Only suppress warnings that are definitely safe to ignore
suppress_warnings = [
    # These are genuinely noisy and don't indicate real issues
    'app.add_node',  # Extension internal warnings
    'ref.class',  # Missing type references that can't be resolved
    'ref.exc',    # Missing exception references
    'ref.obj',    # Missing exception references
    # TODO(doc): Temporary suppression for docutils-origin warnings coming from
    # generated .rst/docstrings. Remove after cleaning docstrings and
    # improving templates. Patterns below cover common docutils emitters.
    'docutils',
    'ref.doc',
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
    # Core navigation settings (scikit-learn exact configuration)
    "sidebar_includehidden": True,
    "navigation_depth": 2,           # Optimal depth (reduced from 4)
    "show_nav_level": 1,            # Show only top level initially
    "show_toc_level": 1,            # Consistent with nav level (reduced from 3)
    "collapse_navigation": True,     # Enable expandable navigation sections
    "navigation_with_keys": False,   # Disable keyboard navigation (scikit-learn style)

    # Interface elements
    "use_edit_page_button": False,
    "show_prev_next": True,
    "search_bar_text": "Search the docs ...",
    "show_version_warning_banner": True,

    # Layout components (scikit-learn structure)
    "navbar_align": "left",          # Changed from "content"
    "navbar_start": ["navbar-logo"],
    "navbar_center": ["navbar-nav"],
    "navbar_end": ["theme-switcher", "navbar-icon-links"],
    "navbar_persistent": ["search-button"],

    # Article layout
    "article_header_start": ["breadcrumbs"],
    "article_footer_items": ["prev-next"],

    # Secondary sidebar (enhanced)
    "secondary_sidebar_items": {
        "**": ["page-toc", "sourcelink"],
        # Can add more specific page configs later
    },

    # Icon links (optional, like scikit-learn)
    "icon_links": [
        {
            "name": "GitHub",
            "url": "https://github.com/FABulous/FABulous",
            "icon": "fa-brands fa-square-github",
            "type": "fontawesome",
        }
    ],
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
