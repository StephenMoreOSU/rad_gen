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
def ic_3d_flow_template() -> rg_ds.RadGenArgs:
    tests_tree, test_grp_name, test_name, test_out_dpath, rg_home = tests_common.get_test_info()
    in_conf_dpath: str = tests_tree.search_subtrees(
        f"tests.data.{test_grp_name}.inputs", is_hier_tag = True
    )[0].path
    dummy_st_args = rg_ds.IC3DArgs(
        input_config_path = os.path.join(in_conf_dpath, "3D_ic_explore.yaml")
    )
    dummy_ic_3d_args = rg_ds.RadGenArgs(
        project_name = "dummy",
        subtools = ["ic_3d"],
        override_outputs = True,
        subtool_args = dummy_st_args,
    )
    return dummy_ic_3d_args

@pytest.fixture
def ic_3d_tb(ic_3d_flow_template: rg_ds.RadGenArgs):
    rg_args = copy.deepcopy(ic_3d_flow_template)
    rg_args.project_name = "intel_foveros_ic_3d"
    rg_args.subtool_args.buffer_dse = True
    tests_common.write_fixture_json(rg_args)
    return rg_args


buffer_dse_conf_init_tb = conftest.create_rg_fixture(
    input_fixture = 'ic_3d_tb',
    fixture_type = 'conf_init'
)

@pytest.mark.buff_3d
@pytest.mark.init
@skip_if_fixtures_only
def test_buffer_dse_conf_init(buffer_dse_conf_init_tb, request):
    tests_common.run_and_verif_conf_init(buffer_dse_conf_init_tb)


@pytest.mark.buff_3d
@skip_if_fixtures_only
def test_buffer_dse(ic_3d_tb: rg_ds.RadGenArgs, request):
    """

    """
    rg_args = ic_3d_tb
    ret_val: Any = tests_common.run_rad_gen(
        rg_args, 
        tests_common.get_rg_home(),
    )



