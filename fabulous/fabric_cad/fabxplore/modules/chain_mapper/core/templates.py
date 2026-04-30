"""Jinja2 Verilog templates for generated chain techmap files."""

from jinja2 import Environment


def _template_env() -> Environment:
    """Create a Jinja2 environment for one chain techmap template family.

    Returns
    -------
    Environment
        A Jinja2 Environment configured for chain techmap templates.
    """
    return Environment(
        autoescape=False,
        keep_trailing_newline=True,
        lstrip_blocks=True,
        trim_blocks=True,
    )


TEMPLATE_ENV = _template_env()

CHAIN_BLACKBOX_TEMPLATE = r"""
(* blackbox *)
module {{ chain_name }} #(
    parameter MODE = "REDUCE_OR",
    parameter [31:0] N = 32'd1,
    parameter INIT = 0,
    parameter [N-1:0] INV_IN = {N{1'b0}},
    parameter INV_OUT = 1'b0,
    parameter ALU_INIT_MODE = "{{ alu_init_mode }}"
) (
    input  [N-1:0] I,
    input  [N-1:0] A,
    input  [N-1:0] B,
    input          CI,
    output         Y,
    output         CO
);
endmodule
"""

REDUCE_AND_TECHMAP_TEMPLATE = r"""
`default_nettype none

(* techmap_celltype = "$reduce_and" *)
module _chain_reduce_and (A, Y);
parameter A_SIGNED = 0;
parameter A_WIDTH = 0;
parameter Y_WIDTH = 0;

(* force_downto *)
input [A_WIDTH-1:0] A;
(* force_downto *)
output [Y_WIDTH-1:0] Y;

localparam integer CHUNK_SIZE = {{ chunk_size }};
localparam integer MIN_CHAIN_PRIMS = {{ effective_min_chain_prims }};
localparam integer MAX_CHAIN_PRIMS = {{ max_chain_prims_value }};
localparam integer NUM_PRIMS = (A_WIDTH + CHUNK_SIZE - 1) / CHUNK_SIZE;
localparam integer MAX_INIT_BITS = (1 << CHUNK_SIZE);
localparam integer INIT_MODE_ID = {{ reducer.init_mode_id }};

wire _TECHMAP_FAIL_ =
    A_WIDTH < 1 ||
    Y_WIDTH < 1 ||
    NUM_PRIMS < MIN_CHAIN_PRIMS ||
    (MAX_CHAIN_PRIMS > 0 && NUM_PRIMS > MAX_CHAIN_PRIMS);

wire result_bit;

function [MAX_INIT_BITS-1:0] chain_local_init;
    input integer bits;
    input integer mode_id;
    integer addr;
    integer bit_idx;
    integer local_value;
    begin
        chain_local_init = {MAX_INIT_BITS{1'b0}};
        for (addr = 0; addr < (1 << bits); addr = addr + 1) begin
            if (mode_id == 1) begin
                local_value = 1;
            end else begin
                local_value = 0;
            end

            for (bit_idx = 0; bit_idx < bits; bit_idx = bit_idx + 1) begin
                if (mode_id == 0) begin
                    local_value = local_value | ((addr >> bit_idx) & 1);
                end else if (mode_id == 1) begin
                    local_value = local_value & ((addr >> bit_idx) & 1);
                end else begin
                    local_value = local_value ^ ((addr >> bit_idx) & 1);
                end
            end

            chain_local_init[addr] = local_value;
        end
    end
endfunction

function [CHUNK_SIZE-1:0] chain_chunk_input;
    input [A_WIDTH-1:0] data;
    input integer offset;
    input integer bits;
    integer bit_idx;
    begin
        chain_chunk_input = {CHUNK_SIZE{ {{ reducer.pad_value }} }};
        for (bit_idx = 0; bit_idx < CHUNK_SIZE; bit_idx = bit_idx + 1) begin
            if (bit_idx < bits) begin
                chain_chunk_input[bit_idx] = {{ reducer.source_bit_expr }};
            end
        end
    end
endfunction

wire [NUM_PRIMS:0] chain;
assign chain[0] = {{ reducer.seed }};

genvar i;
generate
for (i = 0; i < NUM_PRIMS; i = i + 1) begin: chunk
    localparam integer OFFSET = i * CHUNK_SIZE;
    localparam integer REMAINING_BITS = A_WIDTH - OFFSET;
    localparam integer BITS =
        REMAINING_BITS > CHUNK_SIZE ? CHUNK_SIZE : REMAINING_BITS;

    wire [CHUNK_SIZE-1:0] chunk_i = chain_chunk_input(A, OFFSET, BITS);
    wire unused_y;

    {{ chain_name }} #(
        .MODE("{{ reducer.mode }}"),
        .N(32'd{{ chunk_size }}),
        .INIT(chain_local_init(CHUNK_SIZE, INIT_MODE_ID)),
        .INV_IN({{ reducer.inv_in }}),
        .INV_OUT({{ reducer.inv_out }})
    ) u_chain (
        .I(chunk_i),
        .A({CHUNK_SIZE{1'b0}}),
        .B({CHUNK_SIZE{1'b0}}),
        .CI(chain[i]),
        .Y(unused_y),
        .CO(chain[i+1])
    );
end
endgenerate

assign result_bit = {{ reducer.final_expr }};

generate
if (Y_WIDTH == 1) begin: y_one
    assign Y = result_bit;
end else begin: y_wide
    assign Y = {{'{'}}{{'{'}}(Y_WIDTH-1){{'{'}}1'b0{{'}'}}{{'}'}}, result_bit{{'}'}};
end
endgenerate
endmodule

`default_nettype wire
"""

