module mux4 (
    input        clk,
    input        rst,   // synchronous active-high reset
    input        en,    // register enable
    input  [3:0] data,
    input  [1:0] sel,
    output       out,
    output reg   out_reg
);
    assign out = data[sel];

    always @(posedge clk) begin
        if (rst)
            out_reg <= 1'b0;
        else if (en)
            out_reg <= out;
    end
endmodule

// same functional mux, but arbitrary wrapper input naming/order

// dlhq_to_mux4_select_extract_map.v
//
// Matches:
//
//   sg13g2_dlhq_1.Q -> sg13g2_mux4_1.S0
//   sg13g2_dlhq_1.Q -> sg13g2_mux4_1.S1

(* extract_order = 0 *)
module DLHQ_MUX4_S0 (
    input D,
    input GATE,
    input A0,
    input A1,
    input A2,
    input A3,
    input S1,
    output X
);
    wire q;

    sg13g2_dlhq_1 latch (
        .D(D),
        .GATE(GATE),
        .Q(q)
    );

    sg13g2_mux4_1 mux (
        .A0(A0),
        .A1(A1),
        .A2(A2),
        .A3(A3),
        .S0(q),
        .S1(S1),
        .X(X)
    );
endmodule


(* extract_order = 1 *)
module DLHQ_MUX4_S1 (
    input D,
    input GATE,
    input A0,
    input A1,
    input A2,
    input A3,
    input S0,
    output X
);
    wire q;

    sg13g2_dlhq_1 latch (
        .D(D),
        .GATE(GATE),
        .Q(q)
    );

    sg13g2_mux4_1 mux (
        .A0(A0),
        .A1(A1),
        .A2(A2),
        .A3(A3),
        .S0(S0),
        .S1(q),
        .X(X)
    );
endmodule
