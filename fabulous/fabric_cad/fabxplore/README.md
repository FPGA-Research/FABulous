# fabxplore

fabxplore is a Python design-space exploration framework for FABulous FPGA
architectures. It gives one flow access to synthesis, packing, place-and-route
experiments, FABulous project generation, FASM evaluation, bitstream metadata,
tile RTL generation, and backend gate-level/ASIC-style analysis.

The useful difference to many traditional CAD flows is that fabxplore keeps the
whole experiment inside one editable Python context. In a normal flow, synthesis,
packing, placement, routing, architecture generation, and backend analysis are
often separate tools connected by files. That is powerful, but it makes DSE
loops awkward: once you leave one stage, it is hard to ask a question from
another stage and jump back.

fabxplore is built for that jump:

```text
user RTL
  -> pyosys design context
  -> architecture-specific mapping passes
  -> FABulous project and routing graph
  -> nextpnr route / FASM / report
  -> graph queries and architecture edits
  -> write tile RTL, routing model, bitstream metadata, backend netlists
  -> loop again
```

In one experiment you can synthesize a user design, map it to a new tile model,
edit the tile switch matrix, resize the fabric, route a benchmark batch, parse
the generated FASM, learn which routing resources mattered, run a demand
evaluator, write the modified FABulous project back out, and then map the tile
RTL to a standard-cell library for area feedback.

When the graph state should become a real FABulous artifact, the flow can write
routing metadata, `pips.txt`, `bel.v2.txt`, `template.pcf`, bitstream-spec
metadata, generated tile RTL, and backend netlists.

That is the core idea: fabxplore treats a FABulous architecture as a live design
object, not just as a set of CSV files on disk.

## Quick Start

fabxplore flows are normal Python files. The FABulous CLI exposes them through
the `fabxplore` command:

```text
fabxplore path/to/my_architecture.py
```

Inside FABulous, the file is loaded, exactly one `ArchitectureSynthesizer`
subclass is instantiated, the active FABulous API is attached, and `run_flow()`
is called.

A minimal architecture flow looks like this:

```python
from pathlib import Path

from fabulous.fabric_cad.fabxplore.flow.architecture_synthesizer import (
    ArchitectureSynthesizer,
)


class MyArchitecture(ArchitectureSynthesizer):
    def run_flow(self) -> None:
        # self.design is the active pyosys/Yosys design context.
        self.design.read_verilog_paths([Path("design/top.v")])
        self.design.run_pass("hierarchy -check -top top")
        self.design.run_pass("proc")
        self.design.run_pass("opt")

        # self.fpga_model is the active FABulous/PnR/graph context.
        assert self.fpga_model is not None

        print(self.fpga_model.fabric_dimensions())  # noqa: T201

        self.pnr_switch_matrix_pattern_pass(
            tile_name="LUT5F",
            routing_pip_pattern="full",
            replace_existing_matrix=True,
        )

        result = self.pnr_inverse_router_pass(
            tile_name="LUT5F",
            training_benchmarks={
                "or17_chain": Path("tests/out/or17_chain.json"),
            },
            switch_matrix_remove_unused_ratio=1.0,
            switch_matrix_remove_used_ratio=0.0,
        )

        print(result.report_summary)  # noqa: T201
```

The two global contexts are the important part:

- `self.design` is a `PyosysBridge`. It owns the active user netlist and lets
  the architecture flow call Yosys passes, custom mapping passes, analyzers, and
  writers.
- `self.fpga_model` is a `PnRBridge`. It owns the active FABulous project, the
  loaded routing graph, the current user design, nextpnr helpers, FASM parsing,
  routing-model generation, and graph editing APIs.

This mirrors a pattern used across CAD tools. Yosys has one active design,
nextpnr has one architecture/context plus a design, VPR has an RR graph plus
clusters and nets, and commercial tools such as Cadence or Synopsys flows also
operate around a global design database. fabxplore applies the same idea to
FABulous DSE: keep the design and architecture alive, inspect them, mutate them,
and decide what to try next.

## Documentation Map

The top-level README is the tour. The module READMEs are the manuals.

