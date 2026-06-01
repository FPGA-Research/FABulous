#!/usr/bin/env python3
"""Removes gate-level X-pessimism for FABulous post-PnR (hardened) fabric simulation.

Background
----------

After hardening, OpenROAD resynthesises the X-optimistic ``cus_mux161`` LUT/mux
structures into generic AOI/NAND std cells that are X-pessimistic. Unused fabric
routing therefore forms a self-sustaining X web that leaks into used logic, and
the user flip-flops power up / capture X that the synchronous reset cannot scrub
(the reset path runs through the same X-pessimistic gates; the async reset pin is
tied off). This is the #252 / #719 flop-X manifestation.

This generator emits two one-shot actions fired after configuration upload:

1. ``$deposit`` 0 onto every fabric-level net  -> breaks the combinational
   X web. ``$deposit`` is overrideable, so used (toggling) nets keep working;
   unused nets settle to a defined constant.
2. A momentary ``force`` of every flip-flop async reset pin to its active level
   (a reset pulse), then ``release`` -> clears flop *state* X that no net
   deposit can reach.

Neither action can hide a design bug: the design output is still compared
against the golden reference, so a wrong value can only cause a visible
mismatch, never a false pass.

The flip-flop async reset pin name is PDK-specific; the three PDKs FABulous
hardens for all use an active-low async reset, so the pulse drives it to 0.

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

# Async reset pin of the flip-flop std cell the hardened netlist binds against,
# per PDK. All three are active-low, so the reset pulse drives the pin to 0.
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


def collect_reset_nets(tile_dir: Path, reset_pin: str) -> dict[str, list[str]]:
    """Map each tile type to the unique nets driving its flop reset pins.

    Every tile netlist is scanned; tiles with no flip-flop (no reset-pin
    connection) drop out naturally, so no per-fabric tile-type list is needed.

    Parameters
    ----------
    tile_dir : Path
        The project ``Tile`` directory.
    reset_pin : str
        The flip-flop async reset pin name to match (PDK-specific).

    Returns
    -------
    dict[str, list[str]]
        Tile type (the ``Tile/<type>`` directory name) -> reset net names.
    """
    pin_re = re.compile(rf"\.{re.escape(reset_pin)}\(([^)]*)\)")
    out: dict[str, list[str]] = {}
    for nl in sorted(tile_dir.glob("*/macro/final_views/nl/*.nl.v")):
        ttype = nl.parents[3].name
        nets = sorted(set(pin_re.findall(nl.read_text())))
        if nets:
            out.setdefault(ttype, [])
            out[ttype].extend(n for n in nets if n not in out[ttype])
    return out


def collect_instances(efpga: Path, types: list[str]) -> list[tuple[str, str]]:
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
    """Build a hierarchical reference, preserving escaped-identifier syntax.

    Parameters
    ----------
    top_inst : str
        Hierarchical path to the gate-level fabric core.
    net : str
        Net name relative to the fabric core.

    Returns
    -------
    str
        ``<top_inst>.<net>``; escaped identifiers keep their trailing space.
    """
    suffix = net + " " if net.startswith("\\") else net
    return f"{top_inst}.{suffix}"


def main() -> None:
    """Emit the X-init include consumed by the gate-level testbench."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--efpga", required=True, type=Path)
    ap.add_argument("--tile-dir", required=True, type=Path)
    ap.add_argument(
        "--pdk",
        required=True,
        choices=sorted(_RESET_PIN_BY_PDK),
        help="PDK whose flip-flop async reset pin should be pulsed",
    )
    ap.add_argument(
        "--top-inst",
        default="top_i.eFPGA_inst",
        help="hierarchical path to the gate-level fabric core",
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
    reset_nets = collect_reset_nets(args.tile_dir, reset_pin)
    instances = collect_instances(args.efpga, sorted(reset_nets))

    flop_resets: list[str] = []
    for ttype, inst in instances:
        for rnet in reset_nets.get(ttype, []):
            flop_resets.append(net_ref(args.top_inst, f"{inst}.{rnet}"))

    L: list[str] = []
    L.append("// AUTO-GENERATED by gen_gl_xinit.py -- do not edit by hand.")
    L.append(f"// Gate-level X-pessimism removal for hardened-fabric sim ({args.pdk}).")
    L.append("initial begin : gl_xinit")
    L.append(f"    wait ({args.trigger} === 1'b1);  // configuration upload complete")
    L.append("    #1;")
    L.append("    // 1) break the unused-routing combinational X web (overrideable)")
    for n in nets:
        L.append(f"    $deposit({net_ref(args.top_inst, n)}, 1'b0);")
    L.append(
        f"    // 2) async-reset pulse ({reset_pin}, active-low): clear flop state X"
    )
    for r in flop_resets:
        L.append(f"    force {r}= 1'b0;")
    L.append("    #1;")
    for r in flop_resets:
        L.append(f"    release {r};")
    L.append(
        f'    $display("[gl_xinit] %0d deposits, %0d flop resets @ %0t",'
        f" {len(nets)}, {len(flop_resets)}, $time);"
    )
    L.append("end")

    args.out.write_text("\n".join(L) + "\n")
    sys.stderr.write(
        f"wrote {args.out}: {len(nets)} deposits, {len(flop_resets)} flop async "
        f"resets ({len(instances)} flop tiles, reset pin {reset_pin})\n"
    )


if __name__ == "__main__":
    main()
