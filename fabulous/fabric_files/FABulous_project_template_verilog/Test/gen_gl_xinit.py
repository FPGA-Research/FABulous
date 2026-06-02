#!/usr/bin/env python3
"""Generate ``force_block.vh`` to remove gate-level X-pessimism in hardened sim.

A hardened fabric powers up all-X (OpenROAD resynthesises FABulous's X-optimistic
cells into X-pessimistic gates), and the X never clears on its own. This script
emits ``force_block.vh`` (compiled in with ``-DGL_SIM``) with two one-shot actions
fired at ``config_done``:

1. ``$deposit 0`` on every still-X fabric net -- breaks the combinational X web.
2. A per-flop state clear (a net deposit cannot reach a flop, which re-drives its
   own ``Q``). It is PDK-adaptive, because OpenROAD maps the FABulous DFF to a
   different cell per PDK: a reset-pin pulse where the mapped cell has an async
   reset (IHP ``sg13g2_dfrbpq``, ``RESET_B``), a ``$deposit(Q, 0)`` where it does
   not (sky130 ``dfxtp``, gf180 ``dffq``).

Both actions are **X-only** (gated on the target still being X), so they only add
definedness where the design left X and can never overwrite a configured value or
hide a bug -- a wrong value still mismatches the golden reference.

Implication: a future fabric with a power-on INIT bit staged in config memory but
not yet reflected in ``Q`` would be defaulted to 0 by the flop clear; that case
needs the clear to target the configured INIT value instead.

Usage
-----
    python3 gen_gl_xinit.py \
        --efpga ../Fabric/macro/final_views/nl/eFPGA.nl.v \
        --tile-dir ../Tile \
        --pdk ihp-sg13g2 \
        --top-inst top_i.eFPGA_inst \
        --trigger config_done \
        --out force_block.vh
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Active-low async reset pin to look for, per PDK. Presence is decided per
# instance: IHP maps to a resettable cell (sg13g2_dfrbpq, RESET_B); sky130 / gf180
# map to resetless DFFs, cleared by depositing Q instead.
_RESET_PIN_BY_PDK: dict[str, str] = {
    "ihp-sg13g2": "RESET_B",
    "sky130A": "RESET_B",
    "gf180mcuD": "RN",
}


def collect_efpga_nets(efpga: Path) -> list[str]:
    """Return every net declared at the fabric top level.

    Parameters
    ----------
    efpga : Path
        The fabric netlist (``eFPGA.nl.v``).

    Returns
    -------
    list[str]
        Net names, range prefixes stripped; escaped identifiers keep their
        leading backslash.
    """
    names: list[str] = []
    for line in efpga.read_text().splitlines():
        s = line.strip()
        if not s.startswith("wire "):
            continue
        body = s[len("wire ") :].rstrip(";").strip()
        for tok in body.split(","):
            tok = tok.strip()
            if not tok:
                continue
            tok = re.sub(r"^\[[^\]]*\]\s*", "", tok)  # drop range prefix
            names.append(tok)
    return names


# A gate-level cell instantiation: ``CELL inst ( .PIN(net), ... );``. Net names
# (including escaped identifiers) never contain ``)`` or ``;``, so the body runs
# to the first ``);``.
_INST_RE = re.compile(r"\b\w+\s+\S+\s*\((.*?)\)\s*;", re.DOTALL)


def collect_flops(
    tile_dir: Path, reset_pin: str
) -> dict[str, list[tuple[str, str | None]]]:
    """Map each tile type to its flip-flops' ``(Q net, reset net | None)`` pairs.

    A flip-flop is any cell instantiation carrying both a ``Q`` output and a
    ``CLK`` edge-clock pin. The ``CLK`` requirement is what isolates the
    edge-triggered user flops from the gate-enabled configuration-memory latches
    (``latq`` / ``dlxtp``), which also expose a ``Q`` but are enabled by ``E`` /
    ``GATE`` and have no ``CLK``; it stays std-cell-name agnostic. If the flop
    also carries the PDK async reset pin its reset net is recorded, otherwise the
    pair holds ``None`` -- the two get different X-init treatment (a reset pulse
    vs a ``Q`` deposit). Either way the action is gated on the flop's own ``Q``
    being X, so a flop already holding a defined value is left alone.

    Parameters
    ----------
    tile_dir : Path
        The project ``Tile`` directory.
    reset_pin : str
        The flip-flop async reset pin name to match (PDK-specific). A flop whose
        instantiation lacks it is paired with ``None``.

    Returns
    -------
    dict[str, list[tuple[str, str | None]]]
        Tile type (the ``Tile/<type>`` directory name) -> list of
        ``(Q net, reset net | None)``, one entry per flop instance.
    """
    rpin = re.compile(rf"\.{re.escape(reset_pin)}\(\s*(.*?)\s*\)")
    qpin = re.compile(r"\.Q\(\s*(.*?)\s*\)")
    has_clk = re.compile(r"\.CLK\(")
    out: dict[str, list[tuple[str, str | None]]] = {}
    for nl in sorted(tile_dir.glob("*/macro/final_views/nl/*.nl.v")):
        ttype = nl.parents[3].name
        pairs: list[tuple[str, str | None]] = []
        for body in _INST_RE.findall(nl.read_text()):
            qm = qpin.search(body)
            if not qm or not has_clk.search(body):
                continue
            rm = rpin.search(body)
            reset_net = rm.group(1).strip() if rm else None
            pairs.append((qm.group(1).strip(), reset_net))
        if pairs:
            out[ttype] = pairs
    return out


def collect_flop_tile_instances(efpga: Path, types: list[str]) -> list[tuple[str, str]]:
    """Return ``(tile_type, instance_name)`` for every flop-bearing tile instance.

    Parameters
    ----------
    efpga : Path
        The fabric netlist (``eFPGA.nl.v``).
    types : list[str]
        Tile types known to contain flip-flops.

    Returns
    -------
    list[tuple[str, str]]
        One entry per matching tile instantiation.
    """
    inst_re = re.compile(r"^\s*({types})\s+(\S+)\s+\(".format(types="|".join(types)))
    found: list[tuple[str, str]] = []
    for line in efpga.read_text().splitlines():
        m = inst_re.match(line)
        if m:
            found.append((m.group(1), m.group(2)))
    return found


def net_ref(top_inst: str, net: str) -> str:
    """Build a hierarchical reference of a net, preserving escaped-identifier syntax.

    Parameters
    ----------
    top_inst : str
        Hierarchical path to the gate-level fabric top level instance.
    net : str
        Net name relative to the fabric top level instance.

    Returns
    -------
    str
        ``<top_inst>.<net>``; escaped identifiers keep their trailing space.
    """
    suffix = net + " " if net.startswith("\\") else net
    return f"{top_inst}.{suffix}"


def leaf_ref(top_inst: str, inst: str, net: str) -> str:
    """Build a hierarchical reference of a tile-internal net, preserving escapes.

    Parameters
    ----------
    top_inst : str
        Hierarchical path to the gate-level fabric top level instance.
    inst : str
        Tile instance name (relative to the fabric top level instance).
    net : str
        Net name relative to the tile instance.

    Returns
    -------
    str
        ``<top_inst>.<inst>.<net>``; an escaped leaf net keeps its trailing space.
    """
    leaf = net + " " if net.startswith("\\") else net
    return f"{top_inst}.{inst}.{leaf}"


def main() -> None:
    """Emit the X-init include consumed by the gate-level testbench."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--efpga", required=True, type=Path)
    ap.add_argument("--tile-dir", required=True, type=Path)
    ap.add_argument(
        "--pdk",
        required=True,
        choices=sorted(_RESET_PIN_BY_PDK),
        help="PDK whose flip-flop async reset pin should be pulsed (when its "
        "mapped flop has one; resetless flops are cleared by depositing Q)",
    )
    ap.add_argument(
        "--top-inst",
        default="top_i.eFPGA_inst",
        help="hierarchical path to the gate-level fabric top level instance",
    )
    ap.add_argument(
        "--trigger",
        default="config_done",
        help="testbench signal that is 1 once config upload finished",
    )
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    reset_pin = _RESET_PIN_BY_PDK[args.pdk]

    nets = collect_efpga_nets(args.efpga)
    flops = collect_flops(args.tile_dir, reset_pin)
    instances = collect_flop_tile_instances(args.efpga, sorted(flops))

    # Split flops by how their state X is cleared: a reset pulse where the mapped
    # cell has an async reset pin, a Q deposit where it does not.
    reset_flops: list[tuple[str, str]] = []  # (Q net ref, reset net ref)
    deposit_flops: list[str] = []  # Q net ref
    for ttype, inst in instances:
        for qnet, rnet in flops.get(ttype, []):
            qref = leaf_ref(args.top_inst, inst, qnet)
            if rnet is not None:
                reset_flops.append((qref, leaf_ref(args.top_inst, inst, rnet)))
            else:
                deposit_flops.append(qref)

    L: list[str] = []
    L.append("// AUTO-GENERATED by gen_gl_xinit.py -- do not edit by hand.")
    L.append(f"// Gate-level X-pessimism removal for hardened-fabric sim ({args.pdk}).")
    L.append("initial begin : gl_xinit")
    L.append(f"    wait ({args.trigger} === 1'b1);  // configuration upload complete")
    L.append("    #1;")
    L.append("    // 1) break the unused-routing combinational X web. X-only: a net")
    L.append("    //    the configuration already drives to a constant is left alone,")
    L.append("    //    so a real configured value is never overwritten with 0.")
    for n in nets:
        ref = net_ref(args.top_inst, n)
        L.append(f"    if ({ref} === 1'bx) $deposit({ref}, 1'b0);")
    L.append("    // 2) clear flop state X (a net deposit cannot reach it -- the flop")
    L.append("    //    re-drives its own Q). X-only: a flop already holding a defined")
    L.append("    //    value (e.g. a future INIT-bit power-on value) is left alone.")
    if reset_flops:
        L.append(f"    //    2a) async-reset pulse ({reset_pin}, active-low).")
        for qref, rref in reset_flops:
            L.append(f"    if ({qref} === 1'bx) force {rref}= 1'b0;")
    if deposit_flops:
        L.append("    //    2b) resetless flops: seed Q directly.")
        for qref in deposit_flops:
            L.append(f"    if ({qref} === 1'bx) $deposit({qref}, 1'b0);")
    L.append("    #1;")
    for _qref, rref in reset_flops:
        L.append(f"    release {rref};")
    L.append(
        f'    $display("[gl_xinit] %0d deposits, %0d flop resets, %0d flop deposits'
        f' @ %0t", {len(nets)}, {len(reset_flops)}, {len(deposit_flops)}, $time);'
    )
    L.append("end")

    args.out.write_text("\n".join(L) + "\n")
    sys.stderr.write(
        f"wrote {args.out}: {len(nets)} net deposits, {len(reset_flops)} flop "
        f"reset pulses, {len(deposit_flops)} flop Q deposits "
        f"({len(instances)} flop tile instances, reset pin {reset_pin})\n"
    )


if __name__ == "__main__":
    main()
