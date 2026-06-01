# Inverse Router

The inverse router is a benchmark-driven routing-resource learner. It does not
try to replace nextpnr. Instead, it runs benchmarks through a router that emits
FABulous FASM, reads the routed FASM back into the `PnRBridge`, and asks:

```text
Which tile-local switch-matrix PIPs and external PIPs did the router actually use?
```

The result is an importance score for every observed resource of one tile type.
Those scores can then be used to build a smaller switch matrix, disable unused
external resources, and validate the result on training and test benchmarks.

The pass works in memory on the PnR bridge graph. It does not write FABulous
source files. If the result should become source code, that write/update step
must be done explicitly by the caller.

## Concept

A normal router is a forward tool:

```text
fabric + netlist -> route -> FASM
```

The inverse router uses the route result in the opposite direction:

```text
FASM + fabric graph -> used routing resources -> optimized tile model
```

As a mathematical analogy, a forward function computes $y = f(x)$. If the output
$y$ is already known and the useful information is hidden in how $y$ was made,
then using an inverse view $x = f^{-1}(y)$ can be much faster than searching the
whole input space again. This is also close to the numerical idea of forward and
backward recursion: sometimes the stable or cheap direction is not the direction
in which the original problem is stated.

For routing, the expensive forward question is:

```text
Which subset of millions of possible resources is enough for useful designs?
```

The inverse question is cheaper:

```text
Given routed designs, which resources were actually used?
```

That gives a strong first solution quickly. It is not proof that every future
design will route, so the flow separates training benchmarks from test
benchmarks, similar to a machine-learning style train/test split.

## What Gets Scored

The inverse router scores two resource classes for one tile type.

Switch-matrix PIPs:

```text
row <- column
```

These are internal matrix PIPs of the selected tile type. The score is stored as
a `RoutingSwitchMatrix`.

External PIPs:

```text
source_wire -> destination_wire
```

These are expanded external routing resources owned by the selected tile type,
for example neighbor-wire or jump-wire PIPs that are not switch-matrix cells.
The score is stored as a dictionary keyed by tile-local PIP name.

## Router Requirement

The implementation currently uses the PnR bridge `nextpnr_batch_test()` helper,
because that helper returns route result objects with `fasm_text`. Conceptually,
the algorithm only needs a router that can provide routed FABulous FASM:

```python
route_results = fpga_model.nextpnr_batch_test(...)
document = fpga_model.evaluate_fasm(route_result.fasm_text)
```

`evaluate_fasm()` parses and annotates the FASM against the current graph. That
annotation is what makes the algorithm independent from naming guesses: matrix
PIPs and external PIPs come from graph metadata.

## Training And Test Loop

The high-level loop is:

```text
for seed in configured IO assignment seeds:
    route all training benchmarks
    parse successful FASM
    collect used switch-matrix PIPs
    collect used external PIPs

score resources
prune resources if enabled
apply selected graph edits if enabled

if validate_training:
    route training benchmarks again

if validate_test:
    route test benchmarks
```

Training benchmarks decide resource scores. Test benchmarks are only used to
check whether the learned/pruned graph generalizes to designs the scorer did not
learn from.

`io_seed_start` and `io_seed_count` run the same benchmark with multiple
deterministic auto-PCF assignments. For example:

```python
io_seed_start=1
io_seed_count=4
```

routes each benchmark with seeds `1, 2, 3, 4`. This can expose different edge
and IO routing behavior without needing more HDL designs.

## Switch-Matrix Scoring

For every successful training route, the emitted FASM contains concrete routed
features on concrete tile instances, for example:

```text
X1Y5.N1END0.LA_I0
X3Y7.N1END0.LA_I0
X4Y2.E1END1.LA_I2
```

The inverse router does not keep those as instance-specific matrix entries.
Instead, the FASM parser annotates each feature with the tile type at its
coordinate and then groups matrix PIPs by tile type. For `tile_name="LUT5F"`,
all matrix PIPs from all `LUT5F` instances in that one routed benchmark are
collapsed into one tile-type-level used matrix.

That means repeated use of the same local PIP on different instances becomes one
active cell in the used matrix for that benchmark:

```text
X1Y5.N1END0.LA_I0  -> LUT5F local PIP: LA_I0 <- N1END0
X3Y7.N1END0.LA_I0  -> LUT5F local PIP: LA_I0 <- N1END0

benchmark used matrix cell:
LA_I0 <- N1END0 = 1
```

This is important: the per-benchmark used matrix describes the tile type, not
one tile instance. It answers:

```text
Which local switch-matrix cells of this tile type were used anywhere in this routed benchmark?
```

The helper used by the inverse router is:

```python
used = document.used_switch_matrix_for_tile_type(
    "LUT5F",
    active_pip_value=1,
)
```

So each successful benchmark produces one used matrix:

```text
benchmark_0 FASM -> M0
benchmark_1 FASM -> M1
benchmark_2 FASM -> M2
```

The inverse router then adds those per-benchmark matrices element-wise. If a
cell appears in three benchmark-level used matrices, its score becomes `3`.

Example with three routed benchmarks:

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
```

The score matrix is:

```text
Score = M0 + M1 + M2

        A B C
  X   [ 2 2 1 ]
  Y   [ 1 2 0 ]
```

Interpretation:

```text
score 0: candidate existed, but no training route used it
score 1: used once
score 2: used twice
```

Pruning removes low-information cells:

```text
remove unused first: score == 0
then optionally remove used cells from lowest score upward
```

For example, with:

```python
switch_matrix_remove_unused_ratio=1.0
switch_matrix_remove_used_ratio=0.0
```

the `Y,C` cell is removed and every positive-score cell is kept:

```text
Final =
        A B C
  X   [ 1 1 1 ]
  Y   [ 1 1 0 ]
