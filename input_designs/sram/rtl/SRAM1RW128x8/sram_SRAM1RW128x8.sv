// `include sram_config.svh


// This includes the small amount of extra logic 
// 32x4096 
// module sram_1RW_4096x8 #(
//     parameter ADDR_W = 12,
//     parameter DATA_W = 8
//   )
//   (
//   input  [ADDR_W-1:0] RW0_addr,
//   input               RW0_clk,
//   input  [DATA_W-1:0] RW0_wdata,
//   input               RW0_en,
//   input               RW0_wmode, // if 1, write mode, else read mode
//   output [DATA_W-1:0] RW0_rdata,

//   );


//   logic [DATA_W-1:0] mem_0_0_I_d, mem_0_0_I_q;
//   logic [DATA_W-1:0] mem_0_0_O_d, mem_0_0_O_q;
   

  
//   wire [ADDR_W-1:0] mem_0_0_A; 
//   wire mem_0_0_CE; 
//   wire [DATA_W-1:0] mem_0_0_I; 
//   wire [DATA_W-1:0] mem_0_0_O; 
//   wire mem_0_0_CSB; 
//   wire mem_0_0_OEB; 
//   wire mem_0_0_WE;

//   assign mem_0_0_OEB = ~(~RW0_wmode & RW0_en);
//   assign mem_0_0_CSB = ~RW0_en;
//   assign mem_0_0_WEB = ~(RW0_wmode & RW0_en);
//   assign mem_0_0_A = RW0_addr;
//   assign mem_0_0_I = mem_0_0_I_d;
//   assign RW0_rdata = mem_0_0_O_d;
//   assign mem_0_0_CE = RW0_clk;

  
//   SRAM1RW4096x8 mem_0_0 (
//     .A(mem_0_0_A),
//     .CE(mem_0_0_CE),
//     .I(mem_0_0_I),
//     .O(mem_0_0_O),
//     .CSB(mem_0_0_CSB),
//     .OEB(mem_0_0_OEB),
//     .WEB(mem_0_0_WEB)
//   );


//   always_ff @(posedge RW0_clk) begin 
//     mem_0_0_I_d <= RW0_wdata;
//     mem_0_0_O_d <= mem_0_0_O;
//   end

