# sat_fab

SAT-based configurable circuit equivalence and configuration synthesis.

`sat_fab` is a small Python framework for questions of the form:

```text
exists cfg2 . forall inputs . C1(fixed_cfg1, inputs) == C2(cfg2, inputs)
```

It is import-only. There is no command line interface.

## Public API

Use the package from Python:

```python
from fabulous.fabric_cad.fabxplore.modules.sat_fab import Circuit, Equiv, Func
```

The intended style is:

```python
target = Circuit.truth_table(...)
candidate = Circuit("candidate").inputs(...)
result = Equiv.check(target, candidate).match_inputs_by_name().solve()
```

By default, `Equiv.solve()` discovers all configurable LUT and ROUTE bits in
normal `Circuit` objects and treats unfixed bits as symbolic. Fast truth-table
targets have no symbolic config. Circuit input ports are circuit-local by
default, so same spelling on two sides does not connect the ports unless you add
an explicit input relation.

## Circuit-Local Inputs

Every side owns its input ports independently:

```text
c1/A is different from c2/A
```

Use `.match_inputs_by_name()` when same-named ports should be connected:

```python
result = Equiv.check(c1, c2).match_inputs_by_name().solve()
```

Use `.map_inputs(...)` for fixed custom connections:

```python
result = (
    Equiv.check(c1, c2)
    .map_inputs(c2, {"I0": "A", "I1": "B", "SEL": "S"})
    .solve()
)
```

Use `.route_inputs(...)` when SAT should discover the mapping.

## Features

- `Circuit` graph builder for gates, muxes, constants, LUTs, routes, mux trees,
  reductions, routed LUTs, LUT networks, and fixed truth-table blocks.
- `Func` helpers for automatic truth-table construction:
  - `Func.xor(...)`
  - `Func.and_(...)`
  - `Func.or_(...)`
  - `Func.not_(...)`
  - `Func.mux(...)`
  - `Func.mux_indexed(...)`
  - `Func.expr(lambda ...)`
- Fast truth-table target mode through `Circuit.truth_table(...)`,
  `Circuit.lut_truth_table(...)`, or class-level `Circuit.lut(...)`.
- Multi-output truth-table targets and fixed internal truth blocks.
- Scoped config keys based on `StrEnum` kinds rather than free string literals.
- Fixed config, symbolic config, compact `.fix(...)`, `.fix_lut(...)`,
  `.fix_route(...)`, and `.fix_pin(...)` helpers.
- Explicit input relations with `.match_inputs_by_name()`, `.map_inputs(...)`,
  and `.route_inputs(...)`, including port permutation, optional input sharing,
  constants, and decoded input mappings.
- Optional output routing with `.route_outputs(...)`, so a target output can be
  matched against one of several implementation outputs chosen by SAT.
- CEGIS using PySAT with a persistent outer solver.
- Brute-force verification for small input spaces and SAT miter verification for
  larger cases.
- Optional random example seeding.
- Truth-table symmetry utilities.
- BLIF `.names` import and same-file `.subckt` flattening.
- Useful result helpers:
  - `result.sat`
  - `result.lut_init(...)`
  - `result.route(...)`
  - `result.pinmap(...)`
  - `result.input_mapping(...)`
  - `result.output_mapping(...)`
  - `result.summary(...)`
  - `result.print(...)`
  - `result.emit_verilog_config()`
  - `result.write_json(...)`

Graphviz rendering is intentionally not included in this module.

## Truth-Table Target

No manual INIT generation is needed:

```python
target = Circuit.truth_table(
    name="xor2_target",
    inputs=["A", "B"],
    outputs={
        "Y": Func.xor("A", "B"),
    },
)

cand = Circuit("lut2_candidate")
A, B = cand.inputs("A", "B")
Y = cand.lut([A, B], name="LUT2_0")
cand.output("Y", Y)

result = Equiv.check(target, cand).match_inputs_by_name().solve()

assert result.sat
print(hex(result.lut_init(cand, "LUT2_0")))
```

The same fast target can be written as:

```python
target = Circuit.lut(
    name="xor2_target",
    inputs=["A", "B"],
    outputs={"Y": Func.xor("A", "B")},
)
```

## Multi-Output Truth Tables

Full adder target:

```python
target = Circuit.truth_table(
    name="full_adder_target",
    inputs=["A", "B", "Cin"],
    outputs={
        "SUM": Func.expr(lambda A, B, Cin: A ^ B ^ Cin),
        "COUT": Func.expr(
            lambda A, B, Cin: (A & B) | (A & Cin) | (B & Cin)
        ),
    },
)
```

Internal fixed truth block:

```python
c = Circuit("fa_block")
a, b, cin = c.inputs("A", "B", "Cin")

sum_, cout = c.truth_block(
    name="FA",
    inputs=[a, b, cin],
    outputs={
        "SUM": Func.expr(lambda A, B, Cin: A ^ B ^ Cin),
        "COUT": Func.expr(
            lambda A, B, Cin: (A & B) | (A & Cin) | (B & Cin)
        ),
    },
)

c.output("SUM", sum_)
c.output("COUT", cout)
```

`truth_block(...)` creates fixed truth-table nodes, not symbolic LUT config.

## Fixed Truth Tables vs Configurable LUTs

Use `ttable(...)` when a LUT-like block has fixed contents inside the circuit.
The INIT value is part of the circuit structure, so SAT does not choose it and
`result.lut_init(...)` will not report it as solved configuration.

```python
from fabulous.fabric_cad.fabxplore.modules.sat_fab import Circuit

c = Circuit("fixed_lut_logic")
A, B = c.inputs("A", "B")

# Fixed XOR2 truth table for input order [A, B].
Y = c.ttable(inputs=[A, B], init=0x6, name="XOR2_FIXED")
c.output("Y", Y)
```

Use `lut(...)` when the LUT contents are configurable. By default, unfixed LUT
INIT bits are symbolic, so SAT may choose them during `solve()`.

```python
from fabulous.fabric_cad.fabxplore.modules.sat_fab import Circuit

c = Circuit("symbolic_lut_logic")
A, B = c.inputs("A", "B")

Y = c.lut([A, B], name="LUT2")
c.output("Y", Y)
```

If the LUT is configurable in the circuit but should be fixed for one
equivalence problem, keep it as `lut(...)` and fix the INIT on the `Equiv`
object:

