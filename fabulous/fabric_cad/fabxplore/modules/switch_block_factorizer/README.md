# Switch Block Factorizer

`switch_block_factorizer` rewrites an existing FABulous switch matrix in place.
It breaks large switch-matrix mux rows into smaller JUMP-based mux stages while
preserving the original logical source-to-sink reachability.

This pass is a structural implementation transform:

```text
same logical routing choices
different physical mux structure
```

It is not a sparsification pass. It does not remove routing choices, and it does
not try to make the matrix smaller by deleting PIPs. Instead, it changes how a
large mux is represented inside FABulous.

## Why Factorize?

Routing matrices can produce mux rows with large fanin:

```text
{16}LA_I0,[S0|S1|S2|S3|S4|S5|S6|S7|S8|S9|S10|S11|S12|S13|S14|S15]
```

A large mux is simple as a logical graph edge set, but it can be unattractive as
implementation structure. Routing architecture literature and tools model muxes
as real circuit elements. VTR exposes switch-block topology and flexibility
through `switch_block` and `Fs`, OpenFPGA maps switch-block and connection-block
switches to mux circuit models, and routing architecture work commonly treats
mux fanin as relevant for area and delay modeling.

Factorization lets fabxplore explore this question:

```text
Can we keep the same routing choices while replacing one large mux with smaller
staged muxes?
```

That is useful when:

- Large generated muxes are undesirable for timing, layout regularity, or code
  generation.
- You want to model a hierarchical switch-block structure with FABulous JUMP
  wires.
- You want to keep the same routeability surface before running demand-based
  routing evaluation.
- You want reports that separate logical routing choices from implementation
  mux shape.

## Input And Output

The pass reads the active matrix from the loaded FABulous project. The input may
be either:

```text
<tile>_switch_matrix.list
<tile>_switch_matrix.csv
```

The output is always normalized to:

```text
Tile/<tile>/<tile>_switch_matrix.list
```

The pass then updates:

```text
Tile/<tile>/<tile>.csv
```

to point at the normalized list and to add generated `JUMP` resources. After
that, FABulous is called again to regenerate:

```text
<tile>_switch_matrix.csv
<tile>_switch_matrix.v
<tile>_ConfigMem.csv
<tile>_ConfigMem.v
<tile>.v
```

All work is in-place. Old generated artifacts are removed before FABulous is
called again.

## Basic Example

Flat mux row:

```text
{8}LA_I0,[N0|N1|E0|E1|S0|S1|W0|W1]
```

With `global_reduction=1`, this becomes:

```text
{4}J_FAC_G0_0_BEG0,[N0|N1|E0|E1]
{4}J_FAC_G0_1_BEG0,[S0|S1|W0|W1]
{2}LA_I0,[J_FAC_G0_0_END0|J_FAC_G0_1_END0]
```

and the tile CSV receives:

```text
JUMP,J_FAC_G0_0_BEG,0,0,J_FAC_G0_0_END,1,
JUMP,J_FAC_G0_1_BEG,0,0,J_FAC_G0_1_END,1,
MATRIX,./<tile>_switch_matrix.list
```

Reachability is preserved:

```text
N0 -> LA_I0       before
N0 -> J_FAC... -> LA_I0 after
```

Every original source can still reach the original sink through one generated
JUMP stage.

## Mathematical Model

Treat the switch matrix as a directed bipartite graph:

```text
G = (S union D, E)
```

where:

```text
S = source wires
D = destination mux rows
E = source -> destination PIPs
```

For one destination row `d`, the original source set is:

```text
S_d = {s | (s, d) in E}
n   = |S_d|
```

The flat row is:

```text
d <- S_d
```

For a factorization target `t`, sources are partitioned into chunks:

```text
C_0, C_1, ..., C_m
```

with:

```text
|C_i| <= t
m + 1 = ceil(n / t)
```

For every chunk `C_i`, the factorizer creates one generated JUMP wire:

```text
J_i_BEG -> J_i_END
```

and rewrites the graph as:

```text
J_i_BEG <- C_i
d       <- {J_0_END, J_1_END, ..., J_m_END}
```

In list-file form:

```text
{t}J_i_BEG0,[sources in C_i]
{m+1}d,[J_0_END0|J_1_END0|...|J_m_END0]
```

The important invariant is:

```text
for every original source s in S_d:
    s can still reach d after factorization
```

The pass verifies this invariant before reporting success.

## Config-Bit Effect

Factorization usually reduces maximum mux fanin, but it can increase total
config bits because it adds intermediate muxes.

