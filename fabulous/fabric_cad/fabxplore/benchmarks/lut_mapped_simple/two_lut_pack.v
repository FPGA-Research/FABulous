module two_lut_pack(
  input  wire a,
  input  wire b,
  input  wire c,
  input  wire d,
  input  wire e,
  output wire y0,
  output wire y1
);
  // LUT0 uses shared {a,b,c} + private {d}
  LUT4 #(
    .INIT(16'h6996)
  ) u_lut0 (
    .I0(a),
    .I1(b),
    .I2(c),
    .I3(d),
    .O(y0)
  );

  // LUT1 uses shared {a,b,c} + private {e}
  LUT4 #(
    .INIT(16'hA55A)
  ) u_lut1 (
    .I0(a),
    .I1(b),
    .I2(c),
    .I3(e),
    .O(y1)
  );
endmodule