```python
from fabulous.fabric_cad.fabxplore.modules.sat_fab import Circuit, Equiv, Func

target = Circuit.truth_table(
    name="xor_spec",
    inputs=["A", "B"],
    outputs={"Y": Func.xor("A", "B")},
)

c = Circuit("fixed_for_this_solve")
A, B = c.inputs("A", "B")
Y = c.lut([A, B], name="LUT2")
c.output("Y", Y)

result = (
    Equiv.check(target, c)
    .match_inputs_by_name()
    .fix(c, lut={"LUT2": 0x6})
    .solve()
)
```

So the rule of thumb is:

- `ttable(...)`: fixed truth table, no symbolic config.
- `lut(...)`: configurable LUT, SAT chooses INIT bits unless fixed.
- `lut(...)` plus `.fix(..., lut={...})`: configurable circuit element forced
  to a known INIT for this solve.

## Builder Helpers

Basic gates:

```python
c = Circuit("logic")
a, b, s = c.inputs("A", "B", "S")

y1 = c.and_(a, b)
y2 = c.xor(a, b)
y3 = c.mux(sel=s, d0=a, d1=b)
```

Mux tree:

```python
y = c.mux_tree(
    data=[D0, D1, D2, D3],
    sels=[S0, S1],
    name="mux4",
)
```

Reductions:

```python
parity = c.reduce_xor([a, b, c0, d], name="parity")
any_set = c.reduce_or([a, b, c0, d], name="any")
all_set = c.reduce_and([a, b, c0, d], name="all")
```

Configurable route:

```python
r = c.route(candidates=[a, b, c0, d], name="R0")
```

Configurable LUT:

```python
y = c.lut([a, b, c0, d], name="LUT4_0")
```

Fully routed LUT:

```python
y = c.routed_lut(
    name="LUT0",
    k=4,
    candidates=[a, b, c0, d, e, f],
)
```

The routed LUT creates routes named:

```text
LUT0.a0
LUT0.a1
LUT0.a2
LUT0.a3
```

## LUT Networks

`lut_network(...)` builds a small configurable cascaded LUT cluster:

```python
ys = c.lut_network(
    name="cluster0",
    inputs=[a, b, c0, d, e, f],
    lut_sizes=[4, 4],
    outputs=1,
    allow_routes=True,
)

c.output("Y", ys[0])
```

With `allow_routes=True`, SAT chooses each LUT pin route and every LUT INIT bit.
Later LUTs may use earlier LUT outputs as route candidates.

## MUX4 Candidate Example

```python
target = Circuit.truth_table(
    name="mux4_target",
    inputs=["D0", "D1", "D2", "D3", "S0", "S1"],
    outputs={
        "Y": Func.mux_indexed(
            data=["D0", "D1", "D2", "D3"],
            select=["S0", "S1"],
        )
    },
)

cand = Circuit("two_lut4")
D0, D1, D2, D3, S0, S1 = cand.inputs("D0", "D1", "D2", "D3", "S0", "S1")

t = cand.routed_lut("LUT1", k=4, candidates=[D0, D1, D2, D3, S0, S1])
y = cand.routed_lut("LUT2", k=4, candidates=[D0, D1, D2, D3, S0, S1, t])
cand.output("Y", y)

result = (
    Equiv.check(target, cand)
    .match_inputs_by_name()
    .options(random_examples=16, verify="auto")
    .solve()
)

result.print(verbose=True)
print(result.pinmap(cand, "LUT1"))
```

## Configurable vs Configurable

Both sides can be configurable:

```python
left = Circuit("left")
A, B = left.inputs("A", "B")
yl = left.routed_lut("L0", k=2, candidates=[A, B])
left.output("Y", yl)

right = Circuit("right")
A, B = right.inputs("A", "B")
yr = right.routed_lut("R0", k=2, candidates=[A, B])
right.output("Y", yr)

result = (
    Equiv.check(left, right)
    .match_inputs_by_name()
    .fix(left, lut={"L0": 0x6}, pins={"L0": ["A", "B"]})
    .symbolic_all(right)
    .solve()
)

print(result.pinmap(left, "L0"))
```

Equivalent lower-level helpers are available:

```python
Equiv.check(left, right).fix_lut(left, "L0", init=0x6)
Equiv.check(left, right).fix_pin(left, "L0", "a0", "A")
Equiv.check(left, right).fix_route(left, "L0.a0", select="A")
```

## Virtual Input Routing

Use `.route_inputs(...)` when the implementation circuit already exists but its
input ports may be wired from a pool of target-side signals. This models:

```text
c2 inputs -> [pool]
```

The solver then chooses both the normal circuit config and the input mapping:

```text
exists config2, input_mapping . forall c1_inputs .
    c1(c1_inputs) == c2(input_mapping(c1_inputs), config2)
```

Example:

```python
target = Circuit.truth_table(
    name="xor2_target",
    inputs=["A", "B"],
    outputs={"Y": Func.xor("A", "B")},
)

cand = Circuit("mapped_lut3")
I0, I1, I2 = cand.inputs("I0", "I1", "I2")
Y = cand.lut([I0, I1, I2], name="LUT3")
cand.output("Y", Y)

result = (
    Equiv.check(target, cand)
    .route_inputs(
        cand,
        pool=["A", "B"],
        inputs=["I0", "I1", "I2"],
        allow_reuse=True,
        allow_constants=False,
    )
    .solve()
)

print(result.input_mapping(cand))
print(hex(result.lut_init(cand, "LUT3")))
```

Possible mapping:

```python
{"I0": "A", "I1": "B", "I2": "A"}
```

Here `I2` is still connected to a real source, but the solved LUT INIT may make
it a don't-care input.

Options:

- `pool`: allowed source input names. Defaults to the other side's input names.
- `inputs`: implementation input ports to route. Defaults to all normal inputs
  of the selected circuit.
- `allow_reuse=True`: multiple implementation ports may choose the same source.
- `allow_reuse=False`: source choices must be injective.
- `allow_constants=True`: add constant `0` and `1` sources to the pool.
- `name`: prefix for generated route config names.

## Virtual Output Routing

Without output routing, outputs are matched by name. If `c1` has outputs
`SUM` and `COUT`, then `c2` must also expose `SUM` and `COUT`, and the solver
checks both pairs:

```text
c1.SUM == c2.SUM
c1.COUT == c2.COUT
```

Use `.route_outputs(...)` when one side has several possible output ports and
SAT should choose which one implements a target output.

```python
result = (
    Equiv.check(c1, c2)
    .route_outputs(
        c2,
        {"Y": ["O5_0", "O5_1", "O6"]},
    )
    .solve()
)

print(result.output_mapping(c2))
```

This means `c1.Y` may be matched against one of `c2.O5_0`, `c2.O5_1`, or
`c2.O6`. The selected output is controlled by one-hot route config bits, just
like input routes.

For several target outputs:

```python
result = (
    Equiv.check(c1, c2)
    .route_outputs(
        c2,
        {
            "SUM": ["O0", "O1", "O2"],
            "COUT": ["O0", "O1", "O2"],
        },
        allow_reuse=False,
    )
    .solve()
)
```

With `allow_reuse=False`, two target outputs cannot select the same candidate
output.

## BLIF Import

BLIF files become normal `Circuit` objects:

```python
candidate = Circuit.from_blif(
    "candidate.blif",
    top="top",
    inputs=["I0", "I1", "I2", "I3"],
    configs=["cfg0", "cfg1", "cfg2", "cfg3"],
    outputs=["Y"],
)
```

Config bits can also be detected by prefix:

```python
candidate = Circuit.from_blif(
    "fabric_block.blif",
    inputs=["A", "B", "C", "D"],
    config_prefixes=["cfg", "INIT", "SEL"],
    outputs=["Y"],
)
```

Supported BLIF features:

- `.model`
- `.inputs`
- `.outputs`
- `.names`
- `.subckt` when the referenced model is defined in the same file
- `.end`

Unsupported in this version:

- `.latch`
- external black-box `.subckt` cells without a model definition
- very large `.names` tables above `max_truth_table_inputs`

## Solver Options

```python
result = (
    Equiv.check(target, cand)
    .match_inputs_by_name()
    .options(
        solver="g3",
        max_iters=10_000,
        random_examples=16,
        verify="auto",
        brute_force_input_limit=10,
        fast_truth_table=True,
        reduce_truth_table_symmetry=True,
    )
    .solve()
)
```

`verify` may be:

- `"auto"`: brute force for small input counts, SAT miter for larger counts.
- `"bruteforce"`: force exhaustive concrete checking.
- `"sat"`: force SAT miter checking.

## Result Reporting

```python
if result.sat:
    print(hex(result.lut_init(cand, "LUT1")))
    print(result.route(cand, "LUT1.a0"))
    print(result.pinmap(cand, "LUT1"))
    print(result.input_mapping(cand))
    print(result.input_mapping(cand, scoped=True))
    print(result.emit_verilog_config())
    result.write_json("solution.json")
```

`result.examples` contains the input examples used by CEGIS, and
`result.iterations` reports the number of CEGIS iterations before success.

## Large-Circuit Strategy

The implementation follows the large-circuit plan from the design document:

- flat graph representation rather than recursive expression trees,
- scoped config variables for both sides,
- automatic config discovery,
- output cone extraction during CNF encoding,
- persistent outer SAT solver,
- brute-force verification for small input spaces,
- SAT miter verification for larger input spaces,
- fast truth-table side avoids target mux graph construction,
- BLIF hierarchy is flattened into SAT-friendly graph form.

The current structure is ready for later additions such as Yosys JSON import,
external primitive maps, stronger partial evaluation, and per-output solving.

## Self-Tests

Run the in-package tests from Python:

```python
from fabulous.fabric_cad.fabxplore.modules.sat_fab.test_cases import run_all_tests

run_all_tests()
```

The tests cover:

- automatic `Func` truth-table generation,
- fast target vs configurable LUT,
- fixed truth blocks,
- mux tree and reduction helpers,
- configurable-vs-configurable synthesis,
- routed LUT pin fixing and pin maps,
- circuit-local input semantics and fixed input maps,
- virtual input routing and decoded input mappings,
- routed two-LUT4 MUX4 synthesis,
- BLIF `.names` import,
- BLIF `.subckt` flattening,
- BLIF input mapping.

## End-To-End Examples

These examples show complete `c1`, `c2`, and solver setup patterns.

### Example 1: Fixed Truth Table vs Configurable LUT

Find the INIT for a configurable LUT2 that implements XOR2.

```python
from fabulous.fabric_cad.fabxplore.modules.sat_fab import Circuit, Equiv, Func

c1 = Circuit.truth_table(
    name="xor2_spec",
    inputs=["A", "B"],
    outputs={"Y": Func.xor("A", "B")},
)

c2 = Circuit("lut2_impl")
A, B = c2.inputs("A", "B")
Y = c2.lut([A, B], name="LUT2")
c2.output("Y", Y)

result = Equiv.check(c1, c2).match_inputs_by_name().solve()

assert result.sat
print(result.summary())
print(hex(result.lut_init(c2, "LUT2")))
```

### Example 2: Configurable Circuit vs Configurable Circuit

Fix the left side to XOR2 and synthesize the right side.

```python
from fabulous.fabric_cad.fabxplore.modules.sat_fab import Circuit, Equiv

c1 = Circuit("left")
A, B = c1.inputs("A", "B")
Y = c1.lut([A, B], name="L0")
c1.output("Y", Y)

c2 = Circuit("right")
A, B = c2.inputs("A", "B")
Y = c2.lut([A, B], name="R0")
c2.output("Y", Y)

result = (
    Equiv.check(c1, c2)
    .match_inputs_by_name()
    .fix_lut(c1, "L0", init=0x6)
    .symbolic_all(c2)
    .solve()
)

assert result.sat
print(hex(result.lut_init(c2, "R0")))
```

### Example 3: Fixed Pins on a Routed LUT

Fix the left routed LUT to a known XOR2 implementation and synthesize the right
routed LUT.

```python
from fabulous.fabric_cad.fabxplore.modules.sat_fab import Circuit, Equiv

c1 = Circuit("left_routed")
A, B = c1.inputs("A", "B")
Y = c1.routed_lut("L0", k=2, candidates=[A, B])
c1.output("Y", Y)

c2 = Circuit("right_routed")
A, B = c2.inputs("A", "B")
Y = c2.routed_lut("R0", k=2, candidates=[A, B])
c2.output("Y", Y)

result = (
    Equiv.check(c1, c2)
    .match_inputs_by_name()
    .fix(c1, lut={"L0": 0x6}, pins={"L0": ["A", "B"]})
    .symbolic_all(c2)
    .solve()
)

assert result.sat
print(result.pinmap(c2, "R0"))
print(hex(result.lut_init(c2, "R0")))
```

