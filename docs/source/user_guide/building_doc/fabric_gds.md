# Convert your design into GDSII format

Once you have compiled your fabric RTL using the [building fabric](./building_fabric.md) guide, you can then convert your design into a GDS file for fabrication. The hardening process is a 2-stage process. We will first harden all the tiles, and then stitch them together. We chose to do this instead of compiling the whole fabric as a flat net list is because in an FPGA there are a lot of repeated components, which means synthesis will repeatedly synthesize similar logic, and the subsequent place and route will also be doing the same. To speed up the hardening process, we deploy this two-stage strategy with two key benefits:

1. Makes fabric development time much faster.
2. Makes scaling your fabric to larger designs much easier.

Per tile hardening is much faster as the size of the design is just much smaller. And since a fabric has a lot of repeated elements, optimizing one majority tile might potentially give you huge benefits in terms of power, performance and area (PPA), which enables you to have a performant fabric in a shorter time window. Another benefit is this allows multiple tiles to be developed simultaneously, which allows different parties with different specialties to fully optimize a part of the design.

We are reusing existing pre-hardened tiles, which avoids re-hardening all the tiles on a new run. To get a larger fabric you can simply "add more tiles" to the `fabric.csv`. If you need to add new tiles for new functionality, you can harden the newly created tile, without needing redoing the rest of the tiles.

To take advantage of fabric stitching, there are two limitations to the tile physical implementation.

1. The interfaces of adjacent tiles need to line up in the exact order, and they need to align physically with the same spacing.
2. Adjacent tiles in the same row must have the same height and tiles in the same column must be the same width in order to have perfect stitching. For the tile interface alignment, this is something that our framework will handle, however the tile sizing is something that needs special handling, which we will describe in the following for each stage.

## Prerequisites

### Install tools

