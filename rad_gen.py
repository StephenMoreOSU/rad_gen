
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
from dataclasses import dataclass

from typing import Pattern
import datetime

from dataclasses import field

########################################## DATA STRUCTURES  ###########################################

@dataclass 
class ASIC_flow_settings:
    """ These are settings specific to a design running through the flow"""
    # Paths
    hdl_path: str = None
    config_path: str = None
    top_level_module: str = None
    # Stages being run
    run_sram: bool = False
    run_syn: bool = False
    run_par: bool = False
    run_pt: bool = False
    use_latest_obj_dir: bool = False
    manual_obj_dir: str = None
    # below are not exposed to the cli yet
    obj_dir_path: str = None
    # flow stages
    flow_stages: dict = field(default_factory = lambda: {
        "sram": {
            "name": "sram",
            "run": False,
        },
        "syn": {
            "name": "syn",
            "run": False,
            "tool": "cadence",
        },
        "par": {
            "name": "par",
            "run": False,
            "tool": "cadence",
        },
        "pt": {
            "name": "pt",
            "run": False,
            "tool": "synopsys",
        },
    })

""" STARTING SWEEP DATA STRUCTURES"""
@dataclass
class MultiDesign_settings:
    """
    Settings which are used by users for higher level data preperation 
    Ex.
     - Preparing designs to be swept via RTL/VLSI parameters
     - Using the SRAM mapper
    """
    sweep_config_path: str = ""
    # path which will look for obj files to be parsed
    result_search_path: str = ""

@dataclass
class Sweep_setting:
    """
    Sweep settings for a specific design
    Ex. a single design in which RTL parameters are swept
    """
    # Could probably remove the base config path TODO
    base_config_path: str = ""
    # The directory which will be searched through for all RTL files that need to be used in the design
    rtl_dir_path: str = ""
    # for RTL sweep
    param_sweep_hdr_dir_name: str = "param_sweep_headers"

""" ENDING SWEEP DATA STRUCTURES"""

@dataclass
class RADGen_settings:
    """ Settings which are specific to a user of the RADGen tool, across all designs"""
    env_path: str = ""
    openram_path: str = ""
    hammer_home_path: str = ""
    # utility stuff
    log_path: str = ""
    # Verbosity level
    # 0 - Brief output
    # 1 - Brief output + I/O interactions
    # 2 - Hammer and asic tool outputs will be printed to console
    log_verbosity: int = -1
    # top level path of rad gen tool
    rad_gen_home_path: str = os.path.expanduser("~/rad_gen")
    # default obj output directory
    design_output_path: str = os.path.join(rad_gen_home_path, "output_designs")
    top_level_rad_gen_config_path: str = None
    # input design structure
    input_design_dir_structure: dict = field(default_factory = lambda: {
        "configs": {
            "gen" : {}
        },
        "rtl" : {
            "src" : {},
            "verif" : {},
            "build" : {},
        }
    })

@dataclass
class VLSI_mode:
    enable: bool = False
    config_reuse: bool = False

@dataclass 
class RADGen_mode:
    """ 
    The mode in which the RADGen tool is running
    Ex. 
     - Sweep mode
     - Single design mode
    """
    tool_mode: str = ""
    sweep_gen: bool = False
    result_parse: bool = False
    vlsi_flow: VLSI_mode = VLSI_mode()

@dataclass
class SRAM_compiler_settings:
    rtl_out: str = os.path.expanduser("~/rad_gen/input_designs/sram/rtl/compiler_outputs")
    config_out: str = os.path.expanduser("~/rad_gen/input_designs/sram/configs/compiler_outputs")

@dataclass
class Regexes:
    wspace_re: Pattern = re.compile(r"\s+")
    find_params_re: Pattern = re.compile(f"parameter\s+\w+(\s|=)+.*;")
    find_defines_re: Pattern = re.compile(f"`define\s+\w+\s+.*")
    grab_bw_soft_bkt: Pattern = re.compile(f"\(.*\)")
    
    find_localparam_re: Pattern = re.compile(f"localparam\s+\w+(\s|=)+.*?;",re.MULTILINE|re.DOTALL)
    first_eq_re: Pattern = re.compile("\s=\s")
    find_soft_brkt_chars_re: Pattern = re.compile(f"\(|\)", re.MULTILINE)

    find_verilog_fn_re: Pattern = re.compile(f"function.*?function", re.MULTILINE|re.DOTALL)
    grab_verilog_fn_args: Pattern = re.compile(f"\(.*?\)",re.MULTILINE|re.DOTALL)
    find_verilog_fn_hdr: Pattern = re.compile("<=?")

    decimal_re: Pattern = re.compile("\d+\.{0,1}\d*",re.MULTILINE)
    signed_dec_re: Pattern = re.compile("\-{0,1}\d+\.{0,1}\d*",re.MULTILINE)
    sci_not_dec_re: Pattern = re.compile("\-{0,1}\d+\.{0,1}\d*e{0,1}\-{0,1}\d+",re.MULTILINE)
    # gds to area 

    

@dataclass
class Tech_info:
    lib: str = ""
    sram_lib_path: str = ""
    # Process settings in RADGen settings as we may need to perform post processing (ASAP7)
    pdk_rundir: str = "" 
    cds_lib: str = ""


@dataclass
class Script_info:
    # FILENAMES OF VARIOUS SCRIPTS
    gds_to_area_fname: str = "get_area"

@dataclass
class Report_info:
    gds_area_fname : str = "gds_area.rpt"
    power_lookup : dict = field(default_factory = lambda: {
        "W": float(1),
        "mW": float(1e-3),
        "uW": float(1e-6),
        "nW": float(1e-9),
        "pW": float(1e-12)
    })
    power_display_unit = "mW"
    timing_display_unt = "ps"
    area_display_unit = "um^2"



# struct holding all regexes used in rad gen
res = Regexes()

tech_info = Tech_info(
        lib="asap7",
        # sram_lib_path=os.path.expanduser("~/hammer/src/hammer-vlsi/technology/asap7/sram_compiler/memories"),
        # pdk_rundir=os.path.expanduser("~/ASAP_7_IC/asap7_rundir"),
        cds_lib="asap7_TechLib"
    )


sram_compiler_settings = SRAM_compiler_settings()

script_info = Script_info()
report_info = Report_info()

# Create the global variables which will be later modified
rad_gen_settings = RADGen_settings()
asic_flow_settings = ASIC_flow_settings()
multi_design_settings = MultiDesign_settings()
# Could have multiple sweeps per design
sweep_settings = Sweep_setting()

# modes of operation for RAD Gen
rad_gen_mode = RADGen_mode()
vlsi_mode = VLSI_mode()
########################################## DATA STRUCTURES  ###########################################



########################################## GENERAL UTILITIES ##########################################
def truncate(f, n):
    '''Truncates/pads a float f to n decimal places without rounding'''
    s = '{}'.format(f)
    if 'e' in s or 'E' in s:
        return '{0:.{1}f}'.format(f, n)
    i, p, d = s.partition('.')
    return '.'.join([i, (d+'0'*n)[:n]])

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

def run_shell_cmd_no_logs(cmd_str):
    rad_gen_log(f"Running: {cmd_str}",rad_gen_log_fd)
    run_out = sp.Popen([cmd_str], executable='/bin/bash', env=cur_env, stderr=sp.PIPE, stdout=sp.PIPE, shell=True)
    run_stdout = ""
    for line in iter(run_out.stdout.readline, ""):
        if(run_out.poll() is None):
            run_stdout += line.decode("utf-8")
            if rad_gen_settings.log_verbosity >= 2: 
                sys.stdout.buffer.write(line)
        else:
            break
    if rad_gen_settings.log_verbosity >= 2: 
        _, run_stderr = run_out.communicate()
    else:
        run_stdout, run_stderr = run_out.communicate()
        run_stdout = run_stdout.decode("utf-8")
    run_stderr = run_stderr.decode("utf-8")
    return run_stdout, run_stderr


def run_csh_cmd(cmd_str):
    rad_gen_log(f"Running: {cmd_str}",rad_gen_log_fd)
    sp.call(['csh', '-c', cmd_str])

    

def rec_get_flist_of_ext(design_dir_path,hdl_exts):
    """
    Takes in a path and recursively searches for all files of specified extension, returns dirs of those files and file paths in two lists
    """
    # hdl_exts = [f"({ext})" for ext in hdl_exts]

    # design_files = []
    # ext_str = ".*" + '|'.join(hdl_exts) + "$"
    # ext_re = re.compile(ext_str)
    design_folder = os.path.expanduser(design_dir_path)
    design_files = [os.path.abspath(os.path.join(r,fn)) for r, _, fs in os.walk(design_folder) for fn in fs if fn.endswith(tuple(hdl_exts))]
    design_dirs = [os.path.abspath(r) for r, _, fs in os.walk(design_folder) for fn in fs if fn.endswith(tuple(hdl_exts))]
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

# def write_lib_to_db_script(obj_dir):
#     # create PT run-dir
#     pt_outpath = os.path.join(obj_dir,"pt-rundir")
#     if not os.path.isdir(pt_outpath) :
#         os.mkdir(pt_outpath)
#     lib_dir = os.path.join(obj_dir,"tech-asap7-cache/LIB/NLDM")

#     file_lines = ["enable_write_lib_mode"]
#     for lib in os.listdir(lib_dir):
#         read_lib_cmd = "read_lib " + f"{os.path.join(lib_dir,lib)}"
#         write_lib_cmd = "write_lib " + f"{os.path.splitext(lib)[0]} " + "-f db " + "-o " f"{os.path.splitext(os.path.join(lib_dir,lib))[0]}.db"
#         file_lines.append(read_lib_cmd)
#         file_lines.append(write_lib_cmd)

    
#     fd = open(os.path.join(pt_outpath,"lib_to_db.tcl"),"w")
#     for line in file_lines:
#         file_write_ln(fd,line)
#     file_write_ln(fd,"quit")
#     fd.close()


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

def write_pt_timing_script(power_in_json_data, obj_dir):
    """
    writes the tcl script for timing analysis using Synopsys Design Compiler, tested under 2017 version
    This should look for setup/hold violations using the worst case (hold) and best case (setup) libs
    """

    # Make sure that the $STDCELLS env var is set and use it to find the .lib files to use for Primetime
    search_paths = "/CMC/tools/synopsys/syn_vN-2017.09/libraries/syn /CMC/tools/synopsys/syn_vN-2017.09/libraries/syn_ver /CMC/tools/synopsys/syn_vN-2017.09/libraries/sim_ver"
    
    db_dirs =  [os.path.join(rad_gen_settings.rad_gen_home_path,db_lib) for db_lib in ["sram_db_libs","asap7_db_libs"] ]

    # options are ["TT","FF","SS"]
    # corner_filt_str = "SS"
    # options are ["SLVT", "LVT", "RVT", "SRAM"] in order of decreasing drive strength
    # transistor_type_str = "LVT"
    
    target_libs = " ".join([os.path.join(db_dir,lib) for db_dir in db_dirs for lib in os.listdir(db_dir) if (lib.endswith(".db") )])
    
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
    pnr_design_outpath = os.path.join(obj_dir,"par-rundir",f'{asic_flow_settings.top_level_module}_FINAL')
    if not os.path.isdir(pnr_design_outpath) :
        rad_gen_log("Couldn't find output of pnr stage, Exiting...",rad_gen_log_fd)
        sys.exit(1)


    # report timing / power commands
    report_timing_cmd = "report_timing > " + os.path.join(report_path,"timing.rpt")
    report_power_cmd = "report_power > " + os.path.join(report_path,"power.rpt")



    case_analysis_cmds = ["#MULTIMODAL ANALYSIS DISABLED"]
        
    #get switching activity and toggle rates from power_constraints tcl file
    power_constraints_fd = open(os.path.join(pnr_design_outpath,f'{asic_flow_settings.top_level_module}_power_constraints.tcl'),"r")
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

