module FABULOUS_MUX8(input I0, I1, I2, I3, I4, I5, I6, I7, S0, S1, S2, output O);
  wire A0 = S0 ? I1 : I0;
  wire A1 = S0 ? I3 : I2;
  wire A2 = S0 ? I5 : I4;
  wire A3 = S0 ? I7 : I6;
  wire B0 = S1 ? A1 : A0;
  wire B1 = S1 ? A3 : A2;
  assign O = S2 ? B1 : B0;
endmodule
