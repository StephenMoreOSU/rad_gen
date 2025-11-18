
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

from operator import itemgetter
from itertools import groupby

rad_gen_log_fd = "asic_dse.log"
log_verbosity = 2
cur_env = os.environ.copy()


# TODO remove duplicated function
def decode_sram_name(sram_str: str, stitched_flag: bool = False):
    """ Decode the SRAM name into its parameters (for top lvl module names)"""
    ret_val = None
    mod_name: str = "SRAM" if not stitched_flag else "sram_macro_map_"
    # SRAM name format: SRAM<NUM_RW_PORTS><WIDTH>x<DEPTH>
    if(mod_name in sram_str):
        if not stitched_flag:
            rw_ports_re = re.compile(f"(?<={mod_name})\d+(?=RW)")
            depth_re = re.compile("(?<=RW)\d+(?=x)")
            width_re = re.compile("(?<=x)\d+")
            
            rw_ports = int(rw_ports_re.search(sram_str).group())
            width = int(width_re.search(sram_str).group())
            depth = int(depth_re.search(sram_str).group())
            ret_val = rw_ports, width, depth
        else:
            pattern = r'sram_macro_map_(\d+)x(\d+)x(\d+)'
            ret_val = map(int, re.match(pattern, sram_str).groups())
            # rw_ports_re = re.compile(f"(?<={mod_name})\d+(?=x)")
            # depth_re = re.compile("(?<=x)\d+($|\-)")
            # width_re = re.compile("(?<=x)\d+(?=x)")


    return ret_val

def get_obj_dir_info(obj_dpath: str) -> dict:
    """
        Returns a dictionary containing information about an object directory.
        Information includes:
        - Distance gone in the flow
            - what reports exist?
        - VLSI parameters (from syn-rundir)
    """
    info: dict = {
        "sram": False,
        "syn": False,
        "par": False,
        "timing": False,
        "power": False,
        "final": False,
    }
    # We determine VLSI params from syn rundir
    if os.path.isdir(os.path.join(obj_dpath, "syn-rundir")):
        syn_out_fpath = os.path.join(obj_dpath, "syn-rundir", "syn-output-full.json")
        if os.path.exists(syn_out_fpath):
            vlsi_info = json.load(open(syn_out_fpath, "r"))
            if vlsi_info.get("vlsi.inputs.sram_parameters"):
                obj_name = os.path.basename(obj_dpath)
                if "macro_map" in obj_name:
                    stitched_flag = True
                else:
                    stitched_flag = False
                _, width, depth = decode_sram_name(obj_name, stitched_flag)
                macro_w = int(vlsi_info["vlsi.inputs.sram_parameters"][0]["width"])
                macro_d = int(vlsi_info["vlsi.inputs.sram_parameters"][0]["depth"])
                sram_info = {
                    "macro": vlsi_info["vlsi.inputs.sram_parameters"][0]["name"],
                    "macro_w": macro_w,
                    "macro_d": macro_d,
                    "ports": len(vlsi_info["vlsi.inputs.sram_parameters"][0]["ports"]),
                    "mapped_w": width,
                    "mapped_d": depth,
                    "num_macro_w": int(math.ceil( width / macro_w)),
                    "num_macro_d": int(math.ceil( depth / macro_d)),
                }
                info["sram"] = True
                info = {
                    **sram_info,
                    **info,
                }
            # General VLSI settings
            info = {
                "top_lvl_module": vlsi_info["vlsi.inputs.placement_constraints"][0]["path"], # top level module
                "technology": vlsi_info["vlsi.core.technology"], # process tech
                "target_period": vlsi_info["vlsi.inputs.clocks"][0]["period"], # target period
                **info,
            }
            # Place and Route Info
            info = {
                "effort": vlsi_info["par.innovus.design_flow_effort"], # par effort
                "floorplan_mode": vlsi_info["par.innovus.floorplan_mode"], 
                **info,
            }
        else:
            # If the syn-output-full.json file does not exist, we can't determine the VLSI params, just return
            return info
    # Now we get the existing information from the reports
    flow_order = ["syn", "par", "timing", "power", "final"]
    flow_order.reverse()
    for rep_tag in flow_order:
        reports_dpath = os.path.join(obj_dpath, "reports")
        if os.path.exists(os.path.join(reports_dpath, f"{rep_tag}_report.csv")):
            rep_info: dict = rg_utils.read_csv_to_list(os.path.join(reports_dpath, f"{rep_tag}_report.csv"))
            info[rep_tag] = True
            for key in ["Total Area", "Delay", "Total Power", "GDS Area"]:
                if not info.get(key):
                    info[key] = rep_info[0].get(key)
    return info

