from __future__ import annotations
import os, sys

from typing import Any, List, Tuple

import rad_gen as rg
import src.common.data_structs as rg_ds
import src.common.utils as rg_utils

import inspect
import argparse
from collections import OrderedDict
import copy

def init_tests_tree() -> rg_ds.Tree:
    rad_gen_home: str = os.environ.get("RAD_GEN_HOME")
    tests_tree: rg_ds.Tree = rg_ds.Tree(
        os.path.join(rad_gen_home, "tests"), 
        scan_dir = True,
    )
    tests_tree.update_tree()
    return tests_tree

def init_scan_proj_tree() -> rg_ds.Tree:
    rad_gen_home: str = os.environ.get("RAD_GEN_HOME")
    proj_tree: rg_ds.Tree = rg_ds.Tree(
        os.path.join(rad_gen_home, "projects"),
        scan_dir = True,
    )
    proj_tree.update_tree()
    return proj_tree

def get_test_info(stack_lvl: int = 2) -> Tuple[rg_ds.Tree, str, str, str, str]:
    rg_home: str = os.environ.get("RAD_GEN_HOME")
    tests_tree: rg_ds.Tree = init_tests_tree()
    # Get the name of file that called this function (above the current file)
    caller_file: str = get_caller_file(level = stack_lvl)
    test_grp_name: str = os.path.splitext( os.path.basename(caller_file).replace('test_',''))[0]
    # We call the fn which gets current function name with level = 2 to get the name of the function which calls this function
    test_name: str = get_current_function_name(level = stack_lvl).replace('test_', '')
    test_out_dpath: str = tests_tree.search_subtrees(f"tests.data.{test_grp_name}.outputs", is_hier_tag=True)[0].path 
    assert os.path.exists(test_out_dpath), f"Test output path {test_out_dpath} does not exist"
    return tests_tree, test_grp_name, test_name, test_out_dpath, rg_home


def verify_flow_stage(obj_dpath: str, golden_results_dpath: str, stage_name: str):
    summary_base_fname: str = "report"
    stage_results_fpath: str = os.path.join(obj_dpath, "reports", f"{stage_name}_{summary_base_fname}.csv")
    stage_gold_results_fpath: str = os.path.join(golden_results_dpath, f"{stage_name}_{summary_base_fname}.csv")
    # Use a function to compare results, then transpose and reset indexes to get data in format expected by get_df_output_lines()
    stage_cmp_df = rg_utils.compare_results(stage_results_fpath, stage_gold_results_fpath).T.reset_index()
    for l in rg_utils.get_df_output_lines(stage_cmp_df):
        print(l)

    syn_verif_keys: List[str] = ["Slack", "Delay", "Timing SRC", "Total Area", "Area SRC"]
    par_verif_keys: List[str] = syn_verif_keys + ["Total Power", "Power SRC", "GDS Area"]
    verif_keys: List[str]
    if stage_name == "syn":
        verif_keys = syn_verif_keys
    elif stage_name in ["par", "timing", "power", "final"]:
        verif_keys = par_verif_keys
    # The row index will always be 0 since the comparison is for a single run
    row_idx: int = 0
    for col in stage_cmp_df.columns:
        if col in verif_keys:
            cmp_val: float | str = stage_cmp_df[col].values[row_idx]
            if isinstance(cmp_val, float):
                assert cmp_val == 0.0
            elif isinstance(cmp_val, str):
                assert cmp_val == "Matching"
            else:
                assert False, f"Unexpected type {type(cmp_val)} for comparison value {cmp_val}"

def get_current_function_name(level: int = 1) -> str:
    # Returns the name of the function which called this function (if level = 1)
    return inspect.stack()[level].function

def get_caller_file(level: int = 1):
    return inspect.stack()[level].filename

def run_rad_gen(rg_args: rg_ds.RadGenArgs, rg_home: str, just_print: bool = False) -> Any | None:
    cmd_str, sys_args, sys_kwargs = rg_args.get_rad_gen_cli_cmd(rg_home)
    print(f"Running: {cmd_str}")
    ret_val = None
    if not just_print:
        args_ns = argparse.Namespace(**sys_kwargs) 
        ret_val = rg.main(args_ns) 
    return ret_val

