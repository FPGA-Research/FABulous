module BlockRAM_1KB #(
    // Default 24 means bits wr_data[25:24] will become bits [9:8] of read address
    parameter integer READ_ADDRESS_MSB_FROM_DATA_LSB = 24,
    // Default 16 means bits wr_data[17:16] will become bits [9:8] of write address
    parameter integer WRITE_ADDRESS_MSB_FROM_DATA_LSB = 16,
    // Default 20 means bit wr_data[20] will become the dynamic writeEnable input
    parameter integer WRITE_ENABLE_FROM_DATA = 20
) (
    input clk,
    input [7:0] rd_addr,
    output [31:0] rd_data,
    input [7:0] wr_addr,
    input [31:0] wr_data,
    // Configuration bit inputs
    input C0,
    input C1,  // C0,C1 select write port width
    input C2,  // C2,C3 select read port width
    input C3,
    input C4,  // C4 selects the always_write_enable
    input C5  // C5 selects register bypass
);
  // NOTE: the read enable is currently constantly ON
  // NOTE: the R/W port on the standard cell is used only in write mode
  // NOTE: enable ports on the primitive RAM are active lows
  wire [1:0] rd_port_configuration;
  wire [1:0] wr_port_configuration;
  wire optional_register_enabled_configuration;
  wire always_write_enable;
  assign wr_port_configuration = {C0, C1};
  assign rd_port_configuration = {C2, C3};
  assign always_write_enable = C4;
  assign optional_register_enabled_configuration = C5;

  reg mem_write_enable;
  // verilog_lint: waive always-comb
  always @(*) begin
    if (always_write_enable) begin
      mem_write_enable = 0;  // This RAM primitive is active-low.
    end else begin
      // Inverting the bit to make it active-high
      mem_write_enable = (!(wr_data[WRITE_ENABLE_FROM_DATA]));
    end
  end
  reg  [ 3:0] mem_wr_mask;
  reg  [31:0] muxed_data_in;

  wire [ 1:0] wr_addr_topbits;
  // verilog_lint: waive-start line-length
  assign wr_addr_topbits = wr_data[WRITE_ADDRESS_MSB_FROM_DATA_LSB+1:WRITE_ADDRESS_MSB_FROM_DATA_LSB];
  // verilog_lint: waive-stop line-length
  // Write port config -> mask + write data multiplex
  // verilog_lint: waive always-comb
  always @(*) begin
    muxed_data_in = 32'd0;
    if (wr_port_configuration == 0) begin
      mem_wr_mask   = 4'b1111;
      muxed_data_in = wr_data;
    end else if (wr_port_configuration == 1) begin
      if (wr_addr_topbits == 0) begin
        mem_wr_mask = 4'b0011;
        muxed_data_in[15:0] = wr_data[15:0];
      end else begin
        mem_wr_mask = 4'b1100;
        muxed_data_in[31:16] = wr_data[15:0];
      end
    end else if (wr_port_configuration == 2) begin
      if (wr_addr_topbits == 0) begin
        mem_wr_mask = 4'b0001;
        muxed_data_in[7:0] = wr_data[7:0];
      end else if (wr_addr_topbits == 1) begin
        mem_wr_mask = 4'b0010;
        muxed_data_in[15:8] = wr_data[7:0];
      end else if (wr_addr_topbits == 2) begin
        mem_wr_mask = 4'b0100;
        muxed_data_in[23:16] = wr_data[7:0];
      end else begin
        mem_wr_mask = 4'b1000;
        muxed_data_in[31:24] = wr_data[7:0];
      end
    end else begin
      mem_wr_mask = 4'b0000;
    end
  end
  wire [31:0] mem_dout;
  sram_1rw1r_32_256_8_sky130 memory_cell (
      .clk0(clk),
      .csb0(mem_write_enable),
      .web0(mem_write_enable),
      .wmask0(mem_wr_mask),
      .addr0(wr_addr[7:0]),
      .din0(muxed_data_in),
      /* verilator lint_off PINCONNECTEMPTY */
      .dout0(),  // Use separate ports for reading and writing
      /* verilator lint_on PINCONNECTEMPTY */
      .clk1(clk),
      .csb1(1'b0),
      .addr1(rd_addr[7:0]),
      .dout1(mem_dout)
  );
  reg [1:0] rd_dout_sel;
  always @(posedge clk) begin
    rd_dout_sel <= wr_data[READ_ADDRESS_MSB_FROM_DATA_LSB+1:READ_ADDRESS_MSB_FROM_DATA_LSB];
  end
  reg [31:0] rd_dout_muxed;
  // verilog_lint: waive always-comb
  always @(*) begin
    rd_dout_muxed[31:0] = mem_dout[31:0];
    if (rd_port_configuration == 0) begin
      rd_dout_muxed[31:0] = mem_dout[31:0];
    end else if (rd_port_configuration == 1) begin
      if (rd_dout_sel[0] == 0) begin
        rd_dout_muxed[15:0] = mem_dout[15:0];
      end else begin
        rd_dout_muxed[15:0] = mem_dout[31:16];
      end
    end else if (rd_port_configuration == 2) begin
      if (rd_dout_sel == 0) begin
        rd_dout_muxed[7:0] = mem_dout[7:0];
      end else if (rd_dout_sel == 1) begin
        rd_dout_muxed[7:0] = mem_dout[15:8];
      end else if (rd_dout_sel == 2) begin
        rd_dout_muxed[7:0] = mem_dout[23:16];
      end else begin
        rd_dout_muxed[7:0] = mem_dout[31:24];
      end
    end else begin
      rd_dout_muxed = mem_dout;
    end
  end
  reg [31:0] rd_dout_additional_register;
  always @(posedge clk) begin
    rd_dout_additional_register <= rd_dout_muxed;
  end
  reg [31:0] final_dout;
  assign rd_data = final_dout;
  // verilog_lint: waive always-comb
  always @(*) begin
    if (optional_register_enabled_configuration) begin
      final_dout = rd_dout_additional_register;
    end else begin
      final_dout = rd_dout_muxed;
    end
  end
endmodule


(* blackbox *)
module sram_1rw1r_32_256_8_sky130 #(
    parameter integer NUM_WMASKS = 4,
    parameter integer DATA_WIDTH = 32,
    parameter integer ADDR_WIDTH = 8,
    parameter integer RAM_DEPTH = 1 << ADDR_WIDTH,
    // FIXME: This delay is arbitrary.
    parameter integer DELAY = 3
) (
    // Port 0: RW
    input clk0,  // clock
    input csb0,  // active low chip select
    input web0,  // active low write control
    input [NUM_WMASKS-1:0] wmask0,  // write mask
    input [ADDR_WIDTH-1:0] addr0,
    input [DATA_WIDTH-1:0] din0,
    output [DATA_WIDTH-1:0] dout0,
    // Port 1: R
    input clk1,  // clock
    input csb1,  // active low chip select
    input [ADDR_WIDTH-1:0] addr1,
    output [DATA_WIDTH-1:0] dout1
);
endmodule
