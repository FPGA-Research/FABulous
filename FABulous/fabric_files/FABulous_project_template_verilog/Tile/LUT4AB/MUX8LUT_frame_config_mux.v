// Copyright 2021 University of Manchester
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.


(* FABulous, BelMap,
c0=0,
c1=1
*)
module MUX8LUT_frame_config_mux (A, B, C, D, E, F, G, H, S0, S1, S2, S3, M_AB, M_AD, M_AH, M_EF, ConfigBits);
	parameter NoConfigBits = 2;// has to be adjusted manually (we don't use an arithmetic parser for the value)
	// IMPORTANT: this has to be in a dedicated line
	input A; // MUX inputs
	input B;
	input C;
	input D;
	input E; 
	input F;
	input G;
	input H;
	input S0;
	input S1;
	input S2;
	input S3;
	output M_AB;
	output M_AD;
	output M_AH;
	output M_EF;
	// GLOBAL all primitive pins that are connected to the switch matrix have to go before the GLOBAL label
	(* FABulous, GLOBAL *) input [NoConfigBits-1:0] ConfigBits;

	wire AB, CD, EF, GH;
	wire sCD, sEF, sGH, sEH;
	wire AD, EH, AH;
	wire EH_GH;

	wire c0, c1;// configuration bits

	assign c0 = ConfigBits[0];
	assign c1 = ConfigBits[1];

// see figure (column-wise left-to-right)
	//assign AB = S0 ? B : A;
    my_mux2 my_mux2_AB(
    .A0(A),
    .A1(B),
    .S(S0),
    .X(AB)
    );
	//assign CD = sCD ? D : C;
    my_mux2 my_mux2_CD(
    .A0(C),
    .A1(D),
    .S(sCD),
    .X(CD)
    );
	//assign EF = sEF ? F : E;
    my_mux2 my_mux2_EF(
    .A0(E),
    .A1(F),
    .S(sEF),
    .X(EF)
    );
	//assign GH = sGH ? H : G;
    my_mux2 my_mux2_GH(
    .A0(G),
    .A1(H),
    .S(sGH),
    .X(GH)
    );

	//assign sCD = c0 ? S0 : S1;
    my_mux2 my_mux2_sCD(
    .A0(S1),
    .A1(S0),
    .S(c0),
    .X(sCD)
    );
	//assign sEF = c1 ? S0 : S2;
    my_mux2 my_mux2_sEF(
    .A0(S2),
    .A1(S0),
    .S(c1),
    .X(sEF)
    );
	//assign sGH = c0 ? sEF : sEH;
    my_mux2 my_mux2_sGH(
    .A0(sEH),
    .A1(sEF),
    .S(c0),
    .X(sGH)
    );
	//assign sEH = c1 ? S1 : S3;
    my_mux2 my_mux2_sEH(
    .A0(S3),
    .A1(S1),
    .S(c1),
    .X(sEH)
    );

	//assign AD = S1 ? CD : AB;
    my_mux2 my_mux2_AD(
    .A0(AB),
    .A1(CD),
    .S(S1),
    .X(AD)
    );
	//assign EH = sEH ? GH : EF;
    my_mux2 my_mux2_EH(
    .A0(EF),
    .A1(GH),
    .S(sEH),
    .X(EH)
    );

	//assign AH = S3 ? EH : AD;
    my_mux2 my_mux2_AH(
    .A0(AD),
    .A1(EH),
    .S(S3),
    .X(AH)
    );

	//assign EH_GH = c0 ? EH : GH;
    my_mux2 my_mux2_EH_GH(
    .A0(GH),
    .A1(EH),
    .S(c0),
    .X(EH_GH)
    );

	assign M_AB = AB;
	//assign M_AD = c0 ? AD : CD;
    my_mux2 my_mux2_M_AD(
    .A0(CD),
    .A1(AD),
    .S(c0),
    .X(M_AD)
    );
	//assign M_AH = c1 ? AH : EH_GH;
    my_mux2 my_mux2_M_AH(
    .A0(EH_GH),
    .A1(AH),
    .S(c1),
    .X(M_AH)
    );
	assign M_EF = EF;

endmodule
