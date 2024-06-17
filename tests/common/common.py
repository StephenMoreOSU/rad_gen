from __future__ import annotations
import os, sys

from typing import Any, List, Tuple

import rad_gen as rg
import src.common.data_structs as rg_ds
import src.common.utils as rg_utils

import inspect

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

def get_test_info() -> Tuple[rg_ds.Tree, str, str, str, str]:
    rg_home: str = os.environ.get("RAD_GEN_HOME")
    tests_tree: rg_ds.Tree = init_tests_tree()
    # Get the name of file that called this function (above the current file)
    caller_file: str = get_caller_file(level = 2)
    test_grp_name: str = os.path.splitext( os.path.basename(caller_file).replace('test_',''))[0]
    # We call the fn which gets current function name with level = 2 to get the name of the function which calls this function
    test_name: str = get_current_function_name(level = 2).replace('test_', '')
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