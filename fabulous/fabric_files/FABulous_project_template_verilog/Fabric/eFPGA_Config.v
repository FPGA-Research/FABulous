`default_nettype none

module eFPGA_Config #(
    parameter integer NumberOfRows = 16,
    parameter integer RowSelectWidth = 5,
    parameter integer FrameBitsPerRow = 32,
    parameter integer desync_flag = 20,
    parameter integer bitbang_enable = 1,
    parameter integer uart_enable = 1,
    parameter integer spi_enable = 1,
    parameter integer parallel_enable = 1
) (
    input CLK,
    input resetn,
    // UART configuration port
    input Rx,
    output ComActive,
    output ReceiveLED,
    // BitBang configuration port
    input s_clk,
    input s_data,
    // SPI configuration port
    input sck,
    input mosi,
    input ss_n,
    // Parallel configuration port
    input [31:0] SelfWriteData,
    input SelfWriteStrobe,
    output [31:0] ConfigWriteData,
    output ConfigWriteStrobe,
    output [FrameBitsPerRow-1:0] FrameAddressRegister,
    output LongFrameStrobe,
    output [RowSelectWidth-1:0] RowSelect
);

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

    wire [31:0] spi_write_data;
    wire spi_strobe;
    wire [31:0] spi_write_data_mux;
    wire spi_strobe_mux;
    wire spi_active;

    wire fsm_reset;

    // UART
    generate
        if (uart_enable == 1) begin : gen_uart
            config_UART INST_config_UART (
                .CLK(CLK),
                .reset_n(resetn),
                .Rx(Rx),
                .WriteData(UART_WriteData),
                .ComActive(UART_ComActive),
                .WriteStrobe(UART_WriteStrobe),
                .Command(Command),
                .ReceiveLED(UART_LED)
            );
        end else begin : gen_no_uart
            assign UART_WriteData = 32'b0;
            assign UART_ComActive = 1'b0;
            assign UART_WriteStrobe = 1'b0;
            assign Command = 8'b0;
            assign UART_LED = 1'b0;
        end
    endgenerate

    // BitBang
    generate
        if (bitbang_enable == 1) begin : gen_bitbang
            bitbang inst_bit_bang (
                .s_clk(s_clk),
                .s_data(s_data),
                .strobe(BitBangWriteStrobe),
                .data(BitBangWriteData),
                .active(BitBangActive),
                .clk(CLK),
                .reset_n(resetn)
            );
        end else begin : gen_no_bitbang
            assign BitBangWriteData = 32'b0;
            assign BitBangWriteStrobe = 1'b0;
            assign BitBangActive = 1'b0;
        end
    endgenerate

    generate
        if (spi_enable == 1) begin : gen_spi
            config_SPI INST_config_SPI (
                .sck(sck),
                .mosi(mosi),
                .ss_n(ss_n),
                .strobe(spi_strobe),
                .data(spi_write_data),
                .active(spi_active),
                .clk(CLK),
                .reset_n(resetn)
            );
        end else begin : gen_no_spi
            assign spi_strobe = 1'b0;
            assign spi_write_data = 32'b0;
            assign spi_active = 1'b0;
        end
    endgenerate

    wire [31:0] parallel_data_gated   = (parallel_enable == 1) ? SelfWriteData : 32'b0;
    wire        parallel_strobe_gated = (parallel_enable == 1) ? SelfWriteStrobe : 1'b0;

    // Configuration port priority (highest to lowest): UART > SPI > BitBang > Parallel

    assign BitBangWriteData_Mux = BitBangActive ? BitBangWriteData : parallel_data_gated;
    assign BitBangWriteStrobe_Mux = BitBangActive ? BitBangWriteStrobe : parallel_strobe_gated;

    assign spi_write_data_mux = spi_active ? spi_write_data : BitBangWriteData_Mux;
    assign spi_strobe_mux = spi_active ? spi_strobe : BitBangWriteStrobe_Mux;

    assign UART_WriteData_Mux = UART_ComActive ? UART_WriteData : spi_write_data_mux;
    assign UART_WriteStrobe_Mux = UART_ComActive ? UART_WriteStrobe : spi_strobe_mux;

    assign ConfigWriteData = UART_WriteData_Mux;
    assign ConfigWriteStrobe = UART_WriteStrobe_Mux;

    assign fsm_reset = UART_ComActive || BitBangActive || spi_active;

    assign ComActive = UART_ComActive;
    assign ReceiveLED = UART_LED ^ BitBangWriteStrobe;

    ConfigFSM #(
        .NumberOfRows(NumberOfRows),
        .RowSelectWidth(RowSelectWidth),
        .FrameBitsPerRow(FrameBitsPerRow),
        .desync_flag(desync_flag)
    ) ConfigFSM_inst (
        .CLK(CLK),
        .reset_n(resetn),
        .write_data(UART_WriteData_Mux),
        .write_strobe(UART_WriteStrobe_Mux),
        .fsm_reset(fsm_reset),
        .frame_address_register(FrameAddressRegister),
        .long_frame_strobe(LongFrameStrobe),
        .row_select(RowSelect)
    );

endmodule
`default_nettype wire
