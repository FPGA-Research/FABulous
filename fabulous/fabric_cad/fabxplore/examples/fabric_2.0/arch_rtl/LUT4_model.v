(* FABulous, BelMap,
INIT=0,
INIT_1=1,
INIT_2=2,
INIT_3=3,
INIT_4=4,
INIT_5=5,
INIT_6=6,
INIT_7=7,
INIT_8=8,
INIT_9=9,
INIT_10=10,
INIT_11=11,
INIT_12=12,
INIT_13=13,
INIT_14=14,
INIT_15=15,
IOmux=16
*)
module LUT4ST #(parameter NoConfigBits = 17)(
    input  I0,
    input  I1,
    input  I2,
    input  I3,

    output O,

    input  Ci,
    output Co,

    (* FABulous, GLOBAL *)
    input [NoConfigBits-1:0] ConfigBits
);

    wire [15:0] LUT_values;
    wire        c_I0mux;
    wire        I0mux;
    wire [3:0]  LUT_index;

    assign LUT_values = ConfigBits[15:0];

    // Select whether LUT input 0 is normal I0 or carry input Ci.
    assign c_I0mux = ConfigBits[16];
    assign I0mux   = c_I0mux ? Ci : I0;

    // Same LUT address order as before:
    // {I3, I2, I1, I0mux}
    assign LUT_index = {I3, I2, I1, I0mux};

    // Behavioural LUT.
    assign O = LUT_values[LUT_index];

    // Carry-chain majority function.
    assign Co = (Ci & I1) | (Ci & I2) | (I1 & I2);

endmodule
