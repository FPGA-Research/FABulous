# Simulation setup

FABulous provides a simulation environment to validate that the generated
FPGA fabric works correctly. The simulation loads a test bitstream, built from
the user design, into the simulated FABulous fabric RTL and verifies that
configuration, routing, and primitive behavior function as intended.

```{mermaid}
flowchart TB
    subgraph design ["User Design Flow"]
        A[User Design Verilog/VHDL] --> B[Yosys Synthesis]
        B --> C[nextpnr Place & Route]
        C --> D[Bitstream Generation]
    end

    subgraph fabric ["Fabric Generation"]
        F[FABulous] --> G[Fabric RTL]
    end

    subgraph sim ["Simulation"]
        direction LR
        E[Test Bitstream] --> H[Icarus Testbench]
        H --> I{Pass / Fail}
    end

    subgraph emu ["Emulation"]
        direction LR
        J[Hardwired Bitstream] --> K[Fabric RTL + Bitstream]
        K --> L[Commercial FPGA Board]
    end

    D --> E
    D --> J
    G --> H
    G --> K
```

:::{important}
The purpose of FABulous simulation is to verify the **generated fabric
implementation**, not to validate user designs mapped onto it. If you need to
test your own design logic, use a standard HDL testbench for your design
before mapping it to the fabric.
:::

The following diagram illustrates the simulation flow and how the different
components interact.

```{mermaid}
flowchart LR
    A[User Design Verilog/VHDL] --> B[Yosys Synthesis]
    B --> C[nextpnr Place & Route]
    C --> D[Bitstream Generation]
    D --> E[Test Bitstream]

    F[FABulous] --> G[Fabric RTL]

    E --> H[Testbench Simulation]
    G --> H
    H --> I{Pass / Fail}
```

For simple use cases, there is the `run_simulation` command in the FABulous shell.
For more complex use cases it can be useful to create an own flow, like the following example `make` based flow.

Please make sure to use recent versions of [Yosys](https://github.com/YosysHQ/yosys), [nextpnr-generic](https://github.com/YosysHQ/nextpnr) (_not_ the old FABulous nextpnr fork)
and [GHDL with mcode backend](<https://github.com/ghdl/ghdl/releases>) or use the [OSS-CAD-Suite](https://github.com/YosysHQ/oss-cad-suite-build) which provides nightly builds of the necessary dependencies.

:::{note}
The OSS-CAD-Suite is providing GHDL only with LLVM backend, which increases the simulation speed for FABulous projects significantly. We recommend using the latest GHDL with mcode backend for the best simulation performance.
:::

Also, make sure you have the `make` package installed:

```console
sudo apt-get install make
```

The following series of commands can be used to easily run a simulation with a test bitstream loaded, using Icarus Verilog:

```console
(venv)$ cd demo/Test
(venv)$ make
```

FABulous comes with 3 different simulation methods:

1. Serial (Mode 0)

   Send configuration in through UART

2. Parallel (Mode 1) - default in the testbench

   Use parallel configuration port

3. Bitbang configuration port (To be supported in the testbench)

   We have produced a quick asynchronous serial configuration port interface that is ideal for microcontroller configuration. It uses the original CPU interface that we have in our TSMC chip. The idea of the protocol is as follows:

   :::{figure} ./figs/bitbang1.*
   :align: center
   :alt: Bitbang description
   :::

   We drive s_clk and s_data. On each rising edge of s_clock, we sample data and on the falling edge, we sample control.

   Both values get shifted in a separate register. If the control register sees the bit-pattern x”FAB0” it samples the data shift register into a hold register and issues a one-cycle strobe output (active 1).

   The next figure shows the enable generation (and input sampling) for generating the enable signals for

   - the control shift register and
   - the data shift register.

   :::{figure} ./figs/bitbang2.*
   :align: center
   :alt: An illustration of the signals used in the custom bitbang protocol as well as the decoding of these signals.
   :::
