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

from collections import OrderedDict


@pytest.fixture
def noc_rtl_sweep() -> rg_ds.RadGenArgs:
    """
        Returns:
            The driver for generating SRAM configs + RTL
    """
    tests_tree: rg_ds.Tree
    tests_tree, _, test_name, _, _ = tests_common.get_test_info()
    
    cur_test_input_dpath: str = tests_tree.search_subtrees(f"tests.data.{test_name}.inputs", is_hier_tag = True)[0].path
    # Inputs 
    noc_sweep_path = os.path.join(cur_test_input_dpath, "noc_sweep.yml")
    assert os.path.exists(noc_sweep_path), f"Input path {noc_sweep_path} does not exist"
    asic_dse_args = rg_ds.AsicDseArgs(
        sweep_conf_fpath = noc_sweep_path,
    )
    noc_sweep_args = rg_ds.RadGenArgs(
        override_outputs = True,
        project_name = "NoC",
        subtools = ["asic_dse"],
        subtool_args = asic_dse_args,
    )
    return noc_sweep_args

@pytest.fixture
def noc_rtl_sweep_output(noc_rtl_sweep) -> Tuple[List[rg_ds.RadGenArgs], rg_ds.Tree]:
    """
        Runs the NoC configs + RTL generation
        Returns:
            - List of RadGenArgs drivers that can be used to run sweep points
            - The project tree
    """
    _, _, _, _, rg_home = tests_common.get_test_info()
    proj_tree: rg_ds.Tree
    sw_pt_args_list, proj_tree = driver.run_rad_gen(noc_rtl_sweep, rg_home)

    return sw_pt_args_list, proj_tree


@pytest.fixture
def get_rtl_sw_fpaths(noc_rtl_sweep_output) -> Tuple[List[str], List[str]]:
    proj_tree: rg_ds.Tree
    _, proj_tree = noc_rtl_sweep_output

    param_hdr_dname: str = "param_sweep_headers"
    conf_gen_dpath: str = proj_tree.search_subtrees("projects.NoC.configs.gen", is_hier_tag = True)[0].path
    rtl_param_gen_dpath: str = proj_tree.search_subtrees(f"projects.NoC.rtl.gen.{param_hdr_dname}", is_hier_tag = True)[0].path
    # Expected param values
    expected_rtl_param_sw_pts = OrderedDict(
        [
            ("num_message_classes", [5, 5, 5]),
            ("buffer_size", [20, 40, 80]),
            ("num_nodes_per_router", [1, 1, 1]),
            ("num_dimensions", [2, 2, 2]),
            ("flit_data_width", [124, 196, 342]),
            ("num_vcs", [5, 5, 5]),
        ]
    )

    # Get the length of the lists inside the dictionary
    num_entries: int = len(next(iter(expected_rtl_param_sw_pts.values())))
    # Generate the formatted strings for each index
    rtl_param_strs = []
    for i in range(num_entries):
        formatted_string = '_'.join(
            f"{key}_{value[i]}" for key, value in expected_rtl_param_sw_pts.items()
        )
        rtl_param_strs.append(formatted_string)
    
    # Check that the configuration files were generated
    # Sort them s.t. the sweep with the lowest parameter values (hopefully the least runtime intense) is at index 0
    found_conf_fnames: List[str] = sorted(os.listdir(conf_gen_dpath))
    found_rtl_param_fnames: List[str] = sorted(os.listdir(rtl_param_gen_dpath))
    
    conf_fpaths = [
        os.path.join(conf_gen_dpath, fpath)
            for fpath in found_conf_fnames 
            if any(rtl_param_str in fpath for rtl_param_str in rtl_param_strs)
    ]
    rtl_param_fpaths = [
        os.path.join(rtl_param_gen_dpath, fpath)
            for fpath in found_rtl_param_fnames
            if any(rtl_param_str in fpath for rtl_param_str in rtl_param_strs)
    ]
    return conf_fpaths, rtl_param_fpaths

def test_noc_rtl_sweep(get_rtl_sw_fpaths):
    conf_fpaths, rtl_param_fpaths = get_rtl_sw_fpaths
    for conf_fpath, rtl_param_fpath in zip(conf_fpaths, rtl_param_fpaths):
        assert os.path.exists(conf_fpath), f"Configuration file {conf_fpath} does not exist"
        assert os.path.exists(rtl_param_fpath), f"RTL parameter file {rtl_param_fpath} does not exist"


def test_noc_sw_pt_asic_flow(hammer_flow_template, get_rtl_sw_fpaths):
    tests_tree: rg_ds.Tree
    tests_tree, test_grp_name, test_name, test_out_dpath, rg_home = tests_common.get_test_info()
    conf_fpaths, _ = get_rtl_sw_fpaths
    # We create a project tree by scanning the dir structure of the projects dir
    # We do this rather than getting it from the hammer_flow_template because project trees from specific flows 
    # are subsets of the total directories that exist in rad_gen
    proj_tree: rg_ds.Tree
    proj_tree = tests_common.init_scan_proj_tree() 
    dummy_hammer_flow_args, _ = hammer_flow_template
    min_rt_idx: int = 0 # We assume minimum runtime index is 0 
    # Inputs
    top_lvl_module: str = "router_wrap_bk"
    noc_conf_fpath = conf_fpaths[min_rt_idx]
    noc_rtl_src_dpath = proj_tree.search_subtrees("projects.NoC.rtl.src", is_hier_tag = True)[0].path
    manual_obj_dpath: str = os.path.join(test_out_dpath, top_lvl_module)

    # Update drivers with values for NoC Hammer flow
    rg_args: rg_ds.RadGenArgs = copy.deepcopy(dummy_hammer_flow_args)
    # ASIC DSE Args
    subtool_args: rg_ds.AsicDseArgs = rg_args.subtool_args
    subtool_args.flow_conf_fpaths += [noc_conf_fpath]  # append test specific config to flow_conf_fpaths (they are just the base hammer confs)
    subtool_args.common_asic_flow__top_lvl_module = top_lvl_module
    subtool_args.common_asic_flow__hdl_path = noc_rtl_src_dpath
    subtool_args.compile_results = True

    # RAD Gen Args
    rg_args.manual_obj_dir = manual_obj_dpath
    rg_args.project_name = "NoC"
    rg_args.subtool_args = subtool_args
    
    driver.run_rad_gen(rg_args, rg_home)
    golden_results_dpath = tests_tree.search_subtrees(f"tests.data.{test_grp_name}.golden_results.{test_name}", is_hier_tag=True)[0].path
    for stage in ["syn", "par", "timing", "power", "final"]:
        tests_common.verify_flow_stage(manual_obj_dpath, golden_results_dpath, stage)






