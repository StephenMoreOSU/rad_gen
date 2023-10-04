"""@package docstring
RADGen documentation can be found at https://rad-gen.readthedocs.io/en/latest/

"""


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
import src.data_structs as rg
import src.utils as rg_utils


import datetime

from dataclasses import dataclass

from typing import List, Dict, Any, Tuple, Type, NamedTuple, Set, Optional
# from typing import Pattern

from dataclasses import field
from pathlib import Path


#Import hammer modules
import vlsi.hammer.hammer.config as hammer_config
from vlsi.hammer.hammer.vlsi.hammer_vlsi_impl import HammerVLSISettings 
from vlsi.hammer.hammer.vlsi.driver import HammerDriver
import vlsi.hammer.hammer.tech as hammer_tech

# import gds funcs (for asap7)

import src.gds_fns as gds_fns


###### COFFE CUSTOM FLOW IMPORTS ######
import glob
import stat
import multiprocessing as mp

##### COFFE IMPORTS ##### 
# import COFFE.coffe.utils as coffe_utils 


# class RADGen():
#    def __init__(self, log_level=None):
#       self.




#  ██████╗ ███████╗███╗   ██╗███████╗██████╗  █████╗ ██╗         ██╗   ██╗████████╗██╗██╗     ███████╗
# ██╔════╝ ██╔════╝████╗  ██║██╔════╝██╔══██╗██╔══██╗██║         ██║   ██║╚══██╔══╝██║██║     ██╔════╝
# ██║  ███╗█████╗  ██╔██╗ ██║█████╗  ██████╔╝███████║██║         ██║   ██║   ██║   ██║██║     ███████╗
# ██║   ██║██╔══╝  ██║╚██╗██║██╔══╝  ██╔══██╗██╔══██║██║         ██║   ██║   ██║   ██║██║     ╚════██║
# ╚██████╔╝███████╗██║ ╚████║███████╗██║  ██║██║  ██║███████╗    ╚██████╔╝   ██║   ██║███████╗███████║
#  ╚═════╝ ╚══════╝╚═╝  ╚═══╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝     ╚═════╝    ╚═╝   ╚═╝╚══════╝╚══════╝


def write_dict_to_csv(csv_lines,csv_fname):
    csv_fd = open(f"{csv_fname}.csv","w")
    writer = csv.DictWriter(csv_fd, fieldnames=csv_lines[0].keys())
    writer.writeheader()
    for line in csv_lines:
        writer.writerow(line)
    csv_fd.close()

def check_for_valid_path(path):
    ret_val = False
    if os.path.exists(os.path.abspath(path)):
        ret_val = True
    else:
        rad_gen_log(f"ERROR: {path} does not exist", rad_gen_log_fd)
        raise FileNotFoundError(f"ERROR: {path} does not exist")
    return ret_val

def handle_error(fn, expected_vals: set=None):
    # for fn in funcs:
    if not fn() or (expected_vals is not None and fn() not in expected_vals):
        sys.exit(1)


def create_bordered_str(text: str = "", border_char: str = "#", total_len: int = 150) -> list:
    text = f"  {text}  "
    text_len = len(text)
    if(text_len > total_len):
        total_len = text_len + 10 
    border_size = (total_len - text_len) // 2
    return [ border_char * total_len, f"{border_char * border_size}{text}{border_char * border_size}", border_char * total_len]


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


def rec_find_fpath(dir,fname):
    ret_val = 1
    for root, dirs, files in os.walk(dir):
        if fname in files:
            ret_val = os.path.join(root, fname)
    return ret_val
                                                              
def pretty(d, indent=0):
   """
    Pretty prints a dictionary
   """
   for key, value in d.items():
      print('\t' * indent + str(key))
      if isinstance(value, dict):
         pretty(value, indent+1)
      else:
         print('\t' * (indent+1) + str(value))

def truncate(f, n):
    '''
        Truncates/pads a float f to n decimal places without rounding
    '''
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

def run_shell_cmd_no_logs(cmd_str: str, to_log: bool = True):
    if to_log:
        log_fd = rad_gen_log_fd
    else:
        log_fd = sys.stdout
    rad_gen_log(f"Running: {cmd_str}", log_fd)
    run_out = sp.Popen([cmd_str], executable='/bin/bash', env=cur_env, stderr=sp.PIPE, stdout=sp.PIPE, shell=True)
    run_stdout = ""
    for line in iter(run_out.stdout.readline, ""):
        if(run_out.poll() is None):
            run_stdout += line.decode("utf-8")
            if log_verbosity >= 2: 
                sys.stdout.buffer.write(line)
        else:
            break
    if log_verbosity >= 2: 
        _, run_stderr = run_out.communicate()
    else:
        run_stdout, run_stderr = run_out.communicate()
        run_stdout = run_stdout.decode("utf-8")
    run_stderr = run_stderr.decode("utf-8")
    return run_stdout, run_stderr

def run_shell_cmd_safe_no_logs(cmd_str: str):
    print(f"Running: {cmd_str}")
    ret_code = sp.call(cmd_str, executable='/bin/bash', env=cur_env, shell=True)
    return ret_code


def run_csh_cmd(cmd_str):
    rad_gen_log(f"Running: {cmd_str}",rad_gen_log_fd)
    sp.call(['csh', '-c', cmd_str])

    

def rec_get_flist_of_ext(design_dir_path,hdl_exts):
    """
    Takes in a path and recursively searches for all files of specified extension, returns dirs of those files and file paths in two lists
    """
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


def sanitize_config(config_dict) -> dict:
    """
        Modifies values of yaml config file to do the following:
        - Expand relative paths to absolute paths
    """    
    for param, value in config_dict.copy().items():
        if("path" in param or "sram_parameters" in param):
            if isinstance(value, list):
                config_dict[param] = [os.path.realpath(os.path.expanduser(v)) for v in value]
            elif isinstance(value, str):
                config_dict[param] = os.path.realpath(os.path.expanduser(value))
            else:
                pass
    return config_dict

def get_df_output_lines(df: pd.DataFrame) -> List[str]:
    cell_chars = 40
    ncols = len(df.columns)
    seperator = "+".join(["-"*cell_chars]*ncols)
    format_str = f"{{:^{cell_chars}}}"
    df_output_lines = [
        seperator,
        "|".join([format_str for _ in range(len(df.columns))]).format(*df.columns),
        seperator,
        *["|".join([format_str for _ in range(len(df.columns))]).format(*row.values) for _, row in df.iterrows()],
        seperator,
    ]
    return df_output_lines

# ██████╗ ██████╗ ██╗███╗   ███╗███████╗████████╗██╗███╗   ███╗███████╗
# ██╔══██╗██╔══██╗██║████╗ ████║██╔════╝╚══██╔══╝██║████╗ ████║██╔════╝
# ██████╔╝██████╔╝██║██╔████╔██║█████╗     ██║   ██║██╔████╔██║█████╗  
# ██╔═══╝ ██╔══██╗██║██║╚██╔╝██║██╔══╝     ██║   ██║██║╚██╔╝██║██╔══╝  
# ██║     ██║  ██║██║██║ ╚═╝ ██║███████╗   ██║   ██║██║ ╚═╝ ██║███████╗
# ╚═╝     ╚═╝  ╚═╝╚═╝╚═╝     ╚═╝╚══════╝   ╚═╝   ╚═╝╚═╝     ╚═╝╚══════╝


def write_pt_sdc(hammer_driver: HammerDriver):
    """
    Writes an sdc file in the format which will match the output of innovus par stage.
    """
    
    # create PT run-dir
    pt_outpath = os.path.join(hammer_driver.obj_dir,"pt-rundir")
    if not os.path.isdir(pt_outpath) :
        os.mkdir(pt_outpath)

    dec_re = re.compile(r"\d+\.{0,1}\d*")
    
    # <TAG> <MULTI-CLOCK TODO> add support for multiple clocks
    period = hammer_driver.database.get_setting("vlsi.inputs.clocks")[0]["period"]
    clock_fac = 1.0
    if "us" in period:
        clock_fac = 1e6 * clock_fac
    elif "ns" in period:
        clock_fac = 1e3 * clock_fac
    elif "ps" in period:
        clock_fac = 1.0 * clock_fac
    else:
        raise ValueError("Clock period units not recognized: us, ns, ps are supported")
    
    clk_period_ps = float(dec_re.search(period).group(0)) * clock_fac
    # TODO below could change to timing.inputs.clocks if there is a change between those stages 
    clk_pin = hammer_driver.database.get_setting("vlsi.inputs.clocks")[0]["name"]
    file_lines = [
        "#"*68,
        "# Created by rad_gen.py for ASAP7 connection from Cadence Innovus par to Synopsys Primetime",
        "#"*68,
        "set sdc_version 2.0",
        "set_units -time ps -resistance kOhm -capacitance pF -voltage V -current mA",
        f"create_clock [get_ports {clk_pin}] -period " + f"{clk_period_ps} " + f"-waveform {{0.0 {clk_period_ps/2.0}}}",
    ]
    fname = "pt.sdc"
    fd = open(os.path.join(pt_outpath,fname),"w")
    for line in file_lines:
        file_write_ln(fd,line)
    fd.close()



def pt_init(rad_gen_settings: rg.HighLvlSettings) -> Tuple[str]:
    """
        Performs actions required prior to running PrimeTime for Power or Timing
    """
    # create PT run-dir
    pt_outpath = os.path.join(rad_gen_settings.asic_flow_settings.obj_dir_path,"pt-rundir")
    if not os.path.isdir(pt_outpath) :
        os.mkdir(pt_outpath)

    # create reports dir
    report_path = os.path.join(pt_outpath,"reports")
    if not os.path.isdir(report_path) :
        os.mkdir(report_path)

    # get pnr output path (should be in this format)
    pnr_design_outpath = os.path.join(rad_gen_settings.asic_flow_settings.obj_dir_path,"par-rundir",f'{rad_gen_settings.asic_flow_settings.top_lvl_module}_FINAL')
    if not os.path.isdir(pnr_design_outpath) :
        rad_gen_log("Couldn't find output of pnr stage, Exiting...",rad_gen_log_fd)
        sys.exit(1)

    return pt_outpath, report_path, pnr_design_outpath

def write_pt_power_script(rad_gen_settings: rg.HighLvlSettings):
    pt_outpath, report_path, pnr_design_outpath = pt_init(rad_gen_settings)

    # Make sure that the $STDCELLS env var is set and use it to find the .lib files to use for Primetime
    search_paths = [os.path.join(rad_gen_settings.env_settings.rad_gen_home_path, lib) for lib in ["sram_db_libs","asap7_db_libs"] ]  #"/CMC/tools/synopsys/syn_vN-2017.09/libraries/syn /CMC/tools/synopsys/syn_vN-2017.09/libraries/syn_ver /CMC/tools/synopsys/syn_vN-2017.09/libraries/sim_ver"
    db_dirs =  [os.path.join(rad_gen_settings.env_settings.rad_gen_home_path,db_lib) for db_lib in ["sram_db_libs","asap7_db_libs"] ]
    target_libs = " ".join([os.path.join(db_dir,lib) for db_dir in db_dirs for lib in os.listdir(db_dir) if (lib.endswith(".db"))]) #and corner_filt_str in lib and transistor_type_str in lib) ])
    #default switching probability (TODO) find where this is and make it come from there
    switching_prob = "0.5"
    report_power_cmd = "report_power > " + os.path.join(report_path,"power.rpt")
    case_analysis_cmds = ["#MULTIMODAL ANALYSIS DISABLED"]
    #get switching activity and toggle rates from power_constraints tcl file
    top_mod = rad_gen_settings.asic_flow_settings.hammer_driver.database.get_setting("power.inputs.top_module")
    power_constraints_fd = open(os.path.join(pnr_design_outpath,f'{top_mod}_power_constraints.tcl'),"r")
    power_constraints_lines = power_constraints_fd.readlines()
    toggle_rate_var = "seq_activity"
    grab_opt_val_re = re.compile(f"(?<={toggle_rate_var}\s).*")
    toggle_rate = ""
    for line in power_constraints_lines:
        if "set_default_switching_activity" in line:
            toggle_rate = str(grab_opt_val_re.search(line).group(0))
    power_constraints_fd.close()
    switching_activity_cmd = "set_switching_activity -static_probability " + switching_prob + " -toggle_rate " + toggle_rate + " -base_clock $my_clock_pin -type inputs"
    # access driver db to get required info
    top_mod = rad_gen_settings.asic_flow_settings.hammer_driver.database.get_setting("power.inputs.top_module")
    # <TAG> <MULTI-CLOCK-TODO>
    clk_pin = rad_gen_settings.asic_flow_settings.hammer_driver.database.get_setting("vlsi.inputs.clocks")[0]["name"]
    verilog_netlist = rad_gen_settings.asic_flow_settings.hammer_driver.database.get_setting("power.inputs.netlist")
    #Standard Parasitic Exchange Format. File format to save parasitic information extracted by the place and route tool.
    # Just taking index 0 which is the 100C corner for case of high power
    spef_path = rad_gen_settings.asic_flow_settings.hammer_driver.database.get_setting("power.inputs.spefs")[0]
    file_lines = [
        "set sh_enable_page_mode true",
        "set search_path " + f"\"{search_paths}\"",
        "set my_top_level " + top_mod,
        "set my_clock_pin " + clk_pin,
        "set target_library " + f"\"{target_libs}\"",
        "set link_library " + "\"* $target_library\"",
        "read_verilog " + verilog_netlist,
        "current_design $my_top_level",
        case_analysis_cmds,
        "link",
        f"read_sdc -echo {pt_outpath}/pt.sdc",
        "read_parasitics -increment " + spef_path,
        "set power_enable_analysis TRUE",
        "set power_analysis_mode \"averaged\"",
        switching_activity_cmd,
        report_power_cmd,
        "quit",
    ]

    file_lines = flatten_mixed_list(file_lines)

    fname = os.path.join(pt_outpath,"pt_power.tcl")
    fd = open(fname, "w")
    for line in file_lines:
        file_write_ln(fd,line)
    fd.close()


def write_pt_timing_script(rad_gen_settings: rg.HighLvlSettings):
    """
    writes the tcl script for timing analysis using Synopsys Design Compiler, tested under 2017 version
    This should look for setup/hold violations using the worst case (hold) and best case (setup) libs
    """
    pt_outpath, report_path, pnr_design_outpath = pt_init(rad_gen_settings)

    # TODO all hardcoded paths need to be moved to the config file

    # Make sure that the $STDCELLS env var is set and use it to find the .lib files to use for Primetime
    search_paths = [os.path.join(rad_gen_settings.env_settings.rad_gen_home_path, lib) for lib in ["sram_db_libs","asap7_db_libs"] ]  #"/CMC/tools/synopsys/syn_vN-2017.09/libraries/syn /CMC/tools/synopsys/syn_vN-2017.09/libraries/syn_ver /CMC/tools/synopsys/syn_vN-2017.09/libraries/sim_ver"
    db_dirs =  [os.path.join(rad_gen_settings.env_settings.rad_gen_home_path,db_lib) for db_lib in ["sram_db_libs","asap7_db_libs"] ]


    # I tried to filter out specific corners and transistors but it results in errors ¯\_(ツ)_/¯
    # options are ["TT","FF","SS"]
    # corner_filt_str = "TT"
    # options are ["SLVT", "LVT", "RVT", "SRAM"] in order of decreasing drive strength
    # transistor_type_str = "SLVT"
    
    target_libs = " ".join([os.path.join(db_dir,lib) for db_dir in db_dirs for lib in os.listdir(db_dir) if (lib.endswith(".db"))]) #and corner_filt_str in lib and transistor_type_str in lib) ])
    
    #default switching probability (TODO) find where this is and make it come from there
    # switching_prob = "0.5"




    # report timing / power commands
    report_timing_cmd = "report_timing > " + os.path.join(report_path,"timing.rpt")
    #report_power_cmd = "report_power > " + os.path.join(report_path,"power.rpt")
    # <TAG> <MULTIMODAL-PWR-TIMING TODO>
    case_analysis_cmds = ["#MULTIMODAL ANALYSIS DISABLED"]
    
    # access driver db to get required info
    top_mod = rad_gen_settings.asic_flow_settings.hammer_driver.database.get_setting("timing.inputs.top_module")
    # <TAG> <MULTI-CLOCK-TODO>
    clk_pin = rad_gen_settings.asic_flow_settings.hammer_driver.database.get_setting("vlsi.inputs.clocks")[0]["name"]
    verilog_netlists = " ".join(rad_gen_settings.asic_flow_settings.hammer_driver.database.get_setting("timing.inputs.input_files"))
    #backannotate into primetime
    #This part should be reported for all the modes in the design.
    file_lines = [
        "set sh_enable_page_mode true",
        "set search_path " + f"\"{search_paths}\"",
        "set my_top_level " + top_mod,
        "set my_clock_pin " + clk_pin,
        "set target_library " + f"\"{target_libs}\"",
        "set link_library " + "\"* $target_library\"",
        "read_verilog " + f"\" {verilog_netlists} \"",
        "current_design $my_top_level",
        case_analysis_cmds,
        "link",
        #set clock constraints (this can be done by defining a clock or specifying an .sdc file)
        #read constraints file
        f"read_sdc -echo {pt_outpath}/pt.sdc",
        report_timing_cmd,
        "quit",
    ]
    file_lines = flatten_mixed_list(file_lines)

    fname = os.path.join(pt_outpath,"pt_timing.tcl")
    fd = open(fname, "w")
    for line in file_lines:
        file_write_ln(fd,line)
    fd.close()

    return


# ██╗  ██╗ █████╗ ███╗   ███╗███╗   ███╗███████╗██████╗     ██╗   ██╗████████╗██╗██╗     ███████╗
# ██║  ██║██╔══██╗████╗ ████║████╗ ████║██╔════╝██╔══██╗    ██║   ██║╚══██╔══╝██║██║     ██╔════╝
# ███████║███████║██╔████╔██║██╔████╔██║█████╗  ██████╔╝    ██║   ██║   ██║   ██║██║     ███████╗
# ██╔══██║██╔══██║██║╚██╔╝██║██║╚██╔╝██║██╔══╝  ██╔══██╗    ██║   ██║   ██║   ██║██║     ╚════██║
# ██║  ██║██║  ██║██║ ╚═╝ ██║██║ ╚═╝ ██║███████╗██║  ██║    ╚██████╔╝   ██║   ██║███████╗███████║
# ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝     ╚═╝╚══════╝╚═╝  ╚═╝     ╚═════╝    ╚═╝   ╚═╝╚══════╝╚══════╝                                                                           

def run_hammer_stage(asic_flow: rg.ASICFlowSettings, flow_stage: str, config_paths: List[str], update_db: bool = True, execute_stage: bool = True):
    """
        Invokes the hammer-vlsi tool with the specified config files and flow stage, returns hammer output config path, stdout & stderr
    """
    # For transitional flow stages
    # format config paths if multiple are needed
    config_path_args = [f'-p {c_p}' for c_p in config_paths]
    config_path_args = " ".join(config_path_args)
    # format env paths
    env_path_args = [f'-e {e_p}' for e_p in asic_flow.hammer_driver.options.environment_configs]
    env_path_args = " ".join(env_path_args)

    # Load path to hammer driver
    hammer_cli = asic_flow.hammer_cli_driver_path
    
    # rad_gen_log(f'Running hammer with input configs: {" ".join(config_paths)}...',rad_gen_log_fd)

    
    # return output config path for flow stage 
    # TODO make the recognition of a transitional stage
    rundir_flow_stages = ["lvs", "drc", "par", "syn", "timing", "power", "sim", "formal"]
    if flow_stage in rundir_flow_stages:
        if not os.path.isdir(os.path.join(asic_flow.hammer_driver.obj_dir,f"{flow_stage}-rundir")):
            os.mkdir(os.path.join(asic_flow.hammer_driver.obj_dir,f"{flow_stage}-rundir"))
        ret_config_path = os.path.join(asic_flow.hammer_driver.obj_dir,f"{flow_stage}-rundir",f"{flow_stage}-output.json")
        hammer_cmd = f'{hammer_cli} {env_path_args} {config_path_args} --obj_dir {asic_flow.hammer_driver.obj_dir} -o {ret_config_path} {flow_stage}'
    else:
        if "-to-" in flow_stage:
            flow_from = flow_stage.split("-")[0]
            flow_to = flow_stage.split("-")[2]
            ret_config_path = os.path.join(asic_flow.hammer_driver.obj_dir,f"{flow_to}-input.json")
        else:
            ret_config_path = os.path.join(asic_flow.hammer_driver.obj_dir,f"{flow_stage}-output.json")
        hammer_cmd = f'{hammer_cli} {env_path_args} {config_path_args} --obj_dir {asic_flow.hammer_driver.obj_dir} -o {ret_config_path} {flow_stage}'

    stdout, stderr = "", ""
    if execute_stage:
        stdout, stderr = run_shell_cmd_no_logs(hammer_cmd)
    
    if update_db and os.path.exists(ret_config_path):
        # update the driver information with new config
        proj_config_dicts = []
        for config in config_paths + [ret_config_path]:
            is_yaml = config.endswith(".yml") or config.endswith(".yaml")
            if not os.path.exists(config):
                rad_gen_log("Project config %s does not exist!" % (config),rad_gen_log_fd)
            config_str = Path(config).read_text()
            proj_config_dicts.append(hammer_config.load_config_from_string(config_str, is_yaml, str(Path(config).resolve().parent)))
        asic_flow.hammer_driver.update_project_configs(proj_config_dicts)


    return ret_config_path, stdout, stderr


# ██████╗  █████╗ ██████╗      ██████╗ ███████╗███╗   ██╗    ██╗   ██╗████████╗██╗██╗     ███████╗
# ██╔══██╗██╔══██╗██╔══██╗    ██╔════╝ ██╔════╝████╗  ██║    ██║   ██║╚══██╔══╝██║██║     ██╔════╝
# ██████╔╝███████║██║  ██║    ██║  ███╗█████╗  ██╔██╗ ██║    ██║   ██║   ██║   ██║██║     ███████╗
# ██╔══██╗██╔══██║██║  ██║    ██║   ██║██╔══╝  ██║╚██╗██║    ██║   ██║   ██║   ██║██║     ╚════██║
# ██║  ██║██║  ██║██████╔╝    ╚██████╔╝███████╗██║ ╚████║    ╚██████╔╝   ██║   ██║███████╗███████║
# ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝      ╚═════╝ ╚══════╝╚═╝  ╚═══╝     ╚═════╝    ╚═╝   ╚═╝╚══════╝╚══════╝


def get_rad_gen_flow_cmd(rad_gen_settings: rg.HighLvlSettings, config_path: str, sram_flag = False, top_level_mod = None, hdl_path = None):
    if top_level_mod is None and hdl_path is None:
        cmd = f'python3 rad_gen.py -e {rad_gen_settings.env_settings.top_lvl_config_path} -p {config_path}'
    else:
        cmd = f'python3 rad_gen.py -e {rad_gen_settings.env_settings.top_lvl_config_path} -p {config_path} -t {top_level_mod} -v {hdl_path}'

    if sram_flag:
        cmd = cmd + " -sram"
    return cmd

def modify_config_file(rad_gen: rg.HighLvlSettings):
    # recursively get all files matching extension in the design directory
    exts = ['.v','.sv','.vhd',".vhdl"]
    design_files, design_dirs = rec_get_flist_of_ext(rad_gen.asic_flow_settings.hdl_path, exts)

    # with open(rad_gen_settings.asic_flow_settings.config_path, 'r') as yml_file:
        # design_config = yaml.safe_load(yml_file)

    # TODO check to see if the multiple input config files breaks this
    design_config = rad_gen.asic_flow_settings.hammer_driver.project_config

    design_config["synthesis.inputs.input_files"] = design_files
    design_config["synthesis.inputs.top_module"] = rad_gen.asic_flow_settings.top_lvl_module
    # If the user specified valid search paths we should not override them but just append to them
    
    # TODO ADD THE CONDITIONAL TO CHECK BEFORE CONCAT, this could be cleaner but is ok for now, worst case we have too many serach paths
    # if("inputs.hdl_search_paths" in design_config["synthesis"].keys()):
    if("synthesis.inputs.hdl_search_paths" in design_config.keys()):
        design_config["synthesis.inputs.hdl_search_paths"] = design_config["synthesis.inputs.hdl_search_paths"] + design_dirs
    else:
        design_config["synthesis.inputs.hdl_search_paths"] = design_dirs
    
    # remove duplicates
    design_config["synthesis.inputs.hdl_search_paths"] = list(dict.fromkeys(design_config["synthesis.inputs.hdl_search_paths"])) 
    
    # init top level placement constraints
    design_config["vlsi.inputs.placement_constraints"][0]["path"] = rad_gen.asic_flow_settings.top_lvl_module

    # Creates directory for modified config files and writes new config
    # Intermediate/Generated configs & RTL will be output to the following directory
    # Not perfect but this allows for top directory of input designs to be named arbitrarily
    mod_config_outdir = None
    config_paths = rad_gen.asic_flow_settings.hammer_driver.options.project_configs
    for config_path in config_paths:
        # Read all configs and figure out which one contains the top level module info
        config_str = Path(config_path).read_text()
        is_yaml = config_path.endswith(".yml") or config_path.endswith(".yaml")
        config_dict = hammer_config.load_config_from_string(config_str, is_yaml, str(Path(config_path).resolve().parent))
        if "synthesis.inputs.top_module" in config_dict.keys():
            input_config_split = os.path.split(config_path)
            config_fname = os.path.splitext(os.path.basename(config_path))[0]
            mod_config_outdir = os.path.join(input_config_split[0], "gen")
            modified_config_path = os.path.join(mod_config_outdir, f"{config_fname}_pre_proc.yml")
            break
    
    # If it still can't find it, were just going to make the directory in the design input path with name of top level module
    if mod_config_outdir == None:
        rad_gen_log(f"ERROR: Can't find input design config, Exiting...")
        sys.exit(1)

    if not os.path.isdir( mod_config_outdir ):
        os.makedirs(mod_config_outdir)
    
    with open(modified_config_path, 'w') as yml_file:
        yaml.safe_dump(design_config, yml_file, sort_keys=False) 
    
    # Update hammer driver with new config
    proj_config_dicts = []
    for config in config_paths + [modified_config_path]:
        is_yaml = config.endswith(".yml") or config.endswith(".yaml")
        if not os.path.exists(config):
            rad_gen_log("Project config %s does not exist!" % (config),rad_gen_log_fd)
        config_str = Path(config).read_text()
        proj_config_dicts.append(hammer_config.load_config_from_string(config_str, is_yaml, str(Path(config).resolve().parent)))
    rad_gen.asic_flow_settings.hammer_driver.update_project_configs(proj_config_dicts)

    return modified_config_path


def find_newest_obj_dir(search_dir: str, obj_dir_fmt: str):
    """
        Finds newest object directory corresponding to current design in the specified RAD-Gen output directory.
        The obj_dir_fmt string is used to determine what date time & naming convension we're using to compare
        - If no obj dirs found, None will be returned signaling that one must be created
    """

    # dir were looking for obj dirs in
    #search_dir = os.path.join(rad_gen_settings.env_settings.design_output_path, rad_gen_settings.asic_flow_settings.top_lvl_module)

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


def rad_gen_log(log_str: str, file: str):
    """
    Prints to a log file and the console depending on level of verbosity
    log codes:
    {
        "info"
        "debug"
        "error"
    }
    """
    if file == sys.stdout:
        print(f"{log_str}")
    else:
        fd = open(file, 'a')
        if(log_verbosity >= 0):
            print(f"{log_str}",file=fd)
            print(f"{log_str}")
        fd.close()


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

def read_in_rtl_proj_params(rad_gen_settings: rg.HighLvlSettings, rtl_params, top_level_mod, rtl_dir_path, sweep_param_inc_path=False):

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

            if not os.path.exists(include_fpath):
                rad_gen_log("WARNING: Could not find parameter header file, returning None ...", rad_gen_log_fd)
                return None
            # Look in the include file path and grab all parameters and defines
            include_rtl = open(include_fpath).read()
            clean_include_rtl = c_style_comment_rm(include_rtl)
            for inc_line in clean_include_rtl.split("\n"):
                
                # Look for parameters
                if rad_gen_settings.env_settings.res.find_params_re.search(inc_line):
                    # TODO this parameter re will not work if no whitespace between params
                    clean_line = " ".join(rad_gen_settings.env_settings.res.wspace_re.split(inc_line)[1:]).replace(";","")
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

                elif rad_gen_settings.env_settings.res.find_defines_re.search(inc_line):
                    # TODO this define re will not work if no whitespace between params
                    clean_line = " ".join(rad_gen_settings.env_settings.res.wspace_re.split(inc_line)[1:])
                    # Get the define name and value
                    define_name = rad_gen_settings.env_settings.res.wspace_re.split(clean_line)[0]
                    if rad_gen_settings.env_settings.res.grab_bw_soft_bkt.search(clean_line):
                        define_val = rad_gen_settings.env_settings.res.grab_bw_soft_bkt.search(clean_line).group(0)
                    else:
                        define_val = rad_gen_settings.env_settings.res.wspace_re.split(clean_line)[1].replace("`","")
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
    while rad_gen_settings.env_settings.res.find_localparam_re.search(tmp_top_lvl_rtl):
        local_param = rad_gen_settings.env_settings.res.find_localparam_re.search(tmp_top_lvl_rtl).group(0)
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
    param_print_stdout = sp.run([os.path.join(os.getcwd(),"a.out")],stderr=sp.PIPE,stdout=sp.PIPE,stdin=sp.PIPE)
    rad_gen_log(param_print_stdout.stdout.decode("utf-8"),rad_gen_log_fd)
    sp.run(["rm","a.out"])

    param_print_stdout = param_print_stdout.stdout.decode("utf-8")
    params = []
    for line in param_print_stdout.split("\n"):
        if line != "":
            x = rad_gen_settings.env_settings.res.wspace_re.sub(repl="",string=line).split(":")
            p_dict = {x[0]:x[1]}
            params.append(p_dict)

    return params

# ███████╗██████╗  █████╗ ███╗   ███╗     ██████╗ ███████╗███╗   ██╗
# ██╔════╝██╔══██╗██╔══██╗████╗ ████║    ██╔════╝ ██╔════╝████╗  ██║
# ███████╗██████╔╝███████║██╔████╔██║    ██║  ███╗█████╗  ██╔██╗ ██║
# ╚════██║██╔══██╗██╔══██║██║╚██╔╝██║    ██║   ██║██╔══╝  ██║╚██╗██║
# ███████║██║  ██║██║  ██║██║ ╚═╝ ██║    ╚██████╔╝███████╗██║ ╚████║
# ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝     ╚═════╝ ╚══════╝╚═╝  ╚═══╝



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

def gen_compiled_srams(rad_gen_settings: rg.HighLvlSettings, design_id: int, base_config: dict):
    cur_design = rad_gen_settings.design_sweep_infos[design_id]
    for mem in cur_design.type_info.mems:
        # The path in hammer to directory containing srams.txt file (describes the available macros in the pdk)
        hammer_tech_pdk_path = os.path.join(rad_gen_settings.env_settings.hammer_tech_path, rad_gen_settings.tech_info.name)
        mapping = sram_compiler.compile(hammer_tech_pdk_path, mem["rw_ports"], mem["w"], mem["d"])
        sram_map_info, rtl_outpath = sram_compiler.write_rtl_from_mapping(
                                                    mapping,
                                                    cur_design.type_info.base_rtl_path,
                                                    rad_gen_settings.sram_compiler_settings.rtl_out_path)
        sram_map_info = sram_compiler.translate_logical_to_phsical(sram_map_info)
        config_path = mod_rad_gen_config_from_rtl(
                                            rad_gen_settings,
                                            base_config,
                                            sram_map_info,
                                            rtl_outpath)
        # Log out flow command
        rad_gen_log(get_rad_gen_flow_cmd(rad_gen_settings = rad_gen_settings, config_path = config_path, sram_flag = True),rad_gen_log_fd)
    # for mem in sanitized_design["mems"]:
        
        # get mapping and find the macro in lib, instantiate that many and

