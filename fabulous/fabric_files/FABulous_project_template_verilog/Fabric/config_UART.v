`timescale 1ps/1ps
module config_UART #(
    parameter integer Mode = 0,
    // binary mode and takes a bit more logic,
    // bin is for faster binary mode, but might not work on all machines/boards
    // auto uses the MSB in the command byte (the 8th byte in the comload header)
    // to set the mode
    // 1 is for hex mode, 0 for bin mode
    // [0:auto|1:hex|2:bin] auto selects between ASCII-Hex and binary mode and takes a bit more logic,
    // ComRate = f_CLK / Boud_rate (e.g., 25 MHz/115200 Boud = 217)
    parameter logic [11:0] ComRate = 12'd217
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

    // 25e6/1500 ~= 16666, original minus one
    localparam logic [14:0] TIME_TO_SEND_VALUE = 15'd16776;

    localparam logic [19:0] TEST_FILE_CHECKSUM = 20'h4FB00;

    function automatic [4:0] ASCII2HEX;
        input [7:0] ASCII;
        begin
            case (ASCII)
                8'h30: ASCII2HEX = 5'b00000;  // 0
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
                default:
                // The MSB encodes if there was an unknown code -> error
                ASCII2HEX = 5'b10000;
            endcase
        end
    endfunction

    localparam logic HIGH_NIBBLE = 1'b1, LOW_NIBBLE = 1'b0;
    reg ReceiveState;
    reg [3:0] HighReg;
    wire [4:0] HexValue;  // a 1'b0 MSB indicates a valid value on [3..0]
    reg [7:0] HexData;  // the received byte in hexmode mode
    reg HexWriteStrobe;  // we received two hex nibles and have a result byte

    reg [11:0] ComCount;
    reg ComTick;
    localparam logic [3:0] WAIT_FOR_START_BIT = 4'd0, DELAY_AFTER_START_BIT = 4'd1;
    localparam logic [3:0] GET_BIT_0 = 4'd2,
                           GET_BIT_1 = 4'd3,
                           GET_BIT_2 = 4'd4,
                           GET_BIT_3 = 4'd5,
                           GET_BIT_4 = 4'd6,
                           GET_BIT_5 = 4'd7,
                           GET_BIT_6 = 4'd8,
                           GET_BIT_7 = 4'd9,
                           GET_STOP_BIT = 4'd10;

    reg [3:0] ComState;
    reg [7:0] ReceivedWord;
    reg RxLocal;

    reg [23:0] ID_Reg;
    reg [31:0] Start_Reg;
    reg [15:0] Size_Reg;
    reg [15:0] CRC_Reg;
    reg [7:0] Command_Reg;
    reg [7:0] Data_Reg;

    wire [7:0] ReceivedByte;

    reg TimeToSend;
    reg [14:0] TimeToSendCounter;

    localparam reg [2:0] IDLE=3'd0,
                         GET_ID_00=3'd1,
                         GET_ID_AA=3'd2,
                         GET_ID_FF=3'd3,
                         GET_COMMAND=3'd4,
                         EVAL_COMMAND=3'd5,
                         GET_DATA=3'd6;
    reg [2:0] PresentState;

    localparam reg [1:0] WORD_0 = 2'd0, WORD_1 = 2'd1, WORD_2 = 2'd2, WORD_3 = 2'd3;
    reg [1:0] GetWordState;

    reg LocalWriteStrobe;

    reg ByteWriteStrobe;

    reg [19:0] CRCReg, b_counter;

    reg [22:0] blink;

    always @(posedge CLK, negedge resetn) begin : P_sync
        if (!resetn) RxLocal <= 1'b1;
        else RxLocal <= Rx;
    end  // CLK;

    always @(posedge CLK, negedge resetn) begin : P_com_en
        if (!resetn) begin
            ComCount <= 0;
            ComTick  <= 0;
        end else begin
            if (ComState == WAIT_FOR_START_BIT) begin
                ComCount <= ComRate / 2;  // @ 25 MHz
                ComTick  <= 1'b0;
            end else if (ComCount == 0) begin
                ComCount <= ComRate;
                ComTick  <= 1'b1;
            end else begin
                ComCount <= ComCount - 1;
                ComTick  <= 1'b0;
            end
        end
    end

    always @(posedge CLK, negedge resetn) begin : P_COM
        if (!resetn) begin
            ComState <= WAIT_FOR_START_BIT;
            ReceivedWord <= 8'b0;
            ID_Reg <= 24'b0;
            Start_Reg <= 32'b0;
            Command_Reg <= 8'b0;
        end else begin
            case (ComState)
                WAIT_FOR_START_BIT: begin
                    if (RxLocal == 1'b0) begin
                        ComState <= DELAY_AFTER_START_BIT;
                        ReceivedWord <= 0;
                    end
                end
                DELAY_AFTER_START_BIT: begin
                    if (ComTick == 1'b1) begin
                        ComState <= GET_BIT_0;
                    end
                end
                GET_BIT_0: begin
                    if (ComTick == 1'b1) begin
                        ComState <= GET_BIT_1;
                        ReceivedWord[0] <= RxLocal;
                    end
                end
                GET_BIT_1: begin
                    if (ComTick == 1'b1) begin
                        ComState <= GET_BIT_2;
                        ReceivedWord[1] <= RxLocal;
                    end
                end
                GET_BIT_2: begin
                    if (ComTick == 1'b1) begin
                        ComState <= GET_BIT_3;
                        ReceivedWord[2] <= RxLocal;
                    end
                end
                GET_BIT_3: begin
                    if (ComTick == 1'b1) begin
                        ComState <= GET_BIT_4;
                        ReceivedWord[3] <= RxLocal;
                    end
                end
                GET_BIT_4: begin
                    if (ComTick == 1'b1) begin
                        ComState <= GET_BIT_5;
                        ReceivedWord[4] <= RxLocal;
                    end
                end
                GET_BIT_5: begin
                    if (ComTick == 1'b1) begin
                        ComState <= GET_BIT_6;
                        ReceivedWord[5] <= RxLocal;
                    end
                end
                GET_BIT_6: begin
                    if (ComTick == 1'b1) begin
                        ComState <= GET_BIT_7;
                        ReceivedWord[6] <= RxLocal;
                    end
                end
                GET_BIT_7: begin
                    if (ComTick == 1'b1) begin
                        ComState <= GET_STOP_BIT;
                        ReceivedWord[7] <= RxLocal;
                    end
                end
                GET_STOP_BIT: begin
                    if (ComTick == 1'b1) begin
                        ComState <= WAIT_FOR_START_BIT;
                    end
                end
                default: begin
                    ComState <= WAIT_FOR_START_BIT;
                end
            endcase
            // scan order:
            //  <-to_modules_scan_in
            //  <- LSB_W0..MSB_W0 <- LSB_W1.... <- LSB_W7
            //  <- from_modules_scan_out
            //  W8(7..1)
            if (ComState == GET_STOP_BIT && ComTick == 1'b1) begin
                case (PresentState)
                    GET_ID_00: ID_Reg[23:16] <= ReceivedWord;
                    GET_ID_AA: ID_Reg[15:8] <= ReceivedWord;
                    GET_ID_FF: ID_Reg[7:0] <= ReceivedWord;
                    GET_COMMAND: Command_Reg <= ReceivedWord;
                    GET_DATA: Data_Reg <= ReceivedWord;
                    default: begin
                        // do nothing
                    end
                endcase
            end
        end
    end  //CLK

    always @(posedge CLK, negedge resetn) begin : P_FSM
        if (!resetn) begin
            PresentState <= IDLE;
        end else begin
            case (PresentState)
                IDLE: begin
                    if (ComState == WAIT_FOR_START_BIT && RxLocal == 1'b0) begin
                        PresentState <= GET_ID_00;
                    end
                end
                GET_ID_00: begin
                    if (TimeToSend == 1'b1) begin
                        PresentState <= IDLE;
                    end else if (ComState == GET_STOP_BIT && ComTick == 1'b1) begin
                        PresentState <= GET_ID_AA;
                    end
                end
                GET_ID_AA: begin
                    if (TimeToSend == 1'b1) begin
                        PresentState <= IDLE;
                    end else if (ComState == GET_STOP_BIT && ComTick == 1'b1) begin
                        PresentState <= GET_ID_FF;
                    end
                end
                GET_ID_FF: begin
                    if (TimeToSend == 1'b1) begin
                        PresentState <= IDLE;
                    end else if (ComState == GET_STOP_BIT && ComTick == 1'b1) begin
                        PresentState <= GET_COMMAND;
                    end
                end
                GET_COMMAND: begin
                    if (TimeToSend == 1'b1) begin
                        PresentState <= IDLE;
                    end else if (ComState == GET_STOP_BIT && ComTick == 1'b1) begin
                        PresentState <= EVAL_COMMAND;
                    end
                end
                EVAL_COMMAND: begin
                    if (ID_Reg==24'h00AAFF && (Command_Reg[6:0]=={3'b000,4'h1}
                        || Command_Reg[6:0]=={3'b000,4'h2})) begin
                        PresentState <= GET_DATA;
                    end else begin
                        PresentState <= IDLE;
                    end
                end
                GET_DATA: begin
                    if (TimeToSend == 1'b1) begin
                        PresentState <= IDLE;
                    end
                end
                default: begin
                    PresentState <= IDLE;  // reset state machine
                end
            endcase
        end
    end  //CLK
    assign Command = Command_Reg;

    if (Mode == 0 || Mode == 1) begin : gen_L_hexmode  // mode [0:auto|1:hex|2:bin]
        assign HexValue = ASCII2HEX(ReceivedWord);
        always @(posedge CLK, negedge resetn) begin
            if (!resetn) begin
                ReceiveState <= HIGH_NIBBLE;
                HexData <= 8'b0;
                HighReg <= 4'b0;
                HexWriteStrobe <= 1'b0;
            end else begin
                if (PresentState != GET_DATA) begin
                    ReceiveState <= HIGH_NIBBLE;
                end else if (ComState == GET_STOP_BIT && ComTick == 1'b1
                        && HexValue[4] == 1'b0) begin
                    if (ReceiveState == HIGH_NIBBLE) begin
                        ReceiveState <= LOW_NIBBLE;
                    end
                end else begin
                    ReceiveState <= HIGH_NIBBLE;
                end
                if (ComState == GET_STOP_BIT && ComTick == 1'b1
                    && HexValue[4] == 1'b0) begin
                    if (ReceiveState == HIGH_NIBBLE) begin
                        HighReg <= HexValue[3:0];
                        HexWriteStrobe <= 1'b0;
                    end else begin  // LOW_NIBBLE
                        HexData <= {HighReg, HexValue[3:0]};
                        HexWriteStrobe <= 1'b1;
                    end
                end else begin
                    HexWriteStrobe <= 1'b0;
                end
            end
        end  // CLK
    end

    always @(posedge CLK, negedge resetn) begin : P_checksum
        if (!resetn) begin
            CRCReg <= TEST_FILE_CHECKSUM;
            b_counter <= TEST_FILE_CHECKSUM;
            blink <= 23'b0;
        end else begin
            if (PresentState == GET_COMMAND) begin  // init before data arrives
                CRCReg <= 0;
                b_counter <= 0;
            // mode [0:auto|1:hex|2:bin]
            end else if (Mode==1 || (Mode==0 && Command_Reg[7]==1'b1)) begin
                // if hex mode or if auto mode with detected hex mode in the command
                // register
                if (ComState==GET_STOP_BIT && ComTick==1'b1 && HexValue[4]==1'b0
            && PresentState==GET_DATA && ReceiveState==LOW_NIBBLE) begin
                    CRCReg <= CRCReg + {{12{1'b0}}, HighReg, HexValue[3:0]};
                    b_counter <= b_counter + 1;
                end
            end else begin  // binary mode
                if (ComState == GET_STOP_BIT && ComTick == 1'b1
                    && (PresentState == GET_DATA)) begin
                    CRCReg <= CRCReg + {{12{1'b0}}, ReceivedWord};
                    b_counter <= b_counter + 1;
                end
            end  // checksum computation

            if (PresentState == GET_DATA) begin
                ReceiveLED <= 1'b1;  // receive process in progress
            end else if ((PresentState == IDLE) && (CRCReg != TEST_FILE_CHECKSUM)) begin
                ReceiveLED <= blink[22];
            end else begin
                ReceiveLED <= 1'b0;  // receive process was OK
            end

            blink <= blink - 1;
        end
    end  //CLK

    always @(posedge CLK, negedge resetn) begin : P_bus
        if (!resetn) begin
            LocalWriteStrobe <= 1'b0;
            ByteWriteStrobe  <= 1'b0;
        end else begin
            if (PresentState == EVAL_COMMAND) begin
                LocalWriteStrobe <= 1'b0;
            end else if (PresentState == GET_DATA && ComState == GET_STOP_BIT
                && ComTick == 1'b1) begin
                LocalWriteStrobe <= 1'b1;
            end else begin
                LocalWriteStrobe <= 1'b0;
            end

            // mode [0:auto|1:hex|2:bin]
            if (Mode == 2 || (Mode == 0 && Command_Reg[7] == 1'b0)) begin
                // if binary mode or if auto mode with detected binary mode in the
                // command register
                // delay Strobe to ensure that data is valid when applying CLK
                ByteWriteStrobe <= LocalWriteStrobe;
                // should further prevent glitches in ICAP CLK
            end else begin
                ByteWriteStrobe <= HexWriteStrobe;
            end
        end
    end  // CLK

    always @(posedge CLK, negedge resetn) begin : P_WordMode
        if (!resetn) begin
            GetWordState <= WORD_0;
            WriteData <= 32'b0;
            WriteStrobe <= 1'b0;
        end else begin
            if (PresentState == EVAL_COMMAND) begin
                GetWordState <= WORD_0;
                WriteData <= 0;
            end else begin
                case (GetWordState)
                    WORD_0: begin
                        if (ByteWriteStrobe == 1'b1) begin
                            WriteData[31:24] <= ReceivedByte;
                            GetWordState <= WORD_1;
                        end
                    end
                    WORD_1: begin
                        if (ByteWriteStrobe == 1'b1) begin
                            WriteData[23:16] <= ReceivedByte;
                            GetWordState <= WORD_2;
                        end
                    end
                    WORD_2: begin
                        if (ByteWriteStrobe == 1'b1) begin
                            WriteData[15:8] <= ReceivedByte;
                            GetWordState <= WORD_3;
                        end
                    end
                    WORD_3: begin
                        if (ByteWriteStrobe == 1'b1) begin
                            WriteData[7:0] <= ReceivedByte;
                            GetWordState   <= WORD_0;
                        end
                    end
                    default: begin
                        GetWordState <= WORD_0;  // reset state machine
                    end
                endcase
            end

            if (ByteWriteStrobe == 1'b1 && GetWordState == WORD_3) begin
                WriteStrobe <= 1'b1;
            end else begin
                WriteStrobe <= 1'b0;
            end
        end
    end  // CLK

    // mode [0:auto|1:hex|2:bin]
    assign ReceivedByte = (Mode == 2 || (Mode == 0 && Command_Reg[7] == 1'b0)) ?
                          Data_Reg : HexData;
    // if binary mode or if auto mode with detected binary mode in the command register
    assign ComActive = (PresentState == GET_DATA) ? 1'b1 : 1'b0;

    always @(posedge CLK, negedge resetn) begin : P_TimeOut
        if (!resetn) begin
            TimeToSendCounter <= TIME_TO_SEND_VALUE;
            TimeToSend <= 1'b0;
        end else begin
            if (PresentState == IDLE || ComState == GET_STOP_BIT) begin
                //Init TimeOut
                TimeToSendCounter <= TIME_TO_SEND_VALUE;
                TimeToSend <= 1'b0;
            end else if (TimeToSendCounter > 0) begin
                TimeToSendCounter <= TimeToSendCounter - 1;
                TimeToSend <= 1'b0;
            end else begin
                TimeToSendCounter <= TimeToSendCounter;
                TimeToSend <= 1'b1;  // force FSM to go back to IDLE when inactive
            end
        end
    end  //CLK

endmodule
