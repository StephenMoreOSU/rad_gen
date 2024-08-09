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

import tests.common.common as tests_common

import tests.conftest as conftest
from tests.conftest import skip_if_fixtures_only

@pytest.fixture
def stratix_iv() -> rg_ds.RadGenArgs:
    """
        Returns:
            The driver for generating SRAM configs + RTL
    """
    tests_tree: rg_ds.Tree
    tests_tree, test_grp_name, test_name, test_out_dpath, rg_home = tests_common.get_test_info()
    
    cur_test_input_dpath: str = tests_tree.search_subtrees(
        f"tests.data.{test_grp_name}.inputs",
        is_hier_tag = True,
    )[0].path
    # Inputs 
    stratix_iv_fpath = os.path.join(cur_test_input_dpath, "stratix_iv_rrg.yml")
    assert os.path.exists(stratix_iv_fpath), f"Input path {stratix_iv_fpath} does not exist"
    
    coffe_args = rg_ds.CoffeArgs(
        fpga_arch_conf_path = stratix_iv_fpath,
        rrg_data_dpath = os.path.join(cur_test_input_dpath, "rr_graph_ep4sgx110"),
        # checkpoint_dpaths = [
        #     os.path.join(cur_test_input_dpath, "checkpoints", f"part{i}") for i in range(1, 3)
        # ],
        # pass_through = True,
        max_iterations = 1, # Low QoR but fast for testing purposes
        area_opt_weight = 1,
        delay_opt_weight = 2, 
    )
    rg_args = rg_ds.RadGenArgs(
        override_outputs = True,
        manual_obj_dir = os.path.join(rg_home,"tests", "data", "stratix_iv", "outputs", "stratix_iv_rrg_debug"),
        project_name = "stratix_iv",
        subtools = ["coffe"],
        subtool_args = coffe_args,
    )
    tests_common.write_fixture_json(rg_args)
    return rg_args


@pytest.mark.rrg
@skip_if_fixtures_only
def test_stratix_iv_rrg_parse(request: pytest.FixtureRequest):
    import src.common.rr_parse as rr_parse
    tests_tree, test_grp_name, test_name, test_out_dpath, rg_home = tests_common.get_test_info()
    rrg_fpath: str = os.path.join(
            tests_tree.search_subtrees(
            f"tests.data.{test_grp_name}.inputs",
            is_hier_tag = True,
        )[0].path,
        "rr_graph_ep4sgx110.xml"
    )
    assert os.path.exists(rrg_fpath), f"RRG file {rrg_fpath} does not exist"
    out_dpath = os.path.join(test_out_dpath, "rr_graph_ep4sgx110")
    os.makedirs(out_dpath, exist_ok=True)
    args = ["--rr_xml_fpath", rrg_fpath, "--out_dpath", out_dpath, "--generate_plots"]
    rr_parse.main(args)

@pytest.fixture
def stratix_iv_passthrough_tb(stratix_iv) -> rg_ds.RadGenArgs:
    rg_args: rg_ds.RadGenArgs = copy.deepcopy(stratix_iv)
    rg_args.subtool_args.pass_through = True 
    return rg_args

@pytest.mark.parse
@skip_if_fixtures_only
def test_stratix_iv_passthrough(stratix_iv_passthrough_tb: rg_ds.RadGenArgs, request: pytest.FixtureRequest):
    rg_info, _ = tests_common.run_rad_gen(
        stratix_iv_passthrough_tb, tests_common.get_rg_home()
    )

@pytest.fixture
def stratix_iv_checkpoint_tb(stratix_iv) -> rg_ds.RadGenArgs:
    tests_info: tuple = tests_common.get_test_info()
    tests_tree: rg_ds.Tree = tests_info[0]
    test_grp_name: str = tests_info[1]
    
    rg_args: rg_ds.RadGenArgs = copy.deepcopy(stratix_iv)
    cur_test_input_dpath: str = tests_tree.search_subtrees(
        f"tests.data.{test_grp_name}.inputs",
        is_hier_tag = True,
    )[0].path
    rg_args.subtool_args.checkpoint_dpaths = [
        os.path.join(cur_test_input_dpath, "checkpoints", f"part{i}") for i in range(1, 2)
    ]
    return rg_args

