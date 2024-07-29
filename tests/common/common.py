from __future__ import annotations
import os, sys

from typing import Any, List, Tuple, Callable

import rad_gen as rg
import src.common.data_structs as rg_ds
import src.common.utils as rg_utils

import pytest
import inspect
import argparse
from collections import OrderedDict
import copy
import dataclasses
import shutil

import json
from deepdiff import DeepDiff
import re

def get_rg_home() -> str:
    return os.environ.get("RAD_GEN_HOME")

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
    # TODO replace stack lvl bs with just passing in the name of function + file at the top level
    rg_home: str = get_rg_home()
    tests_tree: rg_ds.Tree = init_tests_tree()
    # Get the name of file that called this function (above the current file)
    caller_file: str = get_caller_file(level = stack_lvl)

    # START DEBUGGING, uncomment if you're having trouble finding the correct stack level to look for
    # for i in range(10):
        # print(get_caller_file(level = i))
    # END DEBUGGING
    
    test_grp_name: str = os.path.splitext( os.path.basename(caller_file).replace('test_',''))[0]
    # We call the fn which gets current function name with level = 2 to get the name of the function which calls this function
    test_name: str = get_current_function_name(level = stack_lvl).replace('test_', '')
    test_out_dpath: str = os.path.join(
        tests_tree.search_subtrees(f"tests.data", is_hier_tag = True)[0].path,
        test_grp_name,
        "outputs",
    )
    os.makedirs(test_out_dpath, exist_ok = True)
    # test_out_dpath: str = tests_tree.search_subtrees(f"tests.data.{test_grp_name}.outputs", is_hier_tag=True)[0].path 
    assert os.path.exists(test_out_dpath), f"Test output path {test_out_dpath} does not exist"
    return tests_tree, test_grp_name, test_name, test_out_dpath, rg_home

def get_fixture_info(stack_lvl = 3) -> Tuple[rg_ds.Tree, str, str, str]:
    tests_tree, test_grp_name, fixture_name, _, _ = get_test_info(stack_lvl)
    
    fixture_out_dpath: str = os.path.join(
        tests_tree.search_subtrees(f"tests.data.{test_grp_name}", is_hier_tag = True)[0].path,
        "fixtures"
    )
    os.makedirs(fixture_out_dpath, exist_ok=True)
    fixture_out_fpath = os.path.join(
        fixture_out_dpath,
        f"{fixture_name}.json",
    )
    return tests_tree, test_grp_name, fixture_name, fixture_out_fpath

def write_fixture_json(rad_gen_args: rg_ds.RadGenArgs, stack_lvl = 4):
    _, _, _, fixture_out_fpath = get_fixture_info(stack_lvl = stack_lvl)
    # Write the fixture object to json
    dataclass_2_json(rad_gen_args, fixture_out_fpath)

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
                assert (cmp_val < 0.1 and cmp_val > 0) or (cmp_val > -0.1 and cmp_val < 0 ) or cmp_val == 0.0 # % difference tolerance we allow
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

def run_sweep(rg_args: rg_ds.RadGenArgs) -> Tuple[List[rg_ds.RadGenArgs], rg_ds.Tree, rg_ds.RadGenArgs]:
    rg_home: str = os.environ.get("RAD_GEN_HOME")
    sw_pt_args_list: List[rg_ds.RadGenArgs]
    proj_tree: rg_ds.Tree
    
    sw_pt_args_list, proj_tree = run_rad_gen(rg_args, rg_home)
    return sw_pt_args_list, proj_tree, rg_args


