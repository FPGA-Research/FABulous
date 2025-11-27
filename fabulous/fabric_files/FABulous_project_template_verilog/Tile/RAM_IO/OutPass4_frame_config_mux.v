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
I0_reg=0,
I1_reg=1,
I2_reg=2,
I3_reg=3
*)
// InPassFlop2 and OutPassFlop2 are the same except for changing which side I0,I1 or O0,O1 gets connected to the top entity
module OutPass4_frame_config_mux #(parameter NoConfigBits = 4)(
    // NoConfigBits has to be adjusted manually (we don't use an arithmetic parser for the value)
    // Pin0
    input [3:0] I,
    (* FABulous, EXTERNAL *) output [3:0] O, // EXTERNAL
    // Tile IO ports from BELs
    (* FABulous, EXTERNAL, SHARED_PORT *) input UserCLK,// EXTERNAL // SHARED_PORT // ## the EXTERNAL keyword will send this signal all the way to top and the //SHARED Allows multiple BELs using the same port (e.g. for exporting a clock to the top)
    // GLOBAL all primitive pins that are connected to the switch matrix have to go before the GLOBAL label
    (* FABulous, GLOBAL *) input [NoConfigBits-1:0] ConfigBits
);

//              ______   ______
//    I////+//->|FLOP|-Q-|1 M |
//         |             |  U |//////-> O
//         +////////////-|0 X |

// I am instantiating an IOBUF primitive.
// However, it is possible to connect corresponding pins all the way to top, just by adding an "// EXTERNAL" comment (see PAD in the entity)

    reg [3:0] Q;   // FLOPs

    always @ (posedge UserCLK)
    begin
        Q <= I;
    end

    //assign O0 = ConfigBits[0] ? Q0 : I0;
    //assign O1 = ConfigBits[1] ? Q1 : I1;
    //assign O2 = ConfigBits[2] ? Q2 : I2;
    //assign O3 = ConfigBits[3] ? Q3 : I3;

    cus_mux21 cus_mux21_inst0(
    .A0(I[0]),
    .A1(Q[0]),
    .S(ConfigBits[0]),
    .X(O[0])
    );

    cus_mux21 cus_mux21_inst1(
    .A0(I[1]),
    .A1(Q[1]),
    .S(ConfigBits[1]),
    .X(O[1])
    );

    cus_mux21 cus_mux21_inst2(
    .A0(I[2]),
    .A1(Q[2]),
    .S(ConfigBits[2]),
    .X(O[2])
    );

    cus_mux21 cus_mux21_inst3(
    .A0(I[3]),
    .A1(Q[3]),
    .S(ConfigBits[3]),
    .X(O[3])
    );

endmodule