def get_hammer_config(flow_stage_trans):
    #find flow stage transition, split up Ex. "syn-to-par"
    flow_from = flow_stage_trans.split("-")[0]
    flow_to = flow_stage_trans.split("-")[2]
    hammer_cmd = f'hammer-vlsi -e {rad_gen_settings.env_path} -p {asic_flow_settings.config_path} -p {asic_flow_settings.obj_dir_path}/{flow_from}-rundir/{flow_from}-output.json -o {asic_flow_settings.obj_dir_path}/{asic_flow_settings.top_level_module}-{flow_stage_trans}.json --obj_dir {asic_flow_settings.obj_dir_path} {flow_stage_trans}'
    stdout, stderr = run_shell_cmd_no_logs(hammer_cmd)
    
    trans_config_path = os.path.join(asic_flow_settings.obj_dir_path,f'{asic_flow_settings.top_level_module}-{flow_from}-to-{flow_to}.json')
    return trans_config_path


def run_hammer_stage(flow_stage, config_paths):
    # config_paths for the next stage of the flow
    ret_config_path = ""
    # format config paths if multiple are needed
    config_path_args = [f'-p {c_p}' for c_p in config_paths]
    config_path_args = " ".join(config_path_args)
    # rad_gen_log(f'Running hammer with input configs: {" ".join(config_paths)}...',rad_gen_log_fd)
    hammer_cmd = f'hammer-vlsi -e {rad_gen_settings.env_path} {config_path_args} --obj_dir {asic_flow_settings.obj_dir_path} {flow_stage}'
    stdout, stderr = run_shell_cmd_no_logs(hammer_cmd)
    
    # return output config path for flow stage
    ret_config_path = os.path.join(asic_flow_settings.obj_dir_path,f"{flow_stage}-rundir/{flow_stage}-output.json")
    
    return ret_config_path, stdout, stderr
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
    exts = ['.v','.sv','.vhd',".vhdl"]
    design_files, design_dirs = rec_get_flist_of_ext(asic_flow_settings.hdl_path,exts)

    with open(asic_flow_settings.config_path, 'r') as yml_file:
        design_config = yaml.safe_load(yml_file)

    design_config["synthesis"]["inputs.input_files"] = design_files
    design_config["synthesis"]["inputs.top_module"] = asic_flow_settings.top_level_module
    # If the user specified valid search paths we should not override them but just append to them
    
    # TODO ADD THE CONDITIONAL TO CHECK BEFORE CONCAT, this could be cleaner but is ok for now, worst case we have too many serach paths
    if("inputs.hdl_search_paths" in design_config["synthesis"].keys()):
        design_config["synthesis"]["inputs.hdl_search_paths"] = design_config["synthesis"]["inputs.hdl_search_paths"] + design_dirs
    else:
        design_config["synthesis"]["inputs.hdl_search_paths"] = design_dirs
    
    # remove duplicates
    design_config["synthesis"]["inputs.hdl_search_paths"] = list(dict.fromkeys(design_config["synthesis"]["inputs.hdl_search_paths"])) 
    
    # init top level placement constraints
    design_config["vlsi.inputs"]["placement_constraints"][0]["path"] = asic_flow_settings.top_level_module

    modified_config_path = os.path.splitext(asic_flow_settings.config_path)[0]+"_mod.yaml"
    with open(modified_config_path, 'w') as yml_file:
        yaml.safe_dump(design_config, yml_file, sort_keys=False) 
    #default to 70% utilization (TODO)
    
    # Get in new design config to use for output directory names s.t. we don't overwrite previous runs when doing sweeps
    with open(modified_config_path, 'r') as yml_file:
        design_config = yaml.safe_load(yml_file)

    # sys.exit(1)
    return design_config, modified_config_path


def find_newest_obj_dir(obj_dir_fmt):
    # cwd = os.getcwd()
    # verify that we're in the rad_gen dir
    if os.getcwd().split("/")[-1] != "rad_gen":
        rad_gen_log("Error: you must run this script from the rad_gen directory",rad_gen_log_fd)
        sys.exit(1)
    search_dir = os.path.join(rad_gen_settings.design_output_path, asic_flow_settings.top_level_module)
    print(search_dir)
    # find the newest obj_dir
    obj_dir_list = []
    for file in os.listdir(search_dir):
        dt_fmt_bool = False
        try:
            datetime.datetime.strptime(file, obj_dir_fmt)
            dt_fmt_bool = True
        except ValueError:
            pass
        if os.path.isdir(os.path.join(search_dir, file)) and dt_fmt_bool:
            obj_dir_list.append(os.path.join(search_dir, file))
    date_times = [datetime.datetime.strptime(os.path.basename(date_string), obj_dir_fmt) for date_string in obj_dir_list]
    sorted_obj_dirs = [obj_dir for _, obj_dir in sorted(zip(date_times, obj_dir_list), key=lambda x: x[0], reverse=True)]
    try:
        obj_dir_path = sorted_obj_dirs[0]
    except:
        rad_gen_log("Warning: no latest obj_dir found in design output directory, creating new one", rad_gen_log_fd)
        obj_dir_path = None
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
    if(rad_gen_settings.log_verbosity >= 0):
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

    return mod_param_out_fpath, mod_config_path

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
    mod_config_paths = []
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
                    mod_param_fpath, mod_config_fpath = replace_rtl_param(top_p_val_name, p_names_i, p_vals_i, base_config_path, base_param_hdr, base_param_hdr_path, param_sweep_hdr_dir)
                    mod_parameter_paths.append(mod_param_fpath)
                    mod_config_paths.append(mod_config_fpath)
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
                    rad_gen_log("Writing modified parameter file to: "+mod_param_out_fpath,rad_gen_log_fd)
                    with open(mod_param_out_fpath,"w") as param_out_fd:
                        param_out_fd.write(mod_param_hdr)
                    mod_parameter_paths.append(mod_param_out_fpath)
                    """ GENERATING AND WRITING RAD GEN CONFIG FILES """
                    with open(base_config_path,"r") as config_fd:
                        rad_gen_config = yaml.safe_load(config_fd)
                    rad_gen_config["synthesis"]["inputs.hdl_search_paths"].append(os.path.abspath(mod_param_dir_str))
                    mod_config_path = os.path.splitext(base_config_path)[0]+f'_{p_name}_{p_val}.yaml'
                    print("Writing modified config file to: "+mod_config_path,rad_gen_log_fd)
                    with open(mod_config_path,"w") as config_fd:
                        yaml.safe_dump(rad_gen_config, config_fd, sort_keys=False)
                    mod_config_paths.append(mod_config_path)

    return mod_parameter_paths, mod_config_paths


def search_path_list_for_file(path_list,fname):
    found_file = False
    file_path = ""
    for path in path_list:
        if(os.path.isfile(os.path.join(path,fname))):
            if found_file == True:
                rad_gen_log(f"WARNING: {fname} found in multiple paths",rad_gen_log_fd)
            file_path = os.path.join(path,fname)
    return file_path

def get_params_and_defines_from_rtl(rtl_text, rtl_preproc_vals, param_define_deps):
    for inc_line in rtl_text.split("\n"): 
        # Look for parameters
        if res.find_params_re.search(inc_line):
            # TODO this parameter re will not work if no whitespace between params
            clean_line = " ".join(res.wspace_re.split(inc_line)[1:]).replace(";","")
            # Get the parameter name and value
            param_name = clean_line.split("=")[0].replace(" ","")
            param_val = clean_line.split("=")[1].replace(" ","").replace("`","")


            # create dep list for params
            for i in range(len(rtl_preproc_vals)):
                if rtl_preproc_vals[i]["name"] in param_val:
                    param_define_deps.append(rtl_preproc_vals[i]["name"])

            # Add the parameter name and value to the design_params dict
            #rtl_preproc["params"][param_name] = str(param_val)
            rtl_preproc_vals.append({"name" : param_name, "value" : str(param_val),"type": "param"})

        elif res.find_defines_re.search(inc_line):
            # TODO this define re will not work if no whitespace between params
            clean_line = " ".join(res.wspace_re.split(inc_line)[1:])
            # Get the define name and value
            define_name = res.wspace_re.split(clean_line)[0]
            if res.grab_bw_soft_bkt.search(clean_line):
                define_val = res.grab_bw_soft_bkt.search(clean_line).group(0)
            else:
                define_val = res.wspace_re.split(clean_line)[1].replace("`","")
            # create dep list for defines
            for i in range(len(rtl_preproc_vals)):
                if rtl_preproc_vals[i]["name"] in define_val:
                    param_define_deps.append(rtl_preproc_vals[i]["name"])
            #rtl_preproc["defines"][define_name] = str(define_val)
            rtl_preproc_vals.append({"name": define_name, "value" : str(define_val),"type": "define"})
    return rtl_preproc_vals, param_define_deps

# def get_functions_from_rtl(rtl_text):
#     tmp_rtl_text = rtl_text
#     while res.find_function_re.search(tmp_rtl_text):
#         function_text = res.find_function_re.search(tmp_rtl_text).group(0)
#         lines = function_text.split(";")
#         top_line = lines[0]
#         args = res.find_function_args_re.search(top_line).group(0).split(",")
#         function_text = re.sub(pattern=",".join(args),string=function_text,repl="")
#         fn_hdr = res.find_
        
#         tmp_rtl_text = res.find_function_re.sub(string=tmp_rtl_text,repl="",count=1)


# def clogb(val):
#     clogb = 0
#     val = val - 1
#     while val > 0:
#         val >>= 1
#         clogb +=1
#     return clogb

# def croot(val,base):
#     croot = 0
#     i = 0
#     while i < val:hdl_path
#         croot += 1
#         i = 1
#         for _ in range(base):
#             i *= croot
#     return croot

