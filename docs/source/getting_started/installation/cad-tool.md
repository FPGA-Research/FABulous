(cad-tool-install)=
# Install Required CAD tools

We use [yosys](https://github.com/YosysHQ/yosys) for Verilog file parsing and [ghdl-yosys-plugin](https://github.com/ghdl/ghdl-yosys-plugin) for VHDL file parsing. As a result `yosys` must be installed in order for FABulous to work. If you want to work with VHDL then having both dependency is a must.

You can automatically install the above packages with the following command:

```bash
FABulous install-oss-cad-suite
```

This will install the [`oss-cad-suit`](https://github.com/YosysHQ/oss-cad-suite-build) for you which will install all the non-required CAD tools, such as `nextpnr-generic` and simulators, which save you the trouble of installing other tools.

:::{note}
If you just want to install `yosys` using **apt**, make sure you have at least Ubuntu 23.10 (24.04 for the LTS versions) installed to meet the above requirement.
:::

Otherwise, you will need to install the CAD tools yourself. An added benefit is all the

## Installing Non required CAD tools

To perform synthesis, place and route and simulation you will need the following software:

- Verilog:
  - [yosys](https://github.com/YosysHQ/yosys)
  - [nextnpr-generic](https://github.com/YosysHQ/nextpnr?tab=readme-ov-file#nextpnr-generic)
  - [iverilog](https://github.com/steveicarus/iverilog)

- VHDL:
  - [yosys](https://github.com/YosysHQ/yosys)
  - [ghdl-yosys-plugin](https://github.com/ghdl/ghdl-yosys-plugin)
  - [nextnpr-generic](https://github.com/YosysHQ/nextpnr?tab=readme-ov-file#nextpnr-generic)
  - [ghdl](https://github.com/ghdl/ghdl/releases/tag/nightly)

As mentioned in the previous section, using the `FABulous install-oss-cad-suite` will install all the required software.

:::{note}
For GHDL we suggest using the `mcode` backend, as the simulation time is short using the `mcode` backend then any other backend. If you are a Mac user, the `mcode` backend is not available, and we recommend going with the `llvm-jit` backend instead.
:::
