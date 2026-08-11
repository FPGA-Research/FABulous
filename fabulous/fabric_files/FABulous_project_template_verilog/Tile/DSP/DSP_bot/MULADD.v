`default_nettype none

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

(* FABulous, BelMap,
    A_reg=0,
    B_reg=1,
    C_reg=2,
    ACC=3,
    signExtension=4,
    ACCout=5
    *)
module MULADD #(parameter integer NoConfigBits = 6) (
    // ConfigBits has to be adjusted manually
    // (we don't use an arithmetic parser for the value)
    input  [ 7:0] A  , // operand A
    input  [ 7:0] B  , // operand B
    input  [19:0] C  , // operand C
    output [19:0] Q  , // result
    input         clr,
    //The "EXTERNAL" keyword will send this signal all the way to top
    //The "SHARED" keyword allows multiple BELs using the same port
    // (e.g. for exporting a clock to the top)
    (* FABulous, EXTERNAL, SHARED_PORT *) input UserCLK,
    // All primitive pins that are connected to the switch matrix have
    // to go before the "GLOBAL" label
    (* FABulous, GLOBAL *) input [NoConfigBits-1:0] ConfigBits
);
    reg  [ 7:0] A_reg_data      ; // port A read data register
    reg  [ 7:0] B_reg_data      ; // port B read data register
    reg  [19:0] C_reg_data      ; // port C read data register
    wire [ 7:0] OPA             ;
    wire [ 7:0] OPB             ;
    wire [19:0] OPC             ;
    reg  [19:0] ACC             ; // accumulator register
    wire [19:0] sum             ;
    wire [19:0] sum_in          ;
    wire [19:0] product_extended;
    wire signed [ 8:0] OPA_extended    ;
    wire signed [ 8:0] OPB_extended    ;
    wire signed [17:0] product_signed  ;

    assign OPA = ConfigBits[0] ? A_reg_data : A;
    assign OPB = ConfigBits[1] ? B_reg_data : B;
    assign OPC = ConfigBits[2] ? C_reg_data : C;

    assign sum_in = ConfigBits[3] ? ACC : OPC;

    assign OPA_extended = ConfigBits[4] ? {OPA[7], OPA} : {1'b0, OPA};
    assign OPB_extended = ConfigBits[4] ? {OPB[7], OPB} : {1'b0, OPB};

    assign product_signed = OPA_extended * OPB_extended;

    assign product_extended = ConfigBits[4] ?
        {{2{product_signed[17]}},product_signed} :
        {2'b00,product_signed};

    assign sum = product_extended + sum_in;

    assign Q = ConfigBits[5] ? ACC : sum;

    always @(posedge UserCLK)
        begin
            A_reg_data <= A;
            B_reg_data <= B;
            C_reg_data <= C;
            if (clr == 1'b1)
                begin
                    ACC <= 20'b00000000000000000000;
                end
            else
                begin
                    ACC <= sum;
                end
        end

endmodule
`default_nettype wire
