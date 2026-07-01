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
// WITHOUT WARRANTIES OR CoNDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

module LUTK #(
    parameter K=4,
    parameter LUT_ENTRIES = 2**K
)(
    input [K-1:0] I,
    input [LUT_ENTRIES-1:0] INIT,
    output O
);

    generate

    if (K == 1) begin : LUT1
        assign O = I ? INIT[1] : INIT[0];
    end else begin : split_LUT
        wire lower_O, upper_O;

        parameter LUT_ENTRIES_HALF = 2**(K-1);

        LUTK #(
          .K (K-1)
        ) LUTK_lower (
          .I    (I[K-2:0]),
          .INIT (INIT[LUT_ENTRIES_HALF-1:0]),
          .O    (lower_O)
        );

        LUTK #(
          .K (K-1)
        ) LUTK_upper (
          .I    (I[K-2:0]),
          .INIT (INIT[LUT_ENTRIES-1:LUT_ENTRIES_HALF]),
          .O    (upper_O)
        );

        assign O = I[K-1] ? upper_O : lower_O;
    end

    endgenerate

endmodule

// Note: nextpnr also has support for ASYNC_SR and NEG_CLK
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
    I0mux=17,
    SET_NORESET=18
*)
module FABULOUS_LC #(
    // #LUT inputs
    parameter K=4,
      parameter LUT_ENTRIES = 2**K,

    // ConfigBits has to be adjusted manually (we don't use an arithmetic parser for the value)
    parameter N_CONFIG_BITS = LUT_ENTRIES + 3
)(
    input [K-1:0] I,   // Vector for I0, I1, I2, I3 ...
    output        O,   // Single output for LUT result
    input         Ci,  // Carry chain input
    output        Co,  // Carry chain output
    input         SR,  // Shared reset
    input         EN,  // Shared enable
    input         CLK, // Sahred clock

    (* FABulous, GLOBAL *) input [N_CONFIG_BITS-1:0] ConfigBits // Config bits as vector
);

      wire [LUT_ENTRIES-1 : 0] LUT_values;
      wire [K-1 : 0] LUT_index;
      wire LUT_out;
      reg  LUT_flop;
      wire I0mux; // normal input '0', or carry input '1'
      wire c_out_mux, c_I0mux, c_reset_value;   // extra configuration bits

      assign LUT_values     = ConfigBits[LUT_ENTRIES-1:0];
      assign c_out_mux      = ConfigBits[LUT_ENTRIES+0];
      assign c_I0mux        = ConfigBits[LUT_ENTRIES+1];
      assign c_reset_value  = ConfigBits[LUT_ENTRIES+2];

      assign I0mux = c_I0mux ? Ci : I[0];

      assign LUT_index = {I[K-1:1], I0mux};

    // The look-up table
    LUTK #(
        .K (4)
    ) LUT4 (
        .I    (LUT_index),
        .INIT (LUT_values),
        .O    (LUT_out)
    );

      assign O = c_out_mux ? LUT_flop : LUT_out;

      // iCE40 like carry chain (as this is supported in Yosys; would normally go for fractured LUT)
      assign Co = (Ci & I[1]) | (Ci & I[2]) | (I[1] & I[2]);

      always @ (posedge CLK) begin
        if (SR) begin
            LUT_flop <= c_reset_value;
        end else begin
            if (EN) begin
                LUT_flop <= LUT_out;
            end
        end
      end

endmodule
