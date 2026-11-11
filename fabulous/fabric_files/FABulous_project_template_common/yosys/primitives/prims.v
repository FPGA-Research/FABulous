// Taken from Yosys techlibs/fabulous (ISC licence) as of 49ecb1ac1, the last
// revision before Yosys stopped shipping FABulous primitives and maps.

module LUT1(output O, input I0);
  parameter [1:0] INIT = 0;
  assign O = I0 ? INIT[1] : INIT[0];
endmodule

module LUT2(output O, input I0, I1);
  parameter [3:0] INIT = 0;
  wire [ 1: 0] s1 = I1 ? INIT[ 3: 2] : INIT[ 1: 0];
  assign O = I0 ? s1[1] : s1[0];
endmodule

module LUT3(output O, input I0, I1, I2);
  parameter [7:0] INIT = 0;
  wire [ 3: 0] s2 = I2 ? INIT[ 7: 4] : INIT[ 3: 0];
  wire [ 1: 0] s1 = I1 ?   s2[ 3: 2] :   s2[ 1: 0];
  assign O = I0 ? s1[1] : s1[0];
endmodule

module LUT4(output O, input I0, I1, I2, I3);
  parameter [15:0] INIT = 0;
  wire [ 7: 0] s3 = I3 ? INIT[15: 8] : INIT[ 7: 0];
  wire [ 3: 0] s2 = I2 ?   s3[ 7: 4] :   s3[ 3: 0];
  wire [ 1: 0] s1 = I1 ?   s2[ 3: 2] :   s2[ 1: 0];
  assign O = I0 ? s1[1] : s1[0];
endmodule

module LUT4_HA(output O, Co, input I0, I1, I2, I3, Ci);
  parameter [15:0] INIT = 0;
  parameter I0MUX = 1'b1;

  wire [ 7: 0] s3 = I3 ? INIT[15: 8] : INIT[ 7: 0];
  wire [ 3: 0] s2 = I2 ?   s3[ 7: 4] :   s3[ 3: 0];
  wire [ 1: 0] s1 = I1 ?   s2[ 3: 2] :   s2[ 1: 0];

  wire I0_sel = I0MUX ? Ci : I0;
  assign O = I0_sel ? s1[1] : s1[0];

  assign Co = (Ci & I1) | (Ci & I2) | (I1 & I2);
endmodule

module LUT5(output O, input I0, I1, I2, I3, I4);
  parameter [31:0] INIT = 0;
  wire [15: 0] s4 = I4 ? INIT[31:16] : INIT[15: 0];
  wire [ 7: 0] s3 = I3 ?   s4[15: 8] :   s4[ 7: 0];
  wire [ 3: 0] s2 = I2 ?   s3[ 7: 4] :   s3[ 3: 0];
  wire [ 1: 0] s1 = I1 ?   s2[ 3: 2] :   s2[ 1: 0];
  assign O = I0 ? s1[1] : s1[0];
endmodule

module LUT6(output O, input I0, I1, I2, I3, I4, I5);
  parameter [63:0] INIT = 0;
  wire [31: 0] s5 = I5 ? INIT[63:32] : INIT[31: 0];
  wire [15: 0] s4 = I4 ?   s5[31:16] :   s5[15: 0];
  wire [ 7: 0] s3 = I3 ?   s4[15: 8] :   s4[ 7: 0];
  wire [ 3: 0] s2 = I2 ?   s3[ 7: 4] :   s3[ 3: 0];
  wire [ 1: 0] s1 = I1 ?   s2[ 3: 2] :   s2[ 1: 0];
  assign O = I0 ? s1[1] : s1[0];
endmodule

module LUT55_FCY (output O, Co, input I0, I1, I2, I3, I4, Ci);
  parameter [63:0] INIT = 0;

  wire comb1, comb2;

  LUT5 #(.INIT(INIT[31: 0])) l5_1 (.I0(I0), .I1(I1), .I2(I2), .I3(I3), .I4(I4), .O(comb1));
  LUT5 #(.INIT(INIT[63:32])) l5_2 (.I0(I0), .I1(I1), .I2(I2), .I3(I3), .I4(I4), .O(comb2));

  assign O = comb1 ^ Ci;
  assign Co = comb1 ? Ci : comb2;
endmodule


module LUTFF(input CLK, D, output reg O);
  initial O = 1'b0;
  always @ (posedge CLK) begin
    O <= D;
  end
endmodule

module FABULOUS_MUX2(input I0, I1, S0, output O);
  assign O = S0 ? I1 : I0;
endmodule

module FABULOUS_MUX4(input I0, I1, I2, I3, S0, S1, output O);
  wire A0 = S0 ? I1 : I0;
  wire A1 = S0 ? I3 : I2;
  assign O = S1 ? A1 : A0;
endmodule

module FABULOUS_MUX8(input I0, I1, I2, I3, I4, I5, I6, I7, S0, S1, S2, output O);
  wire A0 = S0 ? I1 : I0;
  wire A1 = S0 ? I3 : I2;
  wire A2 = S0 ? I5 : I4;
  wire A3 = S0 ? I7 : I6;
  wire B0 = S1 ? A1 : A0;
  wire B1 = S1 ? A3 : A2;
  assign O = S2 ? B1 : B0;
endmodule

