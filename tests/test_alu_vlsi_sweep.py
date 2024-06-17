from __future__ import annotations
import os, sys

from typing import List, Tuple

# Try appending rg base path to sys.path (this worked)
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import src.common.data_structs as rg_ds
import src.common.utils as rg_utils
import tests.common.driver as driver
import tests.common.common as tests_common

import pytest
import pandas as pd

"""
Notes on testing infrastructure:

* Before tests are run we need to do an environment evaluation
* For each test there should be a dir in golden_results dir with the same name as the test file (without test_ prefix)
* From env.yml OR just current env `hspice --version`, etc 
    we need to check the versions of all CAD tools being used and compare them to the versions 
    in a json file in the tests corresponding golden_results directory

"""


#     _   _   _   _  __   ___    ___ ___   _____      _____ ___ ___   _____ ___ ___ _____ 
#    /_\ | | | | | | \ \ / / |  / __|_ _| / __\ \    / / __| __| _ \ |_   _| __/ __|_   _|
#   / _ \| |_| |_| |  \ V /| |__\__ \| |  \__ \\ \/\/ /| _|| _||  _/   | | | _|\__ \ | |  
#  /_/ \_\____\___/    \_/ |____|___/___| |___/ \_/\_/ |___|___|_|     |_| |___|___/ |_| 

@pytest.fixture
def alu_vlsi_sweep() -> rg_ds.RadGenArgs:
    tests_tree = tests_common.init_tests_tree()
    # Naming convension of directory for a particular test file is the name of the file without "test_" prefix
    test_name: str = os.path.splitext( os.path.basename(__file__).replace('test_',''))[0]
    asic_dse_inputs_dpath: str = tests_tree.search_subtrees(f"tests.data.asic_dse", is_hier_tag = True)[0].path
    cur_test_input_dpath: str = tests_tree.search_subtrees(f"tests.data.{test_name}.inputs", is_hier_tag = True)[0].path
    # Inputs 
    tool_env_conf_fpath = os.path.join(asic_dse_inputs_dpath, "env.yml")
    alu_sweep_conf_fpath = os.path.join(cur_test_input_dpath, "alu_sweep.yml")
    for input_path in [tool_env_conf_fpath, alu_sweep_conf_fpath]:
        assert os.path.exists(input_path), f"Input path {input_path} does not exist"
    asic_dse_args = rg_ds.AsicDseArgs(
        sweep_conf_fpath = alu_sweep_conf_fpath,
        tool_env_conf_fpath = tool_env_conf_fpath,
    )
    alu_sweep_args = rg_ds.RadGenArgs(
        override_outputs = True,
        project_name = "alu",
        subtools = ["asic_dse"],
        subtool_args = asic_dse_args,
    )
    return alu_sweep_args #, test_data_dpath


# def verify_flow_stage(obj_dpath: str, golden_results_dpath: str, stage_name: str):
#     summary_base_fname: str = "report"
#     stage_results_fpath: str = os.path.join(obj_dpath, "reports", f"{stage_name}_{summary_base_fname}.csv")
#     stage_gold_results_fpath: str = os.path.join(golden_results_dpath, f"{stage_name}_{summary_base_fname}.csv")
#     # Use a function to compare results, then transpose and reset indexes to get data in format expected by get_df_output_lines()
#     stage_cmp_df = rg_utils.compare_results(stage_results_fpath, stage_gold_results_fpath).T.reset_index()
#     for l in rg_utils.get_df_output_lines(stage_cmp_df):
#         print(l)

#     syn_verif_keys: List[str] = ["Slack", "Delay", "Timing SRC", "Total Area", "Area SRC"]
#     par_verif_keys: List[str] = syn_verif_keys + ["Total Power", "Power SRC", "GDS Area"]
#     verif_keys: List[str]
#     if stage_name == "syn":
#         verif_keys = syn_verif_keys
#     elif stage_name in ["par", "timing", "power", "final"]:
#         verif_keys = par_verif_keys
#     # The row index will always be 0 since the comparison is for a single run
#     row_idx: int = 0
#     for col in stage_cmp_df.columns:
#         if col in verif_keys:
#             cmp_val: float | str = stage_cmp_df[col].values[row_idx]
#             if isinstance(cmp_val, float):
#                 assert cmp_val == 0.0
#             elif isinstance(cmp_val, str):
#                 assert cmp_val == "Matching"
#             else:
#                 assert False, f"Unexpected type {type(cmp_val)} for comparison value {cmp_val}"


