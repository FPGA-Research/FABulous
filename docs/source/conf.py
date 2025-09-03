import os
import sys

# Configuration file for the Sphinx documentation builder.

# -- Project information

project = "FABulous Documentation"
copyright = "2021, University of Manchester"
author = "Jing, Nguyen, Bea, Bardia, Dirk"

release = "0.1"
version = "0.1.0"

# -- General configuration

extensions = [
    "sphinx.ext.duration",
    "sphinx.ext.doctest",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.intersphinx",
    "sphinxcontrib.bibtex",
    "sphinx.ext.napoleon",
    "sphinx-prompt",
    "sphinx.ext.todo",
    "sphinx_rtd_theme",
]

intersphinx_mapping = {
    "python": ("https://docs.python.org/3/", None),
    "sphinx": ("https://www.sphinx-doc.org/en/master/", None),
}
intersphinx_disabled_domains = ["std"]

templates_path = ["_templates"]

sys.path.append(os.getcwd() + "/../../")

napoleon_google_docstring = True
napoleon_numpy_docstring = False
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


# -- Options for HTML output

html_theme = "sphinx_rtd_theme"

html_logo = "figs/FAB_logo.png"

# Set the serachbar background to FABulous blue
html_theme_options = {
    'style_nav_header_background': '#333399',
}
default_dark_mode = True

# -- Options for EPUB output
epub_show_urls = "footnote"

bibtex_bibfiles = ["publications.bib"]
