
#import ..hammer.src.hammer_config 
# The below function parses hammer IR
# load_config_from_paths([config.yamls])

import argparse
import sys, os
import subprocess as sp
import shlex
import re

import json
import yaml


import time
import math

import copy

import csv
import pandas as pd

import src.sram_compiler as sram_compiler 

########################################## DATA STRUCTURES  ###########################################



########################################## DATA STRUCTURES  ###########################################



########################################## GENERAL UTILITIES ##########################################

def flatten_mixed_list(input_list):
    """
    Flattens a list with mixed value Ex. ["hello", ["billy","bob"],[["johnson"]]] -> ["hello", "billy","bob","johnson"]
    """
    # Create flatten list lambda function
    flat_list = lambda input_list:[element for item in input_list for element in flat_list(item)] if type(input_list) is list else [input_list]
    # Call lambda function
    flattened_list = flat_list(input_list)
    return flattened_list

def run_shell_cmd(cmd_str,log_file):
    run_cmd = cmd_str + f" | tee {log_file}"
    rad_gen_log(f"Running: {run_cmd}",rad_gen_log_fd)
    sp.call(run_cmd,shell=True,executable='/bin/bash',env=cur_env)

def rec_get_flist_of_ext(design_dir_path):
    """
    Takes in a path and recursively searches for all files of specified extension, returns dirs of those files and file paths in two lists
    """
    hdl_exts = ['.v','.sv']
    hdl_exts = [f"({ext})" for ext in hdl_exts]

    design_files = []
    ext_str = ".*" + '|'.join(hdl_exts)
    ext_re = re.compile(ext_str)
    design_folder = os.path.expanduser(design_dir_path)
    design_files = [os.path.abspath(os.path.join(r,fn)) for r, _, fs in os.walk(design_folder) for fn in fs if ext_re.search(fn)]
    design_dirs = [os.path.abspath(r) for r, _, fs in os.walk(design_folder) for fn in fs if ext_re.search(fn)]
    design_dirs = list(dict.fromkeys(design_dirs))

    return design_files,design_dirs

def file_write_ln(fd, line):
  """
  writes a line to a file with newline after
  """
  fd.write(line + "\n")

def edit_config_file(config_fpath, config_dict):
    """
    Super useful function which I have needed in multiple tools, take in a dict of key value pairs and replace them in a config file,
    will keep it to yaml specification for now.
    """
    #read in config file as text
    with open(config_fpath, 'r') as f:
        config_text = f.read()

    for key, value in config_dict.items():
        key_re = re.compile(f"{key}:.*",re.MULTILINE)
        
        if(isinstance(value,list)):
            val_str = "\", \"".join(value)
            repl_str = f"{key}: [{val_str}]"
        else:    
            repl_str = f"{key}: {value}"
        #replace relevant configs
        config_text = key_re.sub(repl=repl_str,string=config_text)        
    
    with open(config_fpath, 'w') as f:
        f.write(config_text)


########################################## GENERAL UTILITIES ##########################################

def write_lib_to_db_script(obj_dir):
    # create PT run-dir
    pt_outpath = os.path.join(obj_dir,"pt-rundir")
    if not os.path.isdir(pt_outpath) :
        os.mkdir(pt_outpath)
    lib_dir = os.path.join(obj_dir,"tech-asap7-cache/LIB/NLDM")

    file_lines = ["enable_write_lib_mode"]
    for lib in os.listdir(lib_dir):
        read_lib_cmd = "read_lib " + f"{os.path.join(lib_dir,lib)}"
        write_lib_cmd = "write_lib " + f"{os.path.splitext(lib)[0]} " + "-f db " + "-o " f"{os.path.splitext(os.path.join(lib_dir,lib))[0]}.db"
        file_lines.append(read_lib_cmd)
        file_lines.append(write_lib_cmd)

    
    fd = open(os.path.join(pt_outpath,"lib_to_db.tcl"),"w")
    for line in file_lines:
        file_write_ln(fd,line)
    file_write_ln(fd,"quit")
    fd.close()


########################################## PRIMETIME ##########################################

def write_pt_sdc(power_in_json_data, obj_dir):
    """
    Writes an sdc file in the format which will match the output of innovus par stage.
    """

    # create PT run-dir
    pt_outpath = os.path.join(obj_dir,"pt-rundir")
    if not os.path.isdir(pt_outpath) :
        os.mkdir(pt_outpath)

    dec_re = re.compile(r"\d+\.{0,1}\d*")
    clock_fac = 1.0
    if "us" in power_in_json_data["vlsi.inputs.clocks"][0]["period"]:
        clock_fac = 1e6 * clock_fac
    elif "ns" in power_in_json_data["vlsi.inputs.clocks"][0]["period"]:
        clock_fac = 1e3 * clock_fac
    elif "ps" in power_in_json_data["vlsi.inputs.clocks"][0]["period"]:
        clock_fac = 1.0 * clock_fac
    
    clk_period_ps = float(dec_re.search(power_in_json_data["vlsi.inputs.clocks"][0]["period"]).group(0)) * clock_fac

    file_lines = [
        "#"*68,
        "# Created by rad_gen.py for ASAP7 connection from Cadence Innovus par to Synopsys Primetime",
        "#"*68,
        "set sdc_version 2.0",
        "set_units -time ps -resistance kOhm -capacitance pF -voltage V -current mA",
        "create_clock [get_ports clk] -period " + f"{clk_period_ps} " + f"-waveform {{0.0 {clk_period_ps/2.0}}}",
    ]
    fname = "pt.sdc"
    fd = open(os.path.join(pt_outpath,fname),"w")
    for line in file_lines:
        file_write_ln(fd,line)
    fd.close()

def write_pt_timing_script(power_in_json_data, obj_dir, args):
    """
    writes the tcl script for timing analysis using Synopsys Design Compiler, tested under 2017 version
    This should look for setup/hold violations using the worst case (hold) and best case (setup) libs
    """

    # Make sure that the $STDCELLS env var is set and use it to find the .lib files to use for Primetime
    search_paths = "/CMC/tools/synopsys/syn_vN-2017.09/libraries/syn /CMC/tools/synopsys/syn_vN-2017.09/libraries/syn_ver /CMC/tools/synopsys/syn_vN-2017.09/libraries/sim_ver"
    
    db_dir =  os.path.join(os.getcwd(),"asap7_db_libs")

    # options are ["TT","FF","SS"]
    corner_filt_str = "SS"
    # options are ["SLVT", "LVT", "RVT", "SRAM"] in order of decreasing drive strength
    transistor_type_str = "LVT"
    target_libs = " ".join([os.path.join(db_dir,lib) for lib in os.listdir(db_dir) if (lib.endswith(".db") and corner_filt_str in lib and transistor_type_str in lib)])
    
    #default switching probability (TODO) find where this is and make it come from there
    switching_prob = "0.5"

    # create PT run-dir
    pt_outpath = os.path.join(obj_dir,"pt-rundir")
    if not os.path.isdir(pt_outpath) :
        os.mkdir(pt_outpath)

    # create reports dir
    report_path = os.path.join(pt_outpath,"reports")
    if not os.path.isdir(report_path) :
        os.mkdir(report_path)

    # get pnr output path (should be in this format)
    pnr_design_outpath = os.path.join(obj_dir,"par-rundir",f'{args["top_level"]}_FINAL')
    if not os.path.isdir(pnr_design_outpath) :
        rad_gen_log("Couldn't find output of pnr stage, Exiting...",rad_gen_log_fd)
        sys.exit(1)


    # report timing / power commands
    report_timing_cmd = "report_timing > " + os.path.join(report_path,"timing.rpt")
    report_power_cmd = "report_power > " + os.path.join(report_path,"power.rpt")



    case_analysis_cmds = ["#MULTIMODAL ANALYSIS DISABLED"]
        
    #get switching activity and toggle rates from power_constraints tcl file
    power_constraints_fd = open(os.path.join(pnr_design_outpath,f'{args["top_level"]}_power_constraints.tcl'),"r")
    power_constraints_lines = power_constraints_fd.readlines()
    toggle_rate_var = "seq_activity"
    grab_opt_val_re = re.compile(f"(?<={toggle_rate_var}\s).*")
    toggle_rate = ""
    for line in power_constraints_lines:
        if "set_default_switching_activity" in line:
            toggle_rate = str(grab_opt_val_re.search(line).group(0))

    power_constraints_fd.close()

    switching_activity_cmd = "set_switching_activity -static_probability " + switching_prob + " -toggle_rate " + toggle_rate + " -base_clock $my_clock_pin -type inputs"

    #backannotate into primetime
    #This part should be reported for all the modes in the design.
    file_lines = [
        "set sh_enable_page_mode true",
        "set search_path " + f"\"{search_paths}\"",
        "set my_top_level " + power_in_json_data["power.inputs.top_module"],
        "set my_clock_pin " + power_in_json_data["vlsi.inputs.clocks"][0]["name"],
        "set target_library " + f"\"{target_libs}\"",
        "set link_library " + "\"* $target_library\"",
        "read_verilog " + power_in_json_data["power.inputs.netlist"],
        "current_design $my_top_level",
        case_analysis_cmds,
        "link",
        #set clock constraints (this can be done by defining a clock or specifying an .sdc file)
        #read constraints file
        f"read_sdc -echo {pt_outpath}/pt.sdc",
        #Standard Parasitic Exchange Format. File format to save parasitic information extracted by the place and route tool.
        # Just taking index 0 which is the 100C corner for case of high power
        "read_parasitics -increment " + power_in_json_data["power.inputs.spefs"][0],
        report_timing_cmd,
        "set power_enable_analysis TRUE",
        "set power_analysis_mode \"averaged\"",
        switching_activity_cmd,
        report_power_cmd,
        "quit",
    ]
    file_lines = flatten_mixed_list(file_lines)

    fname = os.path.join(pt_outpath,"pt_analysis.tcl")
    fd = open(fname, "w")
    for line in file_lines:
        file_write_ln(fd,line)
    fd.close()

    return
