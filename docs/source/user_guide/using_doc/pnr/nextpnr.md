# Nextpnr models

After the FABulous flow has run successfully, the model files that describe your fabric
to nextpnr can be found in the project directory under `.FABulous`.
nextpnr reads them at start-up through the `fabulous` viaduct micro-architecture
(`generic/viaduct/fabulous/fabulous.cc` in the nextpnr tree).
The environment variable `FAB_ROOT` must point at the project directory so
nextpnr can find all model files.

## Generated model files

| File               | Purpose                                                                              |
| ------------------ | ------------------------------------------------------------------------------------ |
| `bel.txt`          | Legacy (1.0) BEL list, one line per BEL. Used for projects without a `.FABulous` dir |
| `bel.v2.txt`       | Block-structured BEL description used by current (2.0) projects                       |
| `bel.v3.txt`       | `bel.v2.txt` plus per-BEL timing arcs (see [](#belv3txt-bel-timing))                  |
| `pips.txt`         | Routing resources (programmable interconnect points) and their delays                |
| `placement_estimate.txt`  | The fabric's base delay scaling factors (see [](#placement-estimate))                     |
| `template.pcf`     | A pin-constraint template listing the fabric's IO BELs                                |

nextpnr selects the BEL file as follows:

- if `.FABulous/bel.v3.txt` exists, it is used and the design is timing-aware for
  BELs as well as pips;
- otherwise `.FABulous/bel.v2.txt` is used (BEL timing falls back to built-in
  defaults baked into the viaduct);
- legacy projects with no `.FABulous` directory use `npnroutput/bel.txt`.

All of these files are produced together by the `gen_model_npnr` CLI command.

## `bel.txt` (legacy)

`bel.txt` is the primitive description file, in order of tiles. Each line is one
BEL: tile, X, Y, Z (a letter), primitive type, then its ports.

```{code-block} text
:emphasize-lines: 7

    #Tile_X0Y1
    X0Y1,X0,Y1,A,IO_1_bidirectional_frame_config_pass,A_I,A_T,A_O,A_Q
    X0Y1,X0,Y1,B,IO_1_bidirectional_frame_config_pass,B_I,B_T,B_O,B_Q
    X0Y1,X0,Y1,C,Config_access,
    X0Y1,X0,Y1,D,Config_access,
    #Tile_X1Y1
    X1Y1,X1,Y1,A,FABULOUS_LC,LA_I0,LA_I1,LA_I2,LA_I3,LA_Ci,LA_SR,LA_EN,LA_O,LA_Co
    X1Y1,X1,Y1,B,FABULOUS_LC,LB_I0,LB_I1,LB_I2,LB_I3,LB_Ci,LB_SR,LB_EN,LB_O,LB_Co
    X1Y1,X1,Y1,C,FABULOUS_LC,LC_I0,LC_I1,LC_I2,LC_I3,LC_Ci,LC_SR,LC_EN,LC_O,LC_Co
    X1Y1,X1,Y1,D,FABULOUS_LC,LD_I0,LD_I1,LD_I2,LD_I3,LD_Ci,LD_SR,LD_EN,LD_O,LD_Co
    X1Y1,X1,Y1,E,FABULOUS_LC,LE_I0,LE_I1,LE_I2,LE_I3,LE_Ci,LE_SR,LE_EN,LE_O,LE_Co
    X1Y1,X1,Y1,F,FABULOUS_LC,LF_I0,LF_I1,LF_I2,LF_I3,LF_Ci,LF_SR,LF_EN,LF_O,LF_Co
    X1Y1,X1,Y1,G,FABULOUS_LC,LG_I0,LG_I1,LG_I2,LG_I3,LG_Ci,LG_SR,LG_EN,LG_O,LG_Co
    X1Y1,X1,Y1,H,FABULOUS_LC,LH_I0,LH_I1,LH_I2,LH_I3,LH_Ci,LH_SR,LH_EN,LH_O,LH_Co
    X1Y1,X1,Y1,I,MUX8LUT_frame_config,A,B,C,D,E,F,G,H,S0,S1,S2,S3,M_AB,M_AD,M_AH,M_EF
```

| Tile | X-axis | Y-axis | Z-axis | Primitive name | Ports                                                |
| ---- | ------ | ------ | ------ | -------------- | ---------------------------------------------------- |
| X1Y1 | X1     | Y1     | A      | FABULOUS_LC    | LA_I0,LA_I1,LA_I2,LA_I3,LA_Ci,LA_SR,LA_EN,LA_O,LA_Co |

## `bel.v2.txt`

The 2.0 format describes each BEL as a block delimited by `BelBegin`/`BelEnd`
rather than a single line. This makes the port-to-wire mapping explicit and lets
the description carry extra information that a flat line cannot. Each line in a
block is a command:

| Command                                  | Meaning                                                        |
| ---------------------------------------- | -------------------------------------------------------------- |
| `BelBegin,<tile>,<z>,<type>,<prefix>`    | Start a BEL at tile `<tile>`, Z position `<z>` (a letter)      |
| `I,<port>,<tile>.<wire>`                 | Input pin `<port>` driven by wire `<tile>.<wire>`              |
| `O,<port>,<tile>.<wire>`                 | Output pin `<port>` driving wire `<tile>.<wire>`               |
| `CFG,<feature>`                          | A configuration bit / feature of the BEL                       |
| `GlobalClk`                              | Connect the BEL to the fabric's global clock network           |
| `BelEnd`                                 | End the current BEL                                            |

A `FABULOUS_LC` block looks like:

```{code-block} text
    BelBegin,X1Y1,A,FABULOUS_LC,LA_
    I,I0,X1Y1.LA_I0
    I,I1,X1Y1.LA_I1
    I,I2,X1Y1.LA_I2
    I,I3,X1Y1.LA_I3
    I,Ci,X1Y1.LA_Ci
    I,SR,X1Y1.LA_SR
    I,EN,X1Y1.LA_EN
    O,O,X1Y1.LA_O
    O,Co,X1Y1.LA_Co
    CFG,FF
    CFG,INIT
    CFG,INIT[1]
    CFG,INIT[2]
    ...
    CFG,INIT[15]
    CFG,I0mux
    CFG,SET_NORESET
    CFG,INIT
    CFG,IOmux
    GlobalClk
    BelEnd
```

In nextpnr, the BELs in a tile are usually identified by their Z-axis (A/B/C/D),
like following `X1Y1.A` for the `FABULOUS_LC` in the example above.
Except the BRAM IO BELs `InPass4_frame_config` / `OutPass4_frame_config` and their
`_mux` variants - they are typically named by they `prefix` name, so they have readable name.

(belv3txt-bel-timing)=

## `bel.v3.txt` (BEL timing)

`bel.v3.txt` is identical to `bel.v2.txt` with additional **timing-arc** lines
inside each BEL block. Each arc maps directly to one of nextpnr's
`addCellTiming*` calls, so the file lets the fabric describe its own BEL timing
instead of relying on constants compiled into nextpnr.

| Line                                                | nextpnr call               | Meaning                              |
| --------------------------------------------------- | -------------------------- | ------------------------------------ |
| `Delay,<from>,<to>,<ns>[,<cond>]`                   | `addCellTimingDelay`       | Combinational delay `<from>` -> `<to>`|
| `SetupHold,<port>,<clk>,<setup>,<hold>[,<cond>]`    | `addCellTimingSetupHold`   | Register input setup/hold to `<clk>` |
| `ClkToOut,<port>,<clk>,<ns>[,<cond>]`               | `addCellTimingClockToOut`  | Register output clock-to-out         |
| `Clock,<clk>[,<cond>]`                              | `addCellTimingClock`       | Declare `<clk>` as a clock pin       |

All delays are in nanoseconds.

### Conditions

The optional trailing `<cond>` field gates an arc on how the design actually
uses the BEL. It is an `&`-joined list of predicates that nextpnr evaluates per
cell during placement; if the field is absent the arc always applies. The
predicates are:

- `PARAM=1` / `PARAM=0` - the cell's configuration bit / parameter `PARAM` is
  set / unset (e.g. `FF=1` for a registered LUT).
- `PORT[/PORT...]?` - at least one of the listed ports is connected; the
  `/`-list is an OR (e.g. `Ci/Co?` matches a LUT used in a carry chain).
- `PORT[/PORT...]!` - none of the listed ports are connected.

Because the conditions are evaluated against each placed cell, the same physical
BEL contributes different arcs depending on its mode. For example a LUT used
combinationally gets an input-to-output `Delay`, while the same LUT used as a
flip-flop instead gets `SetupHold` on its inputs and `ClkToOut` on `Q`.

A `FABULOUS_LC` block with timing:

```{code-block} text
:emphasize-lines: 12-26

    BelBegin,X1Y1,A,FABULOUS_LC,LA_
    I,I0,X1Y1.LA_I0
    I,I1,X1Y1.LA_I1
    I,I2,X1Y1.LA_I2
    I,I3,X1Y1.LA_I3
    I,Ci,X1Y1.LA_Ci
    I,SR,X1Y1.LA_SR
    I,EN,X1Y1.LA_EN
    O,O,X1Y1.LA_O
    O,Co,X1Y1.LA_Co
    CFG,FF
    CFG,INIT
    CFG,INIT[1]
    CFG,INIT[2]
    ...
    CFG,INIT[15]
    CFG,I0mux
    CFG,SET_NORESET
    CFG,INIT
    CFG,IOmux
    Clock,CLK,FF=1
    Delay,I0,O,3.0,FF=0
    Delay,I1,O,3.0,FF=0
    Delay,I2,O,3.0,FF=0
    Delay,I3,O,3.0,FF=0
    Delay,Ci,O,3.0,FF=0&I0MUX=1
    Delay,Ci,Co,0.2,Ci/Co?
    Delay,I1,Co,1.0,Ci/Co?
    Delay,I2,Co,1.0,Ci/Co?
    SetupHold,I0,CLK,2.5,0.1,FF=1
    SetupHold,I1,CLK,2.5,0.1,FF=1
    SetupHold,I2,CLK,2.5,0.1,FF=1
    SetupHold,I3,CLK,2.5,0.1,FF=1
    SetupHold,Ci,CLK,2.5,0.1,FF=1&I0MUX=1
    ClkToOut,Q,CLK,1.0,FF=1
    GlobalClk
    BelEnd
```

`Q` looks like a pseudo-port (nextpnr synthesises a `Q` pseudo-pin for
routing after loading the BEL file), but for *timing* it's a real
cell port: FABulous's packer renames the cell's `O` output to `Q`
whenever the FF is used. This is a special case for the
FABULOUS_LC, for every other BEL, there should be no pseudo pins.

:::{warning}
The BEL timing values FABulous writes
are **fixed placeholder constants**, equal to
the values nextpnr historically hard-coded; they are **not** yet derived from
a characterised timing model.
Only pip delays (`pips.txt`) are produced by the timing model today, see
[Timing Characterization](../../building_doc/timing_characterization.md).
:::

## `pips.txt`

`pips.txt` is the routing-resource description: one programmable interconnect
point per line, with its delay.

```{code-block} text
:emphasize-lines: 1

    X1Y1,N1BEG0,X1Y0,N1END0,8,N1BEG0.N1END0
    X1Y1,N1BEG1,X1Y0,N1END1,8,N1BEG1.N1END1
    X1Y1,N1BEG2,X1Y0,N1END2,8,N1BEG2.N1END2
    X1Y1,N1BEG3,X1Y0,N1END3,8,N1BEG3.N1END3
    X1Y1,N2BEG0,X1Y0,N2MID0,8,N2BEG0.N2MID0
    X1Y1,N2BEG1,X1Y0,N2MID1,8,N2BEG1.N2MID1
    X1Y1,N2BEG2,X1Y0,N2MID2,8,N2BEG2.N2MID2
    X1Y1,N2BEG3,X1Y0,N2MID3,8,N2BEG3.N2MID3
    X1Y1,N2BEG4,X1Y0,N2MID4,8,N2BEG4.N2MID4
    X1Y1,N2BEG5,X1Y0,N2MID5,8,N2BEG5.N2MID5
    X1Y1,N2BEG6,X1Y0,N2MID6,8,N2BEG6.N2MID6
    X1Y1,N2BEG7,X1Y0,N2MID7,8,N2BEG7.N2MID7
```

| Source tile | Source port | Destination tile | Destination port | Delay | Wire name     |
| ----------- | ----------- | ---------------- | ---------------- | ----- | ------------- |
| X1Y1        | N1BEG0      | X1Y0             | N1END0           | 8     | N1BEG0.N1END0 |

The delay column is an arbitrary placeholder (`8`) unless a timing model is run,
in which case it is replaced by a characterised per-pip delay; see
[Timing Characterization](../../building_doc/timing_characterization.md) for how
those delays are generated.

(placement-estimate)=

## `placement_estimate.txt`

`placement_estimate.txt` is a `key=value` file of nextpnr placement/routing
tunables. FABulous writes nextpnr's historical defaults, so each value is also
what nextpnr falls back to when the key or the whole file is absent:

```{code-block} text
delayScale=3.0
delayOffset=3.0
delayEpsilon=0.25
ripupPenalty=0.5
carryPredictDelay=0.5
```

| Key                 | nextpnr target             | Default | Meaning                                                    |
| ------------------- | -------------------------- | ------- | ---------------------------------------------------------- |
| `delayScale`        | `setDelayScaling` scale    | 3.0     | `predictDelay` cost per tile of distance                   |
| `delayOffset`       | `setDelayScaling` offset   | 3.0     | Fixed `predictDelay` baseline (pip/pin setup overhead)     |
| `carryPredictDelay` | `predictDelay` `Co`->`Ci`   | 0.5     | Carry-chain placement estimate (dedicated interconnect)    |
| `delayEpsilon`      | `ctx->delay_epsilon`       | 0.25    | Smallest delay difference the timing analysis resolves     |
| `ripupPenalty`      | `ctx->ripup_penalty`       | 0.5     | Router cost for ripping up an existing route               |

nextpnr's placer decides where every BEL goes *before* anything is routed, so
it can't yet know a connection's real pip delay (`pips.txt`), only the two
BEL locations. nextpnrs `predictDelay` function fills that gap with a cheap
Manhattan-distance estimate used to compare candidate placements:

```{code-block} text
estimated_delay = (|dx| + |dy|) * delayScale + delayOffset
```

`delayScale` is the marginal cost per tile of distance; `delayOffset` is a
fixed baseline added regardless of distance (e.g. pip/pin setup overhead).
This estimate only ever steers *which placement is picked*;
the real numbers in the final timing report always come from the
actual routed pips and `bel.v3.txt`'s arcs, never from `predictDelay`.

`carryPredictDelay` is the analogous estimate for the `FABULOUS_LC` carry
chain (`Co`->`Ci`).
It is a flat `0.5` (nextpnr's original hardcoded value),
independent of `delayScale`. `delayEpsilon` and `ripupPenalty`
are plain nextpnr placer/router knobs FABulous simply echoes at their defaults.

:::{note}
None of these keys scale `bel.v3.txt`'s BEL-internal arcs (LUT/FF/carry
timing), they only steer placement and routing.
Any key (or the whole file, for legacy or
unregenerated projects) that is missing falls back to the default in the table,
matching nextpnr's original hard-coded values. By default, FABulous writes
`delayOffset` equal to `delayScale`.
:::

### Per-type placement estimates

After the scaling keys, FABulous appends one representative block per timed
BEL type, delimited by `BelBegin,<type>`/`BelEnd` and containing the same
timing-arc lines as `bel.v3.txt` (minus the pin lines): `FABULOUS_LC`, the
registered output pads (`OutPass4_frame_config`, `OutPass4_frame_config_mux`,
`SetupHold` arcs on `I0`-`I3`), and the registered input pads
(`InPass4_frame_config`, `InPass4_frame_config_mux`, `ClkToOut` arcs on
`O0`-`O3`):

```{code-block} text
delayScale=3.0
delayOffset=3.0
...
BelBegin,FABULOUS_LC
Clock,CLK,FF=1
Delay,I0,O,3.0,FF=0
...
SetupHold,I0,CLK,2.5,0.1,FF=1
ClkToOut,Q,CLK,1.0,FF=1
BelEnd
BelBegin,OutPass4_frame_config
SetupHold,I0,CLK,2.5,0.1
...
BelEnd
BelBegin,InPass4_frame_config
ClkToOut,O0,CLK,2.5
...
BelEnd
```

nextpnr applies BEL timing in two passes: these representative blocks steer
placement (every instance of a type is estimated with its type's block), then
after placement each BEL's own `bel.v3.txt` arcs replace them, so the routed
report is per-instance.

:::{note}
`bel.v3.txt` and `placement_estimate.txt` are written
together; if only one is present nextpnr warns (regenerate with
`gen_model_npnr`).

Like `delayScale`/`delayOffset`, this block only steers
placement, the final report always uses `bel.v3.txt`'s arcs.
:::
