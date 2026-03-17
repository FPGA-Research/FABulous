(quick-start)=

# Quick start

This guide walks you through installing FABulous, generating a fabric, and producing a bitstream in under five minutes. For detailed installation options see the [Installation section](#install).

## 1. Install FABulous

Install [uv](https://github.com/astral-sh/uv) (if you don't have it already), then install FABulous as a tool:

```bash
# Install uv (Linux/macOS)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install FABulous
uv tool install fabulous-fpga
```

If you already have [pipx](https://pipx.pypa.io/) installed, `pipx install fabulous-fpga` works as well.

Verify the installation:

```bash
FABulous --version
```

:::{tip}
See the [Installation section](#install) for alternative methods (venv, Docker, Nix) and platform-specific instructions.
:::

## 2. Install CAD tools

FABulous requires [Yosys](https://github.com/YosysHQ/yosys) and [nextpnr-generic](https://github.com/YosysHQ/nextpnr) for synthesis and place-and-route. The easiest way to install them is through the bundled installer:

```bash
FABulous install-oss-cad-suite
```

This installs the [OSS CAD Suite](https://github.com/YosysHQ/oss-cad-suite-build), which includes Yosys, nextpnr, simulators, and all other required tools. VHDL users will also get [ghdl](https://github.com/ghdl/ghdl) and the [ghdl-yosys-plugin](https://github.com/ghdl/ghdl-yosys-plugin) through this installer. For manual installation or more details, see [CAD tool installation](#cad-tool-install).

## 3. Create a project

```bash
FABulous create-project demo
```

This creates a `demo/` directory with a default fabric definition and example user designs.

## 4. Generate fabric and bitstream

You can run the full flow either interactively or as a one-liner.

**Option A -- Interactive shell:**

```bash
cd demo
FABulous start
```

Inside the FABulous shell:

```
fabulous> run_FABulous_fabric
fabulous> compile_design user_design/sequential_16bit_en.v
```

**Option B -- Command line (batch mode):**

```bash
FABulous -p demo run "run_FABulous_fabric; compile_design user_design/sequential_16bit_en.v"
```

## 5. Check the outputs

After a successful run:

- **Tile RTL files** are in `demo/Tile/`
- **Fabric RTL file** is in `demo/Fabric/`
- **Bitstream** is at `demo/user_design/sequential_16bit_en.bin`
- **Synthesis and PnR logs** are in `demo/user_design/`

## What's next?

- [Building fabric](../user_guide/building_doc/building_fabric.md) -- step-by-step fabric generation and customization
- [Fabric definition](../user_guide/building_doc/fabric_definition.md) -- how to define your own fabric architecture
- [Simulation](../user_guide/simulation/index.md) -- verify your generated fabric through simulation
- [Development setup](../developer_guide/development.md) -- set up a development environment to contribute
