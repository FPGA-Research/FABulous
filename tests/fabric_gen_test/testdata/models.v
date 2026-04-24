`default_nettype none

// Essential modules for ConfigMem RTL simulation
// Extracted from FABulous fabric models

// config_latch Latch - used in configuration memory
module config_latch (
    input D,
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
        // When E=0, Q and QN hold their previous values (latch behavior)
    end
    /* verilator lint_on LATCH */
endmodule
`default_nettype wire
