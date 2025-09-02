`default_nettype none

// Models for the embedded FPGA fabric
module config_latch (
    input D,
    E,
    output reg Q,
    QN
);
    /* verilator lint_off LATCH */

    always @(*) begin
        if (E == 1'b1) begin
            Q  = D;
            QN = ~D;
        end
    end
    /* verilator lint_on LATCH */
endmodule
`default_nettype wire

module my_buf (
    input  A,
    output X
);
    assign X = A;
endmodule

module clk_buf (
    input  A,
    output X
);
    assign X = A;
endmodule

module cus_mux41 (
    input  A0,
    input  A1,
    input  A2,
    input  A3,
    input  S0,
    input  S0N,
    input  S1,
    input  S1N,
    output X
);
    wire B0 = S0 ? A1 : A0;
    wire B1 = S0 ? A3 : A2;
    assign X = S1 ? B1 : B0;
endmodule

module cus_mux21 (
    input  A0,
    input  A1,
    input  S,
    output X
);
    assign X = S ? A1 : A0;
endmodule

module cus_mux81 (
    input  A0,
    input  A1,
    input  A2,
    input  A3,
    input  A4,
    input  A5,
    input  A6,
    input  A7,
    input  S0,
    input  S0N,
    input  S1,
    input  S1N,
    input  S2,
    input  S2N,
    output X
);
    wire cus_mux41_out0;
    wire cus_mux41_out1;

    cus_mux41 cus_mux41_inst0 (
        .A0 (A0),
        .A1 (A1),
        .A2 (A2),
        .A3 (A3),
        .S0 (S0),
        .S0N(S0N),
        .S1 (S1),
        .S1N(S1N),
        .X  (cus_mux41_out0)
    );

    cus_mux41 cus_mux41_inst1 (
        .A0 (A4),
        .A1 (A5),
        .A2 (A6),
        .A3 (A7),
        .S0 (S0),
        .S0N(S0N),
        .S1 (S1),
        .S1N(S1N),
        .X  (cus_mux41_out1)
    );

    cus_mux21 cus_mux21_inst (
        .A0(cus_mux41_out0),
        .A1(cus_mux41_out1),
        .S (S2),
        .X (X)
    );
endmodule

module cus_mux161 (
    input  A0,
    input  A1,
    input  A2,
    input  A3,
    input  A4,
    input  A5,
    input  A6,
    input  A7,
    input  A8,
    input  A9,
    input  A10,
    input  A11,
    input  A12,
    input  A13,
    input  A14,
    input  A15,
    input  S0,
    input  S0N,
    input  S1,
    input  S1N,
    input  S2,
    input  S2N,
    input  S3,
    input  S3N,
    output X
);
    wire cus_mux41_out0;
    wire cus_mux41_out1;
    wire cus_mux41_out2;
    wire cus_mux41_out3;

    cus_mux41 cus_mux41_inst0 (
        .A0 (A0),
        .A1 (A1),
        .A2 (A2),
        .A3 (A3),
        .S0 (S0),
        .S0N(S0N),
        .S1 (S1),
        .S1N(S1N),
        .X  (cus_mux41_out0)
    );

    cus_mux41 cus_mux41_inst1 (
        .A0 (A4),
        .A1 (A5),
        .A2 (A6),
        .A3 (A7),
        .S0 (S0),
        .S0N(S0N),
        .S1 (S1),
        .S1N(S1N),
        .X  (cus_mux41_out1)
    );

    cus_mux41 cus_mux41_inst2 (
        .A0 (A8),
        .A1 (A9),
        .A2 (A10),
        .A3 (A11),
        .S0 (S0),
        .S0N(S0N),
        .S1 (S1),
        .S1N(S1N),
        .X  (cus_mux41_out2)
    );

    cus_mux41 cus_mux41_inst3 (
        .A0 (A12),
        .A1 (A13),
        .A2 (A14),
        .A3 (A15),
        .S0 (S0),
        .S0N(S0N),
        .S1 (S1),
        .S1N(S1N),
        .X  (cus_mux41_out3)
    );

    cus_mux41 cus_mux41_inst4 (
        .A0 (cus_mux41_out0),
        .A1 (cus_mux41_out1),
        .A2 (cus_mux41_out2),
        .A3 (cus_mux41_out3),
        .S0 (S2),
        .S0N(S2N),
        .S1 (S3),
        .S1N(S3N),
        .X  (X)
    );
