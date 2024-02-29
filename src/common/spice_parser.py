import os
import sys
import re


from typing import List, Dict, Any, Tuple, Union
import src.common.data_structs as rg_ds
import re

import argparse

from dataclasses import dataclass



def rec_find_inst(search_insts: List[rg_ds.SpSubCktInst], name_res: List[re.Pattern], found_insts: List[rg_ds.SpSubCktInst] = []):
    # The recursive function keeps traversing down insts tree until it finds the inst that matches names at [0], pops names, and calls itself until names is empty
    # if not name_res:
    #     return found_insts
    for inst in search_insts:
        if name_res:
            if name_res[0].search(inst.name):
                found_insts.append(inst)
                name_res.pop(0)
                # if not name_res:
                #     return found_insts
                # elif inst.subckt.insts and inst.subckt.element == "subckt":
                    # Go down into the insts of this inst's subckt
                rec_find_inst(inst.subckt.insts, name_res, found_insts)
    return found_insts
        #         else:
        #             return found_insts
        # else:
        #     return found_insts


def init_atomic_libs() -> Dict[str, rg_ds.SpSubCkt]:
    # PORT DEFS
    io_ports = {
        "in" : { 
            "name" : "n_in",
            "idx" : 0
        },
        "out" : { 
            "name" : "n_out",
            "idx" : 1
        }
    }

    mfet_ports = {
        "base" : {
            "name" : "n_b",
            "idx": 3,
        },
        "drain" : {
            "name" : "n_d",
            "idx": 0,
        },
        "gate" : {
            "name" : "n_g",
            "idx": 1,
        },
        "source" : {
            "name" : "n_s",
            "idx": 2,
        },
    }

    nfet_width_param = "Wn"
    pfet_width_param = "Wp"
    # global subckt_libs
    """
        Atomic subckts are from spice syntax and are not defined anywhere
        This means that the parameters used are always assigned during an instantiation of atomic subckts
    """    
    sp_subckt_atomic_lib = {
        "cap" : rg_ds.SpSubCkt(
            element = "cap",
            ports = io_ports,
            params = {
                "C" : "1f"
            }
        ),
        "res" : rg_ds.SpSubCkt(
            element = "res",
            ports = io_ports,
            params = {
                "R" : "1m"
            }
        ),
        "ind" : rg_ds.SpSubCkt(
            element = "ind",
            ports = io_ports,
            params = {
                "L" : "1p"
            }
        ),
        "nmos" : rg_ds.SpSubCkt(
            name = "nmos",
            element = "mnfet",
            ports = mfet_ports,
            params = {
                # "hfin" : "hfin",
                "L" : "gate_length",
                "M" : "1",
                "nfin" : f"{nfet_width_param}",
                "ASEO" : f"{nfet_width_param} * min_tran_width * trans_diffusion_length",
                "ADEO" : f"{nfet_width_param} * min_tran_width * trans_diffusion_length",
                "PSEO" : f"{nfet_width_param} * (min_tran_width + 2 * trans_diffusion_length)",
                "PDEO" : f"{nfet_width_param} * (min_tran_width + 2 * trans_diffusion_length)",
            }
        ),
        "nmos_lp" : rg_ds.SpSubCkt(
            name = "nmos_lp",
            element = "mnfet",
            ports = mfet_ports,
            params = {
                # "hfin" : "hfin",
                "L" : "gate_length",
                "M" : "1",
                "nfin" : f"{nfet_width_param}",
                "ASEO" : f"{nfet_width_param} * min_tran_width * trans_diffusion_length",
                "ADEO" : f"{nfet_width_param} * min_tran_width * trans_diffusion_length",
                "PSEO" : f"{nfet_width_param} * (min_tran_width + 2 * trans_diffusion_length)",
                "PDEO" : f"{nfet_width_param} * (min_tran_width + 2 * trans_diffusion_length)",
            }
        ),
        "pmos" : rg_ds.SpSubCkt(
            name = "pmos",
            element = "mpfet",
            ports = mfet_ports,
            params = {
                # "hfin" : "hfin",
                "L" : "gate_length",
                "M" : "1",
                "nfin" : f"{pfet_width_param}",
                "ASEO" : f"{pfet_width_param} * min_tran_width * trans_diffusion_length",
                "ADEO" : f"{pfet_width_param} * min_tran_width * trans_diffusion_length",
                "PSEO" : f"{pfet_width_param} * (min_tran_width + 2 * trans_diffusion_length)",
                "PDEO" : f"{pfet_width_param} * (min_tran_width + 2 * trans_diffusion_length)",
            }
        ),
        "pmos_lp" : rg_ds.SpSubCkt(
            name = "pmos_lp",
            element = "mpfet",
            ports = mfet_ports,
            params = {
                # "hfin" : "hfin",
                "L" : "gate_length",
                "M" : "1",
                "nfin" : f"{pfet_width_param}",
                "ASEO" : f"{pfet_width_param} * min_tran_width * trans_diffusion_length",
                "ADEO" : f"{pfet_width_param} * min_tran_width * trans_diffusion_length",
                "PSEO" : f"{pfet_width_param} * (min_tran_width + 2 * trans_diffusion_length)",
                "PDEO" : f"{pfet_width_param} * (min_tran_width + 2 * trans_diffusion_length)",
            }
        )
    }
    return sp_subckt_atomic_lib


