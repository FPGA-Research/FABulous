// SPDX-FileCopyrightText: © 2026 FABulous Contributors
// SPDX-License-Identifier: Apache-2.0

`default_nettype none

module shift_register (
    input  wire       rst,
    input  wire       ena,
    input  wire       din,
    output wire [7:0] dout
);

    wire clk;
    (* keep *) Global_Clock clk_i (.CLK(clk));

    reg [7:0] sr;

    always @(posedge clk) begin
        if (rst) begin
            sr <= 8'b0;
        end else if (ena) begin
            sr <= {sr[6:0], din};
        end
    end

    assign dout = sr;

endmodule

`default_nettype wire
