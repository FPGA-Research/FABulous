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

This generator emits two one-shot actions fired after configuration upload,
each gated so it touches only state that is still X -- a net or flop the
configuration already drives to a defined value is left untouched:

1. ``if (net === 1'bx) $deposit(net, 0)`` on every fabric-level net -> breaks
   the combinational X web. The X-only guard means a net the configuration
   drives to a real constant is never overwritten with 0; only genuinely
   undriven (unused) nets are pinned to a defined constant.
2. A momentary ``force`` of a flip-flop async reset pin to its active level
   (a reset pulse), then ``release`` -> clears flop *state* X that no net
   deposit can reach. Gated on that flop's own ``Q`` being X, so a flop already
   holding a defined value is left alone.

Neither action can hide a design bug: the design output is still compared
against the golden reference, so a wrong value can only cause a visible
mismatch, never a false pass. Because both actions are X-only, they can only
*add* definedness where the design left X; they never change a value the
configuration or datapath already resolved.

The flip-flop async reset pin name is PDK-specific; the three PDKs FABulous
hardens for all use an active-low async reset, so the pulse drives it to 0.

Why both actions fire *after* config upload (``config_done``)
------------------------------------------------------------

The X originates from uninitialized state: flops and config-memory latches power
up X. The deposit is overrideable, so it only sticks where nothing else drives.
During upload the config-memory latches resolve frame by frame, and every
not-yet-written bit drives an X mux select that re-drives the unused-routing web;
meanwhile ``UserCLK`` is toggling, so the user flops re-capture that X each cycle.
A one-shot scrub *before* upload is therefore undone -- the deposit is re-driven
and the flops re-dirtied before ``config_done``, with no later pass to clear them.
``config_done`` is the first point where config memory is fully defined, so the
deposit holds and the flop reset is final.

This was verified empirically: triggering the scrub before the upload loop
instead leaves every fabric output X and the golden comparison fails outright,
while triggering it at ``config_done`` passes.

Limitation: bitstream-set power-on flop values
----------------------------------------------

The reset pulse drives a user flop to the async-reset level (0), but only when
that flop still holds X (action 2 is X-only). For the current FABulous DFF
(``LUT4c_frame_config_dffesr``) this is moot: the bitstream only configures the
*synchronous* reset target ``c_reset_value`` (applied by the design's own
``SR``), never the power-up runtime value, so every user flop is X at
``config_done`` and the pulse simply defines it.

A future fabric that adds a true INIT bit -- letting the bitstream set a flop's
power-on runtime value -- is largely covered by the X-only guard: if that value
is materialised into the flop's ``Q`` by ``config_done``, ``Q`` is no longer X
and the pulse skips it, preserving the configured value. The guard does *not*
cover an INIT bit staged in config memory but not yet reflected in ``Q`` --
there the flop is still X and the pulse defaults it to 0. The fix in that case
is to pulse each flop toward its configured INIT value instead of a hard 0
(moving the pulse before config does not help -- the X returns during upload,
as verified above).

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


# A gate-level cell instantiation: ``CELL inst ( .PIN(net), ... );``. Net names
# (including escaped identifiers) never contain ``)`` or ``;``, so the body runs
# to the first ``);``.
_INST_RE = re.compile(r"\b\w+\s+\S+\s*\((.*?)\)\s*;", re.DOTALL)


def collect_flop_pins(
    tile_dir: Path, reset_pin: str
) -> dict[str, list[tuple[str, str]]]:
    """Map each tile type to its flops' ``(reset net, Q net)`` pairs.

    Flops are located by the presence of both the async reset pin and a ``Q``
    output on the same cell instantiation, so this is std-cell-name agnostic.
    Pairing the reset net with its own ``Q`` lets the X-init pulse a flop only
    when that flop actually holds X, never overwriting a defined value.

    Parameters
    ----------
    tile_dir : Path
        The project ``Tile`` directory.
    reset_pin : str
        The flip-flop async reset pin name to match (PDK-specific).

    Returns
    -------
    dict[str, list[tuple[str, str]]]
        Tile type (the ``Tile/<type>`` directory name) -> list of
        ``(reset net, Q net)``, one entry per flop instance.
    """
    rpin = re.compile(rf"\.{re.escape(reset_pin)}\(\s*(.*?)\s*\)")
    qpin = re.compile(r"\.Q\(\s*(.*?)\s*\)")
    out: dict[str, list[tuple[str, str]]] = {}
    for nl in sorted(tile_dir.glob("*/macro/final_views/nl/*.nl.v")):
        ttype = nl.parents[3].name
        pairs: list[tuple[str, str]] = []
        for body in _INST_RE.findall(nl.read_text()):
            rm = rpin.search(body)
            qm = qpin.search(body)
            if rm and qm:
                pairs.append((rm.group(1).strip(), qm.group(1).strip()))
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
        help="PDK whose flip-flop async reset pin should be pulsed",
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
    flop_pins = collect_flop_pins(args.tile_dir, reset_pin)
    instances = collect_flop_tile_instances(args.efpga, sorted(flop_pins))

    flop_pulses: list[tuple[str, str]] = []  # (reset net ref, Q net ref) per flop
    for ttype, inst in instances:
        for rnet, qnet in flop_pins.get(ttype, []):
            flop_pulses.append(
                (
                    leaf_ref(args.top_inst, inst, rnet),
                    leaf_ref(args.top_inst, inst, qnet),
                )
            )

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
    L.append(
        f"    // 2) async-reset pulse ({reset_pin}, active-low): clear flop state X."
    )
    L.append("    //    X-only: a flop already holding a defined value (e.g. a future")
    L.append("    //    INIT-bit power-on value) is left alone, never forced to 0.")
    for rnet, qnet in flop_pulses:
        L.append(f"    if ({qnet} === 1'bx) force {rnet}= 1'b0;")
    L.append("    #1;")
    for rnet, _qnet in flop_pulses:
        L.append(f"    release {rnet};")
    L.append(
        f'    $display("[gl_xinit] %0d deposits, %0d flop resets @ %0t",'
        f" {len(nets)}, {len(flop_pulses)}, $time);"
    )
    L.append("end")

    args.out.write_text("\n".join(L) + "\n")
    sys.stderr.write(
        f"wrote {args.out}: {len(nets)} deposits, {len(flop_pulses)} flop async "
        f"resets ({len(instances)} flop tiles, reset pin {reset_pin})\n"
    )


if __name__ == "__main__":
    main()