module FABULOUS_LC #(
  parameter K = 4,
  parameter [2**K-1:0] INIT = 0,
  parameter DFF_ENABLE = 1'b0
) (
  input CLK,
  input [K-1:0] I,
  output O,
  output Q
);
  wire f_wire;

  //LUT #(.K(K), .INIT(INIT)) lut_i(.I(I), .Q(f_wire));
  generate
    if (K == 1) begin
      LUT1 #(.INIT(INIT)) lut1 (.O(f_wire), .I0(I[0]));
    end else
    if (K == 2) begin
      LUT2 #(.INIT(INIT)) lut2 (.O(f_wire), .I0(I[0]), .I1(I[1]));
    end else
    if (K == 3) begin
      LUT3 #(.INIT(INIT)) lut3 (.O(f_wire), .I0(I[0]), .I1(I[1]), .I2(I[2]));
    end else
    if (K == 4) begin
      LUT4 #(.INIT(INIT)) lut4 (.O(f_wire), .I0(I[0]), .I1(I[1]), .I2(I[2]), .I3(I[3]));
    end
  endgenerate

  LUTFF dff_i(.CLK(CLK), .D(f_wire), .O(Q));

  assign O = f_wire;
endmodule

(* blackbox *)
module Global_Clock (output CLK);
`ifndef SYNTHESIS
  initial CLK = 0;
  always #10 CLK = ~CLK;
`endif
endmodule

(* blackbox, keep *)
module InPass4_frame_config (input CLK, output O0, O1, O2, O3);

endmodule


(* blackbox, keep *)
module OutPass4_frame_config (input CLK, I0, I1, I2, I3);

endmodule

(* blackbox, keep *)
module InPass4_frame_config_mux #(
  parameter [3:0] O_reg = 0
) (
  input CLK,
  output O0,
  output O1,
  output O2,
  output O3
);
endmodule

(* blackbox, keep *)
module OutPass4_frame_config_mux #(
  parameter [3:0] I_reg = 0
) (
  input I0,
  input I1,
  input I2,
  input I3,
  input CLK
);
endmodule

(* keep *)
module IO_1_bidirectional_frame_config_pass (input CLK, T, I, output Q, O, (* iopad_external_pin *) inout PAD);
  assign PAD = T ? 1'bz : I;
  assign O = PAD;
  reg Q_q;
  always @(posedge CLK) Q_q <= O;
  assign Q = Q_q;
endmodule


module MULADD (
  input [7:0] A,  // operand A
  input [7:0] B,  // operand B
  input [19:0] C, // operand C
  output [19:0] Q,
  input clr,
  input CLK
);
  parameter A_reg = 1'b0;
  parameter B_reg = 1'b0;
  parameter C_reg = 1'b0;
  parameter ACC = 1'b0;
  parameter signExtension = 1'b0;
  parameter ACCout = 1'b0;

  reg [7:0] A_q;
  reg [7:0] B_q;
  reg [19:0] C_q;
  wire [7:0] OPA;
  wire [7:0] OPB;
  wire [19:0] OPC;
  reg [19:0] ACC_data; // accumulator register
  wire [19:0] sum;
  wire [19:0] sum_in;
  wire [15:0] product;
  wire [19:0] product_extended;

  assign OPA = A_reg ? A_q : A;
  assign OPB = B_reg ? B_q : B;
  assign OPC = C_reg ? C_q : C;
  assign sum_in = ACC ? ACC_data : OPC;
  assign product = OPA * OPB;
  // The sign extension was not tested
  assign product_extended = signExtension ? {{4{product[15]}}, product} : {4'b0000, product};
  assign sum = product_extended + sum_in;
  assign Q = ACCout ? ACC_data : sum;

  always @(posedge CLK) begin
    A_q <= A;
    B_q <= B;
    C_q <= C;
    if (clr == 1'b1) begin
      ACC_data <= 20'b0;
    end else begin
      ACC_data <= sum;
    end
  end
endmodule

module RegFile_32x4 (
  input [3:0] D,     // write data
  input [4:0] W_ADR, // write address
  input W_en,
  output [3:0] AD,   // port A read data
  input [4:0] A_ADR, // port A read address
  output [3:0] BD,   // port B read data
  input [4:0] B_ADR, // port B read address
  input CLK
);
  parameter AD_reg = 1'b0;
  parameter BD_reg = 1'b0;

  reg [3:0] mem [31:0];
  wire [3:0] AD_comb;
  wire [3:0] BD_comb;
  reg [3:0] AD_q; // port A read data register
  reg [3:0] BD_q; // port B read data register
  integer i;

  initial begin
    for (i = 0; i < 32; i = i + 1) begin
      mem[i] = 4'b0000;
    end
  end

  always @(posedge CLK) begin : P_write
    if (W_en == 1'b1) begin
      mem[W_ADR] <= D;
    end
  end

  assign AD_comb = mem[A_ADR];
  assign BD_comb = mem[B_ADR];

  always @(posedge CLK) begin
    AD_q <= AD_comb;
    BD_q <= BD_comb;
  end

  assign AD = AD_reg ? AD_q : AD_comb;
  assign BD = BD_reg ? BD_q : BD_comb;
endmodule


module LUTFF_E (
  output reg O,
  input CLK, E, D
);
  initial O = 1'b0;
  always @(posedge CLK)
    if (E)
      O <= D;
endmodule

module LUTFF_SR (
  output reg O,
  input CLK, R, D
);
  initial O = 1'b0;
  always @(posedge CLK)
    if (R)
      O <= 0;
    else
      O <= D;
endmodule

module LUTFF_SS (
  output reg O,
  input CLK, S, D
);
  initial O = 1'b0;
  always @(posedge CLK)
    if (S)
      O <= 1;
    else
      O <= D;
endmodule

module LUTFF_ESR (
  output reg O,
  input CLK, E, R, D
);
  initial O = 1'b0;
  always @(posedge CLK)
    if (E) begin
      if (R)
        O <= 0;
      else
        O <= D;
    end
endmodule

module LUTFF_ESS (
  output reg O,
  input CLK, E, S, D
);
  initial O = 1'b0;
  always @(posedge CLK)
    if (E) begin
      if (S)
        O <= 1;
      else
        O <= D;
    end
endmodule
