`default_nettype none

module ConfigFSM #(
    parameter integer NumberOfRows = 16,
    parameter integer RowSelectWidth = 5,
    parameter integer FrameBitsPerRow = 32,
    parameter integer desync_flag = 20  // verilog_lint: waive parameter-name-style
) (
    input CLK,
    input reset_n,
    input [31:0] WriteData,
    input WriteStrobe,
    input FSM_Reset,
    output reg [FrameBitsPerRow-1:0] FrameAddressRegister,
    output reg LongFrameStrobe,
    output reg [RowSelectWidth-1:0] RowSelect
);

    reg FrameStrobe;
    reg [4:0] row_index;

    // FSM
    // verilog_lint: waive-start explicit-parameter-storage-type
    localparam [1:0] UNSYNCED = 2'd0, SYNC_HEADER = 2'd1, WRITE_FRAME_DATA = 2'd2;
    // verilog_lint: waive-stop explicit-parameter-storage-type
    reg [1:0] state;
    reg old_reset;
    always @(posedge CLK, negedge reset_n) begin : P_FSM
        if (!reset_n) begin
            old_reset <= 1'b0;
            state <= UNSYNCED;
            row_index <= 5'b00000;
            FrameAddressRegister <= 0;
            FrameStrobe <= 1'b0;
        end else begin
            old_reset   <= FSM_Reset;
            FrameStrobe <= 1'b0;
            // Configuration activates only after detecting the 32-bit sync pattern 0xFAB0_FAB1.
            // This allows the same bitfile to be used for UART or parallel config, with arbitrary
            // metadata in the header, provided the header is 4-byte padded.
            if ((old_reset == 1'b0) && (FSM_Reset == 1'b1)) begin  // reset all on ComActive posedge
                state <= UNSYNCED;
                row_index <= 0;
            end else begin
                // verilog_lint: waive case-missing-default
                case (state)
                    UNSYNCED: begin
                        if (WriteStrobe == 1'b1) begin
                            // fire only after seeing pattern 0xFAB0_FAB1
                            if (WriteData == 32'hFAB0_FAB1) begin
                                state <= SYNC_HEADER;
                            end
                        end
                    end
                    SYNC_HEADER: begin
                        if (WriteStrobe == 1'b1) begin
                            if (WriteData[desync_flag] == 1'b1) begin
                                state <= UNSYNCED;
                            end else begin
                                FrameAddressRegister <= WriteData;
                                // Width-cast to silence WIDTHTRUNC warning
                                row_index <= 5'(NumberOfRows);
                                state <= WRITE_FRAME_DATA;
                            end
                        end
                    end
                    WRITE_FRAME_DATA: begin
                        if (WriteStrobe == 1'b1) begin
                            row_index <= row_index - 1;
                            if (row_index == 1) begin  // on last frame
                                FrameStrobe <= 1'b1;
                                state <= SYNC_HEADER;
                            end
                        end
                    end
                    default: begin
                        state <= UNSYNCED;
                    end
                endcase
            end
        end
    end

    // verilog_lint: waive always-comb
    always @(*) begin
        if (WriteStrobe) begin
            RowSelect = row_index;
        end else begin
            RowSelect = {RowSelectWidth{1'b1}};  // Invalidate the row selection when not writing
        end
    end

    reg oldFrameStrobe;
    always @(posedge CLK, negedge reset_n) begin : P_StrobeREG
        if (!reset_n) begin
            oldFrameStrobe  <= 1'b0;
            LongFrameStrobe <= 1'b0;
        end else begin
            oldFrameStrobe  <= FrameStrobe;
            LongFrameStrobe <= (FrameStrobe || oldFrameStrobe);
        end
    end

endmodule
`default_nettype wire
