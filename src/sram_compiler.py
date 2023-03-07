import os,sys
import re



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

def sram_compiler(rw_ports,width,depth,pdk):
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
            cur_cost = (macro_rw_ps * (cur_compiled_depth * width * n_w_macros) * (1 + (num_d_macros * depth_weight))* 1e-3) # normalized by 1k
            macro_mapping = {
                "macro": sram,
                "num_w_macros" : n_w_macros,
                "num_d_macros": num_d_macros,
                "macro_w": macro_w,
                "macro_d": macro_d,
                "macro_mapped_size": cur_compiled_depth * n_w_macros * width,
                "area_fac": (cur_compiled_depth * n_w_macros * width) / (width*depth),
                "cost": truncate(cur_cost,3)
            }
            if cur_cost < best_cost:
                best_cost = cur_cost
                mapping_options.insert(0,macro_mapping)
            # print(macro_mapping)
            #print(f"SRAM: {sram} Cost: {truncate(cur_cost,3)} Macros: [{n_w_macros}, {num_d_macros}] Macro_dims: [{macro_w}, {macro_d}]")
            #print(f"mapped_size {cur_compiled_depth * n_w_macros * width} : req_size {width*depth}")
            #print(f"SRAM: {sram} Area Increase Factor {truncate((cur_compiled_depth * n_w_macros * width) / (width*depth),3)}")
    #print(f"Best SRAM: {macro_mapping} : req_size {width, depth} req_base_cost : {truncate(width * depth,3)}")
    print("Best SRAM Mappings")
    for i in range(len(mapping_options)):
        print(mapping_options[i])
        
    return mapping_options[0]



# def main():
#     sram_compiler(2,512,512,"asap7")


# if __name__ == "__main__":
#     main()