def read_in_rtl_proj_params_all(top_level, hdl_search_paths):
    init_globals()

    top_lvl_re = re.compile(f"module\s+{top_level}",re.MULTILINE)
    # Find all parameters which will be used in the design (ie find top level module rtl, parse include files top to bottom and get those values )
    """ FIND TOP LEVEL MODULE IN RTL FILES """
    top_lvl_match_found = False
    top_lvl_rtl_text = ""
    # creating another hdl paths var to deal with below TODO issue
    new_hdl_paths = []
    for path in hdl_search_paths:
        # This is to fix the below TODO, I suppose its ok
        cur_paths = res.wspace_re.split(path)
        for c_path in cur_paths:
            if os.path.isdir(c_path):
                new_hdl_paths.append(c_path)
                # TODO fix issue with the NoC sweeps in which the hdl search paths are set to two paths seperated with a space
                # Ex. /fs1/eecg/vaughn/morestep/rad_gen/input_designs/NoC/src /fs1/eecg/vaughn/morestep/rad_gen/input_designs/NoC/src/clib
                for rtl_file in os.listdir(c_path):
                    if rtl_file.endswith(".v") or rtl_file.endswith(".sv") or rtl_file.endswith(".vhd") or rtl_file.endswith(".vhdl") and os.path.isfile(os.path.join(c_path,rtl_file)):
                        # read in the file with comments removed
                        rtl_text = c_style_comment_rm(open(os.path.join(c_path,rtl_file)).read())
                        if top_lvl_re.search(rtl_text):
                            print(f"Found top level module {top_level} in {c_path}/{rtl_file}")
                            if top_lvl_match_found == True:
                                rad_gen_log(f"ERROR: Multiple top level modules found in rtl files",rad_gen_log_fd)
                                sys.exit(1)
                            top_lvl_match_found = True
                            top_lvl_rtl_text = rtl_text
    """ RTL TOP LEVEL FOUND AT THIS POINT"""
    # lists which will hold parameters and a list of all required dependancies as we move through the includes
    rtl_preproc_vals = []
    param_define_deps = []
    for line in top_lvl_rtl_text.split("\n"):
        # Look for include statements
        if "include" in line:
            # Get the include file path
            include_fname = res.wspace_re.split(line)[1].replace('"','')
            fpath = search_path_list_for_file(new_hdl_paths,include_fname)
            include_rtl = c_style_comment_rm(open(fpath).read())
            rtl_preproc_vals, param_define_deps = get_params_and_defines_from_rtl(include_rtl,rtl_preproc_vals,param_define_deps)
    """ NOW WE HAVE A LIST OF ALL PARAMS AND DEFINES IN THE RTL & THEIR DEPENDANCIES """
    # remove duplicate dependancies
    # Only using parsing technique of looking for semi colon in localparams as these are expected to have larger operations
    # Not parsing lines as we need multiline capture w regex
    tmp_top_lvl_rtl = top_lvl_rtl_text
    local_param_matches = []
    # TODO allow for parameters / defines to also be defined in the top level module (not just in the includes)
    # Searching through the text in this way preserves initialization order
    while res.find_localparam_re.search(tmp_top_lvl_rtl):
        local_param = res.find_localparam_re.search(tmp_top_lvl_rtl).group(0)
        local_param_matches.append(local_param)
        tmp_top_lvl_rtl = tmp_top_lvl_rtl.replace(local_param,"")
    """ NOW WE HAVE A LIST OF ALL LOCALPARAMS IN THE TOP LEVEL RTL """
    """ EVALUATING BOOLEANS FOR LOCAL PARAMS W PARAMS AND DEFINES """
    
    # We are going to make .h and .c files which we can use the gcc preproc engine to evaluate the defines and local parameters
    # Loop through all parameters and find its dependancies on other parameters
    for local_param_str in local_param_matches:
        """ CREATING LIST OF REQUIRED DEPENDANCIES FOR ALL PARAMS """
        local_param_name = re.sub("localparam\s+",repl="",string=res.first_eq_re.split(local_param_str)[0]).replace(" ","").replace("\n","")
        local_param_val = res.first_eq_re.split(local_param_str)[1]
        rtl_preproc_vals.append({"name": local_param_name, "value": local_param_val, "type": "localparam"})

    
    """ CONVERT SV/V LOCALPARAMS TO C DEFINES """
    # Write out localparams which need to be evaluated to a temp dir
    tmp_dir = "/tmp/rad_gen_tmp"
    if not os.path.exists(tmp_dir):
        os.mkdir(tmp_dir)
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



    # rtl_preproc_vals 
    for val in rtl_preproc_vals:
        clean_c_def_val = val["value"].replace("\n","").replace(";","").replace("`","")
        c_def_str = "#define " + val["name"] + " (" + clean_c_def_val + ")"
        print(c_def_str,file=header_fd)
    header_fd.close()
    sys.exit(1)
    # Look through sweep param list in config file and match them to the ones found in design
    for val in rtl_preproc_vals:
        # If they match, write the c code which will print the parameter and its value
        main_lines.append("\t" + f'printf("{val["name"]}: %d \n",{val["name"]});'.encode('unicode_escape').decode('utf-8'))
                
    for line in main_lines:
        print(line,file=main_fd)
    print("}",file=main_fd)
    main_fd.close()
    # This runs the c file which prints out evaluated parameter values set in the verilog
    gcc_out = sp.run(["/usr/bin/gcc",f"{rtl_preproc_fname}.h",f"{rtl_preproc_fname}.c"],stderr=sp.PIPE,stdout=sp.PIPE,stdin=sp.PIPE)#,"-o",f'{os.path.join(tmp_dir,"print_params")}'])
    sp.run(["a.out"])
    sp.run(["rm","a.out"])
    # Now we have a list of dictionaries containing the localparam string and thier dependancies

    sys.exit(1)
    # Found the file with the top level module




def read_in_rtl_proj_params(rtl_params, top_level_mod, rtl_dir_path, sweep_param_inc_path=False):
    wspace_re = re.compile(r"\s+")
    # Now that we have a mem_params.json and sram_config.yaml file for each design, we can run the flow for each design in parallel (up to user defined amount)
    find_params_re = re.compile(f"parameter\s+\w+(\s|=)+.*;")
    find_defines_re = re.compile(f"`define\s+\w+\s+.*")
    grab_bw_soft_bkt = re.compile(f"\(.*\)")
    
    find_localparam_re = re.compile(f"localparam\s+\w+(\s|=)+.*?;",re.MULTILINE|re.DOTALL)

    # Find all parameters which will be used in the design (ie find top level module rtl, parse include files top to bottom and get those values )
    """ FIND TOP LEVEL MODULE IN RTL FILES """
    # TODO fix this, if there are multiple instantiations of top level in same directory, there could be a problem
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
    param_print_stdout = sp.run(["a.out"],stderr=sp.PIPE,stdout=sp.PIPE,stdin=sp.PIPE)
    rad_gen_log(param_print_stdout.stdout.decode("utf-8"),rad_gen_log_fd)
    sp.run(["rm","a.out"])

    param_print_stdout = param_print_stdout.stdout.decode("utf-8")
    params = []
    for line in param_print_stdout.split("\n"):
        if line != "":
            x = res.wspace_re.sub(repl="",string=line).split(":")
            p_dict = {x[0]:x[1]}
            params.append(p_dict)

    return params


def parse_report_c(top_level_mod, report_path, rep_type, flow_stage: dict, summarize=False):
    # print( report_path )
    # pwr_lookup ={
    #     "W": float(1),
    #     "mW": float(1e-3),
    #     "uW": float(1e-6),
    #     "nW": float(1e-9),
    #     "pW": float(1e-12)
    # }
    
    # wspace_re = re.compile("\s+", re.MULTILINE)
    # decimal_re = re.compile("\d+\.{0,1}\d*",re.MULTILINE)
    # signed_dec_re = re.compile("\-{0,1}\d+\.{0,1}\d*",re.MULTILINE)
    if flow_stage["name"] == "syn":
        cadence_hdr_catagories = ["Instance","Module","Cell Count","Cell Area","Net Area","Total Area"]
        # this regex should match text in the header line which shows result catagories and below
        cadence_area_hdr_re_str = r'(\s+){0,1}'.join(cadence_hdr_catagories) + r'.*'
        cadence_area_hdr_re = re.compile(cadence_area_hdr_re_str, re.MULTILINE|re.DOTALL)
        # cadence_area_hdr_re = re.compile("^\s+Instance\s+Module.*Cell\s+Count.*Cell\s+Area.*Total\s+Area.*", re.MULTILINE|re.DOTALL)
        cadence_arrival_time_re = re.compile("Data\sPath:-.*$",re.MULTILINE)
    elif flow_stage["name"] == "par":
        cadence_hdr_catagories = ["Hinst Name","Module Name","Inst Count","Total Area"]
        cadence_area_hdr_re = re.compile("^\s+Hinst\s+Name\s+Module\sName\s+Inst\sCount\s+Total\sArea.*", re.MULTILINE|re.DOTALL)
        cadence_arrival_time_re = re.compile("Arrival:=.*$",re.MULTILINE)

    if flow_stage["name"] == "syn":
        if flow_stage["tool"] == "cadence":
            cadence_hdr_catagories = ["Leakage","Internal","Switching","Total","Row%"]

    cadence_timing_grab_re = re.compile("Path(.*?#-+){3}",re.MULTILINE|re.DOTALL)
    cadence_timing_setup_re = re.compile("Setup:-.*$",re.MULTILINE)
    
    unit_re_str = "(" + "|".join([f"({unit})" for unit in report_info.power_lookup.keys()]) + ")"                  
    
    grab_val_re_str = f"\d+\.{{0,1}}\d*.*?{unit_re_str}"
    synopsys_grab_pwr_val_re = re.compile(grab_val_re_str)
    
    report_list = []

    # parse synopsys report
    if(rep_type == "area"):
        area_rpt_text = open(report_path,"r").read()
        # removes stuff above the header so we only have info we need
        area_rpt_text = cadence_area_hdr_re.search(area_rpt_text).group(0)
        for line in area_rpt_text.split("\n"):
            report_dict = {}
            # below conditional finds the header line
            sep_line = res.wspace_re.split(line)
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
                if summarize:
                    break
    elif(rep_type == "timing"):
        timing_rpt_text = open(report_path,"r").read()
        if flow_stage["tool"] == "cadence":
            timing_path_text = timing_rpt_text
            while cadence_timing_grab_re.search(timing_rpt_text):
                timing_dict = {}
                timing_path_text = cadence_timing_grab_re.search(timing_rpt_text).group(0)
                for line in timing_path_text.split("\n"):
                    if cadence_timing_setup_re.search(line):
                        timing_dict["Setup"] = float(res.decimal_re.findall(line)[0])
                    elif cadence_arrival_time_re.search(line):
                        timing_dict["Arrival"] = float(res.decimal_re.findall(line)[0])
                    elif "Slack" in line:
                        timing_dict["Slack"] = float(res.signed_dec_re.findall(line)[0])
                    if "Setup" in timing_dict and "Arrival" in timing_dict:
                        timing_dict["Delay"] = timing_dict["Arrival"] + timing_dict["Setup"]
                    


                report_list.append(timing_dict)
                if summarize:
                    break
                timing_rpt_text = timing_rpt_text.replace(timing_path_text,"")
        elif flow_stage["tool"] == "synopsys":
            timing_dict = {}
            for line in timing_rpt_text.split("\n"):
                if "library setup time" in line:
                    timing_dict["Setup"] = float(res.decimal_re.findall(line)[0])
                elif "data arrival time" in line:
                    timing_dict["Arrival"] = float(res.decimal_re.findall(line)[0])
                elif "slack" in line:
                    timing_dict["Slack"] = float(res.signed_dec_re.findall(line)[0])
                elif "Setup" in timing_dict and "Arrival" in timing_dict:
                    timing_dict["Delay"] = timing_dict["Arrival"] + timing_dict["Setup"]
                # This indicates taht all lines have been read in and we can append the timing_dict
            report_list.append(timing_dict)
    elif(rep_type == "power"):
        power_rpt_text = open(report_path,"r").read()
        if flow_stage["tool"] == "synopsys":
            power_dict = {}
            for line in power_rpt_text.split("\n"):
                if "Total Dynamic Power" in line:
                    for unit in report_info.power_lookup.keys():
                        if f" {unit} " in line or f" {unit}" in line:
                            units = report_info.power_lookup[unit]
                            break
                    power_dict["Dynamic"] = float(res.decimal_re.findall(line)[0]) * units
                    # Check to make sure that the total has multiple values associated with it
                elif "Total" in line and len(res.decimal_re.findall(line)) > 1:
                    pwr_totals = []
                    pwr_vals_line = line
                    while synopsys_grab_pwr_val_re.search(pwr_vals_line):
                        pwr_val = synopsys_grab_pwr_val_re.search(pwr_vals_line).group(0)
                        for unit in report_info.power_lookup.keys():
                            if f" {unit} " in pwr_val or f" {unit}" in pwr_val:
                                units = report_info.power_lookup[unit]
                                break
                        pwr_total = float(res.wspace_re.split(pwr_val)[0]) * units
                        pwr_totals.append(pwr_total)
                        pwr_vals_line = pwr_vals_line.replace(pwr_val,"")
                    power_dict["Total"] = pwr_totals[-1]
            report_list.append(power_dict)
        elif flow_stage["tool"] == "cadence":
            power_dict = {}
            for line in power_rpt_text.split("\n"):
                if "Power Unit" in line:
                    for unit in report_info.power_lookup.keys():
                        if unit in line:
                            units = report_info.power_lookup[unit]
                            break
                if flow_stage["name"] == "par":
                    if "Total Internal Power:" in line:
                        power_dict["Internal"] = float(res.decimal_re.findall(line)[0]) * units
                    elif "Total Switching Power:" in line:
                        power_dict["Leakage"] = float(res.decimal_re.findall(line)[0]) * units
                    elif "Total Leakage Power:" in line:
                        power_dict["Switching"] = float(res.decimal_re.findall(line)[0]) * units
                    elif "Total Power:" in line:
                        power_dict["Total"] = float(res.decimal_re.findall(line)[0]) * units
                elif flow_stage["name"] == "syn":
                    if "Subtotal" in line:
                        power_vals = [ float(str_val) for str_val in res.sci_not_dec_re.findall(line)]
                        power_dict = {catagory: float(power_vals[idx]) * units for idx, catagory in enumerate(cadence_hdr_catagories) }

            report_list.append(power_dict)

    
    return report_list


