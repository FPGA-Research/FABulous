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
AD_reg=0,
BD_reg=1
*)
module RegFile_32x4 (D0, D1, D2, D3, W_ADR0, W_ADR1, W_ADR2, W_ADR3, W_ADR4, W_en, AD0, AD1, AD2, AD3, A_ADR0, A_ADR1, A_ADR2, A_ADR3, A_ADR4, BD0, BD1, BD2, BD3, B_ADR0, B_ADR1, B_ADR2, B_ADR3, B_ADR4, UserCLK, ConfigBits);
	parameter NoConfigBits = 2;// has to be adjusted manually (we don't use an arithmetic parser for the value)
	// IMPORTANT: this has to be in a dedicated line
	input D0; // Register File write port
	input D1;
	input D2;
	input D3;
	input W_ADR0;
	input W_ADR1;
	input W_ADR2;
	input W_ADR3;
	input W_ADR4;
	input W_en;
	
	output AD0;// Register File read port A
	output AD1;
	output AD2;
	output AD3;
	input A_ADR0;
	input A_ADR1;
	input A_ADR2;
	input A_ADR3;
	input A_ADR4;

	output BD0;//Register File read port B
	output BD1;
	output BD2;
	output BD3;
	input B_ADR0;
	input B_ADR1;
	input B_ADR2;
	input B_ADR3;
	input B_ADR4;

	(* FABulous, EXTERNAL, SHARED_PORT *) input UserCLK;// EXTERNAL // SHARED_PORT // ## the EXTERNAL keyword will send this sisgnal all the way to top and the //SHARED Allows multiple BELs using the same port (e.g. for exporting a clock to the top)
	// GLOBAL all primitive pins that are connected to the switch matrix have to go before the GLOBAL label
	(* FABulous, GLOBAL *) input [NoConfigBits-1:0] ConfigBits;

	//type memtype is array (31 downto 0) of std_logic_vector(3 downto 0); // 32 entries of 4 bit
	//signal mem : memtype := (others => (others => '0'));
	reg [3:0] mem [31:0];

	wire [4:0] W_ADR;// write address
	wire [4:0] A_ADR;// port A read address
	wire [4:0] B_ADR;// port B read address

	wire [3:0] D;		// write data
	wire [3:0] AD;		// port A read data
	wire [3:0] BD;		// port B read data

	reg [3:0] AD_reg;		// port A read data register
	reg [3:0] BD_reg;		// port B read data register
	
	integer i;

	assign W_ADR = {W_ADR4,W_ADR3,W_ADR2,W_ADR1,W_ADR0};
	assign A_ADR = {A_ADR4,A_ADR3,A_ADR2,A_ADR1,A_ADR0};
	assign B_ADR = {B_ADR4,B_ADR3,B_ADR2,B_ADR1,B_ADR0};

	assign D = {D3,D2,D1,D0};
	
	initial begin
		for (i=0; i<32; i=i+1) begin
			mem[i] = 4'b0000;
		end
	end

//P_write: process (UserCLK)
	always @ (posedge UserCLK) begin : P_write
		if (W_en == 1'b1) begin
			mem[W_ADR] <= D ;
		end
	end

	assign AD = mem[A_ADR];
	assign BD = mem[B_ADR];

    always @ (posedge UserCLK) begin
        AD_reg <= AD;
		BD_reg <= BD;
    end

	assign AD0 = ConfigBits[0] ? AD_reg[0] : AD[0];
	assign AD1 = ConfigBits[0] ? AD_reg[1] : AD[1];
	assign AD2 = ConfigBits[0] ? AD_reg[2] : AD[2];
	assign AD3 = ConfigBits[0] ? AD_reg[3] : AD[3];

	assign BD0 = ConfigBits[1] ? BD_reg[0] : BD[0];
	assign BD1 = ConfigBits[1] ? BD_reg[1] : BD[1];
	assign BD2 = ConfigBits[1] ? BD_reg[2] : BD[2];
	assign BD3 = ConfigBits[1] ? BD_reg[3] : BD[3];

endmodule
