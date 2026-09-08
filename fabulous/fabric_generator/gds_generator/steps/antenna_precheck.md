# Fabric-aware antenna pre-check

Surfaces the antenna problems a tile will have **once the fabric is stitched**,
while the tile is still being built and a fix is still cheap.

## Why a tile cannot see its own antenna problem

FABulous declares every routing wire with an offset. `gen_tile.py` wires a
pass-through wire with an offset of N as a chain through `my_buf`, but `my_buf`
is `assign X = A` and carries no keep attribute, so Yosys collapses it. What
reaches the layout is one net that enters the tile on one edge and leaves on the
other with nothing in between.

Once tiles abut, those per-tile segments fuse. A wire declared with an offset of
N becomes a single conductor N tiles long, terminating on a mux input in the
destination tile. The metal that threatens that gate is N tiles' worth; the tile
flow only ever measured one.

The configuration buses are the widest instance of this: `FrameData` is
distributed along a whole row and `FrameStrobe` down a whole column, so their
spans are the fabric's column and row count rather than a port offset.

Measured on the real `S_term_single` tile from the gf180 demo, which
`OpenROAD.CheckAntennas` passes clean today:

| Wire | span | layer | predicted ratio |
| --- | --- | --- | --- |
| `FrameStrobe[1]` | 10 | Metal3 | **4.09x** its limit |
| `FrameStrobe[2]` | 10 | Metal3 | 3.91x |
| `FrameData[18]` | 4 | Metal3 | 1.55x |

29 wires in that one tile, all invisible to the tile flow.

## How the check works

The trick is not to measure anything. OpenROAD's antenna checker already knows
how to judge a net against the PDK's real rules, and
`AntennaChecker::getAntennaViolations` takes a `ratio_margin` percentage that
scales every required ratio by `1 - margin/100`. Holding a net to `limit / span`
is arithmetically identical to giving it `span` times the metal, so

```text
margin = 100 * (1 - 1/span)
```

asks "would this wire violate if it were N tiles long?". The `excess_ratio` that
comes back is then the predicted stitched ratio directly, as a multiple of the
limit. Verified against a known-good `check_antennas` report: for `FrameData[12]`
on Metal3 the report says 599.67 against a required 400, and the checker returns
1.49916 at margin 0, exactly 2x that at margin 50 and exactly 10x at margin 90.

Because the measurement is OpenROAD's, the PDK's real rules apply: side-area
versus plan-area ratios, PWL curves against diffusion area, cumulative ratios,
cut layers, and any diodes already placed.

### `antenna_precheck.py` — the span, the one thing OpenROAD cannot know

`wire_spans()` walks the tile's declared ports and takes each wire's span from
`xOffset`/`yOffset`, or the fabric dimensions for the configuration buses.
`parse_summary()` turns the resulting JSON into violations, and `diode_targets()`
reduces those to the sinks that need protecting.

OpenROAD has no idea what a `FrameStrobe` is or how many rows the fabric has, so
this half cannot move into the script. It needs no layout at all, and it is why
the check can run before the fabric exists.

### `../script/odb_antenna_precheck.py` — the verdict

An ODB script. For every net whose declared wire travels more than one tile, it
calls the antenna checker at that wire's margin and records what comes back:

```sh
openroad -python odb_antenna_precheck.py --spans spans.json --summary out.json tile.odb
```

Wires that stay inside their tile are skipped — at span 1 this predicts nothing
`OpenROAD.CheckAntennas` has not already reported. Post-global-route the block
carries guides rather than wires, and the script materialises them exactly as
`check_antennas` does.

## Running it in the flow

`FABulous.AntennaPrecheck` (in `antenna_precheck.py`) builds the span map
from the tile's ports, runs the script over the routed ODB, and reads the
summary back. `Checker.FABulousAntennaPrecheck` follows it. Both sit at the end
of `tile_check_steps`, so they are in the tile flow only — there is nothing for
them to predict about an already-stitched fabric.

They run by default (`RUN_FABULOUS_ANTENNA_PRECHECK`) and in the normal case need
no configuration at all: everything comes from objects the flow already has.

| What is needed | Where it comes from |
| --- | --- |
| The tile's port offsets | `FABULOUS_TILE`, the object the tile flow is already handed |
| Fabric row/column counts, for the config buses | `FABULOUS_FABRIC` |
| Antenna rules, layers, gate areas | OpenDB, from the PDK LEFs the flow already read |

