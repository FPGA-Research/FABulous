# Routing Demand Evaluator

`routing_demand_evaluator` is a PnR-side analysis pass for FABulous switch
matrices. It reads one tile, builds the routing graph represented by the active
switch matrix, generates synthetic routing demands, routes those demands with a
PathFinder-style negotiated-congestion router, and reports how the matrix behaves.

The pass answers questions like:

- Can every important BEL input be reached from at least one routing source?
- Can every BEL output escape back into routing?
- Do JUMP wires and hierarchy levels preserve source-to-sink reachability?
- Which source-to-sink combinations are missing?
- How much fanout can one local net drive?
- Which resources become routing bottlenecks?
- Which demand classes fail because the matrix is not connected enough?
- Which demand classes pass but route through highly congested resources?

This makes the pass useful as a routing-quality oracle before a complete user
design is available. It is also useful after a tile-builder or switch-block
factorizer pass, because it can check whether generated or factorized matrices
still have the expected reachability.

## Pass Interface

Use the pass from an architecture flow:

```python
self.pnr_routing_demand_evaluator_pass(
    tile_name="LUT4AB",

    # Optional file overrides.
    tile_dir=None,
    tile_csv=None,
    switch_matrix=None,

    # Demand profile.
    demand_profile="full",
    demand_iterations=1000,
    random_demand_ratio=0.25,
    seed=1,

    # Optimizer hook.
    opt=False,
    optimizer="none",
    opt_target_pip_reduction=0.20,
    opt_max_soft_failure_rate=0.05,
    opt_max_hard_failure_rate=0.0,
    opt_use_baseline_failure_rates=True,
    opt_write_back=False,
    report_max_soft_failure_rate=0.05,

    # PathFinder-style router.
    router="pathfinder",
    router_max_iterations=30,
    router_present_cost_multiplier=1.3,
    router_history_cost_increment=1.0,
    router_base_resource_capacity=1,

    # Multi-sink net stress.
    fanout_targets=[2, 4, 8],
    max_net_sinks=8,

    # Config-bit policy.
    config_bit_capacity_override=None,
    config_bit_margin=0,

    track_progress=True,
)
```

Options:

- `tile_name`: FABulous tile name to evaluate.
- `tile_dir`: optional tile directory override. If omitted, the pass uses the
  directory from the loaded FABulous tile.
- `tile_csv`: optional tile CSV override.
- `switch_matrix`: optional switch-matrix `.list` or `.csv` override. If omitted,
  the pass uses the tile's active matrix.
- `demand_profile`: preset demand bundle. Users select profiles, not individual
  demand classes.
- `demand_iterations`: target demand budget. The final number can be lower or
  higher depending on what the selected tile can generate. Structural classes
  are bounded by available terminals, and random classes are bounded by matching
  reachable candidate pairs.
- `random_demand_ratio`: fraction of the budget reserved for random classes.
- `seed`: random seed for repeatable random demand selection.
- `opt`: enable an optimizer. Currently `False` is the normal evaluation mode.
- `optimizer`: optimizer name. Currently `none` is implemented.
- `opt_target_pip_reduction`: global reduction target for optimizer modes.
- `opt_max_soft_failure_rate`: maximum soft-demand failure-rate increase allowed
  during optimization.
- `opt_max_hard_failure_rate`: maximum hard-demand failure-rate increase allowed
  during optimization.
- `opt_use_baseline_failure_rates`: when `True`, optimizer failure-rate limits
  are added to the baseline failure rates. When `False`, the optimizer limits
  are absolute.
- `opt_write_back`: when `True`, optimizer changes overwrite the active tile
  files in place. The pass must regenerate the dependent switch-matrix,
  config-memory, and tile artifacts so no stale files remain. The default is
  `False`, which keeps optimizer runs report-only.
- `report_max_soft_failure_rate`: soft-failure threshold used for top-level
  report status. Hard failures always make the report fail.
- `router`: router implementation. Currently `pathfinder`.
- `router_max_iterations`: maximum negotiated-congestion iterations.
- `router_present_cost_multiplier`: multiplier for present congestion cost.
- `router_history_cost_increment`: increment for historical congestion cost.
- `router_base_resource_capacity`: default capacity per intermediate routing
  resource. A value of `1` is the conservative FPGA routing default.
