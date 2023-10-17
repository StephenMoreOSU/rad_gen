
// We need to make this a bit larger, ASIC tools were getting confused with a single inverter design

module inv #(
    parameter WIDTH = 52
)(
    input logic clk,
    input logic rst,
    input logic [WIDTH-1:0] in,
    output logic [WIDTH-1:0] out,
);

logic [WIDTH-1:0] in_reg;
logic [WIDTH-1:0] out_reg;

always_ff @(posedge clk) begin
    if (rst) begin
        in_reg <= 0;
        out_reg <= 0;
    end else begin
        in_reg <= in;
        out <= out_reg;
    end
end
assign out_reg = ~in_reg;

endmodule