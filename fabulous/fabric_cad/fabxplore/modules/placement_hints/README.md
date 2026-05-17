# Placement Hints

The placement-hints pass adds non-functional attributes to existing cells. It
does not map logic, replace cells, or require changes in earlier mapping passes.
The first supported rule detects linear chains.

```text
tile0.Co -> tile1.Ci -> tile2.Ci
```

becomes:

```text
tile0: FAB_CLUSTER_ID=carry_0, FAB_CLUSTER_INDEX=0, FAB_CLUSTER_SIZE=3
tile1: FAB_CLUSTER_ID=carry_0, FAB_CLUSTER_INDEX=1, FAB_CLUSTER_SIZE=3
tile2: FAB_CLUSTER_ID=carry_0, FAB_CLUSTER_INDEX=2, FAB_CLUSTER_SIZE=3
```

## Interface

```python
self.design_placement_hints_pass(
    rules=[
        {
            "kind": "linear_chain",
            "name": "carry",
            "cell_types": ["FLUT5_1P_2PS"],
            "source_port": "Co",
            "sink_port": "Ci",
            "min_length": 2,
            "allow_branching": False,
            "allow_single_stage": False,
        },
    ],
    attribute_prefix="FAB_CLUSTER",
    overwrite_existing=False,
    fail_on_conflict=True,
    top_name=None,
    track_progress=True,
    progress_chunk_size=100,
)
```

## Emitted Attributes

With the default prefix, each clustered cell receives:

- `FAB_CLUSTER_KIND`: structural rule kind, currently `linear_chain`.
- `FAB_CLUSTER_NAME`: user rule name, for example `carry`.
- `FAB_CLUSTER_ID`: unique cluster name such as `carry_0`.
- `FAB_CLUSTER_ROLE`: cell role, currently `stage`.
- `FAB_CLUSTER_INDEX`: zero-based stage index.
- `FAB_CLUSTER_SIZE`: number of stages in the cluster.

The pass is intentionally generic. The same `linear_chain` rule can describe
carry chains, register pipelines, or any other sequence of tiles connected from
one source port to one sink port.
