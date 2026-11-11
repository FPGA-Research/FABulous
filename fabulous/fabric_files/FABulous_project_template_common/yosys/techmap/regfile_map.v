// Taken from Yosys techlibs/fabulous (ISC licence) as of 49ecb1ac1, the last
// revision before Yosys stopped shipping FABulous primitives and maps, and
// changed to connect whole vectors, since the RegFile_32x4 BEL keeps its
// vector ports (VECTOR_PORTS).

(* techmap_celltype = "$__REGFILE_[AS][AS]_" *)
module \$__REGFILE_XX_ (...);

parameter _TECHMAP_CELLTYPE_ = "";
localparam [0:0] B_SYNC = _TECHMAP_CELLTYPE_[15:8] == "S";
localparam [0:0] A_SYNC = _TECHMAP_CELLTYPE_[23:16] == "S";

localparam WIDTH = 4;
localparam ABITS = 5;

input [WIDTH-1:0] PORT_W_WR_DATA;
input [ABITS-1:0] PORT_W_ADDR;
input PORT_W_WR_EN;

output [WIDTH-1:0] PORT_A_RD_DATA;
input [ABITS-1:0] PORT_A_ADDR;

output [WIDTH-1:0] PORT_B_RD_DATA;
input [ABITS-1:0] PORT_B_ADDR;

// Unused - we have a shared clock - but keep techmap happy
input PORT_W_CLK;
input PORT_A_CLK;
input PORT_B_CLK;

input CLK_CLK;

RegFile_32x4 #(
    .AD_reg(A_SYNC),
    .BD_reg(B_SYNC)
) _TECHMAP_REPLACE_ (
    .D(PORT_W_WR_DATA),
    .W_ADR(PORT_W_ADDR),
    .W_en(PORT_W_WR_EN),
    .AD(PORT_A_RD_DATA),
    .A_ADR(PORT_A_ADDR),
    .BD(PORT_B_RD_DATA),
    .B_ADR(PORT_B_ADDR),
    .CLK(CLK_CLK)
);

endmodule
