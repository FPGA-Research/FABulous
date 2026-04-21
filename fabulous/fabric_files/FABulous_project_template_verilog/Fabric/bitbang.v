`default_nettype none

module bitbang (
    input s_clk,
    input s_data,
    output reg strobe,
    output reg [31:0] data,
    output reg active,
    input clk,
    input resetn
);
    // verilog_lint: waive-start explicit-parameter-storage-type
    localparam [15:0] ON_PATTERN = 16'hFAB1;
    localparam [15:0] OFF_PATTERN = 16'hFAB0;
    // verilog_lint: waive-stop explicit-parameter-storage-type

    reg [3:0] s_data_sample;
    reg [3:0] s_clk_sample;

    reg [31:0] serial_data;
    reg [15:0] serial_control;

    reg local_strobe;
    reg old_local_strobe;

    always @(posedge clk, negedge resetn) begin : p_input_sync
        if (!resetn) begin
            s_data_sample <= 4'b0;
            s_clk_sample  <= 4'b0;
        end else begin
            s_data_sample <= {s_data_sample[2:0], s_data};
            s_clk_sample  <= {s_clk_sample[2:0], s_clk};
        end
    end

    always @(posedge clk, negedge resetn) begin : p_in_shift
        if (!resetn) begin
            serial_data <= 32'b0;
            serial_control <= 16'b0;
        end else begin
            // On s_clk_sample rising edge, we sample in a serial_data bit
            if ((s_clk_sample[3] == 1'b0) && (s_clk_sample[3-1] == 1'b1)) begin
                serial_data <= {serial_data[31-1:0], s_data_sample[3]};
            end
            // On s_clk_sample falling edge, we sample in a serial_control bit
            if ((s_clk_sample[3] == 1'b1) && (s_clk_sample[3-1] == 1'b0)) begin
                serial_control <= {serial_control[15-1:0], s_data_sample[3]};
            end
        end
    end

    always @(posedge clk, negedge resetn) begin : p_parallel_load
        if (!resetn) begin
            local_strobe <= 1'b0;
            data <= 32'b0;
            old_local_strobe <= 1'b0;
            strobe <= 1'b0;
        end else begin
            local_strobe <= 1'b0;
            if (serial_control == ON_PATTERN) begin
                data <= serial_data;
                local_strobe <= 1'b1;
            end
            old_local_strobe <= local_strobe;
            // Activates strobe for one clock cycle after ON_PATTERN was detected
            strobe <= local_strobe & ~old_local_strobe;
        end
    end

    always @(posedge clk, negedge resetn) begin : active_FSM
        if (!resetn) begin
            active <= 1'b0;
        end else begin
            if (serial_control == ON_PATTERN) begin
                active <= 1'b1;
            end
            if (serial_control == OFF_PATTERN) begin
                active <= 1'b0;
            end
        end
    end

endmodule
`default_nettype wire
