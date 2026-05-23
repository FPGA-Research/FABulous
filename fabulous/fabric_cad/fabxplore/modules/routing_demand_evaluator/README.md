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
    opt_max_iterations=50,
    opt_clean_mux=False,
    opt_power_of_two_muxes=False,
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
    progress_chunk_size=10,
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
- `opt`: enable an optimizer. `False` is the normal evaluation mode.
- `optimizer`: optimizer name. Use `none` for evaluation only, `greedy` for
  deterministic demand-oracle pruning, or `monte_carlo` for sampled
  PIP-importance learning followed by checked pruning.
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
- `opt_max_iterations`: maximum optimizer iteration budget. For `greedy`, this
  is the maximum pruning attempts. For `monte_carlo`, this is used once for
  importance learning and again for checked pruning, so `1000` means up to
  `1000` temporary ablation evaluations plus up to `1000` pruning evaluations.
- `opt_clean_mux`: make optimizer pruning mux-aware. Instead of only ranking
  individual PIPs, the optimizer tries row batches that cross FABulous mux
  implementation buckets, such as `mux16 -> mux8` or `mux4 -> mux2`.
- `opt_power_of_two_muxes`: restrict pruning to mux-cleanup batches that move
  rows toward direct or power-of-two fanins. This option automatically enables
  `opt_clean_mux`. For `greedy` and `monte_carlo`,
  `opt_target_pip_reduction` remains an upper pruning budget: if no strict
  mux-cleanup batch fits the remaining budget, pruning stops early. If strict
  cleanup cannot produce a
  direct-or-power-of-two final matrix, write-back is skipped and the report
  lists the remaining non-power-of-two mux rows.
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
- `progress_chunk_size`: number of optimizer iterations between progress
  updates.

The optimizer target is based only on removable switch-matrix routing PIPs, not
on fixed JUMP wires:

$$
N_{targetRemove} =
\left\lceil
N_{routingPips,baseline} \cdot r_{target}
\right\rceil
$$

where $r_{target}$ is `opt_target_pip_reduction`. For example, a baseline with
$1329$ routing PIPs and `opt_target_pip_reduction=0.70` gives:

$$
\left\lceil 1329 \cdot 0.70 \right\rceil = 931
$$

That is the meaning of a progress line such as:

```text
[RoutingDemandEvaluator] Optimizer greedy start: target_removed_pips=931, max_iterations=300
```

## Greedy Optimizer

The `greedy` optimizer removes switch-matrix PIPs only when the demand oracle
accepts the candidate matrix. It never removes structural JUMP edges directly.
It only considers selectable matrix edges of the form:

$$
e = (\mathrm{source}, \mathrm{row})
$$

where `row` still has at least one other source after removal.

The optimizer first evaluates the baseline matrix and derives failure-rate
limits. If `opt_use_baseline_failure_rates=True`, the limits are relative to the
baseline:

$$
r_{hard,limit} =
r_{hard,baseline} + r_{hard,opt}
$$

$$
r_{soft,limit} =
r_{soft,baseline} + r_{soft,opt}
$$

If `opt_use_baseline_failure_rates=False`, the optimizer limits are absolute:

$$
r_{hard,limit} = r_{hard,opt}
$$

$$
r_{soft,limit} = r_{soft,opt}
$$

Each candidate batch is accepted only if:

$$
r_{hard,candidate} \le r_{hard,limit}
$$

and:

$$
r_{soft,candidate} \le r_{soft,limit}
$$

By default, candidate PIPs are ranked by current routed-path use. PIPs used by
hard demands are protected most strongly, PIPs used by soft demands are
protected next, and unused PIPs are tried first. A rejected non-mux batch is
split into smaller batches down to individual PIPs.

Rows with one source are direct wires. They have no select bits and no redundant
matrix choice to remove:

$$
f = 1 \Rightarrow b(f) = 0
$$

