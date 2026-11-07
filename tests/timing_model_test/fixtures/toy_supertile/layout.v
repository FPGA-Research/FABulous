module TOY (Tile_X0Y0_ConfigBits,
        Tile_X0Y0_E1BEG,
        Tile_X0Y1_E1BEG,
        Tile_X0Y1_WW4BEG,
        Tile_X0Y1_ConfigBits,
        Tile_X0Y1_W1END,
        Tile_X0Y1_WW4END);
    input Tile_X0Y0_ConfigBits;
    output Tile_X0Y0_E1BEG;
    output Tile_X0Y1_E1BEG;
    output Tile_X0Y1_WW4BEG;
    input [1:0] Tile_X0Y1_ConfigBits;
    input [2:0] Tile_X0Y1_W1END;
    input [1:0] Tile_X0Y1_WW4END;

    wire \Tile_X0Y1_N1BEG[0] ;
    wire \Tile_X0Y1_N1BEG[1] ;
    wire \Tile_X0Y1_TOY_bot/Inst_TOY_bot_switch_matrix.N1BEG0 ;
    wire \Tile_X0Y1_TOY_bot/ww ;

    sg13g2_mux2_1 \Tile_X0Y0_TOY_top/_0_  (.A0(\Tile_X0Y1_N1BEG[0] ),
        .A1(\Tile_X0Y1_N1BEG[1] ),
        .S(Tile_X0Y0_ConfigBits),
        .X(Tile_X0Y0_E1BEG));
    sg13g2_mux2_1 \Tile_X0Y1_TOY_bot/_0_  (.A0(Tile_X0Y1_W1END[1]),
        .A1(Tile_X0Y1_W1END[2]),
        .S(Tile_X0Y1_ConfigBits[1]),
        .X(Tile_X0Y1_E1BEG));
    sg13g2_mux2_1 \Tile_X0Y1_TOY_bot/_1_  (.A0(Tile_X0Y1_W1END[0]),
        .A1(Tile_X0Y1_W1END[1]),
        .S(Tile_X0Y1_ConfigBits[0]),
        .X(\Tile_X0Y1_TOY_bot/Inst_TOY_bot_switch_matrix.N1BEG0 ));
    sg13g2_buf_1 \Tile_X0Y1_TOY_bot/_2_  (.A(\Tile_X0Y1_TOY_bot/Inst_TOY_bot_switch_matrix.N1BEG0 ),
        .X(\Tile_X0Y1_N1BEG[0] ));
    sg13g2_buf_1 \Tile_X0Y1_TOY_bot/inbuf  (.A(Tile_X0Y1_WW4END[1]),
        .X(\Tile_X0Y1_TOY_bot/ww ));
    sg13g2_buf_1 \Tile_X0Y1_TOY_bot/n1buf  (.A(Tile_X0Y1_W1END[2]),
        .X(\Tile_X0Y1_N1BEG[1] ));
    sg13g2_buf_1 \Tile_X0Y1_TOY_bot/outbuf  (.A(\Tile_X0Y1_TOY_bot/ww ),
        .X(Tile_X0Y1_WW4BEG));
endmodule
