# FABulous: an Embedded FPGA Framework

FABulous is an open-source embedded FPGA (eFPGA) framework for generating FPGA fabric and integrates the open source CAD tools Yosys and nextpnr for the user design flow. It is silicon-proven through multiple successful tapeouts across TSMC 180nm, Skywater 130nm, IHP SG13G2, GF180MCU, and 28nm CMOS, FABulous provides a full-stack toolchain from CSV-based fabric definition to production-ready GDSII. The framework supports frame-based partial reconfiguration for runtime reconfiguration of individual FPGA regions.

This guide describes everything you need to set up your system to develop with the FABulous ecosystem.

## At a glance

- **What it does** -- FABulous generates complete embedded FPGA fabrics and supporting flows for synthesis, place-and-route, bitstream generation, and GDSII physical design.
- **Fabric definition** -- Fabrics are defined through a simple CSV-based configuration (fabric.csv) instead of complex XML architecture descriptions, making customisation accessible to hardware engineers without specialised tooling.
- **Silicon track record** -- 12+ successful tapeouts across TSMC 180nm, Skywater 130nm, IHP SG13G2, GF180MCU, and 28nm CMOS process nodes.
- **Partial reconfiguration** -- Supports frame-based partial reconfiguration, enabling runtime reconfiguration of individual FPGA regions.
- **Licence** -- Apache 2.0 open-source licence, freely available for commercial and academic use.
- **Maintainers** -- Developed and maintained by the Novel Computing Technologies Group at the University of Heidelberg.

## Key links

- [Quick Start](getting_started/quickstart) -- Get FABulous running in minutes
- [Fabric Definition](user_guide/building_doc/index) -- Define your custom eFPGA architecture
- [CLI Usage](user_guide/cli_doc/index) -- Command-line interface reference
- [Simulation](user_guide/simulation/index) -- Pre-silicon validation and FPGA emulation
- [Chip Gallery](gallery/index) -- Silicon-proven tapeout examples
- [Publications](misc/publications) -- Academic papers and citations

:::{figure} figs/workflows.*
:align: center
:alt: An Illustation of the FABulous workflows and dependencies.

FABulous workflows and dependencies.
:::

:::{figure} figs/fabulous_ecosystem.*
:align: center
:alt: An Illustration of the FABulous ASIC, emulation and bitstream generation flows.
:width: 80%
:::

:::{note}
This project is under active development.
:::

## Contents

```{toctree}
:maxdepth: 2

getting_started/index
user_guide/index
developer_guide/development
gallery/index
misc/contact
misc/publications
generated_doc/index
```
