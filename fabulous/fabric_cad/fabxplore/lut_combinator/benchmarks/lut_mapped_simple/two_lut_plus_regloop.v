module two_lut_plus_regloop(
  input  wire clk,
  input  wire we,
  input  wire a,
  input  wire b,
  input  wire c,
  input  wire d,
  input  wire e,
  input  wire sel,
  output wire y0,
  output wire y1,
  output wire y_r
);
  wire n0;
  wire n1;
  wire rdata;
  wire wdata;

  // Packable pair for FRAC_LUT5 (K=4, shared=3).
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

  // Feedback LUT: wdata depends on current rdata.
  LUT2 #(
    .INIT(4'h6) // XOR
  ) u_fb (
    .I0(rdata),
    .I1(sel),
    .O(wdata)
  );

  // Unknown/non-LUT "register-like" cell.
  // Equiv harness models this synthetically (not true sequential behavior).
  REGX u_regx (
    .CLK(clk),
    .WE(we),
    .WDATA(wdata),
    .RDATA(rdata)
  );

  assign y0 = n0;
  assign y1 = n1;
  assign y_r = rdata;
endmodule