where $f$ is row fanin and $b(f)$ is the number of switch-matrix config bits for
that row. This is why terminal passthrough tiles can have routing PIPs but still
stop with `no_removable_pips`.

With `opt_clean_mux=True`, candidates are grouped by matrix row and by mux
bucket threshold. For a row with fanin $f$, the mux-aware target is:

$$
f_{target} = 2^{\lceil \log_2(f) \rceil - 1}
$$

for $f > 1$. This means the optimizer tries complete cleanup batches such as
$9 \rightarrow 8$, $7 \rightarrow 4$, $5 \rightarrow 4$, and
$3 \rightarrow 2$. These batches are accepted only when the demand oracle still
satisfies the configured failure-rate limits.

With `opt_power_of_two_muxes=True`, pruning is restricted to mux-cleanup
batches that move rows toward direct or power-of-two fanins. If the input matrix
already contains only direct or power-of-two mux rows, this mode preserves that
property because each accepted batch crosses to another allowed boundary. If
the input matrix already contains non-power-of-two fanin rows, the optimizer
tries to normalize those rows, for example `14 -> 8` or `7 -> 4`, and reports
how many remain.

The optimizer stops when it reaches `opt_target_pip_reduction`, reaches
`opt_max_iterations`, has no removable PIPs left, or cannot complete a requested
power-of-two mux cleanup under the configured limits.

With `opt_write_back=False`, the pass is report-only: it shows the optimized
candidate result but does not touch tile files. With `opt_write_back=True`, the
accepted matrix is written back to the active tile and dependent FABulous
artifacts are regenerated.

## Monte Carlo Optimizer

The `monte_carlo` optimizer is a two-phase optimizer. It first learns a
PIP-importance model using temporary ablations, then it prunes the matrix using
the learned weights and the same demand oracle used by the greedy optimizer.
Like `greedy`, it only removes switch-matrix routing PIPs and never removes
fixed JUMP wires directly.

### Phase 1: Importance Learning

During learning, the optimizer repeatedly samples a temporary batch $B$ of
matrix PIPs:

$$
B = \{e_1, e_2, \ldots, e_k\}
$$

It removes $B$ from a copy of the baseline matrix, evaluates the generated
demands, records the loss, and then restores the batch. No PIP is permanently
removed during this phase:

```text
remove temporary batch
run evaluator
measure loss
restore batch
update importance evidence
```

The current loss function is deliberately conservative:

$$
L =
1000 \Delta r_{hard}
+ 100 \Delta r_{soft}
+ 10 \Delta r_{failedSinks}
+ \Delta r_{path}
$$

where $\Delta r_{hard}$ and $\Delta r_{soft}$ are increases in hard and soft
failure rates relative to the baseline, $\Delta r_{failedSinks}$ is the
normalized increase in failed sinks, and $\Delta r_{path}$ is the normalized
increase in average routed path length. Hard-demand regressions dominate the
score because a hard failure means the matrix no longer satisfies an essential
structural check.

The importance learner is internal and modular. The default learner is a
gradient-style learner; an average-difference learner is kept in the same
module as a simple fallback/comparison implementation. Both implement the same
contract:

```text
observe(batch, loss)
penalize(rejected_batch, loss)
scores()
```

The default gradient learner predicts batch loss as the sum of PIP weights:

$$
\hat{L}_B = \sum_{e \in B} w(e)
$$

Then it compares predicted loss with measured loss and distributes the update
across the PIPs in the removed batch:

$$
w(e) \leftarrow
\max\left(
0,
w(e) + \eta \frac{L_B - \hat{L}_B}{|B|}
\right)
\quad\text{for each } e \in B
$$

Only PIPs in the temporary batch receive a direct update. A low $w(e)$ means the
PIP often appears in temporary removals without causing extra loss. A high
$w(e)$ means the PIP tends to appear in high-loss removals and should be
protected.

For example, assume a temporary batch contains three PIPs:

```text
B = {A, B, C}
```

