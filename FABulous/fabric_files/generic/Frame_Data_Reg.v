module Frame_Data_Reg (FrameData_I, FrameData_O, RowSelect, CLK);
	parameter FrameBitsPerRow = 32;
	parameter RowSelectWidth = 5;
	parameter Row = 1;
	input [FrameBitsPerRow-1:0] FrameData_I;
	output reg [FrameBitsPerRow-1:0] FrameData_O;
	input [RowSelectWidth-1:0] RowSelect;
	input CLK;
	
	always @ (posedge CLK) begin
		if (RowSelect==Row)
			FrameData_O <= FrameData_I;
	end//CLK
endmodule