- `fanout_targets`: sink counts used by fanout-style demand classes.
- `max_net_sinks`: maximum number of sinks in one generated multi-sink demand.
- `config_bit_capacity_override`: optional config-bit capacity override. `None`
  uses the loaded FABulous fabric capacity.
- `config_bit_margin`: reserved config-bit margin.
- `track_progress`: enables progress logging.

## What The Pass Builds

The evaluator builds a directed graph:

$$
G = (V, E)
$$

where each switch-matrix node is a vertex $v \in V$, and every selectable PIP is
a directed edge:

$$
(s, t) \in E
$$

meaning source node $s$ can drive destination row $t$.

FABulous JUMP wires are added as explicit directed edges:

$$
J_{beg} \rightarrow J_{end}
$$

This is important because hierarchy is not flattened away. A path such as:

```text
JN2END1 -> J_l_AB_BEG0 -> J_l_AB_END0 -> LA_I0
```

is represented as three graph edges, so hierarchy, local mux stages, and
factorized switch blocks are evaluated as they really exist.

## Terminal Semantics

The pass uses FABulous objects to classify terminals. It does **not** infer
special behavior from names.

Classification sources:

- `tile.portsInfo`
- `bel.inputs`
- `bel.outputs`
- `bel.externalInput`
- `bel.externalOutput`
- `bel.carry`
- `bel.localShared`
- `bel.sharedPort`
- carry annotations in tile CSV ports

Internal roles include:

```text
bel_input
bel_output
tile_input
tile_output
jump_begin
jump_end
constant
carry_input
carry_output
local_reset
local_enable
shared_reset
shared_enable
io_input
io_output
external_input
external_output
```

This rule is deliberate: if a BEL has a port named `SR`, `EN`, `Ci`, or `Co`,
that name alone is not enough to classify it as reset, enable, or carry. The
semantic role must be exposed by FABulous metadata or the tile CSV. Otherwise
the port is treated as a generic BEL input or output.

For example, `LUT4AB` contains ports and wires such as:

```text
LA_SR
LA_EN
LA_Ci
LA_Co
J_SR_BEG0 -> J_SR_END0
J_EN_BEG0 -> J_EN_END0
```

If these are not marked as control or carry in the loaded FABulous BEL or tile
metadata, then `control_reachability`, `control_net`, and `carry_chain` generate
no demands. That is correct behavior for this pass because names are not stable
architecture contracts.

## Demand Profiles

A **profile** is a user-facing preset. A **demand class** is an internal generator
that creates one family of routing questions. Users choose a profile, and the
profile chooses the demand classes.

### `minimal`

Fast smoke test for basic matrix health:

- `matrix_row_coverage`
- `bel_input_reachability`
- `bel_output_escape`

Use this when you only want to know whether the matrix has obvious broken rows
or disconnected BEL access.

### `default`

Practical single-tile quality check:

- `matrix_row_coverage`
- `bel_input_reachability`
- `bel_output_escape`
- `hierarchy_integrity`
- `bel_input_source_coverage`
- `matrix_source_usefulness`
- `local_feedback`
- `straight_routing`
- `turn_routing`
- `bel_input_fanout`
- `random_local`
- `random_medium`

Use this as the normal evaluator profile while developing tile-builder settings
or switch-matrix patterns.

### `routing_stress`

Routing-fabric pressure profile:

- `matrix_row_coverage`
- `hierarchy_integrity`
- `bel_input_source_coverage`
- `matrix_source_usefulness`
- `straight_routing`
- `turn_routing`
- `short_to_long`
- `long_to_short`
- `multi_hop`
- `routing_redundancy`
- `bel_input_fanout`
- `random_medium`
- `random_long`

Use this when the tile is structurally valid and you want to see routing quality,
long/short access, path diversity, and congestion pressure.

### `control_stress`

Control and high-fanout focused profile:

- `bel_input_reachability`
- `bel_input_source_coverage`
- `control_reachability`
- `control_net`
- `bel_input_fanout`
- `carry_chain`
- `random_local`
- `random_medium`

Use this when the tile explicitly exposes reset, enable, carry, or similar
semantic metadata and you want to stress those paths.

### `full`

Runs every implemented demand class:

```python
classes=list(DemandClassName)
```

Use this for detailed reports and final sanity checks. It is intentionally more
aggressive than `default`, so it can produce soft failures even when a tile is
perfectly reasonable.

## Demand Classes

Demand classes are grouped in the report by intent.

