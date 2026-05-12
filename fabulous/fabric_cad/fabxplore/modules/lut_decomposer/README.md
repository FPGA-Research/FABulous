# LUT Decomposer

The LUT decomposer replaces a high-width Yosys `$lut` with a set of smaller
leaf `$lut` cells plus a configurable mux-like primitive. It is useful when the
synthesis flow can temporarily create larger LUTs, for example LUT6/LUT7/LUT8,
but the architecture should finally express that logic as smaller LUTs and a
special recombination block.

The important part is that the recombination block is not hard-coded. The user
provides a Verilog module, its data input ports, select input ports, output
ports, and config bits. The decomposer then asks SAT whether that module can
behave like the mux shape required by the decomposition.

## Why This Is Useful

Many FPGA-style fabrics can build a larger logical LUT by combining smaller LUTs
inside one tile. Xilinx-style `MUXF` cells are the classic mental model: two
LUTs compute the cofactors of a larger function, and a dedicated mux chooses the
right cofactor output with the remaining LUT input.

The same idea is useful for FABulous tiles. A tile might physically contain
LUT4/LUT5 resources plus a configurable mux network. To the mapper, however, it
can be convenient to first create a larger logical `$lut`, such as LUT6 or LUT8,
because this gives ABC/Yosys more freedom during technology mapping. The LUT
decomposer bridges those two views:

```text
logical netlist view:
  one LUT6 or LUT8 cell

tile implementation view:
  several smaller leaf LUTs + one configurable mux primitive
```

So the pass answers the question:

> Can this full LUT from the mapped netlist be decomposed into smaller LUTs and
> then recombined by the tile's mux-like primitive?

If the answer is yes, the high-width `$lut` is replaced by generated leaf
`$lut` cells and one configured mux primitive instance. If the answer is no,
the original `$lut` is left untouched and reported as failed.

## Mux Primitive Contract

The mux primitive is a normal Verilog module, but for the decomposer it must
represent a configurable recombination block. It should have:

- data input ports that can receive leaf LUT outputs,
- select input ports that can receive the remaining original LUT inputs,
- at least one output port that can drive the original LUT output,
- optional config ports or config-bit prefixes that select the internal mux
  behavior.

Mathematically, the primitive should be able to realize a mux function:

$$
M_o(\rho(D,S), c) = D_{\mathrm{idx}(S)}
$$

for some input routing \(\rho\), output choice \(o\), and config assignment
\(c\). The decomposer does not assume that port `A` is always data input 0 or
that output `M_AB` is always the right output. SAT discovers that routing and
configuration from the Verilog model.

A tiny illustrative primitive could look like this:

```verilog
module mux2_configurable (
  input A,
  input B,
  input S,
  input ConfigBits,
  output M0,
  output M1
);
  wire mux_ab = S ? B : A;
  wire mux_ba = S ? A : B;

  assign M0 = ConfigBits ? mux_ba : mux_ab;
  assign M1 = ConfigBits ? mux_ab : mux_ba;
endmodule
```

For LUT6-to-LUT5 decomposition, the leaf LUTs produce `D0` and `D1`, and the
sixth original LUT input becomes `S0`. SAT can prove whether the primitive can
be configured so that either `M0` or `M1` behaves like:

$$
S_0 ? D_1 : D_0.
$$

## Mental Model

A high-width LUT implements one Boolean function

$$
f : \{0,1\}^{n} \to \{0,1\}.
$$

If the target leaf LUT width is \(k\), with \(k < n\), then the function can be
split into cofactors over the upper \(n-k\) inputs. Let

$$
x = (x_0,\ldots,x_{k-1})
$$

be the leaf LUT inputs and

$$
s = (s_0,\ldots,s_{n-k-1})
$$

be the select inputs. For every select assignment \(j\), the decomposer creates
one leaf function

$$
g_j(x) = f(x, s=j).
$$

Then the original function can be reconstructed as

$$
f(x,s) = g_{\mathrm{idx}(s)}(x),
$$

where

$$
\mathrm{idx}(s) = \sum_{i=0}^{n-k-1} s_i 2^i.
$$

So a LUT decomposition has two parts:

1. A deterministic cofactor extraction step.
2. A mux realization step that selects the correct cofactor output.

Only the second part needs SAT.

## What Does Not Need SAT

