# FABulous Routing Graph

`fab_graph` is the public routing-fabric editing API for FABulous projects.  It
loads a parsed FABulous fabric into a tile-type based routing graph, lets users
and optimizers edit routing resources in memory, and writes either a lightweight
`pips.txt` for nextpnr experiments or a complete regenerated FABulous project.
The interface is inspired by the global routing graph objects used in VTR/VPR:
optimizers work on one typed routing model instead of directly rewriting many
tile CSV/list files during exploration.

The graph edits architecture resources, not single placed PIP instances.  If a
matrix row or external wire is changed for tile type `LUT4AB`, the change applies
to every placed `LUT4AB` tile.

## Basic Setup

```python
from pathlib import Path

from fabulous.fabulous_api import FABulous_API
from fabulous.fabric_definition.define import Direction
from fabulous.fabric_generator.code_generator.code_generator_Verilog import (
    VerilogCodeGenerator,
)
from fabulous.fabric_cad.fabxplore.pnr.fab_graph import (
    FabGraph,
    RoutingPipKind,
)

project_dir = Path("demo_opt")

fab = FABulous_API(VerilogCodeGenerator())
fab.loadFabric(project_dir / "fabric.csv")

graph = FabGraph(fab, project_dir)
```

## Public Functions

Construction and graph access:

- `FabGraph(fabulous_api, project_dir, routing_graph=None)`
- `FabGraph.from_routing_graph(fabulous_api, project_dir, routing_graph)`
- `routing_graph`

Queries and rendering:

- `stats()`
- `get_config_bits(tile_type=None)`
- `get_resource_counts(tile_type=None)`
- `tile_types(where=None)`
- `placed_tile_types(where=None)`
- `standalone_tile_types(where=None)`
- `tile_model(tile_type)`
- `external_resources(tile_type=None, active_only=True, where=None)`
- `matrix_resources(tile_type=None, active_only=True, where=None)`
- `matrix_sources(tile_type, where=None)`
- `matrix_sinks(tile_type, where=None)`
- `active_pips(where=None)`
- `disabled_pips(where=None)`
- `render_pips_txt()`

Add and modify:

- `add_external_resource(...)`
- `add_matrix_resource(...)`
- `add_matrix_rows(tile_type, entries, overwrite=False)`
- `resize_external_resource(..., new_wire_count, key=None)`

Delete and disable:

- `delete_external_resource(..., key=None)`
- `disable_external_resource(..., key=None)`
- `delete_matrix_resource(..., key=None)`
- `disable_matrix_resource(..., key=None)`

Restore and enable:

- `restore_external_resource(..., key=None)`
- `enable_external_resource(..., key=None)`
- `restore_matrix_resource(..., key=None)`
- `enable_matrix_resource(..., key=None)`

Write-back:

- `write_pips_txt(output_path)`
- `write_pips(path=None)`
- `write_tile(name, path)`
- `write_project(path=None, generate_rtl=True)`
- `write_tile_sources(output_root=None, tile_types=None, remove_generated_artifacts=True)`

## Public API Examples

### `FabGraph(...)`

Create a public graph facade from a loaded FABulous API object.

```python
graph = FabGraph(fab, project_dir)
```

### `FabGraph.from_routing_graph(...)`

Wrap an existing low-level routing graph without rebuilding it.

```python
raw_graph = graph.routing_graph
wrapped = FabGraph.from_routing_graph(fab, project_dir, raw_graph)
```

### `routing_graph`

Access the lower-level graph when implementing advanced tooling.  Most user code
should stay on the `FabGraph` facade.

```python
raw_graph = graph.routing_graph
raw_graph.validate()
```

### `stats()`

Materialize graph statistics.  This walks the lazy PIP model, so use it for
reporting, not inside tight edit loops.

```python
stats = graph.stats()
print(stats.active_pips, stats.external_pips, stats.internal_pips)
```

### `get_config_bits(tile_type=None)`

Return current configuration-bit counts.  Matrix bits are recomputed from active
switch-matrix rows, so adding, deleting, restoring, overwriting, or resizing
routing resources is reflected immediately.  Fixed bits are taken from the
preserved BEL metadata.

```python
lut_bits = graph.get_config_bits("LUT4AB")
print(lut_bits.matrix_config_bits)
print(lut_bits.fixed_config_bits)
print(lut_bits.total_config_bits)
```

Without a tile type, the method returns a dictionary keyed by tile type.

```python
bits_by_tile = graph.get_config_bits()
for tile_type, bits in bits_by_tile.items():
    print(tile_type, bits.total_config_bits)
```

### `get_resource_counts(tile_type=None)`

