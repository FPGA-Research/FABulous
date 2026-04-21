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
     compute pip delays per tile, and write the `pips.txt` file for nextpnr.
5. The fully-resolved configuration used for the run is written to
     `.FABulous/timing_model_config_resolved.json` so you can inspect what FABulous
     actually used.

## Running the timing model from the CLI

The FABulous interactive CLI exposes the command `timing_model`. Key options:

- `--mode [physical|structural]` — Select analysis mode. Default: `physical`.
- `--outfile <path>` — Output path for the generated pip file (default:
    `.FABulous/pips.txt`).
- `--emit-config-template` — Emit a JSON configuration template and exit.
- `--with-config-file <path>` — Use the supplied JSON config instead of PDK defaults.

:::{note}
The place and route tool (nextpnr) will use the file
`.FABulous/pips.txt` located in the project directory.
That should be kept in mind if a custom output path is provided.
:::

### Examples

In the default setting the timing model does not need a custom configuration, instead it
expects default paths and PDK setting, that means the backend flow must be run
first with a supported PDK by FABulous.

A simple working flow will look like:

```bash
FABulous create-project demo_test
FABulous -p demo_test run "run_FABulous_fabric"
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
the results were generated in `demo_test/.FABulous/pip.txt`
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
- `synth_executable`  — Path to Yosys (or other synth tool) if synthesis is required.
- `sta_executable` — Path to the STA tool (e.g. OpenSTA) required to generate SDF from the netlist.
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
- `sta_program` / `synth_program` — Strings naming the backends (e.g. opensta, yosys).
- `mode` — physical or structural.
- `consider_wire_delay` — Boolean. Include wire delay when computing pip delays.
- `delay_type_str` — Which DelayType to use (max_all, min_all, avg_all, etc.).
- `delay_scaling_factor` — Multiplier applied to computed delays (numeric). Mostly useful
when the timing model was run with structural mode to compensate the more optimistic approximation.
- `debug` — Enable verbose logging to help debugging.

### Example configuration (shortened)

```json
{
    "project_dir": "/path/to/demo_test",
    "liberty_files": "libs/sky130_fd_sc_hd__tt_025C_1v80.lib",
    "min_buf_cell_and_ports": "sky130_fd_sc_hd__buf_1 A X",
    "synth_executable": "/usr/bin/yosys",
    "sta_executable": "/usr/bin/sta",
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
    "sta_program": "opensta",
    "synth_program": "yosys",
    "mode": "physical",
    "consider_wire_delay": true,
    "delay_type_str": "max_all",
    "delay_scaling_factor": 1.0,
    "debug": false
}
```

Notes about the example:

- `custom_per_tile_source_files` is optional. Use it if you have tile-specific
    post-layout netlists / SPEFs or custom RTL for a tile. The keys should match
    your tile type names.
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
- `.FABulous/timing_model_config_resolved.json` — The resolved, validated
    configuration that was used for the run. Inspect this file to see absolute
    paths and the effective settings.

## Debugging and common issues

- Missing or incorrect paths: Pydantic validation will raise errors when required
    fields are missing. Ensure `liberty_files`, `synth_executable` and
    `sta_executable` are present and correct.
- Tools not found or failing: Make sure `yosys` and `opensta` are available and
    executable in the environment, or set full paths in the config.
- In physical mode you must provide SPEF/RC files (per-tile or project-wide) if
    you want wire/parasitic delays to be included.
- If runs fail silently, enable `debug: true` in the config and re-run — the
    flow will produce more detailed log messages.

## Programmatic usage

If you prefer not to use the CLI, the same functionality is exposed by the
FABulous API. Example (python):

```py
from fabulous.fabulous_api import FABulous_API
from fabulous.fabric_cad.timing_model.models import TimingModelConfig

# instantiate FABulous API (example, depends on how you normally set it up)
fab_api = FABulous_API(my_writer)

# load or construct a TimingModelConfig (validate with Pydantic)
# then call the interface
config = TimingModelConfig.model_validate_json(open('my_config.json').read())
fab_api.timing_model_interface(
    mode='physical',
    output_file=Path('.FABulous/pips.txt'),
    debug=True,
    manual_config=config
)
```
