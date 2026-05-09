# Morph Tile

Morph tile is a SAT-assisted mapping module for turning ordinary LUT-mapped
logic into instances of a configurable architecture tile.

The name is meant to describe the mental model: before an architecture exposes a
fixed primitive, we can describe a more abstract reconfigurable circuit. That
circuit has data inputs, optional input routing, configuration bits, internal
state, and several possible outputs. A SAT solver then chooses one legal state
of that circuit so the tile morphs into the logic function we want to implement.

In the final netlist, the abstract freedom is gone. The morph tile instance is a
normal Verilog cell with concrete input wires, one selected output, and solved
configuration bits tied to constants.

You can think of the Verilog tile model as the highest-entropy description of a
future primitive. It intentionally keeps many choices alive: which tile inputs
come from which logical inputs, which config bits are set, which output is used,
and sometimes which internal state is exposed as an observable output. The SAT
result collapses that high-entropy model into one concrete architectural state.

## Mental Model

A normal primitive says:

```text
this cell implements this fixed behavior
```

A morph tile says:

```text
this configurable circuit can implement many behaviors;
find the state that implements this one LUT function
```

For example, a tile might expose:

- data inputs: `I0`, `I1`, `I2`, `A0`, `B0`, `S`, `Ci`
- configuration bits: `ConfigBits[0]`, `ConfigBits[1]`, ...
- outputs: `O0`, `O1`, `Co`

The mapper tries to replace a LUT:

```verilog
$lut #(
  .WIDTH(2),
  .LUT(4'h8)
) u_and (
  .A({ b, a }),
  .Y(y)
);
```

with a configured tile instance:

```verilog
FLUT5_1P_2PS u_and__morph_tile (
  .I0(a),
  .I1(b),
  .I2(1'b0),
  .A0(1'b0),
  .B0(1'b0),
  .S(1'b0),
  .Ci(1'b0),
  .ConfigBits(32'b...),
  .O0(y)
);
```

The exact port mapping and config values are not guessed. They are solved.

## Mathematical View

Let the morph tile be a configurable Boolean circuit

$T : \{0,1\}^x \times \{0,1\}^c \rightarrow \{0,1\}^z$

where:

- $x$ is the number of tile data inputs
- $c$ is the number of configuration bits
- $z$ is the number of candidate outputs

For a selected output $j$, the tile computes:

$T_j(i, q)$

where $i \in \{0,1\}^x$ is the data-input vector and
$q \in \{0,1\}^c$ is the config vector.

A LUT with width $k$ defines one Boolean function:

$f : \{0,1\}^k \rightarrow \{0,1\}$

encoded by its INIT value. The solver asks whether there exists:

- an input route $\rho$
- an output route $j$
- a config vector $q$

such that:

$\forall a \in \{0,1\}^k : T_j(\rho(a), q) = f(a)$

The route $\rho$ maps tile inputs to logical LUT inputs such as `A0`, `A1`,
constants, or reused inputs, depending on the pass options.

So the problem is not only "can the circuit compute this truth table?" It is:

$\exists \rho, j, q \;.\; \forall a : T_j(\rho(a), q) = f(a)$

That is why this is a natural fit for SAT-based equivalence.

## Entropy

A LUT is flexible, but for this problem it has low entropy. Once the INIT is
known, it represents one function. A LUT does not contain many independent
internal states that can be exposed in different ways.

A morph tile can have much higher entropy. It may contain:

- many config bits
- several usable outputs
- internal muxing
- carry behavior
- arithmetic behavior
- pass-through behavior
- input permutation freedom

It may also expose intermediate architecture states as outputs. That is useful
for exploration because the same configurable circuit can be tested as many
possible primitives before the final primitive boundary is fixed.

Very roughly, the number of possible observable behaviors is bounded by:

$|F_T| \le z \cdot 2^c \cdot R(x,k)$

where $R(x,k)$ is the number of legal input routes from tile inputs to LUT
inputs. If reuse is allowed and constants are not allowed, a simple upper bound
is:

$R(x,k) = k^x$

If constants are also allowed, the route space grows to:

$R(x,k) = (k + 2)^x$

This high entropy is useful because one tile description can represent many
architecture states. But it also makes SAT harder, because the solver has more
routes, outputs, and config states to search.

That is the tradeoff:

```text
more morph freedom -> more architecture coverage -> harder SAT problem
```

## Small Example

Consider this tiny configurable tile:

```verilog
module morph2 (
  input  I0,
  input  I1,
  input  C,
  output O0,
  output O1
);
  assign O0 = C ? (I0 ^ I1) : (I0 & I1);
  assign O1 = I0 | I1;
endmodule
```

This tile has one config bit and two outputs:

$T_0(I0,I1,C) = C ? (I0 \oplus I1) : (I0 \land I1)$

$T_1(I0,I1,C) = I0 \lor I1$