def get_param_gen_fpaths(param_dict: OrderedDict, gen_dpath: str) -> Tuple[List[str], List[str]]:
    # Get the length of the lists inside the dictionary
    num_entries: int = len(next(iter(param_dict.values())))
    # Generate the formatted strings for each index
    param_strs = []
    for i in range(num_entries):
        formatted_string = '__'.join(
            f"{key}_{str(value[i]).replace(' ','')}" for key, value in param_dict.items()
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

def gen_hammer_flow_rg_args(
    hammer_flow_template,
    proj_name: str, 
    design_conf_fpath: str,
    top_lvl_module: str | None = None ,
    manual_obj_dpath: str | None = None , 
    subtool_fields: dict = {},
    rg_fields: dict = {},
    proj_tree: rg_ds.Tree | None = None,
):
    _, _, fixture_name, test_out_dpath, _ = get_test_info(stack_lvl = 3)
    # Unique case for parse tests, we want to make sure we still parse the golden results correctly and compare with asic flow
    dummy_hammer_flow_args, template_proj_tree = hammer_flow_template
    if proj_tree is None:
        proj_tree = template_proj_tree
    test_name: str = fixture_name.replace("_tb", "")
    # Inputs
    if manual_obj_dpath is None and top_lvl_module is not None:
        manual_obj_dpath = os.path.join(
            test_out_dpath, test_name, top_lvl_module
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
    return rg_args

def run_verif_hammer_asic_flow(
    rg_args: rg_ds.RadGenArgs,
    exec_flag: bool = True,
    verif_flag: bool = True,
    backup_flag: bool = True,
) -> Any:
    
    tests_tree: rg_ds.Tree
    tests_tree, test_grp_name, test_name, test_out_dpath, rg_home = get_test_info(stack_lvl = 3)
    # Unique case for parse tests, we want to make sure we still parse the golden results correctly and compare with asic flow
    if "parse" in test_name:
        test_name = test_name.replace("parse", "asic_flow")
    manual_obj_dpath: str = rg_args.manual_obj_dir
    # If backup arg is specified we will copy the manual obj dir to a backup location
    if os.path.isdir(manual_obj_dpath) and backup_flag:
        backup_obj_dpath = f"{manual_obj_dpath}_backup_{rg_ds.create_timestamp()}"
        shutil.move(manual_obj_dpath, backup_obj_dpath)
            
    ret_val: Any = None
    if exec_flag:
        ret_val = run_rad_gen(rg_args, rg_home)
    if verif_flag:
        golden_results_dpath = tests_tree.search_subtrees(
            f"tests.data.{test_grp_name}.golden_results.{test_name}", is_hier_tag = True
        )[0].path
        for stage in ["syn", "par", "timing", "power", "final"]:
            verify_flow_stage(manual_obj_dpath, golden_results_dpath, stage)
    return ret_val

def rec_convert_dataclass_to_dict(obj, key: str = None):
    """
        Converts a dict / dataclass of nested dicts / dataclasses into a dictionary object
    """
    # Checks if its a type we should skip
    skip_tup = (rg_ds.HammerDriver,)
    if isinstance(obj, skip_tup):
        return None
    elif dataclasses.is_dataclass(obj):
        try:
            # If there is a module that's not serializable we will convert manually instead
            return {k: rec_convert_dataclass_to_dict(v, k) for k, v in dataclasses.asdict(obj).items()}
        except: 
            # manually traversing the dataclass fields
            result = {}
            for field in dataclasses.fields(obj):
                field_val = getattr(obj, field.name)
                result[field.name] = rec_convert_dataclass_to_dict(field_val, field.name)
            return result

    elif isinstance(obj, list):
        return [rec_convert_dataclass_to_dict(i, key) for i in obj]
    elif isinstance(obj, dict):
        return {k: rec_convert_dataclass_to_dict(v, k) for k, v in obj.items()}
    # checks if instance is any primitive type, if its not then its a non dataclass class so we have to ignore for now
    elif not isinstance(obj, (str, int, float, bool)) and obj is not None:
        return None
    # Case for exporting paths so tests can be non system specific
    elif isinstance(obj, str) and key != None and 'path' in key:
        return obj.replace(os.path.expanduser('~'), '~')
    else:
        return obj
    

class EnhancedJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if dataclasses.is_dataclass(obj):
            return dataclasses.asdict(obj)
        return super().default(obj)
    
def run_fixtures(rg_home: str, test_args: List[str]):
    prev_cwd = os.getcwd()
    os.chdir(rg_home)
    # Run the fixtures
    pytest.main(["-vv", "-s", "--fixtures-only", *test_args])
    os.chdir(prev_cwd)

def dataclass_2_json(in_dataclass: Any, out_fpath: str):
    json_text = json.dumps(rec_convert_dataclass_to_dict(in_dataclass), cls=EnhancedJSONEncoder, indent=4)
    with open(out_fpath, "w") as f:
        f.write(json_text)

def run_and_verif_conf_init(rg_args: rg_ds.RadGenArgs):
    """
        Runs args for a 'init' marked test and does a deepdict comparison
    """
    tests_tree, test_grp_name, tests_name, _, _ = get_test_info(stack_lvl = 3)
    rg_info, _ = run_rad_gen(
        rg_args, 
        get_rg_home()
    )
    subtool: str = rg_args.subtools[0]
    init_struct = rg_info[subtool]
    test_init: dict = rec_convert_dataclass_to_dict(init_struct)
    
    # Get golden ref to compare against
    golden_results_dpath: str = tests_tree.search_subtrees(
        f"tests.data.{test_grp_name}.golden_results", is_hier_tag = True
    )[0].path
    tests_name_substr: str = tests_name.replace("_conf_init","")
    golden_init_struct_fpath: str = None
    for dname in os.listdir(golden_results_dpath):
        if tests_name_substr in dname:
            # Look for files with "init_struct" in them
            init_struct_fpaths = [
                os.path.join(golden_results_dpath, dname, fname)
                    for fname in os.listdir(os.path.join(golden_results_dpath, dname))
                    if "init_struct" in fname
            ]
            assert len(init_struct_fpaths) == 1, f"Expected 1 init struct file in {os.path.join(golden_results_dpath, dname)}"
            golden_init_struct_fpath: str = init_struct_fpaths[0]
            break
    assert golden_init_struct_fpath is not None, f"Could not find golden init struct file in {golden_results_dpath}"
    golden_init: dict = json.load(open(golden_init_struct_fpath,"r"))
    # Compare the two
    ddiff = DeepDiff(test_init, golden_init, ignore_order=True, verbose_level = 2)
    col_width = 50
    # na_ele = f"{'N/A':<{col_width}}"
    # If there are any differences iterate over them
    if ddiff:
        hier_key_re = re.compile(r"(?<=')\w+(?=')")
        # Any values exist in golden but not in test?
        items_added_dict: dict = ddiff.get("dictionary_item_added")
        if items_added_dict:
            golden_added_subhdr = rg_utils.create_bordered_str("GOLDEN Key : Value pairs not found in TEST")
            print(golden_added_subhdr[1])
            diff_cols = f"{'Key':<{col_width}}{'Value':<{col_width}}"
            print(diff_cols)
            for k, v in items_added_dict.items():
                hier_key = '.'.join( hier_key_re.findall(k) )
                row = f"{hier_key:<{col_width}}{v:<{col_width}}"
                print(row)
        # Any values exist in test but not in golden?
        items_removed_dict: dict = ddiff.get("dictionary_item_removed")
        if items_removed_dict:
            items_removed_subhdr = rg_utils.create_bordered_str("TEST Key : Value pairs not found in GOLDEN")
            print(items_removed_subhdr[1])
            diff_cols = f"{'Key':<{col_width}}{'Value':<{col_width}}"
            print(diff_cols)
            for k, v in items_removed_dict.items():
                hier_key = '.'.join( hier_key_re.findall(k) )
                row = f"{hier_key:<{col_width}}{v:<{col_width}}"
                print(row)
        # Any values exist in both but are different?
        items_changed_dict: dict = ddiff.get("values_changed")
        if items_changed_dict:
            items_changed_subhdr = rg_utils.create_bordered_str("Differences")
            print(items_changed_subhdr[1])
            diff_cols = f"{'Key':<{col_width}}{'Test Value':<{col_width}}{'Golden Value':<{col_width}}"
            print(diff_cols)
            for k, v in items_changed_dict.items():
                hier_key = '.'.join( hier_key_re.findall(k) )
                row = f"{hier_key:<{col_width}}{v['old_value']:<{col_width}}{v['new_value']:<{col_width}}"
                print(row)
        assert False, "Differences found between test and golden init struct"
    else:
        print("No differences found between test and golden init struct")



# def run_verif_coffe(rg_args: rg_ds.RadGenArgs):
#     tests_tree, test_grp_name, tests_name, _, _ = get_test_info(stack_lvl = 3)
#     rg_info, _ = run_rad_gen(
#         rg_args, 
#         get_rg_home()
#     )
#     subtool: str = rg_args.subtools[0]
#     coffe_info = rg_info[subtool]

# def run_verif_ic_3d(rg_args: rg_ds.RadGenArgs):