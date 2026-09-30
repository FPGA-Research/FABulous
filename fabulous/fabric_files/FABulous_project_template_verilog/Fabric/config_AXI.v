`default_nettype none

module config_AXI (

    input wire clk,
    input wire reset_n,

    output reg strobe,
    output reg [31:0] data,
    output wire active,

    // AW
    input wire [31:0] s_axi_awaddr,
    input wire s_axi_awvalid,
    output wire s_axi_awready,

    // W
    input wire [31:0] s_axi_wdata,
    input wire [3:0] s_axi_wstrb,
    input wire s_axi_wvalid,
    output wire s_axi_wready,

    // B
    output wire [1:0] s_axi_bresp,
    output wire s_axi_bvalid,
    input wire s_axi_bready,

    // AR
    input wire [31:0] s_axi_araddr,
    input wire s_axi_arvalid,
    output wire s_axi_arready,

    // R
    output wire [31:0] s_axi_rdata,
    output wire [1:0] s_axi_rresp,
    output s_axi_rvalid,
    input wire s_axi_rready
);
    reg aw_done;
    reg w_done;
    reg b_done;
    reg ar_done;

    always @(posedge clk) begin : AW
        if (!reset_n) begin
            aw_done <= 1'b0;
        end else if (s_axi_awready && s_axi_awvalid) begin
            aw_done <= 1'b1;
        end else if (s_axi_bready && s_axi_bvalid) begin
            aw_done <= 1'b0;
        end
    end

    assign s_axi_awready = !aw_done;

    always @(posedge clk) begin : W
        if (!reset_n) begin
            w_done <= 1'b0;
        end else if (s_axi_wready && s_axi_wvalid) begin
            w_done <= 1'b1;
            data <= s_axi_wdata;
        end else if (s_axi_bready && s_axi_bvalid) begin
            w_done <= 0;
        end
    end

    assign s_axi_wready = !w_done;

    always @(posedge clk) begin : B
        if (!reset_n) begin
            b_done <= 1'b0;
        end else if (s_axi_bready && s_axi_bvalid) begin
            b_done <= 1'b0;
        end else if (aw_done && w_done) begin
            b_done <= 1'b1;
        end
    end

    assign s_axi_bvalid = b_done;
    assign s_axi_bresp = 2'b0;

    assign s_axi_rdata = 32'b0;
    assign s_axi_rresp = 2'b0;

    always @(posedge clk) begin : AR_R
        if (!reset_n) begin
            ar_done <= 1'b0;
        end else if (s_axi_arvalid && s_axi_arready) begin
            ar_done <= 1'b1;
        end else if (s_axi_rvalid && s_axi_rready) begin
            ar_done <= 1'b0;
        end
    end

    assign s_axi_rvalid = ar_done;
    assign s_axi_arready = !ar_done;

    // Strobe
    reg local_strobe;
    reg old_local_strobe;
    always@ (posedge clk) begin
        if (!reset_n) begin
            local_strobe <= 1'b0;
            old_local_strobe <= 1'b0;
            strobe <= 1'b0;
        end else begin
            local_strobe <= 1'b0;
            if (aw_done && w_done) begin
                local_strobe <= 1'b1;
            end
            old_local_strobe <= local_strobe;
            strobe <= local_strobe & ~old_local_strobe;
        end
    end

    // Active
    assign active = aw_done | w_done | b_done;

endmodule
`default_nettype wire
