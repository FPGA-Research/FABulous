module FABULOUS_MUX4(input I0, I1, I2, I3, S0, S1, output O);
  wire A0 = S0 ? I1 : I0;
  wire A1 = S0 ? I3 : I2;
  assign O = S1 ? A1 : A0;
endmodule