// endmodule 


  // generate
  // /************
  // * 8 bit width SRAMs
  // ************/
  // if(ADDR_W == 12 && DATA_W == 8) begin
  //   SRAM1RW4096x8 mem_0_0 (
  //     .A(mem_0_0_A),
  //     .CE(mem_0_0_CE),
  //     .I(mem_0_0_I),
  //     .O(mem_0_0_O),
  //     .CSB(mem_0_0_CSB),
  //     .OEB(mem_0_0_OEB),
  //     .WEB(mem_0_0_WEB)
  //   );
  // end
  // else if(ADDR_W == 11 && DATA_W == 8) begin
  //   SRAM1RW2048x8 mem_0_0 (
  //     .A(mem_0_0_A),
  //     .CE(mem_0_0_CE),
  //     .I(mem_0_0_I),
  //     .O(mem_0_0_O),
  //     .CSB(mem_0_0_CSB),
  //     .OEB(mem_0_0_OEB),
  //     .WEB(mem_0_0_WEB)
  //   );
  // end
  // else if(ADDR_W == 9 && DATA_W == 8) begin
  //   SRAM1RW512x8 mem_0_0 (
  //     .A(mem_0_0_A),
  //     .CE(mem_0_0_CE),
  //     .I(mem_0_0_I),
  //     .O(mem_0_0_O),
  //     .CSB(mem_0_0_CSB),
  //     .OEB(mem_0_0_OEB),
  //     .WEB(mem_0_0_WEB)
  //   );
  // end
  // else if(ADDR_W == 4 && DATA_W == 8) begin
  //   SRAM1RW16x8 mem_0_0 (
  //     .A(mem_0_0_A),
  //     .CE(mem_0_0_CE),
  //     .I(mem_0_0_I),
  //     .O(mem_0_0_O),
  //     .CSB(mem_0_0_CSB),
  //     .OEB(mem_0_0_OEB),
  //     .WEB(mem_0_0_WEB)
  //   );
  // end
  // /************
  // * 16 bit width SRAMs
  // ************/
  // if(ADDR_W == 12 && DATA_W == 16) begin : SRAM1RW4096x16
  //   SRAM1RW4096x16 mem_0_0 (
  //     .A(mem_0_0_A),
  //     .CE(mem_0_0_CE),
  //     .I(mem_0_0_I),
  //     .O(mem_0_0_O),
  //     .CSB(mem_0_0_CSB),
  //     .OEB(mem_0_0_OEB),
  //     .WEB(mem_0_0_WEB)
  //   );
  // end
  // else if(ADDR_W == 11 && DATA_W == 16) begin
  //   SRAM1RW2048x16 mem_0_0 (
  //     .A(mem_0_0_A),
  //     .CE(mem_0_0_CE),
  //     .I(mem_0_0_I),
  //     .O(mem_0_0_O),
  //     .CSB(mem_0_0_CSB),
  //     .OEB(mem_0_0_OEB),
  //     .WEB(mem_0_0_WEB)
  //   );
  // end
  // else if(ADDR_W == 9 && DATA_W == 16) begin
  //   SRAM1RW512x16 mem_0_0 (
  //     .A(mem_0_0_A),
  //     .CE(mem_0_0_CE),
  //     .I(mem_0_0_I),
  //     .O(mem_0_0_O),
  //     .CSB(mem_0_0_CSB),
  //     .OEB(mem_0_0_OEB),
  //     .WEB(mem_0_0_WEB)
  //   );
  // end
  // else if(ADDR_W == 4 && DATA_W == 16) begin : SRAM1RW16x16
  //   SRAM1RW16x16 mem_0_0 (
  //     .A(mem_0_0_A),
  //     .CE(mem_0_0_CE),
  //     .I(mem_0_0_I),
  //     .O(mem_0_0_O),
  //     .CSB(mem_0_0_CSB),
  //     .OEB(mem_0_0_OEB),
  //     .WEB(mem_0_0_WEB)
  //   );
  // end
  // endgenerate


parameter SRAM_ADDR_W = 7;
parameter SRAM_DATA_W = 8;

// This module instantiates the ram based on user configuration
module sram_wrapper #(
    parameter ADDR_W = SRAM_ADDR_W,
    parameter DATA_W = SRAM_DATA_W
  ) 
  (
    input  [ADDR_W-1:0] RW0_addr,
    input               RW0_clk,
    input  [DATA_W-1:0] RW0_wdata,
    input               RW0_en,
    input               RW0_wmode, // if 1, write mode, else read mode
    output [DATA_W-1:0] RW0_rdata
  );

  logic [DATA_W-1:0] mem_0_0_I_d, mem_0_0_O_q;
  wire [ADDR_W-1:0] mem_0_0_A; 
  wire mem_0_0_CE; 
  wire [DATA_W-1:0] mem_0_0_I; 
  wire [DATA_W-1:0] mem_0_0_O; 
  wire mem_0_0_CSB; 
  wire mem_0_0_OEB; 
  wire mem_0_0_WE;

  assign mem_0_0_OEB = ~(~RW0_wmode & RW0_en);
  assign mem_0_0_CSB = ~RW0_en;
  assign mem_0_0_WEB = ~(RW0_wmode & RW0_en);
  assign mem_0_0_A = RW0_addr;
  assign mem_0_0_I = mem_0_0_I_d;
  assign RW0_rdata = mem_0_0_O_q;
  assign mem_0_0_CE = RW0_clk;

  /************ DO NOT REMOVE BELOW COMMENTS THEY ARE USED FOR AUTO GENERATION OF SRAM INSTANTIATION ************/
  // START SRAM INSTANTIATION HERE
  SRAM1RW128x8 mem_0_0(
    .A(mem_0_0_A),
    .CE(mem_0_0_CE),
    .I(mem_0_0_I),
    .O(mem_0_0_O),
    .CSB(mem_0_0_CSB),
    .OEB(mem_0_0_OEB),
    .WEB(mem_0_0_WEB)
  );
  // END SRAM INSTANTIATION HERE
  /************ DO NOT REMOVE ABOVE COMMENTS THEY ARE USED FOR AUTO GENERATION OF SRAM INSTANTIATION ************/


  always_ff @(posedge RW0_clk) begin 
    mem_0_0_I_d <= RW0_wdata;
    mem_0_0_O_q <= mem_0_0_O;
  end