and the current weights are:

```text
w(A)=2.0, w(B)=1.0, w(C)=0.0
```

The predicted batch loss is:

$$
\hat{L}_B = 2.0 + 1.0 + 0.0 = 3.0
$$

If the evaluator measures an actual loss of:

$$
L_B = 12.0
$$

then the prediction was too small by:

$$
12.0 - 3.0 = 9.0
$$

With learning rate $\eta = 0.25$, the update distributed over the three
temporary removals is:

$$
\frac{0.25 \cdot 9.0}{3} = 0.75
$$

so the new weights become:

```text
w(A)=2.75, w(B)=1.75, w(C)=0.75
```

If later batches containing `A` continue to produce high loss, `A` keeps rising.
If batches containing `C` usually do not hurt, `C` stays low or is pulled less
often into accepted pruning candidates.

This gradient form is useful because it is online, cheap, and works naturally
with partial evidence. The optimizer does not need to store every past sample or
recompute all PIP scores from scratch after every observation. It also lets
rejected pruning batches directly increase the weights of the PIPs that caused
the rejected candidate. That is why the gradient learner is the default: it is
not a proof of true global importance, but it is a practical estimator that
adapts as the demand oracle gives more evidence.

When a batch has much higher loss than the running average, Monte Carlo also
splits that batch into smaller attribution batches and evaluates those pieces
while learning budget remains. This gives high-loss batches better attribution:
one critical PIP should not permanently poison a whole otherwise-safe group.

The average-difference learner computes the older score:

$$
w(e) =
\max\left(
0,
\overline{L \mid e \in B}
-
\overline{L \mid e \notin B}
\right)
$$

It is useful because it is stable and easy to reason about, but the default
gradient learner is more direct for online updates and rejected-batch feedback.

Learning samples use small shuffled sliding windows. The optimizer builds the
removable routing-PIP list, shuffles it, removes a small fixed-size window
temporarily, then advances the window. When the end of the shuffled list is
reached, it shuffles again and starts a new pass:

```text
shuffle removable PIPs
try PIPs[0:batch]
try PIPs[batch:2*batch]
...
reshuffle and repeat
```

One full shuffled pass is called an epoch. During the first epoch, Monte Carlo
forces sliding-window batches until every removable PIP has been sampled at
least once. After `unsampled_pips` reaches zero, the remaining learning budget
is used for refinement: the sampler continues with new shuffled epochs and may
mix in mux-threshold batches when mux cleanup is enabled.

This is intentionally different from sampling huge random batches. If too many
PIPs are removed at once, the loss almost always gets worse and the optimizer
learns little about which individual PIP caused the regression. Small windows
give each PIP direct evidence, avoid repeatedly testing only nearby row-local
connections, and make the importance matrix converge more globally. The batch
size and related tuning constants live in an internal Monte Carlo hyperparameter
dataclass; they are not public pass options.

### Why This Is Not Shapley

The Monte Carlo optimizer uses sampled batch ablation around the baseline
matrix. Its learning question is:

```text
How much does the demand oracle get worse when these PIPs are temporarily
removed from the current full matrix?
```

That is the right question for checked pruning, because the optimizer starts
from a complete matrix and wants to remove PIPs safely.

This is related to Shapley-style importance, but it is not the same estimator.
Exact Shapley values ask for the average marginal contribution of one player
over all possible contexts:

$$
\phi(e) =
\sum_{S \subseteq P \setminus \{e\}}
\frac{|S|!(|P|-|S|-1)!}{|P|!}
\left(
V(S \cup \{e\}) - V(S)
\right)
$$

For loss, where smaller is better, the marginal can be written as:

$$
\Delta_e = L(S) - L(S \cup \{e\})
$$

If adding PIP $e$ reduces loss, the marginal is positive. If adding it makes
loss worse, the marginal is negative.

A Monte Carlo Shapley approximation samples random build-up orders:

```text
score = {pip: 0}

for sampled order in random_permutations(PIPs):
    S = empty_matrix_or_partial_matrix()
    old_loss = loss(S)

    for pip in sampled order:
        add pip to S
        new_loss = loss(S)
        score[pip] += old_loss - new_loss
        old_loss = new_loss
```

For a tiny example with three PIPs:

```text
loss({})        = 100
add A -> loss  = 70    A gets 100 - 70 = 30
add B -> loss  = 60    B gets 70 - 60  = 10
add C -> loss  = 20    C gets 60 - 20  = 40
```

Another random order may give different marginal values. The Shapley estimate
is the average over many random orders.

The computational difference is large. The current Monte Carlo learner costs
approximately:

$$
N_{learn} = \texttt{opt\_max\_iterations}
$$

temporary demand-oracle evaluations. With `opt_max_iterations=400`, that is
about 400 learning evaluations.

Monte Carlo Shapley costs approximately:

$$
N_{shapley} = N_{permutations} \cdot N_{PIPs}
$$

For LUT4AB with 1329 routing PIPs:

```text
10 sampled orders   -> about 13,290 evaluator runs
100 sampled orders  -> about 132,900 evaluator runs
1000 sampled orders -> about 1,329,000 evaluator runs
```

Exact Shapley would be far larger because it averages over all subsets of PIPs.
That is not practical with a demand router in the loop.

There is also an architectural reason to prefer baseline ablation here. Many
partial matrices in a Shapley build-up order are not meaningful FABulous routing
architectures: they may have empty mux rows, broken hierarchy, or no useful path
structure. The optimizer's actual task is not to value PIPs in arbitrary partial
matrices; it is to decide which PIPs can be removed from the existing matrix
while preserving the configured demand oracle.

So the honest description is:

```text
Monte Carlo batch-ablation importance, followed by checked pruning.
```

It is a practical approximation of removal sensitivity under the selected
demand profile, not an exact Shapley-value computation.

The live progress log reports the current epoch:

```text
epoch=2, epoch_pips=128/1248
```

Here `epoch` is the current shuffled pass and `epoch_pips` is how many
removable PIPs have been consumed in that pass. This makes it clear whether the
optimizer is still in first-coverage learning or already refining weights.

The report shows:

- sampled PIPs
- unsampled PIPs
- sampled PIP rate
- minimum, average, and maximum samples per removable PIP

These coverage numbers explain the reliability of the importance matrix. A zero
importance value on a well-sampled PIP means the optimizer did not observe loss
from removing it. A zero importance value on an unsampled PIP only means there
was no evidence yet.

Learning stops after `opt_max_iterations` temporary ablation evaluations. The
optimizer does not currently stop early on convergence. It still reports a
weight-change indicator:

$$
\Delta_w =
\frac{
\frac{1}{N}\sum_i |w_i^{new} - w_i^{old}|
}{
\epsilon + \frac{1}{N}\sum_i |w_i^{new}|
}
$$

When $\Delta_w$ trends toward zero, the importance weights are becoming more
stable. This is a diagnostic only; it is not a stop condition.

### Phase 2: Checked Pruning

After learning, the optimizer ranks candidate PIP batches by low importance and
high implementation value. A candidate batch is still accepted only if the full
demand oracle remains inside the configured limits:

$$
r_{hard,candidate} \le r_{hard,limit}
$$

and:

$$
r_{soft,candidate} \le r_{soft,limit}
$$

If a supposedly low-risk pruning batch fails the oracle, the optimizer restores
the batch, marks it rejected, and increases the score of the PIPs in that batch.
This feeds pruning feedback back into the importance model:

$$
w(e) \leftarrow w(e) + \frac{\max(L_B, 1)}{|B|}
\quad\text{for each } e \in B
$$

This matters because a high-loss batch does not prove every PIP in the batch is
bad. Overlapping samples and rejected-batch feedback make the attribution more
robust: PIPs that repeatedly appear in bad combinations become expensive, while
PIPs that appear in safe combinations stay cheap.