########################################## PRIMETIME ##########################################


########################################## HAMMER UTILITIES ##########################################

def get_hammer_config(flow_stage_trans,config_paths, args, obj_dir_path):
    config_path_args = [f'-p {c_p}' for c_p in config_paths]
    config_path_args = " ".join(config_path_args)
    #find flow stage transition, split up Ex. "syn-to-par"
    flow_from = flow_stage_trans.split("-")[0]
    flow_to = flow_stage_trans.split("-")[2]
    hammer_cmd = f'hammer-vlsi -e {args["env_path"]} -p {args["config_path"]} -p {obj_dir_path}/{flow_from}-rundir/{flow_from}-output.json -o {obj_dir_path}/{args["top_level"]}-{flow_stage_trans}.json --obj_dir {obj_dir_path} {flow_stage_trans}'
    run_shell_cmd(hammer_cmd,f'hammer_{flow_stage_trans}_{args["top_level"]}.log')
    
    trans_config_path = os.path.join(obj_dir_path,f'{args["top_level"]}-{flow_from}-to-{flow_to}.json')
    return trans_config_path


def run_hammer_stage(flow_stage, config_paths, args, obj_dir_path):
    # config_paths for the next stage of the flow
    ret_config_path = ""
    # format config paths if multiple are needed
    config_path_args = [f'-p {c_p}' for c_p in config_paths]
    config_path_args = " ".join(config_path_args)
    # rad_gen_log(f'Running hammer with input configs: {" ".join(config_paths)}...',rad_gen_log_fd)
    hammer_cmd = f'hammer-vlsi -e {args["env_path"]} {config_path_args} --obj_dir {obj_dir_path} {flow_stage}'
    run_shell_cmd(hammer_cmd,f'hammer_{flow_stage}_{args["top_level"]}.log')
    # return output config path for flow stage
    ret_config_path = os.path.join(obj_dir_path,f"{flow_stage}-rundir/{flow_stage}-output.json")
    
    return ret_config_path
########################################## HAMMER UTILITIES ##########################################

########################################## OPENRAM UTILITIES ##########################################
# def check_openram_env():
#     """
#     Checks to make sure openram environment variables are set currently only supports freepdk45
#     """
#     if "OPENRAM_HOME" not in os.environ or "OPENRAM_TECH" not in os.environ or "FREEPDK45" not in os.environ:
#         rad_gen_log("OPENRAM_HOME not set")
#         sys.exit(1)

# def run_openram (args):

########################################## OPENRAM UTILITIES ##########################################

########################################## RAD GEN UTILITIES ##########################################



def sanitize_config(config_dict):
    """
        Want to apply various transformations across configuration data structure
        Python does not make this easy or understandable whats going on under the hood...
    """    
    for param, value in config_dict.copy().items():
        if("path" in param):
            config_dict[param] = os.path.expanduser(value)
    return config_dict
        


def modify_config_file(args):
    # recursively get all files matching extension in the design directory
    design_files, design_dirs = rec_get_flist_of_ext(args["hdl_path"])

    with open(args["config_path"], 'r') as yml_file:
        design_config = yaml.safe_load(yml_file)

    design_config["synthesis"]["inputs.input_files"] = design_files
    design_config["synthesis"]["inputs.top_module"] = args["top_level"]
    # If the user specified valid search paths we should not override them but just append to them
    
    # TODO ADD THE CONDITIONAL TO CHECK BEFORE CONCAT, this could be cleaner but is ok for now, worst case we have too many serach paths
    if("inputs.hdl_search_paths" in design_config["synthesis"].keys()):
        design_config["synthesis"]["inputs.hdl_search_paths"] = design_config["synthesis"]["inputs.hdl_search_paths"] + design_dirs
    else:
        design_config["synthesis"]["inputs.hdl_search_paths"] = design_dirs
    
    # remove duplicates
    design_config["synthesis"]["inputs.hdl_search_paths"] = list(dict.fromkeys(design_config["synthesis"]["inputs.hdl_search_paths"])) 
    #init top level placement constraints
    design_config["vlsi.inputs"]["placement_constraints"][0]["path"] = args["top_level"]

    modified_config_path = os.path.splitext(args["config_path"])[0]+"_mod.yaml"
    with open(modified_config_path, 'w') as yml_file:
        yaml.safe_dump(design_config, yml_file, sort_keys=False) 
    #default to 70% utilization (TODO)
    
    # Get in new design config to use for output directory names s.t. we don't overwrite previous runs when doing sweeps
    with open(modified_config_path, 'r') as yml_file:
        design_config = yaml.safe_load(yml_file)

    # sys.exit(1)
    return design_config, modified_config_path


def find_newest_obj_dir(args):
    cwd = os.getcwd()
    # verify that we're in the rad_gen dir
    if os.getcwd().split("/")[-1] != "rad_gen":
        rad_gen_log("Error: you must run this script from the rad_gen directory",rad_gen_log_fd)
        sys.exit(1)
    # find the newest obj_dir
    obj_dir_list = []
    for file in os.listdir("."):
        if args["top_level"] in file and os.path.isdir(file):
            obj_dir_list.append(os.path.join(cwd, file))
    obj_dir_list.sort(key=os.path.getmtime)
    obj_dir_path = obj_dir_list[-1]
    return obj_dir_path


def rad_gen_log(log_str,file):
    """
    Prints to a log file and the console depending on level of verbosity
    log codes:
    {
        "info"
        "debug"
        "error"
    }
    """
    fd = open(file, 'a')
    if(verbosity_lvl == 3):
        print(f"{log_str}",file=fd)
        print(f"{log_str}")
    fd.close()


def rec_find_fpath(dir,fname):
    ret_val = 1
    for root, dirs, files in os.walk(dir):
        if fname in files:
            ret_val = os.path.join(root, fname)
    return ret_val

def c_style_comment_rm(text):
    """ 
        This function removes c/c++ style comments from a file
        WARNING does not work for all cases (such as escaped characters and other edge cases of comments) but should work for most
    """
    def replacer(match):
        s = match.group(0)
        if s.startswith('/'):
            return " " # note: a space and not an empty string
        else:
            return s
    pattern = re.compile(
        r'//.*?$|/\*.*?\*/|\'(?:\\.|[^\\\'])*\'|"(?:\\.|[^\\"])*"',
        re.DOTALL | re.MULTILINE
    )
    return re.sub(pattern, replacer, text)


