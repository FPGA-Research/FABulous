.. _fabric_automation:

FABulous Fabric Automation
==========================

The fabric automation offers a set of tools and commands to automate common tasks
in FABulous and explains them with detailed examples.

.. _generating_custom_tiles:

Generating Custom Tiles
-----------------------

Defining a custom fabric, custom tiles or just add some custom functionality
can be a complex task.
The section :ref:`fabric_definition` describes in detail, how to model FABulous fabrics
with all its components.
In addition to that, we provide a set of tools to automate the generation of custom
tiles and switch matrices, as well as basic integration in CAD tools.
The generated components can be used as bases for the design of own custom
tiles and custom fabrics.

.. warning::

  Please note that the generation of custom tiles and switch matrices is an experimental
  feature and should be treated with care. Please double-check all generated
  files, they might need some manual additions or changes.


Generating and testing a custom tile
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
In this section we describe how to add a basic custom tile and use it in your user design.
As an example for a custom tile, we implement a simple CRC5 generator, as it is used in USB2.0.

FABulous already provides a set of default tiles which can be used to design an FPGA
fabric. For designing a custom tile with custom functionality, you should provide
one or more custom BELs with the desired functionality.


.. note::

    Currently, the tile generation is based on the default FABulous fabric
    and supports only up to 32 input and 8 output internal ports per tile, cumulated
    over all provided BELs. External ports are not counted, since they don't
    connect to the switch matrix.


