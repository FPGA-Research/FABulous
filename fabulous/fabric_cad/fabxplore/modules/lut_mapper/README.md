# LUT Mapper

The LUT mapper is an architecture-aware front-end for Yosys `abc`/`abc9` LUT
mapping. It does not pack fractional LUTs by itself. Instead, it computes the
ABC `-luts` cost vector so that ABC produces a LUT-size distribution that is
more suitable for the later `lut_combinator` pass.

The problem is that ABC only sees abstract LUT sizes:

```text
LUT1, LUT2, LUT3, ...
```

but the FABulous fractional LUT architecture sees whether two LUTs can be
placed together in one macro. Therefore a good ABC cost vector should not only
ask for fewer logical LUTs. It should shift the LUT distribution toward sizes
that are likely to pair well in the final fractional-LUT packer.

## Goal

Given a fractional LUT architecture, we want to choose ABC costs:

```text
C = [C1, C2, ..., Cmax]
```

where `Cw` is the cost of a `LUTw`, such that the mapped design contains LUT
sizes that are useful for the final macro.

For example, in a `K=4` architecture with two internal LUT4 tables, a `LUT3`
and another `LUT3` may be easy to pack together, while two unrelated `LUT4`s may
need too many shared inputs. In that case the mapper should make `LUT3` cheaper
than a naive size-only model would.

## Architecture Model

For pair mode, define:

```text
K = internal LUT size
S = nominal shared inputs
P = private inputs per side = K - S
```

If select-as-data pair mode is enabled, the `S` pin can act as one additional
private input in dual mode:

```text
P_eff = K - S + 1
```

Otherwise:

```text
P_eff = K - S
```

The effective shared-input count used by the model is:

```text
S_eff = K - P_eff
```

and the maximum number of unique input nets that two packed LUTs can cover is:

```text
Q = K + P_eff
```

The implementation calls this value `pair_capacity`.

## Pair Feasibility

Let two candidate LUTs have input sets:

```text
A = inputs of L0
B = inputs of L1
```

They can be packed if:

```text
|A union B| <= Q
```

Since:

```text
|A union B| = |A| + |B| - |A intersect B|
```

the number of shared inputs required for a `LUTa + LUTb` pair is:

```text
R(a,b) = max(0, a + b - Q)
```

`R(a,b)` becomes the required-shared-input table. Higher values are worse,
because it is less likely that two arbitrary LUTs share many inputs.

## Size Penalty

Pairing two very small LUTs may be easy, but it can waste useful capacity.
Therefore the mapper also builds an unused-capacity table:

```text
U(a,b) = max(0, 2K - (a + b))
```

Small pairs have a large `U(a,b)`. Large pairs have a small `U(a,b)`.

## Combined Pair Penalty

The mapper combines the two tables with user-controlled factors:

```text
M(a,b) =
    sharing_penalty_factor * R(a,b)
  + size_penalty_factor    * U(a,b)
```

Lower `M(a,b)` means the pair size is more desirable for the architecture.

In matrix form:

```text
M = alpha * R + beta * U
```

where:

```text
alpha = sharing_penalty_factor
beta  = size_penalty_factor
```

This is intentionally simple for design-space exploration. Increasing `alpha`
pushes the cost model away from LUT combinations that need many shared inputs.
Increasing `beta` pushes the model away from small LUT pairs that waste
capacity.

## Pairability By LUT Width

The combined matrix is converted into a pairability score for each LUT width.
First, every matrix entry is normalized so that low penalties become high
scores:

```text
score(a,b) = 1 - (M(a,b) - min(M)) / (max(M) - min(M))
```

Then each LUT width gets the average score of its row:

```text
pairability(a) = average_b(score(a,b))
```

This gives values in the range:

```text
0.0 = poor pairability
1.0 = best pairability in this model
```

## ABC Cost Calculation

For LUT widths up to `K`, the mapper computes:

```text
Cw = cost_scale * (1 - pair_discount_strength * pairability(w))
```

So LUT widths that pair well become cheaper for ABC.

For LUT widths above `K`, the mapper treats them as composed wider LUTs and
costs them relative to the emitted `LUTK` cost:

```text
Cw =
    CK
  * larger_lut_base_multiplier^(w-K)
  * larger_lut_discount_factor^(w-K)
```

This matters because ABC only sees the final emitted vector. If `LUT4` is
discounted to `50`, then `LUT5` should be compared against `50`, not against an
internal hidden scale of `100`.

For example:

```text
CK = 50
larger_lut_base_multiplier = 2.0
larger_lut_discount_factor = 0.9
```

then:

```text
C5 = 50 * 2^1 * 0.9^1 = 90
C6 = 50 * 2^2 * 0.9^2 = 162
C7 = 50 * 2^3 * 0.9^3 = 292
```

If `raw_cost_vector` is set, the analytical model is ignored and the provided
tuple is passed directly to ABC.

## Larger LUTs And Mux-Combiner Primitives

LUTs wider than the base fragment size are interpreted as composed LUTs. The
model assumes that a `LUT(K+n)` can be built by combining `2^n` smaller `LUTK`
truth-table fragments with a runtime mux tree.

