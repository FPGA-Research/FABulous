# FABulous: an Embedded FPGA Framework

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/Python-3.9-3776AB.svg?style=flat&logo=python&logoColor=white)](https://www.python.org)
[![Code Style](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

## Introduction

FABulous is designed to fulfill the objectives of ease of use, maximum portability to different process nodes, good control for customization, and delivering good area, power, and performance characteristics of the generated FPGA fabrics. The framework provides templates for logic, arithmetic, memory, and I/O blocks that can be easily stitched together, whilst enabling users to add their own fully customized blocks and primitives.

The FABulous ecosystem generates the embedded FPGA fabric for chip fabrication, integrates
[YosysHQ](https://github.com/YosysHQ/oss-cad-suite-build)
toolchain release packages, deals with the bitstream generation and provides after-fabrication tests. Additionally, we plan to provide an emulation path for system development.

This guide describes everything you need to set up your system to use the FABulous ecosystem, and the full project documentation can be found [here](https://fabulous.readthedocs.io/en/latest/).

![FABulous Ecosystem Diagram](docs/source/figs/fabulous_ecosystem.png)

## How to cite

The following paper can be used to cite FABulous:

Dirk Koch, Nguyen Dao, Bea Healy, Jing Yu, and Andrew Attwood. 2021. FABulous: An Embedded FPGA Framework. In <i>The 2021 ACM/SIGDA International Symposium on Field-Programmable Gate Arrays</i> (<i>FPGA '21</i>). Association for Computing Machinery, New York, NY, USA, 45–56. DOI: <https://doi.org/10.1145/3431920.3439302>

[Link to Paper](https://dl.acm.org/doi/pdf/10.1145/3431920.3439302)

```
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

- Python 3.9 or later

Install python dependencies

```
sudo apt-get install python3-tk python3-virtualenv
```

The following packages need to be installed for the CAD toolchain

- [Yosys](https://github.com/YosysHQ/yosys)
- [nextpnr-generic](https://github.com/YosysHQ/nextpnr#nextpnr-generic)

## Getting started

We recommend using Python virtual environments for the usage of FABulous.
If you are not sure what this is and why you should use it, please read the [virtualenv documentation](https://virtualenv.pypa.io/en/latest/index.html).

```
$ git clone https://github.com/FPGA-Research-Manchester/FABulous
$ cd FABulous
$ virtualenv venv
$ source venv/bin/activate
(venv)$ pip install -r requirements.txt
(venv)$ pip install -e .
```

You can deactivate the virtual environment with the `deactivate` command.
Please note, that you always have to enable the virtual environment to use FABulous:

```
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

```
(venv)$ FABulous -c demo # Create a demo project
(venv)$ FABulous demo # Run Fabulous interactive shell for demo project

# In the FABulous shell
FABulous> load_fabric
FABulous> run_FABulous_fabric
FABulous> run_FABulous_bitstream npnr ./user_design/sequential_16bit_en.v
FABulous> exit
```

To run a simulation of a test bitstream on the design with Icarus Verilog:

```
(venv)$ cd demo/Test
(venv)$ ./build_test_design.sh
(venv)$ ./run_simulation.sh
```

The tool also supports using TCL script to drive the build process. Assuming you have created a demo project using
`FABulous -c demo`, you can call `FABulous demo -s ./demo/FABulous.tcl` to run the demo flow with the TCL interface.

More details on bitstream generation can be found [here](https://fabulous.readthedocs.io/en/latest/FPGA-to-bitstream/Bitstream%20generation.html).

Detailed documentation for the project can be found [here](https://fabulous.readthedocs.io/en/latest/index.html)

## Contribution Guidelines

Thank you for considering contributing to FABulous! By contributing, you're helping us improve and grow the project for everyone. Before you start, please take a moment to review our guidelines to ensure a smooth contribution process.

### Code Formatting

We use [Black](https://github.com/psf/black) for code formatting. Please make sure your code adheres to Black's standards before submitting a pull request.

### Code Review

Once you've submitted a pull request, one of our maintainers will review your code. Please be patient during this process. We may suggest changes or improvements to ensure the quality and compatibility of your contribution.

### License

By contributing to this project, you agree that your contributions will be licensed under the project's [License](https://opensource.org/licenses/Apache-2.0).
