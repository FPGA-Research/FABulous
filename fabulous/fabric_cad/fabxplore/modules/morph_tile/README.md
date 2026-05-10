# Morph Tile

Morph tile is a SAT-assisted mapping module for turning ordinary LUT-mapped
logic into instances of a configurable architecture tile.

The name is meant to describe the mental model: before an architecture exposes a
fixed primitive, we can describe a more abstract reconfigurable circuit. That
circuit has data inputs, optional input routing, configuration bits, internal
state, and several possible outputs. A SAT solver then chooses one legal state
of that circuit so the tile morphs into the logic function we want to implement.

In the final netlist, the abstract freedom is gone. The morph tile instance is a
normal Verilog cell with concrete input wires, selected output wires, and solved
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

## Permutation Cache

Many truth-table specs describe the same function up to input permutation. For
example, these two LUT2 functions are equivalent if the inputs are swapped:

$f(A0,A1) = A0 \land \lnot A1$

$g(A0,A1) = A1 \land \lnot A0$

Their raw INIT values differ, but the SAT problem is essentially the same. If
the tile can implement one, it can implement the other by remapping inputs.

The permutation cache normalizes each output truth table by trying all input
permutations and choosing the smallest resulting tuple of output INITs:

$canon(F) = \min_{\pi \in S_k}
  (INIT(f_{0,\pi}), INIT(f_{1,\pi}), \ldots, INIT(f_{m-1,\pi}))$

with:

$f_\pi(a_0,\ldots,a_{k-1}) = f(a_{\pi(0)},\ldots,a_{\pi(k-1)})$

The cache key is:

$(k, (o_0,\ldots,o_{m-1}), canon(F))$

This works for ordinary LUTs:

```python
{"Y": init}
```

and for multi-output cuts such as FRAC-LUTs:

```python
{"O0": init0, "O1": init1}
```

When a cached result is reused, the input mapping is remapped back through the
stored permutation. So if the cached solve said:

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

This keeps the mapper clean: it still asks for one replacement at a time, but
repeated equivalent truth-table specs avoid repeated SAT calls.

The number of permutations is $k!$. That is still much cheaper than a SAT solve
for the common LUT sizes used here, and the cache can be disabled per circuit
adapter when needed:

```python
circuit_options={"lut": {"enable_permute_cache": False}}
```

Some useful sizes are:

```text
LUT4:  4! = 24 permutations
LUT5:  5! = 120 permutations
LUT6:  6! = 720 permutations
LUT7:  7! = 5040 permutations
```

For larger future cut types, the factorial cost can become more expensive than
the cache benefit. The pass therefore lets each circuit adapter choose whether
to use the shared permutation cache.

## P, NP, and NPN Transformations

The cache currently uses only **P-equivalence**, where `P` means input
permutation. Two functions are P-equivalent when one can be obtained from the
other only by reordering inputs:

$g(a_0,\ldots,a_{k-1}) = f(a_{\pi(0)},\ldots,a_{\pi(k-1)})$

for some permutation $\pi \in S_k$.

Logic synthesis often also uses larger equivalence classes:

- `P`: input permutation
- `NP`: input negation plus input permutation
- `NPN`: output negation plus input negation plus input permutation

For a single-output LUT with $k$ inputs, the maximum number of raw forms in one
equivalence class is:

```text
P:     k!
NP:    2^k * k!
NPN:   2 * 2^k * k!
```

For a LUT6 this becomes:

```text
P:       6!           =     720 forms
NP:      2^6 * 6!     =  46,080 forms
NPN:     2 * 2^6 * 6! =  92,160 forms
```

In the best case, one SAT solve can serve every raw INIT inside the same class.
So for a LUT6, P-caching can avoid up to 719 repeated solves for input-reordered
versions of the same function. Full NPN caching could theoretically avoid up to
92,159 repeated solves for functions related by input inversion, output
inversion, and permutation.

