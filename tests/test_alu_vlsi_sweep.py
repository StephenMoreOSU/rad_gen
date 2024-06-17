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
from collections import OrderedDict
import copy

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

@pytest.fixture
def alu_vlsi_sweep_output(alu_vlsi_sweep: rg_ds.RadGenArgs) -> Tuple[List[rg_ds.RadGenArgs], rg_ds.Tree]:
    return tests_common.run_sweep(alu_vlsi_sweep)

@pytest.mark.alu
@pytest.mark.asic_sweep
def test_alu_vlsi_sweep_gen(alu_vlsi_sweep_output):
    # BELOW ARE ASSUMPTIONS THAT WILL BE CHANGED IF THE SWEEP CONFIG FILE CHANGES
    # THEY AFFECT ASSERTIONS!
    proj_tree: rg_ds.Tree
    _, proj_tree = alu_vlsi_sweep_output

    # TODO find a way to get this information from the sweep generation itself?
    # Assumptions from input sweep config file
    # - Num Sweep Points: 2
    # - Sweep Type: vlsi_params
    # - VLSI Param: clk_periods
    # - Sweep Values: [0, 2] (ns)

    # Test specific variables
    proj_name: str = "alu"
    num_sweep_points: int = 2

    # Get dpath which sweep config files are generated
    sw_conf_dpath: str = proj_tree.search_subtrees(f"projects.{proj_name}.configs.gen", is_hier_tag=True)[0].path

    # Expected VLSI sweep points (will be in the name of generated conf files)
    # <base_conf_name>_<param>_<val>.yml -> 'dummy_base_period_0.0.yml'
    expect_vlsi_sw_pts = OrderedDict(
        [
            ("period", ['0.0', '2.0']),
        ]
    )
    # Check that the sweep config files were generated
    assert len(os.listdir(sw_conf_dpath)) == num_sweep_points
    gen_conf_fpaths, _ = tests_common.get_param_gen_fpaths(expect_vlsi_sw_pts, sw_conf_dpath)
    for gen_conf_fpath in gen_conf_fpaths:
        assert os.path.exists(gen_conf_fpath), f"Generated config file {gen_conf_fpath} does not exist"

@pytest.mark.alu
@pytest.mark.asic_flow
def test_alu_sw_pt_asic_flow(hammer_flow_template):
    proj_tree: rg_ds.Tree = tests_common.init_scan_proj_tree()
    proj_name: str = "alu"
    top_lvl_module: str = "alu_ver"
    gen_conf_dpath: str = proj_tree.search_subtrees(
        f"projects.{proj_name}.configs.gen", is_hier_tag = True
    )[0].path
    # Get the conf fpath for the sweep point we wish to evaluate
    # TODO find a better way to select which sweep point we're evaluating rather than just below hardcoded str
    alu_conf_fpath: str = [
        os.path.join(gen_conf_dpath, fname) 
            for fname in os.listdir(gen_conf_dpath) if "period_0.0" in fname
    ][0]

    tests_common.run_verif_hammer_asic_flow(
        hammer_flow_template,
        proj_name = proj_name,
        top_lvl_module = top_lvl_module,
        design_conf_fpath = alu_conf_fpath,
    )

@pytest.mark.alu
@pytest.mark.parse
def test_alu_sw_pt_parse(hammer_flow_template):
    proj_tree: rg_ds.Tree = tests_common.init_scan_proj_tree()
    proj_name: str = "alu"
    top_lvl_module: str = "alu_ver"
    gen_conf_dpath: str = proj_tree.search_subtrees(
        f"projects.{proj_name}.configs.gen", is_hier_tag = True
    )[0].path
    # Get the conf fpath for the sweep point we wish to evaluate
    # TODO find a better way to select which sweep point we're evaluating rather than just below hardcoded str
    alu_conf_fpath: str = [
        os.path.join(gen_conf_dpath, fname) 
            for fname in os.listdir(gen_conf_dpath) if "period_0.0" in fname
    ][0]
    # Additional ASIC-DSE arguments
    st_fields: dict = {
        "compile_results": True,
    }
    tests_common.run_verif_hammer_asic_flow(
        hammer_flow_template,
        proj_name = proj_name,
        top_lvl_module = top_lvl_module,
        design_conf_fpath = alu_conf_fpath,
        subtool_fields = st_fields,
        verif_flag = False,
    )
    





    
    

    
    