def sram_sweep_gen(rad_gen_settings: rg.HighLvlSettings, design_id: int):
    # current design
    cur_design = rad_gen_settings.design_sweep_infos[design_id]
    base_config = sanitize_config(yaml.safe_load(open(cur_design.base_config_path,"r")))
    # This is where we will send the output sram macros
    if not os.path.isdir(rad_gen_settings.sram_compiler_settings.rtl_out_path):
        os.makedirs(rad_gen_settings.sram_compiler_settings.rtl_out_path)
    gen_compiled_srams(rad_gen_settings, design_id, base_config) #,base_config, sanitized_design)
    # load in the mem_params.json file <TAG> <HAMMER-IR-PARSE TODO>     
    with open(os.path.expanduser(base_config["vlsi.inputs"]["sram_parameters"]), 'r') as fd:
        mem_params = json.load(fd)
    # List of available SRAM macros
    sram_macro_lefs = os.listdir(os.path.join(rad_gen_settings.tech_info.sram_lib_path, "lef"))
    # Sweep over all widths and depths for SRAMs in the sweep config file  
    for rw_port in cur_design.type_info.rw_ports:         
        for depth in cur_design.type_info.depths:
            for width in cur_design.type_info.widths:
                """ MODIFIYING MEM CONFIG JSON FILES """
                # If we want to iterate through and keep an original reference set of configs we need to use deepcopy on the dict
                # This concept is very annoying as when assigning any variable to a dict you are actually just creating a reference to the dict (Very unlike C) :(
                # All mem_params are indexed to 0 since we are only sweeping over a single SRAM TODO
                # Create copies of each configs s.t they can be modified without affecting the original
                mod_base_config = copy.deepcopy(base_config)
                mod_mem_params = copy.deepcopy(mem_params)
                modify_mem_params(mod_mem_params, width, depth, rw_port)
                # Make sure that the SRAM macro exists in the list of SRAM macros
                # <TAG> <HAMMER-IR-PARSE TODO>
                if not any(mod_mem_params[0]["name"] in macro for macro in sram_macro_lefs):
                    rad_gen_log(f"WARNING: {mod_mem_params[0]['name']} not found in list of SRAM macros, skipping config generation...",rad_gen_log_fd)
                    continue
                
                for ret_str in create_bordered_str(f"Generating files required for design: {mod_mem_params[0]['name']}"):
                    rad_gen_log(ret_str,rad_gen_log_fd)                        
                
                # Modify the mem_params.json file with the parameters specified in the design sweep config file
                mem_params_json_fpath = os.path.splitext(base_config["vlsi.inputs"]["sram_parameters"])[0]+f'_{mod_mem_params[0]["name"]}.json'
                with open(os.path.splitext(os.path.expanduser(base_config["vlsi.inputs"]["sram_parameters"]))[0]+f'_{mod_mem_params[0]["name"]}.json', 'w') as fd:
                    json.dump(mod_mem_params, fd, sort_keys=False)
                rad_gen_log(f"INFO: Writing memory params to {mem_params_json_fpath}",rad_gen_log_fd)
                
                """ MODIFIYING SRAM RTL"""
                # Get just the filename of the sram sv file and append the new dims to it
                mod_rtl_fname = os.path.splitext(cur_design.type_info.base_rtl_path.split("/")[-1])[0]+f'_{mod_mem_params[0]["name"]}.sv'
                # Modify the parameters for SRAM_ADDR_W and SRAM_DATA_W and create a copy of the base sram 
                # TODO find a better way to do this rather than just creating a ton of files, the only thing I'm changing are 2 parameters in rtl
                with open(cur_design.type_info.base_rtl_path, 'r') as fd:
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
                
                base_rtl_dir = os.path.split(cur_design.type_info.base_rtl_path)[0]
                # Create a new dir for the modified sram
                mod_rtl_dir = os.path.join(base_rtl_dir,f'{mod_mem_params[0]["name"]}')
                
                sp.call("mkdir -p " + mod_rtl_dir,shell=True)
            
                modified_sram_rtl_path = os.path.join(cur_design.rtl_dir_path, mod_rtl_dir.split("/")[-1], mod_rtl_fname)
                with open(modified_sram_rtl_path, 'w') as fd:
                    fd.write(mod_sram_rtl)
                rad_gen_log(f"INFO: Writing sram rtl to {modified_sram_rtl_path}",rad_gen_log_fd)
                """ MODIFYING HAMMER CONFIG YAML FILES """
                m_sizes = get_sram_macro_sizes(rad_gen_settings, mod_mem_params[0]["name"])
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
                modified_config_path = os.path.splitext(cur_design.base_config_path)[0]+f'_{mod_mem_params[0]["name"]}.yaml'
                with open(modified_config_path, 'w') as fd:
                    yaml.safe_dump(mod_base_config, fd, sort_keys=False)    
                rad_gen_log(f"INFO: Writing rad_gen yml config to {modified_config_path}",rad_gen_log_fd)
                rad_gen_log(get_rad_gen_flow_cmd(rad_gen_settings, modified_config_path, sram_flag=True),rad_gen_log_fd)

def get_sram_macro_sizes(rad_gen_settings: rg.HighLvlSettings, macro_fname: str) -> list:
    for file in os.listdir(os.path.join(rad_gen_settings.tech_info.sram_lib_path,"lef")):
        m_sizes = []
        if macro_fname in file:
            # TODO fix the way that the size of macro is being searched for this way would not work in all cases
            lef_text = open(os.path.join(rad_gen_settings.tech_info.sram_lib_path,"lef",file), "r").read()
            for line in lef_text.split("\n"):
                if "SIZE" in line:
                    # This also assumes the symmetry in the lef is X Y rather than searching for it TODO
                    m_sizes = [float(s) for s in line.split(" ") if rad_gen_settings.env_settings.res.decimal_re.match(s)]
                    break
        if len(m_sizes) > 0:
            break
    return m_sizes


def mod_rad_gen_config_from_rtl(rad_gen_settings: rg.HighLvlSettings, base_config: dict, sram_map_info: dict, rtl_path: str) -> dict:
    config_out_path = rad_gen_settings.sram_compiler_settings.config_out_path
    if not os.path.exists(config_out_path):
        os.mkdir(config_out_path)

    # create a copy which will be modified of the sram base config (hammer config)
    mod_base_config = copy.deepcopy(base_config)
    """ WRITING MEM PARAMS JSON FILES """
    # load in the mem_params.json file            
    with open(os.path.expanduser(base_config["vlsi.inputs"]["sram_parameters"]), 'r') as fd:
        mem_params = json.load(fd)
    mod_mem_params = copy.deepcopy(mem_params)
    modify_mem_params(mod_mem_params, width=sram_map_info["macro_w"], depth=sram_map_info["macro_d"], num_ports=sram_map_info["num_rw_ports"])

    mem_params_json_fpath = os.path.join(config_out_path,"mem_params_"+f'_{sram_map_info["macro"]}.json')
    with open(mem_params_json_fpath, 'w') as fd:
        json.dump(mod_mem_params, fd, sort_keys=False)
    # Defines naming convension of SRAM macros TODO
    """ MODIFYING AND WRITING HAMMER CONFIG YAML FILES """
    
    m_sizes = get_sram_macro_sizes(rad_gen_settings, sram_map_info["macro"])
    
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


# ██████╗  █████╗ ██████╗ ███████╗██╗███╗   ██╗ ██████╗     ██╗   ██╗████████╗██╗██╗     ███████╗
# ██╔══██╗██╔══██╗██╔══██╗██╔════╝██║████╗  ██║██╔════╝     ██║   ██║╚══██╔══╝██║██║     ██╔════╝
# ██████╔╝███████║██████╔╝███████╗██║██╔██╗ ██║██║  ███╗    ██║   ██║   ██║   ██║██║     ███████╗
# ██╔═══╝ ██╔══██║██╔══██╗╚════██║██║██║╚██╗██║██║   ██║    ██║   ██║   ██║   ██║██║     ╚════██║
# ██║     ██║  ██║██║  ██║███████║██║██║ ╚████║╚██████╔╝    ╚██████╔╝   ██║   ██║███████╗███████║
# ╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚═╝╚═╝  ╚═══╝ ╚═════╝      ╚═════╝    ╚═╝   ╚═╝╚══════╝╚══════╝


def parse_gds_to_area_output(rad_gen: rg.HighLvlSettings, obj_dir_path: str):

    gds_to_area_log_fpath = os.path.join(rad_gen.tech_info.pdk_rundir_path, rad_gen.env_settings.scripts_info.gds_to_area_fname + ".log")
    fd = open(gds_to_area_log_fpath, 'r')
    lines = fd.readlines()
    fd.close()
    # Find the line with the area
    for i, line in enumerate(lines):
        if "print(cv~>bBox)" in line:
            bbox_bounds = rad_gen.env_settings.res.signed_dec_re.findall(lines[i+1])
    width = float(bbox_bounds[2]) - float(bbox_bounds[0])
    height = float(bbox_bounds[3]) - float(bbox_bounds[1])
    area = width * height
    with open(os.path.join(obj_dir_path, rad_gen.env_settings.report_info.gds_area_fname),"w") as fd:
        print(f"Area of design is {width}x{height}={area} um^2",file=fd)        
        print(f"GDS Area: {area}",file=fd)    
    print(f"Area of design is {width}x{height}={area} um^2")
    
    return area

def get_macro_info(rad_gen: rg.HighLvlSettings, obj_dir: str, sram_num_bits: int = None) -> dict:
    """ Looking for SRAM Macros """
    report_dict = {}
    sram_macros = []
    macro_lef_areas = []
    if os.path.isfile(os.path.join(obj_dir,"syn-rundir","syn-output-full.json")):
        syn_out_config = json.load(open(os.path.join(obj_dir,"syn-rundir","syn-output-full.json")))
        if "vlsi.inputs.sram_parameters" in syn_out_config.keys():
            for sram in syn_out_config["vlsi.inputs.sram_parameters"]:
                sram_macros.append(sram["name"])
                m_sizes = get_sram_macro_sizes(rad_gen, sram["name"])
                macro_lef_areas.append(m_sizes[0]*m_sizes[1])
                if sram_num_bits is not None:
                    num_macros = sram_num_bits // (int(sram['width'])*int(sram['depth']))
                    report_dict["num_macros"] = num_macros

        if len(sram_macros) > 0:
            report_dict["sram_macros"] = "\t ".join(sram_macros)
            report_dict["sram_macro_lef_areas"] = "\t ".join([str(x) for x in macro_lef_areas])            

    return report_dict

def parse_report_c(rad_gen_settings: rg.HighLvlSettings, top_level_mod: str, report_path: str, rep_type: str, flow_stage: dict, summarize: bool = False):
    """
        This specifically parses reports and looks for keywords to grab the values and put them into a list of dicts 
        The list is indexed based on the number of values present in the report file.
        For example: 
            For Timing -> If there are a bunch of paths in the report, the list will be indexed by each specific timing path (index 0 contains worst case)
            For Area -> If there are a bunch of modules in the report, the list will be indexed by each specific module (index 0 contains total area)
    """    
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

    cadence_timing_grab_re = re.compile("Path(.*?#-+){3}",re.MULTILINE|re.DOTALL)
    cadence_timing_setup_re = re.compile("Setup:-.*$",re.MULTILINE)
    
    unit_re_str = "(" + "|".join([f"({unit})" for unit in rad_gen_settings.env_settings.report_info.power_lookup.keys()]) + ")"                  
    
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
            sep_line = rad_gen_settings.env_settings.res.wspace_re.split(line)
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
                        timing_dict["Setup"] = float(rad_gen_settings.env_settings.res.decimal_re.findall(line)[0])
                    elif cadence_arrival_time_re.search(line):
                        timing_dict["Arrival"] = float(rad_gen_settings.env_settings.res.decimal_re.findall(line)[0])
                    elif "Slack" in line:
                        timing_dict["Slack"] = float(rad_gen_settings.env_settings.res.signed_dec_re.findall(line)[0])
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
                    timing_dict["Setup"] = float(rad_gen_settings.env_settings.res.decimal_re.findall(line)[0])
                elif "data arrival time" in line:
                    timing_dict["Arrival"] = float(rad_gen_settings.env_settings.res.decimal_re.findall(line)[0])
                elif "slack" in line:
                    timing_dict["Slack"] = float(rad_gen_settings.env_settings.res.signed_dec_re.findall(line)[0])
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
                    for unit in rad_gen_settings.env_settings.report_info.power_lookup.keys():
                        if f" {unit} " in line or f" {unit}" in line:
                            units = rad_gen_settings.env_settings.report_info.power_lookup[unit]
                            break
                    power_dict["Dynamic"] = float(rad_gen_settings.env_settings.res.decimal_re.findall(line)[0]) * units
                    # Check to make sure that the total has multiple values associated with it
                elif "Total" in line and len(rad_gen_settings.env_settings.res.decimal_re.findall(line)) > 1:
                    pwr_totals = []
                    pwr_vals_line = line
                    while synopsys_grab_pwr_val_re.search(pwr_vals_line):
                        pwr_val = synopsys_grab_pwr_val_re.search(pwr_vals_line).group(0)
                        for unit in rad_gen_settings.env_settings.report_info.power_lookup.keys():
                            if f" {unit} " in pwr_val or f" {unit}" in pwr_val:
                                units = rad_gen_settings.env_settings.report_info.power_lookup[unit]
                                break
                        pwr_total = float(rad_gen_settings.env_settings.res.wspace_re.split(pwr_val)[0]) * units
                        pwr_totals.append(pwr_total)
                        pwr_vals_line = pwr_vals_line.replace(pwr_val,"")
                    power_dict["Total"] = pwr_totals[-1]
            report_list.append(power_dict)
        elif flow_stage["tool"] == "cadence":
            cadence_hdr_catagories = ["Leakage","Internal","Switching","Total","Row%"]
            power_dict = {}
            for line in power_rpt_text.split("\n"):
                if "Power Unit" in line:
                    for unit in rad_gen_settings.env_settings.report_info.power_lookup.keys():
                        if unit in line:
                            units = rad_gen_settings.env_settings.report_info.power_lookup[unit]
                            break
                if flow_stage["name"] == "par":
                    if "Total Internal Power:" in line:
                        power_dict["Internal"] = float(rad_gen_settings.env_settings.res.decimal_re.findall(line)[0]) * units
                    elif "Total Switching Power:" in line:
                        power_dict["Leakage"] = float(rad_gen_settings.env_settings.res.decimal_re.findall(line)[0]) * units
                    elif "Total Leakage Power:" in line:
                        power_dict["Switching"] = float(rad_gen_settings.env_settings.res.decimal_re.findall(line)[0]) * units
                    elif "Total Power:" in line:
                        power_dict["Total"] = float(rad_gen_settings.env_settings.res.decimal_re.findall(line)[0]) * units
                elif flow_stage["name"] == "syn":
                    if "Subtotal" in line:
                        power_vals = [ float(str_val) for str_val in rad_gen_settings.env_settings.res.sci_not_dec_re.findall(line)]
                        power_dict = {catagory: float(power_vals[idx]) * units for idx, catagory in enumerate(cadence_hdr_catagories) }

            report_list.append(power_dict)

    
    return report_list


def get_report_results(rad_gen_settings: rg.HighLvlSettings, top_level_mod: str, report_dir_path: str, flow_stage: dict) -> dict:
    """
        This function will parse the specified report_dir_path which should contain .rpt report files for various stages of asic flow
        Functional for:
        - Cadence & Synopsys
        - Area, Timing, Power
    """
    results = {}
    if os.path.isdir(report_dir_path):
        for file in os.listdir(report_dir_path):
            if os.path.isfile(os.path.join(report_dir_path, file)) and file.endswith(".rpt"):
                # Look for area summary report
                if("area" in file and "detailed" not in file):
                    results["area"] = parse_report_c(rad_gen_settings, top_level_mod, os.path.join(report_dir_path, file), "area", flow_stage, summarize=False)
                elif("time" in file or "timing" in file):
                    results["timing"] = parse_report_c(rad_gen_settings, top_level_mod, os.path.join(report_dir_path, file), "timing", flow_stage, summarize=False)
                elif("power" in file): 
                    results["power"] = parse_report_c(rad_gen_settings, top_level_mod, os.path.join(report_dir_path, file), "power", flow_stage, summarize=False)
    else:
        rad_gen_log(f"Warning: {flow_stage['name']} report path does not exist", rad_gen_log_fd)
    return results 

def parse_output(rad_gen_settings: rg.HighLvlSettings,top_level_mod: str, output_path: str):
    syn_dir = "syn-rundir"
    par_dir = "par-rundir"
    pt_dir = "pt-rundir"
    # Loop through the output dir and find the relevant files to each stage of the flow
    syn_report_path = os.path.join(output_path,syn_dir,"reports")
    par_report_path = os.path.join(output_path,par_dir)
    pt_report_path = os.path.join(output_path,pt_dir,"reports")
    syn_results = get_report_results(rad_gen_settings, top_level_mod, syn_report_path, rad_gen_settings.asic_flow_settings.flow_stages["syn"])
    par_results = get_report_results(rad_gen_settings, top_level_mod, par_report_path, rad_gen_settings.asic_flow_settings.flow_stages["par"])
    pt_results = get_report_results(rad_gen_settings, top_level_mod, pt_report_path, rad_gen_settings.asic_flow_settings.flow_stages["pt"])
    return syn_results, par_results, pt_results


def get_gds_area_from_rpt(rad_gen: rg.HighLvlSettings, obj_dir: str):
    with open(os.path.join(obj_dir, rad_gen.env_settings.report_info.gds_area_fname),"r") as f:
        for line in f:
            if "Area" in line:
                area = float(rad_gen.env_settings.res.decimal_re.findall(line)[-1]) 
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

    if len(report["par"]) > 0:
        total_area = float(report["par"]["area"][0]["Total Area"])
        # print(f'Total Area: {total_area}')
        report_to_csv["Total Area"] = total_area

        gds_area = float(report["gds_area"])
        report_to_csv["GDS Area"] = gds_area
        # print(f'GDS Area: {gds_area}')
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
        # print(f'Input Module Area: {input_channel_area} : {input_channel_area/total_area}')
        report_to_csv["Input Module Area"] = input_channel_area
        report_to_csv["Input Module Area Percentage"] = input_channel_area/total_area

        # xbr
        xbr_idx = next(( index for (index, d) in enumerate(report["par"]["area"]) if d["Hinst Name"] == "genblk1.vcr/xbr"), None)
        xbr_area = float(report["par"]["area"][xbr_idx]["Total Area"])
        # print(f'XBR Area: {xbr_area} : {xbr_area/total_area}')
        report_to_csv["XBR Area"] = xbr_area
        report_to_csv["XBR Area Percentage"] = xbr_area/total_area
        # sw allocator
        sw_alloc_idx = next(( index for (index, d) in enumerate(report["par"]["area"]) if d["Hinst Name"] == "genblk1.vcr/alo/genblk2.sw_core_sep_if"), None)
        sw_alloc_area = float(report["par"]["area"][sw_alloc_idx]["Total Area"])
        # print(f'SW Alloc Area: {sw_alloc_area} : {sw_alloc_area/total_area}')
        report_to_csv["SW Alloc Area"] = sw_alloc_area
        report_to_csv["SW Alloc Area Percentage"] = sw_alloc_area/total_area
        # vc allocator
        vc_alloc_idx = next(( index for (index, d) in enumerate(report["par"]["area"]) if d["Hinst Name"] == "genblk1.vcr/alo/genblk1.vc_core_sep_if"), None)
        vc_alloc_area = float(report["par"]["area"][vc_alloc_idx]["Total Area"])
        # print(f'VC Alloc Area: {vc_alloc_area} : {vc_alloc_area/total_area}')
        report_to_csv["VC Alloc Area"] = vc_alloc_area
        report_to_csv["VC Alloc Area Percentage"] = vc_alloc_area/total_area
        # output modules
        output_channel_area = float(0)
        for i in range(num_ports):
            opc_alloc_idx = next(( index for (index, d) in enumerate(report["par"]["area"]) if d["Hinst Name"] == f"genblk1.vcr/ops[{i}].opc"), None)
            output_channel_area += float(report["par"]["area"][opc_alloc_idx]["Total Area"])
        # print(f'Output Module Area: {output_channel_area} : {output_channel_area/total_area}')

        report_to_csv["Output Module Area"] = output_channel_area
        report_to_csv["Output Module Area Percentage"] = output_channel_area/total_area
    
    # TIMING
    for flow_tag in ["pt", "par", "syn"]:
        if len(report[flow_tag]) > 0:
            if "timing" in report[flow_tag]:
                report_to_csv["Slack"] = float(report[flow_tag]["timing"][0]["Slack"])
                report_to_csv["Timing Src"] = flow_tag

    return report_to_csv






def gen_reports(rad_gen_settings: rg.HighLvlSettings, design: rg.DesignSweepInfo , top_level_mod: str, report_dir: str, sram_num_bits: int = None):
    """
        Generates reports and runs post processing scripts to generate csv files containing final values for a design point
        Takes a hammer generated obj directory as its input report dir 
    """
    retval = None
    report_dict = {}
    # print(f"Parsing results for {dir}")
    syn_rpts, par_rpts, pt_rpts = parse_output(rad_gen_settings, top_level_mod, report_dir)
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
                m_sizes = get_sram_macro_sizes(rad_gen_settings, sram["name"])
                macro_lef_areas.append(m_sizes[0]*m_sizes[1])
                if sram_num_bits is not None:
                    num_macros = sram_num_bits // (int(sram['width'])*int(sram['depth']))
                    report_dict["num_macros"] = num_macros

        report_dict["sram_macros"] = "\t ".join(sram_macros)
        report_dict["sram_macro_lef_areas"] = "\t ".join([str(x) for x in macro_lef_areas])
    # Add the gds areas to the report
    gds_file = os.path.join(report_dir,"par-rundir",f"{top_level_mod}_drc.gds")
    if os.path.isfile(gds_file):
        write_virtuoso_gds_to_area_script(rad_gen_settings, gds_file)
        for ext in ["csh","sh"]:
            permission_cmd = "chmod +x " +  os.path.join(rad_gen_settings.tech_info.pdk_rundir_path,f'{rad_gen_settings.env_settings.scripts_info.gds_to_area_fname}.{ext}')
            run_shell_cmd_no_logs(permission_cmd)
        # run_shell_cmd_no_logs(os.path.join(tech_info.pdk_rundir_path,f"{script_info.gds_to_area_fname}.sh"))
        if not os.path.exists(os.path.join(report_dir,rad_gen_settings.env_settings.report_info.gds_area_fname)):
            run_csh_cmd(os.path.join(rad_gen_settings.tech_info.pdk_rundir_path,f"{rad_gen_settings.env_settings.scripts_info.gds_to_area_fname}.csh"))
            report_dict["gds_area"] = parse_gds_to_area_output(rad_gen_settings, report_dir)
        else:
            report_dict["gds_area"] = get_gds_area_from_rpt(rad_gen_settings, report_dir)
    # RTL Parameter section
    if design is not None and design.type == "rtl_params":
        # Using the output syn directory to find parameters in hdl search paths
        if(os.path.isfile(os.path.join(report_dir,"syn-rundir","syn-output-full.json"))):
            syn_out_config = json.load(open(os.path.join(report_dir,"syn-rundir","syn-output-full.json")))
            # looping through hdl search paths
            for path in syn_out_config["synthesis.inputs.hdl_search_paths"]:
                if "param_sweep_headers" in path:
                    param_hdr_name = os.path.basename(design.type_info.base_header_path)
                    params = read_in_rtl_proj_params(rad_gen_settings, design.type_info.params, top_level_mod, design.rtl_dir_path, os.path.join(path, param_hdr_name))
                    if params != None and params != []:
                        report_dict["rtl_params"] = params
                    else:
                        report_dict = None
                    break         
        else:
            report_dict = None             
    return report_dict


def gen_parse_reports(rad_gen_settings: rg.HighLvlSettings, report_search_dir: str, top_level_mod: str, design: rg.DesignSweepInfo = None, sram_num_bits: int = None):
    """
        Searches through the specified search directory and will compile a list of all reports from specified design
        TODO allow for users to more easily parse reports from multiple designs or design points ie specify filter for designs users would like to parse
    """
    reports = []
    for dir in os.listdir(report_search_dir):
        design_out_dir = os.path.join(report_search_dir,dir)
        for r_dir in os.listdir(design_out_dir):
            report_dir = os.path.join(design_out_dir, r_dir)
            # only check to determine validity of output dir
            if os.path.isdir(report_dir) and r_dir.startswith(top_level_mod):
                print(f"Parsing results for {report_dir}")
                report = gen_reports(rad_gen_settings, design, top_level_mod, report_dir, sram_num_bits)
                if report != None:
                    reports.append(report)
                
    return reports


#  █████╗ ███████╗██╗ ██████╗    ███████╗██╗      ██████╗ ██╗    ██╗
# ██╔══██╗██╔════╝██║██╔════╝    ██╔════╝██║     ██╔═══██╗██║    ██║
# ███████║███████╗██║██║         █████╗  ██║     ██║   ██║██║ █╗ ██║
# ██╔══██║╚════██║██║██║         ██╔══╝  ██║     ██║   ██║██║███╗██║
# ██║  ██║███████║██║╚██████╗    ██║     ███████╗╚██████╔╝╚███╔███╔╝
# ╚═╝  ╚═╝╚══════╝╚═╝ ╚═════╝    ╚═╝     ╚══════╝ ╚═════╝  ╚══╝╚══╝ 

#   ___ _   _ ___ _____ ___  __  __   _____ ___   ___  _    ___ 
#  / __| | | / __|_   _/ _ \|  \/  | |_   _/ _ \ / _ \| |  / __|
# | (__| |_| \__ \ | || (_) | |\/| |   | || (_) | (_) | |__\__ \
#  \___|\___/|___/ |_| \___/|_|  |_|   |_| \___/ \___/|____|___/



def flow_settings_pre_process(processed_flow_settings, cur_env):
  """Takes values from the flow_settings dict and converts them into data structures which can be used to write synthesis script"""
  # formatting design_files
  design_files = []
  if processed_flow_settings['design_language'] == 'verilog':
    ext_re = re.compile(".*.v")
  elif processed_flow_settings['design_language'] == 'vhdl':
    ext_re = re.compile(".*.vhdl")
  elif processed_flow_settings['design_language'] == 'sverilog':
    ext_re = re.compile(".*(.sv)|(.v)")

  design_folder = os.path.expanduser(processed_flow_settings['design_folder'])
  design_files = [fn for _, _, fs in os.walk(design_folder) for fn in fs if ext_re.search(fn)]
  #The syn_write_tcl_script function expects this to be a list of all design files
  processed_flow_settings["design_files"] = design_files
  # formatting search_path
  search_path_dirs = []
  search_path_dirs.append(".")
  try:
    syn_root = cur_env.get("SYNOPSYS")
    search_path_dirs = [os.path.join(syn_root,"libraries",dirname) for dirname in ["syn","syn_ver","sim_ver"] ]
  except:
    print("could not find 'SYNOPSYS' environment variable set, please source your ASIC tools or run the following command to your sysopsys home directory")
    print("export SYNOPSYS=/abs/path/to/synopsys/home")
    print("Ex. export SYNOPSYS=/CMC/tools/synopsys/syn_vN-2017.09/")
    sys.exit(1)
  #Place and route
  if(processed_flow_settings["pnr_tool"] == "innovus"):
    try:
      edi_root = cur_env.get("EDI_HOME")
      processed_flow_settings["EDI_HOME"] = edi_root
    except:
      print("could not find 'EDI_HOME' environment variable set, please source your ASIC tools or run the following command to your INNOVUS/ENCOUNTER home directory")
      sys.exit(1)
  
  #creating search path values
  for p_lib_path in processed_flow_settings["process_lib_paths"]:
    search_path_dirs.append(p_lib_path)
  search_path_dirs.append(design_folder)
  for root,dirnames,fnames in os.walk(design_folder):
    for dirname,fname in zip(dirnames,fnames):
      if(ext_re.search(fname)):
        search_path_dirs.append(os.path.join(root,dirname))
  
  search_path_str = "\"" + " ".join(search_path_dirs) + "\""
  processed_flow_settings["search_path"] = search_path_str
  #formatting target libs
  processed_flow_settings["target_library"] = "\"" + " ".join(processed_flow_settings['target_libraries']) + "\""
  processed_flow_settings["link_library"] = "\"" + "* $target_library" + "\""
  #formatting all paths to files to expand them to user space
  for flow_key, flow_val in list(processed_flow_settings.items()):
    if("folder" in flow_key):
      processed_flow_settings[flow_key] = os.path.expanduser(flow_val)

  #formatting process specific params
  processed_flow_settings["lef_files"] = "\"" + " ".join(processed_flow_settings['lef_files']) + "\""
  processed_flow_settings["best_case_libs"] = "\"" + " ".join(processed_flow_settings['best_case_libs']) + "\""
  processed_flow_settings["standard_libs"] = "\"" + " ".join(processed_flow_settings['standard_libs']) + "\""
  processed_flow_settings["worst_case_libs"] = "\"" + " ".join(processed_flow_settings['worst_case_libs']) + "\""
  processed_flow_settings["primetime_libs"] = "\"" + " ".join(processed_flow_settings['primetime_libs']) + "\""

  if(processed_flow_settings["partition_flag"]):
    processed_flow_settings["ptn_params"]["top_settings"]["scaling_array"] = [float(scale) for scale in processed_flow_settings["ptn_params"]["top_settings"]["scaling_array"]]
    processed_flow_settings["ptn_params"]["top_settings"]["fp_init_dims"] = [float(dim) for dim in processed_flow_settings["ptn_params"]["top_settings"]["fp_init_dims"]]

    for ptn_dict in processed_flow_settings["ptn_params"]["partitions"]:
      ptn_dict["fp_coords"] = [float(coord) for coord in ptn_dict["fp_coords"]]

    processed_flow_settings["parallel_hardblock_folder"] = os.path.expanduser(processed_flow_settings["parallel_hardblock_folder"])
  
  #Result parsing
  if(processed_flow_settings["condensed_results_folder"] != ""):
    processed_flow_settings["condensed_results_folder"] = os.path.expanduser(processed_flow_settings["condensed_results_folder"])

#   _____   ___  _ _____ _  _ ___ ___ ___ ___ 
#  / __\ \ / / \| |_   _| || | __/ __|_ _/ __|
#  \__ \\ V /| .` | | | | __ | _|\__ \| |\__ \
#  |___/ |_| |_|\_| |_| |_||_|___|___/___|___/

def check_synth_run(flow_settings,syn_report_path):
  """
  This function checks to make sure synthesis ran properly
  """
  # Make sure it worked properly
  # Open the timing report and make sure the critical path is non-zero:
  check_file = open(os.path.join(syn_report_path,"check.rpt"), "r")
  for line in check_file:
    if "Error" in line:
      print("Your design has errors. Refer to check.rpt in synthesis directory")
      sys.exit(-1)
    elif "Warning" in line and flow_settings['show_warnings']:
      print("Your design has warnings. Refer to check.rpt in synthesis directory")
      print("In spite of the warning, the rest of the flow will continue to execute.")
  check_file.close()