:::{warning}
We use [librelane](https://github.com/librelane/librelane) as our main flow. To access the full flow, you should use the [Nix based installation method](../../getting_started/installation/nix-env.md), which will provide the full environment with all the required tools.
:::

:::{note}
As of writing, we are using custom build of librelane, as a result, the upstream version of librelane will not work. We are aiming to upstream all the changes.
:::

### Install PDK

To compile the design, we will also need to install the PDK. In the Nix installation method we have also packaged in a PDK version manager [ciel](https://github.com/fossi-foundation/ciel). By default, we have set up the project to target the `ihp-sg13g2` process (130nm). To install the PDK run the following command:

```bash
ciel enable --pdk-family ihp-sg13g2 cb7daaa8901016cf7c5d272dfa322c41f024931f
```

## Changing PDK

We support all PDKs that are supported by librelane. As a result you can switch to targeting other process nodes such as the Sky130A and gf180mcu. To switch to those PDKs, you will need to modify the `FAB_PDK_ROOT` and `FAB_PDK`, in `./<project>/.FABulous/.env` or set them in the shell as an environment variable. `FAB_PDK` is the PDK you are using, and `FAB_PDK_ROOT` is where the PDK is located. If you are installing the PDK from `ciel`, it will be located at `~/.ciel/`. An example of the `.env` file will be:

```bash
#... existing content
FAB_PDK='sky130A'
FAB_PDK_ROOT='/home/<user>/.ciel/sky130A'
```

For any other PDK, you will need to bring up the PDK to be supported by librelane. You can follow this [guide](https://openroad-flow-scripts.readthedocs.io/en/latest/contrib/PlatformBringUp.html) for more details. For more advanced nodes, it is likely that you will need to further modify and add steps to the flow for getting a working and manufacturable design.

## Tile to GDS

To convert a tile into a GDSII file, run the following command:

```bash
fabulous> gen_tile_macro <tile_name>
```

This will generate the tile GDS for you under the tile macro folder (`<project>/Tile/<tile_name>/macro/`).

### Command Options

The `gen_tile_macro` command supports an optimization flag:

```bash
fabulous> gen_tile_macro <tile_name> --optimise [mode]
```

Where `[mode]` is one of the optimization modes described in the [Tile Size Optimization](#tile-size-optimization) section. If `--optimise` is provided without a mode, `balance` is used by default.

To generate all tiles at once:

```bash
fabulous> gen_all_tile_macros
fabulous> gen_all_tile_macros --parallel      # Run in parallel for faster compilation
fabulous> gen_all_tile_macros --optimise      # With optimization (balance mode)
```

### Tile Config

You can change and customise any setting you want via modifying the `gds_config.yaml` file. There are two layers of configuration. There is a `gds_config.yaml` located at `<project>/Tile/include` and in each of the tiles, they have their respective `gds_config.yaml`. The one in the `include` is the base configuration which applies to all tiles, you can put all the settings that are common to all tiles in that file. For per tile specific configuration, you can set them using the `gds_config.yaml` at the tile.

The per tile `gds_config.yaml` is particularly useful and important as you can set per tile `die_area`. In order for the tiles to perfectly stitch together, as mentioned before, all tiles in the same row must have the same height, and tiles in the same column must have the same width, and you can control the tile sizing by using it. To see what variables can be configured, please check the [flow variable table](#gds-variables).

### Pin Config

During the generation process there will be an extra file generated under the `macro` folder, which is the `io_pin_order.yaml`. This file controls the placement of the IO pins along the tile. This is auto-populated to make sure all the pins of a tile align with the adjacent tiles. But one can modify it for whatever means, such as optimization. The following is an example of the IO config file:

```yaml
X0Y0:
    EAST:
    - max_distance: null
      min_distance: null
      pins:
      - E1BEG\[\d+\]
      - 5
      reverse_result: false
      sort_mode: bus_major
      ...
    WEST:
    - max_distance: null
      min_distance: null
      pins:
      - Co
      reverse_result: false
      sort_mode: bus_major
    ...
X0Y1:
    ...
```

The entry key `X0Y0` represents the location of the pins on a tile. For a normal tile, it will just have `X0Y0`. This is mainly useful for supertiles, where you need to set where the pins should be located relative to the tile shape. Having this control allows us to also align supertile and normal tile pins automatically.

The second layer of key sets along which side of the tile the allocated pins should be placed. Each entry within a `side` controls a pin placement group. The `pins` field is a list of entries for the pins that you want to set. Each entry can be either a regular expression that matches actual pins, or an integer which indicates a virtual pin. A virtual pin is a placeholder to space out the pins, and the integer value represents the number of virtual pins to be added.

In each group you can set the `min_distance` and `max_distance` and the placement script will try its best to fulfil the requirement, and yield an error if the constraint cannot be achieved. The order of the pin layout will be in the following format:

```{figure} _static/pin_layout_order.svg
:align: center
:width: 400px

Pin placement order on each side of a tile.
```

You can change the order of the list by setting the `reverse_result` to reverse the order of the list and sort_mode to change how the pin is being sorted. We support two sort modes, which are `bus_major` and `bit_minor`. `bus_major` will sort by the name of the bus, and `bit_minor` will sort by the bit index of the bus. The following is an example:

```text
# Given these pins: [
    "data_bus[1]", "addr_bus[0]", "data_bus[0]", "addr_bus[1]"
]

# Bus Major
data_bus[0]  # Same bus, lower index
data_bus[1]  # Same bus, higher index
addr_bus[0]  # Different bus, lower index
addr_bus[1]  # Different bus, higher index

# Bit Minor
addr_bus[0]  # Index 0 first
data_bus[0]  # Index 0 second (different bus)
addr_bus[1]  # Index 1 first
data_bus[1]  # Index 1 second (different bus)
```

## Stitching the tiles

Once all the tiles are compiled to GDS format with correct sizing, we then can stitch them together. This can be done by using the following command:

```bash
fabulous>gen_fabric_macro
```

And the full fabric will be stitched together.

We have a custom top-level IO placement script which will align all the pins with the IO pins around the perimeter. You will notice there is a small halo ring around the fabric as we will need some extra space to get the clock leader routed. A clock leader is a clock network where an external input clock is supplied at the bottom of the fabric and the signal is routed upward through each tile toward the top, as shown below.

```{figure} _static/clock_leader.svg
:align: center
:width: 460px

External input clock routing into clock leaders through a 2x2 tile fabric. Red boxes indicate connection points between tiles.
```

Same as tile implementation, there is a `gds_config.yaml` file under the `Fabric` folder where you can set additional variables. Check the [flow variable table](#gds-variables) for available options.

## Full Automated Flow

For a fully automated flow that handles tile size optimization and fabric stitching, use:

```bash
fabulous> run_FABulous_eFPGA_macro
```

:::{note}
The fully automated flow can take significantly longer than manual tile compilation, as it performs design space exploration by compiling all tiles with multiple optimization modes in parallel before running NLP optimization. For large fabrics with many unique tiles, expect longer runtimes.
:::

This command performs the following steps automatically:

1. **Design Space Exploration**: Compiles all tiles with three optimization modes (`balance`, `find_min_width`, `find_min_height`) in parallel to explore possible tile dimensions.

2. **NLP Optimization**: Uses Non-Linear Programming (via pymoo) to find optimal tile dimensions that minimize total fabric area while satisfying:
   - Minimum area constraints for each tile
   - Row height consistency (all tiles in a row must have the same height)
   - Column width consistency (all tiles in a column must have the same width)
   - SuperTile spanning constraints

3. **Recompilation**: Recompiles all tiles with the optimal dimensions found by the NLP solver.

4. **Fabric Stitching**: Assembles all tiles into the final fabric layout.

(tile-size-optimization)=
## Tile Size Optimization

The GDS flow includes an iterative optimization process to find the minimum viable tile dimensions. This is controlled by the `FABULOUS_OPT_MODE` variable.

### Optimization Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| `balance` | Alternates between increasing width and height to find minimal area | **Recommended** - Best for most tiles |
| `find_min_width` | Increases width iteratively while keeping height fixed | When height is constrained |
| `find_min_height` | Increases height iteratively while keeping width fixed | When width is constrained |
| `large` | Increases both dimensions together | Quick compilation, larger area |
| `no_opt` | No optimization, uses provided `DIE_AREA` directly | Manual control, requires `DIE_AREA` to be set |

### How Optimization Works

1. The flow starts with an initial die area (either provided or calculated from instance area)
2. It runs through placement and routing
3. If DRC errors or antenna violations occur, the die area is increased
4. The process repeats until a clean design is achieved or max iterations (20) reached
5. The last successful state is used as the final result

If no feasible solution can be found after all iterations, the flow will raise an error and stop the generation.

### Related Variables

- `FABULOUS_OPTIMISATION_WIDTH_STEP_COUNT`: Sites to increase width per iteration (default: 4)
- `FABULOUS_OPTIMISATION_HEIGHT_STEP_COUNT`: Sites to increase height per iteration (default: 1)
- `IGNORE_ANTENNA_VIOLATIONS`: If `true`, antenna violations won't trigger size increases
- `IGNORE_DEFAULT_DIE_AREA`: If `true`, ignores provided die area and starts from instance area

## Output Structure

After successful compilation, the output is organized as follows:

```text
<project>/
├── Tile/
│   └── <tile_name>/
│       └── macro/
│           ├── balance/          # Output from balance optimization
│           ├── find_min_width/   # Output from width optimization
│           ├── find_min_height/  # Output from height optimization
│           └── final_views/      # Final compiled output
│               ├── gds/          # GDSII files
│               ├── lef/          # LEF macro files
│               ├── spef/         # Parasitic extraction (per corner)
│               ├── nl/           # Netlist files
│               ├── pnl/          # Power netlist files
│               ├── vh/           # Verilog header files
│               └── metrics.json  # Compilation metrics
└── Fabric/
    └── macro/
        └── <pdk_name>/           # Fabric output for specific PDK
            └── final_views/
                └── ...           # Same structure as tile
```

### Key Metrics

The `metrics.json` file contains useful information:

- `design__die__bbox`: Die bounding box (x0 y0 x1 y1)
- `design__instance__area`: Total cell area
- `design__instance__utilization`: Utilization percentage
- `route__drc_errors`: Number of DRC violations
- `antenna__violating__pins`: Pins with antenna violations

### Viewing Results

To view generated GDS/ODB files in a GUI:

```bash
# View in OpenROAD GUI (for ODB files)
fabulous> start_openroad_gui --tile <tile_name>    # View specific tile
fabulous> start_openroad_gui --fabric              # View fabric
fabulous> start_openroad_gui --last-run --tile <tile_name>  # View latest run

# View in KLayout GUI (for GDS files)
fabulous> start_klayout_gui --tile <tile_name>
fabulous> start_klayout_gui --fabric
```

## Troubleshooting

If you encounter issues during the GDS flow, please ask for help in the [GitHub Discussions](https://github.com/FPGA-Research-Manchester/FABulous/discussions).
