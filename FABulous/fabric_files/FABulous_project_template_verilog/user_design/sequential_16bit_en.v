module top(input wire clk, input wire [27:0] io_in, output wire [27:0] io_out, io_oeb);
	wire rst = io_in[0];
	wire en = io_in[1];
	reg [15:0] ctr;

	always @(posedge clk)
		if (en)
			if (rst)
				ctr <= 0;
			else
				ctr <= ctr + 1'b1;
		else
			ctr <= ctr;

	assign io_out = {12'b0, ctr}; // pass thru reset for debugging
	assign io_oeb = 28'b1;
endmodule
