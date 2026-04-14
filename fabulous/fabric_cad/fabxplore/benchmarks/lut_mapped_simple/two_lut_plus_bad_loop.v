module two_lut_plus_bad_loop(
  input  wire a,
  input  wire b,
  input  wire c,
  input  wire d,
  input  wire e,
  output wire y0,
  output wire y1,
  output wire y_r
);
  wire n0;
  wire n1;
  wire rdata;
  wire wdata;

  // Packable pair.
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

  // wdata = ~rdata
  LUT2 #(
    .INIT(4'h6) // XOR
  ) u_inv (
    .I0(rdata),
    .I1(1'b1),
    .O(wdata)
  );

  // Synthetic model in equiv_only maps RDATA <- WDATA.
  // Combined with u_inv this forms rdata = ~rdata.
  REGX u_regx (
    .CLK(1'b0),
    .WE(1'b1),
    .WDATA(wdata),
    .RDATA(rdata)
  );

  assign y0 = n0;
  assign y1 = n1;
  assign y_r = rdata;
endmodule
