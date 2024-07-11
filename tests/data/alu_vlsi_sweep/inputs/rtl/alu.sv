

module alu_ver # (
	parameter DATAW = 16,
	parameter OPS = 4,
	parameter OPCODEW = $clog2(OPS)
)(
	input clk,
    input rst,
	input signed [OPCODEW-1:0] opcode,
	input signed [DATAW-1:0] dataa,
	input signed [DATAW-1:0] datab,
	output signed [DATAW-1:0] result
);

logic [OPCODEW-1:0] r_opcode;
logic signed [DATAW-1:0] r_dataa, r_datab;
logic signed [DATAW-1:0] add_result, a_sub_b_result, b_sub_a_result;
logic signed [2*DATAW-1:0] mult_result;
logic signed [DATAW-1:0] r_result;

// dff u_dff
// (
// 	.clk(clk),
// 	.d(dataa),
// 	.q(r_dataa)
// );

always_ff @ (posedge clk) begin
    if (rst) begin
        r_dataa <= 0;
        r_datab <= 0;
        r_opcode <= 0;
        r_result <= 0;
    end 
	// Register inputs
	r_datab <= datab;
	r_opcode <= opcode;
    r_dataa <= dataa;

	// Choose outputs
	if (r_opcode == 0) begin
		r_result <= add_result;
	end else if (r_opcode == 1) begin
		r_result <= a_sub_b_result;
	end else if (r_opcode == 2) begin
		r_result <= b_sub_a_result;
	end else if (r_opcode == 3) begin
		r_result <= mult_result[DATAW-1:0];
    end else begin
        r_result <= r_result;
    end
end

always_comb begin
	add_result <= r_dataa + r_datab;
	a_sub_b_result <= r_dataa - r_datab;
	b_sub_a_result <= r_datab - r_dataa;
	mult_result <= r_dataa * r_datab;
end

assign result = r_result;

endmodule
