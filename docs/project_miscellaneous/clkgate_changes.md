reg [7:0] mdv_inflight; // counter for how many ops are inside muldiv right now 

/*
VX_pe_switch drives this 
pe_execute_if[0] ->  VX_alu_int
pe_execute_if[1] -> VX_alu_muldiv

*/
wire mdv_in  = pe_execute_if[PE_IDX_MDV].valid && pe_execute_if[PE_IDX_MDV].ready; //1 in a cycle when an op enters muldiv
wire mdv_out = pe_result_if[PE_IDX_MDV].valid  && pe_result_if[PE_IDX_MDV].ready; //1 in a cycle when a result leaves muldiv
always @(posedge clk)
    if (reset) mdv_inflight <= '0; //forgot what the reset signal name is 
    else       mdv_inflight <= mdv_inflight + 8'(mdv_in) - 8'(mdv_out);

wire mdv_clk_en = reset
               || pe_execute_if[PE_IDX_MDV].valid   // op arriving
               || (mdv_inflight != 0);              // ops still inside

/*
Clock on if any of these is true:

reset
valid: a new op is arriving right now so keep it open this cycle
inflight != 0: ops are still inside and need to wait till finish, is this logic correct? 

Otherwise it’s 0, and muldiv’s clock stopped

*/
wire mdv_clk;
VX_clockgate mdv_icg (.clk_in(clk), .en(mdv_clk_en), .clk_out(mdv_clk)); 
// and then while instantiation, changing input clk to mdv_clk for clock 