def copy_syn_outputs(flow_settings,clock_period,wire_selection,syn_report_path,only_reports=True):
  """
  During serial operation of the hardblock flow this function will copy the outputs of synthesis to a new param specific directory, if one only wants reports that is an option
  """
  synth_report_str = flow_settings["top_level"] + "_period_" + clock_period + "_" + "wiremdl_" + wire_selection
  report_dest_str = os.path.join(flow_settings['synth_folder'],synth_report_str + "_reports")
  mkdir_cmd_str = "mkdir -p " + report_dest_str
  copy_rep_cmd_str = "cp " + os.path.join(syn_report_path,"*") + " " + report_dest_str if not only_reports else "cp " + os.path.join(syn_report_path,"*.rpt ") + report_dest_str
  copy_logs_cmd_str = "cp " + "dc.log "+ "dc_script.tcl " + report_dest_str
  sp.call(mkdir_cmd_str,shell=True)
  sp.call(copy_rep_cmd_str,shell=True)
  sp.call(copy_logs_cmd_str,shell=True)
  sp.call('rm -f dc.log dc_script.tcl',shell=True)
  return synth_report_str


def get_dc_cmd(script_path):
  syn_shell = "dc_shell-t"
  return " ".join([syn_shell,"-f",script_path," > dc.log"])

def write_synth_tcl(flow_settings,clock_period,wire_selection,rel_outputs=False):
  """
  Writes the dc_script.tcl file which will be executed to run synthesis using Synopsys Design Compiler, tested under 2017 version.
  Relative output parameter is to accomodate legacy use of function while allowing the new version to run many scripts in parallel
  """
  report_path = flow_settings['synth_folder'] if (not rel_outputs) else os.path.join("..","reports")
  output_path = flow_settings['synth_folder'] if (not rel_outputs) else os.path.join("..","outputs")
  report_path = os.path.abspath(report_path)
  output_path = os.path.abspath(output_path)

  #Below lines could be done in the preprocessing function
  #create var named my_files of a list of design files
  if len(flow_settings["design_files"]) == 1:
    design_files_str = "set my_files " + flow_settings["design_files"][0]
  else:
    design_files_str = "set my_files [list " + " ".join([ent for ent in flow_settings["design_files"] if (ent != "parameters.v" and ent  != "c_functions.v") ]) + " ]"
  #analyze design files based on RTL lang
  if flow_settings['design_language'] == 'verilog':
    analyze_cmd_str = "analyze -f verilog $my_files"
  elif flow_settings['design_language'] == 'vhdl':
    analyze_cmd_str = "analyze -f vhdl $my_files"
  else:
    analyze_cmd_str = "analyze -f sverilog $my_files"

  #If wire_selection is None, then no wireload model is used during synthesis. This does imply results 
  #are not as accurate (wires don't have any delay and area), but is useful to let the flow work/proceed 
  #if the std cell library is missing wireload models.
  if wire_selection != "None":
    wire_ld_sel_str = "set_wire_load_selection " + wire_selection
  else:
    wire_ld_sel_str = "#No WIRE LOAD MODEL SELECTED, RESULTS NOT AS ACCURATE"

  if flow_settings['read_saif_file']:
    sw_activity_str = "read_saif saif.saif"
  else:
    sw_activity_str = "set_switching_activity -static_probability " + str(flow_settings['static_probability']) + " -toggle_rate " + str(flow_settings['toggle_rate']) + " -base_clock $my_clock_pin -type inputs"

  #Ungrouping settings command
  if flow_settings["ungroup_regex"] != "":
    set_ungroup_cmd = "set_attribute [get_cells -regex " + "\"" + flow_settings["ungroup_regex"] + "\"" + "] ungroup false" #this will ungroup all blocks
  else:
    set_ungroup_cmd = "# NO UNGROUPING SETTINGS APPLIED, MODULES WILL BE FLATTENED ACCORDING TO DC"
    
  synthesized_fname = "synthesized"
  file_lines = [
    #This line sets the naming convention of DC to not add parameters to module insts
    "set template_parameter_style \"\"",
    "set template_naming_style \"%s\"",
    "set search_path " + flow_settings["search_path"],
    design_files_str,
    "set my_top_level " + flow_settings['top_level'],
    "set my_clock_pin " + flow_settings['clock_pin_name'],
    "set target_library " + flow_settings["target_library"],
    "set link_library " + flow_settings["link_library"],
    "set power_analysis_mode \"averaged\"",
    "define_design_lib WORK -path ./WORK",
    analyze_cmd_str,
    "elaborate $my_top_level",
    "current_design $my_top_level",
    "check_design > " +                             os.path.join(report_path,"check_precompile.rpt"),
    "link",
    "uniquify",
    wire_ld_sel_str,
    "set my_period " + str(clock_period),
    "set find_clock [ find port [list $my_clock_pin] ]",
    "if { $find_clock != [list] } { ",
    "set clk_name $my_clock_pin ",
    "create_clock -period $my_period $clk_name}",
    set_ungroup_cmd,
    # "set_app_var compile_ultra_ungroup_dw false",
    # "set_app_var compile_seqmap_propagate_constants false",
    "compile_ultra", #-no_autoungroup",
    "check_design >  " +                            os.path.join(report_path,"check.rpt"),
    "write -format verilog -hierarchy -output " +   os.path.join(output_path,synthesized_fname+"_hier.v"),
    "write_file -format ddc -hierarchy -output " +  os.path.join(output_path,flow_settings['top_level'] + ".ddc"),
    sw_activity_str,
    "ungroup -all -flatten ",
    "report_power > " +                             os.path.join(report_path,"power.rpt"),
    "report_area -nosplit -hierarchy > " +          os.path.join(report_path,"area.rpt"),
    "report_resources -nosplit -hierarchy > " +     os.path.join(report_path,"resources.rpt"),
    "report_design > " +                            os.path.join(report_path,"design.rpt"),
    "all_registers > " +                            os.path.join(report_path,"registers.rpt"),
    "report_timing -delay max > " +                 os.path.join(report_path,"setup_timing.rpt"),
    "report_timing -delay min > " +                 os.path.join(report_path,"hold_timing.rpt"),
    "change_names -hier -rule verilog ",    
    "write -f verilog -output " +                   os.path.join(output_path,synthesized_fname+"_flat.v"),
    "write_sdf " +                                  os.path.join(output_path,synthesized_fname+".sdf"),
    "write_parasitics -output " +                   os.path.join(output_path,synthesized_fname+".spef"),
    "write_sdc " +                                  os.path.join(output_path,synthesized_fname+".sdc")
  ]
  fd = open("dc_script.tcl","w")
  for line in file_lines:
    file_write_ln(fd,line)
  file_write_ln(fd,"quit")
  fd.close()
  return report_path,output_path


def run_synth(flow_settings,clock_period,wire_selection):
  """"
  runs the synthesis flow for specific clock period and wireload model
  Prereqs: flow_settings_pre_process() function to properly format params for scripts
  """
  syn_report_path, syn_output_path = write_synth_tcl(flow_settings,clock_period,wire_selection)
  # Run the script in design compiler shell
  synth_run_cmd = "dc_shell-t -f " + "dc_script.tcl" + " | tee dc.log"
  run_shell_cmd_no_logs(synth_run_cmd)
  # clean after DC!
  sp.call('rm -rf command.log', shell=True)
  sp.call('rm -rf default.svf', shell=True)
  sp.call('rm -rf filenames.log', shell=True)

  check_synth_run(flow_settings,syn_report_path)

  #Copy synthesis results to a unique dir in synth dir
  synth_report_str = copy_syn_outputs(flow_settings,clock_period,wire_selection,syn_report_path)
  #if the user doesn't want to perform place and route, extract the results from DC reports and end
  if flow_settings['synthesis_only']:
    # read total area from the report file:
    file = open(flow_settings['synth_folder'] + "/area.rpt" ,"r")
    for line in file:
      if line.startswith('Total cell area:'):
        total_area = re.findall(r'\d+\.{0,1}\d*', line)
    file.close()
    # Read timing parameters
    file = open(flow_settings['synth_folder'] + "/timing.rpt" ,"r")
    for line in file:
      if 'library setup time' in line:
        library_setup_time = re.findall(r'\d+\.{0,1}\d*', line)
      if 'data arrival time' in line:
        data_arrival_time = re.findall(r'\d+\.{0,1}\d*', line)
    try:
      total_delay =  float(library_setup_time[0]) + float(data_arrival_time[0])
    except NameError:
      total_delay =  float(data_arrival_time[0])
    file.close()    
    # Read dynamic power
    file = open(flow_settings['synth_folder'] + "/power.rpt" ,"r")
    for line in file:
      if 'Total Dynamic Power' in line:
        total_dynamic_power = re.findall(r'\d+\.\d*', line)
        total_dynamic_power[0] = float(total_dynamic_power[0])
        if 'mW' in line:
          total_dynamic_power[0] *= 0.001
        elif 'uw' in line:
          total_dynamic_power[0] *= 0.000001
        else:
          total_dynamic_power[0] = 0
    file.close()
    # write the final report file:
    file = open("report.txt" ,"w")
    file.write("total area = "  + str(total_area[0]) +  "\n")
    file.write("total delay = " + str(total_delay) + " ns\n")
    file.write("total power = " + str(total_dynamic_power[0]) + " W\n")
    file.close()
    #return
  return synth_report_str,syn_output_path

#   ___ _      _   ___ ___   _  _   ___  ___  _   _ _____ ___ 
#  | _ \ |    /_\ / __| __| | \| | | _ \/ _ \| | | |_   _| __|
#  |  _/ |__ / _ \ (__| _|  | .` | |   / (_) | |_| | | | | _| 
#  |_| |____/_/ \_\___|___| |_|\_| |_|_\\___/ \___/  |_| |___|


########################################## PNR GENERIC SCRIPTS ##########################################

def write_innovus_view_file(flow_settings,syn_output_path):
  """Write .view file for innovus place and route, this is used for for creating the delay corners from timing libs and importings constraints"""
  fname = flow_settings["top_level"]+".view"

  file_lines = [
    "# Version:1.0 MMMC View Definition File\n# Do Not Remove Above Line",
    #I created a typical delay corner but I don't think its being used as its not called in create_analysis_view command, however, may be useful? not sure but its here
    #One could put RC values (maybe temperature in here) later for now they will all be the same
    "create_rc_corner -name RC_BEST -preRoute_res {1.0} -preRoute_cap {1.0} -preRoute_clkres {0.0} -preRoute_clkcap {0.0} -postRoute_res {1.0} -postRoute_cap {1.0} -postRoute_xcap {1.0} -postRoute_clkres {0.0} -postRoute_clkcap {0.0}",
    "create_rc_corner -name RC_TYP -preRoute_res {1.0} -preRoute_cap {1.0} -preRoute_clkres {0.0} -preRoute_clkcap {0.0} -postRoute_res {1.0} -postRoute_cap {1.0} -postRoute_xcap {1.0} -postRoute_clkres {0.0} -postRoute_clkcap {0.0}",
    "create_rc_corner -name RC_WORST -preRoute_res {1.0} -preRoute_cap {1.0} -preRoute_clkres {0.0} -preRoute_clkcap {0.0} -postRoute_res {1.0} -postRoute_cap {1.0} -postRoute_xcap {1.0} -postRoute_clkres {0.0} -postRoute_clkcap {0.0}",
    #create libraries for each timing corner
    "create_library_set -name MIN_TIMING -timing {" + flow_settings["best_case_libs"] + "}",
    "create_library_set -name TYP_TIMING -timing {" + flow_settings["standard_libs"] + "}",
    "create_library_set -name MAX_TIMING -timing {" + flow_settings["worst_case_libs"] + "}",
    #import constraints from synthesis generated sdc
    "create_constraint_mode -name CONSTRAINTS -sdc_files {" + os.path.join(syn_output_path,"synthesized.sdc") + "}" ,
    "create_delay_corner -name MIN_DELAY -library_set {MIN_TIMING} -rc_corner {RC_BEST}",
    "create_delay_corner -name TYP_DELAY -library_set {TYP_TIMING} -rc_corner {RC_TYP}",
    "create_delay_corner -name MAX_DELAY -library_set {MAX_TIMING} -rc_corner {RC_WORST}",
    "create_analysis_view -name BEST_CASE -constraint_mode {CONSTRAINTS} -delay_corner {MIN_DELAY}",
    "create_analysis_view -name TYP_CASE -constraint_mode {CONSTRAINTS} -delay_corner {TYP_DELAY}",
    "create_analysis_view -name WORST_CASE -constraint_mode {CONSTRAINTS} -delay_corner {MAX_DELAY}",
    #This sets our analysis view to be using our worst case analysis view for setup and best for timing,
    #This makes sense as the BC libs would have the most severe hold violations and vice versa for setup 
    "set_analysis_view -setup {WORST_CASE} -hold {BEST_CASE}"
  ]
  fd = open(fname,"w")
  for line in file_lines:
    file_write_ln(fd,line)
  fd.close()
  view_abs_path = os.path.join(os.getcwd(),fname)
  return view_abs_path 

def write_innovus_init_script(flow_settings,view_fpath,syn_output_path):
  """
  This function generates init script which sets variables used in pnr,
  The contents of this file were generated from using the innovus GUI
  setting relavent files/nets graphically and exporting the .globals file
  """
  if(flow_settings["partition_flag"]):
    init_verilog_cmd = "set init_verilog " + os.path.join(syn_output_path,"synthesized_hier.v")
  else:
    init_verilog_cmd = "set init_verilog " + os.path.join(syn_output_path,"synthesized_flat.v")

  flow_settings["lef_files"] = flow_settings["lef_files"].strip("\"")
  fname = flow_settings["top_level"]+"_innovus_init.tcl"
  file = open(fname,"w")
  file_lines = [
    "set_global _enable_mmmc_by_default_flow      $CTE::mmmc_default",
    "suppressMessage ENCEXT-2799",
    "set ::TimeLib::tsgMarkCellLatchConstructFlag 1",
    "set conf_qxconf_file NULL",
    "set conf_qxlib_file NULL",
    "set dbgDualViewAwareXTree 1",
    "set defHierChar /",
    "set distributed_client_message_echo 1",
    "set distributed_mmmc_disable_reports_auto_redirection 0",
    #The below config file comes from the INNOVUS directory, if not using an x86 system this will probably break
    "set dlgflprecConfigFile " + os.path.join(flow_settings["EDI_HOME"],"tools.lnx86/dlApp/run_flprec.cfg"),
    "set enable_ilm_dual_view_gui_and_attribute 1",
    "set enc_enable_print_mode_command_reset_options 1",
    "set init_design_settop 0",
    "set init_gnd_net " + flow_settings["gnd_net"],
    #/CMC/kits/tsmc_65nm_libs/tcbn65gplus/TSMCHOME/digital/Back_End/lef/tcbn65gplus_200a/lef/tcbn65gplus_9lmT2.lef /CMC/kits/tsmc_65nm_libs/tpzn65gpgv2/TSMCHOME/digital/Back_End/lef/tpzn65gpgv2_140c/mt_2/9lm/lef/antenna_9lm.lef /CMC/kits/tsmc_65nm_libs/tpzn65gpgv2/TSMCHOME/digital/Back_End/lef/tpzn65gpgv2_140c/mt_2/9lm/lef/tpzn65gpgv2_9lm.lef
    "set init_lef_file {" + flow_settings["lef_files"]  + "}",
    "set init_mmmc_file {" + view_fpath + "}",
    "set init_pwr_net " + flow_settings["pwr_net"],
    "set init_top_cell " + flow_settings["top_level"],
    #"set init_verilog " + os.path.join(syn_output_path,"synthesized_hier.v"),
    init_verilog_cmd,
    "get_message -id GLOBAL-100 -suppress",
    "get_message -id GLOBAL-100 -suppress",
    "set latch_time_borrow_mode max_borrow",
    "set pegDefaultResScaleFactor 1",
    "set pegDetailResScaleFactor 1",
    "set pegEnableDualViewForTQuantus 1",
    "get_message -id GLOBAL-100 -suppress",
    "get_message -id GLOBAL-100 -suppress",
    "set report_inactive_arcs_format {from to when arc_type sense reason}",
    "set spgUnflattenIlmInCheckPlace 2",
    "get_message -id GLOBAL-100 -suppress",
    "get_message -id GLOBAL-100 -suppress",
    "set timing_remove_data_path_pessimism_min_slack_threshold -1.70141e+38",
    "set defStreamOutCheckUncolored false",
    "set init_verilog_tolerate_port_mismatch 0",
    "set load_netlist_ignore_undefined_cell 1",
    "setDesignMode -process " + flow_settings["process_size"],
    "init_design"
  ]
  for line in file_lines:
    file_write_ln(file,line)
  file.close()
  init_script_abs_path = os.path.join(os.getcwd(),fname)
  return init_script_abs_path
  

def write_innovus_script(flow_settings,metal_layer,core_utilization,init_script_fname,rel_outputs=False,cts_flag=False):
  """
  This function writes the innvous script which actually performs place and route.
  Precondition to this script is the creation of an initialization script which is sourced on the first line.
  """

  report_path = flow_settings['pr_folder'] if (not rel_outputs) else os.path.join("..","reports")
  output_path = flow_settings['pr_folder'] if (not rel_outputs) else os.path.join("..","outputs")
  
  report_path = os.path.abspath(report_path)
  output_path = os.path.abspath(output_path)

  #some format adjustment (could move to preproc function)
  core_utilization = str(core_utilization)
  metal_layer = str(metal_layer)
  flow_settings["power_ring_spacing"] = str(flow_settings["power_ring_spacing"])

  #filename
  fname = flow_settings["top_level"] + "_innovus.tcl"
  
  #cts commands
  if cts_flag: 
    cts_cmds = [
      "create_ccopt_clock_tree_spec",
      "ccopt_design",
      "timeDesign -postCTS -prefix postCTSpreOpt -outDir " + os.path.join(report_path,"timeDesignPostCTSReports"),
      "optDesign -postCTS -prefix postCTSOpt -outDir " + os.path.join(report_path,"optDesignPostCTSReports"),
      "timeDesign -postCTS -prefix postCTSpostOpt -outDir " + os.path.join(report_path,"timeDesignPostCTSReports")
    ]
  else:
    cts_cmds = ["#CTS NOT PERFORMED"]
  
  #If the user specified a layer mapping file, then use that. Otherwise, just let the tool create a default one.
  if flow_settings['map_file'] != "None":
    stream_out_cmd = "streamOut " +  os.path.join(output_path,"final.gds2") + " -mapFile " + flow_settings["map_file"] + " -stripes 1 -units 1000 -mode ALL"
  else:
    stream_out_cmd = "streamOut " +  os.path.join(output_path,"final.gds2") + " -stripes 1 -units 1000 -mode ALL"

  metal_layer_bottom = flow_settings["metal_layer_names"][0]
  metal_layer_second = flow_settings["metal_layer_names"][1]
  metal_layer_top = flow_settings["metal_layer_names"][int(metal_layer)-1]
  power_ring_metal_top = flow_settings["power_ring_metal_layer_names"][0] 
  power_ring_metal_bottom = flow_settings["power_ring_metal_layer_names"][1] 
  power_ring_metal_left = flow_settings["power_ring_metal_layer_names"][2] 
  power_ring_metal_right = flow_settings["power_ring_metal_layer_names"][3] 


  file_lines = [
    "source " + init_script_fname,
    "setDesignMode -process " + flow_settings["process_size"],
    "floorPlan -site " +
    " ".join([flow_settings["core_site_name"],
    "-r",flow_settings["height_to_width_ratio"],core_utilization,
    flow_settings["space_around_core"],
    flow_settings["space_around_core"],
    flow_settings["space_around_core"],
    flow_settings["space_around_core"]]),
    "setDesignMode -topRoutingLayer " + metal_layer,
    "fit",
    #Add Power Rings
    " ".join(["addRing", "-type core_rings","-nets","{" + " ".join([flow_settings["pwr_net"],flow_settings["gnd_net"]]) + "}",
      "-layer {" + " ".join(["top",metal_layer_bottom,"bottom",metal_layer_bottom,"left",metal_layer_second,"right",metal_layer_second]) + "}",
      "-width", flow_settings["power_ring_width"],
      "-spacing", flow_settings["power_ring_spacing"],
      "-offset", flow_settings["power_ring_width"],
      "-follow io"]),
    #Global net connections
    "clearGlobalNets",
    "globalNetConnect " + flow_settings["gnd_pin"] + " -type pgpin -pin " + flow_settings["gnd_pin"] + " -inst {}",
    "globalNetConnect " + flow_settings["pwr_pin"] + " -type pgpin -pin " + flow_settings["pwr_pin"] + " -inst {}",
    "globalNetConnect " + flow_settings["gnd_net"] + " -type net -net  " + flow_settings["gnd_net"],
    "globalNetConnect " + flow_settings["pwr_net"] + " -type net -net  " + flow_settings["pwr_net"],
    "globalNetConnect " + flow_settings["pwr_pin"] + " -type pgpin -pin  " + flow_settings["pwr_pin"] + " -inst *",
    "globalNetConnect " + flow_settings["gnd_pin"] + " -type pgpin -pin  " + flow_settings["gnd_pin"] + " -inst *",
    "globalNetConnect " + flow_settings["pwr_pin"] + " -type tiehi -inst *",
    "globalNetConnect " + flow_settings["gnd_pin"] + " -type tielo -inst *",
    #special routing for horizontal VDD VSS connections
    "sroute -connect { blockPin padPin padRing corePin floatingStripe } -layerChangeRange { "+ " ".join([metal_layer_bottom,metal_layer_top]) + " }"\
     + " -blockPinTarget { nearestRingStripe nearestTarget } -padPinPortConnect { allPort oneGeom } -checkAlignedSecondaryPin 1 -blockPin useLef -allowJogging 1"\
     + " -crossoverViaBottomLayer " + metal_layer_bottom + " -targetViaBottomLayer " + metal_layer_bottom + " -allowLayerChange 1"\
     + " -targetViaTopLayer " + metal_layer_top + " -crossoverViaTopLayer " + metal_layer_top + " -nets {" + " ".join([flow_settings["gnd_net"],flow_settings["pwr_net"]]) +  "}",
    #perform initial placement with IOs
    "setPlaceMode -fp false -place_global_place_io_pins true",
    "place_design -noPrePlaceOpt",
    "earlyGlobalRoute",
    "timeDesign -preCTS -idealClock -numPaths 10 -prefix preCTSpreOpt -outDir " + os.path.join(report_path,"timeDesignpreCTSReports"),
    "optDesign -preCTS -outDir " + os.path.join(report_path,"optDesignpreCTSReports"),
    "timeDesign -preCTS -idealClock -numPaths 10 -prefix preCTSpostOpt -outDir " + os.path.join(report_path,"timeDesignpreCTSReports"),
    "addFiller -cell {" +  " ".join(flow_settings["filler_cell_names"]) + "} -prefix FILL -merge true",
    # If cts flag is set perform clock tree synthesis and post cts optimization
    cts_cmds,
    
    #perform routing
    "setNanoRouteMode -quiet -routeWithTimingDriven 1",
    "setNanoRouteMode -quiet -routeWithSiDriven 1",
    "setNanoRouteMode -quiet -routeTopRoutingLayer " + metal_layer,
    "setNanoRouteMode -quiet -routeBottomRoutingLayer 1",
    "setNanoRouteMode -quiet -drouteEndIteration 1",
    "setNanoRouteMode -quiet -routeWithTimingDriven true",
    "setNanoRouteMode -quiet -routeWithSiDriven true",
    "routeDesign -globalDetail",
    "setExtractRCMode -engine postRoute",
    "extractRC",
    "buildTimingGraph",
    "setAnalysisMode -analysisType onChipVariation -cppr both",
    "timeDesign -postRoute -prefix postRoutePreOpt -outDir " +  os.path.join(report_path,"timeDesignPostRouteReports"),
    "optDesign -postRoute -prefix postRouteOpt -outDir " +  os.path.join(report_path,"optDesignPostRouteReports"),
    "timeDesign -postRoute -prefix postRoutePostOpt -outDir " +  os.path.join(report_path,"timeDesignPostRouteReports"),
    #output reports
    "report_qor -file " + os.path.join(report_path,"qor.rpt"),
    "verify_drc -report " + os.path.join(report_path,"geom.rpt"),
    "verifyConnectivity -type all -report " + os.path.join(report_path,"conn.rpt"),
    "report_timing > " + os.path.join(report_path,"setup_timing.rpt"),
    "setAnalysisMode -checkType hold",
    "report_timing > " + os.path.join(report_path,"hold_timing.rpt"),
    "report_power > " + os.path.join(report_path,"power.rpt"),
    "report_constraint -all_violators > " + os.path.join(report_path,"violators.rpt"),
    "report_area > " + os.path.join(report_path,"area.rpt"),
    "summaryReport -outFile " + os.path.join(report_path,"pr_report.txt"),
    #output design files
    "saveNetlist " + os.path.join(output_path,"netlist.v"),
    "saveDesign " +  os.path.join(output_path,"design.enc"),
    "rcOut -spef " +  os.path.join(output_path,"spef.spef"),
    "write_sdf -ideal_clock_network " + os.path.join(output_path,"sdf.sdf"),
    stream_out_cmd
  ]
  #flatten list
  file_lines = flatten_mixed_list(file_lines)
  file = open(fname,"w")
  for line in file_lines:
    file_write_ln(file,line)
  file_write_ln(file,"exit")
  file.close()
  
  return fname,output_path

def write_enc_script(flow_settings,metal_layer,core_utilization):
  """
  Writes script for place and route using cadence encounter (tested under 2009 version)
  """
  # generate the EDI (encounter) configuration
  file = open("edi.conf", "w")
  file.write("global rda_Input \n")
  file.write("set cwd .\n\n")
  file.write("set rda_Input(ui_leffile) " + flow_settings['lef_files'] + "\n")
  file.write("set rda_Input(ui_timelib,min) " + flow_settings['best_case_libs'] + "\n")
  file.write("set rda_Input(ui_timelib) " + flow_settings['standard_libs'] + "\n")
  file.write("set rda_Input(ui_timelib,max) " + flow_settings['worst_case_libs'] + "\n")
  file.write("set rda_Input(ui_netlist) " + os.path.expanduser(flow_settings['synth_folder']) + "/synthesized.v" + "\n")
  file.write("set rda_Input(ui_netlisttype) {Verilog} \n")
  file.write("set rda_Input(import_mode) {-treatUndefinedCellAsBbox 0 -keepEmptyModule 1}\n")
  file.write("set rda_Input(ui_timingcon_file) " + os.path.expanduser(flow_settings['synth_folder']) + "/synthesized.sdc" + "\n")
  file.write("set rda_Input(ui_topcell) " + flow_settings['top_level'] + "\n\n")
  gnd_pin = flow_settings['gnd_pin']
  gnd_net = flow_settings['gnd_net']
  pwr_pin = flow_settings['pwr_pin']
  pwr_net = flow_settings['pwr_net']
  file.write("set rda_Input(ui_gndnet) {" + gnd_net + "} \n")
  file.write("set rda_Input(ui_pwrnet) {" + pwr_net + "} \n")
  if flow_settings['tilehi_tielo_cells_between_power_gnd'] is True:
    file.write("set rda_Input(ui_pg_connections) [list {PIN:" + gnd_pin + ":}" + " {TIEL::} " + "{NET:" + gnd_net + ":} {NET:" + pwr_net + ":}" + " {TIEH::} " + "{PIN:" + pwr_pin + ":} ] \n")
  else:
    file.write("set rda_Input(ui_pg_connections) [list {PIN:" + gnd_pin + ":} {NET:" + gnd_net + ":} {NET:" + pwr_net + ":} {PIN:" + pwr_pin + ":} ] \n")
  file.write("set rda_Input(PIN:" + gnd_pin + ":) {" + gnd_pin + "} \n")
  file.write("set rda_Input(TIEL::) {" + gnd_pin + "} \n")
  file.write("set rda_Input(NET:" + gnd_net + ":) {" + gnd_net + "} \n")
  file.write("set rda_Input(PIN:" + pwr_pin + ":) {" + pwr_pin + "} \n")
  file.write("set rda_Input(TIEH::) {" + pwr_pin + "} \n")
  file.write("set rda_Input(NET:" + pwr_net + ":) {" + pwr_net + "} \n\n")
  if (flow_settings['inv_footprint'] != "None"):
    file.write("set rda_Input(ui_inv_footprint) {" + flow_settings['inv_footprint'] + "}\n")
  if (flow_settings['buf_footprint'] != "None"):
    file.write("set rda_Input(ui_buf_footprint) {" + flow_settings['buf_footprint'] + "}\n")
  if (flow_settings['delay_footprint'] != "None"):
    file.write("set rda_Input(ui_delay_footprint) {" + flow_settings['delay_footprint'] + "}\n")
  file.close()
  metal_layer_bottom = flow_settings["metal_layer_names"][0]
  metal_layer_second = flow_settings["metal_layer_names"][1]
  metal_layer_top = flow_settings["metal_layer_names"][int(metal_layer)-1]
  power_ring_metal_top = flow_settings["power_ring_metal_layer_names"][0] 
  power_ring_metal_bottom = flow_settings["power_ring_metal_layer_names"][1] 
  power_ring_metal_left = flow_settings["power_ring_metal_layer_names"][2] 
  power_ring_metal_right = flow_settings["power_ring_metal_layer_names"][3] 
  # generate the EDI (encounter) script
  file = open("edi.tcl", "w")
  file.write("loadConfig edi.conf \n")
  file.write("floorPlan -site " + flow_settings['core_site_name'] \
              + " -r " + str(flow_settings['height_to_width_ratio']) \
              + " " + str(core_utilization) \
              + " " + str(flow_settings['space_around_core']) \
              + " " + str(flow_settings['space_around_core']) + " ")
  file.write(str(flow_settings['space_around_core']) + " " + str(flow_settings['space_around_core']) + "\n")
  file.write("setMaxRouteLayer " + str(metal_layer) + " \n")
  file.write("fit \n")
  file.write("addRing -spacing_bottom " + str(flow_settings['power_ring_spacing']) \
              + " -spacing_right " + str(flow_settings['power_ring_spacing']) \
              + " -spacing_top " + str(flow_settings['power_ring_spacing']) \
              + " -spacing_left " + str(flow_settings['power_ring_spacing']) \
              + " -width_right " + str(flow_settings['power_ring_width']) \
              + " -width_left " + str(flow_settings['power_ring_width']) \
              + " -width_bottom " + str(flow_settings['power_ring_width']) \
              + " -width_top " + str(flow_settings['power_ring_width']) \
              + " -center 1" \
              + " -around core" \
              + " -layer_top " + power_ring_metal_top \
              + " -layer_bottom " + power_ring_metal_bottom \
              + " -layer_left " + power_ring_metal_left \
              + " -layer_right " + power_ring_metal_right \
              + " -nets { " + gnd_net + " " + pwr_net + " }" \
              + " -stacked_via_top_layer "+ metal_layer_top \
              + " -stacked_via_bottom_layer " + metal_layer_bottom + " \n")
  file.write("setPlaceMode -fp false -maxRouteLayer " + str(metal_layer) + "\n")
  file.write("placeDesign -inPlaceOpt -noPrePlaceOpt \n")
  file.write("checkPlace " + flow_settings['top_level'] +" \n")
  file.write("trialroute \n")
  file.write("buildTimingGraph \n")
  file.write("timeDesign -preCTS -idealClock -numPaths 10 -prefix preCTS -outDir " + os.path.expanduser(flow_settings['pr_folder']) + "/timeDesignpreCTSReports" + "\n")
  file.write("optDesign -preCTS -outDir " + os.path.expanduser(flow_settings['pr_folder']) + "/optDesignpreCTSReports" + "\n")
  # I won't do a CTS anyway as the blocks are small.
  file.write("addFiller -cell {" + " ".join([str(item) for item in flow_settings['filler_cell_names']]) + "} -prefix FILL -merge true \n")  
  file.write("clearGlobalNets \n")
  file.write("globalNetConnect " + gnd_net + " -type pgpin -pin " + gnd_pin + " -inst {} \n")
  file.write("globalNetConnect " + pwr_net + " -type pgpin -pin " + pwr_pin + " -inst {} \n")
  file.write("globalNetConnect " + gnd_net + " -type net -net " + gnd_net + " \n")
  file.write("globalNetConnect " + pwr_net + " -type net -net " + pwr_net + " \n")
  file.write("globalNetConnect " + pwr_net + " -type pgpin -pin " + pwr_pin + " -inst * \n")
  file.write("globalNetConnect " + gnd_net + " -type pgpin -pin " + gnd_pin + " -inst * \n")
  file.write("globalNetConnect " + pwr_net + " -type tiehi -inst * \n")
  file.write("globalNetConnect " + gnd_net + " -type tielo -inst * \n")
  file.write("sroute -connect { blockPin padPin padRing corePin floatingStripe }" \
              + " -layerChangeRange { " + metal_layer_bottom + " " + metal_layer_top + " }" \
              + " -blockPinTarget { nearestRingStripe nearestTarget }" \
              + " -padPinPortConnect { allPort oneGeom }" \
              + " -checkAlignedSecondaryPin 1" \
              + " -blockPin useLef" \
              + " -allowJogging 1" \
              + " -crossoverViaBottomLayer " + metal_layer_bottom \
              + " -allowLayerChange 1" \
              + " -targetViaTopLayer " + metal_layer_top \
              + " -crossoverViaTopLayer " + metal_layer_top \
              + " -targetViaBottomLayer " + metal_layer_bottom \
              + " -nets { " + gnd_net + " " + pwr_net + " } \n")
  file.write("routeDesign -globalDetail\n")
  file.write("setExtractRCMode -engine postRoute \n")
  file.write("extractRC \n")
  file.write("buildTimingGraph \n")
  file.write("timeDesign -postRoute -outDir " + os.path.expanduser(flow_settings['pr_folder']) + "/timeDesignReports" + "\n")
  file.write("optDesign -postRoute -outDir " + os.path.expanduser(flow_settings['pr_folder']) + "/optDesignReports" + "\n")
  #by default, violations are reported in designname.geom.rpt
  file.write("verifyGeometry -report " + (os.path.expanduser(flow_settings['pr_folder']) + "/" + flow_settings['top_level'] + ".geom.rpt") + "\n")
  #by default, violations are reported in designname.conn.rpt
  file.write("verifyConnectivity -type all -report " + (os.path.expanduser(flow_settings['pr_folder']) + "/" + flow_settings['top_level'] + ".conn.rpt") + "\n")
  # report area
  file.write("summaryReport -outFile " + os.path.expanduser(flow_settings['pr_folder']) + "/pr_report.txt \n")
  # save design
  file.write(r'saveNetlist ' + os.path.expanduser(flow_settings['pr_folder']) + r'/netlist.v' + "\n")
  file.write(r'saveDesign ' + os.path.expanduser(flow_settings['pr_folder']) + r'/design.enc' + " \n")
  file.write(r'rcOut -spef ' + os.path.expanduser(flow_settings['pr_folder']) + r'/spef.spef' + " \n")
  file.write(r'write_sdf -ideal_clock_network ' + os.path.expanduser(flow_settings['pr_folder']) + r'/sdf.sdf' + " \n")
  #If the user specified a layer mapping file, then use that. Otherwise, just let the tool create a default one.
  if flow_settings['map_file'] != "None":
    file.write(r'streamOut ' + os.path.expanduser(flow_settings['pr_folder']) + r'/final.gds2' + ' -mapFile ' + flow_settings['map_file'] + ' -stripes 1 -units 1000 -mode ALL' + "\n")
  else:
    file.write(r'streamOut ' + os.path.expanduser(flow_settings['pr_folder']) + r'/final.gds2' + ' -stripes 1 -units 1000 -mode ALL' + "\n")
  file.write("exit \n")
  file.close()
