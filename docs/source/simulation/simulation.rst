Simulation setup
================

The following series of commands can be used to easily run a simulation with a test bitstream loaded, using Icarus Verilog:

.. code-block:: console

        (venv)$ cd demo/Test
        (venv)$ ./build_test_design.sh
        (venv)$ ./run_simulation.sh

FABulous comes with 3 different simulation methods _`configuration module`,

#. Serial (Mode 0)

   Send configuration in through UART

#. Parallel (Mode 1) - default in the testbench

   Use parallel configuration port

#. Bitbang configuration port (To be supported in the testbench)

   We have produced a quick asynchronous serial configuration port interface that is ideal for microcontroller configuration. It uses the original CPU interface that we have in our TSMC chip. The idea of the protocol is as follows:

   .. figure:: ../figs/bitbang1.*
       :alt: Bitbang description
       :align: center


   We drive s_clk and s_data. On each rising edge of s_clock, we sample data and on the falling edge, we sample control.

   Both values get shifted in a separate register. If the control register sees the bit-pattern x”FAB0” it samples the data shift register into a hold register and issues a one-cycle strobe output (active 1).

   The next figure shows the enable generation (and input sampling) for generating the enable signals for

   * the control shift register and
   * the data shift register.

   .. figure:: ../figs/bitbang2.*
       :alt: Bitbang schematic
       :align: center