def parse_cli_args(argv: List[str] = []):
    parser = argparse.ArgumentParser(description="Simple SPICE netlist parser")
    parser.add_argument("-i","--input_sp_files", nargs="*", type=str, help="Paths to input spice files")
    parser.add_argument("-d", "--dut_subckt_name", type=str, help="Name of the DUT subckt", default= None)
    parser.add_argument("-p", "--param_substr", type=str, help="Search for heirarchy of subckts containing this a parameter value with this substr", default= None)
    parser.add_argument("-s", "--get_structs", action='store_true', help="Returns a dictionary of parsed spice subckts")
    
    in_args = argv if argv else sys.argv[1:]

    return parser.parse_args(args = in_args)                        


def get_grab_text_re(upper_bound_re: str, lower_bound_re: str) -> re.Pattern:
    # grabs all text between upper_bound_re and lower_bound_re
    return re.compile(fr"{upper_bound_re}.*?{lower_bound_re}", re.IGNORECASE | re.DOTALL)

def get_name_re(name_str: str) -> re.Pattern:
    # returns a regex to put a the first \w+ match after a whitespace following name_str
    return re.compile(fr"{name_str}\s+(\w+)", re.IGNORECASE | re.MULTILINE)

# Regex definitions
# Grab the name of a spice library, name will be in 1st capture group
lib_name_re: re.Pattern = get_name_re(r"\.LIB") 
subckt_name_re: re.Pattern = get_name_re(r"\.SUBCKT")
# Parses the header of a subckt definition
# 1st capture group: subckt name
# 2nd capture group: port names
# 3rd capture group: param name default value pairs 
subckt_hdr_parse_re: re.Pattern = re.compile("\.SUBCKT\s+" + \
    "(\w+)\s+" + \
    "(\w+(?:\s+\w+)*)\s*" + \
    "((?:\w+=(?:\d+|\w+)\s*)+)?",
    re.IGNORECASE | re.MULTILINE
)

wspace_re: re.Pattern = re.compile(r"\s+")


param_delim: str = "="
first_occur_param_delim_re: re.Pattern = re.compile(f"{param_delim}.*?", re.IGNORECASE | re.MULTILINE)




# Print subckt heirarchy
def print_subckt_heir(subckt: rg_ds.SpSubCkt, cur_depth: int = 0, max_depth: int = None):
    msg_lines = subckt.print(summary=True)
    # print("──────" * cur_depth + msg_lines[0])
    prefix = "  " * cur_depth * 2
    if cur_depth == 0:
        print(f"{msg_lines[0]}")
    else:
        print(f"{prefix}│   └── {msg_lines[0]}")
    
    for inst in subckt.insts:
        if inst.subckt.element == "subckt":
            print_inst_heir(inst, cur_depth + 1, max_depth)
            # print_subckt_heir(inst.subckt, cur_depth + 1)