########################################## PNR GENERIC SCRIPTS ##########################################

########################################## PNR PARTITION SCRIPTS ##########################################

def write_edit_port_script_pre_ptn(flow_settings):
  """
  Currently this only works for the NoC ports, in the future these would have to be autogenerated or generated in a more general way.
  This function generates and edits the pin locations for the NoC design based on (1) size of overall floorplan and (2) router partition location
  """
  # Below code was to be used to allow for general correlation of ports/pins based on topology of NoC, innovus commands useful so here they are
  # flow_settings["ptn_params"]["sep_ports_regex"] = "channel"
  # "set enc_tcl_return_display_limit 1000000" #set it to 10^6 why not just dont want to cut off stuff
  # "dbGet top.terms.name -regex "channel" #lets set this to grab input/output channels for now, <- this grabs all ports in the design matching regex
  #number of port groups on the NoC would need to be a param for the above to work (Ex. there should be 4 + 1 for 2D mesh)

  #Current hard params which will only work for the NoC design under current flow, I'd like to change this but I dont see a reason to bring this to the user as no other value would work (unless one parses the verilog and determines parameter values for router)
  rtr_mod_name = "vcr_top_1"

  #offset from start of line in which pins are being placed (Ex. if they are being placed on edge 1 cw the offset would be from NW corner towards NE)
  #grab fp coordinates for the router module
  rtr_fp_coords = [e["fp_coords"] for e in flow_settings["ptn_params"]["partitions"] if e["mod_name"] == rtr_mod_name][0]
  #extract height and width
  rtr_dims = [abs(float(rtr_fp_coords[0]) - float(rtr_fp_coords[2])),abs(float(rtr_fp_coords[1]) - float(rtr_fp_coords[3]))] # w,h
  #below values were tuned manually for reasonable pin placement w.r.t router dimensions
  #below offsets are where the channel in/out pins should be placed
  ch_in_offset = rtr_dims[0]/(10.0) + float(rtr_fp_coords[0]) #Assuming square for now just for ease, rtr side len 
  ch_out_offset = rtr_dims[1] - (rtr_dims[0]/(10.0))*3 + float(rtr_fp_coords[0]) #both offsets, doubled the subtraction as they are instantiated in same direction
  #one side of the NoC will have the equivilant of two channels representing the compute connections so we want to deal with these offsets independantly
  noc_comm_edge_offsets = [ch_in_offset - rtr_dims[0]/(20.0),ch_out_offset - rtr_dims[0]/5.0]  

  #The below port strings for the channel were taken from innovus by loading in the floorplan and using the below command:
  # > dbGet top.terms.name > my_output_file
  # I then divided them according to the topology of the NoC and bits/channel, in the future to make this general one could take the ports from dbGet command...
  # ...and divide thier indicies by the number of connections to other routers (Ex. total_channel_width/4 = 68 ports per in/out channel) 
  # I put other ports into variables but I'm only worrying about channel pin assignments, the rest will be done via pnr tool 
  fd = open("port_vars.tcl","w")
  file_lines = [
    #side 0
    "set my_0_ch_in_ports {\"channel_in_ip_d[0]\" \"channel_in_ip_d[1]\" \"channel_in_ip_d[2]\" \"channel_in_ip_d[3]\" \"channel_in_ip_d[4]\" \"channel_in_ip_d[5]\" \"channel_in_ip_d[6]\" \"channel_in_ip_d[7]\" \"channel_in_ip_d[8]\" \"channel_in_ip_d[9]\" \"channel_in_ip_d[10]\" \"channel_in_ip_d[11]\" \"channel_in_ip_d[12]\" \"channel_in_ip_d[13]\" \"channel_in_ip_d[14]\" \"channel_in_ip_d[15]\" \"channel_in_ip_d[16]\" \"channel_in_ip_d[17]\" \"channel_in_ip_d[18]\" \"channel_in_ip_d[19]\" \"channel_in_ip_d[20]\" \"channel_in_ip_d[21]\" \"channel_in_ip_d[22]\" \"channel_in_ip_d[23]\" \"channel_in_ip_d[24]\" \"channel_in_ip_d[25]\" \"channel_in_ip_d[26]\" \"channel_in_ip_d[27]\" \"channel_in_ip_d[28]\" \"channel_in_ip_d[29]\" \"channel_in_ip_d[30]\" \"channel_in_ip_d[31]\" \"channel_in_ip_d[32]\" \"channel_in_ip_d[33]\" \"channel_in_ip_d[34]\" \"channel_in_ip_d[35]\" \"channel_in_ip_d[36]\" \"channel_in_ip_d[37]\" \"channel_in_ip_d[38]\" \"channel_in_ip_d[39]\" \"channel_in_ip_d[40]\" \"channel_in_ip_d[41]\" \"channel_in_ip_d[42]\" \"channel_in_ip_d[43]\" \"channel_in_ip_d[44]\" \"channel_in_ip_d[45]\" \"channel_in_ip_d[46]\" \"channel_in_ip_d[47]\" \"channel_in_ip_d[48]\" \"channel_in_ip_d[49]\" \"channel_in_ip_d[50]\" \"channel_in_ip_d[51]\" \"channel_in_ip_d[52]\" \"channel_in_ip_d[53]\" \"channel_in_ip_d[54]\" \"channel_in_ip_d[55]\" \"channel_in_ip_d[56]\" \"channel_in_ip_d[57]\" \"channel_in_ip_d[58]\" \"channel_in_ip_d[59]\" \"channel_in_ip_d[60]\" \"channel_in_ip_d[61]\" \"channel_in_ip_d[62]\" \"channel_in_ip_d[63]\" \"channel_in_ip_d[64]\" \"channel_in_ip_d[65]\" \"channel_in_ip_d[66]\" \"channel_in_ip_d[67]\"}",
    #side 1
    "set my_1_ch_in_ports {\"channel_in_ip_d[68]\" \"channel_in_ip_d[69]\" \"channel_in_ip_d[70]\" \"channel_in_ip_d[71]\" \"channel_in_ip_d[72]\" \"channel_in_ip_d[73]\" \"channel_in_ip_d[74]\" \"channel_in_ip_d[75]\" \"channel_in_ip_d[76]\" \"channel_in_ip_d[77]\" \"channel_in_ip_d[78]\" \"channel_in_ip_d[79]\" \"channel_in_ip_d[80]\" \"channel_in_ip_d[81]\" \"channel_in_ip_d[82]\" \"channel_in_ip_d[83]\" \"channel_in_ip_d[84]\" \"channel_in_ip_d[85]\" \"channel_in_ip_d[86]\" \"channel_in_ip_d[87]\" \"channel_in_ip_d[88]\" \"channel_in_ip_d[89]\" \"channel_in_ip_d[90]\" \"channel_in_ip_d[91]\" \"channel_in_ip_d[92]\" \"channel_in_ip_d[93]\" \"channel_in_ip_d[94]\" \"channel_in_ip_d[95]\" \"channel_in_ip_d[96]\" \"channel_in_ip_d[97]\" \"channel_in_ip_d[98]\" \"channel_in_ip_d[99]\" \"channel_in_ip_d[100]\" \"channel_in_ip_d[101]\" \"channel_in_ip_d[102]\" \"channel_in_ip_d[103]\" \"channel_in_ip_d[104]\" \"channel_in_ip_d[105]\" \"channel_in_ip_d[106]\" \"channel_in_ip_d[107]\" \"channel_in_ip_d[108]\" \"channel_in_ip_d[109]\" \"channel_in_ip_d[110]\" \"channel_in_ip_d[111]\" \"channel_in_ip_d[112]\" \"channel_in_ip_d[113]\" \"channel_in_ip_d[114]\" \"channel_in_ip_d[115]\" \"channel_in_ip_d[116]\" \"channel_in_ip_d[117]\" \"channel_in_ip_d[118]\" \"channel_in_ip_d[119]\" \"channel_in_ip_d[120]\" \"channel_in_ip_d[121]\" \"channel_in_ip_d[122]\" \"channel_in_ip_d[123]\" \"channel_in_ip_d[124]\" \"channel_in_ip_d[125]\" \"channel_in_ip_d[126]\" \"channel_in_ip_d[127]\" \"channel_in_ip_d[128]\" \"channel_in_ip_d[129]\" \"channel_in_ip_d[130]\" \"channel_in_ip_d[131]\" \"channel_in_ip_d[132]\" \"channel_in_ip_d[133]\" \"channel_in_ip_d[134]\" \"channel_in_ip_d[135]\"}",
    #side 2
    "set my_2_ch_in_ports {\"channel_in_ip_d[136]\" \"channel_in_ip_d[137]\" \"channel_in_ip_d[138]\" \"channel_in_ip_d[139]\" \"channel_in_ip_d[140]\" \"channel_in_ip_d[141]\" \"channel_in_ip_d[142]\" \"channel_in_ip_d[143]\" \"channel_in_ip_d[144]\" \"channel_in_ip_d[145]\" \"channel_in_ip_d[146]\" \"channel_in_ip_d[147]\" \"channel_in_ip_d[148]\" \"channel_in_ip_d[149]\" \"channel_in_ip_d[150]\" \"channel_in_ip_d[151]\" \"channel_in_ip_d[152]\" \"channel_in_ip_d[153]\" \"channel_in_ip_d[154]\" \"channel_in_ip_d[155]\" \"channel_in_ip_d[156]\" \"channel_in_ip_d[157]\" \"channel_in_ip_d[158]\" \"channel_in_ip_d[159]\" \"channel_in_ip_d[160]\" \"channel_in_ip_d[161]\" \"channel_in_ip_d[162]\" \"channel_in_ip_d[163]\" \"channel_in_ip_d[164]\" \"channel_in_ip_d[165]\" \"channel_in_ip_d[166]\" \"channel_in_ip_d[167]\" \"channel_in_ip_d[168]\" \"channel_in_ip_d[169]\" \"channel_in_ip_d[170]\" \"channel_in_ip_d[171]\" \"channel_in_ip_d[172]\" \"channel_in_ip_d[173]\" \"channel_in_ip_d[174]\" \"channel_in_ip_d[175]\" \"channel_in_ip_d[176]\" \"channel_in_ip_d[177]\" \"channel_in_ip_d[178]\" \"channel_in_ip_d[179]\" \"channel_in_ip_d[180]\" \"channel_in_ip_d[181]\" \"channel_in_ip_d[182]\" \"channel_in_ip_d[183]\" \"channel_in_ip_d[184]\" \"channel_in_ip_d[185]\" \"channel_in_ip_d[186]\" \"channel_in_ip_d[187]\" \"channel_in_ip_d[188]\" \"channel_in_ip_d[189]\" \"channel_in_ip_d[190]\" \"channel_in_ip_d[191]\" \"channel_in_ip_d[192]\" \"channel_in_ip_d[193]\" \"channel_in_ip_d[194]\" \"channel_in_ip_d[195]\" \"channel_in_ip_d[196]\" \"channel_in_ip_d[197]\" \"channel_in_ip_d[198]\" \"channel_in_ip_d[199]\" \"channel_in_ip_d[200]\" \"channel_in_ip_d[201]\" \"channel_in_ip_d[202]\" \"channel_in_ip_d[203]\"}",
    #side 3 (68 + 68)
    "set my_3_ch_in_ports {\"channel_in_ip_d[204]\" \"channel_in_ip_d[205]\" \"channel_in_ip_d[206]\" \"channel_in_ip_d[207]\" \"channel_in_ip_d[208]\" \"channel_in_ip_d[209]\" \"channel_in_ip_d[210]\" \"channel_in_ip_d[211]\" \"channel_in_ip_d[212]\" \"channel_in_ip_d[213]\" \"channel_in_ip_d[214]\" \"channel_in_ip_d[215]\" \"channel_in_ip_d[216]\" \"channel_in_ip_d[217]\" \"channel_in_ip_d[218]\" \"channel_in_ip_d[219]\" \"channel_in_ip_d[220]\" \"channel_in_ip_d[221]\" \"channel_in_ip_d[222]\" \"channel_in_ip_d[223]\" \"channel_in_ip_d[224]\" \"channel_in_ip_d[225]\" \"channel_in_ip_d[226]\" \"channel_in_ip_d[227]\" \"channel_in_ip_d[228]\" \"channel_in_ip_d[229]\" \"channel_in_ip_d[230]\" \"channel_in_ip_d[231]\" \"channel_in_ip_d[232]\" \"channel_in_ip_d[233]\" \"channel_in_ip_d[234]\" \"channel_in_ip_d[235]\" \"channel_in_ip_d[236]\" \"channel_in_ip_d[237]\" \"channel_in_ip_d[238]\" \"channel_in_ip_d[239]\" \"channel_in_ip_d[240]\" \"channel_in_ip_d[241]\" \"channel_in_ip_d[242]\" \"channel_in_ip_d[243]\" \"channel_in_ip_d[244]\" \"channel_in_ip_d[245]\" \"channel_in_ip_d[246]\" \"channel_in_ip_d[247]\" \"channel_in_ip_d[248]\" \"channel_in_ip_d[249]\" \"channel_in_ip_d[250]\" \"channel_in_ip_d[251]\" \"channel_in_ip_d[252]\" \"channel_in_ip_d[253]\" \"channel_in_ip_d[254]\" \"channel_in_ip_d[255]\" \"channel_in_ip_d[256]\" \"channel_in_ip_d[257]\" \"channel_in_ip_d[258]\" \"channel_in_ip_d[259]\" \"channel_in_ip_d[260]\" \"channel_in_ip_d[261]\" \"channel_in_ip_d[262]\" \"channel_in_ip_d[263]\" \"channel_in_ip_d[264]\" \"channel_in_ip_d[265]\" \"channel_in_ip_d[266]\" \"channel_in_ip_d[267]\" \"channel_in_ip_d[268]\" \"channel_in_ip_d[269]\" \"channel_in_ip_d[270]\" \"channel_in_ip_d[271]\" \"channel_in_ip_d[272]\" \"channel_in_ip_d[273]\" \"channel_in_ip_d[274]\" \"channel_in_ip_d[275]\" \"channel_in_ip_d[276]\" \"channel_in_ip_d[277]\" \"channel_in_ip_d[278]\" \"channel_in_ip_d[279]\" \"channel_in_ip_d[280]\" \"channel_in_ip_d[281]\" \"channel_in_ip_d[282]\" \"channel_in_ip_d[283]\" \"channel_in_ip_d[284]\" \"channel_in_ip_d[285]\" \"channel_in_ip_d[286]\" \"channel_in_ip_d[287]\" \"channel_in_ip_d[288]\" \"channel_in_ip_d[289]\" \"channel_in_ip_d[290]\" \"channel_in_ip_d[291]\" \"channel_in_ip_d[292]\" \"channel_in_ip_d[293]\" \"channel_in_ip_d[294]\" \"channel_in_ip_d[295]\" \"channel_in_ip_d[296]\" \"channel_in_ip_d[297]\" \"channel_in_ip_d[298]\" \"channel_in_ip_d[299]\" \"channel_in_ip_d[300]\" \"channel_in_ip_d[301]\" \"channel_in_ip_d[302]\" \"channel_in_ip_d[303]\" \"channel_in_ip_d[304]\" \"channel_in_ip_d[305]\" \"channel_in_ip_d[306]\" \"channel_in_ip_d[307]\" \"channel_in_ip_d[308]\" \"channel_in_ip_d[309]\" \"channel_in_ip_d[310]\" \"channel_in_ip_d[311]\" \"channel_in_ip_d[312]\" \"channel_in_ip_d[313]\" \"channel_in_ip_d[314]\" \"channel_in_ip_d[315]\" \"channel_in_ip_d[316]\" \"channel_in_ip_d[317]\" \"channel_in_ip_d[318]\" \"channel_in_ip_d[319]\" \"channel_in_ip_d[320]\" \"channel_in_ip_d[321]\" \"channel_in_ip_d[322]\" \"channel_in_ip_d[323]\" \"channel_in_ip_d[324]\" \"channel_in_ip_d[325]\" \"channel_in_ip_d[326]\" \"channel_in_ip_d[327]\" \"channel_in_ip_d[328]\" \"channel_in_ip_d[329]\" \"channel_in_ip_d[330]\" \"channel_in_ip_d[331]\" \"channel_in_ip_d[332]\" \"channel_in_ip_d[333]\" \"channel_in_ip_d[334]\" \"channel_in_ip_d[335]\" \"channel_in_ip_d[336]\" \"channel_in_ip_d[337]\" \"channel_in_ip_d[338]\" \"channel_in_ip_d[339]\"}",
    #in ports for ctrl flow
    "set my_flow_ctrl_in_ports {\"flow_ctrl_out_ip_q[0]\" \"flow_ctrl_out_ip_q[1]\" \"flow_ctrl_out_ip_q[2]\" \"flow_ctrl_out_ip_q[3]\" \"flow_ctrl_out_ip_q[4]\" \"flow_ctrl_out_ip_q[5]\" \"flow_ctrl_out_ip_q[6]\" \"flow_ctrl_out_ip_q[7]\" \"flow_ctrl_out_ip_q[8]\" \"flow_ctrl_out_ip_q[9]\"}",

    #side 0
    "set my_0_ch_out_ports {\"channel_out_op_q[0]\" \"channel_out_op_q[1]\" \"channel_out_op_q[2]\" \"channel_out_op_q[3]\" \"channel_out_op_q[4]\" \"channel_out_op_q[5]\" \"channel_out_op_q[6]\" \"channel_out_op_q[7]\" \"channel_out_op_q[8]\" \"channel_out_op_q[9]\" \"channel_out_op_q[10]\" \"channel_out_op_q[11]\" \"channel_out_op_q[12]\" \"channel_out_op_q[13]\" \"channel_out_op_q[14]\" \"channel_out_op_q[15]\" \"channel_out_op_q[16]\" \"channel_out_op_q[17]\" \"channel_out_op_q[18]\" \"channel_out_op_q[19]\" \"channel_out_op_q[20]\" \"channel_out_op_q[21]\" \"channel_out_op_q[22]\" \"channel_out_op_q[23]\" \"channel_out_op_q[24]\" \"channel_out_op_q[25]\" \"channel_out_op_q[26]\" \"channel_out_op_q[27]\" \"channel_out_op_q[28]\" \"channel_out_op_q[29]\" \"channel_out_op_q[30]\" \"channel_out_op_q[31]\" \"channel_out_op_q[32]\" \"channel_out_op_q[33]\" \"channel_out_op_q[34]\" \"channel_out_op_q[35]\" \"channel_out_op_q[36]\" \"channel_out_op_q[37]\" \"channel_out_op_q[38]\" \"channel_out_op_q[39]\" \"channel_out_op_q[40]\" \"channel_out_op_q[41]\" \"channel_out_op_q[42]\" \"channel_out_op_q[43]\" \"channel_out_op_q[44]\" \"channel_out_op_q[45]\" \"channel_out_op_q[46]\" \"channel_out_op_q[47]\" \"channel_out_op_q[48]\" \"channel_out_op_q[49]\" \"channel_out_op_q[50]\" \"channel_out_op_q[51]\" \"channel_out_op_q[52]\" \"channel_out_op_q[53]\" \"channel_out_op_q[54]\" \"channel_out_op_q[55]\" \"channel_out_op_q[56]\" \"channel_out_op_q[57]\" \"channel_out_op_q[58]\" \"channel_out_op_q[59]\" \"channel_out_op_q[60]\" \"channel_out_op_q[61]\" \"channel_out_op_q[62]\" \"channel_out_op_q[63]\" \"channel_out_op_q[64]\" \"channel_out_op_q[65]\" \"channel_out_op_q[66]\" \"channel_out_op_q[67]\"}",
    #side 1
    "set my_1_ch_out_ports {\"channel_out_op_q[68]\" \"channel_out_op_q[69]\" \"channel_out_op_q[70]\" \"channel_out_op_q[71]\" \"channel_out_op_q[72]\" \"channel_out_op_q[73]\" \"channel_out_op_q[74]\" \"channel_out_op_q[75]\" \"channel_out_op_q[76]\" \"channel_out_op_q[77]\" \"channel_out_op_q[78]\" \"channel_out_op_q[79]\" \"channel_out_op_q[80]\" \"channel_out_op_q[81]\" \"channel_out_op_q[82]\" \"channel_out_op_q[83]\" \"channel_out_op_q[84]\" \"channel_out_op_q[85]\" \"channel_out_op_q[86]\" \"channel_out_op_q[87]\" \"channel_out_op_q[88]\" \"channel_out_op_q[89]\" \"channel_out_op_q[90]\" \"channel_out_op_q[91]\" \"channel_out_op_q[92]\" \"channel_out_op_q[93]\" \"channel_out_op_q[94]\" \"channel_out_op_q[95]\" \"channel_out_op_q[96]\" \"channel_out_op_q[97]\" \"channel_out_op_q[98]\" \"channel_out_op_q[99]\" \"channel_out_op_q[100]\" \"channel_out_op_q[101]\" \"channel_out_op_q[102]\" \"channel_out_op_q[103]\" \"channel_out_op_q[104]\" \"channel_out_op_q[105]\" \"channel_out_op_q[106]\" \"channel_out_op_q[107]\" \"channel_out_op_q[108]\" \"channel_out_op_q[109]\" \"channel_out_op_q[110]\" \"channel_out_op_q[111]\" \"channel_out_op_q[112]\" \"channel_out_op_q[113]\" \"channel_out_op_q[114]\" \"channel_out_op_q[115]\" \"channel_out_op_q[116]\" \"channel_out_op_q[117]\" \"channel_out_op_q[118]\" \"channel_out_op_q[119]\" \"channel_out_op_q[120]\" \"channel_out_op_q[121]\" \"channel_out_op_q[122]\" \"channel_out_op_q[123]\" \"channel_out_op_q[124]\" \"channel_out_op_q[125]\" \"channel_out_op_q[126]\" \"channel_out_op_q[127]\" \"channel_out_op_q[128]\" \"channel_out_op_q[129]\" \"channel_out_op_q[130]\" \"channel_out_op_q[131]\" \"channel_out_op_q[132]\" \"channel_out_op_q[133]\" \"channel_out_op_q[134]\" \"channel_out_op_q[135]\"}",
    #side 2
    "set my_2_ch_out_ports {\"channel_out_op_q[136]\" \"channel_out_op_q[137]\" \"channel_out_op_q[138]\" \"channel_out_op_q[139]\" \"channel_out_op_q[140]\" \"channel_out_op_q[141]\" \"channel_out_op_q[142]\" \"channel_out_op_q[143]\" \"channel_out_op_q[144]\" \"channel_out_op_q[145]\" \"channel_out_op_q[146]\" \"channel_out_op_q[147]\" \"channel_out_op_q[148]\" \"channel_out_op_q[149]\" \"channel_out_op_q[150]\" \"channel_out_op_q[151]\" \"channel_out_op_q[152]\" \"channel_out_op_q[153]\" \"channel_out_op_q[154]\" \"channel_out_op_q[155]\" \"channel_out_op_q[156]\" \"channel_out_op_q[157]\" \"channel_out_op_q[158]\" \"channel_out_op_q[159]\" \"channel_out_op_q[160]\" \"channel_out_op_q[161]\" \"channel_out_op_q[162]\" \"channel_out_op_q[163]\" \"channel_out_op_q[164]\" \"channel_out_op_q[165]\" \"channel_out_op_q[166]\" \"channel_out_op_q[167]\" \"channel_out_op_q[168]\" \"channel_out_op_q[169]\" \"channel_out_op_q[170]\" \"channel_out_op_q[171]\" \"channel_out_op_q[172]\" \"channel_out_op_q[173]\" \"channel_out_op_q[174]\" \"channel_out_op_q[175]\" \"channel_out_op_q[176]\" \"channel_out_op_q[177]\" \"channel_out_op_q[178]\" \"channel_out_op_q[179]\" \"channel_out_op_q[180]\" \"channel_out_op_q[181]\" \"channel_out_op_q[182]\" \"channel_out_op_q[183]\" \"channel_out_op_q[184]\" \"channel_out_op_q[185]\" \"channel_out_op_q[186]\" \"channel_out_op_q[187]\" \"channel_out_op_q[188]\" \"channel_out_op_q[189]\" \"channel_out_op_q[190]\" \"channel_out_op_q[191]\" \"channel_out_op_q[192]\" \"channel_out_op_q[193]\" \"channel_out_op_q[194]\" \"channel_out_op_q[195]\" \"channel_out_op_q[196]\" \"channel_out_op_q[197]\" \"channel_out_op_q[198]\" \"channel_out_op_q[199]\" \"channel_out_op_q[200]\" \"channel_out_op_q[201]\" \"channel_out_op_q[202]\" \"channel_out_op_q[203]\"}",
    #side 3 (68 + 68)
    "set my_3_ch_out_ports {\"channel_out_op_q[204]\" \"channel_out_op_q[205]\" \"channel_out_op_q[206]\" \"channel_out_op_q[207]\" \"channel_out_op_q[208]\" \"channel_out_op_q[209]\" \"channel_out_op_q[210]\" \"channel_out_op_q[211]\" \"channel_out_op_q[212]\" \"channel_out_op_q[213]\" \"channel_out_op_q[214]\" \"channel_out_op_q[215]\" \"channel_out_op_q[216]\" \"channel_out_op_q[217]\" \"channel_out_op_q[218]\" \"channel_out_op_q[219]\" \"channel_out_op_q[220]\" \"channel_out_op_q[221]\" \"channel_out_op_q[222]\" \"channel_out_op_q[223]\" \"channel_out_op_q[224]\" \"channel_out_op_q[225]\" \"channel_out_op_q[226]\" \"channel_out_op_q[227]\" \"channel_out_op_q[228]\" \"channel_out_op_q[229]\" \"channel_out_op_q[230]\" \"channel_out_op_q[231]\" \"channel_out_op_q[232]\" \"channel_out_op_q[233]\" \"channel_out_op_q[234]\" \"channel_out_op_q[235]\" \"channel_out_op_q[236]\" \"channel_out_op_q[237]\" \"channel_out_op_q[238]\" \"channel_out_op_q[239]\" \"channel_out_op_q[240]\" \"channel_out_op_q[241]\" \"channel_out_op_q[242]\" \"channel_out_op_q[243]\" \"channel_out_op_q[244]\" \"channel_out_op_q[245]\" \"channel_out_op_q[246]\" \"channel_out_op_q[247]\" \"channel_out_op_q[248]\" \"channel_out_op_q[249]\" \"channel_out_op_q[250]\" \"channel_out_op_q[251]\" \"channel_out_op_q[252]\" \"channel_out_op_q[253]\" \"channel_out_op_q[254]\" \"channel_out_op_q[255]\" \"channel_out_op_q[256]\" \"channel_out_op_q[257]\" \"channel_out_op_q[258]\" \"channel_out_op_q[259]\" \"channel_out_op_q[260]\" \"channel_out_op_q[261]\" \"channel_out_op_q[262]\" \"channel_out_op_q[263]\" \"channel_out_op_q[264]\" \"channel_out_op_q[265]\" \"channel_out_op_q[266]\" \"channel_out_op_q[267]\" \"channel_out_op_q[268]\" \"channel_out_op_q[269]\" \"channel_out_op_q[270]\" \"channel_out_op_q[271]\" \"channel_out_op_q[272]\" \"channel_out_op_q[273]\" \"channel_out_op_q[274]\" \"channel_out_op_q[275]\" \"channel_out_op_q[276]\" \"channel_out_op_q[277]\" \"channel_out_op_q[278]\" \"channel_out_op_q[279]\" \"channel_out_op_q[280]\" \"channel_out_op_q[281]\" \"channel_out_op_q[282]\" \"channel_out_op_q[283]\" \"channel_out_op_q[284]\" \"channel_out_op_q[285]\" \"channel_out_op_q[286]\" \"channel_out_op_q[287]\" \"channel_out_op_q[288]\" \"channel_out_op_q[289]\" \"channel_out_op_q[290]\" \"channel_out_op_q[291]\" \"channel_out_op_q[292]\" \"channel_out_op_q[293]\" \"channel_out_op_q[294]\" \"channel_out_op_q[295]\" \"channel_out_op_q[296]\" \"channel_out_op_q[297]\" \"channel_out_op_q[298]\" \"channel_out_op_q[299]\" \"channel_out_op_q[300]\" \"channel_out_op_q[301]\" \"channel_out_op_q[302]\" \"channel_out_op_q[303]\" \"channel_out_op_q[304]\" \"channel_out_op_q[305]\" \"channel_out_op_q[306]\" \"channel_out_op_q[307]\" \"channel_out_op_q[308]\" \"channel_out_op_q[309]\" \"channel_out_op_q[310]\" \"channel_out_op_q[311]\" \"channel_out_op_q[312]\" \"channel_out_op_q[313]\" \"channel_out_op_q[314]\" \"channel_out_op_q[315]\" \"channel_out_op_q[316]\" \"channel_out_op_q[317]\" \"channel_out_op_q[318]\" \"channel_out_op_q[319]\" \"channel_out_op_q[320]\" \"channel_out_op_q[321]\" \"channel_out_op_q[322]\" \"channel_out_op_q[323]\" \"channel_out_op_q[324]\" \"channel_out_op_q[325]\" \"channel_out_op_q[326]\" \"channel_out_op_q[327]\" \"channel_out_op_q[328]\" \"channel_out_op_q[329]\" \"channel_out_op_q[330]\" \"channel_out_op_q[331]\" \"channel_out_op_q[332]\" \"channel_out_op_q[333]\" \"channel_out_op_q[334]\" \"channel_out_op_q[335]\" \"channel_out_op_q[336]\" \"channel_out_op_q[337]\" \"channel_out_op_q[338]\" \"channel_out_op_q[339]\"}",
    #out ports for ctrl flow
    "set my_flow_ctrl_out_ports {\"flow_ctrl_in_op_d[0]\" \"flow_ctrl_in_op_d[1]\" \"flow_ctrl_in_op_d[2]\" \"flow_ctrl_in_op_d[3]\" \"flow_ctrl_in_op_d[4]\" \"flow_ctrl_in_op_d[5]\" \"flow_ctrl_in_op_d[6]\" \"flow_ctrl_in_op_d[7]\" \"flow_ctrl_in_op_d[8]\" \"flow_ctrl_in_op_d[9]\"}",
    
    #gen i/o s these can be assigned pretty much anywhere (can be left to the tool)
    "set my_gen_pins {\"clk\" \"reset\" \"router_address[0]\" \"router_address[1]\" \"router_address[2]\" \"router_address[3]\" \"router_address[4]\" \"router_address[5]\" \"flow_ctrl_out_ip_q[0]\" \"flow_ctrl_out_ip_q[1]\" \"flow_ctrl_out_ip_q[2]\" \"flow_ctrl_out_ip_q[3]\" \"flow_ctrl_out_ip_q[4]\" \"flow_ctrl_out_ip_q[5]\" \"flow_ctrl_out_ip_q[6]\" \"flow_ctrl_out_ip_q[7]\" \"flow_ctrl_out_ip_q[8]\" \"flow_ctrl_out_ip_q[9]\" \"flow_ctrl_in_op_d[0]\" \"flow_ctrl_in_op_d[1]\" \"flow_ctrl_in_op_d[2]\" \"flow_ctrl_in_op_d[3]\" \"flow_ctrl_in_op_d[4]\" \"flow_ctrl_in_op_d[5]\" \"flow_ctrl_in_op_d[6]\" \"flow_ctrl_in_op_d[7]\" \"flow_ctrl_in_op_d[8]\" \"flow_ctrl_in_op_d[9]\" \"error\"}",
    #swapped edge 0 and edge 4 channel in/out locations to allow for it to work
    #assign pin locations
    "editPin -pinWidth 0.1 -pinDepth 0.52 -fixOverlap 1 -global_location -unit TRACK -spreadDirection clockwise -edge 0 -layer 3 -spreadType start -spacing " + str(flow_settings["ptn_params"]["top_settings"]["fp_pin_spacing"]) + " -offsetStart " + str(ch_out_offset) + " -pin $my_0_ch_in_ports",
    "editPin -pinWidth 0.1 -pinDepth 0.52 -fixOverlap 1 -global_location -unit TRACK -spreadDirection clockwise -edge 1 -layer 4 -spreadType start -spacing "+ str(flow_settings["ptn_params"]["top_settings"]["fp_pin_spacing"]) + " -offsetStart " + str(ch_in_offset) + " -pin $my_1_ch_in_ports",
    "editPin -pinWidth 0.1 -pinDepth 0.52 -fixOverlap 1 -global_location -unit TRACK -spreadDirection counterclockwise -edge 2 -layer 3 -spreadType start -spacing "+ str(flow_settings["ptn_params"]["top_settings"]["fp_pin_spacing"]) + " -offsetStart " + str(ch_in_offset) + " -pin $my_2_ch_in_ports",
    "editPin -pinWidth 0.1 -pinDepth 0.52 -fixOverlap 1 -global_location -unit TRACK -spreadDirection counterclockwise -edge 3 -layer 4 -spreadType start -spacing "+ str(flow_settings["ptn_params"]["top_settings"]["fp_pin_spacing"]) + " -offsetStart " + str(noc_comm_edge_offsets[1]) + " -pin $my_3_ch_in_ports",
    "",
    "editPin -pinWidth 0.1 -pinDepth 0.52 -fixOverlap 1 -global_location -unit TRACK -spreadDirection clockwise -edge 0 -layer 3 -spreadType start -spacing "+ str(flow_settings["ptn_params"]["top_settings"]["fp_pin_spacing"]) + " -offsetStart " + str(ch_in_offset) + " -pin $my_0_ch_out_ports",
    "editPin -pinWidth 0.1 -pinDepth 0.52 -fixOverlap 1 -global_location -unit TRACK -spreadDirection clockwise -edge 1 -layer 4 -spreadType start -spacing "+ str(flow_settings["ptn_params"]["top_settings"]["fp_pin_spacing"]) + " -offsetStart " + str(ch_out_offset) + " -pin $my_1_ch_out_ports",
    "editPin -pinWidth 0.1 -pinDepth 0.52 -fixOverlap 1 -global_location -unit TRACK -spreadDirection counterclockwise -edge 2 -layer 3 -spreadType start -spacing "+ str(flow_settings["ptn_params"]["top_settings"]["fp_pin_spacing"]) + " -offsetStart " + str(ch_out_offset) + " -pin $my_2_ch_out_ports",
    "editPin -pinWidth 0.1 -pinDepth 0.52 -fixOverlap 1 -global_location -unit TRACK -spreadDirection counterclockwise -edge 3 -layer 4 -spreadType start -spacing "+ str(flow_settings["ptn_params"]["top_settings"]["fp_pin_spacing"]) + " -offsetStart " + str(noc_comm_edge_offsets[0]) + " -pin $my_3_ch_out_ports",
    "",

    "legalizePin"
  ]
  for line in file_lines:
    file_write_ln(fd,line)
  fd.close()
  return ch_in_offset, ch_out_offset