endmodule





// module sram_1RW_2048x8 #(
//     parameter ADDR_W = 12,
//     parameter DATA_W = 8
//   )
//   (
//   input  [ADDR_W-1:0] RW0_addr,
//   input               RW0_clk,
//   input  [DATA_W-1:0] RW0_wdata,
//   input               RW0_en,
//   input               RW0_wmode, // if 1, write mode, else read mode
//   output [DATA_W-1:0] RW0_rdata,

//   );
//   wire mem_0_0_A; 
//   wire mem_0_0_CE; 
//   wire mem_0_0_I; 
//   wire mem_0_0_O; 
//   wire mem_0_0_CSB; 
//   wire mem_0_0_OEB; 
//   wire mem_0_0_WE;
  
//   assign mem_0_0_OEB = ~(~RW0_wmode & RW0_en);
//   assign mem_0_0_CSB = ~RW0_en;
//   assign mem_0_0_WEB = ~(RW0_wmode & RW0_en);
//   assign mem_0_0_A = RW0_addr;
//   assign mem_0_0_I = RW0_wdata;
//   assign RW0_rdata = mem_0_0_O;
//   SRAM1RW4096x8 mem_0_0 (
//     .A(mem_0_0_A),
//     .CE(mem_0_0_CE),
//     .I(mem_0_0_I),
//     .O(mem_0_0_O),
//     .CSB(mem_0_0_CSB),
//     .OEB(mem_0_0_OEB),
//     .WEB(mem_0_0_WEB)
//   );

// endmodule 

// module sram_1RW_512x8 #(
//     parameter ADDR_W = 12,
//     parameter DATA_W = 8
//   )
//   (
//   input  [ADDR_W-1:0] RW0_addr,
//   input               RW0_clk,
//   input  [DATA_W-1:0] RW0_wdata,
//   input               RW0_en,
//   input               RW0_wmode, // if 1, write mode, else read mode
//   output [DATA_W-1:0] RW0_rdata,

//   );
//   wire mem_0_0_A; 
//   wire mem_0_0_CE; 
//   wire mem_0_0_I; 
//   wire mem_0_0_O; 
//   wire mem_0_0_CSB; 
//   wire mem_0_0_OEB; 
//   wire mem_0_0_WE;
  
//   assign mem_0_0_OEB = ~(~RW0_wmode & RW0_en);
//   assign mem_0_0_CSB = ~RW0_en;
//   assign mem_0_0_WEB = ~(RW0_wmode & RW0_en);
//   assign mem_0_0_A = RW0_addr;
//   assign mem_0_0_I = RW0_wdata;
//   assign RW0_rdata = mem_0_0_O;
//   SRAM1RW4096x8 mem_0_0 (
//     .A(mem_0_0_A),
//     .CE(mem_0_0_CE),
//     .I(mem_0_0_I),
//     .O(mem_0_0_O),
//     .CSB(mem_0_0_CSB),
//     .OEB(mem_0_0_OEB),
//     .WEB(mem_0_0_WEB)
//   );

// endmodule 

// module sram_1RW_16x8 #(
//     parameter ADDR_W = 12,
//     parameter DATA_W = 8
//   )
//   (
//   input  [ADDR_W-1:0] RW0_addr,
//   input               RW0_clk,
//   input  [DATA_W-1:0] RW0_wdata,
//   input               RW0_en,
//   input               RW0_wmode, // if 1, write mode, else read mode
//   output [DATA_W-1:0] RW0_rdata,

