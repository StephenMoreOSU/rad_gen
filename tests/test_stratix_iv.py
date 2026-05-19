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
    stratix_iv_fpath = os.path.join(cur_test_input_dpath, "stratix_iv.yml")
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


@pytest.fixture
def stratix_iv_sb_muxes() -> rg_ds.RadGenArgs:
    """
        Returns test args for non-RRG initialization using explicit sb_muxes config
    """
    tests_tree: rg_ds.Tree
    tests_tree, test_grp_name, test_name, test_out_dpath, rg_home = tests_common.get_test_info()

    cur_test_input_dpath: str = tests_tree.search_subtrees(
        f"tests.data.{test_grp_name}.inputs",
        is_hier_tag = True,
    )[0].path
    # Inputs - uses stratix_iv.yml which has sb_muxes defined
    stratix_iv_fpath = os.path.join(cur_test_input_dpath, "stratix_iv.yml")
    assert os.path.exists(stratix_iv_fpath), f"Input path {stratix_iv_fpath} does not exist"

    coffe_args = rg_ds.CoffeArgs(
        fpga_arch_conf_path = stratix_iv_fpath,
        rrg_data_dpath = None,  # No RRG data - triggers non-RRG path (sb_muxes method)
        max_iterations = 1,
        area_opt_weight = 1,
        delay_opt_weight = 2,
        # pass_through = True,  # Use pass_through to just test initialization
    )
    rg_args = rg_ds.RadGenArgs(
        override_outputs = True,
        manual_obj_dir = os.path.join(rg_home, "tests", "data", "stratix_iv", "outputs", "stratix_iv_sb_muxes_debug"),
        project_name = "stratix_iv_sb_muxes",
        subtools = ["coffe"],
        subtool_args = coffe_args,
    )
    tests_common.write_fixture_json(rg_args)
    return rg_args


@pytest.fixture
def stratix_iv_fs_mtx() -> rg_ds.RadGenArgs:
    """
        Returns test args for non-RRG initialization using Fs_mtx config
    """
    tests_tree: rg_ds.Tree
    tests_tree, test_grp_name, test_name, test_out_dpath, rg_home = tests_common.get_test_info()

    cur_test_input_dpath: str = tests_tree.search_subtrees(
        f"tests.data.{test_grp_name}.inputs",
        is_hier_tag = True,
    )[0].path
    # Inputs - uses stratix_iv_fs_mtx.yml which has only Fs_mtx (no sb_muxes)
    stratix_iv_fpath = os.path.join(cur_test_input_dpath, "stratix_iv_fs_mtx.yml")
    assert os.path.exists(stratix_iv_fpath), f"Input path {stratix_iv_fpath} does not exist"

    coffe_args = rg_ds.CoffeArgs(
        fpga_arch_conf_path = stratix_iv_fpath,
        rrg_data_dpath = None,  # No RRG data - triggers non-RRG path (Fs_mtx method)
        max_iterations = 1,
        area_opt_weight = 1,
        delay_opt_weight = 2,
        # pass_through = True,  # Use pass_through to just test initialization
    )
    rg_args = rg_ds.RadGenArgs(
        override_outputs = True,
        manual_obj_dir = os.path.join(rg_home, "tests", "data", "stratix_iv", "outputs", "stratix_iv_fs_mtx_debug"),
        project_name = "stratix_iv_fs_mtx",
        subtools = ["coffe"],
        subtool_args = coffe_args,
    )
    tests_common.write_fixture_json(rg_args)
    return rg_args


@pytest.mark.non_rrg
@pytest.mark.sb_muxes
@skip_if_fixtures_only
def test_stratix_iv_sb_muxes(stratix_iv_sb_muxes: rg_ds.RadGenArgs, request: pytest.FixtureRequest):
    """
        Tests non-RRG initialization path using explicit sb_muxes config.
        This tests Method 1: User specifies sb_muxes directly in YAML.
    """
    rg_args = copy.deepcopy(stratix_iv_sb_muxes)
    ret_val = tests_common.run_rad_gen(
        rg_args,
        tests_common.get_rg_home(),
    )


