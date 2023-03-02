 

 

 
 
 

 
parameter topology = `TOPOLOGY_MESH;

 
 
 
parameter buffer_size = 10;


 
 
 
parameter num_message_classes = 2;

 
parameter num_resource_classes = 1;

 
parameter num_vcs_per_class = 1;

 
parameter num_nodes = 64;

 
 
 
parameter num_dimensions = 2;

 
 
 
parameter num_nodes_per_router = 1;

 
parameter packet_format = `PACKET_FORMAT_EXPLICIT_LENGTH;

 
parameter flow_ctrl_type = `FLOW_CTRL_TYPE_CREDIT;

 
parameter flow_ctrl_bypass = 0;

 
parameter max_payload_length = 4;

 
parameter min_payload_length = 0;

 
parameter router_type = `ROUTER_TYPE_VC;

 
parameter enable_link_pm = 1;

 
 
 
parameter flit_data_width = 208;

 
parameter error_capture_mode = `ERROR_CAPTURE_MODE_NO_HOLD;

 
 
 
parameter restrict_turns = 1;

 
 
parameter predecode_lar_info = 1;

 
parameter routing_type = `ROUTING_TYPE_PHASED_DOR;

 
parameter dim_order = `DIM_ORDER_ASCENDING;

 
parameter input_stage_can_hold = 0;

 
parameter fb_regfile_type = `REGFILE_TYPE_FF_2D;

 
parameter fb_mgmt_type = `FB_MGMT_TYPE_STATIC;

 
parameter fb_fast_peek = 1;

 
 
 
 
parameter disable_static_reservations = 0;

 
parameter explicit_pipeline_register = 1;

 
 
parameter gate_buffer_write = 0;

 
parameter dual_path_alloc = 0;

 
 
parameter dual_path_allow_conflicts = 0;

 
parameter dual_path_mask_on_ready = 1;

 
parameter precomp_ivc_sel = 0;

 
parameter precomp_ip_sel = 0;

 
parameter elig_mask = `ELIG_MASK_FULL;

 
parameter vc_alloc_type = `VC_ALLOC_TYPE_SEP_IF;

 
parameter vc_alloc_arbiter_type = `ARBITER_TYPE_ROUND_ROBIN_BINARY;

 
parameter vc_alloc_prefer_empty = 0;

 
parameter sw_alloc_type = `SW_ALLOC_TYPE_SEP_IF;

 
parameter sw_alloc_arbiter_type = `ARBITER_TYPE_ROUND_ROBIN_BINARY;

 
parameter sw_alloc_spec_type = `SW_ALLOC_SPEC_TYPE_PRIO;

 
parameter crossbar_type = `CROSSBAR_TYPE_MUX;

parameter reset_type = `RESET_TYPE_ASYNC;