To implement `AND`, with INIT `4'h8`, the solver can choose:

$C = 0,\; j = 0,\; I0 \leftarrow A0,\; I1 \leftarrow A1$

To implement `XOR`, with INIT `4'h6`, it can choose:

$C = 1,\; j = 0,\; I0 \leftarrow A0,\; I1 \leftarrow A1$

To implement `OR`, with INIT `4'he`, it can choose:

$j = 1,\; I0 \leftarrow A0,\; I1 \leftarrow A1$

If the original LUT pins are swapped, the tile does not need to change. The
input route changes:

$I0 \leftarrow A1,\; I1 \leftarrow A0$

## Cut Solver

`CutSolver` answers one question:

```text
Can this Verilog tile implement this LUT INIT?
```

Internally it builds two SAT-fab circuits.

The first circuit is the specification:

```python
Circuit.fast_lut(
    name="cut_spec",
    init=init,
    inputs=["A0", "A1", ..., "A{k-1}"],
    output="X",
)
```

This circuit is exactly the LUT function we want.

The second circuit is the candidate tile. It is built once when the solver is
created:

```text
Verilog tile
  -> pyosys prep
  -> aigmap
  -> synth -top <tile_top> -flatten
  -> BLIF
  -> Circuit.from_blif(...)
```

Building the tile circuit once matters. The mapper calls `solve_lut` many times,
but the tile Verilog does not change between calls.

Then the solver creates an equivalence query:

```python
Equiv.check(spec, candidate)
    .route_inputs(...)
    .route_outputs(...)
    .solve()
```

If the result is SAT, the returned `CutSolveResult` contains:

- whether the solve was SAT
- tile input to LUT input mapping
- LUT output to tile output mapping
- solved config bit values
- the raw SAT-fab result for deeper inspection

## CEGIS View

SAT-fab uses a counterexample-guided style of equivalence solving. Conceptually,
the solver searches for a candidate tuple:

$(\rho, j, q)$

Then it checks whether that tuple is correct for all input assignments:

$\forall a \in \{0,1\}^k$

If some assignment $a^\*$ disagrees, that counterexample refines the search. The
process repeats until either a valid tuple is found or the solver proves that no
tuple exists.

This is important for high-entropy tiles. Instead of eagerly expanding every
truth table possibility of the tile, the solver only adds the constraints needed
to separate wrong states from correct states.

## Canonical Cache

Many LUT INIT values describe the same function up to input permutation. For
example, these two LUT2 functions are equivalent if the inputs are swapped:

$f(A0,A1) = A0 \land \lnot A1$

$g(A0,A1) = A1 \land \lnot A0$

Their raw INIT values differ, but the SAT problem is essentially the same. If
the tile can implement one, it can implement the other by remapping inputs.

The canonical cache normalizes each INIT by trying all input permutations and
choosing the smallest resulting INIT:

$canon(f) = \min_{\pi \in S_k} INIT(f_\pi)$

with:

$f_\pi(a_0,\ldots,a_{k-1}) = f(a_{\pi(0)},\ldots,a_{\pi(k-1)})$

The cache key is:

$(k, canon(f))$

When a cached result is reused, the input mapping is remapped back through the
stored permutation. So if the canonical solve said:

```text
I0 <- A0
I1 <- A1
```

and the original LUT was canonicalized by swapping pins, the final mapping can
become:

```text
I0 <- A1
I1 <- A0
```

This keeps the mapper clean: it still asks for one LUT replacement at a time,
but repeated equivalent INITs avoid repeated SAT calls.

The number of permutations is $k!$, so canonicalization is intentionally capped:

```python
canonical_cache_max_width=6
```

Some useful sizes are:

```text
LUT4:  4! = 24 permutations
LUT5:  5! = 120 permutations
LUT6:  6! = 720 permutations
LUT7:  7! = 5040 permutations
```

For larger LUT widths, the factorial cost can become more expensive than the
cache benefit. The pass therefore lets the user keep canonical caching enabled
for normal LUT sizes and disable it above a chosen width.

## Module Flow

The morph tile module is split into small pieces so the SAT logic, Yosys design
access, and report generation do not depend on each other too tightly.

`core/reader.py`
: Reads the current pyosys design into internal morph-tile objects. Today this
uses `PyosysBridge.to_py_object()`, which still goes through JSON internally.
That is fine for now because the JSON dependency is isolated in the reader.

`core/models.py`
: Defines the typed objects shared by the flow: LUT cells, replacements, stats,
results, and cut-solver output.

`core/cut_solver.py`
: Converts the user-provided tile Verilog into a SAT-fab candidate circuit and
solves individual LUT INIT functions against it.

`core/canonical.py`
: Builds canonical LUT cache keys under input permutation and remaps cached SAT
solutions back to the original LUT pin order.

`core/mapper.py`
: Orchestrates the mapping. It reads LUTs, filters widths, applies replacement
limits, checks the cache, calls the cut solver, collects replacements, and asks
the writer to update the live design.

