`default_nettype none

module Frame_Data_Reg #(
    parameter integer FrameBitsPerRow = 32,
    parameter integer RowSelectWidth = 5,
    parameter reg [RowSelectWidth-1:0] Row = 1
) (
    input CLK,
    input reg [FrameBitsPerRow-1:0] FrameData_I,
    output reg [FrameBitsPerRow-1:0] FrameData_O,
    input reg [RowSelectWidth-1:0] RowSelect
);

    always @(posedge CLK) begin
        if (RowSelect == Row) FrameData_O <= FrameData_I;
    end

endmodule
`default_nettype wire
