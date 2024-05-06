// Models for the embedded FPGA fabric
// LHD1 Latch area 11.76
//`timescale 1ns/1ns
/* module LHD1_old (D, E, Q, QN);
	input D;     // global signal 1: configuration, 0: operation
	input E;
	output Q;
	output QN; 

	wire M_set_gate, M_reset_gate;
	wire S_set_gate, S_reset_gate;
	wire M_q, M_qn;
	wire S_q, S_qn;

	// master
	assign M_set_gate = ~(D & E);
	assign M_reset_gate = ~((~D) & E);
	assign M_q = ~(M_qn & M_set_gate);
	assign M_qn = ~(M_q & M_reset_gate);

	assign Q = M_q;
	assign QN = M_qn;

endmodule

module LHQD1 (input D, E, output reg Q);
    always @(*) begin
        if (E == 1'b1) begin
            Q = D;
        end
    end
endmodule

module LHQD1_old (D, E, Q);
	input D;// global signal 1: configuration, 0: operation
	input E;
	output Q;

	wire M_set_gate;
	wire M_reset_gate;
	wire M_q;
	wire M_qn;

// master
	assign M_set_gate = ~(D & E);
	assign M_reset_gate = ~((~D) & E);
	assign M_q = ~(M_qn & M_set_gate);
	assign M_qn = (M_q & M_reset_gate);

	assign Q = M_q;

endmodule */

