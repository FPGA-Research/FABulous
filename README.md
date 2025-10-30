# FABulous: an Embedded FPGA Framework

> [!WARNING]
> **Active Development - Use Tagged Releases for Production**
>
> The **main** branch is under active development and may contain errors, incomplete features, and breaking changes. We are not responsible for any issues caused by using the development branch.
>
> **For production use, please use [tagged releases](https://github.com/FPGA-Research/FABulous/releases) or reach out to us for further advice.**
>
> **Documentation:** Our [documentation](https://fabulous.readthedocs.io/) defaults to the latest development version. You can switch between versions (including the latest development version or specific tagged releases) using the version selector at
> documentation page. Please ensure you consult the documentation version that matches your installation to avoid compatibility issues.

<!--toc:start-->

- [FABulous: an Embedded FPGA Framework](#fabulous-an-embedded-fpga-framework)
  - [Introduction](#introduction)
  - [How to cite](#how-to-cite)
  - [Prerequisites](#prerequisites)
    - [Optional: uv for faster dependency management](#optional-uv-for-faster-dependency-management)
  - [Getting started](#getting-started)
    - [Using uv (optional)](#using-uv-optional)
  - [Contribution Guidelines](#contribution-guidelines)

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB.svg?style=flat&logo=python&logoColor=white)](https://www.python.org)
[![Code Style](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Doc Style](https://img.shields.io/badge/%20style-numpy-459db9.svg)](https://numpydoc.readthedocs.io/en/latest/format.html)

## Introduction

FABulous is designed to fulfill the objectives of ease of use, maximum portability to different process nodes, good control for customization, and delivering good area, power, and performance characteristics of the generated FPGA fabrics. The framework provides templates for logic, arithmetic, memory, and I/O blocks that can be easily stitched together, whilst enabling users to add their own fully customized blocks and primitives.

The FABulous ecosystem generates the embedded FPGA fabric for chip fabrication, integrates
[YosysHQ](https://github.com/YosysHQ/oss-cad-suite-build)
toolchain release packages, deals with the bitstream generation and provides after-fabrication tests. Additionally, we plan to provide an emulation path for system development.

This guide describes everything you need to set up your system to use the FABulous ecosystem, and the full project documentation can be found [here](https://fabulous.readthedocs.io/en/latest/).

![FABulous Ecosystem Diagram](docs/source/figs/fabulous_ecosystem.png)

### Silicon Proven

FABulous is **silicon proven** technology with multiple successful tapeouts. The framework has been used to fabricate real chips, demonstrating its capability to generate production-ready FPGA fabrics. These tapeouts validate the correctness and reliability of the generated IP across different process nodes and design configurations.

See our [Chip Gallery](https://fabulous.readthedocs.io/en/latest/gallery/index.html) for a few examples of fabricated chips using FABulous fabrics.

## How to cite

The following paper can be used to cite FABulous:

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

## Prerequisites

The following packages need to be installed for generating fabric HDL models and using the FABulous front end:

- Python 3.12 or later

Install python dependencies

```bash
sudo apt-get install python3-virtualenv
```

> [!NOTE]
>
> If you get the warning `ModuleNotFoundError: No module named virtualenv` or
> errors when installing the requirements, you have to install the dependencies
> for your specific python version. For Python 3.12 use
>
> ```bash
> sudo apt-get install python3.12-virtualenv
> ```

> [!NOTE]
>
> If you are using an older version than Ubuntu 24.04, you may need to install tkinter.
> Otherwise, you might get the warning `ModuleNotFoundError: No module named 'tkinter'`.
>
> ```bash
> sudo apt-get install make python3-tk
> ```

The following packages need to be installed for the CAD toolchain

- [Yosys](https://github.com/YosysHQ/yosys)
- [nextpnr-generic](https://github.com/YosysHQ/nextpnr#nextpnr-generic)

### Optional: uv for faster dependency management

[uv](https://github.com/astral-sh/uv) is a high-performance Python package manager that provides faster dependency resolution and installation. While not required for end users, it offers significant speed improvements and reproducible environments.

**Benefits of using uv:**

- 10-100x faster than pip for dependency resolution
- Automatic virtual environment management
- Deterministic dependency locking
- Cross-platform compatibility

**Installation:**

Linux/macOS:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

macOS with Homebrew:

```bash
brew install uv
```

Windows:

```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Or from PyPI:

```bash
pip install uv
```

To build the docs locally, some further Python dependencies are required - to install these, run

```
pip3 install -r docs/requirements.txt
```

from the top directory of the repository.

## Getting started

We recommend using Python virtual environments for the usage of FABulous.
If you are not sure what this is and why you should use it, please read the [virtualenv documentation](https://virtualenv.pypa.io/en/latest/index.html).

```bash
$ git clone https://github.com/FPGA-Research-Manchester/FABulous
$ cd FABulous
$ virtualenv venv
$ source venv/bin/activate
(venv)$ pip install -r requirements.txt
(venv)$ pip install -e .
```

You can deactivate the virtual environment with the `deactivate` command.
Please note, that you always have to enable the virtual environment to use FABulous:

```bash
cd <path to FABulous>
source venv/bin/activate
```

We have provided a Python Command Line Interface (CLI) as well as a project structure for easy access of the FABulous toolchain.

The `Tile` folder contains all the definitions of the fabric primitive as well as the fabric matrix configuration. `fabric.csv` is what defining the architecture of the fabric. The FABulous project folder also contains a `.FABulous` folder which contains all the metadata during the generation of the fabric.

We can initiate the FABulous shell with `FABulous <project_dir>`. After that you will see a shell interface which allow for interactive fabric generation. To generate a fabric we first need to run `load_fabric [fabric_CSV]` to load in the fabric definition. Then we can call `run_FABulous_fabric` to generate a fabric.

To generate a model and bitstream for a specific design call `run_FABulous_bitstream npnr <dir_to_top>` which will
generate a bitstream for the provided design in the same folder as the design.

To exit the shell simply type `exit` and this will terminate the shell.

A demo of the whole flow:

```bash
(venv)$ FABulous create-project demo # Create a demo project
(venv)$ cd demo
(venv)$ FABulous start # Run Fabulous interactive shell for demo project

# In the FABulous shell
FABulous> load_fabric
FABulous> run_FABulous_fabric
FABulous> run_FABulous_bitstream npnr ./user_design/sequential_16bit_en.v
FABulous> exit
```

To run a simulation of a test bitstream on the design with Icarus Verilog:

```bash
(venv)$ cd demo/Test
(venv)$ make sim
```

The tool also supports using TCL script to drive the build process. Assuming you have created a demo project using
`(venv)$ FABulous -c demo`, you can call `(venv)$ FABulous demo -s ./demo/FABulous.tcl` to run the demo flow with the TCL interface.

### Using uv (optional)

If you have [uv](https://github.com/astral-sh/uv) installed (see Prerequisites section), you can use it for faster dependency management and automatic virtual environment handling:

```bash
git clone https://github.com/FPGA-Research-Manchester/FABulous
cd FABulous
uv sync                    # Install dependencies and create virtual environment
uv pip install -e .       # Install FABulous in editable mode
```

Running FABulous with uv:

```bash
uv run FABulous -c demo    # Create a demo project
uv run FABulous demo       # Run FABulous interactive shell

# Or activate the environment and run directly:
source .venv/bin/activate
(venv)$ FABulous -c demo
(venv)$ FABulous demo
```

Benefits of using uv:

- No need to manually create/manage virtual environments
- Faster dependency installation
- Automatic dependency resolution and locking
- Consistent environments across different machines

More details on bitstream generation can be found [here](https://fabulous.readthedocs.io/en/latest/FPGA-to-bitstream/Bitstream%20generation.html).

Detailed documentation for the project can be found [here](https://fabulous.readthedocs.io/en/latest/index.html)

## GUI Setup

[FABulator](https://github.com/FPGA-Research-Manchester/FABulator)
supports exploration of fabrics generated
by FABulous, as well as displaying user
designs.

to import a fabric into FABulator, a geometry file
for the fabric is needed. This can be generated by
running

```
load_fabric
gen_fabric      # only needed once to generate matrix.csv files
gen_geometry
```

in the FABulous shell. This file can then be imported
into FABulator. More information can be found
[here](https://github.com/FPGA-Research-Manchester/FABulator).

## Contribution Guidelines

For comprehensive development information including environment setup, coding standards, and contribution workflows, please see our [Development Guide](https://fabulous.readthedocs.io/en/latest/development.html).

**Quick Reference for Contributors:**

- Use [uv](https://github.com/astral-sh/uv) for development environment setup
- Follow [Ruff](https://docs.astral.sh/ruff/) formatting and linting standards
- Use [conventional commits](https://www.conventionalcommits.org/) for commit messages
- Target the `FABulous2.0-development` branch for pull requests
- Ensure all tests pass and CI checks succeed

**Quick Setup:**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh  # Install uv
git clone https://github.com/FPGA-Research-Manchester/FABulous
cd FABulous
uv sync --dev
uv pip install -e .
uv run pre-commit install
```

By contributing to this project, you agree that your contributions will be licensed under the project's [License](https://opensource.org/licenses/Apache-2.0).

## Disclaimer and Limitation of Liability

**IMPORTANT: READ CAREFULLY BEFORE USING THIS SOFTWARE**

This software is provided **AS IS”** without any express or implied warranty. In no event shall the authors, contributors, copyright holders, or affiliated institutions be liable for any claims, damages, or other liabilities.

### IP Generation and ASIC/FPGA Fabrication

FABulous is an IP generator framework that produces HDL designs for embedded FPGA fabrics intended for ASIC fabrication. Users of this software acknowledge and agree that:

1. **No Liability for Generated IP**: The developers and contributors assume no responsibility or liability for any intellectual property (IP) generated using this framework, including but not limited to HDL code, netlists, GDSII files, or any other design artifacts.

2. **No Liability for Fabricated Products**: We are not responsible for any chips, ASICs, FPGAs, or any physical devices fabricated using IP generated by this framework. This includes but is not limited to:
   - Design errors, bugs, or defects in generated IP
   - Manufacturing defects or yield issues
   - Functional failures or performance issues
   - Timing violations or signal integrity problems
   - Power consumption or thermal issues
   - Any damages or losses resulting from the use of fabricated devices

3. **No Warranty of Correctness**: While constant efforts are being made to create reliable tools, we make no guarantees regarding the correctness, reliability, or suitability of generated IP for any specific purpose, including but not limited to:
   - Functional correctness of generated HDL
   - Timing closure or synthesis results
   - Physical design or layout quality
   - Compliance with any manufacturing process or design rules

   **IMPORTANT**: Silicon proven status does NOT imply that FABulous-generated designs can be used without thorough verification. Users MUST perform comprehensive whole-system verification, including timing-annotated simulation and formal verification, to ensure the generated fabric works correctly for their specific circuit and application requirements. Previous successful tapeouts do not guarantee functionality for new designs or configurations.

4. **User Responsibility**: Users are solely responsible for:
   - Verification and validation of all generated IP
   - Testing and qualification of designs before fabrication
   - Ensuring compliance with applicable standards and regulations
   - Any consequences of using designs generated by this framework

### Use at Your Own Risk

By using this software, you acknowledge that you have read this disclaimer, understand it, and agree to be bound by its terms. You accept full responsibility for any use of this software and any IP or products derived from it.

For the complete license terms, see the [Apache 2.0 License](https://opensource.org/licenses/Apache-2.0).
