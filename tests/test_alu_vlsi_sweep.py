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
from collections import OrderedDict
import copy

import json
import re

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

@pytest.fixture(scope='session')
def alu_vlsi_sweep() -> rg_ds.RadGenArgs:
    tests_tree, test_grp_name, fixture_name, fixture_out_fpath = tests_common.get_fixture_info()
    # Naming convension of directory for a particular test file is the name of the file without "test_" prefix
    asic_dse_inputs_dpath: str = tests_tree.search_subtrees(f"tests.data.asic_dse", is_hier_tag = True)[0].path
    cur_test_input_dpath: str = tests_tree.search_subtrees(f"tests.data.{test_grp_name}.inputs", is_hier_tag = True)[0].path
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
    # Dump the args to json named after this fixture
    tests_common.dataclass_2_json(alu_sweep_args, fixture_out_fpath)
    return alu_sweep_args 

@pytest.fixture(scope='session')
def alu_vlsi_sweep_gen_tb(alu_vlsi_sweep: rg_ds.RadGenArgs) -> Tuple[List[rg_ds.RadGenArgs], rg_ds.Tree]:
    return tests_common.run_sweep(alu_vlsi_sweep)

alu_vlsi_sweep_init_conf_tb = conftest.create_rg_fixture(
    input_fixture = 'alu_vlsi_sweep',
    fixture_type = 'conf_init',
)

# Naming of this test is important
# notice how we are not reaching for the alu_vlsi_sweep_gen_tb but rather for the alu_vlsi_sweep testbench
# This is because that testbench is the one that provides the sweep json
@pytest.mark.alu
@pytest.mark.asic_sweep
@pytest.mark.init
@skip_if_fixtures_only
def test_alu_vlsi_sweep_gen_conf_init(alu_vlsi_sweep_init_conf_tb, request):
    tests_common.run_and_verif_conf_init(alu_vlsi_sweep_init_conf_tb)


@pytest.mark.alu
@pytest.mark.asic_sweep
@skip_if_fixtures_only
def test_alu_vlsi_sweep_gen(alu_vlsi_sweep_gen_tb, request):
    # BELOW ARE ASSUMPTIONS THAT WILL BE CHANGED IF THE SWEEP CONFIG FILE CHANGES
    # THEY AFFECT ASSERTIONS!
    proj_tree: rg_ds.Tree
    _, proj_tree, rg_args = alu_vlsi_sweep_gen_tb

    # TODO find a way to get this information from the sweep generation itself?
    # Assumptions from input sweep config file
    # - Num Sweep Points: 2
    # - Sweep Type: vlsi_params
    # - VLSI Param: clk_periods
    # - Sweep Values: [0, 2] (ns)

    # Test specific variables
    proj_name: str = "alu"

    # Get dpath which sweep config files are generated
    sw_conf_dpath: str = proj_tree.search_subtrees(f"projects.{proj_name}.configs.gen", is_hier_tag=True)[0].path

    # Expected VLSI sweep points (will be in the name of generated conf files)
    # <base_conf_name>_<param>_<val>.yml -> 'dummy_base_period_0.0.yml'
    custom_map_expect_vlsi_sw_pts = OrderedDict(
        [
            ("period", ['0 ns', '0 ns', '2 ns']),
            ("core_util", [0.5, 0.7, 0.9]),
            ("effort", ["express", "standard", "extreme"]) 
        ]
    )
    num_sweep_points = len(custom_map_expect_vlsi_sw_pts["period"])
    for vals in custom_map_expect_vlsi_sw_pts.values():
        assert len(vals) == num_sweep_points
    # Check that the sweep config files were generated
    gen_conf_fpaths, _ = tests_common.get_param_gen_fpaths(custom_map_expect_vlsi_sw_pts, sw_conf_dpath)
    for gen_conf_fpath in gen_conf_fpaths:
        assert os.path.exists(gen_conf_fpath), f"Generated config file {gen_conf_fpath} does not exist"

@pytest.fixture(scope='session')
def alu_sw_pt_asic_flow_tb(hammer_flow_template) -> rg_ds.RadGenArgs:
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
            for fname in os.listdir(gen_conf_dpath) if "period_0ns__core_util_0.7__effort_standard" in fname
    ][0]
    rg_args: rg_ds.RadGenArgs = tests_common.gen_hammer_flow_rg_args(
        hammer_flow_template = hammer_flow_template,
        proj_name = proj_name,
        top_lvl_module = top_lvl_module,
        design_conf_fpath = alu_conf_fpath,
    )
    tests_common.write_fixture_json(rg_args)
    return rg_args


