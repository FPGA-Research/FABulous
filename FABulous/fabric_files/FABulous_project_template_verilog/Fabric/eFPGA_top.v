// Minimal stub of eFPGA_top for linting purposes under Verilator.
// This provides only the interface expected by the testbench.
`timescale 1ps/1ps

module eFPGA_top (
    input  wire        CLK,
    input  wire        resetn,
    input  wire        SelfWriteStrobe,
    input  wire [31:0] SelfWriteData,
    input  wire        Rx,
    input  wire        s_clk,
    input  wire        s_data,
    input  wire [27:0] O_top,
    output wire [27:0] I_top,
    output wire [27:0] T_top,
    output wire [55:0] A_config_C,
    output wire [55:0] B_config_C,
    output wire        ComActive,
    output wire        ReceiveLED
);

    // Tie-offs for linting; no functional behavior is modeled here.
    assign I_top      = 28'b0;
    assign T_top      = 28'b0;
    assign A_config_C = 56'b0;
    assign B_config_C = 56'b0;
    assign ComActive  = 1'b0;
    assign ReceiveLED = 1'b0;

endmodule
