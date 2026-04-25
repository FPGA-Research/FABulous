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

---

## 15. Select-as-Data Pair Mode

The newest architecture option is:

```python
use_select_as_data_in_pair_mode=True
```

This option only changes **dual pair mode**. It does not change full
`LUT(K+1)` mode, because full mode still needs `S` as the final mux select.

### Motivation

In normal pair mode the mux select input `S` is fixed to `0`, because the two
packed LUTs are independent:

- `O0 = L0`
- `O1 = L1`

So in normal dual mode, `S` is not used as a data input. The select-as-data
mode uses this fact to recover one more effective data input without adding a
new external pin.

The idea is:

- cut one nominal shared input from one internal LUT side
- keep that cut shared pin as a private input for the other side
- route `S` as the matching private input for the first side
- keep the final output mux configured to select `L0`

So the physical pin count stays the same, but pair feasibility behaves as if
the architecture had one fewer shared input and one more private input per
internal LUT.

### Effective architecture

Let the nominal architecture be:

- internal LUT size: $K$
- nominal shared inputs: $S_n$
- nominal private inputs per side:

$$
P_n = K - S_n
$$

When select-as-data is enabled for pair mode:

$$
S_e = S_n - 1
$$

and therefore:

$$
P_e = K - S_e = K - (S_n - 1) = P_n + 1
$$

So the mapper treats pair packing as:

- effective shared inputs: $S_e$
- effective private inputs per side: $P_e$

This is exactly the same feasibility region as explicitly lowering
`num_shared_inputs` by one, except that no extra package pin is needed because
the otherwise-unused `S` pin supplies the extra data input on one side.

The feasibility condition from section 5 becomes:

$$
\exists C,\ |C| = S_e,\ |A \setminus C| \le P_e,\ |B \setminus C| \le P_e
$$

or equivalently:

$$
|A \cup B| \le K + P_e
$$

Compared with the nominal pair mode, this allows one more effective private
input per side.

### Concrete `K=4`, `S_n=3` example

Normal pair mode has:

```text
L0(I0, I1, I2, A0)
L1(I0, I1, I2, B0)
S = 0, so O0 = L0
O1 = L1
```

Here:

$$
P_n = 4 - 3 = 1
$$

With select-as-data enabled:

$$
S_e = 3 - 1 = 2
$$

and:

$$
P_e = 4 - 2 = 2
$$

The effective internal pair mode becomes:

```text
L0(I0, I1, A0, S)
L1(I0, I1, B0, I2)
```

The nominal shared pin `I2` is cut from `L0`. It remains externally available,
but it is now used as the second private input of `L1`. The external `S` pin is
used as the second private input of `L0`.

So this logical situation:

```text
LUT4_0(I0, I1, I2, A0)
LUT4_1(I0, I1, I2, B0)
```

can be interpreted in select-as-data mode as:

```text
LUT4_0(I0, I1, S,  A0)
LUT4_1(I0, I1, I2, B0)
```

or, if we rename the cut side's `I2` usage as a private input:

```text
LUT4_0(I0, I1, A1, A0)   where A1 is physically driven by S
LUT4_1(I0, I1, B1, B0)   where B1 is physically driven by I2
```

Mathematically, this is the same as a `K=4`, `S=2` pair-mode architecture,
but implemented with the original `K=4`, `S_n=3` external pin interface.

### Internal mux sketch

The intended hardware interpretation is that there are small configuration
muxes inside the primitive. In normal pair mode, all nominal shared pins go to
both LUT halves and `S` is the output mux select. In select-as-data pair mode,
one shared connection is broken on the `L0` side and `S` is routed into that
data position instead.

For `K=4`, `S_n=3`:

```text
Normal pair mode
----------------

             I0 --------+----------------> L0 input 0
                        |
                        +----------------> L1 input 0

             I1 --------+----------------> L0 input 1
                        |
                        +----------------> L1 input 1

             I2 --------+----------------> L0 input 2
                        |
                        +----------------> L1 input 2

             A0 -------------------------> L0 input 3
             B0 -------------------------> L1 input 3

             L0 ------------------+
                                   +---- output mux ----> O0
             L1 ------------------+          ^
                                             |
                                             S = 0 in dual mode

             O1 = L1
```

