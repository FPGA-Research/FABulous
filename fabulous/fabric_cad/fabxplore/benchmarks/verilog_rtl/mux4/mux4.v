module mux4 (
    input        clk,
    input        rst,   // synchronous active-high reset
    input        en,    // register enable
    input  [3:0] data,
    input  [1:0] sel,
    output       out,
    output reg   out_reg
);
    assign out = data[sel];

    always @(posedge clk) begin
        if (rst)
            out_reg <= 1'b0;
        else if (en)
            out_reg <= out;
    end
endmodule
