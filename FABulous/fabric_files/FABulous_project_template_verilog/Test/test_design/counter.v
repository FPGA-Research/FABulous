module top(input wire clk, input wire [27:0] io_in, output wire [27:0] io_out, io_oeb);
	wire rst = io_in[0];
	reg [15:0] ctr;

	always @(posedge clk)
		if (rst)
			ctr <= 0;
		else
			ctr <= ctr + 1'b1;

	assign io_out = {10'h123, ctr, rst, 1'b0}; // pass thru reset for debugging
	assign io_oeb = 28'b1;
endmodule
