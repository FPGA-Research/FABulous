// Models for the embedded FPGA fabric
module config_latch (
    input D,
    E,
    output reg Q,
    QN
);
  always @(*) begin
    if (E == 1'b1) begin
      Q  = D;
      QN = ~D;
    end
  end
endmodule

module my_buf (
    A,
    X
);
  input A;
  output X;
  assign X = A;
endmodule

module clk_buf (
    input  A,
    output X
);
  assign X = A;
endmodule

module cus_mux41 (
    A0,
    A1,
    A2,
    A3,
    S0,
    S0N,
    S1,
    S1N,
    X
);
  input A0;
  input A1;
  input A2;
  input A3;
  input S0;
  input S0N;
  input S1;
  input S1N;
  output X;

  wire B0 = S0 ? A1 : A0;
  wire B1 = S0 ? A3 : A2;
  assign X = S1 ? B1 : B0;
endmodule

module cus_mux21 (
    A0,
    A1,
    S,
    X
);
  input A0;
  input A1;
  input S;
  output X;

  assign X = S ? A1 : A0;
endmodule

module cus_mux81 (
    A0,
    A1,
    A2,
    A3,
    A4,
    A5,
    A6,
    A7,
    S0,
    S0N,
    S1,
    S1N,
    S2,
    S2N,
    X
);
  input A0;
  input A1;
  input A2;
  input A3;
  input A4;
  input A5;
  input A6;
  input A7;
  input S0;
  input S0N;
  input S1;
  input S1N;
  input S2;
  input S2N;
  output X;

  wire cus_mux41_out0;
  wire cus_mux41_out1;

  cus_mux41 cus_mux41_inst0 (
      .A0 (A0),
      .A1 (A1),
      .A2 (A2),
      .A3 (A3),
      .S0 (S0),
      .S0N(S0N),
      .S1 (S1),
      .S1N(S1N),
      .X  (cus_mux41_out0)
  );

  cus_mux41 cus_mux41_inst1 (
      .A0 (A4),
      .A1 (A5),
      .A2 (A6),
      .A3 (A7),
      .S0 (S0),
      .S0N(S0N),
      .S1 (S1),
      .S1N(S1N),
      .X  (cus_mux41_out1)
  );

  cus_mux21 cus_mux21_inst (
      .A0(cus_mux41_out0),
      .A1(cus_mux41_out1),
      .S (S2),
      .X (X)
  );
endmodule

module cus_mux161 (
    A0,
    A1,
    A2,
    A3,
    A4,
    A5,
    A6,
    A7,
    A8,
    A9,
    A10,
    A11,
    A12,
    A13,
    A14,
    A15,
    S0,
    S0N,
    S1,
    S1N,
    S2,
    S2N,
    S3,
    S3N,
    X
);
  input A0;
  input A1;
  input A2;
  input A3;
  input A4;
  input A5;
  input A6;
  input A7;
  input A8;
  input A9;
  input A10;
  input A11;
  input A12;
  input A13;
  input A14;
  input A15;
  input S0;
  input S0N;
  input S1;
  input S1N;
  input S2;
  input S2N;
  input S3;
  input S3N;
  output X;

  wire cus_mux41_out0;
  wire cus_mux41_out1;
  wire cus_mux41_out2;
  wire cus_mux41_out3;

  cus_mux41 cus_mux41_inst0 (
      .A0 (A0),
      .A1 (A1),
      .A2 (A2),
      .A3 (A3),
      .S0 (S0),
      .S0N(S0N),
      .S1 (S1),
      .S1N(S1N),
      .X  (cus_mux41_out0)
  );

  cus_mux41 cus_mux41_inst1 (
      .A0 (A4),
      .A1 (A5),
      .A2 (A6),
      .A3 (A7),
      .S0 (S0),
      .S0N(S0N),
      .S1 (S1),
      .S1N(S1N),
      .X  (cus_mux41_out1)
  );

  cus_mux41 cus_mux41_inst2 (
      .A0 (A8),
      .A1 (A9),
      .A2 (A10),
      .A3 (A11),
      .S0 (S0),
      .S0N(S0N),
      .S1 (S1),
      .S1N(S1N),
      .X  (cus_mux41_out2)
  );

  cus_mux41 cus_mux41_inst3 (
      .A0 (A12),
      .A1 (A13),
      .A2 (A14),
      .A3 (A15),
      .S0 (S0),
      .S0N(S0N),
      .S1 (S1),
      .S1N(S1N),
      .X  (cus_mux41_out3)
  );

  cus_mux41 cus_mux41_inst4 (
      .A0 (cus_mux41_out0),
      .A1 (cus_mux41_out1),
      .A2 (cus_mux41_out2),
      .A3 (cus_mux41_out3),
      .S0 (S2),
      .S0N(S2N),
      .S1 (S3),
      .S1N(S3N),
      .X  (X)
  );
endmodule