REDUCE_BOOL_TECHMAP_TEMPLATE = r"""
`default_nettype none

(* techmap_celltype = "$reduce_bool" *)
module _chain_reduce_bool (A, Y);
parameter A_SIGNED = 0;
parameter A_WIDTH = 0;
parameter Y_WIDTH = 0;

(* force_downto *)
input [A_WIDTH-1:0] A;
(* force_downto *)
output [Y_WIDTH-1:0] Y;

localparam integer CHUNK_SIZE = {{ chunk_size }};
localparam integer MIN_CHAIN_PRIMS = {{ effective_min_chain_prims }};
localparam integer MAX_CHAIN_PRIMS = {{ max_chain_prims_value }};
localparam integer NUM_PRIMS = (A_WIDTH + CHUNK_SIZE - 1) / CHUNK_SIZE;
localparam integer MAX_INIT_BITS = (1 << CHUNK_SIZE);
localparam integer INIT_MODE_ID = {{ reducer.init_mode_id }};

wire _TECHMAP_FAIL_ =
    A_WIDTH < 1 ||
    Y_WIDTH < 1 ||
    NUM_PRIMS < MIN_CHAIN_PRIMS ||
    (MAX_CHAIN_PRIMS > 0 && NUM_PRIMS > MAX_CHAIN_PRIMS);

wire result_bit;

function [MAX_INIT_BITS-1:0] chain_local_init;
    input integer bits;
    input integer mode_id;
    integer addr;
    integer bit_idx;
    integer local_value;
    begin
        chain_local_init = {MAX_INIT_BITS{1'b0}};
        for (addr = 0; addr < (1 << bits); addr = addr + 1) begin
            if (mode_id == 1) begin
                local_value = 1;
            end else begin
                local_value = 0;
            end

            for (bit_idx = 0; bit_idx < bits; bit_idx = bit_idx + 1) begin
                if (mode_id == 0) begin
                    local_value = local_value | ((addr >> bit_idx) & 1);
                end else if (mode_id == 1) begin
                    local_value = local_value & ((addr >> bit_idx) & 1);
                end else begin
                    local_value = local_value ^ ((addr >> bit_idx) & 1);
                end
            end

            chain_local_init[addr] = local_value;
        end
    end
endfunction

function [CHUNK_SIZE-1:0] chain_chunk_input;
    input [A_WIDTH-1:0] data;
    input integer offset;
    input integer bits;
    integer bit_idx;
    begin
        chain_chunk_input = {CHUNK_SIZE{ {{ reducer.pad_value }} }};
        for (bit_idx = 0; bit_idx < CHUNK_SIZE; bit_idx = bit_idx + 1) begin
            if (bit_idx < bits) begin
                chain_chunk_input[bit_idx] = {{ reducer.source_bit_expr }};
            end
        end
    end
endfunction

wire [NUM_PRIMS:0] chain;
assign chain[0] = {{ reducer.seed }};

genvar i;
generate
for (i = 0; i < NUM_PRIMS; i = i + 1) begin: chunk
    localparam integer OFFSET = i * CHUNK_SIZE;
    localparam integer REMAINING_BITS = A_WIDTH - OFFSET;
    localparam integer BITS =
        REMAINING_BITS > CHUNK_SIZE ? CHUNK_SIZE : REMAINING_BITS;

    wire [CHUNK_SIZE-1:0] chunk_i = chain_chunk_input(A, OFFSET, BITS);
    wire unused_y;

    {{ chain_name }} #(
        .MODE("{{ reducer.mode }}"),
        .N(32'd{{ chunk_size }}),
        .INIT(chain_local_init(CHUNK_SIZE, INIT_MODE_ID)),
        .INV_IN({{ reducer.inv_in }}),
        .INV_OUT({{ reducer.inv_out }})
    ) u_chain (
        .I(chunk_i),
        .A({CHUNK_SIZE{1'b0}}),
        .B({CHUNK_SIZE{1'b0}}),
        .CI(chain[i]),
        .Y(unused_y),
        .CO(chain[i+1])
    );
end
endgenerate

assign result_bit = {{ reducer.final_expr }};

generate
if (Y_WIDTH == 1) begin: y_one
    assign Y = result_bit;
end else begin: y_wide
    assign Y = {{'{'}}{{'{'}}(Y_WIDTH-1){{'{'}}1'b0{{'}'}}{{'}'}}, result_bit{{'}'}};
end
endgenerate
endmodule

`default_nettype wire
"""