def get_obj_dir_flow_score(obj_dir_info: dict) -> int:
    """
        Returns a score for the object directory based on how far it has gotten in the flow
        - syn = 1
        - par = 2
        - timing = 3
        - power = 4
        - final = 5
    """
    flow_order = ["syn", "par", "timing", "power", "final"]
    for key in flow_order:
        if obj_dir_info.get(key):
            return flow_order.index(key) + 1
    return 0

def get_obj_dir_qor_score(obj_dir_info: dict) -> float:
    """
        Returns a score for the object directory based on the quality of results
        Score function is (1 / delay) * (1 / area) 
    """
    score: float = 1.0
    delay: int | None = obj_dir_info.get("Delay")
    total_area: int | None = obj_dir_info.get("Total Area")
    total_power: int | None = obj_dir_info.get("Total Power")
    gds_area: int | None = obj_dir_info.get("GDS Area")
    
    if delay:
        delay = float(delay)
    if total_area:
        total_area = float(total_area)
    if total_power:
        total_power = float(total_power)
    if gds_area:
        gds_area = float(gds_area)
    
    if not delay or not total_area:
        assert False, "Delay or Total Area not found in obj_dir_info, this should not happen"
    
    score *= (1 / delay)
    # score *= (1 / obj_dir_info.get("Total Power")) # uncomment to include power in the cost function
    if gds_area:
        score *= (1 / gds_area)
    else:
        score *= (1 / total_area)

    return score



def group_dicts(
    data: List[Tuple[str, Dict]],
    group_fields: List[str]
) -> List[List[Tuple[str, Dict]]]:
    """
        Groups a list of (obj_dir, dict) tuples by unique values of specified group fields.

        Args:
            data: A list of tuples where each tuple contains an obj_dir string and its corresponding dictionary.
            group_fields: A list of dictionary keys to group by.

        Returns:
            A list of groups, where each group is a list of (str, dict) tuples sharing the same group field values.
    """
    # Define a key function that extracts the group_fields from the dict part of the tuple
    def key_func(item: Tuple[str, Dict]) -> Tuple:
        return tuple(item[1].get(field) for field in group_fields)

    # Sort the data based on the group_fields extracted by key_func
    sorted_data = sorted(data, key=key_func)
    # Group the sorted data using groupby with the same key_func
    grouped = groupby(sorted_data, key=key_func)
    # Extract the groups into a list of lists
    return [list(group) for _, group in grouped]

# def group_dicts(data: list[dict], group_fields: list[str]) -> list[list[dict]]:
#     # Sort data based on group_fields
#     sorted_data = sorted(data, key=itemgetter(*group_fields))
#     # Group using groupby
#     grouped = groupby(sorted_data, key=itemgetter(*group_fields))
#     # Extract groups
#     return [list(group) for key, group in grouped]

# def group_dicts(data: list[dict], group_fields: list[str]) -> list[list[dict]]:
#     grouped = defaultdict(list)
#     for item in data:
#         # Create a tuple of the values for the grouping fields
#         key = tuple(item[field] for field in group_fields)
#         grouped[key].append(item)
#     # Return the grouped data as a list of lists
#     return list(grouped.values())