Return cheap tile-local resource counts without materializing concrete PIPs.  Use
this inside optimizer loops when you want to know how many external CSV rows or
matrix rows are active/disabled.

```python
counts = graph.get_resource_counts("LUT4AB")
print(counts.external_active)
print(counts.matrix_active)
print(counts.total_active)
```

Without a tile type, the method returns a dictionary keyed by tile type.

```python
counts_by_tile = graph.get_resource_counts()
for tile_type, counts in counts_by_tile.items():
    print(tile_type, counts.total_active, counts.total_disabled)
```

### `tile_types(where=None)`

List all known tile types, optionally filtered by a callable.  This includes
placed grid tile types and standalone tile declarations.

```python
lut_tile_types = graph.tile_types(
    where=lambda tile_type: tile_type.startswith("LUT"),
)
```

### `placed_tile_types(where=None)`

List tile types that have at least one placed grid instance and therefore can
emit concrete routing PIPs.

```python
for tile_type in graph.placed_tile_types():
    print(tile_type, graph.get_resource_counts(tile_type).total_active)
```

### `standalone_tile_types(where=None)`

List declared tile types that are not placed in the fabric grid.  These tile
models can be queried and edited, but they do not emit concrete routing PIPs.

```python
for tile_type in graph.standalone_tile_types():
    matrix = graph.switch_matrix(tile_type)
    print(tile_type, len(matrix.rows), len(matrix.columns))
```

### `tile_model(tile_type)`

Read preserved tile metadata such as source paths, BELs, ports, and matrix file
information.

```python
lut_model = graph.tile_model("LUT4AB")
print(lut_model.tile_csv_path)
print([bel.module_name for bel in lut_model.bels])
```

### `external_resources(tile_type=None, active_only=True, where=None)`

Query external CSV-style routing resources.  Returned values are
`RoutingResourceKey` objects that can be passed back with `key=`.

```python
east_vectors = graph.external_resources(
    "LUT4AB",
    where=lambda key: key.direction is Direction.EAST and key.wire_count >= 4,
)

for key in east_vectors:
    graph.resize_external_resource(key=key, new_wire_count=key.wire_count - 1)
```

Use `active_only=False` to include disabled resources.

```python
all_external = graph.external_resources("LUT4AB", active_only=False)
```

### `matrix_resources(tile_type=None, active_only=True, where=None)`

Query switch-matrix rows.  These keys can be used for delete/restore operations.

```python
lut_input_rows = graph.matrix_resources(
    "LUT4AB",
    where=lambda key: key.destination_name.startswith("LA_I"),
)

for key in lut_input_rows[:10]:
    graph.delete_matrix_resource(key=key)
```

### `matrix_sources(tile_type, where=None)`

List valid source wire names for a tile matrix.

```python
east_sources = graph.matrix_sources(
    "LUT4AB",
    where=lambda name: name.startswith("E"),
)
```

### `matrix_sinks(tile_type, where=None)`

List valid sink wire names for a tile matrix.

```python
lut_sinks = graph.matrix_sinks(
    "LUT4AB",
    where=lambda name: name.startswith("LA_I"),
)
```

### `active_pips(where=None)`

Materialize active concrete nextpnr PIPs.  This is useful for inspection, but it
is fabric-wide work.

```python
external_pips = graph.active_pips(
    where=lambda pip: pip.kind is RoutingPipKind.EXTERNAL_WIRE,
)

print(external_pips[0].render())
```

### `disabled_pips(where=None)`

Materialize concrete PIPs produced by disabled resources.

```python
disabled_lut_pips = graph.disabled_pips(
    where=lambda pip: pip.tile_type == "LUT4AB",
)
```

### `render_pips_txt()`

Render active concrete PIPs in FABulous/nextpnr `pips.txt` format.

```python
pips_text = graph.render_pips_txt()
assert "X" in pips_text
```

### `add_external_resource(...)`

Add a tile CSV-style external wire resource.  This declares the wire vector; it
does not automatically add switch-matrix rows that consume the new wire.

```python
graph.add_external_resource(
    tile_type="LUT4AB",
    direction=Direction.EAST,
    source_name="E1BEG",
    x_offset=1,
    y_offset=0,
    destination_name="E1END",
    wire_count=4,
)
```

### `add_matrix_resource(...)`

Add one switch-matrix row for a tile type.

```python
graph.add_matrix_resource(
    tile_type="LUT4AB",
    source_name="E1END0",
    destination_name="LA_I0",
)
```

### `add_matrix_rows(tile_type, entries, overwrite=False)`

Add several switch-matrix rows.  Entries are `(source, destination, delay)`
triplets.

