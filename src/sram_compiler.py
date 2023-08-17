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
    width_weight = 0.01 # It costs extra routing resources to be able to connect the pins of wider macros so this is to deincentivize width
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
            util_perc = (width*depth) / (cur_compiled_depth * n_w_macros * macro_w)
            """ number of macros in X direction * width weight * number of macros in Y direction * depth weight * read/write ports * depth """
            # cur_cost = (1/(macro_rw_ps * (cur_compiled_depth * macro_w * n_w_macros) - (width*depth*rw_ports)))*(num_d_macros * depth_weight) + (n_w_macros * width_weight)
            cur_cost = (1/(util_perc + 1e-3))*(num_d_macros * depth_weight)*(n_w_macros * width_weight)
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
    # print(f'Best SRAM Mapping: {mapping_options[0]}')
    # for i in range(len(mapping_options)):
    #     print(f'Best SRAM Mapping: {mapping_options[i]}')
    
    return mapping_options[0]


def translate_sram_grid(w: int, d: int, mapping_grid: list, cut_bool: bool) -> list:
    # if cut bool is 1 then we are cutting the grid in half in the x direction (vertical cut)
    # if cut bool is 0 then we are cutting the grid in half in the y direction (horizontal cut)
    sq_val = float(w / d) if w > d else float(d / w)
    cur_bounds = [max([coord["phys_coord"][i] for coord in mapping_grid]) for i in range(2)]
    
    updated_mapping_grid = []
    mapping_idx = 0
    cut_map_limit = -1

    for coord in mapping_grid:
        new_p_coord = []
        new_p_coord.append(coord["phys_coord"][0])
        new_p_coord.append(coord["phys_coord"][1])

        # old_p_coord = coord["phys_coord"]
        if cut_bool: 
            # Veritical Cut
            if sq_val > 2.0:
                if coord["phys_coord"][0] > math.floor(cur_bounds[0] / 2):
                    new_p_coord[0] = coord["phys_coord"][0] - w // 2
                    new_p_coord[1] = coord["phys_coord"][1] + d        
            else:                   
                if coord["phys_coord"][0] > math.floor(cur_bounds[0]*3 / 4):
                    cut_map_limit = w*d * 3/4
                    new_p_coord[0] = mapping_idx % d
                    new_p_coord[1] = max([n_coord["phys_coord"][1] for n_coord in mapping_grid]) + mapping_idx // d + 1
                    mapping_idx += 1                
        else:
            if sq_val > 2.0:
                # Horizontal Cut
                if coord["phys_coord"][1] > math.floor(cur_bounds[1] / 2):
                    new_p_coord[0] = coord["phys_coord"][1] + w // 2
                    new_p_coord[1] = coord["phys_coord"][0] - d
            else:
                if coord["phys_coord"][1] > math.floor(cur_bounds[1]*3 / 4):
                    cut_map_limit = w*d * 3/4
                    new_p_coord[1] = mapping_idx % w
                    new_p_coord[0] = max([n_coord["phys_coord"][1] for n_coord in mapping_grid]) + mapping_idx // w + 1
                    mapping_idx += 1                
        
        # print(f"{old_p_coord} --> {new_p_coord}")    
        if mapping_idx >= cut_map_limit:
            mapping_idx = 0
        # Check to make sure no coords being overridden
        for n_coord in updated_mapping_grid:
            if n_coord["phys_coord"] == new_p_coord:
                print(f"ERROR: {n_coord['phys_coord']} == {new_p_coord}")
        updated_mapping_grid.append({"phys_coord": new_p_coord, "log_coord": coord["log_coord"]})
    
    cur_w = max([n_coord["phys_coord"][0] for n_coord in updated_mapping_grid]) + 1
    cur_d = max([n_coord["phys_coord"][1] for n_coord in updated_mapping_grid]) + 1
    return updated_mapping_grid, cur_w, cur_d


def translate_logical_to_phsical(mapping_dict) -> dict:
    """ This function uses the macro instantiation names as the logical mapping and returns a physical mapping"""
    digit_re = re.compile("\d+")
    macro_list = []
    # Get logical coords from the inst names
    for inst_name in mapping_dict["macro_inst_names"]:
        coords = [int(name) for name in inst_name.split("_") if digit_re.match(name)]
        macro_list.append({"log_coord": coords, "phys_coord": coords})
    
    i = 0

    cur_w = mapping_dict["num_w_macros"]
    cur_d = mapping_dict["num_d_macros"]
    prev_area = cur_w * cur_d
    # The higher this is the less square the grid will be
    # sq_val = float(cur_w / cur_d) if cur_w > cur_d else float(cur_d / cur_w) 
    sq_val = float(cur_w / cur_d) if cur_w > cur_d else float(cur_d / cur_w) 
    # stops at an aspect ratio of 2
    # while sq_val >= 2.0:
    while sq_val > 2.0:
        aspect_ratio = cur_w / cur_d
        # check to see if some threshold of squareness has been met
        if aspect_ratio > 1.0:
            macro_list, cur_w, cur_d = translate_sram_grid(cur_w,cur_d,macro_list, True)
        elif aspect_ratio < 1.0:
            macro_list, cur_w, cur_d = translate_sram_grid(cur_w,cur_d,macro_list, False)
        else:
            break
        sq_val = float(cur_w / cur_d) if cur_w > cur_d else float(cur_d / cur_w) 
        i = i + 1
    mapping_dict["macro_list"] = []
    new_area = cur_w * cur_d
    print(f"Utilization: {prev_area / new_area}")

    for inst_name in mapping_dict["macro_inst_names"]:
        coords = [int(name) for name in inst_name.split("_") if digit_re.match(name)]
        for macro_info in macro_list:
            if macro_info["log_coord"] == coords:
                mapping_dict["macro_list"].append({"inst": inst_name, "log_coord": coords, "phys_coord": macro_info["phys_coord"]})
                macro_info["phys_coord"] = coords
                break

    
    return mapping_dict
        # This means the mapping is square so we can return
        # split the grid in with a line going down center of the grid in x direction




