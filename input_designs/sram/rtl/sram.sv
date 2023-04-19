parameter SRAM_ADDR_W = 4;
parameter SRAM_DATA_W = 16;

// This module instantiates the ram based on user configuration
module sram_wrapper #(
    parameter ADDR_W = SRAM_ADDR_W,
    parameter DATA_W = SRAM_DATA_W
  ) 
  (
    `ifdef DUAL_PORT
      input               clk,
      input  [ADDR_W-1:0] RW0_addr_1,
      input  [DATA_W-1:0] RW0_wdata_1,
      input               RW0_en_1,
      input               RW0_wmode_1, // if 1, write mode, else read mode
      output [DATA_W-1:0] RW0_rdata_1,
      input  [ADDR_W-1:0] RW0_addr_2,
      input  [DATA_W-1:0] RW0_wdata_2,
      input               RW0_en_2,
      input               RW0_wmode_2, // if 1, write mode, else read mode
      output [DATA_W-1:0] RW0_rdata_2
    `else
      input  [ADDR_W-1:0] RW0_addr,
      input               clk,
      input  [DATA_W-1:0] RW0_wdata,
      input               RW0_en,
      input               RW0_wmode, // if 1, write mode, else read mode
      output [DATA_W-1:0] RW0_rdata
    `endif
  );

  `ifdef DUAL_PORT
    logic [DATA_W-1:0] mem_0_0_I_d_1, mem_0_0_O_q_1;
    logic addr_q_1;
    logic OEB_q_1;
    logic CSB_q_1;
    logic WEB_q_1;
    
    logic [DATA_W-1:0] mem_0_0_I_d_2, mem_0_0_O_q_2;
    logic addr_q_2;
    logic OEB_q_2;
    logic CSB_q_2;
    logic WEB_q_2;

    wire [ADDR_W-1:0] mem_0_0_A_1; 
    wire mem_0_0_CE_1; 
    wire [DATA_W-1:0] mem_0_0_I_1; 
    wire [DATA_W-1:0] mem_0_0_O_1; 
    wire mem_0_0_CSB_1; 
    wire mem_0_0_OEB_1; 
    wire mem_0_0_WE_1;
    
    wire [ADDR_W-1:0] mem_0_0_A_2; 
    wire mem_0_0_CE_2; 
    wire [DATA_W-1:0] mem_0_0_I_2; 
    wire [DATA_W-1:0] mem_0_0_O_2; 
    wire mem_0_0_CSB_2; 
    wire mem_0_0_OEB_2; 
    wire mem_0_0_WE_2;

    assign mem_0_0_OEB_1 = OEB_q_1;
    assign mem_0_0_CSB_1 = CSB_q_1;
    assign mem_0_0_WEB_1 = WEB_q_1;
    assign mem_0_0_A_1 = addr_q_1;
    assign mem_0_0_I_1 = mem_0_0_I_d_1;
    assign RW0_rdata_1 = mem_0_0_O_q_1;
    assign mem_0_0_CE_1 = clk;

    assign mem_0_0_OEB_2 = OEB_q_2;
    assign mem_0_0_CSB_2 = CSB_q_2;
    assign mem_0_0_WEB_2 = WEB_q_2;
    assign mem_0_0_A_2 = addr_q_2;
    assign mem_0_0_I_2 = mem_0_0_I_d_2;
    assign RW0_rdata_2 = mem_0_0_O_q_2;
    assign mem_0_0_CE_2 = clk;

    always_ff @(posedge clk) begin 
      // port 1
      mem_0_0_I_d_1 <= RW0_wdata_1;
      mem_0_0_O_q_1 <= mem_0_0_O_1;
      addr_q_1 <= RW0_addr_1;
      OEB_q_1 <= ~(~RW0_wmode_1 & RW0_en_1);
      CSB_q_1 <= ~RW0_en_1;
      WEB_q_1 <= ~(RW0_wmode_1 & RW0_en_1);
      // port 2
      mem_0_0_I_d_2 <= RW0_wdata_2;
      mem_0_0_O_q_2 <= mem_0_0_O_2;
      addr_q_2 <= RW0_addr_2;
      OEB_q_2 <= ~(~RW0_wmode_2 & RW0_en_2);
      CSB_q_2 <= ~RW0_en_2;
      WEB_q_2 <= ~(RW0_wmode_2 & RW0_en_2);
    end
  `else
    logic [DATA_W-1:0] mem_0_0_I_d, mem_0_0_O_q;
    logic addr_q;
    logic OEB_q;
    logic CSB_q;
    logic WEB_q;

    wire [ADDR_W-1:0] mem_0_0_A; 
    wire mem_0_0_CE; 
    wire [DATA_W-1:0] mem_0_0_I; 
    wire [DATA_W-1:0] mem_0_0_O; 
    wire mem_0_0_CSB; 
    wire mem_0_0_OEB; 
    wire mem_0_0_WE;

    assign mem_0_0_OEB = OEB_q;
    assign mem_0_0_CSB = CSB_q;
    assign mem_0_0_WEB = WEB_q;
    assign mem_0_0_A = addr_q;
    assign mem_0_0_I = mem_0_0_I_d;
    assign RW0_rdata = mem_0_0_O_q;
    assign mem_0_0_CE = clk;
    
    always_ff @(posedge clk) begin 
      mem_0_0_I_d <= RW0_wdata;
      mem_0_0_O_q <= mem_0_0_O;
      addr_q <= RW0_addr;
      OEB_q <= ~(~RW0_wmode & RW0_en);
      CSB_q <= ~RW0_en;
      WEB_q <= ~(RW0_wmode & RW0_en);
    end
  `endif

  `ifndef DUAL_PORT
    /************ DO NOT REMOVE BELOW COMMENTS THEY ARE USED FOR AUTO GENERATION OF SRAM INSTANTIATION ************/
    // START SRAM 1PORT INSTANTIATION HERE
    SRAM1RW16x16 mem_0_0(
      .A(mem_0_0_A),
      .CE(mem_0_0_CE),
      .I(mem_0_0_I),
      .O(mem_0_0_O),
      .CSB(mem_0_0_CSB),
      .OEB(mem_0_0_OEB),
      .WEB(mem_0_0_WEB)
    );
    // END SRAM 1PORT INSTANTIATION HERE
    /************ DO NOT REMOVE ABOVE COMMENTS THEY ARE USED FOR AUTO GENERATION OF SRAM INSTANTIATION ************/
  `else
    /************ DO NOT REMOVE BELOW COMMENTS THEY ARE USED FOR AUTO GENERATION OF SRAM INSTANTIATION ************/
    // START SRAM 2PORT INSTANTIATION HERE
    SRAM2RW16x16 mem_0_0(
      .A1(mem_0_0_A_1),
      .CE1(mem_0_0_CE_1),
      .I1(mem_0_0_I_1),
      .O1(mem_0_0_O_1),
      .CSB1(mem_0_0_CSB_1),
      .OEB1(mem_0_0_OEB_1),
      .WEB1(mem_0_0_WEB_1),
      .A2(mem_0_0_A_2),
      .CE2(mem_0_0_CE_2),
      .I2(mem_0_0_I_2),
      .O2(mem_0_0_O_2),
      .CSB2(mem_0_0_CSB_2),
      .OEB2(mem_0_0_OEB_2),
      .WEB2(mem_0_0_WEB_2)
    );
    // END SRAM 2PORT INSTANTIATION HERE
    /************ DO NOT REMOVE ABOVE COMMENTS THEY ARE USED FOR AUTO GENERATION OF SRAM INSTANTIATION ************/
  `endif




endmodule


