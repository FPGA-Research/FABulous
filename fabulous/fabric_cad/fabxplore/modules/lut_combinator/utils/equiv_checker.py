"""Standalone formal equivalence test: original mapped LUT netlist vs mapped output.

This script intentionally focuses on LUT correctness:
- LUT* and FRAC cell types get behavioral models.
- All other cell types get synthetic pass-through models (input -> output),
  so top-level outputs are driven and equivalence is not vacuous due to blackboxes.
"""

from __future__ import annotations

import json
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pyosys.libyosys as ys

from fabulous.fabric_cad.fabxplore.modules.lut_combinator.core.verilog_model import (
    FracLutBehavioralModel,
)

_LUT_RE = re.compile(r"^LUT(\d+)$")


@dataclass(frozen=True)
class CellTypeShape:
    """Port width summary for one cell type."""

    port_widths: dict[str, int]
    parameter_names: tuple[str, ...]


@dataclass(frozen=True)
class EquivalenceCheckConfig:
    """Configuration for one LUT-focused formal equivalence run."""

    gold_verilog: Path
    gate_verilog: Path
    top_name: str
    frac_cell_name: str
    frac_lut_size: int
    num_shared_inputs: int


class LutEquivalenceChecker:
    """Run LUT-focused formal equivalence between two Verilog netlists."""

    def __init__(self, config: EquivalenceCheckConfig) -> None:
        self.config = config

    def run(self) -> None:
        """Run the LUT-focused formal equivalence check."""
        gold_cells = _extract_top_cells(
            self.config.gold_verilog, self.config.top_name, ys
        )
        gate_cells = _extract_top_cells(
            self.config.gate_verilog, self.config.top_name, ys
        )

        all_shapes = _collect_shapes(gold_cells, gate_cells)
        model_text = _build_model_library(
            shapes=all_shapes,
            frac_cell_name=self.config.frac_cell_name,
            frac_lut_size=self.config.frac_lut_size,
            num_shared_inputs=self.config.num_shared_inputs,
        )

        with tempfile.TemporaryDirectory(prefix="lut_comb_equiv_") as td:
            model_path = Path(td) / "equiv_models.v"
            model_path.write_text(model_text, encoding="utf-8")

            design = ys.Design()

            def run(cmd: str) -> None:
                """Run a Yosys command on the design."""
                ys.run_pass(cmd, design)

            run(f"read_verilog {model_path}")
            run(f"read_verilog {self.config.gold_verilog}")
            run(f"rename {self.config.top_name} {self.config.top_name}_gold")
            run(f"read_verilog {self.config.gate_verilog}")
            run(f"rename {self.config.top_name} {self.config.top_name}_gate")
            run(
                f"equiv_make {self.config.top_name}_gold "
                f"{self.config.top_name}_gate equiv"
            )
            run("hierarchy -top equiv")
            run("flatten")
            run("opt_clean")
            run("equiv_struct")
            run("equiv_simple -undef")
            run("equiv_induct -undef")
            run("equiv_simple -undef")
            run("equiv_status -assert")


def _extract_top_cells(
    verilog_path: Path, top_name: str, ys: object
) -> dict[str, dict]:
    """Extract the top-level cells from a Verilog file."""
    with tempfile.TemporaryDirectory(prefix="lut_comb_topjson_") as td:
        out_json = Path(td) / "top.json"
        design = ys.Design()
        ys.run_pass(f"read_verilog {verilog_path}", design)
        ys.run_pass(f"write_json {out_json}", design)
        obj = json.loads(out_json.read_text(encoding="utf-8"))

    modules = obj.get("modules", {})
    if top_name not in modules:
        available = ", ".join(sorted(modules.keys()))
        raise RuntimeError(
            f"Top module '{top_name}' not found in "
            f"{verilog_path}. Available: {available}"
        )
    return modules[top_name].get("cells", {})


def _collect_shapes(*cell_maps: dict[str, dict]) -> dict[str, CellTypeShape]:
    """Collect the shapes of all cell types from the given cell maps."""
    raw: dict[str, dict[str, int]] = {}
    raw_params: dict[str, set[str]] = {}

    for cmap in cell_maps:
        for cell in cmap.values():
            ctype = str(cell.get("type", "")).lstrip("\\")
            if not ctype:
                continue
            shape = raw.setdefault(ctype, {})
            params = raw_params.setdefault(ctype, set())
            conns = cell.get("connections", {})
            for pname, bits in conns.items():
                width = len(bits) if isinstance(bits, list) else 1
                shape[pname] = max(shape.get(pname, 0), width)
            for k in cell.get("parameters", {}):
                params.add(str(k))

    return {
        t: CellTypeShape(
            port_widths=pw, parameter_names=tuple(sorted(raw_params.get(t, set())))
        )
        for t, pw in raw.items()
    }


