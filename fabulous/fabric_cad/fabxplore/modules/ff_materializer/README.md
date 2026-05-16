# FF Materializer

The FF materializer replaces standalone one-bit flip-flop cells with configured
instances of an architecture tile. It is the companion pass to register
absorption:

- register absorption uses an already placed/mapped tile and absorbs a nearby FF
  into one of its sequential outputs;
- FF materialization handles the FFs that are still left over by creating new
  tile instances configured as register lanes.

The goal is simple: after the mapping flow, the final netlist should contain
architecture primitives, not generic FF cells such as `$dff`, `$dffe`, or
`LUTFF`.

## Mental Model

A normal FF cell represents $q(t + 1) = d(t)$ with optional clock,
enable, reset, and reset value semantics. A tile register lane represents the
same state update, but the FF is hidden inside the tile:

$$
\begin{aligned}
Q_i(t + 1) &= f_i(x(t), c)
\end{aligned}
$$

where:

- $Q_i$ is a sequential output port of the tile, for example `Q0`;
- $x$ are tile input ports, for example `I0`, `I1`, `A0`, `S`;
- $c$ are tile configuration bits;
- $f_i$ is the combinational path that feeds the register.

To replace a standalone FF with a tile lane, the user provides a lane
configuration such that $f_i(x(t), c) = d(t)$ for the chosen data input. The
pass then connects the old FF data net to the lane input and connects the tile
sequential output to the old FF output net.

For example, if a tile has:

```verilog
always @(posedge UserCLK) begin
  if (EN) begin
    if (SR) begin
      Q0 <= 1'b0;
    end else begin
      Q0 <= O0;
    end
  end
end
```

and the lane config programs `O0 = I0`, then this tile lane implements
$Q0(t + 1) = I0(t)$.

So a standalone FF:

```text
D ----> [ FF ] ----> Q
```

can become:

```text
D ----> I0   FLUT5_1P_2PS   Q0 ----> Q
          configured so O0 = I0
```

The final netlist no longer contains the original FF cell.

## Why This Pass Exists

In FPGA-style architectures, flip-flops are often physically inside logic tiles.
Earlier synthesis passes may still leave FFs as separate netlist cells because
that is a convenient generic representation:

```text
logic/LUT/tile output ----> FF ----> registered net
```

Register absorption can remove many of these when the FF is directly next to a
mapped tile. But some FFs remain standalone:

```text
some net ----> FF ----> some other net
```

The materializer replaces those remaining FFs with new tile instances configured
only as register resources.

## Simple Examples

### One FF, One Lane

Before:

```text
net_d ----> LUTFF ----> net_q
```

After:

```text
FLUT5_1P_2PS __ff_materialized_pack_0 (
  .I0(net_d),
  .Q0(net_q),
  .EN(1'b1),
  .SR(1'b0),
  .UserCLK(clk),
  .ConfigBits(...)
);
```

The lane definition says:

```python
{
    "data_port": "I0",
    "output_port": "Q0",
    "clock_port": "UserCLK",
    "enable_tile_port": "EN",
    "enable_neutral": 1,
    "reset_tile_port": "SR",
    "reset_neutral": 0,
    "config": {
        "ConfigBits[1]": 1,
        "ConfigBits[3]": 1,
        "ConfigBits[5]": 1,
        "ConfigBits[7]": 1,
        "ConfigBits[9]": 1,
        "ConfigBits[11]": 1,
        "ConfigBits[13]": 1,
        "ConfigBits[15]": 1,
        "ConfigBits[32]": 1,
    },
}
```

For the example FLUT tile, these config bits program the internal combinational
path used by `Q0`.

### Two FFs Packed Into One Tile

If `pack_multiple_ffs_per_tile=True`, the materializer tries to fill multiple
lanes in the same replacement tile. For a two-lane tile:

```text
FF_A.D ----> lane 0 ----> FF_A.Q
FF_B.D ----> lane 1 ----> FF_B.Q
```