```text
fabxplore/
|-- README.md                                      this overview
|-- pnr/fab_graph/README.md                       live FABulous routing graph
|-- pnr/pnr_modules/nextpnr/README.md             nextpnr wrapper and auto-PCF
`-- modules/
    |-- sat_fab/README.md                         SAT circuit/config solver
    |-- morph_tile/README.md                      SAT-assisted tile mapping
    |-- lut_mapper/README.md                      ABC LUT cost shaping
    |-- lut_combinator/README.md                  fractional LUT packing
    |-- lut_decomposer/README.md                  large LUT plus mux primitive
    |-- lut_layering/README.md                    multi-layer LUT reuse
    |-- chain_mapper/README.md                    carry/reduction chain lowering
    |-- reg_absorber/README.md                    absorb adjacent FFs into tiles
    |-- ff_materializer/README.md                 materialize FFs as tile lanes
    |-- placement_hints/README.md                 structural placement metadata
    |-- tile_builder/README.md                    create FABulous tile packages
    |-- routing_patterns/README.md                switch-matrix pattern edits
    |-- switch_block_factorizer/README.md         mux hierarchy/JUMP factoring
    |-- routing_demand_evaluator/README.md        PathFinder-style demand oracle
    |-- inverse_router/README.md                  benchmark-driven matrix learner
    `-- netlist_tool/README.md                    tile RTL to gate-level backend
```

The `design_analyzer` module currently has no local README, but it is exposed
through `ArchitectureSynthesizer.design_analyzer_pass(...)` and is summarized
below.

## The Big Picture

fabxplore is an architecture workbench. It is not only a mapper, not only a
router, and not only a project generator. It is a place where those stages can
interact:

```text
                   +----------------------+
                   | ArchitectureSynthesizer |
                   +-----------+----------+
                               |
             +-----------------+-----------------+
             |                                   |
      +------v------+                     +------v------+
      | self.design |                     | fpga_model  |
      | PyosysBridge|                     | PnRBridge   |
      +------+------+                     +------+------+
             |                                   |
    synth/map/analyze                    FabGraph / nextpnr
             |                                   |
             +-----------------+-----------------+
                               |
                         DSE loop in Python
```

Because both sides are available in one Python object, a pass can ask questions
that normally cross tool boundaries:

- Which cell families dominate this design before mapping?
- How many FFs remain after register absorption?
- How many switch-matrix PIPs does this tile have after a routing pattern pass?
- Does a resized fabric still route my training benchmarks?
- Which local switch-matrix cells appeared in the routed FASM?
- What is the area of the generated switch-matrix RTL after ASIC mapping?
- If this pass failed, can I add back routing resources and try again?

That loop is the reason fabxplore is useful for DSE.

## FABulous As A Graph

[fab_graph README](pnr/fab_graph/README.md)

fabxplore loads the FABulous project into `FabGraph`, a tile-type routing graph
inspired by VTR/VPR's RR-graph idea. The graph is not just a dump of concrete
PIPs. It preserves tile-local resource models and materializes concrete
instances lazily when needed.

```text
FABulous project files
  fabric.csv
  Tile/*/*.csv
  switch_matrix.list/csv
        |
        v
    FabGraph
        |
        +-- tile-type models
        +-- matrix resources
        +-- external resources
        +-- BEL metadata
        +-- placed tile coordinates
        +-- lazy concrete PIPs
```

The graph edits architecture resources by tile type. If the `LUT5F` switch
matrix changes, every placed `LUT5F` tile sees the same changed tile-local
resource model.

Important operations include:

- query tile types, placed instances, BELs, matrix rows, external resources,
  active/disabled PIPs, and config-bit counts;
- get and replace a tile switch matrix with `switch_matrix()` and
  `set_switch_matrix()`;
- add, disable, restore, or delete matrix and external resources;
- resize external vectors or remove individual external tracks;
- resize the whole fabric with `resize_fabric(...)`;
- reset the layout with `reset_fabric_layout()`;
- render `pips.txt`, `bel.txt`, `bel.v2.txt`, and `template.pcf`;
- write a complete routing model with `write_routing_model(...)`;
- write tile sources or a full updated project, including generated RTL.

The resize operation is intentionally graph-level. It changes the placed
tile-type coordinate map, not the tile model itself:

