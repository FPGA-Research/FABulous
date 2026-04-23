// Copyright 2021 University of Manchester
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// 8x8 multiply-accumulate unit with optional input registers
//
//  A[7:0] -->[MUX c0]--> OPA --+
//            (A/A_reg)         |   +------+   +--------+   +-----+
//                              +-->| 8x8  |-->|  ext   |-->|     |
//  B[7:0] -->[MUX c1]--> OPB --+-->| MUL  |   | [c4]   |   | ADD |----> sum
//            (B/B_reg)             +------+   +--------+ +>|     |       |
//                                                        | +-----+       |
//  C[19:0] ->[MUX c2]--> OPC -->[MUX c3]--> sum_in ------+               |
//            (C/C_reg)          (OPC/ACC)                                |
//                                   ^          +-------+                 |
//                                   +----------|  ACC  |<----------------+
//                                              | D   Q |<-- clr
//  Q[19:0] <-----[MUX c5]----------------------+-------+
//                (sum/ACC)
//
(* FABulous, BelMap,
A_reg=0,
B_reg=1,
C_reg=2,
ACC=3,
signExtension=4,
ACCout=5
*)
module MULADD #(parameter NoConfigBits = 6)(
    input [7:0] A,          // operand A
    input [7:0] B,          // operand B
    input [19:0] C,         // operand C (add input)
    output [19:0] Q,        // result
    input clr,              // accumulator clear
    (* FABulous, EXTERNAL, SHARED_PORT *) input UserCLK,
    // GLOBAL all primitive pins that are connected to the switch matrix have to go before the GLOBAL label
    (* FABulous, GLOBAL *) input [NoConfigBits-1:0] ConfigBits
);
    reg [7:0] A_reg;
    reg [7:0] B_reg;
    reg [19:0] C_reg;
    wire [7:0] OPA;
    wire [7:0] OPB;
    wire [19:0] OPC;
    reg [19:0] ACC;
    wire [19:0] sum;
    wire [19:0] sum_in;
    wire [15:0] product;
    wire [19:0] product_extended;

    assign OPA = ConfigBits[0] ? A_reg : A;
    assign OPB = ConfigBits[1] ? B_reg : B;
    assign OPC = ConfigBits[2] ? C_reg : C;

    assign sum_in = ConfigBits[3] ? ACC : OPC;

    assign product = OPA * OPB;

    assign product_extended = ConfigBits[4] ? {product[15],product[15],product[15],product[15],product} : {4'b0000,product};

    assign sum = product_extended + sum_in;

    assign Q = ConfigBits[5] ? ACC : sum;

    always @ (posedge UserCLK)
    begin
        A_reg <= A;
        B_reg <= B;
        C_reg <= C;
        if (clr == 1'b1) begin
            ACC <= 20'b0;
        end else begin
            ACC <= sum;
        end
    end

endmodule