def replace_rtl_param(top_p_name_val, p_names, p_vals, base_config_path, base_param_hdr, base_param_hdr_path, param_sweep_hdr_dir):
    # p_names and p_vals are lists of parameters which need to be edited_concurrently

    mod_param_dir_str = ""
    mod_param_hdr = base_param_hdr
    for p_name, p_val in zip(p_names,p_vals):
        edit_params_re = re.compile(f"parameter\s+{p_name}.*$",re.MULTILINE)
        new_param_str = f'parameter {p_name} = {p_val};'
        mod_param_hdr = edit_params_re.sub(string=mod_param_hdr,repl=new_param_str)
        if(mod_param_dir_str == ""):
            mod_param_dir_str = f'{p_name}_{p_val}'
        else:
            mod_param_dir_str = f'{mod_param_dir_str}_{p_name}_{p_val}'
    mod_param_dir_name = f'{mod_param_dir_str}_{top_p_name_val[0]}_{top_p_name_val[1]}'
    # TODO fix hardcoded fextension
    mod_param_dir_path = os.path.join(param_sweep_hdr_dir,mod_param_dir_name)
    if not os.path.isdir(mod_param_dir_path):
        os.mkdir(mod_param_dir_path)
    mod_param_out_fpath = os.path.join(mod_param_dir_path,"parameters.v")
    with open(mod_param_out_fpath,"w") as param_out_fd:
        param_out_fd.write(mod_param_hdr)
    """ GENERATING AND WRITING RAD GEN CONFIG FILES """
    with open(base_config_path,"r") as config_fd:
        rad_gen_config = yaml.safe_load(config_fd)
    rad_gen_config["synthesis"]["inputs.hdl_search_paths"].append(os.path.abspath(mod_param_dir_path))
    mod_config_path = os.path.splitext(base_config_path)[0]+f'_{mod_param_dir_name}.yaml'
    with open(mod_config_path,"w") as config_fd:
        yaml.safe_dump(rad_gen_config, config_fd, sort_keys=False)

    return mod_param_out_fpath

def edit_rtl_proj_params(rtl_params, rtl_dir_path, base_param_hdr_path, base_config_path):
    """ 
        Edits the parameters specified in the design config file 
        Specifically only works for parameters associated with NoC currently TODO
    """

    # Its expected that the modified parameter files will be generated in the directory above project src files
    param_sweep_hdr_dir = os.path.join(rtl_dir_path,"..","param_sweep_headers")

    if not os.path.isdir(param_sweep_hdr_dir):
        os.mkdir(param_sweep_hdr_dir)

    base_param_hdr = c_style_comment_rm(open(base_param_hdr_path).read())
    
    mod_parameter_paths = []
    # p_val is a list of parameter sweep values
    for p_name,p_vals in rtl_params.items():
        # TODO FIXME this hacky conditional seperating print params vs edit params
        if(len(p_vals) > 0 or isinstance(p_vals,dict) ):
            # print(p_name)
            if(isinstance(p_vals,dict)):
                for i in range(len(p_vals["vals"])):
                    """ WRITE PARAMETER/CONFIG FILES FOR EACH ITERATION """
                    # Crate a sweep iter dict which will contain the param values which need to be set for a given iteration
                    sweep_iter = {}
                    for k, v in p_vals.items():
                        sweep_iter[k] = v[i]
                    p_vals_i = []
                    p_names_i = []
                    for p_name_i, p_val_i in sweep_iter.items():
                        # The vals list will be the value which we want our p_name to be set to and will not be used for editing
                        # They will be used to make sure that the correct parameter value is generated
                        if(p_name_i == "vals"):
                            top_p_val_name = [p_name,p_val_i]
                            continue
                        else:
                            edit_param = p_name_i
                        p_names_i.append(edit_param)
                        p_vals_i.append(p_val_i)
                    mod_param_fpath = replace_rtl_param(top_p_val_name, p_names_i, p_vals_i, base_config_path, base_param_hdr, base_param_hdr_path, param_sweep_hdr_dir)
                    mod_parameter_paths.append(mod_param_fpath)
            else:
                for p_val in p_vals:
                    """ GENERATING AND WRITING RTL PARAMETER FILES """
                    mod_param_hdr = base_param_hdr
                    # each iteration creates a new parameter file
                    edit_params_re = re.compile(f"parameter\s+{p_name}.*$",re.MULTILINE)
                    new_param_str = f'parameter {p_name} = {p_val};'
                    mod_param_hdr = edit_params_re.sub(string=mod_param_hdr,repl=new_param_str)
                    mod_param_dir_str = os.path.join(param_sweep_hdr_dir,f'{p_name}_{p_val}_{os.path.splitext(os.path.split(base_param_hdr_path)[1])[0]}')
                    if not os.path.isdir(mod_param_dir_str):
                        os.mkdir(mod_param_dir_str)
                    mod_param_out_fpath = os.path.join(mod_param_dir_str,"parameters.v")
                    with open(mod_param_out_fpath,"w") as param_out_fd:
                        param_out_fd.write(mod_param_hdr)
                    mod_parameter_paths.append(mod_param_out_fpath)
                    """ GENERATING AND WRITING RAD GEN CONFIG FILES """
                    with open(base_config_path,"r") as config_fd:
                        rad_gen_config = yaml.safe_load(config_fd)
                    rad_gen_config["synthesis"]["inputs.hdl_search_paths"].append(os.path.abspath(mod_param_dir_str))
                    mod_config_path = os.path.splitext(base_config_path)[0]+f'_{p_name}_{p_val}.yaml'
                    with open(mod_config_path,"w") as config_fd:
                        yaml.safe_dump(rad_gen_config, config_fd, sort_keys=False)

    return mod_parameter_paths

