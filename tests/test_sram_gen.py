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
import copy

#   ___ ___    _   __  __   ___ _____ ___ _____ ___ _  _ ___ ___    __  __   _   ___ ___  ___     ___ ___ _  _ 
#  / __| _ \  /_\ |  \/  | / __|_   _|_ _|_   _/ __| || | __|   \  |  \/  | /_\ / __| _ \/ _ \   / __| __| \| |
#  \__ \   / / _ \| |\/| | \__ \ | |  | |  | || (__| __ | _|| |) | | |\/| |/ _ \ (__|   / (_) | | (_ | _|| .` |
#  |___/_|_\/_/ \_\_|  |_| |___/ |_| |___| |_| \___|_||_|___|___/  |_|  |_/_/ \_\___|_|_\\___/   \___|___|_|\_|


#   ___ ___    _   __  __   ___ ___ _  _  ___ _    ___   __  __   _   ___ ___  ___  
#  / __| _ \  /_\ |  \/  | / __|_ _| \| |/ __| |  | __| |  \/  | /_\ / __| _ \/ _ \ 
#  \__ \   / / _ \| |\/| | \__ \| || .` | (_ | |__| _|  | |\/| |/ _ \ (__|   / (_) |
#  |___/_|_\/_/ \_\_|  |_| |___/___|_|\_|\___|____|___| |_|  |_/_/ \_\___|_|_\\___/ 



@pytest.fixture
def sram_gen() -> rg_ds.RadGenArgs:
    """
        Returns:
            The driver for generating SRAM configs + RTL
    """
    tests_tree = tests_common.init_tests_tree()
    # Naming convension of directory for a particular test file is the name of the file without "test_" prefix
    test_name: str = os.path.splitext( os.path.basename(__file__).replace('test_',''))[0]
    # asic_dse_inputs_dpath: str = tests_tree.search_subtrees(f"tests.data.asic_dse", is_hier_tag = True)[0].path
    cur_test_input_dpath: str = tests_tree.search_subtrees(f"tests.data.{test_name}.inputs", is_hier_tag = True)[0].path
    # Inputs 
    sram_sweep_path = os.path.join(cur_test_input_dpath, "sram_sweep.yml")
    assert os.path.exists(sram_sweep_path), f"Input path {sram_sweep_path} does not exist"
    asic_dse_args = rg_ds.AsicDseArgs(
        sweep_conf_fpath = sram_sweep_path,
    )
    sram_gen_args = rg_ds.RadGenArgs(
        override_outputs = True,
        subtools = ["asic_dse"],
        subtool_args = asic_dse_args,
    )
    return sram_gen_args

@pytest.fixture
def sram_gen_output(sram_gen: rg_ds.RadGenArgs) -> Tuple[List[rg_ds.RadGenArgs], rg_ds.Tree]:
    """
        Runs the SRAM configs + RTL generation
        Returns:
            The list of drivers for running flows based on generated configs
            RAD-Gen project tree
    """
    rg_home: str = os.environ.get("RAD_GEN_HOME")

    sw_pt_args_list: List[rg_ds.RadGenArgs]
    proj_tree: rg_ds.Tree

    sw_pt_args_list, proj_tree = driver.run_rad_gen(sram_gen, rg_home)
    return sw_pt_args_list, proj_tree

def test_sram_gen(sram_gen_output):
    proj_tree: rg_ds.Tree
    _, proj_tree = sram_gen_output

    conf_gen_dpath: str = proj_tree.search_subtrees("shared_resources.sram_lib.configs.gen", is_hier_tag = True)[0].path
    rtl_gen_dpath: str = proj_tree.search_subtrees("shared_resources.sram_lib.rtl.gen", is_hier_tag = True)[0].path

    # TODO implement more thorough test including all generated SRAMs
    # For now lets just do a big one 
    test_gen_sram_params: dict = {
        "rw_ports": 2,
        "w": 1024,
        "d": 512,
    }
    test_sram_key: str = f"{test_gen_sram_params['rw_ports']}x{test_gen_sram_params['w']}x{test_gen_sram_params['d']}"
    sram_gen_conf_fpaths: List[str] = [
        # TODO get the composition of macros for each mapped SRAM and perform some check
        # os.path.join(conf_gen_dpath, f"mem_params_SRAM{test_gen_sram_params['rw_ports']}RW{test_gen_sram_params['w']}x{test_gen_sram_params['d']}.json"),
        os.path.join(conf_gen_dpath, f"sram_config_sram_macro_map_{test_sram_key}.json")
    ]
    # Assert expected files were generated
    # Configs
    for sram_gen_conf_fpath in sram_gen_conf_fpaths:
        assert os.path.exists(sram_gen_conf_fpath), f"SRAM config file {sram_gen_conf_fpath} does not exist"
    # RTL
    rtl_gen_fpath: str = os.path.join(rtl_gen_dpath, f"sram_macro_map_{test_sram_key}",f"sram_macro_map_{test_sram_key}.sv")
    assert os.path.exists(rtl_gen_fpath), f"SRAM RTL file {rtl_gen_fpath} does not exist"


