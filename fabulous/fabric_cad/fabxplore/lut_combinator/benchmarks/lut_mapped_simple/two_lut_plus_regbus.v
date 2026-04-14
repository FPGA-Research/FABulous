module two_lut_plus_regbus(
  input  wire a,
  input  wire b,
  input  wire c,
  input  wire d,
  input  wire e,
  output wire y0,
  output wire y1,
  output wire [15:0] y_bus
);
  wire n0;
  wire n1;
  wire [15:0] rdata;
  wire [15:0] wdata;

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

  // Feedback fabric: wdata[i] = rdata[i] XOR pattern_bit[i].
  // For bits with pattern_bit=1 this creates contradiction under
  // synthetic REGFILEX passthrough abstraction.
  LUT2 #(.INIT(4'h6)) u_fb_0  (.I0(rdata[0]),  .I1(1'b1), .O(wdata[0]));
  LUT2 #(.INIT(4'h6)) u_fb_1  (.I0(rdata[1]),  .I1(1'b0), .O(wdata[1]));
  LUT2 #(.INIT(4'h6)) u_fb_2  (.I0(rdata[2]),  .I1(1'b1), .O(wdata[2]));
  LUT2 #(.INIT(4'h6)) u_fb_3  (.I0(rdata[3]),  .I1(1'b0), .O(wdata[3]));
  LUT2 #(.INIT(4'h6)) u_fb_4  (.I0(rdata[4]),  .I1(1'b1), .O(wdata[4]));
  LUT2 #(.INIT(4'h6)) u_fb_5  (.I0(rdata[5]),  .I1(1'b0), .O(wdata[5]));
  LUT2 #(.INIT(4'h6)) u_fb_6  (.I0(rdata[6]),  .I1(1'b1), .O(wdata[6]));
  LUT2 #(.INIT(4'h6)) u_fb_7  (.I0(rdata[7]),  .I1(1'b0), .O(wdata[7]));
  LUT2 #(.INIT(4'h6)) u_fb_8  (.I0(rdata[8]),  .I1(1'b1), .O(wdata[8]));
  LUT2 #(.INIT(4'h6)) u_fb_9  (.I0(rdata[9]),  .I1(1'b0), .O(wdata[9]));
  LUT2 #(.INIT(4'h6)) u_fb_10 (.I0(rdata[10]), .I1(1'b1), .O(wdata[10]));
  LUT2 #(.INIT(4'h6)) u_fb_11 (.I0(rdata[11]), .I1(1'b0), .O(wdata[11]));
  LUT2 #(.INIT(4'h6)) u_fb_12 (.I0(rdata[12]), .I1(1'b1), .O(wdata[12]));
  LUT2 #(.INIT(4'h6)) u_fb_13 (.I0(rdata[13]), .I1(1'b0), .O(wdata[13]));
  LUT2 #(.INIT(4'h6)) u_fb_14 (.I0(rdata[14]), .I1(1'b1), .O(wdata[14]));
  LUT2 #(.INIT(4'h6)) u_fb_15 (.I0(rdata[15]), .I1(1'b0), .O(wdata[15]));

  REGFILEX u_regfilex (
    .CLK(1'b0),
    .WE(1'b1),
    .WDATA(wdata),
    .RDATA(rdata)
  );

  assign y0 = n0;
  assign y1 = n1;
  assign y_bus = rdata;
endmodule