module LHQD1 (input D, E, output reg Q, QN);
    always @(*)
    begin
        if (E == 1'b1) begin
            Q = D;
            QN = ~D;
        end
    end
endmodule

// (MUX4PTv4) and 1.2ns (MUX16PTv2) in worse case when all select bits=0, so I think they work fine with f=50MHz. 
// The area are HxW = 7um x 9.86um (MUX4PTv4) and 7um x 44.72um (MUX16PTv2). 
// Please note, the pins are named as IN1, IN2, ..., IN16 for inputs, S1, .., S4 for selects and OUT for output.

module MUX4PTv4 (IN1, IN2, IN3, IN4, S1, S2, O);
	input IN1;
	input IN2;
	input IN3;
	input IN4;
	input S1;
	input S2;
	output O; 
	reg O;
	wire [1:0] SEL;

	assign SEL = {S2,S1};
	always @(*) 
	begin
		case(SEL)
			2'b00:O = IN1;
			2'b01:O = IN2;
			2'b10:O = IN3;
			2'b11:O = IN4;
			default:O = 1'b0;
		endcase
	end

endmodule 

module MUX16PTv2 (IN1, IN2, IN3, IN4, IN5, IN6, IN7, IN8, IN9, IN10, IN11, IN12, IN13, IN14, IN15, IN16, S1, S2, S3, S4, O);
	input IN1;
	input IN2;
	input IN3;
	input IN4;
	input IN5;
	input IN6;
	input IN7;
	input IN8;
	input IN9;
	input IN10;
	input IN11;
	input IN12;
	input IN13;
	input IN14;
	input IN15;
	input IN16;
	input S1;
	input S2;
	input S3;
	input S4;
	output O;
	reg O;
	wire [3:0] SEL;

	assign SEL = {S4,S3,S2,S1};
	always @(*)
	begin
		case(SEL)
			4'b0000: O = IN1;
			4'b0001: O = IN2;
			4'b0010: O = IN3;
			4'b0011: O = IN4;
			4'b0100: O = IN5;
			4'b0101: O = IN6;
			4'b0110: O = IN7;
			4'b0111: O = IN8;
			4'b1000: O = IN9;
			4'b1001: O = IN10;
			4'b1010: O = IN11;
			4'b1011: O = IN12;
			4'b1100: O = IN13;
			4'b1101: O = IN14;
			4'b1110: O = IN15;
			4'b1111: O = IN16;
			default: O = 1'b0;
		endcase
	end

endmodule

module my_buf (A, X);
    input A;
    output X;
    assign X = A;
endmodule

module cus_mux41 (A0, A1, A2, A3, S0, S0N, S1, S1N, X);
	input A0;
	input A1;
	input A2;
	input A3;
	input S0;
	input S0N;
	input S1;
	input S1N;
	output X; 
	wire [1:0] SEL;
	wire [3:0] AIN;

	break_comb_loop break_comb_loop_inst0(.A (A0), .X (AIN[0]));
	break_comb_loop break_comb_loop_inst1(.A (A1), .X (AIN[1]));
	break_comb_loop break_comb_loop_inst2(.A (A2), .X (AIN[2]));
	break_comb_loop break_comb_loop_inst3(.A (A3), .X (AIN[3]));

	wire B0 = S0 ? AIN[1] : AIN[0];
	wire B1 = S0 ? AIN[3] : AIN[2];
	assign X =  S1 ? B1 : B0;
endmodule

module cus_mux41_buf (A0, A1, A2, A3, S0, S0N, S1, S1N, X);
	input A0;
	input A1;
	input A2;
	input A3;
	input S0;
	input S0N;
	input S1;
	input S1N;
	output X; 
	wire [3:0] AIN;

	break_comb_loop break_comb_loop_inst0(.A (A0), .X (AIN[0]));
	break_comb_loop break_comb_loop_inst1(.A (A1), .X (AIN[1]));
	break_comb_loop break_comb_loop_inst2(.A (A2), .X (AIN[2]));
	break_comb_loop break_comb_loop_inst3(.A (A3), .X (AIN[3]));

	wire B0 = S0 ? AIN[1] : AIN[0];
	wire B1 = S0 ? AIN[3] : AIN[2];
	assign X =  S1 ? B1 : B0;
endmodule

module my_mux2 (A0, A1, S, X);
	input A0;
	input A1;
	input S;
	output X;
	wire [1:0] AIN;

	break_comb_loop break_comb_loop_inst0(.A (A0), .X (AIN[0]));
	break_comb_loop break_comb_loop_inst1(.A (A1), .X (AIN[1]));

	assign X = S ? AIN[1] : AIN[0];
endmodule 

module cus_mux81 (A0, A1, A2, A3, A4, A5, A6, A7, S0, S0N, S1, S1N, S2, S2N, X);
	input A0;
	input A1;
	input A2;
	input A3;
	input A4;
	input A5;
	input A6;
	input A7;
	input S0;
	input S0N;
	input S1;
	input S1N;
	input S2;
	input S2N;
	output X;

	wire cus_mux41_out0;
	wire cus_mux41_out1;

	cus_mux41 cus_mux41_inst0(
	.A0 (A0),
	.A1 (A1),
	.A2 (A2),
	.A3 (A3),
	.S0 (S0),
	.S0N(S0N),
	.S1 (S1),
	.S1N(S1N),
	.X  (cus_mux41_out0)
	);
	
	cus_mux41 cus_mux41_inst1(
	.A0 (A4),
	.A1 (A5),
	.A2 (A6),
	.A3 (A7),
	.S0 (S0),
	.S0N(S0N),
	.S1 (S1),
	.S1N(S1N),
	.X  (cus_mux41_out1)
	);

	my_mux2 my_mux2_inst(
	.A0(cus_mux41_out0),
	.A1(cus_mux41_out1),
	.S (S2),
	.X (X)
	);
endmodule

module cus_mux81_buf (A0, A1, A2, A3, A4, A5, A6, A7, S0, S0N, S1, S1N, S2, S2N, X);
	input A0;
	input A1;
	input A2;
	input A3;
	input A4;
	input A5;
	input A6;
	input A7;
	input S0;
	input S0N;
	input S1;
	input S1N;
	input S2;
	input S2N;
	output X;

	wire cus_mux41_buf_out0;
	wire cus_mux41_buf_out1;

	cus_mux41_buf cus_mux41_buf_inst0(
	.A0 (A0),
	.A1 (A1),
	.A2 (A2),
	.A3 (A3),
	.S0 (S0),
	.S0N(S0N),
	.S1 (S1),
	.S1N(S1N),
	.X  (cus_mux41_buf_out0)
	);
	
	cus_mux41_buf cus_mux41_buf_inst1(
	.A0 (A4),
	.A1 (A5),
	.A2 (A6),
	.A3 (A7),
	.S0 (S0),
	.S0N(S0N),
	.S1 (S1),
	.S1N(S1N),
	.X  (cus_mux41_buf_out1)
	);

	my_mux2 my_mux2_inst(
	.A0(cus_mux41_buf_out0),
	.A1(cus_mux41_buf_out1),
	.S (S2),
	.X (X)
	);
endmodule

module cus_mux161 (A0, A1, A2, A3, A4, A5, A6, A7, A8, A9, A10, A11, A12, A13, A14, A15, S0, S0N, S1, S1N, S2, S2N, S3, S3N, X);
	input A0;
	input A1;
	input A2;
	input A3;
	input A4;
	input A5;
	input A6;
	input A7;
	input A8;
	input A9;
	input A10;
	input A11;
	input A12;
	input A13;
	input A14;
	input A15;
	input S0;
	input S0N;
	input S1;
	input S1N;
	input S2;
	input S2N;
	input S3;
	input S3N;
	output X;

	wire cus_mux41_out0;
	wire cus_mux41_out1;
	wire cus_mux41_out2;
	wire cus_mux41_out3;

	cus_mux41 cus_mux41_inst0(
	.A0 (A0),
	.A1 (A1),
	.A2 (A2),
	.A3 (A3),
	.S0 (S0),
	.S0N(S0N),
	.S1 (S1),
	.S1N(S1N),
	.X  (cus_mux41_out0)
	);
	
	cus_mux41 cus_mux41_inst1(
	.A0 (A4),
	.A1 (A5),
	.A2 (A6),
	.A3 (A7),
	.S0 (S0),
	.S0N(S0N),
	.S1 (S1),
	.S1N(S1N),
	.X  (cus_mux41_out1)
	);

	cus_mux41 cus_mux41_inst2(
	.A0 (A8),
	.A1 (A9),
	.A2 (A10),
	.A3 (A11),
	.S0 (S0),
	.S0N(S0N),
	.S1 (S1),
	.S1N(S1N),
	.X  (cus_mux41_out2)
	);

	cus_mux41 cus_mux41_inst3(
	.A0 (A12),
	.A1 (A13),
	.A2 (A14),
	.A3 (A15),
	.S0 (S0),
	.S0N(S0N),
	.S1 (S1),
	.S1N(S1N),
	.X  (cus_mux41_out3)
	);
	
	cus_mux41 cus_mux41_inst4(
	.A0 (cus_mux41_out0),
	.A1 (cus_mux41_out1),
	.A2 (cus_mux41_out2),
	.A3 (cus_mux41_out3),
	.S0 (S2),
	.S0N(S2N),
	.S1 (S3),
	.S1N(S3N),
	.X  (X)
	);
endmodule

module cus_mux161_buf (A0, A1, A2, A3, A4, A5, A6, A7, A8, A9, A10, A11, A12, A13, A14, A15, S0, S0N, S1, S1N, S2, S2N, S3, S3N, X);
	input A0;
	input A1;
	input A2;
	input A3;
	input A4;
	input A5;
	input A6;
	input A7;
	input A8;
	input A9;
	input A10;
	input A11;
	input A12;
	input A13;
	input A14;
	input A15;
	input S0;
	input S0N;
	input S1;
	input S1N;
	input S2;
	input S2N;
	input S3;
	input S3N;
	output X;

	wire cus_mux41_buf_out0;
	wire cus_mux41_buf_out1;
	wire cus_mux41_buf_out2;
	wire cus_mux41_buf_out3;

	cus_mux41_buf cus_mux41_buf_inst0(
	.A0 (A0),
	.A1 (A1),
	.A2 (A2),
	.A3 (A3),
	.S0 (S0),
	.S0N(S0N),
	.S1 (S1),
	.S1N(S1N),
	.X  (cus_mux41_buf_out0)
	);
	
	cus_mux41_buf cus_mux41_buf_inst1(
	.A0 (A4),
	.A1 (A5),
	.A2 (A6),
	.A3 (A7),
	.S0 (S0),
	.S0N(S0N),
	.S1 (S1),
	.S1N(S1N),
	.X  (cus_mux41_buf_out1)
	);

	cus_mux41_buf cus_mux41_buf_inst2(
	.A0 (A8),
	.A1 (A9),
	.A2 (A10),
	.A3 (A11),
	.S0 (S0),
	.S0N(S0N),
	.S1 (S1),
	.S1N(S1N),
	.X  (cus_mux41_buf_out2)
	);

	cus_mux41_buf cus_mux41_buf_inst3(
	.A0 (A12),
	.A1 (A13),
	.A2 (A14),
	.A3 (A15),
	.S0 (S0),
	.S0N(S0N),
	.S1 (S1),
	.S1N(S1N),
	.X  (cus_mux41_buf_out3)
	);
	
	cus_mux41_buf cus_mux41_buf_inst4(
	.A0 (cus_mux41_buf_out0),
	.A1 (cus_mux41_buf_out1),
	.A2 (cus_mux41_buf_out2),
	.A3 (cus_mux41_buf_out3),
	.S0 (S2),
	.S0N(S2N),
	.S1 (S3),
	.S1N(S3N),
	.X  (X)
	);
endmodule
