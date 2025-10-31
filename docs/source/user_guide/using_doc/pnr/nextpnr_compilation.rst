Nextpnr compilation
===================

Nextpnr can compile a JSON description of a circuit to FASM [#]_ using the
architectural description in bels.txt and pips.txt

Our nextpnr implementation uses nextpnr-generic for place and route.

Building
--------

Please refer to the `Nextpnr-generic <https://github.com/YosysHQ/nextpnr#nextpnr-generic>`_:

.. note:: Any new version architecture should be declared in ``$FAB_ROOT/nextpnr/CMakeLists.txt``

User guide
----------

To generate the FASM file using nextpnr, run the following command:

.. code-block:: console

        $ FAB_ROOT=<Project_directory> nextpnr-generic --uarch fabulous --json <JSON_file> -o fasm=<output_FASM_file>


+---------------------+------------------------------------------------+
| <Project_directory> | the directory to the project                   |
| <JSON_file>         | the JSON file generated from Yosys compilation |
| <output_FASM_file>  | the output directory of the FASM file          |
+---------------------+------------------------------------------------+

Example,

.. code-block:: console

        $ FAB_ROOT=demo nextpnr-generic --uarch fabulous --json demo/user_design/sequential_16bit_en.v -o fasm=demo/user_design/sequential_16bit_en.fasm

Primitive instantiation
-----------------------

As described in more detail in the yosys documentation, the (\* keep \*) attribute can be used to instantiate a component and clarify that yosys should not try to optimise it away. This can be used to directly instantiate components as blackbox models, and is done in the format

.. code-block:: none

        (* keep *) COMPONENT_TYPE #(PARAMETER = VALUE)  COMPONENT_NAME(.PORT_NAME1(WIRE_NAME1), .PORT_NAME2(WIRE_NAME2), ...);

Constraints for the placement of IO/bels
----------------------------------------

Constraints for your architecture can be put in place using Absolute Placement Constraints ``(* BEL="X2/Y5/lc0" *)``. For example,

.. code-block:: verilog

        (* BEL="X7Y3.C" *) FABULOUS_LC #(.INIT(16'b1010101010101010), .DFF_ENABLE(1'b0)) constraint_test (.CLK(clk), .I0(enable), .O (enable_i));

We can constrain which BEL should be used - LUT "C" is constrained to be used in Tile X7Y3 in the example. With the same constraint method, we can also instantiate ``InPass4_frame_config, OutPass4_frame_config and IO_1_bidirectional_frame_config_pass`` blocks for IO constraints.

The following example is a 16-bit counter output to Block_RAM, and then Block_RAM to W_IO in a 10x10 fabric.

.. code-block:: verilog

        module sequential_16bit_en_bram (enable, reset, counter);

        input enable, reset;
        output [15:0] counter;

        reg [15:0] counter_i;

        wire clk;
        (* keep *) Global_Clock inst_clk (.CLK(clk));

        wire Tile_X11Y10_RAM2FAB_D0_O0, Tile_X11Y10_RAM2FAB_D0_O1, Tile_X11Y10_RAM2FAB_D0_O2, Tile_X11Y10_RAM2FAB_D0_O3;
        (* keep *) (* BEL="X11Y10.A" *) InPass4_frame_config Tile_X11Y10_A (.O0(Tile_X11Y10_RAM2FAB_D0_O0), .O1(Tile_X11Y10_RAM2FAB_D0_O1), .O2(Tile_X11Y10_RAM2FAB_D0_O2), .O3(Tile_X11Y10_RAM2FAB_D0_O3));
        wire Tile_X11Y10_RAM2FAB_D1_O0, Tile_X11Y10_RAM2FAB_D1_O1, Tile_X11Y10_RAM2FAB_D1_O2, Tile_X11Y10_RAM2FAB_D1_O3;
        (* keep *) (* BEL="X11Y10.B" *) InPass4_frame_config Tile_X11Y10_B (.O0(Tile_X11Y10_RAM2FAB_D1_O0), .O1(Tile_X11Y10_RAM2FAB_D1_O1), .O2(Tile_X11Y10_RAM2FAB_D1_O2), .O3(Tile_X11Y10_RAM2FAB_D1_O3));
        wire Tile_X11Y10_RAM2FAB_D2_O0, Tile_X11Y10_RAM2FAB_D2_O1, Tile_X11Y10_RAM2FAB_D2_O2, Tile_X11Y10_RAM2FAB_D2_O3;
        (* keep *) (* BEL="X11Y10.C" *) InPass4_frame_config Tile_X11Y10_C (.O0(Tile_X11Y10_RAM2FAB_D2_O0), .O1(Tile_X11Y10_RAM2FAB_D2_O1), .O2(Tile_X11Y10_RAM2FAB_D2_O2), .O3(Tile_X11Y10_RAM2FAB_D2_O3));
        wire Tile_X11Y10_RAM2FAB_D3_O0, Tile_X11Y10_RAM2FAB_D3_O1, Tile_X11Y10_RAM2FAB_D3_O2, Tile_X11Y10_RAM2FAB_D3_O3;
        (* keep *) (* BEL="X11Y10.D" *) InPass4_frame_config Tile_X11Y10_D (.O0(Tile_X11Y10_RAM2FAB_D3_O0), .O1(Tile_X11Y10_RAM2FAB_D3_O1), .O2(Tile_X11Y10_RAM2FAB_D3_O2), .O3(Tile_X11Y10_RAM2FAB_D3_O3));

        wire Tile_X11Y9_FAB2RAM_D0_I0, Tile_X11Y9_FAB2RAM_D0_I1, Tile_X11Y9_FAB2RAM_D0_I2, Tile_X11Y9_FAB2RAM_D0_I3;
        (* keep *) (* BEL="X11Y9.E" *) OutPass4_frame_config Tile_X11Y9_E (.I0(Tile_X11Y9_FAB2RAM_D0_I0), .I1(Tile_X11Y9_FAB2RAM_D0_I1), .I2(Tile_X11Y9_FAB2RAM_D0_I2), .I3(Tile_X11Y9_FAB2RAM_D0_I3));
        wire Tile_X11Y9_FAB2RAM_D1_I0, Tile_X11Y9_FAB2RAM_D1_I1, Tile_X11Y9_FAB2RAM_D1_I2, Tile_X11Y9_FAB2RAM_D1_I3;
        (* keep *) (* BEL="X11Y9.F" *) OutPass4_frame_config Tile_X11Y9_F (.I0(Tile_X11Y9_FAB2RAM_D1_I0), .I1(Tile_X11Y9_FAB2RAM_D1_I1), .I2(Tile_X11Y9_FAB2RAM_D1_I2), .I3(Tile_X11Y9_FAB2RAM_D1_I3));
        wire Tile_X11Y9_FAB2RAM_D2_I0, Tile_X11Y9_FAB2RAM_D2_I1, Tile_X11Y9_FAB2RAM_D2_I2, Tile_X11Y9_FAB2RAM_D2_I3;
        (* keep *) (* BEL="X11Y9.G" *) OutPass4_frame_config Tile_X11Y9_G (.I0(Tile_X11Y9_FAB2RAM_D2_I0), .I1(Tile_X11Y9_FAB2RAM_D2_I1), .I2(Tile_X11Y9_FAB2RAM_D2_I2), .I3(Tile_X11Y9_FAB2RAM_D2_I3));
        wire Tile_X11Y9_FAB2RAM_D3_I0, Tile_X11Y9_FAB2RAM_D3_I1, Tile_X11Y9_FAB2RAM_D3_I2, Tile_X11Y9_FAB2RAM_D3_I3;
        (* keep *) (* BEL="X11Y9.H" *) OutPass4_frame_config Tile_X11Y9_H (.I0(Tile_X11Y9_FAB2RAM_D3_I0), .I1(Tile_X11Y9_FAB2RAM_D3_I1), .I2(Tile_X11Y9_FAB2RAM_D3_I2), .I3(Tile_X11Y9_FAB2RAM_D3_I3));
        wire Tile_X11Y10_FAB2RAM_D0_I0, Tile_X11Y10_FAB2RAM_D0_I1, Tile_X11Y10_FAB2RAM_D0_I2, Tile_X11Y10_FAB2RAM_D0_I3;
        (* keep *) (* BEL="X11Y10.E" *) OutPass4_frame_config Tile_X11Y10_E (.I0(Tile_X11Y10_FAB2RAM_D0_I0), .I1(Tile_X11Y10_FAB2RAM_D0_I1), .I2(Tile_X11Y10_FAB2RAM_D0_I2), .I3(Tile_X11Y10_FAB2RAM_D0_I3));
        wire Tile_X11Y10_FAB2RAM_D1_I0, Tile_X11Y10_FAB2RAM_D1_I1, Tile_X11Y10_FAB2RAM_D1_I2, Tile_X11Y10_FAB2RAM_D1_I3;
        (* keep *) (* BEL="X11Y10.F" *) OutPass4_frame_config Tile_X11Y10_F (.I0(Tile_X11Y10_FAB2RAM_D1_I0), .I1(Tile_X11Y10_FAB2RAM_D1_I1), .I2(Tile_X11Y10_FAB2RAM_D1_I2), .I3(Tile_X11Y10_FAB2RAM_D1_I3));
        wire Tile_X11Y10_FAB2RAM_D2_I0, Tile_X11Y10_FAB2RAM_D2_I1, Tile_X11Y10_FAB2RAM_D2_I2, Tile_X11Y10_FAB2RAM_D2_I3;
        (* keep *) (* BEL="X11Y10.G" *) OutPass4_frame_config Tile_X11Y10_G (.I0(Tile_X11Y10_FAB2RAM_D2_I0), .I1(Tile_X11Y10_FAB2RAM_D2_I1), .I2(Tile_X11Y10_FAB2RAM_D2_I2), .I3(Tile_X11Y10_FAB2RAM_D2_I3));
        wire Tile_X11Y10_FAB2RAM_D3_I0, Tile_X11Y10_FAB2RAM_D3_I1, Tile_X11Y10_FAB2RAM_D3_I2, Tile_X11Y10_FAB2RAM_D3_I3;
        (* keep *) (* BEL="X11Y10.H" *) OutPass4_frame_config Tile_X11Y10_H (.I0(Tile_X11Y10_FAB2RAM_D3_I0), .I1(Tile_X11Y10_FAB2RAM_D3_I1), .I2(Tile_X11Y10_FAB2RAM_D3_I2), .I3(Tile_X11Y10_FAB2RAM_D3_I3));

        wire Tile_X11Y9_FAB2RAM_A0_I0, Tile_X11Y9_FAB2RAM_A0_I1, Tile_X11Y9_FAB2RAM_A0_I2, Tile_X11Y9_FAB2RAM_A0_I3;
        (* keep *) (* BEL="X11Y9.I" *) OutPass4_frame_config Tile_X11Y9_I (.I0(Tile_X11Y9_FAB2RAM_A0_I0), .I1(Tile_X11Y9_FAB2RAM_A0_I1), .I2(Tile_X11Y9_FAB2RAM_A0_I2), .I3(Tile_X11Y9_FAB2RAM_A0_I3));
        wire Tile_X11Y9_FAB2RAM_A1_I0, Tile_X11Y9_FAB2RAM_A1_I1, Tile_X11Y9_FAB2RAM_A1_I2, Tile_X11Y9_FAB2RAM_A1_I3;
        (* keep *) (* BEL="X11Y9.J" *) OutPass4_frame_config Tile_X11Y9_J (.I0(Tile_X11Y9_FAB2RAM_A1_I0), .I1(Tile_X11Y9_FAB2RAM_A1_I1), .I2(Tile_X11Y9_FAB2RAM_A1_I2), .I3(Tile_X11Y9_FAB2RAM_A1_I3));

        wire Tile_X11Y10_FAB2RAM_A0_I0, Tile_X11Y10_FAB2RAM_A0_I1, Tile_X11Y10_FAB2RAM_A0_I2, Tile_X11Y10_FAB2RAM_A0_I3;
        (* keep *) (* BEL="X11Y10.I" *) OutPass4_frame_config Tile_X11Y10_I (.I0(Tile_X11Y10_FAB2RAM_A0_I0), .I1(Tile_X11Y10_FAB2RAM_A0_I1), .I2(Tile_X11Y10_FAB2RAM_A0_I2), .I3(Tile_X11Y10_FAB2RAM_A0_I3));
        wire Tile_X11Y10_FAB2RAM_A1_I0, Tile_X11Y10_FAB2RAM_A1_I1, Tile_X11Y10_FAB2RAM_A1_I2, Tile_X11Y10_FAB2RAM_A1_I3;
        (* keep *) (* BEL="X11Y10.J" *) OutPass4_frame_config Tile_X11Y10_J (.I0(Tile_X11Y10_FAB2RAM_A1_I0), .I1(Tile_X11Y10_FAB2RAM_A1_I1), .I2(Tile_X11Y10_FAB2RAM_A1_I2), .I3(Tile_X11Y10_FAB2RAM_A1_I3));

        wire Tile_X11Y9_FAB2RAM_C_I2, Tile_X11Y9_FAB2RAM_C_I3;
        (* keep *) (* BEL="X11Y9.K" *) OutPass4_frame_config Tile_X11Y9_K (.I2(Tile_X11Y9_FAB2RAM_C_I2), .I3(Tile_X11Y9_FAB2RAM_C_I3));
        wire Tile_X11Y10_FAB2RAM_C_I0, Tile_X11Y10_FAB2RAM_C_I1, Tile_X11Y10_FAB2RAM_C_I2, Tile_X11Y10_FAB2RAM_C_I3;
        (* keep *) (* BEL="X11Y10.K" *) OutPass4_frame_config Tile_X11Y10_K (.I0(Tile_X11Y10_FAB2RAM_C_I0), .I1(Tile_X11Y10_FAB2RAM_C_I1), .I2(Tile_X11Y10_FAB2RAM_C_I2), .I3(Tile_X11Y10_FAB2RAM_C_I3));

        initial begin
            counter_i = 16'b0000000000000000;
        end

        always @ (posedge clk) begin
            if(enable) begin
                    if(reset) begin
                        counter_i <= 0;
                    end
                    else begin
                        counter_i <= counter_i + 1'b1;
                    end
            end
        end

        assign counter = {Tile_X11Y10_RAM2FAB_D0_O0, Tile_X11Y10_RAM2FAB_D0_O1, Tile_X11Y10_RAM2FAB_D0_O2, Tile_X11Y10_RAM2FAB_D0_O3,
                        Tile_X11Y10_RAM2FAB_D1_O0, Tile_X11Y10_RAM2FAB_D1_O1, Tile_X11Y10_RAM2FAB_D1_O2, Tile_X11Y10_RAM2FAB_D1_O3,
                        Tile_X11Y10_RAM2FAB_D2_O0, Tile_X11Y10_RAM2FAB_D2_O1, Tile_X11Y10_RAM2FAB_D2_O2, Tile_X11Y10_RAM2FAB_D2_O3,
                        Tile_X11Y10_RAM2FAB_D3_O0, Tile_X11Y10_RAM2FAB_D3_O1, Tile_X11Y10_RAM2FAB_D3_O2, Tile_X11Y10_RAM2FAB_D3_O3};

        assign {Tile_X11Y9_FAB2RAM_D0_I0, Tile_X11Y9_FAB2RAM_D0_I1, Tile_X11Y9_FAB2RAM_D0_I2, Tile_X11Y9_FAB2RAM_D0_I3,
                Tile_X11Y9_FAB2RAM_D1_I0, Tile_X11Y9_FAB2RAM_D1_I1, Tile_X11Y9_FAB2RAM_D1_I2, Tile_X11Y9_FAB2RAM_D1_I3,
                Tile_X11Y9_FAB2RAM_D2_I0, Tile_X11Y9_FAB2RAM_D2_I1, Tile_X11Y9_FAB2RAM_D2_I2, Tile_X11Y9_FAB2RAM_D2_I3,
                Tile_X11Y9_FAB2RAM_D3_I0, Tile_X11Y9_FAB2RAM_D3_I1, Tile_X11Y9_FAB2RAM_D3_I2, Tile_X11Y9_FAB2RAM_D3_I3,
                Tile_X11Y10_FAB2RAM_D0_I0, Tile_X11Y10_FAB2RAM_D0_I1, Tile_X11Y10_FAB2RAM_D0_I2, Tile_X11Y10_FAB2RAM_D0_I3,
                Tile_X11Y10_FAB2RAM_D1_I0, Tile_X11Y10_FAB2RAM_D1_I1, Tile_X11Y10_FAB2RAM_D1_I2, Tile_X11Y10_FAB2RAM_D1_I3,
                Tile_X11Y10_FAB2RAM_D2_I0, Tile_X11Y10_FAB2RAM_D2_I1, Tile_X11Y10_FAB2RAM_D2_I2, Tile_X11Y10_FAB2RAM_D2_I3,
                Tile_X11Y10_FAB2RAM_D3_I0, Tile_X11Y10_FAB2RAM_D3_I1, Tile_X11Y10_FAB2RAM_D3_I2, Tile_X11Y10_FAB2RAM_D3_I3} = {16'd0, counter_i};

        assign {Tile_X11Y9_FAB2RAM_A0_I0, Tile_X11Y9_FAB2RAM_A0_I1, Tile_X11Y9_FAB2RAM_A0_I2, Tile_X11Y9_FAB2RAM_A0_I3, Tile_X11Y9_FAB2RAM_A1_I0, Tile_X11Y9_FAB2RAM_A1_I1, Tile_X11Y9_FAB2RAM_A1_I2, Tile_X11Y9_FAB2RAM_A1_I3} = 8'd0;
        assign {Tile_X11Y10_FAB2RAM_A0_I0, Tile_X11Y10_FAB2RAM_A0_I1, Tile_X11Y10_FAB2RAM_A0_I2, Tile_X11Y10_FAB2RAM_A0_I3, Tile_X11Y10_FAB2RAM_A1_I0, Tile_X11Y10_FAB2RAM_A1_I1, Tile_X11Y10_FAB2RAM_A1_I2, Tile_X11Y10_FAB2RAM_A1_I3} = 8'd0;
        assign {Tile_X11Y9_FAB2RAM_C_I2, Tile_X11Y9_FAB2RAM_C_I3, Tile_X11Y10_FAB2RAM_C_I0, Tile_X11Y10_FAB2RAM_C_I1, Tile_X11Y10_FAB2RAM_C_I2, Tile_X11Y10_FAB2RAM_C_I3} = 6'b110000;

        endmodule

Footnotes
---------

.. [#] The FPGA Assembly format, describing a concrete list of features on a
   specific FPGA fabric to be enabled