def print_inst_heir(inst: rg_ds.SpSubCktInst, cur_depth: int = 0, last_inst: bool = False, max_depth: int = None):
    msg_lines = inst.print(summary=True)
    # print("──────" * cur_depth + msg_lines[0])
    # prefix = "  " * (cur_depth) * 2
    start_spacing = " "
    if cur_depth == 1:
        print(f"{start_spacing}├── {msg_lines[0]}")
    else:
        prefix = ''.join([f"│{' ' * 4}" for _ in range(cur_depth - 1)])
        if not last_inst:
            print(f"{start_spacing}{prefix}├── {msg_lines[0]}")
        else:
            print(f"{start_spacing}{prefix}└── {msg_lines[0]}")
    if max_depth and cur_depth >= max_depth:
        return
    for i, cur_inst in enumerate(inst.subckt.insts):
        if cur_inst.subckt.element == "subckt":
            if i == len(cur_inst.subckt.insts) - 1:
                cur_last_inst = True
            else:
                cur_last_inst = False
            print_inst_heir(cur_inst, cur_depth + 1, cur_last_inst)


def trav_inst_heir(inst: rg_ds.SpSubCktInst, field: str, field_tag: str = None, cur_depth: int = 0, max_depth: int = None):

    val = getattr(inst, field)
    if val is not None:
        yield cur_depth, inst, val
    if max_depth is None or cur_depth < max_depth:
        for inst in inst.subckt.insts:
            if inst.subckt.element == "subckt":
                yield from trav_inst_heir(inst, field, field_tag, cur_depth + 1, max_depth)

def traverse_subckt_heir(subckt: rg_ds.SpSubCkt, field: str, field_tag: str = None, cur_depth: int = 0, max_depth: int = None):
    # fields and field_tags are for subckt insts not subckts
    for inst in subckt.insts:
        if inst.subckt.element == "subckt":
            yield from trav_inst_heir(inst, field, field_tag, cur_depth + 1, max_depth)        

def find_top_subckt(found_subckts: List[rg_ds.SpSubCkt], all_subckts: Dict[str, rg_ds.SpSubCkt]):
    new_found_subckts: List[rg_ds.SpSubCkt] = []
    for subckt_name, subckt in all_subckts.items():
        if subckt.element == "subckt":
            for inst in subckt.insts:
                # if we find a subckt which contains an instance of a found subckt (the original ones that we found parameters in)
                if inst.subckt.name in [f_subckt.name for f_subckt in found_subckts]:
                    new_found_subckts.append(inst.parent_subckt)
    if new_found_subckts:
        yield new_found_subckts
        yield from find_top_subckt(new_found_subckts, all_subckts)


def red_print(in_str: str): 
    print("\033[91m {}\033[00m" .format(in_str), end="")


