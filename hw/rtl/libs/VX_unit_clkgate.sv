// Copyright © 2019-2023
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
// http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

`include "VX_define.vh"

// VX_unit_clkgate - wrapper for existing icg with reset, valid and inflight tracker
//
// Counts ops inside the unit (+1 when one is accepted, -1 when its result
// leaves) and lets the clock through only while there is work:
//
//   en = reset || req_valid || (inflight != 0) || busy
//
//   req_valid : an op is at the unit's input (wake up this cycle)
//   req_fire  : the unit accepted an op (valid && ready)
//   rsp_fire  : a result left the unit   (valid && ready)
//   busy      : anything else that needs a clock edge, e.g. a registered
//               side output that must clear one cycle after an op
//
// The counter runs on the free-running clk so it can see the next op
// arrive while the unit is gated. Each accepted op must produce exactly
// one result (rsp_fire), or the counter would never return to zero.

module VX_unit_clkgate #(
    parameter CTR_WIDTH = 8
) (
    input  wire clk,        // free-running clock
    input  wire reset,
    input  wire req_valid,
    input  wire req_fire,
    input  wire rsp_fire,
    input  wire busy,
    output wire clk_out     // gated clock for the unit
);

    reg [CTR_WIDTH-1:0] inflight;

    always @(posedge clk) begin
        if (reset) begin
            inflight <= '0;
        end else begin
            inflight <= inflight + CTR_WIDTH'(req_fire) - CTR_WIDTH'(rsp_fire);
        end
    end

    wire clk_en = reset || req_valid || (inflight != '0) || busy;

    VX_clockgate icg (
        .clk_in  (clk),
        .en      (clk_en),
        .clk_out (clk_out)
    );

    // a result can't leave an empty unit, and the counter can't wrap
    `RUNTIME_ASSERT(~rsp_fire || req_fire || (inflight != '0), ("VX_unit_clkgate: result with nothing in flight"))
    `RUNTIME_ASSERT(~req_fire || rsp_fire || (inflight != '1), ("VX_unit_clkgate: in-flight counter overflow"))

endmodule