### Example 4: LUT Network vs MUX4 Truth Table

Synthesize two routed LUT4s to implement a 4:1 mux.

```python
from fabulous.fabric_cad.fabxplore.modules.sat_fab import Circuit, Equiv, Func

c1 = Circuit.truth_table(
    name="mux4_spec",
    inputs=["D0", "D1", "D2", "D3", "S0", "S1"],
    outputs={
        "Y": Func.mux_indexed(
            data=["D0", "D1", "D2", "D3"],
            select=["S0", "S1"],
        )
    },
)

c2 = Circuit("two_lut4")
D0, D1, D2, D3, S0, S1 = c2.inputs("D0", "D1", "D2", "D3", "S0", "S1")

t = c2.routed_lut("LUT1", k=4, candidates=[D0, D1, D2, D3, S0, S1])
y = c2.routed_lut("LUT2", k=4, candidates=[D0, D1, D2, D3, S0, S1, t])
c2.output("Y", y)

result = (
    Equiv.check(c1, c2)
    .match_inputs_by_name()
    .options(random_examples=16)
    .solve()
)

assert result.sat
result.print(verbose=True)
print(result.pinmap(c2, "LUT1"))
print(result.pinmap(c2, "LUT2"))
```

### Example 5: BLIF Circuit vs Truth Table

Load a combinational BLIF implementation and check it against a Python-defined
truth table.

```python
from fabulous.fabric_cad.fabxplore.modules.sat_fab import Circuit, Equiv, Func

c1 = Circuit.truth_table(
    name="xor2_spec",
    inputs=["A", "B"],
    outputs={"Y": Func.xor("A", "B")},
)

c2 = Circuit.from_blif(
    "xor_impl.blif",
    top="top",
    inputs=["A", "B"],
    outputs=["Y"],
)

result = Equiv.check(c1, c2).match_inputs_by_name().solve()

assert result.sat
print(result.summary())
```

### Example 6: BLIF With Config Inputs

Treat selected BLIF inputs as configuration bits. This solves for config values
that make the BLIF circuit match the target for all normal inputs.

```python
from fabulous.fabric_cad.fabxplore.modules.sat_fab import Circuit, Equiv, Func

c1 = Circuit.truth_table(
    name="target",
    inputs=["A", "B"],
    outputs={"Y": Func.xor("A", "B")},
)

c2 = Circuit.from_blif(
    "candidate_with_cfg.blif",
    top="top",
    inputs=["A", "B"],
    configs=["cfg0", "cfg1", "cfg2", "cfg3"],
    outputs=["Y"],
)

result = Equiv.check(c1, c2).match_inputs_by_name().solve()

assert result.sat
print(result.config_for(c2).external_value("cfg0"))
print(result.config_for(c2).external_value("cfg1"))
print(result.config_for(c2).external_value("cfg2"))
print(result.config_for(c2).external_value("cfg3"))
```

The same import can classify config inputs by prefix:

```python
c2 = Circuit.from_blif(
    "candidate_with_cfg.blif",
    inputs=["A", "B"],
    config_prefixes=["cfg", "INIT", "SEL"],
    outputs=["Y"],
)
```

### Example 7: BLIF With Unknown Input Mapping

Load a BLIF circuit whose ports are named differently from the target, and let
SAT choose the input mapping.

```python
from fabulous.fabric_cad.fabxplore.modules.sat_fab import Circuit, Equiv, Func

c1 = Circuit.truth_table(
    name="xor2_spec",
    inputs=["A", "B"],
    outputs={"Z": Func.xor("A", "B")},
)

c2 = Circuit.from_blif(
    "xor_renamed_ports.blif",
    top="top",
    inputs=["X", "Y"],
    outputs=["Z"],
)

result = (
    Equiv.check(c1, c2)
    .route_inputs(
        c2,
        pool=["A", "B"],
        allow_reuse=False,
    )
    .solve()
)

assert result.sat
print(result.input_mapping(c2))
```

Possible output:

```python
{"X": "B", "Y": "A"}
```

Because XOR is symmetric, either permutation is valid.

### Example 8: Full Adder With Two Manual Routed LUT3s

This example uses a fast full-adder truth-table target and asks SAT to configure
exactly two LUT3s plus manually specified unknown routing. One LUT3 drives
`SUM`; the other drives `COUT`.

```python
from fabulous.fabric_cad.fabxplore.modules.sat_fab import Circuit, Equiv, Func

c1 = Circuit.truth_table(
    name="full_adder_spec",
    inputs=["A", "B", "Cin"],
    outputs={
        "SUM": Func.expr(lambda A, B, Cin: A ^ B ^ Cin),
        "COUT": Func.expr(lambda A, B, Cin: (A & B) | (A & Cin) | (B & Cin)),
    },
)

c2 = Circuit("two_lut3_fa")
A, B, Cin = c2.inputs("A", "B", "Cin")

sum_ = c2.routed_lut(
    name="SUM_LUT",
    k=3,
    candidates=[A, B, Cin],
)

cout = c2.routed_lut(
    name="COUT_LUT",
    k=3,
    candidates=[A, B, Cin],
)

c2.output("SUM", sum_)
c2.output("COUT", cout)

result = Equiv.check(c1, c2).match_inputs_by_name().solve()

assert result.sat
print("SUM_LUT", hex(result.lut_init(c2, "SUM_LUT")))
print("COUT_LUT", hex(result.lut_init(c2, "COUT_LUT")))
print(result.pinmap(c2, "SUM_LUT"))
print(result.pinmap(c2, "COUT_LUT"))
```

This is the most explicit style. You choose each candidate pool yourself, so the
search space matches the architecture you want to test. This exact two-LUT3
case is covered by `test_full_adder_two_manual_lut3()`.

### Example 9: Full Adder With `lut_network`

The same style can be made more compact with `lut_network(...)`. Here the
network creates exactly two LUT3s and returns both LUT outputs as the
full-adder outputs.

