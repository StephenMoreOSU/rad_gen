
# General imports
from typing import List, Dict, Tuple, Set, Union, Any, Type
import os, sys
from dataclasses import dataclass, asdict
import datetime
import yaml
import re
import subprocess as sp
from pathlib import Path
import json
import copy
import math
import pandas as pd


# asic_dse imports
import src.asic_dse.hammer_flow as asic_hammer
import src.asic_dse.custom_flow as asic_custom

# rad gen utils imports
import src.common.utils as rg_utils
import src.common.data_structs as rg_ds


rad_gen_log_fd = "asic_dse.log"
log_verbosity = 2
cur_env = os.environ.copy()

def compile_results(rad_gen_settings: rg_ds.HighLvlSettings):
    # read in the result config file
    report_search_dir = rad_gen_settings.env_settings.design_output_path
    csv_lines = []
    reports = []
    for design in rad_gen_settings.design_sweep_infos:
        rg_utils.rad_gen_log(f"Parsing results of parameter sweep using parameters defined in {rad_gen_settings.sweep_config_path}",rad_gen_log_fd)
        if design.type != None:
            if design.type == "sram":
                for mem in design.type_info.mems:
                    mem_top_lvl_name = f"sram_macro_map_{mem['rw_ports']}x{mem['w']}x{mem['d']}"
                    num_bits = mem['w']*mem['d']
                    reports += asic_hammer.gen_parse_reports(rad_gen_settings, report_search_dir, mem_top_lvl_name, design, num_bits)
                reports += asic_hammer.gen_parse_reports(rad_gen_settings, report_search_dir, design.top_lvl_module, design)
            elif design.type == "rtl_params":
                """ Currently focused on NoC rtl params"""
                reports = asic_hammer.gen_parse_reports(rad_gen_settings, report_search_dir, design.top_lvl_module, design)
            else:
                rg_utils.rad_gen_log(f"Error: Unknown design type {design.type} in {rad_gen_settings.sweep_config_path}",rad_gen_log_fd)
                sys.exit(1)
        else:
            # This parsing of reports just looks at top level and takes whatever is in the obj dir
            reports = asic_hammer.gen_parse_reports(rad_gen_settings, report_search_dir, design.top_lvl_module)
        
        # General parsing of report to csv
        for report in reports:
            report_to_csv = {}
            if design.type == "rtl_params":
                if "rtl_params" in report.keys():
                    report_to_csv = asic_hammer.noc_prse_area_brkdwn(report)
            else:
                report_to_csv = asic_hammer.gen_report_to_csv(report)
            if len(report_to_csv) > 0:
                csv_lines.append(report_to_csv)
    result_summary_outdir = os.path.join(rad_gen_settings.env_settings.design_output_path,"result_summaries")
    if not os.path.isdir(result_summary_outdir):
        os.makedirs(result_summary_outdir)
    csv_fname = os.path.join(result_summary_outdir, os.path.splitext(os.path.basename(rad_gen_settings.sweep_config_path))[0] )
    rg_utils.write_dict_to_csv(csv_lines,csv_fname)