A concrete LUT2 example:

$f(A0,A1) = A0 \land A1$

Under P, swapping inputs gives the same function:

$f(A1,A0) = A1 \land A0$

Under NP, input inversion also belongs to the same class:

$f(\lnot A0,A1) = \lnot A0 \land A1$

Under NPN, output inversion is also included:

$\lnot f(A0,A1) = \lnot(A0 \land A1)$

That larger NPN class is powerful, but morph-tile replacement has an important
architecture constraint: after SAT, the final netlist should contain only the
chosen tile primitive and direct wires/constants. If a cached NPN solution used
an inverted logical input, the replacement would need either:

- an available inverted-input route inside the morph tile, or
- an extra inverter outside the tile

The second option is not acceptable for this pass because it would add logic
outside the primitive being tested. The first option depends on the tile model:
some morph tiles may be able to absorb input inversion through config bits or
internal muxing, while others cannot.

That is why the current implementation deliberately uses only P-equivalence.
P-equivalence is always safe for our replacement model because it only changes
which original input wire is connected to which tile input. No extra logic is
needed and no assumption is made about whether the tile can behave like a LUT
with freely invertible inputs.

Full NP or NPN caching could be added later, but it should be guarded by a proof
or tile capability check. For example, a future adapter could first prove that
the target tile can realize all needed input/output inversions internally, then
upgrade that adapter from P to NPN cache keys. Until then, P gives a useful
speedup while preserving exact primitive-only replacement semantics.

## Module Flow

The morph tile module is split into small pieces so the SAT logic, Yosys design
access, and report generation do not depend on each other too tightly.

`core/reader.py`
: Reads the current pyosys design into internal morph-tile objects. Today this
uses `PyosysBridge.to_py_object()`, which still goes through JSON internally.
That is fine for now because the JSON dependency is isolated in the reader.

`core/models.py`
: Defines the typed objects shared by the flow: generic netlist cells,
replacements, stats, results, and cut-solver output.

`core/cut_solver.py`
: Converts the user-provided tile Verilog into a SAT-fab candidate circuit and
solves specification circuits against it.

`core/permute_cache.py`
: Builds single-output and multi-output cache keys under input permutation and
remaps cached SAT solutions back to the original input order.

`core/mapper.py`
: Orchestrates the mapping. It reads generic cells, asks registered circuit
adapters for candidates, applies replacement limits, checks adapter-local
caches, calls the cut solver, collects replacements, and asks the writer to
update the live design.

`core/writer.py`
: Applies successful replacements to the live pyosys `ys.Design`. It removes the
original source cell and instantiates the morph tile with solved routes and
config bits.

`core/base.py` and `core/registry.py`
: Define the generic circuit-adapter interface and instantiate enabled
adapters. A new cut kind should normally be added as one file in `circuits/` and
one registry entry.

`circuits/lut.py`
: Adapter for ordinary `$lut` cells. This is the classic one-output LUT path and
can use the shared permutation cache.

`circuits/frac_lut.py`
: Adapter for LUT-combinator `__frac_lut` cells. It reconstructs the fixed
multi-output behavior from `L0_INIT`, `L1_INIT`, `LUT_SIZE`,
`NUM_SHARED_INPUTS`, and select-as-data parameters, then solves that
multi-output specification against the morph tile.

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
    enabled_circuits=["lut"],
    tile_config_prefixes=["ConfigBits"],
    circuit_options={
        "lut": {
            "widths": [6],
            "enable_permute_cache": True,
        },
    },
    max_replacements=20,
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
- `enabled_circuits`: registered source-cell adapters to run. Today this can
  include `lut` and `frac_lut`.
- `circuit_options`: adapter-specific options keyed by circuit name. For
  `frac_lut`, useful keys are `modes`, `cell_types`, and
  `enable_permute_cache`. For `lut`, useful keys are `widths` and
  `enable_permute_cache`.
