module FABULOUS_MUX2(input I0, I1, S0, output O);
  assign O = S0 ? I1 : I0;
endmodule
