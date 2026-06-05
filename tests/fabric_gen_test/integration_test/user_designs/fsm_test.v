module fsm_test (
  input clk,
  input rst,
  input in,
  output reg out
);
  reg state;
  always @(posedge clk) begin
    if (rst) state <= 0;
    else case (state)
      0: begin out <= 0; if (in) state <= 1; end
      1: begin out <= 1; if (!in) state <= 0; end
    endcase
  end
endmodule