```python
from fabulous.fabric_cad.fabxplore.modules.sat_fab import Circuit, Equiv, Func

c1 = Circuit.truth_table(
    name="full_adder_spec",
    inputs=["A", "B", "Cin"],
    outputs={
        "SUM": Func.expr(lambda A, B, Cin: A ^ B ^ Cin),
        "COUT": Func.expr(lambda A, B, Cin: (A & B) | (A & Cin) | (B & Cin)),
    },
)

c2 = Circuit("lut_network_fa")
A, B, Cin = c2.inputs("A", "B", "Cin")

sum_, cout = c2.lut_network(
    name="FA",
    inputs=[A, B, Cin],
    lut_sizes=[3, 3],
    outputs=2,
    allow_routes=True,
)

c2.output("SUM", sum_)
c2.output("COUT", cout)

result = Equiv.check(c1, c2).match_inputs_by_name().solve()

assert result.sat
print(result.summary(verbose=True))
print(result.pinmap(c2, "FA_LUT0"))
print(result.pinmap(c2, "FA_LUT1"))
```

`lut_network(...)` is useful for quickly asking whether a small configurable LUT
cluster can implement a target. For precise FABulous-style structures, prefer
the manual routed-LUT form so each candidate pool exactly matches the routing
resources you want to model. This exact two-LUT3 network case is covered by
`test_full_adder_two_lut3_network()`.

### Example 10: LUT6 MUX4 Into Two LUT5s With Private Pins

This example models the fracturable-LUT case we discussed. `c1` is a MUX4
implemented as a fast LUT6 truth table. `c2` is two LUT5s feeding a hard MUX2:
the LUT5s have four shared data inputs, one private input each, and one hard mux
select. The input-routing layer lets SAT decide whether the two private ports
map to the same LUT6 input or to different LUT6 inputs.

```python
from fabulous.fabric_cad.fabxplore.modules.sat_fab import Circuit, Equiv, Func

c1 = Circuit.truth_table(
    name="mux4_lut6_spec",
    inputs=["D0", "D1", "D2", "D3", "S0", "S1"],
    outputs={
        "Y": Func.mux_indexed(
            data=["D0", "D1", "D2", "D3"],
            select=["S0", "S1"],
        )
    },
)

c2 = Circuit("two_lut5_hard_mux")
I0, I1, I2, I3, P0, P2, S = c2.inputs(
    "I0",
    "I1",
    "I2",
    "I3",
    "P0",
    "P2",
    "S",
)

lo = c2.lut([I0, I1, I2, I3, P0], name="LUT5_LO")
hi = c2.lut([I0, I1, I2, I3, P2], name="LUT5_HI")
y = c2.mux(sel=S, d0=lo, d1=hi, name="MUX2")
c2.output("Y", y)

result = (
    Equiv.check(c1, c2)
    .route_inputs(
        c2,
        pool=["D0", "D1", "D2", "D3", "S0", "S1"],
        inputs=["I0", "I1", "I2", "I3", "P0", "P2", "S"],
        allow_reuse=True,
        allow_constants=False,
    )
    .solve()
)

assert result.sat
print(result.input_mapping(c2))
print("LUT5_LO", hex(result.lut_init(c2, "LUT5_LO")))
print("LUT5_HI", hex(result.lut_init(c2, "LUT5_HI")))
```

One valid mapping has the private pins shared:

```python
{
    "I0": "D0",
    "I1": "D1",
    "I2": "D2",
    "I3": "D3",
    "P0": "S0",
    "P2": "S0",
    "S": "S1",
}
```

This means both LUT5s use `S0` internally and the hard MUX2 uses `S1`. If a
different architecture permits a non-shared solution, `allow_reuse=True` also
allows that; the decoded input mapping tells you which structure SAT selected.

### Example 11: Single Target Output Routed To One Candidate Output

This example has a one-output target `Y`, but the implementation exposes three
candidate outputs. Only `O1` is XOR, so SAT must select `O1`.

```python
from fabulous.fabric_cad.fabxplore.modules.sat_fab import Circuit, Equiv, Func

c1 = Circuit.truth_table(
    name="xor_spec",
    inputs=["A", "B"],
    outputs={"Y": Func.xor("A", "B")},
)

c2 = Circuit("candidate_outputs")
A, B = c2.inputs("A", "B")

c2.output("O0", c2.and_(A, B, name="wrong_and"))
c2.output("O1", c2.xor(A, B, name="right_xor"))
c2.output("O2", c2.or_(A, B, name="wrong_or"))

result = (
    Equiv.check(c1, c2)
    .match_inputs_by_name()
    .route_outputs(c2, {"Y": ["O0", "O1", "O2"]})
    .solve()
)

assert result.sat
print(result.output_mapping(c2))
```

Expected mapping:

```python
{"Y": "O1"}
```

Without `.route_outputs(...)`, this example would fail because `c2` has no
same-named output `Y`.

### Example 12: Multi-Output Target Routed To Multi-Output Candidate

Here the target is a full adder with outputs `SUM` and `COUT`. The candidate
has three possible outputs, and SAT chooses which two implement the target
outputs. `allow_reuse=False` prevents both target outputs from selecting the
same candidate output.

```python
from fabulous.fabric_cad.fabxplore.modules.sat_fab import Circuit, Equiv, Func

c1 = Circuit.truth_table(
    name="full_adder_spec",
    inputs=["A", "B", "Cin"],
    outputs={
        "SUM": Func.expr(lambda A, B, Cin: A ^ B ^ Cin),
        "COUT": Func.expr(lambda A, B, Cin: (A & B) | (A & Cin) | (B & Cin)),
    },
)

c2 = Circuit("multi_output_fa")
A, B, Cin = c2.inputs("A", "B", "Cin")

sum_ = c2.reduce_xor([A, B, Cin], name="sum")
ab = c2.and_(A, B, name="ab")
ac = c2.and_(A, Cin, name="ac")
bc = c2.and_(B, Cin, name="bc")
cout = c2.reduce_or([ab, ac, bc], name="cout")

c2.output("O0", cout)
c2.output("O1", sum_)
c2.output("O2", c2.or_(A, B, name="junk"))

result = (
    Equiv.check(c1, c2)
    .match_inputs_by_name()
    .route_outputs(
        c2,
        {
            "SUM": ["O0", "O1", "O2"],
            "COUT": ["O0", "O1", "O2"],
        },
        allow_reuse=False,
    )
    .solve()
)

assert result.sat
print(result.output_mapping(c2))
```

