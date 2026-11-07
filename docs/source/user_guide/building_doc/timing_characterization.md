 (timing-characterization)=

:::{warning}
The timing model produced by FABulous is experimental and has not been
tested on physical hardware. Use the generated timing data and models with caution,
they may be incomplete or inaccurate. Always validate timing results on real devices
before relying on them for design decisions.
:::

# Timing Characterization

FABulous can produce timing data used by nextpnr in `pips.txt` and `bel.v3.txt`. Pip
delays are generated from gate-level netlists and (optionally) parasitic RC data (SPEF)
and Liberty timing libraries. BEL timing is derived from the SDF timing graph generated
for each tile. For every resolvable BEL input-to-output path, the flow emits the
available combinational delay or sequential setup, hold, and clock-to-output timing.
Every BEL definition is characterized through the same interface, including custom
BELs and multiple BELs within one tile type. Two main modes are supported:

- `physical`: Uses a post-layout (routed) netlist and parasitic information (SPEF)
    to produce more realistic delay estimates.
- `structural`: Uses the structural (gate-level) netlist without parasitics, useful
    when no post-layout data is available.

Internally the flow performs synthesis (or uses provided netlists), runs static
timing analysis (STA) with a backend such as OpenSTA, parses the produced SDF
timing information into a timing graph, computes the selected timing data, and writes
nextpnr timing files.

This page explains how the pieces fit together, how to generate and use a
configuration template, and how to run the timing-model generation from the
FABulous CLI or programmatically.

## How it works (high level)

1. Prepare inputs: gate-level netlists, Liberty (.lib) files and (for physical mode)
     SPEF/RC files. These can either be the project defaults or provided per-tile.
2. Create or modify a timing model configuration (JSON) which lists the paths to
     the required files and tools, and selects the mode and analysis options.
3. Run the FABulous timing-model flow (CLI command `timing_model`) with the
     configuration file or let FABulous resolve defaults from a supported PDK.
4. FABulous will (depending on the config): run synthesis (Yosys) if needed,
     run STA (OpenSTA) to create an SDF timing file, parse the SDF into a timing graph,
     compute the pip delays and BEL arcs per tile, and write `pips.txt` and `bel.v3.txt`
     for nextpnr.
5. The fully-resolved configuration used for the run is written to
     `.FABulous/timing_model_config_resolved.json` so you can inspect what FABulous
     actually used.

### Supertiles

FABulous characterises a supertile as one macro. It synthesises and times the
supertile module one time, with all its member tiles, and reads the pips and BEL arcs
of each member tile from that run. A tile type can be in one supertile only, and only
one time in it; else the run stops with an error.

The pips of a member tile are timed at the boundary of its instance
(`Tile_X{x}Y{y}_{tile}`) in the supertile netlist, with the same rules as a tile:

- A pip through one switch-matrix mux gets the delay of the path through that mux.
- A pip from a member input gets the delay from that input to the nearest member
    output, inside the member.
- A pip from a member output gets the fixed stitched delay, as a pip from a tile
    output does. This applies also when the wire goes to a neighbour member in the
    same supertile, so that a wire gets the same delay in a supertile and between
    tiles.

The pips of the supertile switch matrix are timed at the top of the supertile module,
as the pips of a tile switch matrix are. The supertile BELs are timed in the same
supertile run.

