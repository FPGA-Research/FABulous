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
module MULADD (A7, A6, A5, A4, A3, A2, A1, A0, B7, B6, B5, B4, B3, B2, B1, B0, C19, C18, C17, C16, C15, C14, C13, C12, C11, C10, C9, C8, C7, C6, C5, C4, C3, C2, C1, C0, Q19, Q18, Q17, Q16, Q15, Q14, Q13, Q12, Q11, Q10, Q9, Q8, Q7, Q6, Q5, Q4, Q3, Q2, Q1, Q0, clr, UserCLK, ConfigBits);
	parameter NoConfigBits = 6;// has to be adjusted manually (we don't use an arithmetic parser for the value)
	// IMPORTANT: this has to be in a dedicated line
	input A7;// operand A
	input A6;
	input A5;
	input A4;
	input A3;
	input A2;
	input A1;
	input A0;
	input B7;// operand B
	input B6;
	input B5;
	input B4;
	input B3;
	input B2;
	input B1;
	input B0;
	input C19;// operand C
	input C18;
	input C17;
	input C16;
	input C15;
	input C14;
	input C13;
	input C12;
	input C11;
	input C10;
	input C9;
	input C8;
	input C7;
	input C6;
	input C5;
	input C4;
	input C3;
	input C2;
	input C1;
	input C0;
	output Q19;// result
	output Q18;
	output Q17;
	output Q16;
	output Q15;
	output Q14;
	output Q13;
	output Q12;
	output Q11;
	output Q10;
	output Q9;
	output Q8;
	output Q7;
	output Q6;
	output Q5;
	output Q4;
	output Q3;
	output Q2;
	output Q1;
	output Q0;

	input clr;
	(* FABulous, EXTERNAL, SHARED_PORT *) input UserCLK; // EXTERNAL // SHARED_PORT // ## the EXTERNAL keyword will send this sisgnal all the way to top and the //SHARED Allows multiple BELs using the same port (e.g. for exporting a clock to the top)
	// GLOBAL all primitive pins that are connected to the switch matrix have to go before the GLOBAL label
	(* FABulous, GLOBAL *) input [NoConfigBits-1:0] ConfigBits;

	wire [7:0] A;		// port A read data 
	wire [7:0] B;		// port B read data 
	wire [19:0] C;		// port B read data 
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

	assign A = {A7,A6,A5,A4,A3,A2,A1,A0};
	assign B = {B7,B6,B5,B4,B3,B2,B1,B0};
	assign C = {C19,C18,C17,C16,C15,C14,C13,C12,C11,C10,C9,C8,C7,C6,C5,C4,C3,C2,C1,C0};

	assign OPA = ConfigBits[0] ? A_reg : A;
	assign OPB = ConfigBits[1] ? B_reg : B;
	assign OPC = ConfigBits[2] ? C_reg : C;

	assign sum_in = ConfigBits[3] ? ACC : OPC;// we can

	assign product = OPA * OPB;

// The sign extension was not tested
	assign product_extended = ConfigBits[4] ? {product[15],product[15],product[15],product[15],product} : {4'b0000,product};

	assign sum = product_extended + sum_in;

	assign Q19	= ConfigBits[5] ? ACC[19] : sum[19];
	assign Q18	= ConfigBits[5] ? ACC[18] : sum[18];
	assign Q17	= ConfigBits[5] ? ACC[17] : sum[17];
	assign Q16	= ConfigBits[5] ? ACC[16] : sum[16];
	assign Q15	= ConfigBits[5] ? ACC[15] : sum[15];
	assign Q14	= ConfigBits[5] ? ACC[14] : sum[14];
	assign Q13	= ConfigBits[5] ? ACC[13] : sum[13];
	assign Q12	= ConfigBits[5] ? ACC[12] : sum[12];
	assign Q11	= ConfigBits[5] ? ACC[11] : sum[11];
	assign Q10	= ConfigBits[5] ? ACC[10] : sum[10];
	assign Q9	= ConfigBits[5] ? ACC[9] : sum[9];
	assign Q8	= ConfigBits[5] ? ACC[8] : sum[8];
	assign Q7	= ConfigBits[5] ? ACC[7] : sum[7];
	assign Q6	= ConfigBits[5] ? ACC[6] : sum[6];
	assign Q5	= ConfigBits[5] ? ACC[5] : sum[5];
	assign Q4	= ConfigBits[5] ? ACC[4] : sum[4];
	assign Q3	= ConfigBits[5] ? ACC[3] : sum[3];
	assign Q2	= ConfigBits[5] ? ACC[2] : sum[2];
	assign Q1	= ConfigBits[5] ? ACC[1] : sum[1];
	assign Q0	= ConfigBits[5] ? ACC[0] : sum[0];

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
