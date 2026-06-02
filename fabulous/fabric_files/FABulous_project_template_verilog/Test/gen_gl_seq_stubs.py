#!/usr/bin/env python3
"""Behavioural stubs for sequential std cells some simulators cannot clock.

Why this exists
---------------

Gate-level simulation of a hardened FABulous fabric must use the PDK's
*timing-annotated* cell models: the alternative ``FUNCTIONAL`` models are
zero-delay, and the unconfigured fabric's combinational routing loops then
oscillate forever at ``t=0`` (a livelock -- simulation time never advances).

Some simulators, notably Icarus Verilog 12, do not drive the negative-timing
``$setuphold`` *delayed* nets that the timing models route a sequential cell's
data and clock through. Those nets sit at ``z``, so the cell's internal UDP is
fed ``z`` and its output is stuck X for the whole run -- no X-init can revive a
flop (or config latch) that never clocks. sky130's ``dfxtp`` / ``dlxtp`` hit
this; gf180's ``dffq`` / ``latq`` wire their UDP directly and are unaffected.

This generator emits a small Verilog file of *behavioural* replacements for the
sequential cells the netlists instantiate, plus filtered copies of the PDK sim
libraries with those module definitions removed (so there is no duplicate). The
combinational cells keep their timing models -- their delays are what stop the
livelock -- while the sequential cells become plain edge flops / level latches
the simulator can evaluate. This changes only X-pessimism behaviour, never
logic: the design output is still compared against the golden reference.

Usage
-----
    python3 gen_gl_seq_stubs.py \
        --efpga ../Fabric/macro/final_views/nl/eFPGA.nl.v \
        --tile-dir ../Tile \
        --sim-lib /path/to/sky130_fd_sc_hd.v \
        --out-dir build/gl_stubs

Writes ``<out-dir>/gl_seq_stubs.v`` and, for each ``--sim-lib``, a filtered copy
``<out-dir>/<name>`` with the stubbed modules excised. Prints the resulting
source list (filtered libs first, then the stub file) one path per line on
stdout so the caller can splice it into the simulator command in place of the
original ``--sim-lib`` files.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Clock-pin names that mark an edge-triggered flop (vs a gate-enabled latch).
_CLOCK_PINS = ("CLK", "CK", "GCLK", "CLK_N")
# Active-low async reset / set pins, by the level the cell drives when asserted.
_RESET_PINS = ("RESET_B", "RN", "RESETB", "CLRB", "CLR_B")
_SET_PINS = ("SET_B", "SN", "SETB", "PRE_B", "PRESET_B")
# Power / ground / well pins to drop from a stub's port list.
_POWER_PINS = frozenset({"VPWR", "VGND", "VPB", "VNB", "VNW", "VDD", "VSS", "VPW"})

# A cell instantiation: ``CELL inst ( .PIN(net), ... );`` -- the body runs to the
# first ``);`` because net names never contain ``)`` or ``;``.
_INST_RE = re.compile(r"^\s*(\w+)\s+\S+\s*\(", re.MULTILINE)


def collect_used_cells(netlists: list[Path]) -> set[str]:
    """Return the set of std-cell module names instantiated across ``netlists``.

    Parameters
    ----------
    netlists : list[Path]
        Fabric and tile gate-level netlists.

    Returns
    -------
    set[str]
        Every cell type instantiated at least once.
    """
    used: set[str] = set()
    for nl in netlists:
        for m in _INST_RE.finditer(nl.read_text()):
            used.add(m.group(1))
    return used


def parse_module_ports(lib_text: str, cell: str) -> dict[str, str] | None:
    """Return ``{port: direction}`` for ``cell``'s first definition in ``lib_text``.

    Parameters
    ----------
    lib_text : str
        Contents of a PDK sim-library file.
    cell : str
        Module name to look up.

    Returns
    -------
    dict[str, str] | None
        Port name -> ``"input"`` / ``"output"`` (power pins dropped), or ``None``
        if the module is not found.
    """
    start = re.search(rf"^module {re.escape(cell)}\b", lib_text, re.MULTILINE)
    if not start:
        return None
    end = lib_text.find("endmodule", start.end())
    body = lib_text[start.start() : end if end != -1 else len(lib_text)]
    ports: dict[str, str] = {}
    for direction in ("input", "output"):
        for m in re.finditer(rf"\b{direction}\b([^;]*);", body):
            for name in m.group(1).split(","):
                name = name.strip()
                if name and name not in _POWER_PINS:
                    ports[name] = direction
    return ports


def first_match(names: list[str], candidates: tuple[str, ...]) -> str | None:
    """Return the first of ``candidates`` present in ``names``, else ``None``."""
    return next((c for c in candidates if c in names), None)


def stub_for(cell: str, ports: dict[str, str]) -> str | None:
    """Build a behavioural Verilog stub for sequential ``cell``, or ``None``.

    Parameters
    ----------
    cell : str
        Module name.
    ports : dict[str, str]
        Port directions from :func:`parse_module_ports`.

    Returns
    -------
    str | None
        A module definition string, or ``None`` if ``cell`` is not a sequential
        cell (no ``Q`` output, or no clock/gate input -> combinational).
    """
    ins = [p for p, d in ports.items() if d == "input"]
    if "Q" not in ports:
        return None
    clk = first_match(ins, _CLOCK_PINS)
    gate = first_match(ins, ("GATE", "E", "EN", "G"))
    if clk is None and gate is None:
        return None  # not sequential
    data = "D" if "D" in ins else None
    if data is None:
        return None  # scan/complex cell we should not guess at
    rst = first_match(ins, _RESET_PINS)
    setp = first_match(ins, _SET_PINS)
    has_qn = "Q_N" in ports

    decl = ", ".join(f"input {p}" for p in ins) + ", output reg Q"
    if has_qn:
        decl += ", output Q_N"
    lines = [f"module {cell} ({decl});"]
    if clk is not None:
        # active-low async reset / set when the cell exposes one
        edges = [f"posedge {clk}"]
        if rst:
            edges.append(f"negedge {rst}")
        if setp:
            edges.append(f"negedge {setp}")
        lines.append(f"  always @({' or '.join(edges)})")
        body = ""
        if rst:
            body += f"if (!{rst}) Q <= 1'b0; else "
        if setp:
            body += f"if (!{setp}) Q <= 1'b1; else "
        lines.append(f"    {body}Q <= {data};")
    else:
        lines.append(f"  always @* if ({gate}) Q = {data};")
    if has_qn:
        lines.append("  assign Q_N = ~Q;")
    lines.append("endmodule")
    return "\n".join(lines)


def filter_lib(lib_text: str, cells: set[str]) -> str:
    """Return ``lib_text`` with every ``module <cell> ... endmodule`` removed.

    Parameters
    ----------
    lib_text : str
        Contents of a PDK sim-library file.
    cells : set[str]
        Module names to excise (all of their guarded variants).

    Returns
    -------
    str
        The library text without the named modules.
    """
    out: list[str] = []
    drop = False
    header = re.compile(r"^module (\w+)\b")
    for line in lib_text.splitlines():
        if not drop:
            m = header.match(line)
            if m and m.group(1) in cells:
                drop = True
                continue
            out.append(line)
            continue
        # Inside a dropped module: keep preprocessor directives so the file's
        # `ifdef/`else/`endif nesting stays balanced (some PDKs, e.g. gf180,
        # interleave those with the module declaration), but drop the body.
        if line.lstrip().startswith("`"):
            out.append(line)
        if line.startswith("endmodule"):
            drop = False
    return "\n".join(out) + "\n"


def main() -> None:
    """Emit behavioural sequential-cell stubs and filtered PDK libraries."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--efpga", required=True, type=Path)
    ap.add_argument("--tile-dir", required=True, type=Path)
    ap.add_argument(
        "--sim-lib",
        required=True,
        action="append",
        type=Path,
        help="PDK sim-library Verilog file (repeatable)",
    )
    ap.add_argument("--out-dir", required=True, type=Path)
    args = ap.parse_args()

    tile_nls = sorted(args.tile_dir.glob("*/macro/final_views/nl/*.nl.v"))
    used = collect_used_cells([args.efpga, *tile_nls])

    args.out_dir.mkdir(parents=True, exist_ok=True)

    # Find which used cells are sequential, and build their stubs.
    lib_texts = {lib: lib.read_text() for lib in args.sim_lib}
    stubs: dict[str, str] = {}
    for cell in sorted(used):
        for text in lib_texts.values():
            ports = parse_module_ports(text, cell)
            if ports is None:
                continue
            stub = stub_for(cell, ports)
            if stub is not None:
                stubs[cell] = stub
            break

    if not stubs:
        # Nothing to stub: emit the libraries unchanged so the caller's source
        # list stays valid.
        for lib in args.sim_lib:
            sys.stdout.write(f"{lib}\n")
        sys.stderr.write("no sequential cells stubbed\n")
        return

    stub_path = args.out_dir / "gl_seq_stubs.v"
    stub_path.write_text(
        "// AUTO-GENERATED by gen_gl_seq_stubs.py -- do not edit by hand.\n"
        "// Behavioural replacements for sequential cells the simulator cannot\n"
        "// clock through the PDK timing models. See the generator's docstring.\n"
        "`timescale 1ps / 1ps\n" + "\n".join(stubs[c] for c in sorted(stubs)) + "\n"
    )

    cells = set(stubs)
    out_libs: list[Path] = []
    for lib in args.sim_lib:
        filtered = args.out_dir / lib.name
        # Force an explicit `timescale: some PDK models (gf180) ship without one,
        # so under iverilog their cells inherit whatever scale was last set and
        # their specify delays are misread -- enough to leave switching nets X.
        # The vendor convention for these libs is 1ns/1ps (sky130 declares it).
        filtered.write_text(
            "`timescale 1ns / 1ps\n" + filter_lib(lib_texts[lib], cells)
        )
        out_libs.append(filtered)

    for lib in out_libs:
        sys.stdout.write(f"{lib}\n")
    sys.stdout.write(f"{stub_path}\n")
    sys.stderr.write(
        f"stubbed {len(stubs)} sequential cell(s): {', '.join(sorted(stubs))}\n"
    )


if __name__ == "__main__":
    main()
