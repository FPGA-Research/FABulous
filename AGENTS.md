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
- **Pre-commit is enforced** (ruff, docstring linting, dependency hygiene, etc.). If a hook fails, fix the cause — don't `--no-verify`.

## Repository Layout

The package lives at `fabulous/` (lowercase — older docs may say `FABulous/`).

- `fabric_definition/` — dataclass-based fabric model (`Fabric`, `Tile`, `Bel`, `SwitchMatrix`, `Port` hierarchy, …).
- `file_parser/` — CSV/YAML, BEL HDL, FASM, and Python mux readers.
- `fabric_generator/` — emits Verilog/VHDL via `hdlgen`; also houses the GDS generator.
- `fabric_cad/` — bitstream spec, FASM→binary, nextpnr chip database. Bitstream binary I/O is in the external `FABulous-bit-gen` package.
- `geometry_generator/` — FABulator visualizer geometry.
- `fabulous_cli/` — interactive `cmd2` shell; new features usually need a shell command.
- `fabulous_api.py` — programmatic API used by CLI and tests.
- `tests/` — pytest suites; shared fixtures in `tests/conftest.py`.

## Coding Taste

Rules that make changes feel native. Follow them even when a tool's defaults disagree.

### Style

- **Python 3.12+**. Built-in generics only (`list[int]`, `X | None`); never `typing.List`/`Optional`.
- **Paths**: `pathlib.Path`. Never `os.path` or string concatenation.
- **Logging**: `loguru` (`from loguru import logger`). Not `print`, not stdlib `logging`.
- **Docstrings**: NumPy style — `pydoclint` + `interrogate` (≥95% coverage) enforce this.
- **Inline code in docstrings/comments**: use a single backtick (`` `models_pack` ``, `` `None` ``), not double (`` ``models_pack`` ``).
- **Naming**: this repo uses `camelCase` for variables/functions, `PascalCase` for classes, `CONSTANT_CASE` for module constants. Match existing files, don't "fix" to PEP 8.
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
- `cocotb` is available for HDL-level verification, not for Python logic.

## House Rules

- Don't edit the symlinked agent files (`CLAUDE.md`, `GEMINI.md`, `.cursorrules`, `.github/copilot-instructions.md`) — edit `AGENTS.md`.
- Don't add new top-level packages without a clear home in the layout above.
- When in doubt, read `Taskfile.yml`, `pyproject.toml`, and `tests/conftest.py` — they encode the live conventions. The Sphinx docs under `docs/` cover user-facing flow.
