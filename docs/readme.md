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
- CLI and REPL usage: docs/source/user_guide/cli_doc
- Fabric definition, configuration and GDS flow: docs/source/user_guide/building_doc
- Synthesis, place and route, pin constraints and bitstream generation: docs/source/user_guide/using_doc
- Simulation and emulation: docs/source/user_guide/simulation

## General

Our docs are built using [Sphinx](https://www.sphinx-doc.org/en/master).
Pages are written in [MyST Markdown](https://myst-parser.readthedocs.io/en/latest/);
the API reference is auto-generated from source docstrings by [sphinx-autoapi](https://sphinx-autoapi.readthedocs.io/).

## Changing the docs

Each kind of content has one home, and the generated pages have no hand-edited copy.

| Content | Edit here | Not here |
|---------|-----------|----------|
| Guide pages | `docs/source/<section>/*.md`, plus one entry in that section's `index.md` toctree | |
| API reference | the docstring in `fabulous/` | `generated_doc/fabulous/**` |
| REPL command reference | the `do_*` docstring and its `@with_annotated` parameters in `fabulous/fabulous_repl/` | `generated_doc/interactive_repl_commands.md` |
| `FABulousSettings` variables | the field and its description in `fabulous/fabulous_settings.py` | `generated_doc/fabulous_variable.md` |
| GDS flow variables | the `config_vars` of the step or flow in `fabulous/fabric_generator/gds_generator/` | `generated_doc/gds_variable.md` |

`source/generated_doc/` is gitignored and rebuilt by `task docs-build`. AutoAPI
writes the API pages there, and the three extensions in `source/_ext/` write
the reference pages there from Jinja templates in `source/_templates/` at
`config-inited`. Two of those pages sit in a toctree directly. The settings page
is excluded in `conf.py` and pulled into `user_guide/cli_doc/fabulous_variable.md`
with `{include}`, because that page carries hand-written prose around the table.

The REPL generator imports the live command classes. A command's category is
its `@with_category` value, else its `CommandSet`'s `DEFAULT_CATEGORY`, and it
must be one of the `CMD_*` constants in `fabulous_repl/command_set_base.py`,
otherwise the build stops. Numpy `Notes`, `Examples` and `See Also` sections are
kept and render as bold labels. `Parameters`, `Returns`, `Raises` and `Yields`
are dropped, because the argument table already carries them.

The build runs Sphinx with `-n -W`, so an unresolved cross-reference fails it.
When a docstring type does not resolve, edit one of the two lists in `conf.py`.
`_XREF_REWRITE` maps a bare or mis-qualified name to a target an intersphinx
inventory can link. `_XREF_AS_TEXT` renders a name with no published target as
plain text. `nitpick_ignore` is not used, because it silences the warning but
still renders the unresolved fully-qualified name. A type from a package with no
inventory in `intersphinx_mapping` needs a new mapping entry or an
`_XREF_AS_TEXT` entry.

Moving or deleting a page needs an entry in `redirects` in `conf.py`, mapping
the old docname to its new URL relative to the old location, so published links
keep resolving.

Pages and docstrings are MyST. Pre-commit rejects reST double-backtick
literals, reST directives and `:role:` syntax. A page's first heading becomes
its title in `llms.txt`, so the `(label)=` target and the `#` heading come
before any admonition.

## Prerequisites

To build the documentation, you should already have set up your environment and installed the required packages to use FABulous as described in the [README](../README.md). Make sure you have picked the right FABulous branch you want to build the documentation for.

The documentation dependencies live in the `docs` dependency group of the
repository-root `pyproject.toml`, so there is a single environment for both
FABulous and its docs. The docs tasks install them from the root `uv.lock` with
`--locked`, so a lock that no longer matches `pyproject.toml` fails the build
rather than resolving around it. Run `uv lock` after editing the dependencies.
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
uv run --locked --project .. --group docs sphinx-build -M latexpdf source build
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

`source/generated_doc` holds the AutoAPI output, which is not regenerated while
it is still present.

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

- **MyST docstrings** (`source/_ext/myst_docstring.py`) -- sphinx-autoapi nested-parses
  docstrings as reST, so MyST written in one would never be parsed. This extension
  supplies a `myst-docstring` directive that parses the content with the MyST parser
  instead, and registers it over autoapi's own `autoapi-nested-parse` so module
  docstrings take the same path. Docstrings are therefore written in the same
  CommonMark as the rest of the docs -- single backticks for inline code, fenced
  code blocks, and `{class}`-style roles for cross-references.

  The object templates carry the wrap because upstream routes only *module*
  docstrings through a directive; see [sphinx-autoapi#287](https://github.com/readthedocs/sphinx-autoapi/issues/287).
  If upstream routes every object's docstring through `autoapi-nested-parse`, those
  templates can be deleted the way `module.rst` was.
- **Page-body filters** (`source/_ext/docstring_renderer.py`) -- shape the reST
  scaffolding autoapi generates *around* the docstring: the `Bases:` line, and the
  return sections a property's rendered type already states. They do not translate
  markup.
- **Class template** -- groups members into Properties and Methods subsections with
  cross-referenced inheritance. Attributes are deliberately skipped
  (`autoapi_skip_member` in `conf.py`); this codebase documents them in the class
  docstring, so rendering them again would duplicate.
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
