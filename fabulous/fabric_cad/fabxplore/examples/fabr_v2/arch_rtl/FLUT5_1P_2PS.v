// SPDX-License-Identifier: Apache-2.0
//
// Modified FABulous V2-style LUT4x2 primitive.
//
// Config cost:
//   32 bits  LUT contents
//    4 bits  feature mode CFG[3:0]
//   ----------------------------
//   36 bits total
//
// The 4 CFG bits are encoded as one feature field, not as independent muxes.
//
// Physical LUT structure:
//
//   L0 = LUT4(...)
//   L1 = LUT4(...)
//
//   O0_NORMAL = mux(S, L0, L1)
//   O1        = L1
//
// In SELECT_AS_DATA mode, S becomes LUT data.
// Therefore the O0 mux select is forced to 0:
//
//   O0_NORMAL = L0
//
// Port naming:
//
//   I* ports are shared-input candidates.
//   A* ports are private-input candidates for L0.
//   B* ports are private-input candidates for L1.
//
// Normal mapping:
//
//   L0(I0, I1, I2, A0)
//   L1(I0, I1, I2, B0)
//
// SELECT_AS_DATA mapping:
//
//   L0(I0, I1, A0, S)
//   L1(I0, I1, B0, I2)
//
// LUT5 mode:
//
//   Route the same logical net to A0 and B0.
//   Then L0/L1 are the S=0/S=1 cofactors:
//
//   O0_NORMAL = S ? L1 : L0
//
// Fixed carry chain:
//
//   MUXCY-like:
//
//     carry_p   = O0_NORMAL
//     carry_sum = carry_p ^ carry_in
//     Co        = carry_p ? carry_in : carry_di
//
// This supports:
//
//   full adder:
//     carry_p  = a ^ b
//     carry_di = a or b
//     O0       = carry_sum
//     Co       = carry out
//
//   wide OR:
//     carry_p  = ~OR5(local inputs)
//     carry_di = 1
//     Co       = carry_in | OR5(local inputs)
//
//   wide AND:
//     carry_p  = AND5(local inputs)
//     carry_di = 0
//     Co       = carry_in & AND5(local inputs)
//
// The document describes fixed carry hardware after the LUT and mentions
// full adder behavior, wide OR, wide AND via De Morgan, MUX4, XOR6, and
// optional registered outputs. This version keeps those behaviors but uses
// two LUT4 INIT tables instead of the 8x4 memory macro. :contentReference[oaicite:0]{index=0}
//
// FABulous/nextpnr integration still needs matching BEL/packer/bitstream
// support; FABulous generates nextpnr model files such as bel.txt/pips.txt
// and maps features through bitstream/FASM data. :contentReference[oaicite:1]{index=1}
//
// LUT bit order:
//
//   LUT_OUT = INIT[{I3, I2, I1, I0}]
//
//   INIT[0]  -> 0000
//   INIT[15] -> 1111