def read_in_rtl_proj_params(rtl_params, top_level_mod, rtl_dir_path, sweep_param_inc_path=False):
    wspace_re = re.compile(r"\s+")
    # Now that we have a mem_params.json and sram_config.yaml file for each design, we can run the flow for each design in parallel (up to user defined amount)
    find_params_re = re.compile(f"parameter\s+\w+(\s|=)+.*;")
    find_defines_re = re.compile(f"`define\s+\w+\s+.*")
    grab_bw_soft_bkt = re.compile(f"\(.*\)")
    
    find_localparam_re = re.compile(f"localparam\s+\w+(\s|=)+.*?;",re.MULTILINE|re.DOTALL)

    # Find all parameters which will be used in the design (ie find top level module rtl, parse include files top to bottom and get those values )
    """ FIND TOP LEVEL MODULE IN RTL FILES """
    grep_out = sp.run(["grep","-R",top_level_mod,rtl_dir_path],stdout=sp.PIPE)
    grep_stdout = grep_out.stdout.decode('utf-8')
    top_level_fpath = grep_stdout.split(":")[0]
    """ FIND PARAMS IN TOP LEVEL SEQUENTIALLY """
    rtl_preproc = {
        "vals": []
    }
    top_level_rtl = open(top_level_fpath).read()
    clean_top_lvl_rtl = c_style_comment_rm(top_level_rtl)
    # Stores the total idx of lines read in
    global_line_idx = 0
    param_define_deps = []
    for line in clean_top_lvl_rtl.split("\n"):
        # Look for include statements
        if "include" in line:
            # Get the include file path
            include_fname = line.split(" ")[1].replace('"','')
            # Look for the include path in the rtl directory, if its not found default back to 'sweep_param_inc_path'
            # TODO FIX THIS HACKERY this is hackery because its only looking for the parameters file and using it to determine when to use the sweep_param_inc_path as the include
            if "parameters" not in line:
                include_fpath = rec_find_fpath(rtl_dir_path,include_fname)
            else:
                include_fpath = sweep_param_inc_path

            # if we couldnt find the include in the rtl_dir_path
            # and include_fname in sweep_param_inc_path

            # if(include_fpath == 1 and os.path.exists(sweep_param_inc_path) and sweep_param_inc_path != False):
            #     include_fpath = sweep_param_inc_path
            # elif(include_fpath == 1):
            #     print("ERROR occured the script could not find an include file in the top level rtl and a backup was not specified")
            #     sys.exit(1)

            # Look in the include file path and grab all parameters and defines
            include_rtl = open(include_fpath).read()
            clean_include_rtl = c_style_comment_rm(include_rtl)
            for inc_line in clean_include_rtl.split("\n"):
                
                # Look for parameters
                if find_params_re.search(inc_line):
                    # TODO this parameter re will not work if no whitespace between params
                    clean_line = " ".join(wspace_re.split(inc_line)[1:]).replace(";","")
                    # Get the parameter name and value
                    param_name = clean_line.split("=")[0].replace(" ","")
                    param_val = clean_line.split("=")[1].replace(" ","").replace("`","")

                    # create dep list for params
                    for i in range(len(rtl_preproc["vals"])):
                        if rtl_preproc["vals"][i]["name"] in param_val:
                            param_define_deps.append(rtl_preproc["vals"][i]["name"])

                    # Add the parameter name and value to the design_params dict
                    #rtl_preproc["params"][param_name] = str(param_val)
                    rtl_preproc["vals"].append({"name" : param_name, "value" : str(param_val),"type": "param","line_idx": global_line_idx})

                elif find_defines_re.search(inc_line):
                    # TODO this define re will not work if no whitespace between params
                    clean_line = " ".join(wspace_re.split(inc_line)[1:])
                    # Get the define name and value
                    define_name = wspace_re.split(clean_line)[0]
                    if grab_bw_soft_bkt.search(clean_line):
                        define_val = grab_bw_soft_bkt.search(clean_line).group(0)
                    else:
                        define_val = wspace_re.split(clean_line)[1].replace("`","")
                    # create dep list for defines
                    for i in range(len(rtl_preproc["vals"])):
                        if rtl_preproc["vals"][i]["name"] in define_val:
                            param_define_deps.append(rtl_preproc["vals"][i]["name"])
                    #rtl_preproc["defines"][define_name] = str(define_val)
                    rtl_preproc["vals"].append({"name": define_name, "value" : str(define_val),"type": "define" ,"line_idx": global_line_idx})
                # increment line index keeping track of global (both in top level rtl and in includes of the lines read in)
                global_line_idx += 1

    param_define_deps = list(dict.fromkeys(param_define_deps))    
    # Only using parsing technique of looking for semi colon in localparams as these are expected to have larger operations
    # Not parsing lines as we need multiline capture w regex
    tmp_top_lvl_rtl = clean_top_lvl_rtl
    local_param_matches = []
    # Searching through the text in this way preserves initialization order
    while find_localparam_re.search(tmp_top_lvl_rtl):
        local_param = find_localparam_re.search(tmp_top_lvl_rtl).group(0)
        local_param_matches.append(local_param)
        tmp_top_lvl_rtl = tmp_top_lvl_rtl.replace(local_param,"")
    """ EVALUATING BOOLEANS FOR LOCAL PARAMS W PARAMS AND DEFINES """
    # Write out localparams which need to be evaluated to a temp dir
    tmp_dir = "/tmp/rad_gen_tmp"
    if not os.path.exists(tmp_dir):
        os.mkdir(tmp_dir)
    # Sort list of preproc vals by line index
    # val_list = copy.deepcopy(rtl_preproc["vals"])
    rtl_preproc["vals"] = sorted(rtl_preproc["vals"], key=lambda k: k["line_idx"])
    # We are going to make .h and .c files which we can use the gcc preproc engine to evaluate the defines and local parameters
    # Loop through all parameters and find its dependancies on other parameters
    local_param_deps = []
    for local_param_str in local_param_matches:
        """ CREATING LIST OF REQUIRED DEPENDANCIES FOR ALL PARAMS """
        first_eq_re = re.compile("\s=\s")
        local_param_name = re.sub("localparam\s+",repl="",string=first_eq_re.split(local_param_str)[0]).replace(" ","").replace("\n","")
        local_param_val = first_eq_re.split(local_param_str)[1]

        tmp_lparam_list = []
        for i in range(len(rtl_preproc["vals"])):
            if rtl_preproc["vals"][i]["name"] in local_param_val:
                local_param_deps.append(rtl_preproc["vals"][i]["name"])
                local_param_dict = {"name": local_param_name, "value": local_param_val, "type": "localparam"}
                tmp_lparam_list.append(local_param_dict)
        rtl_preproc["vals"] = rtl_preproc["vals"] + tmp_lparam_list
    
    local_param_deps = list(dict.fromkeys(local_param_deps))  
    # TODO this assumes the following rtl structure
    # 1 -> includes init parameters and defines at the top of a module
    # 2 -> there are only local params in the top level module
    # Using above assumptions the below dep list should maintain order without having to build dep tree
    all_deps = param_define_deps + local_param_deps
    # Now we have list of all dependancies we need to initialize

    # Now we have a list of dictionaries containing the localparam string and thier dependancies
    """ CONVERT SV/V LOCALPARAMS TO C DEFINES """
    rtl_preproc_fname = os.path.join(tmp_dir,"rtl_preproc_vals")
    header_fd = open(rtl_preproc_fname + ".h","w")
    main_fd = open(rtl_preproc_fname + ".c","w")
    # init .c file containing main which will just print out the values of our params/defs/localparams
    main_lines = [
        f'#include "{rtl_preproc_fname}.h"',
        f'#include <stdio.h>',
        '',
        '',
        'int main(int argc, char argv [] ) {',
        # CODE TO PRINT PARAMS GOES HERE
    ]

    # Initialize deps in order of local param dep list
    for dep in all_deps:
        for val in rtl_preproc["vals"]:
            # find dependancy value in rtl_preproc dict
            if(dep == val["name"]):
                # convert param into something c can understand
                clean_c_def_val = val["value"].replace("\n","").replace(";","").replace("`","")
                c_def_str = "#define " + dep + " (" + clean_c_def_val + ")"
                print(c_def_str,file=header_fd)
                break
    for p_name,p_val in rtl_params.items():
        for val in rtl_preproc["vals"]:
            if(p_name == val["name"] and p_name not in all_deps):
                clean_c_def_val = val["value"].replace("\n","").replace(";","").replace("`","")
                c_def_str = "#define " + p_name + " (" + clean_c_def_val + ")"
                print(c_def_str,file=header_fd)
                break
    header_fd.close()
    # Look through sweep param list in config file and match them to the ones found in design
    for p_name, p_val in rtl_params.items():
        for val in rtl_preproc["vals"]:
            # If they match, write the c code which will print the parameter and its value
            if(val["name"] == p_name):
                main_lines.append("\t" + f'printf("{p_name}: %d \n",{p_name});'.encode('unicode_escape').decode('utf-8'))
                break
    for line in main_lines:
        print(line,file=main_fd)
    print("}",file=main_fd)
    main_fd.close()
    # This runs the c file which prints out evaluated parameter values set in the verilog
    gcc_out = sp.run(["/usr/bin/gcc",f"{rtl_preproc_fname}.h",f"{rtl_preproc_fname}.c"],stderr=sp.PIPE,stdout=sp.PIPE,stdin=sp.PIPE)#,"-o",f'{os.path.join(tmp_dir,"print_params")}'])
    sp.run(["a.out"])
    sp.run(["rm","a.out"])



# This class will have info applicable to all tools
# @dataclass
# class AsicToolInfo:
#     pwr_lookup : dict = {
#             "W": float(1),
#             "mW": float(1e-3),
#             "uW": float(1e-6)
#         }