def write_innovus_fp_script(flow_settings,metal_layer,init_script_fname,fp_dims):
  """
  This generates the lines for a script which can generate a floorplan for a design, this must be done prior to creating partitions.
  The fp_dims parameter is a list of floorplan dimensions for the width and height of floorplan
  """
  output_path = os.path.join("..","outputs")
  script_path = os.path.join("..","scripts")
  output_path = os.path.abspath(output_path)
  script_path = os.path.abspath(script_path)

  #new file for every dimension
  fp_script_fname = flow_settings["top_level"] + "_dimlen_" + str(fp_dims[0]) + "_innovus_fp_gen.tcl"
  #new floorplan for every dimension
  fp_save_file = "_".join([flow_settings["top_level"],"dimlen",str(fp_dims[0])+".fp"])
  metal_layer_bottom = flow_settings["metal_layer_names"][0]
  metal_layer_second = flow_settings["metal_layer_names"][1]
  metal_layer_top = flow_settings["metal_layer_names"][int(metal_layer)-1]

  file_lines = [
    "source " + init_script_fname,
    
    # New static dimension fplan cmd
    "floorPlan -site " +
      " ".join([flow_settings["core_site_name"],
      "-s", 
      " ".join(["{",
        str(fp_dims[0]),
        str(fp_dims[1]),
        flow_settings["space_around_core"],
        flow_settings["space_around_core"],
        flow_settings["space_around_core"],
        flow_settings["space_around_core"],
        "}"])
      ]),
    "setDesignMode -topRoutingLayer " + metal_layer,
    "fit",
    " ".join(["addRing", "-type core_rings","-nets","{" + " ".join([flow_settings["pwr_net"],flow_settings["gnd_net"]]) + "}",
      "-layer {" + " ".join(["top",metal_layer_bottom,"bottom",metal_layer_bottom,"left",metal_layer_second,"right",metal_layer_second]) + "}",
      "-width", flow_settings["power_ring_width"],
      "-spacing", flow_settings["power_ring_spacing"],
      "-offset", flow_settings["power_ring_width"],
      "-follow io"]),
    "set sprCreateIeRingOffset 1.0",
    "set sprCreateIeRingLayers {}",
    "set sprCreateIeStripeWidth " + flow_settings["space_around_core"],
    "set sprCreateIeStripeThreshold 1.0",
    #TODO keep the width and spacing settings of noc settings file constant while running length tests, change the below lines for parameterization later.
    "setAddStripeMode -ignore_block_check false -break_at none -route_over_rows_only false -rows_without_stripes_only false -extend_to_closest_target none -stop_at_last_wire_for_area false -partial_set_thru_domain false -ignore_nondefault_domains false -trim_antenna_back_to_shape none -spacing_type edge_to_edge -spacing_from_block 0 -stripe_min_length stripe_width -stacked_via_top_layer AP -stacked_via_bottom_layer M1 -via_using_exact_crossover_size false -split_vias false -orthogonal_only true -allow_jog { padcore_ring  block_ring } -skip_via_on_pin {  standardcell } -skip_via_on_wire_shape {  noshape   }",
    "addStripe -nets {VDD VSS} -layer M2 -direction vertical -width 1.8 -spacing 1.8 -set_to_set_distance 50 -start_from left -start_offset 50 -switch_layer_over_obs false -max_same_layer_jog_length 2 -padcore_ring_top_layer_limit AP -padcore_ring_bottom_layer_limit M1 -block_ring_top_layer_limit AP -block_ring_bottom_layer_limit M1 -use_wire_group 0 -snap_wire_center_to_grid None",
    #"clearGlobalNets", #Pretty sure we don't need this but leaving it in case
    "globalNetConnect " + flow_settings["gnd_pin"] + " -type pgpin -pin " + flow_settings["gnd_pin"] + " -inst {}",
    "globalNetConnect " + flow_settings["pwr_pin"] + " -type pgpin -pin " + flow_settings["pwr_pin"] + " -inst {}",
    "globalNetConnect " + flow_settings["gnd_net"] + " -type net -net  " + flow_settings["gnd_net"],
    "globalNetConnect " + flow_settings["pwr_net"] + " -type net -net  " + flow_settings["pwr_net"],
    "globalNetConnect " + flow_settings["pwr_pin"] + " -type pgpin -pin  " + flow_settings["pwr_pin"] + " -inst *",
    "globalNetConnect " + flow_settings["gnd_pin"] + " -type pgpin -pin  " + flow_settings["gnd_pin"] + " -inst *",
    "globalNetConnect " + flow_settings["pwr_pin"] + " -type tiehi -inst *",
    "globalNetConnect " + flow_settings["gnd_pin"] + " -type tielo -inst *",
    "sroute -connect { blockPin padPin padRing corePin floatingStripe } -layerChangeRange { "+ " ".join([metal_layer_bottom,metal_layer_top]) + " }"\
     + " -blockPinTarget { nearestRingStripe nearestTarget } -padPinPortConnect { allPort oneGeom } -checkAlignedSecondaryPin 1 -blockPin useLef -allowJogging 1"\
     + " -crossoverViaBottomLayer " + metal_layer_bottom + " -targetViaBottomLayer " + metal_layer_bottom + " -allowLayerChange 1"\
     + " -targetViaTopLayer " + metal_layer_top + " -crossoverViaTopLayer " + metal_layer_top + " -nets {" + " ".join([flow_settings["gnd_net"],flow_settings["pwr_net"]]) +  "}",
    #Placement needs to be performed to place IO pins... 
    "setPlaceMode -fp false -place_global_place_io_pins true",
    "place_design -noPrePlaceOpt",
    "earlyGlobalRoute",
    # Assign port locations
    "source " + os.path.join(script_path,"port_vars.tcl"),
    "saveFPlan " + os.path.join(output_path,fp_save_file)
  ]
  fd = open(fp_script_fname,"w")
  for line in file_lines:
    file_write_ln(fd,line)
  file_write_ln(fd,"exit")
  fd.close()
  return fp_script_fname, os.path.join(output_path,fp_save_file)

def write_innovus_ptn_script(flow_settings,init_script_fname,fp_save_file,offsets,dim_pair,auto_assign_regs=False):
  """
  Writes script to partition a design, uses ptn_info_list extracted from parameter file to define partition locations, has the option to auto assign register partitions but option has not been 
  extended to support unique params.
  """
  
  ptn_info_list = flow_settings["ptn_params"]["partitions"]
  #
  report_path = os.path.join("..","reports")
  output_path = os.path.join("..","outputs")
  report_path = os.path.abspath(report_path)
  output_path = os.path.abspath(output_path)
  

  if(auto_assign_regs):
    #offsets[0] is channel_in [1] is channel out
    ff_const_offset = 1.0 #ff offset from pin offsets
    ff_depth_from_pins = 20.0
    ff_width = 68.0 #w.r.t the pins
    ff_height = 12.0 #w.r.t the pins
    
    #This is a bit of a hack as to really find the width of a grouping of pins we need to access innovus and it would be annoying to make the script generation execution dependant again
    #Actually realized I can properly estimate the width by looking at the beginning and end of pin offsets
    for ptn in ptn_info_list:
      if("ff" in ptn["inst_name"]): #TODO fix -> design specific
        #The bounds will be found automatically to match pin locations
        #filter out which channel corresponds to ports, again this is going to be hacky
        # 1 in inst name corresponds to edge 1
        if("1" in ptn["inst_name"]):
          #North side connections
          if("in" in ptn["inst_name"]):
            ptn["fp_coords"][0] = offsets[0] - ff_const_offset #lc x 
            ptn["fp_coords"][1] = dim_pair[1] - ff_depth_from_pins - ff_height #lc y
            ptn["fp_coords"][2] = offsets[0] + ff_width + ff_const_offset #uc x 
            ptn["fp_coords"][3] = dim_pair[1] - ff_depth_from_pins #uc y
          elif("out" in ptn["inst_name"]):
            ptn["fp_coords"][0] = offsets[1] - ff_const_offset #lc x 
            ptn["fp_coords"][1] = dim_pair[1] - ff_depth_from_pins - ff_height #lc y
            ptn["fp_coords"][2] = offsets[1] + ff_width + ff_const_offset#uc x 
            ptn["fp_coords"][3] = dim_pair[1] - ff_depth_from_pins #uc y
        elif("2" in ptn["inst_name"]):
          if("in" in ptn["inst_name"]):
            #East side connections
            ptn["fp_coords"][0] = dim_pair[0] - ff_depth_from_pins - ff_height #lc x 
            ptn["fp_coords"][1] = offsets[0] - ff_const_offset #lc y
            ptn["fp_coords"][2] = dim_pair[0] - ff_depth_from_pins #uc y
            ptn["fp_coords"][3] = offsets[0] + ff_width + ff_const_offset
          elif("out" in ptn["inst_name"]):
            ptn["fp_coords"][0] = dim_pair[0] - ff_depth_from_pins - ff_height #lc x 
            ptn["fp_coords"][1] = offsets[1] - ff_const_offset #lc y
            ptn["fp_coords"][2] = dim_pair[0] - ff_depth_from_pins #uc y
            ptn["fp_coords"][3] = offsets[1] + ff_width + ff_const_offset

      
  #load in partition floorplan boundaries
  obj_fplan_box_cmds = [" ".join(["setObjFPlanBox","Module",ptn["inst_name"]," ".join([str(coord) for coord in ptn["fp_coords"]])]) for ptn in ptn_info_list]
  #define partitions
  def_ptn_cmds = [" ".join(["definePartition","-hinst",ptn["inst_name"],"-coreSpacing 0.0 0.0 0.0 0.0 -railWidth 0.0 -minPitchLeft 2 -minPitchRight 2 -minPitchTop 2 -minPitchBottom 2 -reservedLayer { 1 2 3 4 5 6 7 8 9 10} -pinLayerTop { 2 4 6 8 10} -pinLayerLeft { 3 5 7 9} -pinLayerBottom { 2 4 6 8 10} -pinLayerRight { 3 5 7 9} -placementHalo 0.0 0.0 0.0 0.0 -routingHalo 0.0 -routingHaloTopLayer 10 -routingHaloBottomLayer 1"]) for ptn in ptn_info_list]
  ptn_script_fname = os.path.splitext(os.path.basename(fp_save_file))[0] + "_ptn" + ".tcl"
  post_partition_fplan = "_".join([os.path.splitext(fp_save_file)[0],"post_ptn.fp"])

  file_lines = [
    " ".join(["source",init_script_fname]),
    "loadFPlan " + fp_save_file,
    obj_fplan_box_cmds,
    def_ptn_cmds,
    #Tutorial says that one should save the floorplan after the partition is defined, not sure why maybe will have to add SaveFP command here
    "saveFPlan " + os.path.join(output_path,post_partition_fplan),
    "setPlaceMode -place_hard_fence true",
    "setOptMode -honorFence true",
    "place_opt_design",
    "assignPtnPin",
    "setBudgetingMode -virtualOptEngine gigaOpt",
    "setBudgetingMode -constantModel true",
    "setBudgetingMode -includeLatency true",
    "deriveTimingBudget",
    #commits partition
    "partition",
    "savePartition -dir " + os.path.splitext(os.path.basename(fp_save_file))[0] + "_ptn" + " -def"
  ]

  file_lines = flatten_mixed_list(file_lines)
  fd = open(ptn_script_fname,"w")
  for line in file_lines:
    file_write_ln(fd,line)
  file_write_ln(fd,"exit")
  fd.close()
  return ptn_script_fname

def write_innovus_ptn_block_flow(metal_layer,ptn_dir_name,block_name):
  """
  After parititioning, we need to run placement and routing for each new partition created as well as the top level, This function generates the 
  script to run block specific pnr flow, partitions must be created at this point with subdirectories for each block
  """ 
  file_lines = [
    "cd " + os.path.join("..","work",ptn_dir_name,block_name),
    " ".join(["source", block_name + ".globals"]),
    "init_design",
    "loadFPlan " + block_name + ".fp.gz",
    "place_opt_design",
    "extractRC",
    "timeDesign -preCTS -pathReports -drvReports -slackReports -numPaths 50 -prefix " + block_name + "_preCTS -outDir timingReports",
    "create_ccopt_clock_tree_spec",
    "ccopt_design",
    "optDesign -postCTS",
    "setNanoRouteMode -quiet -routeWithTimingDriven 1",
    "setNanoRouteMode -quiet -routeWithSiDriven 1",
    "setNanoRouteMode -quiet -routeTopRoutingLayer " + str(metal_layer),
    "setNanoRouteMode -quiet -routeBottomRoutingLayer 1",
    "setNanoRouteMode -quiet -drouteEndIteration 1",
    "setNanoRouteMode -quiet -routeWithTimingDriven true",
    "setNanoRouteMode -quiet -routeWithSiDriven true",
    "routeDesign -globalDetail",
    "setAnalysisMode -analysisType onChipVariation -cppr both",
    "optDesign -postRoute",
    #put a check in place to make sure the above optimization actually results in timing passing
    "timeDesign -postRoute -pathReports -drvReports -slackReports -numPaths 50 -prefix " +  block_name + "_postRoute -outDir timingReports",
    "saveDesign " + block_name + "_imp",
  ]
  block_ptn_flow_script_fname = ptn_dir_name + "_" + block_name + "_block_flow.tcl"
  fd = open(block_ptn_flow_script_fname,"w")
  for line in file_lines:
    file_write_ln(fd,line)
  file_write_ln(fd,"exit")
  fd.close()

def write_innovus_ptn_top_level_flow(metal_layer,ptn_dir_name,top_level_name):
  """
  This script runs partitioning for the top level module containing the sub blocks, the sub block partitions must have gone through pnr before this point.
  """ 
  file_lines = [
    "cd " + os.path.join("..","work",ptn_dir_name,top_level_name),
    " ".join(["source", top_level_name + ".globals"]),
    "init_design",
    "defIn " + top_level_name + ".def.gz",
    "create_ccopt_clock_tree_spec",
    "ccopt_design",
    "optDesign -postCTS",
    "setNanoRouteMode -quiet -routeWithTimingDriven 1",
    "setNanoRouteMode -quiet -routeWithSiDriven 1",
    "setNanoRouteMode -quiet -routeTopRoutingLayer " + str(metal_layer),
    "setNanoRouteMode -quiet -routeBottomRoutingLayer 1",
    "setNanoRouteMode -quiet -drouteEndIteration 1",
    "setNanoRouteMode -quiet -routeWithTimingDriven true",
    "setNanoRouteMode -quiet -routeWithSiDriven true",
    "routeDesign -globalDetail",
    "setAnalysisMode -analysisType onChipVariation -cppr both",
    "optDesign -postRoute",
    "timeDesign -postRoute -pathReports -drvReports -slackReports -numPaths 50 -prefix " + top_level_name + " -outDir timingReports",
    "saveDesign " + top_level_name + "_imp",
  ]
  toplvl_ptn_flow_script_fname = ptn_dir_name + "_toplvl_flow.tcl"
  fd = open(toplvl_ptn_flow_script_fname,"w")
  for line in file_lines:
    file_write_ln(fd,line)
  file_write_ln(fd,"exit")
  fd.close()

def write_innovus_assemble_script(flow_settings,ptn_dir_name,block_list,top_level_name):
  """
  Once all previous partition pnr stages have been completed, we can assemble the design, optimize it and get timing results for the hierarchical design.
  """
  report_path = os.path.join("..","reports")
  output_path = os.path.join("..","outputs")
  report_path = os.path.abspath(report_path)
  output_path = os.path.abspath(output_path)
  if flow_settings['map_file'] != "None":
    stream_out_cmd = "streamOut " +  os.path.join(output_path,"final.gds2") + " -mapFile " + flow_settings["map_file"] + " -stripes 1 -units 1000 -mode ALL"
  else:
    stream_out_cmd = "streamOut " +  os.path.join(output_path,"final.gds2") + " -stripes 1 -units 1000 -mode ALL"
  assem_blk_str_list = ["-blockDir " + os.path.join(ptn_dir_name,block_name,block_name + "_imp.dat") for block_name in block_list]
  assem_blk_str = " " + " ".join(assem_blk_str_list) + " "
  file_lines = [ 
    "assembleDesign -topDir " + os.path.join(ptn_dir_name,top_level_name,top_level_name+"_imp.dat") +
     assem_blk_str +
     #os.path.join(ptn_dir_name,block_name,block_name + "_imp.dat") + 
     " -fe -mmmcFile " + os.path.join("..","scripts",flow_settings["top_level"]+".view"),
    "setAnalysisMode -analysisType onChipVariation -cppr both",
    "optDesign -postRoute",
    #-setup -postRoute",
    #"optDesign -hold -postRoute",
    #"optDesign -drv -postRoute",
    "timeDesign -postRoute -prefix assembled -outDir " + os.path.join(report_path,ptn_dir_name,"timingReports"),
    "verify_drc -report " + os.path.join(report_path, ptn_dir_name,"geom.rpt"),
    "verifyConnectivity -type all -report " + os.path.join(report_path,ptn_dir_name, "conn.rpt"),
    "report_timing > " + os.path.join(report_path,ptn_dir_name, "setup_timing.rpt"),
    "setAnalysisMode -checkType hold",
    "report_timing > " + os.path.join(report_path,ptn_dir_name, "hold_timing.rpt"),
    "report_power > " + os.path.join(report_path,ptn_dir_name, "power.rpt"),
    "report_constraint -all_violators > " + os.path.join(report_path,ptn_dir_name, "violators.rpt"),
    "report_area > " + os.path.join(report_path,ptn_dir_name, "area.rpt"),
    "summaryReport -outFile " + os.path.join(report_path,ptn_dir_name, "pr_report.txt"),
    "saveDesign " + os.path.join(output_path,ptn_dir_name + "_assembled"),
    "saveNetlist " + os.path.join(output_path,ptn_dir_name,"netlist.v"),
    "rcOut -spef " +  os.path.join(output_path,ptn_dir_name,"spef.spef"),
    "write_sdf " + os.path.join(output_path,ptn_dir_name,"sdf.sdf"),
    stream_out_cmd
  ]
  assemble_ptn_flow_script_fname = ptn_dir_name + "_assembly_flow.tcl"
  fd = open(assemble_ptn_flow_script_fname,"w")
  for line in file_lines:
    file_write_ln(fd,line)
  file_write_ln(fd,"exit")
  fd.close()  
  return ptn_dir_name,os.path.abspath(report_path),os.path.abspath(output_path)
########################################## PNR PARTITION SCRIPTS ##########################################


########################################## PNR UTILITY FUNCS ############################################
def get_innovus_cmd(script_path):
  innovus_cmd = " ".join(["innovus","-no_gui","-init",script_path])
  innovus_cmd = innovus_cmd + " > " + os.path.splitext(os.path.basename(innovus_cmd.split(" ")[-1]))[0] + ".log"
  return innovus_cmd

def get_encounter_cmd(script_path):
  encounter_cmd = " ".join(["encounter","-no_gui","-init",script_path])
  encounter_cmd = encounter_cmd + " > " + os.path.splitext(os.path.basename(encounter_cmd.split(" ")[-1]))[0] + ".log"
  return encounter_cmd

def copy_pnr_outputs(flow_settings,copy_logs_cmd_str,report_dest_str,only_reports=False):
  #Copy pnr results to a unique dir in pnr dir
  clean_logs_cmd_str = copy_logs_cmd_str.split(" ")
  clean_logs_cmd_str[0] = "rm -f"
  #removes the last element in the string (this is the desintation report directory)
  del clean_logs_cmd_str[-1]
  clean_logs_cmd_str = " ".join(clean_logs_cmd_str)

  mkdir_cmd_str = "mkdir -p " + report_dest_str
  if(not only_reports):
    copy_rep_cmd_str = "cp " + flow_settings['pr_folder'] + "/* " + report_dest_str
  else:
    copy_rep_cmd_str = "cp " + flow_settings['pr_folder'] + "/*.rpt " + report_dest_str
  copy_rec_cmd_str = " ".join(["cp -r",os.path.join(flow_settings['pr_folder'],"design.enc.dat"),report_dest_str])
  sp.call(mkdir_cmd_str,shell=True)
  sp.call(copy_rep_cmd_str,shell=True)
  sp.call(copy_rec_cmd_str,shell=True)
  sp.call(copy_logs_cmd_str,shell=True)
  #subprocess.call(clean_logs_cmd_str,shell=True)
########################################## PNR UTILITY FUNCS ############################################
########################################## PNR RUN FUNCS ############################################

def run_pnr(flow_settings,metal_layer,core_utilization,synth_report_str,syn_output_path):
  """
  runs place and route using cadence encounter/innovus
  Prereqs: flow_settings_pre_process() function to properly format params for scripts
  """
  work_dir = os.getcwd()
  pnr_report_str = synth_report_str + "_" + "metal_layers_" + metal_layer + "_" + "util_" + core_utilization
  report_dest_str = os.path.join(flow_settings['pr_folder'],pnr_report_str + "_reports")
  if(flow_settings["pnr_tool"] == "encounter"):
    write_enc_script(flow_settings,metal_layer,core_utilization)
    copy_logs_cmd_str = "cp " + "edi.log " + "edi.tcl " + "edi.conf " + "encounter.log " + "encounter.cmd " + report_dest_str
    encounter_cmd = "encounter -nowin -init edi.tcl | tee edi.log"
    run_shell_cmd_no_logs(encounter_cmd)
  elif(flow_settings["pnr_tool"] == "innovus"):
    view_fpath = write_innovus_view_file(flow_settings,syn_output_path)
    init_script_fname = write_innovus_init_script(flow_settings,view_fpath,syn_output_path)
    innovus_script_fname, pnr_output_path = write_innovus_script(flow_settings,metal_layer,core_utilization,init_script_fname,cts_flag=False)
    run_innovus_cmd = "innovus -no_gui -init " + innovus_script_fname + " | tee inn.log"
    copy_logs_cmd_str = " ".join(["cp", "inn.log", init_script_fname, view_fpath, os.path.join(work_dir,innovus_script_fname), report_dest_str])
    run_shell_cmd_no_logs(run_innovus_cmd)

  # read total area from the report file:
  file = open(os.path.expanduser(flow_settings['pr_folder']) + "/pr_report.txt" ,"r")
  for line in file:
    if line.startswith('Total area of Core:'):
      total_area = re.findall(r'\d+\.{0,1}\d*', line)
  file.close()
  copy_pnr_outputs(flow_settings,copy_logs_cmd_str,report_dest_str)
  return pnr_report_str, pnr_output_path, total_area

########################################## PNR RUN FUNCS ############################################
#   _____ ___ __  __ ___ _  _  ___   _  _   ___  _____      _____ ___ 
#  |_   _|_ _|  \/  |_ _| \| |/ __| | \| | | _ \/ _ \ \    / / __| _ \
#    | |  | || |\/| || || .` | (_ | | .` | |  _/ (_) \ \/\/ /| _||   /
#    |_| |___|_|  |_|___|_|\_|\___| |_|\_| |_|  \___/ \_/\_/ |___|_|_\

########################################## STA UTIL FUNCS ############################################
def get_sta_cmd(script_path):
  pt_shell = "dc_shell-t"
  return " ".join([pt_shell,"-f",script_path,">",os.path.splitext(os.path.basename(script_path))[0]+".log"])

