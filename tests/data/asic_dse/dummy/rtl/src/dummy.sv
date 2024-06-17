

module dummy #(
    parameter WIDTH = 8
)
(
    input logic clk,
    input logic rst_n,
    input logic [WIDTH-1:0] in,
    output logic [WIDTH-1:0] out
);
    // Just putting a register in here but this is a dummy module
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            out <= 8'b0;
        end else begin
            out <= in;
        end
    end
endmodule