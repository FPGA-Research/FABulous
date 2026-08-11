# FABulous docs

FABulous is an open-source embedded FPGA (eFPGA) framework for generating FPGA fabric and integrates the open source CAD tools Yosys and nextpnr for the user design flow. It is silicon-proven through multiple successful tapeouts across TSMC 180nm, Skywater 130nm, IHP SG13G2, GF180MCU, and 28nm CMOS, FABulous provides a full-stack toolchain from CSV-based fabric definition to production-ready GDSII. The framework supports frame-based partial reconfiguration for runtime reconfiguration of individual FPGA regions.

The upstream FABulous documentation is available at [https://fabulous.readthedocs.io](https://fabulous.readthedocs.io/en/latest/)

## TL;DR

```bash
git clone https://github.com/FPGA-Research/FABulous
cd FABulous
task docs-build
xdg-open docs/build/html/index.html
```

## What to search for

- Quick start and installation: docs/source/getting_started
- CLI commands: docs/source/user_guide/cli_doc
- Fabric build flow: docs/source/user_guide/building_doc
- Bitstream and configuration: docs/source/user_guide/using_doc
- Simulation and emulation: docs/source/user_guide/simulation

## General

Our docs are built using [Sphinx](https://www.sphinx-doc.org/en/master).
Pages are written in [MyST Markdown](https://myst-parser.readthedocs.io/en/latest/),
apart from the command and variable reference tables, which extensions in
`source/_ext/` generate from the installed package at build time.

## Prerequisites

To build the documentation, you should already have set up your environment and installed the required packages to use FABulous as described in the [README](../README.md). Make sure you have picked the right FABulous branch you want to build the documentation for.

The documentation dependencies live in the `docs` dependency group of the
repository-root `pyproject.toml`, so there is a single environment for both
FABulous and its docs. Install them from the repository root with:

```bash
uv sync --group docs
```

`uv run` syncs the environment before each command, so the tasks below work from
a fresh checkout without installing anything first.

## Building the documentation

### HTML format

To build the documentation in HTML format, run from the repository root:

```bash
task docs-build
```

This should create a `build/html/` directory path in the `docs` directory for the HTML documentation.
It builds with `-W`, so a warning fails the build the same way Read the Docs does.

Open it with your browser:

```bash
xdg-open docs/build/html/index.html
```

For a live-reloading server while writing, use `task docs-server` instead. That
one drops `-W`, so a page with an outstanding warning still renders.

### PDF format

If you want to build the documentation in PDF format, you need to install additional packages.
and a working LaTeX installation on your system, you can find the needed packages in the
[LaTeXBuilder sphinx documentation](https://www.sphinx-doc.org/en/master/usage/builders/index.html#sphinx.builders.latex.LaTeXBuilder).
You also need to install [Imagemagic](https://imagemagick.org/script/index.php), which you can install via `apt-get`:

```bash
sudo apt-get install imagemagick
```

To build the documentation in PDF format, run from the `docs` directory:

```bash
uv run --project .. --group docs sphinx-build -M latexpdf source build
```

This should create a `build/latex/` directory path in the `docs` directory for the PDF documentation.
The PDF file is named `fabulous.pdf`.

Open it with your PDF viewer:

```bash
xdg-open build/latex/fabulous.pdf
```

### Clean the build directory

`task docs-build` cleans before building. To clean without building, run from the
`docs` directory:

```bash
rm -rf build source/generated_doc
```

`source/generated_doc` holds the pages the generator extensions write, which are
not rebuilt while they are still present.

## Customizations

Custom modifications on top of the [Furo](https://pradyunsg.me/furo/) Sphinx
theme.

### Collapsible TOC sidebar

The right-hand "Contents" sidebar has a toggle button for collapsing/expanding
on desktop viewports (wider than 82 em). The collapse state persists via
`localStorage`. If content overflows horizontally, the sidebar auto-collapses
unless the user has explicitly expanded it.

- `source/_static/toc_sidebar.js` -- toggle logic and state management
- `source/_static/custom.css` -- toggle styles and collapse animations

### Generated reference pages

Three extensions in `source/_ext/` write MyST pages into `source/generated_doc/`
at build time, each rendering a Jinja template in `source/_templates/`:

- `generate_repl_docs.py` -- the interactive REPL command reference.
- `generate_configvar_docs.py` -- the FABulous configuration variables.
- `generate_gds_variable_docs.py` -- the GDS-flow variables, read from librelane.

They introspect the installed package, so a new command or config variable shows
up without anyone editing a page.

### No Python API reference

There is deliberately no auto-generated per-module API reference. It cost roughly
900 lines of templates, extensions, and cross-reference workarounds to keep
building, and nothing in the prose documentation linked into it. Read the source
for API detail; the docstrings are the reference.

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
