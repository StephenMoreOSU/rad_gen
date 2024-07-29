from __future__ import annotations
import os, sys

from typing import List, Tuple

# Try appending rg base path to sys.path (this worked)
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import src.common.data_structs as rg_ds
import src.common.utils as rg_utils
import tests.common.common as tests_common

import tests.conftest as conftest
from tests.conftest import skip_if_fixtures_only

import pytest

import pandas as pd
import copy

from collections import OrderedDict


@pytest.fixture()
def noc_rtl_sweep() -> rg_ds.RadGenArgs:
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
    tests_common.write_fixture_json(noc_sweep_args)
    return noc_sweep_args

noc_rtl_sweep_conf_init_tb = conftest.create_rg_fixture(
    input_fixture = 'noc_rtl_sweep',
    fixture_type = 'conf_init',
)

@pytest.mark.noc
@pytest.mark.asic_sweep
@pytest.mark.init
@skip_if_fixtures_only
def test_noc_rtl_sweep_gen_conf_init(noc_rtl_sweep_conf_init_tb, request):
    tests_common.run_and_verif_conf_init(noc_rtl_sweep_conf_init_tb)


@pytest.fixture()
def noc_rtl_sweep_output(noc_rtl_sweep) -> Tuple[List[rg_ds.RadGenArgs], rg_ds.Tree]:
    """
        Runs the NoC configs + RTL generation
        Returns:
            - List of RadGenArgs drivers that can be used to run sweep points
            - The project tree
    """
    return tests_common.run_sweep(noc_rtl_sweep)


@pytest.fixture()
def get_sw_info(noc_rtl_sweep_output) -> Tuple[List[str], List[str]]:
    proj_tree: rg_ds.Tree
    _, proj_tree, _ = noc_rtl_sweep_output

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

@pytest.mark.noc
@pytest.mark.asic_sweep
@skip_if_fixtures_only
def test_noc_rtl_sweep_gen(get_sw_info, request):
    conf_fpaths, rtl_param_fpaths = get_sw_info
    for conf_fpath, rtl_param_fpath in zip(conf_fpaths, rtl_param_fpaths):
        assert os.path.exists(conf_fpath), f"Configuration file {conf_fpath} does not exist"
        assert os.path.exists(rtl_param_fpath), f"RTL parameter file {rtl_param_fpath} does not exist"

@pytest.fixture()
def noc_sw_pt_asic_flow_tb(
    hammer_flow_template,
    get_sw_info,
) -> rg_ds.RadGenArgs:
    conf_fpaths, _ = get_sw_info
    # We create a project tree by scanning the dir structure of the projects dir
    # We do this rather than getting it from the hammer_flow_template because project trees from specific flows 
    # are subsets of the total directories that exist in rad_gen
    proj_tree: rg_ds.Tree
    proj_tree = tests_common.init_scan_proj_tree() 
    min_rt_idx: int = 0 # We assume minimum runtime index is 0 
    # Inputs
    top_lvl_module: str = "router_wrap_bk"
    noc_conf_fpath = conf_fpaths[min_rt_idx]
    noc_rtl_src_dpath = proj_tree.search_subtrees(
        "projects.NoC.rtl.src",
        is_hier_tag = True,
    )[0].path
    subtool_fields: dict = {
        "hdl_dpath": noc_rtl_src_dpath,
        "top_lvl_module": top_lvl_module,
    } 
    rg_args = tests_common.gen_hammer_flow_rg_args(
        hammer_flow_template = hammer_flow_template,
        proj_name = "NoC",
        top_lvl_module = top_lvl_module,
        design_conf_fpath = noc_conf_fpath,
        subtool_fields = subtool_fields,
        # proj_tree = proj_tree,
    )
    tests_common.write_fixture_json(rg_args)
    return rg_args

noc_sw_pt_asic_flow_conf_init_tb = conftest.create_rg_fixture(
    input_fixture = 'noc_sw_pt_asic_flow_tb',
    fixture_type = 'conf_init',
)

@pytest.mark.noc
@pytest.mark.asic_flow
@pytest.mark.init
@skip_if_fixtures_only
def test_noc_sw_pt_asic_flow_conf_init(noc_sw_pt_asic_flow_conf_init_tb, request):
    tests_common.run_and_verif_conf_init(noc_sw_pt_asic_flow_conf_init_tb)


@pytest.mark.noc
@pytest.mark.asic_flow
@skip_if_fixtures_only
def test_noc_sw_pt_asic_flow(noc_sw_pt_asic_flow_tb, request):
    tests_common.run_verif_hammer_asic_flow(rg_args = noc_sw_pt_asic_flow_tb)


@pytest.fixture()
def noc_sw_pt_parse_tb(noc_sw_pt_asic_flow_tb) -> rg_ds.RadGenArgs:
    rg_args = copy.deepcopy(noc_sw_pt_asic_flow_tb)
    rg_args.subtool_args.compile_results = True
    tests_common.write_fixture_json(rg_args)
    return rg_args

noc_sw_pt_parse_conf_init_tb = conftest.create_rg_fixture(
    input_fixture = 'noc_sw_pt_parse_tb',
    fixture_type = 'conf_init',
)

@pytest.mark.noc
@pytest.mark.asic_flow
@pytest.mark.init
@skip_if_fixtures_only
def test_noc_sw_pt_parse_conf_init(noc_sw_pt_parse_conf_init_tb, request):
    tests_common.run_and_verif_conf_init(noc_sw_pt_parse_conf_init_tb)


@pytest.mark.noc
@pytest.mark.parse
@skip_if_fixtures_only
def test_noc_sw_pt_parse(noc_sw_pt_parse_tb, request):
    tests_common.run_verif_hammer_asic_flow(
        rg_args = noc_sw_pt_parse_tb,
        backup_flag = False, # Don't backup as this is for parsing existing results
    )