In `physical` mode, FABulous finds each member tile in the flat post-layout netlist
of the supertile. This needs a supertile macro hardened with its members kept as
modules, which FABulous's GDS flow does for Verilog projects (see
[supertiles in the GDS flow](#gds-supertiles)). Each member cell then carries its
member instance as a name prefix, and each wire between two members keeps the name
the supertile module gives it, so each member port is found on its post-layout net.
The member pips are timed with the rules above, from the post-layout delays:

- A wire between two members is charged once, at the member that receives it: a
    pip from a member input includes the wire from the sibling member, and a pip
    to a member output stops at the member, as the output pip is stitched.
- A wire from or to a supertile port is charged as for a tile.

The run stops with an error that names the member, the port and
`SYNTH_KEEP_HIERARCHY_MODULES` if the post-layout netlist has no cell of a member
(the supertile was hardened flat, for example before FABulous kept the members),
if no post-layout net has the name of a member port's net, or if that net has no
pin inside the member (a cell was inserted at the member boundary). Harden the
supertile again with the member hierarchy kept.

## Running the timing model from the CLI

The FABulous interactive CLI exposes the command `timing_model`. Key options:

- `--mode [physical|structural]` — Select analysis mode. Default: `physical`.
- `--outfile <path>` — Output path for the generated pip file (default:
    `.FABulous/pips.txt`).
- `--bel-outfile <path>` — Output path for the generated BEL timing file (default:
    `bel.v3.txt` beside the pip output).
- `--emit-config-template` — Emit a JSON configuration template and exit.
- `--with-config-file <path>` — Use the supplied JSON config instead of PDK defaults.

:::{note}
The place and route tool (nextpnr) uses `.FABulous/pips.txt` and
`.FABulous/bel.v3.txt` from the project directory. Keep that in mind when custom output
paths are provided.
:::

### Examples

In the default setting the timing model does not need a custom configuration, instead it
expects default paths and PDK setting, that means the backend flow must be run
first with a supported PDK by FABulous.

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
FABulous -p demo_test run "timing_model --mode structural"
```

After that the timing model has been generated and
the results were generated in `demo_test/.FABulous/pips.txt`,
`demo_test/.FABulous/bel.v3.txt`,
and `demo_test/.FABulous/timing_model_config_resolved.json`

In order to obtain more accurate timing information that actually represents
the design the FABulous GDS-FLOW must be run before the timing model,
that means in our example:

```bash
gen_macro all_tile
# or
gen_macro stitch
```

Then we can run:

```bash
FABulous -p demo_test run "timing_model
```

The output files are the same as with the `structural`
mode but the delay estimates will now represent the
the physical design.


## Configuration JSON: fields and meaning

The timing-model configuration is validated using the `TimingModelConfig`
Pydantic model. The important fields are documented below, paths are interpreted
relative to `project_dir` unless absolute.

- `project_dir` — Base directory for resolving relative paths.
Usually your project root.
- `liberty_files` — One or more Liberty (.lib) files providing cell timing information.
REQUIRED. Define here the timing library for the desired corner.
- `min_buf_cell_and_ports`  — Example: "cell_name in_port out_port".
Used to identify the buffer cell to map minimal buffer insertion.
- `techmap_files` — Optional techmap/verilog files used by the synthesiser to produce gate-level
netlists for the target cell library. Sometimes needed to map multiplexers and latch gates.
- `pdk_name` — Optional PDK identifier. if FABulous knows defaults for that PDK
it can use automatic values (like liberty_files and techmap_files).
- `custom_per_tile_source_files` — Optional mapping from tile name to per-tile overrides.
Each value is an object with:
    - `rtl_files` — RTL sources for that tile.
    - `netlist_file` — A pre-generated netlist (gate-level or routed for the tile.
    if set it will be used instead of the project default netlist.
    - `rc_file` — SPEF/RC file for that tile (used in physical mode).
- `mode` — physical or structural.
- `consider_wire_delay` — Boolean. Include wire delay when computing pip delays.
- `delay_type_str` — Which DelayType to use (max_all, min_all, avg_all, etc.).
- `delay_scaling_factor` — Multiplier applied to computed delays (numeric). Mostly useful
when the timing model was run with structural mode to compensate the more optimistic approximation.

Synthesis always runs on Yosys and STA on OpenSTA. Their executables come from the
FABulous settings (`FAB_YOSYS_PATH`, `FAB_OPENSTA_PATH`), not from this file.

### Example configuration (shortened)

```json
{
    "project_dir": "/path/to/demo_test",
    "liberty_files": "libs/sky130_fd_sc_hd__tt_025C_1v80.lib",
    "min_buf_cell_and_ports": "sky130_fd_sc_hd__buf_1 A X",
    "techmap_files": [
        "tools/latch_map.v",
        "tools/tribuff_map.v"
    ],
    "custom_per_tile_source_files": {
        "RAM_IO": {
            "rtl_files": [
                "demo_test/Tile/RAM_IO/*.v",
                "demo_test/Fabric/models_pack.v"
            ],
            "netlist_file": "demo_test/Tile/RAM_IO/phys/RAM_IO.v",
            "rc_file": "demo_test/Tile/RAM_IO/phys/RAM_IO.spef"
        }
    },
    "mode": "physical",
    "consider_wire_delay": true,
    "delay_type_str": "max_all",
    "delay_scaling_factor": 1.0
}
```

Notes about the example:

- `custom_per_tile_source_files` is optional. Use it if you have tile-specific
    post-layout netlists / SPEFs or custom RTL for a tile. The keys should match
    your tile type names; a tile inside a supertile is synthesised as part of the
    supertile, so its key is the supertile name.
- Paths may be absolute or relative to `project_dir`.

## Using templates and per-tile overrides

1. Generate a template with `--emit-config-template` and open the resulting JSON.
2. Fill in the required fields shown above. Paths are easier to manage if you use
     paths relative to `project_dir`.
3. If only some tiles have post-layout netlists / SPEF, add entries under
     `custom_per_tile_source_files` to point to those files, other tiles will use
     the project's defaults.

## Outputs

- `pips.txt` (default: `.FABulous/pips.txt` or the path you pass with `--outfile`)
    — The nextpnr pip delay file generated by the flow.
- `bel.v3.txt` (default: `.FABulous/bel.v3.txt` or the path you pass with
    `--bel-outfile`) — Per-BEL nextpnr timing arcs characterized from the tile's SDF
    timing graph. The file can contain combinational delays, setup/hold checks, and
    clock-to-output delays. A BEL for which no resolvable timing path exists has no
    timing-arc lines. Normal nextpnr model generation without a timing-model run retains
    its historical hardcoded timing values.
- `.FABulous/timing_model_config_resolved.json` — The resolved, validated
    configuration that was used for the run. Inspect this file to see absolute
    paths and the effective settings.

## Debugging and common issues

- Missing or incorrect paths: Pydantic validation will raise errors when required
    fields are missing. Ensure `liberty_files` and `min_buf_cell_and_ports` are
    present and correct. A tile source file (RTL, post-layout netlist or SPEF) that
    does not exist stops the run with a `FileNotFoundError` that names the tile,
    before any tool runs for it.
- Tools not found or failing: Make sure `yosys` and `sta` (OpenSTA) are available
    and executable in the environment, or set `FAB_YOSYS_PATH` and
    `FAB_OPENSTA_PATH`.
- In physical mode you must provide SPEF/RC files (per-tile or project-wide) if
    you want wire/parasitic delays to be included.
- OpenSTA skips SPEF nets whose names it cannot find in the netlist, which would
    leave their wire delays at zero. So after it reads the SPEF files, FABulous runs
    `report_parasitic_annotation` and stops with an error that names the first
    drivers if a driver with loads got no parasitics, or got them for only some of
    its loads. A driver without loads, such as an unused input port, is ignored. The
    usual cause is a SPEF file from a different run than the netlist.
- Run FABulous with `--debug` to log every Yosys and OpenSTA script and the
    tool output.

## Programmatic usage

If you prefer not to use the CLI, the same functionality is exposed by the
FABulous API. Example (python):

```py
from fabulous.fabulous_api import FABulous_API
from fabulous.fabric_cad.timing_model.config import TimingModelConfig, TimingModelMode

# instantiate FABulous API (example, depends on how you normally set it up)
fab_api = FABulous_API(my_writer)

# load or construct a TimingModelConfig (validate with Pydantic)
# then characterise the fabric
config = TimingModelConfig.model_validate_json(open('my_config.json').read())
fab_api.timing_model(
    mode=TimingModelMode.PHYSICAL,
    pip_file=Path('.FABulous/pips.txt'),
    bel_file=Path('.FABulous/bel.v3.txt'),
    manual_config=config,
)
```
