# Test file for single wire type FPGAs
# These tests use the Fs_mtx method with a single wire type (L4 or L16)
# Used for comparison with legacy COFFE which only supported single wire types

from __future__ import annotations
import os
import copy

from typing import Any

import rad_gen as rg
import src.common.data_structs as rg_ds

import pytest

import tests.common.common as tests_common
from tests.conftest import skip_if_fixtures_only


# ============================================================================
# L4-only FPGA Tests
# ============================================================================

@pytest.fixture
def l4_only() -> rg_ds.RadGenArgs:
    """
        Returns test args for L4-only FPGA using Fs_mtx method.
        This is a single wire type FPGA for comparison with legacy COFFE.
    """
    tests_tree: rg_ds.Tree
    tests_tree, test_grp_name, test_name, test_out_dpath, rg_home = tests_common.get_test_info()

    cur_test_input_dpath: str = tests_tree.search_subtrees(
        f"tests.data.{test_grp_name}.inputs",
        is_hier_tag=True,
    )[0].path

    l4_only_fpath = os.path.join(cur_test_input_dpath, "l4_only.yml")
    assert os.path.exists(l4_only_fpath), f"Input path {l4_only_fpath} does not exist"

    coffe_args = rg_ds.CoffeArgs(
        fpga_arch_conf_path=l4_only_fpath,
        rrg_data_dpath=None,  # No RRG data - uses Fs_mtx method
        max_iterations=1,
        area_opt_weight=1,
        delay_opt_weight=2,
        pass_through=True,  # Use pass_through to just test initialization
    )
    rg_args = rg_ds.RadGenArgs(
        override_outputs=True,
        manual_obj_dir=os.path.join(rg_home, "tests", "data", "single_wire", "outputs", "l4_only_debug"),
        project_name="l4_only",
        subtools=["coffe"],
        subtool_args=coffe_args,
    )
    tests_common.write_fixture_json(rg_args)
    return rg_args


@pytest.fixture
def l4_only_full() -> rg_ds.RadGenArgs:
    """
        Returns test args for L4-only FPGA full run (no pass_through).
        This runs the full COFFE transistor sizing optimization.
    """
    tests_tree: rg_ds.Tree
    tests_tree, test_grp_name, test_name, test_out_dpath, rg_home = tests_common.get_test_info()

    cur_test_input_dpath: str = tests_tree.search_subtrees(
        f"tests.data.{test_grp_name}.inputs",
        is_hier_tag=True,
    )[0].path

    l4_only_fpath = os.path.join(cur_test_input_dpath, "l4_only.yml")
    assert os.path.exists(l4_only_fpath), f"Input path {l4_only_fpath} does not exist"

    coffe_args = rg_ds.CoffeArgs(
        fpga_arch_conf_path=l4_only_fpath,
        rrg_data_dpath=None,  # No RRG data - uses Fs_mtx method
        max_iterations=1,
        area_opt_weight=1,
        delay_opt_weight=2,
    )
    rg_args = rg_ds.RadGenArgs(
        override_outputs=True,
        manual_obj_dir=os.path.join(rg_home, "tests", "data", "single_wire", "outputs", "l4_only_full"),
        project_name="l4_only_full",
        subtools=["coffe"],
        subtool_args=coffe_args,
    )
    tests_common.write_fixture_json(rg_args)
    return rg_args


@pytest.mark.single_wire
@pytest.mark.l4
@skip_if_fixtures_only
def test_l4_only_init(l4_only: rg_ds.RadGenArgs, request: pytest.FixtureRequest):
    """
        Tests L4-only FPGA initialization using Fs_mtx method.
        Uses pass_through mode to only test initialization (no SPICE simulation).
    """
    rg_args = copy.deepcopy(l4_only)
    ret_val = tests_common.run_rad_gen(
        rg_args,
        tests_common.get_rg_home(),
    )


@pytest.mark.single_wire
@pytest.mark.l4
@pytest.mark.full_run
@skip_if_fixtures_only
def test_l4_only_full(l4_only_full: rg_ds.RadGenArgs, request: pytest.FixtureRequest):
    """
        Tests L4-only FPGA full run using Fs_mtx method.
        Runs full COFFE transistor sizing optimization.
        WARNING: This test takes a long time (5-10 hours).
    """
    rg_args = copy.deepcopy(l4_only_full)
    ret_val = tests_common.run_rad_gen(
        rg_args,
        tests_common.get_rg_home(),
    )


