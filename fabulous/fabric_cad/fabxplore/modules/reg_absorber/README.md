# Register Absorber

The register absorber moves flip-flops that are already adjacent to a mapped
primitive into sequential ports of that primitive. It is a structural cleanup
pass for architectures where a tile can expose both a combinational data path
and a registered data path.

A typical tile has a combinational output such as `O0` and a registered output
such as `Q0`. Before absorption the netlist may contain an explicit FF after
`O0`:

```text
        +---------+        +------+        downstream
... --> | tile O0 | -----> |  FF  | -----> logic
        +---------+        +------+
```

After absorption the FF is removed and the downstream logic is driven by the
tile's sequential output:

```text
        +---------+
... --> | tile Q0 | ---------------------> downstream logic
        +---------+
```

The same idea works on tile inputs. If an FF drives a combinational tile input,
the pass can move that FF into a sequential tile input port:

```text
before:  upstream -----> FF -----> tile.I0

after:   upstream -------------> tile.IQ0
```

This pass does not invent new sequential resources. It only absorbs FFs that
are directly upstream or downstream of a selected primitive instance. Remaining
FFs elsewhere in the design are intentionally left alone and need a later pass
or primitive replacement flow.

## Problem View

Let a combinational tile output implement a Boolean function

$$
    y = f(x_0, x_1, \ldots, x_{n-1}).
$$

If an adjacent FF stores that output, the observable registered value is

$$
    q(t+1) = f(x_0(t), x_1(t), \ldots, x_{n-1}(t)).
$$

If the architecture has a sequential tile output `Q0` with the same next-state
function, then the explicit FF and the tile register are equivalent when their
sequential controls match:

$$
    Q_0(t+1) = f(x_0(t), x_1(t), \ldots, x_{n-1}(t)).
$$

The pass therefore rewrites the netlist from

$$
    f(x) \rightarrow D_{FF}, \quad Q_{FF} \rightarrow z
$$

to

$$
    Q_{tile} \rightarrow z.
$$

For input-side absorption, the same reasoning applies with the FF moved before
the tile input. The explicit FF output is replaced by a tile sequential input.

## Matching Rules

Each absorption rule describes one legal movement:

```text
output-side: tile.comb_port -> FF.D    becomes tile.seq_port -> users
input-side:  FF.Q -> tile.comb_port    becomes FF.D -> tile.seq_port
```

The pass checks the matched FF and primitive instance before rewriting:

- The candidate signal must be one bit wide.
- The FF must be a supported type from `ff_ports`.
- The matched signal must not have extra fanout unless `allow_extra_fanout=True`.
- If `clock_port` is given, the primitive clock must match the FF clock, or be
  unconnected so the writer can connect it.
- Variable enable/reset FFs are skipped unless the rule explicitly includes
  them.
- Reset kind and reset value must match when requested.
- Conflicting config updates on the same primitive are skipped.
- The same FF or primitive port is not consumed twice.

## ASCII Examples

### Output FF Absorption

Rule:

```python
{
    "side": "output",
    "cell_type": "MY_TILE",
    "comb_port": "O0",
    "seq_port": "Q0",
    "clock_port": "CLK0",
}
```

Before:

```text
          MY_TILE                 LUTFF
      +------------+            +-------+
a --> | I0      O0 |--- comb -->| D   Q |--- y
clk ->| CLK0    Q0 |            | CLK   |
      +------------+            +-------+
```

After:

```text
          MY_TILE
a --> +------------+
clk ->| CLK0    Q0 |--- y
      +------------+
```

### Input FF Absorption

Rule:

```python
{
    "side": "input",
    "cell_type": "MY_TILE",
    "comb_port": "I0",
    "seq_port": "IQ0",
    "clock_port": "CLKI",
}
```

Before:

```text
         LUTFF                  MY_TILE
      +-------+              +------------+
a --->| D   Q |--- in_q ---->| I0      O0 |--- y
clk ->| CLK   |              | CLKI       |
      +-------+              +------------+
```

After:

```text
          MY_TILE
a ----> +------------+
clk --> | CLKI   IQ0 |
        |        O0  |--- y
        +------------+
```

### Enable FF Absorption

If the FF has an enable and the tile has an enable port, the enable can be
wired into the tile:

```python
{
    "side": "output",
    "cell_type": "MY_TILE",
    "comb_port": "O0",
    "seq_port": "Q0",
    "clock_port": "CLK0",
    "include_enable_ff": True,
    "enable_tile_port": "EN0",
    "enable_neutral": 1,
}
```

Before:

```text
tile.O0 ---> $dffe.D
ff.EN   <--- en
ff.Q    ---> y
```

After:

```text
tile.Q0  ---> y
tile.EN0 <--- en
```

If `include_enable_ff=True` is set but `enable_tile_port` is omitted, the pass
still removes the FF. That mode is useful when a later packing/configuration
flow handles enable routing. It is powerful, but should be used only when that
flow really preserves enable semantics.

### Reset FF Absorption

Sync-reset FFs can be absorbed into sync-reset tile ports:

```python
{
    "side": "output",
    "cell_type": "MY_TILE",
    "comb_port": "O0",
    "seq_port": "Q0",
    "clock_port": "CLK0",
    "include_reset_ff": True,
    "reset_tile_port": "SR0",
    "reset_neutral": 0,
    "reset_kind": "sync",
    "reset_value": 0,
}
```

The pass rejects incompatible reset behavior, for example an async-reset FF when
the rule says the tile reset is sync.

