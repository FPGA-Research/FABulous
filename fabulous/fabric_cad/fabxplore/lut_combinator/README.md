# LUT Combinator

## 1. What Problem This Project Solves

Modern mapped netlists often contain many small LUT cells (`LUT2`, `LUT3`, `LUT4`, ...).
On FPGA-like fabrics with *fracturable* LUT resources, two logical LUTs can sometimes be
implemented inside one physical macro cell. If we detect these opportunities, we reduce
resource count while preserving logic behavior.

`LUT Combinator` automates exactly this transformation:

- input: a LUT-mapped design (typically Verilog, or Yosys JSON)
- process: identify mathematically feasible LUT packings for a paired fractured architecture
- output: a mapped design containing packed `FRAC_*` style cells plus unchanged passthrough LUTs

The focus is LUT-only packing correctness and reproducibility.

---

## 2. Expected Inputs and Typical Workflow

### Input design expectations

The source is expected to be already LUT-mapped (for example from a synthesis flow), with
cell types such as `LUT2`, `LUT3`, `LUT4`, `LUT5`, etc.

The project can start from:

- Verilog netlist (`map_from_verilog(...)`)
- Yosys JSON netlist (`map_from_json(...)`)
- in-memory pyosys design object (`map_from_design(...)`)

### What LUT Combinator does in one run

1. Parse LUT cells from the selected top module.
2. Partition LUTs into:
   - pair candidates (`width <= K`)
   - optional full-LUT passthrough candidates (`width = K+1`)
   - blocked (`width > K+1`)
3. Build feasibility graph for pair candidates.
4. Select disjoint pairs with configurable matching mode.
5. Emit packed cells with correct remapped `INIT` values.
6. Rebuild mapped netlist JSON and (optionally) Verilog text.
7. Report before/after LUT statistics.

---

## 3. Architecture Model

LUT Combinator intentionally uses a **paired fractured architecture** model.
It is generic by parameters, but the structure is fixed and explicit.

### Parameterization

- `frac_lut_size = K`
  - each internal LUT slot has size `K`
- `num_shared_inputs = S`
  - exactly `S` pins are shared between both slots
- private pins per slot: $P = K - S$

### Structural interpretation

The modeled macro has two internal `LUT(K)` functions `L0` and `L1`, and a 2:1 mux:

- $O_0 = \mathrm{mux}(S, L_0, L_1)$
- $O_1 = L_1$

ASCII view:

```text
                   shared inputs
              I0 I1 ... I(S-1)
                |  |       |
                v  v       v
        +--------------------------------------+
 A0..A(P-1) ---> [      LUT slot L0       ] ---+---\
                                                |    \
 B0..B(P-1) ---> [      LUT slot L1       ] ---+-----+--> [ 2:1 MUX ] ---> O0
                                                     /          ^
                                                    /           |
                                      direct path --           S (select input)
                                                  \
                                                   +---------------------------> O1
        +--------------------------------------+
```

Important: this model supports packing two LUTs of **any width up to `K`**
(not only exact `K`/`K`). Smaller LUTs leave some slot pins as don't-care.

---

## 4. What “Fracturable LUT” Means Here

A fracturable LUT macro can operate in two conceptual modes:

1. **Pair mode**: two separate logical LUTs are packed into one macro.
2. **Full-LUT (`K+1`) mode** (optional passthrough): one larger LUT is split into
   two `K`-LUT halves selected by one extra input.

So V3 can model both:

- dual independent logic cones sharing infrastructure
- single larger function decomposed into muxed halves

when `passthrough=True` is enabled for `K+1` LUTs.

---

## 5. Mathematical Feasibility of Pair Packing

Let:

- $A$ be the input-net set of LUT0
- $B$ be the input-net set of LUT1
- $|A| = w_0$, $|B| = w_1$
- architecture parameters are:
  - slot size $K$
  - shared-pin count $S$
  - private pins per side $P = K - S$

A candidate pair must satisfy at least:

- $w_0 \le K$
- $w_1 \le K$

Then we must find a shared-net set $C$ with:

- $|C| = S$
- $|A \setminus C| \le P$
- $|B \setminus C| \le P$

If such a set $C$ exists, the pair is packable.

This is the important point: we are not only asking whether the union of inputs is small
enough. We are asking whether the inputs can actually be assigned onto the physical pin
structure of the architecture.

Another useful way to write the same condition is:

- LUT0 needs at least $w_0 - P$ of its signals to live in the shared region
- LUT1 needs at least $w_1 - P$ of its signals to live in the shared region

So the shared set $C$ must be chosen such that both LUTs can offload enough signals into
the shared pins, while the remainder fits into each side's private pins.

It is also useful to note that this feasibility rule can be written in an equivalent
compact form:

$$
|A \cup B| \le K + P
$$

So the shared/private formulation and the union-size formulation describe the same
mathematical feasibility region for this architecture.

A short proof sketch is useful here.

From

- $|A \setminus C| \le P$
- $|B \setminus C| \le P$

we get

- $|A \cap C| \ge w_0 - P$
- $|B \cap C| \ge w_1 - P$

Now let

$$
z = |A \cap B|
$$

The minimum number of shared-pin positions needed to satisfy both LUTs is then

$$
(w_0 - P) + (w_1 - P) - z
$$

because a signal in $A \cap B$ can satisfy both LUTs with one shared pin.
Therefore feasibility is equivalent to

$$
S \ge (w_0 - P) + (w_1 - P) - z
$$

Using

$$
z = |A \cap B| = w_0 + w_1 - |A \cup B|
$$

we get

$$
S \ge w_0 + w_1 - 2P - (w_0 + w_1 - |A \cup B|)
$$

which simplifies to

$$
S \ge |A \cup B| - 2P
$$

and therefore

$$
|A \cup B| \le S + 2P
$$

Since

$$
K = S + P
$$

we obtain

$$
|A \cup B| \le K + P
$$

So the final equivalence can be written as

$$
\exists C \text{ with } |C| = S,\ |A \setminus C| \le P,\ |B \setminus C| \le P
\iff
|A \cup B| \le K + P
$$

The reason we still prefer the shared/private formulation in this document is that it
matches the physical architecture more directly: it explains *why* a pair fits, not only
*that* it fits.

### Why lower overlap can still be packable

Even if two LUTs do not naturally share many inputs, packing can still work because
smaller LUTs can treat extra shared pins as don't-care. The shared-pin set can include
nets heavily used by one side while unused by the other side.

In other words, the architecture does **not** require that every shared pin corresponds to
a signal used by both LUTs. A shared pin is simply a pin that both internal LUT slots can
see. One slot may use it functionally while the other slot ignores that dimension.

---

## 6. Don’t-Care Assisted Packing (Key Idea)

Assume $K=4$, $S=3$, $P=1$. This is the typical `FRAC_LUT5`-style case:

- two internal `LUT4` slots
- three shared inputs
- one private input per slot
- one select input for the muxed output

Now consider a more interesting example where the two LUTs do **not** share any
inputs at all.

Example logical LUTs:

- LUT0 is `LUT2` with inputs $\{a, b\}$
- LUT1 is `LUT3` with inputs $\{c, d, e\}$

So explicitly:

$$
\{a, b\} \cap \{c, d, e\} = \varnothing
$$

At first this may look impossible, because there is no natural overlap. But in this
architecture, the shared pins do not have to carry only truly shared signals. They are
simply the pins that are visible to both internal `LUT4` slots.

The physical macro has the following input structure:

- shared data pins: `I0`, `I1`, `I2`
- one private pin for the first `LUT4`: `A`
- one private pin for the second `LUT4`: `B`
- one mux select pin: `S`

So each internal `LUT4` sees four data inputs:

- first slot sees `I0`, `I1`, `I2`, `A`
- second slot sees `I0`, `I1`, `I2`, `B`

ASCII architecture view:

