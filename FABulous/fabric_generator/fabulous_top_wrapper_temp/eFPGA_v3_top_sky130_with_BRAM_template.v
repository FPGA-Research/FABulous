// For caravel only
/* module eFPGA_top (
	// Wishbone Slave ports (WB MI A)
	input wb_clk_i,
	input wbs_stb_i,
	input wbs_cyc_i,
	input wbs_we_i,
	input [31:0] wbs_dat_i,
	input [31:0] wbs_adr_i,
	output [31:0] wbs_dat_o,

	// Logic Analyzer Signals
	output [6:0] la_data_out,

	// IOs
	input  [30:0] io_in,
	output [30:0] io_out,
	output [30:0] io_oeb,

	// Independent clock (on independent integer divider)
	input   user_clock2
); */

module eFPGA_top (I_top, T_top, O_top, A_config_C, B_config_C, CLK, resetn, SelfWriteStrobe, SelfWriteData, Rx, ComActive, ReceiveLED, s_clk, s_data);

	localparam include_eFPGA = 1;
	localparam NumberOfRows = 16;
	localparam NumberOfCols = 19;
	localparam FrameBitsPerRow = 32;
	localparam MaxFramesPerCol = 20;
	localparam desync_flag = 20;
	localparam FrameSelectWidth = 5;
	localparam RowSelectWidth = 5;

	// External USER ports 
	//inout [16-1:0] PAD; // these are for Dirk and go to the pad ring
	output wire [32-1:0] I_top; 
	output wire [32-1:0] T_top;
	input wire [32-1:0] O_top;
	output wire [64-1:0] A_config_C;
	output wire [64-1:0] B_config_C;

	input wire CLK; // This clock can go to the CPU (connects to the fabric LUT output flops
	input wire resetn; // active low async reset for all the config logic

	// CPU configuration port
	input wire SelfWriteStrobe; // must decode address and write enable
	input wire [32-1:0] SelfWriteData; // configuration data write port

	// UART configuration port
	input wire Rx;
	output wire ComActive;
	output wire ReceiveLED;

	// BitBang configuration port
	input wire s_clk;
	input wire s_data;

	//BlockRAM ports
	input wire [64-1:0] RAM2FAB_D;
	output wire [64-1:0] FAB2RAM_D;
	output wire [64-1:0] FAB2RAM_A;
	output wire [64-1:0] FAB2RAM_C;
	output wire [64-1:0] Config_accessC;

	// Signal declarations
	wire [(NumberOfRows*FrameBitsPerRow)-1:0] FrameRegister;
	wire [(MaxFramesPerCol*NumberOfCols)-1:0] FrameSelect;
	wire [(FrameBitsPerRow*(NumberOfRows+2))-1:0] FrameData;
	wire [FrameBitsPerRow-1:0] FrameAddressRegister;
	wire LongFrameStrobe;
	wire [31:0] LocalWriteData;
	wire LocalWriteStrobe;
	wire [RowSelectWidth-1:0] RowSelect;