```python
graph.add_matrix_rows(
    "LUT4AB",
    [
        ("E1END0", "LA_I0", 8.0),
        ("E1END1", "LA_I0", 8.0),
        ("N1END0", "LA_I1", 8.0),
    ],
)
```

Use `overwrite=True` to replace the active matrix for that tile type.

```python
graph.add_matrix_rows(
    "LUT4AB",
    [
        ("S1END0", "LA_I0", 8.0),
        ("S1END1", "LA_I1", 8.0),
    ],
    overwrite=True,
)
```

### `delete_external_resource(..., key=None)`

Disable an external resource.  External deletion can cascade and disable matrix
rows that reference removed wires.

```python
key = graph.external_resources(
    "LUT4AB",
    where=lambda key: key.direction is Direction.EAST and key.source_name == "E1BEG",
)[0]

graph.delete_external_resource(key=key)
```

The same operation can be expressed with parameters.

```python
graph.delete_external_resource(
    tile_type="LUT4AB",
    direction=Direction.EAST,
    source_name="E1BEG",
    x_offset=1,
    y_offset=0,
    destination_name="E1END",
    wire_count=4,
)
```

### `disable_external_resource(..., key=None)`

Alias for `delete_external_resource`.

```python
key = graph.external_resources("LUT4AB")[0]
graph.disable_external_resource(key=key)
```

### `delete_matrix_resource(..., key=None)`

Disable one switch-matrix row.

```python
key = graph.matrix_resources(
    "LUT4AB",
    where=lambda key: key.source_name == "E1END0"
    and key.destination_name == "LA_I0",
)[0]

graph.delete_matrix_resource(key=key)
```

The parameter form is equivalent.

```python
graph.delete_matrix_resource(
    tile_type="LUT4AB",
    source_name="E1END0",
    destination_name="LA_I0",
)
```

### `disable_matrix_resource(..., key=None)`

Alias for `delete_matrix_resource`.

```python
key = graph.matrix_resources("LUT4AB")[0]
graph.disable_matrix_resource(key=key)
```

### `restore_external_resource(..., key=None)`

Restore a disabled external resource if it is valid in the current tile model.

```python
key = graph.external_resources("LUT4AB")[0]
graph.delete_external_resource(key=key)
graph.restore_external_resource(key=key)
```

### `enable_external_resource(..., key=None)`

Alias for `restore_external_resource`.

```python
key = graph.external_resources("LUT4AB")[0]
graph.disable_external_resource(key=key)
graph.enable_external_resource(key=key)
```

### `restore_matrix_resource(..., key=None)`

Restore a disabled switch-matrix row.

```python
key = graph.matrix_resources("LUT4AB")[0]
graph.delete_matrix_resource(key=key)
graph.restore_matrix_resource(key=key)
```

### `enable_matrix_resource(..., key=None)`

Alias for `restore_matrix_resource`.

```python
key = graph.matrix_resources("LUT4AB")[0]
graph.disable_matrix_resource(key=key)
graph.enable_matrix_resource(key=key)
```

### `resize_external_resource(..., new_wire_count, key=None)`

Resize an external wire vector.  Shrinking removes high-index lanes first.
Growing declares additional external PIPs, but does not add matrix rows.

```python
key = graph.external_resources(
    "LUT4AB",
    where=lambda key: key.source_name == "E1BEG" and key.wire_count == 4,
)[0]

graph.resize_external_resource(key=key, new_wire_count=2)
```

Resource keys are immutable and include `wire_count`, so query again after a
resize if you need the current key.

```python
resized_key = graph.external_resources(
    "LUT4AB",
    where=lambda key: key.source_name == "E1BEG" and key.wire_count == 2,
)[0]
```

### `write_pips_txt(output_path)`

Write active PIPs to one explicit `pips.txt` path.

```python
graph.write_pips_txt("runs/candidate_001/.FABulous/pips.txt")
```

### `write_pips(path=None)`

Write only `pips.txt`.  This is the lightweight path for nextpnr-driven optimizer
loops.

```python
graph.write_pips()
graph.write_pips("runs/candidate_001/.FABulous")
graph.write_pips("runs/candidate_001/.FABulous/pips.txt")
```

### `write_tile(name, path)`

Write one standalone tile source directory.  Both arguments are required.

```python
graph.write_tile("LUT4AB", "/tmp/LUT4AB_debug")
```

### `write_project(path=None, generate_rtl=True)`

Write a complete FABulous project.  If `path` is omitted, the current project is
updated in place.  If `path` is provided, a new project is written there.

```python
graph.write_project("/tmp/fabulous_candidate", generate_rtl=True)
```