def get_condensed_obj_dirs(obj_dirs_dpath: str) -> list[str]:
    """
        Returns a list of unique object directories that have been condensed (filtering out duplicates and keeping high QoR runs)
    """
    condensed_dirs: Set = set()
    print(f"Top LVL Module: {os.listdir(obj_dirs_dpath)[0]}, num_dirs: {len(os.listdir(obj_dirs_dpath))}")
    if len(os.listdir(obj_dirs_dpath)) > 1:
        max_flow_score: int = max( 
            [
                get_obj_dir_flow_score(get_obj_dir_info(os.path.join(obj_dirs_dpath, obj_dir)))
                    for obj_dir in os.listdir(obj_dirs_dpath)
            ]
        )
        # Find the object directories that have gone the furthest in the CAD flow
        valid_obj_dirs = [ 
            obj_dir for obj_dir in os.listdir(obj_dirs_dpath) 
                if get_obj_dir_flow_score(get_obj_dir_info(os.path.join(obj_dirs_dpath, obj_dir))) == max_flow_score
        ]
        # Return a list of object directories which have unique VLSI parameters
        vlsi_fields = [
            "technology",
            "target_period",
            "effort",
            "floorplan_mode",
        ]
        grouped_obj_dirs: list[list[dict]] = []
        # eliminate obj dirs without all vlsi fields
        valid_obj_dirs = [ obj_dir for obj_dir in valid_obj_dirs if all(get_obj_dir_info(os.path.join(obj_dirs_dpath, obj_dir)).get(field) for field in vlsi_fields) ]
        # Group the object directories by their VLSI parameters 
        grouped_obj_dirs = group_dicts(
            data=[
                (obj_dir, get_obj_dir_info(os.path.join(obj_dirs_dpath, obj_dir)))
                for obj_dir in valid_obj_dirs
            ],
            group_fields=vlsi_fields,
        )
        # Iterate through groups and find the highest QoR score for each group
        for vlsi_group in grouped_obj_dirs:
            obj_dir_score_tup: list[tuple] = [
                (obj_dir, get_obj_dir_qor_score(obj_dir_info))
                    for obj_dir, obj_dir_info in vlsi_group
            ]
            # Sort the object directories by their QoR score
            obj_dir_score_tup.sort(key = lambda x: x[1], reverse = True)
            # Add the object directory with the highest QoR score to the condensed_dirs set
            condensed_dirs.add(obj_dir_score_tup[0][0])
    else:
        condensed_dirs.add(
            os.path.join(obj_dirs_dpath,os.listdir(obj_dirs_dpath)[0])
        )
    return condensed_dirs

        
        
        # for obj_dir in os.listdir(obj_dirs_dpath):
        #     # Skip if object directory has already been invalidated
        #     if any(obj_dir in con_dirs or obj_dir in skipped_dirs):
        #         continue
        
        # for obj_dir_1 in os.listdir(obj_dirs_dpath):
        #     for obj_dir_2 in os.listdir(obj_dirs_dpath):
        #         if (obj_dir_1 == obj_dir_2) or \
        #             any(dir in con_dirs or dir in skipped_dirs for dir in (obj_dir_1, obj_dir_2)):
        #             continue
        #         info1 = get_obj_dir_info(os.path.join(obj_dirs_dpath,obj_dir_1))
        #         info2 = get_obj_dir_info(os.path.join(obj_dirs_dpath,obj_dir_2))
        #         if info1 == info2:
        #             con_dirs.add(obj_dir_1)
        #             skipped_dirs.add(obj_dir_2)
        #         else:
        #             if cmp_obj_dir_infos(info1, info2):
        #                 con_dirs.add(obj_dir_1)
        #                 skipped_dirs.add(obj_dir_2)
        #             else:
        #                 con_dirs.add(obj_dir_2)
        #                 skipped_dirs.add(obj_dir_1)
        
    # else:
    #     con_dirs.add(os.path.join(obj_dirs_dpath,os.listdir(obj_dirs_dpath)[0]))
        
    # return con_dirs
        
        
    