def write_rtl_from_mapping(mapping_dict: dict, base_sram_wrapper_path: str, outpath: str) -> tuple:
    top_level_mod_name = f"sram_macro_map_{mapping_dict['num_rw_ports']}x{mapping_dict['width']}x{mapping_dict['depth']}"
    compiled_sram_outdir = os.path.join(outpath,top_level_mod_name)
    if not os.path.exists(compiled_sram_outdir):
        os.mkdir(compiled_sram_outdir)
    compiled_sram_outpath = os.path.join(compiled_sram_outdir,f"{top_level_mod_name}.sv")

    mapped_addr_w = int(math.log2(mapping_dict["depth"]))
    mapped_data_w = int(mapping_dict["width"])
    """
        # I think this was previously used to modify the existing RTL rather than create new ones, but it makes more sense to just write new RTL
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
        f"    parameter N = {mapped_addr_w-macro_addr_w} ",
        f") (",
        f"    input logic [N-1:0] select,",
        f"    input logic [{mapping_dict['macro_w'] * mapping_dict['num_w_macros']}-1:0] in [2**N-1:0],",
        f"    output logic [{mapping_dict['macro_w'] * mapping_dict['num_w_macros']}-1:0] out",
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
                    f"assign mem_{x_coord}_{y_coord}_{i}_addr = reg_addr_{i}[{macro_addr_w}-1:0];",
                    # We arrange the grid moving left to right bottom to top [0,0] is bottom left, so we want to set the MSBs of width to the 0,0 coordinate
                    # PREVIOUS when looping x coord from top to bottom First bit select of macro is width-1 : width-1 - macro_w -> -:
                    f"assign mem_{x_coord}_{y_coord}_{i}_wdata = reg_wdata_{i}[({mapping_dict['macro_w']}*{mapping_dict['num_w_macros']-x_coord}-1)-:{mapping_dict['macro_w']}];",
                    f"assign mem_{x_coord}_{y_coord}_{i}_we = ~(reg_mode_{i} & reg_en_{i});",
                    f"assign mem_{x_coord}_{y_coord}_{i}_re = ~(~reg_mode_{i} & reg_en_{i});",
                    f"assign mem_{x_coord}_{y_coord}_{i}_cs = ~reg_en_{i};",
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
    dec_signal_insts_lines = []
    dec_inst_lines = []
    sram_map_reg_lines = []
    sram_map_ff_reg_lines = [
        f"always_ff @(posedge clk) begin",
    ]
    for i in range(1,mapping_dict["num_rw_ports"]+1,1):
        sram_map_reg_lines += [
            f"logic [{mapped_addr_w}-1:0] reg_addr_{i};",
            f"logic [{mapped_data_w}-1:0] reg_wdata_{i};",
            f"logic [{mapped_data_w}-1:0] reg_rdata_{i};",
            f"logic reg_en_{i};",
            f"logic reg_mode_{i};"
        ]
        sram_map_ff_reg_lines += [ 
            f"    reg_addr_{i} <= addr_{i};",
            f"    reg_wdata_{i} <= wdata_{i};",
            f"    reg_en_{i} <= en_{i};",
            f"    reg_mode_{i} <= mode_{i};",
            f"    rdata_{i} <= reg_rdata_{i};",
        ]
        dec_signal_insts_lines += [
            f"logic [{mapping_dict['num_d_macros']}-1:0] cs_bits_{i};"
        ]
        dec_inst_lines += [
            f"cs_decoder_{mapped_addr_w-macro_addr_w}_to_{mapping_dict['num_d_macros']} u_cs_decoder_{i} (",
            f"   .in(reg_addr_{i}[{mapped_addr_w}-1:{mapped_addr_w-1-(mapped_addr_w-macro_addr_w)}]),",
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
            f"mux #(.N({mapped_addr_w-macro_addr_w})) u_mux_{i}_{mapping_dict['num_d_macros']}_to_1 (",
            f"   .select(cs_bits_{i}),",
            f"   .in (mux_in_{i}),",
            f"   .out(reg_rdata_{i})",
            f");",
        ]
    sram_map_ff_reg_lines += [
        f"end",
    ]

    out_fd = open(compiled_sram_outpath,"w")
    for l in sram_map_mod_lines:
        print(l,file=out_fd)
    for l in sram_map_reg_lines + sram_map_ff_reg_lines:
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
    mapping_dict["top_level_module"] = top_level_mod_name
    # TODO its assumed that the coordinates are inside of inst names
    mapping_dict["macro_inst_names"] = macro_inst_names
    return mapping_dict, compiled_sram_outpath

    # We need to define the wires used

    # print(sram_inst_rtl)



# def full_compile(mem_dict: dict, tech: str):
#     """Compile the memory dictionary into config and RTL files"""
#     mapping = compile(mem_dict["rw_ports"],mem_dict["w"],mem_dict["d"],tech)
#     sram_map_info, rtl_outpath = write_rtl_from_mapping()

# def main():
#     sram_compiler(2,512,512,"asap7")


# if __name__ == "__main__":
#     main()