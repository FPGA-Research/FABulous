module \$_FF_ (input D, output Q);
  LUTFF _TECHMAP_REPLACE_ (.D(D), .O(Q), .CLK(1'b1));
endmodule

(* blackbox *)
module FABULOUS_MUX2(input I0, I1, S0, output O);
endmodule

(* blackbox *)
module FABULOUS_MUX4(input I0, I1, I2, I3, S0, S1, output O);
endmodule

(* blackbox *)
module FABULOUS_MUX8(input I0, I1, I2, I3, I4, I5, I6, I7, S0, S1, S2, output O);
endmodule

module \$lut (A, Y);
  parameter WIDTH = 0;
  parameter [255:0] LUT = 0;

  input [WIDTH-1:0] A;
  output Y;

  generate
    if (WIDTH == 1) begin
      LUT5 #(.INIT(LUT[31:0])) _TECHMAP_REPLACE_ (
        .O(Y),
        .I0(A[0]),
        .I1(1'b0),
        .I2(1'b0),
        .I3(1'b0),
        .I4(1'b0)
      );

    end else
    if (WIDTH == 2) begin
      LUT5 #(.INIT(LUT[31:0])) _TECHMAP_REPLACE_ (
        .O(Y),
        .I0(A[0]),
        .I1(A[1]),
        .I2(1'b0),
        .I3(1'b0),
        .I4(1'b0)
      );

    end else
    if (WIDTH == 3) begin
      LUT5 #(.INIT(LUT[31:0])) _TECHMAP_REPLACE_ (
        .O(Y),
        .I0(A[0]),
        .I1(A[1]),
        .I2(A[2]),
        .I3(1'b0),
        .I4(1'b0)
      );

    end else
    if (WIDTH == 4) begin
      LUT5 #(.INIT(LUT[31:0])) _TECHMAP_REPLACE_ (
        .O(Y),
        .I0(A[0]),
        .I1(A[1]),
        .I2(A[2]),
        .I3(A[3]),
        .I4(1'b0)
      );

    end else
    if (WIDTH == 5) begin
      LUT5 #(.INIT(LUT[31:0])) _TECHMAP_REPLACE_ (
        .O(Y),
        .I0(A[0]),
        .I1(A[1]),
        .I2(A[2]),
        .I3(A[3]),
        .I4(A[4])
      );

    end else
    if (WIDTH == 6) begin
      wire leaf0;
      wire leaf1;

      LUT5 #(.INIT(LUT[31:0])) lut0 (
        .O(leaf0),
        .I0(A[0]),
        .I1(A[1]),
        .I2(A[2]),
        .I3(A[3]),
        .I4(A[4])
      );
      LUT5 #(.INIT(LUT[63:32])) lut1 (
        .O(leaf1),
        .I0(A[0]),
        .I1(A[1]),
        .I2(A[2]),
        .I3(A[3]),
        .I4(A[4])
      );
      FABULOUS_MUX2 _TECHMAP_REPLACE_ (
        .I0(leaf0),
        .I1(leaf1),
        .S0(A[5]),
        .O(Y)
      );

    end else
    if (WIDTH == 7) begin
      wire leaf0;
      wire leaf1;
      wire leaf2;
      wire leaf3;

      LUT5 #(.INIT(LUT[31:0])) lut0 (
        .O(leaf0),
        .I0(A[0]),
        .I1(A[1]),
        .I2(A[2]),
        .I3(A[3]),
        .I4(A[4])
      );
      LUT5 #(.INIT(LUT[63:32])) lut1 (
        .O(leaf1),
        .I0(A[0]),
        .I1(A[1]),
        .I2(A[2]),
        .I3(A[3]),
        .I4(A[4])
      );
      LUT5 #(.INIT(LUT[95:64])) lut2 (
        .O(leaf2),
        .I0(A[0]),
        .I1(A[1]),
        .I2(A[2]),
        .I3(A[3]),
        .I4(A[4])
      );
      LUT5 #(.INIT(LUT[127:96])) lut3 (
        .O(leaf3),
        .I0(A[0]),
        .I1(A[1]),
        .I2(A[2]),
        .I3(A[3]),
        .I4(A[4])
      );
      FABULOUS_MUX4 _TECHMAP_REPLACE_ (
        .I0(leaf0),
        .I1(leaf1),
        .I2(leaf2),
        .I3(leaf3),
        .S0(A[5]),
        .S1(A[6]),
        .O(Y)
      );

    end else
    if (WIDTH == 8) begin
      wire leaf0;
      wire leaf1;
      wire leaf2;
      wire leaf3;
      wire leaf4;
      wire leaf5;
      wire leaf6;
      wire leaf7;

      LUT5 #(.INIT(LUT[31:0])) lut0 (
        .O(leaf0),
        .I0(A[0]),
        .I1(A[1]),
        .I2(A[2]),
        .I3(A[3]),
        .I4(A[4])
      );
      LUT5 #(.INIT(LUT[63:32])) lut1 (
        .O(leaf1),
        .I0(A[0]),
        .I1(A[1]),
        .I2(A[2]),
        .I3(A[3]),
        .I4(A[4])
      );
      LUT5 #(.INIT(LUT[95:64])) lut2 (
        .O(leaf2),
        .I0(A[0]),
        .I1(A[1]),
        .I2(A[2]),
        .I3(A[3]),
        .I4(A[4])
      );
      LUT5 #(.INIT(LUT[127:96])) lut3 (
        .O(leaf3),
        .I0(A[0]),
        .I1(A[1]),
        .I2(A[2]),
        .I3(A[3]),
        .I4(A[4])
      );
      LUT5 #(.INIT(LUT[159:128])) lut4 (
        .O(leaf4),
        .I0(A[0]),
        .I1(A[1]),
        .I2(A[2]),
        .I3(A[3]),
        .I4(A[4])
      );
      LUT5 #(.INIT(LUT[191:160])) lut5 (
        .O(leaf5),
        .I0(A[0]),
        .I1(A[1]),
        .I2(A[2]),
        .I3(A[3]),
        .I4(A[4])
      );
      LUT5 #(.INIT(LUT[223:192])) lut6 (
        .O(leaf6),
        .I0(A[0]),
        .I1(A[1]),
        .I2(A[2]),
        .I3(A[3]),
        .I4(A[4])
      );
      LUT5 #(.INIT(LUT[255:224])) lut7 (
        .O(leaf7),
        .I0(A[0]),
        .I1(A[1]),
        .I2(A[2]),
        .I3(A[3]),
        .I4(A[4])
      );
      FABULOUS_MUX8 _TECHMAP_REPLACE_ (
        .I0(leaf0),
        .I1(leaf1),
        .I2(leaf2),
        .I3(leaf3),
        .I4(leaf4),
        .I5(leaf5),
        .I6(leaf6),
        .I7(leaf7),
        .S0(A[5]),
        .S1(A[6]),
        .S2(A[7]),
        .O(Y)
      );

    end else begin
      wire _TECHMAP_FAIL_ = 1;
    end
  endgenerate
endmodule
