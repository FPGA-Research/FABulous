// Maps the synth_fabulous pad cells onto the fabric IO BEL.

module \$__FABULOUS_IBUF (input PAD, output OUT);
    IO_1_bidirectional_frame_config_pass _TECHMAP_REPLACE_ (.T(1'b1), .O(OUT), .PAD(PAD));
endmodule

module \$__FABULOUS_OBUF (output PAD, input IN);
    IO_1_bidirectional_frame_config_pass _TECHMAP_REPLACE_ (.T(1'b0), .I(IN), .PAD(PAD));
endmodule

module \$__FABULOUS_TBUF (output PAD, input IN, input EN);
    IO_1_bidirectional_frame_config_pass _TECHMAP_REPLACE_ (.T(!EN), .I(IN), .PAD(PAD));
endmodule

module \$__FABULOUS_IOBUF (inout PAD, output OUT, input IN, input EN);
    IO_1_bidirectional_frame_config_pass _TECHMAP_REPLACE_ (.T(!EN), .I(IN), .O(OUT), .PAD(PAD));
endmodule
