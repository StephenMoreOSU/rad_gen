from __future__ import annotations
import os, sys

from typing import List, Tuple, Dict

# Try appending rg base path to sys.path (this worked)
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import src.common.data_structs as rg_ds
import src.common.utils as rg_utils
import tests.common.driver as driver
import tests.common.common as tests_common

import pytest

import pandas as pd
import copy


@pytest.fixture
def sram_gen() -> rg_ds.RadGenArgs:
    """
        Returns:
            The driver for generating SRAM configs + RTL
    """
    tests_tree: rg_ds.Tree
    tests_tree, _, test_name, _, _ = tests_common.get_test_info()    
    
    cur_test_input_dpath: str = tests_tree.search_subtrees(
        f"tests.data.{test_name}.inputs",
        is_hier_tag = True,
    )[0].path
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
    return tests_common.run_sweep(sram_gen)

@pytest.fixture
def get_stitched_srams() -> List[Dict[str, int]]:
    stitched_macros: List[Dict[str, int]] = [
        {
            # for now this will only support RW not either R or W
            "rw_ports": 2,
            # size in [w,d]
            "w": 1024,
            "d": 256
        },
        ################## DEPTH 512 ##################
        {
            # for now this will only support RW not either R or W
            "rw_ports": 2,
            # size in [w,d]
            "w": 256,
            "d": 512
        },
        {
            # for now this will only support RW not either R or W
            "rw_ports": 2,
            # size in [w,d]
            "w": 512,
            "d": 512
        },
        {
            # for now this will only support RW not either R or W
            "rw_ports": 2,
            # size in [w,d]
            "w": 1024,
            "d": 512
        },
        ################## DEPTH 1024 ##################
        {
            # for now this will only support RW not either R or W
            "rw_ports": 2,
            # size in [w,d]
            "w": 256,
            "d": 1024
        },
        {
            # for now this will only support RW not either R or W
            "rw_ports": 2,
            # size in [w,d]
            "w": 512,
            "d": 1024
        },
        {
            # for now this will only support RW not either R or W
            "rw_ports": 2,
            # size in [w,d]
            "w": 1024,
            "d": 1024
        },
        ################## DEPTH 2048 ##################
        {
            # for now this will only support RW not either R or W
            "rw_ports": 2,
            # size in [w,d]
            "w": 256,
            "d": 2048
        },
        {
            # for now this will only support RW not either R or W
            "rw_ports": 2,
            # size in [w,d]
            "w": 512,
            "d": 2048
        },
        {
            # for now this will only support RW not either R or W
            "rw_ports": 2,
            # size in [w,d]
            "w": 1024,
            "d": 2048
        },
        ################## DEPTH 64 ##################
        {
            # for now this will only support RW not either R or W
            "rw_ports": 2,
            # size in [w,d]
            "w": 256,
            "d": 64
        },
        {
            # for now this will only support RW not either R or W
            "rw_ports": 2,
            # size in [w,d]
            "w": 512,
            "d": 64
        },
        {
            # for now this will only support RW not either R or W
            "rw_ports": 2,
            # size in [w,d]
            "w": 1024,
            "d": 64
        }
    ]
    return stitched_macros

@pytest.fixture
def get_dut_single_macro(sram_gen_output) -> Tuple[
    rg_ds.Tree, 
    str,
    Dict[str, int],
]:
    macro_params: dict = {
        "rw_ports": 2,
        "w": 32,
        "d": 128,
    }
    proj_tree: rg_ds.Tree
    sw_pt_args_list, proj_tree = sram_gen_output
    # We want to test the asic flow for a single sram macro
    sram_gen_conf_dpath: str = proj_tree.search_subtrees(
        "shared_resources.sram_lib.configs.gen",
        is_hier_tag = True
    )[0].path
    macro_conf_fpath: str = os.path.join(
        sram_gen_conf_dpath, 
        # concat str over mult lines
        (
            f"sram_SRAM{macro_params['rw_ports']}"
            f"RW{macro_params['d']}x{macro_params['w']}.json"
        )
    )
    return proj_tree, macro_conf_fpath, macro_params

@pytest.fixture
def get_dut_stitched_sram(sram_gen_output) ->Tuple[
    rg_ds.Tree, 
    str,
    Dict[str, int],
]:
    sram_params = {
        "rw_ports": 2,
        "w": 256,
        "d": 512,
    }
    proj_tree: rg_ds.Tree
    sw_pt_args_list, proj_tree = sram_gen_output
    # We want to test the asic flow for a single sram macro
    sram_gen_conf_dpath: str = proj_tree.search_subtrees(
        "shared_resources.sram_lib.configs.gen",
        is_hier_tag = True
    )[0].path
    sram_conf_fpath: str = os.path.join(
        sram_gen_conf_dpath, 
        # concat str over mult lines
        (
            f"sram_config_sram_macro_map_"
            # TODO macros need to swap order of w and d
            f"{sram_params['rw_ports']}x{sram_params['w']}x{sram_params['d']}.json" 
        )
    )
    return proj_tree, sram_conf_fpath, sram_params

