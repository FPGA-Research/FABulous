`default_nettype none

(* FABulous, BelMap,
    C_bit0=0,
    C_bit1=1,
    C_bit2=2,
    C_bit3=3
*)

module Config_access #(
        parameter integer NoConfigBits = 4
    ) (
        // ConfigBits has to be adjusted manually (we don't use an arithmetic parser for the value)
        (* FABulous, EXTERNAL *) output [3:0] C_bit,
        // All primitive pins that are connected to the switch matrix have to go before the "GLOBAL" label
        (* FABulous, GLOBAL *) input [NoConfigBits-1:0] ConfigBits
    );
    // Configuration bits are wired to the fabric top module so that fabric-external functionality
    // can be controlled from the user design
    assign C_bit = ConfigBits;

endmodule
`default_nettype wire
