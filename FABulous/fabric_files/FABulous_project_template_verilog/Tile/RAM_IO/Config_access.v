(* FABulous, BelMap,
C_bit0=0,
C_bit1=1,
C_bit2=2,
C_bit3=3
*)
module Config_access (C_bit0, C_bit1, C_bit2, C_bit3, ConfigBits);
	parameter NoConfigBits = 4;// has to be adjusted manually (we don't use an arithmetic parser for the value)
	// Pin0
	(* FABulous, EXTERNAL *)output C_bit0; // EXTERNAL
	(* FABulous, EXTERNAL *)output C_bit1; // EXTERNAL
	(* FABulous, EXTERNAL *)output C_bit2; // EXTERNAL
	(* FABulous, EXTERNAL *)output C_bit3; // EXTERNAL
	// GLOBAL all primitive pins that are connected to the switch matrix have to go before the GLOBAL label
	(* FABulous, GLOBAL *)input [NoConfigBits-1:0] ConfigBits;

	// we just wire configuration bits to fabric top
	assign C_bit0 = ConfigBits[0];
	assign C_bit1 = ConfigBits[1];
	assign C_bit2 = ConfigBits[2];
	assign C_bit3 = ConfigBits[3];

endmodule