- `include_unused_inputs`: whether the writer should connect unused tile inputs
  instead of leaving them unconnected.
- `max_replacements`: optional cap for testing or partial morphing.
- `map_luts_first`: optionally LUT-map the design before morphing.
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

## Fractional LUT Cuts

When the LUT combinator has already packed a design into `__frac_lut` cells, a
single source cell may expose two related outputs:

```verilog
__frac_lut #(
  .L0_INIT(16'h8caf),
  .L1_INIT(16'hf000),
  .LUT_SIZE("4"),
  .NUM_SHARED_INPUTS("3"),
  .META_DATA("lut_mapping=dual_select_as_data;..."),
  .SELECT_AS_DATA_USED(1'b1),
  .MUX_SELECT_CONFIG(1'b0)
) u_frac (
  .I0(i0),
  .I1(i1),
  .I2(i2),
  .A0(a0),
  .B0(b0),
  .S(s),
  .O0(y0),
  .O1(y1)
);
```

The `frac_lut` adapter treats this as one multi-output cut, not as two unrelated
LUTs. It rebuilds a specification circuit:

$F : \{0,1\}^k \rightarrow \{0,1\}^m$

where $m$ is the number of connected FRAC outputs. For normal dual mode:

$L_0 = LUT(L0\_INIT, I, A)$

$L_1 = LUT(L1\_INIT, I, B)$

$O_0 = S ? L_1 : L_0$

$O_1 = L_1$

For `dual_select_as_data`, the select pin is consumed as a data input on the L0
side and the final output mux is fixed by `MUX_SELECT_CONFIG`, matching the
LUT-combinator behavioral model. Then the solver asks whether the morph tile can
implement all connected outputs of that FRAC cut at once.

To enable this path:

```python
self.design_morph_tile_pass(
    tile_verilog_path=Path("tile.v"),
    tile_top_name="my_tile",
    tile_inputs=["I0", "I1", "I2", "A0", "B0", "S"],
    tile_outputs=["O0", "O1"],
    enabled_circuits=["frac_lut"],
    circuit_options={
        "frac_lut": {
            "modes": ["dual", "dual_select_as_data"],
            "cell_types": ["__frac_lut"],
        },
    },
)
```

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
- How much solver work is saved by input-permutation caching?

The report is intentionally summarized instead of listing every replacement. It
focuses on replacement rate, failure count, cache behavior, and the most common
INIT functions that were successfully mapped.

## Limitations

The current mapper replaces one source cut with one morph tile instance. The
`lut` adapter covers normal single-output `$lut` cells, and the `frac_lut`
adapter covers multi-output LUT-combinator `__frac_lut` cells. Larger composed
cuts are still future work.

Permutation caching only considers input permutation. It does not yet canonicalize
under input inversion or output inversion, so it is not a full NPN cache.

High-entropy tile descriptions can still be expensive. More config bits, more
outputs, and more legal input routes increase the SAT search space. Use
adapter width filters such as `lut.widths`, `max_replacements`, progress
logging, and adapter cache options such as `lut.enable_permute_cache` to keep
experiments controlled.

The reader currently uses the existing pyosys-to-Python object conversion. Since
that dependency is isolated in `reader.py`, the module can later move to a more
direct design-object reader without changing the mapper, solver, or writer.

## Adding A Custom Circuit Adapter

Morph tile is designed so new source-cell kinds do not require changes to the
mapper or writer. A circuit adapter describes one kind of cut:

```text
source netlist cell -> candidate object -> truth-table/spec solve -> replacement
```

The core loop stays generic:

1. The reader extracts generic netlist cells.
2. Each enabled adapter yields candidates it understands.
3. The adapter solves one candidate using the shared `CutSolver`.
4. The adapter returns a generic `MorphTileReplacement`.
5. The writer applies that replacement.

For a new adapter, add one file under `modules/morph_tile/circuits/`, then add a
registry entry in `core/registry.py`.

