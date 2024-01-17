# General modules
from typing import List, Dict, Tuple, Set, Union, Any, Type
import os, sys
import argparse
import datetime
import yaml
import re
import subprocess as sp
from pathlib import Path
import json
import copy
import math
import pandas as pd

#Import hammer modules
import third_party.hammer.hammer.config as hammer_config
from third_party.hammer.hammer.vlsi.hammer_vlsi_impl import HammerVLSISettings 
from third_party.hammer.hammer.vlsi.driver import HammerDriver
import third_party.hammer.hammer.tech as hammer_tech
from third_party.hammer.hammer.vlsi.cli_driver import dump_config_to_json_file


# import gds funcs (for asap7)
import src.common.gds_fns as gds_fns

# RAD Gen modules
import src.common.data_structs as rg_ds
import src.common.utils as rg_utils

# SRAM Compiler modules
import src.asic_dse.sram_compiler as sram_compiler 


# from rad_gen import rad_gen_log_fd, cur_env, log_verbosity
rad_gen_log_fd = "asic_dse.log"
log_verbosity = 2
cur_env = os.environ.copy()

# ██████╗ ██████╗ ██╗███╗   ███╗███████╗████████╗██╗███╗   ███╗███████╗
# ██╔══██╗██╔══██╗██║████╗ ████║██╔════╝╚══██╔══╝██║████╗ ████║██╔════╝
# ██████╔╝██████╔╝██║██╔████╔██║█████╗     ██║   ██║██╔████╔██║█████╗  
# ██╔═══╝ ██╔══██╗██║██║╚██╔╝██║██╔══╝     ██║   ██║██║╚██╔╝██║██╔══╝  
# ██║     ██║  ██║██║██║ ╚═╝ ██║███████╗   ██║   ██║██║ ╚═╝ ██║███████╗
# ╚═╝     ╚═╝  ╚═╝╚═╝╚═╝     ╚═╝╚══════╝   ╚═╝   ╚═╝╚═╝     ╚═╝╚══════╝