def write_pt_power_timing_script(flow_settings, fname, mode_enabled, clock_period, x, synth_output_path, pnr_output_path, rel_outputs=False):
  """
  writes the tcl script for timing analysis using Synopsys Design Compiler, tested under 2017 version
  This should look for setup/hold violations using the worst case (hold) and best case (setup) libs
  """
  report_path = flow_settings["primetime_folder"] if (not rel_outputs) else os.path.join("..","reports")
  report_path = os.path.abspath(report_path)
  
  
  #TODO make this more general but this is how we see if the report output should have a string appended to it
  if "ptn" in pnr_output_path.split("/")[-1]:
    report_prefix = pnr_output_path.split("/")[-1]
    report_timing_cmd = "report_timing > " + os.path.join(report_path,report_prefix+"_timing.rpt")
    report_power_cmd = "report_power > " + os.path.join(report_path,report_prefix + "_power.rpt")
  else:
    report_timing_cmd = "report_timing > " + os.path.join(report_path,"timing.rpt")
    report_power_cmd = "report_power > " + os.path.join(report_path,"power.rpt")
  
  if mode_enabled and x < 2**len(flow_settings['mode_signal']):
    case_analysis_cmds = [" ".join(["set_case_analysis",str((x >> y) & 1),flow_settings['mode_signal'][y]]) for y in range(0,len(flow_settings["mode_signal"]))]
  else:
    case_analysis_cmds = ["#MULTIMODAL ANALYSIS DISABLED"]
  #For power switching activity estimation
  if flow_settings['generate_activity_file']:
    switching_activity_cmd = "read_saif -input saif.saif -instance_name testbench/uut"
  else:
    switching_activity_cmd = "set_switching_activity -static_probability " + str(flow_settings['static_probability']) + " -toggle_rate " + str(flow_settings['toggle_rate']) + " -base_clock $my_clock_pin -type inputs"

  # backannotate into primetime
  # This part should be reported for all the modes in the design.
  file_lines = [
    "set sh_enable_page_mode true",
    "set search_path " + flow_settings['search_path'],
    "set my_top_level " + flow_settings['top_level'],
    "set my_clock_pin " + flow_settings['clock_pin_name'],
    "set target_library " + flow_settings['primetime_libs'],
    "set link_library " + flow_settings['link_library'],
    "read_verilog " + pnr_output_path + "/netlist.v",
    "current_design $my_top_level",
    "link",
    # "set my_period " + str(clock_period),
    # "set find_clock [ find port [list $my_clock_pin] ] ",
    # "if { $find_clock != [list] } { ",
    # "set clk_name $my_clock_pin",
    # "create_clock -period $my_period $clk_name",
    # "}",

    # read constraints file
    "read_sdc -echo " + synth_output_path + "/synthesized.sdc",
    case_analysis_cmds,
    report_timing_cmd,
    #Standard Parasitic Exchange Format. File format to save parasitic information extracted by the place and route tool.
    "set power_enable_analysis TRUE",
    "set power_analysis_mode \"averaged\"",
    switching_activity_cmd,
    "read_parasitics -increment " + pnr_output_path + "/spef.spef",
    report_power_cmd,
    "quit",
  ]
  file_lines = flatten_mixed_list(file_lines)

  fd = open(fname, "w")
  for line in file_lines:
    file_write_ln(fd,line)
  fd.close()
  fpath = os.path.join(os.getcwd(),fname)
  return fpath,report_path

########################################## STA UTIL FUNCS ############################################
########################################## STA RUN FUNCS ############################################
def run_power_timing(flow_settings,mode_enabled,clock_period,x,synth_output_path,pnr_report_str,pnr_output_path):
  """
  This runs STA using PrimeTime and the pnr generated .spef and netlist file to get a more accurate result for delay
  """
  #If there is no multi modal analysis selected then x (mode of operation) will be set to 0 (only 1 mode) not sure why this is done like below but not going to change it
  #if there is multi modal analysis then the x will be the mode of operation and it will be looped from 0 -> 2^num_modes
  #This is done because multimodal setting basically sets a mux to the value of 0 or 1 and each mode represents 1 mux ie to evaluate them all we have 2^num_modes states to test 
  if not mode_enabled:
    x = 2**len(flow_settings['mode_signal'])
  pt_timing_fpath,timing_report_path = write_pt_power_timing_script(flow_settings, "pt_timing.tcl", mode_enabled, clock_period, x, synth_output_path, pnr_output_path)
  # run prime time, by getting abs path from writing the script, we can run the command in different directory where the script exists
  run_pt_timing_cmd = "dc_shell-t -f " + pt_timing_fpath + " | tee pt_timing.log"
  run_shell_cmd_no_logs(run_pt_timing_cmd)
  # Read timing parameters
  file = open(os.path.join(timing_report_path,"timing.rpt"),"r")
  for line in file:
    if 'library setup time' in line:
      library_setup_time = re.findall(r'\d+\.{0,1}\d*', line)
    if 'data arrival time' in line:
      data_arrival_time = re.findall(r'\d+\.{0,1}\d*', line)
  try:
    total_delay =  float(library_setup_time[0]) + float(data_arrival_time[0])
  except NameError:
    total_delay =  float(data_arrival_time[0])
  file.close()
  
  #write_pt_power_script(flow_settings,"primetime_power.tcl",mode_enabled,clock_period,x,pnr_output_path)
  # run prime time
  #pt_pwr_cmd = "dc_shell-t -f primetime_power.tcl | tee pt_pwr.log"
  #run_shell_cmd_no_logs(pt_pwr_cmd)
  
  #copy reports and logs to a unique dir in pt dir
  pt_report_str = pnr_report_str + "_" + "mode_" + str(x)
  report_dest_str = os.path.expanduser(flow_settings['primetime_folder']) + "/" + pt_report_str + "_reports"
  mkdir_cmd_str = "mkdir -p " + report_dest_str
  copy_rep_cmd_str = "cp " + os.path.expanduser(flow_settings['primetime_folder']) + "/* " + report_dest_str
  copy_logs_cmd_str = "cp " + "pt.log pt_pwr.log primetime.tcl primetime_power.tcl " + report_dest_str
  sp.call(mkdir_cmd_str,shell=True)
  sp.call(copy_rep_cmd_str,shell=True)
  sp.call(copy_logs_cmd_str,shell=True)
  # subprocess.call('rm -f pt.log pt_pwr.log primetime.tcl primetime_power.tcl', shell=True)
  # Read dynamic power
  file = open(os.path.expanduser(flow_settings['primetime_folder']) + "/power.rpt" ,"r")
  for line in file:
    if 'Total Dynamic Power' in line:
      total_dynamic_power = re.findall(r'\d+\.{0,1}\d*', line)
      total_dynamic_power[0] = float(total_dynamic_power[0])
      if 'mW' in line:
        total_dynamic_power[0] *= 0.001
      elif 'uw' in line:
        total_dynamic_power[0] *= 0.000001
      else:
        total_dynamic_power[0] = 0
  file.close() 
  return library_setup_time, data_arrival_time, total_delay, total_dynamic_power   
########################################## STA RUN FUNCS ############################################


def hardblock_flow(flow_settings: Dict[str, Any]) -> Tuple[float]: 
  """
  This function will write and run asic flow scripts for each stage of the asic flow and for each combination of user inputted parameters  
  """
  pre_func_dir = os.getcwd()
  cur_env = os.environ.copy()
  processed_flow_settings = flow_settings
  flow_settings_pre_process(processed_flow_settings, cur_env)
  # Enter all the signals that change modes
  lowest_cost = sys.float_info.max
  lowest_cost_area = 1.0
  lowest_cost_delay = 1.0
  lowest_cost_power = 1.0
  sp.call("mkdir -p " + flow_settings['synth_folder'] + "\n", shell=True)
  sp.call("mkdir -p " + flow_settings['pr_folder'] + "\n", shell=True)
  sp.call("mkdir -p " + flow_settings['primetime_folder'] + "\n", shell=True)
  # Make sure we managed to read the design files
  assert len(processed_flow_settings["design_files"]) >= 1
  for clock_period in flow_settings['clock_period']:
    for wire_selection in flow_settings['wire_selection']:
      synth_report_str,syn_output_path = run_synth(processed_flow_settings,clock_period,wire_selection)
      for metal_layer in flow_settings['metal_layers']:
        for core_utilization in flow_settings['core_utilization']:
          #set the pnr flow to accept the correct name for flattened netlist
          pnr_report_str, pnr_output_path, total_area = run_pnr(processed_flow_settings,metal_layer,core_utilization,synth_report_str,syn_output_path)
          mode_enabled = True if len(flow_settings['mode_signal']) > 0 else False
          the_power = 0.0
          # Optional: use modelsim to generate an activity file for the design:
          # if flow_settings['generate_activity_file'] is True:
          #   run_sim()
          #loops over every combination of user inputted modes to set the set_case_analysis value (determines value of mode mux)
          for x in range(0, 2**len(flow_settings['mode_signal']) + 1):
            library_setup_time, data_arrival_time, total_delay, total_dynamic_power = run_power_timing(flow_settings,mode_enabled,clock_period,x,syn_output_path,pnr_report_str,pnr_output_path)
            # write the final report file:
            if mode_enabled and x <2**len(flow_settings['mode_signal']):
              file = open("report_mode" + str(x) + "_" + str(flow_settings['top_level']) + "_" + str(clock_period) + "_" + str(wire_selection) + "_wire_" + str(metal_layer) + "_" + str(core_utilization) + ".txt" ,"w")
            else:
              file = open("report_" + str(flow_settings['top_level']) + "_" + str(clock_period) + "_" + str(wire_selection) + "_wire_" + str(metal_layer) + "_" + str(core_utilization) + ".txt" ,"w")
            file.write("total area = "  + str(total_area[0]) +  " um^2 \n")
            file.write("total delay = " + str(total_delay) + " ns \n")
            file.write("total power = " + str(total_dynamic_power[0]) + " W \n")
            file.close()
            if total_dynamic_power[0] > the_power:
              the_power = total_dynamic_power[0]
            if lowest_cost > math.pow(float(total_area[0]), float(flow_settings['area_cost_exp'])) * math.pow(float(total_delay), float(flow_settings['delay_cost_exp'])):
              lowest_cost = math.pow(float(total_area[0]), float(flow_settings['area_cost_exp'])) * math.pow(float(total_delay), float(flow_settings['delay_cost_exp']))
              lowest_cost_area = float(total_area[0])
              lowest_cost_delay = float(total_delay)
              lowest_cost_power = float(the_power)
            del total_dynamic_power[:]
            del library_setup_time[:]
            del data_arrival_time[:]

  os.chdir(pre_func_dir)  
  return (float(lowest_cost_area), float(lowest_cost_delay), float(lowest_cost_power))


def gen_n_trav(dir_path):
  os.makedirs(dir_path,exist_ok=True)
  os.chdir(dir_path)


########################################## PARALLEL FLOW ##########################################

def get_params_from_str(param_dict,param_str):
  """
  Given a dict containing keys for valid parameters, and a string which contains parameters and thier values seperated by "_"
  This function will return a dict with valid parameter keys and values
  """
  out_dict = {}
  params = param_str.split("_")
  for idx, p in enumerate(params):
    if(p in list(param_dict.keys())):
      out_dict[p] = params[idx+1]
  return out_dict

def compare_run_filt_params_to_str(flow_settings,param_str):
  """
  This function compares the inputted string with run_params filters for the coresponding flow stage
  """
  if( "param_filters" in flow_settings["hb_run_params"].keys()):
    param_dict = get_params_from_str(flow_settings["input_param_options"],param_str)
    #we will parse the current directory param dict and check to see if it contains params outside of our run settings, if so skip the directory
    filt_match = 1
    for cur_key,cur_val in list(param_dict.items()):
      if cur_key in list(flow_settings["hb_run_params"]["param_filters"].keys()):
        if all(cur_val != val for val in flow_settings["hb_run_params"]["param_filters"][cur_key]):
          filt_match = 0
          break
  else:
    filt_match = 1
  #if returns 1, then the string is a valid combination of params, else 0
  return filt_match


def write_param_flow_stage_bash_script(flow_settings,param_path):
  """
  Writes a bash wrapper around the tcl script that needs to be run for this particular flow stage
  """
  flow_stage = param_path.split("/")[-2]
  flow_cmd = ""
  if(flow_stage == "synth"):
    script_rel_path = os.path.join("..","scripts", "dc_script.tcl")
    flow_cmd = get_dc_cmd(script_rel_path)
  elif(flow_stage == "pnr"):
    script_rel_path = os.path.join("..","scripts","_".join([flow_settings["top_level"],flow_settings["pnr_tool"]+".tcl"]))
    if(flow_settings["pnr_tool"] == "innovus"):
      flow_cmd = get_innovus_cmd(script_rel_path)
    elif(flow_settings["pnr_tool"] == "encounter"):
      flow_cmd = get_encounter_cmd(script_rel_path)
  elif(flow_stage == "sta"):
    if(flow_settings["partition_flag"]):
      flow_cmds = []
      for script in os.listdir(os.path.join(param_path,"scripts")):
        #if the script uses ptn generated netlist
        if("dimlen" in script):
          flow_cmds.append(get_sta_cmd(os.path.join("..","scripts",script)) + " &")
      flow_cmds.append("wait")
      flow_cmd = "\n".join(flow_cmds)
    else:
      script_rel_path = os.path.join("..","scripts", "pt_timing.tcl") #TODO fix the filename dependancy issues
      timing_cmd = get_sta_cmd(script_rel_path)
      flow_cmd = timing_cmd
      #script_rel_path = os.path.join("..","scripts", "primetime_power.tcl") #TODO fix the filename dependancy issues
      #power_cmd = get_sta_cmd(script_rel_path)
      #flow_cmd = "\n".join([timing_cmd,power_cmd])
  if(flow_cmd == ""):
    return
  file_lines = [
    "#!/bin/bash",
    "cd " + os.path.join(param_path,"work"),
    flow_cmd,
  ]
  fd = open(param_path.split("/")[-1] + "_" + flow_stage + "_run_parallel.sh","w")  
  for line in file_lines:
    file_write_ln(fd,line)
  fd.close()

def write_top_lvl_parallel_bash_script(parallel_script_path):
  #this writes a top_level script which runs each synthesis script for respective params in parallel
  script_fname = "top_level_parallel.sh"
  file_lines = [
    "#!/bin/bash"
    ]  
  for f in os.listdir(parallel_script_path):
    if(os.path.isfile(os.path.join(parallel_script_path,f) )):
      file_lines.append(os.path.join(parallel_script_path,f) + " &")
  file_lines.append("wait")
  fd = open(script_fname,"w")
  for line in file_lines:
    file_write_ln(fd,line)
  fd.close()

def write_parallel_scripts(flow_settings,top_level_path):
  """
  Writes script for each existing parameter directory in each flow stage, 
  Writes a top level script to call all of the parameter directory scripts
  """
  os.chdir(top_level_path)
  #CWD Ex. asic_work/router_wrap
  for flow_stage_dir in os.listdir(top_level_path):
    parallel_work_dir = flow_stage_dir + "_parallel_work"
    os.chdir(flow_stage_dir)
    flow_path = os.getcwd()
    #CWD Ex. asic_work/router_wrap/synth
    gen_n_trav(parallel_work_dir)
    gen_n_trav("scripts")
    #clean existing bash scripts
    sh_scripts = glob.glob("*.sh")
    for s in sh_scripts:
      os.remove(s)
    for dir in os.listdir(flow_path):
      if(compare_run_filt_params_to_str(flow_settings,dir) and "period" in dir):  #TODO DEPENDANCY
        write_param_flow_stage_bash_script(flow_settings,os.path.join(flow_path,dir))
    os.chdir("..")
    write_top_lvl_parallel_bash_script("scripts")
    os.chdir(top_level_path)



def hardblock_script_gen(flow_settings):
  """
  This function will generate all ASIC flow scripts and run some basic environment/parameter checks to make sure the scripts will function properly but won't run any tools
  This function should be run into an asic_work directory which will have directory structure generated inside of it
  """
  print("Generating hardblock scripts...")
  pre_func_dir = os.getcwd()
  cur_env = os.environ.copy()
  processed_flow_settings = flow_settings
  flow_settings_pre_process(processed_flow_settings, cur_env)
  #Generate the parallel work directory if it doesn't exist and move into it
  gen_n_trav(flow_settings["parallel_hardblock_folder"])

  #some constants for directory structure will stay the same for now (dont see a reason why users should be able to change this)
  synth_dir = "synth"
  pnr_dir = "pnr"
  sta_dir = "sta"
  #directories generated in each parameterized directory
  work_dir = "work" 
  script_dir = "scripts"
  outputs_dir = "outputs"
  reports_dir = "reports"

  parameterized_subdirs = [work_dir,script_dir,outputs_dir,reports_dir]

  assert len(processed_flow_settings["design_files"]) >= 1
  #create top level directory, synth dir traverse to synth dir
  gen_n_trav(flow_settings["top_level"])
  top_abs_path = os.getcwd()
  gen_n_trav(synth_dir)
  synth_abs_path = os.getcwd()
  for clock_period in flow_settings["clock_period"]:
    for wire_selection in flow_settings['wire_selection']:
      os.chdir(synth_abs_path)
      parameterized_synth_dir = "_".join(["period",clock_period,"wiremdl",wire_selection])
      gen_n_trav(parameterized_synth_dir)
      #generate subdirs in parameterized dir
      for d in parameterized_subdirs:
        os.makedirs(d, exist_ok=True)
      os.chdir(script_dir)
      #synthesis script generation
      syn_report_path, syn_output_path = write_synth_tcl(flow_settings,clock_period,wire_selection,rel_outputs=True)
      #the next stage will traverse into pnr directory so we want to go back to top level
      os.chdir(top_abs_path)
      gen_n_trav(pnr_dir)
      pnr_abs_path = os.getcwd()
      for metal_layer in flow_settings['metal_layers']:
          for core_utilization in flow_settings['core_utilization']:
            os.chdir(pnr_abs_path)
            #expect to be in pnr dir
            parameterized_pnr_dir = parameterized_synth_dir + "_" + "_".join(["mlayer",metal_layer,"util",core_utilization])
            gen_n_trav(parameterized_pnr_dir)
            param_pnr_path = os.getcwd()   
            #generate subdirs in parameterized dir
            os.chdir(param_pnr_path)
            for d in parameterized_subdirs:
              os.makedirs(d,exist_ok=True)
            os.chdir(script_dir)
            #this list will tell the sta section how many scripts it needs to make
            ptn_dirs = []
            dim_strs = []
            #clean existings scripts
            prev_scripts = glob.glob("./*.tcl")
            for file in prev_scripts:
              os.remove(file)
            # if(flow_settings["pnr_tool"] == "encounter"):
            #   #write encounter scripts
            #   write_enc_script(flow_settings,metal_layer,core_utilization)
            # elif(flow_settings["pnr_tool"] == "innovus"):

            #write generic innovus scripts
            view_fpath = write_innovus_view_file(flow_settings,syn_output_path)
            init_script_fname = write_innovus_init_script(flow_settings,view_fpath,syn_output_path)
            innovus_script_fname,pnr_output_path = write_innovus_script(flow_settings,metal_layer,core_utilization,init_script_fname,rel_outputs=True)

            #TODO below command could be done with the dbGet, which makes it more general 
            #top.terms.name (then looking at parameters for network on chip verilog to determine number of ports per edge)
            if(flow_settings["partition_flag"]):
              offsets = write_edit_port_script_pre_ptn(flow_settings)

              #initializing floorplan settings
              scaled_dims_list = []
              for scale in flow_settings["ptn_params"]["top_settings"]["scaling_array"]:
                ptn_info_list = flow_settings["ptn_params"]["partitions"]
                ptn_block_list = [ptn["mod_name"] for ptn in ptn_info_list]
                #overall floorplan 
                new_dim_pair = [dim*scale for dim in flow_settings["ptn_params"]["top_settings"]["fp_init_dims"]]
                scaled_dims_list.append(new_dim_pair)
              
              for dim_pair in scaled_dims_list:
                #creates initial floorplan
                fp_script_fname, fp_save = write_innovus_fp_script(flow_settings,metal_layer,init_script_fname,dim_pair)
                #creates partitions
                ptn_script_fname = write_innovus_ptn_script(flow_settings,init_script_fname,fp_save,offsets,dim_pair,auto_assign_regs=True)
                
                for block_name in ptn_block_list:
                  #runs pnr on subblock ptn
                  write_innovus_ptn_block_flow(metal_layer,os.path.splitext(ptn_script_fname)[0],block_name)
                #runs pnr on top level module ptn
                write_innovus_ptn_top_level_flow(metal_layer,os.path.splitext(ptn_script_fname)[0],flow_settings["top_level"])
                #assembles parititons and gets results
                #to make it easier to parse results we want to create an output dir for each set of params
                ptn_dir, report_path, output_path = write_innovus_assemble_script(flow_settings,os.path.splitext(ptn_script_fname)[0],ptn_block_list,flow_settings["top_level"])
                ptn_dirs.append(ptn_dir)
                dim_strs.append(str(dim_pair[0]))
                os.makedirs(os.path.join(report_path,ptn_dir), exist_ok=True)
                os.makedirs(os.path.join(output_path,ptn_dir), exist_ok=True)

            os.chdir(top_abs_path)
            gen_n_trav(sta_dir)
            sta_abs_dir = os.getcwd()
            #this cycles through all modes of the design
            for mode in range(0, 2**len(flow_settings['mode_signal']) + 1):
              os.chdir(sta_abs_dir)
              mode_enabled = True if (len(flow_settings['mode_signal']) > 0) else False
              if mode_enabled:
                parameterized_sta_dir = parameterized_pnr_dir + "_" + "_".join(["mode",str(mode)])
              else:
                parameterized_sta_dir = parameterized_pnr_dir
              gen_n_trav(parameterized_sta_dir)
              #generate subdirs in parameterized dir
              for d in parameterized_subdirs:
                os.makedirs(d, exist_ok=True)
              os.chdir(script_dir)
              #clean existings scripts
              prev_scripts = glob.glob("./*.tcl")
              for file in prev_scripts:
                os.remove(file)
              if(flow_settings["partition_flag"]):
                for dim_str,ptn_dir in zip(dim_strs,ptn_dirs):
                  timing_fname = "dimlen_" + dim_str + "_" + "pt_timing.tcl"
                  power_fname = "dimlen_" + dim_str + "_" + "primetime_power.tcl"
                  fpath ,report_path = write_pt_power_timing_script(flow_settings,timing_fname,mode_enabled,clock_period,mode,syn_output_path,os.path.join(pnr_output_path,ptn_dir),rel_outputs=True)
                  #write_pt_power_script(flow_settings,power_fname,mode_enabled,clock_period,mode,os.path.join(pnr_output_path,ptn_dir),rel_outputs=True)
              else:
                fpath,report_path = write_pt_power_timing_script(flow_settings,"pt_timing.tcl",mode_enabled,clock_period,mode,syn_output_path,pnr_output_path,rel_outputs=True)
                #write_pt_power_script(flow_settings,"primetime_power.tcl",mode_enabled,clock_period,mode,pnr_output_path,rel_outputs=True)
  
  write_parallel_scripts(flow_settings,top_abs_path)
  os.chdir(pre_func_dir)
########################################## PARALLEL FLOW ##########################################
########################################## PLL RUN FUNCS  ##########################################

def run_inn_dim_specific_pnr_cmd_series(inn_command_series):
  """
  runs innovus commands for a list of dimension specific partition commands grouped in order of execution
  """
  for dim_cmds in inn_command_series:
    if(isinstance(dim_cmds,list) and len(dim_cmds) > 1):
      for cmd in dim_cmds:
        run_shell_cmd_no_logs(get_innovus_cmd(cmd))
    else:
      run_shell_cmd_no_logs(get_innovus_cmd(dim_cmds))

def run_pll_flow_stage(parallel_work_path):
  """
  Runs a single stage of the parallel flow Ex. synth, pnr, or sta
  """
  # scripts will be executed in parallel fashion based on parameters in hardblock_settings file and will execute all scripts in parallel
  os.chdir(parallel_work_path)
  #setup the scripts to be able to run
  pll_scripts = glob.glob(os.path.join(parallel_work_path,"scripts","*"))
  pll_scripts.append("top_level_parallel.sh")
  for s in pll_scripts:
    os.chmod(s,stat.S_IRWXU)

  #Runs the parallel synthesis across params
  #top_pll_cmds = ["top_level_parallel.sh"]
  # commented above command, as the below function expects str TODO make sure this is ok
  top_pll_cmds = "./top_level_parallel.sh"

  ret_code = run_shell_cmd_safe_no_logs(top_pll_cmds)

  # stdout, stderr = run_shell_cmd_no_logs(top_pll_cmds)
  # parallel_p = sp.Popen(top_pll_cmds, stdout=sp.PIPE, stderr=sp.PIPE)
  # stdout, stderr = parallel_p.communicate()


# PARALLEL FLOW
def hardblock_script_gen(flow_settings):
  """
  This function will generate all ASIC flow scripts and run some basic environment/parameter checks to make sure the scripts will function properly but won't run any tools
  This function should be run into an asic_work directory which will have directory structure generated inside of it
  """
  print("Generating hardblock scripts...")
  pre_func_dir = os.getcwd()
  cur_env = os.environ.copy()
  processed_flow_settings = flow_settings
  flow_settings_pre_process(processed_flow_settings,cur_env)
  #Generate the parallel work directory if it doesn't exist and move into it
  gen_n_trav(flow_settings["parallel_hardblock_folder"])

  #some constants for directory structure will stay the same for now (dont see a reason why users should be able to change this)
  synth_dir = "synth"
  pnr_dir = "pnr"
  sta_dir = "sta"
  #directories generated in each parameterized directory
  work_dir = "work" 
  script_dir = "scripts"
  outputs_dir = "outputs"
  reports_dir = "reports"

  parameterized_subdirs = [work_dir,script_dir,outputs_dir,reports_dir]

  assert len(processed_flow_settings["design_files"]) >= 1
  #create top level directory, synth dir traverse to synth dir
  gen_n_trav(flow_settings["top_level"])
  top_abs_path = os.getcwd()
  gen_n_trav(synth_dir)
  synth_abs_path = os.getcwd()
  for clock_period in flow_settings["clock_period"]:
    for wire_selection in flow_settings['wire_selection']:
      os.chdir(synth_abs_path)
      parameterized_synth_dir = "_".join(["period",clock_period,"wiremdl",wire_selection])
      gen_n_trav(parameterized_synth_dir)
      #generate subdirs in parameterized dir
      for d in parameterized_subdirs:
        os.makedirs(d, exist_ok=True)
      os.chdir(script_dir)
      #synthesis script generation
      syn_report_path, syn_output_path = write_synth_tcl(flow_settings,clock_period,wire_selection,rel_outputs=True)
      #the next stage will traverse into pnr directory so we want to go back to top level
      os.chdir(top_abs_path)
      gen_n_trav(pnr_dir)
      pnr_abs_path = os.getcwd()
      for metal_layer in flow_settings['metal_layers']:
          for core_utilization in flow_settings['core_utilization']:
            os.chdir(pnr_abs_path)
            #expect to be in pnr dir
            parameterized_pnr_dir = parameterized_synth_dir + "_" + "_".join(["mlayer",metal_layer,"util",core_utilization])
            gen_n_trav(parameterized_pnr_dir)
            param_pnr_path = os.getcwd()   
            #generate subdirs in parameterized dir
            os.chdir(param_pnr_path)
            for d in parameterized_subdirs:
              os.makedirs(d, exist_ok=True)
            os.chdir(script_dir)
            #this list will tell the sta section how many scripts it needs to make
            ptn_dirs = []
            dim_strs = []
            #clean existings scripts
            prev_scripts = glob.glob("./*.tcl")
            for file in prev_scripts:
              os.remove(file)
            # if(flow_settings["pnr_tool"] == "encounter"):
            #   #write encounter scripts
            #   write_enc_script(flow_settings,metal_layer,core_utilization)
            # elif(flow_settings["pnr_tool"] == "innovus"):

            #write generic innovus scripts
            view_fpath = write_innovus_view_file(flow_settings,syn_output_path)
            init_script_fname = write_innovus_init_script(flow_settings,view_fpath,syn_output_path)
            innovus_script_fname,pnr_output_path = write_innovus_script(flow_settings,metal_layer,core_utilization,init_script_fname,rel_outputs=True)

            #TODO below command could be done with the dbGet, which makes it more general 
            #top.terms.name (then looking at parameters for network on chip verilog to determine number of ports per edge)
            if(flow_settings["partition_flag"]):
              offsets = write_edit_port_script_pre_ptn(flow_settings)

              #initializing floorplan settings
              scaled_dims_list = []
              for scale in flow_settings["ptn_params"]["top_settings"]["scaling_array"]:
                ptn_info_list = flow_settings["ptn_params"]["partitions"]
                ptn_block_list = [ptn["mod_name"] for ptn in ptn_info_list]
                #overall floorplan 
                new_dim_pair = [dim*scale for dim in flow_settings["ptn_params"]["top_settings"]["fp_init_dims"]]
                scaled_dims_list.append(new_dim_pair)
              
              for dim_pair in scaled_dims_list:
                #creates initial floorplan
                fp_script_fname, fp_save = write_innovus_fp_script(flow_settings,metal_layer,init_script_fname,dim_pair)
                #creates partitions
                ptn_script_fname = write_innovus_ptn_script(flow_settings,init_script_fname,fp_save,offsets,dim_pair,auto_assign_regs=True)
                
                for block_name in ptn_block_list:
                  #runs pnr on subblock ptn
                  write_innovus_ptn_block_flow(metal_layer,os.path.splitext(ptn_script_fname)[0],block_name)
                #runs pnr on top level module ptn
                write_innovus_ptn_top_level_flow(metal_layer,os.path.splitext(ptn_script_fname)[0],flow_settings["top_level"])
                #assembles parititons and gets results
                #to make it easier to parse results we want to create an output dir for each set of params
                ptn_dir, report_path, output_path = write_innovus_assemble_script(flow_settings,os.path.splitext(ptn_script_fname)[0],ptn_block_list,flow_settings["top_level"])
                ptn_dirs.append(ptn_dir)
                dim_strs.append(str(dim_pair[0]))
                os.makedirs(os.path.join(report_path,ptn_dir), exist_ok=True)
                os.makedirs(os.path.join(output_path,ptn_dir), exist_ok=True)

            os.chdir(top_abs_path)
            gen_n_trav(sta_dir)
            sta_abs_dir = os.getcwd()
            #this cycles through all modes of the design
            for mode in range(0, 2**len(flow_settings['mode_signal']) + 1):
              os.chdir(sta_abs_dir)
              mode_enabled = True if (len(flow_settings['mode_signal']) > 0) else False
              if mode_enabled:
                parameterized_sta_dir = parameterized_pnr_dir + "_" + "_".join(["mode",str(mode)])
              else:
                parameterized_sta_dir = parameterized_pnr_dir
              gen_n_trav(parameterized_sta_dir)
              #generate subdirs in parameterized dir
              for d in parameterized_subdirs:
                os.makedirs(d, exist_ok=True)
              os.chdir(script_dir)
              #clean existings scripts
              prev_scripts = glob.glob("./*.tcl")
              for file in prev_scripts:
                os.remove(file)
              if(flow_settings["partition_flag"]):
                for dim_str,ptn_dir in zip(dim_strs,ptn_dirs):
                  timing_fname = "dimlen_" + dim_str + "_" + "pt_timing.tcl"
                  power_fname = "dimlen_" + dim_str + "_" + "primetime_power.tcl"
                  fpath ,report_path = write_pt_power_timing_script(flow_settings,timing_fname,mode_enabled,clock_period,mode,syn_output_path,os.path.join(pnr_output_path,ptn_dir),rel_outputs=True)
                  #write_pt_power_script(flow_settings,power_fname,mode_enabled,clock_period,mode,os.path.join(pnr_output_path,ptn_dir),rel_outputs=True)
              else:
                fpath,report_path = write_pt_power_timing_script(flow_settings,"pt_timing.tcl",mode_enabled,clock_period,mode,syn_output_path,pnr_output_path,rel_outputs=True)
                #write_pt_power_script(flow_settings,"primetime_power.tcl",mode_enabled,clock_period,mode,pnr_output_path,rel_outputs=True)
  
  write_parallel_scripts(flow_settings,top_abs_path)
  os.chdir(pre_func_dir)

