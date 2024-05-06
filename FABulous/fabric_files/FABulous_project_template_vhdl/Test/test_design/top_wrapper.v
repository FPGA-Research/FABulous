// TODO: find a more fun test design

module top_wrapper;

wire [27:0] io_in, io_out, io_oeb;
(* keep, BEL="X0Y1.A" *) IO_1_bidirectional_frame_config_pass io27_i (.O(io_in[27]), .I(io_out[27]), .T(io_oeb[27]));
(* keep, BEL="X0Y1.B" *) IO_1_bidirectional_frame_config_pass io26_i (.O(io_in[26]), .I(io_out[26]), .T(io_oeb[26]));
(* keep, BEL="X0Y2.A" *) IO_1_bidirectional_frame_config_pass io25_i (.O(io_in[25]), .I(io_out[25]), .T(io_oeb[25]));
(* keep, BEL="X0Y2.B" *) IO_1_bidirectional_frame_config_pass io24_i (.O(io_in[24]), .I(io_out[24]), .T(io_oeb[24]));
(* keep, BEL="X0Y3.A" *) IO_1_bidirectional_frame_config_pass io23_i (.O(io_in[23]), .I(io_out[23]), .T(io_oeb[23]));
(* keep, BEL="X0Y3.B" *) IO_1_bidirectional_frame_config_pass io22_i (.O(io_in[22]), .I(io_out[22]), .T(io_oeb[22]));
(* keep, BEL="X0Y4.A" *) IO_1_bidirectional_frame_config_pass io21_i (.O(io_in[21]), .I(io_out[21]), .T(io_oeb[21]));
(* keep, BEL="X0Y4.B" *) IO_1_bidirectional_frame_config_pass io20_i (.O(io_in[20]), .I(io_out[20]), .T(io_oeb[20]));
(* keep, BEL="X0Y5.A" *) IO_1_bidirectional_frame_config_pass io19_i (.O(io_in[19]), .I(io_out[19]), .T(io_oeb[19]));
(* keep, BEL="X0Y5.B" *) IO_1_bidirectional_frame_config_pass io18_i (.O(io_in[18]), .I(io_out[18]), .T(io_oeb[18]));
(* keep, BEL="X0Y6.A" *) IO_1_bidirectional_frame_config_pass io17_i (.O(io_in[17]), .I(io_out[17]), .T(io_oeb[17]));
(* keep, BEL="X0Y6.B" *) IO_1_bidirectional_frame_config_pass io16_i (.O(io_in[16]), .I(io_out[16]), .T(io_oeb[16]));
(* keep, BEL="X0Y7.A" *) IO_1_bidirectional_frame_config_pass io15_i (.O(io_in[15]), .I(io_out[15]), .T(io_oeb[15]));
(* keep, BEL="X0Y7.B" *) IO_1_bidirectional_frame_config_pass io14_i (.O(io_in[14]), .I(io_out[14]), .T(io_oeb[14]));
(* keep, BEL="X0Y8.A" *) IO_1_bidirectional_frame_config_pass io13_i (.O(io_in[13]), .I(io_out[13]), .T(io_oeb[13]));
(* keep, BEL="X0Y8.B" *) IO_1_bidirectional_frame_config_pass io12_i (.O(io_in[12]), .I(io_out[12]), .T(io_oeb[12]));
(* keep, BEL="X0Y9.A" *) IO_1_bidirectional_frame_config_pass io11_i (.O(io_in[11]), .I(io_out[11]), .T(io_oeb[11]));
(* keep, BEL="X0Y9.B" *) IO_1_bidirectional_frame_config_pass io10_i (.O(io_in[10]), .I(io_out[10]), .T(io_oeb[10]));
(* keep, BEL="X0Y10.A" *) IO_1_bidirectional_frame_config_pass io9_i (.O(io_in[9]), .I(io_out[9]), .T(io_oeb[9]));
(* keep, BEL="X0Y10.B" *) IO_1_bidirectional_frame_config_pass io8_i (.O(io_in[8]), .I(io_out[8]), .T(io_oeb[8]));
(* keep, BEL="X0Y11.A" *) IO_1_bidirectional_frame_config_pass io7_i (.O(io_in[7]), .I(io_out[7]), .T(io_oeb[7]));
(* keep, BEL="X0Y11.B" *) IO_1_bidirectional_frame_config_pass io6_i (.O(io_in[6]), .I(io_out[6]), .T(io_oeb[6]));
(* keep, BEL="X0Y12.A" *) IO_1_bidirectional_frame_config_pass io5_i (.O(io_in[5]), .I(io_out[5]), .T(io_oeb[5]));
(* keep, BEL="X0Y12.B" *) IO_1_bidirectional_frame_config_pass io4_i (.O(io_in[4]), .I(io_out[4]), .T(io_oeb[4]));
(* keep, BEL="X0Y13.A" *) IO_1_bidirectional_frame_config_pass io3_i (.O(io_in[3]), .I(io_out[3]), .T(io_oeb[3]));
(* keep, BEL="X0Y13.B" *) IO_1_bidirectional_frame_config_pass io2_i (.O(io_in[2]), .I(io_out[2]), .T(io_oeb[2]));
(* keep, BEL="X0Y14.A" *) IO_1_bidirectional_frame_config_pass io1_i (.O(io_in[1]), .I(io_out[1]), .T(io_oeb[1]));
(* keep, BEL="X0Y14.B" *) IO_1_bidirectional_frame_config_pass io0_i (.O(io_in[0]), .I(io_out[0]), .T(io_oeb[0]));

wire clk;
(* keep *) Global_Clock clk_i (.CLK(clk));

top top_i(.clk(clk), .io_in(io_in), .io_out(io_out), .io_oeb(io_oeb));

endmodule

