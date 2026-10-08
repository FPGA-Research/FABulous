(emulation-setup)=
# Emulation setup

:::{note}
This page describes *hardwired-bitstream* emulation. For running the fabric on a
board with its configuration port intact and reprogramming it over UART at
runtime, see [Emulating a fabric on a commercial FPGA](#emulation-on-fpga).
:::

:::{note}
The emulation functionality is implemented but needs more testing.
:::

The `bit_gen` command from the `FABulous-bit-gen` package, which `compile_design` runs as its
[bitstream generation](#bitstream-generation) step, not only generates the binary bitstream for simulation,
but also writes the Verilog (`.vh`) and VHDL (`.vhd`) bitstream files for emulation next to the `.bin` file.

:::{note}
The bitstream in both Verilog and VHDL follow the original order of configuration bits in each tile, not the re-mapping one.
:::

- Verilog: Users should define the global macro `EMULATION` to enable the emulation function in the fabric testing.

  ```{code-block} verilog
  :emphasize-lines: 1

     `ifdef EMULATION
             `include "sequential_2bit_en_bitstream.vh"
     `endif
  ```

- VHDL: Users should set the generic `Mode` to **ASIC** or **EMULATE** in `fabric.vhdl` to disable or enable the emulation function.

  ```{code-block} vhdl
  :emphasize-lines: 5

     entity  eFPGA  is
             Generic (
                     MaxFramesPerCol : integer := 20;
                     FrameBitsPerRow : integer := 32;
                     Mode : string := "EMULATE"; -- "ASIC" will use the normal configuration port and "EMULATE" will hardwire a bitstream from emulate_bitstream.vhd
                     NoConfigBits : integer := 0 );
             Port (...);
     end entity eFPGA ;
  ```