### Multi-Clock Tiles

A tile may have multiple sequential paths with different clocks. Use one rule
per path:

```python
rules=[
    {
        "side": "output",
        "cell_type": "MY_TILE",
        "comb_port": "O0",
        "seq_port": "Q0",
        "clock_port": "CLK0",
    },
    {
        "side": "output",
        "cell_type": "MY_TILE",
        "comb_port": "O1",
        "seq_port": "Q1",
        "clock_port": "CLK1",
    },
]
```

This can absorb

```text
O0 -> FF(clk_a) -> y0
O1 -> FF(clk_b) -> y1
```

into

```text
Q0 -> y0, CLK0 <- clk_a
Q1 -> y1, CLK1 <- clk_b
```

If two different FF clocks try to use the same tile clock port, the second
absorption is skipped as a clock mismatch.

## What It Does Not Do

The pass is intentionally local. It does not remove all FFs from a design.
It only handles these adjacent patterns:

```text
tile output -> FF
FF output   -> tile input
```

It does not currently absorb:

- FFs separated from a tile by arbitrary logic.
- FF chains such as `tile -> FF -> FF -> FF` beyond the first adjacent pattern.
- Vector FFs; the current model is one-bit only.
- Latches. Latches are level-sensitive and require a separate rule model.
- Clock polarity conversion, such as absorbing a negative-edge FF into a
  positive-edge-only tile register.

## Pass Interface

Use the pass through the synthesizer:

```python
self.design_absorb_registers_pass(
    cell_types=["MY_TILE"],
    rules=[
        {
            "side": "output",
            "cell_type": "MY_TILE",
            "comb_port": "O0",
            "seq_port": "Q0",
            "clock_port": "CLK0",

            "include_enable_ff": True,
            "enable_tile_port": "EN0",
            "enable_neutral": 1,

            "include_reset_ff": True,
            "reset_tile_port": "SR0",
            "reset_neutral": 0,
            "reset_kind": "sync",
            "reset_value": 0,

            "config": {
                "ConfigBits[12]": 1,
            },
            "attributes": {
                "FF_USED": 1,
            },
            "remove_disconnected_comb_port": True,
        }
    ],
    ff_ports=None,
    allow_extra_fanout=False,
    strict=False,
    track_progress=True,
    progress_chunk_size=100,
    top_name=None,
)
```

### Top-Level Options

`cell_types`
: Primitive/tile cell types that may absorb adjacent FFs.

`rules`
: List of absorption rules. Each rule can be a dictionary and is validated into
  an internal pydantic model.

`ff_ports`
: Optional FF cell interface map. If `None`, built-in Yosys-style defaults are
  used. You can override this for custom FF cells.

`allow_extra_fanout`
: If `False`, skip candidates where the absorbed signal also drives other logic.
  This is the safe default.

`strict`
: If `True`, selected invalid cases raise an error instead of being counted as
  skipped.

`track_progress`
: Enables progress logging.

`progress_chunk_size`
: Number of rule checks between progress updates.

`top_name`
: Top module to process. `None` uses the current design top.

`log_report`
: Synthesizer wrapper option. If `True`, logs the final report.

### Rule Options

`side`
: Either `"output"` or `"input"`.

`cell_type`
: Primitive type the rule applies to.

`comb_port`
: Existing combinational primitive port.

`seq_port`
: Sequential primitive port used after absorption.

`clock_port`
: Optional primitive clock port. If set, it must match the FF clock or be
  unconnected so the pass can wire it. If omitted, the pass does not handle the
  clock port.

`include_enable_ff`
: Allows FFs with variable enable to be absorbed. Without this, enabled FFs are
  absorbed only when their enable is statically active.

`enable_tile_port`
: Optional tile enable port. If the FF has an enable, it is wired here.

`enable_neutral`
: Constant used for `enable_tile_port` when the absorbed FF has no enable.

`include_reset_ff`
: Allows FFs with variable reset to be absorbed. Without this, reset FFs are
  absorbed only when reset is statically inactive.

`reset_tile_port`
: Optional tile reset port. If the FF has reset, it is wired here.

`reset_neutral`
: Constant used for `reset_tile_port` when the absorbed FF has no reset.

`reset_kind`
: Optional reset timing semantics, `"sync"` or `"async"`. If set, it must match
  the FF reset kind.

`reset_value`
: Optional reset value required by the tile. If set, it must match the FF reset
  value.

`config`
: Config port updates to apply to the primitive instance, for example
  `{"ConfigBits[12]": 1}`.

`attributes`
: Attribute updates to apply to the primitive instance.

`remove_disconnected_comb_port`
: If `True`, disconnect `comb_port` after absorption when `comb_port != seq_port`.

### FF Port Defaults

The pass has defaults for common Yosys cells such as `$dff`, `$dffe`, `$sdff`,
`$adff`, `$sdffe`, and `LUTFF`. A custom map can be supplied:

```python
ff_ports={
    "MY_DFFE": {
        "clock": "C",
        "data": "D",
        "output": "Q",
        "enable_port": "CE",
        "enable_polarity_param": "CE_POLARITY",
    },
}
```

FF-side metadata describes the source FF. Rule-side metadata describes how the
tile exposes the absorbed register.

## Report

The pass emits a report with:

- number of primitive cells considered
- number of FF cells considered
- absorbed FFs, split by input-side and output-side
- skipped candidates by reason
- absorptions grouped by primitive type