def test_alu_vlsi_sweep(alu_vlsi_sweep: rg_ds.RadGenArgs): #, test_data_dpath: str):
    # BELOW ARE ASSUMPTIONS THAT WILL BE CHANGED IF THE SWEEP CONFIG FILE CHANGES
    # THEY AFFECT ASSERTIONS!
    rg_home: str = os.environ.get("RAD_GEN_HOME")
    tests_tree: rg_ds.Tree = tests_common.init_tests_tree()
    test_name: str = os.path.splitext( os.path.basename(__file__).replace('test_',''))[0]
    # TODO find a way to get this information from the sweep generation itself?
    # Assumptions from input sweep config file
    # - Num Sweep Points: 2
    # - Sweep Type: vlsi_params
    # - VLSI Param: clk_periods
    # - Sweep Values: [0, 2] (ns)
    proj_name: str = alu_vlsi_sweep.project_name
    num_sweep_points: int = 2
    # On sweeps will return a list of 
    sw_pt_args_list: List[rg_ds.RadGenArgs]
    proj_tree: rg_ds.Tree
    # Tell pytest to fail if an exception is raised
    # with pytest.raises(Exception):
    sw_pt_args_list, proj_tree = driver.run_rad_gen(alu_vlsi_sweep, rg_home)
    # We will just check the first sweep point for now, which is assumed to be target period of 0ns
    # TODO figure out some way to distinguish between different sweep points for testing
    
    # Get dpath which sweep config files are generated
    sw_conf_dpath: str = proj_tree.search_subtrees(f"projects.{proj_name}.configs.gen", is_hier_tag=True)[0].path
    # Check that the sweep config files were generated
    assert len(os.listdir(sw_conf_dpath)) == num_sweep_points
    
    sw_pt_args: rg_ds.RadGenArgs = sw_pt_args_list[0]

    # Using generic name for obj dir on this sweep point
    sw_pt_args.manual_obj_dir = os.path.join(
            tests_tree.search_subtrees(f"tests.data.{test_name}", is_hier_tag=True)[0].path
            , "obj_dir"
    )
    # sw_pt_args.subtool_args.common_asic_flow__flow_stages__par__run = True
    sw_pt_obj_dpath: str = sw_pt_args.manual_obj_dir
    # Now we will run the sweep point at index 0 and make sure it runs to completion
    # with pytest.raises(Exception):
    driver.run_rad_gen(sw_pt_args, rg_home)
    
    golden_results_dpath = tests_tree.search_subtrees(f"tests.data.{test_name}.golden_results", is_hier_tag=True)[0].path
    for stage in ["syn", "par", "timing", "power", "final"]:
        tests_common.verify_flow_stage(sw_pt_obj_dpath, golden_results_dpath, stage)



    # Get runtime for below options as well but should have no assertions
    # Check + Compare Synthesis results 
    
    # syn_results_fpath: str = os.path.join(sw_pt_obj_dpath, "syn_report.csv")
    # syn_gold_results_fpath: str = os.path.join(golden_results_dpath, "syn_report.csv")
    # syn_cmp_df = rg_utils.compare_results(syn_results_fpath, syn_gold_results_fpath)
    # for l in rg_utils.get_df_output_lines(syn_cmp_df):
    #     print(l)
    
    # Check + Compare Place & Route results
    # par_results = rg_utils.read_csv_to_list(os.path.join(sw_pt_obj_dpath, "par_report.csv"))
    # # Check + Compare Timing Analyzer results
    # timing_results = rg_utils.read_csv_to_list(os.path.join(sw_pt_obj_dpath, "timing_report.csv"))
    # # Check + Compare Power Analyzer results
    # power_results = rg_utils.read_csv_to_list(os.path.join(sw_pt_obj_dpath, "power_report.csv"))
    # # Check + Compare GDS Converted results (if needed for pdk in question)
    # final_results = rg_utils.read_csv_to_list(os.path.join(sw_pt_obj_dpath, "final_report.csv"))

    
    # Check + Compare the total flow result options
    #   Which portion of the flow contributed to the final result? (static timing should report timing not par, etc)

    



    
    

    
    