```python
self.fpga_model.resize_fabric(
    copy_column_after=(1, 5),
)

print(self.fpga_model.fabric_dimensions())  # noqa: T201
```

That can create graph experiments that FABulous would not normally accept as a
final fabric. That is fine during exploration. When the result is ready, the
graph can render or write routing metadata and tile sources explicitly.

The key implementation detail is efficiency. The graph keeps resource state in
dict indexes, groups by tile type, and avoids materializing the full concrete
PIP set unless a query asks for it. That makes loops such as "try a matrix,
route benchmarks, score FASM, modify matrix, try again" practical.

## Pyosys And nextpnr

[Fabric router README](pnr/pnr_modules/nextpnr/README.md)

fabxplore uses pyosys through `PyosysBridge` for design-side transformations.
The same active design can be mapped, analyzed, written as Verilog or JSON, and
handed to PnR.

For routing, fabxplore wraps the existing FABulous nextpnr backend. The designs
and routing metadata remain compatible with the current `nextpnr-generic
--uarch fabulous` implementation:

```text
active pyosys design
  -> Yosys JSON
  -> auto or user PCF
  -> nextpnr-generic --uarch fabulous
  -> FASM + JSON report
```

The wrapper can auto-generate PCF files from the current graph-rendered
`template.pcf`. `pcf_assignment_seed=1` preserves template order; higher seeds
deterministically shuffle legal IO sites. That makes benchmark sweeps easy:

```python
self.fpga_model.nextpnr_batch_test(
    {"or17_chain": Path("or17_chain.json")},
    pcf_assignment_seed=3,
)
```

The router returns structured results including report data and FASM text. That
FASM text can immediately be passed back into `evaluate_fasm(...)`, closing the
loop from route result back to architecture-resource query.

## Project Structure And Extension Model

fabxplore keeps the reusable functionality in `modules/`, then registers many
of those modules as pass helpers on `ArchitectureSynthesizer`.

```text
ArchitectureSynthesizer
  design_* passes -> PyosysBridge / user netlist
  pnr_* passes    -> PnRBridge / FABulous graph
  netlist_tool    -> backend gate-level mapping
```

Examples of registered helpers:

```python
self.design_lut_mapper_pass(...)
self.design_lut_combinator_pass(...)
self.design_morph_tile_pass(...)
self.design_lut_layering_pass(...)
self.design_chain_mapper_pass(...)
self.design_absorb_registers_pass(...)
self.design_materialize_registers_pass(...)
self.design_placement_hints_pass(...)

self.pnr_tile_builder_pass(...)
self.pnr_switch_matrix_pattern_pass(...)
self.pnr_switch_block_factorizer_pass(...)
self.pnr_routing_demand_evaluator_pass(...)
self.pnr_inverse_router_pass(...)

self.netlist_tool_pass(...)
```

New modules follow the same style:

```text
module core algorithm
  -> model/result/report classes
  -> thin custom pass wrapper
  -> ArchitectureSynthesizer helper
  -> optional README and tests
```

This is what lets fabxplore act as a framework rather than a fixed flow. One
architecture can be mostly LUT-based, another can be carry-heavy, another can
experiment with morph tiles, another can generate a custom tile and then
rewrite its switch matrix before routing.

That also means the modules are not tied to one architecture. A flow can
prototype a fracturable LUT tile, a LUT-plus-carry tile, a tile with custom mux
combiner BELs, a sequential lane tile, a pass-through heavy routing tile, or a
completely new configurable primitive as long as the needed mapping and PnR
contracts are described in Python.

## SAT-FAB

[sat_fab README](modules/sat_fab/README.md)

`sat_fab` is a small standalone SAT framework for configurable Boolean
circuits. It answers questions of the form:

$\exists cfg_2\ .\ \forall inputs\ .\ C_1(fixed\_cfg_1, inputs) = C_2(cfg_2, inputs)$

In words: can a configurable candidate circuit be configured so that it behaves
like a target circuit for every input assignment?

It provides circuit builders for LUTs, gates, muxes, routes, truth-table
targets, routed inputs, output choices, fixed config, symbolic config, BLIF
import, CEGIS solving, brute-force checks for small spaces, SAT miter
verification for larger spaces, and result helpers such as INIT extraction and
route/pin mapping.

