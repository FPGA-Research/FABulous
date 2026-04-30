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
        parameter [11:0] ComRate = 12'd217
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


    localparam HIGH_NIBBLE = 1'b1, LOW_NIBBLE = 1'b0;
    reg ReceiveState;
    reg [3:0] high_reg;
    wire [4:0] hex_value;  // A 0 at the MSB indicates a valid value on bits [3..0]
    reg [7:0] hex_data;  // The received byte in "hex" mode
    reg hex_write_strobe;  // We received two hex nibbles and have a result byte

    reg [11:0] com_count;
    reg com_tick;

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


    reg [3:0] com_state;
    reg [7:0] received_word;
    reg rx_local;

    reg [23:0] ID_Reg;
    reg [31:0] start_reg;
    reg [15:0] size_reg;
    reg [15:0] CRC_reg;
    reg [7:0] command_reg;
    reg [7:0] data_reg;

    wire [7:0] received_byte;

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

    reg [2:0] present_state;

    localparam reg [1:0] WORD_0 = 2'd0, WORD_1 = 2'd1, WORD_2 = 2'd2, WORD_3 = 2'd3;
    reg [1:0] get_word_state;

    reg local_write_strobe;

    reg byte_write_strobe;

    reg [19:0] CRCReg, b_counter;

    reg [22:0] blink;

    always @(posedge CLK, negedge reset_n)
    begin : P_sync
        if (!reset_n)
            rx_local <= 1'b1;
        else
            rx_local <= Rx;
    end

    always @(posedge CLK, negedge reset_n)
    begin : P_com_en
        if (!reset_n)
        begin
            com_count <= 0;
            com_tick  <= 0;
        end
        else
        begin
            if (com_state == WAIT_FOR_START_BIT)
            begin
                com_count <= ComRate / 2;
                com_tick  <= 1'b0;
            end
            else if (com_count == 0)
            begin
                com_count <= ComRate;
                com_tick  <= 1'b1;
            end
            else
            begin
                com_count <= com_count - 1;
                com_tick  <= 1'b0;
            end
        end
    end

    always @(posedge CLK, negedge reset_n)
    begin : P_COM
        if (!reset_n)
        begin
            com_state <= WAIT_FOR_START_BIT;
            received_word <= 8'b0;
            ID_Reg <= 24'b0;
            start_reg <= 32'b0;
            command_reg <= 8'b0;
        end
        else
        begin
            case (com_state)
                WAIT_FOR_START_BIT:
                begin
                    if (rx_local == 1'b0)
                    begin
                        com_state <= DELAY_AFTER_START_BIT;
                        received_word <= 0;
                    end
                end
                DELAY_AFTER_START_BIT:
                begin
                    if (com_tick == 1'b1)
                    begin
                        com_state <= GET_BIT_0;
                    end
                end
                GET_BIT_0:
                begin
                    if (com_tick == 1'b1)
                    begin
                        com_state <= GET_BIT_1;
                        received_word[0] <= rx_local;
                    end
                end
                GET_BIT_1:
                begin
                    if (com_tick == 1'b1)
                    begin
                        com_state <= GET_BIT_2;
                        received_word[1] <= rx_local;
                    end
                end
                GET_BIT_2:
                begin
                    if (com_tick == 1'b1)
                    begin
                        com_state <= GET_BIT_3;
                        received_word[2] <= rx_local;
                    end
                end
                GET_BIT_3:
                begin
                    if (com_tick == 1'b1)
                    begin
                        com_state <= GET_BIT_4;
                        received_word[3] <= rx_local;
                    end
                end
                GET_BIT_4:
                begin
                    if (com_tick == 1'b1)
                    begin
                        com_state <= GET_BIT_5;
                        received_word[4] <= rx_local;
                    end
                end
                GET_BIT_5:
                begin
                    if (com_tick == 1'b1)
                    begin
                        com_state <= GET_BIT_6;
                        received_word[5] <= rx_local;
                    end
                end
                GET_BIT_6:
                begin
                    if (com_tick == 1'b1)
                    begin
                        com_state <= GET_BIT_7;
                        received_word[6] <= rx_local;
                    end
                end
                GET_BIT_7:
                begin
                    if (com_tick == 1'b1)
                    begin
                        com_state <= GET_STOP_BIT;
                        received_word[7] <= rx_local;
                    end
                end
                GET_STOP_BIT:
                begin
                    if (com_tick == 1'b1)
                    begin
                        com_state <= WAIT_FOR_START_BIT;
                    end
                end
                default:
                begin
                    com_state <= WAIT_FOR_START_BIT;
                end
            endcase
            if (com_state == GET_STOP_BIT && com_tick == 1'b1)
            begin
                case (present_state)
                    GET_ID_00:
                        ID_Reg[23:16] <= received_word;
                    GET_ID_AA:
                        ID_Reg[15:8] <= received_word;
                    GET_ID_FF:
                        ID_Reg[7:0] <= received_word;
                    GET_COMMAND:
                        command_reg <= received_word;
                    GET_DATA:
                        data_reg <= received_word;
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
            present_state <= IDLE;
        end
        else
        begin
            case (present_state)
                IDLE:
                begin
                    if (com_state == WAIT_FOR_START_BIT && rx_local == 1'b0)
                    begin
                        present_state <= GET_ID_00;
                    end
                end
                GET_ID_00:
                begin
                    if (rx_timeout == 1'b1)
                    begin
                        present_state <= IDLE;
                    end
                    else if (com_state == GET_STOP_BIT && com_tick == 1'b1)
                    begin
                        present_state <= GET_ID_AA;
                    end
                end
                GET_ID_AA:
                begin
                    if (rx_timeout == 1'b1)
                    begin
                        present_state <= IDLE;
                    end
                    else if (com_state == GET_STOP_BIT && com_tick == 1'b1)
                    begin
                        present_state <= GET_ID_FF;
                    end
                end
                GET_ID_FF:
                begin
                    if (rx_timeout == 1'b1)
                    begin
                        present_state <= IDLE;
                    end
                    else if (com_state == GET_STOP_BIT && com_tick == 1'b1)
                    begin
                        present_state <= GET_COMMAND;
                    end
                end
                GET_COMMAND:
                begin
                    if (rx_timeout == 1'b1)
                    begin
                        present_state <= IDLE;
                    end
                    else if (com_state == GET_STOP_BIT && com_tick == 1'b1)
                    begin
                        present_state <= EVAL_COMMAND;
                    end
                end
                EVAL_COMMAND:
                begin
                    if (ID_Reg==24'h00AAFF &&
                        (command_reg[6:0]=={3'b000,4'h1} ||
                        command_reg[6:0]=={3'b000,4'h2}))
                    begin
                        present_state <= GET_DATA;
                    end
                    else
                    begin
                        present_state <= IDLE;
                    end
                end
                GET_DATA:
                begin
                    if (rx_timeout == 1'b1)
                    begin
                        present_state <= IDLE;
                    end
                end
                default:
                begin
                    present_state <= IDLE;
                end
            endcase
        end
    end
    assign Command = command_reg;

    if (Mode == MODE_AUTO || Mode == MODE_HEX)
    begin : gen_L_hexmode
        assign hex_value = ASCII2HEX(received_word);
        always @(posedge CLK, negedge reset_n)
        begin
            if (!reset_n)
            begin
                ReceiveState <= HIGH_NIBBLE;
                hex_data <= 8'b0;
                high_reg <= 4'b0;
                hex_write_strobe <= 1'b0;
            end
            else
            begin
                if (present_state != GET_DATA)
                begin
                    ReceiveState <= HIGH_NIBBLE;
                end
                else if (com_state == GET_STOP_BIT && com_tick == 1'b1 && hex_value[4] == 1'b0)
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
                if (com_state == GET_STOP_BIT && com_tick == 1'b1 && hex_value[4] == 1'b0)
                begin
                    if (ReceiveState == HIGH_NIBBLE)
                    begin
                        high_reg <= hex_value[3:0];
                        hex_write_strobe <= 1'b0;
                    end
                    else
                    begin  // LOW_NIBBLE
                        hex_data <= {high_reg, hex_value[3:0]};
                        hex_write_strobe <= 1'b1;
                    end
                end
                else
                begin
                    hex_write_strobe <= 1'b0;
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
            if (present_state == GET_COMMAND)
            begin  // Init before data arrives
                CRCReg <= 0;
                b_counter <= 0;
            end
            else if (Mode == 1 || (Mode == 0 && command_reg[7] == 1'b1))
            begin
                // "hex" mode or "auto" mode with detected "hex" mode in the command
                // register
                // checksum computation
                if (com_state==GET_STOP_BIT && com_tick==1'b1 && hex_value[4]==1'b0
                        && present_state==GET_DATA && ReceiveState==LOW_NIBBLE)
                begin
                    CRCReg <= CRCReg + {{12{1'b0}}, high_reg, hex_value[3:0]};
                    b_counter <= b_counter + 1;
                end
            end
            else
            begin  // "binary" mode
                // checksum computation
                if (com_state == GET_STOP_BIT && com_tick == 1'b1 && (present_state == GET_DATA))
                begin
                    CRCReg <= CRCReg + {{12{1'b0}}, received_word};
                    b_counter <= b_counter + 1;
                end
            end

            if (present_state == GET_DATA)
            begin
                ReceiveLED <= 1'b1;  // Receive process in progress
            end
            else if ((present_state == IDLE) && (CRCReg != TEST_FILE_CHECKSUM))
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
            local_write_strobe <= 1'b0;
            byte_write_strobe  <= 1'b0;
        end
        else
        begin
            if (present_state == EVAL_COMMAND)
            begin
                local_write_strobe <= 1'b0;
            end
            else if (present_state == GET_DATA && com_state == GET_STOP_BIT && com_tick == 1'b1)
            begin
                local_write_strobe <= 1'b1;
            end
            else
            begin
                local_write_strobe <= 1'b0;
            end

            if (Mode == MODE_BIN || (Mode == MODE_AUTO && command_reg[7] == 1'b0))
            begin
                // "binary" mode or "auto" mode with detected binary mode in the
                // command register
                // Extra register stage ensures data is valid and prevents glitches on the strobe output
                byte_write_strobe <= local_write_strobe;
            end
            else
            begin
                byte_write_strobe <= hex_write_strobe;
            end
        end
    end

    always @(posedge CLK, negedge reset_n)
    begin : P_WordMode
        if (!reset_n)
        begin
            get_word_state <= WORD_0;
            WriteData <= 32'b0;
            WriteStrobe <= 1'b0;
        end
        else
        begin
            if (present_state == EVAL_COMMAND)
            begin
                get_word_state <= WORD_0;
                WriteData <= 0;
            end
            else
            begin
                case (get_word_state)
                    WORD_0:
                    begin
                        if (byte_write_strobe == 1'b1)
                        begin
                            WriteData[31:24] <= received_byte;
                            get_word_state <= WORD_1;
                        end
                    end
                    WORD_1:
                    begin
                        if (byte_write_strobe == 1'b1)
                        begin
                            WriteData[23:16] <= received_byte;
                            get_word_state <= WORD_2;
                        end
                    end
                    WORD_2:
                    begin
                        if (byte_write_strobe == 1'b1)
                        begin
                            WriteData[15:8] <= received_byte;
                            get_word_state <= WORD_3;
                        end
                    end
                    WORD_3:
                    begin
                        if (byte_write_strobe == 1'b1)
                        begin
                            WriteData[7:0] <= received_byte;
                            get_word_state   <= WORD_0;
                        end
                    end
                    default:
                    begin
                        get_word_state <= WORD_0;
                    end
                endcase
            end

            if (byte_write_strobe == 1'b1 && get_word_state == WORD_3)
            begin
                WriteStrobe <= 1'b1;
            end
            else
            begin
                WriteStrobe <= 1'b0;
            end
        end
    end

    assign received_byte = (Mode == 2 || (Mode == 0 && command_reg[7] == 1'b0)) ? data_reg : hex_data;
    // "binary" mode or "auto" mode with detected "binary" mode in the command register
    assign ComActive = (present_state == GET_DATA) ? 1'b1 : 1'b0;

    always @(posedge CLK, negedge reset_n)
    begin : P_TimeOut
        if (!reset_n)
        begin
            rx_timeout_counter <= RX_TIMEOUT_VALUE;
            rx_timeout <= 1'b0;
        end
        else
        begin
            if (present_state == IDLE || com_state == GET_STOP_BIT)
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
