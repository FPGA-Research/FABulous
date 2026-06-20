module FLUT5_1P_2PS #(
    parameter INIT = 32'h00000000,
    parameter FF_USED = 0
)(
    input  wire I0,
    input  wire I1,
    input  wire I2,
    input  wire I3,
    input  wire I4,
    input  wire CLK,
    output wire O,
    output reg  Q0,
    output reg  Q1
);
    assign O = I0;

    always @(posedge CLK) begin
        Q0 <= O;
        Q1 <= I1;
    end
endmodule