def compile_results(
    asic_dse: rg_ds.AsicDSE, 
    top_lvl_modules: list[str] = None,
) -> None:
    """
        Parses the results of all output directories matching the provided top_lvl_modules. 
        Creates top level detailed and summary reports from this information.
        Will index each object directory from the top_lvl_module based on its VLSI parameters, determined from the synthesis input json file.
        Looks for duplicate runs (and filters them out) by seeing if they have the same VLSI parameters & QoR (for syn / par / timing / power).
        Will additionally filter with RTL or SRAM macro information based on if the tag is either "sram" or "rtl".
        
        If `top_lvl_modules` is not provided, it will loop through all top level modules within the project output directory.

        Args:
            asic_dse: The ASIC DSE object containing all the information about the design sweep
            top_lvl_modules: The top level modules to search for in the output directories
            tag: The tag to filter the results by, either "sram" or "rtl"
            
        Todo:
            * Allow for SRAMs and non SRAMs to be specified in the same `top_lvl_modules` list
    """
    out_search_dpath: str = asic_dse.common.project_tree.search_subtrees(f"projects.{asic_dse.common.project_name}.outputs", is_hier_tag = True)[0].path
    if not top_lvl_modules:
        top_lvl_modules = os.listdir(out_search_dpath)
    for top_lvl_module in top_lvl_modules:
        reports = []
        csv_lines = []
        top_lvl_mod_infos = []
        top_lvl_mod_search_dpath = os.path.join(out_search_dpath, top_lvl_module)
        if os.path.isdir(top_lvl_mod_search_dpath):
            obj_dirs_dpath = os.path.join(top_lvl_mod_search_dpath, "obj_dirs")
            # for obj_dir_dpath in os.listdir(obj_dirs_dpath):
            uniq_obj_dirs = get_condensed_obj_dirs(obj_dirs_dpath)
            for obj_dir in uniq_obj_dirs:
                reports.append(asic_hammer.gen_reports(asic_dse, asic_dse.design_sweep_info, top_lvl_module, os.path.join(obj_dirs_dpath, obj_dir)))
                obj_dir_info = get_obj_dir_info(os.path.join(obj_dirs_dpath, obj_dir))
                top_lvl_mod_infos.append(obj_dir_info)
        # Write out the top level module info to a csv
        top_lvl_report_dpath = os.path.join(top_lvl_mod_search_dpath, "reports")
        if top_lvl_mod_infos:
            rg_utils.write_dict_to_csv(top_lvl_mod_infos, os.path.join(top_lvl_report_dpath,f"summary"))
        #########################################################################################
        rg_utils.rad_gen_log(f"Parsing results of parameter sweep using parameters defined in {asic_dse.sweep_conf_fpath}",rad_gen_log_fd)
        
        # if asic_dse.design_sweep_info.type != None:
        #     if asic_dse.design_sweep_info.type == "sram":
        #         reports += asic_hammer.gen_parse_reports(asic_dse, top_lvl_mod_search_dpath, top_lvl_module, asic_dse.design_sweep_info)
        #         # for mem in design.type_info.mems:
        #         #     mem_top_lvl_name = f"sram_macro_map_{mem['rw_ports']}x{mem['w']}x{mem['d']}"
        #         #     num_bits = mem['w']*mem['d']
        #         #     reports += asic_hammer.gen_parse_reports(asic_dse, report_search_dir, mem_top_lvl_name, design, num_bits)
        #         # reports += asic_hammer.gen_parse_reports(asic_dse, report_search_dir, design.top_lvl_module, design)
        #     elif asic_dse.design_sweep_info.type == "rtl":
        #         """ Currently focused on NoC rtl params"""
        #         reports = asic_hammer.gen_parse_reports(asic_dse, top_lvl_mod_search_dpath, top_lvl_module, asic_dse.design_sweep_info)
        #     else:
        #         rg_utils.rad_gen_log(f"Error: Unknown design type {asic_dse.design_sweep_info.type} in {asic_dse.sweep_conf_fpath}",rad_gen_log_fd)
        #         sys.exit(1)
        # else:
        #     # This parsing of reports just looks at top level and takes whatever is in the obj dir
        #     reports = asic_hammer.gen_parse_reports(asic_dse, top_lvl_mod_search_dpath, top_lvl_module)
        
        # General parsing of report to csv
        for report in reports:
            report_to_csv = {}
            if asic_dse.design_sweep_info.type == "rtl":
                if "rtl_params" in report.keys():
                    report_to_csv = asic_hammer.noc_prse_area_brkdwn(report)
            else:
                report_to_csv = asic_hammer.gen_report_to_csv(report)
            if len(report_to_csv) > 0:
                csv_lines.append(report_to_csv)
        # result_summary_outdir = os.path.join(asic_dse.env_settings.design_output_path,"result_summaries") # TODO remove anything that uses deprecated `env_settings`
        # if not os.path.isdir(result_summary_outdir):
            # os.makedirs(result_summary_outdir)
        # csv_fname = os.path.join(result_summary_outdir, os.path.splitext(os.path.basename(asic_dse.sweep_conf_fpath))[0] )
        rg_utils.write_dict_to_csv(csv_lines,os.path.join(top_lvl_report_dpath,f"detailed"))
        #########################################################################################


    
