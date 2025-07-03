// Essential modules for ConfigMem RTL simulation
// Extracted from FABulous fabric models

`timescale 1ps/1ps

// LHQD1 Latch - used in configuration memory
module LHQD1 (input D, E, output reg Q, QN);
    always @(*)
    begin
        if (E == 1'b1) begin
            Q = D;
            QN = ~D;
        end
        // When E=0, Q and QN hold their previous values (latch behavior)
    end
endmodule

// Break combinational loop helper module
module break_comb_loop(input A, output X);
assign X = A;
endmodule