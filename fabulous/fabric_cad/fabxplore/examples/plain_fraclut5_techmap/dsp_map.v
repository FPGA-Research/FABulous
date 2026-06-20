// -----------------------------------------------------------------------------
// Helper wrapper with vector ports.
// The final cells are still MULADD instances with the scalar FABulous interface.
// -----------------------------------------------------------------------------

module _MULADD8X8_PRODUCT (A, B, Q);
  input  [7:0] A;
  input  [7:0] B;
  output [19:0] Q;

  MULADD #(
    .A_reg(1'b0),
    .B_reg(1'b0),
    .C_reg(1'b0),
    .ACC(1'b0),
    .signExtension(1'b0),
    .ACCout(1'b0)
  ) muladd_i (
    .A7(A[7]), .A6(A[6]), .A5(A[5]), .A4(A[4]),
    .A3(A[3]), .A2(A[2]), .A1(A[1]), .A0(A[0]),

    .B7(B[7]), .B6(B[6]), .B5(B[5]), .B4(B[4]),
    .B3(B[3]), .B2(B[2]), .B1(B[1]), .B0(B[0]),

    .C19(1'b0), .C18(1'b0), .C17(1'b0), .C16(1'b0),
    .C15(1'b0), .C14(1'b0), .C13(1'b0), .C12(1'b0),
    .C11(1'b0), .C10(1'b0), .C9(1'b0),  .C8(1'b0),
    .C7(1'b0),  .C6(1'b0),  .C5(1'b0),  .C4(1'b0),
    .C3(1'b0),  .C2(1'b0),  .C1(1'b0),  .C0(1'b0),

    .Q19(Q[19]), .Q18(Q[18]), .Q17(Q[17]), .Q16(Q[16]),
    .Q15(Q[15]), .Q14(Q[14]), .Q13(Q[13]), .Q12(Q[12]),
    .Q11(Q[11]), .Q10(Q[10]), .Q9(Q[9]),   .Q8(Q[8]),
    .Q7(Q[7]),   .Q6(Q[6]),   .Q5(Q[5]),   .Q4(Q[4]),
    .Q3(Q[3]),   .Q2(Q[2]),   .Q1(Q[1]),   .Q0(Q[0]),

    .clr(1'b0),
    .CLK(1'b0)
  );
endmodule


// -----------------------------------------------------------------------------
// $macc_v2 -> many MULADDs plus glue logic.
// -----------------------------------------------------------------------------

(* techmap_celltype = "$macc_v2" *)
module _80_muladd_macc_v2 (A, B, C, Y);
  parameter integer NPRODUCTS = 0;
  parameter integer NADDENDS = 0;

  parameter [(16*NPRODUCTS)-1:0] A_WIDTHS = 0;
  parameter [(16*NPRODUCTS)-1:0] B_WIDTHS = 0;
  parameter [(16*NADDENDS)-1:0]  C_WIDTHS = 0;

  parameter integer Y_WIDTH = 0;

  parameter [NPRODUCTS-1:0] PRODUCT_NEGATED = 0;
  parameter [NADDENDS-1:0]  ADDEND_NEGATED = 0;

  parameter [NPRODUCTS-1:0] A_SIGNED = 0;
  parameter [NPRODUCTS-1:0] B_SIGNED = 0;
  parameter [NADDENDS-1:0]  C_SIGNED = 0;

  function integer sum_product_widths;
    input [(16*NPRODUCTS)-1:0] widths;
    integer i;
    begin
      sum_product_widths = 0;
      for (i = 0; i < NPRODUCTS; i = i + 1)
        sum_product_widths = sum_product_widths + widths[16*i +: 16];
    end
  endfunction

  function integer sum_addend_widths;
    input [(16*NADDENDS)-1:0] widths;
    integer i;
    begin
      sum_addend_widths = 0;
      for (i = 0; i < NADDENDS; i = i + 1)
        sum_addend_widths = sum_addend_widths + widths[16*i +: 16];
    end
  endfunction

  function integer product_width_before;
    input [(16*NPRODUCTS)-1:0] widths;
    input integer idx;
    integer i;
    begin
      product_width_before = 0;
      for (i = 0; i < idx; i = i + 1)
        product_width_before = product_width_before + widths[16*i +: 16];
    end
  endfunction

  function integer addend_width_before;
    input [(16*NADDENDS)-1:0] widths;
    input integer idx;
    integer i;
    begin
      addend_width_before = 0;
      for (i = 0; i < idx; i = i + 1)
        addend_width_before = addend_width_before + widths[16*i +: 16];
    end
  endfunction

  localparam integer A_TOTAL = sum_product_widths(A_WIDTHS);
  localparam integer B_TOTAL = sum_product_widths(B_WIDTHS);
  localparam integer C_TOTAL = sum_addend_widths(C_WIDTHS);

  localparam integer CHUNKS = (Y_WIDTH + 7) / 8;
  localparam integer NPARTS = CHUNKS * CHUNKS;

  input  [A_TOTAL-1:0] A;
  input  [B_TOTAL-1:0] B;
  input  [C_TOTAL-1:0] C;
  output [Y_WIDTH-1:0] Y;

  // We intentionally do not map degenerate zero-width results here.
  wire _TECHMAP_FAIL_ = (Y_WIDTH <= 0);

  // Product terms after decomposition.
  wire [NPRODUCTS*Y_WIDTH-1:0] product_terms;

  genvar p;
  generate
    for (p = 0; p < NPRODUCTS; p = p + 1) begin : gen_product
      localparam integer AW = A_WIDTHS[16*p +: 16];
      localparam integer BW = B_WIDTHS[16*p +: 16];
      localparam integer AOFF = product_width_before(A_WIDTHS, p);
      localparam integer BOFF = product_width_before(B_WIDTHS, p);

      wire [Y_WIDTH-1:0] a_ext;
      wire [Y_WIDTH-1:0] b_ext;

      // Extend/truncate the product inputs to the $macc_v2 output width.
      // This matches the modulo-2^Y_WIDTH behavior of the Yosys model.
      if (AW >= Y_WIDTH) begin : gen_a_trunc
        assign a_ext = A[AOFF +: Y_WIDTH];
      end else begin : gen_a_extend
        if (A_SIGNED[p]) begin : gen_a_signed
          assign a_ext = {{(Y_WIDTH-AW){A[AOFF+AW-1]}}, A[AOFF +: AW]};
        end else begin : gen_a_unsigned
          assign a_ext = {{(Y_WIDTH-AW){1'b0}}, A[AOFF +: AW]};
        end
      end

      if (BW >= Y_WIDTH) begin : gen_b_trunc
        assign b_ext = B[BOFF +: Y_WIDTH];
      end else begin : gen_b_extend
        if (B_SIGNED[p]) begin : gen_b_signed
          assign b_ext = {{(Y_WIDTH-BW){B[BOFF+BW-1]}}, B[BOFF +: BW]};
        end else begin : gen_b_unsigned
          assign b_ext = {{(Y_WIDTH-BW){1'b0}}, B[BOFF +: BW]};
        end
      end

      // Pad to a multiple of 8 so that each chunk is exactly one MULADD input.
      wire [CHUNKS*8-1:0] a_pad = {{(CHUNKS*8-Y_WIDTH){1'b0}}, a_ext};
      wire [CHUNKS*8-1:0] b_pad = {{(CHUNKS*8-Y_WIDTH){1'b0}}, b_ext};

      // Accumulate all 8x8 partial products for this product term.
      wire [(NPARTS+1)*Y_WIDTH-1:0] part_acc;
      assign part_acc[0 +: Y_WIDTH] = {Y_WIDTH{1'b0}};

      genvar ia, ib;
      for (ia = 0; ia < CHUNKS; ia = ia + 1) begin : gen_chunk_a
        for (ib = 0; ib < CHUNKS; ib = ib + 1) begin : gen_chunk_b
          localparam integer IDX = ia*CHUNKS + ib;
          localparam integer SHIFT = 8*(ia + ib);

          wire [7:0] a8 = a_pad[8*ia +: 8];
          wire [7:0] b8 = b_pad[8*ib +: 8];
          wire [19:0] q20;

          _MULADD8X8_PRODUCT muladd_product_i (
            .A(a8),
            .B(b8),
            .Q(q20)
          );

          // Shift the 20-bit partial product into a wider temporary vector and
          // then take the low Y_WIDTH bits. This implements modulo truncation.
          wire [Y_WIDTH+20-1:0] shifted_wide =
              ({{Y_WIDTH{1'b0}}, q20} << SHIFT);

          wire [Y_WIDTH-1:0] shifted_part = shifted_wide[Y_WIDTH-1:0];

          assign part_acc[(IDX+1)*Y_WIDTH +: Y_WIDTH] =
              part_acc[IDX*Y_WIDTH +: Y_WIDTH] + shifted_part;
        end
      end

      wire [Y_WIDTH-1:0] product_value =
          part_acc[NPARTS*Y_WIDTH +: Y_WIDTH];

      assign product_terms[p*Y_WIDTH +: Y_WIDTH] =
          PRODUCT_NEGATED[p] ? (~product_value + {{(Y_WIDTH-1){1'b0}}, 1'b1})
                             : product_value;
    end
  endgenerate

  // Addend terms after sign extension/truncation.
  wire [NADDENDS*Y_WIDTH-1:0] addend_terms;

  genvar cidx;
  generate
    for (cidx = 0; cidx < NADDENDS; cidx = cidx + 1) begin : gen_addend
      localparam integer CW = C_WIDTHS[16*cidx +: 16];
      localparam integer COFF = addend_width_before(C_WIDTHS, cidx);

      wire [Y_WIDTH-1:0] c_ext;

      if (CW >= Y_WIDTH) begin : gen_c_trunc
        assign c_ext = C[COFF +: Y_WIDTH];
      end else begin : gen_c_extend
        if (C_SIGNED[cidx]) begin : gen_c_signed
          assign c_ext = {{(Y_WIDTH-CW){C[COFF+CW-1]}}, C[COFF +: CW]};
        end else begin : gen_c_unsigned
          assign c_ext = {{(Y_WIDTH-CW){1'b0}}, C[COFF +: CW]};
        end
      end

      assign addend_terms[cidx*Y_WIDTH +: Y_WIDTH] =
          ADDEND_NEGATED[cidx] ? (~c_ext + {{(Y_WIDTH-1){1'b0}}, 1'b1})
                               : c_ext;
    end
  endgenerate

  // Final accumulation of all products and addends.
  localparam integer NTERMS = NPRODUCTS + NADDENDS;
  wire [(NTERMS+1)*Y_WIDTH-1:0] total_acc;

  assign total_acc[0 +: Y_WIDTH] = {Y_WIDTH{1'b0}};

  genvar t;
  generate
    for (t = 0; t < NTERMS; t = t + 1) begin : gen_total
      wire [Y_WIDTH-1:0] term_value;

      if (t < NPRODUCTS) begin : gen_term_product
        assign term_value = product_terms[t*Y_WIDTH +: Y_WIDTH];
      end else begin : gen_term_addend
        assign term_value = addend_terms[(t-NPRODUCTS)*Y_WIDTH +: Y_WIDTH];
      end

      assign total_acc[(t+1)*Y_WIDTH +: Y_WIDTH] =
          total_acc[t*Y_WIDTH +: Y_WIDTH] + term_value;
    end
  endgenerate

  assign Y = total_acc[NTERMS*Y_WIDTH +: Y_WIDTH];

endmodule
