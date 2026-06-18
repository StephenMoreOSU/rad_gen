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
def stratix_10() -> rg_ds.RadGenArgs:
    """
        Returns:
            The driver for generating SRAM configs + RTL
    """
    tests_tree: rg_ds.Tree
    tests_tree, test_grp_name, test_name, test_out_dpath, rg_home = tests_common.get_test_info()
    
    cur_test_input_dpath: str = tests_tree.search_subtrees(
        f"tests.data.{test_name}.inputs",
        is_hier_tag = True,
    )[0].path

    # Inputs
    stratix_10_fpath = os.path.join(cur_test_input_dpath, "stratix10_rrg.yml")
    assert os.path.exists(stratix_10_fpath), f"Input path {stratix_10_fpath} does not exist"

    coffe_args = rg_ds.CoffeArgs(
        fpga_arch_conf_path = stratix_10_fpath,
        # Parsed RRG stats (CSVs produced by src/common/rr_parse.py) drive the routing model.
        rrg_data_dpath = os.path.join(cur_test_input_dpath, "rrg_stats", "rr_graph_strtx10"),
        pass_through = True, # Generate the full circuit structure without running SPICE
        max_iterations = 1, # Low QoR but fast for testing purposes
        area_opt_weight = 1,
        delay_opt_weight = 2,
    )
    rg_args = rg_ds.RadGenArgs(
        override_outputs = True,
        manual_obj_dir = os.path.join(test_out_dpath, "stratix_10_rrg_debug"),
        project_name = "stratix_10",
        subtools = ["coffe"],
        subtool_args = coffe_args,
    )
    tests_common.write_fixture_json(rg_args)
    return rg_args


@pytest.fixture
def stratix_10_sizing() -> rg_ds.RadGenArgs:
    """
        Driver for a real COFFE transistor-sizing run on Stratix 10 (runs HSPICE).
        Same architecture as the `stratix_10` fixture but WITHOUT pass_through, so the
        sizing optimization loop actually executes. Writes to its own obj dir.
    """
    tests_tree: rg_ds.Tree
    tests_tree, test_grp_name, test_name, test_out_dpath, rg_home = tests_common.get_test_info()

    cur_test_input_dpath: str = tests_tree.search_subtrees(
        f"tests.data.stratix_10.inputs",
        is_hier_tag = True,
    )[0].path

    stratix_10_fpath = os.path.join(cur_test_input_dpath, "stratix10_rrg.yml")
    assert os.path.exists(stratix_10_fpath), f"Input path {stratix_10_fpath} does not exist"

    coffe_args = rg_ds.CoffeArgs(
        fpga_arch_conf_path = stratix_10_fpath,
        rrg_data_dpath = os.path.join(cur_test_input_dpath, "rrg_stats", "rr_graph_strtx10"),
        # No pass_through => transistor sizing runs (invokes HSPICE).
        max_iterations = 1, # One optimization iteration; bump up for higher QoR (longer runtime).
        area_opt_weight = 1,
        delay_opt_weight = 2,
    )
    rg_args = rg_ds.RadGenArgs(
        override_outputs = True,
        manual_obj_dir = os.path.join(test_out_dpath, "stratix_10_rrg_sizing"),
        project_name = "stratix_10",
        subtools = ["coffe"],
        subtool_args = coffe_args,
    )
    tests_common.write_fixture_json(rg_args)
    return rg_args


@pytest.mark.rrg
@skip_if_fixtures_only
def test_stratix_10_rrg_parse():
    import src.common.rr_parse as rr_parse
    tests_tree, test_grp_name, test_name, test_out_dpath, rg_home = tests_common.get_test_info()
    rrg_fpath: str = os.path.join(
            tests_tree.search_subtrees(
            f"tests.data.{test_grp_name}.inputs",
            is_hier_tag = True,
        )[0].path,
        "rr_graph_strtx10.xml"
    )
    assert os.path.exists(rrg_fpath), f"RRG file {rrg_fpath} does not exist"
    out_dpath = os.path.join(test_out_dpath, "parsed_rrg")
    os.makedirs(out_dpath, exist_ok=True)
    args = ["--rr_xml_fpath", rrg_fpath, "--out_dpath", out_dpath, "--generate_plots"]
    rr_parse.main(args)


@pytest.mark.stratix_10
@pytest.mark.custom_fpga
@skip_if_fixtures_only
def test_stratix_10(stratix_10: rg_ds.RadGenArgs, request: pytest.FixtureRequest):
    """ Run COFFE on the Stratix 10 architecture (pass-through: generate structure, no SPICE). """
    rg_args = copy.deepcopy(stratix_10)
    ret_val: Any = tests_common.run_rad_gen(
        stratix_10,
        tests_common.get_rg_home(),
    )


@pytest.mark.stratix_10
@pytest.mark.custom_fpga
@pytest.mark.sizing
@skip_if_fixtures_only
def test_stratix_10_sizing(stratix_10_sizing: rg_ds.RadGenArgs, request: pytest.FixtureRequest):
    """ Run COFFE transistor sizing on the Stratix 10 architecture (runs HSPICE; long runtime). """
    rg_args = copy.deepcopy(stratix_10_sizing)
    ret_val: Any = tests_common.run_rad_gen(
        stratix_10_sizing,
        tests_common.get_rg_home(),
    )