def design_sweep(rad_gen_settings: rg_ds.HighLvlSettings):
    # Starting with just SRAM configurations for a single rtl file (changing parameters in header file)
    rg_utils.rad_gen_log(f"Running design sweep from config file {rad_gen_settings.sweep_config_path}",rad_gen_log_fd)
    
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
                            asic_hammer.get_rad_gen_flow_cmd(rad_gen_settings, modified_config_path, sram_flag=False, top_level_mod=design_sweep.top_lvl_module, hdl_path=design_sweep.rtl_dir_path) + " &",
                            "sleep 2",
                        ]
                        sweep_script_lines += rad_gen_cmd_lines
                        if sweep_idx % design_sweep.flow_threads == 0 and sweep_idx != 0:
                            sweep_script_lines.append("wait")
                        sweep_idx += 1
            rg_utils.rad_gen_log("\n".join(rg_utils.create_bordered_str("Autogenerated Sweep Script")),rad_gen_log_fd)
            rg_utils.rad_gen_log("\n".join(sweep_script_lines),rad_gen_log_fd)
            sweep_script_lines = rg_utils.create_bordered_str("Autogenerated Sweep Script") + sweep_script_lines
            script_path = os.path.join(scripts_outdir, f"{design_sweep.top_lvl_module}_vlsi_sweep.sh")
            for line in sweep_script_lines:
                with open(script_path , "w") as fd:
                    rg_utils.file_write_ln(fd, line)
            permission_cmd = f"chmod +x {script_path}"
            rg_utils.run_shell_cmd_no_logs(permission_cmd)
        # TODO This wont work for multiple SRAMs in a single design, simply to evaluate individual SRAMs
        elif design_sweep.type == "sram":      
            asic_hammer.sram_sweep_gen(rad_gen_settings, id)                
        # TODO make this more general but for now this is ok
        # the below case should deal with any asic_param sweep we want to perform
        elif design_sweep.type == 'rtl_params':
            mod_param_hdr_paths, mod_config_paths = asic_hammer.edit_rtl_proj_params(design_sweep.type_info.params, design_sweep.rtl_dir_path, design_sweep.type_info.base_header_path, design_sweep.base_config_path)
            sweep_idx = 1
            for hdr_path, config_path in zip(mod_param_hdr_paths, mod_config_paths):
            # for hdr_path in mod_param_hdr_paths:
                rg_utils.rad_gen_log(f"PARAMS FOR PATH {hdr_path}",rad_gen_log_fd)
                rad_gen_cmd_lines = [
                    asic_hammer.get_rad_gen_flow_cmd(rad_gen_settings, config_path, sram_flag=False, top_level_mod=design_sweep.top_lvl_module, hdl_path=design_sweep.rtl_dir_path) + " &",
                    "sleep 2",
                ]
                sweep_script_lines += rad_gen_cmd_lines
                if sweep_idx % design_sweep.flow_threads == 0 and sweep_idx != 0:
                    sweep_script_lines.append("wait")
                sweep_idx += 1
                # rad_gen_log(get_rad_gen_flow_cmd(config_path,sram_flag=False,top_level_mod=sanitized_design["top_level_module"],hdl_path=sanitized_design["rtl_dir_path"]),rad_gen_log_fd)
                asic_hammer.read_in_rtl_proj_params(rad_gen_settings, design_sweep.type_info.params, design_sweep.top_lvl_module, design_sweep.rtl_dir_path, hdr_path)
                """ We shouldn't need to edit the values of params/defines which are operations or values set to other params/defines """
                """ EDIT PARAMS/DEFINES IN THE SWEEP FILE """
                # TODO this assumes parameter sweep vars arent kept over multiple files
            rg_utils.rad_gen_log("\n".join(rg_utils.create_bordered_str("Autogenerated Sweep Script")),rad_gen_log_fd)
            rg_utils.rad_gen_log("\n".join(sweep_script_lines),rad_gen_log_fd)
            sweep_script_lines = rg_utils.create_bordered_str("Autogenerated Sweep Script") + sweep_script_lines
            script_path = os.path.join(scripts_outdir, f"{design_sweep.top_lvl_module}_rtl_sweep.sh")
            for line in sweep_script_lines:
                with open( script_path, "w") as fd:
                    rg_utils.file_write_ln(fd, line)
            permission_cmd = f"chmod +x {script_path}"
            rg_utils.run_shell_cmd_no_logs(permission_cmd)

def run_asic_flow(rad_gen_settings: rg_ds.HighLvlSettings) -> Dict[str, Any]:
    if rad_gen_settings.mode.vlsi_flow.flow_mode == "custom":
        if rad_gen_settings.mode.vlsi_flow.run_mode == "serial":
            for hb_settings in rad_gen_settings.custom_asic_flow_settings["asic_hardblock_params"]["hardblocks"]:
                flow_results = asic_custom.hardblock_flow(hb_settings)
        elif rad_gen_settings.mode.vlsi_flow.run_mode == "parallel":
            for hb_settings in rad_gen_settings.custom_asic_flow_settings["asic_hardblock_params"]["hardblocks"]:
                # Maybe 
                asic_custom.hardblock_parallel_flow(hb_settings)
                flow_results = None
    elif rad_gen_settings.mode.vlsi_flow.flow_mode == "hammer":
      # If the args for top level and rtl path are not set, we will use values from the config file
      in_configs = []
      if rad_gen_settings.mode.vlsi_flow.config_pre_proc:
          """ Check to make sure all parameters are assigned and modify if required to"""
          mod_config_file = asic_hammer.modify_config_file(rad_gen_settings)
          in_configs.append(mod_config_file)

      # Run the flow
      flow_results = asic_hammer.run_hammer_flow(rad_gen_settings, in_configs)
       
    rg_utils.rad_gen_log("Done!", rad_gen_log_fd)
    return flow_results


def run_asic_dse(asic_dse_cli: rg_ds.AsicDseCLI) -> Tuple[float]:
    global cur_env
    global rad_gen_log_fd
    global log_verbosity

    #Clear rad gen log
    fd = open(rad_gen_log_fd, 'w')
    fd.close()


    # Hack to convert asic_dse_cli to dict as input for init_structs function
    asic_dse_conf = asdict(asic_dse_cli)

    asic_flow_dse_info = rg_utils.init_asic_dse_structs(asic_dse_conf)

    # args, gen_arg_keys, default_arg_vals = rg_utils.parse_rad_gen_top_cli_args()

    # rad_gen_settings = init_structs(args)
    # rad_gen_info = rg_utils.init_structs_top(args, gen_arg_keys, default_arg_vals)

    ret_info = None
    """ Ex. args python3 rad_gen.py -s param_sweep/configs/noc_sweep.yml -c """
    if asic_flow_dse_info.mode.result_parse:
        compile_results(asic_flow_dse_info)
    # If a design sweep config file is specified, modify the flow settings for each design in sweep
    elif asic_flow_dse_info.mode.sweep_gen:
        design_sweep(asic_flow_dse_info)
    elif asic_flow_dse_info.mode.vlsi_flow.enable:
        ret_info = run_asic_flow(asic_flow_dse_info)

    return ret_info