def hardblock_parallel_flow(flow_settings):
  pre_flow_dir = os.getcwd()
  #This expects cwd to be asic_work
  hardblock_script_gen(flow_settings)
  #make sure to be in the parallel_hardblock_folder
  os.chdir(flow_settings["parallel_hardblock_folder"])
  
  flow_stages = ["synth","pnr","sta"] 
  ########################### PARALLEL SYNTHESIS SECTION ###########################
  if flow_settings["hb_run_params"]["synth"]["run_flag"]:
    print("Running synthesis scripts in parallel...")
    synth_parallel_work_path = os.path.join(flow_settings["parallel_hardblock_folder"],flow_settings["top_level"],"synth","synth_parallel_work")
    run_pll_flow_stage(synth_parallel_work_path)
  ########################### PARALLEL SYNTHESIS SECTION ###########################
  ########################### PARALLEL PNR SECTION #################################
  if flow_settings["hb_run_params"]["pnr"]["run_flag"]:
    print("Running pnr scripts in parallel...")
    #below path should point to pnr directory in pll flow folder
    pnr_parallel_path = os.path.join(flow_settings["parallel_hardblock_folder"],flow_settings["top_level"],"pnr")
    if(flow_settings["partition_flag"]):
      #DEPENDANCY OF PTN PNR SCRIPTS
      # run_gen_blocks for each ptn block in design [] denotes parallelism
      # gen_fp(dim) -> gen_ptns(dim) -> [gen_blocks(dim)]  -> pnr(top_lvl) -> assemble(all_parts_of_design) 
      #if override outputs is set 
      #pre_processing for filtering ptn commands by specified settings
      #floorplan x dimension (this is used in the filename of generated scripts/outputs/reports)
      fp_dim = float(flow_settings["ptn_params"]["top_settings"]["fp_init_dims"][0])
      #get factors which we are scaling the initial dimension value with
      scaling_array = [float(fac) for fac in flow_settings["ptn_params"]["top_settings"]["scaling_array"]]
      #multiplies initial dimension to find the filenames of all dims we wish to run
      scaled_dims = [fp_dim*fac for fac in scaling_array]
      os.chdir(pnr_parallel_path)
      for param_dir in os.listdir(pnr_parallel_path):
        #traverse into pnr directory for a particular set of run parameters
        os.chdir(param_dir)
        #continue flag will skip the parameterized directory if it is outside of the user inputted filtering settings
        continue_flag = False
        # TODO this needs to check if the parameter dir is actually a param dir, to be quality it should make sure all parameters in the input param dict are present in filename
        if("period" not in param_dir): 
          os.chdir(pnr_parallel_path)
          continue
        #Before anything else use filter to only run the selected params:
        #get a dict of the current directories parameter settings
        param_dict = get_params_from_str(flow_settings["input_param_options"],param_dir)
        #we will parse the current directory param dict and check to see if it contains params outside of our run settings, if so skip the directory
        for cur_key,cur_val in list(param_dict.items()):
          if cur_key in list(flow_settings["hb_run_params"]["param_filters"].keys()):
            if all(cur_val != val for val in flow_settings["hb_run_params"]["param_filters"][cur_key]):
              continue_flag = True
              break

        #if the cur directory was outside of the run params, continue...
        if(continue_flag):
          os.chdir(pnr_parallel_path)
          continue

        #First group the scripts according to their floorplan dimensions
        dim_grouped_scripts = []
        for dim in scaled_dims:
          dim_group = [f for f in os.listdir("scripts") if str(dim) in f]
          dim_grouped_scripts.append(dim_group)
        #Now group according to order of execution
        order_of_exec_pnr_per_dim = []
        for group in dim_grouped_scripts:
          #TODO create filename data structure to prevent below fname dependancies
          fp_gen_script = [f for f in group if "fp_gen" in f]
          ptn_script = [f for f in group if "ptn.tcl" in f]
          block_scripts = [f for f in group if "block" in f]
          toplvl_script = [f for f in group if "toplvl" in f]
          assembly_script = [f for f in group if "assembly" in f]
          order_of_exec_pnr_scripts = [fp_gen_script,ptn_script,block_scripts,toplvl_script,assembly_script]
          order_of_exec_pnr_scripts = [e[0] if len(e) == 1 else e for e in order_of_exec_pnr_scripts]
          order_of_exec_pnr_per_dim.append(order_of_exec_pnr_scripts)

        #change to work directory to prepare to execute scripts
        os.chdir("work")
        output_dir = os.path.join("..","outputs")

        cmd_series_list = []
        
        #Filter out innovus commands if the intermediary files already exist
        for inn_command_series in order_of_exec_pnr_per_dim:
          
          #filter out commands which are out of bounds of our dims we want to evaluate
          # if not any(str(dim) in inn_command_series[0] for dim in scaled_dims):
            # print("dim out of dimension list, not running %s... " % (inn_command_series[0]))
            # continue

          #if override outputs is selected the script will not check for intermediate files in the ptn flow and will start from the beginning
          if(not flow_settings["hb_run_params"]["pnr"]["override_outputs"]):
            #if theres already an assembled design saved for the fp flow skip it
            saved_design = os.path.join(output_dir,os.path.splitext(inn_command_series[1])[0]+"_assembled.dat")
            if(os.path.exists(saved_design)):
              print(("found %s, Skipping..." % (saved_design)))
              # print(os.getcwd())
              continue

            #if top level flow has been run only run the assembly
            saved_tl_imp = os.path.join(os.path.splitext(inn_command_series[1])[0],flow_settings["top_level"],flow_settings["top_level"]+"_imp")

            #if partition flow has been run only run top lvl + assembly
            ptn_dir = os.path.join(os.path.splitext(inn_command_series[1])[0])
            
            cmds = []
            #loop through commands for this fp size and group the lists s.t they are in the following format:
            #cmds = [fp_gen.tcl, ptn.tcl, [blk1.tcl, blk2.tcl, ...],top_lvl.tcl, assemble.tcl]
            for cmd in inn_command_series:
              if(isinstance(cmd,str)):
                cmds.append(os.path.join("..","scripts",cmd))
              elif(isinstance(cmd,list)):
                blk_cmds = [os.path.join("..","scripts",blk_cmd) for blk_cmd in cmd]
                cmds.append(blk_cmds)
            #if there is a top level implementation, we can delete all commands leading up to assembly script
            if(os.path.isfile(saved_tl_imp)):
              print("found top level imp, running only assembly")
              print((os.getcwd()))
              del cmds[0:3]
            #if there is a ptn directory, we can delete all commands leading up to block level flow
            elif(os.path.isdir(ptn_dir)):
              print("found ptn dir, running only blocks + toplvl + assembly")
              print((os.getcwd()))
              del cmds[0:2]
            cmd_series_list.append(cmds)
          else:
            #if the user selected to override all outputs
            cmd_series_list = []
            for cmd_series in order_of_exec_pnr_per_dim:
              cmds = []
              for cmd in cmd_series:
                if(isinstance(cmd,str)):
                  cmds.append(os.path.join("..","scripts",cmd))
                elif(isinstance(cmd,list)):
                  blk_cmds = [os.path.join("..","scripts",blk_cmd) for blk_cmd in cmd]
                  cmds.append(blk_cmds)
              cmd_series_list.append(cmds)
              
        #At this point the cmd_series_list should be in the following format
        #cmd_series_list = [[fp_gen_dimx.tcl, ptn_dimx.tcl, [blk1_dimx.tcl, blk2_dimx.tcl, ...],top_lvl_dimx.tcl, assemble_dimx.tcl],[fp_gen_dimx.tcl, ...], ...]
        pool = mp.Pool(int(flow_settings["mp_num_cores"]))
        #execute all scripts according to order in list
        pool.map(run_inn_dim_specific_pnr_cmd_series,cmd_series_list)
        pool.close()
        os.chdir(pnr_parallel_path)
    else:
      #If not running partitioning, pnr scripts will be executed in parallel fashion based on parameters in hardblock_settings file and will execute all scripts in parallel
      pnr_parallel_work_path = os.path.join(flow_settings["parallel_hardblock_folder"],flow_settings["top_level"],"pnr","pnr_parallel_work")
      run_pll_flow_stage(pnr_parallel_work_path)
  ########################### PARALLEL PNR SECTION #################################
  ########################### PARALLEL STA SECTION #################################
  if(flow_settings["hb_run_params"]["sta"]["run_flag"]):
    print("Running sta scripts in parallel...")
    sta_parallel_work_path = os.path.join(flow_settings["parallel_hardblock_folder"],flow_settings["top_level"],"sta","sta_parallel_work")
    run_pll_flow_stage(sta_parallel_work_path)
  ########################### PARALLEL STA SECTION #################################
  

  # TODO integrate parallel output parsing function and lowest cost function to return the best parameter run for parallel flow

  #hardblock flow stuff
  # lowest_cost = sys.float_info.max
  # lowest_cost_area = 1.0
  # lowest_cost_delay = 1.0
  # lowest_cost_power = 1.0
  
  os.chdir(pre_flow_dir)
  # return (float(lowest_cost_area), float(lowest_cost_delay), float(lowest_cost_power))


########################################## PLL PARSE/PLOT RESULTS UTILS ##########################################

def find_lowest_cost_in_result_dict(flow_settings,result_dict):
  """
  Finds the lowest cost flow result for parameter combinations for each stage of the asic flow,
  uses result dict returned by parse_parallel_outputs
  """
  #values required for each stage to be able to make this work
  req_values = {
    "synth": ["delay","power","area"],
    "pnr": ["delay","power","area"],
    "sta": ["delay","power"]
  }

  lowest_cost_dicts = {}
  
  for flow_type, flow_dict in list(result_dict.items()):
    param_str = ""
    lowest_cost_dict = {}
    lowest_cost_dicts[flow_type] = {}
    lowest_cost = sys.float_info.max
    lowest_cost_area = 0.0
    lowest_cost_delay = 0.0
    lowest_cost_power = 0.0
    if(flow_type == "synth" or flow_type == "pnr"):
      for run_params, param_result_dict in list(flow_dict.items()):
        total_delay = param_result_dict["delay"]
        total_power = param_result_dict["power"]
        total_area = param_result_dict["area"]
        cur_cost = math.pow(float(total_area), float(flow_settings['area_cost_exp'])) * math.pow(float(total_delay), float(flow_settings['delay_cost_exp']))
        result_dict[flow_type][run_params]["cost"] = cur_cost
        #if cost is higher than lower, create new lowest
        if lowest_cost > cur_cost:
          param_str = run_params
          lowest_cost = cur_cost
          lowest_cost_area = total_area
          lowest_cost_delay = total_delay
          lowest_cost_power = total_power
      
      lowest_cost_dict["area"] = lowest_cost_area
      lowest_cost_dict["delay"] = lowest_cost_delay
      lowest_cost_dict["power"] = lowest_cost_power
      lowest_cost_dict["cost"] = lowest_cost
      lowest_cost_dict["run_params"] = param_str
      lowest_cost_dicts[flow_type] = lowest_cost_dict
    
  return lowest_cost_dicts


def decode_dict_dtypes(param_dtype_dict,param_key,val):
  """
  From an inputted dict contatining params as keys and strings of datatypes as values, its key, and a value one would like to convert,
  return the appropriately converted datatype of value
  """    
  dtype_conv = param_dtype_dict[param_key]
  ret_val = None
  if(val == "NA"):
    ret_val = "NA"
  elif(dtype_conv == "str"):
    ret_val = str(val)
  elif(dtype_conv == "float"):
    ret_val = float(val)
  elif(dtype_conv == "int"):
    ret_val = int(val)
  elif(dtype_conv == "bool"):
    ret_val = bool(val)

  return ret_val


def parse_power_file(report_file,flow_dir,dict_entry,out_dict,decimal_re):
  #power report
  fd = open(report_file,"r")
  total_power = None #TODO FIX THIS
  for line in fd:
    if(flow_dir == "sta" or flow_dir == "synth"):
      if 'Total Dynamic Power' in line:
        total_power = re.findall(r'\d+\.{0,1}\d*', line)
        total_power = float(total_power[0])
        if 'mW' in line:
          total_power *= 0.001
        elif 'uW' in line:
          total_power *= 0.000001
        elif 'W' in line:
          total_power = total_power
        else:
          total_power = 0.0
    elif(flow_dir == "pnr"):
      if("Total Power:" in line):
        total_power = float(decimal_re.search(line).group(0))
      if("Power Units" in line):
        if 'mW' in line:
          power_fac = 0.001
        elif 'uW' in line:
          power_fac = 0.000001
        elif 'W' in line:
          power_fac = 1.0

  if(total_power != None):
    if(flow_dir == "pnr"):        
      total_power *= power_fac
    out_dict[flow_dir][dict_entry]["power"] = float(truncate(total_power,3)) #if total_power != "NA" else "NA"
  fd.close()
  return dict_entry

def parse_area_file(flow_settings,report_file,flow_dir,dict_entry,out_dict,log_file_fd):
  #Below is the index at which the value for total area will be found in either synth or pnr report file
  area_idx = -2 if (flow_dir == "pnr") else 1
  area=None
  #Area report
  fd = open(report_file,"r")
  for line in fd:
    if(flow_settings["top_level"] in line):
      area = re.split(r"\s+",line)[area_idx]
  if(area != None):
    out_dict[flow_dir][dict_entry]["area"] = float(area)
  fd.close()

def parse_timing_file(report_file,flow_dir,dict_entry,timing_mode,out_dict,decimal_re,log_file_fd):
  #init values for setup timing variables
  arrival_time = None
  lib_setup_time = None

  timing_met_re = re.compile(r"VIOLATED")
  if(flow_dir == "synth" or flow_dir == "sta"):
    arrival_time_str = "data arrival time"
    lib_setup_time_str = "library setup time"    
  elif(flow_dir == "pnr"):
    arrival_time_str = "- Arrival Time"
    lib_setup_time_str = "Setup"
  
  #timing report
  fd = open(report_file,"r")
  text = fd.read()
  if("setup" in timing_mode):

    #look for delay info (only if looking at setup)
    for line in text.split("\n"):
      if(arrival_time_str in line):
        arrival_time = float(decimal_re.findall(line)[0])
      elif(lib_setup_time_str in line):
        lib_setup_time = float(decimal_re.findall(line)[0])
    if(arrival_time == None or lib_setup_time == None):
      file_write_ln(log_file_fd,"\n".join(["Could not find arrival/setup time variables for param:",dict_entry,"At path:",os.path.join(os.getcwd(),report_file)]))
    else:
      total_del = arrival_time + lib_setup_time
      out_dict[flow_dir][dict_entry]["delay"] = float(truncate(total_del,3))
  if(timing_met_re.search(text)):
    timing_met = False
  else:
    timing_met = True
  out_dict[flow_dir][dict_entry]["timing_met_"+timing_mode] = timing_met
  fd.close()
  return dict_entry

def check_for_valid_report(report_path):
  ret_val = True
  invalid_re = re.compile("Error")
  fd = open(report_path,"r")
  text = fd.read()
  if(invalid_re.search(text)):
    ret_val = False
  fd.close()

  return ret_val    


def get_dict_entry(report_file,parameterized_dir,report_str):
  cwd = os.getcwd()
  #find if this is occuring in a subreport directory or a parameterized dir
  if(cwd.split("/")[-1] == "reports"): #TODO fix structure dependancy
    dict_entry  = parameterized_dir + "_" + re.sub(string=os.path.basename(os.path.splitext(report_file)[0]),pattern=report_str,repl="")
  elif(cwd.split("/")[-2] == "reports"):
    dict_entry  = parameterized_dir + "_" + cwd.split("/")[-1] + "_"
  else:
    print("unrecognized directory structure, exiting...")
    sys.exit(1)
  
  return dict_entry

def parse_report(flow_settings,report_file,flow_dir,parameterized_dir,out_dict,log_fd,param_dtype_dict):
  decimal_re = re.compile(r"\d+\.{0,1}\d*")
  area_str = "area"
  power_str = "power"
  dict_entry = ""

  # rep_fd = open(report_file,"r")
  # rep_lines = rep_fd.read().split("\n")
  # print(os.path.join(os.getcwd(),report_file))
  if("area" in report_file and ".rpt" in report_file):
    #Area parsing
    #get key value for this set of params
    dict_entry = get_dict_entry(report_file,parameterized_dir,area_str)
    if(dict_entry not in out_dict[flow_dir]):
      out_dict[flow_dir][dict_entry] = {}
    parse_area_file(flow_settings,report_file,flow_dir,dict_entry,out_dict,log_fd)
  elif("timing" in report_file and ".rpt" in report_file):
    #check to see what timing mode file is reporting
    if("setup" in report_file):
      timing_mode = "setup"
      timing_str = timing_mode + "_" + "timing"
    elif("hold" in report_file):
      timing_mode = "hold"
      timing_str = timing_mode + "_" + "timing"
    # This is to deal with old synthesis script producing a "timing" filename for setup report
    # TODO remove, I added the hold timing check script to synthesis so shouldnt be an issue unless using old results
    else:
      timing_mode = "setup"
      timing_str = "timing"

    dict_entry = get_dict_entry(report_file,parameterized_dir,timing_str)
    if(dict_entry not in out_dict[flow_dir]):
      out_dict[flow_dir][dict_entry] = {}
    parse_timing_file(report_file,flow_dir,dict_entry,timing_mode,out_dict,decimal_re,log_fd)
  elif("power" in report_file and ".rpt" in report_file):
    dict_entry = get_dict_entry(report_file,parameterized_dir,power_str)
    # print(dict_entry)
    if(dict_entry not in out_dict[flow_dir]):
      out_dict[flow_dir][dict_entry] = {}
    dict_entry = parse_power_file(report_file,flow_dir,dict_entry,out_dict,decimal_re)
  #This writes the rest of the input params to the dict entry (parsed from the dict_entry)
  if(dict_entry != ""):
    # print("dict_entry: %s" % (dict_entry))
    #assign top level to dict entry if doesnt exist
    out_dict[flow_dir][dict_entry]["top_level"] = flow_settings["top_level"]
    #grabbing link dimensions from the fname
    dict_ent_params = dict_entry.split("_")
    for idx,e in enumerate(dict_ent_params):
      if(e in list(param_dtype_dict.keys())):
        out_dict[flow_dir][dict_entry][e] = decode_dict_dtypes(param_dtype_dict,e,dict_ent_params[idx+1]) 

def parse_parallel_outputs(flow_settings):
  """
  This function parses the ASIC results directory created after running scripts generated from option of coffe flow
  """
  #Directory structure of the parallel results is as follows:
  #results_dir: 
  #--->synth
  #-------->parameterized_folder
  #------------>outputs
  #------------>reports
  #------------>work
  #------------>scripts
  #--->pnr
  #......Same as above structure....
  #--->sta
  #......Same as above structure....
  pre_func_dir = os.getcwd()
  report_csv_fname = "condensed_pll_results.csv"
  os.makedirs(flow_settings["condensed_results_folder"], exist_ok=True)
  parse_pll_outputs_log_file = os.path.join(flow_settings["condensed_results_folder"],"parse_pll_outputs.log")
  log_fd = open(parse_pll_outputs_log_file,"w")
  #this dict will contain values parsed from pll outputs
  out_dict = {
    "pnr": {},
    "synth": {},
    "sta": {}
  }
  #this dict contains all parameters and their datatypes which will be used as keys in output dict
  param_dtype_dict = {
    #input params
    "top_level": "str",
    "period" : "float",
    "wiremdl" : "str",
    "mlayer" : "int",
    "util" : "float",
    "dimlen" : "float",
    "mode" : "int",
    #output values
    "delay" : "float",
    "area" : "float",
    "power" : "float",
    "timing_met_setup" : "bool",
    "timing_met_hold" : "bool"
  }
  

  parallel_results_path = os.path.expanduser(flow_settings["parallel_hardblock_folder"])
  #for parsing decimal values in report directories

  valid_rpt_dir_re = re.compile("^dimlen_[0-9]+|\.[0-9]+_ptn$",re.MULTILINE)
  os.chdir(parallel_results_path)
  results_path = os.getcwd()
  #list containing an output dict for each top level module
  top_lvl_dicts = []
  for top_level_mod in os.listdir(os.getcwd()):
    if(top_level_mod != flow_settings["top_level"]):
      continue
    #filter out to only look at a single top level mod
    os.chdir(os.path.join(results_path,top_level_mod))
    top_level_mod_path = os.getcwd()
    for flow_dir in os.listdir(os.getcwd()):
      os.chdir(os.path.join(top_level_mod_path,flow_dir))
      flow_path = os.getcwd()
      for parameterized_dir in os.listdir(os.getcwd()):
        if("period" not in parameterized_dir): #TODO fix dir name dependancy
          continue
        # This would filter out any params that werent in current run set
        # if(not compare_run_filt_params_to_str(flow_settings,parameterized_dir)):
        #   continue
        os.chdir(os.path.join(flow_path,parameterized_dir))
        parameterized_path = os.getcwd()
        for dir in os.listdir(os.getcwd()):
          os.chdir(os.path.join(parameterized_path,dir))
          dir_path = os.getcwd()
          if(os.path.basename(dir_path) == "reports" and len(dir_path) > 0):
            for report_file in os.listdir(os.getcwd()):
              if(valid_rpt_dir_re.search(report_file) and os.path.isdir(report_file) and len(os.listdir(report_file)) > 0):
                os.chdir(report_file)
                for sub_report_file in os.listdir(os.getcwd()):
                  if(os.path.isfile(sub_report_file)):
                    parse_report(flow_settings,sub_report_file,flow_dir,parameterized_dir,out_dict,log_fd,param_dtype_dict)
                  else:
                    continue
                os.chdir(dir_path)
                continue                
              #checks to see if "Error" string is in the file, if so skip...
              elif(os.path.isfile(report_file) and not check_for_valid_report(report_file)):
                continue
              elif(os.path.isfile(report_file)):
                parse_report(flow_settings,report_file,flow_dir,parameterized_dir,out_dict,log_fd,param_dtype_dict)
  
  #remove the old str format files (they are old runs which dont have relevant results)
  for flow_key,flow_dict in list(out_dict.items()):
    # print("############################# %s :" %(flow_key))
    for param_key, val_out_dict in list(flow_dict.items()):
      # print("########### %s :" %(param_key))
      if( (("_ptn_" not in param_key or "mlayers" in param_key) and flow_key == "pnr" and flow_settings["partition_flag"] == True) or ()):
        # print("deleted %s" % (param_key))
        del out_dict[flow_key][param_key]
      # else:
        # for out_key, out_val in val_out_dict.items():
          # print( "%s : %s" % (out_key,out_val))
  #pass area and other params from pnr to sta

  #Generate output csv file which can be used by plotting script
  log_fd.close()
  write_pll_results_csv(param_dtype_dict,out_dict,os.path.join(flow_settings["condensed_results_folder"],report_csv_fname))
  os.chdir(pre_func_dir)
  return report_csv_fname,out_dict

def write_pll_results_csv(param_dtype_dict, out_dict, csv_fpath):
  fd = open(csv_fpath,"w")
  w = csv.writer(fd)
  #This is a csv of all flow types combined and seperated by a column name
  w.writerow(list(param_dtype_dict.keys()) + list(out_dict.keys()))
  for flow_type,flow_dict in list(out_dict.items()):
    flow_type_vals = [True if possible_flow == flow_type else False for possible_flow in list(out_dict.keys())]
    for param_key,param_dict in list(flow_dict.items()):
      csv_row = []
      for ref_result_key in list(param_dtype_dict.keys()):
        if(ref_result_key in list(param_dict.keys())):
          val = param_dict[ref_result_key]
        else:
          val = "NA"
        csv_row.append(val)
      csv_row = csv_row + flow_type_vals
      w.writerow(csv_row)
  fd.close()


def run_plot_script(flow_settings,report_csv_fname):
  """
  This function will run a python3 plotting script using a generated csv file from the parse_parallel_outputs() function
  Plots will be saved to the flow_settings[condensed_results_folder]
  """
  condensed_results_path = os.path.join(flow_settings["condensed_results_folder"],report_csv_fname)
  plot_script_fname = "run_plot_script.sh"
  analyze_results_dir=os.path.join(flow_settings["coffe_repo_path"],"analyze_results")
  plot_script_path=os.path.join(analyze_results_dir,plot_script_fname)
  req_paths = [plot_script_path,condensed_results_path,analyze_results_dir]
  exit_flag = 0
  for p in req_paths:
    if(not os.path.exists(p)):
      print(("Plotting function could not find file or directory: %s" % (p)))
      exit_flag = 1
  
  if(exit_flag):
    return -1
  if(flow_settings["partition_flag"]):  
    plot_script_cmd = " ".join([plot_script_path,"-p",condensed_results_path,analyze_results_dir,"-ptn"])
  else:
    plot_script_cmd = " ".join([plot_script_path,"-p",condensed_results_path,analyze_results_dir])
  run_shell_cmd_no_logs(plot_script_cmd)
  return 1

########################################## PLL PARSE/PLOT RESULTS UTILS ##########################################




def write_virtuoso_gds_to_area_script(rad_gen_settings: rg.HighLvlSettings, gds_fpath: str):
    # skill_fname = "get_area.il"
    skill_script_lines = [
        f"system(\"strmin -library {rad_gen_settings.tech_info.cds_lib} -strmFile {gds_fpath} -logFile strmIn.log\")",
        f'cv = dbOpenCellViewByType("asap7_TechLib" "TOPCELL" "layout")',
        "print(cv~>bBox)",
    ]
    skill_fpath = os.path.join(rad_gen_settings.tech_info.pdk_rundir_path, f"{rad_gen_settings.env_settings.scripts_info.gds_to_area_fname}.il")
    csh_fpath = os.path.join(rad_gen_settings.tech_info.pdk_rundir_path, f"{rad_gen_settings.env_settings.scripts_info.gds_to_area_fname}.csh")

    # TODO remove abs paths
    csh_script_lines = [
        "#!/bin/csh",
       f"source {rad_gen_settings.env_settings.scripts_info.virtuoso_setup_path} && virtuoso -nograph -replay {skill_fpath} -log get_area.log {skill_fpath} -log {rad_gen_settings.env_settings.scripts_info.gds_to_area_fname}.log"
    ]

    fd = open(skill_fpath, 'w')
    for line in skill_script_lines:
        file_write_ln(fd, line)
    fd.close()
    fd = open(csh_fpath, 'w')
    for line in csh_script_lines:
        file_write_ln(fd, line)
    fd.close()


def write_lc_lib_to_db_script(rad_gen_settings: rg.HighLvlSettings, in_libs_paths: List[str]):
    """ Takes in a list of abs paths for libs that need to be converted to .dbs """
    lc_script_name = "lc_lib_to_db.tcl"
    pt_outpath = os.path.join(rad_gen_settings.asic_flow_settings.obj_dir_path, "pt-rundir")
    db_lib_outpath = os.path.join(rad_gen_settings.env_settings.rad_gen_home_path, "sram_db_libs")
    if not os.path.isdir(pt_outpath):
        os.makedirs(pt_outpath)
    if not os.path.isdir(db_lib_outpath):
        os.makedirs(db_lib_outpath)
    lc_script_path = os.path.join(pt_outpath, lc_script_name)
    
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


def run_asap7_gds_scaling_scripts(rad_gen: rg.HighLvlSettings, obj_dir: str, top_lvl_mod: str):
    """
        This function will run gds scaling from the par outputs for asap7 pdk
        - It uses Cadence Virtuoso skill scripts to read in the gds output (which is scaled using gdspy or gdstk tools)
        - Then it will extract the GDS area (of bounding box TODO figure out how to do metal area without entering UI)
    """
    gds_file = os.path.join(obj_dir,"par-rundir",f"{top_lvl_mod}_drc.gds")
    if os.path.isfile(gds_file):
        if not os.path.exists(os.path.join(obj_dir,rad_gen.env_settings.report_info.gds_area_fname)):
            write_virtuoso_gds_to_area_script(rad_gen, gds_file)
            for ext in ["csh","sh"]:
                permission_cmd = "chmod +x " +  os.path.join(rad_gen.tech_info.pdk_rundir_path,f'{rad_gen.env_settings.scripts_info.gds_to_area_fname}.{ext}')
                run_shell_cmd_no_logs(permission_cmd)
            run_csh_cmd(os.path.join(rad_gen.tech_info.pdk_rundir_path,f"{rad_gen.env_settings.scripts_info.gds_to_area_fname}.csh"))
            gds_area = parse_gds_to_area_output(rad_gen, obj_dir)
        else:
            gds_area = get_gds_area_from_rpt(rad_gen, obj_dir)

    return gds_area



