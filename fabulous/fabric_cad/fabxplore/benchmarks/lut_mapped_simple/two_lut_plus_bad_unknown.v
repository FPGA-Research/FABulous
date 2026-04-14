module two_lut_plus_bad_unknown(
  input  wire a,
  input  wire b,
  input  wire c,
  input  wire d,
  input  wire e,
  input  wire sel,
  output wire y0,
  output wire y1,
  output wire y_bad
);
  wire n0;
  wire n1;
  wire bad_r;
  wire bad_x;

  // Packable LUT pair (K=4, shared=3).
  LUT4 #(
    .INIT(16'h6996)
  ) u_lut0 (
    .I0(a),
    .I1(b),
    .I2(c),
    .I3(d),
    .O(n0)
  );

  LUT4 #(
    .INIT(16'hA55A)
  ) u_lut1 (
    .I0(a),
    .I1(b),
    .I2(c),
    .I3(e),
    .O(n1)
  );

  // Unknown/non-LUT cell with intentionally tricky port names.
  // In our synthetic equiv model, output inference can mis-detect this shape.
  BADCELL u_bad (
    .A(n0),
    .R(bad_r),
    .X(bad_x),
    .SEL(sel),
    .B(n1)
  );

  assign y0 = n0;
  assign y1 = n1;
  assign y_bad = bad_r;
endmodule