//   );
//   wire mem_0_0_A; 
//   wire mem_0_0_CE; 
//   wire mem_0_0_I; 
//   wire mem_0_0_O; 
//   wire mem_0_0_CSB; 
//   wire mem_0_0_OEB; 
//   wire mem_0_0_WE;
  
//   assign mem_0_0_OEB = ~(~RW0_wmode & RW0_en);
//   assign mem_0_0_CSB = ~RW0_en;
//   assign mem_0_0_WEB = ~(RW0_wmode & RW0_en);
//   assign mem_0_0_A = RW0_addr;
//   assign mem_0_0_I = RW0_wdata;
//   assign RW0_rdata = mem_0_0_O;
//   SRAM1RW4096x8 mem_0_0 (
//     .A(mem_0_0_A),
//     .CE(mem_0_0_CE),
//     .I(mem_0_0_I),
//     .O(mem_0_0_O),
//     .CSB(mem_0_0_CSB),
//     .OEB(mem_0_0_OEB),
//     .WEB(mem_0_0_WEB)
//   );

// endmodule 

// module data_arrays_0_ext(
//   input  [11:0] RW0_addr,
//   input         RW0_clk,
//   input  [31:0] RW0_wdata,
//   output [31:0] RW0_rdata,
//   input         RW0_en,
//   input         RW0_wmode,
//   input  [3:0]  RW0_wmask
// );
//   wire [11:0] mem_0_0_A;
//   wire  mem_0_0_CE;
//   wire [7:0] mem_0_0_I;
//   wire [7:0] mem_0_0_O;
//   wire  mem_0_0_CSB;
//   wire  mem_0_0_OEB;
//   wire  mem_0_0_WEB;
//   wire [11:0] mem_0_1_A;
//   wire  mem_0_1_CE;
//   wire [7:0] mem_0_1_I;
//   wire [7:0] mem_0_1_O;
//   wire  mem_0_1_CSB;
//   wire  mem_0_1_OEB;
//   wire  mem_0_1_WEB;
//   wire [11:0] mem_0_2_A;
//   wire  mem_0_2_CE;
//   wire [7:0] mem_0_2_I;
//   wire [7:0] mem_0_2_O;
//   wire  mem_0_2_CSB;
//   wire  mem_0_2_OEB;
//   wire  mem_0_2_WEB;
//   wire [11:0] mem_0_3_A;
//   wire  mem_0_3_CE;
//   wire [7:0] mem_0_3_I;
//   wire [7:0] mem_0_3_O;
//   wire  mem_0_3_CSB;
//   wire  mem_0_3_OEB;
//   wire  mem_0_3_WEB;
//   wire [7:0] RW0_rdata_0_0 = mem_0_0_O;
//   wire [7:0] RW0_rdata_0_1 = mem_0_1_O;
//   wire [7:0] RW0_rdata_0_2 = mem_0_2_O;
//   wire [7:0] RW0_rdata_0_3 = mem_0_3_O;
//   wire [15:0] _GEN_0 = {RW0_rdata_0_1,RW0_rdata_0_0};
//   wire [23:0] _GEN_1 = {RW0_rdata_0_2,RW0_rdata_0_1,RW0_rdata_0_0};
//   wire [31:0] RW0_rdata_0 = {RW0_rdata_0_3,RW0_rdata_0_2,RW0_rdata_0_1,RW0_rdata_0_0};
//   wire [15:0] _GEN_2 = {RW0_rdata_0_1,RW0_rdata_0_0};
//   wire [23:0] _GEN_3 = {RW0_rdata_0_2,RW0_rdata_0_1,RW0_rdata_0_0};
//   wire  _GEN_4 = ~RW0_wmode;
//   wire  _GEN_5 = ~RW0_wmode & RW0_en;
//   wire  _GEN_6 = RW0_wmask[0];
//   wire  _GEN_7 = RW0_wmode & RW0_wmask[0];
//   wire  _GEN_8 = ~RW0_wmode;
//   wire  _GEN_9 = ~RW0_wmode & RW0_en;
//   wire  _GEN_10 = RW0_wmask[1];
//   wire  _GEN_11 = RW0_wmode & RW0_wmask[1];
//   wire  _GEN_12 = ~RW0_wmode;
//   wire  _GEN_13 = ~RW0_wmode & RW0_en;
//   wire  _GEN_14 = RW0_wmask[2];
//   wire  _GEN_15 = RW0_wmode & RW0_wmask[2];
//   wire  _GEN_16 = ~RW0_wmode;
//   wire  _GEN_17 = ~RW0_wmode & RW0_en;
//   wire  _GEN_18 = RW0_wmask[3];
//   wire  _GEN_19 = RW0_wmode & RW0_wmask[3];
//   SRAM1RW4096x8 mem_0_0 (
//     .A(mem_0_0_A),
//     .CE(mem_0_0_CE),
//     .I(mem_0_0_I),
//     .O(mem_0_0_O),
//     .CSB(mem_0_0_CSB),
//     .OEB(mem_0_0_OEB),
//     .WEB(mem_0_0_WEB)
//   );
//   SRAM1RW4096x8 mem_0_1 (
//     .A(mem_0_1_A),
//     .CE(mem_0_1_CE),
//     .I(mem_0_1_I),
//     .O(mem_0_1_O),
//     .CSB(mem_0_1_CSB),
//     .OEB(mem_0_1_OEB),
//     .WEB(mem_0_1_WEB)
//   );
//   SRAM1RW4096x8 mem_0_2 (
//     .A(mem_0_2_A),
//     .CE(mem_0_2_CE),
//     .I(mem_0_2_I),
//     .O(mem_0_2_O),
//     .CSB(mem_0_2_CSB),
//     .OEB(mem_0_2_OEB),
//     .WEB(mem_0_2_WEB)
//   );
//   SRAM1RW4096x8 mem_0_3 (
//     .A(mem_0_3_A),
//     .CE(mem_0_3_CE),
//     .I(mem_0_3_I),
//     .O(mem_0_3_O),
//     .CSB(mem_0_3_CSB),
//     .OEB(mem_0_3_OEB),
//     .WEB(mem_0_3_WEB)
//   );
//   assign RW0_rdata = {RW0_rdata_0_3,_GEN_1};
//   assign mem_0_0_A = RW0_addr;
//   assign mem_0_0_CE = RW0_clk;
//   assign mem_0_0_I = RW0_wdata[7:0];
//   assign mem_0_0_CSB = ~RW0_en;
//   assign mem_0_0_OEB = ~(~RW0_wmode & RW0_en);
//   assign mem_0_0_WEB = ~(RW0_wmode & RW0_wmask[0]);
//   assign mem_0_1_A = RW0_addr;
//   assign mem_0_1_CE = RW0_clk;
//   assign mem_0_1_I = RW0_wdata[15:8];
//   assign mem_0_1_CSB = ~RW0_en;
//   assign mem_0_1_OEB = ~(~RW0_wmode & RW0_en);
//   assign mem_0_1_WEB = ~(RW0_wmode & RW0_wmask[1]);
//   assign mem_0_2_A = RW0_addr;
//   assign mem_0_2_CE = RW0_clk;
//   assign mem_0_2_I = RW0_wdata[23:16];
//   assign mem_0_2_CSB = ~RW0_en;
//   assign mem_0_2_OEB = ~(~RW0_wmode & RW0_en);
//   assign mem_0_2_WEB = ~(RW0_wmode & RW0_wmask[2]);
//   assign mem_0_3_A = RW0_addr;
//   assign mem_0_3_CE = RW0_clk;
//   assign mem_0_3_I = RW0_wdata[31:24];
//   assign mem_0_3_CSB = ~RW0_en;
//   assign mem_0_3_OEB = ~(~RW0_wmode & RW0_en);
//   assign mem_0_3_WEB = ~(RW0_wmode & RW0_wmask[3]);
// endmodule