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

  wire clock;

  (* keep *) Global_Clock clock_global (
    .CLK(clock)
  );

  lut32_mixed_core core (
    .a0(a0),
    .a1(a1),
    .a2(a2),
    .a3(a3),
    .a4(a4),
    .a5(a5),
    .a6(a6),
    .a7(a7),
    .a8(a8),
    .a9(a9),
    .a10(a10),
    .a11(a11),
    .y0(y0),
    .y1(y1)
  );

endmodule

module lut32_mixed_core(
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

  function lut2;
    input [3:0] init;
    input i0, i1;
    begin
      case ({i1, i0})
        2'b00: lut2 = init[0];
        2'b01: lut2 = init[1];
        2'b10: lut2 = init[2];
        2'b11: lut2 = init[3];
      endcase
    end
  endfunction

  function lut3;
    input [7:0] init;
    input i0, i1, i2;
    begin
      case ({i2, i1, i0})
        3'b000: lut3 = init[0];
        3'b001: lut3 = init[1];
        3'b010: lut3 = init[2];
        3'b011: lut3 = init[3];
        3'b100: lut3 = init[4];
        3'b101: lut3 = init[5];
        3'b110: lut3 = init[6];
        3'b111: lut3 = init[7];
      endcase
    end
  endfunction

  function lut4;
    input [15:0] init;
    input i0, i1, i2, i3;
    begin
      case ({i3, i2, i1, i0})
        4'b0000: lut4 = init[0];
        4'b0001: lut4 = init[1];
        4'b0010: lut4 = init[2];
        4'b0011: lut4 = init[3];
        4'b0100: lut4 = init[4];
        4'b0101: lut4 = init[5];
        4'b0110: lut4 = init[6];
        4'b0111: lut4 = init[7];
        4'b1000: lut4 = init[8];
        4'b1001: lut4 = init[9];
        4'b1010: lut4 = init[10];
        4'b1011: lut4 = init[11];
        4'b1100: lut4 = init[12];
        4'b1101: lut4 = init[13];
        4'b1110: lut4 = init[14];
        4'b1111: lut4 = init[15];
      endcase
    end
  endfunction

  function lut5;
    input [31:0] init;
    input i0, i1, i2, i3, i4;
    begin
      case ({i4, i3, i2, i1, i0})
        5'b00000: lut5 = init[0];
        5'b00001: lut5 = init[1];
        5'b00010: lut5 = init[2];
        5'b00011: lut5 = init[3];
        5'b00100: lut5 = init[4];
        5'b00101: lut5 = init[5];
        5'b00110: lut5 = init[6];
        5'b00111: lut5 = init[7];
        5'b01000: lut5 = init[8];
        5'b01001: lut5 = init[9];
        5'b01010: lut5 = init[10];
        5'b01011: lut5 = init[11];
        5'b01100: lut5 = init[12];
        5'b01101: lut5 = init[13];
        5'b01110: lut5 = init[14];
        5'b01111: lut5 = init[15];
        5'b10000: lut5 = init[16];
        5'b10001: lut5 = init[17];
        5'b10010: lut5 = init[18];
        5'b10011: lut5 = init[19];
        5'b10100: lut5 = init[20];
        5'b10101: lut5 = init[21];
        5'b10110: lut5 = init[22];
        5'b10111: lut5 = init[23];
        5'b11000: lut5 = init[24];
        5'b11001: lut5 = init[25];
        5'b11010: lut5 = init[26];
        5'b11011: lut5 = init[27];
        5'b11100: lut5 = init[28];
        5'b11101: lut5 = init[29];
        5'b11110: lut5 = init[30];
        5'b11111: lut5 = init[31];
      endcase
    end
  endfunction

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

  assign n0  = lut2(4'h6,           a0,  a1);
  assign n1  = lut3(8'h96,          a2,  a3,  a4);
  assign n2  = lut4(16'h6996,       a0,  a2,  a5,  a6);
  assign n3  = lut5(32'hA55A3CC3,   a0,  a1,  a2,  a3,  a4);
  assign n4  = lut2(4'h8,           n0,  a5);
  assign n5  = lut3(8'hE8,          n1,  a6,  a7);
  assign n6  = lut4(16'hF0CC,       n2,  n0,  a8,  a9);
  assign n7  = lut2(4'hD,           n3,  a10);
  assign n8  = lut3(8'h53,          n4,  n5,  a11);
  assign n9  = lut4(16'h9669,       n6,  n5,  n4,  a0);
  assign n10 = lut2(4'h7,           n7,  n8);
  assign n11 = lut3(8'hA6,          n9,  n6,  a1);
  assign n12 = lut4(16'h0FF0,       n10, n11, n8,  a2);
  assign n13 = lut2(4'h2,           n12, a3);
  assign n14 = lut3(8'hC9,          n11, n13, a4);
  assign n15 = lut4(16'hAA96,       n14, n12, n9,  a5);
  assign n16 = lut2(4'hB,           n15, a6);
  assign n17 = lut3(8'h1E,          n16, n13, a7);
  assign n18 = lut4(16'h3C5A,       n17, n15, n10, a8);
  assign n19 = lut5(32'hC33CA55A,   n18, n17, n16, n15, a9);
  assign n20 = lut2(4'hE,           n19, a10);
  assign n21 = lut3(8'h78,          n18, n20, a11);
  assign n22 = lut4(16'h5AA5,       n21, n17, n14, a0);
  assign n23 = lut2(4'h9,           n22, n11);
  assign n24 = lut3(8'hD2,          n23, n21, a1);
  assign n25 = lut4(16'hC3F0,       n24, n22, n20, a2);
  assign n26 = lut2(4'h1,           n25, n18);
  assign n27 = lut3(8'hB4,          n26, n24, a3);
  assign n28 = lut4(16'h96A5,       n27, n26, n25, a4);
  assign n29 = lut2(4'h4,           n28, n27);
  assign y0  = lut3(8'h6D,          n29, n23, a5);
  assign y1  = lut4(16'h39C6,       n29, n28, n24, a6);

endmodule