def get_report_results(top_level_mod: str, report_dir_path: str, flow_stage: dict) -> dict:
    results = {}
    if os.path.isdir(report_dir_path):
            for file in os.listdir(report_dir_path):
                if os.path.isfile(os.path.join(report_dir_path, file)) and file.endswith(".rpt"):
                    if("area" in file and "detailed" not in file):
                        results["area"] = parse_report_c(top_level_mod, os.path.join(report_dir_path, file), "area", flow_stage, summarize=False)
                    elif("time" in file or "timing" in file):
                        results["timing"] = parse_report_c(top_level_mod, os.path.join(report_dir_path, file), "timing", flow_stage, summarize=False)
                    elif("power" in file): 
                        results["power"] = parse_report_c(top_level_mod, os.path.join(report_dir_path, file), "power", flow_stage, summarize=False)
    else:
        rad_gen_log(f"Warning: {flow_stage['name']} report path does not exist", rad_gen_log_fd)
    return results 

def parse_output(top_level_mod, output_path):
    syn_dir = "syn-rundir"
    par_dir = "par-rundir"
    pt_dir = "pt-rundir"
    # Loop through the output dir and find the relevant files to each stage of the flow
    syn_report_path = os.path.join(output_path,syn_dir,"reports")
    par_report_path = os.path.join(output_path,par_dir)
    pt_report_path = os.path.join(output_path,pt_dir,"reports")
    syn_results = get_report_results(top_level_mod, syn_report_path, asic_flow_settings.flow_stages["syn"])
    par_results = get_report_results(top_level_mod, par_report_path, asic_flow_settings.flow_stages["par"])
    pt_results = get_report_results(top_level_mod, pt_report_path, asic_flow_settings.flow_stages["pt"])
    return syn_results, par_results, pt_results


def get_gds_area_from_rpt(obj_dir_fpath):
    with open(os.path.join(obj_dir_fpath,report_info.gds_area_fname),"r") as f:
        for line in f:
            print(line)
            if "Area" in line:
                area = float(res.decimal_re.findall(line)[-1]) 
    return area

def gen_report_to_csv(report: dict):
    """
        Takes report which is a complete or incomplete asic flow run and will take the highest fidelity results and return it to a dict that can be used to write to a csv
    """
    report_to_csv = {}

    # This is where if there are empty reports for a particular 
    # flow stages are in order of fidelity
    # General input parameters
    if "target_freq" in report:
        report_to_csv["Target Freq"] = report["target_freq"]
    # TIMING
    for flow_stage in ["pt", "par", "syn"]:
        if report[flow_stage] != None and "timing" in report[flow_stage]:
            if len(report[flow_stage]["timing"]) > 0:
                if "Slack" in report[flow_stage]["timing"][0]:
                    report_to_csv["Slack"] = float(report[flow_stage]["timing"][0]["Slack"])
                if "Delay" in report[flow_stage]["timing"][0]:
                    report_to_csv["Delay"] = float(report[flow_stage]["timing"][0]["Delay"])
                report_to_csv["Timing SRC"] = flow_stage
        # For the first flow stage which has timing results, we can break out of the loop
        if "Slack" and "Delay" in report_to_csv:
            break
    # AREA
    for flow_stage in ["pt", "par", "syn"]:
        if report[flow_stage] != None and "area" in report[flow_stage]:
            if len(report[flow_stage]["area"]) > 0:
                if "Hinst Name" in report[flow_stage]["area"][0]:
                    report_to_csv["Top Level Inst"] = report[flow_stage]["area"][0]["Hinst Name"]
                if "Total Area" in report[flow_stage]["area"][0]:
                    report_to_csv["Total Area"] = float(report[flow_stage]["area"][0]["Total Area"])
                report_to_csv["Area SRC"] = flow_stage
        if "Top Level Inst" and "Total Area" in report_to_csv:
            break
    # POWER
    for flow_stage in ["pt", "par", "syn"]:
        if report[flow_stage] != None and "power" in report[flow_stage]:
            if len(report[flow_stage]["power"]) > 0:
                if "Total" in report[flow_stage]["power"][0]:
                    report_to_csv["Total Power"] = float(report[flow_stage]["power"][0]["Total"])
                report_to_csv["Power SRC"] = flow_stage
        if "Total Power" in report_to_csv:
            break
    

    if "gds_area" in report:
        report_to_csv["GDS Area"] = float(report["gds_area"])
    if "obj_dir" in report:
        report_to_csv["Obj Dir"] = report["obj_dir"]
    if "sram_macros" in report:
        report_to_csv["SRAM Macros"] = report["sram_macros"]
    if "sram_macro_lef_areas" in report:
        report_to_csv["SRAM LEF Areas"] = report["sram_macro_lef_areas"]
    if "num_macros" in report:
        report_to_csv["Num Macros"] = report["num_macros"]

    for key,val in report_to_csv.items():
        if isinstance(val,float):
            if "e" in str(val):
                report_to_csv[key] = '{0:7e}'.format(val)
            else:
                report_to_csv[key] = round(val,7)

    return report_to_csv

def noc_prse_area_brkdwn(report):
    report_to_csv = {}

    report_to_csv["Obj Dir"] = report["obj_dir"]

    for p in report["rtl_params"]:
        for k,v in p.items():
            report_to_csv[k] = v

    total_area = float(report["par"]["area"][0]["Total Area"])
    print(f'Total Area: {total_area}')
    report_to_csv["Total Area"] = total_area

    gds_area = float(report["gds_area"])
    report_to_csv["GDS Area"] = gds_area
    print(f'GDS Area: {gds_area}')
    # input modules
    num_ports_param_idx = next(( index for (index, d) in enumerate(report["rtl_params"]) if "num_ports" in d.keys()), None)
    if(num_ports_param_idx != None): 
        num_ports = int(report["rtl_params"][num_ports_param_idx]["num_ports"]) 
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
    
    if "timing" in report["pt"].keys():
        report_to_csv["Slack"] = float(report["pt"]["timing"][0]["Slack"])
        report_to_csv["Timing Src"] = "pt"
    else:
        report_to_csv["Slack"] = float(report["par"]["timing"][0]["Slack"])
        report_to_csv["Timing Src"] = "par"

    return report_to_csv


def create_bordered_str(text: str = "", border_char: str = "#", total_len: int = 150) -> list:
    text = f"  {text}  "
    text_len = len(text)
    if(text_len > total_len):
        total_len = text_len + 10 
    border_size = (total_len - text_len) // 2
    return [ border_char * total_len, f"{border_char * border_size}{text}{border_char * border_size}", border_char * total_len]

# def rtl_pre_process(design_config):
#     top_mod_re = re.compile(f"module\s+{design_config['synthesis']['inputs.top_module']}",re.MULTILINE)
#     # loop through all input files
#     for f in design_config["synthesis"]["inputs.input_files"]:
#         # TODO create instantiation tree s.t we can automate the creation of paths for sram macros
#         # For now this will only work if sram macros are instatiated in the top level file
#         rtl_text = open(f, "r").read()
#         print(top_mod_re.search(rtl_text).group(0))
#         sys.exit(1)
#     sys.exit(1)

def get_sram_macro_sizes(macro_fname: str) -> list:
    for file in os.listdir(os.path.join(tech_info.sram_lib_path,"lef")):
        m_sizes = []
        if macro_fname in file:
            # TODO fix the way that the size of macro is being searched for this way would not work in all cases
            lef_text = open(os.path.join(tech_info.sram_lib_path,"lef",file), "r").read()
            for line in lef_text.split("\n"):
                if "SIZE" in line:
                    # This also assumes the symmetry in the lef is X Y rather than searching for it TODO
                    m_sizes = [float(s) for s in line.split(" ") if res.decimal_re.match(s)]
                    break
        if len(m_sizes) > 0:
            break
    return m_sizes
        
