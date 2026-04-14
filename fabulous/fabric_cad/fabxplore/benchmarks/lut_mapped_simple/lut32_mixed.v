module lut32_mixed(
  input  wire a0,
  input  wire a1,
  input  wire a2,
  input  wire a3,
  input  wire a4,
  input  wire a5,
  input  wire a6,
  input  wire a7,
  input  wire a8,
  input  wire a9,
  input  wire a10,
  input  wire a11,
  output wire y0,
  output wire y1
);
  wire n0;
  wire n1;
  wire n2;
  wire n3;
  wire n4;
  wire n5;
  wire n6;
  wire n7;
  wire n8;
  wire n9;
  wire n10;
  wire n11;
  wire n12;
  wire n13;
  wire n14;
  wire n15;
  wire n16;
  wire n17;
  wire n18;
  wire n19;
  wire n20;
  wire n21;
  wire n22;
  wire n23;
  wire n24;
  wire n25;
  wire n26;
  wire n27;
  wire n28;
  wire n29;

  LUT2 #(.INIT(4'h6)) u0  (.I0(a0),  .I1(a1),  .O(n0));
  LUT3 #(.INIT(8'h96)) u1  (.I0(a2),  .I1(a3),  .I2(a4),  .O(n1));
  LUT4 #(.INIT(16'h6996)) u2  (.I0(a0),  .I1(a2),  .I2(a5),  .I3(a6),  .O(n2));
  LUT5 #(.INIT(32'hA55A3CC3)) u3  (.I0(a0),  .I1(a1),  .I2(a2),  .I3(a3),  .I4(a4),  .O(n3));
  LUT2 #(.INIT(4'h8)) u4  (.I0(n0),  .I1(a5),  .O(n4));
  LUT3 #(.INIT(8'hE8)) u5  (.I0(n1),  .I1(a6),  .I2(a7),  .O(n5));
  LUT4 #(.INIT(16'hF0CC)) u6  (.I0(n2),  .I1(n0),  .I2(a8),  .I3(a9),  .O(n6));
  LUT2 #(.INIT(4'hD)) u7  (.I0(n3),  .I1(a10), .O(n7));
  LUT3 #(.INIT(8'h53)) u8  (.I0(n4),  .I1(n5),  .I2(a11), .O(n8));
  LUT4 #(.INIT(16'h9669)) u9  (.I0(n6),  .I1(n5),  .I2(n4),  .I3(a0),  .O(n9));
  LUT2 #(.INIT(4'h7)) u10 (.I0(n7),  .I1(n8),  .O(n10));
  LUT3 #(.INIT(8'hA6)) u11 (.I0(n9),  .I1(n6),  .I2(a1),  .O(n11));
  LUT4 #(.INIT(16'h0FF0)) u12 (.I0(n10), .I1(n11), .I2(n8),  .I3(a2),  .O(n12));
  LUT2 #(.INIT(4'h2)) u13 (.I0(n12), .I1(a3),  .O(n13));
  LUT3 #(.INIT(8'hC9)) u14 (.I0(n11), .I1(n13), .I2(a4),  .O(n14));
  LUT4 #(.INIT(16'hAA96)) u15 (.I0(n14), .I1(n12), .I2(n9),  .I3(a5),  .O(n15));
  LUT2 #(.INIT(4'hB)) u16 (.I0(n15), .I1(a6),  .O(n16));
  LUT3 #(.INIT(8'h1E)) u17 (.I0(n16), .I1(n13), .I2(a7),  .O(n17));
  LUT4 #(.INIT(16'h3C5A)) u18 (.I0(n17), .I1(n15), .I2(n10), .I3(a8),  .O(n18));
  LUT5 #(.INIT(32'hC33CA55A)) u19 (.I0(n18), .I1(n17), .I2(n16), .I3(n15), .I4(a9),  .O(n19));
  LUT2 #(.INIT(4'hE)) u20 (.I0(n19), .I1(a10), .O(n20));
  LUT3 #(.INIT(8'h78)) u21 (.I0(n18), .I1(n20), .I2(a11), .O(n21));
  LUT4 #(.INIT(16'h5AA5)) u22 (.I0(n21), .I1(n17), .I2(n14), .I3(a0),  .O(n22));
  LUT2 #(.INIT(4'h9)) u23 (.I0(n22), .I1(n11), .O(n23));
  LUT3 #(.INIT(8'hD2)) u24 (.I0(n23), .I1(n21), .I2(a1),  .O(n24));
  LUT4 #(.INIT(16'hC3F0)) u25 (.I0(n24), .I1(n22), .I2(n20), .I3(a2),  .O(n25));
  LUT2 #(.INIT(4'h1)) u26 (.I0(n25), .I1(n18), .O(n26));
  LUT3 #(.INIT(8'hB4)) u27 (.I0(n26), .I1(n24), .I2(a3),  .O(n27));
  LUT4 #(.INIT(16'h96A5)) u28 (.I0(n27), .I1(n26), .I2(n25), .I3(a4),  .O(n28));
  LUT2 #(.INIT(4'h4)) u29 (.I0(n28), .I1(n27), .O(n29));
  LUT3 #(.INIT(8'h6D)) u30 (.I0(n29), .I1(n23), .I2(a5),  .O(y0));
  LUT4 #(.INIT(16'h39C6)) u31 (.I0(n29), .I1(n28), .I2(n24), .I3(a6),  .O(y1));
endmodule