def _build_model_library(
    shapes: dict[str, CellTypeShape],
    frac_cell_name: str,
    frac_lut_size: int,
    num_shared_inputs: int,
) -> str:
    """Build a model library for the given shapes and FRAC LUT configuration."""
    lines: list[str] = []

    lut_widths = sorted(
        {int(m.group(1)) for t in shapes for m in [_LUT_RE.match(t)] if m is not None}
    )
    for w in lut_widths:
        lines.extend(_lut_model(w))
        lines.append("")

    if frac_cell_name in shapes:
        frac_model = FracLutBehavioralModel(
            name=frac_cell_name,
            lut_size=frac_lut_size,
            num_shared_inputs=num_shared_inputs,
            interface_width=max(frac_lut_size, 16),
            include_equiv_compat_params=True,
        )
        lines.extend(frac_model.to_lines())
        lines.append("")

    for ctype, shape in sorted(shapes.items()):
        if _LUT_RE.match(ctype):
            continue
        if ctype == frac_cell_name:
            continue
        if _is_yosys_builtin_cell(ctype):
            continue
        lines.extend(
            _passthrough_model(ctype, shape.port_widths, shape.parameter_names)
        )
        lines.append("")

    return "\n".join(lines)


def _is_yosys_builtin_cell(cell_type: str) -> bool:
    """Return whether a cell type is a Yosys built-in internal `$` cell."""
    return cell_type.startswith("$")


def _lut_model(width: int) -> list[str]:
    """Generate a Verilog model for a LUT of the given width."""
    init_width = 1 << width
    ports = [f"I{i}" for i in range(width)] + ["O"]
    idx_expr = ", ".join([f"I{i}" for i in reversed(range(width))])
    return [
        f"module LUT{width}({', '.join(ports)});",
        f"  input {', '.join(f'I{i}' for i in range(width))};",
        "  output O;",
        f"  parameter [{init_width - 1}:0] INIT = {init_width}'b0;",
        f"  wire [{width - 1}:0] _idx = {{{idx_expr}}};",
        "  assign O = INIT[_idx];",
        "endmodule",
    ]


def _passthrough_model(
    cell_type: str, port_widths: dict[str, int], parameter_names: tuple[str, ...]
) -> list[str]:
    """Generate a pass-through Verilog model for a cell type with the given shape."""
    ports = sorted(port_widths)
    outputs = _infer_outputs(ports)
    inputs = [p for p in ports if p not in outputs]

    lines = [f"module {cell_type}({', '.join(ports)});"]
    for pname in parameter_names:
        lines.append(f"  parameter {pname} = 0;")

    for p in inputs:
        lines.append(f"  {_decl('input', p, port_widths[p])}")
    for p in outputs:
        lines.append(f"  {_decl('output', p, port_widths[p])}")

    for outp in outputs:
        src = _pick_source_for_output(outp, inputs)
        if src is None:
            lines.append(f"  assign {outp} = {_zero_const(port_widths[outp])};")
        else:
            lines.append(f"  assign {outp} = {src};")

    lines.append("endmodule")
    return lines


def _infer_outputs(ports: list[str]) -> list[str]:
    """Infer the output ports from a list of ports based on naming conventions."""
    out: list[str] = []
    for p in ports:
        u = p.upper()
        if u in {"O", "Q", "Y", "Z", "PAD", "OUT", "DO", "DOUT"}:
            out.append(p)
            continue
        if re.fullmatch(r"[OQY]\d+", u):
            out.append(p)
            continue
        if re.fullmatch(r"(?:AD|BD)\d+", u):
            out.append(p)
            continue
        if u.startswith(("OUT", "DOUT", "RDATA")):
            out.append(p)
            continue

    if not out and ports:
        # Keep model well-formed: if nothing looks like output,
        # pick one deterministic port.
        out.append(ports[-1])

    return out


def _pick_source_for_output(output_port: str, inputs: list[str]) -> str | None:
    """Pick a source input for the given output port based on naming conventions."""
    if not inputs:
        return None

    in_set = set(inputs)
    up = output_port.upper()

    if up in {"O", "Q", "Y", "PAD"}:
        for cand in ("I", "D", "A", "B"):
            if cand in in_set:
                return cand

    m = re.fullmatch(r"(?:AD|BD)(\d+)", up)
    if m:
        dn = f"D{m.group(1)}"
        if dn in in_set:
            return dn

    for cand in inputs:
        cu = cand.upper()
        if any(
            tok in cu
            for tok in (
                "CLK",
                "CLOCK",
                "RST",
                "RESET",
                "SET",
                "CLR",
                "EN",
                "WE",
                "CE",
                "T",
            )
        ):
            continue
        return cand

    return inputs[0]


def _decl(direction: str, name: str, width: int) -> str:
    """Generate a declaration for a port with the given direction, name, and width."""
    if width <= 1:
        return f"{direction} {name};"
    return f"{direction} [{width - 1}:0] {name};"


def _zero_const(width: int) -> str:
    """Generate a Verilog constant with all bits set to zero for the given width."""
    return "1'b0" if width <= 1 else f"{width}'b0"
