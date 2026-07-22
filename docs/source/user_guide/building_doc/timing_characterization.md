 (timing-characterization)=

:::{warning}
The timing model produced by FABulous is experimental and has not been
tested on physical hardware. Use the generated timing data and models with caution,
they may be incomplete or inaccurate. Always validate timing results on real devices
before relying on them for design decisions.
:::

# Timing Characterization

FABulous can produce a timing model that maps physical or structural design information
into pip delays used by nextpnr (the `pips.txt` format). The timing model is generated
from gate-level netlists and (optionally) parasitic RC data (SPEF) and Liberty timing
libraries. Two main modes are supported:

- `physical`: Uses a post-layout (routed) netlist and parasitic information (SPEF)
    to produce more realistic delay estimates.
- `structural`: Uses the structural (gate-level) netlist without parasitics, useful
    when no post-layout data is available.

Internally the flow performs synthesis (or uses provided netlists), runs static
timing analysis (STA) with a backend such as OpenSTA, parses the produced SDF
timing information into a timing graph, computes delays for fabric pips, and
writes an output pip file that nextpnr can consume.

This page explains how the pieces fit together and how to run the timing-model
generation from the FABulous CLI or programmatically.

## How it works (high level)

1. Prepare inputs: the backend flow produces the gate-level netlists (and, for
     physical mode, SPEF/RC files) under the project. The liberty/techmap files and
     standard cells come from `Fabric/std_cell_library.yaml`.
2. Run the routing-model generation with timing extraction (CLI command
     `gen_routing_model --timing <mode>`). FABulous reads the standard-cell library
     for the active PDK from `Fabric/std_cell_library.yaml`.
3. FABulous runs synthesis (Yosys) if needed, runs STA (OpenSTA) to create an SDF
     timing file, parses the SDF into a timing graph, computes pip delays per tile,
     and writes the `pips.txt` file for nextpnr.
4. The fully-resolved configuration used for the run is written to
     `.FABulous/timing_model_config_resolved.json` so you can inspect what FABulous
     actually used.

## Configuration sources

The standard-cell inputs live in `Fabric/std_cell_library.yaml`, and the analysis
options are CLI flags:

- **Standard-cell library** — `Fabric/std_cell_library.yaml`, keyed per PDK, supplies
    the liberty files, techmap files, and the cells the synthesizer maps onto (a buffer
    and, optionally, the tie cells). The project template ships sections for `sky130A`,
    `sky130B`, `ihp-sg13g2` and `gf180mcuD`. To characterize another PDK, add a matching
    `pdk::<variant>` section (see below).
- **Analysis options** (mode, delay collapsing, scaling, wire delay) are passed as
    flags to `gen_routing_model`.

### `Fabric/std_cell_library.yaml`

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/FPGA-Research/FABulous/main/schema/std_cell_library.schema.json
pdk::sky130A:
  liberty_files:
    - ${PDK_ROOT}/${PDK}/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib
  techmap_files:
    - ${PDK_ROOT}/${PDK}/libs.tech/openlane/sky130_fd_sc_hd/latch_map.v
    - ${PDK_ROOT}/${PDK}/libs.tech/openlane/sky130_fd_sc_hd/tribuff_map.v
  cells:
    buffer:
      - cell: sky130_fd_sc_hd__buf_1
        input_ports: [A]
        output_ports: [X]
    tie_high:                              # optional
      - cell: sky130_fd_sc_hd__conb_1
        output_ports: [HI]
    tie_low:                               # optional
      - cell: sky130_fd_sc_hd__conb_1
        output_ports: [LO]
```

Each `pdk::<variant>` section is a standard-cell library: the `liberty_files` and
`techmap_files` paths, and the `cells` the synthesizer needs, grouped by function. A
function may list more than one cell (the first is used). Only a `buffer` cell is
required; the tie cells are optional.

Liberty and techmap paths may be:

- **absolute** — used as-is;
- **relative** — resolved against the project directory;
- **`${VAR}` references** — resolved from the active settings:
    `${PDK_ROOT}` (`FAB_PDK_ROOT`), `${PDK}` (`FAB_PDK`), and `${PROJ_DIR}` (the project
    directory). The shipped template uses `${PDK_ROOT}/${PDK}/...` so it works against
    any PDK install without editing.

The `# yaml-language-server` header points editors at the published
`schema/std_cell_library.schema.json` (generated from the model, served from the
FABulous repository) for validation and autocompletion.

## Running the timing model from the CLI

The FABulous interactive CLI generates the routing model with the command
`gen_routing_model`. Timing extraction is enabled with the `--timing` flag. Key options:

