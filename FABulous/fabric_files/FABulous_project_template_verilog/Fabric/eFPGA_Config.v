module eFPGA_Config (CLK, resetn, Rx, ComActive, ReceiveLED, s_clk, s_data, SelfWriteData, SelfWriteStrobe, ConfigWriteData, ConfigWriteStrobe, FrameAddressRegister, LongFrameStrobe, RowSelect);
	parameter NumberOfRows = 16;
	parameter RowSelectWidth = 5;
	parameter FrameBitsPerRow = 32;
	parameter desync_flag = 20;
	input CLK;
	input resetn;
	// UART configuration port
	input Rx;
	output ComActive;
	output ReceiveLED;
	// BitBang configuration port
	input s_clk;
	input s_data;
	// CPU configuration port
	input [32-1:0] SelfWriteData; // configuration data write port
	input SelfWriteStrobe; // must decode address and write enable
	
	output [32-1:0] ConfigWriteData;
	output ConfigWriteStrobe;
	
	output [FrameBitsPerRow-1:0] FrameAddressRegister;
	output LongFrameStrobe;
	output [RowSelectWidth-1:0] RowSelect;

	wire [7:0] Command;
	wire [31:0] UART_WriteData;
	wire UART_WriteStrobe;
	wire [31:0] UART_WriteData_Mux;
	wire UART_WriteStrobe_Mux;
	wire UART_ComActive;
	wire UART_LED;

	wire [31:0] BitBangWriteData;
	wire BitBangWriteStrobe;
	wire [31:0] BitBangWriteData_Mux;
	wire BitBangWriteStrobe_Mux;
	wire BitBangActive;
	
	wire FSM_Reset;

	config_UART INST_config_UART (
	.CLK(CLK),
	.resetn(resetn),
	.Rx(Rx),
	.WriteData(UART_WriteData),
	.ComActive(UART_ComActive),
	.WriteStrobe(UART_WriteStrobe),
	.Command(Command),
	.ReceiveLED(UART_LED)
	);
	
	//bitbang
	bitbang Inst_bitbang (
	.s_clk(s_clk),
	.s_data(s_data),
	.strobe(BitBangWriteStrobe),
	.data(BitBangWriteData),
	.active(BitBangActive),
	.clk(CLK),
	.resetn(resetn)
	);
	
	// BitBangActive is used to switch between bitbang or internal configuration port (BitBang has therefore higher priority)
	assign BitBangWriteData_Mux = BitBangActive ? BitBangWriteData : SelfWriteData;
	assign BitBangWriteStrobe_Mux = BitBangActive ? BitBangWriteStrobe : SelfWriteStrobe;	

	// ComActive is used to switch between (bitbang+internal) port or UART (UART has therefore higher priority
	assign UART_WriteData_Mux = UART_ComActive ? UART_WriteData : BitBangWriteData_Mux;
	assign UART_WriteStrobe_Mux = UART_ComActive ? UART_WriteStrobe : BitBangWriteStrobe_Mux;	
	
	assign ConfigWriteData = UART_WriteData_Mux;
	assign ConfigWriteStrobe = UART_WriteStrobe_Mux;
	
	assign FSM_Reset = UART_ComActive || BitBangActive;

	assign ComActive = UART_ComActive;
	assign ReceiveLED = UART_LED^BitBangWriteStrobe;   
	
//	wire [FrameBitsPerRow-1:0] FrameAddressRegister;
//	wire LongFrameStrobe;
//	wire [RowSelectWidth-1:0] RowSelect;
	
	ConfigFSM #(
	.NumberOfRows(NumberOfRows),
	.RowSelectWidth(RowSelectWidth),
	.FrameBitsPerRow(FrameBitsPerRow),
	.desync_flag(desync_flag)
	)
	ConfigFSM_inst
	(.CLK(CLK),
	.resetn(resetn),
	.WriteData(UART_WriteData_Mux),
	.WriteStrobe(UART_WriteStrobe_Mux),
	.FSM_Reset(FSM_Reset),
	//outputs
	.FrameAddressRegister(FrameAddressRegister),
	.LongFrameStrobe(LongFrameStrobe),
	.RowSelect(RowSelect)
	);
	
endmodule