REDUCE_OR_TECHMAP_TEMPLATE = r"""
`default_nettype none

(* techmap_celltype = "$reduce_or" *)
module _chain_reduce_or (A, Y);
parameter A_SIGNED = 0;
parameter A_WIDTH = 0;
parameter Y_WIDTH = 0;

(* force_downto *)
input [A_WIDTH-1:0] A;
(* force_downto *)
output [Y_WIDTH-1:0] Y;

localparam integer CHUNK_SIZE = {{ chunk_size }};
localparam integer MIN_CHAIN_PRIMS = {{ effective_min_chain_prims }};
localparam integer MAX_CHAIN_PRIMS = {{ max_chain_prims_value }};
localparam integer NUM_PRIMS = (A_WIDTH + CHUNK_SIZE - 1) / CHUNK_SIZE;
localparam integer MAX_INIT_BITS = (1 << CHUNK_SIZE);
localparam integer INIT_MODE_ID = {{ reducer.init_mode_id }};

wire _TECHMAP_FAIL_ =
    A_WIDTH < 1 ||
    Y_WIDTH < 1 ||
    NUM_PRIMS < MIN_CHAIN_PRIMS ||
    (MAX_CHAIN_PRIMS > 0 && NUM_PRIMS > MAX_CHAIN_PRIMS);

wire result_bit;

function [MAX_INIT_BITS-1:0] chain_local_init;
    input integer bits;
    input integer mode_id;
    integer addr;
    integer bit_idx;
    integer local_value;
    begin
        chain_local_init = {MAX_INIT_BITS{1'b0}};
        for (addr = 0; addr < (1 << bits); addr = addr + 1) begin
            if (mode_id == 1) begin
                local_value = 1;
            end else begin
                local_value = 0;
            end

            for (bit_idx = 0; bit_idx < bits; bit_idx = bit_idx + 1) begin
                if (mode_id == 0) begin
                    local_value = local_value | ((addr >> bit_idx) & 1);
                end else if (mode_id == 1) begin
                    local_value = local_value & ((addr >> bit_idx) & 1);
                end else begin
                    local_value = local_value ^ ((addr >> bit_idx) & 1);
                end
            end

            chain_local_init[addr] = local_value;
        end
    end
endfunction

function [CHUNK_SIZE-1:0] chain_chunk_input;
    input [A_WIDTH-1:0] data;
    input integer offset;
    input integer bits;
    integer bit_idx;
    begin
        chain_chunk_input = {CHUNK_SIZE{ {{ reducer.pad_value }} }};
        for (bit_idx = 0; bit_idx < CHUNK_SIZE; bit_idx = bit_idx + 1) begin
            if (bit_idx < bits) begin
                chain_chunk_input[bit_idx] = {{ reducer.source_bit_expr }};
            end
        end
    end
endfunction

wire [NUM_PRIMS:0] chain;
assign chain[0] = {{ reducer.seed }};

genvar i;
generate
for (i = 0; i < NUM_PRIMS; i = i + 1) begin: chunk
    localparam integer OFFSET = i * CHUNK_SIZE;
    localparam integer REMAINING_BITS = A_WIDTH - OFFSET;
    localparam integer BITS =
        REMAINING_BITS > CHUNK_SIZE ? CHUNK_SIZE : REMAINING_BITS;

    wire [CHUNK_SIZE-1:0] chunk_i = chain_chunk_input(A, OFFSET, BITS);
    wire unused_y;

    {{ chain_name }} #(
        .MODE("{{ reducer.mode }}"),
        .N(32'd{{ chunk_size }}),
        .INIT(chain_local_init(CHUNK_SIZE, INIT_MODE_ID)),
        .INV_IN({{ reducer.inv_in }}),
        .INV_OUT({{ reducer.inv_out }})
    ) u_chain (
        .I(chunk_i),
        .A({CHUNK_SIZE{1'b0}}),
        .B({CHUNK_SIZE{1'b0}}),
        .CI(chain[i]),
        .Y(unused_y),
        .CO(chain[i+1])
    );
end
endgenerate

assign result_bit = {{ reducer.final_expr }};

generate
if (Y_WIDTH == 1) begin: y_one
    assign Y = result_bit;
end else begin: y_wide
    assign Y = {{'{'}}{{'{'}}(Y_WIDTH-1){{'{'}}1'b0{{'}'}}{{'}'}}, result_bit{{'}'}};
end
endgenerate
endmodule

`default_nettype wire
"""