```

The values in the final matrix are not usage scores. They are active PIP values.
By default, kept cells are written with `switch_matrix_active_pip_value=1`.
If `switch_matrix_active_pip_value=None`, original delays are kept where they
are available.

## External-PIP Scoring

External PIPs are scored in the same spirit, but they are a list rather than a
2D matrix.

Example training routes:

```text
route0 uses: N1END0.N1BEG0, E1END0.E1BEG0
route1 uses: N1END0.N1BEG0
route2 uses: S1END0.S1BEG0
```

The score map becomes:

```text
N1END0.N1BEG0: 2
E1END0.E1BEG0: 1
S1END0.S1BEG0: 1
W1END0.W1BEG0: 0
```

The score-zero entry means the external PIP exists in the graph for that tile
type, but no successful training FASM used it.

External pruning also removes unused resources first, then optionally removes
used resources from the lowest score upward:

```python
external_remove_unused_ratio=1.0
external_remove_used_ratio=0.0
```

keeps all positive-score external PIPs and disables score-zero external PIPs
when `optimize_external_pips=True`.

## Applying Results

The inverse router can run as an evaluator or as an in-memory graph edit pass.

Switch matrix:

```python
optimize_switch_matrix=True
```

applies the final matrix with:

```python
fpga_model.set_switch_matrix(tile_name, columns, rows, matrix)
```

External PIPs:

```python
optimize_external_pips=True
```

disables selected external resources in the graph.

Neither mode writes tile CSV, list, Verilog, or generated source files. The
graph is modified in memory. Source writing remains an explicit user action.

## Example Pass

```python
self.pnr_inverse_router_pass(
    tile_name="LUT5F",
    training_benchmarks={
        "or17_chain": Path("tests/out/or17_chain.json"),
        "lut32_mixed": Path("tests/out/lut32_mixed.json"),
    },
    test_benchmarks={
        "adder": Path("tests/out/adder.json"),
    },
    io_seed_start=1,
    io_seed_count=4,
    optimize_switch_matrix=True,
    switch_matrix_remove_unused_ratio=1.0,
    switch_matrix_remove_used_ratio=0.0,
    switch_matrix_active_pip_value=1,
    optimize_external_pips=True,
    external_remove_unused_ratio=1.0,
    external_remove_used_ratio=0.0,
    validate_training=True,
    validate_test=True,
    nextpnr_exec=Path("/path/to/nextpnr-generic"),
    live_output=False,
    track_progress=True,
    progress_chunk_size=1,
)
```

This configuration is conservative: it removes unused switch-matrix cells and
unused external PIPs, but it does not remove any PIP that appeared in training.

## Pass Options

`tile_name`

Tile type to score and optionally modify, for example `"LUT5F"`.

`training_benchmarks`

Dictionary of benchmark name to packed design source. These benchmarks decide
the resource scores. Only successful routes with available FASM contribute to
scores.

`test_benchmarks`

Dictionary of benchmark name to packed design source. These are not used for
scoring. They are only routed after pruning when `validate_test=True`.

`io_seed_start`

First deterministic auto-PCF assignment seed. Must be positive.

`io_seed_count`

Number of deterministic IO assignment seeds per benchmark set. Must be
positive. With `io_seed_start=3` and `io_seed_count=2`, the pass uses seeds `3`
and `4`.

`optimize_switch_matrix`

If `True`, apply the final switch matrix to the graph. If `False`, still compute
and report `switch_matrix_score` and `final_switch_matrix`.

`switch_matrix_remove_unused_ratio`

Ratio of score-zero matrix PIPs to remove. `1.0` means remove all matrix PIPs
that were not observed in training.

`switch_matrix_remove_used_ratio`

Ratio of score-positive matrix PIPs to remove after unused pruning. Removal
starts at the lowest score. `0.0` is conservative. Values above `0.0` are
aggressive and should be validated carefully.

`switch_matrix_active_pip_value`

Value assigned to kept matrix cells in the final matrix. If this is an integer,
all kept cells use that value. If this is `None`, original graph delays are kept
where available.

`optimize_external_pips`

If `True`, disable selected external resources in the graph. If `False`, still
compute and report `external_scores`, `final_external_pips`, and
`removed_external_pips`.

`external_remove_unused_ratio`

Ratio of score-zero external PIPs to remove.

`external_remove_used_ratio`

Ratio of score-positive external PIPs to remove after unused pruning. Removal
starts at the lowest score.

`validate_training`

If `True`, rerun the training benchmarks after applying graph edits. Failed
routes are recorded in the result and report. They do not raise an exception.

`validate_test`

If `True`, route the test benchmarks after applying graph edits. Failed routes
are recorded in the result and report. They do not raise an exception.

`nextpnr_exec`

Optional path to `nextpnr-generic`. If omitted, the normal PnR bridge defaults
are used.

`extra_args`

Extra nextpnr command-line arguments forwarded to the route calls.

`live_output`

If `True`, stream nextpnr output while benchmarks route.

`track_progress`

If `True`, emit inverse-router progress messages.

`progress_chunk_size`

Number of route cases between progress updates.

## Result Fields

The pass instance stores an `InverseRouterResult` in:

```python
result = pass_instance.result_data
```

`training_routes`

Route records from the training collection phase. Each record contains benchmark
name, IO seed, phase, whether routing passed, whether FASM was available, and a
non-fatal error string if one occurred.

`training_validation_routes`

Route records from rerunning training benchmarks after graph edits.

`test_validation_routes`

Route records from routing test benchmarks after graph edits.

`switch_matrix_score`

`RoutingSwitchMatrix` whose values are usage counts from training FASM. This is
the importance metric for internal matrix PIPs.

`final_switch_matrix`

`RoutingSwitchMatrix` after pruning. This is the matrix that is applied when
`optimize_switch_matrix=True`.

`switch_matrix_stats`

Counts for matrix candidates, unused candidates, used candidates, removed
unused, removed used, and kept PIPs.

`external_scores`

Dictionary from tile-local external PIP name to training usage count.

`final_external_pips`

External PIP representatives kept after pruning. This list is useful as an
importance metric even when external optimization is disabled.

`removed_external_pips`

External PIP representatives selected for removal. These are disabled when
`optimize_external_pips=True`.

`external_stats`

Counts for external candidates, unused candidates, used candidates, removed
unused, removed used, and kept PIPs.

`report_summary`

Human-readable report with configuration, route counts, pruning counts, and
validation counts.

## Practical Guidance

Good default strategy:

```text
1. Start from a generous tile, often produced by pattern/full or another growth pass.
2. Run inverse routing on several training benchmarks and several IO seeds.
3. Remove unused resources only.
4. Validate with training and held-out test benchmarks.
5. Increase used-resource pruning only after the conservative run is stable.
```

The algorithm is only as representative as the training set. If a routing
pattern is never exercised by training FASM, it receives score `0`. That can be
exactly what you want for benchmark-specific optimization, but it is risky for a
general-purpose tile unless the test set is broad enough.