def run_hammer_flow(rad_gen_settings: rg.HighLvlSettings, config_paths: List[str]) -> None:
    """
        This runs the entire RAD-Gen flow depending on user specified parameters, the following stages can be run in user specified combination:
        - SRAM generation (kinda)
        - Synthesis
        - Place & Route
        - Static Timing & Power Analysis
        Reports will also be printed to stdout & written to csv
    """

    ## config_paths = [rad_gen_settings.asic_flow_settings.config_path]
    # TODO low priority -> see if theres a way to do this through hammer api
    config_paths = rad_gen_settings.asic_flow_settings.hammer_driver.options.project_configs + config_paths
    # These config paths are not initialized in a dataclass so we need to process them to make sure they all have abspaths
    config_paths = [ os.path.realpath(os.path.expanduser(c_p)) for c_p in config_paths]
    
    # Get cwd and change to the design specific output directory (above individual obj dirs)
    pre_flow_dir = os.getcwd()

    work_dir = os.path.realpath(os.path.join("..",rad_gen_settings.asic_flow_settings.hammer_driver.obj_dir))
    os.chdir(work_dir)

    flow_report = {
        "syn" : None,
        "par" : None,
        "pt" : None
    }
    # Add some items to flow report
    # <TAG> <HAMMER-IR-PARSE TODO> # TODO make freq calc rather than period
    flow_report["target_freq"] = rad_gen_settings.asic_flow_settings.hammer_driver.database.get_setting("vlsi.inputs.clocks")[0]["period"]
    
    # Create a list of config paths, this will start with the user defined design config and after each stage of hammer flow will be appended by the resulting config file
    # In hammer the later the configuration is specified after the "-p" argument the higher the priority it has in ASIC flow
    # - Therefore appending to the list of config paths and passing it in order of list indexes is correct
    

    # TODO get Makefile based build working (need to add support for SRAM generator stages)
    # if rad_gen_settings.asic_flow_settings.make_build:
    # Generate dependancy and make files
    _, _, _, = run_hammer_stage(rad_gen_settings.asic_flow_settings, "build", config_paths, update_db = False, execute_stage = rad_gen_settings.asic_flow_settings.make_build)
    if rad_gen_settings.asic_flow_settings.make_build:
        if not os.path.isdir(os.path.join(rad_gen_settings.asic_flow_settings.hammer_driver.obj_dir,"build")):
            os.makedirs(os.path.join(rad_gen_settings.asic_flow_settings.hammer_driver.obj_dir,"build"))
        run_shell_cmd_no_logs(f"mv hammer.d {os.path.join(rad_gen_settings.asic_flow_settings.hammer_driver.obj_dir,'build')}")
        file_lines = [
            "include build/hammer.d"
        ]
        with open( os.path.join(rad_gen_settings.asic_flow_settings.hammer_driver.obj_dir, "Makefile"),"w+") as fd:
            for line in file_lines:
                file_write_ln(fd,line)

    # Check to see if design has an SRAM configuration
    # if rad_gen_settings.asic_flow_settings.run_sram:
    sram_config, sram_stdout, sram_stderr = run_hammer_stage(rad_gen_settings.asic_flow_settings, "sram_generator", config_paths, update_db = True, execute_stage = rad_gen_settings.asic_flow_settings.run_sram)
    # Add sram config to config paths if it exists (if a previous run created it then it will be there)
    if os.path.exists(sram_config):
        config_paths.append(sram_config)
    
    # Run hammer stages
    # Run synthesis
    syn_config, syn_stdout, syn_stderr = run_hammer_stage(rad_gen_settings.asic_flow_settings, "syn", config_paths, update_db = True, execute_stage = rad_gen_settings.asic_flow_settings.run_syn)
    if os.path.exists(syn_config):
        config_paths.append(syn_config)

    # If the synthesis report path exists, then parse
    syn_reports_path = os.path.join(rad_gen_settings.asic_flow_settings.hammer_driver.obj_dir, "syn-rundir", "reports")
    if os.path.isdir(syn_reports_path):
        syn_report = get_report_results(rad_gen_settings, rad_gen_settings.asic_flow_settings.top_lvl_module, syn_reports_path, rad_gen_settings.asic_flow_settings.flow_stages["syn"])
        flow_report["syn"] = syn_report

    # Run place & route
    # if rad_gen_settings.asic_flow_settings.run_par:
    syn_to_par_config, _, _ = run_hammer_stage(rad_gen_settings.asic_flow_settings, "syn-to-par", config_paths, update_db = True, execute_stage = rad_gen_settings.asic_flow_settings.run_par)
    if os.path.exists(syn_to_par_config):
        config_paths.append(syn_to_par_config)
    par_out_config, par_stdout, par_stderr = run_hammer_stage(rad_gen_settings.asic_flow_settings, "par", config_paths, update_db = True, execute_stage = rad_gen_settings.asic_flow_settings.run_par)
    if os.path.exists(par_out_config):
        config_paths.append(par_out_config)
        
    
    if rad_gen_settings.asic_flow_settings.hammer_driver.database.get_setting("vlsi.core.technology") == "asap7":
        # If the user doesn't specify a virtuoso setup script, then we can assume we cant run virtuoso for gds scaling
        if rad_gen_settings.env_settings.scripts_info.virtuoso_setup_path != None:
            # If using asap7 run the gds scaling scripts
            flow_report["gds_area"] = run_asap7_gds_scaling_scripts(rad_gen_settings, rad_gen_settings.asic_flow_settings.hammer_driver.obj_dir, rad_gen_settings.asic_flow_settings.hammer_driver.database.get_setting("par.inputs.top_module"))
        else:
            stdcells_fpath = os.path.join( rad_gen_settings.asic_flow_settings.hammer_driver.tech.cache_dir, "stdcells.txt")
            # This data structure assumes cadence tools ("output_gds_filename")
            scaled_gds_fpath = os.path.join(rad_gen_settings.asic_flow_settings.hammer_driver.obj_dir, "par-rundir", f"{rad_gen_settings.asic_flow_settings.top_lvl_module}_drc.gds")
            # calls a function which uses a gds tool to return area from file rather than virtuoso
            # It seems like the gds libs return an area thats around 2x what virtuoso gives so I scale by 1/2 hence virtuoso is ideal
            flow_report["gds_area"] = gds_fns.main([f"{stdcells_fpath}",f"{scaled_gds_fpath}", "get_area"])/2
            


    # Get macro info
    flow_report = {
        **flow_report,
        **get_macro_info(rad_gen_settings, rad_gen_settings.asic_flow_settings.hammer_driver.obj_dir)
    }
    # If the par report path exists, then parse
    par_reports_path = os.path.join(rad_gen_settings.asic_flow_settings.hammer_driver.obj_dir, "par-rundir", "reports")
    if os.path.isdir(par_reports_path):
        par_report = get_report_results(rad_gen_settings, rad_gen_settings.asic_flow_settings.top_lvl_module, par_reports_path, rad_gen_settings.asic_flow_settings.flow_stages["par"])
        flow_report["par"] = par_report

    # Run static timing & power analysis
    # if rad_gen_settings.asic_flow_settings.run_pt:
    par_to_power_config, _, _ = run_hammer_stage(rad_gen_settings.asic_flow_settings, "par-to-power", config_paths, update_db = True, execute_stage = rad_gen_settings.asic_flow_settings.run_pt)
    if os.path.exists(par_to_power_config):
        config_paths.append(par_to_power_config)
    par_to_timing_config, _, _ = run_hammer_stage(rad_gen_settings.asic_flow_settings, "par-to-timing", config_paths, update_db = True, execute_stage = rad_gen_settings.asic_flow_settings.run_pt)
    if os.path.exists(par_to_timing_config):
        config_paths.append(par_to_timing_config)
    
    if rad_gen_settings.asic_flow_settings.run_pt:
        write_pt_sdc(rad_gen_settings.asic_flow_settings.hammer_driver)


        # Check to see if sram parameters exist in the database
        try:
            sram_params = rad_gen_settings.asic_flow_settings.hammer_driver.database.get_setting("vlsi.inputs.sram_parameters")
        except:
            sram_params = None

        if sram_params != None and sram_params != []:
            # get list of macro names from config generated from par-to-power stage
            macros = [params["name"] for params in sram_params]
            # timing lib paths should be all in the same directory
            timing_lib_paths = [os.path.join(rad_gen_settings.tech_info.sram_lib_path,"lib",f"{macro}_lib") for macro in macros]
            # As we use primetime, the timing libs need to be converted to .db
            conversion_libs = []
            for timing_lib_path in timing_lib_paths:
                conversion_libs += [os.path.join(timing_lib_path,f) for f in os.listdir(timing_lib_path) if f.endswith(".lib")]
            # Run Synopsys logic compier to convert .lib to .db
            lc_script_path = write_lc_lib_to_db_script(rad_gen_settings, conversion_libs)
            lc_run_cmd = f"lc_shell -f {lc_script_path}"
            # Change to pt-rundir
            os.chdir(os.path.join(rad_gen_settings.asic_flow_settings.hammer_driver.obj_dir,"pt-rundir"))
            run_shell_cmd_no_logs(lc_run_cmd)
            # Change back to original directory
            os.chdir(work_dir)

        # Write STA & Power script
        write_pt_timing_script(rad_gen_settings)
        write_pt_power_script(rad_gen_settings)
        os.chdir(os.path.join(rad_gen_settings.asic_flow_settings.hammer_driver.obj_dir,"pt-rundir"))

        # Run Timing
        timing_stdout, timing_stderr = run_shell_cmd_no_logs("dc_shell-t -f pt_timing.tcl")
        with open("timing_stdout.log","w") as fd:
            fd.write(timing_stdout)
        with open("timing_stderr.log","w") as fd:
            fd.write(timing_stderr)

        # Run Power
        power_stdout, power_stderr = run_shell_cmd_no_logs("dc_shell-t -f pt_power.tcl")
        with open("timing_stdout.log","w") as fd:
            fd.write(power_stdout)
        with open("timing_stderr.log","w") as fd:
            fd.write(power_stderr)


        os.chdir(work_dir)
        
    pt_reports_path = os.path.join(rad_gen_settings.asic_flow_settings.hammer_driver.obj_dir, "pt-rundir", "reports")
    if os.path.isdir(pt_reports_path):
        pt_report = get_report_results(rad_gen_settings, rad_gen_settings.asic_flow_settings.top_lvl_module, pt_reports_path, rad_gen_settings.asic_flow_settings.flow_stages["pt"])
        flow_report["pt"] = pt_report

    # Now that we have all the reports, we can generate the final report
    report_to_csv = gen_report_to_csv(flow_report)
    df = pd.DataFrame.from_dict(report_to_csv, orient='index').T
    
    rad_gen_log("\n".join(get_df_output_lines(df)), rad_gen_log_fd)

    csv_fname = os.path.join(rad_gen_settings.asic_flow_settings.hammer_driver.obj_dir,"flow_report")
    write_dict_to_csv([report_to_csv], csv_fname)

    os.chdir(pre_flow_dir)


# ██████╗  █████╗ ████████╗ █████╗     ███████╗████████╗██████╗ ██╗   ██╗ ██████╗████████╗███████╗
# ██╔══██╗██╔══██╗╚══██╔══╝██╔══██╗    ██╔════╝╚══██╔══╝██╔══██╗██║   ██║██╔════╝╚══██╔══╝██╔════╝
# ██║  ██║███████║   ██║   ███████║    ███████╗   ██║   ██████╔╝██║   ██║██║        ██║   ███████╗
# ██║  ██║██╔══██║   ██║   ██╔══██║    ╚════██║   ██║   ██╔══██╗██║   ██║██║        ██║   ╚════██║
# ██████╔╝██║  ██║   ██║   ██║  ██║    ███████║   ██║   ██║  ██║╚██████╔╝╚██████╗   ██║   ███████║
# ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝    ╚══════╝   ╚═╝   ╚═╝  ╚═╝ ╚═════╝  ╚═════╝   ╚═╝   ╚══════╝


def init_dataclass(dataclass_type: Type, input_yaml_config: dict, add_arg_config: dict = {}) -> dict:
    """
        Initializes dictionary values for fields defined in input data structure, basically acts as sanitation for keywords defined in data class fields
        Returns a instantiation of the dataclass
    """
    dataclass_inputs = {}
    for field in dataclass_type.__dataclass_fields__:
        # if the field is read in from input yaml file
        if field in input_yaml_config.keys():
            dataclass_inputs[field] = input_yaml_config[field]
        # additional arg values for fields not defined in input yaml (defined in default_value_config[field])
        elif field in add_arg_config.keys():
            dataclass_inputs[field] = add_arg_config[field]
        if "path" in field and field in dataclass_inputs:
            if isinstance(dataclass_inputs[field], list):
                for idx, path in enumerate(dataclass_inputs[field]):
                    dataclass_inputs[field][idx] = os.path.realpath( os.path.expanduser(path) )
                    handle_error(lambda: check_for_valid_path(dataclass_inputs[field][idx]), {True : None})
            elif isinstance(dataclass_inputs[field], str):
                dataclass_inputs[field] = os.path.realpath( os.path.expanduser(dataclass_inputs[field]) )
                handle_error(lambda: check_for_valid_path(dataclass_inputs[field]), {True : None})
            else:
                pass
    # return created dataclass instance
    # The constructor below will fail if
    # - key in yaml != field name in dataclass 
    return dataclass_type(**dataclass_inputs)


def init_structs(args: argparse.Namespace) -> rg.HighLvlSettings:
    """
       Initializes data structures containing information global to an invocation of RAD gen from the command line.
       - This is structured by using fields in the data structures defined in src/data_structs.py and mapping them to existing keys loaded from yamls
       - If the argument is optional or requires pre processing from yaml it will be done in that data structures field iteration
    """
    if args.top_lvl_config != None:
        # Check if path is valid
        handle_error(lambda: check_for_valid_path(args.top_lvl_config), {True : None})
        with open(args.top_lvl_config, 'r') as yml_file:
            top_level_config = yaml.safe_load(yml_file)
    else:
        raise ValueError("Top level RAD-Gen config file not provided")

    # Sanitize config file 
    top_level_config = sanitize_config(top_level_config)

    
    script_info_inputs = top_level_config["scripts"] if "scripts" in top_level_config.keys() else {}
    scripts_info = init_dataclass(rg.ScriptInfo, script_info_inputs)

    # create additional dicts for argument passed information
    env_inputs = {
        "top_lvl_config_path": args.top_lvl_config,
        "scripts_info": scripts_info,
    }
    env_settings = init_dataclass(rg.EnvSettings, top_level_config["env"], env_inputs)

    # tech_inputs = {
    #    "sram_lib_path": os.path.join(env_settings.hammer_tech_path, "asap7","sram_compiler","memories"),
    # }
    tech_info = init_dataclass(rg.TechInfo, top_level_config["tech"], {})


    asic_flow_settings_input = {} # asic flow settings
    mode_inputs = {} # Set appropriate tool modes
    vlsi_mode_inputs = {} # vlsi flow modes
    high_lvl_inputs = {} # high level setting parameters (associated with a single invocation of rad_gen from cmd line)
    design_sweep_infos = [] # list of design sweep info objects
    if args.design_sweep_config != None:
        ######################################################
        #  _____      _____ ___ ___   __  __  ___  ___  ___  #
        # / __\ \    / / __| __| _ \ |  \/  |/ _ \|   \| __| #
        # \__ \\ \/\/ /| _|| _||  _/ | |\/| | (_) | |) | _|  #
        # |___/ \_/\_/ |___|___|_|   |_|  |_|\___/|___/|___| #
        ######################################################                               
        asic_flow_settings = rg.ASICFlowSettings() 
        # If a sweep file is specified with result compile flag, results across sweep points will be compiled
        if not args.compile_results:
            mode_inputs["sweep_gen"] = True # generate config, rtl, etc related to sweep config
        else:
            mode_inputs["result_parse"] = True # parse results for each sweep point
        handle_error(lambda: check_for_valid_path(args.design_sweep_config), {True : None})
        with open(args.design_sweep_config, 'r') as yml_file:
            sweep_config = yaml.safe_load(yml_file)
        sweep_config = sanitize_config(sweep_config)
        high_lvl_inputs["sweep_config_path"] = args.design_sweep_config
        high_lvl_inputs["result_search_path"] = env_settings.design_output_path

        for design in sweep_config["designs"]:
            sweep_type_inputs = {} # parameters for a specific type of sweep
            if design["type"] == "sram":
                sweep_type_info = init_dataclass(rg.SRAMSweepInfo, design, sweep_type_inputs)
            elif design["type"] == "rtl_params":
                sweep_type_info = init_dataclass(rg.RTLSweepInfo, design, sweep_type_inputs)
            elif design["type"] == "vlsi_params":
                sweep_type_info = init_dataclass(rg.VLSISweepInfo, design, sweep_type_inputs)
            
            design_inputs = {}
            design_inputs["type_info"] = sweep_type_info
            design_sweep_infos.append(init_dataclass(rg.DesignSweepInfo, design, design_inputs))
    # Currently only enabling VLSI mode when other modes turned off
    else:
        ################################################
        # \ \ / / |  / __|_ _| |  \/  |/ _ \|   \| __| #
        #  \ V /| |__\__ \| |  | |\/| | (_) | |) | _|  #
        #   \_/ |____|___/___| |_|  |_|\___/|___/|___| #
        ################################################
        # Initializes Data structures to be used for running stages in ASIC flow

        design_sweep_infos = None

        if args.flow_config_paths != None:
            # Initialize a Hammer Driver, this will deal with the defaults & will allow us to load & manipulate configs before running hammer flow
            driver_opts = HammerDriver.get_default_driver_options()
            # update values
            driver_opts = driver_opts._replace(environment_configs = list(env_settings.env_paths))
            driver_opts = driver_opts._replace(project_configs = list(args.flow_config_paths))
            hammer_driver = HammerDriver(driver_opts)

            vlsi_mode_inputs["enable"] = True
            # if cli provides a top level module and hdl path, we will modify the provided design config file to use them
            if args.top_lvl_module != None and args.hdl_path != None:
                vlsi_mode_inputs["config_pre_proc"] = True
                asic_flow_settings_input["top_lvl_module"] = args.top_lvl_module
                asic_flow_settings_input["hdl_path"] = args.hdl_path
            else:
                vlsi_mode_inputs["config_pre_proc"] = False
                # TODO these should be parsed with hammer IR parser s.t. they can be in its standard format rather just yaml parser
                # <TAG> <HAMMER-IR-PARSE TODO>
                asic_flow_settings_input["top_lvl_module"] = hammer_driver.database.get_setting("synthesis.inputs.top_module")
                # asic_flow_settings_input["top_lvl_module"] = design_config["synthesis"]["inputs.top_module"]
            
            # Create output directory for obj dirs to be created inside of
            out_dir = os.path.join(env_settings.design_output_path, asic_flow_settings_input["top_lvl_module"])
            obj_dir_fmt = f"{asic_flow_settings_input['top_lvl_module']}-{rg.create_timestamp()}"
            
            # TODO restrict input to only accept one of below two options
            obj_dir_path = None
            # Users can specify a specific obj directory
            if args.manual_obj_dir != None:
                obj_dir_path = os.path.realpath(os.path.expanduser(args.manual_obj_dir))
            # Or they can use the latest created obj dir
            elif args.use_latest_obj_dir:
                if os.path.isdir(out_dir):
                    obj_dir_path = find_newest_obj_dir(search_dir = out_dir,obj_dir_fmt = f"{asic_flow_settings_input['top_lvl_module']}-{rg.create_timestamp(fmt_only_flag = True)}")
            # If no value given or no obj dir found, we will create a new one
            if obj_dir_path == None:
                obj_dir_path = os.path.join(out_dir,obj_dir_fmt)

            if not os.path.isdir(obj_dir_path):
                os.makedirs(obj_dir_path)

            rad_gen_log(f"Using obj_dir: {obj_dir_path}",rad_gen_log_fd)

            hammer_driver.obj_dir = obj_dir_path
            # At this point hammer driver should be fully initialized
            asic_flow_settings_input["hammer_driver"] = hammer_driver
            asic_flow_settings_input["obj_dir_path"] = obj_dir_path

            # if not specified the flow will run all the stages by defualt
            run_all_flow = not (args.synthesis or args.place_n_route or args.primetime) and not args.compile_results
            
            asic_flow_settings_input["make_build"] = args.make_build
            asic_flow_settings_input["run_sram"] = args.sram_compiler
            asic_flow_settings_input["run_syn"] = args.synthesis or run_all_flow
            asic_flow_settings_input["run_par"] = args.place_n_route or run_all_flow
            asic_flow_settings_input["run_pt"] = args.primetime or run_all_flow
            # TODO implement "flow_stages" element of ASICFlowSettings struct
            if "asic_flow" in top_level_config.keys():
                config_file_input = top_level_config["asic_flow"]
            else:
                config_file_input = {}
            asic_flow_settings = init_dataclass(rg.ASICFlowSettings, config_file_input, asic_flow_settings_input)

    vlsi_flow = init_dataclass(rg.VLSIMode, vlsi_mode_inputs, {})
    rad_gen_mode = init_dataclass(rg.RADGenMode, mode_inputs, {"vlsi_flow" : vlsi_flow})
    high_lvl_inputs = {
        **high_lvl_inputs,
        "mode": rad_gen_mode,
        "tech_info": tech_info,
        "design_sweep_infos": design_sweep_infos,
        "asic_flow_settings": asic_flow_settings,
        "env_settings": env_settings,
    }
    high_lvl_settings = init_dataclass(rg.HighLvlSettings, high_lvl_inputs, {})
    return high_lvl_settings
    
    

# ██████╗  █████╗ ██████╗      ██████╗ ███████╗███╗   ██╗    ███████╗██╗  ██╗███████╗ ██████╗    ███╗   ███╗ ██████╗ ██████╗ ███████╗███████╗
# ██╔══██╗██╔══██╗██╔══██╗    ██╔════╝ ██╔════╝████╗  ██║    ██╔════╝╚██╗██╔╝██╔════╝██╔════╝    ████╗ ████║██╔═══██╗██╔══██╗██╔════╝██╔════╝
# ██████╔╝███████║██║  ██║    ██║  ███╗█████╗  ██╔██╗ ██║    █████╗   ╚███╔╝ █████╗  ██║         ██╔████╔██║██║   ██║██║  ██║█████╗  ███████╗
# ██╔══██╗██╔══██║██║  ██║    ██║   ██║██╔══╝  ██║╚██╗██║    ██╔══╝   ██╔██╗ ██╔══╝  ██║         ██║╚██╔╝██║██║   ██║██║  ██║██╔══╝  ╚════██║
# ██║  ██║██║  ██║██████╔╝    ╚██████╔╝███████╗██║ ╚████║    ███████╗██╔╝ ██╗███████╗╚██████╗    ██║ ╚═╝ ██║╚██████╔╝██████╔╝███████╗███████║
# ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝      ╚═════╝ ╚══════╝╚═╝  ╚═══╝    ╚══════╝╚═╝  ╚═╝╚══════╝ ╚═════╝    ╚═╝     ╚═╝ ╚═════╝ ╚═════╝ ╚══════╝╚══════╝


def parse_cli_args(input_parser: argparse.ArgumentParser = None) -> argparse.Namespace:
    if input_parser == None:
        parser = argparse.ArgumentParser()
    parser.add_argument('-t', '--top_lvl_module', help="name of top level design in HDL", type=str, default=None)
    parser.add_argument('-v', '--hdl_path', help="path to directory containing HDL files", type=str, default=None)
    parser.add_argument('-p', '--flow_config_paths', 
                        help="list of paths to hammer design specific config.yaml files",
                        nargs="*",
                        type=str,
                        default=None)
    parser.add_argument('-l', '--use_latest_obj_dir', help="uses latest obj dir found in rad_gen dir", action='store_true') 
    parser.add_argument('-o', '--manual_obj_dir', help="uses user specified obj dir", type=str, default=None)
    parser.add_argument('-e', '--top_lvl_config', help="path to top level config file",  type=str, default=None)
    parser.add_argument('-s', '--design_sweep_config', help="path to config file containing design sweep parameters",  type=str, default=None)
    parser.add_argument('-c', '--compile_results', help="path to dir", action='store_true') 
    parser.add_argument('-syn', '--synthesis', help="flag runs synthesis on specified design", action='store_true') 
    parser.add_argument('-par', '--place_n_route', help="flag runs place & route on specified design", action='store_true') 
    parser.add_argument('-pt', '--primetime', help="flag runs primetime on specified design", action='store_true') 
    parser.add_argument('-sram', '--sram_compiler', help="flag enables srams to be run in design", action='store_true') 
    parser.add_argument('-make', '--make_build', help="flag enables make build system for asic flow", action='store_true') 
    
    # Testing integration
    #parser.add_argument('-j', '--top_config', help="path to top level config file",  type=str, default=None)

    # parser.add_argument('-r', '--openram_config_dir', help="path to dir (TODO)", type=str, default='')
    # parser.add_argument('-sim', '--sram_compiler', help="path to dir", action='store_true') 
    args = parser.parse_args()
    
    return args



def compile_results(rad_gen_settings: rg.HighLvlSettings):
    # read in the result config file
    report_search_dir = rad_gen_settings.env_settings.design_output_path
    csv_lines = []
    reports = []
    for design in rad_gen_settings.design_sweep_infos:
        rad_gen_log(f"Parsing results of parameter sweep using parameters defined in {rad_gen_settings.sweep_config_path}",rad_gen_log_fd)
        if design.type != None:
            if design.type == "sram":
                for mem in design.type_info.mems:
                    mem_top_lvl_name = f"sram_macro_map_{mem['rw_ports']}x{mem['w']}x{mem['d']}"
                    num_bits = mem['w']*mem['d']
                    reports += gen_parse_reports(rad_gen_settings, report_search_dir, mem_top_lvl_name, design, num_bits)
                reports += gen_parse_reports(rad_gen_settings, report_search_dir, design.top_lvl_module, design)
            elif design.type == "rtl_params":
                """ Currently focused on NoC rtl params"""
                reports = gen_parse_reports(rad_gen_settings, report_search_dir, design.top_lvl_module, design)
            else:
                rad_gen_log(f"Error: Unknown design type {design.type} in {rad_gen_settings.sweep_config_path}",rad_gen_log_fd)
                sys.exit(1)
        else:
            # This parsing of reports just looks at top level and takes whatever is in the obj dir
            reports = gen_parse_reports(rad_gen_settings, report_search_dir, design.top_lvl_module)
        
        # General parsing of report to csv
        for report in reports:
            report_to_csv = {}
            if design.type == "rtl_params":
                if "rtl_params" in report.keys():
                    report_to_csv = noc_prse_area_brkdwn(report)
            else:
                report_to_csv = gen_report_to_csv(report)
            if len(report_to_csv) > 0:
                csv_lines.append(report_to_csv)
    result_summary_outdir = os.path.join(rad_gen_settings.env_settings.design_output_path,"result_summaries")
    if not os.path.isdir(result_summary_outdir):
        os.makedirs(result_summary_outdir)
    csv_fname = os.path.join(result_summary_outdir, os.path.splitext(os.path.basename(rad_gen_settings.sweep_config_path))[0] )
    write_dict_to_csv(csv_lines,csv_fname)

def design_sweep(rad_gen_settings: rg.HighLvlSettings):
    # Starting with just SRAM configurations for a single rtl file (changing parameters in header file)
    rad_gen_log(f"Running design sweep from config file {rad_gen_settings.sweep_config_path}",rad_gen_log_fd)
    
    scripts_outdir = os.path.join(rad_gen_settings.env_settings.design_output_path,"scripts")
    if not os.path.isdir(scripts_outdir):
        os.makedirs(scripts_outdir)
    # design_sweep_config = yaml.safe_load(open(rad_gen_settings.sweep_config_path))
    for id, design_sweep in enumerate(rad_gen_settings.design_sweep_infos):
        """ General flow for all designs in sweep config """
        # Load in the base configuration file for the design
        # sanitized_design = sanitize_config(design)
        base_config = yaml.safe_load(open(design_sweep.base_config_path))
        
        """ Currently only can sweep either vlsi params or rtl params not both """
        sweep_script_lines = [
            "#!/bin/bash",
        ]
        # If there are vlsi parameters to sweep over
        if design_sweep.type == "vlsi_params":
            mod_base_config = copy.deepcopy(base_config)
            """ MODIFYING HAMMER CONFIG YAML FILES """
            sweep_idx = 1
            for param_sweep_key, param_sweep_vals in design_sweep.type_info.params.items():
                # <TAG> <HAMMER-IR-PARSE TODO> , This is looking for the period in parameters and will set the associated hammer IR to that value 
                if "period" in param_sweep_key:
                    for period in design_sweep.type_info.params[param_sweep_key]:
                        mod_base_config["vlsi.inputs"]["clocks"][0]["period"] = f'{str(period)} ns'
                        modified_config_path = os.path.splitext(design_sweep.base_config_path)[0] + f'_period_{str(period)}.yaml'
                        with open(modified_config_path, 'w') as fd:
                            yaml.safe_dump(mod_base_config, fd, sort_keys=False) 

                        rad_gen_cmd_lines = [
                            get_rad_gen_flow_cmd(rad_gen_settings, modified_config_path, sram_flag=False, top_level_mod=design_sweep.top_lvl_module, hdl_path=design_sweep.rtl_dir_path) + " &",
                            "sleep 2",
                        ]
                        sweep_script_lines += rad_gen_cmd_lines
                        if sweep_idx % design_sweep.flow_threads == 0 and sweep_idx != 0:
                            sweep_script_lines.append("wait")
                        sweep_idx += 1
            rad_gen_log("\n".join(create_bordered_str("Autogenerated Sweep Script")),rad_gen_log_fd)
            rad_gen_log("\n".join(sweep_script_lines),rad_gen_log_fd)
            sweep_script_lines = create_bordered_str("Autogenerated Sweep Script") + sweep_script_lines
            script_path = os.path.join(scripts_outdir, f"{design_sweep.top_lvl_module}_vlsi_sweep.sh")
            for line in sweep_script_lines:
                with open(script_path , "w") as fd:
                    file_write_ln(fd, line)
            permission_cmd = f"chmod +x {script_path}"
            run_shell_cmd_no_logs(permission_cmd)
        # TODO This wont work for multiple SRAMs in a single design, simply to evaluate individual SRAMs
        elif design_sweep.type == "sram":      
            sram_sweep_gen(rad_gen_settings, id)                
        # TODO make this more general but for now this is ok
        # the below case should deal with any asic_param sweep we want to perform
        elif design_sweep.type == 'rtl_params':
            mod_param_hdr_paths, mod_config_paths = edit_rtl_proj_params(design_sweep.type_info.params, design_sweep.rtl_dir_path, design_sweep.type_info.base_header_path, design_sweep.base_config_path)
            sweep_idx = 1
            for hdr_path, config_path in zip(mod_param_hdr_paths, mod_config_paths):
            # for hdr_path in mod_param_hdr_paths:
                rad_gen_log(f"PARAMS FOR PATH {hdr_path}",rad_gen_log_fd)
                rad_gen_cmd_lines = [
                    get_rad_gen_flow_cmd(rad_gen_settings, config_path, sram_flag=False, top_level_mod=design_sweep.top_lvl_module, hdl_path=design_sweep.rtl_dir_path) + " &",
                    "sleep 2",
                ]
                sweep_script_lines += rad_gen_cmd_lines
                if sweep_idx % design_sweep.flow_threads == 0 and sweep_idx != 0:
                    sweep_script_lines.append("wait")
                sweep_idx += 1
                # rad_gen_log(get_rad_gen_flow_cmd(config_path,sram_flag=False,top_level_mod=sanitized_design["top_level_module"],hdl_path=sanitized_design["rtl_dir_path"]),rad_gen_log_fd)
                read_in_rtl_proj_params(rad_gen_settings, design_sweep.type_info.params, design_sweep.top_lvl_module, design_sweep.rtl_dir_path, hdr_path)
                """ We shouldn't need to edit the values of params/defines which are operations or values set to other params/defines """
                """ EDIT PARAMS/DEFINES IN THE SWEEP FILE """
                # TODO this assumes parameter sweep vars arent kept over multiple files
            rad_gen_log("\n".join(create_bordered_str("Autogenerated Sweep Script")),rad_gen_log_fd)
            rad_gen_log("\n".join(sweep_script_lines),rad_gen_log_fd)
            sweep_script_lines = create_bordered_str("Autogenerated Sweep Script") + sweep_script_lines
            script_path = os.path.join(scripts_outdir, f"{design_sweep.top_lvl_module}_rtl_sweep.sh")
            for line in sweep_script_lines:
                with open( script_path, "w") as fd:
                    file_write_ln(fd, line)
            permission_cmd = f"chmod +x {script_path}"
            run_shell_cmd_no_logs(permission_cmd)

def run_asic_flow(rad_gen_settings: rg.HighLvlSettings):
    if rad_gen_settings.mode.vlsi_flow.flow_mode == "custom":
      if rad_gen_settings.mode.vlsi_flow.run_mode == "serial":
        for hb_settings in rad_gen_settings.custom_asic_flow_settings["asic_hardblock_params"]["hardblocks"]:
          hardblock_flow(hb_settings)
      elif rad_gen_settings.mode.vlsi_flow.run_mode == "parallel":
        for hb_settings in rad_gen_settings.custom_asic_flow_settings["asic_hardblock_params"]["hardblocks"]:
          hardblock_parallel_flow(hb_settings)
    elif rad_gen_settings.mode.vlsi_flow.flow_mode == "hammer":
      # If the args for top level and rtl path are not set, we will use values from the config file
      in_configs = []
      if rad_gen_settings.mode.vlsi_flow.config_pre_proc:
          """ Check to make sure all parameters are assigned and modify if required to"""
          mod_config_file = modify_config_file(rad_gen_settings)
          in_configs.append(mod_config_file)

      # Run the flow
      run_hammer_flow(rad_gen_settings, in_configs)
       
    rad_gen_log("Done!", rad_gen_log_fd)
    sys.exit()    


def main(args: Optional[List[str]] = None) -> None:
    global cur_env
    # # global verbosity_lvl
    global rad_gen_log_fd
    global log_verbosity
    rad_gen_log_fd = "rad_gen.log"
    log_verbosity = 2

    #Clear rad gen log
    fd = open(rad_gen_log_fd, 'w')
    fd.close()

    # Parse command line arguments
    # args = parse_cli_args()

    args, gen_arg_keys, default_arg_vals = rg_utils.parse_rad_gen_top_cli_args()

    # rad_gen_settings = init_structs(args)
    rad_gen_info = rg_utils.init_structs_top(args, gen_arg_keys, default_arg_vals)


    # Make sure HAMMER env vars are set
    # if 'HAMMER_HOME' not in os.environ:
    #     rad_gen_log('Error: HAMMER_HOME environment variable not set!', rad_gen_log_fd)
    #     rad_gen_log("Please set HAMMER_HOME to the root of the HAMMER repository, and run 'source $HAMMER_HOME/sourceme.sh'", rad_gen_log_fd)
    #     sys.exit(1)

    cur_env = os.environ.copy()

    """ Ex. args python3 rad_gen.py -s param_sweep/configs/noc_sweep.yml -c """
    if rad_gen_info["asic_dse"].mode.result_parse:
        compile_results(rad_gen_info["asic_dse"])
    # If a design sweep config file is specified, modify the flow settings for each design in sweep
    elif rad_gen_info["asic_dse"].mode.sweep_gen:
        design_sweep(rad_gen_info["asic_dse"])
    elif rad_gen_info["asic_dse"].mode.vlsi_flow.enable:
        run_asic_flow(rad_gen_info["asic_dse"])
    
    
if __name__ == '__main__':
    main()