The project writer regenerates tile CSV/list files, generated RTL, and
`.FABulous` metadata such as `pips.txt`, `bel.txt`, `bel.v2.txt`,
`template.pcf`, and bitstream specs.

### `write_tile_sources(output_root=None, tile_types=None, remove_generated_artifacts=True)`

Write tile source files without regenerating the whole project.  This is mainly
useful for writer tests and custom flows.

```python
result = graph.write_tile_sources(
    output_root="/tmp/tile_sources",
    tile_types=["LUT4AB"],
)

for tile_result in result.tile_results:
    print(tile_result.tile_csv_path)
```

## Resource Semantics

FABulous routing resources are owned by tile type.  If a resource is changed on
tile type `LUT4AB`, that change applies to every placed `LUT4AB` instance.
Declared tile types that are not placed in the fabric grid are still loaded as
standalone tile models.  They can be queried, edited, and written as tile
sources, but they do not emit concrete routing PIPs because they have no grid
locations.

`fab_graph` uses two routing resource classes.

`RoutingPipKind.INTERNAL_MATRIX`
: A switch-matrix connection inside a tile type.  In FABulous source files this
  is a matrix/list row such as `E1END0,LA_I0`.  When materialized for nextpnr it
  becomes one concrete PIP for every placed instance of that tile type.

`RoutingPipKind.EXTERNAL_WIRE`
: A tile CSV routing row that connects one tile to another tile.  It has a
  direction, source name, destination name, `(x_offset, y_offset)`, and
  `wire_count`.  A vector external wire emits one concrete PIP per wire lane per
  valid tile instance.

Deleting or shrinking external resources can make matrix rows invalid.  The
graph handles this with local cascade behavior: matrix rows that depend on
removed external wires are disabled too, including common FABulous termination
cases such as `NULL` mappings.

## Internal Design

The implementation is intentionally tile-local for hot operations.

At load time, FABulous files and the parsed `Fabric` object are converted into
tile-type models and resource indexes:

```python
external_by_tile = {
    "LUT4AB": {
        RoutingResourceKey(...): ResourceState(active=True, delay=8.0),
        ...
    },
}

matrix_by_tile = {
    "LUT4AB": {
        RoutingResourceKey(...): ResourceState(active=True, delay=8.0),
        ...
    },
}
```

All declared tile models live in the model/index layer.  Concrete routing uses a
separate placed-location index:

```python
tile_models = {"LUT5F": ..., "LUT4AB": ...}
tile_locations_by_type = {"LUT5F": ((1, 2), (2, 2), ...)}
```

Here `LUT4AB` is editable as a standalone model, but it cannot be emitted into
`pips.txt` unless it also appears in the placed-location index.

An edit touches only one tile type and one indexed resource family:

```python
def delete_matrix_resource(key):
    state = matrix_by_tile[key.tile_type][key]
    state.active = False
    validate_tile(key.tile_type)
```

That means add/delete/restore/resize/query operations do not update a global list
of concrete PIPs.  They update tile-local resource state and validate only the
affected tile type.

Tile-local metadata is also used for configuration-bit queries:

```python
matrix_bits = sum(
    (len(rows_for_source) - 1).bit_length()
    for rows_for_source in active_matrix_rows_by_source.values()
    if len(rows_for_source) >= 2
)

total_bits = matrix_bits + sum(bel.config_bits for bel in tile_model.bels)
```

Concrete PIPs are generated lazily:

```python
def iter_pips():
    for (x, y), tile_type in placed_tiles:
        for matrix_state in active_matrix_resources[tile_type]:
            yield materialize_matrix_pip(matrix_state, x, y)
        for external_state in active_external_resources[tile_type]:
            yield from materialize_external_pips(external_state, x, y)
```

This keeps optimizer mutations fast.  The O(number of concrete PIPs) work happens
only when needed:

- `render_pips_txt()`
- `write_pips()`
- `active_pips()`
- `disabled_pips()`
- `stats()`
- full project metadata generation

## Typical Optimizer Loop

```python
from pathlib import Path

run_dir = Path("runs/candidate")
run_dir.mkdir(parents=True, exist_ok=True)

keys = graph.matrix_resources(
    "LUT4AB",
    where=lambda key: key.destination_name.startswith("LA_I"),
)

for idx, key in enumerate(keys):
    graph.delete_matrix_resource(key=key)
    graph.write_pips(run_dir / f"pips_{idx}.txt")
    # Run nextpnr / benchmark evaluator with this pips.txt.

graph.write_project("runs/final_architecture", generate_rtl=True)
```

This keeps expensive full FABulous project regeneration out of the inner loop.
The inner loop pays only for selected tile-local edits and lazy `pips.txt`
materialization.
