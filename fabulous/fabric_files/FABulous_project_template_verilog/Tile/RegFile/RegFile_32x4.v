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
module RegFile_32x4 #(parameter NoConfigBits = 2)(
    // ConfigBits has to be adjusted manually (we don't use an arithmetic parser for the value)
    input [3:0] D, // Register File write port
    input [4:0] W_ADR,
    input W_en,

    output [3:0] AD, // Register File read port A
    input [4:0] A_ADR,

    output [3:0] BD, //Register File read port B
    input [4:0] B_ADR,

    (* FABulous, EXTERNAL, SHARED_PORT *) input UserCLK, // EXTERNAL // SHARED_PORT // ## the EXTERNAL keyword will send this sisgnal all the way to top and the //SHARED Allows multiple BELs using the same port (e.g. for exporting a clock to the top)
    // GLOBAL all primitive pins that are connected to the switch matrix have to go before the GLOBAL label
    (* FABulous, GLOBAL *) input [NoConfigBits-1:0] ConfigBits
);

    //type memtype is array (31 downto 0) of std_logic_vector(3 downto 0); // 32 entries of 4 bit
    //signal mem : memtype := (others => (others => '0'));
    reg [3:0] mem [31:0];

    wire [3:0] AD_comb;     // port A read data, combinatorial
    wire [3:0] BD_comb;     // port B read data, combinatorial

    reg [3:0] AD_reg;       // port A read data, registered
    reg [3:0] BD_reg;       // port B read data, registered

    integer i;

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

    assign AD_comb = mem[A_ADR];
    assign BD_comb = mem[B_ADR];

    always @ (posedge UserCLK) begin
        AD_reg <= AD_comb;
        BD_reg <= BD_comb;
    end

    assign AD = ConfigBits[0] ? AD_reg : AD_comb;
    assign BD = ConfigBits[1] ? BD_reg : BD_comb;

endmodule