alu_sw_pt_asic_flow_conf_init_tb = conftest.create_rg_fixture(
    input_fixture = 'alu_sw_pt_asic_flow_tb',
    fixture_type = 'conf_init',
)

@pytest.mark.alu
@pytest.mark.asic_flow
@pytest.mark.init
@skip_if_fixtures_only
def test_alu_sw_pt_asic_flow_conf_init(alu_sw_pt_asic_flow_conf_init_tb, request):
    tests_common.run_and_verif_conf_init(alu_sw_pt_asic_flow_conf_init_tb) 

@pytest.mark.alu
@pytest.mark.asic_flow
@skip_if_fixtures_only
def test_alu_sw_pt_asic_flow(alu_sw_pt_asic_flow_tb, request):
    tests_common.run_verif_hammer_asic_flow(rg_args = alu_sw_pt_asic_flow_tb)

# TODO get this to work, problem with writing out fixture json (due to stack lvl stuff)
# alu_sw_pt_parse_tb = conftest.create_rg_fixture(
#     input_fixture = 'alu_sw_pt_asic_flow_tb',
#     fixture_type = 'parse',
# )

@pytest.fixture(scope='session')
def alu_sw_pt_parse_tb(alu_sw_pt_asic_flow_tb) -> rg_ds.RadGenArgs:
    rg_args = copy.deepcopy(alu_sw_pt_asic_flow_tb)
    rg_args.subtool_args.compile_results = True
    tests_common.write_fixture_json(rg_args)
    return rg_args

test_alu_sw_pt_parse_conf_init_tb = conftest.create_rg_fixture(
    input_fixture = 'alu_sw_pt_parse_tb',
    fixture_type = 'conf_init',
)

@pytest.mark.alu
@pytest.mark.parse
@pytest.mark.init
@skip_if_fixtures_only
def test_alu_sw_pt_parse_conf_init(test_alu_sw_pt_parse_conf_init_tb, request):
    tests_common.run_and_verif_conf_init(test_alu_sw_pt_parse_conf_init_tb) 

@pytest.mark.alu
@pytest.mark.parse
@skip_if_fixtures_only
def test_alu_sw_pt_parse(alu_sw_pt_parse_tb, request):
    tests_common.run_verif_hammer_asic_flow(
        rg_args = alu_sw_pt_parse_tb,
        backup_flag = False, # Don't backup as this is for parsing existing results
    )


@pytest.fixture(scope='session')
def alu_sw_pt_virtuoso_gds_tb(alu_sw_pt_parse_tb, request):
    # Requires the `test_alu_sw_pt_asic_flow` to be run first to get results to convert to gds in virtuoso
    rg_args = copy.deepcopy(alu_sw_pt_parse_tb)
    rg_args.subtool_args.scripts__virtuoso_setup_path = os.path.join(tests_common.get_rg_home(),"scripts","setup_virtuoso_env.sh")
    # TODO figure out a good place to tell people to make this rundir
    rg_args.subtool_args.stdcell_lib__pdk_rundir_path = os.path.expanduser(
        os.path.join("~","ASAP_7_IC","asap7_rundir")
    )
    tests_common.write_fixture_json(rg_args)
    return rg_args

alu_sw_pt_virtuoso_gds_conf_init_tb = conftest.create_rg_fixture(
    input_fixture = 'alu_sw_pt_virtuoso_gds_tb',
    fixture_type = 'conf_init',
)

@pytest.mark.alu
@pytest.mark.gds
@pytest.mark.init
@skip_if_fixtures_only
def test_alu_sw_pt_virtuoso_gds_conf_init(alu_sw_pt_virtuoso_gds_conf_init_tb, request):
    tests_common.run_and_verif_conf_init(alu_sw_pt_virtuoso_gds_conf_init_tb)


@pytest.mark.alu
@pytest.mark.gds
@skip_if_fixtures_only
def test_alu_sw_pt_virtuoso_gds(alu_sw_pt_virtuoso_gds_tb, request):
    """
        Todos:
            * Add the asic sw pt as a dependancy for this test
    """
    if not os.path.exists(alu_sw_pt_virtuoso_gds_tb.subtool_args.stdcell_lib__pdk_rundir_path):
        pytest.skip(f"Path {alu_sw_pt_virtuoso_gds_tb.subtool_args.stdcell_lib__pdk_rundir_path} does not exist")
    tests_common.run_verif_hammer_asic_flow(
        rg_args = alu_sw_pt_virtuoso_gds_tb,
        backup_flag = False,
    )





    
    

    
    