Approximate select-bit cost for one mux row is:

```text
cost(n) = ceil(log2(n))
```

So a flat 8:1 mux costs roughly:

```text
ceil(log2(8)) = 3 bits
```

After factorization into two 4:1 muxes plus one 2:1 mux:

```text
2 * ceil(log2(4)) + ceil(log2(2)) = 5 bits
```

FABulous computes the actual config-bit count from the generated matrix. The
formula above is only the mental model for why reports often show:

```text
max fanin decreases
matrix config bits increase
```

## Pass Interface

```python
self.pnr_switch_block_factorizer_pass(
    tile_name="test_tile2",
    global_reduction=1,
    reduction_rules=[
        {"from_fanin": 16, "to_fanin": 8},
        {"from_fanin": 8, "to_fanin": 4},
    ],
    min_mux_fanin_to_factorize=3,
    jump_prefix="J_FAC",
    max_added_jump_wires=None,
    config_bit_capacity_override=None,
    config_bit_margin=0,
    track_progress=True,
)
```

## Options

### `tile_name`

Name of the loaded FABulous tile to transform.

The pass uses the loaded FABulous tile object to find the active matrix. This is
the normal interface:

```python
self.pnr_switch_block_factorizer_pass(tile_name="test_tile2")
```

### `tile_dir`

Optional manual tile-directory override.

Default:

```text
directory containing the loaded tile matrix
```

Use this only when the loaded FABulous tile object does not point to the intended
directory.

### `tile_csv`

Optional manual tile CSV override.

Default:

```text
<tile_dir>/<tile_name>.csv
```

The tile CSV must be rewritten because generated JUMP wires are tile resources,
not only switch-matrix PIPs.

### `switch_matrix`

Optional manual switch-matrix override.

Default:

```text
tile.matrixDir
```

The file may be `.list` or `.csv`. The output is always normalized back to
`<tile>_switch_matrix.list`.

### `global_reduction`

Number of global fanin-halving passes.

```python
global_reduction=1
```

means every eligible mux row is split once:

```text
mux16 -> two mux8 stages -> final mux2
mux8  -> two mux4 stages -> final mux2
mux7  -> one mux4 + one mux3 stage -> final mux2
mux4  -> two mux2 stages -> final mux2
mux2  -> unchanged
```

The implementation chooses:

```text
target_fanin = ceil(current_fanin / 2)
```

Rows are then chunked into groups of at most `target_fanin`.

`global_reduction=None` disables the global step. `global_reduction=0` also
performs no global factorization.

### `reduction_rules`

Exact fanin rules applied after `global_reduction`.

Each rule is a Pydantic `MuxReductionRule` or a dictionary:

```python
{"from_fanin": 16, "to_fanin": 4}
```

This means:

```text
only rows with exactly 16 sources are split into generated muxes of at most 4
sources each
```

Example:

```text
mux16 -> four mux4 stages -> final mux4
```

Rules are useful when you want precise control:

```python
global_reduction=None
reduction_rules=[
    {"from_fanin": 16, "to_fanin": 8},
    {"from_fanin": 8, "to_fanin": 4},
]
```

In that case, mux4 rows are untouched unless a rule targets them.

### `min_mux_fanin_to_factorize`

Smallest mux row eligible for factorization.

For example:

```python
min_mux_fanin_to_factorize=8
```

means:

```text
mux8, mux9, ... may be factorized
mux7 and below are left unchanged
```

This option is important with `global_reduction=1`. If it is set to `3`, mux4
rows are also eligible and may become staged muxes. If you only want to remove
very large muxes, use a larger value.

### `jump_prefix`

Prefix for generated JUMP resources.

Example:

```python
jump_prefix="J_FAC"
```

Generates names like:

```text
J_FAC_G0_0_BEG
J_FAC_G0_0_END
```

Before inserting new JUMP rows, the pass removes old generated rows with the same
prefix. This keeps repeated in-place runs from accumulating stale resources.

### `max_added_jump_wires`

Optional guardrail on generated JUMP rows.

```python
max_added_jump_wires=128
```

If the transform would generate more than 128 JUMP wires, the pass fails before
rewriting files.

Use this when you are exploring aggressive factorization and want a clear bound
on tile-resource growth.

### `config_bit_capacity_override`

Optional total tile config-bit capacity.

Default:

```python
config_bit_capacity_override=None
```

uses the loaded FABulous fabric capacity:

```text
frameBitsPerRow * maxFramesPerCol
```

