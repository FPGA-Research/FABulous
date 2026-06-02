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
2. A per-flop clear of flop *state* X that no net deposit can reach (a flop's own
   ``Q`` is re-driven by the flop, so depositing the routing net it feeds does
   not stick). Gated on that flop's own ``Q`` being X, so a flop already holding
   a defined value is left alone. The clear is **PDK-adaptive**, because OpenROAD
   does not map the FABulous DFF to the same std cell for every PDK:

   - When the mapped flop carries an async reset pin (IHP ``sg13g2_dfrbp`` has
     ``RESET_B``), a momentary ``force`` of that pin to its active level (a reset
     pulse), then ``release``, drives the flop's internal state to 0 through the
     cell's reset input.
   - When the mapped flop is a plain DFF with no reset pin (sky130 ``dfxtp``,
     gf180 ``dffq`` -- the bitstream configures only the *synchronous* reset, so
     OpenROAD keeps a resetless cell), there is no reset pin to pulse, so the
     state is seeded directly with ``if (Q === 1'bx) $deposit(Q, 0)``. The
     deposit seeds the flop's state, after which it captures its now-defined
     ``D`` on the next clock -- verified on the worst case, a self-feedback
     toggle (``D = ~Q``) the net deposits cannot reach.

Neither action can hide a design bug: the design output is still compared
against the golden reference, so a wrong value can only cause a visible
mismatch, never a false pass. Because both actions are X-only, they can only
*add* definedness where the design left X; they never change a value the
configuration or datapath already resolved.

Do not compile the cell models with ``-DFUNCTIONAL``
----------------------------------------------------

The simulation must use the **timing-annotated** cell models (``iverilog
-gspecify``, *no* ``-DFUNCTIONAL``). The ``FUNCTIONAL`` variants are zero-delay,
so the unconfigured fabric's combinational routing loops oscillate forever at
``t=0`` -- a livelock in which simulation time never advances and the run hangs
before it ever reaches ``config_done``. The timing variants carry non-zero
specify delays that break those loops, so time advances and the run completes.

The sequential cells are behavioural stubs (see ``gen_gl_seq_stubs.py``)
--------------------------------------------------------------------------

Icarus Verilog does not drive the ``$setuphold`` negative-timing *delayed* nets
that the timing models route a flop's / latch's clock and data through, so those
cells are stuck X and no X-init can revive them (sky130 ``dfxtp`` / ``dlxtp``
hit this; gf180 ``dffq`` / ``latq`` wire their UDP directly but still misbehave).
``gen_gl_seq_stubs.py`` replaces just the sequential cells with behavioural
equivalents (and forces an explicit ``timescale`` -- gf180's models ship without
one) while leaving the combinational cells on their timing models. This X-init
seeds those stub flops; the deposits + the stubs together clear the fabric.

The slow process / fabric may also need a relaxed clock: gf180's hardened gates
do not meet timing at the RTL clock period, so the testbench widens the period
under ``GL_SIM``. This is orthogonal to X removal but required for a functional
match (a counter clocked faster than its critical path produces wrong values,
exactly as the silicon would).

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
deposit holds and the flop clear is final.

This was verified empirically: triggering the scrub before the upload loop
instead leaves every fabric output X and the golden comparison fails outright,
while triggering it at ``config_done`` passes.

Limitation: bitstream-set power-on flop values
----------------------------------------------

The flop clear drives a user flop to 0, but only when that flop still holds X
(action 2 is X-only). For the current FABulous DFF
(``LUT4c_frame_config_dffesr``) this is moot: the bitstream only configures the
*synchronous* reset target ``c_reset_value`` (applied by the design's own
``SR``), never the power-up runtime value, so every user flop is X at
``config_done`` and the clear simply defines it.

A future fabric that adds a true INIT bit -- letting the bitstream set a flop's
power-on runtime value -- is largely covered by the X-only guard: if that value
is materialised into the flop's ``Q`` by ``config_done``, ``Q`` is no longer X
and the clear skips it, preserving the configured value. The guard does *not*
cover an INIT bit staged in config memory but not yet reflected in ``Q`` --
there the flop is still X and the clear defaults it to 0. The fix in that case
is to clear each flop toward its configured INIT value instead of a hard 0
(moving the clear before config does not help -- the X returns during upload,
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

# Async reset pin of the flip-flop std cell the hardened netlist *may* bind
# against, per PDK. All are active-low, so the reset pulse drives the pin to 0.
# Whether a flop actually carries this pin is decided per instance: IHP maps to
# a resettable cell (``sg13g2_dfrbp``, ``RESET_B``); sky130 / gf180 map to plain
# DFFs with no reset pin, which are cleared by depositing ``Q`` instead. The
# entry is the pin to look for, not a promise that the netlist contains it.
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
        L.append("    //    2b) resetless flops: seed Q directly (needs -DFUNCTIONAL).")
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
