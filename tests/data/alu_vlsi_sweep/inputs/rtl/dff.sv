module dff # (
    parameter DATAW = 16
)
(
    input logic clk,
    input logic [DATAW-1:0] d,
    output logic [DATAW-1:0] q
);
    always_ff @(posedge clk) begin
        q <= d;
    end
endmodule



