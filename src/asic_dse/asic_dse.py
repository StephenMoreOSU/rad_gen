
# General imports
from typing import List, Dict, Tuple, Set, Union, Any, Type
import os, sys
from dataclasses import dataclass, asdict, fields
import datetime
import yaml
import re
import subprocess as sp
from pathlib import Path
import json
import copy
import math
import pandas as pd

from collections import defaultdict

# Hammer imports
from third_party.hammer.hammer.vlsi.cli_driver import dump_config_to_json_file


# asic_dse imports
import src.asic_dse.hammer_flow as asic_hammer
import src.asic_dse.custom_flow as asic_custom

# rad gen utils imports
import src.common.utils as rg_utils
import src.common.data_structs as rg_ds


rad_gen_log_fd = "asic_dse.log"
log_verbosity = 2
cur_env = os.environ.copy()


def compile_results(asic_dse: rg_ds.AsicDSE):
    # read in the result config file
    report_search_dir = asic_dse.env_settings.design_output_path
    csv_lines = []
    reports = []
    for design in asic_dse.design_sweep_infos:
        rg_utils.rad_gen_log(f"Parsing results of parameter sweep using parameters defined in {asic_dse.sweep_conf_fpath}",rad_gen_log_fd)
        if design.type != None:
            if design.type == "sram":
                for mem in design.type_info.mems:
                    mem_top_lvl_name = f"sram_macro_map_{mem['rw_ports']}x{mem['w']}x{mem['d']}"
                    num_bits = mem['w']*mem['d']
                    reports += asic_hammer.gen_parse_reports(asic_dse, report_search_dir, mem_top_lvl_name, design, num_bits)
                reports += asic_hammer.gen_parse_reports(asic_dse, report_search_dir, design.top_lvl_module, design)
            elif design.type == "rtl_params":
                """ Currently focused on NoC rtl params"""
                reports = asic_hammer.gen_parse_reports(asic_dse, report_search_dir, design.top_lvl_module, design)
            else:
                rg_utils.rad_gen_log(f"Error: Unknown design type {design.type} in {asic_dse.sweep_conf_fpath}",rad_gen_log_fd)
                sys.exit(1)
        else:
            # This parsing of reports just looks at top level and takes whatever is in the obj dir
            reports = asic_hammer.gen_parse_reports(asic_dse, report_search_dir, design.top_lvl_module)
        
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
    result_summary_outdir = os.path.join(asic_dse.env_settings.design_output_path,"result_summaries")
    if not os.path.isdir(result_summary_outdir):
        os.makedirs(result_summary_outdir)
    csv_fname = os.path.join(result_summary_outdir, os.path.splitext(os.path.basename(asic_dse.sweep_conf_fpath))[0] )
    rg_utils.write_dict_to_csv(csv_lines,csv_fname)