Rejected pruning batches are also split adaptively while pruning budget remains:

```text
try full low-importance batch
if rejected:
    penalize the batch
    split by learned importance
    retry smaller pieces
```

This prevents one critical PIP from blocking a whole otherwise-safe batch. Near
the configured hard/soft failure-rate limits, Monte Carlo becomes more cautious
and shrinks non-power-of-two candidate batches before evaluating them. This helps
avoid accepting large removals that barely fit inside the limits.

With `opt_clean_mux=True`, Monte Carlo ranks row-local mux cleanup batches by
importance and mux/config-bit savings. With `opt_power_of_two_muxes=True`, this
mux-aware mode is enabled automatically and pruning is restricted to strict
mux-cleanup batches that target direct or power-of-two fanins. In this strict
mode, the PIP reduction target is an upper budget, not a lower bound. The
optimizer may stop below the requested reduction if the next strict mux-cleanup
batch would exceed the remaining budget:

```text
target_removed_pips = 195
accepted_pips       = 188
next legal batch    = 8 PIPs
stop instead of removing 196 PIPs
```

This means a run with `opt_target_pip_reduction=0.25` can legitimately finish at
`0.02` if only 2% can be removed while preserving the strict mux constraint and
the demand limits. Rejected strict mux-cleanup batches are not partially
accepted, because a partial split can turn a legal row such as `mux16` into an
illegal row such as `mux12`. If the input matrix already contains
non-power-of-two rows and they cannot all be normalized inside the pruning
budget and demand limits, write-back is skipped and the report warns that
non-power-of-two rows remain.

With `opt_write_back=True`, Monte Carlo also writes a PIP importance matrix:

```text
<tile_name>_pip_importance.txt
```

The file uses a CSV-shaped table but the extension is `.txt`. Rows are matrix
destination rows, columns are matrix sources, and each populated cross point is
the learned importance value for that PIP. The same matrix is also available in
the structured optimizer result as `optimizer_stats.pip_importance_matrix`.
Markdown reports show only the filename to keep the optimization and importance
tables narrow; the structured result keeps the full path.

## Mux And Config-Bit Math

The report separates routing graph size from implementation cost.

The number of selectable switch-matrix PIPs is:

$$
N_{routingPips} = \sum_{row \in R} f(row)
$$

where $f(row)$ is the number of sources in a matrix row. JUMP wires are reported
separately because they are fixed hierarchy edges, not optimizer-removable mux
choices:

$$
N_{graphEdges} = N_{routingPips} + N_{jumpWires}
$$

The switch-matrix config-bit cost of one row is:

$$
b(f) =
\begin{cases}
0 & f \le 1 \\
\lceil \log_2(f) \rceil & f > 1
\end{cases}
$$

The matrix config-bit count is:

$$
B_{matrix} = \sum_{row \in R} b(f(row))
$$

The report also shows a mux bucket cost used for cleanup analysis:

$$
m(f) =
\begin{cases}
0 & f \le 1 \\
2^{\lceil \log_2(f) \rceil} & f > 1
\end{cases}
$$

This cost approximates the implementation bucket selected by FABulous. Removing
one PIP from a `mux16` row may save no implementation cost if it remains in the
same bucket, while reducing a row from `mux16` to `mux8` saves one select bit
and one mux bucket level. That is why mux-aware pruning is often more useful
than raw PIP pruning when the goal is area or config-bit reduction.

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

## Tile Applicability Detection

Demand classes only generate checks when the tile exposes matching terminals and
graph structure. If a class cannot find the terminals it needs, it reports:

```text
Demand class generated no demands: <class> (not applicable or no classified terminals matched)
```

This is not a failure by itself. It means the tile is not expected to support
that feature according to the loaded FABulous metadata.

