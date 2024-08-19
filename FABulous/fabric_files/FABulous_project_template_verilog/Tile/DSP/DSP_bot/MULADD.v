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
module MULADD #(parameter NoConfigBits = 6)(
	// ConfigBits has to be adjusted manually (we don't use an arithmetic parser for the value)
	input [7:0] A, // operand A
	input [7:0] B, // operand B
	input [19:0] C, // operand C
	output [19:0] Q,// result
	input clr,
	(* FABulous, EXTERNAL, SHARED_PORT *) input UserCLK, // EXTERNAL // SHARED_PORT // ## the EXTERNAL keyword will send this sisgnal all the way to top and the //SHARED Allows multiple BELs using the same port (e.g. for exporting a clock to the top)
	// GLOBAL all primitive pins that are connected to the switch matrix have to go before the GLOBAL label
	(* FABulous, GLOBAL *) input [NoConfigBits-1:0] ConfigBits
);
	reg [7:0] A_reg;		// port A read data register
	reg [7:0] B_reg;		// port B read data register
	reg [19:0] C_reg;		// port B read data register
	wire [7:0] OPA;		// port A 
	wire [7:0] OPB;		// port B 
	wire [19:0] OPC;		// port B  
	reg [19:0] ACC ;		// accumulator register
	wire [19:0] sum;// port B read data register
	wire [19:0] sum_in;// port B read data register
	wire [15:0] product;
	wire [19:0] product_extended;

	assign OPA = ConfigBits[0] ? A_reg : A;
	assign OPB = ConfigBits[1] ? B_reg : B;
	assign OPC = ConfigBits[2] ? C_reg : C;

	assign sum_in = ConfigBits[3] ? ACC : OPC;// we can

	assign product = OPA * OPB;

// The sign extension was not tested
	assign product_extended = ConfigBits[4] ? {product[15],product[15],product[15],product[15],product} : {4'b0000,product};

	assign sum = product_extended + sum_in;

	assign Q = ConfigBits[5] ? ACC : sum;

	always @ (posedge UserCLK)
	begin
		A_reg <= A;
		B_reg <= B;
		C_reg <= C;
		if (clr == 1'b1) begin
			ACC <= 20'b00000000000000000000;
		end else begin
			ACC <= sum;
		end
	end

endmodule