endmodule

// Sky130 SRAM 1RW1R 32x256x8 simulation model
module sram_1rw1r_32_256_8_sky130(
// Port 0: RW
    clk0,csb0,web0,wmask0,addr0,din0,dout0,
// Port 1: R
    clk1,csb1,addr1,dout1
);

  parameter NUM_WMASKS = 4 ;
  parameter DATA_WIDTH = 32 ;
  parameter ADDR_WIDTH = 8 ;
  parameter RAM_DEPTH = 1 << ADDR_WIDTH;
  // FIXME: This delay is arbitrary.
  parameter DELAY = 3 ;

  input  clk0; // clock
  input   csb0; // active low chip select
  input  web0; // active low write control
  input [NUM_WMASKS-1:0]   wmask0; // write mask
  input [ADDR_WIDTH-1:0]  addr0;
  input [DATA_WIDTH-1:0]  din0;
  output [DATA_WIDTH-1:0] dout0;
  input  clk1; // clock
  input   csb1; // active low chip select
  input [ADDR_WIDTH-1:0]  addr1;
  output [DATA_WIDTH-1:0] dout1;

  reg  csb0_reg;
  reg  web0_reg;
  reg [NUM_WMASKS-1:0]   wmask0_reg;
  reg [ADDR_WIDTH-1:0]  addr0_reg;
  reg [DATA_WIDTH-1:0]  din0_reg;
  reg [DATA_WIDTH-1:0]  dout0;

  // All inputs are registers
  always @(posedge clk0)
  begin
    csb0_reg = csb0;
    web0_reg = web0;
    wmask0_reg = wmask0;
    addr0_reg = addr0;
    din0_reg = din0;
    dout0 = 32'bx;
  end

  reg  csb1_reg;
  reg [ADDR_WIDTH-1:0]  addr1_reg;
  reg [DATA_WIDTH-1:0]  dout1;

  // All inputs are registers
  always @(posedge clk1)
  begin
    csb1_reg = csb1;
    addr1_reg = addr1;
    dout1 = 32'bx;
  end

reg [DATA_WIDTH-1:0]    mem [0:RAM_DEPTH-1];

  // Memory Write Block Port 0
  // Write Operation : When web0 = 0, csb0 = 0
  always @ (negedge clk0)
  begin : MEM_WRITE0
    if ( !csb0_reg && !web0_reg ) begin
        if (wmask0_reg[0])
                mem[addr0_reg][7:0] = din0_reg[7:0];
        if (wmask0_reg[1])
                mem[addr0_reg][15:8] = din0_reg[15:8];
        if (wmask0_reg[2])
                mem[addr0_reg][23:16] = din0_reg[23:16];
        if (wmask0_reg[3])
                mem[addr0_reg][31:24] = din0_reg[31:24];
    end
  end

  // Memory Read Block Port 0
  // Read Operation : When web0 = 1, csb0 = 0
  always @ (negedge clk0)
  begin : MEM_READ0
    if (!csb0_reg && web0_reg)
       dout0 <= #(DELAY) mem[addr0_reg];
  end

  // Memory Read Block Port 1
  // Read Operation : When web1 = 1, csb1 = 0
  always @ (negedge clk1)
  begin : MEM_READ1
    if (!csb1_reg)
       dout1 <= #(DELAY) mem[addr1_reg];
  end

endmodule