```text
Architecture: K = 4, S = 3, P = 1

                 shared to both LUT4 slots
                   I0      I1      I2
                    |       |       |
                    v       v       v
              +---------------------------+
              |        LUT4 slot L0       |----\
         A -->| private pin for slot 0    |     \
              +---------------------------+      +--> O0 through mux
                                                    ^
              +---------------------------+         |
              |        LUT4 slot L1       |----+---+
         B -->| private pin for slot 1    |    |
              +---------------------------+    +-------> O1 direct

         S is the select input of the 2:1 mux on O0
```

Now choose the shared set as:

$$
C = \{a, c, d\}
$$

with:

- `I0 = a`
- `I1 = c`
- `I2 = d`
- `A = b`
- `B = e`

This gives:

- LUT0 (`LUT2`) uses $\{a,b\}$ and ignores $\{c,d\}$
- LUT1 (`LUT3`) uses $\{c,d,e\}$ and ignores $\{a\}$

Now check the private-demand condition:

- $|\{a,b\} \setminus \{a,c,d\}| = |\{b\}| = 1 \le 1$
- $|\{c,d,e\} \setminus \{a,c,d\}| = |\{e\}| = 1 \le 1$

So the pair fits even though the original LUTs had no shared inputs at all.

ASCII packing picture:

```text
Logical LUTs to pack:

  LUT0 = LUT2(a, b)
  LUT1 = LUT3(c, d, e)

No natural overlap:

  {a, b} ∩ {c, d, e} = empty

Physical FRAC_LUT5-style input structure:

  Shared pins:   I0  I1  I2
  Private pins:  A   B
  Mux select:    S

Choose placement:

  I0 = a
  I1 = c
  I2 = d
  A  = b
  B  = e

Internal slot realization:

  L0 slot implements LUT2(a,b)
    uses I0 = a
    uses A  = b
    ignores I1 = c
    ignores I2 = d

  L1 slot implements LUT3(c,d,e)
    uses I1 = c
    uses I2 = d
    uses B  = e
    ignores I0 = a

Outputs:
  O0 = LUT0 output
  O1 = LUT1 output
  S  = 0 in normal pair-packing mode
```

The key observation is this: a signal placed on a shared pin does **not** need to be
functionally used by both LUTs. It only needs to be physically available to both slots.
If one LUT does not depend on that signal, the INIT remapping simply duplicates its truth
table across that dimension.

That is the meaning of don't-care assisted packing in this project.

This is why LUT Combinator can pack combinations like `LUT2 + LUT3` into a `K=4` paired
macro even when they have zero natural overlap.

### Another way to read this example

The architecture exposes three shared data inputs to both slots, but each logical LUT may
use only some of them. A smaller LUT embedded inside a larger slot simply repeats the same
truth-table value across the unused dimensions. The INIT remapping step takes care of that
expansion automatically.

---

## 7. INIT / Truth-Table Mapping Mathematics

Each LUT truth table is represented as an integer `INIT`.

For pair mapping, if source LUT input order differs from slot pin order,
LUT Combinator remaps truth-table indices by permutation.

Let:

- source LUT width be $n$
- slot width be $K$
- $\pi(i)$ be the slot pin index used by source input $i$

For a destination assignment $x \in \{0,1\}^K$, the source LUT only looks at the slot
positions it was wired to. Therefore the source-table index becomes:

$\mathrm{src\_index}(x) = \sum_{i=0}^{n-1} x_{\pi(i)} 2^i$

Then the remapped destination truth-table bit is:

$\mathrm{INIT}_{\mathrm{dst}}(x) = \mathrm{INIT}_{\mathrm{src}}[\mathrm{src\_index}(x)]$

This means the packed slot computes exactly the same Boolean function as the original LUT,
just expressed over the slot's physical input coordinates.

This exactly preserves logic behavior under pin relocation.

### Why don't-cares work in the remap

If the source LUT has width $n < K$, then some slot dimensions are unused. In the formula
above, those unused slot bits never appear in $\mathrm{src\_index}(x)$. As a result,
multiple destination assignments map to the same source-table entry, which is exactly the
correct don't-care behavior.

### Optional `K+1` passthrough split

For one LUT of width $K+1$, LUT Combinator can also split it into two `LUT(K)` halves when
`passthrough=True`.

Let the last source input be the select dimension $s$. Then for each data assignment $t$:

- $\mathrm{INIT}_{L0}[t] = \mathrm{INIT}_{\mathrm{full}}[t, s=0]$
- $\mathrm{INIT}_{L1}[t] = \mathrm{INIT}_{\mathrm{full}}[t, s=1]$

and drives macro select from the LUT's extra input.
So the muxed output reproduces the original $(K+1)$-input LUT exactly:

$O_0 = \begin{cases}
L_0(t) & s = 0 \\\\
L_1(t) & s = 1
\end{cases}$

---

## 8. Pair Selection as Graph Matching

After feasibility checks, LUT Combinator builds a graph:

- node = one pair-candidate LUT with width $\le K$
- edge $(i,j)$ exists iff LUTs $i$ and $j$ are architecture-feasible together
- edge weight is the natural overlap score:
  - $w(i,j) = |A_i \cap A_j|$

Then select disjoint edges via NetworkX:

- `max_weight`: maximum-weight matching with `maxcardinality=True`
- `maximal`: greedy maximal matching (faster, possibly lower quality)

This gives a deterministic, scalable way to choose non-overlapping pairs.

---

## 9. Pyosys Role in the Flow

LUT Combinator uses **pyosys as the canonical netlist bridge**:

- read Verilog into Yosys design
- write/read JSON as normalized interchange format
- emit mapped Verilog from transformed JSON
- allow access to in-memory design for additional Yosys passes

Because pyosys is used, mapped outputs can be forwarded to additional
Yosys `write_*` backends and pass pipelines.

---

## 10. Output Artifacts

From one mapping run, you can retrieve:

- mapped JSON dictionary / text
- mapped Verilog text
- mapping report text with LUT type statistics

Typical statistics include:

- total LUTs before
- packed macro count (`FRAC_LUT*`)
- mapped LUT count
- passthrough LUT count
- post-mapping type distribution

---

## 11. Verification Strategy

Correctness is not assumed from heuristics; it is validated.

### Formal equivalence approach

The formal checker in `tests/equiv_only.py` compares:

- the original mapped Verilog netlist as the **gold** design
- the packed Verilog netlist as the **gate** design

The checker builds a temporary verification design using pyosys and then runs a standard
Yosys equivalence flow. At a high level, the sequence is:

- `read_verilog` for the generated model library
- `read_verilog` for the gold netlist
- `rename` the gold top module to `<top>_gold`
- `read_verilog` for the mapped netlist
- `rename` the mapped top module to `<top>_gate`
- `equiv_make <top>_gold <top>_gate equiv`
- `hierarchy -top equiv`
- `flatten`
- `opt_clean`
- `equiv_struct`
- `equiv_simple -undef`
- `equiv_induct -undef`
- `equiv_simple -undef`
- `equiv_status -assert`

The purpose of the main proof stages is:

- `equiv_make`
  - builds one combined miter-like equivalence design containing `$equiv` cells
- `equiv_struct`
  - proves easy matches structurally when corresponding logic cones already look alike
- `equiv_simple -undef`
  - uses Yosys's combinational equivalence reasoning to prove remaining `$equiv` cells,
    including handling undefined values conservatively
- `equiv_induct -undef`
  - adds a stronger proof step for cases where a more global argument is needed
- `equiv_status -assert`
  - fails the run if any `$equiv` cell remains unproven

In practice, the hard proof work is SAT-style Boolean reasoning inside Yosys's equivalence
engine. So the flow is not just a text or graph comparison of netlists. It is attempting
to prove that corresponding outputs compute the same logic.

### Generated LUT behavioral models

The formal check does not compare raw implementation cells directly. Instead, it generates
behavioral Verilog models for the LUT cell types seen in the design.

For a `LUTn`, the generated model is essentially:

```verilog
module LUT4(I0, I1, I2, I3, O);
  input I0, I1, I2, I3;
  output O;
  parameter [15:0] INIT = 16'b0;
  wire [3:0] _idx = {I3, I2, I1, I0};
  assign O = INIT[_idx];
endmodule
```

This directly captures the semantic meaning of a LUT:

- the inputs form an address
- `INIT` is the truth table
- the output is the addressed truth-table bit

So the proof checks Boolean functionality, not instance naming or netlist syntax.

### Generated FRAC behavioral models

The packed `FRAC_*` cell is also given a behavioral model. That model reflects the exact
macro interpretation used by LUT Combinator:

- pair mode: two internal `LUT(K)` images feeding `O0` and `O1`
- optional full-LUT mode: one original `LUT(K+1)` split into two `K`-LUT halves selected
  by `S`

Conceptually the generated model behaves like:

```verilog
wire _l0 = L0_INIT[idx0];
wire _l1 = L1_INIT[idx1];
assign O0 = S ? _l1 : _l0;
assign O1 = _l1;
```

and, when passthrough/full-LUT decomposition is active, the model also supports the
recombined `K+1` behavior using the split `INIT` images.

### Why non-LUT cells are modeled as passthroughs

Many benchmarks contain cells that are not part of the LUT packing problem:

- flip-flops
- memories
- vendor-specific helper cells
- miscellaneous mapped library cells

For this project we want the formal check to focus on LUT transformation correctness.
So the checker generates very simple placeholder models for non-LUT cell types.

The idea is: preserve connectivity well enough that both designs remain comparable, while
avoiding the need to fully model every unrelated cell library.

A simplified generated passthrough model looks like:

```verilog
module SOME_CELL(A, B, Y);
  input A, B;
  output Y;
  assign Y = A;
endmodule
```

The actual script generates these models automatically from the observed port names and
widths in the design. This is intentionally approximate. It is good for LUT-focused
equivalence experiments, but it is not a universal replacement for full standard-cell or
vendor-library models.

That is why:

- LUT-only benchmarks are the cleanest and strongest tests
- mixed-cell benchmarks are useful, but their proof quality depends on how safely the
  non-LUT placeholder models approximate the real cells

### What a successful proof means

If `equiv_status -assert` succeeds, then within the generated semantic model library the
gold and mapped designs are equivalent at the checked top module outputs.

For LUT-only benchmarks, this is a strong result:

- the original design and packed design compute the same Boolean function
- the INIT remapping is correct
- the chosen pin assignments are functionally correct

For mixed-cell benchmarks, a successful proof still gives useful evidence, but it should
be interpreted together with the modeling assumptions for the non-LUT cells.

### Benchmarks

The test suite includes simple synthetic LUT-only benchmarks and larger
benchmark netlists (for example ENET-style mapped designs) to validate both:

- local truth-table remap correctness
- system-level flow robustness

The recommended progression is:

- start with LUT-only micro-benchmarks
- then use larger LUT-only graphs
- then run mixed benchmarks containing unrelated cells

This makes it easier to separate:

- packing/math bugs
- INIT remap bugs
- equivalence-modeling limitations for non-LUT cells

---

## 12. Practical Interpretation of Shared Inputs

`num_shared_inputs` is an architectural knob, not a strict overlap demand.

- Higher $S$ means fewer private pins because $P = K-S$.
- Lower `S` means more private flexibility.
- Feasibility is determined by whether some shared set $C$ of size $S$ can satisfy
  both private-side constraints, including don't-care possibilities.

So `S` controls architecture shape, while the mapper tries to pack everything
that is mathematically implementable in that shape.

---

## 13. Scope

LUT Combinator deliberately focuses on a strong, clear core:

- paired fractured architecture with configurable `K` and `S`
- optional `K+1` split/mux passthrough
- graph-based selection with two matching modes
- pyosys-backed import/export and formal checking support

It is meant as a reliable base for exploring fracturable LUT packing quality,
correctness, and tradeoffs across architectures and benchmarks.

## 14. Comparison with Xilinx in yosys

In yosys the Xilinx architecture has also a pass that can map
to fracturable LUTs but this is very not optimized.

The ony thing what is done is that they map to say LUT6
and then just converting the LUT6 to fracturable LUT5 by
just splitting the INIT function and adding a mux to the
output in the techmap pass, advaned packing as we do is
not considered also shared inputs and free inputs
cannot be changed.