def run_sweep(rg_args: rg_ds.RadGenArgs) -> Tuple[List[rg_ds.RadGenArgs], rg_ds.Tree]:
    rg_home: str = os.environ.get("RAD_GEN_HOME")
    sw_pt_args_list: List[rg_ds.RadGenArgs]
    proj_tree: rg_ds.Tree
    
    sw_pt_args_list, proj_tree = run_rad_gen(rg_args, rg_home)
    return sw_pt_args_list, proj_tree


def get_param_gen_fpaths(param_dict: OrderedDict, gen_dpath: str) -> Tuple[List[str], List[str]]:
    # Get the length of the lists inside the dictionary
    num_entries: int = len(next(iter(param_dict.values())))
    # Generate the formatted strings for each index
    param_strs = []
    for i in range(num_entries):
        formatted_string = '_'.join(
            f"{key}_{value[i]}" for key, value in param_dict.items()
        )
        param_strs.append(formatted_string)
    
    # Check that the configuration files were generated
    # Sort them s.t. the sweep with the lowest parameter values (hopefully the least runtime intense) is at index 0
    found_conf_fnames: List[str] = sorted(os.listdir(gen_dpath))
    
    # Looks for the formatted strings in the filenames
    gen_fpaths = [
        os.path.join(gen_dpath, fpath)
            for fpath in found_conf_fnames 
            if any(param_str in fpath for param_str in param_strs)
    ]
    return gen_fpaths, param_strs

def set_fields(obj: Any, field_dict: dict = {}, **kwargs):
    # Check for conflicts between field_dict and kwargs
    conflicts = set(field_dict.keys()) & set(kwargs.keys())
    if conflicts:
        raise ValueError(f"Conflicting keys found in field_dict and kwargs: {conflicts}")
    
    # Set fields from field_dict
    for field_name, field_val in field_dict.items():
        setattr(obj, field_name, field_val)
    
    # Set fields from kwargs
    for field_name, field_val in kwargs.items():
        setattr(obj, field_name, field_val)
    
    return obj

def run_verif_hammer_asic_flow(
    hammer_flow_template, 
    proj_name: str, 
    design_conf_fpath: str,
    top_lvl_module: str = None,
    manual_obj_dpath: str = None, 
    subtool_fields: dict = {},
    rg_fields: dict = {},
    proj_tree: rg_ds.Tree = None,
    verif_flag: bool = True,
):
    tests_tree: rg_ds.Tree
    tests_tree, test_grp_name, test_name, test_out_dpath, rg_home = get_test_info(stack_lvl = 3)
    # Unique case for parse tests, we want to make sure we still parse the golden results correctly and compare with asic flow
    if "parse" in test_name:
        test_name = test_name.replace("parse", "asic_flow")
    dummy_hammer_flow_args, template_proj_tree = hammer_flow_template
    if proj_tree is None:
        proj_tree = template_proj_tree
    # Inputs
    if manual_obj_dpath is None and top_lvl_module is not None:
        manual_obj_dpath = os.path.join(
            test_out_dpath, top_lvl_module
        )
    else:
        assert manual_obj_dpath is not None, "manual_obj_dpath must be provided if top_lvl_module is None"
    
    rg_args: rg_ds.RadGenArgs = copy.deepcopy(dummy_hammer_flow_args)
    # append test specific config to flow_conf_fpaths (they are just the base hammer confs)
    subtool_args: rg_ds.AsicDseArgs = rg_args.subtool_args
    subtool_args = set_fields(
        subtool_args, 
        subtool_fields, 
        flow_conf_fpaths = subtool_args.flow_conf_fpaths + [design_conf_fpath] 
    )
    rg_args = set_fields(
        rg_args, 
        rg_fields, 
        manual_obj_dir = manual_obj_dpath,
        project_name = proj_name,
    )
    rg_args.subtool_args = subtool_args

    run_rad_gen(rg_args, rg_home)
    if verif_flag:
        golden_results_dpath = tests_tree.search_subtrees(
            f"tests.data.{test_grp_name}.golden_results.{test_name}", is_hier_tag = True
        )[0].path
        for stage in ["syn", "par", "timing", "power", "final"]:
            verify_flow_stage(manual_obj_dpath, golden_results_dpath, stage)
    