becomes:

```text
FLUT5_1P_2PS __ff_materialized_pack_0 (
  .I0(FF_A_D),
  .I1(FF_B_D),
  .Q0(FF_A_Q),
  .Q1(FF_B_Q),
  .EN(1'b1),
  .SR(1'b0),
  .UserCLK(clk),
  .ConfigBits(...)
);
```

Packing is only legal when shared tile ports are compatible. For example, if
both lanes use `UserCLK`, both FFs must have the same clock net. If both lanes
use `EN`, both FFs must either share the same enable net or use the same neutral
constant.

### FF Chains

A chain:

```text
FF0.Q ----> FF1.D ----> FF1.Q
```

may become either:

```text
tile0.Q0 ----> tile1.I0
```

or, if both FFs fit into one tile:

```text
tile.I0 ----> tile.Q0
tile.I1 ----> tile.Q1
```

The pass does not invent extra timing behavior. It preserves the FF data and
output nets according to the selected lane bindings.

## How Sequential Logic Is Handled

The pass does not map arbitrary sequential logic with SAT. It replaces each
supported one-bit FF cell with one sequential lane of the replacement tile. The
state element is still present in the final netlist, but it lives inside the
architecture primitive instead of in a generic FF cell.

For a plain FF:

```text
before:

  d_net ----> D  $dff  Q ----> q_net
              ^        |
              |        |
             clk      output state

after:

  d_net ----> I0  TILE  Q0 ----> q_net
              ^         |
              |         |
             clk ----> UserCLK
```

The intended behavior is the same:

$$
\begin{aligned}
q_\text{old}(t + 1) &= d_\text{old}(t) \\
Q0_\text{tile}(t + 1) &= I0_\text{tile}(t)
\end{aligned}
$$

The writer therefore performs two structural edits:

- connect the old FF data signal to the lane `data_port`;
- connect the lane `output_port` to the old FF output signal and remove the old
  FF cell.

Clock, enable, and reset are handled as ports of the replacement tile. If a lane
names `clock_port`, the old FF clock net is connected to that tile port. If a
lane names `enable_tile_port` or `reset_tile_port`, then matching FF control
nets are connected when present. If the FF has no such control, the pass may use
the lane neutral value:

```text
$dff without enable/reset:

  .EN(1'b1)   because enable_neutral = 1
  .SR(1'b0)   because reset_neutral = 0
```

For an enabled FF:

```text
before:

  d_net ----> D  $dffe  Q ----> q_net
  en_net ----> EN
  clk -------> CLK

after:

  d_net ----> I0  TILE  Q0 ----> q_net
  en_net --------> EN
  clk -----------> UserCLK
```

For a resettable FF, `reset_kind` and `reset_value` describe what kind of reset
the lane can preserve. For example, a lane with `reset_kind="sync"` and
`reset_value=0` may absorb an FF whose reset is synchronous and resets the
output to zero. A reset mismatch is skipped, or raises when the relevant failure
option is enabled.

### Register Position Inside The Tile

The materializer does not require the register to be physically located only at
the tile output. A lane is described by the external data port and the external
output port that together implement one FF-equivalent timing step. Therefore the
tile may place the register on the output side, the input side, or mix both
styles across different lanes.

Output-side register lane:

```text
old FF:

  d_net ----> [ FF ] ----> q_net

tile lane:

  d_net ----> I0 ----> comb path ----> [ tile FF ] ----> Q0 ----> q_net
```

The lane definition uses the tile input and registered output:

```python
{
    "data_port": "I0",
    "output_port": "Q0",
    "clock_port": "CLK",
}
```

Input-side register lane:

```text
old FF:

  d_net ----> [ FF ] ----> q_net

tile lane:

  d_net ----> I0 ----> [ tile FF ] ----> comb/bypass path ----> O0 ----> q_net
```

The lane definition still names the external data and output ports:

```python
{
    "data_port": "I0",
    "output_port": "O0",
    "clock_port": "CLK",
}
```

Mixed tiles are also supported. For example, one tile may materialize five FFs
where lanes 0 and 2 expose input-side registers through `O0` and `O2`, while
lanes 1, 3, and 4 expose output-side registers through `Q1`, `Q3`, and `Q4`:

```text
lane 0: d0 -> I0 -> [FF] -> O0 -> q0
lane 1: d1 -> I1 -> comb -> [FF] -> Q1 -> q1
lane 2: d2 -> I2 -> [FF] -> O2 -> q2
lane 3: d3 -> I3 -> comb -> [FF] -> Q3 -> q3
lane 4: d4 -> I4 -> comb -> [FF] -> Q4 -> q4
```

The corresponding lanes are just the external port pairs:

```python
lanes=[
    {"data_port": "I0", "output_port": "O0", "clock_port": "CLK"},
    {"data_port": "I1", "output_port": "Q1", "clock_port": "CLK"},
    {"data_port": "I2", "output_port": "O2", "clock_port": "CLK"},
    {"data_port": "I3", "output_port": "Q3", "clock_port": "CLK"},
    {"data_port": "I4", "output_port": "Q4", "clock_port": "CLK"},
]
```

The important rule is that each lane must represent exactly one FF worth of
latency between `data_port` and `output_port`. If a tile path contains two
registers, or no register, then it is not equivalent to replacing one standalone
FF unless the surrounding flow intentionally accounts for that timing.

### Auto-Config And Sequential Tiles

`auto_config=True` only uses sequential passthrough during the config search. It
does not remove the tile registers from the final netlist.

Internally, the tile Verilog is lowered to BLIF. For the SAT problem, sat_fab
imports that BLIF with `sequential_mode="passthrough"`, so a register boundary
inside the tile is treated like an identity edge while solving the combinational
question:

```text
SAT-only view:

  I0 ----> combinational config fabric ----> Q0

real emitted tile:

  I0 ----> combinational config fabric ----> D(register)  Q0
```

This lets SAT find the config bits for the data path, for example `I0 -> Q0`,
without trying to prove sequential behavior. The sequential behavior is
preserved by the tile instance itself.

If the tile has controls that can block the identity path, auto-config
temporarily fixes them to their lane neutral values while compiling the BLIF for
SAT:

```text
auto-config solve view:

  EN = 1
  SR = 0
  solve ConfigBits so Q0 = I0
```

The real output netlist still wires the actual FF controls when the FF has them.
The neutral values are only for finding the identity data-path configuration.

When multiple lanes are packed into one tile, auto-config solves the full packed
set together:

$$
\begin{aligned}
Q0 &= I0 \\
Q1 &= I1
\end{aligned}
$$

with one shared config assignment. This is important when both lanes share mode
bits. The pack is accepted only if one config assignment implements all occupied
lane identities at the same time.

### What This Pass Does Not Do

This pass does not:

- absorb FFs into already mapped neighboring tiles; use the register absorber
  for that;
- reason about arbitrary sequential equivalence;
- create a globally optimal placement of all FFs;
- remove all sequential behavior from the design.

It only turns supported standalone FF cells into architecture tile instances
whose lanes have matching clock/control semantics.

## Mathematical Packing Problem

Let $F$ be the set of supported FF cells and $L$ be the set of tile lanes.
For each FF $f \in F$, the materializer tries to choose a lane $l \in L$.

A binding is structurally valid when the FF clock, data, and output connect to
the selected lane ports:

$$
\begin{aligned}
\text{clock}(f) &\rightarrow \text{clock\_port}(l) \\
\text{data}(f) &\rightarrow \text{data\_port}(l) \\
\text{output\_port}(l) &\rightarrow \text{output}(f)
\end{aligned}
$$

and the optional controls are compatible:

$$
\begin{aligned}
\text{enable}(f) &\rightarrow \text{enable\_tile\_port}(l) \\
\text{reset}(f) &\rightarrow \text{reset\_tile\_port}(l)
\end{aligned}
$$

If an FF does not have an enable or reset but the tile lane needs one, the pass
can connect a neutral constant such as `EN=1` or `SR=0`.

When multiple FFs are packed into one tile instance, config and parameter updates
must agree: $\forall k,\ c_a[k] = c_b[k]$ for every config bit or parameter key
used by more than one occupied lane. Shared tile input ports must also have the
same source: $\text{source}_a(p) = \text{source}_b(p)$ for every shared port
$p$.

This is a greedy packing pass. It is deterministic and conservative. It does not
currently solve a global optimum assignment.

## Manual And Auto Config

By default the materializer does not derive lane configuration. The user
supplies `config` and `params`, and the pass checks structural legality, control
compatibility, config conflicts, and port compatibility. This is useful for
architectures with direct register bypass paths where no SAT solve is needed.

When the pass-level option `auto_config=True` is set, the pass uses sat_fab to
derive config bits that make every occupied lane output behave as an identity of
its lane input:

$$
\forall i \in \text{packed lanes}: Q_i = I_i
$$

The tile BLIF is imported with `sequential_mode="passthrough"`, so register
boundaries inside the tile are treated as data-path boundaries for this solve.
The solve is joint for all FFs packed into one tile instance. This matters when
two lanes share mode bits: the pass accepts a packed replacement only if one
global config assignment implements every requested identity at the same time.

`auto_config_overwrites` can fix selected config bits before SAT and therefore
acts as a global constraint. SAT fills the remaining config bits. The emitted
tile instance receives the merged result:

```text
final config = auto_config_overwrites + SAT-found config
```

Lane-local `config` entries are not allowed when `auto_config=True`; use
`auto_config_overwrites` for fixed constraints. If `auto_config=False` and
`config` is absent, the pass simply replaces the FF and emits no config updates
for that lane.

## Internal Structure

The module follows the same shape as the other mapping modules:

```text
modules/ff_materializer/
  core/
    models.py           typed internal models and pydantic lane validation
    reader.py           reads pyosys design and tile model
    tile_compiler.py    emits normalized BLIF from the tile Verilog
    materializer.py     plans FF-to-lane replacements
    writer.py           mutates the live pyosys design
    report.py           renders a Jinja2 report
    process_tracker.py  progress logging
```

The reader builds internal Python objects from the Yosys object view. The tile
compiler uses Yosys to lower the replacement tile Verilog into normalized BLIF;
the same compiler path is used by the reader and by auto-config solves. The
materializer creates a replacement plan. The writer applies that plan directly
to the live pyosys design by inserting tile cells and removing the original FF
cells.

The tile model stores:

```python
FfMaterializerTileModel(
    top_name=...,
    verilog_path=...,
    blif_text=...,
    inputs=(...),
    outputs=(...),
    config_bits=(...),
    config_prefixes=(...),
)
```

The BLIF text is stored so `auto_config` can run SAT-derived passthrough
configuration on the same tile model.

## Pass Interface

The synthesizer-facing API is:

```python
self.design_materialize_registers_pass(
    tile_verilog_path=Path("demo0/Tile/test_tile/FLUT5_1P_2PS.v"),
    tile_top_name="FLUT5_1P_2PS",
    tile_inputs=[
        "I0",
        "I1",
        "I2",
        "A0",
        "B0",
        "S",
        "Ci",
        "EN",
        "SR",
        "UserCLK",
    ],
    tile_outputs=[
        "Q0",
        "Q1",
    ],
    tile_config_prefixes=[
        "ConfigBits",
    ],
    lanes=[
        {
            "data_port": "I0",
            "output_port": "Q0",
            "clock_port": "UserCLK",
            "include_enable_ff": True,
            "enable_tile_port": "EN",
            "enable_neutral": 1,
            "include_reset_ff": True,
            "reset_tile_port": "SR",
            "reset_neutral": 0,
            "reset_kind": "sync",
            "reset_value": 0,
            "depth_options": [
                {
                    "depth": 1,
                    "mode_config": {
                        "ConfigBits[32]": 1,
                    },
                },
            ],
            "config": {
                "ConfigBits[1]": 1,
                "ConfigBits[3]": 1,
                "ConfigBits[5]": 1,
                "ConfigBits[7]": 1,
                "ConfigBits[9]": 1,
                "ConfigBits[11]": 1,
                "ConfigBits[13]": 1,
                "ConfigBits[15]": 1,
            },
        },
        {
            "data_port": "I1",
            "output_port": "Q1",
            "clock_port": "UserCLK",
            "include_enable_ff": True,
            "enable_tile_port": "EN",
            "enable_neutral": 1,
            "include_reset_ff": True,
            "reset_tile_port": "SR",
            "reset_neutral": 0,
            "reset_kind": "sync",
            "reset_value": 0,
            "depth_options": [
                {
                    "depth": 1,
                    "mode_config": {
                        "ConfigBits[32]": 1,
                    },
                },
            ],
            "config": {
                "ConfigBits[18]": 1,
                "ConfigBits[19]": 1,
                "ConfigBits[22]": 1,
                "ConfigBits[23]": 1,
                "ConfigBits[26]": 1,
                "ConfigBits[27]": 1,
                "ConfigBits[30]": 1,
                "ConfigBits[31]": 1,
            },
        },
    ],
    ff_ports=None,
    pack_multiple_ffs_per_tile=True,
    auto_config=False,
    auto_config_overwrites=None,
    max_replacements=None,
    fail_on_invalid_lane=True,
    fail_on_auto_config_unsat=False,
    fail_on_pack_conflict=False,
    fail_on_unmaterialized_ff=False,
    track_progress=True,
    progress_chunk_size=100,
    top_name=None,
)
```

## Top-Level Options

`tile_verilog_path`
: Verilog file containing the replacement tile module.

`tile_top_name`
: Module name to instantiate for each replacement tile.

`tile_inputs`
: Scalar tile input ports the pass may connect. Include data, clock, enable,
reset, and other input ports referenced by lanes.

`tile_outputs`
: Scalar tile output ports the pass may connect. For this pass these are usually
sequential output ports such as `Q0` and `Q1`.

`tile_configs`
: Optional explicit scalar config bit names. Use this when config bits are
already scalarized or when you want to list exact names.

`tile_config_prefixes`
: Prefixes used to discover config bits from the emitted tile BLIF. For example,
`["ConfigBits"]` discovers scalarized names such as `ConfigBits[0]`.

`lanes`
: Register lane definitions. Each dictionary is validated as a pydantic
`FfMaterializerLane`.

`ff_ports`
: Optional mapping that describes supported FF cell port names. If `None`, the
default FF definitions are used. Defaults include common Yosys word-level and
gate-level FF cells such as `LUTFF`, `$dff`, `$dffe`, `$sdff`, `$adff`,
`$sdffe`, `$sdffce`, `$_DFF_P_`, and `$_DFF_N_`.

`pack_multiple_ffs_per_tile`
: If `True`, the pass tries to pack several FFs into different lanes of one
replacement tile when ports and config do not conflict. If `False`, every
materialized FF gets its own tile instance.

`auto_config`
: If `True`, derive one shared config with sat_fab for each packed lane set so
each selected output is an identity of its selected input. If `False`, no SAT
solve is run and lane-local `config` is used directly.

`auto_config_overwrites`
: Fixed config constraints used by `auto_config`. These values are also emitted
on the replacement tile. This option is ignored when `auto_config=False`.

`max_replacements`
: Optional cap on the number of FFs to replace.

`fail_on_invalid_lane`
: If `True`, invalid lane definitions, unknown lane config names, and invalid
`auto_config_overwrites` raise during setup. If `False`, invalid lanes and
invalid overwrites are ignored.