### Essential Checks

`matrix_row_coverage`

Checks that switch-matrix rows have meaningful source coverage. This catches
rows that exist but cannot be driven in a useful way.

`bel_input_reachability`

For each generic BEL input, asks whether at least one useful routing source can
reach it. This is a minimum condition for mapping logic into the tile.

Mathematically, for each BEL input sink $b$, the class checks whether:

$$
\exists s \in S_{route}: \mathrm{path}(s, b) \neq \emptyset
$$

`bel_output_escape`

For each generic BEL output, asks whether it can escape into at least one useful
routing row. This catches BELs that can compute values but cannot feed the fabric.

`hierarchy_integrity`

Checks explicit hierarchy edges, especially JUMP wires. If a tile uses:

```text
source -> J_LOCAL_BEG -> J_LOCAL_END -> sink
```

this class confirms that the hierarchy stages are present and routable.

### Stress Checks

`bel_input_source_coverage`

Checks individual source-to-BEL-input pairs. Unlike `bel_input_reachability`,
which only needs one source per sink, this class asks how broad the source access
is.

This is useful because two matrices can both pass basic reachability while one
has much better source diversity.

`matrix_source_usefulness`

Checks whether source terminals can reach useful matrix destinations. It helps
detect sources that technically exist but do not help route meaningful demands.

`local_feedback`

Routes BEL outputs back to same-tile BEL inputs. This models local feedback such
as LUT output to LUT input. It is important for logic packing, local recirculation,
state-machine structures, and LUT-composition patterns.

`neighbor_feedback`

In the current single-tile evaluator this uses the same tile-local graph and
acts as a proxy for feedback pressure. In a whole-fabric extension, this class is
the natural place to add real tile-adjacency demands.

`straight_routing`

Routes tile routing resources in the same direction class. It asks whether the
switch matrix supports straight-through movement.

`turn_routing`

Routes tile routing resources across different direction classes. It asks whether
the switch matrix supports turns.

`short_to_long`

Routes from short/local resources into longer resources. This measures whether
local signals can enter longer-distance routing.

`long_to_short`

Routes from long resources into short/local resources. This measures whether
long-distance routes can re-enter local routing near a tile.

`multi_hop`

Generates paths that need more than one internal routing stage. This is important
for hierarchical switch matrices and factorized mux structures.

`routing_redundancy`

Tests alternative reachable routes and path diversity. A matrix can pass basic
reachability while still having very little redundancy.

`bel_input_fanout`

Generates one-source, multi-sink demands into BEL inputs. It asks:

$$
s \rightarrow \{b_0, b_1, \ldots, b_k\}
$$

and is reported as a net demand, not only independent point-to-point paths.

This is useful because a real net often feeds more than one BEL input. A matrix
with good point-to-point reachability can still be weak for one-net fanout.

### Special Checks

`control_reachability`

Checks reachability into reset/enable-like terminals, but only when those
terminals are explicitly classified as control roles by FABulous metadata.

`control_net`

Generates high-fanout control-like net demands. This is useful for reset and
enable distribution, again only when the tile explicitly exposes the relevant
semantic roles.

`carry_chain`

Checks carry input/output chains when FABulous exposes carry metadata. It does
not guess carry from names like `Ci` or `Co`.

`dsp_ram_access`

Checks access to DSP/RAM-like terminals when the tile exposes such special roles.

`io_access`

Checks access to IO-like terminals when the tile exposes IO roles.

### Random Checks

`random_local`

Samples reachable local-distance source/sink pairs.

`random_medium`

Samples medium-distance source/sink pairs.

`random_long`

Samples long-distance source/sink pairs.

Random buckets also report candidate statistics:

- candidate pairs
- reachable pairs
- generated demands

This makes an empty random class explainable. For example:

```text
random_long: candidate pairs exist, but none are reachable
```

means the tile has long-distance-looking endpoints, but the current graph has no
reachable pairs in that bucket.

## Hard And Soft Demands

Demand kind controls report status:

- `hard`: required structural checks. A hard failure makes the whole report fail.
- `soft`: quality or stress checks. Soft failures are allowed up to
  `report_max_soft_failure_rate`.

Top-level status:

$$
\mathrm{status} =
\begin{cases}
\mathrm{FAIL} & \text{if any hard demand fails} \\
\mathrm{PASS\ WITH\ WARNINGS} & \text{if soft failure rate exceeds threshold} \\
\mathrm{PASS} & \text{otherwise}
\end{cases}
$$