@pytest.mark.non_rrg
@pytest.mark.fs_mtx
@skip_if_fixtures_only
def test_stratix_iv_fs_mtx(stratix_iv_fs_mtx: rg_ds.RadGenArgs, request: pytest.FixtureRequest):
    """
        Tests non-RRG initialization path using Fs_mtx config.
        This tests Method 2: SB mux sizes derived from Fs connectivity matrix.
    """
    rg_args = copy.deepcopy(stratix_iv_fs_mtx)
    ret_val = tests_common.run_rad_gen(
        rg_args,
        tests_common.get_rg_home(),
    )


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


# ---------------------------------------------------------------------------
# Parametrized BRAM unit tests (22nm process)
# ---------------------------------------------------------------------------
# Each entry: (yaml_basename, label_for_obj_dir, pytest_markers)
# These mirror the BRAM configurations from legacy COFFE's input_files/BRAM/
# (Chiasson/Betz, FPT 2013) and exercise different paths through the BRAM
# generation code: varying memory geometry, SRAM vs MTJ technology, and
# pass_transistor vs transmission_gate switches.
# Parameter tuples: (yaml_basename, label_for_obj_dir)
# Each entry is wrapped in pytest.param() so we can attach distinct markers.
# Two case lists:
#   * _BRAM_22NM_PASSTHROUGH_CASES — exercises the full COFFE BRAM netlist
#     generation path in pass-through mode (slower, ~3-4 min per case).
#   * _BRAM_22NM_CONF_INIT_CASES — just parses the yaml + initializes the
#     Coffe dataclass (sub-second per case). Includes one extra case
#     (pass_transistor switch) that the passthrough flow can't currently
#     handle due to an unrelated assertion in src/coffe/mux.py:209.
# The MTJ case carries an extra `slow` marker because the MTJ-specific
# sub-circuits dominate sizing-iteration time; users can deselect with
# `pytest -m "not slow"`.
_BRAM_22NM_PASSTHROUGH_CASES = [
    pytest.param(
        ("stratix_iv_rrg_bram_ram32.yml", "ram32_sram_tgate"),
        marks = [pytest.mark.bram],
        id = "ram32_sram_tgate",
    ),
    pytest.param(
        ("stratix_iv_rrg_bram_ram64.yml", "ram64_sram_tgate"),
        marks = [pytest.mark.bram],
        id = "ram64_sram_tgate",
    ),
    pytest.param(
        ("stratix_iv_rrg_bram_ram128.yml", "ram128_sram_tgate"),
        marks = [pytest.mark.bram],
        id = "ram128_sram_tgate",
    ),
    pytest.param(
        ("stratix_iv_rrg_bram_mtj32.yml", "mtj32_tgate"),
        marks = [pytest.mark.bram, pytest.mark.mtj, pytest.mark.slow],
        id = "mtj32_tgate",
    ),
]

_BRAM_22NM_CONF_INIT_CASES = _BRAM_22NM_PASSTHROUGH_CASES + [
    pytest.param(
        ("stratix_iv_rrg_bram_pt_switch.yml", "ram32_sram_ptran"),
        marks = [pytest.mark.bram],
        id = "ram32_sram_ptran",
    ),
]