@pytest.mark.checkpoint
@pytest.mark.custom_fpga
@skip_if_fixtures_only
def test_stratix_iv_checkpoint(stratix_iv_checkpoint_tb: rg_ds.RadGenArgs, request: pytest.FixtureRequest):
    """
        Tests ability to take intermediate COFFE checkpoint files and continue from them, getting the same result as if we ran the whole thing in one go
    """
    ret_val = tests_common.run_rad_gen(
        stratix_iv_checkpoint_tb, 
        tests_common.get_rg_home(),
    )
    if ret_val:
        rg_info = ret_val[0]
    

stratix_iv_conf_init_tb = conftest.create_rg_fixture(
    input_fixture = 'stratix_iv',
    fixture_type = 'conf_init'
)

@pytest.mark.init
@pytest.mark.custom_fpga
@skip_if_fixtures_only
def test_stratix_iv_conf_init(stratix_iv_conf_init_tb, request: pytest.FixtureRequest):
    tests_common.run_and_verif_conf_init(stratix_iv_conf_init_tb)

@pytest.mark.stratix_iv
@pytest.mark.custom_fpga
@skip_if_fixtures_only
def test_stratix_iv(stratix_iv: rg_ds.RadGenArgs, request: pytest.FixtureRequest):
    rg_args = copy.deepcopy(stratix_iv)
    ret_val: Any = tests_common.run_rad_gen(
        stratix_iv, 
        tests_common.get_rg_home(),
    )

@pytest.fixture
def stratix_iv_bram_tb(stratix_iv) -> rg_ds.RadGenArgs:
    tests_tree: rg_ds.Tree
    tests_tree, test_grp_name, test_name, test_out_dpath, rg_home = tests_common.get_test_info()
    cur_test_input_dpath: str = tests_tree.search_subtrees(
        f"tests.data.{test_grp_name}.inputs",
        is_hier_tag = True,
    )[0].path
    # manual_obj_dir = os.path.join(rg_home, "tests", "data", "stratix_iv", "outputs", "stratix_iv_rrg_debug"),

    stratix_iv_bram_fpath = os.path.join(cur_test_input_dpath, "stratix_iv_rrg_bram.yml")
    rg_args: rg_ds.RadGenArgs = copy.deepcopy(stratix_iv)
    rg_args.subtool_args.fpga_arch_conf_path = stratix_iv_bram_fpath
    rg_args.manual_obj_dir = os.path.join(
        tests_tree.search_subtrees(f"tests.data.{test_grp_name}.outputs", is_hier_tag = True)[0].path,
        "stratix_iv_rrg_bram_22nm_debug",
    ) 
    tests_common.write_fixture_json(rg_args)

    return rg_args

@pytest.fixture
def stratix_iv_bram_passthrough_tb(stratix_iv_bram_tb) -> rg_ds.RadGenArgs:
    tests_tree: rg_ds.Tree
    tests_tree, test_grp_name, test_name, test_out_dpath, rg_home = tests_common.get_test_info()
    rg_args: rg_ds.RadGenArgs = copy.deepcopy(stratix_iv_bram_tb)
    rg_args.manual_obj_dir = os.path.join(
        tests_tree.search_subtrees(f"tests.data.{test_grp_name}.outputs", is_hier_tag = True)[0].path,
        "stratix_iv_rrg_bram_22nm_passthrough_debug",
    ) 
    rg_args.subtool_args.pass_through = True 
    tests_common.write_fixture_json(rg_args)

    return rg_args

@pytest.mark.stratix_iv
@pytest.mark.custom_fpga
@skip_if_fixtures_only
def test_stratix_iv_bram_passthrough(stratix_iv_bram_passthrough_tb: rg_ds.RadGenArgs, request: pytest.FixtureRequest):
    rg_info, _ = tests_common.run_rad_gen(
        stratix_iv_bram_passthrough_tb, tests_common.get_rg_home()
    )

@pytest.mark.stratix_iv
@pytest.mark.custom_fpga
@skip_if_fixtures_only
def test_stratix_iv_bram(stratix_iv_bram_tb, request: pytest.FixtureRequest):
    rg_args = copy.deepcopy(stratix_iv_bram_tb)
    ret_val: Any = tests_common.run_rad_gen(
        rg_args, 
        tests_common.get_rg_home(),
    )