def test_single_macro_asic_flow(sram_gen_output):
    rg_home: str = os.environ.get("RAD_GEN_HOME")
    proj_tree: rg_ds.Tree
    sw_pt_args_list, proj_tree = sram_gen_output
    # Get general flow inputs (CAD tools / PDK)
    tests_tree = tests_common.init_tests_tree()
    test_grp_name: str = os.path.splitext( os.path.basename(__file__).replace('test_',''))[0]
    test_name: str = tests_common.get_current_function_name().replace('test_', '')
    test_out_dpath: str = tests_tree.search_subtrees(f"tests.data.{test_grp_name}.outputs", is_hier_tag=True)[0].path 
    assert os.path.exists(test_out_dpath), f"Output path {test_out_dpath} does not exist"

    asic_dse_inputs_dpath: str = tests_tree.search_subtrees(f"tests.data.asic_dse", is_hier_tag = True)[0].path
    tool_env_conf_fpath = os.path.join(asic_dse_inputs_dpath, "env.yml")
    cad_conf_fpath = os.path.join(asic_dse_inputs_dpath, "cad_tools", "cadence_tools.yml")
    pdk_conf_fpath = os.path.join(asic_dse_inputs_dpath, "pdks", "asap7.yml")
    
    top_lvl_module: str = "SRAM2RW128x32_wrapper"
    # We want to test the asic flow for a single sram macro
    test_sram_macro_params: dict = {
        "rw_ports": 2,
        "w": 32,
        "d": 128,
    }
    # macro_key: str = f"SRAM{test_sram_macro_params['rw_ports']}RW{test_sram_macro_params['w']}x{test_sram_macro_params['d']}"
    sram_gen_conf_dpath = proj_tree.search_subtrees("shared_resources.sram_lib.configs.gen", is_hier_tag = True)[0].path
    test_macro_conf_fpath = os.path.join(sram_gen_conf_dpath, f"sram_SRAM{test_sram_macro_params['rw_ports']}RW{test_sram_macro_params['d']}x{test_sram_macro_params['w']}.json")
    assert os.path.exists(test_macro_conf_fpath), f"Test macro config file {test_macro_conf_fpath} does not exist"
    asic_dse_args = rg_ds.AsicDseArgs(
        flow_conf_fpaths = [cad_conf_fpath, pdk_conf_fpath, test_macro_conf_fpath],
        tool_env_conf_fpaths = [tool_env_conf_fpath],
        common_asic_flow__flow_stages__sram__run = True,
    )
    macro_obj_dir: str = os.path.join(test_out_dpath, top_lvl_module)
    rg_sram_macro_args = rg_ds.RadGenArgs(
        project_name = "sram",
        manual_obj_dir = macro_obj_dir,
        subtools = ["asic_dse"],
        subtool_args = asic_dse_args,
    )
    driver.run_rad_gen(rg_sram_macro_args, rg_home)

    golden_results_dpath = tests_tree.search_subtrees(f"tests.data.{test_grp_name}.golden_results.{test_name}", is_hier_tag=True)[0].path
    for stage in ["syn", "par", "timing", "power", "final"]:
        tests_common.verify_flow_stage(macro_obj_dir, golden_results_dpath, stage)


def test_stitched_macro_asic_flow(hammer_flow_template):
    tests_tree: rg_ds.Tree
    tests_tree, test_grp_name, test_name, test_out_dpath, rg_home = tests_common.get_test_info()
    proj_tree: rg_ds.Tree
    dummy_hammer_flow_args, proj_tree = hammer_flow_template
    # TODO get top_lvl_module from the config / other unified source (so we don't have to change this when it updates)
    top_lvl_module: str = "sram_macro_map_2x256x64"
    # Inputs
    stitched_macro_conf_fpath: str = os.path.join(
        proj_tree.search_subtrees("shared_resources.sram_lib.configs.gen", is_hier_tag = True)[0].path,
        "sram_config_sram_macro_map_2x256x64.json"
    )
    manual_obj_dpath: str = os.path.join(
        test_out_dpath, top_lvl_module
    )
    rg_stitched_macro_flow_args: rg_ds.RadGenArgs = copy.deepcopy(dummy_hammer_flow_args)
    subtool_args: rg_ds.AsicDseArgs = rg_stitched_macro_flow_args.subtool_args
    subtool_args.flow_conf_fpaths += [stitched_macro_conf_fpath]  # append test specific config to flow_conf_fpaths (they are just the base hammer confs)
    subtool_args.common_asic_flow__flow_stages__sram__run = True
    rg_stitched_macro_flow_args.manual_obj_dir = manual_obj_dpath
    rg_stitched_macro_flow_args.project_name = "sram"
    rg_stitched_macro_flow_args.subtool_args = subtool_args

    driver.run_rad_gen(rg_stitched_macro_flow_args, rg_home)
    golden_results_dpath = tests_tree.search_subtrees(f"tests.data.{test_grp_name}.golden_results.{test_name}", is_hier_tag=True)[0].path
    for stage in ["syn", "par", "timing", "power", "final"]:
        tests_common.verify_flow_stage(manual_obj_dpath, golden_results_dpath, stage)
        