`fail_on_auto_config_unsat`
: If `True`, an unsatisfiable auto-config solve raises. If `False`, that
candidate pack is rejected and the pass may try another tile or skip the FF.

`fail_on_pack_conflict`
: If `True`, config, parameter, or shared-port conflicts while packing raise.
If `False`, the conflicting FF is tried in another tile or skipped.

`fail_on_unmaterialized_ff`
: If `True`, the pass raises after planning when any supported FF cell remains
unreplaced. If `False`, leftovers are reported in the summary counters.

`track_progress`
: Enable progress logging.

`progress_chunk_size`
: Number of processed FFs between progress messages.

`top_name`
: Top module to process. If `None`, the current pyosys top is used.

## Lane Options

`data_port`
: Tile input port connected to the old FF data input.

`output_port`
: Tile output port connected to the old FF output net. This is usually the
sequential output port of the tile.

`clock_port`
: Optional tile clock port connected to the old FF clock. If omitted, the pass
still materializes the FF but does not wire a tile clock port. That is only
correct for architectures where the replacement tile clock is supplied by other
means.

`include_enable_ff`
: Whether FFs with a variable enable may use this lane. If this is `False`,
enabled FFs are only compatible when their enable is statically inactive or
neutral according to the FF port definition.

`enable_tile_port`
: Tile enable port to connect.

`enable_neutral`
: Constant connected to `enable_tile_port` when the old FF has no enable. For a
normal active-high enable this is usually `1`.

`include_reset_ff`
: Whether FFs with a variable reset may use this lane.

`reset_tile_port`
: Tile reset port to connect.

`reset_neutral`
: Constant connected to `reset_tile_port` when the old FF has no reset. For a
normal active-high reset this is usually `0`.

`reset_kind`
: Optional reset timing required by the lane, either `"sync"` or `"async"`.
The FF must have matching reset semantics when it has a reset port.

`reset_value`
: Optional reset value required by the lane. The FF must have a matching reset
value parameter when one is present.

`depth_options`
: Legal latency modes for this lane. If omitted, the lane has one default
option with `depth=1` and no `mode_config`. A depth of `N` means the lane
consumes exactly `N` chained FFs from the netlist and must preserve that
latency. The planner only collapses a linear chain segment when every consumed
stage has compatible clock, enable, and reset semantics. Intermediate fanout is
left alone, so observable chain taps are not silently removed.

Example:

```python
{
    "data_port": "I0",
    "output_port": "Q0",
    "clock_port": "UserCLK",
    "depth_options": [
        {
            "depth": 3,
            "mode_config": {
                "ConfigBits[10]": 0,
                "ConfigBits[11]": 1,
            },
        },
        {
            "depth": 2,
            "mode_config": {
                "ConfigBits[10]": 1,
                "ConfigBits[11]": 0,
            },
        },
    ],
}
```

For a 5-FF chain and the lane above, the pass can materialize one depth-3
chunk and one depth-2 chunk. The final circuit still has five cycles of latency.

```text
original netlist chain:

  d -> [FF0] -> n0 -> [FF1] -> n1 -> [FF2] -> n2 -> [FF3] -> n3 -> [FF4] -> q

selected materializer chunks:

  chunk A, depth 3:

    d  -> I0 -> [tile stage 0] -> [tile stage 1] -> [tile stage 2] -> Q0 -> n2

  chunk B, depth 2:

    n2 -> I0 -> [tile stage 0] -> [tile stage 1] --------------------> Q0 -> q

latency before: 5 cycles
latency after:  3 cycles + 2 cycles = 5 cycles
```

The planner visits FF chains from source to sink where possible. It tries deeper
options first, so `depth_options=[3, 2]` naturally packs a 5-FF linear chain as
`3 + 2`. It will not collapse across an intermediate fanout:

