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

// Configurable 8-input fracturable MUX tree for LUT composition
//
// Depending on config bits c0 and c1, this module can operate as:
//   c0=0, c1=0: Four independent 2:1 muxes (AB, CD, EF, GH)
//   c0=1, c1=0: Two independent 4:1 muxes (AD, EH)
//   c0=1, c1=1: One 8:1 mux (AH)
//
//                  Stage 1           Stage 2           Stage 3
//
//                 +------+          +------+          +------+
//  A ------------>|0  AB |--------->|0  AD |--------->|0  AH |
//  B ------------>|1     |    +---->|1     |    +---->|1     |
//                 +------+    |     +------+    |     +------+
//                   ^         |       ^         |       ^
//                  S[0]       |      S[1]       |      S[3]
//                 +------+    |                 |
//  C ------------>|0  CD |----+                 |
//  D ------------>|1     |                      |
//                 +------+                      |
//                   ^                           |
//                  sCD                          |
//                 +------+          +------+    |
//  E ------------>|0  EF |--------->|0  EH |----+
//  F ------------>|1     |    +---->|1     |
//                 +------+    |     +------+
//                   ^         |       ^
//                  sEF        |      sEH
//                 +------+    |
//  G ------------>|0  GH |----+
//  H ------------>|1     |
//                 +------+
//                   ^
//                  sGH
//
// Output muxes (controlled by config bits c0, c1):
//   M_AB = AB (direct)
//   M_AD = c0 ? AD : CD
//   M_EF = EF (direct)
//   M_AH = c1 ? AH : (c0 ? EH : GH)
//
// Select signal generation (config-dependent):
//   sCD = c0 ? S[0] : S[1]    sEF = c1 ? S[0] : S[2]
//   sEH = c1 ? S[1] : S[3]    sGH = c0 ? sEF  : sEH
//
(* FABulous, BelMap,
c0=0,
c1=1
*)
module MUX8LUT_frame_config_mux #(parameter NoConfigBits = 2)(
    // ConfigBits has to be adjusted manually (we don't use an arithmetic parser for the value)
    input A, // MUX inputs
    input B,
    input C,
    input D,
    input E,
    input F,
    input G,
    input H,
    input [3:0] S,
    output M_AB,
    output M_AD,
    output M_AH,
    output M_EF,
    // GLOBAL all primitive pins that are connected to the switch matrix have to go before the GLOBAL label
    (* FABulous, GLOBAL *) input [NoConfigBits-1:0] ConfigBits
);

    wire AB, CD, EF, GH;
    wire sCD, sEF, sGH, sEH;
    wire AD, EH, AH;
    wire EH_GH;

    wire c0, c1;// configuration bits

    assign c0 = ConfigBits[0];
    assign c1 = ConfigBits[1];

    cus_mux21 cus_mux21_AB(
    .A0(A),
    .A1(B),
    .S(S[0]),
    .X(AB)
    );
    cus_mux21 cus_mux21_CD(
    .A0(C),
    .A1(D),
    .S(sCD),
    .X(CD)
    );
    cus_mux21 cus_mux21_EF(
    .A0(E),
    .A1(F),
    .S(sEF),
    .X(EF)
    );
    cus_mux21 cus_mux21_GH(
    .A0(G),
    .A1(H),
    .S(sGH),
    .X(GH)
    );

    cus_mux21 cus_mux21_sCD(
    .A0(S[1]),
    .A1(S[0]),
    .S(c0),
    .X(sCD)
    );
    cus_mux21 cus_mux21_sEF(
    .A0(S[2]),
    .A1(S[0]),
    .S(c1),
    .X(sEF)
    );
    cus_mux21 cus_mux21_sGH(
    .A0(sEH),
    .A1(sEF),
    .S(c0),
    .X(sGH)
    );
    cus_mux21 cus_mux21_sEH(
    .A0(S[3]),
    .A1(S[1]),
    .S(c1),
    .X(sEH)
    );

    cus_mux21 cus_mux21_AD(
    .A0(AB),
    .A1(CD),
    .S(S[1]),
    .X(AD)
    );
    cus_mux21 cus_mux21_EH(
    .A0(EF),
    .A1(GH),
    .S(sEH),
    .X(EH)
    );

    cus_mux21 cus_mux21_AH(
    .A0(AD),
    .A1(EH),
    .S(S[3]),
    .X(AH)
    );

    cus_mux21 cus_mux21_EH_GH(
    .A0(GH),
    .A1(EH),
    .S(c0),
    .X(EH_GH)
    );

    assign M_AB = AB;
    cus_mux21 cus_mux21_M_AD(
    .A0(CD),
    .A1(AD),
    .S(c0),
    .X(M_AD)
    );
    cus_mux21 cus_mux21_M_AH(
    .A0(EH_GH),
    .A1(AH),
    .S(c1),
    .X(M_AH)
    );
    assign M_EF = EF;

endmodule