Expected mapping:

```python
{"SUM": "O1", "COUT": "O0"}
```

### Example 13: Input And Output Routing Together

Input and output routing can be active in the same solve. This is useful when
the implementation has different top-level input names and also exposes several
possible output ports.

```python
from fabulous.fabric_cad.fabxplore.modules.sat_fab import Circuit, Equiv, Func

c1 = Circuit.truth_table(
    name="and_not_spec",
    inputs=["A", "B"],
    outputs={"Y": Func.expr(lambda A, B: A and not B)},
)

c2 = Circuit("routed_in_and_out")
I, J, K = c2.inputs("I", "J", "K")

c2.output("O0", c2.and_(I, J, name="wrong_and"))
c2.output("O1", c2.and_(I, c2.not_(J, name="not_j"), name="right"))
c2.output("O2", c2.xor(I, K, name="wrong_xor"))

result = (
    Equiv.check(c1, c2)
    .route_inputs(
        c2,
        pool=["A", "B"],
        inputs=["I", "J", "K"],
        allow_reuse=True,
        allow_constants=False,
    )
    .route_outputs(c2, {"Y": ["O0", "O1", "O2"]})
    .solve()
)

assert result.sat
print(result.input_mapping(c2))
print(result.output_mapping(c2))
```

One valid result is:

```python
{"I": "A", "J": "B", "K": "A"}
{"Y": "O1"}
```

Here `K` is a don't-care input because the selected output `O1` does not use it.

### Input Relation Cases

Same port names are local by default. This intentionally returns UNSAT for an
identity circuit unless the ports are connected:

```python
c1 = Circuit.truth_table(
    name="identity_spec",
    inputs=["A"],
    outputs={"Y": Func.var("A")},
)

c2 = Circuit("identity_impl")
A = c2.input("A")
c2.output("Y", A)

assert not Equiv.check(c1, c2).solve().sat
assert Equiv.check(c1, c2).match_inputs_by_name().solve().sat
```

For a fixed custom map, use `.map_inputs(...)`:

```python
result = (
    Equiv.check(c1, c2)
    .map_inputs(c2, {"A": "A"})
    .solve()
)

print(result.input_mapping(c2))
print(result.input_mapping(c2, scoped=True))
print(result.input_mapping(c2, scoped=True, separator="::"))
```

Possible output:

```python
{"A": "A"}
{"c2/A": "c1/A"}
{"c2::A": "c1::A"}
```

For SAT-discovered maps, use `.route_inputs(...)`. The result format is the same
but the source choices come from SAT route selector bits rather than fixed
connections.

## Mathematical Explanation

The framework solves configurable combinational circuit equivalence and
configuration synthesis.

Assume two circuits:

```text
C1(cfg1, x) -> y1
C2(cfg2, x) -> y2
```

Here:

- $x$ is the vector of normal primary inputs.
- $\text{cfg}_1$ is the configuration vector of circuit 1.
- $\text{cfg}_2$ is the configuration vector of circuit 2.
- $y_1$ and $y_2$ are output vectors.

In the implementation, input variables are circuit-local. A port named `A` on
the left and a port named `A` on the right are different variables until an
input relation connects them. `.match_inputs_by_name()` adds that relation by
name, `.map_inputs(...)` adds a fixed custom relation, and `.route_inputs(...)`
lets SAT synthesize the relation.

The main synthesis question is $\exists \text{cfg}_2 . \forall x . C_1(\text{cfg}_1^{\text{fixed}}, x) = C_2(\text{cfg}_2, x)$.

In words: for a given fixed configuration of circuit 1, find one configuration
of circuit 2 such that both circuits produce the same outputs for every possible
normal input.

More generally, both sides may have fixed and symbolic configuration bits. Let $F$
be all fixed configuration constraints, and let $s$ be the remaining symbolic
configuration variables. Then the framework solves $\exists s . \forall x . F \land \left(C_1(\text{cfg}_1, x) = C_2(\text{cfg}_2, x)\right)$.

For multiple outputs, equality means all corresponding outputs match: $C_1(\text{cfg}_1, x) = C_2(\text{cfg}_2, x) \iff \bigwedge_i C_{1,i}(\text{cfg}_1, x) = C_{2,i}(\text{cfg}_2, x)$.

By default, corresponding outputs are matched by name. If output routing is
enabled, the framework introduces an output mapping $\rho$. For a target output
$y_i$, $\rho(y_i)$ is one of the candidate outputs on the routed circuit. The
comparison becomes $C_{1,i}(x) = C_{2,\rho(y_i)}(\text{cfg}_2, x)$.

The routed-output synthesis question is
$\exists \text{cfg}_2,\rho . \forall x . \bigwedge_i C_{1,i}(x) = C_{2,\rho(y_i)}(\text{cfg}_2, x)$.

Equivalently, define a miter: $M(\text{cfg}_1, \text{cfg}_2, x) = \bigvee_i \left(C_{1,i}(\text{cfg}_1, x) \oplus C_{2,i}(\text{cfg}_2, x)\right)$.

The miter is true exactly when the circuits differ for at least one output.
So equivalence means $\forall x . \neg M(\text{cfg}_1, \text{cfg}_2, x)$.

The original synthesis problem can therefore be written as $\exists \text{cfg}_2 . \forall x . \neg M(\text{cfg}_1^{\text{fixed}}, \text{cfg}_2, x)$.

Or, equivalently, $\exists \text{cfg}_2 . \neg \exists x . M(\text{cfg}_1^{\text{fixed}}, \text{cfg}_2, x)$.

This is an exists-forall Boolean problem, also called a 2-QBF shape: $\exists \text{cfg} . \forall x . \phi(\text{cfg}, x)$.

Instead of solving it directly with a QBF solver, `sat_fab` uses CEGIS:
counterexample-guided inductive synthesis.

The CEGIS loop splits the problem into two normal SAT problems.

### Candidate Synthesis SAT

Maintain a finite set of input examples: $E = \{x_0, x_1, \dots, x_k\}$.

The outer SAT solver asks: $\exists \text{cfg}_2 . \bigwedge_{x_j \in E} C_1(\text{cfg}_1^{\text{fixed}}, x_j) = C_2(\text{cfg}_2, x_j)$.