def write_pt_sdc(hammer_driver: HammerDriver):
    """
    Writes an sdc file in the format which will match the output of innovus par stage.
    This may not be needed as Hammer produces an sdc file prior to synthesis but I think there was some issue with it
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
        rg_utils.file_write_ln(fd,line)
    fd.close()


def pt_init(rad_gen_settings: rg_ds.AsicDSE) -> Tuple[str]:
    """
        Performs actions required prior to running PrimeTime for Power or Timing
    """
    # create PT run-dir
    pt_outpath = os.path.join(rad_gen_settings.asic_flow_settings.obj_dir_path, "pt-rundir")
    os.makedirs(pt_outpath, exist_ok=True)
    
    # create reports dir
    report_path = os.path.join(pt_outpath, rad_gen_settings.env_settings.report_info.report_dir)
    unparse_report_path = os.path.join(report_path, rad_gen_settings.env_settings.report_info.unparse_report_dir)
    os.makedirs(report_path, exist_ok=True)
    os.makedirs(unparse_report_path, exist_ok=True)

    # get pnr output path (should be in this format)
    pnr_design_outpath = os.path.join(rad_gen_settings.asic_flow_settings.obj_dir_path,"par-rundir",f'{rad_gen_settings.asic_flow_settings.top_lvl_module}_FINAL')
    if not os.path.isdir(pnr_design_outpath):
        rg_utils.rad_gen_log("Couldn't find output of pnr stage, Exiting...",rad_gen_log_fd)
        sys.exit(1)

    return pt_outpath, report_path, unparse_report_path, pnr_design_outpath

def write_pt_power_script(rad_gen_settings: rg_ds.AsicDSE):
    pt_outpath, report_path, unparse_report_path, pnr_design_outpath = pt_init(rad_gen_settings)

    # Make sure that the $STDCELLS env var is set and use it to find the .lib files to use for Primetime
    db_dirs =  [os.path.join(rad_gen_settings.env_settings.rad_gen_home_path,db_lib) for db_lib in ["sram_db_libs","asap7_db_libs"] ]
    
    # Use FF corner for worst case power
    corners = ["FF"]
    tx_types = ["SLVT", "LVT"]
    filt_strs = [f"{tx_type}_{corner}" for corner in corners for tx_type in tx_types]
    target_libs = " ".join([
        os.path.join(db_dir, lib)\
        for db_dir in db_dirs\
        for lib in os.listdir(db_dir)\
        for filt_str in filt_strs\
        if lib.endswith(".db") and filt_str in lib
    ])
    
    #default switching probability (TODO) find where this is and make it come from there
    switching_prob = "0.5"
    report_power_cmds = [ 
        "report_power > " + os.path.join(report_path,"power.rpt"),
        # From PrimeTime RM
        "report_power -threshold_voltage_group > " + os.path.join(unparse_report_path, "power_per_lib_leakage.rpt"),
        "report_threshold_voltage_group > " + os.path.join(unparse_report_path, "power_per_volt_th_grp.rpt"),
    ]
    # TODO implement multimodal analysis (mainly only for power but its also relevant to timing)
    # By multimodal analysis I mean something like inputs to muxes which control mode of operation of something like a DSP block
    # More complicated examples may be inputting different instructions to a processor
    case_analysis_cmds = ["#MULTIMODAL ANALYSIS DISABLED"]
    #get switching activity and toggle rates from power_constraints tcl file
    top_mod = rad_gen_settings.asic_flow_settings.hammer_driver.database.get_setting("power.inputs.top_module")

    # Open power constraints file and grab toggle rate
    power_constraints_fd = open(os.path.join(pnr_design_outpath,f'{top_mod}_power_constraints.tcl'),"r")
    power_constraints_lines = power_constraints_fd.readlines()
    power_constraints_fd.close()

    # Grabbing sequential activity
    toggle_rate_var = "seq_activity"
    grab_opt_val_re = re.compile(f"(?<={toggle_rate_var}\s).*")
    # This is a decent default toggle rate value
    toggle_rate = "0.25"
    for line in power_constraints_lines:
        if "set_default_switching_activity" in line:
            toggle_rate = str(grab_opt_val_re.search(line).group(0))
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
        "set power_enable_analysis true", 
        "set power_enable_multi_rail_analysis true", 
        "set power_analysis_mode averaged", 
        "set sh_enable_page_mode true",
        "set search_path " + f"\"{' '.join(db_dirs)}\"",
        "set my_top_level " + top_mod,
        "set my_clock_pin " + clk_pin,
        "set target_library " + f"\"{target_libs}\"",
        # Not sure about difference between these two but I think they should be the same
        "set link_library " + "\"* $target_library\"",
        "set link_path " + "\"* $target_library\"", 
        "read_verilog " + verilog_netlist,
        "current_design $my_top_level",
        case_analysis_cmds,
        "link",
        # Read in constraints
        f"read_sdc -echo {pt_outpath}/pt.sdc",
        # read in parasitics from pnr stage
        "read_parasitics -increment " + spef_path,
        switching_activity_cmd,
        "check_power > " + os.path.join(report_path,"check_power.rpt"),
        "update_power", 
        *report_power_cmds,
        "quit",
    ]

    file_lines = rg_utils.flatten_mixed_list(file_lines)

    fname = os.path.join(pt_outpath,"pt_power.tcl")
    fd = open(fname, "w")
    for line in file_lines:
        rg_utils.file_write_ln(fd,line)
    fd.close()


def write_pt_timing_script(rad_gen_settings: rg_ds.AsicDSE):
    """
    writes the tcl script for timing analysis using Synopsys Design Compiler, tested under 2017 version
    This should look for setup/hold violations using the worst case (hold) and best case (setup) libs
    """
    pt_outpath, report_path, unparse_report_path, pnr_design_outpath = pt_init(rad_gen_settings)

    # Make sure that the $STDCELLS env var is set and use it to find the .lib files to use for Primetime

    # Below are some example generic paths for a tool like synopsys design compiler     
    #"/CMC/tools/synopsys/syn_vN-2017.09/libraries/syn /CMC/tools/synopsys/syn_vN-2017.09/libraries/syn_ver /CMC/tools/synopsys/syn_vN-2017.09/libraries/sim_ver"
    
    db_dirs =  [os.path.join(rad_gen_settings.env_settings.rad_gen_home_path, db_lib) for db_lib in ["sram_db_libs","asap7_db_libs"] ]


    # corner options are ["SS", "TT", "FF"]
    # tx_type options are ["SLVT", "LVT", "RVT", "SRAM"] in order of decreasing drive strength

    # Designs are made up of SLVT and LVT if not including SRAMs
    # Using SS corner to show worst case timing
    corners = ["SS"]
    tx_types = ["SLVT", "LVT"]
    filt_strs = [f"{tx_type}_{corner}" for corner in corners for tx_type in tx_types]
    target_libs = " ".join([
        os.path.join(db_dir, lib)\
        for db_dir in db_dirs\
        for lib in os.listdir(db_dir)\
        for filt_str in filt_strs\
        if lib.endswith(".db") and filt_str in lib
    ]) 
    
    # report timing / power commands
    report_timing_cmds = [
        "report_timing > " + os.path.join(report_path,"timing.rpt"),
        "report_global_timing > " + os.path.join(unparse_report_path, "global_timing.rpt"),
        "report_clock -skew -attribute > " + os.path.join(unparse_report_path, "clock_timing.rpt"),
        "report_analysis_coverage > " + os.path.join(unparse_report_path, "analysis_coverage.rpt"),
        "report_timing -slack_lesser_than 0.0 -delay min_max -nosplit -input -net > " + os.path.join(unparse_report_path, "timing_violations.rpt"),
    ]
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
        "set search_path " + f"\"{' '.join(db_dirs)}\"",
        "set my_top_level " + top_mod,
        "set my_clock_pin " + clk_pin,
        "set target_library " + f"\"{target_libs}\"",
        "set link_library " + "\"* $target_library\"",
        "read_verilog " + f"\" {verilog_netlists} \"",
        "current_design $my_top_level",
        case_analysis_cmds,
        "link",
        #set clock constraints (this can be done by defining a clock or specifying an .sdc file)
        f"read_sdc -echo {pt_outpath}/pt.sdc",
        "check_timing -verbose > " + os.path.join(report_path,'check_timing.rpt'),
        "update_timing -full",
        #read constraints file
        *report_timing_cmds,
        "quit",
    ]
    file_lines = rg_utils.flatten_mixed_list(file_lines)

    fname = os.path.join(pt_outpath,"pt_timing.tcl")
    fd = open(fname, "w")
    for line in file_lines:
        rg_utils.file_write_ln(fd,line)
    fd.close()

    return


# ██╗  ██╗ █████╗ ███╗   ███╗███╗   ███╗███████╗██████╗     ██╗   ██╗████████╗██╗██╗     ███████╗
# ██║  ██║██╔══██╗████╗ ████║████╗ ████║██╔════╝██╔══██╗    ██║   ██║╚══██╔══╝██║██║     ██╔════╝
# ███████║███████║██╔████╔██║██╔████╔██║█████╗  ██████╔╝    ██║   ██║   ██║   ██║██║     ███████╗
# ██╔══██║██╔══██║██║╚██╔╝██║██║╚██╔╝██║██╔══╝  ██╔══██╗    ██║   ██║   ██║   ██║██║     ╚════██║
# ██║  ██║██║  ██║██║ ╚═╝ ██║██║ ╚═╝ ██║███████╗██║  ██║    ╚██████╔╝   ██║   ██║███████╗███████║
# ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝     ╚═╝╚══════╝╚═╝  ╚═╝     ╚═════╝    ╚═╝   ╚═╝╚══════╝╚══════╝                                                                           

def run_hammer_stage(asic_flow: rg_ds.ASICFlowSettings, flow_stage: str, config_paths: List[str], update_db: bool = True, execute_stage: bool = True):
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
        stdout, stderr = rg_utils.run_shell_cmd_no_logs(hammer_cmd)
    
    if update_db and os.path.exists(ret_config_path):
        # update the driver information with new config
        proj_config_dicts = []
        for config in config_paths + [ret_config_path]:
            is_yaml = config.endswith(".yml") or config.endswith(".yaml")
            if not os.path.exists(config):
                rg_utils.rad_gen_log("Project config %s does not exist!" % (config),rad_gen_log_fd)
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


def get_rad_gen_flow_cmd(rad_gen_settings: rg_ds.AsicDSE, config_path: str, sram_flag = False, top_level_mod = None, hdl_path = None):
    if top_level_mod is None and hdl_path is None:
        cmd = f'python3 rad_gen.py -e {rad_gen_settings.env_settings.top_lvl_config_path} -p {config_path}'
    else:
        cmd = f'python3 rad_gen.py -e {rad_gen_settings.env_settings.top_lvl_config_path} -p {config_path} -t {top_level_mod} -v {hdl_path}'

    if sram_flag:
        cmd = cmd + " -sram"
    return cmd

def modify_config_file(rad_gen: rg_ds.AsicDSE) -> str:
    # recursively get all files matching extension in the design directory
    exts = ['.v','.sv','.vhd',".vhdl"]
    design_files, design_dirs = rg_utils.rec_get_flist_of_ext(rad_gen.asic_flow_settings.hdl_path, exts)

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
    config_paths = rad_gen.asic_flow_settings.hammer_driver.options.project_configs
    for config_path in config_paths:
        # Read all configs and figure out which one contains the top level module info
        config_str = Path(config_path).read_text()
        is_yaml = config_path.endswith(".yml") or config_path.endswith(".yaml")
        config_dict = hammer_config.load_config_from_string(config_str, is_yaml, str(Path(config_path).resolve().parent))
        # If top module exists in the synthesis inputs, write 
        if "synthesis.inputs.top_module" in config_dict.keys():
            # TODO remove hardcoding of "_pre_proc" and replace with a variable linked to data struct
            # _pre_proc is the key that tells us if the config file was initialized by rad_gen, if it was then we should just override the file 
            if "_pre_proc" in config_path:
                modified_config_path = config_path
            else:
                input_config_split = os.path.split(config_path)
                config_fname = os.path.splitext(os.path.basename(config_path))[0]
                mod_config_outdir = os.path.join(input_config_split[0], rad_gen.env_settings.input_dir_struct["configs"]["mod"])
                modified_config_path = os.path.join(mod_config_outdir, f"{config_fname}_pre_proc.yml")
            break
    
    
    # Make dirs to modified config path if they don't exist
    os.makedirs(os.path.dirname(modified_config_path), exist_ok=True)
    
    with open(modified_config_path, 'w') as yml_file:
        yaml.safe_dump(design_config, yml_file, sort_keys=False) 
    
    # Update hammer driver with new config
    proj_config_dicts = []
    # Appending it to the end gives the highest precedence in hammer
    for config in config_paths + [modified_config_path]:
        is_yaml = config.endswith(".yml") or config.endswith(".yaml")
        if not os.path.exists(config):
            rg_utils.rad_gen_log("Project config %s does not exist!" % (config),rad_gen_log_fd)
        config_str = Path(config).read_text()
        proj_config_dicts.append(hammer_config.load_config_from_string(config_str, is_yaml, str(Path(config).resolve().parent)))
    rad_gen.asic_flow_settings.hammer_driver.update_project_configs(proj_config_dicts)

    return modified_config_path

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
    
    # TODO remove hardcoding, connect to the "input_dir_struct" data structure in EnvSettings
    # mod_configs_dir = os.path.join( os.path.dirname(base_config_path), "mod")
    # mod_config_path = os.path.join(mod_configs_dir, os.path.splitext(base_config_path)[0]+f'_{mod_param_dir_name}.yaml')
    # # make modified config dir if it doesnt exist
    # os.makedirs(mod_configs_dir, exist_ok=True)
    
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

    base_param_hdr = rg_utils.c_style_comment_rm(open(base_param_hdr_path).read())
    
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
                    rg_utils.rad_gen_log("Writing modified parameter file to: "+mod_param_out_fpath,rad_gen_log_fd)
                    with open(mod_param_out_fpath,"w") as param_out_fd:
                        param_out_fd.write(mod_param_hdr)
                    mod_parameter_paths.append(mod_param_out_fpath)
                    """ GENERATING AND WRITING RAD GEN CONFIG FILES """
                    with open(base_config_path,"r") as config_fd:
                        rad_gen_config = yaml.safe_load(config_fd)
                    rad_gen_config["synthesis"]["inputs.hdl_search_paths"].append(os.path.abspath(mod_param_dir_str))
                    mod_config_path = os.path.splitext(base_config_path)[0]+f'_{p_name}_{p_val}.yaml'
                    print("Writing modified config file to: " + mod_config_path, rad_gen_log_fd)
                    with open(mod_config_path,"w") as config_fd:
                        yaml.safe_dump(rad_gen_config, config_fd, sort_keys=False)
                    mod_config_paths.append(mod_config_path)

    return mod_parameter_paths, mod_config_paths

def read_in_rtl_proj_params(rad_gen_settings: rg_ds.AsicDSE, rtl_params, top_level_mod, rtl_dir_path, sweep_param_inc_path=False):

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
    clean_top_lvl_rtl = rg_utils.c_style_comment_rm(top_level_rtl)
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
                include_fpath = rg_utils.rec_find_fpath(rtl_dir_path,include_fname)
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
                rg_utils.rad_gen_log("WARNING: Could not find parameter header file, returning None ...", rad_gen_log_fd)
                return None
            # Look in the include file path and grab all parameters and defines
            include_rtl = open(include_fpath).read()
            clean_include_rtl = rg_utils.c_style_comment_rm(include_rtl)
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
    rg_utils.rad_gen_log(param_print_stdout.stdout.decode("utf-8"),rad_gen_log_fd)
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

def gen_compiled_srams(asic_dse: rg_ds.AsicDSE, design_id: int, base_config: dict):
    cur_design = asic_dse.design_sweep_infos[design_id]
    mem_idx = 1
    mem_sweep_script_lines = []
    for mem in cur_design.type_info.mems:
        # The path in hammer to directory containing srams.txt file (describes the available macros in the pdk)
        hammer_tech_pdk_dpath =  asic_dse.common.project_tree.search_subtrees(f"hammer.hammer.technology.{asic_dse.stdcell_lib.name}", is_hier_tag=True)[0].path
        mapping = sram_compiler.compile(hammer_tech_pdk_dpath, mem["rw_ports"], mem["w"], mem["d"])
        sram_map_info, rtl_outpath = sram_compiler.write_rtl_from_mapping(
                                                    mapping,
                                                    asic_dse.sram_compiler_settings.rtl_out_dpath)
        sram_map_info = sram_compiler.translate_logical_to_phsical(sram_map_info)
        config_fpath = mod_rad_gen_config_from_rtl(
                                            asic_dse,
                                            base_config,
                                            sram_map_info,
                                            rtl_outpath)
        
        mem_cmd_lines, mem_idx = get_hammer_flow_sweep_point_lines(asic_dse, design_id, mem_idx, config_fpath, sram_compiler=True)
        if mem_cmd_lines is None:
            break
        else:
            mem_sweep_script_lines += mem_cmd_lines

    stiched_mem_script_fpath = os.path.join(asic_dse.sram_compiler_settings.scripts_out_dpath, f"stitched_mem_sweep_script.sh")
    rg_utils.write_out_script(mem_sweep_script_lines, stiched_mem_script_fpath)
        
        # Log out flow command
        # rg_utils.rad_gen_log(get_rad_gen_flow_cmd(rad_gen_settings = rad_gen_settings, config_path = config_path, sram_flag = True),rad_gen_log_fd)
    # for mem in sanitized_design["mems"]:
        
        # get mapping and find the macro in lib, instantiate that many and

def get_hammer_flow_sweep_point_lines(asic_dse: rg_ds.AsicDSE, des_sweep_id: int, sweep_pt_idx: int, mod_flow_conf_fpath: str,  **kwargs) -> Tuple[Union[None, List[str]], Union[None, int]]:
    """
        Returns a tuple of lines and (new) sweep_pt_idx to run RAD-Gen for a given sweep point with hammer flow, if no env config files are specified in the sweep config file then None is returned
        asic_dse: AsicDSE object
        des_sweep_id: sweep id for design (index for which sweep we're dealing with when expecting multiple sweeps)
        mod_flow_conf_fpath: path to flow config file (possibly) modified in previous stages and used for this sweep point
        sweep_pt_idx: sweep point index for the current sweep (ie one of the points )
    """
    if asic_dse.design_sweep_infos[des_sweep_id].tool_env_conf_paths == None:
        rg_utils.rad_gen_log(f"WARN: No tool environment config files specified in {asic_dse.sweep_config_path}, cmd script won't be generated!",rad_gen_log_fd)
        return None, None
    
    asic_dse_args = rg_ds.AsicDseArgs(
        flow_conf_paths = asic_dse.design_sweep_infos[des_sweep_id].flow_conf_paths + [mod_flow_conf_fpath] if asic_dse.design_sweep_infos[des_sweep_id].flow_conf_paths != None else [mod_flow_conf_fpath],
        tool_env_conf_paths = asic_dse.design_sweep_infos[des_sweep_id].tool_env_conf_paths,
        **kwargs
    )
    rad_gen_args = rg_ds.RadGenArgs(
        subtools = ["asic_dse"],
        subtool_args = asic_dse_args,
    )
    rg_cmd, _, _ = rad_gen_args.get_rad_gen_cli_cmd(asic_dse.common.rad_gen_home_path)
    cmd_lines = [
        f"{rg_cmd} &", # Get the cmd then run in bg so we can run multiple sweeps in parallel
        "sleep 0.01", # Sleep for 0.01 seconds to make sure directories which are uniquified with a datetime tag are unique TODO fix
    ]
    if sweep_pt_idx % asic_dse.design_sweep_infos[des_sweep_id].flow_threads == 0 and sweep_pt_idx != 0:
        cmd_lines += ["wait"]
    sweep_pt_idx += 1

    return cmd_lines, sweep_pt_idx






def sram_sweep_gen(asic_dse: rg_ds.AsicDSE, design_id: int):
    # get current sweep, base config & RTL associated with it
    cur_design = asic_dse.design_sweep_infos[design_id]
    base_config = rg_utils.parse_config(cur_design.base_config_path)
    ## base_config = rg_utils.sanitize_config(yaml.safe_load(open(cur_design.base_config_path,"r")))
    ## This is where we will send the output sram macros
    ## if not os.path.isdir(asic_dse.sram_compiler_settings.rtl_out_path):
    ##     os.makedirs(asic_dse.sram_compiler_settings.rtl_out_path)
    # 
    gen_compiled_srams(asic_dse, design_id, base_config) #,base_config, sanitized_design)
    # mem_params = rg_utils.parse_config(base_config["vlsi.inputs.sram_parameters"])
    with open(os.path.expanduser(base_config["vlsi.inputs.sram_parameters"]), 'r') as fd:
        mem_params = json.load(fd)

    # List of available SRAM macros
    sram_macro_lefs = os.listdir(os.path.join(asic_dse.stdcell_lib.sram_lib_path, "lef"))

    # Retreive the path used for the sram base RTL (which we will modifying), it should not be renamed or moved from this location and will throw an error if its not found
    # sram_rtl_template_fpath = os.path.join( 
    #     asic_dse.common.project_tree.search_subtrees("shared_resources.sram_lib.rtl.src", is_hier_tag = True)[0].path,
    #     "sram_template.sv"
    # )
    # Check to see if valid
    # rg_utils.check_for_valid_path(sram_rtl_template_fpath)

    # sweep_script_lines = [
    #     "#!/bin/bash",
    # ]
    sweep_script_lines = []
    sweep_pt_idx = 1
    # Sweep over all widths and depths for SRAMs in the sweep config file  
    for rw_port in cur_design.type_info.rw_ports:
        for depth in cur_design.type_info.depths:
            for width in cur_design.type_info.widths:
                """ MODIFIYING MEM CONFIG JSON FILES """
                # If we want to iterate through and keep an original reference set of configs we need to use deepcopy on the dict
                # This concept is very annoying as when assigning any variable to a dict you are actually just creating a reference to the dict (Very unlike C) :(
                # All mem_params are indexed to 0 since we are only sweeping over a single SRAM TODO
                # Create copies of each configs s.t they can be modified without affecting the original
                mod_mem_params = copy.deepcopy(mem_params)
                modify_mem_params(mod_mem_params, width, depth, rw_port)
                # Make sure that the SRAM macro exists in the list of SRAM macros LEF files, if not just skip this SRAM 
                # TODO if it doesn't exist add option for it to be created via OpenRAM 
                if not any(mod_mem_params[0]["name"] in macro for macro in sram_macro_lefs):
                    rg_utils.rad_gen_log(f"WARNING: {mod_mem_params[0]['name']} not found in list of SRAM macros, skipping config generation...",rad_gen_log_fd)
                    continue
                
                # I/O WR Logging
                for ret_str in rg_utils.create_bordered_str(f"Generating files required for design: {mod_mem_params[0]['name']}"):
                    rg_utils.rad_gen_log(ret_str,rad_gen_log_fd)                        
                
                # Modify the mem_params.json file with the parameters specified in the design sweep config file
                # Wherever the sram_parameters files are specified in base_config file we will create directories for generated results
                mem_params_fpath = os.path.join(
                    asic_dse.common.project_tree.search_subtrees("shared_resources.sram_lib.configs.gen", is_hier_tag = True)[0].path, 
                    os.path.splitext(os.path.basename(base_config["vlsi.inputs.sram_parameters"]))[0] + f'_{mod_mem_params[0]["name"]}.json'
                )
                
                # I/O WR Logging
                rg_utils.rad_gen_log(f"INFO: Writing memory params to {mem_params_fpath}",rad_gen_log_fd)
                dump_config_to_json_file(mem_params_fpath, mod_mem_params)
                # with open(mem_params_fpath, 'w') as fd:
                #     json.dump(mod_mem_params, fd, sort_keys=False)
                
                """ MODIFIYING SRAM RTL"""
                # Get just the filename of the sram sv file and append the new sram dimensions to it
                mod_rtl_fname = os.path.splitext(os.path.basename(cur_design.type_info.sram_rtl_template_fpath))[0] + f'_{mod_mem_params[0]["name"]}.sv'

                # Modify the parameters for SRAM_ADDR_W and SRAM_DATA_W and create a copy of the base sram 
                # TODO find a better way to do this rather than just creating a ton of files, the only thing I'm changing are 2 parameters in rtl
                # I/O RD Logging
                with open(cur_design.type_info.sram_rtl_template_fpath, 'r') as fd:
                    base_rtl = fd.read()
                mod_sram_rtl = copy.deepcopy(base_rtl)
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
                edit_sram_inst_re = re.compile(f"^\s+//\s+START\sSRAM\s{port_str}\sINST.*END\sSRAM\s{port_str}", re.MULTILINE|re.DOTALL)
                # Edit the sram inst to use the correct sram macro module name
                sram_inst_rtl = edit_sram_inst_re.search(mod_sram_rtl).group(0)
                edit_sram_macro_name = re.compile(f"SRAM{rw_port}RW.*\s")
                edit_sram_inst = edit_sram_macro_name.sub(f'{mod_mem_params[0]["name"]} mem_0_0(\n',sram_inst_rtl)
                # The correct RTL for the sram inst is in the edit_sram_inst string so we now will replace the previous sram inst with the new one
                mod_sram_rtl = edit_sram_inst_re.sub(edit_sram_inst,mod_sram_rtl)
                
                # Edit the name of the top level wrapper module to reflect the new macro instantiated in it
                # regex does positive lookbehind for "module", then non capturing groups for leading/trailing wspace, then positive lookahead for "#(", ie should only match the "sram_wrapper"
                edit_wrapper_module_name_re = re.compile(r"(?<=module)(?:\s+)sram_wrapper(?:\s+)(?=\#\()")
                mod_sram_rtl = edit_wrapper_module_name_re.sub(f'{mod_mem_params[0]["name"]}_wrapper',mod_sram_rtl)

                # 
                # base_rtl_dir = os.path.split(cur_design.type_info.base_rtl_path)[0]
                # Create a new dir for the modified sram
                # mod_rtl_dir = os.path.join(base_rtl_dir,f'{mod_mem_params[0]["name"]}')
                
                # sp.call("mkdir -p " + mod_rtl_dir,shell=True)
                #
                # Create a new directory for each SRAM macro

                # Write the modified sram rtl to the sram compiler output directory
                modified_sram_rtl_path = os.path.join(asic_dse.sram_compiler_settings.rtl_out_dpath, mod_rtl_fname)
                with open(modified_sram_rtl_path, 'w') as fd:
                    fd.write(mod_sram_rtl)
                rg_utils.rad_gen_log(f"INFO: Writing sram rtl to {modified_sram_rtl_path}", rad_gen_log_fd)
                """ MODIFYING HAMMER CONFIG YAML FILES """
                m_sizes = get_sram_macro_sizes(asic_dse, mod_mem_params[0]["name"])
                # Now we need to modify the base_config file to use the correct sram macro
                # TODO bring these params to top level config
                macro_init = 15 if rw_port == 1 else 30
                macro_extra_logic_spacing = 15 if rw_port == 1 else 30
                top_lvl_idx = 0

                # Make a copy of the base config which we will modify
                mod_base_config = copy.deepcopy(base_config)
                for pc_idx, pc in enumerate(base_config["vlsi.inputs.placement_constraints"]):
                    # Check if its a hardmacro and do some check to make sure its an SRAM 
                    # TODO this requires "SRAM" to be in the macro name which is possibly dangerous
                    if pc["type"] == "hardmacro" and "SRAM" in pc["master"]:
                        mod_base_config["vlsi.inputs.placement_constraints"][pc_idx]["master"] = mod_mem_params[0]["name"]
                        mod_base_config["vlsi.inputs.placement_constraints"][pc_idx]["x"] = macro_init
                        mod_base_config["vlsi.inputs.placement_constraints"][pc_idx]["y"] = macro_init
                    # Check if placement contraint is for top level module
                    elif pc["type"] == "toplevel":
                        mod_base_config["vlsi.inputs.placement_constraints"][pc_idx]["width"] = macro_init + m_sizes[0] + macro_extra_logic_spacing
                        mod_base_config["vlsi.inputs.placement_constraints"][pc_idx]["height"] = macro_init + m_sizes[1] + macro_extra_logic_spacing
                        top_lvl_idx = pc_idx
                
                # Determine side of pin placement for top level module
                if (mod_base_config["vlsi.inputs.placement_constraints"][top_lvl_idx]["width"] > mod_base_config["vlsi.inputs.placement_constraints"][top_lvl_idx]["height"]):
                    mod_base_config["vlsi.inputs.pin.assignments"][0]["side"] = "bottom"
                else:
                    mod_base_config["vlsi.inputs.pin.assignments"][0]["side"] = "left"

                # TASKS WHICH ALLOW CONFIG TO BE RUN DIRECTLY WITHOUT PRE PROCESSING
                # Such as
                    # Setting inputs to all design files
                    # Setting HDL search paths
                    # Setting SRAM parameters to the ones we just created
                # Find design files in newly created rtl dir
                design_files, design_dirs = rg_utils.rec_get_flist_of_ext(asic_dse.sram_compiler_settings.rtl_out_dpath, ['.v','.sv','.vhd',".vhdl"])
                mod_base_config["synthesis.inputs.input_files"] = design_files
                mod_base_config["synthesis.inputs.hdl_search_paths"] = design_dirs
                mod_base_config["vlsi.inputs.sram_parameters"] = mem_params_fpath #os.path.splitext(base_config["vlsi.inputs.sram_parameters"])[0] + f'_{mod_mem_params[0]["name"]}.json'
                # Write the modified base_config file to a new file
                mod_flow_conf_fpath = os.path.join(
                    asic_dse.common.project_tree.search_subtrees("shared_resources.sram_lib.configs.gen", is_hier_tag = True)[0].path,
                    os.path.splitext(os.path.basename(cur_design.base_config_path))[0] + f'_{mod_mem_params[0]["name"]}.json'
                )

                # I/O WR Logging
                rg_utils.rad_gen_log(f"INFO: Writing rad_gen yml config to {mod_flow_conf_fpath}", rad_gen_log_fd)
                dump_config_to_json_file(mod_flow_conf_fpath, mod_base_config)

                # modified_config_path = os.path.splitext(cur_design.base_config_path)[0]+f'_{mod_mem_params[0]["name"]}.yaml'
                # with open(modified_config_path, 'w') as fd:
                #     yaml.safe_dump(mod_base_config, fd, sort_keys=False) 
                
                # Create a script cmd to run this sram compiler generated config through the tool
                cmd_lines, sweep_pt_idx = get_hammer_flow_sweep_point_lines(asic_dse, design_id, sweep_pt_idx, mod_flow_conf_fpath, sram_compiler=True)
                if cmd_lines == None:
                    continue
                sweep_script_lines += cmd_lines

    if sweep_script_lines:
        # write out script
        rg_utils.write_out_script(sweep_script_lines, os.path.join(asic_dse.sram_compiler_settings.scripts_out_dpath, "sram_single_macro_sweep.sh"))

   

def get_sram_macro_sizes(asic_dse: rg_ds.AsicDSE, macro_fname: str) -> list:
    for file in os.listdir(os.path.join(asic_dse.stdcell_lib.sram_lib_path,"lef")):
        m_sizes = []
        if macro_fname in file:
            # TODO fix the way that the size of macro is being searched for this way would not work in all cases
            lef_text = open(os.path.join(asic_dse.stdcell_lib.sram_lib_path,"lef",file), "r").read()
            for line in lef_text.split("\n"):
                if "SIZE" in line:
                    # This also assumes the symmetry in the lef is X Y rather than searching for it TODO
                    m_sizes = [float(s) for s in line.split(" ") if asic_dse.common.res.decimal_re.match(s)]
                    break
        if len(m_sizes) > 0:
            break
    return m_sizes


def mod_rad_gen_config_from_rtl(asic_dse: rg_ds.AsicDSE, base_config: dict, sram_map_info: dict, rtl_path: str) -> dict:
    # config_out_dpath = asic_dse.sram_compiler_settings.config_out_dpath
    # if not os.path.exists(config_out_path):
    #     os.mkdir(config_out_path)

    # create a copy which will be modified of the sram base config (hammer config)
    mod_base_config = copy.deepcopy(base_config)
    """ WRITING MEM PARAMS JSON FILES """
    ## load in the mem_params.json file            
    ## mem_params = rg_utils.parse_config(base_config["vlsi.inputs.sram_parameters"])
    # Can't use the above parse_config function as it can't seem to handle if json is not a dict at top level TODO fix this
    with open(os.path.expanduser(base_config["vlsi.inputs.sram_parameters"]), 'r') as fd:
        mem_params = json.load(fd)
    mod_mem_params = copy.deepcopy(mem_params)
    modify_mem_params(mod_mem_params, width=sram_map_info["macro_w"], depth=sram_map_info["macro_d"], num_ports=sram_map_info["num_rw_ports"])

    mem_params_json_fpath = os.path.join(asic_dse.sram_compiler_settings.config_out_dpath, "mem_params_"+f'_{sram_map_info["macro"]}.json')

    # mem_params_json_fpath = os.path.join(config_out_path,"mem_params_"+f'_{sram_map_info["macro"]}.json')
    dump_config_to_json_file(mem_params_json_fpath, mod_mem_params)
    # with open(mem_params_json_fpath, 'w') as fd:
    #     json.dump(mod_mem_params, fd, sort_keys=False)
    # Defines naming convension of SRAM macros TODO
    """ MODIFYING AND WRITING HAMMER CONFIG YAML FILES """
    
    m_sizes = get_sram_macro_sizes(asic_dse, sram_map_info["macro"])
    
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
    for pc_idx, pc in enumerate(base_config["vlsi.inputs.placement_constraints"]):
        # TODO make sure to set the dimensions of the top level to be larger than the sum of all sram macro placements and spacing
        # set the top level to that of the new mapped sram macro we created when writing the rtl
        if pc["type"] == "toplevel":
            mod_base_config["vlsi.inputs.placement_constraints"][pc_idx]["path"] = sram_map_info["top_level_module"]
            mod_base_config["vlsi.inputs.placement_constraints"][pc_idx]["width"] = sram_max_x + spacing_outline
            mod_base_config["vlsi.inputs.placement_constraints"][pc_idx]["height"] = sram_max_y + spacing_outline
        else:
            # clean placement constraints
            del mod_base_config["vlsi.inputs.placement_constraints"][pc_idx]
        #     # TODO this requires "SRAM" to be in the macro name which is possibly dangerous
        # if pc["type"] == "hardmacro" and "SRAM" in pc["master"]:
        #     mod_base_config["vlsi.inputs"]["placement_constraints"][pc_idx]["master"] = mod_mem_params[0]["name"]
    
    for sram_pc in sram_pcs:
        mod_base_config["vlsi.inputs.placement_constraints"].append(sram_pc)

    # Find design files in newly created rtl dir
    # TODO adapt to support multiple input files in the sram macro
    mod_base_config["synthesis.inputs.top_module"] = sram_map_info["top_level_module"]
    mod_base_config["synthesis.inputs.input_files"] = [rtl_path]
    mod_base_config["synthesis.inputs.hdl_search_paths"] = [os.path.split(rtl_path)[0]]
    mod_base_config["vlsi.inputs.sram_parameters"] = mem_params_json_fpath
    mod_base_config["vlsi.inputs.clocks"][0]["name"] = "clk" 

    # Write the modified base_config file to a new file
    modified_config_path = os.path.join(asic_dse.sram_compiler_settings.config_out_dpath, "sram_config_"+f'_{sram_map_info["top_level_module"]}.json')
    dump_config_to_json_file(modified_config_path, mod_base_config)
    # with open(modified_config_path, 'w') as fd:
    #     yaml.safe_dump(mod_base_config, fd, sort_keys=False) 
    return modified_config_path


# ██████╗  █████╗ ██████╗ ███████╗██╗███╗   ██╗ ██████╗     ██╗   ██╗████████╗██╗██╗     ███████╗
# ██╔══██╗██╔══██╗██╔══██╗██╔════╝██║████╗  ██║██╔════╝     ██║   ██║╚══██╔══╝██║██║     ██╔════╝
# ██████╔╝███████║██████╔╝███████╗██║██╔██╗ ██║██║  ███╗    ██║   ██║   ██║   ██║██║     ███████╗
# ██╔═══╝ ██╔══██║██╔══██╗╚════██║██║██║╚██╗██║██║   ██║    ██║   ██║   ██║   ██║██║     ╚════██║
# ██║     ██║  ██║██║  ██║███████║██║██║ ╚████║╚██████╔╝    ╚██████╔╝   ██║   ██║███████╗███████║
# ╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚═╝╚═╝  ╚═══╝ ╚═════╝      ╚═════╝    ╚═╝   ╚═╝╚══════╝╚══════╝


def parse_gds_to_area_output(rad_gen: rg_ds.AsicDSE, obj_dir_path: str):

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

def get_macro_info(rad_gen: rg_ds.AsicDSE, obj_dir: str, sram_num_bits: int = None) -> dict:
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

def parse_report_c(rad_gen_settings: rg_ds.AsicDSE, top_level_mod: str, report_path: str, rep_type: str, flow_stage: dict, summarize: bool = False):
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
                elif "slack" in line and rad_gen_settings.env_settings.res.decimal_re.search(line):
                    timing_dict["Slack"] = float(rad_gen_settings.env_settings.res.signed_dec_re.findall(line)[0])
                elif "Setup" in timing_dict and "Arrival" in timing_dict:
                    timing_dict["Delay"] = timing_dict["Arrival"] + timing_dict["Setup"]
                # This indicates taht all lines have been read in and we can append the timing_dict
            report_list.append(timing_dict)
        # elif flow_stage["tool"] == "synopsys":
        #     timing_dict = {}
        #     for line in timing_rpt_text.split("\n"):
        #         if "library setup time" in line:
        #             timing_dict["Setup"] = float(rad_gen_settings.env_settings.res.decimal_re.findall(line)[0])
        #         elif "data arrival time" in line:
        #             timing_dict["Arrival"] = float(rad_gen_settings.env_settings.res.decimal_re.findall(line)[0])
        #         elif "slack" in line:
        #             timing_dict["Slack"] = float(rad_gen_settings.env_settings.res.signed_dec_re.findall(line)[0])
        #         elif "Setup" in timing_dict and "Arrival" in timing_dict:
        #             timing_dict["Delay"] = timing_dict["Arrival"] + timing_dict["Setup"]
        #         # This indicates taht all lines have been read in and we can append the timing_dict
        #     report_list.append(timing_dict)
    elif(rep_type == "power"):
        power_rpt_text = open(report_path,"r").read()
        # TODO should have a section for subtools being used in stages of flow as dc_shell can do timing analysis but doesnt output primetime format
        if flow_stage["tool"] == "synopsys_dc":
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
        elif flow_stage["tool"] == "synopsys":
            power_dict = {}
            power_data = []
            # Section for capturing detailed primetime power data
            # TODO figure out something to do with this, it doesn't get returned to summary dict as others do because its format is tabular rather than a single row which can be mapped to df
            # for line in power_rpt_text.split("\n"):
            #     headers_captured = False
            #     # After headers captured we start to look at the values
            #     if headers_captured:
            #         power_data_dict = {}
            #         line_vals = rad_gen_settings.env_settings.res.wspace_re.split(line)
            #         if len(line_vals) != len(power_type_headers):
            #             break
                    
            #         for val_str, header in zip(line_vals, power_type_headers):
            #             if header not in ["Power Group", "Attributes"]:
            #                 val = rad_gen_settings.env_settings.res.sci_not_dec_re.search(val_str).group(0)
            #             else:
            #                 val = val_str
            #             power_data_dict[header] = val
            #             power_data.append(power_data_dict)
            #     # Based on power report we assume it starts with "Internal" for first line of column headers
            #     if "Internal" in line:
            #         # There is a "Power Group" and "Percentage" column on opposite of each sides
            #         power_type_headers = ["Power Group"] + rad_gen_settings.env_settings.res.wspace_re.split(line) + ["Percentage", "Attributes"]
            #         headers_captured = True
            for line in power_rpt_text.split("\n"):
                if "Net Switching Power" in line:
                    vals = rad_gen_settings.env_settings.res.sci_not_dec_re.findall(line)
                    power_dict["Switching"] = float(vals[0])
                elif "Cell Internal Power" in line:
                    vals = rad_gen_settings.env_settings.res.sci_not_dec_re.findall(line)
                    power_dict["Switching"] = float(vals[0])
                elif "Cell Leakage Power" in line:
                    vals = rad_gen_settings.env_settings.res.sci_not_dec_re.findall(line)
                    power_dict["Leakage"] = float(vals[0])
                elif "Total Power" in line:
                    vals = rad_gen_settings.env_settings.res.sci_not_dec_re.findall(line)
                    power_dict["Total"] = float(vals[0])
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


def get_report_results(rad_gen_settings: rg_ds.AsicDSE, top_level_mod: str, report_dir_path: str, flow_stage: dict) -> dict:
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
        rg_utils.rad_gen_log(f"Warning: {flow_stage['name']} report path does not exist", rad_gen_log_fd)
    return results 

def parse_output(rad_gen_settings: rg_ds.AsicDSE, top_level_mod: str, output_path: str):
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


def get_gds_area_from_rpt(rad_gen: rg_ds.AsicDSE, obj_dir: str):
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



def gen_reports(rad_gen_settings: rg_ds.AsicDSE, design: rg_ds.DesignSweepInfo , top_level_mod: str, report_dir: str, sram_num_bits: int = None):
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
            rg_utils.run_shell_cmd_no_logs(permission_cmd)
        # run_shell_cmd_no_logs(os.path.join(tech_info.pdk_rundir_path,f"{script_info.gds_to_area_fname}.sh"))
        if not os.path.exists(os.path.join(report_dir,rad_gen_settings.env_settings.report_info.gds_area_fname)):
            rg_utils.run_csh_cmd(os.path.join(rad_gen_settings.tech_info.pdk_rundir_path,f"{rad_gen_settings.env_settings.scripts_info.gds_to_area_fname}.csh"))
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


def gen_parse_reports(rad_gen_settings: rg_ds.AsicDSE, report_search_dir: str, top_level_mod: str, design: rg_ds.DesignSweepInfo = None, sram_num_bits: int = None):
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

def write_virtuoso_gds_to_area_script(rad_gen_settings: rg_ds.AsicDSE, gds_fpath: str):
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
        rg_utils.file_write_ln(fd, line)
    fd.close()
    fd = open(csh_fpath, 'w')
    for line in csh_script_lines:
        rg_utils.file_write_ln(fd, line)
    fd.close()


def write_lc_lib_to_db_script(rad_gen_settings: rg_ds.AsicDSE, in_libs_paths: List[str]):
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
        rg_utils.file_write_ln(fd,line)
    rg_utils.file_write_ln(fd,"quit")
    fd.close()

    return os.path.abspath(lc_script_path)


def run_asap7_gds_scaling_scripts(rad_gen: rg_ds.AsicDSE, obj_dir: str, top_lvl_mod: str):
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
                rg_utils.run_shell_cmd_no_logs(permission_cmd)
            rg_utils.run_csh_cmd(os.path.join(rad_gen.tech_info.pdk_rundir_path,f"{rad_gen.env_settings.scripts_info.gds_to_area_fname}.csh"))
            gds_area = parse_gds_to_area_output(rad_gen, obj_dir)
        else:
            gds_area = get_gds_area_from_rpt(rad_gen, obj_dir)

    return gds_area


def run_hammer_flow(rad_gen_settings: rg_ds.AsicDSE, config_paths: List[str]) -> Tuple[float]:
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
        rg_utils.run_shell_cmd_no_logs(f"mv hammer.d {os.path.join(rad_gen_settings.asic_flow_settings.hammer_driver.obj_dir,'build')}")
        file_lines = [
            "include build/hammer.d"
        ]
        with open( os.path.join(rad_gen_settings.asic_flow_settings.hammer_driver.obj_dir, "Makefile"),"w+") as fd:
            for line in file_lines:
                rg_utils.file_write_ln(fd,line)

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
            tech_cache_dir = os.path.basename(rad_gen_settings.asic_flow_settings.hammer_driver.tech.cache_dir)
            stdcells_fpath = os.path.join( rad_gen_settings.asic_flow_settings.hammer_driver.obj_dir, tech_cache_dir, "stdcells.txt")
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
            # Run Synopsys logic compiler to convert .lib to .db
            lc_script_path = write_lc_lib_to_db_script(rad_gen_settings, conversion_libs)
            lc_run_cmd = f"lc_shell -f {lc_script_path}"
            # Change to pt-rundir
            os.chdir(os.path.join(rad_gen_settings.asic_flow_settings.hammer_driver.obj_dir,"pt-rundir"))
            rg_utils.run_shell_cmd_no_logs(lc_run_cmd)
            # Change back to original directory
            os.chdir(work_dir)

        # Write STA & Power script
        write_pt_timing_script(rad_gen_settings)
        write_pt_power_script(rad_gen_settings)
        os.chdir(os.path.join(rad_gen_settings.asic_flow_settings.hammer_driver.obj_dir,"pt-rundir"))

        # Run Timing
        timing_stdout, timing_stderr = rg_utils.run_shell_cmd_no_logs("pt_shell -f pt_timing.tcl")
        with open("timing_stdout.log","w") as fd:
            fd.write(timing_stdout)
        with open("timing_stderr.log","w") as fd:
            fd.write(timing_stderr)

        # Run Power
        power_stdout, power_stderr = rg_utils.run_shell_cmd_no_logs("pt_shell -f pt_power.tcl")
        with open("power_stdout.log","w") as fd:
            fd.write(power_stdout)
        with open("power_stderr.log","w") as fd:
            fd.write(power_stderr)


        os.chdir(work_dir)
        
    pt_reports_path = os.path.join(rad_gen_settings.asic_flow_settings.hammer_driver.obj_dir, "pt-rundir", "reports")
    if os.path.isdir(pt_reports_path):
        pt_report = get_report_results(rad_gen_settings, rad_gen_settings.asic_flow_settings.top_lvl_module, pt_reports_path, rad_gen_settings.asic_flow_settings.flow_stages["pt"])
        flow_report["pt"] = pt_report

    # Now that we have all the reports, we can generate the final report
    report_to_csv = gen_report_to_csv(flow_report)
    df = pd.DataFrame.from_dict(report_to_csv, orient='index').T
    
    rg_utils.rad_gen_log("\n".join(rg_utils.get_df_output_lines(df)), rad_gen_log_fd)

    csv_fname = os.path.join(rad_gen_settings.asic_flow_settings.hammer_driver.obj_dir,"flow_report")
    rg_utils.write_dict_to_csv([report_to_csv], csv_fname)

    os.chdir(pre_flow_dir)

    # Convert to format COFFE finds acceptable (Area, Delay, Power)
    flow_results = (float(report_to_csv["Total Area"]), float(report_to_csv["Delay"]), float(report_to_csv["Total Power"])) 
    return flow_results