def mod_rad_gen_config_from_rtl(base_config: dict, sram_map_info: dict, rtl_path: str) -> dict:
    config_out_path = sram_compiler_settings.config_out
    if not os.path.exists(config_out_path):
        os.mkdir(config_out_path)

    # create a copy which will be modified of the sram base config (hammer config)
    mod_base_config = copy.deepcopy(base_config)
    """ WRITING MEM PARAMS JSON FILES """
    # load in the mem_params.json file            
    with open(base_config["vlsi.inputs"]["sram_parameters"], 'r') as fd:
        mem_params = json.load(fd)
    mod_mem_params = copy.deepcopy(mem_params)
    modify_mem_params(mod_mem_params, width=sram_map_info["macro_w"], depth=sram_map_info["macro_d"], num_ports=sram_map_info["num_rw_ports"])

    mem_params_json_fpath = os.path.join(config_out_path,"mem_params_"+f'_{sram_map_info["macro"]}.json')
    with open(mem_params_json_fpath, 'w') as fd:
        json.dump(mod_mem_params, fd, sort_keys=False)
    # Defines naming convension of SRAM macros TODO
    """ MODIFYING AND WRITING HAMMER CONFIG YAML FILES """
    
    m_sizes = get_sram_macro_sizes(sram_map_info["macro"])
    
    # origin in um from the 0,0 point of the design
    sram_pcs = []
    sram_origin = [20,20]
    macro_spacing = 20
    for macro in sram_map_info["macro_list"]:
        pc = {"type": "hardmacro", "path": f"{sram_map_info['top_level_module']}/{macro['inst']}", "master": sram_map_info["macro"]}
        # coords = [float(name) for name in inst_name.split("_") if digit_re.match(name)]
        pc["x"] = round(sram_origin[0] + macro["log_coord"][0]*(m_sizes[0] + macro_spacing),3)
        pc["y"] = round(sram_origin[1] + macro["log_coord"][1]*(m_sizes[1] + macro_spacing),3)
        # if(macro["log_coord"] != macro["phys_coord"]):
        #     print(f'{macro["log_coord"]} --> {macro["phys_coord"]}')
        sram_pcs.append(pc)
        # mod_base_config["vlsi.inputs"]["placement_constraints"].append(pc)


    sram_max_x = max([pc["x"] + m_sizes[0] for pc in sram_pcs])
    sram_max_y = max([pc["y"] + m_sizes[1] for pc in sram_pcs])

    spacing_outline = 20
    # TODO instead of finding the top level module, just assign in outright
    # Now we need to modify the base_config file to use the correct sram macro
    for pc_idx, pc in enumerate(base_config["vlsi.inputs"]["placement_constraints"]):
        # TODO make sure to set the dimensions of the top level to be larger than the sum of all sram macro placements and spacing
        # set the top level to that of the new mapped sram macro we created when writing the rtl
        if pc["type"] == "toplevel":
            mod_base_config["vlsi.inputs"]["placement_constraints"][pc_idx]["path"] = sram_map_info["top_level_module"]
            mod_base_config["vlsi.inputs"]["placement_constraints"][pc_idx]["width"] = sram_max_x + spacing_outline
            mod_base_config["vlsi.inputs"]["placement_constraints"][pc_idx]["height"] = sram_max_y + spacing_outline
        else:
            # clean placement constraints
            del mod_base_config["vlsi.inputs"]["placement_constraints"][pc_idx]
        #     # TODO this requires "SRAM" to be in the macro name which is possibly dangerous
        # if pc["type"] == "hardmacro" and "SRAM" in pc["master"]:
        #     mod_base_config["vlsi.inputs"]["placement_constraints"][pc_idx]["master"] = mod_mem_params[0]["name"]
    
    for sram_pc in sram_pcs:
        mod_base_config["vlsi.inputs"]["placement_constraints"].append(sram_pc)

    # Find design files in newly created rtl dir
    # TODO adapt to support multiple input files in the sram macro
    mod_base_config["synthesis"]["inputs.top_module"] = sram_map_info["top_level_module"]
    mod_base_config["synthesis"]["inputs.input_files"] = [rtl_path]
    mod_base_config["synthesis"]["inputs.hdl_search_paths"] = [os.path.split(rtl_path)[0]]
    mod_base_config["vlsi.inputs"]["sram_parameters"] = mem_params_json_fpath
    mod_base_config["vlsi.inputs"]["clocks"][0]["name"] = "clk" 

    # Write the modified base_config file to a new file
    modified_config_path = os.path.join(config_out_path,"sram_config_"+f'_{sram_map_info["top_level_module"]}.yaml')
    with open(modified_config_path, 'w') as fd:
        yaml.safe_dump(mod_base_config, fd, sort_keys=False) 
    return modified_config_path

def get_rad_gen_flow_cmd(config_path, sram_flag=False, top_level_mod=None, hdl_path=None):
    if top_level_mod is None and hdl_path is None:
        cmd = f'python3 rad_gen.py -e {rad_gen_settings.top_level_rad_gen_config_path} -p {config_path}'
    else:
        cmd = f'python3 rad_gen.py -e {rad_gen_settings.top_level_rad_gen_config_path} -p {config_path} -t {top_level_mod} -v {hdl_path}'

    if sram_flag:
        cmd = cmd + " -sram"
    return cmd


def gen_parse_reports(report_search_dir,top_level_mod, design_config: dict = None, sram_num_bits: int = None):
    reports = []
    for dir in os.listdir(report_search_dir):
        design_out_dir = os.path.join(report_search_dir,dir)
        for r_dir in os.listdir(design_out_dir):
            report_dir = os.path.join(design_out_dir, r_dir)
            if os.path.isdir(report_dir) and dir.startswith(top_level_mod):
                print(f"Parsing results for {report_dir}")
            #if os.path.isdir(dir) and top_level_mod in dir:
                report_dict = {}
                # print(f"Parsing results for {dir}")
                syn_rpts, par_rpts, pt_rpts = parse_output(top_level_mod,report_dir)
                report_dict["syn"] = syn_rpts
                report_dict["par"] = par_rpts
                report_dict["pt"] = pt_rpts
                report_dict["obj_dir"] = report_dir
                # checks to see if initial run was even valid
                """ Looking for SRAM Macros """
                sram_macros = []
                macro_lef_areas = []
                if os.path.isfile(os.path.join(report_dir,"syn-rundir","syn-output-full.json")):
                    syn_out_config = json.load(open(os.path.join(report_dir,"syn-rundir","syn-output-full.json")))
                    if "vlsi.inputs.sram_parameters" in syn_out_config.keys():
                        for sram in syn_out_config["vlsi.inputs.sram_parameters"]:
                            sram_macros.append(sram["name"])
                            m_sizes = get_sram_macro_sizes(sram["name"])
                            macro_lef_areas.append(m_sizes[0]*m_sizes[1])
                            if sram_num_bits is not None:
                                num_macros = sram_num_bits // (int(sram['width'])*int(sram['depth']))
                                report_dict["num_macros"] = num_macros

                    report_dict["sram_macros"] = ", ".join(sram_macros)
                    report_dict["sram_macro_lef_areas"] = ", ".join([str(x) for x in macro_lef_areas])
                # Add the gds areas to the report
                gds_file = os.path.join(report_dir,"par-rundir",f"{top_level_mod}_drc.gds")
                if os.path.isfile(gds_file):
                    write_virtuoso_gds_to_area_script(gds_file)
                    for ext in ["csh","sh"]:
                        permission_cmd = "chmod +x " +  os.path.join(tech_info.pdk_rundir,f'{script_info.gds_to_area_fname}.{ext}')
                        run_shell_cmd_no_logs(permission_cmd)
                    # run_shell_cmd_no_logs(os.path.join(tech_info.pdk_rundir,f"{script_info.gds_to_area_fname}.sh"))
                    if not os.path.exists(os.path.join(report_dir,report_info.gds_area_fname)):
                        run_csh_cmd(os.path.join(tech_info.pdk_rundir,f"{script_info.gds_to_area_fname}.csh"))
                        report_dict["gds_area"] = parse_gds_to_area_output(report_dir)
                    else:
                        report_dict["gds_area"] = get_gds_area_from_rpt(report_dir)
                    # report_dict["gds_area"] = parse_gds_to_area_output(os.path.join(report_search_dir,dir))
                # RTL Parameter section
                if design_config is not None and design_config["type"] == "rtl_params":
                    # Using the output syn directory to find parameters in hdl search paths
                    if(os.path.isfile(os.path.join(report_dir,"syn-rundir","syn-output-full.json"))):
                        syn_out_config = json.load(open(os.path.join(report_dir,"syn-rundir","syn-output-full.json")))
                        # looping through hdl search paths
                        for path in syn_out_config["synthesis.inputs.hdl_search_paths"]:
                            if sweep_settings.param_sweep_hdr_dir_name in path:
                                param_hdr_name = os.path.basename(design_config["base_param_hdr_path"])
                                params = read_in_rtl_proj_params(design_config["params"], top_level_mod, design_config["rtl_dir_path"],os.path.join(path,param_hdr_name))
                                report_dict["rtl_params"] = params
                                break                      
                    if len(report_dict["syn"]) > 0 and len(report_dict["par"]) > 0 and "rtl_params" in report_dict:
                        reports.append(report_dict)
                else: 
                    if len(report_dict["syn"]) > 0 and len(report_dict["par"]) > 0:
                        reports.append(report_dict)
    return reports
########################################## RAD GEN UTILITIES ##########################################
##########################################   RAD GEN FLOW   ############################################


def write_lc_lib_to_db_script (in_libs_paths):
    """ Takes in a list of abs paths for libs that need to be converted to .dbs """
    lc_script_name = "lc_lib_to_db.tcl"
    pt_outpath = os.path.join(asic_flow_settings.obj_dir_path, "pt-rundir")
    db_lib_outpath = os.path.join(rad_gen_settings.rad_gen_home_path, "sram_db_libs")
    if not os.path.isdir(pt_outpath):
        os.makedirs(pt_outpath)
    if not os.path.isdir(db_lib_outpath):
        os.makedirs(db_lib_outpath)
    lc_script_path = os.path.join(pt_outpath,lc_script_name)
    
    file_lines = []
    for lib in in_libs_paths:
        read_lib_cmd = "read_lib " + f"{lib}"
        write_lib_cmd = "write_lib " + f"{os.path.splitext(os.path.basename(lib))[0]} " + "-f db " + "-o " f"{os.path.join(db_lib_outpath,os.path.splitext(os.path.basename(lib))[0])}.db"
        file_lines.append(read_lib_cmd)
        file_lines.append(write_lib_cmd)
    fd = open(lc_script_path,"w")
    for line in file_lines:
        file_write_ln(fd,line)
    file_write_ln(fd,"quit")
    fd.close()

    return os.path.abspath(lc_script_path)


def pretty(d, indent=0):
   for key, value in d.items():
      print('\t' * indent + str(key))
      if isinstance(value, dict):
         pretty(value, indent+1)
      else:
         print('\t' * (indent+1) + str(value))

