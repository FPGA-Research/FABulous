// Toy supertile TOY: member TOY_bot drives member TOY_top through the wrapper
// wire Tile_X0Y1_N1BEG. Each switch-matrix mux has its own set of inputs.
module TOY_bot_switch_matrix (W1END0, W1END1, W1END2, ConfigBits, N1BEG0, E1BEG0);
    input W1END0;
    input W1END1;
    input W1END2;
    input [1:0] ConfigBits;
    output N1BEG0;
    output E1BEG0;
    assign N1BEG0 = ConfigBits[0] ? W1END1 : W1END0;
    assign E1BEG0 = ConfigBits[1] ? W1END2 : W1END1;
endmodule

module TOY_bot (W1END, WW4END, ConfigBits, N1BEG, E1BEG, WW4BEG);
    input [2:0] W1END;
    input [1:0] WW4END;
    input [1:0] ConfigBits;
    output [1:0] N1BEG;
    output E1BEG;
    output WW4BEG;
    wire ww;
    TOY_bot_switch_matrix Inst_TOY_bot_switch_matrix (
        .W1END0(W1END[0]), .W1END1(W1END[1]), .W1END2(W1END[2]),
        .ConfigBits(ConfigBits), .N1BEG0(N1BEG[0]), .E1BEG0(E1BEG)
    );
    sg13g2_buf_1 n1buf (.A(W1END[2]), .X(N1BEG[1]));
    sg13g2_buf_1 inbuf (.A(WW4END[1]), .X(ww));
    sg13g2_buf_1 outbuf (.A(ww), .X(WW4BEG));
endmodule

module TOY_top_switch_matrix (N1END0, N1END1, ConfigBits, E1BEG0);
    input N1END0;
    input N1END1;
    input ConfigBits;
    output E1BEG0;
    assign E1BEG0 = ConfigBits ? N1END1 : N1END0;
endmodule

module TOY_top (N1END, ConfigBits, E1BEG);
    input [1:0] N1END;
    input ConfigBits;
    output E1BEG;
    TOY_top_switch_matrix Inst_TOY_top_switch_matrix (
        .N1END0(N1END[0]), .N1END1(N1END[1]), .ConfigBits(ConfigBits),
        .E1BEG0(E1BEG)
    );
endmodule

module TOY (
    Tile_X0Y1_W1END, Tile_X0Y1_WW4END, Tile_X0Y1_ConfigBits, Tile_X0Y0_ConfigBits,
    Tile_X0Y0_E1BEG, Tile_X0Y1_E1BEG, Tile_X0Y1_WW4BEG
);
    input [2:0] Tile_X0Y1_W1END;
    input [1:0] Tile_X0Y1_WW4END;
    input [1:0] Tile_X0Y1_ConfigBits;
    input Tile_X0Y0_ConfigBits;
    output Tile_X0Y0_E1BEG;
    output Tile_X0Y1_E1BEG;
    output Tile_X0Y1_WW4BEG;
    wire [1:0] Tile_X0Y1_N1BEG;
    TOY_top Tile_X0Y0_TOY_top (
        .N1END(Tile_X0Y1_N1BEG), .ConfigBits(Tile_X0Y0_ConfigBits),
        .E1BEG(Tile_X0Y0_E1BEG)
    );
    TOY_bot Tile_X0Y1_TOY_bot (
        .W1END(Tile_X0Y1_W1END), .WW4END(Tile_X0Y1_WW4END),
        .ConfigBits(Tile_X0Y1_ConfigBits), .N1BEG(Tile_X0Y1_N1BEG),
        .E1BEG(Tile_X0Y1_E1BEG), .WW4BEG(Tile_X0Y1_WW4BEG)
    );
endmodule
