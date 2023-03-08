import os,sys
import re

import math

def truncate(f, n):
    '''Truncates/pads a float f to n decimal places without rounding'''
    s = '{}'.format(f)
    if 'e' in s or 'E' in s:
        return '{0:.{1}f}'.format(f, n)
    i, p, d = s.partition('.')
    return '.'.join([i, (d+'0'*n)[:n]])


def decode_sram_name(sram_str):
    """ Decode the SRAM name into its parameters """
    ret_val = None
    # SRAM name format: SRAM<NUM_RW_PORTS><WIDTH>x<DEPTH>
    if("SRAM" in sram_str):
        rw_ports_re = re.compile("(?<=SRAM)\d+(?=RW)")
        depth_re = re.compile("(?<=RW)\d+(?=x)")
        width_re = re.compile("(?<=x)\d+")
        rw_ports = int(rw_ports_re.search(sram_str).group())
        width = int(width_re.search(sram_str).group())
        depth = int(depth_re.search(sram_str).group())
        ret_val = rw_ports, width, depth
    return ret_val

def compile(rw_ports,width,depth,pdk):
    env = os.environ.copy()
    if pdk == "asap7":
        pdk_path = f'{env["HAMMER_HOME"]}/src/hammer-vlsi/technology/asap7'
        sram_memories_path = f'{pdk_path}/sram_compiler/memories'
    sram_list = f'{pdk_path}/srams.txt'
    srams = open(sram_list,"r").read()
    # This is going to be a very basic, dumb sram compiler
    # deincentivize depth over width
    depth_weight = (0.06 / 4 ) # factor which is added to cost as penalty for each depthwise macro
    best_cost = float("inf")
    mapping_options = []
    for sram in srams.split("\n"):
        macro_mapping = {}
        if "SRAM" in sram:
            macro_rw_ps, macro_w, macro_d = decode_sram_name(sram)
        else:
            continue
        # we need to match the width exactly
        if width == macro_w or (macro_w < width and width % macro_w == 0) and macro_rw_ps == rw_ports:
            # mult num of macros until we get a matching width
            if(macro_w < width):
                n_w_macros = width // macro_w
            else:
                n_w_macros = 1
            num_d_macros = 1
            cur_compiled_depth = macro_d
            while cur_compiled_depth < depth:
                cur_compiled_depth += macro_d
                num_d_macros += 1
            # (n_w_macros * width_weight) * (num_d_macros * depth_weight) *
            """ number of macros in X direction * width weight * number of macros in Y direction * depth weight * read/write ports * depth """
            cur_cost = (macro_rw_ps * (cur_compiled_depth * macro_w * n_w_macros) * (1 + (num_d_macros * depth_weight))* 1e-3) # normalized by 1k
            macro_mapping = {
                "macro": sram,
                "num_rw_ports": macro_rw_ps,
                "num_w_macros" : n_w_macros,
                "num_d_macros": num_d_macros,
                "macro_w": macro_w,
                "macro_d": macro_d,
                "depth": cur_compiled_depth,
                "width": n_w_macros*macro_w,
                "macro_mapped_size": cur_compiled_depth * n_w_macros * width,
                "util_perc": (width*depth) / (cur_compiled_depth * n_w_macros * macro_w),
                "cost": truncate(cur_cost,3)
            }
            if cur_cost <= best_cost:
                best_cost = cur_cost
                mapping_options.insert(0,macro_mapping)
            # print(macro_mapping)
            #print(f"SRAM: {sram} Cost: {truncate(cur_cost,3)} Macros: [{n_w_macros}, {num_d_macros}] Macro_dims: [{macro_w}, {macro_d}]")
            #print(f"mapped_size {cur_compiled_depth * n_w_macros * width} : req_size {width*depth}")
            #print(f"SRAM: {sram} Area Increase Factor {truncate((cur_compiled_depth * n_w_macros * width) / (width*depth),3)}")
    #print(f"Best SRAM: {macro_mapping} : req_size {width, depth} req_base_cost : {truncate(width * depth,3)}")
    print(f'Best SRAM Mapping: {mapping_options[0]}')
        
    return mapping_options[0]


