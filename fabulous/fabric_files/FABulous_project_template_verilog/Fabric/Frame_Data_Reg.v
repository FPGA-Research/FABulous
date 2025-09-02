module Frame_Data_Reg (
    FrameData_I,
    FrameData_O,
    RowSelect,
    CLK
);
  parameter integer FrameBitsPerRow = 32;
  parameter integer RowSelectWidth = 5;
  parameter integer Row = 1;
  input reg [FrameBitsPerRow-1:0] FrameData_I;
  output reg [FrameBitsPerRow-1:0] FrameData_O;
  input reg [RowSelectWidth-1:0] RowSelect;
  input CLK;

  always @(posedge CLK) begin
    if (RowSelect == Row) FrameData_O <= FrameData_I;
  end  //CLK
endmodule