def design_sweep(asic_dse: rg_ds.AsicDSE) -> List[rg_ds.MetaDataclass]:
    """
        Returns a list of RadGenArgs objects, each containing rad_gen command line arguments for each design sweep point
        Basically when you run sweep it should return 'driver' objects that faciltate execution of that design point. 
    """
    rg_sw_pt_drivers: list = []

    # Starting with just SRAM configurations for a single rtl file (changing parameters in header file)
    rg_utils.rad_gen_log(f"Running design sweep from config file {asic_dse.sweep_conf_fpath}", rad_gen_log_fd)
    
    # for id, design_sweep in enumerate(asic_dse.design_sweep_infos):
    """ General flow for all designs in sweep config """
    design_sweep = asic_dse.design_sweep_info
    # Load in the base configuration file for the design
    base_config = rg_utils.parse_config(design_sweep.base_config_path)

    # Output to current project directory output "scripts" directory
    
    # TODO move below intializations to asic_dse init function, should not be here
    if design_sweep.type == "rtl" or design_sweep.type == "vlsi":
        scripts_out_dpath = asic_dse.common.project_tree.search_subtrees(
            f"{asic_dse.common.project_name}.outputs.{design_sweep.top_lvl_module}.script", is_hier_tag = True
        )[0].path
    
    elif design_sweep.type == "sram":
        # if doing sram sweep we don't need a top level module specified
        pass

    """ Currently only can sweep either vlsi params or rtl params not both """
    sweep_script_lines = []
    # If there are vlsi parameters to sweep over
    if design_sweep.type == "vlsi":
        mod_base_config = copy.deepcopy(base_config)
        """ MODIFYING HAMMER CONFIG YAML FILES """
        # sweep_idx = 1        
        
        # Validation
        # TODO move this validation to init function 
        custom_sweeps = {}
        for field in fields(design_sweep.vlsi_params.custom_map):
            field_val = getattr(design_sweep.vlsi_params.custom_map, field.name)
            if isinstance(field_val, list) and len(field_val) > 0:
                custom_sweeps[field.name] = field_val
        assert len(set([len(val) for val in custom_sweeps.values()])) == 1, "Custom map lists must be of equal length (each either being None or having an element for each sweep index)"
        # Get number of sweep points
        sweep_points = len(list(custom_sweeps.values())[0]) if custom_sweeps else 0
        for sweep_idx in range(sweep_points):
            param_fstr: str = "" # String which specifies which params have been modified in the config file
            for field in fields(design_sweep.vlsi_params.custom_map):
                field_val = getattr(design_sweep.vlsi_params.custom_map, field.name)
                sweep_pt_val = field_val[sweep_idx]
                # For any custom mapped fields implement the logic here
                if field.name == "period":
                    # <TAG> <HAMMER-IR-PARSE TODO> , This is looking for the period in parameters and will set the associated hammer IR to that value 
                    # TODO support multiple clocks
                    mod_base_config["vlsi.inputs.clocks"][0]["period"] = sweep_pt_val
                # TODO remove innovus specific stuff
                elif field.name == "core_util":
                    mod_base_config["par.innovus.floorplan_mode"] = "manual"
                    if mod_base_config.get("par.innovus.floorplan_script_contents") and asic_dse.common.res.inn_fp_grab_stdcell_density_re.search(mod_base_config.get("par.innovus.floorplan_script_contents")):
                        inn_fp_cmd: str = mod_base_config.get("par.innovus.floorplan_script_contents")
                    else:
                        inn_fp_cmd: str = r"create_floorplan -core_margins_by die -flip f -die_size_by_io_height max -site ${vlsi.technology.placement_site} -stdcell_density_size {1.0 0.7 10 10 10 10}"
                    stdcell_density_args: list[str] = asic_dse.common.res.inn_fp_grab_stdcell_density_re.search(inn_fp_cmd).group(0).strip().replace("{","").replace("}","").split()
                    stdcell_density_args[1] = str(sweep_pt_val)
                    mod_base_config["par.innovus.floorplan_script_contents"] = asic_dse.common.res.inn_fp_grab_stdcell_density_re.sub(f'{{{" ".join(stdcell_density_args)}}}', inn_fp_cmd)
                    mod_base_config["par.innovus.floorplan_script_contents_meta"] = "lazysubst"
                # TODO remove innovus specific stuff
                elif field.name == "effort":
                    mod_base_config["par.innovus.design_flow_effort"] = sweep_pt_val
                else:
                    Exception(f"Unhandled field {field.name} in custom_map")
                
                param_fstr += f"__{field.name}_{str(sweep_pt_val).replace(" ","")}"
            # TODO make paramater based naming optional, give ability to be named via hash of config or via parameters
            modified_config_fname = os.path.basename(os.path.splitext(design_sweep.base_config_path)[0]) + f'{param_fstr}.json'
            sweep_point_config_fpath = os.path.join( 
                asic_dse.common.project_tree.search_subtrees(f"{asic_dse.common.project_name}.configs.gen", is_hier_tag = True)[0].path,
                modified_config_fname
            )
            asic_hammer.mod_n_write_config_file(
                hdl_dpath = design_sweep.hdl_dpath,
                top_lvl_module = design_sweep.top_lvl_module,
                mod_conf_out_fpath = sweep_point_config_fpath,
                template_conf = mod_base_config
            )
            cmd_lines, _, rg_args = asic_hammer.get_hammer_flow_sweep_point_lines(asic_dse, sweep_idx, sweep_point_config_fpath)
            if cmd_lines == None:
                continue
            rg_sw_pt_drivers.append(rg_args)
            sweep_script_lines += cmd_lines

        # Get the path to write out script to, if the -l (override) flag is provided we will overwrite the script
        script_path = None
        
        # For timestamped scripts to be overrided on script gen
        if asic_dse.common.override_outputs:
            script_path = rg_utils.find_newest_file(scripts_out_dpath, f"{design_sweep.top_lvl_module}_vlsi_sweep_{rg_ds.create_timestamp(fmt_only_flag=True)}.sh", is_dir = False)
        
        if script_path == None:
            script_path = os.path.join(scripts_out_dpath, f"{design_sweep.top_lvl_module}_vlsi_sweep_{rg_ds.create_timestamp()}.sh")
        
        rg_utils.write_out_script(sweep_script_lines, script_path)

    # TODO This wont work for multiple SRAMs in a single design, simply to evaluate individual SRAMs
    elif design_sweep.type == "sram":
        rg_sw_pt_drivers += asic_hammer.sram_sweep_gen(asic_dse)
    # TODO make this more general but for now this is ok
    # the below case should deal with any asic_param sweep we want to perform
    elif design_sweep.type == 'rtl':
        # This is post initalization, so we can use the RTL path provided in the project config 
        rtl_dir_path = asic_dse.common.project_tree.search_subtrees(f"{asic_dse.common.project_name}.rtl.src", is_hier_tag = True)[0].path
        # We shouldn't need to edit the values of params/defines which are operations or values set to other params/defines
        # EDIT PARAMS/DEFINES IN THE SWEEP FILE
        # TODO this assumes parameter sweep vars arent kept over multiple files
        mod_param_hdr_paths, mod_config_fpaths = asic_hammer.edit_rtl_proj_params(asic_dse, design_sweep.rtl_params.sweep, design_sweep.rtl_params.base_header_fpath, design_sweep.base_config_path)
        sweep_idx = 1
        for hdr_path, config_fpath in zip(mod_param_hdr_paths, mod_config_fpaths):
            rg_utils.rad_gen_log(f"PARAMS FOR PATH {hdr_path}", rad_gen_log_fd)

            add_args = {
                "top_lvl_module": design_sweep.top_lvl_module,
                "hdl_path" : rtl_dir_path
            }
            cmd_lines, sweep_idx, rg_args = asic_hammer.get_hammer_flow_sweep_point_lines(asic_dse, sweep_idx, config_fpath, **add_args)
            if cmd_lines == None:
                continue
            rg_sw_pt_drivers.append(rg_args)
            sweep_script_lines += cmd_lines
            
            asic_hammer.read_in_rtl_proj_params(asic_dse, design_sweep.rtl_params.sweep, design_sweep.top_lvl_module, rtl_dir_path, hdr_path)

        script_path = None

        # Uncomment below for timestamped scripts to not be overrided on script gen (seems a bit unnecessary)
        if asic_dse.common.override_outputs:
            script_path = rg_utils.find_newest_file(scripts_out_dpath, f"{design_sweep.top_lvl_module}_rtl_sweep_{rg_ds.create_timestamp(fmt_only_flag=True)}.sh", is_dir = False)

        if script_path == None:
            script_path = os.path.join(scripts_out_dpath, f"{design_sweep.top_lvl_module}_rtl_sweep.sh_{rg_ds.create_timestamp()}.sh")
        
        rg_utils.write_out_script(sweep_script_lines, script_path)

    return rg_sw_pt_drivers

