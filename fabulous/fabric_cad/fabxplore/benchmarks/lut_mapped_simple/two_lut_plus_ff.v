module two_lut_plus_ff(
  input  wire clk,
  input  wire a,
  input  wire b,
  input  wire c,
  input  wire d,
  input  wire e,
  output wire y0,
  output wire y1,
  output wire q
);
  wire n0;
  wire n1;

  // Two LUT4 cells that fit one FRAC_LUT5 for K=4, shared=3.
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

  // Intentionally no module definition provided for LUTFF:
  // this acts like an "unknown/non-LUT" cell in the benchmark.
  LUTFF u_ff0 (
    .CLK(clk),
    .D(n0),
    .O(q)
  );

  assign y0 = n0;
  assign y1 = n1;
endmodule