def parse_report_c(top_level_mod,report_path,rep_type,flow_stage, tool_type):
    
    pwr_lookup ={
        "W": float(1),
        "mW": float(1e-3),
        "uW": float(1e-6),
        "nW": float(1e-9),
        "pW": float(1e-12)
    }
    
    wspace_re = re.compile("\s+", re.MULTILINE)
    decimal_re = re.compile("\d+\.{0,1}\d*",re.MULTILINE)
    signed_dec_re = re.compile("\-{0,1}\d+\.{0,1}\d*",re.MULTILINE)
    if flow_stage == "syn":
        cadence_hdr_catagories = ["Instance","Module","Cell Count","Cell Area","Net Area","Total Area"]
        cadence_area_hdr_re = re.compile("^\s+Instance.*Module.*Cell\sCount.*Cell\sArea.*Total\sArea.*", re.MULTILINE|re.DOTALL)
        cadence_arrival_time_re = re.compile("Data\sPath:-.*$",re.MULTILINE)
    elif flow_stage == "par":
        cadence_hdr_catagories = ["Hinst Name","Module Name","Inst Count","Total Area"]
        cadence_area_hdr_re = re.compile("^\s+Hinst\s+Name\s+Module\sName\s+Inst\sCount\s+Total\sArea.*", re.MULTILINE|re.DOTALL)
        cadence_arrival_time_re = re.compile("Arrival:=.*$",re.MULTILINE)
        
    cadence_timing_grab_re = re.compile("Path(.*?#-+){3}",re.MULTILINE|re.DOTALL)
    cadence_timing_setup_re = re.compile("Setup:-.*$",re.MULTILINE)
    
    unit_re_str = "(" + "|".join([f"({unit})" for unit in pwr_lookup.keys()]) + ")"                  
    
    # synopsys_unit_re = re.compile(unit_re_str)
    grab_val_re_str = f"\d+\.{{0,1}}\d*.*?{unit_re_str}"
    synopsys_grab_pwr_val_re = re.compile(grab_val_re_str)
    # print(grab_val_re_str)
    
    # synopsys_unit_re_list = [ re.compile(f'{pwr_lookup[unit]}',re.MULTILINE) for unit in pwr_lookup.keys() ]
    

    # report_dict = {
    #     "Instance": [],
    #     "Module": [],
    #     "Cell Count": [],
    #     "Cell Area": [],
    #     "Net Area": [],
    #     "Total Area": []
    # }
    report_list = []
    # parse synopsys report
    if(rep_type == "area"):
        area_rpt_text = open(report_path,"r").read()
        # removes stuff above the header so we only have info we need
        area_rpt_text = cadence_area_hdr_re.search(area_rpt_text).group(0)
        for line in area_rpt_text.split("\n"):
            report_dict = {}
            # below conditional finds the header line
            sep_line = wspace_re.split(line)
            sep_line = list(filter(lambda x: x != "", sep_line))
            if(len(sep_line) >= len(cadence_hdr_catagories)-1 and len(sep_line) <= len(cadence_hdr_catagories)):
                sep_idx = 0
                for i in range(len(cadence_hdr_catagories)):
                    if("Module" in cadence_hdr_catagories[i] and top_level_mod in line):
                        report_dict[cadence_hdr_catagories[i]] = "NA"
                        sep_idx = sep_idx
                    else:
                        report_dict[cadence_hdr_catagories[i]] = sep_line[sep_idx]
                        sep_idx = sep_idx + 1                       
                report_list.append(report_dict)
    elif(rep_type == "timing"):
        timing_rpt_text = open(report_path,"r").read()
        if tool_type == "cadence":
            timing_path_text = timing_rpt_text
            while cadence_timing_grab_re.search(timing_rpt_text):
                timing_dict = {}
                timing_path_text = cadence_timing_grab_re.search(timing_rpt_text).group(0)
                for line in timing_path_text.split("\n"):
                    if cadence_timing_setup_re.search(line):
                        timing_dict["Setup"] = float(decimal_re.findall(line)[0])
                    elif cadence_arrival_time_re.search(line):
                        timing_dict["Arrival"] = float(decimal_re.findall(line)[0])
                    if "Setup" in timing_dict and "Arrival" in timing_dict:
                        timing_dict["Delay"] = timing_dict["Arrival"] + timing_dict["Setup"]
                report_list.append(timing_dict)
                timing_rpt_text = timing_rpt_text.replace(timing_path_text,"")
        elif tool_type == "synopsys":
            timing_dict = {}
            for line in timing_rpt_text.split("\n"):
                if "library setup time" in line:
                    timing_dict["Setup"] = float(decimal_re.findall(line)[0])
                elif "data arrival time" in line:
                    timing_dict["Arrival"] = float(decimal_re.findall(line)[0])
                elif "slack" in line:
                    timing_dict["Slack"] = float(signed_dec_re.findall(line)[0])
                elif "Setup" in timing_dict and "Arrival" in timing_dict:
                    timing_dict["Delay"] = timing_dict["Arrival"] + timing_dict["Setup"]
                # This indicates taht all lines have been read in and we can append the timing_dict
            report_list.append(timing_dict)
    elif(rep_type == "power"):
        power_rpt_text = open(report_path,"r").read()
        if tool_type == "synopsys":
            power_dict = {}
            for line in power_rpt_text.split("\n"):
                if "Total Dynamic Power" in line:
                    for unit in pwr_lookup.keys():
                        if f" {unit} " in line or f" {unit}" in line:
                            units = pwr_lookup[unit]
                            break
                    power_dict["Dynamic"] = float(decimal_re.findall(line)[0]) * units
                    # Check to make sure that the total has multiple values associated with it
                elif "Total" in line and len(decimal_re.findall(line)) > 1:
                    pwr_totals = []
                    pwr_vals_line = line
                    while synopsys_grab_pwr_val_re.search(pwr_vals_line):
                        pwr_val = synopsys_grab_pwr_val_re.search(pwr_vals_line).group(0)
                        for unit in pwr_lookup.keys():
                            # pwr_unti_re_str = r"\s" + unit + r"(\s|\n)"
                            # pwr_unit_re = re.compile(pwr_unti_re_str)
                            # print(pwr_val)
                            if f" {unit} " in pwr_val or f" {unit}" in pwr_val:
                                # print(f"Found {unit} in {pwr_val}")
                                units = pwr_lookup[unit]
                                break
                        pwr_total = float(wspace_re.split(pwr_val)[0]) * units
                        pwr_totals.append(pwr_total)
                        pwr_vals_line = pwr_vals_line.replace(pwr_val,"")
                    power_dict["Total"] = pwr_totals[-1]
            report_list.append(power_dict)
    
    return report_list
                

def parse_output(top_level_mod, output_path):
    syn_dir = "syn-rundir"
    par_dir = "par-rundir"
    pt_dir = "pt-rundir"
    # Loop through the output dir and find the relevant files to each stage of the flow
    syn_report_path = os.path.join(output_path,syn_dir,"reports")
    par_report_path = os.path.join(output_path,par_dir)
    pt_report_path = os.path.join(output_path,pt_dir,"reports")
    syn_results = {}
    par_results = {}
    pt_results = {}
    if os.path.isdir(syn_report_path):
        for file in os.listdir(syn_report_path):
            if("area" in file):
                syn_results["area"] = parse_report_c(top_level_mod,os.path.join(syn_report_path,file),"area","syn","cadence")
            elif("time" in file or "timing" in file):
                syn_results["timing"] = parse_report_c(top_level_mod,os.path.join(syn_report_path,file),"timing","syn","cadence")
    if os.path.isdir(par_report_path):
        for file in os.listdir(par_report_path):
            if(file == "area.rpt"):
                par_results["area"] = parse_report_c(top_level_mod,os.path.join(par_report_path,file),"area","par","cadence")
            elif(file == "timing.rpt"):
                par_results["timing"] = parse_report_c(top_level_mod,os.path.join(par_report_path,file),"timing","par","cadence")
    if os.path.isdir(pt_report_path):
        for file in os.listdir(pt_report_path):
            if("timing" in file):
                pt_results["timing"] = parse_report_c(top_level_mod,os.path.join(pt_report_path,file),"timing","pt","synopsys")
            elif ("power" in file):
                pt_results["power"] = parse_report_c(top_level_mod,os.path.join(pt_report_path,file),"power","pt","synopsys")

    return syn_results, par_results, pt_results


def parse_reports(report_search_dir,param_search_list,top_level_mod):
    reports = []
    for dir in os.listdir(report_search_dir):
        if os.path.isdir(dir) and dir.startswith(top_level_mod):
            report_dict = {}
            # print(f"Parsing results for {dir}")
            syn_rpts, par_rpts, pt_rpts = parse_output(top_level_mod,dir)
            report_dict["syn"] = syn_rpts
            report_dict["par"] = par_rpts
            report_dict["pt"] = pt_rpts
            # We need to get parameter values associated with this report dict
            # Currently using the value in the hdl_search_path to determine the specific parameters TODO fix this in the future
            # Using the synthesis generated output file to get this value, if this file does not exist, synthesis was not run and will return invalid tag for the directory
            if(os.path.isfile(os.path.join(report_search_dir,dir,"syn-rundir","syn-output-full.json"))):
                syn_out_config = json.load(open(os.path.join(report_search_dir,dir,"syn-rundir","syn-output-full.json")))
                #design_sweep_config = yaml.safe_load(open(args.design_sweep_config_file))
                # TODO fix the specific config path being looked up (if hammer changes so could this)
                for path in syn_out_config["synthesis.inputs.hdl_search_paths"]:
                    # This expects there to only be one path which contains param sweep header 
                    if "param_sweep_headers" in path:
                        param_dir_name = os.path.basename(path)
                        # TODO fix this to not just use the first design in the sweep file
                        for param in param_search_list:
                            if param in param_dir_name:
                                param_grab_re = re.compile(f"{param}_\d+")
                                # This only works if the param name is seperated by a "_"
                                param_val = param_grab_re.search(param_dir_name).group(0).split("_")[-1]
                                report_dict["rtl_param"] = { param : param_val }
                                # print({ param : param_val })
                                if len(report_dict["syn"]) > 0 and len(report_dict["par"]) > 0:
                                    reports.append(report_dict)
                                break
    return reports


