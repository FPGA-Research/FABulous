`default_nettype none

module config_SPI (
    input sck,
    input mosi,
    input ss_n,
    output reg strobe,
    output reg [31:0] data,
    output reg active,
    input clk,
    input reset_n
);
    // CPOL/CPHA = 0

    reg [5:0] bit_counter;

    reg [3:0] sck_sample;
    reg [3:0] mosi_sample;
    reg [3:0] ss_n_sample;

    reg [31:0] serial_data;

    reg word_complete;
    reg local_strobe;
    reg old_local_strobe;

    always @(posedge clk, negedge reset_n) begin : p_input_sync
        if (!reset_n) begin
            sck_sample <= 4'b0;
            mosi_sample <= 4'b0;
            ss_n_sample <= 4'b0;
        end else begin
            sck_sample <= {sck_sample[2:0], sck};
            mosi_sample <= {mosi_sample[2:0], mosi};
            ss_n_sample  <= {ss_n_sample[2:0], ss_n};
        end
    end

    always @(posedge clk, negedge reset_n) begin : p_in_shift
        if (!reset_n) begin
            serial_data <= 32'b0;
            bit_counter <= 6'b0;
        end else begin
            word_complete <= 1'b0;
            if ( (sck_sample[3]==1'b0) && (sck_sample[2]==1'b1) && ss_n_sample[3]==1'b0) begin
                serial_data <= {serial_data[30:0], mosi_sample[3]};
                if (bit_counter == 6'd31) begin
                    word_complete <= 1'b1;
                    bit_counter <= 6'b0;
                end else begin
                    bit_counter <= bit_counter+1;
                end
            end

            if ( (ss_n_sample[3]==1'b1) && (ss_n_sample[2]==1'b0)) begin
                bit_counter <= 6'b0;
            end
        end
    end

    always @(posedge clk, negedge reset_n) begin : p_parallel_load
        if (!reset_n) begin
            local_strobe <= 1'b0;
            data <= 32'b0;
            old_local_strobe <= 1'b0;
            strobe <= 1'b0;
        end else begin
            local_strobe <= 1'b0;
            if (word_complete == 1'b1) begin
                data <= serial_data;
                local_strobe <= 1'b1;
            end
            old_local_strobe <= local_strobe;
            strobe <= local_strobe & ~old_local_strobe;
        end
    end

    always @(posedge clk, negedge reset_n) begin : active_FSM
        if (!reset_n) begin
            active <= 1'b0;
        end else begin
            if (ss_n_sample[3] == 1'b0) begin
                active <= 1'b1;
            end
            if (ss_n_sample[3] == 1'b1) begin
                active <= 1'b0;
            end
        end
    end

endmodule

`default_nettype wire