@pytest.mark.sram
@pytest.mark.asic_sweep
def test_sram_gen(sram_gen_output, get_stitched_srams):
    proj_tree: rg_ds.Tree
    _, proj_tree = sram_gen_output
    stitched_mems: List[Dict[str, int]] = get_stitched_srams

    conf_gen_dpath: str = proj_tree.search_subtrees("shared_resources.sram_lib.configs.gen", is_hier_tag = True)[0].path
    rtl_gen_dpath: str = proj_tree.search_subtrees("shared_resources.sram_lib.rtl.gen", is_hier_tag = True)[0].path

    for stitched_mem in stitched_mems:
        # Get the key for the test sram
        test_sram_key: str = f"{stitched_mem['rw_ports']}x{stitched_mem['w']}x{stitched_mem['d']}"
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


#   ___ ___    _   __  __   ___ ___ _  _  ___ _    ___   __  __   _   ___ ___  ___  
#  / __| _ \  /_\ |  \/  | / __|_ _| \| |/ __| |  | __| |  \/  | /_\ / __| _ \/ _ \ 
#  \__ \   / / _ \| |\/| | \__ \| || .` | (_ | |__| _|  | |\/| |/ _ \ (__|   / (_) |
#  |___/_|_\/_/ \_\_|  |_| |___/___|_|\_|\___|____|___| |_|  |_/_/ \_\___|_|_\\___/ 
@pytest.mark.sram
@pytest.mark.asic_flow
def test_single_macro_asic_flow(
    hammer_flow_template, 
    get_dut_single_macro
):
    proj_tree: rg_ds.Tree
    # We want to test the asic flow for a single sram macro
    proj_tree, test_macro_conf_fpath, test_sram_macro_params = get_dut_single_macro
    subtool_fields: dict = {
        "common_asic_flow__flow_stages__sram__run": True,
    }
    tests_common.run_verif_hammer_asic_flow(
        hammer_flow_template = hammer_flow_template,
        proj_name = "sram",
        top_lvl_module = "SRAM2RW128x32_wrapper",
        design_conf_fpath = test_macro_conf_fpath,
        subtool_fields = subtool_fields,
        proj_tree = proj_tree,
    )

@pytest.mark.sram
@pytest.mark.parse
def test_single_macro_parse(
    hammer_flow_template,
    get_dut_single_macro
):
    proj_tree: rg_ds.Tree
    # We want to test the asic flow for a single sram macro
    proj_tree, test_macro_conf_fpath, test_sram_macro_params = get_dut_single_macro
    subtool_fields: dict = {
        "common_asic_flow__flow_stages__sram__run": True,
        "compile_results": True,
    }
    tests_common.run_verif_hammer_asic_flow(
        hammer_flow_template = hammer_flow_template,
        proj_name = "sram",
        top_lvl_module = "SRAM2RW128x32_wrapper",
        design_conf_fpath = test_macro_conf_fpath,
        subtool_fields = subtool_fields,
        proj_tree = proj_tree,
    )

#   ___ ___    _   __  __   ___ _____ ___ _____ ___ _  _ ___ ___    __  __   _   ___ ___  ___  
#  / __| _ \  /_\ |  \/  | / __|_   _|_ _|_   _/ __| || | __|   \  |  \/  | /_\ / __| _ \/ _ \ 
#  \__ \   / / _ \| |\/| | \__ \ | |  | |  | || (__| __ | _|| |) | | |\/| |/ _ \ (__|   / (_) |
#  |___/_|_\/_/ \_\_|  |_| |___/ |_| |___| |_| \___|_||_|___|___/  |_|  |_/_/ \_\___|_|_\\___/ 

@pytest.mark.sram
@pytest.mark.asic_flow
def test_stitched_sram_asic_flow(
    hammer_flow_template,
    get_dut_stitched_sram,
):
    proj_tree: rg_ds.Tree
    proj_tree, test_stitched_conf_fpath, test_stitched_sram_params = get_dut_stitched_sram
    subtool_fields: dict = {
        "common_asic_flow__flow_stages__sram__run": True,
    }
    tests_common.run_verif_hammer_asic_flow(
        hammer_flow_template = hammer_flow_template,
        proj_name = "sram",
        top_lvl_module = "sram_macro_map_2x256x512",
        design_conf_fpath = test_stitched_conf_fpath,
        subtool_fields = subtool_fields,
        proj_tree = proj_tree,
    )

@pytest.mark.sram
@pytest.mark.parse
def test_stitched_sram_parse(
    hammer_flow_template,
    get_dut_stitched_sram,
):
    proj_tree: rg_ds.Tree
    proj_tree, test_stitched_conf_fpath, test_stitched_sram_params = get_dut_stitched_sram
    subtool_fields: dict = {
        "common_asic_flow__flow_stages__sram__run": True,
        "compile_results": True,
    }
    tests_common.run_verif_hammer_asic_flow(
        hammer_flow_template = hammer_flow_template,
        proj_name = "sram",
        top_lvl_module = "sram_macro_map_2x256x512",
        design_conf_fpath = test_stitched_conf_fpath,
        subtool_fields = subtool_fields,
        proj_tree = proj_tree,
    )

