Simulation setup
================

FABulous provides a simulation environment to test the fabric and the bitstream generated for it.
For simple use cases, there is the `run_simulation` command in the FABulous shell.
For more complex use cases it can be useful to create an own flow, like the following example `make` based flow.


Please make sure to use recent versions of (Yosys)[https://github.com/YosysHQ/yosys], (nextpnr-generic)[https://github.com/YosysHQ/nextpnr] (_not_ the old FABulous nextpnr fork)
and (GHDL with mcode backend)[https://github.com/ghdl/ghdl/releases] or use the (OSS-CAD-Suite)[https://github.com/YosysHQ/oss-cad-suite-build] which provides nightly builds of the necessary dependencies.

.. note:: The OSS-CAD-Suite is providing GHDL only with LLVM backend, which increases the simulation speed for FABulous projects significantly. We recommend using the latest GHDL with mcode backend for the best simulation performance.

Also, make sure you have the `make` package installed:

.. code-block:: console

    $ sudo apt-get install make

The following series of commands can be used to easily run a simulation with a test bitstream loaded, using Icarus Verilog:

.. code-block:: console

        (venv)$ cd demo/Test
        (venv)$ make

FABulous comes with 3 different simulation methods _`configuration module`,

#. Serial (Mode 0)

   Send configuration in through UART

#. Parallel (Mode 1) - default in the testbench

   Use parallel configuration port

#. Bitbang configuration port (To be supported in the testbench)

   We have produced a quick asynchronous serial configuration port interface that is ideal for microcontroller configuration. It uses the original CPU interface that we have in our TSMC chip. The idea of the protocol is as follows:

   .. figure:: ./figs/bitbang1.*
       :alt: Bitbang description
       :align: center


   We drive s_clk and s_data. On each rising edge of s_clock, we sample data and on the falling edge, we sample control.

   Both values get shifted in a separate register. If the control register sees the bit-pattern x”FAB0” it samples the data shift register into a hold register and issues a one-cycle strobe output (active 1).

   The next figure shows the enable generation (and input sampling) for generating the enable signals for

   * the control shift register and
   * the data shift register.

   .. figure:: ./figs/bitbang2.*
       :alt: Bitbang schematic
       :align: center
