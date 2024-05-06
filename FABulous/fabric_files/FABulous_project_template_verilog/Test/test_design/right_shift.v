`define SIZE 649 

module top(input wire clk, input wire [27:0] io_in, output wire [27:0] io_out, io_oeb);
wire rst = io_in[0];
reg [`SIZE:0] data_in;
reg [13:0] counter;

always @ (posedge clk)
begin
    if (rst)
        begin
            counter <= 0;
            data_in <= 0;
        end
    else 
        begin
            data_in <= {counter,data_in[`SIZE:13]};
            counter <= counter + 1;
        end
end

assign io_oeb = 28'b1;
assign io_out = {data_in[`SIZE-:14],data_in[13:0]};

endmodule