Example:

```python
from fabulous.fabric_cad.fabxplore.modules.sat_fab import Circuit, Equiv, Func

target = Circuit.truth_table(
    name="xor2_target",
    inputs=["A", "B"],
    outputs={"Y": Func.xor("A", "B")},
)

cand = Circuit("lut2_candidate")
A, B = cand.inputs("A", "B")
Y = cand.lut([A, B], name="LUT2")
cand.output("Y", Y)

result = Equiv.check(target, cand).match_inputs_by_name().solve()
assert result.sat
print(result.lut_init(cand, "LUT2"))  # noqa: T201
```

The most important detail is that inputs are circuit-local by default. If both
circuits have a port named `A`, that does not connect them unless the query
explicitly calls `.match_inputs_by_name()` or provides a custom input relation.

## Morph Tile

[Morph tile README](modules/morph_tile/README.md)

Morph tile is the main SAT-assisted mapper for architecture exploration. It
maps ordinary LUT-mapped logic into instances of a configurable architecture
tile.

The mental model is entropy. A fixed primitive says:

```text
this cell implements this behavior
```

A morph tile says:

```text
this configurable circuit can implement many behaviors;
find the state that implements this one LUT function
```

The tile Verilog may expose data inputs, config bits, carry paths, internal mux
states, and several outputs. SAT then chooses:

- how logical LUT inputs route to tile inputs,
- which tile output implements the function,
- which configuration bits must be set.

Mathematically, for a tile output $T_j$ and a LUT function $f$:

$\exists \rho, j, q\ .\ \forall a:\ T_j(\rho(a), q) = f(a)$

The result is not an abstract LUT. The final netlist contains the real BEL/tile
cell with concrete input wires, concrete output choice, and solved config bits.
That matters because downstream timing and area analysis can see the real BELs
and, after PnR, the real PIP timing model.

The most important detail is that morph tile is generic. It can map to whatever
configurable Verilog circuit the architecture designer provides, as long as the
SAT problem is bounded enough to solve.

## LUT Mapping, Combination, Decomposition, And Layering

[LUT mapper README](modules/lut_mapper/README.md)

The LUT mapper shapes Yosys ABC/ABC9 cost vectors for later fractional-LUT
packing. ABC sees abstract LUT sizes, but a fracturable FABulous tile cares
about whether two LUTs can share physical pins. The mapper computes costs that
prefer LUT-size distributions likely to pack well later.

[LUT combinator README](modules/lut_combinator/README.md)

The LUT combinator packs two logical LUTs into one fractional LUT macro when
the shared/private pin structure allows it. The idea is similar to LUT
combination in commercial FPGA flows such as Xilinx/Vivado style LUT combining,
where disabling LUT combining leaves more separate logic cells. fabxplore
generalizes the idea: the user can configure internal LUT size, shared inputs,
private inputs, select-as-data behavior, and passthrough full-LUT modes.

The feasibility rule for paired LUTs can be seen as:

$|A \cup B| \le K + P$

where $K$ is the internal LUT size and $P$ is the private-pin count per side.

[LUT decomposer README](modules/lut_decomposer/README.md)

The LUT decomposer handles the opposite case: a wide logical LUT, such as LUT6
or LUT8, can be split into smaller leaf LUTs plus a configurable mux-like
primitive. The leaf truth tables are deterministic cofactors; SAT is only used
to prove that the user-provided mux primitive can select the right cofactor.
This is the generalized FABulous version of MUXF-style LUT extension.

[LUT layering README](modules/lut_layering/README.md)

LUT layering uses unused fractional-LUT capacity left by one mapped design to
inject another design. The base design is not repacked from scratch. Instead,
the combinator result is used as an inventory of free internal LUT slots.

```text
before:
  FRAC_LUT(L0=base logic, L1=unused)

after:
  FRAC_LUT(L0=base logic, L1=overlay logic)
```

This gives a "multi-layer synthesis" style loop: synthesize one design, find
remaining LUT space, synthesize another design into the gaps, and repeat until
the inventory is exhausted.

The most important detail across these LUT modules is that fabxplore can move
between abstract LUTs and real architecture cells while preserving exact INIT
and pin semantics.