- `--timing [placeholder|physical|structural]` — Select the timing mode.
    `placeholder` (the default) uses placeholder delays; `physical` and `structural`
    extract real pip delays.
- `--outfile <path>` — Output path for the generated pip file (default:
    `.FABulous/pips.txt`).
- `--delay-type [min_all|max_all|avg_all|avg_fast|avg_slow|max_fast|max_slow|min_fast|min_slow]`
    — How multi-corner SDF delays are collapsed to a single scalar (default `max_all`).
- `--delay-scale <float>` — Multiplier applied to computed delays (default `1.0`).
    Useful in `structural` mode to compensate for its more optimistic approximation.
- `--consider-wire-delay` / `--no-consider-wire-delay` — Include wire (SPEF/RC) delay
    in physical-mode analysis (default on).

:::{note}
The `gen_model_npnr` and `routing_model` commands are deprecated and now forward to
`gen_routing_model`. Use `gen_routing_model` directly.
:::

:::{note}
The place and route tool (nextpnr) will use the file
`.FABulous/pips.txt` located in the project directory.
That should be kept in mind if a custom output path is provided.
:::

### Examples

In the default setting the timing model does not need a custom configuration, instead it
expects default paths and PDK setting, that means the backend flow must be run
first with a PDK supported by FABulous.

A simple working flow will look like:

```bash
FABulous create-project demo_test
FABulous -p demo_test run "run_fab"
```

At this point all rtl files for the tiles were
generated and we have enough information to run
the timing model in `structural` mode. This mode
approximates the delay based on the rtl code without
the need of any physical data - no backend flow required.
But the results are likely less accurate compared to a run
that uses physical information.

We continue with:

```bash
FABulous -p demo_test run "gen_routing_model --timing structural"
```

After that the timing model has been generated and
the results were generated in `demo_test/.FABulous/pips.txt`
and `demo_test/.FABulous/timing_model_config_resolved.json`

In order to obtain more accurate timing information that actually represents
the design the FABulous GDS-FLOW must be run before the timing model,
that means in our example:

```bash
gen_all_tile_macros
# or
gen_fabric_macro
```

Then we can run:

```bash
FABulous -p demo_test run "gen_routing_model --timing physical"
```

The output files are the same as with the `structural`
mode but the delay estimates will now represent the
physical design.

## Outputs

- `pips.txt` (default: `.FABulous/pips.txt` or the path you pass with `--outfile`)
    — The nextpnr pip delay file generated by the flow.
- `.FABulous/timing_model_config_resolved.json` — The timing knobs used for the
    run (mode, wire-delay, delay type, and scaling factor). Inspect this file to
    confirm the effective settings FABulous used.

## Debugging and common issues

- Liberty not found: if a configured liberty path does not exist, Yosys/OpenSTA fail
    with that path. Fix the `liberty_files` entries in `Fabric/std_cell_library.yaml`.
- Missing PDK section: if `Fabric/std_cell_library.yaml` has no `pdk::<variant>` entry
    for your active PDK, add one with `liberty_files` and a `buffer` cell.
- Tools not found or failing: make sure `yosys` and `opensta` (`sta`) are available and
    executable in the environment, or set `FAB_YOSYS_PATH` / `FAB_OPENSTA_PATH`.
- In physical mode you need SPEF/RC files from the backend flow for wire/parasitic
    delays; run the GDS flow first, or pass `--no-consider-wire-delay`.
- If runs fail silently, add `--debug` to the FABulous invocation and re-run — the
    flow will produce more detailed log messages.

## Programmatic usage

If you prefer not to use the CLI, the same functionality is exposed by the
FABulous API. Pass the timing knobs directly and the Verilog sources to
characterize. The standard-cell inputs (liberty and techmap files, and the
buffer/tie cells) are read from the project's `Fabric/std_cell_library.yaml` for the
active PDK, so make sure `FAB_PDK` is set:

```py
from pathlib import Path

from fabulous.fabulous_api import FABulous_API
from fabulous.fabulous_cli.helper import gather_project_verilog_files
from fabulous.fabulous_settings import get_context
from fabulous.routing_model.tile_timing_model import TimingModelMode

# instantiate FABulous API (example, depends on how you normally set it up)
fab_api = FABulous_API(my_writer)

# gather the fabric's Verilog sources from the project directory
verilog_files = gather_project_verilog_files(get_context().proj_dir)

# generate the routing model with extracted pip delays
pips, bel, belv2, constraints = fab_api.generate_routing_model(
    mode=TimingModelMode.STRUCTURAL,
    verilog_files=verilog_files,
)
Path(".FABulous/pips.txt").write_text(pips)
```