This is not yet a proof. It only finds a candidate configuration that works for
the currently known examples.

### Counterexample Checking SAT

After SAT gives a candidate $\text{cfg}_2^*$, the checker asks $\exists x . M(\text{cfg}_1^{\text{fixed}}, \text{cfg}_2^*, x)$.

If this SAT query is satisfiable, the model gives a counterexample input $x_{\text{bad}}$
where the circuits differ. The framework adds $x_{\text{bad}}$ to the example set $E$
and repeats.

If this SAT query is unsatisfiable, then $\neg \exists x . M(\text{cfg}_1^{\text{fixed}}, \text{cfg}_2^*, x)$, which is equivalent to $\forall x . \neg M(\text{cfg}_1^{\text{fixed}}, \text{cfg}_2^*, x)$.

At that point the candidate configuration is formally proven.

### Why SAT Can Choose LUT INITs

A configurable LUT with $k$ inputs has $2^k$ INIT bits: $\text{cfg} = (c_0, c_1, \dots, c_{2^k-1})$.

For input bits $a_0, a_1, \dots, a_{k-1}$, the LUT index is $\text{idx} = a_0 + 2a_1 + 4a_2 + \dots + 2^{k-1}a_{k-1}$.

The LUT output is $\text{LUT}(a, \text{cfg}) = c_{\text{idx}}$.

When the INIT bits are symbolic SAT variables, the solver can choose the truth
table. For example, XOR2 is represented by $c_0 = 0,\quad c_1 = 1,\quad c_2 = 1,\quad c_3 = 0$, so the INIT value is $\text{0b0110} = \text{0x6}$.

### Why SAT Can Choose Routing

A `ROUTE` node is a one-hot mux. If the candidates are $d_0, d_1, \dots, d_{n-1}$ and the route select bits are $s_0, s_1, \dots, s_{n-1}$, then the validity constraint is $\sum_i s_i = 1$.

The route output is $y = \bigvee_i (s_i \land d_i)$.

Because the select bits are symbolic configuration bits, SAT chooses which
candidate signal drives the route.

For a routed LUT, SAT therefore chooses both $\text{pin mapping}$ and $\text{LUT INIT bits}$.

### Fast Truth-Table Targets

When a side is created with `Circuit.truth_table(...)`, it is represented as a
fixed function $T(x) \rightarrow y$.

There is no symbolic configuration for this side. During small-case checking,
the framework can evaluate $T(x)$ directly from its INIT table. During SAT
miter checking, the same truth table can be encoded as a fixed mux tree.

For a multi-output target, $T(x) = (T_0(x), T_1(x), \dots, T_m(x))$, and each
output gets its own INIT table.

### BLIF Circuits

A BLIF `.names` block is a fixed truth table. During import, each `.names` block
is converted into a fixed internal truth-table node $y = f(a_0, a_1, \dots, a_{k-1})$.

If some BLIF inputs are declared as `configs=[...]` or match
`config_prefixes=[...]`, those inputs are treated as configuration variables
instead of universally quantified normal inputs.

So a BLIF circuit can participate in the same formula $\exists \text{cfg}_{\text{blif}} . \forall x . C_{\text{target}}(x) = C_{\text{blif}}(\text{cfg}_{\text{blif}}, x)$.

### Input Mapping

Input mapping adds a relation between circuit-local inputs. A fixed mapping is
a function $\mu$ chosen by the user. Virtual input routing makes $\mu$
existential and lets SAT choose it.

If the implementation has input ports $p_0, p_1, \dots, p_{n-1}$ and the
allowed source pool is $S = \{s_0, s_1, \dots, s_{m-1}\}$, each routed port gets
one one-hot route selector.

The solver chooses a mapping $\mu$ where $\mu(p_i) \in S$. With reuse enabled,
two ports may choose the same source, so $\mu(p_i) = \mu(p_j)$ is allowed. That
models shared inputs. With reuse disabled, the encoding adds clauses requiring
different routed ports to satisfy $\mu(p_i) \ne \mu(p_j)$.

The full routed-input synthesis question is $\exists \text{cfg}_2,\mu . \forall x . C_1(x) = C_2(\mu(x), \text{cfg}_2)$.

Constants are just extra pool entries, so allowing constants changes the source
set from $S$ to $S \cup \{0,1\}$.

### Output Mapping

Output mapping adds a relation between comparison outputs and candidate outputs.
A virtual output route makes this relation existential and lets SAT choose it.

If target output $y_i$ may be implemented by candidate outputs
$o_0, o_1, \dots, o_{m-1}$, the solver creates one-hot selector bits
$q_{i,0}, q_{i,1}, \dots, q_{i,m-1}$. The validity constraint is
$\sum_j q_{i,j} = 1$.

The selected value is $z_i = \bigvee_j (q_{i,j} \land o_j)$, and the miter
compares $C_{1,i}(x)$ against $z_i$ instead of comparing against a same-named
output.

With output reuse enabled, two target outputs may choose the same candidate
output. With reuse disabled, the encoding adds clauses
$\neg q_{i,j} \lor \neg q_{k,j}$ so two target outputs cannot select the same
source output $o_j$.

This is opt-in. If `.route_outputs(...)` is not used, output comparison remains
same-name matching and no extra selector bits or mux clauses are added.

### C2 To Pool Formulation

The notation `C2 -- [pool]` means that every selected input port of circuit 2 is
not directly a free environment variable. Instead, it is driven by a configurable
crossbar from a pool of source signals.

Let circuit 1 have environment inputs $x = (x_0, x_1, \dots, x_{m-1})$. Let the
selected input ports of circuit 2 be $p = (p_0, p_1, \dots, p_{n-1})$. The pool
is usually the inputs of circuit 1, so $S = \{x_0, x_1, \dots, x_{m-1}\}$, or
$S = \{x_0, x_1, \dots, x_{m-1}, 0, 1\}$ when constants are allowed.

An input mapping is a function $\mu : p \rightarrow S$. For each circuit-2 port
$p_i$, the mapped value is $p_i = \mu(p_i)$. Reuse means $\mu$ may be
many-to-one, so two circuit-2 inputs can share the same source. Disabling reuse
requires $\mu$ to be injective.

