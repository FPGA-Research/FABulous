Emulation setup
===============

.. note:: The emulation functionality is implemented but needs more testing.

The script ``bit_gen.py`` in
:ref:`bitstream generation<bitstream generation>`
not only generates the binary bitstream for simulation, but also the bitstream files for Verilog and VHDL emulation.

.. note:: The bitstream in both Verilog and VHDL follow the original order of configuration bits in each tile, not the re-mapping one.

* Verilog: Users should define the global macro value of ``EMULATION_MODE`` to enable the emulation function in the fabric testing.

  .. code-block:: verilog
     :emphasize-lines: 1

        `ifdef EMULATION_MODE
                `include "sequential_2bit_en_bitstream.vh"
        `endif

* VHDL: Users should set the generic ``Mode`` to **ASIC** or **EMULATE** in ``fabric.vhdl`` to disable or enable the emulation function.

  .. code-block:: vhdl
     :emphasize-lines: 5

        entity  eFPGA  is
                Generic (
                        MaxFramesPerCol : integer := 20;
                        FrameBitsPerRow : integer := 32;
                        Mode : string := "EMULATE"; -- "ASIC" will use the normal configuration port and "EMULATE" will hardwire a bitstream from emulate_bitstream.vhd
                        NoConfigBits : integer := 0 );
                Port (...);
        end entity eFPGA ;
