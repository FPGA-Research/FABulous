# FABulous: an Embedded FPGA Framework

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Code Style](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Doc Style](https://img.shields.io/badge/%20style-numpy-459db9.svg)](https://numpydoc.readthedocs.io/en/latest/format.html)
[![Documentation](https://readthedocs.org/projects/fabulous/badge/?version=latest)](https://fabulous.readthedocs.io/en/latest/)

> [!WARNING]
> **Active Development - Use Tagged Releases for Production**
>
> The **main** branch is under active development and may contain errors, incomplete features, and breaking changes. We are not responsible for any issues caused by using the development branch.
>
> **For production use, please use [tagged releases](https://github.com/FPGA-Research/FABulous/releases) or reach out to us for further advice.**
>
> **Documentation:** Our [documentation](https://fabulous.readthedocs.io/) defaults to the latest development version. You can switch between versions (including the latest development version or specific tagged releases) using the version selector at
> documentation page. Please ensure you consult the documentation version that matches your installation to avoid compatibility issues.

## Overview and Features

FABulous is an open-source embedded FPGA (eFPGA) framework for generating FPGA fabric and integrates the open source CAD tools Yosys and nextpnr for the user design flow. It is silicon-proven through multiple successful tapeouts across TSMC 180nm, Skywater 130nm, IHP SG13G2, GF180MCU, and 28nm CMOS, FABulous provides a full-stack toolchain from CSV-based fabric definition to production-ready GDSII. The framework supports frame-based partial reconfiguration for runtime reconfiguration of individual FPGA regions.

### Key Capabilities

- **Full-stack toolchain** -- Integrates [Yosys](https://github.com/YosysHQ/yosys) (synthesis), [nextpnr](https://github.com/YosysHQ/nextpnr) (place-and-route), and [LibreLane](https://github.com/librelane/librelane) (physical design) for a complete fabric-to-GDSII flow.
- **CSV-based fabric definition** -- Define custom fabrics through a simple `fabric.csv` configuration file instead of complex XML architecture descriptions, making customisation accessible to hardware engineers without specialised tooling.
- **Modular tile-based architecture** -- Compose fabrics from look-up tables (LUTs), memory blocks, DSPs, I/O blocks, and arithmetic units, with full support for user-defined custom primitives.
- **Frame-based partial reconfiguration** -- Supports frame-based partial reconfiguration, enabling runtime reconfiguration of individual FPGA regions without disrupting the rest of the fabric.
- **Multi-process-node portability** -- Silicon-proven across 5+ process nodes, demonstrating portability across foundry processes.
- **Production-ready GDS flow** -- Generate GDSII layout directly from fabric definitions using the integrated OpenROAD flow, ready for ASIC fabrication.
- **Apache 2.0 licence** -- Freely available for both commercial and academic use.

## Silicon Proven

FABulous has been validated through 12+ successful tapeouts across multiple process nodes.

| Process Node | Project | Description |
| :--- | :--- | :--- |
| TSMC 180nm | FORTE-ENG1 | eFPGA with RISC-V core and 1K DPRAM |
| Skywater 130nm | [STRIVE](https://github.com/FPGA-Research/eFPGA---RTL-to-GDS-with-SKY130) | 1440 LUT4s + 180 LUT5s + dual-port memories |
| Skywater 130nm | [Google MPW-2](https://github.com/nguyendao-uom/eFPGA_v3_caravel) | CLBs, DSPs, RegFiles, BBRAMs |
| Skywater 130nm | [Google MPW-3](https://github.com/FPGA-Research/FABulous-Sky---a-heterogeneous-FPGA-fabric-in-Skywater130) | FABulous-Sky heterogeneous fabric with custom cells |
| Skywater 130nm | [Google MPW-3](https://github.com/nguyendao-uom/fuserisc_ver2) | FuseRISC -- RISC-V with eFPGA for TensorFlow Micro |
| Skywater 130nm | [Google MPW-4](https://github.com/nguyendao-uom/ICESOC) | ICESOC -- Ibex-Crypto-eFPGA for cryptography |
| Skywater 130nm | [Google MPW-4](https://github.com/nguyendao-uom/rram_testchip) | ReRAM-based eFPGA |
| Skywater 130nm | [Google MPW-5](https://github.com/nguyendao-uom/open_eFPGA) | Full open-source eFPGA with OpenLane |
| 130nm / 28nm CMOS | JINST '24 | eFPGA for ML in particle detector readout |
| IHP SG13G2 | [Greyhound SoC](https://github.com/mole99/greyhound-ihp) | Taped out, bring-up pending |
| IHP SG13G2 | [MFPGA](https://github.com/EverythingElseWasAlreadyTaken/MFPGA) | eFPGA on IHP shuttle |
| GF180MCU | [gf180mcu-fabulous-fpga](https://github.com/mole99/gf180mcu-fabulous-fpga) | eFPGA on wafer.space GF180 run |

See the [Chip Gallery](https://fabulous.readthedocs.io/en/latest/gallery/index.html) for detailed descriptions and links to each tapeout.

## FABulous and Alternative Offerings

| Feature | FABulous | OpenFPGA | PRGA |
| :--- | :--- | :--- | :--- |
| Fabric definition format | CSV + Python API | XML | Python API |
| Partial reconfiguration | Frame-based | Not supported | Not supported |
| GDS generation | Integrated LibreLane flow | External flow required | External flow required |
| Silicon tapeouts | 12+ across 5+ process nodes | SOFA series (Skywater 130nm) | None published |
| CAD tools | Yosys + nextpnr | Yosys + VTR | Yosys + VTR |
| License | Apache 2.0 | MIT | BSD-3-Clause |

## System Requirements

To run FABulous, you need Python 3.12 or later. The framework is fully supported on Linux and macOS. Windows users must utilise the Windows Subsystem for Linux (WSL) for compatibility.

For the complete toolchain experience, you will need synthesis and place-and-route tools. We recommend installing the [OSS CAD Suite](https://github.com/YosysHQ/oss-cad-suite-build), which bundles Yosys and nextpnr, using the provided `FABulous install-oss-cad-suite` command. Additionally, using `uv` is highly recommended for faster Python package management.

## Installation

You can install FABulous either directly from the Python Package Index for standard usage or from the source code if you intend to contribute to the development of the framework.

### Standard Installation (via PyPI)

```bash
pip install fabulous-fpga
# or
# uv tool install fabulous-fpga
FABulous create-project demo
cd demo && FABulous start
```

### Development Installation (from source)

```bash
git clone https://github.com/FPGA-Research/FABulous
cd FABulous
uv sync
FABulous create-project demo
cd demo && FABulous start
```

Once installed, you can automatically install the recommended CAD tools by running `FABulous install-oss-cad-suite` in your terminal.

## Using FABulous

Interacting with FABulous is typically done via its interactive shell or through automated scripts. The outputs are systematically organised into a `Fabric` directory for generated RTL and a `Tile` directory for primitive definitions. Bitstreams and logs are stored within your `user_design` folder.

### Essential Commands Table

| Task | Command |
| :---- | :---- |
| Create a new project | FABulous create-project \<name> |
| Launch interactive shell | FABulous start |
| Run a non-interactive flow | FABulous -p \<dir> run "<cmd1>; <cmd2>; ..." |
| Execute a TCL script | FABulous -p \<dir> script custom_flow.tcl |
| View help documentation | FABulous --help |

### Typical Interactive Workflow

```bash
FABulous> run_FABulous_fabric
FABulous> run_FABulous_bitstream user_design/sequential_16bit_en.v
FABulous> exit
```

## GUI Setup with FABulator

[FABulator](https://github.com/FPGA-Research/FABulator) is a companion tool that allows you to visually explore the fabrics generated by FABulous and display user designs. To import a fabric into FABulator, you must first generate a geometry file. You can achieve this by running the following commands within the FABulous shell:

```bash
FABulous> gen_fabric
FABulous> gen_geometry
```

*(Note: gen_fabric is only needed once to generate the required switch_matrix.csv files).*

## Contribution Guidelines

We welcome community contributions. To ensure consistency, please use uv for environment setup, follow Ruff formatting standards, and use conventional commits for your messages. Comprehensive details regarding environment setup and coding standards are available in our [Development Guide](https://fabulous.readthedocs.io/en/latest/development.html).

By contributing to this project, you agree that your modifications will be licensed under the project's Apache 2.0 License.

## Citation

If you use FABulous in your academic research, please cite the following publication:

Dirk Koch, Nguyen Dao, Bea Healy, Jing Yu, and Andrew Attwood. 2021. FABulous: An Embedded FPGA Framework. In <i>The 2021 ACM/SIGDA International Symposium on Field-Programmable Gate Arrays</i> (<i>FPGA '21</i>). Association for Computing Machinery, New York, NY, USA, 45–56. DOI: <https://doi.org/10.1145/3431920.3439302>

[Link to Paper](https://dl.acm.org/doi/pdf/10.1145/3431920.3439302)

```latex
@inproceedings{koch2021fabulous,
  title={FABulous: An embedded FPGA framework},
  author={Koch, Dirk and Dao, Nguyen and Healy, Bea and Yu, Jing and Attwood, Andrew},
  booktitle={The 2021 ACM/SIGDA International Symposium on Field-Programmable Gate Arrays},
  pages={45--56},
  year={2021}
}
```

## Disclaimer and Limitation of Liability

> [!IMPORTANT]  
> READ CAREFULLY BEFORE USING THIS SOFTWARE!

### Liability

This software is provided "as is" without any express or implied warranty. In no event shall the authors, contributors, copyright holders, or affiliated institutions be liable for any claims, damages, or other liabilities arising from its use.

FABulous is an IP generator framework that produces HDL designs for embedded FPGA fabrics intended for ASIC fabrication. The developers and contributors assume no responsibility or liability for any intellectual property generated using this framework, nor are we responsible for any chips, ASICs, FPGAs, or physical devices fabricated using these designs.

While continuous efforts are made to ensure reliability, and several designs have been silicon-proven, we make no guarantees regarding the functional correctness, timing closure, physical design quality, or manufacturing compliance of the generated IP. Silicon-proven status does not imply that FABulous-generated designs can be used without rigorous verification. Users are solely responsible for performing comprehensive whole-system verification (including timing-annotated and formal verification) to ensure the generated fabric functions correctly for their specific application prior to fabrication. Use of this software and any derived products is entirely at your own risk.

### License

For the complete license terms of using the software, see the [Apache 2.0 License](https://opensource.org/licenses/Apache-2.0).
