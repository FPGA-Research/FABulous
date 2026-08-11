# AGENTS.md

## Project Overview

FABulous is a parametric FPGA fabric generator. It takes a fabric definition (CSV or YAML), builds an in-memory fabric model, and emits the HDL, nextpnr chip database, synthesis scripts, geometry, and bitstream needed to target that fabric.

```text
config (CSV/YAML) → fabric model → HDL + chip DB + synth scripts
user design → Yosys (synth) → nextpnr (P&R) → FASM → bitstream
```

## How to Work in This Repo

- **Python deps: `uv`.** Run `uv sync` after pulling; add deps with `uv add` (`--group dev` for dev-only). Never hand-edit `uv.lock`. Run commands as `uv run <cmd>` or activate `.venv/`.
- **EDA toolchain: Nix.** `flake.nix` pins Yosys, nextpnr, OpenROAD, GHDL, Librelane, etc. The **GDS / ASIC flow** (anything under `gds_flow_test`, `librelane_plugin_fabulous`, or `fabulous/fabric_generator/gds_generator`) requires the Nix shell — `nix develop` first, when inside the shell you will not need `uv`. Don't try to substitute system installs of these tools; CI uses Nix and version drift will burn you.
- **Tasks**: `Taskfile.yml` is the canonical runner. The ones you'll use most: `task test` (forwards args after `--`; pass `--runslow` for slow tests), `task ci` (run before pushing), `task smoke-test` (end-to-end). `task --list` for the rest.
- **Pre-commit is enforced** (ruff, docstring linting, dependency hygiene, etc.). If a hook fails, fix the cause — don't `--no-verify`. Run the hooks through uv (`uv run pre-commit run --all-files`): `deptry` resolves imports against the *installed* project, so outside the uv environment it falls back to assuming a module name for every package ("Assuming the corresponding module name of package ... is ...") and fails on dependencies that are perfectly fine. Re-run a dependency-hygiene failure under `uv` before believing it, and commit with `uv run git commit` so the hooks git triggers see the same environment.

- **Docs: MyST (Sphinx).** Project documentation is written in MyST Markdown and built with Sphinx. Prefer MyST for new documentation (uses directives, roles, and math blocks) rather than raw reStructuredText. Build with `task docs-build` (`task docs-server` for live reload); see `docs/source/conf.py` for the Sphinx configuration and `docs/readme.md` for the customizations. There is no generated Python API reference — document behaviour on a prose page, not by expecting a module page to appear.

## Coding Taste

Rules that make changes feel native. Follow them even when a tool's defaults disagree.

### Style

- **Python 3.12+**. Built-in generics only (`list[int]`, `X | None`); never `typing.List`/`Optional`.
- **Paths**: `pathlib.Path`. Never `os.path` or string concatenation.
- **Logging**: `loguru` (`from loguru import logger`). Not `print`, not stdlib `logging`.
- **Docstrings**: NumPy style — `pydoclint` + `interrogate` (≥95% coverage) enforce this.
- **Markup in docstrings/comments**: CommonMark, the same as the docs pages — single backticks for inline code, fenced blocks for code, and either `*asterisks*` or `_underscores_` for italic. Docstrings are not rendered into the docs (there is no generated API reference), so this is about them reading well in source and staying consistent with the pages. The reST spellings — doubled-backtick literals, dot-dot directives, and colon-wrapped roles — are rejected by pre-commit.
- **Naming**: this repo right now uses `camelCase` for variables/functions, `PascalCase` for classes, `CONSTANT_CASE` for module constants. Use snake case for all newly created methods and variables as we slow transition to meet PEP 8.
- Formatting (line length, quotes, etc.) is whatever `ruff format` produces.

### Design

- **No fallbacks, no silent retries.** Surface failures with clear errors. A stack trace beats a wrong result.
- **Fix root causes.** If a fix doesn't change behavior the way you expected, stop and re-analyze before patching again.
- **Validate at boundaries, trust internals.** Defensive checks belong where untrusted input enters (parsers, CLI, external tools).
- **No premature abstraction.** Three similar lines beat a speculative helper. Ship the smallest correct change.
- **Clear over clever.** Loops over unreadable comprehensions; parsers over paragraph-long regexes.
- **Comments explain *why*, not *what*.** Reserve them for hidden constraints, non-obvious invariants, bug-specific workarounds. Don't reference task numbers or callers — that rots.
- **Pydantic** for runtime-validated config (`fabulous_settings.py`); **dataclasses** for the fabric model — keep them light, no heavy logic.

### Testing

- `pytest` + `pytest-mock` (use the `mocker` fixture; don't import `unittest.mock`).
- Mark slow tests `@pytest.mark.slow` so default `task test` stays fast.
- Prefer real in-memory fabric fixtures over heavy mocks.
- `cocotb` is available for RTL-level verification, not for Python logic.
- Try to reuse fixture as much as possible.
- Try to parameterize the test if possible

## House Rules

- Don't edit the symlinked agent files (`CLAUDE.md`, `GEMINI.md`, `.cursorrules`, `.github/copilot-instructions.md`) — edit `AGENTS.md`.
- Don't add new top-level packages without a clear home in the layout above.
- When in doubt, read `Taskfile.yml`, `pyproject.toml`, and `tests/conftest.py` — they encode the live conventions. The Sphinx docs under `docs/` cover user-facing flow.