// For caravel only
/* 	wire external_clock;
	wire [1:0] clk_sel;

	wire config_strobe;
	wire fabric_strobe;
	wire read_ena;
	reg [31:0] config_data;
	reg [16:0] to_fabric_ios;
	wire [15:0] from_fabric_ios;

	//latch for config_strobe
	reg latch_config_strobe = 0;
	reg config_strobe_reg1 = 0;
	reg config_strobe_reg2 = 0;
	reg config_strobe_reg3 = 0;
	wire latch_config_strobe_inverted1;
	wire latch_config_strobe_inverted2;
	always @ (*) begin
		if(config_strobe_reg2) begin
			latch_config_strobe = 0;
		end else if(latch_config_strobe_inverted2) begin
			latch_config_strobe = 0;
		end else if(wbs_stb_i && wbs_cyc_i && wbs_we_i && !wbs_stb_i && (wbs_adr_i == 32'h30000000)) begin
			latch_config_strobe = 1;
		end
	end
	//assign latch_config_strobe_inverted1 = (!latch_config_strobe);			//This are the two inverters
	sky130_fd_sc_hd__inv latch_config_strobe_inv_0 (.Y(latch_config_strobe_inverted1), .A(latch_config_strobe));
	//assign latch_config_strobe_inverted2 = (!latch_config_strobe_inverted1);
	sky130_fd_sc_hd__inv latch_config_strobe_inv_1 (.Y(latch_config_strobe_inverted2), .A(latch_config_strobe_inverted1));
	always @ (posedge CLK) begin
		config_strobe_reg1 <= latch_config_strobe;
		config_strobe_reg2 <= config_strobe_reg1;
		config_strobe_reg3 <= config_strobe_reg2;
	end
	assign config_strobe = (config_strobe_reg3 && (!config_strobe_reg2)); //posedge pulse for config strobe
	
	
	//latch for fabric_strobe
	reg latch_fabric_strobe = 0;
	reg fabric_strobe_reg1 = 0;
	reg fabric_strobe_reg2 = 0;
	reg fabric_strobe_reg3 = 0;
	wire latch_fabric_strobe_inverted1;
	wire latch_fabric_strobe_inverted2;
	
	always @ (*) begin
		if(fabric_strobe_reg2) begin
			latch_fabric_strobe = 0;
		end else if(latch_fabric_strobe_inverted2) begin
			latch_fabric_strobe = 0;
		end else if(wbs_stb_i && wbs_cyc_i && wbs_we_i && !wbs_stb_i && (wbs_adr_i == 32'h30000004)) begin
			latch_fabric_strobe = 1;
		end
	end
	//assign latch_fabric_strobe_inverted1 = (!latch_fabric_strobe);			//This are the two inverters
	sky130_fd_sc_hd__inv latch_fabric_strobe_inv_0 (.Y(latch_fabric_strobe_inverted1), .A(latch_fabric_strobe));
	//assign latch_fabric_strobe_inverted2 = (!latch_fabric_strobe_inverted1);
	sky130_fd_sc_hd__inv latch_fabric_strobe_inv_1 (.Y(latch_fabric_strobe_inverted2), .A(latch_fabric_strobe_inverted1));
	always @ (posedge CLK) begin
		fabric_strobe_reg1 <= latch_fabric_strobe;
		fabric_strobe_reg2 <= fabric_strobe_reg1;
		fabric_strobe_reg3 <= fabric_strobe_reg2;
	end
	assign fabric_strobe = (fabric_strobe_reg3 && (!fabric_strobe_reg2)); //posedge pulse for config strobe
	
	//config data register
	always @ (posedge wb_clk_i) begin
		if(wbs_stb_i && wbs_cyc_i && wbs_we_i && !wbs_stb_i && (wbs_adr_i == 32'h30000000)) begin
			config_data = wbs_dat_i;
		end
	end
	//to_fabric_ios register
	always @ (posedge wb_clk_i) begin
		if(wbs_stb_i && wbs_cyc_i && wbs_we_i && !wbs_stb_i && (wbs_adr_i == 32'h30000004)) begin
			to_fabric_ios = wbs_dat_i[16:0];
		end
	end
	
	//to_wishbone
	assign wbs_dat_o = {16'b0,from_fabric_ios};
	assign read_ena = (wbs_adr_i == 32'h30000004)? (wbs_stb_i & wbs_cyc_i & ~wbs_we_i & ~wbs_stb_i) : 1'b0;
	
	my_mux2 from_fabric_io_0  (.A0(1'b0), .A1(I_top[0]),  .S(read_ena), .X(from_fabric_ios[0]));
	my_mux2 from_fabric_io_1  (.A0(1'b0), .A1(I_top[1]),  .S(read_ena), .X(from_fabric_ios[1]));
	my_mux2 from_fabric_io_2  (.A0(1'b0), .A1(I_top[2]),  .S(read_ena), .X(from_fabric_ios[2]));
	my_mux2 from_fabric_io_3  (.A0(1'b0), .A1(I_top[3]),  .S(read_ena), .X(from_fabric_ios[3]));
	my_mux2 from_fabric_io_4  (.A0(1'b0), .A1(I_top[4]),  .S(read_ena), .X(from_fabric_ios[4]));
	my_mux2 from_fabric_io_5  (.A0(1'b0), .A1(I_top[5]),  .S(read_ena), .X(from_fabric_ios[5]));
	my_mux2 from_fabric_io_6  (.A0(1'b0), .A1(I_top[6]),  .S(read_ena), .X(from_fabric_ios[6]));
	my_mux2 from_fabric_io_7  (.A0(1'b0), .A1(I_top[7]),  .S(read_ena), .X(from_fabric_ios[7]));
	my_mux2 from_fabric_io_8  (.A0(1'b0), .A1(I_top[8]),  .S(read_ena), .X(from_fabric_ios[8]));
	my_mux2 from_fabric_io_9  (.A0(1'b0), .A1(I_top[9]),  .S(read_ena), .X(from_fabric_ios[9]));
	my_mux2 from_fabric_io_10 (.A0(1'b0), .A1(I_top[10]), .S(read_ena), .X(from_fabric_ios[10]));
	my_mux2 from_fabric_io_11 (.A0(1'b0), .A1(I_top[11]), .S(read_ena), .X(from_fabric_ios[11]));
	my_mux2 from_fabric_io_12 (.A0(1'b0), .A1(I_top[12]), .S(read_ena), .X(from_fabric_ios[12]));
	my_mux2 from_fabric_io_13 (.A0(1'b0), .A1(I_top[13]), .S(read_ena), .X(from_fabric_ios[13]));
	my_mux2 from_fabric_io_14 (.A0(1'b0), .A1(I_top[14]), .S(read_ena), .X(from_fabric_ios[14]));
	my_mux2 from_fabric_io_15 (.A0(1'b0), .A1(I_top[15]), .S(read_ena), .X(from_fabric_ios[15]));

	my_mux2 to_fabric_io_0  (.A0(io_in[7]), .A1(to_fabric_ios[0]),  .S(B_config_C[0]),  .X(O_top[0]));
	my_mux2 to_fabric_io_1  (.A0(io_in[8]), .A1(to_fabric_ios[1]),  .S(A_config_C[0]),  .X(O_top[1]));
	my_mux2 to_fabric_io_2  (.A0(io_in[9]), .A1(to_fabric_ios[2]),  .S(B_config_C[4]),  .X(O_top[2]));
	my_mux2 to_fabric_io_3  (.A0(io_in[10]), .A1(to_fabric_ios[3]),  .S(A_config_C[4]),  .X(O_top[3]));
	my_mux2 to_fabric_io_4  (.A0(io_in[11]), .A1(to_fabric_ios[4]),  .S(B_config_C[8]),  .X(O_top[4]));
	my_mux2 to_fabric_io_5  (.A0(io_in[12]), .A1(to_fabric_ios[5]),  .S(A_config_C[8]),  .X(O_top[5]));
	my_mux2 to_fabric_io_6  (.A0(io_in[13]), .A1(to_fabric_ios[6]),  .S(B_config_C[12]), .X(O_top[6]));
	my_mux2 to_fabric_io_7  (.A0(io_in[14]), .A1(to_fabric_ios[7]),  .S(A_config_C[12]), .X(O_top[7]));
	my_mux2 to_fabric_io_8  (.A0(io_in[15]), .A1(to_fabric_ios[8]),  .S(B_config_C[16]), .X(O_top[8]));
	my_mux2 to_fabric_io_9  (.A0(io_in[16]), .A1(to_fabric_ios[9]),  .S(A_config_C[16]), .X(O_top[9]));
	my_mux2 to_fabric_io_10 (.A0(io_in[17]), .A1(to_fabric_ios[10]), .S(B_config_C[20]), .X(O_top[10]));
	my_mux2 to_fabric_io_11 (.A0(io_in[18]), .A1(to_fabric_ios[11]), .S(A_config_C[20]), .X(O_top[11]));
	my_mux2 to_fabric_io_12 (.A0(io_in[19]), .A1(to_fabric_ios[12]), .S(B_config_C[24]), .X(O_top[12]));
	my_mux2 to_fabric_io_13 (.A0(io_in[20]), .A1(to_fabric_ios[13]), .S(A_config_C[24]), .X(O_top[13]));
	my_mux2 to_fabric_io_14 (.A0(io_in[21]), .A1(to_fabric_ios[14]), .S(B_config_C[28]), .X(O_top[14]));
	my_mux2 to_fabric_io_15 (.A0(io_in[22]), .A1(to_fabric_ios[15]), .S(A_config_C[28]), .X(O_top[15]));
	
	my_mux2 to_fabric_addr  (.A0(io_in[23]), .A1(to_fabric_ios[16]), .S(B_config_C[32]), .X(O_top[16]));
	
	my_mux2 to_fabric_strobe(.A0(io_in[24]), .A1(fabric_strobe),     .S(A_config_C[32]), .X(O_top[17]));

	assign external_clock = io_in[0];
	assign clk_sel = {io_in[2],io_in[1]};
	assign s_clk          = io_in[3];
	assign s_data         = io_in[4];
	assign Rx             = io_in[5];
	assign io_out[6]     = ReceiveLED;

	assign io_oeb[6:0] = 7'b0111111;
	
	assign SelfWriteStrobe = config_strobe;
	assign SelfWriteData   = config_data;

	assign CLK = clk_sel[0] ? (clk_sel[1] ? user_clock2 : wb_clk_i) : external_clock;

	assign la_data_out[6:0] = {A_config_C[39], A_config_C[31], A_config_C[16], FAB2RAM_C[45], ReceiveLED, Rx, ComActive};

	assign O_top[23:18] = io_in[30:25];
	assign io_out[30:7] = I_top;
	assign io_oeb[30:7] = T_top; */

Config Config_inst (
	.CLK(CLK),
	.resetn(resetn),
	.Rx(Rx),
	.ComActive(ComActive),
	.ReceiveLED(ReceiveLED),
	.s_clk(s_clk),
	.s_data(s_data),
	.SelfWriteData(SelfWriteData),
	.SelfWriteStrobe(SelfWriteStrobe),
	
	.ConfigWriteData(LocalWriteData),
	.ConfigWriteStrobe(LocalWriteStrobe),
	
	.FrameAddressRegister(FrameAddressRegister),
	.LongFrameStrobe(LongFrameStrobe),
	.RowSelect(RowSelect)
);


	// L: if include_eFPGA = 1 generate

