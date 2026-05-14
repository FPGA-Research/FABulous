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

## What The Pass Does Not Prove

The current implementation does not use SAT to derive the lane configuration.
The user supplies the lane `config` and `params`.

That means the architecture author is responsible for making sure the lane
configuration really implements the intended FF path, for example
$Q0(t + 1) = I0(t)$ or $Q1(t + 1) = I1(t)$.

The pass checks structural legality, control compatibility, config conflicts,
and port compatibility. It does not formally prove that the provided config bits
make the tile behave like the removed FF.

This is intentional for now because many architectures have direct register
bypass paths where SAT is unnecessary and manual config is clearer. A future
auto-config mode can use the stored tile BLIF model to derive passthrough config
bits when the data must pass through configurable logic.

## Internal Structure

The module follows the same shape as the other mapping modules:

```text
modules/ff_materializer/
  core/
    models.py           typed internal models and pydantic lane validation
    reader.py           reads pyosys design and tile model
    materializer.py     plans FF-to-lane replacements
    writer.py           mutates the live pyosys design
    report.py           renders a Jinja2 report
    process_tracker.py  progress logging
```

The reader builds internal Python objects from the Yosys object view. The
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

The BLIF text is stored so future features, such as SAT-derived passthrough
configuration, can reuse the same tile model.

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
            "config": {
                "ConfigBits[18]": 1,
                "ConfigBits[19]": 1,
                "ConfigBits[22]": 1,
                "ConfigBits[23]": 1,
                "ConfigBits[26]": 1,
                "ConfigBits[27]": 1,
                "ConfigBits[30]": 1,
                "ConfigBits[31]": 1,
                "ConfigBits[32]": 1,
            },
        },
    ],
    ff_ports=None,
    pack_multiple_ffs_per_tile=True,
    max_replacements=None,
    strict=False,
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

`max_replacements`
: Optional cap on the number of FFs to replace.

`strict`
: If `True`, some invalid packing situations raise errors instead of being
reported as skips. This is useful while validating an architecture definition.

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

`config`
: Config bits applied to the inserted tile. Keys may be scalar port names such
as `"MODE"` or indexed names such as `"ConfigBits[32]"`.

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
