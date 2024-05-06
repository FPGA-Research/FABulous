module config_UART #(
	parameter Mode = 0, // [0:auto|1:hex|2:bin] auto selects between ASCII-Hex and binary mode and takes a bit more logic, 
						// bin is for faster binary mode, but might not work on all machines/boards
						// auto uses the MSB in the command byte (the 8th byte in the comload header) to set the mode
						// "1//- ////" is for hex mode, "0//- ////" for bin mode
	parameter ComRate = 217 // ComRate = f_CLK / Boud_rate (e.g., 25 MHz/115200 Boud = 217)
) (
	input CLK,
	input resetn,
	input Rx,
	output reg [31:0] WriteData,
	output ComActive,
	output reg WriteStrobe,
	output [7:0] Command,
	output reg ReceiveLED
);

	//constant TimeToSendValue : integer := 16777216-1; //200000000;  
	localparam TimeToSendValue = 16777-1; //200000000;  
	//localparam CRC_InitValue = 16'b1111111111111111;
	localparam TestFileChecksum = 20'h4FB00;

	function [4:0] ASCII2HEX;
	input [7:0] ASCII;
	begin
	case (ASCII)
		8'h30: ASCII2HEX = 5'b00000;// 0
		8'h31: ASCII2HEX = 5'b00001;
		8'h32: ASCII2HEX = 5'b00010;
		8'h33: ASCII2HEX = 5'b00011;
		8'h34: ASCII2HEX = 5'b00100;
		8'h35: ASCII2HEX = 5'b00101;
		8'h36: ASCII2HEX = 5'b00110;
		8'h37: ASCII2HEX = 5'b00111;
		8'h38: ASCII2HEX = 5'b01000;
		8'h39: ASCII2HEX = 5'b01001;
		8'h41: ASCII2HEX = 5'b01010;  // A
		8'h61: ASCII2HEX = 5'b01010;  // a
		8'h42: ASCII2HEX = 5'b01011;  // B
		8'h62: ASCII2HEX = 5'b01011;  // b
		8'h43: ASCII2HEX = 5'b01100;  // C
		8'h63: ASCII2HEX = 5'b01100;  // c
		8'h44: ASCII2HEX = 5'b01101;  // D
		8'h64: ASCII2HEX = 5'b01101;  // d
		8'h45: ASCII2HEX = 5'b01110;  // E
		8'h65: ASCII2HEX = 5'b01110;  // e
		8'h46: ASCII2HEX = 5'b01111;  // F
		8'h66: ASCII2HEX = 5'b01111;  // f
		default: ASCII2HEX = 5'b10000;   // The MSB encodes if there was an unknown code -> error
	endcase
	end
	endfunction

	//typedef enum{HighNibble, LowNibble} ReceiveStateType; //systemverilog
	localparam HighNibble = 1, LowNibble = 0;
	//ReceiveStateType ReceiveState;
	reg ReceiveState;
	reg [3:0] HighReg;
	wire [4:0] HexValue; // a 1'b0 MSB indicates a valid value on [3..0]
	reg [7:0] HexData; // the received byte in hexmode mode
	reg HexWriteStrobe; // we received two hex nibles and have a result byte

	reg [11:0] ComCount;
	reg ComTick;
	//typedef enum{WaitForStartBit, DelayAfterStartBit, GetBit0, GetBit1, GetBit2, GetBit3, GetBit4, GetBit5, GetBit6, GetBit7, GetStopBit} ComStateType;
	//ComStateType ComState;
	localparam WaitForStartBit=0, DelayAfterStartBit=1, GetBit0=2, GetBit1=3, GetBit2=4, GetBit3=5, GetBit4=6, GetBit5=7, GetBit6=8, GetBit7=9, GetStopBit=10;
	reg [3:0] ComState;
	reg [7:0] ReceivedWord;
	reg RxLocal;

	//signal W0, W1, W2, W3, W4, W5, W6, W7 : std_logic_vector(7 downto 0);

	reg [23:0] ID_Reg;
	reg [31:0] Start_Reg;
	reg [15:0] Size_Reg;
	reg [15:0] CRC_Reg;
	reg [7:0] Command_Reg;
	reg [7:0] Data_Reg;

	wire [7:0] ReceivedByte;

	reg TimeToSend;
	reg [14:0] TimeToSendCounter;

	//typedef enum{Idle, GetID_00, GetID_AA, GetID_FF, GetCommand, EvalCommand, GetData} PresentType;
	//PresentType PresentState;
	localparam Idle=0, GetID_00=1, GetID_AA=2, GetID_FF=3, GetCommand=4, EvalCommand=5, GetData=6;
	reg [2:0] PresentState;

	//typedef enum{Word0, Word1, Word2, Word3} GetWordType;
	//GetWordType GetWordState;
	localparam Word0=0, Word1=1, Word2=2, Word3=3;
	reg [1:0] GetWordState;

	reg LocalWriteStrobe;

	reg ByteWriteStrobe;

	//wire [31:0] Data_Reg32;

	//wire [15:0] Word_Count;

	reg [19:0] CRCReg,b_counter;
	//wire [7:0] ReceivedWordDebug;
	reg [22:0] blink;

	always @ (posedge CLK, negedge resetn)
	begin : P_sync
		if (!resetn)
			RxLocal <= 1'b1;
		else
			RxLocal <= Rx;
	end// CLK;

	always @ (posedge CLK, negedge resetn)
	begin : P_com_en
		if (!resetn) begin
			ComCount <= 0;
			ComTick <= 0;
		end else begin
			if (ComState == WaitForStartBit) begin
				ComCount <= ComRate/2;// @ 25 MHz
				ComTick <= 1'b0;
			end else if (ComCount==0) begin
				ComCount <= ComRate;
				ComTick <= 1'b1;
			end else begin
				ComCount <= ComCount - 1;
				ComTick <= 1'b0;
			end
		end
	end

	always @ (posedge CLK, negedge resetn)
	begin : P_COM
		if (!resetn) begin
			ComState <= WaitForStartBit;
			ReceivedWord <= 8'b0;
			ID_Reg <= 24'b0;
			Start_Reg <= 32'b0;
			Command_Reg <= 8'b0;
		end else begin
			case(ComState)
			WaitForStartBit: begin
				if (RxLocal==1'b0) begin
					ComState <= DelayAfterStartBit;
					ReceivedWord <= 0;
				end
			end
			DelayAfterStartBit: begin
				if (ComTick==1'b1) begin
					ComState <= GetBit0;
				end
			end
			GetBit0: begin
				if (ComTick==1'b1) begin
					ComState <= GetBit1;
					ReceivedWord[0] <= RxLocal;
				end
			end
			GetBit1: begin
				if (ComTick==1'b1) begin
					ComState <= GetBit2;
					ReceivedWord[1] <= RxLocal;
				end
			end
			GetBit2: begin
				if (ComTick==1'b1) begin
					ComState <= GetBit3;
					ReceivedWord[2] <= RxLocal;
				end
			end
			GetBit3: begin
				if (ComTick==1'b1) begin
					ComState <= GetBit4;
					ReceivedWord[3] <= RxLocal;
				end
			end
			GetBit4: begin
				if (ComTick==1'b1) begin
					ComState <= GetBit5;
					ReceivedWord[4] <= RxLocal;
				end
			end
			GetBit5: begin
				if (ComTick==1'b1) begin
					ComState <= GetBit6;
					ReceivedWord[5] <= RxLocal;
				end
			end
			GetBit6: begin
				if (ComTick==1'b1) begin
					ComState <= GetBit7;
					ReceivedWord[6] <= RxLocal;
				end
			end
			GetBit7: begin
				if (ComTick==1'b1) begin
					ComState <= GetStopBit;
					ReceivedWord[7] <= RxLocal;
				end
			end
			GetStopBit: begin
				if (ComTick==1'b1) begin
					ComState <= WaitForStartBit;
				end
			end
			endcase
	// scan order:
	// <-to_modules_scan_in <- LSB_W0..MSB_W0 <- LSB_W1.... <- LSB_W7 <- from_modules_scan_out
	// W8(7..1)
			if (ComState==GetStopBit && ComTick==1'b1) begin
				case (PresentState)
					GetID_00: ID_Reg[23:16] <= ReceivedWord;
					GetID_AA: ID_Reg[15:8] <= ReceivedWord;
					GetID_FF: ID_Reg[7:0] <= ReceivedWord;
	//         when GetSize0 => Size_Reg(15 downto 8) <= ReceivedWord;
	//         when GetSize1 => Size_Reg(7 downto 0) <= ReceivedWord;
	//         when GetCRC_H => CRC_Reg(15 downto 8) <= ReceivedWord;
	//         when GetCRC_L => CRC_Reg(7 downto 0) <= ReceivedWord;
					GetCommand: Command_Reg <= ReceivedWord;
					GetData: Data_Reg <= ReceivedWord;
				endcase
			end
		end
	end//CLK

	always @(posedge CLK, negedge resetn)
	begin : P_FSM
		if (!resetn) begin
			PresentState <= Idle;
		end else begin
			case(PresentState)
			Idle: begin
				if (ComState==WaitForStartBit && RxLocal==1'b0) begin 
					PresentState <= GetID_00;
				end
			end
			GetID_00: begin
				if (TimeToSend==1'b1) begin 
					PresentState<=Idle;
				end else if (ComState==GetStopBit && ComTick==1'b1) begin
					PresentState <= GetID_AA;
				end
			end
			GetID_AA: begin
				if (TimeToSend==1'b1) begin
					PresentState<=Idle;
				end else if (ComState==GetStopBit && ComTick==1'b1) begin
					PresentState <= GetID_FF;
				end
			end
			GetID_FF: begin
				if (TimeToSend==1'b1) begin
					PresentState<=Idle;
				end else if (ComState==GetStopBit && ComTick==1'b1) begin 
					PresentState <= GetCommand;
				end
			end
	//		GetSize1:
	//        if TimeToSend=1'b1 begin PresentState<=Idle;
	//        elsif ComState=GetStopBit && ComTick=1'b1 begin PresentState <= GetSize0; end if;
	//		GetSize0:
	//        if TimeToSend=1'b1 begin PresentState<=Idle;
	//        elsif ComState=GetStopBit && ComTick=1'b1 begin PresentState <= GetCommand; end if;
			GetCommand: begin
				if (TimeToSend==1'b1) begin
					PresentState<=Idle;
				end else if (ComState==GetStopBit && ComTick==1'b1) begin 
					PresentState <= EvalCommand;
				end
			end
			EvalCommand: begin
				if (ID_Reg==24'h00AAFF && (Command_Reg[6:0]=={3'b000,4'h1} || Command_Reg[6:0]=={3'b000,4'h2})) begin
					PresentState <= GetData;
				end else begin
					PresentState <= Idle;
				end
			end
			GetData: begin
				if (TimeToSend==1'b1) begin 
					PresentState<=Idle; 
				end
			end
			endcase
		end
	end//CLK
	assign Command = Command_Reg;

	if (Mode==0 || Mode==1) begin : L_hexmode// mode [0:auto|1:hex|2:bin]
		assign HexValue = ASCII2HEX(ReceivedWord);
		always @ (posedge CLK, negedge resetn)
		begin
			if (!resetn) begin
				ReceiveState <= HighNibble;
				HexData <= 8'b0;
				HighReg <= 4'b0;
				HexWriteStrobe <= 1'b0;
			end else begin
				if (PresentState!=GetData) begin
					ReceiveState <= HighNibble;
				end else if (ComState==GetStopBit && ComTick==1'b1 && HexValue[4]==1'b0) begin
					if(ReceiveState==HighNibble) begin
						ReceiveState <= LowNibble;
					end
				end else begin
				  ReceiveState <= HighNibble;
				end
			//end// CLK
				if (ComState==GetStopBit && ComTick==1'b1 && HexValue[4]==1'b0) begin
					if(ReceiveState==HighNibble) begin
						HighReg <= HexValue[3:0];
						HexWriteStrobe <= 1'b0;
					end else begin// LowNibble
						HexData <= {HighReg,HexValue[3:0]};
						HexWriteStrobe <= 1'b1;
					end
				end else begin
					HexWriteStrobe <= 1'b0;
				end
			end
		end// CLK
	end

	always @(posedge CLK, negedge resetn)
	begin : P_checksum
		if (!resetn) begin
			CRCReg <= TestFileChecksum;
			b_counter <= TestFileChecksum;
			blink <= 23'b0;
		end else begin
			if (PresentState==GetCommand) begin // init before data arrives 
				CRCReg <= 0;
				b_counter <= 0;
			end else if (Mode==1 || (Mode==0 && Command_Reg[7]==1'b1)) begin // mode [0:auto|1:hex|2:bin]
				// if hex mode or if auto mode with detected hex mode in the command register
				if (ComState==GetStopBit && ComTick==1'b1 && HexValue[4]==1'b0 && PresentState==GetData && ReceiveState==LowNibble) begin
					CRCReg <= CRCReg + {HighReg,HexValue[3:0]};
					b_counter <= b_counter+1;
				end
			end else begin// binary mode
				if (ComState==GetStopBit && ComTick==1'b1 && (PresentState==GetData)) begin
					CRCReg <= CRCReg + ReceivedWord;
					b_counter <= b_counter +1;
				end
			end// checksum computation

			if (PresentState==GetData) begin
				ReceiveLED <= 1'b1; // receive process in progress
			end else if ((PresentState==Idle) && (CRCReg!=TestFileChecksum)) begin
				//ReceiveLED <= blink(blink'high);
				ReceiveLED <= blink[22];
			end else begin
				ReceiveLED <= 1'b0; // receive process was OK
			end

			blink <= blink-1;
		end
	end //CLK

	always @(posedge CLK, negedge resetn)
	begin : P_bus
		if (!resetn) begin
			LocalWriteStrobe <= 1'b0;
			ByteWriteStrobe <= 1'b0;
		end else begin
			if (PresentState==EvalCommand) begin
				LocalWriteStrobe <= 1'b0;
			end else if (PresentState==GetData && ComState==GetStopBit && ComTick==1'b1) begin
				LocalWriteStrobe <= 1'b1;
			end else begin
				LocalWriteStrobe <= 1'b0;
			end

			if (Mode==2 || (Mode==0 && Command_Reg[7]==1'b0)) begin // mode [0:auto|1:hex|2:bin]
			// if binary mode or if auto mode with detected binary mode in the command register
				ByteWriteStrobe <= LocalWriteStrobe; // delay Strobe to ensure that data is valid when applying CLK
														// should further prevent glitches in ICAP CLK
			end else begin
				ByteWriteStrobe <= HexWriteStrobe;
			end
		end
	end// CLK

	always @(posedge CLK, negedge resetn)
	begin : P_WordMode
		if (!resetn) begin
			GetWordState <= Word0;
			WriteData <= 32'b0;
			WriteStrobe <= 1'b0;
		end else begin
			if (PresentState==EvalCommand) begin
				GetWordState <= Word0;
				WriteData <= 0;
			end else begin
				case(GetWordState)
				Word0: begin
					if (ByteWriteStrobe==1'b1) begin
						WriteData[31:24] <= ReceivedByte;
						GetWordState <= Word1;
					end
				end
				Word1: begin
					if (ByteWriteStrobe==1'b1) begin
						WriteData[23:16] <= ReceivedByte;
						GetWordState <= Word2;
					end
				end
				Word2: begin
					if (ByteWriteStrobe==1'b1) begin
						WriteData[15:8] <= ReceivedByte;
						GetWordState <= Word3;
					end
				end
				Word3: begin
					if (ByteWriteStrobe==1'b1) begin
						WriteData[7:0] <= ReceivedByte;
						GetWordState <= Word0;
					end
				end
				endcase
			end

			if (ByteWriteStrobe==1'b1 && GetWordState==Word3) begin
				WriteStrobe <= 1'b1;
			end else begin
				WriteStrobe <= 1'b0;
			end
		end
	end// CLK

	//ComLoaderActive <= 1'b0;
	assign ReceivedByte = (Mode==2 || (Mode==0 && Command_Reg[7]==1'b0)) ? Data_Reg : HexData; // mode [0:auto|1:hex|2:bin]
	// if binary mode or if auto mode with detected binary mode in the command register
	// ReceivedWordDebug <= Data_Reg when (Mode="bin" OR (Mode="auto" && Command_Reg(7)=1'b0)) else HexData;
	assign ComActive = (PresentState==GetData) ? 1'b1 : 1'b0;

	always @(posedge CLK, negedge resetn)
	begin : P_TimeOut
		if (!resetn) begin
			TimeToSendCounter <= TimeToSendValue;
			TimeToSendCounter <= 1'b0;
		end else begin
			if (PresentState==Idle || ComState==GetStopBit) begin
			//Init TimeOut
				TimeToSendCounter <= TimeToSendValue;
				TimeToSend <= 1'b0;
			end else if (TimeToSendCounter>0) begin
				TimeToSendCounter <= TimeToSendCounter - 1;
				TimeToSend <= 1'b0;
			end else begin
				TimeToSendCounter <= TimeToSendCounter;
				TimeToSend <= 1'b1; // force FSM to go back to idle when inactive
			end
		end
	end//CLK

endmodule