reg [7:0] mdv_inflight;
wire mdv_in  = pe_execute_if[PE_IDX_MDV].valid && pe_execute_if[PE_IDX_MDV].ready;
wire mdv_out = pe_result_if[PE_IDX_MDV].valid  && pe_result_if[PE_IDX_MDV].ready;
always @(posedge clk)
    if (reset) mdv_inflight <= '0;
    else       mdv_inflight <= mdv_inflight + 8'(mdv_in) - 8'(mdv_out);

wire mdv_clk_en = reset
               || pe_execute_if[PE_IDX_MDV].valid   // op arriving
               || (mdv_inflight != 0);              // ops still inside
wire mdv_clk;
VX_clockgate mdv_icg (.clk_in(clk), .en(mdv_clk_en), .clk_out(mdv_clk));
// and then while instantiation, changing input clk to mdv_clk for clock 