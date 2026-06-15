(* extract_order = 0 *)
module CUS_LATCH_MUX2 (
    input D,
    input SEL,
    input A,
    input B,
    output X
);
    wire q;

sg13g2_dlhq_1 latch (
    .D(D),
    .GATE(SEL),
    .Q(q)
);

sg13g2_mux2_1 mux (
    .A0(A),
    .A1(B),
    .S(q),
    .X(X)
);
endmodule



(* extract_order = 1 *)
module CUS_LATCH_MUX2_INV (
    input D,
    input SEL,
    input A,
    input B,
    output X
);
    wire q;
    wire i;

sg13g2_dlhq_1 latch (
    .D(D),
    .GATE(SEL),
    .Q(q)
);

sg13g2_mux2_1 mux (
    .A0(A),
    .A1(B),
    .S(q),
    .X(i)
);

sg13g2_inv_1 inv (
    .A(i),
    .Y(X)
);
endmodule



(* extract_order = 2 *)
module CUS_MUX2_INV (
    input A,
    input B,
    input SEL,
    output X
);

wire i;

sg13g2_mux2_1 mux (
    .A0(A),
    .A1(B),
    .S(SEL),
    .X(i)
);

sg13g2_inv_1 inv (
    .A(i),
    .Y(X)
);
endmodule



(* extract_order = 3 *)
module CUS_MUX2 (
    input A,
    input B,
    input SEL,
    output X
);

sg13g2_mux2_1 mux (
    .A0(A),
    .A1(B),
    .S(SEL),
    .X(X)
);
endmodule


(* extract_order = 4 *)
module CUS_LATCH (
    input D,
    input GATE,
    output Q
);

sg13g2_dlhq_1 latch (
    .D(D),
    .GATE(GATE),
    .Q(Q)
);

endmodule