## Design Analysis

The design analyzer is a read-only pass over `self.design`. It exports the
active pyosys design to an internal netlist model and reports:

- total cells, ports, and signal bits;
- coarse Yosys cells vs fine gates vs custom cells;
- combinational, sequential, memory, and unknown cell counts;
- control signal references;
- cell-family breakdowns;
- fanin/fanout metrics;
- chain-oriented metrics;
- characterization tags.

Use it when deciding which architecture features are worth exploring:

```python
analysis = self.design_analyzer_pass()
print(analysis.report_summary)  # noqa: T201
```

The most important detail is that it does not mutate the design. It is a
diagnostic pass for choosing what to do next.

## Chains, Registers, And Sequential Mapping

[Chain mapper README](modules/chain_mapper/README.md)

The chain mapper lowers selected Yosys word-level or reduction cells into a
generic `__chain` primitive. It supports `$alu`, `$reduce_and`, `$reduce_or`,
`$reduce_xor`, and `$reduce_bool`. This is useful because Yosys has a standard
notion of ALU cells, but architecture experiments often need more explicit
chain shapes: carry chains, wide reductions, boolean reductions, or other local
state transitions.

For reductions, the mapper emits a linear sequence of chain primitives. For
ALU-style cells, it preserves both sum and carry behavior. A later architecture
techmap or morph-tile stage can turn `__chain` into the real FABulous primitive.

[Register absorber README](modules/reg_absorber/README.md)

The register absorber moves FFs that are already adjacent to a mapped primitive
into that primitive's sequential ports. An output-side example is:

```text
before: tile.O0 -> FF -> users
after:  tile.Q0 ------> users
```

It does not invent new registers. It only absorbs matching nearby FFs when
clock, enable, reset, fanout, and config rules allow the move.

[FF materializer README](modules/ff_materializer/README.md)

The FF materializer handles FFs that are still standalone after absorption. It
creates configured tile instances that act as register lanes:

```text
before: D -> FF -> Q
after:  D -> tile.I0, tile.Q0 -> Q
```

The pass can pack multiple compatible FF lanes into one tile and uses SAT-style
configuration reasoning where needed for lane behavior.

[Placement hints README](modules/placement_hints/README.md)

Placement hints attach non-functional attributes to existing cells. The first
rule detects linear chains and emits cluster attributes such as
`FAB_CLUSTER_ID`, `FAB_CLUSTER_INDEX`, and `FAB_CLUSTER_SIZE`. This gives later
placement tools a structural hint without changing logic behavior.

The most important detail in this family is that fabxplore can keep sequential
intent explicit all the way from Yosys cells to architecture tile lanes and
placement metadata.

## PnR And The FPGA Model

The `fpga_model` context is where architecture DSE becomes concrete. It is pure
in-memory until the user writes something. There is no need to obey final
FABulous bitstream limits while exploring, so a flow can resize the fabric,
overbuild a routing matrix, test routability, prune it, and only later write
files.

```text
fpga_model
  +-- FABulous API
  +-- active pyosys design
  +-- FabGraph
  +-- nextpnr helpers
  +-- FASM parser/evaluator
  +-- routing model writer
```

### Tile Builder

[Tile builder README](modules/tile_builder/README.md)

The tile builder creates a complete FABulous tile package from BEL RTL files
and a baseline switch-matrix policy. It writes the tile CSV, switch-matrix list
or `MATRIX,GENERATE` request, copied BEL RTL, `custom_prims.v` updates,
generated switch-matrix/config-memory RTL, and `fabric.csv` registration when
requested.

The baseline routing generator is intentionally modest. It gives the DSE loop a
valid starting tile, not a final optimal matrix.

### Routing Patterns

[Routing patterns README](modules/routing_patterns/README.md)

The routing pattern pass edits the in-memory switch matrix. It can add source
coverage for BEL inputs, output-row coverage, route-through patterns, constants,
BEL feedback, and optional local JUMP hierarchy.

Available route-through patterns include:

- `none`: do not add routing-to-routing PIPs;
- `full`: enable every current row/column pair;
- `subset`: same-index style track connectivity;
- `wilton`: deterministic side-dependent permutation;
- `universal`: diverse round-robin source selection.