```text
allowed depth-2 chunk:

  d -> [FF0] -> n0 -> [FF1] -> q

rejected as one depth-2 chunk:

  d -> [FF0] -> n0 -> [FF1] -> q
                |
                +----> other logic / observable tap
```

That rejection is deliberate. If `n0` is used by other logic, removing `FF0`
as part of a larger replacement would also remove or move an observable pipeline
tap.

`mode_config`
: Config bits required for one selected `depth_options` entry. In manual mode,
the emitted config is `lane.config + selected mode_config`, and conflicting
bits reject that pack. In `auto_config=True`, lane-local `config` is forbidden;
`auto_config_overwrites + selected mode_config` is fixed first, then SAT solves
the remaining config bits for the identity data path.

Manual depth selection:

```text
depth option says:

  depth = 2
  mode_config = ConfigBits[10]=1, ConfigBits[11]=0

replacement emits:

  lane.config
  + ConfigBits[10]=1
  + ConfigBits[11]=0
```

Auto-config depth selection:

```text
fixed before SAT:

  auto_config_overwrites
  + selected mode_config
  + neutralized EN/SR controls

SAT then solves:

  I0(t) == Q0(t) in the passthrough solve view

planner still consumes:

  exactly `depth` netlist FFs
```

The SAT solve proves the configured data path is identity. The `depth` value is
the timing contract that tells the planner how many original FFs this identity
path is allowed to replace.

`config`
: Config bits applied to the inserted tile. Keys may be scalar port names such
as `"MODE"` or indexed names such as `"ConfigBits[32]"`. This is valid only
when pass-level `auto_config=False`.

`params`
: Parameter updates applied to the inserted tile.

## FF Port Descriptions

The default FF port table is shared with the register absorber. A custom entry
looks like:

```python
ff_ports={
    "$dffe": {
        "clock": "CLK",
        "data": "D",
        "output": "Q",
        "enable_port": "EN",
        "enable_polarity_param": "EN_POLARITY",
    },
}
```

Reset-capable FFs can also describe reset timing and value parameters:

```python
ff_ports={
    "$sdff": {
        "clock": "CLK",
        "data": "D",
        "output": "Q",
        "reset_port": "SRST",
        "reset_kind": "sync",
        "reset_polarity_param": "SRST_POLARITY",
        "reset_value_param": "SRST_VALUE",
    },
}
```

Some FF cells have extra control ports that must be inactive for the cell to be
treated as a normal DFF. Those can be described with `required_ports`:

```python
ff_ports={
    "$dffsr": {
        "clock": "CLK",
        "data": "D",
        "output": "Q",
        "required_ports": {
            "SET": "inactive",
            "CLR": "inactive",
        },
        "polarity_params": {
            "SET": "SET_POLARITY",
            "CLR": "CLR_POLARITY",
        },
    },
}
```

## Report

The pass reports:

- the replacement tile and tile source;
- the number of lanes, discovered config bits, and supported FF cell types;
- the pass options used for the run, including `auto_config`,
  `auto_config_overwrites`, packing, failure-policy flags, and replacement
  limits;
- FF cells considered;
- FFs materialized;
- tile instances inserted;
- skipped FFs by reason;
- inserted tiles grouped by occupied lane count.

Example summary:

```text
FF Materializer Report
Top Module: ode

Summary
- FF cells considered: 1384
- Materialized FFs: 1384
- Inserted tile instances: 692

Inserted Tiles by Occupied Lane Count
- 2 lane(s): 692
```

## Typical Flow Placement

A common high-level flow is:

```text
map generic logic
map or combine LUTs
morph/replace LUT and chain cells with architecture tiles
absorb FFs that directly follow or precede existing tiles
materialize remaining standalone FFs into fresh tile instances
run final hierarchy/check/stat
```

The materializer should usually run after the passes that consume nearby FFs
into existing tiles. Otherwise it may create fresh register-only tile instances
that could have been avoided by absorption.