For a terminal passthrough tile such as `N_term_single`, the pass detects that
the tile has no BEL inputs, no BEL outputs, no control metadata, no carry chain,
and no muxed switch rows. The generated matrix contains only direct passthrough
rows:

```text
S1BEG0 <- N1END3
S1BEG1 <- N1END2
S1BEG2 <- N1END1
S1BEG3 <- N1END0
...
```

For that tile, a report like this is expected:

```text
hard demands passed: 74 / 74
soft demands passed: 0 / 89
original routing PIPs: 52
final routing PIPs: 52
generated matrix config bits: 0
stop reason: no_removable_pips
```

The hard checks pass because the required passthrough rows exist. The soft
stress checks fail because the tile is intentionally not a general-purpose
routing tile. For example, `N1END1 -> N1END0` is not a valid passthrough; the
tile routes `N1END1 -> S1BEG2`.

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
- `fanin_diversity`
- `source_fanout_diversity`
- `side_pair_balance`
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
- `fanin_diversity`
- `source_fanout_diversity`
- `side_pair_balance`
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

`fanin_diversity`

Checks rows that originally have multiple selectable sources by probing each
alternative source into that row. This catches optimizations that preserve a row
but collapse too much input choice.

`source_fanout_diversity`

Checks sources that originally feed multiple rows by probing each source-to-row
choice. This catches optimizations that keep a source useful for one route but
remove most of its matrix fanout.

`side_pair_balance`

Checks ordered side-to-side routing coverage, for example north-to-east,
north-to-south, east-to-north, and so on. It generates one soft probe per
available ordered cardinal side pair, which helps reveal matrices that preserve
some turns while starving other directions.

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

## Reading A LUT4AB Report

The following block is an aggressive `LUT4AB` full-profile optimizer report. It
is useful because it shows all major concepts at once: baseline graph size,
optimized graph size, write-back config bits, hard/soft demand rates, mux
cleanup, and skipped feature-specific classes.

```text
Tile: LUT4AB
Directory: /home/hausding/Documents/FABulous/demo0/Tile/LUT4AB
Switch matrix: /home/hausding/Documents/FABulous/demo0/Tile/LUT4AB/LUT4AB_switch_matrix.list

## Summary
- status: FAIL
- opt: True
- optimizer: greedy
- demand_profile: full
- router: pathfinder
- demands: 553
- hard demands passed: 162 / 209 (77.51%)
- hard demands failed: 47 / 209
- hard failure rate: 22.49%
- soft demands passed: 59 / 344 (17.15%)
- soft demands failed: 285 / 344
- failed sinks: 464
- soft failure rate: 82.85%
- original routing PIPs: 1329
- final routing PIPs: 275
- jump wires: 98
- original routing graph edges: 1427
- final routing graph edges: 373
- generated matrix config bits: 462
- generated total config bits: 616 / 640
- average routed sink path length: 2.08

## Optimization
| Metric                               |             Value |
| ------------------------------------ | ----------------: |
| optimizer                            |            greedy |
| write back                           |              True |
| baseline routing PIPs                |              1329 |
| final routing PIPs                   |               275 |
| removed routing PIPs                 |              1054 |
| baseline matrix config bits          |               462 |
| written optimized matrix config bits |                 0 |
| baseline total config bits           |               616 |
| written optimized total config bits  |               154 |
| routing PIP reduction                |            79.31% |
| target routing PIP reduction         |            90.00% |
| baseline hard failure rate           |             0.00% |
| final hard failure rate              |            22.49% |
| allowed hard failure rate            |            90.00% |
| baseline soft failure rate           |             5.23% |
| final soft failure rate              |            82.85% |
| allowed soft failure rate            |            95.23% |
| iterations                           |               462 |
| accepted batches                     |               462 |
| rejected batches                     |                 0 |
| accepted routing PIPs                |              1054 |
| rejected routing PIPs                |                 0 |
| stop reason                          | no_removable_pips |

## Mux Cleanup
| Metric                       |                    Value |
| ---------------------------- | -----------------------: |
| mux objective                | power-of-two mux cleanup |
| baseline mux cost            |                     1248 |
| final mux cost               |                        0 |
| mux cost reduction           |                  100.00% |
| threshold crossings          |                      194 |
| direct-wire conversions      |                      194 |
| matrix config bits saved     |                      462 |
| non-power-of-two rows before |                        0 |
| non-power-of-two rows after  |                        0 |

### Mux Buckets
| Bucket | Before | After | Delta |
| ------ | -----: | ----: | ----: |
| direct |     81 |   275 |  +194 |
| mux2   |     16 |     0 |   -16 |
| mux4   |    124 |     0 |  -124 |
| mux8   |     18 |     0 |   -18 |
| mux16  |     36 |     0 |   -36 |

## Failed Demand Examples
- bel_output_escape_0 (bel_output_escape): LA_O -> JN2BEG1; reason=unreachable
- bel_input_source_coverage_50 (bel_input_source_coverage): Ci0 -> LA_I0; reason=unreachable
- matrix_row_coverage_120 (matrix_row_coverage): E1END2 -> J2MID_ABa_BEG2; reason=unreachable
- local_feedback_197 (local_feedback): LA_O -> LA_I0; reason=unreachable
- random_local_0 (random_local): LA_O -> LD_I0; reason=unreachable

## Warnings
- Demand class generated no demands: control_reachability (not applicable or no classified terminals matched)
- Demand class generated no demands: control_net (not applicable or no classified terminals matched)
- Demand class generated no demands: carry_chain (not applicable or no classified terminals matched)
- Demand class generated no demands: dsp_ram_access (not applicable or no classified terminals matched)
- Demand class generated no demands: io_access (not applicable or no classified terminals matched)
```