REDUCE_XOR_TECHMAP_TEMPLATE = r"""
`default_nettype none

(* techmap_celltype = "$reduce_xor" *)
module _chain_reduce_xor (A, Y);
parameter A_SIGNED = 0;
parameter A_WIDTH = 0;
parameter Y_WIDTH = 0;

(* force_downto *)
input [A_WIDTH-1:0] A;
(* force_downto *)
output [Y_WIDTH-1:0] Y;

localparam integer CHUNK_SIZE = {{ chunk_size }};
localparam integer MIN_CHAIN_PRIMS = {{ effective_min_chain_prims }};
localparam integer MAX_CHAIN_PRIMS = {{ max_chain_prims_value }};
localparam integer NUM_PRIMS = (A_WIDTH + CHUNK_SIZE - 1) / CHUNK_SIZE;
localparam integer MAX_INIT_BITS = (1 << CHUNK_SIZE);
localparam integer INIT_MODE_ID = {{ reducer.init_mode_id }};

wire _TECHMAP_FAIL_ =
    A_WIDTH < 1 ||
    Y_WIDTH < 1 ||
    NUM_PRIMS < MIN_CHAIN_PRIMS ||
    (MAX_CHAIN_PRIMS > 0 && NUM_PRIMS > MAX_CHAIN_PRIMS);

wire result_bit;

function [MAX_INIT_BITS-1:0] chain_local_init;
    input integer bits;
    input integer mode_id;
    integer addr;
    integer bit_idx;
    integer local_value;
    begin
        chain_local_init = {MAX_INIT_BITS{1'b0}};
        for (addr = 0; addr < (1 << bits); addr = addr + 1) begin
            if (mode_id == 1) begin
                local_value = 1;
            end else begin
                local_value = 0;
            end

            for (bit_idx = 0; bit_idx < bits; bit_idx = bit_idx + 1) begin
                if (mode_id == 0) begin
                    local_value = local_value | ((addr >> bit_idx) & 1);
                end else if (mode_id == 1) begin
                    local_value = local_value & ((addr >> bit_idx) & 1);
                end else begin
                    local_value = local_value ^ ((addr >> bit_idx) & 1);
                end
            end

            chain_local_init[addr] = local_value;
        end
    end
endfunction

function [CHUNK_SIZE-1:0] chain_chunk_input;
    input [A_WIDTH-1:0] data;
    input integer offset;
    input integer bits;
    integer bit_idx;
    begin
        chain_chunk_input = {CHUNK_SIZE{ {{ reducer.pad_value }} }};
        for (bit_idx = 0; bit_idx < CHUNK_SIZE; bit_idx = bit_idx + 1) begin
            if (bit_idx < bits) begin
                chain_chunk_input[bit_idx] = {{ reducer.source_bit_expr }};
            end
        end
    end
endfunction

wire [NUM_PRIMS:0] chain;
assign chain[0] = {{ reducer.seed }};

genvar i;
generate
for (i = 0; i < NUM_PRIMS; i = i + 1) begin: chunk
    localparam integer OFFSET = i * CHUNK_SIZE;
    localparam integer REMAINING_BITS = A_WIDTH - OFFSET;
    localparam integer BITS =
        REMAINING_BITS > CHUNK_SIZE ? CHUNK_SIZE : REMAINING_BITS;

    wire [CHUNK_SIZE-1:0] chunk_i = chain_chunk_input(A, OFFSET, BITS);
    wire unused_y;

    {{ chain_name }} #(
        .MODE("{{ reducer.mode }}"),
        .N(32'd{{ chunk_size }}),
        .INIT(chain_local_init(CHUNK_SIZE, INIT_MODE_ID)),
        .INV_IN({{ reducer.inv_in }}),
        .INV_OUT({{ reducer.inv_out }})
    ) u_chain (
        .I(chunk_i),
        .A({CHUNK_SIZE{1'b0}}),
        .B({CHUNK_SIZE{1'b0}}),
        .CI(chain[i]),
        .Y(unused_y),
        .CO(chain[i+1])
    );
end
endgenerate

assign result_bit = {{ reducer.final_expr }};

generate
if (Y_WIDTH == 1) begin: y_one
    assign Y = result_bit;
end else begin: y_wide
    assign Y = {{'{'}}{{'{'}}(Y_WIDTH-1){{'{'}}1'b0{{'}'}}{{'}'}}, result_bit{{'}'}};
end
endgenerate
endmodule

`default_nettype wire
"""

