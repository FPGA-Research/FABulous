`default_nettype none

// Models for the embedded FPGA fabric
module config_latch (
    input wire D,
    E,
    output reg Q,
    QN
);
    /* verilator lint_off LATCH */

    always @(*) begin
        if (E == 1'b1) begin
            Q  = D;
            QN = ~D;
        end
    end
    /* verilator lint_on LATCH */
endmodule

module my_buf (
    input  wire A,
    output wire X
);
    assign X = A;
endmodule

module clk_buf (
    input  wire A,
    output wire X
);
    assign X = A;
endmodule

module cus_mux41 (
    input  wire A0 ,
    input  wire A1 ,
    input  wire A2 ,
    input  wire A3 ,
    input  wire S0 ,
    input  wire S0N,
    input  wire S1 ,
    input  wire S1N,
    output wire X
);
    wire B0 = S0 ? A1 : A0;
    wire B1 = S0 ? A3 : A2;
    assign X = S1 ? B1 : B0;
endmodule

module cus_mux21 (
    input  wire A0,
    input  wire A1,
    input  wire S ,
    output wire X
);
    assign X = S ? A1 : A0;
endmodule

module cus_mux81 (
    input  wire A0 ,
    input  wire A1 ,
    input  wire A2 ,
    input  wire A3 ,
    input  wire A4 ,
    input  wire A5 ,
    input  wire A6 ,
    input  wire A7 ,
    input  wire S0 ,
    input  wire S0N,
    input  wire S1 ,
    input  wire S1N,
    input  wire S2 ,
    input  wire S2N,
    output wire X
);
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
    input  wire A0 ,
    input  wire A1 ,
    input  wire A2 ,
    input  wire A3 ,
    input  wire A4 ,
    input  wire A5 ,
    input  wire A6 ,
    input  wire A7 ,
    input  wire A8 ,
    input  wire A9 ,
    input  wire A10,
    input  wire A11,
    input  wire A12,
    input  wire A13,
    input  wire A14,
    input  wire A15,
    input  wire S0 ,
    input  wire S0N,
    input  wire S1 ,
    input  wire S1N,
    input  wire S2 ,
    input  wire S2N,
    input  wire S3 ,
    input  wire S3N,
    output wire X
);
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
`default_nettype wire