Set this only for experiments where the architecture capacity is intentionally
being changed. Note that FABulous generation itself also checks the loaded fabric
capacity when generating config memory, so for final generation the project
`fabric.csv` must agree with the capacity you actually want.

### `config_bit_margin`

Reserved margin below the config-bit capacity.

```python
config_bit_margin=16
```

means:

```text
usable capacity = capacity - 16
```

Use this when later passes may add config bits.

### `track_progress`

Whether the pass logs progress messages.

Set this to `False` in tests or scripted sweeps where only the final report is
needed.

## Reading The Report

Example:

```text
Muxes
- rows: 426 -> 558
- pips: 956 -> 1088
- max fanin: 8 -> 4
- factorized rows: 66
- added JUMP wires: 132
- generated hierarchy PIPs: 404
```

Interpretation:

- `rows` may increase because generated JUMP mux rows are new rows.
- `pips` may increase because reachability now goes through intermediate muxes.
- `max fanin` should decrease if factorization was effective.
- `added JUMP wires` is the number of generated tile resources.
- `generated hierarchy PIPs` counts PIPs involving generated hierarchy rows.

Config bits:

```text
matrix config bits before: 458
matrix config bits after: 526
total tile config bits after: 636
```

This is expected when a flat mux is replaced with multiple smaller muxes.

Verification:

```text
source-to-sink reachability preserved: True
```

This is the key correctness check. It means the pass did not remove an original
logical routing option.

## Benefits And Disadvantages

| Aspect | Benefit | Disadvantage |
| --- | --- | --- |
| Maximum mux fanin | Can reduce worst-case mux size, for example mux8 to mux4 stages. | May create more mux rows overall. |
| Logical routability | Original source-to-sink choices are preserved. | It does not improve logical routability by itself. |
| Config bits | Can make mux shape more regular and staged. | Usually increases select-bit count because intermediate muxes need control bits. |
| Architecture modeling | Lets FABulous model hierarchical switch blocks using JUMP wires. | The hierarchy is structural; physical timing still needs later evaluation. |
| Reports | Makes large muxes visible and measurable. | A lower max fanin is not automatically a better architecture. |
| DSE | Useful knob for comparing flat vs staged switch matrices. | Must be evaluated with routing-demand or nextpnr-based tests before drawing conclusions. |

## What This Pass Does Not Do

It does not remove PIPs:

```text
source -> sink choices are preserved
```

It does not choose Wilton/subset/universal patterns:

```text
tile_builder creates those logical edge sets
switch_block_factorizer stages the edge sets
```

It does not update the real project frame capacity:

```text
fabric.csv still controls FABulous generation capacity
```

It does not prove timing is better:

```text
smaller mux fanin is a useful structural signal, but timing requires a physical
model or downstream implementation data
```

## Recommended Usage

For only very large muxes:

```python
self.pnr_switch_block_factorizer_pass(
    tile_name="test_tile2",
    global_reduction=1,
    min_mux_fanin_to_factorize=8,
)
```

For precise explicit rules:

```python
self.pnr_switch_block_factorizer_pass(
    tile_name="test_tile2",
    global_reduction=None,
    reduction_rules=[
        {"from_fanin": 16, "to_fanin": 8},
        {"from_fanin": 8, "to_fanin": 4},
    ],
)
```

For aggressive staging:

```python
self.pnr_switch_block_factorizer_pass(
    tile_name="test_tile2",
    global_reduction=2,
    min_mux_fanin_to_factorize=3,
    max_added_jump_wires=256,
)
```

Expect the last case to add many JUMP wires and config bits.

## References

- VTR architecture reference, switch-block patterns and `Fs`:
  <https://mithro-vtr.readthedocs.io/en/latest/arch/reference.html>
- OpenFPGA architecture annotation, switch-block and connection-block mux circuit
  binding:
  <https://openfpga.readthedocs.io/en/latest/manual/arch_lang/annotate_vpr_arch/>
- Murray et al., "The Speed of Diversity: Exploring Complex FPGA Routing
  Architectures", discussion of switch-block topology and mux fanin delay
  modeling:
  <https://www.eecg.utoronto.ca/~vaughn/papers/fpl2016_complex_routing.pdf>
- Betz and Rose, "FPGA Routing Architecture: Segmentation and Buffering to
  Optimize Speed and Density", area and delay modeling for FPGA routing:
  <https://www.eecg.toronto.edu/~jayar/pubs/betz/fpga99betz.pdf>
