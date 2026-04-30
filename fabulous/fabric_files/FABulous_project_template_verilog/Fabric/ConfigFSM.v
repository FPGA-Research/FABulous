`default_nettype none

module ConfigFSM #(
    parameter integer NumberOfRows = 16,
    parameter integer RowSelectWidth = 5,
    parameter integer FrameBitsPerRow = 32,
    parameter integer desync_flag = 20
) (
    input CLK,
    input reset_n,
    input [31:0] write_data,
    input write_strobe,
    input fsm_reset,
    output reg [FrameBitsPerRow-1:0] frame_address_register,
    output reg long_frame_strobe,
    output reg [RowSelectWidth-1:0] row_select
);

    reg frame_strobe;
    reg [4:0] row_index;

    // FSM

    localparam [1:0] UNSYNCED = 2'd0, SYNC_HEADER = 2'd1, WRITE_FRAME_DATA = 2'd2;
    localparam [31:0] SYNC_HEADER_PATTERN = 32'hFAB0_FAB1;

    reg [1:0] state;
    reg old_reset;
    always @(posedge CLK, negedge reset_n) begin : P_FSM
        if (!reset_n) begin
            old_reset <= 1'b0;
            state <= UNSYNCED;
            row_index <= 5'b00000;
            frame_address_register <= 0;
            frame_strobe <= 1'b0;
        end else begin
            old_reset <= fsm_reset;
            frame_strobe <= 1'b0;
            // Configuration activates only after detecting the 32-bit sync pattern 0xFAB0_FAB1.
            // This allows the same bitfile to be used for UART or parallel config, with arbitrary
            // metadata in the header, provided the header is 4-byte padded.
            if ((old_reset == 1'b0) && (fsm_reset == 1'b1)) begin
                state <= UNSYNCED;
                row_index <= 0;
            end else begin

                case (state)
                    UNSYNCED: begin
                        if (write_strobe == 1'b1) begin
                            // fire only after seeing pattern 0xFAB0_FAB1
                            if (write_data == SYNC_HEADER_PATTERN) begin
                                state <= SYNC_HEADER;
                            end
                        end
                    end
                    SYNC_HEADER: begin
                        if (write_strobe == 1'b1) begin
                            if (write_data[desync_flag] == 1'b1) begin
                                state <= UNSYNCED;
                            end else begin
                                frame_address_register <= write_data;
                                // Width-cast to silence WIDTHTRUNC warning
                                row_index <= 5'(NumberOfRows);
                                state <= WRITE_FRAME_DATA;
                            end
                        end
                    end
                    WRITE_FRAME_DATA: begin
                        if (write_strobe == 1'b1) begin
                            row_index <= row_index - 1;
                            if (row_index == 1) begin  // on last frame
                                frame_strobe <= 1'b1;
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


    always @(*) begin
        if (write_strobe) begin
            row_select = row_index;
        end else begin
            row_select = {RowSelectWidth{1'b1}};  // Invalidate the row selection when not writing
        end
    end

    reg old_frame_strobe;
    always @(posedge CLK, negedge reset_n) begin : P_StrobeREG
        if (!reset_n) begin
            old_frame_strobe  <= 1'b0;
            long_frame_strobe <= 1'b0;
        end else begin
            old_frame_strobe  <= frame_strobe;
            long_frame_strobe <= (frame_strobe || old_frame_strobe);
        end
    end

endmodule
`default_nettype wire