The most important detail is that `full` is an upper bound only over the
current graph resource universe. It does not add new external resources or BEL
pins. If `full` does not route, the resource universe itself is likely missing
something.

### Switch Block Factorizer

[Switch block factorizer README](modules/switch_block_factorizer/README.md)

The switch block factorizer preserves source-to-sink reachability while
rewriting large mux rows into smaller JUMP-based stages:

```text
before:
  OUT <- S0, S1, S2, S3, S4, S5, S6, S7

after:
  J0_BEG <- S0, S1, S2, S3
  J1_BEG <- S4, S5, S6, S7
  OUT    <- J0_END, J1_END
```

This changes implementation structure, not logical routing reachability. It is
useful when one flat switch-matrix row is too large as a physical mux, or when
an architecture wants hierarchical switch blocks.

### Routing Demand Evaluator

[Routing demand evaluator README](modules/routing_demand_evaluator/README.md)

The demand evaluator builds a tile-local routing graph from the current switch
matrix and generates synthetic source-to-sink demands. It then routes those
demands with a PathFinder-style negotiated-congestion router and reports
reachability, bottlenecks, fanout stress, failure classes, and congestion
pressure.

It can be used as a quality oracle before a full user benchmark exists:

```python
self.pnr_routing_demand_evaluator_pass(
    tile_name="LUT5F",
    demand_profile="full",
    router="pathfinder",
    repair_unreachable_demands=True,
    relax_congestion=True,
)
```

It also includes optimizers (`dense`, `greedy`, `monte_carlo`) that prune
switch-matrix PIPs under demand constraints and can add back baseline PIPs to
repair unreachable or congested demand routes.

### Direct Routing And Batch Routing

[Fabric router README](pnr/pnr_modules/nextpnr/README.md)

fabxplore can route the active design or a batch of benchmark JSON designs
directly from the graph-rendered routing model:

```python
single = self.fpga_model.nextpnr_route(check=False)

batch = self.fpga_model.nextpnr_batch_test(
    {
        "or17_chain": Path("or17_chain.json"),
        "lut32_mixed": Path("lut32_mixed.json"),
    },
    pcf_assignment_seed=2,
    check=False,
)
```

The router wrapper can temporarily write the graph-rendered `.FABulous`
metadata, run nextpnr, collect reports and FASM, and restore previous files.
That is what makes in-memory graph experiments routeable without committing the
graph state to source files first.

## Benchmark-Driven Inverse Router

[Inverse router README](modules/inverse_router/README.md)

The inverse router is a matrix learner. A normal router is a forward tool:

```text
fabric + netlist -> route -> FASM
```

The inverse router looks backward:

```text
FASM + fabric graph -> used tile-local switch-matrix PIPs -> learned matrix
```

The name is meant literally. If a forward function computes $y=f(x)$, and the
interesting information is hidden in how the output was produced, an inverse
view $x=f^{-1}(y)$ can be faster than exploring the whole input space again.
This is similar to forward/backward numerical recursions: sometimes the cheap
or stable direction is the opposite of the way the original problem is phrased.

The training loop is:

```text
for each IO seed:
    route training benchmarks
    parse successful FASM
    group routed matrix PIPs by tile type
    build one used matrix per benchmark

score = sum(used matrices)
remove score-zero PIPs
optionally remove low-score positive PIPs
validate training benchmarks
validate test benchmarks
```

One routed benchmark may use the same local PIP on many tile instances. The
used matrix collapses that to one tile-type-level cell:

```text
X1Y5.N1END0.LA_I0 -> LUT5F local cell LA_I0 <- N1END0
X3Y7.N1END0.LA_I0 -> same local cell

benchmark used matrix:
  LA_I0 <- N1END0 = 1
```

With three benchmarks:

```text
M0 =
      A B C
  X [ 1 0 1 ]
  Y [ 0 1 0 ]

M1 =
      A B C
  X [ 1 1 0 ]
  Y [ 0 1 0 ]

M2 =
      A B C
  X [ 0 1 0 ]
  Y [ 1 0 0 ]

Score = M0 + M1 + M2

        A B C
  X   [ 2 2 1 ]
  Y   [ 1 2 0 ]
```