Extracting the smaller LUT truth tables is pure truth-table indexing. The INIT
of a Yosys `$lut` is LSB-first, so bit \(a\) of the original INIT is the output
for input assignment \(a\). For source width \(n\), leaf width \(k\), and
cofactor index \(j\), the generated leaf INIT is:

$$
\mathrm{INIT}_{g_j}[u] =
\mathrm{INIT}_{f}\left[u + (j \ll k)\right]
$$

for all

$$
0 \le u < 2^k.
$$

This is exact and does not depend on the target mux primitive. The decomposer
can always generate the leaf LUTs once it has the original INIT.

Example: LUT6 to LUT5 creates two cofactors:

```text
leaf0 = f(A0, A1, A2, A3, A4, A5=0)
leaf1 = f(A0, A1, A2, A3, A4, A5=1)
```

The final result is:

```text
Y = A5 ? leaf1 : leaf0
```

Example: LUT8 to LUT5 creates eight cofactors:

```text
leaf0 = f(A0..A4, A5=0, A6=0, A7=0)
leaf1 = f(A0..A4, A5=1, A6=0, A7=0)
...
leaf7 = f(A0..A4, A5=1, A6=1, A7=1)
```

The final result is:

```text
Y = leaf[{A7, A6, A5}]
```

with the usual LSB-first select indexing.

## What SAT Solves

The user-provided mux primitive is a configurable circuit:

$$
M(p, c) : \{0,1\}^{m} \times \{0,1\}^{q} \to \{0,1\}^{r},
$$

where:

- \(p\) are the primitive input ports,
- \(c\) are configuration bits,
- \(r\) is the number of candidate output ports.

For a decomposition needing \(d\) cofactor data inputs and \(t\) select inputs,
the abstract mux specification is:

$$
h(D_0,\ldots,D_{d-1}, S_0,\ldots,S_{t-1}) =
D_{\mathrm{idx}(S)}.
$$

SAT tries to find:

- a routing function from primitive inputs to abstract inputs,
- a selected primitive output,
- a config-bit assignment,

such that the primitive behaves exactly like \(h\):

$$
\exists \rho, o, c\quad
\forall D,S:\quad
M_o(\rho(D,S), c) = h(D,S).
$$

In words: can this Verilog module be configured and wired so that one of its
outputs acts like the mux needed to recombine the generated leaf LUTs?

If SAT succeeds, the decomposer receives:

- which primitive input gets each leaf output,
- which primitive input gets each select signal,
- which primitive output drives the original LUT output,
- what value each config bit must have.

If SAT fails, the selected LUT cannot be decomposed with that primitive shape
and is counted as failed.

## Shape Cache

The SAT problem depends on the mux shape, not on the actual LUT INIT. For
example, every LUT6-to-LUT5 decomposition needs the same shape:

```text
2 data inputs + 1 select input
```

Every LUT8-to-LUT5 decomposition needs:

```text
8 data inputs + 3 select inputs
```

So the solver caches by:

$$
(d,t) = (\text{number of data inputs}, \text{number of select inputs})
$$

After the first successful solve for a shape, all later LUTs of the same shape
reuse the same mux input/output/config mapping. The leaf LUT INITs are still
different per original LUT, but the mux wiring pattern is the same.

## Concrete Example

Suppose the design contains:

```verilog
$lut #(.WIDTH(32'd6), .LUT(64'h...)) u_lut (
  .A({A5, A4, A3, A2, A1, A0}),
  .Y(Y)
);
```

With:

```python
source_lut_widths=[6]
leaf_lut_width=5
```

the decomposer creates:

```text
u_lut__leaf_lut0 = LUT5(A0..A4), INIT = cofactor A5=0
u_lut__leaf_lut1 = LUT5(A0..A4), INIT = cofactor A5=1
```

Then SAT checks whether the provided mux primitive can implement:

```text
X = S0 ? D1 : D0
```

If the primitive can do that, the final design contains:

```text
leaf0_out = u_lut__leaf_lut0(A0..A4)
leaf1_out = u_lut__leaf_lut1(A0..A4)
Y         = mux(leaf0_out, leaf1_out, A5, config_bits)
```

## Example With `MUX8LUT_frame_config_mux`

The FABulous demo mux has ports:

```verilog
input A, B, C, D, E, F, G, H;
input [3:0] S;
output M_AB, M_AD, M_AH, M_EF;
input [NoConfigBits-1:0] ConfigBits;
```

A suitable pass call is:

```python
self.design_decompose_lut_pass(
    source_lut_widths=[6, 7, 8],
    leaf_lut_width=5,
    mux_verilog_path=Path(
        "/home/hausding/Documents/FABulous/demo0/Tile/LUT4AB/"
        "MUX8LUT_frame_config_mux.v"
    ),
    mux_top_name="MUX8LUT_frame_config_mux",
    mux_data_inputs=["A", "B", "C", "D", "E", "F", "G", "H"],
    mux_select_inputs=["S[0]", "S[1]", "S[2]", "S[3]"],
    mux_outputs=["M_AB", "M_AD", "M_AH", "M_EF"],
    mux_config_prefixes=["ConfigBits"],
)
```

For a LUT6-to-LUT5 decomposition, SAT only needs a 2-to-1 mux shape. For a
LUT8-to-LUT5 decomposition, SAT needs an 8-to-1 mux shape. The same physical
primitive can be used for both if SAT proves that the required shape is
available through some config/output choice.

## Internal Flow

The module follows the same reader/planner/writer structure used by other
fabxplore modules.

1. `reader.py`
   Reads the current `PyosysBridge` design into internal Python models. It
   extracts normal Yosys `$lut` cells, their width, INIT, input bits, and output
   bit.

2. `decomposer.py`
   Selects LUTs whose width is in `source_lut_widths`. For each selected LUT it
   computes cofactors, asks the mux solver for the required mux shape, and
   builds a pure-Python replacement plan.

3. `mux_solver.py`
   Compiles the mux Verilog to BLIF, imports it into `sat_fab.Circuit`, builds
   the abstract mux truth table, and asks `sat_fab.Equiv` to find input routing,
   output routing, and config bits.

4. `writer.py`
   Applies the replacement plan to the live pyosys design. It removes the
   original high-width `$lut`, adds the generated leaf `$lut` cells, adds the
   mux primitive instance, connects the solved routes, and writes config bits.

5. `report.py`
   Produces a Jinja2-rendered summary of the run.

## Interface Options

`source_lut_widths`

: Source `$lut` widths selected for decomposition. Example: `[6, 7, 8]`.

`leaf_lut_width`

: Width of the generated cofactor LUTs. Example: `5` means LUT6 becomes two
  LUT5s, LUT7 becomes four LUT5s, and LUT8 becomes eight LUT5s.

`mux_verilog_path`

: Path to the Verilog module that should be used as the recombination mux.

`mux_top_name`

: Top module name inside `mux_verilog_path`.

`mux_data_inputs`

: Primitive input ports that may receive generated leaf LUT outputs.

`mux_select_inputs`

: Primitive input ports that may receive the high original LUT inputs used as
  mux selects. Scalar ports can be listed directly, for example `"S"`. Bus bits
  can be listed explicitly, for example `"S[0]"`, `"S[1]"`, or by bus base if
  the compiled BLIF exposes indexed names.

`mux_outputs`

: Candidate primitive outputs. SAT may choose one of these as the output that
  recreates the original LUT.

`mux_configs`

: Explicit config input names if they are known exactly.

`mux_config_prefixes`

: Prefixes used to discover config inputs, for example `["ConfigBits"]`.

`mux_dependency_paths`

: Extra Verilog files needed to elaborate the mux module. The solver also tries
  to auto-discover `Fabric/models_pack.v` for FABulous tile modules.

`include_unused_mux_inputs`

: If `True`, unused mux inputs are tied to zero in the generated instance.
  Inputs used by the SAT solution are always connected.

`max_decompositions`

: Optional limit on the number of successful decompositions. This is useful for
  debugging large designs.

`track_progress` and `progress_chunk_size`

: Control progress logging while many LUT candidates are processed.

## Report

The report lists:

- selected source widths,
- leaf LUT width,
- total and candidate LUT counts,
- successful and failed decompositions,
- number of generated leaf LUTs,
- SAT mux solves and cache hits,
- decomposition shapes such as `LUT8 -> 8 x LUT5 + mux`.

This makes it easy to see whether the pass is decomposing the intended cells
and whether the mux-shape cache is doing useful work.