.. code-block:: verilog

    //-----------------------------------------------------------------------------
    // CRC5 module
    // Generates a CRC5 polynomial crc_out[4:0]=1+x^2+x^5 for a 16-bit input data_in[15:0]
    //-----------------------------------------------------------------------------
    module crc5(
      input [15:0] data_in,
      input crc_en,
      output [4:0] crc_out,
      input rst,
      input clk
      );
      reg [4:0] lfsr_q,lfsr_c;
      assign crc_out = lfsr_q;
      always @(*) begin
        lfsr_c[0] = lfsr_q[0] ^ lfsr_q[1] ^ lfsr_q[2] ^ data_in[0] ^ data_in[3] ^ data_in[5] ^ data_in[6] ^ data_in[9] ^ data_in[10] ^ data_in[11] ^ data_in[12] ^ data_in[13];
        lfsr_c[1] = lfsr_q[0] ^ lfsr_q[1] ^ lfsr_q[2] ^ lfsr_q[3] ^ data_in[1] ^ data_in[4] ^ data_in[6] ^ data_in[7] ^ data_in[10] ^ data_in[11] ^ data_in[12] ^ data_in[13] ^ data_in[14];
        lfsr_c[2] = lfsr_q[3] ^ lfsr_q[4] ^ data_in[0] ^ data_in[2] ^ data_in[3] ^ data_in[6] ^ data_in[7] ^ data_in[8] ^ data_in[9] ^ data_in[10] ^ data_in[14] ^ data_in[15];
        lfsr_c[3] = lfsr_q[0] ^ lfsr_q[4] ^ data_in[1] ^ data_in[3] ^ data_in[4] ^ data_in[7] ^ data_in[8] ^ data_in[9] ^ data_in[10] ^ data_in[11] ^ data_in[15];
        lfsr_c[4] = lfsr_q[0] ^ lfsr_q[1] ^ data_in[2] ^ data_in[4] ^ data_in[5] ^ data_in[8] ^ data_in[9] ^ data_in[10] ^ data_in[11] ^ data_in[12];
      end // always
      always @(posedge clk, posedge rst) begin
        if(rst) begin
          lfsr_q <= {5{1'b1}};
        end
        else begin
          lfsr_q <= crc_en ? lfsr_c : lfsr_q;
        end
      end // always
    endmodule // crc

.. note::

    We are using Verilog as HDL language in this example, but the tile generation
    should work similar with VHDL. Please note that Verilog is still the default
    language for FABulous and the VHDL support can miss some features of FABulous.
    If you run in any problems, please check the
    `Issues <https://github.com/FPGA-Research/FABulous/issues>`_
    and `Discussions <https://github.com/FPGA-Research/FABulous/discussions>`_ on the
    `FABulous GitHub Page <https://github.com/FPGA-Research/FABulous>`_.

Preparation
+++++++++++

Each tile config is usually stored in an individual folder under the `Tile` directory of
your FABulous project. A tile config typically consists of a tile CSV file,
a switch matrix list file and a set of BEL files.

In order to generate a custom tile, we need to create a custom tile folder in your
FABulous project folder.
In our case, we name the folder `CRC5` and place it in the `Tile` folder of our demo project:
`demo/Tile/CRC5`. We add the custom BEL `crc5.v` to the folder.
The folder name, will be also used as the tile name.

.. note::

   The tile config generation also can handle multiple BELs in the same folder.
   All BELs will be automatically added in the config CSV and the switch matrix.

.. warning::

   The tile config generation is based on the default FABulous fabric and does currently
   support a total of 32 input ports and 8 output ports combined over all
   provided BELs in a tile.

For the start, we create a new FABulous demo project and create the folder structure.
We assume, that you have already installed FABulous and the needed dependencies,
as described in the :ref:`Quick start` section.

.. code-block:: console

    (venv)$ FABulous -c demo
    (venv)$ mkdir demo/Tile/CRC5

Afterward we place our BEL file `crc5.v` in the `CRC5` folder.

Annotating the BEL
++++++++++++++++++

FABulous requires a set of annotations in the BEL file to handle it correctly.
The :ref:`primitives` section explains the basic FABulous annotations in detail.
How to add and access bitstream bits in the BEL is described in the :ref:`BELmap` section.

In our case, we just need to annotate the `clk` port of our BEL with the
SHARED_PORT and EXTERNAL.
We also rename the `clk` port to `UserCLK`, since we want to use the same clock as the
rest of the fabric, and therefore the names have to match.

The resulting BEL file with annotations `crc5.v` looks like this:


.. code-block:: verilog

    //-----------------------------------------------------------------------------
    // CRC5 module
    // Generates a CRC5 polynomial crc_out[4:0]=1+x^2+x^5 for a 16-bit input data_in[15:0]
    //-----------------------------------------------------------------------------
    module crc5(
      input [15:0] data_in,
      input crc_en,
      output [4:0] crc_out,
      input rst,
      (* FABulous, EXTERNAL, SHARED_PORT *) input UserCLK
      );
      reg [4:0] lfsr_q,lfsr_c;
      assign crc_out = lfsr_q;
      always @(*) begin
        lfsr_c[0] = lfsr_q[0] ^ lfsr_q[1] ^ lfsr_q[2] ^ data_in[0] ^ data_in[3] ^ data_in[5] ^ data_in[6] ^ data_in[9] ^ data_in[10] ^ data_in[11] ^ data_in[12] ^ data_in[13];
        lfsr_c[1] = lfsr_q[0] ^ lfsr_q[1] ^ lfsr_q[2] ^ lfsr_q[3] ^ data_in[1] ^ data_in[4] ^ data_in[6] ^ data_in[7] ^ data_in[10] ^ data_in[11] ^ data_in[12] ^ data_in[13] ^ data_in[14];
        lfsr_c[2] = lfsr_q[3] ^ lfsr_q[4] ^ data_in[0] ^ data_in[2] ^ data_in[3] ^ data_in[6] ^ data_in[7] ^ data_in[8] ^ data_in[9] ^ data_in[10] ^ data_in[14] ^ data_in[15];
        lfsr_c[3] = lfsr_q[0] ^ lfsr_q[4] ^ data_in[1] ^ data_in[3] ^ data_in[4] ^ data_in[7] ^ data_in[8] ^ data_in[9] ^ data_in[10] ^ data_in[11] ^ data_in[15];
        lfsr_c[4] = lfsr_q[0] ^ lfsr_q[1] ^ data_in[2] ^ data_in[4] ^ data_in[5] ^ data_in[8] ^ data_in[9] ^ data_in[10] ^ data_in[11] ^ data_in[12];
      end // always
      always @(posedge UserCLK, posedge rst) begin
        if(rst) begin
          lfsr_q <= {5{1'b1}};
        end
        else begin
          lfsr_q <= crc_en ? lfsr_c : lfsr_q;
        end
      end // always
    endmodule // crc


Tile Config Generation
++++++++++++++++++++++

To generate the tile config, we use the `generate_custom_tile_config` command in the FABulous CLI:

.. code-block:: console

    FABulous> generate_custom_tile_config -h
    Usage: generate_custom_tile_config [-h] [--no-switch-matrix] tile_path

    Generates a custom tile configuration for a given tile folder
    or path to BEL folder.
    A tile .csv file and a switch matrix .list file will be generated.

    positional arguments:
      tile_path             Path to the target tile directory

    optional arguments:
      -h, --help            show this help message and exit
      --no-switch-matrix, -nosm
                            Do not generate a Tile Switch Matrix

We will now generate the tile config:

.. code-block:: console

    (venv)$ FABulous demo
    FABulous> generate_custom_tile_config Tile/CRC5

The FABulous log output will tell you exactly what it is doing:

.. code-block:: console

    INFO | Generating custom tile config Tile/CRC5
    INFO | Found BEL file Tile/CRC5/crc5.v for custom tile CRC5
    INFO | Creating tile config CSV file Tile/CRC5/CRC5.csv
    INFO | Reading tile configuration: Tile/CRC5/CRC5.csv
    INFO | Generating switch matrix list for tile CRC5
    INFO | Generating matrix file Tile/CRC5/CRC5_generated_switch_matrix.list
    INFO | Creating prims file user_design/custom_prims.v
    INFO | Adding BELs crc5 to yosys primitives file user_design/custom_prims.v.

We'll go through the generated files step by step.
In the `Tile/CRC5` folder, we now have the following files:

.. code-block:: console

    demo/Tile/CRC5
    ├── CRC5.csv
    ├── CRC5_generated_switch_matrix.list
    ├── crc5.v
    └── crc5.json

The `crc5.json` is json netlist of the BEL file, created by Yosys.
It is only needed for the BEL file parsing and can be ignored.

Tile CSV Generation
+++++++++++++++++++

Lets take a look into the `CRC5.csv`:

.. code-block:: console

  TILE,CRC5
  INCLUDE,./../include/Base.csv
  BEL,./crc5.v
  MATRIX,GENERATE
  EndTILE

It contains the standard tile information, includes the base routing .csv, which provides
the standard tile interconnect information for the tiles, and the provided
BEL file. If you want to add more BELs, duplicate a BEL, add a prefix or add additional
routing, you can do it there, like described in the :ref:`fabric_definition` section.

Switch Matrix Generation
++++++++++++++++++++++++

The `MATRIX,GENERATE` line tells FABulous to generate a switch matrix for the tile.

This means, after you have changed the tile .csv, you have to re-run the
`generate_custom_tile_config` in order to update the switch matrix list file,
for example to include additional BELs or routing.

Alternatively, to generating a tile csv file, you can also provide an own tile csv file,
by just placing it in the tile folder. The `generate_custom_tile_config` command
will parse the provided csv file, when it contains a `MATRIX,GENERATE` line,
a switch matrix list file will be generated.

.. warning::

   As long as the `MATRIX,GENERATE` command is in the tile CSV config,
   the switch matrix list file for the tile gets regenerated every time,
   the fabric is regenerated with `run_FABulous_fabric` or
   `generate_custom_tile_config` command is called.
   If you want to make manual changes in the list file directly,
   you should remove the `GENERATE` command from the tile CSV config
   and replace it with the path to the switch matrix list file.
   `MATRIX,./CRC5_generated_switch_matrix.list`

The generated switch matrix list file `CRC5_generated_switch_matrix.list` looks like following
(shortened for clarity):

.. code-block:: console

    # --------------WARNING-----------------
    # This is a generated list file!
    # Your changes will be overwritten!
    # If you want to keep your changes,
    # please make a copy of this file and edit your tile csv.
    # --------------WARNING-----------------
    N2BEGb0,N2MID0
    N2BEGb1,N2MID1
    N2BEGb2,N2MID2
    ...
    ...
    [J2MID_ABa_BEG0|J2MID_ABa_BEG0|J2MID_ABa_BEG0|J2MID_ABa_BEG0],[JN2END3|N2MID6|S2MID6|W2MID6]
    [J2MID_ABa_BEG1|J2MID_ABa_BEG1|J2MID_ABa_BEG1|J2MID_ABa_BEG1],[E2MID2|JE2END3|S2MID2|W2MID2]
    [J2MID_ABa_BEG2|J2MID_ABa_BEG2|J2MID_ABa_BEG2|J2MID_ABa_BEG2],[E2MID4|N2MID4|JS2END3|W2MID4]
    ...
    ...


The generated switch matrix list file is relatively simple, every line contains only
one multiplexer description. This means one output and one or more inputs per line.
The generated switch matrix list file is based on the LUT4AB switch matrix, to ensure
a homogenous routing graph in the whole fabric.


CAD Tool Integration
++++++++++++++++++++

To use our CRC5 custom tile in a user design, the CAD tools (Yosys and nextpnr) also
need to know about our custom tile. The nextpnr integration is automatically resolved
through the nextpnr model, which is generated while the fabric generation.

For Yosys, we need to provide a custom primitives file, which make yosys aware of our
custom BEL primitive. Our custom primitives file is located in the `user_design`
folder of the FABulous project folder and is named `custom_prims.v`

The `generate_custom_tile_config command` automatically creates the `custom_prims.v`,
if it does not exist and adds a blackbox description
of our custom primitive there:

.. code-block:: verilog

    //Warning: The primitive crc5 was added by FABulous automatically.
    (* blackbox, keep *)
    module crc5 (
        input crc_en,
        input data_in0,
        input data_in1,
        input data_in2,
        input data_in3,
        input data_in4,
        input data_in5,
        input data_in6,
        input data_in7,
        input data_in8,
        input data_in9,
        input data_in10,
        input data_in11,
        input data_in12,
        input data_in13,
        input data_in14,
        input data_in15,
        input rst,
        output crc_out0,
        output crc_out1,
        output crc_out2,
        output crc_out3,
        output crc_out4,
        input CLK
    );
    endmodule

This is the minimum to describe the custom primitive to Yosys, but it is enough
to instantiate the custom primitive in a user design. The description is
also the blueprint, how to instantiate the custom primitive in a user design.
You can see, that all vectors are unrolled to individual ports.
This is needed, since our nextpnr integration currently does not support vectors in the
port descriptions. This might change in the future.

You can see, that the `UserCLK` port name was replaced with `CLK` which is the default
clock port name for Yosys.

`EXTERNAL` pins will automatically get decorated with an `(* iopad_external_pin *)` attribute.
This marks it as the external-facing pin of an I/O pad for Yosys and keeps it from trying
to place an IO cell to the pin.

If you are planning to make more advanced custom tiles and also want Yosys optimize your flow,
you should provide the implementation details about your BEL in the primitives file
and provide a custom techmap for your BEL.

Here you can get an introduction how Yosys technology mapping works:

`Logic Primitive Transformations with Yosys Techmap <https://blog.yosyshq.com/p/logic-primitive-transformations-with-yosys-techmap/>`_

For more information, please take a look at the `Yosys documentation <https://yosyshq.readthedocs.io/en/latest/>`_

The `custom_prims.v` will automatically be included in the FABulous bitstream flow,
You can use the FABulous CLI or the provided Makefile in the `Test` folder to generate
your bitstream.
If you are running Yosys manually, you have to specify it manually.
For more information run `yosys -p "help synth_fabulous"`


Generating the Fabric
+++++++++++++++++++++

To finally generate our fabric with our custom prim, we have to place the generated
tile description in our `fabric.csv` file:

.. code-block:: bash

    FabricBegin,,,,,,,,,,,,,,,,,,
    NULL,N_term_single,N_term_single,N_term_single2,N_term_single,N_term_single,N_term_DSP,N_term_single,N_term_single,N_term_RAM_IO,,#,,,,,,,
    W_IO,CRC5,LUT4AB,RegFile,LUT4AB,LUT4AB,DSP_top,LUT4AB,LUT4AB,RAM_IO,,#,,,,,,,
    W_IO,CRC5,LUT4AB,RegFile,LUT4AB,LUT4AB,DSP_bot,LUT4AB,LUT4AB,RAM_IO,,#,,,,,,,
    W_IO,CRC5,LUT4AB,RegFile,LUT4AB,LUT4AB,DSP_top,LUT4AB,LUT4AB,RAM_IO,,#,,,,,,,
    W_IO,CRC5,LUT4AB,RegFile,LUT4AB,LUT4AB,DSP_bot,LUT4AB,LUT4AB,RAM_IO,,#,,,,,,,
    W_IO,CRC5,LUT4AB,RegFile,LUT4AB,LUT4AB,DSP_top,LUT4AB,LUT4AB,RAM_IO,,#,,,,,,,
    W_IO,CRC5,LUT4AB,RegFile,LUT4AB,LUT4AB,DSP_bot,LUT4AB,LUT4AB,RAM_IO,,#,,,,,,,
    W_IO,CRC5,LUT4AB,RegFile,LUT4AB,LUT4AB,DSP_top,LUT4AB,LUT4AB,RAM_IO,,#,,,,,,,
    W_IO,CRC5,LUT4AB,RegFile,LUT4AB,LUT4AB,DSP_bot,LUT4AB,LUT4AB,RAM_IO,,#,,,,,,,
    W_IO,CRC5,LUT4AB,RegFile,LUT4AB,LUT4AB,DSP_top,LUT4AB,LUT4AB,RAM_IO,,#,,,,,,,
    W_IO,CRC5,LUT4AB,RegFile,LUT4AB,LUT4AB,DSP_bot,LUT4AB,LUT4AB,RAM_IO,,#,,,,,,,
    W_IO,CRC5,LUT4AB,RegFile,LUT4AB,LUT4AB,DSP_top,LUT4AB,LUT4AB,RAM_IO,,#,,,,,,,
    W_IO,CRC5,LUT4AB,RegFile,LUT4AB,LUT4AB,DSP_bot,LUT4AB,LUT4AB,RAM_IO,,#,,,,,,,
    W_IO,CRC5,LUT4AB,RegFile,LUT4AB,LUT4AB,DSP_top,LUT4AB,LUT4AB,RAM_IO,,#,,,,,,,
    W_IO,CRC5,LUT4AB,RegFile,LUT4AB,LUT4AB,DSP_bot,LUT4AB,LUT4AB,RAM_IO,,#,,,,,,,
    NULL,S_term_single,S_term_single,S_term_single2,S_term_single,S_term_single,S_term_DSP,S_term_single,S_term_single,S_term_RAM_IO,,#,,,,,,,
    FabricEnd,,,,,,,,,,,,,,,,,,
    ,,,,,,,,,,,,,,,,,,
    ParametersBegin,,,,,,,,,,,,,,,,,,
    ConfigBitMode,frame_based,,,,,,,,,,,,,,,
    #FrameBitsPerRow,32,,,,,,,,,,,,,,,,,
    #MaxFramesPerCol,20,,,,,,,,,,,,,,,,,
    #Package,use work.my_package.all;,,,,,,,,,,,,,,,,,
    GenerateDelayInSwitchMatrix,80,,,,,,,,,,,,,,,,,
    MultiplexerStyle,custom,#,custom,generic,,,,,,,,,,,,,,
    SuperTileEnable,TRUE,#,TRUE,FALSE,,,,,,,,,,,,,,
    ,,,,,,,,,,,,,,,,,,
    Tile,./Tile/LUT4AB/LUT4AB.csv,,,,,,,,,,,,,,,,,
    Tile,./Tile/N_term_single/N_term_single.csv,,,,,,,,,,,,,,,,,
    Tile,./Tile/S_term_single/S_term_single.csv,,,,,,,,,,,,,,,,,
    Tile,./Tile/RAM_IO/RAM_IO.csv,,,,,,,,,,,,,,,,,
    Tile,./Tile/N_term_RAM_IO/N_term_RAM_IO.csv,,,,,,,,,,,,,,,,,
    Tile,./Tile/S_term_RAM_IO/S_term_RAM_IO.csv,,,,,,,,,,,,,,,,,
    Tile,./Tile/RegFile/RegFile.csv,,,,,,,,,,,,,,,,,
    Tile,./Tile/N_term_single2/N_term_single2.csv,,,,,,,,,,,,,,,,,
    Tile,./Tile/S_term_single2/S_term_single2.csv,,,,,,,,,,,,,,,,,
    Tile,./Tile/W_IO/W_IO.csv,,,,,,,,,,,,,,,,,
    Tile,./Tile/DSP/DSP_top/DSP_top.csv,,,,,,,,,,,,,,,,,
    Tile,./Tile/DSP/DSP_bot/DSP_bot.csv,,,,,,,,,,,,,,,,,
    Tile,./Tile/N_term_DSP/N_term_DSP.csv,,,,,,,,,,,,,,,,,
    Tile,./Tile/S_term_DSP/S_term_DSP.csv,,,,,,,,,,,,,,,,,
    Tile,./Tile/CRC5/CRC5.csv
    ,,,,,,,,,,,,,,,,,,
    Supertile,./Tile/DSP/DSP.csv,,,,,,,,,,,,,,,,,
    ,,,,,,,,,,,,,,,,,,
    ParametersEnd,,,,,,,,,,,,,,,,,,

We've replaced a row of LUT4AB tiles with our CRC5 tiles and added our custom tile
config csv in the tile include list.

To generate our fabric, we run the `run_FABulous_fabric` command:

.. code-block:: console

    (venv)$ FABulous demo
    FABulous> load_fabric
    FABulous> run_FABulous_fabric


This generates our custom fabric, with our new custom tile.

Testing the Tile
++++++++++++++++

To test our custom tile, we need to modify our current test setup.
The current simulation setup is described in section :ref:`simulation_setup`.

Our current simulation setup uses a simple counter to test the fabric.
You can find the testbench `sequential_16bit_en_tb.v` in the `Test` folder of your FABulous project.
The `Test` folder also contains a Makefile, which can be used to run the testbench and
a `README.md`,  which describes how to run the testbench.


Our default testbench uses a simple 16-bit counter, to test our fabric.
The counter is once synthesized to a bitstream for our generated FABulous fabric and
also instantiated directly in the testbench. The testbench simulates
our fabric and loads the previously generated bitstream of the counter in our
simulated fabric. Whenever the bitstream is loaded, both counters are reset and the output of
both counters are compared, to ensure that the counter on the simulated fabric
runs similar to the counter in the testbench.

We'll extend this example to include our CRC5 example.
We want to instantiate our custom primitive in the simulated fabric and
compare the output of our CRC5 custom tile, with the output of the simulated
crc5 implementation in the testbench.

The counter is located in the `user_design` folder and is named `sequential_16bit_en.v`.
We want to instantiate the provided `crc5` module in the simulated counter as well as
in the bitstream loaded into the simulated fabric, but the port descriptions
differ. To keep it simple, we are just using the `__ICARUS__` macro,
which is a predefined macro for our simulator Icarus Verilog and can be used
write simulation specific code.
To test our custom primitive, we just use the counter as input for our crc5
module and the output of the crc5 module is assigned to some unused bits of the
output of the counter module.

We just extend our `sequential_16bit_en.v` counter like following:

.. code-block:: verilog

    module top(input wire clk, input wire [27:0] io_in, output wire [27:0] io_out, io_oeb);
        wire rst = io_in[0];
        wire en = io_in[1];
        reg [15:0] ctr;
        wire [4:0] crc_out;
        always @(posedge clk)
            if (en)
                if (rst)
                    ctr <= 0;
                else
                    ctr <= ctr + 1'b1;
            else
                ctr <= ctr;
        assign io_out = {7'b0, crc_out , ctr}; // pass thru reset for debugging
        assign io_oeb = 28'b1;
    //CRC5 Simulation example:
    `ifdef __ICARUS__
    // Icarus Verilog simulation
        crc5 crc5_icarus_i (
            .rst(rst),
            .crc_en(en),
            .UserCLK(clk),
            .data_in(ctr),
            .crc_out(crc_out)
        );
    `else
    // Yosys Synthesis
    // We have to use the custom primitives module description here, as in custom_prims.v
        crc5 crc5_yosys_i (
            .rst(rst),
            .CLK(clk),
            .crc_en(en),
            .data_in0(ctr[0]),
            .data_in1(ctr[1]),
            .data_in2(ctr[2]),
            .data_in3(ctr[3]),
            .data_in4(ctr[4]),
            .data_in5(ctr[5]),
            .data_in6(ctr[6]),
            .data_in7(ctr[7]),
            .data_in8(ctr[8]),
            .data_in9(ctr[9]),
            .data_in10(ctr[10]),
            .data_in11(ctr[11]),
            .data_in12(ctr[12]),
            .data_in13(ctr[13]),
            .data_in14(ctr[14]),
            .data_in15(ctr[15]),
            .crc_out0(crc_out[0]),
            .crc_out1(crc_out[1]),
            .crc_out2(crc_out[2]),
            .crc_out3(crc_out[3]),
            .crc_out4(crc_out[4])
        );
    `endif
    endmodule

Afterward, we just run our simulation with the FABulous CLI command `run_simulation`:

.. code-block:: console

    (venv)$ FABulous demo
    FABulous> load_fabric
    FABulous> run_FABulous_fabric
    FABulous> run_FABulous_bitstream ./user_design/sequential_16bit_en.v
    FABulous> run_simulation fst ./user_design/sequential_16bit_en.bin
    FABulous> exit


These commands build our FABulous fabric, generates a bitstream from our
extended counter example and runs the simulation afterward.
The output of the whole flow is quite a lot, for debugging, we recommend
running the steps individually, to see what is actually going on.

.. code-block:: console

    iverilog -s sequential_16bit_en_tb -o build/sequential_16bit_en.vvp build/fabric_files/* ../user_design/sequential_16bit_en.v sequential_16bit_en_tb.v -g2012
    vvp build/sequential_16bit_en.vvp +output_waveform=build/sequential_16bit_en.fst +bitstream_hex=build/sequential_16bit_en.hex -fst
    FST info: dumpfile build/sequential_16bit_en.fst opened for output.
    Output waveform set to build/sequential_16bit_en.fst
    Read bitstream hex from build/sequential_16bit_en.hex
    fabric(I_top) = 0x01f0000 gold = 0x01f0000, fabric(T_top) = 0xffffffe gold = 0xffffffe
    fabric(I_top) = 0x0010001 gold = 0x0010001, fabric(T_top) = 0xffffffe gold = 0xffffffe
    fabric(I_top) = 0x01e0002 gold = 0x01e0002, fabric(T_top) = 0xffffffe gold = 0xffffffe
    fabric(I_top) = 0x0100003 gold = 0x0100003, fabric(T_top) = 0xffffffe gold = 0xffffffe
    fabric(I_top) = 0x0030004 gold = 0x0030004, fabric(T_top) = 0xffffffe gold = 0xffffffe
    ...
    shortened for clarity
    ...
    fabric(I_top) = 0x003005f gold = 0x003005f, fabric(T_top) = 0xffffffe gold = 0xffffffe
    fabric(I_top) = 0x0030060 gold = 0x0030060, fabric(T_top) = 0xffffffe gold = 0xffffffe
    fabric(I_top) = 0x01e0061 gold = 0x01e0061, fabric(T_top) = 0xffffffe gold = 0xffffffe
    fabric(I_top) = 0x0090062 gold = 0x0090062, fabric(T_top) = 0xffffffe gold = 0xffffffe
    fabric(I_top) = 0x0010063 gold = 0x0010063, fabric(T_top) = 0xffffffe gold = 0xffffffe
    sequential_16bit_en_tb.v:107: $finish called at 207060000 (1ps)
    rm -rf build


You can see, that our `I_top` output and the `gold` output always match and
have no undefined values. This indicates, that our custom tile is working
correctly.

.. warning::

   This testbench is just a simple example, to show how to test and use your custom tile.
   But it does not necessarily mean, that the custom primitives' functionality is correct.
   This test just shows, that our custom primitive can be instantiated correctly and
   in a user design and outputs the same values as instantiated directly in the simulation.
   Please make sure to verify your custom BEL before you build a custom tile with it.


Working with multiple BELs
~~~~~~~~~~~~~~~~~~~~~~~~~~
In this example, we'll generate a custom LUT tile, based on our standard
`LUT4c_frame_config_dffesr` implementation, to show how to work with multiple BELs.
The LUT4c_frame_config_dffesr implementation is a standard LUT4 with a flip-flop and
a carry chain:

.. code-block:: verilog

    (*FABulous, BelMap, INIT=0, INIT_1=1, INIT_2=2, INIT_3=3, INIT_4=4, INIT_5=5, INIT_6=6,
    INIT_7=7, INIT_8=8, INIT_9=9, INIT_10=10, INIT_11=11, INIT_12=12, INIT_13=13, INIT_14=14,
    INIT_15=15, FF=16, IOmux=17, SET_NORESET=18 *)
    module LUT4c_frame_config_dffesr #(parameter NoConfigBits = 19)(
        input [3:0]  I,   // Vector for I0, I1, I2, I3
        output       O,           // Single output for LUT result
        input        Ci,          // Carry chain input
        output       Co,          // Carry chain output
        input        SR,          // SHARED_RESET
        input        EN,          // SHARED_ENABLE
        (* FABulous, EXTERNAL, SHARED_PORT *) input UserCLK, // External and shared clock
        (* FABulous, GLOBAL *) input [NoConfigBits-1:0] ConfigBits // Config bits as vector
    );
        localparam LUT_SIZE = 4;
        localparam N_LUT_flops = 2 ** LUT_SIZE;
        wire [N_LUT_flops-1 : 0] LUT_values;
        wire [LUT_SIZE-1 : 0] LUT_index;
        wire LUT_out;
        reg LUT_flop;
        wire I0mux; // normal input '0', or carry input '1'
        wire c_out_mux, c_I0mux, c_reset_value; // extra configuration bits
        assign LUT_values = ConfigBits[15:0];
        assign c_out_mux  = ConfigBits[16];
        assign c_I0mux = ConfigBits[17];
        assign c_reset_value = ConfigBits[18];

        // MUX2 for seelecting between I0 and Ci
        cus_mux21 cus_mux21_I0mux(
        .A0(I[0]),
        .A1(Ci),
        .S(c_I0mux),
        .X(I0mux)
        );

        assign LUT_index = {I[3],I[2],I[1],I0mux};

        // MUX16 for our main LUT4 implementation
        cus_mux161_buf inst_cus_mux161_buf(
        .A0(LUT_values[0]),
        .A1(LUT_values[1]),
        .A2(LUT_values[2]),
        .A3(LUT_values[3]),
        .A4(LUT_values[4]),
        .A5(LUT_values[5]),
        .A6(LUT_values[6]),
        .A7(LUT_values[7]),
        .A8(LUT_values[8]),
        .A9(LUT_values[9]),
        .A10(LUT_values[10]),
        .A11(LUT_values[11]),
        .A12(LUT_values[12]),
        .A13(LUT_values[13]),
        .A14(LUT_values[14]),
        .A15(LUT_values[15]),
        .S0 (LUT_index[0]),
        .S0N(+LUT_index[0]),
        .S1 (LUT_index[1]),
        .S1N(+LUT_index[1]),
        .S2 (LUT_index[2]),
        .S2N(+LUT_index[2]),
        .S3 (LUT_index[3]),
        .S3N(+LUT_index[3]),
        .X  (LUT_out)
        );

        // MUX2 for selecting between combinatorial and flip-flop output
        cus_mux21 cus_mux21_O(
        .A0(LUT_out),
        .A1(LUT_flop),
        .S(c_out_mux),
        .X(O)
        );

        // iCE40 like carry chain (as this is supported in Yosys; would normally go for fractured LUT)
        assign Co = (Ci & I[1]) | (Ci & I[2]) | (I[1] & I[2]);

        // LUT flip-flop
        always @ (posedge UserCLK) begin
            if (EN) begin
                if (SR)
                    LUT_flop <= c_reset_value;
                else
                    LUT_flop <= LUT_out;
            end
        end
    endmodule


Shared RESET and ENABLE Ports
+++++++++++++++++++++++++++++
The tile generator also supports shared reset and enable ports.
To mark the enable/reset BEL ports, we can use the `SHARED_RESET` and `SHARED_ENABLE`
attribute in the port description.
The `SHARED_RESET` and `SHARED_ENABLE` ports are automatically grouped together in the whole
tile. This means there will only be one shared `SHARED_RESET` and one `SHARED_ENABLE`
port per tile. This is common practice in FPGAs to save routing resources.
`SHARED_RESET` and `SHARED_ENABLE` ports, will not be counted as internal ports,
so our limit of 32 internal ports and 8 internal outputs for our BELs, is not affected by them.


Carry Chains
++++++++++++

Our custom tile generation also supports carry chains.
The carry chain will always be routed vertically from BEL to BEL and also from tile to tile.
Specify a carry chain for the tile generator, we need to annotate a `CARRY` attribute to the
ports, that BELong the carry chain.
The `CARRY` attribute can be used in the port description of the BEL file.
There always need to be a carry input and a carry output port in the BEL file, which
both need to be marked with the `CARRY` attribute.

As well as our `SHARED_RESET` and `SHARED_ENABLE` ports, the `CARRY` ports are not counted
as internal ports and are therefore, they also not affect our port limitations per tile.

It is also possible to define multiple CARRY ports in a tile. Each CARRY port
then needs an individual prefix, which we set in the `CARRY` attribute with an equal sign:
`CARRY="prefix"`. The prefix is a sting value and has to be surrounded with quotes.

.. note::

   The `CARRY` attribute has currently no vector support and can only be used with single wires!
   But you can instantiate multiple carry chains in a tile, by using different prefixes.


Annotating the BELs
+++++++++++++++++++
Before we can generate our custom tile, we have to annotate our BEL ports first.
We add the `CARRY` attribute to the carry input and output ports. Just for
completion, we also define a carry prefix `CARRY=0`, which is only mandatory if we have
more than one carry bit. We also set the `SHARED_RESET` and `SHARED_ENABLE` attributes for
our enable and reset ports. We will also rename our module to `LUT4c_test` to avoid
conflicts with the original `LUT4c_frame_config_dffesr` module.

Our annotated port list of our `LUT4_test`` looks like following:

.. code-block:: verilog

    (*FABulous, BelMap, INIT=0, INIT_1=1, INIT_2=2, INIT_3=3, INIT_4=4, INIT_5=5, INIT_6=6,
    INIT_7=7, INIT_8=8, INIT_9=9, INIT_10=10, INIT_11=11, INIT_12=12, INIT_13=13, INIT_14=14,
    INIT_15=15, FF=16, IOmux=17, SET_NORESET=18 *)
    module LUT4c_test #(parameter NoConfigBits = 19)(
        input [3:0]  I,           // Vector for I0, I1, I2, I3
        output       O,           // Single output for LUT result
        (* FABulous, CARRY=0 *)      input   Ci,          // Carry chain input
        (* FABulous, CARRY=0 *)      output  Co,          // Carry chain output
        (* FABulous, SHARED_RESET *)  input   SR,          // SHARED_RESET
        (* FABulous, SHARED_ENABLE *) input   EN,          // SHARED_ENABLE
        (* FABulous, EXTERNAL, SHARED_PORT *) input UserCLK, // External and shared clock
        (* FABulous, GLOBAL *) input [NoConfigBits-1:0] ConfigBits // Config bits as vector
    );
    ...

Generating the Custom Tile
++++++++++++++++++++++++++

After we annotated our BEL, we can generate our custom tile.
We save the BEL to our tile folder in our demo project `demo/Tile/LUT4_test`
and generate our custom tile with the `generate_custom_tile_config` command
in the FABulous CLI:

.. code-block:: console

    (venv)$ FABulous demo
    FABulous> load_fabric
    FABulous> generate_custom_tile_config Tile/LUT4_test

This will generate a custom tile config file in the `Tile/LUT4_TEST` folder:

.. code-block:: console

    LUT_TEST
    ├── LUT4_TEST.csv
    ├── LUT4_TEST_generated_switch_matrix.list
    ├── LUT4_test.json
    └── LUT4_test.v

First we take a look at our tile csv `LUT4_TEST.csv`:

.. code-block:: bash

    TILE,LUT4_TEST
    INCLUDE,./../include/Base.csv
    NORTH,Co0,0,-1,Ci0,1,CARRY="C0"
    JUMP,J_SRST_BEG,0,0,J_SRST_END,1,SHARED_RESET
    JUMP,J_SEN_BEG,0,0,J_SEN_END,1,SHARED_ENABLE
    BEL,./LUT4_test.v
    MATRIX,GENERATE
    EndTILE

You can see the annotated information for our carry chain `CARRY="CO"` as well as our
shared reset `SHARED_RESET` and `SHARED_ENABLE` ports.

.. note::

    The annotation of the ports in the tile csv and the ports of your BEL always have to
    match! If you want to create the tile csv by yourself, you have to make
    sure, any `CARRY/SHARED_RESET/SHARED_ENABLE` annotation in the BEL files,
    are also needs a corresponding annotation in the tile csv.

    This is needed, that our switch matrix generator knows, which ports
    of the BEL BELongs to which tile ports.
    Otherwise, an error will be thrown.


You can see in the tile csv file is currently only one BEL instantiated.
We can now just copy the BEL entries and add a prefix for each BEL.

.. code-block:: bash

    TILE,LUT4_TEST
    INCLUDE,./../include/Base.csv
    NORTH,Co0,0,-1,Ci0,1,CARRY="C0"
    JUMP,J_SRST_BEG,0,0,J_SRST_END,1,SHARED_RESET
    JUMP,J_SEN_BEG,0,0,J_SEN_END,1,SHARED_ENABLE
    BEL,./LUT4_test.v,LT_A_
    BEL,./LUT4_test.v,LT_B_
    BEL,./LUT4_test.v,LT_C_
    BEL,./LUT4_test.v,LT_D_
    BEL,./LUT4_test.v,LT_E_
    BEL,./LUT4_test.v,LT_F_
    BEL,./LUT4_test.v,LT_G_
    BEL,./LUT4_test.v,LT_H_
    MATRIX,GENERATE
    EndTILE

Since we are restricted to 32 inputs and 8 outputs over to whole BEL,
excluding, `EXTERNAL`, `SHARED`, `CARRY`, `SHARED_ENABLE` and `SHARED_RESET` ports.
We can add 8 of our `LUT4_test` BELs to the custom tile, since we have
4 inputs and 1 output each. We have added
prefixes `LT_A_` to `LT_H_` to the BEL entries. This is needed that the BELs
can be identified as individual BELs.

Afterward, we can generate our custom tile with the `generate_custom_tile_config` command
again. This will generate our generate the switch matrix and the custom prims
file. We can now use the custom tile like any other tile in the `fabric.csv`.

.. note::

    This example is shows how to work with multiple BELs in a custom tile, based on
    our own LUT4 implementation. This means our carry chain implementation is already
    supported in Yosys and should work out of the box. If you are implementing
    a custom carry logic, you should also consider implementing custom
    techmap scripts for Yosys!

    Alternatively, you can use [absolute placement constraints] (https://github.com/YosysHQ/nextpnr/blob/master/docs/constraints.md#absolute-placement-constraints)
    to exactly specify which BELs should be instantiated.

.. _gen_io:

Generative IOs (GEN_IO)
-----------------------

The GEN_IO keyword generates generic IO Bels for FABulous.
Each IO has a EXTERNAL port to the top level of the Fabric and an internal port, that
is routed to the switch matrix.

GEN_IOs can be used as following in the fabric.csv::

  GEN_IO,<Number of Pins>,<Direction>,<Prefix>,[<Parameters>]

The direction is defined as either INPUT or OUTPUT and is defined from the fabric side.
This means an OUTPUT will be an output from the fabric side, so its an input port at the top level.
The IO generator will generate an generic IO Bel for every tile.


fabric.csv::

  GEN_IO,2,OUTPUT,A_O,,,,,,,,,,,,,,
  GEN_IO,2,INPUT,A_I,,,,,,,,,,,,,,

This will generate four IOs, two input (A_I0, A_I1) and two output (A_O0, A_O1)
IOs, which can be accessed in the tile through the switch matrix.
This will also generate four external ports, (A_I0_top, A_I1_top,
A_O0_top, A_O1_top) which are routed to the top level and are connected
to the equivalent tile ports. The :ref:gen_io_example: will make this more clear.


GEN_IO Parameters
~~~~~~~~~~~~~~~~~

* **CONFIGACCESS**: This flag will generate config access bits for the tile.
  Config access bits are simply config bit from the configuration bitstream,
  that are routed to the top level. They can be used to configure external
  IPs or devices through the bitstream. The number of config access bits
  generated is equal to the number of pins in the GEN_IO.
  The config access bits are routed to the top level where they can be
  connected to external.

  GEN_IO.csv::

    GEN_IO,2,OUTPUT,C_,CONFIGACCESS,,,,,,,,,,,,,

  Will generate 2 config access bits for this tile, that will be routed to
  top level.

  The config Access ports will be generated as as a separate Bel file and are not
  connected to the switch matrix.

* **CLOCKED**: This flag will add a register to the GEN_IO,
  which will be clocked by the UserCLK signal.

  fabric.csv::

     GEN_IO,2,OUTPUT,A_O_,CLOCKED,,,,,,,,,,,,,

  Will generate 2 output ports for the fabric, that are clocked.

* **CLOCKED_COMB**: This flag creates two signals for every GEN_IO.
  <prefix><Number>_Q: The clocked signal, which is clocked by UserCLK signal.
  <prefix><Number>: The original combinatorial signal.
  If the GEN_IO is an INPUT, then there will be
  two signals to the top, <prefix><Number>_Q_top is the clocked input
  signal and <prefix><Number>_top is the combinatorial input signal.
  If the GEN_IO is an OUTPUT, then there will be two signals connected
  to the switch matrix, <prefix><Number>_Q is the clocked output signal
  and <prefix><Number> is the combinatorial output signal.

  GEN_IO.csv::

     GEN_IO,2,OUTPUT,A_O_,CLOCKED_COMB,,,,,,,,,,,,,

  Will generate 4 output ports for the fabric, 2 that are clocked and
  2 combinatorial.

* **CLOCKED_MUX**: This flag is quite similar to the CLOCKED_COMB feature, but
  instead of routing the combinatorial and the clocked signal to two individual outputs,
  it adds a multiplexer, that can selected between the clocked and the combinatorial signal.
  The selection of the signal is done via configuration bits, so for each port,
  there will be one bit added to the `INIT` param of the IO bel.
  Per default, the combinatorial signal is selected.

  GEN_IO.csv::

     GEN_IO,2,OUTPUT,A_O_,CLOCKED_MUX,,,,,,,,,,,,,

  Will generate 2 output ports for the fabric, that can be individually selected
  if they should be clocked or combinatorial.

* **INVERTED**: This flag will invert the generated IOs.

  GEN_IO.csv::

     GEN_IO,2,OUTPUT,A_O_,INVERTED,,,,,,,,,,,,,

  Will generate 2 output ports for the fabric, that are inverted.
  Can be also used with CONFIGACCESS or CLOCKED:

  GEN_IO.csv::

     GEN_IO,2,OUTPUT,C_,CONFIGACCESS,INVERTED,,,,,,,,,,,,

  Will generate 2 config access bits for this tile, which are inverted.

.. _gen_io_example:

GEN_IO Example
~~~~~~~~~~~~~~

The following example shows how to replace our current W_IO implementation in the default Fabric with GEN_IOs.
We use Verilog as default language for the example, but the same can be done with VHDL.

We first start with creating a new demo project:

.. code-block:: console

    (venv)$ FABulous -c demo

The demo project is created in the `demo` folder has the following structure (all unneeded files are hidden)

.. code-block:: console

  demo
  ├── Fabric        # Static Fabric Files
  │   └── ...
  ├── fabric.csv    # Fabric Configuration File
  ├── Test          # Test Files
  │   └── ...
  ├── Tile          # Tile Configuration Files
  │   ├── ...
  │   └── W_IO      # W_IO Tile Configuration Files
  │       ├── Config_access.v
  │       ├── IO_1_bidirectional_frame_config_pass.v
  │       ├── W_IO.csv
  │       └── W_IO_switch_matrix.list
  └── user_design   # User Design Files
      └── ...

Currently, we need three files to implement the W_IOs, the tile definition (W_IO.csv),
the switch matrix (W_IO_switch_matrix.list) and the Verilog/VHDL file (IO_1_bidirectional_frame_config_pass.v).

The default W_IO.csv file looks like following:

.. code-block:: Bash

  TILE,W_IO,,,,,,,,,,,,,,,,,
  #direction,source_name,X-offset,Y-offset,destination_name,wires,,,,,,,,,,,,,
  EAST,E1BEG,1,0,NULL,4,,,,,,,,,,,,,
  EAST,E2BEG,1,0,NULL,8,,,,,,,,,,,,,
  EAST,E2BEGb,1,0,NULL,8,,,,,,,,,,,,,
  EAST,EE4BEG,4,0,NULL,4,,,,,,,,,,,,,
  EAST,E6BEG,6,0,NULL,2,,,,,,,,,,,,,
  WEST,NULL,-1,0,W1END,4,,,,,,,,,,,,,
  WEST,NULL,-1,0,W2MID,8,,,,,,,,,,,,,
  WEST,NULL,-1,0,W2END,8,,,,,,,,,,,,,
  WEST,NULL,-4,0,WW4END,4,,,,,,,,,,,,,
  WEST,NULL,-6,0,W6END,2,,,,,,,,,,,,,
  JUMP,NULL,0,0,GND,1,,,,,,,,,,,,,
  JUMP,NULL,0,0,VCC,1,,,,,,,,,,,,,
  BEL,./IO_1_bidirectional_frame_config_pass.v,A_,,,,,,,,,,,,,,,,
  BEL,./IO_1_bidirectional_frame_config_pass.v,B_,,,,,,,,,,,,,,,,
  BEL,./Config_access.v,A_config_,,,,,,,,,,,,,,,,
  BEL,./Config_access.v,B_config_,,,,,,,,,,,,,,,,
  MATRIX,./W_IO_switch_matrix.list,,,,,,,,,,,,,,,,,
  EndTILE,,,,,,,,,,,,,,,,,,

At the top, we define our EAST/WEST connections for our connecting tiles.
We also define the JUMP wires for the GND and VCC connections.
The BEL statements define the Verilog/VHDL files that are used to implement the IOs.
The MATRIX statement defines the switch matrix that is used to connect the IOs to the switch matrix.

For our W_IO Tile we have two IOs, A and B, which are implemented in the IO_1_bidirectional_frame_config_pass.v file.
Our IO_1_bidirectional_frame_config_pass.v file looks like following:

.. code-block:: Verilog

  module IO_1_bidirectional_frame_config_pass (I, T, O, Q, I_top, T_top, O_top, UserCLK);//, ConfigBits);
    //parameter NoConfigBits = 0; // has to be adjusted manually (we don't use an arithmetic parser for the value)
    input I; // from fabric to external pin
    input T; // tristate control
    output O; // from external pin to fabric
    output Q; // from external pin to fabric (registered)
    (* FABulous, EXTERNAL *) output I_top; // EXTERNAL has to ge to top-level entity not the switch matrix
    (* FABulous, EXTERNAL *) output T_top; // EXTERNAL has to ge to top-level entity not the switch matrix
    (* FABulous, EXTERNAL *) input O_top; // EXTERNAL has to ge to top-level entity not the switch matrix
    (* FABulous, EXTERNAL, SHARED_PORT *) input UserCLK; // EXTERNAL // SHARED_PORT // the EXTERNAL keyword will send this signal all the way to top and the //SHARED Allows multiple BELs using the same port (e.g. for exporting a clock to the top)
    (* FABulous, GLOBAL *)
    reg Q;
    assign O = O_top;
    assign I_top = I;
    assign T_top = ~T;

    always @ (posedge UserCLK)
    begin
      Q <= O_top;
    end
  endmodule

It implements a bidirectional IO with a tristate control and a registered output.
The I_top, T_top, O_top and UserCLK signals are exported to the top-level entity,
since they are declared as EXTERNAL. The I, T, O and Q signals are connected to the
switch matrix in the tile.

We also have a Config_access.v file, which is used to implement the config access bits for the tile.
The Config_access.v file looks like following:

.. code-block:: Verilog

  (* FABulous, BelMap, C_bit0=0, C_bit1=1, C_bit2=2, C_bit3=3 *)
  module Config_access (C_bit0, C_bit1, C_bit2, C_bit3, ConfigBits);
    parameter NoConfigBits = 4;// has to be adjusted manually (we don't use an arithmetic parser for the value)
    (* FABulous, EXTERNAL *)output C_bit0; // EXTERNAL
    (* FABulous, EXTERNAL *)output C_bit1; // EXTERNAL
    (* FABulous, EXTERNAL *)output C_bit2; // EXTERNAL
    (* FABulous, EXTERNAL *)output C_bit3; // EXTERNAL
    (* FABulous, GLOBAL *)input [NoConfigBits-1:0] ConfigBits;
    assign C_bit0 = ConfigBits[0];
    assign C_bit1 = ConfigBits[1];
    assign C_bit2 = ConfigBits[2];
    assign C_bit3 = ConfigBits[3];
  endmodule

It just wires four config bits as EXTERNAL ports to the top-level entity.

For reworking the W_IO tile with GEN_IO to use GEN_IOs instead our handcrafted IOs,
we start with copying the W_IO tile folder to a new folder called GEN_W_IO.
Next we rename all files accordingly and remove the Bel files, we don't need these
anymore.

.. code-block:: Bash

   $(venv) cp -r demo/Tile/W_IO demo/Tile/GEN_W_IO

   $(venv) mv demo/Tile/GEN_W_IO/W_IO.csv demo/Tile/GEN_W_IO/GEN_W_IO.csv
   $(venv) mv demo/Tile/GEN_W_IO/W_IO_switch_matrix.list demo/Tile/GEN_W_IO/GEN_W_IO_switch_matrix.list

   $(venv) rm demo/Tile/GEN_W_IO/IO_1_bidirectional_frame_config_pass.v
   $(venv) rm demo/Tile/GEN_W_IO/Config_access.v


Now we have the following structure in our `demo/Tile/GEN_W_IO` folder:

.. code-block:: Bash

  demo
  ├── ...
  ├── Tile
  │   └── ...
  │   └── GEN_W_IO
  │       ├── GEN_W_IO.csv
  │       └── GEN_W_IO_switch_matrix.list


Then we need to change the tile CSV description to add the new tile name and
replace the BEL statements and with our GEN_IO statements.
The new W_IO.csv should look something like the following:

.. code-block:: Bash

  TILE,GEN_W_IO,,,,,,,,,,,,,,,,,
  #direction,source_name,X-offset,Y-offset,destination_name,wires,,,,,,,,,,,,,
  EAST,E1BEG,1,0,NULL,4,,,,,,,,,,,,,
  EAST,E2BEG,1,0,NULL,8,,,,,,,,,,,,,
  EAST,E2BEGb,1,0,NULL,8,,,,,,,,,,,,,
  EAST,EE4BEG,4,0,NULL,4,,,,,,,,,,,,,
  EAST,E6BEG,6,0,NULL,2,,,,,,,,,,,,,
  WEST,NULL,-1,0,W1END,4,,,,,,,,,,,,,
  WEST,NULL,-1,0,W2MID,8,,,,,,,,,,,,,
  WEST,NULL,-1,0,W2END,8,,,,,,,,,,,,,
  WEST,NULL,-4,0,WW4END,4,,,,,,,,,,,,,
  WEST,NULL,-6,0,W6END,2,,,,,,,,,,,,,
  JUMP,NULL,0,0,GND,1,,,,,,,,,,,,,
  JUMP,NULL,0,0,VCC,1,,,,,,,,,,,,,
  GEN_IO,2,INPUT,I,,,,,,,,,,,,,,
  GEN_IO,2,OUTPUT,O,CLOCKED_COMB,,,,,,,,,,,,,
  GEN_IO,2,OUTPUT,T,INVERTED,,,,,,,,,,,,,
  GEN_IO,4,OUTPUT,A_config_,CONFIGACCESS,,,,,,,,,,,,,
  GEN_IO,4,OUTPUT,B_config_,CONFIGACCESS,,,,,,,,,,,,,
  MATRIX,./W_IO_switch_matrix.list,,,,,,,,,,,,,,,,,
  EndTILE,,,,,,,,,,,,,,,,,,

This will generate two Bel files, they'll have the same  number of IOs and config access
bits as before, but now using our GEN_IO keyword. They will be generated automatically
in either VHDL or Verilog, depending on the FABulous configuration.

To generate the IO Bel, you can either just run the `run_FABulous_fabric` command
in the FABulous CLI, which will generate the IO Bel files automatically, while
generating the whole farbic. But for debugging purposes, you can also
use the `gen_io_tiles`` command:

.. code-block:: console

    (venv)$ FABulous demo
    FABulous> gen_io_tiles GEN_W_IO

This will generate the IO Bel files in the `Tile/GEN_W_IO_GenIO` folder, from the
config in the `Tile/GEN_W_IO/GEN_W_IO.csv` file.
This is an example Verilog output for the config above:

.. code-block:: Verilog

  //Generative IO BEL for GEN_W_IO_GenIO
  //This is a generated file, please don't edit!

  module GEN_W_IO_GenIO
      (
          input  I0,
          input  I1,
          output reg O0_Q,
          output  O0,
          output reg O1_Q,
          output  O1,
          input  T0,
          input  T1,
          (* FABulous, EXTERNAL *) output  I0_top,
          (* FABulous, EXTERNAL *) output  I1_top,
          (* FABulous, EXTERNAL *) input  O0_top,
          (* FABulous, EXTERNAL *) input  O1_top,
          (* FABulous, EXTERNAL *) output  T0_top,
          (* FABulous, EXTERNAL *) output  T1_top,
          (* FABulous, EXTERNAL, SHARED *) input  UserCLK
      );


  assign I0_top = I0;
  assign I1_top = I1;

  always @ (posedge UserCLK)
  begin
      O0_Q <= O0_top;
  end

  assign O0 = O0_top;

  always @ (posedge UserCLK)
  begin
      O1_Q <= O1_top;
  end

  assign O1 = O1_top;
  assign T0_top = ~T0;
  assign T1_top = ~T1;

  endmodule

The config access files are generated separately and look like following:

.. code-block:: Verilog

  //Generative IO BEL for GEN_W_IO_ConfigAccess_GenIO
  //This is a generated file, please don't edit!

  (* FABulous, BelMap, INIT=0, INIT_1=1, INIT_2=2, INIT_3=3, INIT_4=4, INIT_5=5, INIT_6=6, INIT_7=7 *)

  module GEN_W_IO_ConfigAccess_GenIO
      #(
          parameter NoConfigBits=8
      )
      (
          (* FABulous, EXTERNAL *) output  A_config_0,
          (* FABulous, EXTERNAL *) output  A_config_1,
          (* FABulous, EXTERNAL *) output  A_config_2,
          (* FABulous, EXTERNAL *) output  A_config_3,
          (* FABulous, EXTERNAL *) output  B_config_0,
          (* FABulous, EXTERNAL *) output  B_config_1,
          (* FABulous, EXTERNAL *) output  B_config_2,
          (* FABulous, EXTERNAL *) output  B_config_3,
          input reg [NoConfigBits -1:0] ConfigBits
      );


   //gen_io config access
  assign A_config_0 = ConfigBits[0];
  assign A_config_1 = ConfigBits[1];
  assign A_config_2 = ConfigBits[2];
  assign A_config_3 = ConfigBits[3];
  assign B_config_0 = ConfigBits[4];
  assign B_config_1 = ConfigBits[5];
  assign B_config_2 = ConfigBits[6];
  assign B_config_3 = ConfigBits[7];


  endmodule

Now we just need to change the names in the switch matrix list file, since the naming scheme for the IOs has changed.
Our generated IOs will be named I0, I1, T0, T1, O0, O1, O_Q0, O_Q1 which were previously named A_I, A_O, B_I, B_O, A_T, B_T, A_Q, B_Q.
So we just have to replace all the occurrences in the switch matrix list file.
The ports for the config access bits are named.
A_config_0, A_config_1, A_config_2, A_config_3, B_config_0, B_config_1, B_config_2, B_config_3.
For the config access bits we don't need to change anything, since they are **EXTERNAL** pins, that don't connect to the switch matrix.

Our previous switch matrix list file should look like the following:

.. code-block:: Bash

    # W_IO
    # Fabric to PAD output multiplexers
    A_[I|I|I|I|I|I|I|I],W2MID[0|1|2|3|4|5|6|7]
    A_[I|I|I|I|I|I|I|I],W2END[0|1|2|3|4|5|6|7]
    B_[I|I|I|I|I|I|I|I],W2MID[0|1|2|3|4|5|6|7]
    B_[I|I|I|I|I|I|I|I],W2END[0|1|2|3|4|5|6|7]
    A_[T|T|T|T|T|T|T|T],[W2END0|W2END1|W2END2|W2END3|W2END4|W2MID7|VCC0|GND0]
    B_[T|T|T|T|T|T|T|T],[W2END0|W2END4|W2END5|W2END6|W2MID6|W2MID7|VCC0|GND0]

    ### # single just go back, we swap bits in vector to get more twists into the graph
    E1BEG[0|1|2|3],W1END[3|2|1|0]
    # Single get connected to PAD output
    E1BEG[0|1|2|3],[A_O|A_Q|B_O|B_Q]

    # we also connect the hex wires
    # Note that we only have 2 wires starting in each CLB (so 2x6=12 wires in the channel)
    # we connect the combinatorial outputs in every other column and the register outputs in the remaining columns
    E6BEG[0|1|6|7],[A_O|B_O|A_Q|B_Q]
    E6BEG[2|3|8|9],[A_O|B_O|A_Q|B_Q]
    E6BEG[4|5|10|11],[A_O|B_O|A_Q|B_Q]
    E6BEG[0|1|6|7],W6END[11|10|9|8]
    E6BEG[2|3|8|9],W6END[7|6|5|4]
    E6BEG[4|5|10|11],W6END[3|2|1|0]
    E6BEG[0|1|6|7],WW4END[11|10|9|8]
    E6BEG[2|3|8|9],WW4END[7|6|5|4]
    E6BEG[4|5|10|11],WW4END[3|2|1|0]
    E6BEG[0|1|6|7],W1END[2|3|1|0]
    E6BEG[2|3|8|9],WW4END[15|14|13|12]
    E6BEG[4|5|10|11],W1END[2|3|1|0]

    # The MID are half way in so they get connected to the longest patch (S2BEG)
    # The END are longest so get on the cascading begin (S2BEGb)
    # on top we twist wire indexes for more entropy
    E2BEGb[0|1|2|3|4|5|6|7],W2END[7|6|5|4|3|2|1|0]
    E2BEGb[0|1|2|3|4|5|6|7],WW4END[7|6|5|4|3|2|1|0]
    E2BEGb[0|1|2|3|4|5|6|7],WW4END[15|14|13|12|11|10|9|8]
    E2BEGb[0|1|2|3|4|5|6|7],W6END[7|6|5|4|3|2|1|0]

    E2BEG[0|1|2|3|4|5|6|7],W2MID[7|6|5|4|3|2|1|0]
    E2BEG[0|1|2|3|4|5|6|7],WW4END[7|6|5|4|3|2|1|0]
    E2BEG[0|1|2|3|4|5|6|7],WW4END[15|14|13|12|11|10|9|8]
    E2BEG[0|1|2|3|4|5|6|7],W6END[7|6|5|4|3|2|1|0]

    EE4BEG[0|0|0|0],[A_O|W6END0|W6END2|W6END4]
    EE4BEG[1|1|1|1],[B_O|W6END6|W6END8|W6END10]
    EE4BEG[2|2|2|2],[A_Q|W6END1|W6END3|W6END5]
    EE4BEG[3|3|3|3],[B_Q|W6END7|W6END9|W6END11]
    EE4BEG[4|4|4|4],[W2END0|W2END2|W2END4|W2END6]
    EE4BEG[5|5|5|5],[W2END1|W2END3|W2END5|W2END7]
    EE4BEG[6|6|6|6],[W2MID0|W2MID2|W2MID4|W2MID6]
    EE4BEG[7|7|7|7],[W2MID1|W2MID3|W2MID5|W2MID7]
    EE4BEG[8|8|8|8],[W6END4|W6END6|W6END8|W6END10]
    EE4BEG[9|9|9|9],[W6END1|W6END3|W6END5|W6END7]
    EE4BEG1[0|0|0|0],[A_O|W6END0|W6END2|W6END4]
    EE4BEG1[1|1|1|1],[B_O|W6END6|W6END8|W6END10]
    EE4BEG1[2|2|2|2],[A_Q|W6END1|W6END3|W6END5]
    EE4BEG1[3|3|3|3],[B_Q|W6END7|W6END9|W6END11]
    EE4BEG1[4|4|4|4],[W2MID0|W2MID2|W2MID4|W2MID6]

After changing all connection names in the switch matrix list file, it should look like following:

.. code-block:: Bash

    # W_IO
    # Fabric to PAD output multiplexers
    [I|I|I|I|I|I|I|I]0,W2MID[0|1|2|3|4|5|6|7]
    [I|I|I|I|I|I|I|I]0,W2END[0|1|2|3|4|5|6|7]
    [I|I|I|I|I|I|I|I]1,W2MID[0|1|2|3|4|5|6|7]
    [I|I|I|I|I|I|I|I]1,W2END[0|1|2|3|4|5|6|7]
    [T|T|T|T|T|T|T|T]0,[W2END0|W2END1|W2END2|W2END3|W2END4|W2MID7|VCC0|GND0]
    [T|T|T|T|T|T|T|T]1,[W2END0|W2END4|W2END5|W2END6|W2MID6|W2MID7|VCC0|GND0]

    ### # single just go back, we swap bits in vector to get more twists into the graph
    E1BEG[0|1|2|3],W1END[3|2|1|0]
    # Single get connected to PAD output
    E1BEG[0|1|2|3],[O0|O_Q0|O1|O_Q1]

    # we also connect the hex wires
    # Note that we only have 2 wires starting in each CLB (so 2x6=12 wires in the channel)
    # we connect the combinatorial outputs in every other column and the register outputs in the remaining columns
    E6BEG[0|1|6|7],[O0|O1|O_Q0|O_Q1]
    E6BEG[2|3|8|9],[O0|O1|O_Q0|O_Q1]
    E6BEG[4|5|10|11],[O0|O1|O_Q0|O_Q1]
    E6BEG[0|1|6|7],W6END[11|10|9|8]
    E6BEG[2|3|8|9],W6END[7|6|5|4]
    E6BEG[4|5|10|11],W6END[3|2|1|0]
    E6BEG[0|1|6|7],WW4END[11|10|9|8]
    E6BEG[2|3|8|9],WW4END[7|6|5|4]
    E6BEG[4|5|10|11],WW4END[3|2|1|0]
    E6BEG[0|1|6|7],W1END[2|3|1|0]
    E6BEG[2|3|8|9],WW4END[15|14|13|12]
    E6BEG[4|5|10|11],W1END[2|3|1|0]

    # The MID are half way in so they get connected to the longest patch (S2BEG)
    # The END are longest so get on the cascading begin (S2BEGb)
    # on top we twist wire indexes for more entropy
    E2BEGb[0|1|2|3|4|5|6|7],W2END[7|6|5|4|3|2|1|0]
    E2BEGb[0|1|2|3|4|5|6|7],WW4END[7|6|5|4|3|2|1|0]
    E2BEGb[0|1|2|3|4|5|6|7],WW4END[15|14|13|12|11|10|9|8]
    E2BEGb[0|1|2|3|4|5|6|7],W6END[7|6|5|4|3|2|1|0]

    E2BEG[0|1|2|3|4|5|6|7],W2MID[7|6|5|4|3|2|1|0]
    E2BEG[0|1|2|3|4|5|6|7],WW4END[7|6|5|4|3|2|1|0]
    E2BEG[0|1|2|3|4|5|6|7],WW4END[15|14|13|12|11|10|9|8]
    E2BEG[0|1|2|3|4|5|6|7],W6END[7|6|5|4|3|2|1|0]

    EE4BEG[0|0|0|0],[O0|W6END0|W6END2|W6END4]
    EE4BEG[1|1|1|1],[O1|W6END6|W6END8|W6END10]
    EE4BEG[2|2|2|2],[O_Q0|W6END1|W6END3|W6END5]
    EE4BEG[3|3|3|3],[O_Q1|W6END7|W6END9|W6END11]
    EE4BEG[4|4|4|4],[W2END0|W2END2|W2END4|W2END6]
    EE4BEG[5|5|5|5],[W2END1|W2END3|W2END5|W2END7]
    EE4BEG[6|6|6|6],[W2MID0|W2MID2|W2MID4|W2MID6]
    EE4BEG[7|7|7|7],[W2MID1|W2MID3|W2MID5|W2MID7]
    EE4BEG[8|8|8|8],[W6END4|W6END6|W6END8|W6END10]
    EE4BEG[9|9|9|9],[W6END1|W6END3|W6END5|W6END7]
    EE4BEG1[0|0|0|0],[O0|W6END0|W6END2|W6END4]
    EE4BEG1[1|1|1|1],[O1|W6END6|W6END8|W6END10]
    EE4BEG1[2|2|2|2],[O_Q0|W6END1|W6END3|W6END5]
    EE4BEG1[3|3|3|3],[O_Q1|W6END7|W6END9|W6END11]
    EE4BEG1[4|4|4|4],[W2MID0|W2MID2|W2MID4|W2MID6]
    EE4BEG1[5|5|5|5],[W2MID1|W2MID3|W2MID5|W2MID7]


After changing the switch matrix list file, we can generate the new tile with the GEN_IOs.
The generated tile will have the same functionality as the previous tile, but now with the GEN_IOs.