With conservative pruning:

```python
switch_matrix_remove_unused_ratio=1.0
switch_matrix_remove_used_ratio=0.0
```

only score-zero cells are removed. The training-union argument is:

$$
s_M(m) = \sum_{b \in B} \mathbf{1}[m \in U_{M,b}]
$$

$$
U_M = \bigcup_{b \in B} U_{M,b}
$$

If $s_M(m)=0$, then $m \notin U_M$. Removing that cell cannot remove any matrix
PIP used by any collected successful training route.

The most important detail is diagnostic: training validation should pass for
routes that passed during collection when only unused matrix cells are removed
and the validation run sees the same effective routing model. If it does not,
either extraction missed a required matrix resource or the validation model is
not equivalent to the collection model.

## Netlist Tool And Backend Design

[Netlist tool README](modules/netlist_tool/README.md)

The netlist tool maps FABulous tile RTL to a PDK-specific gate-level netlist.
It uses Yosys/pyosys, but not as a generic ASIC recipe. The flow is tuned for
FPGA tile RTL, especially mux-heavy switch matrices and configuration logic.

Important features:

- custom ABC restructuring before final Liberty mapping;
- Liberty text editing to add, remove, or resize cell areas in memory;
- sub-circuit extraction with Yosys graph-isomorphic matching;
- optional cell-type remapping;
- `stat -liberty` reporting and parsed area feedback.

This is useful for experiments such as:

```text
What happens if this mux+latch pattern becomes one custom cell?
How much area does a factored switch matrix save?
Does a custom compound mux cell make this tile cheaper?
```

The key point is that `techmap` alone is not enough for many backend
experiments. Sometimes the interesting object is a multi-cell pattern after
standard-cell mapping. The netlist tool can let Yosys extract that pattern and
replace it with a custom cell while still giving direct area feedback.

## A Practical DSE Loop

Because fabxplore is just Python, an experiment can be a loop:

```python
for columns in [10, 12, 14, 16]:
    self.fpga_model.reset_fabric_layout()
    self.fpga_model.resize_fabric(copy_column_after=(1, columns - 10))

    self.pnr_switch_matrix_pattern_pass(
        tile_name="LUT5F",
        routing_pip_pattern="full",
        replace_existing_matrix=True,
    )

    route_result = self.pnr_inverse_router_pass(
        tile_name="LUT5F",
        training_benchmarks=training,
        test_benchmarks=test,
        switch_matrix_remove_unused_ratio=1.0,
        switch_matrix_remove_used_ratio=0.0,
    )

    demand = self.pnr_routing_demand_evaluator_pass(
        tile_name="LUT5F",
        demand_profile="full",
        opt=False,
    )

    print(columns, route_result.result_data.switch_matrix_stats)  # noqa: T201
    print(demand.report_summary)  # noqa: T201
```

Nothing forces this loop to be only PnR. You can move between:

- `self.design`: run Yosys, mapper, analyzer, SAT-assisted tile mapping;
- `self.fpga_model`: edit the FABulous graph, resize the fabric, route
  benchmarks, parse FASM;
- tile/source writers: emit FABulous CSV/list/RTL/routing metadata;
- netlist tool: map generated RTL to gate-level libraries and read area.

That is the central reason fabxplore exists: it lets architecture exploration
use synthesis results, routing results, graph queries, FASM evidence, and
backend area feedback in one programmable loop.

## Readme-By-Readme Summary

### [FABulous Routing Graph](pnr/fab_graph/README.md)

`FabGraph` is the live FABulous architecture graph. It loads tile models,
switch matrices, external resources, BEL metadata, and placed coordinates. It
supports fast queries, lazy concrete PIP materialization, graph edits, fabric
resize/reset, routing-model rendering, and write-back to tile/project sources.

Most important detail: edits are tile-type-level architecture edits, not one
placed instance edit.

### [Fabric Router](pnr/pnr_modules/nextpnr/README.md)

The router wrapper exports the active design to JSON, creates or accepts a PCF,
invokes `nextpnr-generic --uarch fabulous`, captures FASM and reports, and can
auto-generate PCF assignments from the graph-rendered routing model.