(* FABulous, BelMap,
//
// LUT0 truth table bits.
//
INIT0_0=0,
INIT0_1=1,
INIT0_2=2,
INIT0_3=3,
INIT0_4=4,
INIT0_5=5,
INIT0_6=6,
INIT0_7=7,
INIT0_8=8,
INIT0_9=9,
INIT0_10=10,
INIT0_11=11,
INIT0_12=12,
INIT0_13=13,
INIT0_14=14,
INIT0_15=15,

//
// LUT1 truth table bits.
//
INIT1_0=16,
INIT1_1=17,
INIT1_2=18,
INIT1_3=19,
INIT1_4=20,
INIT1_5=21,
INIT1_6=22,
INIT1_7=23,
INIT1_8=24,
INIT1_9=25,
INIT1_10=26,
INIT1_11=27,
INIT1_12=28,
INIT1_13=29,
INIT1_14=30,
INIT1_15=31,

//
// CFG[3:0] feature field.
//
// CFG = 0000:
//   normal LUT5 / dual-compatible mode
//   L0(I0,I1,I2,A0)
//   L1(I0,I1,I2,B0)
//   O0 = S ? L1 : L0
//   O1 = L1
//   carry_in = Ci
//   carry_di = B0
//
// CFG = 0001:
//   SELECT_AS_DATA dual mode
//   L0(I0,I1,A0,S)
//   L1(I0,I1,B0,I2)
//   O0 = L0
//   O1 = L1
//   carry_in = Ci
//   carry_di = B0
//
// CFG = 0010:
//   full-adder mode
//   O0 = carry_sum
//   Co = carry_p ? carry_in : carry_di
//   carry_p = O0_NORMAL
//   carry_di = B0
//
// CFG = 0011:
//   hard MUX4 mode
//   O0 = MUX4(I0,I1,A0,B0; select={S,I2})
//
// CFG = 0100:
//   XOR6 mode
//   O0 = I0 ^ I1 ^ I2 ^ A0 ^ B0 ^ S
//
// CFG = 0101:
//   wide OR chain, continue
//   carry_in = Ci
//   carry_di = 1
//   Program carry_p = ~OR5(local inputs).
//
// CFG = 0110:
//   wide OR chain, start
//   carry_in = 0
//   carry_di = 1
//   Program carry_p = ~OR5(local inputs).
//
// CFG = 0111:
//   wide AND chain, continue
//   carry_in = Ci
//   carry_di = 0
//   Program carry_p = AND5(local inputs).
//
// CFG = 1000:
//   wide AND chain, start
//   carry_in = 1
//   carry_di = 0
//   Program carry_p = AND5(local inputs).
//
// CFG = 1001..1111:
//   reserved for future features.
//   Currently behaves like CFG=0000.
//
CFG_0=32,
CFG_1=33,
CFG_2=34,
CFG_3=35
*)
module FLUT5_1P_2PS #(
    parameter NoConfigBits = 36
)(
    // Shared-input candidates.
    input  wire I0,
    input  wire I1,
    input  wire I2,

    // Private-input candidate for LUT0.
    input  wire A0,

    // Private-input candidate for LUT1.
    // Also used as carry_di in normal/full-adder modes.
    input  wire B0,

    // LUT5 select input.
    // In SELECT_AS_DATA mode this becomes LUT0 data.
    input  wire S,

    // Combinational outputs.
    output wire O0,
    output wire O1,

    // Registered outputs.
    //
    // These do not consume config bits. They are always present.
    output reg  Q0,
    output reg  Q1,

    // Fixed carry chain.
    (* FABulous, CARRY="C0" *) input  wire Ci,
    (* FABulous, CARRY="C0" *) output wire Co,

    // Shared reset/enable/clock for Q0/Q1.
    //
    // Reset is synchronous and active-high.
    (* FABulous, SHARED_RESET *) input wire SR,
    (* FABulous, SHARED_ENABLE *) input wire EN,
    (* FABulous, EXTERNAL, SHARED_PORT *) input wire UserCLK,

    // Global configuration bits.
    (* FABulous, GLOBAL *) input wire [NoConfigBits-1:0] ConfigBits
);

    // ---------------------------------------------------------------------
    // Config unpacking
    // ---------------------------------------------------------------------

    wire [15:0] INIT0;
    wire [15:0] INIT1;
    wire [3:0]  CFG;

    assign INIT0 = ConfigBits[15:0];
    assign INIT1 = ConfigBits[31:16];
    assign CFG   = ConfigBits[35:32];

    // ---------------------------------------------------------------------
    // CFG encoding constants
    // ---------------------------------------------------------------------

    localparam CFG_NORMAL         = 4'b0000;
    localparam CFG_SELECT_AS_DATA = 4'b0001;
    localparam CFG_FULL_ADDER     = 4'b0010;
    localparam CFG_MUX4           = 4'b0011;
    localparam CFG_XOR6           = 4'b0100;
    localparam CFG_WIDE_OR        = 4'b0101;
    localparam CFG_WIDE_OR_START  = 4'b0110;
    localparam CFG_WIDE_AND       = 4'b0111;
    localparam CFG_WIDE_AND_START = 4'b1000;

    // ---------------------------------------------------------------------
    // Derived mode controls
    // ---------------------------------------------------------------------

    wire mode_select_as_data;
    wire mode_full_adder;
    wire mode_mux4;
    wire mode_xor6;
    wire mode_wide_or;
    wire mode_wide_or_start;
    wire mode_wide_and;
    wire mode_wide_and_start;

    assign mode_select_as_data = (CFG == CFG_SELECT_AS_DATA);
    assign mode_full_adder     = (CFG == CFG_FULL_ADDER);
    assign mode_mux4           = (CFG == CFG_MUX4);
    assign mode_xor6           = (CFG == CFG_XOR6);
    assign mode_wide_or        = (CFG == CFG_WIDE_OR);
    assign mode_wide_or_start  = (CFG == CFG_WIDE_OR_START);
    assign mode_wide_and       = (CFG == CFG_WIDE_AND);
    assign mode_wide_and_start = (CFG == CFG_WIDE_AND_START);

    // ---------------------------------------------------------------------
    // LUT input mapping
    // ---------------------------------------------------------------------
    //
    // Normal:
    //
    //   L0(I0, I1, I2, A0)
    //   L1(I0, I1, I2, B0)
    //
    // SELECT_AS_DATA:
    //
    //   L0(I0, I1, A0, S)
    //   L1(I0, I1, B0, I2)
    //
    // Only CFG_SELECT_AS_DATA changes the LUT input mapping.
    // Other features use the normal LUT5-compatible mapping.

    wire select_as_data;

    assign select_as_data = mode_select_as_data;

    wire l0_i0;
    wire l0_i1;
    wire l0_i2;
    wire l0_i3;

    wire l1_i0;
    wire l1_i1;
    wire l1_i2;
    wire l1_i3;

    assign l0_i0 = I0;
    assign l0_i1 = I1;
    assign l0_i2 = select_as_data ? A0 : I2;
    assign l0_i3 = select_as_data ? S  : A0;

    assign l1_i0 = I0;
    assign l1_i1 = I1;
    assign l1_i2 = select_as_data ? B0 : I2;
    assign l1_i3 = select_as_data ? I2 : B0;

    wire [3:0] l0_index;
    wire [3:0] l1_index;

    assign l0_index = {l0_i3, l0_i2, l0_i1, l0_i0};
    assign l1_index = {l1_i3, l1_i2, l1_i1, l1_i0};

    wire l0_out;
    wire l1_out;

    assign l0_out = INIT0[l0_index];
    assign l1_out = INIT1[l1_index];

    // ---------------------------------------------------------------------
    // Normal fractured LUT outputs
    // ---------------------------------------------------------------------
    //
    // In normal mode:
    //
    //   O0_NORMAL = S ? L1 : L0
    //
    // In SELECT_AS_DATA mode:
    //
    //   S is LUT data, so the mux select is forced to 0:
    //
    //   O0_NORMAL = L0

    wire o0_mux_sel;
    wire o0_normal;
    wire o1_normal;

    assign o0_mux_sel = select_as_data ? 1'b0 : S;

    assign o0_normal = o0_mux_sel ? l1_out : l0_out;
    assign o1_normal = l1_out;

    // ---------------------------------------------------------------------
    // Fixed carry chain
    // ---------------------------------------------------------------------
    //
    // Fixed hardware:
    //
    //   carry_sum = carry_p ^ carry_in
    //   Co        = carry_p ? carry_in : carry_di
    //
    // The CFG field only selects constants for carry_in/carry_di in the
    // wide OR/AND start modes. It does not select a different carry circuit.

    wire carry_in;
    wire carry_di;
    wire carry_p;
    wire carry_sum;

    assign carry_p = o0_normal;

    assign carry_in =
        mode_wide_or_start  ? 1'b0 :
        mode_wide_and_start ? 1'b1 :
                               Ci;

    assign carry_di =
        (mode_wide_or || mode_wide_or_start)   ? 1'b1 :
        (mode_wide_and || mode_wide_and_start) ? 1'b0 :
                                                  B0;

    assign carry_sum = carry_p ^ carry_in;

    assign Co = carry_p ? carry_in : carry_di;

    // ---------------------------------------------------------------------
    // MUX4 mode
    // ---------------------------------------------------------------------
    //
    // Hard 4:1 mux:
    //
    //   select = {S, I2}
    //
    //   00 -> I0
    //   01 -> I1
    //   10 -> A0
    //   11 -> B0

    reg mux4_out;

    always @* begin
        case ({S, I2})
            2'b00: mux4_out = I0;
            2'b01: mux4_out = I1;
            2'b10: mux4_out = A0;
            2'b11: mux4_out = B0;
            default: mux4_out = 1'b0;
        endcase
    end

    // ---------------------------------------------------------------------
    // XOR6 mode
    // ---------------------------------------------------------------------

    wire xor6_out;

    assign xor6_out = I0 ^ I1 ^ I2 ^ A0 ^ B0 ^ S;

    // ---------------------------------------------------------------------
    // O0 source selection by CFG mode
    // ---------------------------------------------------------------------
    //
    // Normal / select-as-data / wide-chain modes:
    //   O0 = O0_NORMAL
    //
    // Full-adder mode:
    //   O0 = carry_sum
    //
    // MUX4 mode:
    //   O0 = mux4_out
    //
    // XOR6 mode:
    //   O0 = xor6_out

    reg o0_selected;

    always @* begin
        case (CFG)
            CFG_FULL_ADDER: o0_selected = carry_sum;
            CFG_MUX4:       o0_selected = mux4_out;
            CFG_XOR6:       o0_selected = xor6_out;
            default:        o0_selected = o0_normal;
        endcase
    end

    assign O0 = o0_selected;
    assign O1 = o1_normal;

    // ---------------------------------------------------------------------
    // Registered outputs
    // ---------------------------------------------------------------------
    //
    // Q0/Q1 are always present and always register O0/O1 when EN=1.
    // This costs no extra configuration bits.
    //
    // SR is synchronous active-high reset to 0.

    always @(posedge UserCLK) begin
        if (EN) begin
            if (SR) begin
                Q0 <= 1'b0;
                Q1 <= 1'b0;
            end else begin
                Q0 <= O0;
                Q1 <= O1;
            end
        end
    end

endmodule