# def compile_results(asic_dse: rg_ds.AsicDSE):
#     # read in the result config file
#     report_search_dir = asic_dse.env_settings.design_output_path
#     csv_lines = []
#     reports = []
#     for design in asic_dse.design_sweep_infos:
#         rg_utils.rad_gen_log(f"Parsing results of parameter sweep using parameters defined in {asic_dse.sweep_conf_fpath}",rad_gen_log_fd)
#         if design.type != None:
#             if design.type == "sram":
#                 for mem in design.type_info.mems:
#                     mem_top_lvl_name = f"sram_macro_map_{mem['rw_ports']}x{mem['w']}x{mem['d']}"
#                     num_bits = mem['w']*mem['d']
#                     reports += asic_hammer.gen_parse_reports(asic_dse, report_search_dir, mem_top_lvl_name, design, num_bits)
#                 reports += asic_hammer.gen_parse_reports(asic_dse, report_search_dir, design.top_lvl_module, design)
#             elif design.type == "rtl_params":
#                 """ Currently focused on NoC rtl params"""
#                 reports = asic_hammer.gen_parse_reports(asic_dse, report_search_dir, design.top_lvl_module, design)
#             else:
#                 rg_utils.rad_gen_log(f"Error: Unknown design type {design.type} in {asic_dse.sweep_conf_fpath}",rad_gen_log_fd)
#                 sys.exit(1)
#         else:
#             # This parsing of reports just looks at top level and takes whatever is in the obj dir
#             reports = asic_hammer.gen_parse_reports(asic_dse, report_search_dir, design.top_lvl_module)
        
#         # General parsing of report to csv
#         for report in reports:
#             report_to_csv = {}
#             if design.type == "rtl_params":
#                 if "rtl_params" in report.keys():
#                     report_to_csv = asic_hammer.noc_prse_area_brkdwn(report)
#             else:
#                 report_to_csv = asic_hammer.gen_report_to_csv(report)
#             if len(report_to_csv) > 0:
#                 csv_lines.append(report_to_csv)
#     result_summary_outdir = os.path.join(asic_dse.env_settings.design_output_path,"result_summaries") # TODO remove anything that uses deprecated `env_settings`
#     if not os.path.isdir(result_summary_outdir):
#         os.makedirs(result_summary_outdir)
#     csv_fname = os.path.join(result_summary_outdir, os.path.splitext(os.path.basename(asic_dse.sweep_conf_fpath))[0] )
#     rg_utils.write_dict_to_csv(csv_lines,csv_fname)

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
                "hdl_dpath" : rtl_dir_path
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