```text
Select-as-data pair mode
------------------------

             I0 --------+----------------> L0 input 0
                        |
                        +----------------> L1 input 0

             I1 --------+----------------> L0 input 1
                        |
                        +----------------> L1 input 1

             A0 -------------------------> L0 input 2
             B0 -------------------------> L1 input 2

             S  ---- cfg mux ------------> L0 input 3
                      ^
                      |
                      +-- select S-as-data instead of I2

             I2 ---- cfg mux ------------> L1 input 3
                      ^
                      |
                      +-- keep cut shared pin as L1 private input

             L0 ------------------+
                                   +---- output mux ----> O0
             L1 ------------------+          ^
                                             |
                                      MUX_SELECT_CONFIG = 0

             O1 = L1
```

A more pin-order-accurate view of the select-as-data `K=4`, `S_n=3` model is:

```text
L0 slot index bits, low to high:
  I0, I1, A0, S

L1 slot index bits, low to high:
  I0, I1, B0, I2
```

The final output mux is not selected by the external `S` signal in this mode.
Instead the emitted parameter `MUX_SELECT_CONFIG` is fixed to `0`, so:

```text
O0 = L0
O1 = L1
```

This is why `S` can safely become data for `L0`.

### INIT remapping with select-as-data

The INIT calculation itself does not need a special truth-table algorithm.
The existing `remap_init_to_slot(...)` operation is enough, because the mode is
represented as a different source-to-slot pin assignment.

For any logical source LUT of width $n$, the source input order is preserved.
Let:

- $x \in \{0,1\}^K$ be one assignment of the internal slot pins
- $\pi(i)$ be the internal slot pin used by source input $i$

Then:

$$
\mathrm{src\_index}(x) =
\sum_{i=0}^{n-1} x_{\pi(i)} 2^i
$$

and:

$$
\mathrm{INIT}_{dst}(x) =
\mathrm{INIT}_{src}[\mathrm{src\_index}(x)]
$$

In normal `K=4`, `S_n=3` pair mode, the internal index bits are:

```text
L0: I0, I1, I2, A0
L1: I0, I1, I2, B0
```

With select-as-data enabled, the internal index bits become:

```text
L0: I0, I1, A0, S
L1: I0, I1, B0, I2
```

So the same remap formula produces different `L0_INIT` and `L1_INIT` images
because the physical coordinate system changed.

This is also why smaller LUTs still work correctly. If a logical LUT does not
use one of these internal slot dimensions, that bit never appears in
$\mathrm{src\_index}(x)$, so the destination INIT is automatically duplicated
over that don't-care dimension.

### Emitted parameters and metadata

Packed cells always emit the same stable parameter set. Select-as-data is
communicated through parameter values and metadata, not by changing the shape
of the emitted cell.

Important parameters are:

- `SELECT_AS_DATA_CAPABLE`
  - `1` when the architecture was built with
    `use_select_as_data_in_pair_mode=True`
- `SELECT_AS_DATA_USED`
  - `1` for dual pair cells that actually use this mode
  - `0` for single/full mapped cells
- `EFFECTIVE_SHARED_INPUTS`
  - equals `S_n - 1` when select-as-data is enabled
- `CUT_SHARED_INDEX`
  - normally `-1`
  - equals `S_n - 1` when the last nominal shared input is cut
- `MUX_SELECT_CONFIG`
  - fixed to `0` for the current select-as-data pair implementation
  - this makes `O0` select `L0` while external `S` is used as data

The metadata string also records values such as:

```text
lut_mapping=dual_select_as_data
select_as_data_capable=1
select_as_data_used=1
nominal_shared_inputs=3
effective_shared_inputs=2
cut_shared_index=2
s_data_side=L0
cut_shared_side=L1
mux_select_config=0
```

### Full LUT mode is unchanged

For a single `LUT(K+1)`, the implementation still splits the truth table by
the extra select input:

$$
\mathrm{INIT}_{L0}[t] = \mathrm{INIT}_{full}[t, s=0]
$$

$$
\mathrm{INIT}_{L1}[t] = \mathrm{INIT}_{full}[t, s=1]
$$

and:

```text
O0 = S ? L1 : L0
```

So select-as-data is deliberately not used there. The `S` pin is already
semantically required to reconstruct the original `K+1` input LUT.