def rad_gen_flow(flow_settings: dict, config_paths: list) -> None:
    # Create the output directory with top level module name if it doesnt exist
    out_dir = os.path.join(rad_gen_settings.design_output_path,asic_flow_settings.top_level_module)
    # sp.call(f"mkdir -p {out_dir}")
    obj_dir_fmt = f"{asic_flow_settings.top_level_module}-%Y-%m-%d---%H-%M-%S"
    # Set the obj directory for hammer
    if asic_flow_settings.use_latest_obj_dir == True:
        obj_dir_path = find_newest_obj_dir(obj_dir_fmt)
    elif asic_flow_settings.manual_obj_dir != None:
        obj_dir_path = asic_flow_settings.manual_obj_dir
    else:
        timestr = time.strftime(obj_dir_fmt)
        obj_dir_path = os.path.join(out_dir,timestr)
    
    # This means the usesr used the -l option with no existing object directory
    if obj_dir_path == None:
        timestr = time.strftime(obj_dir_fmt)
        obj_dir_path = os.path.join(out_dir,timestr)
    
    asic_flow_settings.obj_dir_path = obj_dir_path


    # Create the obj directory if it doesnt exist, hammer already does this but it will be used for preprocesing the rtl and outputting its parameter values
    if not os.path.exists(obj_dir_path):
        os.makedirs(obj_dir_path)

    # Get cwd and change to the generated output directory
    pre_flow_cwd = os.getcwd()
    os.chdir(out_dir)

    rad_gen_log(f"Using obj_dir: {obj_dir_path}",rad_gen_log_fd)

    flow_report = {
        "syn" : None,
        "par" : None,
        "pt" : None
    }
    # read in the default config file and add some items to flow report
    input_config = yaml.safe_load(open(config_paths[0], 'r'))
    flow_report["target_freq"] = input_config["vlsi.inputs"]["clocks"][0]["period"]

    # Check to see if design has an SRAM configuration
    if asic_flow_settings.run_sram:
        sram_config, sram_stdout, sram_stderr = run_hammer_stage("sram_generator", config_paths)
        config_paths.append(sram_config)
    
    #run hammer stages
    if asic_flow_settings.run_syn:
        # """
        # for config in config_paths:
        #     config_settings = yaml.safe_load(open(config, 'r'))
        #     if "synthesis" in config_settings.keys():
        #         read_in_rtl_proj_params_all(config_settings["synthesis"]["inputs.top_module"],config_settings["synthesis"]["inputs.hdl_search_paths"])
        # """

        syn_config, syn_stdout, syn_stderr = run_hammer_stage("syn", config_paths)
    # If the synthesis report path exists, then parse
    syn_reports_path = os.path.join(asic_flow_settings.obj_dir_path, "syn-rundir", "reports")
    if os.path.isdir(syn_reports_path):
        syn_report = get_report_results(asic_flow_settings.top_level_module, syn_reports_path, asic_flow_settings.flow_stages["syn"])
        flow_report["syn"] = syn_report

    if asic_flow_settings.run_par:
        syn_to_par_config = get_hammer_config("syn-to-par")
        config_paths.append(syn_to_par_config)
        par_out_config, par_stdout, par_stderr = run_hammer_stage("par", config_paths)
    
    # If the par report path exists, then parse
    par_reports_path = os.path.join(asic_flow_settings.obj_dir_path, "par-rundir")
    if os.path.isdir(par_reports_path):
        par_report = get_report_results(asic_flow_settings.top_level_module, par_reports_path, asic_flow_settings.flow_stages["par"])
        flow_report["par"] = par_report

    if asic_flow_settings.run_pt:
        par_to_power_config = get_hammer_config("par-to-power")
        #get params from par-to-power.json file
        json_fd = open(os.path.join(obj_dir_path,f'{asic_flow_settings.top_level_module}-par-to-power.json'),"r")
        par_to_power_data = json.load(json_fd)
        json_fd.close()
        #get params from syn-to-par.json file
        json_fd = open(os.path.join(obj_dir_path,f'{asic_flow_settings.top_level_module}-syn-to-par.json'),"r")
        syn_to_par_data = json.load(json_fd)
        json_fd.close()

        write_pt_sdc(par_to_power_data,os.path.join(os.getcwd(),obj_dir_path))

        #now use the pnr output to run primetime
        # find the required macro lib files and convert to .db
        if "vlsi.inputs.sram_parameters" in par_to_power_data.keys():
            macros = [params["name"] for params in par_to_power_data["vlsi.inputs.sram_parameters"]]
            timing_lib_paths = [os.path.join(tech_info.sram_lib_path,"lib",f"{macro}_lib") for macro in macros]
            conversion_libs = []
            for timing_lib_path in timing_lib_paths:
                conversion_libs += [os.path.join(timing_lib_path,f) for f in os.listdir(timing_lib_path) if f.endswith(".lib")]
            lc_script_path = write_lc_lib_to_db_script(conversion_libs)
            lc_run_cmd = f"lc_shell -f {lc_script_path}"
            os.chdir(os.path.join(rad_gen_settings.rad_gen_home_path,asic_flow_settings.obj_dir_path,"pt-rundir"))
            run_shell_cmd_no_logs(lc_run_cmd)
            os.chdir(rad_gen_settings.rad_gen_home_path)

        ################################ LIB TO DB CONVERSION ################################
        #prepare lib files to be read in from pt, means we need to unzip them in asap7 cache
        #asap7_std_cell_lib_cache = os.path.join(obj_dir_path,"tech-asap7-cache/LIB/NLDM")
        # for lib_file in os.listdir(asap7_std_cell_lib_cache):
            # if(lib_file.endswith(".gz")):
                # sp.run(["gunzip",os.path.join(asap7_std_cell_lib_cache,lib_file)])
        #write_lib_to_db_script(os.path.join(os.getcwd(),obj_dir_path))
        ################################ LIB TO DB CONVERSION ################################
        
        write_pt_timing_script(par_to_power_data,os.path.join(os.getcwd(),obj_dir_path))
        cwd = os.getcwd()
        os.chdir(os.path.join(os.getcwd(),obj_dir_path,"pt-rundir"))

        pt_stdout, pt_stderr = run_shell_cmd_no_logs("dc_shell-t -f pt_analysis.tcl")
        with open("pt_stdout.log","w") as fd:
            fd.write(pt_stdout)
        with open("pt_stderr.log","w") as fd:
            fd.write(pt_stderr)

        os.chdir(cwd)
        os.chdir(pre_flow_cwd)
        
    pt_reports_path = os.path.join(asic_flow_settings.obj_dir_path, "pt-rundir", "reports")
    if os.path.isdir(pt_reports_path):
        pt_report = get_report_results(asic_flow_settings.top_level_module, pt_reports_path, asic_flow_settings.flow_stages["pt"])
        flow_report["pt"] = pt_report

        # copy the run dir to a new directory to save results
        #sp.run(["cp", "-r", flow_stage_rundir_path_src,flow_stage_rundir_path_dest])
        ################################ LIB TO DB CONVERSION ################################
        # re zip the after primetime
        # for lib_file in os.listdir(asap7_std_cell_lib_cache):
        #     sp.run(["gunzip",os.path.join(asap7_std_cell_lib_cache,lib_file)])
        ################################ LIB TO DB CONVERSION ################################
    # Now that we have all the reports, we can generate the final report
    report_to_csv = gen_report_to_csv(flow_report)
    df = pd.DataFrame.from_dict(report_to_csv, orient='index').T
    # Set separator format
    separator = "+".join(["-"*15]*9)

    rad_gen_log('\n'.join(create_bordered_str(f"'{asic_flow_settings.top_level_module}' ASIC FLOW REPORT")), rad_gen_log_fd)

    # Print formatted dataframe
    rad_gen_log(separator,rad_gen_log_fd)
    rad_gen_log("|".join(["{:^15}" for _ in range(len(df.columns))]).format(*df.columns),rad_gen_log_fd)
    rad_gen_log(separator,rad_gen_log_fd)
    for i, row in df.iterrows():
        rad_gen_log("|".join(["{:^15}" for _ in range(len(df.columns))]).format(*row.values),rad_gen_log_fd)
        rad_gen_log(separator,rad_gen_log_fd)

    # rad_gen_log('\n'.join(create_bordered_str(f"'{asic_flow_settings.top_level_module}' ASIC FLOW REPORT")), rad_gen_log_fd)
    # rad_gen_log(df, rad_gen_log_fd)
##########################################   RAD GEN FLOW   ############################################


def init_globals():
    """ Initializes all global variables s.t functions can use them"""
    global rad_gen_settings
    global asic_flow_settings
    global multi_design_settings
    global sweep_settings
    global rad_gen_mode
    global vlsi_mode
    global res
    global tech_info
    global report_info
    global script_info
    global sram_compiler_settings

# def check_for_valid_input(data_struct):

def check_for_valid_path(path):
    ret_val = False
    if os.path.exists(os.path.abspath(path)):
        ret_val = True
    else:
        rad_gen_log(f"ERROR: {path} does not exist", rad_gen_log_fd)
    return ret_val

def handle_error(fn, expected_vals: set=None):
    # for fn in funcs:
    if not fn():
        sys.exit(1)

def init_structs_from_cli(args):
    init_globals()

    if args.high_lvl_rad_gen_config_file != "":
        handle_error(lambda: check_for_valid_path(args.high_lvl_rad_gen_config_file), {True : None})
        with open(args.high_lvl_rad_gen_config_file, 'r') as yml_file:
            rad_gen_config = yaml.safe_load(yml_file)
        # pretty(rad_gen_config)
        rad_gen_settings.hammer_home_path = os.path.join(os.path.expanduser(rad_gen_config["rad_gen_settings"]["rad_gen_home_path"]),"hammer")
        rad_gen_settings.top_level_rad_gen_config_path = os.path.realpath(args.high_lvl_rad_gen_config_file)
        rad_gen_settings.rad_gen_home_path = os.path.expanduser(rad_gen_config["rad_gen_settings"]["rad_gen_home_path"])
        rad_gen_settings.design_output_path = os.path.join(rad_gen_settings.rad_gen_home_path, "output_designs")
        rad_gen_settings.env_path = os.path.expanduser(rad_gen_config["rad_gen_settings"]["env_config_path"])
        # init tech info settings
        tech_info.pdk_rundir = os.path.expanduser(rad_gen_config["rad_gen_settings"]["asap7"]["rundir_path"])
        tech_info.sram_lib_path = os.path.join(rad_gen_settings.hammer_home_path,"src","hammer-vlsi","technology","asap7","sram_compiler","memories")


    else:
        rad_gen_log("ERROR: High level RAD-Gen config file not provided", rad_gen_log_fd)
        sys.exit(1)
    # determine mode of operation of RAD-Gen
    tool_mode = None
    if args.config_path != "":
        tool_mode = "vlsi"
    elif args.compile_results and args.design_sweep_config_file != '':
        tool_mode = "gen_results"
    elif args.design_sweep_config_file != '' and not args.compile_results:
        tool_mode = "design_sweep"
    
    rad_gen_mode.tool_mode = tool_mode
    if tool_mode == None:
        rad_gen_log("ERROR: No mode of operation specified", rad_gen_log_fd)
        sys.exit(1)

    """ Settings required when running in VLSI flow mode """
    if tool_mode == "vlsi":
        rad_gen_mode.vlsi_flow.enable = True
        # If the user specified a top level module and hdl path, then we can reuse a config file with the correct VLSI settings
        if args.manual_obj_dir != "":
            asic_flow_settings.manual_obj_dir = os.path.realpath(args.manual_obj_dir)
            # if os.path.exists
            # handle_error(lambda: check_for_valid_path(asic_flow_settings.manual_obj_dir), {True : None})

        if args.top_level != "" and args.hdl_path != "":
            rad_gen_mode.vlsi_flow.config_reuse = True
            asic_flow_settings.top_level_module = args.top_level
            asic_flow_settings.hdl_path = os.path.realpath(args.hdl_path)
            # If path is invalid, exit with error handler
            handle_error(lambda: check_for_valid_path(asic_flow_settings.hdl_path), {True : None})
        else:
            # This means that the config file the user passed into the tool is expected to be valid
            rad_gen_mode.vlsi_flow.config_reuse = False
        
        # rad_gen_settings.env_path = os.path.realpath(args.env_path)

        asic_flow_settings.config_path = os.path.realpath(args.config_path)
        handle_error(lambda: check_for_valid_path(asic_flow_settings.config_path), {True : None})
        
        # if not specified the flow will run all the stages by defualt
        run_all_flow = not (args.synthesis or args.place_n_route or args.primetime)
        asic_flow_settings.run_sram = args.sram_compiler and not args.compile_results
        asic_flow_settings.run_syn = args.synthesis or run_all_flow and not args.compile_results
        asic_flow_settings.run_par = args.place_n_route or run_all_flow and not args.compile_results
        asic_flow_settings.run_pt = args.primetime or run_all_flow and not args.compile_results
        # If user wants to use the latest generated obj dir for the design
        asic_flow_settings.use_latest_obj_dir = args.use_latest_obj_dir
    elif tool_mode == "gen_results" or tool_mode == "design_sweep":
        handle_error(lambda: check_for_valid_path(args.design_sweep_config_file), {True : None})
        multi_design_settings.sweep_config_path = os.path.realpath(args.design_sweep_config_file)
        sram_compiler_settings.rtl_out = os.path.join(rad_gen_settings.rad_gen_home_path,"input_designs","sram","rtl","compiler_outputs")
        sram_compiler_settings.config_out = os.path.join(rad_gen_settings.rad_gen_home_path,"input_designs","sram","configs","compiler_outputs")

    