def run_asic_flow(asic_dse: rg_ds.AsicDSE) -> Dict[str, Any]:
    if asic_dse.mode.vlsi.flow == "custom":
        if asic_dse.mode.vlsi.run == "serial":
            for hb_settings in asic_dse.custom_asic_flow_settings["asic_hardblock_params"]["hardblocks"]:
                flow_results = asic_custom.hardblock_flow(hb_settings)
        elif asic_dse.mode.vlsi.run == "parallel":
            for hb_settings in asic_dse.custom_asic_flow_settings["asic_hardblock_params"]["hardblocks"]:
                # TODO get flow results from parallel flow
                asic_custom.hardblock_parallel_flow(hb_settings)
                flow_results = None
    elif asic_dse.mode.vlsi.flow == "hammer":
      # If the args for top level and rtl path are not set, we will use values from the config file
      in_configs = []
      if asic_dse.mode.vlsi.config_pre_proc:
          """ Check to make sure all parameters are assigned and modify if required to"""
          mod_config_file = asic_hammer.modify_config_file(asic_dse)
          in_configs.append(mod_config_file)

      # Run the flow
      flow_results = asic_hammer.run_hammer_flow(asic_dse, in_configs)
       
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
        ret_info = design_sweep(asic_flow_dse_info)
    elif asic_flow_dse_info.mode.vlsi.enable:
        ret_info = run_asic_flow(asic_flow_dse_info)

    return ret_info
