# FABulous docs

FABulous is an open-source embedded FPGA (eFPGA) framework for generating FPGA fabric and integrates the open source CAD tools Yosys and nextpnr for the user design flow. It is silicon-proven through multiple successful tapeouts across TSMC 180nm, Skywater 130nm, IHP SG13G2, GF180MCU, and 28nm CMOS, FABulous provides a full-stack toolchain from CSV-based fabric definition to production-ready GDSII. The framework supports frame-based partial reconfiguration for runtime reconfiguration of individual FPGA regions.

The upstream FABulous documentation is available at [https://fabulous.readthedocs.io](https://fabulous.readthedocs.io/en/latest/)

## TL;DR

```bash
git clone https://github.com/FPGA-Research/FABulous
cd FABulous/docs
uv sync
make html
xdg-open build/html/index.html
```

## What to search for

- Quick start and installation: docs/source/getting_started
- CLI commands: docs/source/user_guide/cli_doc
- Fabric build flow: docs/source/user_guide/building_doc
- Bitstream and configuration: docs/source/user_guide/using_doc
- Simulation and emulation: docs/source/user_guide/simulation

## General

Our docs are built using [Sphinx](https://www.sphinx-doc.org/en/master).
The documentation is written in [reStructuredText](https://docutils.sourceforge.io/rst.html) format.

## Prerequisites

To build the documentation, you should already have set up your environment and installed the required packages to use FABulous as described in the [README](../README.md). Make sure you have picked the right FABulous branch you want to build the documentation for.

Install the documentation dependencies with uv:

```bash
uv sync
```

## Building the documentation

### HTML format

To build the documentation in HTML format, run:

```bash
make html
```

This should create a `build/html/` directory path in the `docs` directory for the HTML documentation.

Open it with your browser:

```bash
xdg-open build/html/index.html
```

### PDF format

If you want to build the documentation in PDF format, you need to install additional packages.
and a working LaTeX installation on your system, you can find the needed packages in the
[LaTeXBuilder sphinx documentation](https://www.sphinx-doc.org/en/master/usage/builders/index.html#sphinx.builders.latex.LaTeXBuilder).
You also need to install [Imagemagic](https://imagemagick.org/script/index.php), which you can install via `apt-get`:

```bash
sudo apt-get install imagemagick
```

To build the documentation in PDF format, run:

```bash
make latexpdf
```

This should create a `build/latex/` directory path in the `docs` directory for the PDF documentation.
The PDF file is named `fabulous.pdf`.

Open it with your PDF viewer:

```bash
xdg-open build/latex/fabulous.pdf
```

### Clean the build directory

To clean the build directory, run:

```bash
make clean
```

This will remove the `build/` directory.

## Customizations

Custom modifications on top of the [Furo](https://pradyunsg.me/furo/) Sphinx
theme and [sphinx-autoapi](https://sphinx-autoapi.readthedocs.io/).

### Collapsible TOC sidebar

The right-hand "Contents" sidebar has a toggle button for collapsing/expanding
on desktop viewports (wider than 82 em). The collapse state persists via
`localStorage`. If content overflows horizontally, the sidebar auto-collapses
unless the user has explicitly expanded it.

- `source/_static/toc_sidebar.js` -- toggle logic and state management
- `source/_static/custom.css` -- toggle styles and collapse animations

### Custom AutoAPI templates

The API reference uses customized Jinja templates (`source/_templates/autoapi/`)
instead of the sphinx-autoapi defaults:

- **Docstring normalization** (`source/_ext/docstring_renderer.py`) -- converts
  markdown-style code blocks, inline code, and lists into valid reST. Strips
  redundant `:rtype:` fields.
- **Class template** -- organizes members into Attributes, Properties, and
  Methods subsections with cross-referenced inheritance.
- **Index template** -- shows subpackages in a flat toctree for cleaner
  navigation.

### Custom sidebar brand

`source/_templates/sidebar/brand.html` replaces Furo's default brand area with
a layout showing the project name, tagline, and version tag, styled via
`custom.css`.

## Contributing

Thank you for considering contributing to FABulous!
If you find any issues or have any suggestions, improvements, new features or questions,
please open an [issue](https://github.com/FPGA-Research/FABulous/issues),
start a [discussion](https://github.com/FPGA-Research/FABulous/discussions)
or create a [pull request](https://github.com/FPGA-Research/FABulous/pulls).
