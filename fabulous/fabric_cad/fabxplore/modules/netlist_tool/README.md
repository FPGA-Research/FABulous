## Netlist Tool

The netlist tool maps FABulous tile RTL into a PDK-specific gate-level netlist.
It is built around Yosys/pyosys, but it does not use a generic ASIC synthesis
recipe unchanged. The pass sequence is trimmed and tuned for FPGA tile netlists,
especially mux-heavy switch-matrix and configuration logic.

The tool currently provides:

- a Yosys synthesis and mapping sequence optimized for FPGA tile netlists
- a custom ABC restructuring script before final Liberty mapping
- Liberty text editing for fast custom-cell experiments
- late sub-circuit extraction using Yosys graph-isomorphic matching
- optional cell type remapping with Yosys `chtype`
- direct access to the underlying pyosys pass interface
- final Yosys `stat -liberty` output and parsed chip area

## Main Flow

`NetlistTool.map_rtl()` runs the complete flow:

```text
read RTL
hierarchy/proc/flatten/optimization
generic AIG + custom ABC restructuring
Liberty-based dfflibmap / abc / clockgate
PDK techmaps
tie-cell insertion
optional buffer insertion
final cleanup
optional sub-circuit extraction
optional cell type remapping
Liberty-based statistics
```

This flow is deliberately narrower than a full generic synthesis flow. FPGA
switch-matrix and tile logic usually does not contain the same design features
that appear in complete user RTL designs, such as large memories, larger FSM
extraction opportunities, high-level arithmetic datapaths, or deep module
hierarchies. Removing those unrelated synthesis stages keeps the tile mapper
focused on the logic that actually appears in mux networks, latches, tie cells,
and local configuration structures.

## ABC Optimization

ABC is the main Boolean optimization engine used by the netlist tool. Yosys first
converts the combinational part of the design into a form ABC can optimize,
often an AIG: an And-Inverter Graph made from 2-input AND nodes and optional
inversions. This gives ABC a uniform representation for comparing, rewriting,
and remapping Boolean logic. Yosys commonly uses ABC for technology mapping from
internal Yosys gates to generic gates, LUTs, or standard cells. See the Yosys ABC
documentation for background: [abc - use ABC for technology mapping][1].

The netlist tool uses two ABC stages:

```text
1. abc -g cmos      -> generic gate/AIG restructuring
2. abc -liberty     -> final standard-cell mapping
```

The first stage is not the final ASIC mapping. It is a tile-specific
restructuring step that tries to produce a better Boolean shape before the real
Liberty area mapper sees the circuit. In practice this can beat a plain
`abc -liberty` run because the Liberty mapper starts from a cleaner, more shared
structure.

The custom ABC script does the following:

```text
strash
&get -n
&fraig -x
&put
scorr
balance/resub/rewrite/refactor sequence
dc2
repeat balance/resub/rewrite/refactor sequence
strash
&get -n
&dch -f
&nf -R 1000
&put
```

The first block canonicalizes and merges logic. `strash` structurally hashes the
AIG so identical AND/inverter structures are shared. `&get -n`, `&fraig -x`, and
`&put` move the design into ABC's newer AIG manager, merge functionally
equivalent nodes, then return it to the normal network. This is close in spirit
to Yosys's default ABC setup, but used here as part of a longer tile-oriented
optimization flow.

The middle of the script is an expanded area-compression sequence:

```text
balance -l
resub -K 6 -l
rewrite -l
resub -K 6 -N 2 -l
refactor -l
resub -K 8 -l
balance -l
resub -K 8 -N 2 -l
rewrite -l
resub -K 10 -l
rewrite -z -l
resub -K 10 -N 2 -l
balance -l
resub -K 12 -l
refactor -z -l
resub -K 12 -N 2 -l
rewrite -z -l
balance -l
```

The important operations are:

- `balance -l`: rebalance the AIG while staying level-aware.
- `resub -K N`: replace local cones with expressions that reuse nearby signals.
- `rewrite`: replace small AIG subgraphs with better known implementations.
- `refactor`: rebuild a cone through a different factored form.
- `-z`: accept zero-cost changes that may enable later reductions.
- `-l`: avoid damaging depth too much while optimizing area.

The script runs one long local compression block, then `dc2`, then repeats the
compression block. `dc2` is a stronger global combinational optimization step;
after it reshapes the network, the second local block can find reductions that
were not visible before.

The final tail prepares the result for mapping:

```text
strash
&get -n
&dch -f
&nf -R 1000
&put
```

`&dch -f` creates and uses structural choices, and `&nf -R 1000` maps through
ABC's `&` flow with a more aggressive recovery budget. This produces a compact
generic structure that is then handed to the final `abc -liberty` pass.

This is useful for FPGA tiles because switch matrices and configuration logic are
often mux-heavy and contain repeated select/decode cones. The script encourages
sharing and reshaping in exactly those areas:

```text
strash/fraig       -> merge equal or equivalent logic
resub             -> reuse existing select/decode signals
rewrite/refactor  -> reshape local mux/gate structures
dc2               -> globally reshape the AIG
&dch/&nf          -> prepare a compact structure for final Liberty mapping
```

## Sub-Circuit Extraction Rules

`sub_circuit_map_rules` are applied near the end of the flow, after the design
has already been mapped and cleaned into standard cells. Each rule is a string
containing a Verilog module that Yosys can use with:

```text
extract -map <temporary-rule-file>
```

This uses Yosys's graph-isomorphic `extract` pass. Instead of matching one cell
at a time, it can identify a whole standard-cell subgraph that is isomorphic to
the rule module and replace that subgraph with a custom module instance.

