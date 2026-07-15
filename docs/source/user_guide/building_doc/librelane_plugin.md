# Hardening through the LibreLane plugin

:::{warning}
**This plugin is experimental.**

The supported, first-class FABulous path is the CLI GDS flow in [Convert your design into GDSII format](./fabric_gds.md). It drives the same hardening steps while keeping the standard FABulous project layout (`Tile/`, `Fabric/`, per-tile `gds_config.yaml`), and it is the path FABulous develops and tests end to end.

The plugin adds no hardening capability the CLI flow lacks. It only swaps the driver: you drive the same underlying steps through `librelane` and hand-written `config.yaml` files instead of through the FABulous CLI. Its main reason to exist is pairing FABulous with an external, [fabulous tile library](https://github.com/FPGA-Research/fabulous-tiles) and FABulous itself is not yet fully integrated to consume such a library. Until that integration lands, the plugin is essentially just a different interface onto the same flow, and you take on writing the `config.yaml` files and managing the tile macros by hand. If you are not deliberately building on the tile library, use the CLI GDS flow instead.
:::

FABulous ships a [LibreLane](https://github.com/librelane/librelane) plugin, `librelane_plugin_fabulous`, that exposes the tile-hardening and fabric-stitching flows as native LibreLane flows. This lets you drive the ASIC flow directly with `librelane` and a `config.yaml`, rather than through the FABulous CLI. It is a thin adapter over the same steps as the CLI flow, so the [flow variable table](#gds-variables), [pin configuration](#pin-config), and [tile stitching](#stitching-the-tiles) sections of the GDS guide apply here as well.

Because it hands control to `librelane`, the plugin does not follow the usual FABulous project structure and does not provide the fabric-wide automated bring-up that the CLI's `run_FABulous_eFPGA_macro` offers (the multi-mode design-space exploration and NLP joint tile sizing described in the [Full Automated Flow](#full-automated-flow)). Per-tile size optimisation via `FABULOUS_OPT_MODE` is still available, since it is a step in the shared flow. You lay out the `config.yaml` files and manage the tile macros yourself.

The plugin provides two flows:

- `FABulousTile` - hardens a single tile or supertile.
- `FABulousFabric` - stitches pre-hardened tile macros into a fabric.

## Prerequisites

The plugin uses the same toolchain as the CLI GDS flow. You need the Nix environment and a PDK. See the [prerequisites](#prerequisites) of the GDS guide for details on entering the Nix environment and installing a PDK.

The plugin is generated into the `fabulous-fpga` wheel at build time, so it is available as soon as FABulous is installed in the Nix environment. There is no separate install step.

## Plugin discovery

LibreLane auto-discovers any package whose name matches `librelane_plugin_*`. To confirm the plugin is registered, run inside the Nix environment:

```bash
librelane --version
```

The output lists the plugin under _Discovered plugins_:

```text
Discovered plugins:
librelane_plugin_fabulous -> ...
```

## Selecting a flow

Each design is described by a `config.yaml` whose `meta.flow` field selects the flow:

```yaml
meta:
  version: 2
  flow: FABulousTile   # or FABulousFabric
```

Run it with:

```bash
librelane path/to/config.yaml
```

## FABulousTile

Place the `config.yaml` in the same directory as the tile CSV (`<tile_name>.csv`).

Plugin configuration variables:

| Variable | Type | Description |
| --- | --- | --- |
| `FABULOUS_TILE_DIR` | `list[Path]` | Path to the tile directory containing the tile CSV and its Verilog sources. Only the first element is used. |
| `FABULOUS_EXTERNAL_SIDE` | `"N" \| "E" \| "S" \| "W"` | Side of the macro at which the external pins are placed. Used as a fallback for standalone tile runs; when hardening as part of a fabric the pin order is derived from the tile's position. |
| `FABULOUS_SUPERTILE` | `bool` | If true, `FABULOUS_TILE_DIR` refers to a supertile and a supertile wrapper is generated. Defaults to `false`. |
| `FABULOUS_CONFIG_BIT_MODE` | `ConfigBitMode` | Config-bit storage mode used when regenerating the tile switch matrix and config memory. Must match the parent fabric. Defaults to `FRAME_BASED`. |
| `FABULOUS_MULTIPLEXER_STYLE` | `MultiplexerStyle` | Multiplexer implementation style used when regenerating the tile switch matrix. Must match the parent fabric. Defaults to `CUSTOM`. |

Set `DESIGN_NAME` to the tile name (for example `LUT4x8_ha`) and `CLOCK_PORT` to the tile's clock port. Add the models and cells the tile depends on to `VERILOG_FILES`. Any other LibreLane variable, such as `DIE_AREA`, `CLOCK_PERIOD`, or `SYNTH_STRATEGY`, is set as usual.

Example `config.yaml`:

```yaml
meta:
  version: 2
  flow: FABulousTile

FABULOUS_TILE_DIR: dir::.

DESIGN_NAME: LUT4x8_ha
VERILOG_FILES:
  - dir::../../../models_pack.v

DIE_AREA: [ 0, 0, 250, 250 ]

# Disable timing-driven placement so it does not resize the buffers
PL_TIMING_DRIVEN: false
SYNTH_STRATEGY: "AREA 2"
CLOCK_PERIOD: 20
```

## FABulousFabric

`FABulousFabric` stitches previously-hardened tile macros into a full fabric.

Plugin configuration variables:

| Variable | Type | Description |
| --- | --- | --- |
| `FABULOUS_FABRIC_CONFIG` | `list[Path]` | Path to the fabric CSV describing the tile map, parameters, and per-tile CSV locations. Only the first element is used. |
| `FABULOUS_TILE_LIBRARY` | `list[Path]` | Paths to the tile library roots. |
| `FABULOUS_TILE_MACROS` | `dict[str, Path]` | Mapping of tile name to a previously-hardened macro output directory (containing `metrics.json`, `gds/`, `lef/`, `vh/`, `nl/`, `pnl/`, `spef/`). When omitted, each tile in the fabric CSV is auto-resolved by scanning `FABULOUS_TILE_LIBRARY` for a `<tile>/runs/RUN_*/final` directory and picking the most recently modified one. |

Set `DESIGN_NAME` to the fabric name and add any top-level models and custom cells to `VERILOG_FILES`. The tile spacing and halo variables from the base flow (`FABULOUS_TILE_SPACING`, `FABULOUS_HALO_SPACING`) and the rest of the LibreLane variables apply here too; see the [flow variable table](#gds-variables).

Example `config.yaml`:

```yaml
meta:
  version: 2
  flow: FABulousFabric

DESIGN_NAME: my_fabric
VERILOG_FILES: []

FABULOUS_FABRIC_CONFIG: dir::my_fabric.csv
FABULOUS_TILE_LIBRARY: dir::../../tiles/classic/

FABULOUS_TILE_SPACING: [ 0, 0 ]
FABULOUS_HALO_SPACING: [ 0, 0, 0, 0 ]
```