def sort_by_params(reports, result_parse_config):
    # This directory is where a sucessful synthesis run will have a json file from which we can get the hdl search path of the design
    # From the hdl search path we can find the parameters used for the run ...
    config_search_dir = os.path.join("syn-rundir","syn-output-full.json")
    syn_config_outpath = os.path.join(result_parse_config["report_search_path"],report["obj_dir"],config_search_dir)
    for report in reports:
        if os.path.isfile(syn_config_outpath):
            syn_out_config = json.load(open(syn_config_outpath))
            for path in syn_out_config["synthesis.inputs.hdl_search_paths"]:
                print("test")


def write_virtuoso_gds_to_area_script(gds_fpath):
    # skill_fname = "get_area.il"
    skill_script_lines = [
        f"system(\"strmin -library {tech_info.cds_lib} -strmFile {gds_fpath} -logFile strmIn.log\")",
        f'cv = dbOpenCellViewByType("asap7_TechLib" "TOPCELL" "layout")',
        "print(cv~>bBox)",
    ]
    skill_fpath = os.path.join(tech_info.pdk_rundir, f"{script_info.gds_to_area_fname}.il")
    csh_fpath = os.path.join(tech_info.pdk_rundir, f"{script_info.gds_to_area_fname}.csh")

    # TODO remove abs paths
    csh_script_lines = [
        "#!/bin/csh",
       f"source ~/auto_asic_flow/setup_virtuoso_env.sh && virtuoso -nograph -replay {skill_fpath} -log get_area.log {skill_fpath} -log {script_info.gds_to_area_fname}.log"
    ]

    fd = open(skill_fpath, 'w')
    for line in skill_script_lines:
        file_write_ln(fd, line)
    fd.close()
    fd = open(csh_fpath, 'w')
    for line in csh_script_lines:
        file_write_ln(fd, line)
    fd.close()

def parse_gds_to_area_output(obj_dir_path):

    gds_to_area_log_fpath = os.path.join(tech_info.pdk_rundir, script_info.gds_to_area_fname + ".log")
    fd = open(gds_to_area_log_fpath, 'r')
    lines = fd.readlines()
    fd.close()
    # Find the line with the area
    for i, line in enumerate(lines):
        if "print(cv~>bBox)" in line:
            bbox_bounds = res.signed_dec_re.findall(lines[i+1])
    width = float(bbox_bounds[2]) - float(bbox_bounds[0])
    height = float(bbox_bounds[3]) - float(bbox_bounds[1])
    area = width * height
    with open(os.path.join(obj_dir_path,report_info.gds_area_fname),"w") as fd:
        print(f"Area of design is {width}x{height}={area} um^2",file=fd)        
        print(f"GDS Area: {area}",file=fd)    
    print(f"Area of design is {width}x{height}={area} um^2")
    
    return area

    
def write_dict_to_csv(csv_lines,csv_fname):
    csv_fd = open(f"{csv_fname}.csv","w")
    writer = csv.DictWriter(csv_fd, fieldnames=csv_lines[0].keys())
    writer.writeheader()
    for line in csv_lines:
        writer.writerow(line)
    csv_fd.close()

def modify_mem_params(mem_params: dict, width: int, depth: int, num_ports: int) -> None:
    mem_params[0]["depth"] = str(depth)
    mem_params[0]["width"] = str(width)
    # Defines naming convension of SRAM macros TODO
    mem_params[0]["name"] = f"SRAM{num_ports}RW{depth}x{width}"
    if num_ports == 2:
        mem_params[0]["ports"] = [{}]*2
        mem_params[0]["family"] = "2RW"
        mem_params[0]["ports"][0]["read enable port name"] = "OEB1"
        mem_params[0]["ports"][0]["read enable port polarity"] = "active low"
        mem_params[0]["ports"][0]["write enable port name"] = "WEB1"
        mem_params[0]["ports"][0]["write enable port polarity"] = "active low"
        mem_params[0]["ports"][0]["chip enable port name"] = "CSB1"
        mem_params[0]["ports"][0]["chip enable port polarity"] = "active low"
        mem_params[0]["ports"][0]["clock port name"] = "CE1"
        mem_params[0]["ports"][0]["clock port polarity"] = "positive edge"
        mem_params[0]["ports"][0]["address port name"] = "A1"
        mem_params[0]["ports"][0]["address port polarity"] = "active high"
        mem_params[0]["ports"][0]["output port name"] = "O1"
        mem_params[0]["ports"][0]["output port polarity"] = "active high"
        mem_params[0]["ports"][0]["input port name"] = "I1"
        mem_params[0]["ports"][0]["input port polarity"] = "active high"
        mem_params[0]["ports"][1]["read enable port name"] = "OEB2"
        mem_params[0]["ports"][1]["read enable port polarity"] = "active low"
        mem_params[0]["ports"][1]["write enable port name"] = "WEB2"
        mem_params[0]["ports"][1]["write enable port polarity"] = "active low"
        mem_params[0]["ports"][1]["chip enable port name"] = "CSB2"
        mem_params[0]["ports"][1]["chip enable port polarity"] = "active low"
        mem_params[0]["ports"][1]["clock port name"] = "CE2"
        mem_params[0]["ports"][1]["clock port polarity"] = "positive edge"
        mem_params[0]["ports"][1]["address port name"] = "A2"
        mem_params[0]["ports"][1]["address port polarity"] = "active high"

def gen_compiled_srams(base_config, sanitized_design):
    for mem in sanitized_design["mems"]:
        mapping = sram_compiler.compile(mem["rw_ports"],mem["w"],mem["d"],"asap7")
        sram_map_info, rtl_outpath = sram_compiler.write_rtl_from_mapping(mapping,sanitized_design["base_rtl_path"],sram_compiler_settings.rtl_out)
        sram_map_info = sram_compiler.translate_logical_to_phsical(sram_map_info)
        config_path = mod_rad_gen_config_from_rtl(base_config, sram_map_info, rtl_outpath)
        rad_gen_log(get_rad_gen_flow_cmd(config_path,sram_flag=True),rad_gen_log_fd)
        # get mapping and find the macro in lib, instantiate that many and

def sram_sweep_gen(base_config, sanitized_design):
    # This is where we will send the output sram macros
    # sram_out_path = os.path.expanduser("~/rad_gen/input_designs/sram/rtl/compiler_outputs")
    if not os.path.isdir(sram_compiler_settings.rtl_out):
        os.mkdir(sram_compiler_settings.rtl_out)
    gen_compiled_srams(base_config, sanitized_design)
    # load in the mem_params.json file            
    with open(base_config["vlsi.inputs"]["sram_parameters"], 'r') as fd:
        mem_params = json.load(fd)
    # List of available SRAM macros
    sram_macro_lefs = os.listdir(os.path.join(tech_info.sram_lib_path,"lef"))
    # Sweep over all widths and depths for SRAMs in the sweep config file  
    for rw_port in sanitized_design["rw_ports"]:         
        for depth in sanitized_design["depths"]:
            for width in sanitized_design["widths"]:
                """ MODIFIYING MEM CONFIG JSON FILES """
                # If we want to iterate through and keep an original reference set of configs we need to use deepcopy on the dict
                # This concept is very annoying as when assigning any variable to a dict you are actually just creating a reference to the dict (Very unlike C) :(
                # All mem_params are indexed to 0 since we are only sweeping over a single SRAM TODO
                # Create copies of each configs s.t they can be modified without affecting the original
                mod_base_config = copy.deepcopy(base_config)
                mod_mem_params = copy.deepcopy(mem_params)
                modify_mem_params(mod_mem_params, width, depth, rw_port)
                # Make sure that the SRAM macro exists in the list of SRAM macros
                if not any(mod_mem_params[0]["name"] in macro for macro in sram_macro_lefs):
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
                if rw_port == 2:
                    mod_sram_rtl = f"`define DUAL_PORT\n" + mod_sram_rtl
                # Look for the SRAM instantiation and replace the name of the sram macro, the below regex uses the comments in the rtl file to find the instantiation
                # Inst starts with "START SRAM INST" and ends with "END SRAM INST"
                port_str = "1PORT" if rw_port == 1 else "2PORT"
                edit_sram_inst_re = re.compile(f"^\s+//\s+START\sSRAM\s{port_str}\sINST.*END\sSRAM\s{port_str}",re.MULTILINE|re.DOTALL)

                sram_inst_rtl = edit_sram_inst_re.search(mod_sram_rtl).group(0)
                edit_sram_macro_name = re.compile(f"SRAM{rw_port}RW.*\s")
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
                m_sizes = get_sram_macro_sizes(mod_mem_params[0]["name"])
                # Now we need to modify the base_config file to use the correct sram macro
                
                macro_init = 15 if rw_port == 1 else 30
                macro_extra_logic_spacing = 15 if rw_port == 1 else 30
                top_lvl_idx = 0
                for pc_idx, pc in enumerate(base_config["vlsi.inputs"]["placement_constraints"]):
                    # TODO this requires "SRAM" to be in the macro name which is possibly dangerous
                    if pc["type"] == "hardmacro" and "SRAM" in pc["master"]:
                        mod_base_config["vlsi.inputs"]["placement_constraints"][pc_idx]["master"] = mod_mem_params[0]["name"]
                        mod_base_config["vlsi.inputs"]["placement_constraints"][pc_idx]["x"] = macro_init
                        mod_base_config["vlsi.inputs"]["placement_constraints"][pc_idx]["y"] = macro_init
                    elif pc["type"] == "toplevel":
                        mod_base_config["vlsi.inputs"]["placement_constraints"][pc_idx]["width"] = macro_init + m_sizes[0] + macro_extra_logic_spacing
                        mod_base_config["vlsi.inputs"]["placement_constraints"][pc_idx]["height"] = macro_init + m_sizes[1] + macro_extra_logic_spacing
                        top_lvl_idx = pc_idx
                if (mod_base_config["vlsi.inputs"]["placement_constraints"][top_lvl_idx]["width"] > mod_base_config["vlsi.inputs"]["placement_constraints"][top_lvl_idx]["height"]):
                    mod_base_config["vlsi.inputs"]["pin.assignments"][0]["side"] = "bottom"
                else:
                    mod_base_config["vlsi.inputs"]["pin.assignments"][0]["side"] = "left"



                # Find design files in newly created rtl dir
                design_files, design_dirs = rec_get_flist_of_ext(mod_rtl_dir,['.v','.sv','.vhd',".vhdl"])
                mod_base_config["synthesis"]["inputs.input_files"] = design_files
                mod_base_config["synthesis"]["inputs.hdl_search_paths"] = design_dirs
                mod_base_config["vlsi.inputs"]["sram_parameters"] = os.path.splitext(base_config["vlsi.inputs"]["sram_parameters"])[0] + f'_{mod_mem_params[0]["name"]}.json'
                # Write the modified base_config file to a new file
                modified_config_path = os.path.splitext(sanitized_design["base_config_path"])[0]+f'_{mod_mem_params[0]["name"]}.yaml'
                with open(modified_config_path, 'w') as fd:
                    yaml.safe_dump(mod_base_config, fd, sort_keys=False)    
                rad_gen_log(f"INFO: Writing rad_gen yml config to {modified_config_path}",rad_gen_log_fd)
                rad_gen_log(get_rad_gen_flow_cmd(modified_config_path,sram_flag=True),rad_gen_log_fd)


