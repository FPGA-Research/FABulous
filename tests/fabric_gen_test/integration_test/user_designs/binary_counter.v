module binary_counter (
  input clk,
  input rst,
  output reg [3:0] count
);
  always @(posedge clk) begin
    if (rst) count <= 4'b0000;
    else count <= count + 4'b1;
  end
endmodule