For example, with `K=4`:

```text
2 x LUT4 + mux2 -> LUT5
4 x LUT4 + mux4 -> LUT6
8 x LUT4 + mux8 -> LUT7
```

This is the same architectural idea as Xilinx-style `MUXF` resources:

```text
MUXF5 / mux2  combines two LUT outputs
MUXF6 / mux4  combines four LUT outputs through two levels
MUXF7 / mux8  combines eight LUT outputs through three levels
```

The exact primitive names in FABulous do not need to be identical to Xilinx.
The important modeling point is that wider LUTs are not free. They consume
multiple base LUT fragments and a mux-combiner path, and they usually produce
one logical output. Therefore the mapper grows their cost approximately
exponentially:

```text
LUT(K+1) ~= 2 * LUTK
LUT(K+2) ~= 4 * LUTK
LUT(K+3) ~= 8 * LUTK
```

The `larger_lut_discount_factor` lets the user make these wider LUTs slightly
cheaper than exact multiplication:

```text
C(K+n) = CK * larger_lut_base_multiplier^n * larger_lut_discount_factor^n
```

This discount is useful because a wider LUT can reduce logic depth. For
example, a `LUT6` may replace a small cascade of LUT4 logic. If that helps ABC
reduce the mapped graph, it can be worth paying more than one base fragment.

However, this only helps final resource use if the backend can later implement
the wide LUT efficiently. If the downstream FABulous flow only has a clean
full-mode implementation for `LUT5`, then exposing `LUT6`, `LUT7`, or `LUT8` to
ABC may increase the final resource count unless matching mux-combiner
primitives are available. In that case, set `max_lut_size=5` or raise the costs
of larger LUTs.

## Example: K=4, S=3, Select-As-Data Enabled

With:

```text
K = 4
S = 3
select-as-data = true
```

the effective private input count is:

```text
P_eff = K - S + 1 = 2
```

and:

```text
Q = K + P_eff = 6
```

### Required Shared Inputs

```text
        LUT1  LUT2  LUT3  LUT4
LUT1      0     0     0     0
LUT2      0     0     0     0
LUT3      0     0     0     1
LUT4      0     0     1     2
```

Interpretation:

```text
LUT3 + LUT3 needs 0 shared inputs
LUT4 + LUT2 needs 0 shared inputs
LUT4 + LUT3 needs 1 shared input
LUT4 + LUT4 needs 2 shared inputs
```

### Unused-Capacity Penalty

For `K=4`, the two internal LUT fragments have a total input-width capacity of
`2K = 8`.

```text
        LUT1  LUT2  LUT3  LUT4
LUT1      6     5     4     3
LUT2      5     4     3     2
LUT3      4     3     2     1
LUT4      3     2     1     0
```

### Combined Pair Penalty

With default factors:

```text
sharing_penalty_factor = 1.0
size_penalty_factor    = 1.0
```

the combined matrix is:

```text
        LUT1  LUT2  LUT3  LUT4
LUT1      6     5     4     3
LUT2      5     4     3     2
LUT3      4     3     2     2
LUT4      3     2     2     2
```

The lowest entries are the most desirable pair shapes. Here the model likes
combinations such as:

```text
LUT2 + LUT4
LUT3 + LUT3
LUT3 + LUT4
LUT4 + LUT4
```

but `LUT4 + LUT4` only looks good if the sharing penalty is not too strong. If
experiments show that actual `LUT4 + LUT4` pairs rarely share two inputs, the
user can increase `sharing_penalty_factor`.

## Example With Stronger Sharing Penalty

Suppose:

```text
sharing_penalty_factor = 3.0
size_penalty_factor    = 0.7
```

Then the model more strongly punishes pairs that need shared inputs while still
preferring useful larger LUTs over tiny pairs. This kind of setting often pushes
ABC toward distributions with more `LUT2`, `LUT3`, and `LUT5` instead of too
many hard-to-pair `LUT4 + LUT4` candidates.

This is useful when the final `lut_combinator` report shows that the design has
limited real shared-input overlap.

## Backend Selection

The mapper can emit either:

```text
abc  -luts C1,C2,...
abc9 -luts C1,C2,...
```

The default backend is `abc9`, because it often produces better FPGA LUT
mapping results. The same analytical cost vector is used for both backends.

## How To Use

From an architecture synthesizer:

```python
self.design_lut_mapper_pass(
    max_lut_size=5,
    use_select_as_data_in_pair_mode=True,
    sharing_penalty_factor=3.0,
    size_penalty_factor=0.7,
    larger_lut_discount_factor=0.9,
)
```

Then run the `lut_combinator` afterwards:

```python
self.design_lut_combinator_pass(
    passthrough=True,
    use_select_as_data_in_pair_mode=True,
)
```

The intended exploration loop is:

```text
1. Choose LUT mapper parameters.
2. Run ABC/ABC9 with the generated cost vector.
3. Run lut_combinator.
4. Inspect the final pair/shared-input report.
5. Adjust penalty factors or max_lut_size.
```

The key feedback is the actual shared-input distribution after ABC. The cost
model is analytical, but the design decides whether those assumptions were good.