This report says the optimizer made the tile extremely small: it reduced
selectable routing PIPs from $1329$ to $275$ and converted every switch-matrix
row into a direct wire. The switch matrix therefore has:

$$
B_{matrix,final} = 0
$$

The written optimized tile uses $154$ total config bits, down from the baseline
$616$. The $154$ remaining bits belong to non-switch-matrix tile logic, not to
the routing matrix.

The report status is still `FAIL` because hard failures are not zero:

$$
r_{hard} = \frac{47}{209} = 22.49\%
$$

That is acceptable only because this was an intentionally aggressive optimizer
experiment with `allowed hard failure rate = 90.00%`. For normal tile-quality
checking, `opt_max_hard_failure_rate` should usually stay at `0.0`.

The failed examples are exact graph statements. For example:

```text
LA_O -> JN2BEG1
```

means there is no directed path from `LA_O` to `JN2BEG1` in the generated graph
after optimization. It does not mean `LA_O` is useless; it means this exact
source/sink combination is not supported by the optimized matrix.

The warning block is also meaningful. Even though names such as `SR`, `EN`,
`Ci`, or `Co` can appear in Verilog or matrix files, the evaluator does not
classify them as control or carry unless FABulous metadata or tile CSV
annotations say so. Therefore `control_net` and `carry_chain` can correctly
generate no demands for a tile that has those names but not those semantic
roles.

When the optimizer is `monte_carlo`, the same report also contains learning
rows in the `Optimization` section:

```text
learning iterations
pruning iterations
sampled batches
importance rounds
average sample loss
max sample loss
weight change rate
sampled PIPs
unsampled PIPs
sampled PIP rate
min / avg / max samples per PIP
PIP importance file
```

These rows separate temporary learning work from permanent pruning work. A
large `learning iterations` value means many temporary ablations were evaluated
against the baseline matrix. A large `pruning iterations` value means many
low-importance batches were checked against the demand oracle after learning.
The `PIP Importance` section lists the highest-scored PIPs, and the
`PIP importance file` points at the full CSV-shaped `.txt` matrix when
`opt_write_back=True`.

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