def noc_prse_area_brkdwn(report):
    report_to_csv = {}
    print(report["rtl_param"])
    for k,v in report["rtl_param"].items():
        report_to_csv["param_key"] = k
        report_to_csv["param_val"] = v

    total_area = float(report["par"]["area"][0]["Total Area"])
    print(f'Total Area: {total_area}')
    report_to_csv["Total Area"] = total_area
    # input modules
    if("num_ports" in report["rtl_param"]): 
        num_ports = int(report["rtl_param"]["num_ports"]) 
    else:
        num_ports = 5
    input_channel_area = float(0)
    for i in range(num_ports):
        ipc_alloc_idx = next(( index for (index, d) in enumerate(report["par"]["area"]) if d["Hinst Name"] == f"genblk1.vcr/ips[{i}].ipc"), None)
        input_channel_area += float(report["par"]["area"][ipc_alloc_idx]["Total Area"])
        # print(report["par"]["area"][ipc_alloc_idx])
    print(f'Input Module Area: {input_channel_area} : {input_channel_area/total_area}')
    report_to_csv["Input Module Area"] = input_channel_area
    report_to_csv["Input Module Area Percentage"] = input_channel_area/total_area

    # xbr
    xbr_idx = next(( index for (index, d) in enumerate(report["par"]["area"]) if d["Hinst Name"] == "genblk1.vcr/xbr"), None)
    xbr_area = float(report["par"]["area"][xbr_idx]["Total Area"])
    print(f'XBR Area: {xbr_area} : {xbr_area/total_area}')
    report_to_csv["XBR Area"] = xbr_area
    report_to_csv["XBR Area Percentage"] = xbr_area/total_area
    # sw allocator
    sw_alloc_idx = next(( index for (index, d) in enumerate(report["par"]["area"]) if d["Hinst Name"] == "genblk1.vcr/alo/genblk2.sw_core_sep_if"), None)
    sw_alloc_area = float(report["par"]["area"][sw_alloc_idx]["Total Area"])
    print(f'SW Alloc Area: {sw_alloc_area} : {sw_alloc_area/total_area}')
    report_to_csv["SW Alloc Area"] = sw_alloc_area
    report_to_csv["SW Alloc Area Percentage"] = sw_alloc_area/total_area
    # vc allocator
    vc_alloc_idx = next(( index for (index, d) in enumerate(report["par"]["area"]) if d["Hinst Name"] == "genblk1.vcr/alo/genblk1.vc_core_sep_if"), None)
    vc_alloc_area = float(report["par"]["area"][vc_alloc_idx]["Total Area"])
    print(f'VC Alloc Area: {vc_alloc_area} : {vc_alloc_area/total_area}')
    report_to_csv["VC Alloc Area"] = vc_alloc_area
    report_to_csv["VC Alloc Area Percentage"] = vc_alloc_area/total_area
    # output modules
    output_channel_area = float(0)
    for i in range(num_ports):
        opc_alloc_idx = next(( index for (index, d) in enumerate(report["par"]["area"]) if d["Hinst Name"] == f"genblk1.vcr/ops[{i}].opc"), None)
        output_channel_area += float(report["par"]["area"][opc_alloc_idx]["Total Area"])
    print(f'Output Module Area: {output_channel_area} : {output_channel_area/total_area}')

    report_to_csv["Output Module Area"] = output_channel_area
    report_to_csv["Output Module Area Percentage"] = output_channel_area/total_area
    report_to_csv["Slack"] = float(report["pt"]["timing"][0]["Slack"])
    return report_to_csv


def create_bordered_str(text: str = "", border_char: str = "#", total_len: int = 150) -> list:
    text = f"  {text}  "
    text_len = len(text)
    if(text_len > total_len):
        total_len = text_len + 10 
    border_size = (total_len - text_len) // 2
    return [ border_char * total_len, f"{border_char * border_size}{text}{border_char * border_size}", border_char * total_len]

########################################## RAD GEN UTILITIES ##########################################
##########################################   RAD GEN FLOW   ############################################
def rad_gen_flow(flow_settings,run_stages,config_paths):
    # Set the obj directory for hammer
    if flow_settings["use_latest_obj_dir"] == True:
        obj_dir_path = find_newest_obj_dir(flow_settings)
    else:
        timestr = time.strftime("%Y-%m-%d---%H-%M-%S")
        obj_dir_path = f'{flow_settings["top_level"]}-{timestr}'


    rad_gen_log(f"Using obj_dir: {obj_dir_path}",rad_gen_log_fd)
    # Check to see if design has an SRAM configuration
    if run_stages["sram"]:
        sram_config = run_hammer_stage("sram_generator", config_paths, flow_settings, obj_dir_path)
        config_paths.append(sram_config)
    #run hammer stages
    if run_stages["syn"]:
        syn_config = run_hammer_stage("syn", config_paths, flow_settings, obj_dir_path)
        # get_hammer_config("syn-to-par", flow_settings)
    if run_stages["par"]:
        syn_to_par_config = get_hammer_config("syn-to-par", config_paths, flow_settings, obj_dir_path)
        config_paths.append(syn_to_par_config)
        par_out_config = run_hammer_stage("par", config_paths, flow_settings, obj_dir_path)
    if run_stages["pt"]:
        par_to_power_config = get_hammer_config("par-to-power", config_paths, flow_settings, obj_dir_path)
        #get params from par-to-power.json file
        json_fd = open(os.path.join(obj_dir_path,f'{flow_settings["top_level"]}-par-to-power.json'),"r")
        par_to_power_data = json.load(json_fd)
        json_fd.close()
        #get params from syn-to-par.json file
        json_fd = open(os.path.join(obj_dir_path,f'{flow_settings["top_level"]}-syn-to-par.json'),"r")
        syn_to_par_data = json.load(json_fd)
        json_fd.close()

        write_pt_sdc(par_to_power_data,os.path.join(os.getcwd(),obj_dir_path))

        #now use the pnr output to run primetime

        ################################ LIB TO DB CONVERSION ################################
        #prepare lib files to be read in from pt, means we need to unzip them in asap7 cache
        #asap7_std_cell_lib_cache = os.path.join(obj_dir_path,"tech-asap7-cache/LIB/NLDM")
        # for lib_file in os.listdir(asap7_std_cell_lib_cache):
            # if(lib_file.endswith(".gz")):
                # sp.run(["gunzip",os.path.join(asap7_std_cell_lib_cache,lib_file)])
        #write_lib_to_db_script(os.path.join(os.getcwd(),obj_dir_path))
        ################################ LIB TO DB CONVERSION ################################
        
        flow_stage = "pt"
        write_pt_timing_script(par_to_power_data,os.path.join(os.getcwd(),obj_dir_path),flow_settings)
        cwd = os.getcwd()
        os.chdir(os.path.join(os.getcwd(),obj_dir_path,"pt-rundir"))
        run_shell_cmd("dc_shell-t -f pt_analysis.tcl","pt.log")
        os.chdir(cwd)
        # copy the run dir to a new directory to save results
        #sp.run(["cp", "-r", flow_stage_rundir_path_src,flow_stage_rundir_path_dest])
        ################################ LIB TO DB CONVERSION ################################
        # re zip the after primetime
        # for lib_file in os.listdir(asap7_std_cell_lib_cache):
        #     sp.run(["gunzip",os.path.join(asap7_std_cell_lib_cache,lib_file)])
        ################################ LIB TO DB CONVERSION ################################