def parse_cli_args() -> tuple:
    parser = argparse.ArgumentParser()
    parser.add_argument('-t', '--top_level', help="name of top level design in HDL", type=str, default='')
    parser.add_argument('-v', '--hdl_path', help="path to directory containing HDL files", type=str, default='')
    parser.add_argument('-p', '--config_path', help="path to hammer design specific config.yaml file", type=str, default='')
    # parser.add_argument('-r', '--openram_config_dir', help="path to dir (TODO)", type=str, default='')
    parser.add_argument('-l', '--use_latest_obj_dir', help="uses latest obj dir found in rad_gen dir", action='store_true') 
    parser.add_argument('-o', '--manual_obj_dir', help="uses user specified obj dir", type=str, default='')
    

    parser.add_argument('-e', '--high_lvl_rad_gen_config_file', help="path to high level config file",  type=str, default='')
    parser.add_argument('-s', '--design_sweep_config_file', help="path to config file containing design sweep parameters",  type=str, default='')
    parser.add_argument('-c', '--compile_results', help="path to dir", action='store_true') 


    parser.add_argument('-syn', '--synthesis', help="flag runs synthesis on specified design", action='store_true') 
    parser.add_argument('-par', '--place_n_route', help="flag runs place & route on specified design", action='store_true') 
    parser.add_argument('-pt', '--primetime', help="flag runs primetime on specified design", action='store_true') 
    parser.add_argument('-sram', '--sram_compiler', help="flag enables srams to be run in design", action='store_true') 
    # parser.add_argument('-sim', '--sram_compiler', help="path to dir", action='store_true') 
    args = parser.parse_args()
    
    return args


def compile_results(args):
    # read in the result config file
    # report_search_dir = os.path.expanduser(rad_gen_settings.rad_gen_home_path)
    report_search_dir = rad_gen_settings.design_output_path
    design_sweep_config = sanitize_config(yaml.safe_load(open(args.design_sweep_config_file)))
    csv_lines = []
    reports = []
    for design in design_sweep_config["designs"]:
        design_config = sanitize_config(design)
        if ("type" in design_config.keys()):
            # This parses for sram or rtl param sweeps
            if (design_config["type"] == "sram"):
                rad_gen_log(f"Parsing results of parameter sweep using parameters defined in {args.design_sweep_config_file}",rad_gen_log_fd)
                for mem in design["mems"]:
                    mem_top_lvl_name = f"sram_macro_map_{mem['rw_ports']}x{mem['w']}x{mem['d']}"
                    num_bits = mem['w']*mem['d']
                    reports += gen_parse_reports(report_search_dir, mem_top_lvl_name, design_config, num_bits)
                reports += gen_parse_reports(report_search_dir, design_config['top_level_module'], design_config)

            elif (design_config["type"] == "rtl_params"):
                """ Currently focused on NoC rtl params"""
                rad_gen_log(f"Parsing results of parameter sweep using parameters defined in {args.design_sweep_config_file}",rad_gen_log_fd)
                reports = gen_parse_reports(report_search_dir,design_config["top_level_module"],design_config)
            else:
                rad_gen_log(f"Error: Unknown design type {design_config['type']} in {args.design_sweep_config_file}",rad_gen_log_fd)
                sys.exit(1)
        else:
            # This parsing of reports just looks at top level and takes whatever is in the obj dir
            rad_gen_log(f"Parsing results of parameter sweep using parameters defined in {args.design_sweep_config_file}",rad_gen_log_fd)
            reports = gen_parse_reports(report_search_dir,design_config["top_level_module"])
            # General parsing of report to csv
        
        for report in reports:
            if "type" in design_config.keys() and design_config["type"] == "rtl_params":
                report_to_csv = noc_prse_area_brkdwn(report)
            else:
                report_to_csv = gen_report_to_csv(report)
            if len(report_to_csv) > 0:
                csv_lines.append(report_to_csv)
    csv_fname = os.path.splitext(os.path.basename(args.design_sweep_config_file))[0]
    write_dict_to_csv(csv_lines,csv_fname)

def design_sweep(args):
    # Starting with just SRAM configurations for a single rtl file (changing parameters in header file)
    rad_gen_log(f"Running design sweep from config file {multi_design_settings.sweep_config_path}",rad_gen_log_fd)
    design_sweep_config = yaml.safe_load(open(multi_design_settings.sweep_config_path))
    for design in design_sweep_config["designs"]:
        """ General flow for all designs in sweep config """
        # Load in the base configuration file for the design
        sanitized_design = sanitize_config(design)
        base_config = yaml.safe_load(open(sanitized_design["base_config_path"]))
        
        """ Currently only can sweep either vlsi params or rtl params not both """
        sweep_script_lines = [
            "#!/bin/bash",
        ]
        # If there are vlsi parameters to sweep over
        if sanitized_design["type"] == "vlsi_params":
            mod_base_config = copy.deepcopy(base_config)
            """ MODIFYING HAMMER CONFIG YAML FILES """
            sweep_idx = 1
            for param_sweep_key, param_sweep_vals in sanitized_design["params"].items():
                if "period" in param_sweep_key:
                    for period in sanitized_design["params"][param_sweep_key]:
                        mod_base_config["vlsi.inputs"]["clocks"][0]["period"] = f'{str(period)} ns'
                        modified_config_path = os.path.splitext(sanitized_design["base_config_path"])[0]+f'_period_{str(period)}.yaml'
                        with open(modified_config_path, 'w') as fd:
                            yaml.safe_dump(mod_base_config, fd, sort_keys=False) 

                        rad_gen_cmd_lines = [get_rad_gen_flow_cmd(modified_config_path,sram_flag=False,top_level_mod=sanitized_design["top_level_module"],hdl_path=sanitized_design["rtl_dir_path"]) + " &",
                        "sleep 2",
                        ]
                        sweep_script_lines += rad_gen_cmd_lines
                        if sweep_idx % sanitized_design["flow_threads"] == 0 and sweep_idx != 0:
                            sweep_script_lines.append("wait")
                        sweep_idx += 1
            rad_gen_log("\n".join(create_bordered_str("Autogenerated Sweep Script")),rad_gen_log_fd)
            rad_gen_log("\n".join(sweep_script_lines),rad_gen_log_fd)
        # TODO This wont work for multiple SRAMs in a single design, simply to evaluate individual SRAMs
        elif sanitized_design["type"] == "sram":      
            sram_sweep_gen(base_config,sanitized_design)                
        # TODO make this more general but for now this is ok
        # the below case should deal with any asic_param sweep we want to perform
        elif sanitized_design["type"] == 'rtl_params':
            mod_param_hdr_paths, mod_config_paths = edit_rtl_proj_params(sanitized_design["params"], sanitized_design["rtl_dir_path"], sanitized_design["base_param_hdr_path"],sanitized_design["base_config_path"])
            sweep_idx = 1
            for hdr_path, config_path in zip(mod_param_hdr_paths, mod_config_paths):
            # for hdr_path in mod_param_hdr_paths:
                rad_gen_log(f"PARAMS FOR PATH {hdr_path}",rad_gen_log_fd)
                rad_gen_cmd_lines = [get_rad_gen_flow_cmd(config_path,sram_flag=False,top_level_mod=sanitized_design["top_level_module"],hdl_path=sanitized_design["rtl_dir_path"]) + " &",
                    "sleep 2",
                ]
                sweep_script_lines += rad_gen_cmd_lines
                if sweep_idx % sanitized_design["flow_threads"] == 0 and sweep_idx != 0:
                    sweep_script_lines.append("wait")
                sweep_idx += 1
                # rad_gen_log(get_rad_gen_flow_cmd(config_path,sram_flag=False,top_level_mod=sanitized_design["top_level_module"],hdl_path=sanitized_design["rtl_dir_path"]),rad_gen_log_fd)
                read_in_rtl_proj_params(sanitized_design["params"],sanitized_design["top_level_module"],sanitized_design["rtl_dir_path"],hdr_path)
                """ We shouldn't need to edit the values of params/defines which are operations or values set to other params/defines """
                """ EDIT PARAMS/DEFINES IN THE SWEEP FILE """
                # TODO this assumes parameter sweep vars arent kept over multiple files
            rad_gen_log("\n".join(create_bordered_str("Autogenerated Sweep Script")),rad_gen_log_fd)
            rad_gen_log("\n".join(sweep_script_lines),rad_gen_log_fd)

def run_asic_flow(args):
    # Convert from cli args into rad_gen_flow_settings for a particular flow run    
    rad_gen_flow_settings = vars(args)
    """ USED FOR THE SRAM SWEEP RUN, I THINK THIS IS UNSAFE TO USE TODO REMOVE THIS"""
    # If the args for top level and rtl path are not set, we will use values from the config file
    if rad_gen_mode.vlsi_flow.config_reuse == False:
        design_config = yaml.safe_load(open(asic_flow_settings.config_path))
        # Assuming that the top level module and input files are set in the config file
        # Add additional input files which may exist in the module rtl_dir
        rad_gen_flow_settings["top_level"] = design_config["synthesis"]["inputs.top_module"]
        asic_flow_settings.top_level_module = design_config["synthesis"]["inputs.top_module"]
        config_paths = [asic_flow_settings.config_path]
    else:
    # Edit the config file with cli args
        """ Check to make sure all parameters are assigned and modify if required to"""
        design_config, modified_config_path = modify_config_file(rad_gen_flow_settings)
        config_paths = [modified_config_path]
    
    # Run the flow
    rad_gen_flow(rad_gen_flow_settings, config_paths)
    rad_gen_log("Done!", rad_gen_log_fd)
    sys.exit()    

def main():
    global cur_env
    global openram_gen_path
    # global verbosity_lvl
    global rad_gen_log_fd
    rad_gen_log_fd = "rad_gen.log"

    #Clear rad gen log
    fd = open(rad_gen_log_fd, 'w')
    fd.close()

    rad_gen_settings.log_verbosity = 2
    # Verbosity level
    # 0 - Brief output
    # 1 - Brief output + I/O interactions
    # 2 - Hammer and asic tool outputs will be printed to console  

    openram_gen_path = "openram_gen"

    # Parse command line arguments
    args = parse_cli_args()

    # if(not args.openram_config_dir == ''):
    #     rad_gen_log(f"Using OpenRam to generate SRAMs in {args.openram_config_dir}",rad_gen_log_fd)
    #     sys.exit(0)

    init_structs_from_cli(args)

    # Make sure HAMMER env vars are set
    if 'HAMMER_HOME' not in os.environ:
        rad_gen_log('Error: HAMMER_HOME environment variable not set!', rad_gen_log_fd)
        rad_gen_log("Please set HAMMER_HOME to the root of the HAMMER repository, and run 'source $HAMMER_HOME/sourceme.sh'", rad_gen_log_fd)
        sys.exit(1)

    cur_env = os.environ.copy()

    """ Ex. args python3 rad_gen.py -s param_sweep/configs/noc_sweep.yml -c """
    if args.compile_results and args.design_sweep_config_file != '':
        compile_results(args)
    # If a design sweep config file is specified, modify the flow settings for each design in sweep
    elif args.design_sweep_config_file != '':
        design_sweep(args)
    else:
        run_asic_flow(args)
    
    


if __name__ == '__main__':
    main()