Most important detail: route results include `fasm_text`, which makes FASM-based
analysis and inverse routing possible.

### [SAT-FAB](modules/sat_fab/README.md)

SAT-FAB is a standalone configurable-circuit equivalence engine. It supports
truth-table targets, symbolic LUT/config bits, routed inputs and outputs,
CEGIS, and result extraction.

Most important detail: it answers exact configuration questions, not heuristic
pattern guesses.

### [Morph Tile](modules/morph_tile/README.md)

Morph tile maps LUT functions into configurable Verilog tile models by solving
input routing, output choice, and config bits with SAT.

Most important detail: the output netlist contains real configured tile/BEL
instances, enabling architecture-aware STA and PnR.

### [LUT Mapper](modules/lut_mapper/README.md)

The LUT mapper computes ABC/ABC9 cost vectors for fractional-LUT architectures.

Most important detail: it biases abstract LUT mapping toward LUT sizes that
will pack well later.

### [LUT Combinator](modules/lut_combinator/README.md)

The combinator packs two logical LUTs into fractional LUT macros when the
shared/private pin model allows it.

Most important detail: it generalizes commercial LUT-combination ideas to
configurable shared-input architectures.

### [LUT Decomposer](modules/lut_decomposer/README.md)

The decomposer splits wide LUTs into leaf LUT cofactors plus a configurable
mux-like primitive.

Most important detail: cofactor extraction is deterministic; SAT is used only
to prove the mux primitive can realize the recombination function.

### [LUT Layering](modules/lut_layering/README.md)

Layering inserts additional designs into unused fractional-LUT slots left by a
base design.

Most important detail: it enables multi-layer synthesis without repacking the
base design from scratch.

### [Chain Mapper](modules/chain_mapper/README.md)

The chain mapper lowers reductions and ALU-style cells into a generic
`__chain` representation for later architecture-specific mapping.

Most important detail: it lets the flow describe more than Yosys' default ALU
view, including reduction chains.

### [Register Absorber](modules/reg_absorber/README.md)

The absorber removes adjacent FF cells by moving their behavior into sequential
ports of existing mapped primitives.

Most important detail: it only absorbs FFs whose structural and control
semantics match the rule.

### [FF Materializer](modules/ff_materializer/README.md)

The materializer replaces remaining standalone FFs with configured tile
instances acting as register lanes.

Most important detail: it can pack multiple compatible FF lanes into one tile.

### [Placement Hints](modules/placement_hints/README.md)

Placement hints add non-functional clustering attributes, currently for linear
chains.

Most important detail: they guide placement without changing logic.

### [Tile Builder](modules/tile_builder/README.md)

The tile builder creates complete FABulous tile packages from BEL RTL and a
baseline routing policy.

Most important detail: it deliberately creates a modest valid starting matrix
that later graph/PnR passes can expand or prune.

### [Routing Patterns](modules/routing_patterns/README.md)

Routing patterns apply parameterized switch-matrix edits such as `full`,
`subset`, `wilton`, `universal`, BEL access, constants, and JUMP hierarchy.

Most important detail: pattern passes are graph edits, not file writes.

### [Switch Block Factorizer](modules/switch_block_factorizer/README.md)

The factorizer rewrites large mux rows into staged JUMP-based muxes while
preserving logical reachability.

Most important detail: it changes implementation mux shape without removing
original routing choices.

### [Routing Demand Evaluator](modules/routing_demand_evaluator/README.md)

The demand evaluator routes synthetic source-to-sink checks through a
switch-matrix snapshot with a PathFinder-style router.

Most important detail: it is a routing-quality oracle before or alongside real
benchmark routing.

### [Inverse Router](modules/inverse_router/README.md)

The inverse router learns switch-matrix importance scores from routed FASM and
uses them to prune a tile matrix.

Most important detail: conservative unused-only pruning has a training-union
safety argument, so training validation failures are diagnostic.

### [Netlist Tool](modules/netlist_tool/README.md)

The netlist tool maps tile RTL through a Yosys/ABC/Liberty backend flow tuned
for FPGA tiles and custom-cell experiments.

Most important detail: it gives area feedback for architecture RTL and custom
compound-cell ideas, not only user RTL.