##########################################   RAD GEN FLOW   ############################################


def main():
    global cur_env
    global openram_gen_path
    global verbosity_lvl
    global rad_gen_log_fd
    rad_gen_log_fd = "rad_gen.log"
    #Clear rad gen log
    fd = open(rad_gen_log_fd, 'w')
    fd.close()

    verbosity_lvl = 3
    # Verbosity level
    # 0 - No output
    # 1 - Only errors
    # 2 - Errors and warnings
    # 3 - Errors, warnings, and info    

    openram_gen_path = "openram_gen"
    parser = argparse.ArgumentParser()
    parser.add_argument('-t', '--top_level', help="name of top level design in HDL", type=str, default='')
    parser.add_argument('-v', '--hdl_path', help="path to directory containing HDL files", type=str, default='')
    parser.add_argument('-e', '--env_path', help="path to hammer env.yaml file", type=str, default='')
    parser.add_argument('-p', '--config_path', help="path to hammer design specific config.yaml file", type=str, default='')
    parser.add_argument('-r', '--openram_config_dir', help="path to dir", type=str, default='')
    parser.add_argument('-l', '--use_latest_obj_dir', help="uses latest obj dir found in rad_gen dir", action='store_true') 
    
    parser.add_argument('-s', '--design_sweep_config_file', help="path to config file containing design sweep parameters",  type=str, default='')
    parser.add_argument('-c', '--compile_results', help="path to dir", action='store_true') 

    parser.add_argument('-syn', '--synthesis', help="path to dir", action='store_true') 
    parser.add_argument('-par', '--place_n_route', help="path to dir", action='store_true') 
    parser.add_argument('-pt', '--primetime', help="path to dir", action='store_true') 
    parser.add_argument('-sram', '--sram_compiler', help="path to dir", action='store_true') 

    
    args = parser.parse_args()


    # Use hammer parser to load configs from paths
    # hammer_config = load_config_from_paths([args.config_path])
    # print(hammer_config)
    # sys.exit(1)

    if(not args.openram_config_dir == ''):
        rad_gen_log(f"Using OpenRam to generate SRAMs in {args.openram_config_dir}",rad_gen_log_fd)
        sys.exit(0)

    # Determines which stages of ASIC flow to run 
    run_all_flow = not (args.synthesis or args.place_n_route or args.primetime)
    run_stages = {
        "sram" : args.sram_compiler,
        "syn": args.synthesis or run_all_flow,
        "par": args.place_n_route or run_all_flow,
        "pt": args.primetime or run_all_flow,
    }

    # Make sure HAMMER env vars are set
    if 'HAMMER_HOME' not in os.environ:
        rad_gen_log('Error: HAMMER_HOME environment variable not set!',rad_gen_log_fd)
        rad_gen_log("Please set HAMMER_HOME to the root of the HAMMER repository, and run 'source $HAMMER_HOME/sourceme.sh'",rad_gen_log_fd)
        sys.exit(1)

    cur_env = os.environ.copy()
    
    # Convert from cli args into rad_gen_flow_settings for a particular flow run    
    rad_gen_flow_settings = vars(args)

    if args.compile_results and args.design_sweep_config_file != '':
        report_search_dir = os.path.expanduser("~/rad_gen")
        rad_gen_log(f"Parsing results of parameter sweep using parameters in {args.design_sweep_config_file}",rad_gen_log_fd)
        design_sweep_config = yaml.safe_load(open(args.design_sweep_config_file))
        for design in design_sweep_config["designs"]:
            reports = parse_reports(report_search_dir,design["params"].keys(),design["top_level_module"])
            # TODO fix to support multiple designs through a single param sweep file, below break only allows for one
            break        

        """ OUTPUTTING REPORTS FOR THE NOC SWEEP VALUES TODO MAKE LESS DESIGN SPECIFIC """
        csv_lines = []
        for report in reports:
            report_to_csv = noc_prse_area_brkdwn(report)            
            csv_lines.append(report_to_csv)

        csv_fd = open("area_csv.csv","w")
        writer = csv.DictWriter(csv_fd, fieldnames=csv_lines[0].keys())
        writer.writeheader()
        for line in csv_lines:
            writer.writerow(line)
        csv_fd.close()
        sys.exit(1)
    # If a design sweep config file is specified, modify the flow settings for each design in sweep
    elif args.design_sweep_config_file != '':
        # Vars for storing the values initialized in the loops for base configuration params of sweep file
        base_config_dir = ""
        base_rtl_dir = ""
        # Starting with just SRAM configurations for a single rtl file (changing parameters in header file)
        rad_gen_log(f"Running design sweep from config file {args.design_sweep_config_file}",rad_gen_log_fd)
        design_sweep_config = yaml.safe_load(open(args.design_sweep_config_file))
        for design in design_sweep_config["designs"]:
            """ General flow for all designs in sweep config """
            # Load in the base configuration file for the design
            sanitized_design = sanitize_config(design)
            base_config_dir = os.path.split(sanitized_design["base_config_path"])[0]
            base_config = yaml.safe_load(open(sanitized_design["base_config_path"]))
            
            """ Currently only can sweep either vlsi params or rtl params not both """
            # If there are vlsi parameters to sweep over
            if "vlsi_params" in design_sweep_config:
                mod_base_config = copy.deepcopy(base_config)
                """ MODIFYING HAMMER CONFIG YAML FILES """
                for param_sweep_key in design_sweep_config["vlsi_params"]:
                    if "clk" in param_sweep_key:
                        for period in design_sweep_config["vlsi_params"][param_sweep_key]:
                            mod_base_config["vlsi.inputs"]["clocks"][0]["period"] = f'{str(period)} ns'
                            modified_config_path = os.path.splitext(sanitized_design["base_config_path"])[0]+f'_period_{str(period)}.yaml'
                            with open(modified_config_path, 'w') as fd:
                                yaml.safe_dump(mod_base_config, fd, sort_keys=False) 
                            # print(modified_config_path)
            # TODO This wont work for multiple SRAMs in a single design, simply to evaluate individual SRAMs
            elif sanitized_design["type"] == "sram":                
                # load in the mem_params.json file            
                with open(base_config["vlsi.inputs"]["sram_parameters"], 'r') as fd:
                    mem_params = json.load(fd)
                # List of available SRAM macros
                sram_macros = os.listdir(os.path.join(sanitized_design["sram_memory_path"],"lef"))
                # Sweep over all widths and depths for SRAMs in the sweep config file                
                for depth in sanitized_design["depths"]:
                    """ MODIFIYING MEM CONFIG JSON FILES """
                    # If we want to iterate through and keep an original reference set of configs we need to use deepcopy on the dict
                    # This concept is very annoying as when assigning any variable to a dict you are actually just creating a reference to the dict (Very unlike C) :(
                    mod_mem_params = copy.deepcopy(mem_params)
                    # All mem_params are indexed to 0 since we are only sweeping over a single SRAM TODO
                    mod_mem_params[0]["depth"] = str(depth)
                    for width in sanitized_design["widths"]:
                        # Create copies of each configs s.t they can be modified without affecting the original
                        mod_base_config = copy.deepcopy(base_config)

                        mod_mem_params[0]["width"] = str(width)
                        # Defines naming convension of SRAM macros TODO
                        mod_mem_params[0]["name"] = f"SRAM1RW{depth}x{width}"
                        # Make sure that the SRAM macro exists in the list of SRAM macros
                        if not any(mod_mem_params[0]["name"] in macro for macro in sram_macros):
                            rad_gen_log(f"WARNING: {mod_mem_params[0]['name']} not found in list of SRAM macros, skipping config generation...",rad_gen_log_fd)
                            continue
                        
                        for ret_str in create_bordered_str(f"Generating files required for design: {mod_mem_params[0]['name']}"):
                            rad_gen_log(ret_str,rad_gen_log_fd)                        
                        
                        # Modify the mem_params.json file with the parameters specified in the design sweep config file
                        mem_params_json_fpath = os.path.splitext(base_config["vlsi.inputs"]["sram_parameters"])[0]+f'_{mod_mem_params[0]["name"]}.json'
                        with open(os.path.splitext(base_config["vlsi.inputs"]["sram_parameters"])[0]+f'_{mod_mem_params[0]["name"]}.json', 'w') as fd:
                            json.dump(mod_mem_params, fd, sort_keys=False)
                        rad_gen_log(f"INFO: Writing memory params to {mem_params_json_fpath}",rad_gen_log_fd)
                        
                        """ MODIFIYING SRAM RTL"""
                        # Get just the filename of the sram sv file and append the new dims to it
                        mod_rtl_fname = os.path.splitext(sanitized_design["base_rtl_path"].split("/")[-1])[0]+f'_{mod_mem_params[0]["name"]}.sv'
                        # Modify the parameters for SRAM_ADDR_W and SRAM_DATA_W and create a copy of the base sram 
                        # TODO find a better way to do this rather than just creating a ton of files, the only thing I'm changing are 2 parameters in rtl
                        with open(sanitized_design["base_rtl_path"], 'r') as fd:
                            base_rtl = fd.read()
                        mod_sram_rtl = base_rtl
                        # Modify the parameters in rtl and create new dir for the sram
                        # Regex looks for parameters and will replace whole line
                        edit_param_re = re.compile(f"parameter\s+SRAM_ADDR_W.*",re.MULTILINE)
                        # Replace the whole line with the new parameter (log2 of depth fior SRAM_ADDR_W)
                        mod_sram_rtl = edit_param_re.sub(f"parameter SRAM_ADDR_W = {int(math.log2(depth))};",base_rtl)
                        
                        edit_param_re = re.compile(f"parameter\s+SRAM_DATA_W.*",re.MULTILINE)
                        # Replace the whole line with the new parameter (log2 of depth fior SRAM_ADDR_W)
                        mod_sram_rtl = edit_param_re.sub(f"parameter SRAM_DATA_W = {int(width)};",mod_sram_rtl)
                        # Look for the SRAM instantiation and replace the name of the sram macro, the below regex uses the comments in the rtl file to find the instantiation
                        # Inst starts with "START SRAM INST" and ends with "END SRAM INST"
                        edit_sram_inst_re = re.compile(f"^\s+//\s+START\sSRAM\sINST.*END\sSRAM\sINST",re.MULTILINE|re.DOTALL)

                        sram_inst_rtl = edit_sram_inst_re.search(mod_sram_rtl).group(0)
                        edit_sram_macro_name = re.compile(f"SRAM1RW.*\s")
                        edit_sram_inst = edit_sram_macro_name.sub(f'{mod_mem_params[0]["name"]} mem_0_0(\n',sram_inst_rtl)
                        # The correct RTL for the sram inst is in the edit_sram_inst string so we now will replace the previous sram inst with the new one
                        mod_sram_rtl = edit_sram_inst_re.sub(edit_sram_inst,mod_sram_rtl)
                        
                        base_rtl_dir = os.path.split(sanitized_design["base_rtl_path"])[0]
                        # Create a new dir for the modified sram
                        mod_rtl_dir = os.path.join(base_rtl_dir,f'{mod_mem_params[0]["name"]}')
                        
                        sp.call("mkdir -p " + mod_rtl_dir,shell=True)
                    
                        modified_sram_rtl_path = os.path.join(sanitized_design["rtl_dir_path"],mod_rtl_dir.split("/")[-1],mod_rtl_fname)
                        with open(modified_sram_rtl_path, 'w') as fd:
                            fd.write(mod_sram_rtl)
                        rad_gen_log(f"INFO: Writing sram rtl to {modified_sram_rtl_path}",rad_gen_log_fd)
                        
                        """ MODIFYING HAMMER CONFIG YAML FILES """
                        # Now we need to modify the base_config file to use the correct sram macro
                        for pc_idx, pc in enumerate(base_config["vlsi.inputs"]["placement_constraints"]):
                            # TODO this requires "SRAM" to be in the macro name which is possibly dangerous
                            if pc["type"] == "hardmacro" and "SRAM" in pc["master"]:
                                mod_base_config["vlsi.inputs"]["placement_constraints"][pc_idx]["master"] = mod_mem_params[0]["name"]

                        # Find design files in newly created rtl dir
                        design_files, _ = rec_get_flist_of_ext(mod_rtl_dir)
                        mod_base_config["synthesis"]["inputs.input_files"] = design_files
                        mod_base_config["vlsi.inputs"]["sram_parameters"] = os.path.splitext(base_config["vlsi.inputs"]["sram_parameters"])[0] + f'_{mod_mem_params[0]["name"]}.json'
                        # Write the modified base_config file to a new file
                        modified_config_path = os.path.splitext(sanitized_design["base_config_path"])[0]+f'_{mod_mem_params[0]["name"]}.yaml'
                        with open(modified_config_path, 'w') as fd:
                            yaml.safe_dump(mod_base_config, fd, sort_keys=False)    
                        rad_gen_log(f"INFO: Writing rad_gen yml config to {modified_config_path}",rad_gen_log_fd)
                # Accessing variables declared outside and initized in the loop
                # Compare generated RTL files to configs that exist and run all configs with paths to the generated RTL        
                run_configs = []
                for file in os.listdir(base_config_dir):
                    # TODO fix the below line, it only looks for if the SRAM keyword is contained in the file
                    if file.endswith(".yaml") and "SRAM" in file:
                        run_configs.append(os.path.join(base_config_dir,file))
                """ rad_gen flow settings are equal to the command line args typically expected in rad_gen """
                """
                for config in run_configs:
                    # below are the only flow settings which we actually need to run hammer 
                    sw_flow_settings = {
                        "top_level": "sram_wrapper",
                        "env_path" : args.env_path,
                        # We want a new obj dir for each run
                        "use_latest_obj_dir" : False,
                        "config_path" : config,
                    }
                    # TODO fix Hardcoded for now to run full flow
                    sw_run_stages = {
                        "sram" : True,
                        "syn" : True,
                        "par" : True,
                        "pt" : True
                    }
                    #Run the flow for each config
                    #rad_gen_flow(sw_flow_settings,sw_run_stages,[config])     
                    break     
                """  
            # TODO make this more general but for now this is ok
            # the below case should deal with any asic_param sweep we want to perform
            elif sanitized_design["type"] == 'rtl_params':
                mod_param_hdr_paths = edit_rtl_proj_params(sanitized_design["params"], sanitized_design["rtl_dir_path"], sanitized_design["base_param_hdr_path"],sanitized_design["base_config_path"])
                # read_in_rtl_proj_params(sanitized_design["params"],sanitized_design["top_level_module"],sanitized_design["rtl_dir_path"])
                for hdr_path in mod_param_hdr_paths:
                    rad_gen_log(f"PARAMS FOR PATH {hdr_path}",rad_gen_log_fd)
                    read_in_rtl_proj_params(sanitized_design["params"],sanitized_design["top_level_module"],sanitized_design["rtl_dir_path"],hdr_path)
                    """ We shouldn't need to edit the values of params/defines which are operations or values set to other params/defines """
                    """ EDIT PARAMS/DEFINES IN THE SWEEP FILE """
                    # TODO this assumes parameter sweep vars arent kept over multiple files
                    # copy original parameter file containing sweep vars
    else:
        """ USED FOR THE SRAM SWEEP RUN, I THINK THIS IS UNSAFE TO USE TODO REMOVE THIS"""
        # If the args for top level and rtl path are not set, we will use values from the config file
        """
        if rad_gen_flow_settings["top_level"] == '' or rad_gen_flow_settings["hdl_path"] == '':
            design_config = yaml.safe_load(open(rad_gen_flow_settings["config_path"]))
            # Assuming that the top level module and input files are set in the config file
            # Add additional input files which may exist in the module rtl_dir
            rad_gen_flow_settings["top_level"] = design_config["synthesis"]["inputs.top_module"]
            config_paths = [rad_gen_flow_settings["config_path"]]
        else:
        """
        # Edit the config file with cli args
        """ Check to make sure all parameters are assigned and modify if required to"""
        design_config, modified_config_path = modify_config_file(rad_gen_flow_settings)
        config_paths = [modified_config_path]

        # Run the flow
        rad_gen_flow(rad_gen_flow_settings,run_stages,config_paths)

        rad_gen_log("Done!",rad_gen_log_fd)
        sys.exit()    
    
    


if __name__ == '__main__':
    main()