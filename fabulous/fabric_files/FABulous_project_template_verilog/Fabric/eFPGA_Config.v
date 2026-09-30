`default_nettype none

module eFPGA_Config #(
    parameter integer NumberOfRows = 16,
    parameter integer RowSelectWidth = 5,
    parameter integer FrameBitsPerRow = 32,
    parameter integer desync_flag = 20,
    parameter integer bitbang_enable = 1,
    parameter integer uart_enable = 1,
    parameter integer spi_enable = 0,
    parameter integer parallel_enable = 1,
    parameter integer axi_enable = 0
) (
    input wire CLK,
    input wire resetn,
    // UART configuration port
    input wire Rx,
    output wire ComActive,
    output wire ReceiveLED,
    // BitBang configuration port
    input wire s_clk,
    input wire s_data,
    // SPI configuration port
    input wire sck,
    input wire mosi,
    input wire ss_n,
    // AXI configuration port
    input wire [31:0] s_axi_awaddr, //AW
    input wire s_axi_awvalid,
    output wire s_axi_awready,
    input wire [31:0] s_axi_wdata,  // W
    input wire [3:0] s_axi_wstrb,
    input wire s_axi_wvalid,
    output wire s_axi_wready,
    output wire [1:0] s_axi_bresp,  // B
    output wire s_axi_bvalid,
    input wire s_axi_bready,
    input wire [31:0] s_axi_araddr, // AR
    input wire s_axi_arvalid,
    output wire s_axi_arready,
    output wire [31:0] s_axi_rdata, // R
    output wire [1:0] s_axi_rresp,
    output s_axi_rvalid,
    input wire s_axi_rready,
    // Parallel configuration port
    input wire [31:0] SelfWriteData,
    input wire SelfWriteStrobe,
    output wire [31:0] ConfigWriteData,
    output wire ConfigWriteStrobe,
    output wire [FrameBitsPerRow-1:0] FrameAddressRegister,
    output wire LongFrameStrobe,
    output wire [RowSelectWidth-1:0] RowSelect
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

    wire [31:0] axi_write_data;
    wire axi_strobe;
    wire [31:0] axi_write_data_mux;
    wire axi_strobe_mux;
    wire axi_active;

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

    generate
        if (axi_enable == 1) begin : gen_axi
            config_AXI INST_configAXI (
                .clk(CLK),
                .reset_n(resetn),
                .s_axi_awaddr(s_axi_awaddr),
                .s_axi_awvalid(s_axi_awvalid),
                .s_axi_awready(s_axi_awready),
                .s_axi_wdata(s_axi_wdata),
                .s_axi_wstrb(s_axi_wstrb),
                .s_axi_wvalid(s_axi_wvalid),
                .s_axi_wready(s_axi_wready),
                .s_axi_bresp(s_axi_bresp),
                .s_axi_bvalid(s_axi_bvalid),
                .s_axi_bready(s_axi_bready),
                .s_axi_araddr(s_axi_araddr),
                .s_axi_arvalid(s_axi_arvalid),
                .s_axi_arready(s_axi_arready),
                .s_axi_rdata(s_axi_rdata),
                .s_axi_rresp(s_axi_rresp),
                .s_axi_rvalid(s_axi_rvalid),
                .s_axi_rready(s_axi_rready),
                .strobe(axi_strobe),
                .data(axi_write_data),
                .active(axi_active)
            );
        end else begin : gen_no_axi
            assign axi_strobe = 1'b0;
            assign axi_write_data = 32'b0;
            assign axi_active = 1'b0;
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

    assign axi_write_data_mux = axi_active ? axi_write_data : UART_WriteData_Mux;
    assign axi_strobe_mux = axi_active ? axi_strobe : UART_WriteStrobe_Mux;

    assign ConfigWriteData = axi_write_data_mux;
    assign ConfigWriteStrobe = axi_strobe_mux;

    assign fsm_reset = UART_ComActive || BitBangActive || spi_active || axi_active;

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
        .write_data(axi_write_data_mux),
        .write_strobe(axi_strobe_mux),
        .fsm_reset(fsm_reset),
        .frame_address_register(FrameAddressRegister),
        .long_frame_strobe(LongFrameStrobe),
        .row_select(RowSelect)
    );

endmodule
`resetall
