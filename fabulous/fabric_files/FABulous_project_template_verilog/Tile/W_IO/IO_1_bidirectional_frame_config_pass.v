`default_nettype none

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



module IO_1_bidirectional_frame_config_pass (
    input I,  // from fabric to external pin
    input T,  // tristate control
    output O,  // from external pin to fabric
    output reg Q,  // from external pin to fabric (registered)
These ports need to be available at the top-level, not the switch matrix
    (* FABulous, EXTERNAL *) output I_top,
    (* FABulous, EXTERNAL *) output T_top,
    (* FABulous, EXTERNAL *) input O_top,
    // The EXTERNAL keyword will send this signal all the way to top and the
    // SHARED Allows multiple BELs using the same port (e.g. for exporting a clock to the top)
    (* FABulous, EXTERNAL, SHARED_PORT *) input UserCLK
    // GLOBAL all primitive pins that are connected to the switch matrix have to go before the GLOBAL label
);  //, ConfigBits);
    //                        _____
    //    I////-T_DRIVER////->|PAD|//+//////-> O
    //              |         ////-  |
    //    T////////-+                +//>FF//> Q

    // I am instantiating an IOBUF primitive.
    // However, it is possible to connect corresponding pins all the way to top, just by adding an "// EXTERNAL" comment (see PAD in the entity)
    assign O = O_top;

    always @(posedge UserCLK) begin
        Q <= O_top;
    end

    assign I_top = I;
    assign T_top = ~T;


endmodule
`default_nettype wire