That is useful when a custom FPGA tile primitive corresponds to multiple
standard cells. A normal `techmap` is often enough for one-to-one structural
rewrites, but it is not the right tool when the mapped implementation is a
multi-cell pattern that should become one custom cell after standard-cell
mapping.

Typical use cases:

- replace a standard-cell mux tree with a custom mux module
- collapse a latch-plus-mux pattern into one tile primitive
- recognize repeated switch-matrix fragments after mapping

## Liberty Support

The mapper reads the PDK's default Liberty corner, passes it through
`LibertyHandler.modify_liberty()`, and uses the modified text for mapping and
area statistics. This makes it possible to experiment with custom cells without
editing PDK files on disk.

Supported Liberty edits:

- `add_liberty_cells`: append one or more complete `cell (...) { ... }` blocks
  from each string fragment.
- `remove_liberty_cells`: remove named cells from the active Liberty corner.
- `change_liberty_cell_area`: override the direct `area` attribute of named
  cells.

Adding cells is intentionally fragment-based. One list entry may contain one
cell or several cells:

```python
add_liberty_cells=[
    """
    cell (MY_CUSTOM_CELL) {
      area : 42.0;
      pin(A) { direction : input; }
      pin(Y) { direction : output; function : "A"; }
    }

    cell (MY_OTHER_CELL) {
      area : 12.0;
    }
    """,
]
```

The Liberty handler validates the fragments. Added cells must be complete cell
blocks, must not duplicate existing library cells, and must not contain
meaningful non-comment text outside cell blocks.

## Cell Type Remapping

`change_cell_types` applies Yosys `chtype` commands after optional sub-circuit
extraction:

```text
chtype -map <cell> <cell_type>
```

The option is a dictionary:

```python
change_cell_types={
    "mytypes": [
        "sg13g2_tiehi",
        "sg13g2_or2_1",
        "sg13g2_o21ai_1",
        "sg13g2_nor3_1",
    ],
}
```

For every listed source cell, the mapper changes matching instances to the
dictionary key. This is useful when several concrete standard-cell names should
be treated as one abstract cell family or reported under one common name in a
downstream architecture model.

## Public Interface

The high-level architecture flow exposes the mapper through
`ArchitectureSynthesizer.netlist_tool_pass(...)`:

```python
mapper = synthesizer.netlist_tool_pass(
    tile_name="LUT4AB",
    sub_circuit_map_rules=[mux4_rule_text],
    buffer_wire_insertion=False,
    change_cell_types={
        "mytypes": ["sg13g2_or2_1", "sg13g2_nor3_1"],
    },
    add_liberty_cells=[custom_cell_liberty_text],
    remove_liberty_cells=["sg13g2_buf_16"],
    change_liberty_cell_area={"sg13g2_buf_1": 1.0},
)

print(mapper.stats)
print(mapper.area)
```

For direct use, construct `PdkInputConfig` and `NetlistTool`:

```python
from pathlib import Path

from fabulous.fabric_cad.fabxplore.modules.netlist_tool.core.gatelevel_mapper import (
    NetlistTool,
)
from fabulous.fabric_cad.fabxplore.modules.netlist_tool.core.models import (
    PdkInputConfig,
)

config = PdkInputConfig(
    top_name="TileTop",
    rtl_files=[Path("tile.v")],
    sub_circuit_map_rules=None,
    buffer_wire_insertion=False,
    change_cell_types=None,
    add_liberty_cells=None,
    remove_liberty_cells=None,
    change_liberty_cell_area=None,
)

mapper = NetlistTool(config=config, debug=False)
mapper.map_rtl()

print(mapper.stats)
print(mapper.area)
```

## Configuration Options

`PdkInputConfig` controls the flow:

| Option | Description |
| --- | --- |
| `top_name` | Top RTL module to synthesize and map. |
| `rtl_files` | Verilog files loaded into the Pyosys design. |
| `sub_circuit_map_rules` | Verilog rule modules applied with Yosys `extract -map` near the end of the flow. |
| `buffer_wire_insertion` | If true, run `insbuf` with the PDK's minimum buffer cell. |
| `change_cell_types` | Dictionary of destination cell type to source cells for `chtype -map`. |
| `add_liberty_cells` | Liberty fragments containing complete custom `cell` blocks to append. |
| `remove_liberty_cells` | Liberty cell names to remove before mapping/statistics. |
| `change_liberty_cell_area` | Mapping from Liberty cell name to replacement area value. |

The model also derives PDK-specific values from the active FABulous context:

- `pdk_root`
- `pdk`
- `liberty_corner_file`
- `techmap_files`
- `tiehi_cell_and_port`
- `tielo_cell_and_port`
- `min_buf_cell_and_ports`

## Pass Interface

`NetlistTool` keeps the active pyosys design in:

```python
mapper.netlist_design
```

This is a `PyosysBridge`. Its `run_pass(cmd: str)` method executes any Yosys pass
string against the current design:

```python
mapper.netlist_design.run_pass("stat")
mapper.netlist_design.run_pass("write_verilog mapped_tile.v")
```

When `debug=False`, the bridge runs commands quietly through `tee -q`. When
`debug=True`, pass output remains visible, which is useful while tuning mapping
rules or debugging ABC/Yosys behavior.

The bridge also exposes convenience methods for reading and writing designs:

- `read_verilog_paths(...)`
- `read_verilog_string(...)`
- `read_json_paths(...)`
- `write_verilog_path(...)`
- `write_json_path(...)`
- `to_verilog_string(...)`
- `to_netlist_dict(...)`
- `to_py_object(...)`

This means the default netlist flow can be used as a starting point, and custom
Yosys passes can still be inserted manually before or after `map_rtl()` when a
tile experiment needs extra inspection.

[1]: https://yosyshq.readthedocs.io/projects/yosys/en/0.35/cmd/abc.html "abc - use ABC for technology mapping"