The soft failure rate is:

$$
r_{soft} = \frac{N_{soft,failed}}{N_{soft,total}}
$$

## PathFinder-Style Router

The router is a PathFinder-style negotiated-congestion router. It is inspired by
the same family of negotiation-based FPGA routing algorithms used in production
routers such as nextpnr, but it is intentionally scoped to demand evaluation. It
is not a replacement for nextpnr.

The router handles single-sink and multi-sink demands. A multi-sink demand is
routed as a route tree:

```text
source -> sink0
       -> sink1
       -> sink2
```

For each global iteration:

1. Compute node costs from historical and present congestion.
2. Route every demand.
3. For a multi-sink demand, route each sink to the current route tree.
4. Count intermediate resource usage.
5. Increase historical cost for overused resources.
6. Stop when there are no failed sinks and no congestion, or when
   `router_max_iterations` is reached.

Let $u_i$ be the current usage of resource $i$, and $c_i$ be its capacity. A
resource is congested when:

$$
u_i > c_i
$$

The present overuse is:

$$
p_i = \max(u_i - c_i, 0)
$$

The router uses a cost shape:

$$
\mathrm{cost}_i =
h_i \cdot H + p_i \cdot P^{(k - 1)}
$$

where:

- $h_i$ is historical overuse count for resource $i$
- $H$ is `router_history_cost_increment`
- $P$ is `router_present_cost_multiplier`
- $k$ is the current router iteration

The shortest-path search minimizes:

$$
\mathrm{pathCost}(s,t) =
\sum_{v \in path(s,t)} \left(1 + \mathrm{cost}_v\right)
$$

This means resources that are repeatedly overused become more expensive, so later
iterations try alternative paths when the graph has alternatives.

## Congestion Reporting

The report has two usage views:

- `Most Used Resources`: counts all nodes in routed paths, including endpoints.
- `Congestion`: counts intermediate routing nodes only.

Congestion uses intermediate nodes because source and sink endpoints can be
popular without being routing bottlenecks. For a path:

```text
source -> a -> b -> sink
```

the congestion section counts:

```text
a, b
```

not:

```text
source, sink
```

The report shows:

- resource capacity
- number of congested resources
- maximum intermediate resource usage
- number of routed demands that pass through congested resources
- top congested resources
- congestion by demand class

High congestion does not necessarily mean the tile is wrong. It means many
synthetic demands are using the same resources. For example, in a `LUT4AB` report
the following hot resources are plausible:

```text
JN2BEG1 / JN2END1
J_SR_BEG0 / J_SR_END0
J_l_AB_BEG0 / J_l_AB_END0
J_EN_BEG0 / J_EN_END0
```

Those are real generated JUMP/mux resources. If many demands go through them,
the report correctly identifies them as bottlenecks.

## Reading A LUT4AB-Style Report

An example `LUT4AB` full-profile report can show:

```text
hard demands passed: 209 / 209
soft demands passed: 326 / 344
status: PASS WITH WARNINGS
```

This means the tile passes all required structural checks, but some quality
checks failed.

If `bel_input_source_coverage` fails for examples like:

```text
Ci0 -> LA_I0
E1END0 -> LA_I1
```

then the evaluator is saying these exact source-to-sink paths do not exist in
the loaded routing graph. That does not automatically mean the tile is wrong.
It means those combinations are not supported by the matrix.

If the report says:

```text
Demand class generated no demands: control_net
Demand class generated no demands: carry_chain
```

while the Verilog or matrix contains names like `SR`, `EN`, `Ci`, or `Co`, that
is still correct unless the loaded FABulous metadata marks them as control or
carry. The evaluator does not infer special roles from names.

## What The Result Can Be Used For

The structured result contains:

- per-demand route result
- per-sink failures
- routed paths
- hard and soft pass rates
- per-class statistics
- random bucket coverage
- resource usage
- PIP usage
- congestion summary
- config-bit usage

That makes it useful for:

- checking a generated tile before fabric generation
- comparing switch-matrix patterns
- comparing flat and hierarchical matrices
- detecting disconnected BEL inputs or outputs
- finding weak local feedback
- measuring source diversity into BEL inputs
- finding high-fanout bottlenecks
- identifying routing resources that dominate many routes
- serving as a common oracle for future optimization passes
