// Copyright 2021 University of Manchester
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//    http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

(*FABulous, BelMap,
INIT=0,
INIT_1=1,
INIT_2=2,
INIT_3=3,
INIT_4=4,
INIT_5=5,
INIT_6=6,
INIT_7=7,
INIT_8=8,
INIT_9=9,
INIT_10=10,
INIT_11=11,
INIT_12=12,
INIT_13=13,
INIT_14=14,
INIT_15=15,
FF=16,
IOmux=17,
SET_NORESET=18
*)
module LUT4c_frame_config_dffesr #(parameter NoConfigBits = 19)(
    // ConfigBits has to be adjusted manually (we don't use an arithmetic parser for the value)
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

//CONFout <= c_I0mux;

    //assign I0mux = c_I0mux ? Ci : I0;
    cus_mux21 cus_mux21_I0mux(
    .A0(I[0]),
    .A1(Ci),
    .S(c_I0mux),
    .X(I0mux)
    );

    assign LUT_index = {I[3],I[2],I[1],I0mux};

// The LUT is just a multiplexer
// for a first shot, I am using a 16:1
// LUT_out <= LUT_values(TO_INTEGER(LUT_index));
    /*MUX16PTv2 inst_MUX16PTv2_E6BEG1(
    .IN1(LUT_values[0]),
    .IN2(LUT_values[1]),
    .IN3(LUT_values[2]),
    .IN4(LUT_values[3]),
    .IN5(LUT_values[4]),
    .IN6(LUT_values[5]),
    .IN7(LUT_values[6]),
    .IN8(LUT_values[7]),
    .IN9(LUT_values[8]),
    .IN10(LUT_values[9]),
    .IN11(LUT_values[10]),
    .IN12(LUT_values[11]),
    .IN13(LUT_values[12]),
    .IN14(LUT_values[13]),
    .IN15(LUT_values[14]),
    .IN16(LUT_values[15]),
    .S1(LUT_index[0]),
    .S2(LUT_index[1]),
    .S3(LUT_index[2]),
    .S4(LUT_index[3]),
    .O(LUT_out)
    );*/
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
    .S0N(~LUT_index[0]),
    .S1 (LUT_index[1]),
    .S1N(~LUT_index[1]),
    .S2 (LUT_index[2]),
    .S2N(~LUT_index[2]),
    .S3 (LUT_index[3]),
    .S3N(~LUT_index[3]),
    .X  (LUT_out)
    );

    //assign O = c_out_mux ? LUT_flop : LUT_out;
    cus_mux21 cus_mux21_O(
    .A0(LUT_out),
    .A1(LUT_flop),
    .S(c_out_mux),
    .X(O)
    );

    assign Co = (Ci & I[1]) | (Ci & I[2]) | (I[1] & I[2]);// iCE40 like carry chain (as this is supported in Yosys; would normally go for fractured LUT)

    always @ (posedge UserCLK) begin
        if (EN) begin
            if (SR)
                LUT_flop <= c_reset_value;
            else
                LUT_flop <= LUT_out;
        end
    end

endmodule