ALU_TECHMAP_TEMPLATE = r"""
`default_nettype none

(* techmap_celltype = "$alu" *)
module _chain_alu (A, B, CI, BI, X, Y, CO);
parameter A_SIGNED = 0;
parameter B_SIGNED = 0;
parameter A_WIDTH = 1;
parameter B_WIDTH = 1;
parameter Y_WIDTH = 1;

(* force_downto *)
input [A_WIDTH-1:0] A;
(* force_downto *)
input [B_WIDTH-1:0] B;
input CI, BI;
(* force_downto *)
output [Y_WIDTH-1:0] X, Y, CO;

localparam integer MAX_CHAIN_PRIMS = {{ max_chain_prims_value }};

wire _TECHMAP_FAIL_ =
    Y_WIDTH < 1 ||
    (MAX_CHAIN_PRIMS > 0 && Y_WIDTH > MAX_CHAIN_PRIMS);

(* force_downto *)
wire [Y_WIDTH-1:0] A_buf, B_buf;
$pos #(
    .A_SIGNED(A_SIGNED),
    .A_WIDTH(A_WIDTH),
    .Y_WIDTH(Y_WIDTH)
) A_conv (.A(A), .Y(A_buf));
$pos #(
    .A_SIGNED(B_SIGNED),
    .A_WIDTH(B_WIDTH),
    .Y_WIDTH(Y_WIDTH)
) B_conv (.A(B), .Y(B_buf));

(* force_downto *)
wire [Y_WIDTH-1:0] AA = A_buf;
(* force_downto *)
wire [Y_WIDTH-1:0] BB = BI ? ~B_buf : B_buf;

wire [Y_WIDTH:0] carry;
assign carry[0] = CI;

genvar i;
generate
for (i = 0; i < Y_WIDTH; i = i + 1) begin: slice
    localparam integer LOCAL_N = {{ alu_n }};
    wire [LOCAL_N-1:0] local_i = {{ alu_i_expr }};
    wire [LOCAL_N-1:0] local_a = {{ alu_a_expr }};
    wire [LOCAL_N-1:0] local_b = {{ alu_b_expr }};
    wire local_y;

    {{ chain_name }} #(
        .MODE("ADD"),
        .N(32'd{{ alu_n }}),
        .INIT({{ alu_init }}),
        .INV_IN({LOCAL_N{1'b0}}),
        .INV_OUT(1'b0),
        .ALU_INIT_MODE("{{ alu_init_mode }}")
    ) u_chain_add (
        .I(local_i),
        .A(local_a),
        .B(local_b),
        .CI(carry[i]),
        .Y(local_y),
        .CO(carry[i+1])
    );

    assign Y[i] = local_y;
    assign CO[i] = carry[i+1];
end
endgenerate

assign X = AA ^ BB;
endmodule

`default_nettype wire
"""