Nothing is re-parsed when those objects are present: both tile flows pass the
`Tile` they already built. `FABULOUS_FABRIC_CONFIG` is parsed only as a last
resort, for a tile hardened outside a flow that carries either object.

A tile hardened with no parent fabric still gets real spans for its routing wires
from its own ports; only `FrameData` and `FrameStrobe` need fabric dimensions, and
the step warns when it cannot see them rather than quietly checking them at span 1.
`FABULOUS_ANTENNA_MAX_SPAN` applies one conservative span to everything when there
is no fabric model at all. `ERROR_ON_PREDICTED_ANTENNA` (default off) decides
whether a prediction fails the flow.

The step leaves `antenna_spans.json`, `antenna_precheck.json` (the raw verdicts),
`antenna_precheck.rpt` (a human table) and `diode_targets.json` in its step
directory.

## The payoff

`diode_targets.json` is written in the form `Odb.InsertECODiodes` accepts —
`[{"target": "instance/pin"}, ...]` — naming only the sinks actually at risk. That
is the point of predicting early: `DIODE_ON_PORTS: "both"` currently pays diode
area on every port of every tile, which works against `TileAreaOptimisation`.

## Why this is not a KLayout DRC deck

It was, at first: a Ruby deck extracting connectivity from the tile GDS, plus a
`stack.py` that derived the metal stack and antenna limits from the PDK's layer
map, tech LEF and `.lyp`. All of that has been deleted, because under LibreLane
it was reimplementing — less correctly — what OpenDB already had:

- The tech-LEF regex missed gf180's `ANTENNASIDEAREARATIO`, so Metal1 silently
  dropped out of the stack with no warning.
- Metal2 and Metal3 matched `ANTENNADIFFSIDEAREARATIO`, a **side**-area limit,
  and the deck compared it against a **plan**-area measurement. On the real tile
  above that is a 3.9x gap: 155.15 plan-area versus 599.67 side-area on the same
  net, so the deck would have called a violating net clean.
- Cut layers carry their own ratios (20.0 in gf180) that the deck never checked.
- Gate areas were reconstructed as `poly & diff` from geometry, and diffusion and
  poly layers guessed by name from the `.lyp`, when `dbMTerm` states the gate
  area outright.

The deep-mode speed argument did not defend it either: at tile time there is no
instance repetition to exploit.

## Gotchas worth knowing

- **`check_antennas` only reports violating nets.** A clean run is two lines, so
  the report cannot be scraped for the sub-threshold ratios this needs — hence
  calling the checker directly with a scaled margin.
- **A diode on a net is not a diode target.** Diodes declare diffusion area, not
  gate area, so `dbMTerm.hasDefaultAntennaModel()` distinguishes the gate being
  protected from the protection already on the net.
- **Scaling applies to every layer of the net, not just the one it crosses on.**
  This is correct for a fused net — every tile contributes its own copy — but it
  slightly over-reports the terminating tile's local drop-down to the gate. On
  the real tile the effect is invisible: all 29 predictions land on Metal3 and
  Metal2, the layers the wires actually run on, and none on Metal1.
- **`ant.Violation.gates` is not iterable** through the Python bindings, so the
  sinks are enumerated from the net's own input terminals instead.
- **Ratios are `Decimal` from the moment they are parsed**, via
  `json.loads(..., parse_float=Decimal)`, so the metric is the number the checker
  wrote rather than a binary approximation of it. The one float left is
  `margin_for_span`'s return value, which goes straight into a binding that takes
  a C++ double; converting earlier than the JSON would add no precision, since
  `excess_ratio` arrives as a double too.
- **A checker's `error_on_var` must also appear in its `config_vars`.** LibreLane
  only ever reads it back out of the config, so a variable declared in one place
  and not the other is silently unknown: setting it is rejected and the checker
  can never be switched on.

## Not yet done

- Feeding `diode_targets.json` into `Odb.InsertECODiodes` so the predicted sinks
  actually get their diodes and `DIODE_ON_PORTS` can come off. The step writes
  the list; nothing consumes it yet. Doing so wants the check to move earlier
  than `tile_check_steps` — next to `OpenROAD.CheckAntennas`, before diode
  insertion, rather than after stream-out.
- Per-tile-type spans where a wire crosses more than one tile type: the current
  predictor multiplies by the span rather than summing the individual tiles it
  crosses.