# ============================================================================
# L16-only FPGA Tests
# ============================================================================

@pytest.fixture
def l16_only() -> rg_ds.RadGenArgs:
    """
        Returns test args for L16-only FPGA using Fs_mtx method.
        This is a single wire type FPGA for comparison with legacy COFFE.
    """
    tests_tree: rg_ds.Tree
    tests_tree, test_grp_name, test_name, test_out_dpath, rg_home = tests_common.get_test_info()

    cur_test_input_dpath: str = tests_tree.search_subtrees(
        f"tests.data.{test_grp_name}.inputs",
        is_hier_tag=True,
    )[0].path

    l16_only_fpath = os.path.join(cur_test_input_dpath, "l16_only.yml")
    assert os.path.exists(l16_only_fpath), f"Input path {l16_only_fpath} does not exist"

    coffe_args = rg_ds.CoffeArgs(
        fpga_arch_conf_path=l16_only_fpath,
        rrg_data_dpath=None,  # No RRG data - uses Fs_mtx method
        max_iterations=1,
        area_opt_weight=1,
        delay_opt_weight=2,
        pass_through=True,  # Use pass_through to just test initialization
    )
    rg_args = rg_ds.RadGenArgs(
        override_outputs=True,
        manual_obj_dir=os.path.join(rg_home, "tests", "data", "single_wire", "outputs", "l16_only_debug"),
        project_name="l16_only",
        subtools=["coffe"],
        subtool_args=coffe_args,
    )
    tests_common.write_fixture_json(rg_args)
    return rg_args


@pytest.fixture
def l16_only_full() -> rg_ds.RadGenArgs:
    """
        Returns test args for L16-only FPGA full run (no pass_through).
        This runs the full COFFE transistor sizing optimization.
    """
    tests_tree: rg_ds.Tree
    tests_tree, test_grp_name, test_name, test_out_dpath, rg_home = tests_common.get_test_info()

    cur_test_input_dpath: str = tests_tree.search_subtrees(
        f"tests.data.{test_grp_name}.inputs",
        is_hier_tag=True,
    )[0].path

    l16_only_fpath = os.path.join(cur_test_input_dpath, "l16_only.yml")
    assert os.path.exists(l16_only_fpath), f"Input path {l16_only_fpath} does not exist"

    coffe_args = rg_ds.CoffeArgs(
        fpga_arch_conf_path=l16_only_fpath,
        rrg_data_dpath=None,  # No RRG data - uses Fs_mtx method
        max_iterations=1,
        area_opt_weight=1,
        delay_opt_weight=2,
    )
    rg_args = rg_ds.RadGenArgs(
        override_outputs=True,
        manual_obj_dir=os.path.join(rg_home, "tests", "data", "single_wire", "outputs", "l16_only_full"),
        project_name="l16_only_full",
        subtools=["coffe"],
        subtool_args=coffe_args,
    )
    tests_common.write_fixture_json(rg_args)
    return rg_args


@pytest.mark.single_wire
@pytest.mark.l16
@skip_if_fixtures_only
def test_l16_only_init(l16_only: rg_ds.RadGenArgs, request: pytest.FixtureRequest):
    """
        Tests L16-only FPGA initialization using Fs_mtx method.
        Uses pass_through mode to only test initialization (no SPICE simulation).
    """
    rg_args = copy.deepcopy(l16_only)
    ret_val = tests_common.run_rad_gen(
        rg_args,
        tests_common.get_rg_home(),
    )


@pytest.mark.single_wire
@pytest.mark.l16
@pytest.mark.full_run
@skip_if_fixtures_only
def test_l16_only_full(l16_only_full: rg_ds.RadGenArgs, request: pytest.FixtureRequest):
    """
        Tests L16-only FPGA full run using Fs_mtx method.
        Runs full COFFE transistor sizing optimization.
        WARNING: This test takes a long time 5-10hrs.
    """
    rg_args = copy.deepcopy(l16_only_full)
    ret_val = tests_common.run_rad_gen(
        rg_args,
        tests_common.get_rg_home(),
    )