Here is a minimal sketch for a one-output custom cell called `MY_AND2`:

```python
# modules/morph_tile/circuits/my_and2.py

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.base import (
    MorphCircuitAdapter,
    MorphCircuitEnvironment,
    MorphCircuitKind,
    MorphSolveOutcome,
    MorphTileContext,
)
from fabulous.fabric_cad.fabxplore.modules.morph_tile.core.models import (
    CutSolveResult,
    MorphTileNetlistCell,
    MorphTileReplacement,
)


class MyAnd2Options(BaseModel):
    model_config = ConfigDict(frozen=True)

    enable_permute_cache: bool = True


@dataclass(frozen=True)
class MyAnd2Candidate:
    cell_id: str


class MyAnd2Circuit(MorphCircuitAdapter[MyAnd2Candidate]):
    kind = MorphCircuitKind.MY_AND2

    def __init__(self, env: MorphCircuitEnvironment, options: MyAnd2Options) -> None:
        super().__init__(env)
        self.options = options

    def filter_summary(self) -> dict[str, list[str]]:
        return {
            "my_and2.enable_permute_cache": [
                str(self.options.enable_permute_cache)
            ]
        }

    def iter_candidates(self, context: MorphTileContext):
        for cell in context.design.cells:
            if cell.cell_type == "MY_AND2":
                yield MyAnd2Candidate(cell_id=cell.cell_id)

    def is_enabled_candidate(self, candidate: MyAnd2Candidate) -> bool:
        return True

    def solve(self, candidate: MyAnd2Candidate) -> MorphSolveOutcome:
        return self.solve_truth_table_cached(
            name="my_and2_spec",
            input_names=["A0", "A1"],
            output_inits={"Y": 0x8},  # A0 & A1
            enable_permute_cache=self.options.enable_permute_cache,
        )

    def make_replacement(
        self,
        candidate: MyAnd2Candidate,
        result: CutSolveResult,
    ) -> MorphTileReplacement:
        return self.replacement(
            original_cell_id=candidate.cell_id,
            width=2,
            init=0x8,
            result=result,
            input_ports={
                tile_input: self.src_port(source, 0)
                for tile_input, source in result.input_mapping.items()
            },
            output_ports={
                tile_output: self.src_port("Y", 0)
                for tile_output in result.output_mapping.values()
            },
        )

    def width_label(self, candidate: MyAnd2Candidate) -> str:
        return "MY_AND2"

    def init_label(self, candidate: MyAnd2Candidate) -> str:
        return "MY_AND2:AND"
```

In real adapters, `iter_candidates` usually parses the source cell connections
and stores enough information in the candidate so `make_replacement` can wire
the replacement back to the original nets.

Then register the adapter:

```python
# core/base.py

class MorphCircuitKind(StrEnum):
    LUT = "lut"
    FRAC_LUT = "frac_lut"
    MY_AND2 = "my_and2"
```

```python
# core/registry.py

from fabulous.fabric_cad.fabxplore.modules.morph_tile.circuits.my_and2 import (
    MyAnd2Circuit,
    MyAnd2Options,
)

...

if kind is MorphCircuitKind.MY_AND2:
    circuits.append(
        MyAnd2Circuit(
            env=env,
            options=MyAnd2Options.model_validate(_circuit_options(env, kind)),
        )
    )
    continue
```

The pass can then enable it with flat, adapter-local options:

```python
self.design_morph_tile_pass(
    tile_verilog_path=Path("tile.v"),
    tile_top_name="my_tile",
    tile_inputs=["I0", "I1"],
    tile_outputs=["O"],
    enabled_circuits=["my_and2"],
    circuit_options={
        "my_and2": {
            "enable_permute_cache": True,
        },
    },
)
```

The adapter file owns the cut-specific behavior. The registry only wires the
name to the class. The mapper, progress tracker, report, and writer continue to
operate on the generic adapter interface.
