module ConfigFSM (CLK, resetn, WriteData, WriteStrobe, FSM_Reset, FrameAddressRegister, LongFrameStrobe, RowSelect);
	parameter NumberOfRows = 16;
	parameter RowSelectWidth = 5;
	parameter FrameBitsPerRow = 32;
	parameter desync_flag = 20;

	input CLK; 
	input resetn;	

	input [31:0] WriteData;
	input WriteStrobe;
	input FSM_Reset;
	
	output reg [FrameBitsPerRow-1:0] FrameAddressRegister;
	output reg LongFrameStrobe;
	output reg [RowSelectWidth-1:0] RowSelect;
	
	reg FrameStrobe;
	//signal FrameShiftState : integer range 0 to (NumberOfRows + 2);
	reg [4:0] FrameShiftState;

	//FSM
	reg [1:0] state;
	reg old_reset;
	always @ (posedge CLK, negedge resetn) begin : P_FSM
		if (!resetn) begin
			old_reset <= 1'b0;
			state <= 2'b00;
			FrameShiftState <= 5'b00000;
			FrameAddressRegister <= 0;
			FrameStrobe <= 1'b0; 
		end else begin
			old_reset <= FSM_Reset;
			FrameStrobe <= 1'b0;
			// we only activate the configuration after detecting a 32-bit aligned pattern "x"FAB0_FAB1"
			// this allows placing the com-port header into the file and we can use the same file for parallel or UART configuration
			// this also allows us to place whatever metadata, the only point to remeber is that the pattern/file needs to be 4-byte padded in the header
			if ((old_reset == 1'b0) && (FSM_Reset == 1'b1)) begin // reset all on ComActive posedge
				state <= 0;
				FrameShiftState <= 0;
			end else begin
				case(state)
					0: begin // unsynched
						if(WriteStrobe == 1'b1) begin // if writing enabled
							if (WriteData == 32'hFAB0_FAB1) begin // fire only after seeing pattern 0xFAB0_FAB1
								state <= 1; //go to synched state
							end
						end
					end
					1: begin // SyncState read header
						if(WriteStrobe == 1'b1) begin// if writing enabled
							if(WriteData[desync_flag] == 1'b1) begin // desync
								state <= 0; //desynced
							end else begin
								FrameAddressRegister <= WriteData;
								FrameShiftState <= NumberOfRows  ;
								state <= 2; //writing frame data
							end
						end
					end
					2: begin
						if(WriteStrobe == 1'b1) begin// if writing enabled
							FrameShiftState <= FrameShiftState -1 ;
							if(FrameShiftState == 1) begin // on last frame
								FrameStrobe <= 1'b1; //trigger FrameStrobe
								state <= 1; // we go to synched state waiting for next frame or desync
							end
						end
					end
				endcase
			end
		end
	end
	
	always @ (*) begin
		if(WriteStrobe) begin // if writing active
			RowSelect = FrameShiftState; // we write the frame
		end else begin
			RowSelect = {RowSelectWidth{1'b1}}; //otherwise, we write an invalid frame
		end
	end
	
	reg oldFrameStrobe;
	always @ (posedge CLK, negedge resetn) begin : P_StrobeREG
		if (!resetn) begin
			oldFrameStrobe <= 1'b0;
			LongFrameStrobe <= 1'b0;
		end else begin
			oldFrameStrobe <= FrameStrobe;
			LongFrameStrobe <= (FrameStrobe || oldFrameStrobe);
		end
	end//CLK
	
endmodule