With this adapter, circuit 2 is evaluated as $C_2(\mu(x), \text{cfg}_2)$ rather
than $C_2(x, \text{cfg}_2)$. The synthesis question becomes
$\exists \text{cfg}_2, \mu . \forall x . C_1(x) = C_2(\mu(x), \text{cfg}_2)$.

The SAT encoding represents $\mu$ with one-hot selector variables. For each
port $p_i$ and each source $s_j \in S$, there is a selector bit
$r_{i,j}$. The validity constraint is $\sum_j r_{i,j} = 1$. The driven value is
$p_i = \bigvee_j (r_{i,j} \land s_j)$.

If reuse is disabled, additional clauses prevent two different ports from
selecting the same source: for $i \ne k$, the solver adds
$\neg r_{i,j} \lor \neg r_{k,j}$ for every shared source index $j$.

CEGIS treats the selector bits $r_{i,j}$ exactly like other existential
configuration bits. The outer solver chooses both $\text{cfg}_2$ and $\mu$ for
the current finite example set. The checker then asks whether there exists an
input $x$ where $C_1(x)$ and $C_2(\mu(x), \text{cfg}_2)$ differ. If no such $x$
exists, the discovered configuration and input mapping are valid for all inputs.

### Large-Circuit Method

The framework is designed around a flat graph $G = (V, E)$, where each node is
a Boolean primitive such as AND, XOR, LUT, ROUTE, or fixed truth table.

For selected outputs, only the transitive fan-in cone is encoded: $\text{Cone}(Y) = \{v \in V \mid v \text{ can affect } Y\}$.

This avoids encoding unrelated logic.

Each node is translated into CNF using Tseitin variables. A subexpression $z = a \land b$ is encoded by clauses equivalent to $z \leftrightarrow (a \land b)$.

For example: $(\neg z \lor a) \land (\neg z \lor b) \land (\neg a \lor \neg b \lor z)$.

This keeps the SAT formula linear in the number of encoded nodes, instead of
expanding expressions exponentially.

### Final Result

If `result.sat` is true, the solver found concrete values for the existential
configuration variables $\text{cfg}^*$ and proved $\forall x . C_1(\text{cfg}_1^*, x) = C_2(\text{cfg}_2^*, x)$.

The result object decodes $\text{cfg}^*$ back into user-facing artifacts:

- LUT INIT values,
- route selections,
- virtual input mappings,
- routed-LUT pin maps,
- external BLIF config input values,
- JSON or Verilog-style config summaries.

## Notes About CEGIS

CEGIS means counterexample-guided inductive synthesis. The direct problem is
usually of the form $\exists c . \forall x . C_1(x) = C_2(c, x)$, where $c$
contains LUT INIT bits, route selector bits, external BLIF config ports, and
possibly input-mapping selector bits.

Solving the full quantified problem directly is expensive. Instead, sat_fab
keeps a finite example set $E = \{x_0, x_1, \dots, x_k\}$ and asks the outer SAT
solver for a candidate configuration $c^*$ that works on those examples:
$\exists c . \bigwedge_{x_i \in E} C_1(x_i) = C_2(c, x_i)$.

Then a checker asks whether the candidate is wrong for any input:
$\exists x . C_1(x) \ne C_2(c^*, x)$. If the checker finds such an input, that
input is a counterexample and is added to $E$. The outer solver is run again
with the stronger example set.

The loop is:

```text
start with a few examples
solve for candidate config
check candidate on all inputs
if counterexample exists, add it
otherwise the candidate is valid
```

For small input counts, the checker can brute-force all $2^n$ input rows. For
larger cases, the checker builds a SAT miter and asks for one mismatching row.

This is fast in practice because the outer solver does not start with the full
truth table. It only sees the examples needed to eliminate bad candidates. LUT
and route configuration bits are shared across all examples, so every
counterexample strongly constrains the search. Fast truth-table targets avoid
building large target circuits when the target is already known as an INIT
table, and BLIF import prunes to the requested output cone before encoding.

Input and output routing use the same CEGIS machinery. If `route_inputs(...)`
is active, the candidate also contains an input mapping $\mu$. If
`route_outputs(...)` is active, the candidate also contains an output mapping
$\rho$. The outer solver proposes these mappings together with $c^*$, and the
checker verifies them against all inputs.

## Misc Notes

When SAT finds a solution, the result contains one valid configuration. There
may be many other valid configurations; sat_fab reports one model because that
answers the existence question.

To print the solved input mapping for a circuit whose top-level ports were
routed from a source pool:

```python
mapping = result.input_mapping(c2)
print(mapping)

scoped = result.input_mapping(c2, scoped=True)
for dst, src in scoped.items():
    print(f"{dst} <- {src}")
```

For example, a mapped BLIF or hand-built candidate may report:

```text
c2/I0 <- c1/S1
c2/I1 <- c1/D3
c2/P0 <- c1/D0
c2/S  <- c1/S0
```

To print the solved output mapping for a circuit whose output ports were
selected from a candidate set:

```python
mapping = result.output_mapping(c2)
print(mapping)

scoped = result.output_mapping(c2, scoped=True)
for target, source in scoped.items():
    print(f"{target} <- {source}")
```

For example:

```text
c1/Y <- c2/O6
c1/SUM <- c2/O1
c1/COUT <- c2/O0
```

To print every external config port of a BLIF-style module, use
`result.config_for(circuit).external_value(name)`:

```python
cfg = result.config_for(c2)

for name in c2.config_names():
    value = cfg.external_value(name)
    print(f"c2/{name} = {int(bool(value))}")
```

For a module with config inputs like `INIT0[0]`, `INIT0[1]`, and so on, this
prints the top-level port values that should be applied to the module.

For configurable LUT nodes created with `Circuit.lut(...)`, use the LUT helpers:

```python
print(hex(result.lut_init(c2, "LUT5_LO")))
print(result.config_for(c2).lut_bits("LUT5_LO"))
```

For routed LUTs and explicit route muxes, use:

```python
print(result.pinmap(c2, "LUT0"))
print(result.route(c2, "LUT0.a0"))
```

The distinction is:

- `external_value(...)` is for top-level config ports, often from BLIF.
- `lut_init(...)` and `lut_bits(...)` are for symbolic LUT nodes built by the
  sat_fab API.
- `route(...)`, `pinmap(...)`, `input_mapping(...)`, and
  `output_mapping(...)` decode one-hot routing choices.
