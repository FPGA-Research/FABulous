`default_nettype none

module config_UART #(
        parameter reg [1:0] Mode = 2'd0,
        // The default mode is "auto", which switches between "hex" and "binary" mode,
        // but takes a bit more logic.
        // Mode "bin" is the faster binary mode, but might not work on all machines/boards.
        // Mode "auto" uses the MSB in the command byte (the 8th byte in the comload header)
        // to set the mode.
        // Below is shown how the modes can be selected:
        // [0:auto|1:hex|2:bin]
        // com_rate = f_CLK / Baudrate (e.g., 25 MHz/115200 Baud = 217)
        parameter [11:0] ComRate = 12'd217  // verilog_lint: waive explicit-parameter-storage-type
    ) (
        input CLK,
        input reset_n,
        input Rx,
        output reg [31:0] WriteData,
        output ComActive,
        output reg WriteStrobe,
        output [7:0] Command,
        output reg ReceiveLED
    );

    // 25e6/1500 ~= 16666, original minus one
    localparam reg [14:0] RX_TIMEOUT_VALUE = 15'd16665;

    localparam reg [19:0] TEST_FILE_CHECKSUM = 20'h4FB00;

    localparam reg [1:0] MODE_AUTO = 2'd0;
    localparam reg [1:0] MODE_HEX = 2'd1;
    localparam reg [1:0] MODE_BIN = 2'd2;

    function automatic [4:0] ASCII2HEX;
        input [7:0] ASCII;
        begin
            case (ASCII)
                8'h30:
                    ASCII2HEX = 5'b00000;  // 0
                8'h31:
                    ASCII2HEX = 5'b00001;
                8'h32:
                    ASCII2HEX = 5'b00010;
                8'h33:
                    ASCII2HEX = 5'b00011;
                8'h34:
                    ASCII2HEX = 5'b00100;
                8'h35:
                    ASCII2HEX = 5'b00101;
                8'h36:
                    ASCII2HEX = 5'b00110;
                8'h37:
                    ASCII2HEX = 5'b00111;
                8'h38:
                    ASCII2HEX = 5'b01000;
                8'h39:
                    ASCII2HEX = 5'b01001;
                8'h41:
                    ASCII2HEX = 5'b01010;  // A
                8'h61:
                    ASCII2HEX = 5'b01010;  // a
                8'h42:
                    ASCII2HEX = 5'b01011;  // B
                8'h62:
                    ASCII2HEX = 5'b01011;  // b
                8'h43:
                    ASCII2HEX = 5'b01100;  // C
                8'h63:
                    ASCII2HEX = 5'b01100;  // c
                8'h44:
                    ASCII2HEX = 5'b01101;  // D
                8'h64:
                    ASCII2HEX = 5'b01101;  // d
                8'h45:
                    ASCII2HEX = 5'b01110;  // E
                8'h65:
                    ASCII2HEX = 5'b01110;  // e
                8'h46:
                    ASCII2HEX = 5'b01111;  // F
                8'h66:
                    ASCII2HEX = 5'b01111;  // f
                default:
                    // The MSB encodes if there was an unknown code -> error
                    ASCII2HEX = 5'b10000;
            endcase
        end
    endfunction

    // verilog_lint: waive explicit-parameter-storage-type
    localparam HIGH_NIBBLE = 1'b1, LOW_NIBBLE = 1'b0;
    reg ReceiveState;
    reg [3:0] HighReg;
    wire [4:0] HexValue;  // A 0 at the MSB indicates a valid value on bits [3..0]
    reg [7:0] HexData;  // The received byte in "hex" mode
    reg HexWriteStrobe;  // We received two hex nibbles and have a result byte

    reg [11:0] ComCount;
    reg ComTick;
    // verilog_lint: waive-start explicit-parameter-storage-type
    localparam [3:0] WAIT_FOR_START_BIT = 4'd0, DELAY_AFTER_START_BIT = 4'd1;
    localparam [3:0]
        GET_BIT_0 = 4'd2,
        GET_BIT_1 = 4'd3,
        GET_BIT_2 = 4'd4,
        GET_BIT_3 = 4'd5,
        GET_BIT_4 = 4'd6,
        GET_BIT_5 = 4'd7,
        GET_BIT_6 = 4'd8,
        GET_BIT_7 = 4'd9,
        GET_STOP_BIT = 4'd10;
    // verilog_lint: waive-stop explicit-parameter-storage-type

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

    reg rx_timeout;
    reg [14:0] rx_timeout_counter;

    localparam reg [2:0]
        IDLE=3'd0,
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

    always @(posedge CLK, negedge reset_n)
    begin : P_sync
        if (!reset_n)
            RxLocal <= 1'b1;
        else
            RxLocal <= Rx;
    end

    always @(posedge CLK, negedge reset_n)
    begin : P_com_en
        if (!reset_n)
        begin
            ComCount <= 0;
            ComTick  <= 0;
        end
        else
        begin
            if (ComState == WAIT_FOR_START_BIT)
            begin
                ComCount <= ComRate / 2;
                ComTick  <= 1'b0;
            end
            else if (ComCount == 0)
            begin
                ComCount <= ComRate;
                ComTick  <= 1'b1;
            end
            else
            begin
                ComCount <= ComCount - 1;
                ComTick  <= 1'b0;
            end
        end
    end

    always @(posedge CLK, negedge reset_n)
    begin : P_COM
        if (!reset_n)
        begin
            ComState <= WAIT_FOR_START_BIT;
            ReceivedWord <= 8'b0;
            ID_Reg <= 24'b0;
            Start_Reg <= 32'b0;
            Command_Reg <= 8'b0;
        end
        else
        begin
            case (ComState)
                WAIT_FOR_START_BIT:
                begin
                    if (RxLocal == 1'b0)
                    begin
                        ComState <= DELAY_AFTER_START_BIT;
                        ReceivedWord <= 0;
                    end
                end
                DELAY_AFTER_START_BIT:
                begin
                    if (ComTick == 1'b1)
                    begin
                        ComState <= GET_BIT_0;
                    end
                end
                GET_BIT_0:
                begin
                    if (ComTick == 1'b1)
                    begin
                        ComState <= GET_BIT_1;
                        ReceivedWord[0] <= RxLocal;
                    end
                end
                GET_BIT_1:
                begin
                    if (ComTick == 1'b1)
                    begin
                        ComState <= GET_BIT_2;
                        ReceivedWord[1] <= RxLocal;
                    end
                end
                GET_BIT_2:
                begin
                    if (ComTick == 1'b1)
                    begin
                        ComState <= GET_BIT_3;
                        ReceivedWord[2] <= RxLocal;
                    end
                end
                GET_BIT_3:
                begin
                    if (ComTick == 1'b1)
                    begin
                        ComState <= GET_BIT_4;
                        ReceivedWord[3] <= RxLocal;
                    end
                end
                GET_BIT_4:
                begin
                    if (ComTick == 1'b1)
                    begin
                        ComState <= GET_BIT_5;
                        ReceivedWord[4] <= RxLocal;
                    end
                end
                GET_BIT_5:
                begin
                    if (ComTick == 1'b1)
                    begin
                        ComState <= GET_BIT_6;
                        ReceivedWord[5] <= RxLocal;
                    end
                end
                GET_BIT_6:
                begin
                    if (ComTick == 1'b1)
                    begin
                        ComState <= GET_BIT_7;
                        ReceivedWord[6] <= RxLocal;
                    end
                end
                GET_BIT_7:
                begin
                    if (ComTick == 1'b1)
                    begin
                        ComState <= GET_STOP_BIT;
                        ReceivedWord[7] <= RxLocal;
                    end
                end
                GET_STOP_BIT:
                begin
                    if (ComTick == 1'b1)
                    begin
                        ComState <= WAIT_FOR_START_BIT;
                    end
                end
                default:
                begin
                    ComState <= WAIT_FOR_START_BIT;
                end
            endcase
            if (ComState == GET_STOP_BIT && ComTick == 1'b1)
            begin
                case (PresentState)
                    GET_ID_00:
                        ID_Reg[23:16] <= ReceivedWord;
                    GET_ID_AA:
                        ID_Reg[15:8] <= ReceivedWord;
                    GET_ID_FF:
                        ID_Reg[7:0] <= ReceivedWord;
                    GET_COMMAND:
                        Command_Reg <= ReceivedWord;
                    GET_DATA:
                        Data_Reg <= ReceivedWord;
                    default:
                    begin
                        // do nothing
                    end
                endcase
            end
        end
    end

    always @(posedge CLK, negedge reset_n)
    begin : P_FSM
        if (!reset_n)
        begin
            PresentState <= IDLE;
        end
        else
        begin
            case (PresentState)
                IDLE:
                begin
                    if (ComState == WAIT_FOR_START_BIT && RxLocal == 1'b0)
                    begin
                        PresentState <= GET_ID_00;
                    end
                end
                GET_ID_00:
                begin
                    if (rx_timeout == 1'b1)
                    begin
                        PresentState <= IDLE;
                    end
                    else if (ComState == GET_STOP_BIT && ComTick == 1'b1)
                    begin
                        PresentState <= GET_ID_AA;
                    end
                end
                GET_ID_AA:
                begin
                    if (rx_timeout == 1'b1)
                    begin
                        PresentState <= IDLE;
                    end
                    else if (ComState == GET_STOP_BIT && ComTick == 1'b1)
                    begin
                        PresentState <= GET_ID_FF;
                    end
                end
                GET_ID_FF:
                begin
                    if (rx_timeout == 1'b1)
                    begin
                        PresentState <= IDLE;
                    end
                    else if (ComState == GET_STOP_BIT && ComTick == 1'b1)
                    begin
                        PresentState <= GET_COMMAND;
                    end
                end
                GET_COMMAND:
                begin
                    if (rx_timeout == 1'b1)
                    begin
                        PresentState <= IDLE;
                    end
                    else if (ComState == GET_STOP_BIT && ComTick == 1'b1)
                    begin
                        PresentState <= EVAL_COMMAND;
                    end
                end
                EVAL_COMMAND:
                begin
                    if (ID_Reg==24'h00AAFF &&
                        (Command_Reg[6:0]=={3'b000,4'h1} ||
                        Command_Reg[6:0]=={3'b000,4'h2}))
                    begin
                        PresentState <= GET_DATA;
                    end
                    else
                    begin
                        PresentState <= IDLE;
                    end
                end
                GET_DATA:
                begin
                    if (rx_timeout == 1'b1)
                    begin
                        PresentState <= IDLE;
                    end
                end
                default:
                begin
                    PresentState <= IDLE;
                end
            endcase
        end
    end
    assign Command = Command_Reg;

    if (Mode == MODE_AUTO || Mode == MODE_HEX)
    begin : gen_L_hexmode
        assign HexValue = ASCII2HEX(ReceivedWord);
        always @(posedge CLK, negedge reset_n)
        begin
            if (!reset_n)
            begin
                ReceiveState <= HIGH_NIBBLE;
                HexData <= 8'b0;
                HighReg <= 4'b0;
                HexWriteStrobe <= 1'b0;
            end
            else
            begin
                if (PresentState != GET_DATA)
                begin
                    ReceiveState <= HIGH_NIBBLE;
                end
                else if (ComState == GET_STOP_BIT && ComTick == 1'b1 && HexValue[4] == 1'b0)
                begin
                    if (ReceiveState == HIGH_NIBBLE)
                    begin
                        ReceiveState <= LOW_NIBBLE;
                    end
                end
                else
                begin
                    ReceiveState <= HIGH_NIBBLE;
                end
                if (ComState == GET_STOP_BIT && ComTick == 1'b1 && HexValue[4] == 1'b0)
                begin
                    if (ReceiveState == HIGH_NIBBLE)
                    begin
                        HighReg <= HexValue[3:0];
                        HexWriteStrobe <= 1'b0;
                    end
                    else
                    begin  // LOW_NIBBLE
                        HexData <= {HighReg, HexValue[3:0]};
                        HexWriteStrobe <= 1'b1;
                    end
                end
                else
                begin
                    HexWriteStrobe <= 1'b0;
                end
            end
        end
    end

    always @(posedge CLK, negedge reset_n)
    begin : P_checksum
        if (!reset_n)
        begin
            CRCReg <= TEST_FILE_CHECKSUM;
            b_counter <= TEST_FILE_CHECKSUM;
            blink <= 23'b0;
        end
        else
        begin
            if (PresentState == GET_COMMAND)
            begin  // Init before data arrives
                CRCReg <= 0;
                b_counter <= 0;
            end
            else if (Mode == 1 || (Mode == 0 && Command_Reg[7] == 1'b1))
            begin
                // "hex" mode or "auto" mode with detected "hex" mode in the command
                // register
                // checksum computation
                if (ComState==GET_STOP_BIT && ComTick==1'b1 && HexValue[4]==1'b0
                        && PresentState==GET_DATA && ReceiveState==LOW_NIBBLE)
                begin
                    CRCReg <= CRCReg + {{12{1'b0}}, HighReg, HexValue[3:0]};
                    b_counter <= b_counter + 1;
                end
            end
            else
            begin  // "binary" mode
                // checksum computation
                if (ComState == GET_STOP_BIT && ComTick == 1'b1 && (PresentState == GET_DATA))
                begin
                    CRCReg <= CRCReg + {{12{1'b0}}, ReceivedWord};
                    b_counter <= b_counter + 1;
                end
            end

            if (PresentState == GET_DATA)
            begin
                ReceiveLED <= 1'b1;  // Receive process in progress
            end
            else if ((PresentState == IDLE) && (CRCReg != TEST_FILE_CHECKSUM))
            begin
                ReceiveLED <= blink[22];
            end
            else
            begin
                ReceiveLED <= 1'b0;  // Receive process was OK
            end

            blink <= blink - 1;
        end
    end

    always @(posedge CLK, negedge reset_n)
    begin : P_bus
        if (!reset_n)
        begin
            LocalWriteStrobe <= 1'b0;
            ByteWriteStrobe  <= 1'b0;
        end
        else
        begin
            if (PresentState == EVAL_COMMAND)
            begin
                LocalWriteStrobe <= 1'b0;
            end
            else if (PresentState == GET_DATA && ComState == GET_STOP_BIT && ComTick == 1'b1)
            begin
                LocalWriteStrobe <= 1'b1;
            end
            else
            begin
                LocalWriteStrobe <= 1'b0;
            end

            if (Mode == MODE_BIN || (Mode == MODE_AUTO && Command_Reg[7] == 1'b0))
            begin
                // "binary" mode or "auto" mode with detected binary mode in the
                // command register
                // Extra register stage ensures data is valid and prevents glitches on the strobe output
                ByteWriteStrobe <= LocalWriteStrobe;
            end
            else
            begin
                ByteWriteStrobe <= HexWriteStrobe;
            end
        end
    end

    always @(posedge CLK, negedge reset_n)
    begin : P_WordMode
        if (!reset_n)
        begin
            GetWordState <= WORD_0;
            WriteData <= 32'b0;
            WriteStrobe <= 1'b0;
        end
        else
        begin
            if (PresentState == EVAL_COMMAND)
            begin
                GetWordState <= WORD_0;
                WriteData <= 0;
            end
            else
            begin
                case (GetWordState)
                    WORD_0:
                    begin
                        if (ByteWriteStrobe == 1'b1)
                        begin
                            WriteData[31:24] <= ReceivedByte;
                            GetWordState <= WORD_1;
                        end
                    end
                    WORD_1:
                    begin
                        if (ByteWriteStrobe == 1'b1)
                        begin
                            WriteData[23:16] <= ReceivedByte;
                            GetWordState <= WORD_2;
                        end
                    end
                    WORD_2:
                    begin
                        if (ByteWriteStrobe == 1'b1)
                        begin
                            WriteData[15:8] <= ReceivedByte;
                            GetWordState <= WORD_3;
                        end
                    end
                    WORD_3:
                    begin
                        if (ByteWriteStrobe == 1'b1)
                        begin
                            WriteData[7:0] <= ReceivedByte;
                            GetWordState   <= WORD_0;
                        end
                    end
                    default:
                    begin
                        GetWordState <= WORD_0;
                    end
                endcase
            end

            if (ByteWriteStrobe == 1'b1 && GetWordState == WORD_3)
            begin
                WriteStrobe <= 1'b1;
            end
            else
            begin
                WriteStrobe <= 1'b0;
            end
        end
    end

    assign ReceivedByte = (Mode == 2 || (Mode == 0 && Command_Reg[7] == 1'b0)) ? Data_Reg : HexData;
    // "binary" mode or "auto" mode with detected "binary" mode in the command register
    assign ComActive = (PresentState == GET_DATA) ? 1'b1 : 1'b0;

    always @(posedge CLK, negedge reset_n)
    begin : P_TimeOut
        if (!reset_n)
        begin
            rx_timeout_counter <= RX_TIMEOUT_VALUE;
            rx_timeout <= 1'b0;
        end
        else
        begin
            if (PresentState == IDLE || ComState == GET_STOP_BIT)
            begin
                // Init timeout
                rx_timeout_counter <= RX_TIMEOUT_VALUE;
                rx_timeout <= 1'b0;
            end
            else if (rx_timeout_counter > 0)
            begin
                rx_timeout_counter <= rx_timeout_counter - 1;
                rx_timeout <= 1'b0;
            end
            else
            begin
                rx_timeout <= 1'b1;  // Force FSM to go back to IDLE when inactive
            end
        end
    end

endmodule
`default_nettype wire