# ASSUMES:
#   * "\n" at end of SUBCKT & ports definition
#   * parameters are defined without spaces after "=" delim unless moving onto next parameter
#       * Ex. "param1=1 param2=2" is valid, "param1= 1 param2=2" is not valid
def main(argv: List[str] = [], kwargs: Dict[str, str] = {}):
    args = parse_cli_args(argv)
    spice_fpaths = [ os.path.abspath(os.path.expanduser(fpath)) for fpath in args.input_sp_files ]
    # start with just atomic libs
    all_subckts: Dict[str, rg_ds.SpSubCkt] = init_atomic_libs()
    for fpath in spice_fpaths:
        with open(fpath, "r") as f:
            sp_text: str = f.read()
            # Grab the lib names
            lib_names: list = lib_name_re.findall(sp_text)
            for lib_name_grps in lib_names:
                # Grabbing lib name, if its a tuple, grab the first element, if its a string then it will be the only element
                # This is because of a weird behavior of re.findall where it returns
                #   a list of tuples if there are more than 1 capture groups else it returns a list of strings...
                lib_name: str = lib_name_grps if isinstance(lib_name_grps, str) else lib_name_grps[0]
                # Grabbing library text
                lib_grab_re: re.Pattern = get_grab_text_re(r"\.LIB", r"\.ENDL")
                libs_text: list = lib_grab_re.findall(sp_text)
                # Make sure its the only lib in the file
                if len(libs_text) > 1:
                    raise ValueError("Found multiple instances of lib {} in file {}".format(lib_name, fpath))
                lib_text: str = libs_text[0]
                # Grabbing lib subckts
                subckt_names: list = subckt_name_re.findall(lib_text)
                # Struct to hold subckts of this lib
                subckts: list = []
                for subckt_name_grps in subckt_names:
                    subckt_name: str  = subckt_name_grps if isinstance(subckt_name_grps, str) else subckt_name_grps[0]
                    subckt_def_str: str = f"\.SUBCKT\s+{subckt_name}\s+"
                    subckt_grab_re: re.Pattern = get_grab_text_re(subckt_def_str, r"\.ENDS")
                    subckts_text: list = subckt_grab_re.findall(lib_text)
                    if len(subckts_text) > 1:
                        raise ValueError("Found multiple instances of subckt {} in file {}".format(subckt_name, fpath))
                    subckt_text: str = subckts_text[0]
                    
                    # Parsing Individual Subckts
                    
                    # Header parsing
                    subckt_lines: list = subckt_text.split("\n") # split up subckt into lines ()
                    header_grps: re.Match = subckt_hdr_parse_re.search(subckt_lines[0]) # Take line at index 0 header definition
                    # [0] is the whole match, [1] is first cap grp, etc ...
                    subckt_name: str = header_grps[1]
                    subckt_io_ports: list[str] = wspace_re.split(header_grps[2])
                    subckt_params: list[str] = wspace_re.split(header_grps[3].strip()) if header_grps[3] else None

                    subkt_insts: list = []
                    # Instantiation Parsing
                    # Skipping header look at all lines of the subckt
                    for line in subckt_lines[1:]:
                        # Check for empty line
                        if line == "" or ".ENDS" in line or ".ends" in line or line.startswith("*"):
                            continue
                        # Check if parameters exist in the instance
                        if param_delim in line:
                            # seperate instance + ports + subckt with param portion of the string
                            line_front, line_back = first_occur_param_delim_re.split(line, maxsplit=1)
                            # This regex doesn't finish the job we need to look at the last non wspace seperated word in line_front to get our first parameter name
                            front_words: list = wspace_re.split(line_front)
                            # first param name is the last word in line_front
                            # remove last word from front_words as its a param name
                            first_param_name: str = front_words.pop(-1)
                            # Now line back is just parameter stuff
                            line_back: str = f"{first_param_name}{param_delim}{line_back}"
                            # front_words = front_words[:-1]
                        else:
                            line_back = None
                            front_words = wspace_re.split(line)
                        # Above parameter logic is more important if wspaces exist in params


                        # Check if these are atomic elements
                        if line[0].lower() == "r":
                            inst_subckt = "res"
                        elif line[0].lower() == "c":
                            inst_subckt = "cap"
                        elif line[0].lower() == "l":
                            inst_subckt = "ind"
                        else:
                            # assuming this is subckt now
                            inst_subckt : str = front_words.pop(-1) # last word in front_words is subckt
                        
                        inst_name: str = front_words.pop(0) # first word is name of instance
                        inst_ports: list[str] = front_words # remaining words are ports

                        inst_params: Dict[str, Any] = {}
                        if line_back:
                            # Parse the parameters
                            inst_param_pairs: list[str] = wspace_re.split(line_back.strip())
                            for inst_param_pair in inst_param_pairs:
                                isnt_param_name, inst_param_val = inst_param_pair.split(param_delim)
                                inst_params[isnt_param_name] = inst_param_val
                        
                        # At this point we should have all the information needed to create a subckt inst instance
                        inst: dict = {"name": inst_name, "subckt": inst_subckt, "ports": inst_ports, "params": inst_params}
                        subkt_insts.append(inst)
                        # inst: rg_ds.SpSubCktInst = rg_ds.SpSubCktInst(None, inst_name, {port: "" for port in inst_ports}, inst_params)
                    
                    # Convert port list to dict fmt
                    subckt_ports = {port: i for i, port in enumerate(subckt_io_ports)}
                    # Convert str params to dict fmt
                    #   "param1=1" -> {"param1": 1, ...}
                    if subckt_params:
                        subckt_params = {
                            (param.split(param_delim)[0]).strip(): (param.split(param_delim)[1]).strip() 
                            for param in subckt_params
                        }
                    subckt: dict = {"name": subckt_name, "ports": subckt_ports, "params": subckt_params, "insts": subkt_insts}
                    subckts.append(subckt)
        
        # Now "subckts" should be full of our subckts and their instances
        lib_subckts: List[rg_ds.SpSubCkt] = [
            rg_ds.SpSubCkt(name=subckt["name"], ports=subckt["ports"], params=subckt["params"], insts=subckt["insts"], element="subckt")
            for subckt in subckts
        ]
        for subckt in lib_subckts:
            if subckt.name in all_subckts.keys():
                raise ValueError(f"Subckt {subckt.name} already exists in the library")
            all_subckts[subckt.name] = subckt
        # Because of weird instantiation order carried from ic 3d we have to create subckts, then insts
        
        # Holds list of subckts which we haven't parsed and don't exist in our lib, ie we cannot create the Inst Object until they are parsed
        for subckt in lib_subckts:
            subckt_insts: List[rg_ds.SpSubCktInst] = []
            for inst in subckt.insts:
                if inst["subckt"] not in all_subckts.keys():
                    raise ValueError(f"Subckt {inst['subckt']} is not defined in the library")
                subckt_inst: rg_ds.SpSubCktInst = rg_ds.SpSubCktInst(
                    parent_subckt=subckt,
                    subckt = all_subckts[inst["subckt"]],
                    name = inst["name"],
                    # Assuming the ordering of the subckt ports and inst ports are the same
                    conns = {subckt_port: f"{inst_node}" for subckt_port, inst_node in zip(list(subckt.ports.keys()), inst["ports"]) }, # not caring about connections rn just heirarchy
                    param_values = inst["params"]
                )
                subckt_insts.append(subckt_inst)
            subckt.insts = subckt_insts

        # for subckt in lib_subckts:
        #     subckt.print(summary=True)


    # print header
    # dut_subckt.print(summary=True)

    # PRINT DUT SUBCKT HEIR
    # print_subckt_heir(dut_subckt, max_depth=1)

    # PRINT ALL SUBCKT HEIRS
    # for k,v in all_subckts.items():
    #     if v.element == "subckt":
    #         print_subckt_heir(v)


    # Our library of subckts is now complete, what if I want to see the heirarchy of a subckt?

    # Connectivity check?
    # for subckt_name in all_subckts.keys():
    #     dut_subckt = all_subckts[subckt_name]
    #     for subckt in find_top_subckt([dut_subckt], all_subckts):
    #         for subckt in subckt:
    #             print_subckt_heir(subckt, max_depth = 1)
    
    if args.dut_subckt_name:
        dut_subckt: rg_ds.SpSubCkt = all_subckts[args.dut_subckt_name]
        print("#"*50 + "  DUT SUBCKT HEIRARCHY  " + "#"*50)
        print_subckt_heir(dut_subckt)
        print("#"*50 + "  SUBCKTS CONTAINING DUT + HEIRARCHY  " + "#"*50)
        for subckt in find_top_subckt([dut_subckt], all_subckts):
            for subckt in subckt:
                print_subckt_heir(subckt, max_depth = 1)

    
    # TRAVERSE DUT SUBKT HEIR
    if args.param_substr:
        search_param_tag = args.param_substr
        printed_subckts: List[str] = []
        # list of all subckts which contain the serach_param tag
        found_subckts: List[rg_ds.SpSubCkt] = []
        for subckt_key in all_subckts.keys():
            dut_subckt = all_subckts[subckt_key]
            if dut_subckt.element == "subckt":
                for depth, inst, val in traverse_subckt_heir(dut_subckt, "param_values", max_depth=1):
                    if isinstance(val, dict):
                        # across param values
                        for param_val in val.values():
                            # check if our search tag is a substr of the param value
                            if search_param_tag in param_val and inst.parent_subckt.name not in printed_subckts:
                                print_subckt_heir(inst.parent_subckt)
                                # print(inst.parent_subckt.name)
                                found_subckts.append(inst.parent_subckt)
                                printed_subckts.append(inst.parent_subckt.name)

        # find all subckts which have insts of found subckts as children, create a new list of found subckts and repeat until there are no more found subckts
        printed_subckts: set = set()
        for subckts in find_top_subckt(found_subckts, all_subckts):
            for subckt in subckts:
                if subckt.name not in printed_subckts:
                    printed_subckts.add(subckt.name)
                    print_subckt_heir(subckt, max_depth = 1)

    return all_subckts
    


if __name__ == "__main__":
    main()