def write_rtl_from_mapping(mapping_dict: dict, base_sram_wrapper_path: str, outpath: str) -> tuple:
    compiled_sram_outpath = os.path.join(outpath,f'{mapping_dict["macro"]}_mapped.sv')

    mapped_addr_w = int(math.log2(mapping_dict["depth"]))
    mapped_data_w = int(mapping_dict["width"])
    """
        base_sram_wrapper = open(base_sram_wrapper_path,"r").read()
        # Modify the parameters in rtl and create new dir for the sram
        # Regex looks for parameters and will replace whole line
        edit_param_re = re.compile(f"parameter\s+SRAM_ADDR_W.*",re.MULTILINE)
        # Replace the whole line with the new parameter (log2 of depth fior SRAM_ADDR_W)
        mod_sram_rtl = edit_param_re.sub(f'parameter SRAM_ADDR_W = {mapped_addr_w};',base_sram_wrapper)
        
        edit_param_re = re.compile(f"parameter\s+SRAM_DATA_W.*",re.MULTILINE)
        # Replace the whole line with the new parameter (log2 of depth fior SRAM_ADDR_W)
        mod_sram_rtl = edit_param_re.sub(f'parameter SRAM_DATA_W = {int(mapping_dict["width"])};',mod_sram_rtl)
        # Look for the SRAM instantiation and replace the name of the sram macro, the below regex uses the comments in the rtl file to find the instantiation
        # Inst starts with "START SRAM INST" and ends with "END SRAM INST"
        edit_sram_inst_re = re.compile(f"^\s+//\s+START\sSRAM\sINST.*END\sSRAM\sINST",re.MULTILINE|re.DOTALL)
        
        sram_inst_rtl = edit_sram_inst_re.search(mod_sram_rtl).group(0)
    """

    """ SRAM MACRO MOD DEFINITIONS"""
    macro_addr_w = int(math.log2(mapping_dict['macro_d']))

    # defines the header for the sram mapped module, will need to be finished
    sram_map_port_lines = []
    for i in range(1,mapping_dict["num_rw_ports"]+1,1):
        sram_map_port_lines += [
            f"    input logic [{mapped_addr_w}-1:0] addr_{i},",
            f"    input logic [{mapped_data_w}-1:0] wdata_{i},",
            f"    output logic [{mapped_data_w}-1:0] rdata_{i},",
            f"    input logic en_{i}, ",
            f"    input logic mode_{i}, ", # 0 for read, 1 for write
        ]
    sram_map_port_lines[-1] = sram_map_port_lines[-1].replace(",","")
    top_level_mod_name = f"sram_macro_map_{mapping_dict['num_rw_ports']}x{mapping_dict['width']}x{mapping_dict['depth']}"
    sram_map_mod_lines = [
        f"module {top_level_mod_name} (",
        f"    input logic clk,",
        *sram_map_port_lines,
        f");",
    ]
    cs_dec_mod_case_lines = [
            f"        {mapped_addr_w-macro_addr_w}'b" + format(case_idx,f'0{mapped_addr_w-macro_addr_w}b') + f": out = {mapping_dict['num_d_macros']}'b" + format((1 << case_idx),f"0{mapping_dict['num_d_macros']}b") + ";"
            for case_idx in range(2**(mapped_addr_w-macro_addr_w))
    ]
    cs_dec_mod_lines = [
        f"module cs_decoder_{mapped_addr_w-macro_addr_w}_to_{mapping_dict['num_d_macros']} (",
        f"    input logic [{mapped_addr_w-macro_addr_w}-1:0] in,",
        f"    output logic [{mapping_dict['num_d_macros']}-1:0] out",
        f");",
        "always_comb begin",
        f"    case(in)",
        *cs_dec_mod_case_lines,
        f"        default: out = {mapping_dict['num_d_macros']}'b" + format(0,f"0{mapping_dict['num_d_macros']}b") + ";",
        f"    endcase",
        f"end",
        f"endmodule"
    ]
    two_to_N_mux_mod_lines = [
        "module mux #(",
        f"    parameter N = {mapped_addr_w-macro_addr_w}; ",
        f") (",
        f"    input logic [N-1:0] select,",
        f"    input logic [{mapping_dict['macro_w'] * mapping_dict['num_w_macros']}-1:0] in [2**N-1:0],",
        f"    output logic out",
        f");",
        f"    assign out = in[select];",
        f"endmodule",
    ]


    sram_macro_insts_lines = []
    macro_inst_names = []
    rdata_signal_lists = [[] for _ in range(mapping_dict["num_rw_ports"])]
    # This will loop over the entire coordinate space, decrement x_coord and increment y_coord
    for y_coord in range(mapping_dict["num_d_macros"]):
        # for x_coord in range(mapping_dict["num_w_macros"],0,-1):
        for x_coord in range(mapping_dict["num_w_macros"]):
            inst_signal_lines = []
            sram_port_lines = []
            inst_signal_assigns_lines = []
            for i in range(1,mapping_dict["num_rw_ports"]+1,1):
                inst_signal_lines += [
                    f"wire [{macro_addr_w}-1:0] mem_{x_coord}_{y_coord}_{i}_addr;",
                    f"wire [{mapping_dict['macro_w']}-1:0] mem_{x_coord}_{y_coord}_{i}_wdata;",
                    f"wire [{mapping_dict['macro_w']}-1:0] mem_{x_coord}_{y_coord}_{i}_rdata;",
                    f"wire mem_{x_coord}_{y_coord}_{i}_we;",
                    f"wire mem_{x_coord}_{y_coord}_{i}_re;",
                    f"wire mem_{x_coord}_{y_coord}_{i}_cs;",
                ]
                rdata_signal_lists[i-1].append(f"mem_{x_coord}_{y_coord}_{i}_rdata")
                # Assign the bottom lsbs of address to all macro addresses
                inst_signal_assigns_lines += [
                    f"assign mem_{x_coord}_{y_coord}_{i}_addr = addr_{i}[{macro_addr_w}-1:0];",
                    # We arrange the grid moving left to right bottom to top [0,0] is bottom left, so we want to set the MSBs of width to the 0,0 coordinate
                    # PREVIOUS when looping x coord from top to bottom First bit select of macro is width-1 : width-1 - macro_w -> -:
                    f"assign mem_{x_coord}_{y_coord}_{i}_wdata = wdata_{i}[({mapping_dict['macro_w']}*{mapping_dict['num_w_macros']-x_coord}-1)-:{mapping_dict['macro_w']}];",
                    f"assign mem_{x_coord}_{y_coord}_{i}_we = ~(mode_{i} & en_{i});",
                    f"assign mem_{x_coord}_{y_coord}_{i}_re = ~(~mode_{i} & en_{i});",
                    f"assign mem_{x_coord}_{y_coord}_{i}_cs = ~en_{i};",
                ]
                sram_port_lines += [
                    f"      .CE{i}(clk),",
                    f"      .A{i}(mem_{x_coord}_{y_coord}_{i}_addr),",
                    f"      .I{i}(mem_{x_coord}_{y_coord}_{i}_wdata),",
                    f"      .O{i}(mem_{x_coord}_{y_coord}_{i}_rdata),",
                    f"      .WEB{i}(mem_{x_coord}_{y_coord}_{i}_we),",
                    f"      .OEB{i}(mem_{x_coord}_{y_coord}_{i}_re),",
                    f"      .CSB{i}(mem_{x_coord}_{y_coord}_{i}_cs),",
                ]
            if mapping_dict["num_rw_ports"] == 1:
                sram_port_lines = [ 
                    f"      .CE(clk),",
                    f"      .A(mem_{x_coord}_{y_coord}_addr),",
                    f"      .I(mem_{x_coord}_{y_coord}_wdata),",
                    f"      .O(mem_{x_coord}_{y_coord}_rdata),",
                    f"      .WEB(mem_{x_coord}_{y_coord}_we),",
                    f"      .OEB(mem_{x_coord}_{y_coord}_re),",
                    f"      .CSB(mem_{x_coord}_{y_coord}_cs)",
                ]
            # Remove last comma from port connections
            sram_port_lines[-1] = sram_port_lines[-1].replace(",","")
            m_inst_name = f"mem_{x_coord}_{y_coord}"
            sram_inst_lines = [
                mapping_dict["macro"] + f" {m_inst_name} (",
                *sram_port_lines,
                f");",
            ]
            macro_inst_names.append(m_inst_name)
            sram_macro_insts_lines += [*inst_signal_lines,*inst_signal_assigns_lines,*sram_inst_lines]
    # Read mux output signals
    mux_signal_insts_lines = []
    mux_signal_assign_lines = []
    mux_isnt_lines = []
    for i in range(1,mapping_dict["num_rw_ports"]+1,1):
        dec_signal_insts_lines = [
            f"logic [{mapping_dict['num_d_macros']}-1:0] cs_bits_{i};"
        ]
        dec_inst_lines = [
            f"cs_decoder_{mapped_addr_w-macro_addr_w}_to_{mapping_dict['num_d_macros']} u_cs_decoder_{i} (",
            f"   .in(addr_{i}[{mapped_addr_w}-1:{mapped_addr_w-1-(mapped_addr_w-macro_addr_w)}]),",
            f"   .out(cs_bits_{i})",
            f");",
        ]
        mux_signal_insts_lines += [
            f"logic [{mapping_dict['width']}-1:0] mux_in_{i} [{mapping_dict['num_d_macros']}-1:0];",
        ]
        mux_signal_assign_lines += [
            # the below length is also the total number of macros
            f"assign mux_in_{i}[{j}] = {{{','.join(rdata_signal_lists[i-1][j*mapping_dict['num_w_macros']:(j+1)*mapping_dict['num_w_macros']])}}};"
            for j in range(len(rdata_signal_lists[i-1])//mapping_dict['num_w_macros'])
        ]

        # We need a N to 1 mux of size width
        mux_isnt_lines += [
            f"mux #(.N({mapping_dict['num_d_macros']})) u_mux_{i}_{mapping_dict['num_d_macros']}_to_1 (",
            f"   .select(cs_bits_{i}),",
            f"   .in (mux_in_{i}),",
            f"   .out(rdata_{i})",
            f");",
        ]
    
    out_fd = open(compiled_sram_outpath,"w")
    for l in sram_map_mod_lines:
        print(l,file=out_fd)
    for l in sram_macro_insts_lines:
        print(l,file=out_fd)
    for l in dec_signal_insts_lines:
        print(l,file=out_fd)
    for l in dec_inst_lines:
        print(l,file=out_fd)
    for l in mux_signal_insts_lines + mux_signal_assign_lines + mux_isnt_lines:
        print(l,file=out_fd)
    print("endmodule",file=out_fd)

    for l in two_to_N_mux_mod_lines + cs_dec_mod_lines:
        print(l,file=out_fd)

    out_fd.close()
    sram_info = {}
    mapping_dict["top_level_module"] = top_level_mod_name
    # TODO its assumed that the coordinates are inside of inst names
    mapping_dict["macro_inst_names"] = macro_inst_names
    return mapping_dict, compiled_sram_outpath

    # We need to define the wires used

    # print(sram_inst_rtl)



# def main():
#     sram_compiler(2,512,512,"asap7")


# if __name__ == "__main__":
#     main()