@pytest.fixture
def stratix_iv_bram_22nm_tb(stratix_iv, request: pytest.FixtureRequest) -> rg_ds.RadGenArgs:
    """
        Parametrized fixture that points the stratix_iv driver at one of the
        22nm BRAM yaml configs and gives it a unique output directory.

        Indirect-parametrize this fixture with a (yaml_basename, label) tuple.
    """
    yaml_basename, label = request.param

    tests_tree: rg_ds.Tree
    tests_tree, test_grp_name, test_name, test_out_dpath, rg_home = tests_common.get_test_info()
    cur_test_input_dpath: str = tests_tree.search_subtrees(
        f"tests.data.{test_grp_name}.inputs",
        is_hier_tag = True,
    )[0].path

    bram_yaml_fpath: str = os.path.join(cur_test_input_dpath, yaml_basename)
    assert os.path.exists(bram_yaml_fpath), f"BRAM yaml path {bram_yaml_fpath} does not exist"

    rg_args: rg_ds.RadGenArgs = copy.deepcopy(stratix_iv)
    rg_args.subtool_args.fpga_arch_conf_path = bram_yaml_fpath
    # pass_through skips the actual hspice simulations during sizing but still
    # exercises the full COFFE BRAM netlist generation path. Combined with the
    # inherited max_iterations = 1 this keeps each test to a single sizing pass.
    rg_args.subtool_args.pass_through = True
    rg_args.manual_obj_dir = os.path.join(
        tests_tree.search_subtrees(f"tests.data.{test_grp_name}.outputs", is_hier_tag = True)[0].path,
        f"stratix_iv_rrg_bram_22nm_{label}_passthrough_debug",
    )
    tests_common.write_fixture_json(rg_args)

    return rg_args


@pytest.mark.stratix_iv
@pytest.mark.custom_fpga
@pytest.mark.parametrize(
    "stratix_iv_bram_22nm_tb",
    _BRAM_22NM_PASSTHROUGH_CASES,
    indirect = True,
)
@skip_if_fixtures_only
def test_stratix_iv_bram_22nm_passthrough(
    stratix_iv_bram_22nm_tb: rg_ds.RadGenArgs, request: pytest.FixtureRequest
):
    """
        Runs the COFFE BRAM flow end-to-end in pass-through mode for each
        legacy COFFE BRAM configuration at 22nm.

        Pass-through skips the actual hspice simulations but still runs:
        - YAML config parsing & arch_params validation
        - FPGA + BRAM subcircuit object instantiation
        - SPICE netlist generation for every BRAM subcircuit (memory cell,
          row/col/conf decoders, sense amp, write driver, precharge,
          wordline driver, RAM local mux, output crossbar, etc.)
        - VPR architecture file emission with the BRAM block

        These together cover the BRAM-specific code paths an
        --enable_bram_module=1 run touches.

        Note: the MTJ case is marked `slow` because its mtj-specific
        sub-circuits add substantially to sizing-iteration time even in
        pass-through mode. Deselect with `pytest -m "not slow"`.
    """
    rg_args = copy.deepcopy(stratix_iv_bram_22nm_tb)
    tests_common.run_rad_gen(
        rg_args,
        tests_common.get_rg_home(),
    )


# Separate conf-init fixture/test: just verifies the BRAM yamls parse into
# valid CoffeArgs / Coffe data structures without invoking the COFFE flow.
@pytest.fixture
def stratix_iv_bram_22nm_conf_init_tb(stratix_iv_bram_22nm_tb) -> rg_ds.RadGenArgs:
    rg_args = copy.deepcopy(stratix_iv_bram_22nm_tb)
    rg_args.just_config_init = True
    rg_args.subtool_args.pass_through = False
    return rg_args


@pytest.mark.init
@pytest.mark.custom_fpga
@pytest.mark.parametrize(
    "stratix_iv_bram_22nm_tb",
    _BRAM_22NM_CONF_INIT_CASES,
    indirect = True,
)
@skip_if_fixtures_only
def test_stratix_iv_bram_22nm_conf_init(
    stratix_iv_bram_22nm_conf_init_tb: rg_ds.RadGenArgs, request: pytest.FixtureRequest
):
    """
        Fast smoke test: confirms each BRAM yaml can be parsed and yields a
        valid rad_gen Coffe configuration without running the rest of the flow.
    """
    rg_args = copy.deepcopy(stratix_iv_bram_22nm_conf_init_tb)
    rg_info, _ = tests_common.run_rad_gen(
        rg_args,
        tests_common.get_rg_home(),
    )
    # Basic sanity: the parsed config should have BRAM enabled and gate_length 22nm.
    coffe_struct = rg_info["coffe"]
    arch_params = coffe_struct.fpga_arch_conf["fpga_arch_params"]
    assert arch_params["enable_bram_module"] == 1, "enable_bram_module not set to 1"
    assert arch_params["gate_length"] == 22, "gate_length is not 22nm"