`core/writer.py`
: Applies successful replacements to the live pyosys `ys.Design`. It removes the
original `$lut` and instantiates the morph tile with solved routes and config
bits.

`core/process_tracker.py`
: Emits progress messages for long runs without cluttering the mapper logic.

`core/report.py`
: Generates a compact human-readable report with candidate counts, replacement
rates, failures, cache hits, and common mapped INIT functions.

`pyosys/custom_passes/morph_tile_pass.py`
: Wraps the mapper as a custom pass.

`pyosys/synthesizer.py`
: Exposes the pass through `design_morph_tile_pass(...)`.

## Synthesizer Interface

A typical call looks like this:

```python
self.design_morph_tile_pass(
    tile_verilog_path=Path("demo0/Tile/test_tile/FLUT5_1P_2PS.v"),
    tile_top_name="FLUT5_1P_2PS",
    tile_inputs=["I0", "I1", "I2", "A0", "B0", "S", "Ci"],
    tile_outputs=["O0", "O1", "Co"],
    considered_lut_widths=[6],
    tile_config_prefixes=["ConfigBits"],
    max_replacements=20,
    use_canonical_cache=True,
    canonical_cache_max_width=6,
    progress_chunk_size=5,
)
```

Important options:

- `tile_verilog_path`: Verilog model of the configurable tile.
- `tile_top_name`: top module inside the tile Verilog.
- `tile_inputs`: tile input ports that may be routed from LUT inputs.
- `tile_outputs`: tile output ports that may implement the LUT output.
- `tile_configs`: explicit config ports, if they should be named directly.
- `tile_config_prefixes`: prefixes used to discover config ports, such as
  `ConfigBits`.
- `considered_lut_widths`: LUT widths that should be tested.
- `include_unused_inputs`: whether the writer should connect unused tile inputs
  instead of leaving them unconnected.
- `max_replacements`: optional cap for testing or partial morphing.
- `map_luts_first`: optionally LUT-map the design before morphing.
- `use_canonical_cache`: reuse SAT solves across input-permutation-equivalent
  INIT functions.
- `canonical_cache_max_width`: largest LUT width where canonicalization is used.
- `track_progress`: enable progress logging.
- `progress_chunk_size`: print progress every N processed candidates.

## Replacement Example

Assume the design contains a LUT6:

```verilog
$lut #(
  .WIDTH(6),
  .LUT(64'h6996966996696996)
) u0 (
  .A({ a5, a4, a3, a2, a1, a0 }),
  .Y(y)
);
```

The mapper builds:

$f : \{0,1\}^6 \rightarrow \{0,1\}$

from that INIT. Then it asks whether the tile can implement $f$. If SAT finds:

```text
I0 <- A0
I1 <- A1
I2 <- A2
A0 <- A3
B0 <- A4
S  <- A5
Ci <- A0
X  <- O1
ConfigBits[0] = 1
ConfigBits[1] = 0
...
```

the writer replaces `u0` with a tile instance:

```verilog
FLUT5_1P_2PS u0__morph_tile (
  .I0(a0),
  .I1(a1),
  .I2(a2),
  .A0(a3),
  .B0(a4),
  .S(a5),
  .Ci(a0),
  .ConfigBits(...),
  .O1(y)
);
```

The original LUT behavior is preserved because the SAT result proved:

$\forall a \in \{0,1\}^6 : T_{O1}(\rho(a), q) = f(a)$

## Why This Is Useful

Morph tile lets us explore whether an architecture tile can absorb logic that
was originally represented as LUTs. This is useful before committing to a fixed
primitive definition, because the tile can expose more behavior than a normal
mapped cell.

It can answer questions like:

- Can this architecture tile implement every LUT6 in this design?
- Which LUT INIT functions fail?
- Which config states are needed most often?
- How often can a carry or fracturable tile replace general LUT logic?
- How much solver work is saved by canonical input-permutation caching?

The report is intentionally summarized instead of listing every replacement. It
focuses on replacement rate, failure count, cache behavior, and the most common
INIT functions that were successfully mapped.

## Limitations

The current mapper replaces one LUT with one morph tile instance. The SAT-fab
cut solver can express richer routing ideas, but the pass currently targets
single-output LUT cuts.

Canonical caching only considers input permutation. It does not yet canonicalize
under input inversion or output inversion, so it is not a full NPN cache.

High-entropy tile descriptions can still be expensive. More config bits, more
outputs, and more legal input routes increase the SAT search space. Use
`considered_lut_widths`, `max_replacements`, progress logging, and
`canonical_cache_max_width` to keep experiments controlled.

The reader currently uses the existing pyosys-to-Python object conversion. Since
that dependency is isolated in `reader.py`, the module can later move to a more
direct design-object reader without changing the mapper, solver, or writer.
