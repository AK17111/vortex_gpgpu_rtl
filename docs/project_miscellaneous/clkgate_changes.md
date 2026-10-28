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


// FILES TO LOOK INTO 
All files are in hw/rtl/core/, 

VX_alu_unit.sv . The top of the ALU. Instructions come in through dispatch_if, get split into blocks by VX_lane_dispatch, and go into the g_blocks loop. Inside the loop, pe_select decides where each instruction goes: if op_args.alu.xtype == ALU_TYPE_MULDIV it goes to muldiv, otherwise to the integer ALU. Below that are  VX_pe_switch, VX_alu_int and VX_alu_muldiv instantiations, and VX_lane_gather collects the results at the end. 

VX_pe_switch.sv . A router with one input and two outputs. The top half (VX_stream_switch) sends each instruction to the unit picked by pe_sel. The bottom half (VX_stream_arb) merges results from both units back into one stream, round-robin. data moves only in a cycle where both are 1.

VX_alu_int.sv . Integer ops that finish in one cycle: add/sub, shifts, compares, logic, LUI/AUIPC, and branches.

VX_alu_muldiv.sv . Split into two halves. Multiply (mul_valid_in) runs through a pipelined VX_multiplier with LATENCY_IMUL stages. Divide (div_valid_in) uses VX_serial_div, which takes many cycles per op. execute_if.ready picks the right half's ready signal, and a VX_stream_arb at the bottom merges mul and div results. The operands are execute_if.data.rs1_data[i] / rs2_data[i], one per lane, and the thread mask is execute_if.data.header.tmask.

The interfaces these files pass around (VX_execute_if, VX_result_if) are in hw/rtl/interfaces/. Each one is just a valid, a data struct and a ready.