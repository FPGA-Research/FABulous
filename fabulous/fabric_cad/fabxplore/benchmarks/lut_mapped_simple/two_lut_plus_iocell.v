module two_lut_plus_iocell(
  input  wire a,
  input  wire b,
  input  wire c,
  input  wire d,
  input  wire e,
  inout  wire pad,
  output wire y0,
  output wire y1,
  output wire ypad
);
  wire n0;
  wire n1;
  wire pad_in;

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

  // Unknown IO-style cell (like enet style wrappers).
  IO_1_bidirectional_frame_config_pass u_io (
    .I(n0),
    .OE(n1),
    .PAD(pad),
    .O(pad_in)
  );

  assign y0 = n0;
  assign y1 = n1;
  assign ypad = pad_in;
endmodule
