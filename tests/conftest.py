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

@pytest.fixture
def hammer_flow_template() -> Tuple[rg_ds.RadGenArgs, rg_ds.Tree]:
    """
        Uses some dummy arguments with the basic flow arguments to get both
        - A project tree
        - A driver object that can be modified by other flows for desired results
    """
    rg_home: str = os.environ.get("RAD_GEN_HOME")
    tests_tree = tests_common.init_tests_tree()
    asic_dse_inputs_dpath: str = tests_tree.search_subtrees(f"tests.data.asic_dse", is_hier_tag = True)[0].path
    # Inputs
    # Using defualt env.yml, cadence_tools.yml, and asap7.yml for sys configs
    tool_env_conf_fpath = os.path.join(asic_dse_inputs_dpath, "env.yml")
    base_configs = [
        os.path.join(asic_dse_inputs_dpath, "cad_tools", "cadence_tools.yml"),
        os.path.join(asic_dse_inputs_dpath, "pdks", "asap7.yml"),
    ]
    dummy_flow_conf_fpath = os.path.join(asic_dse_inputs_dpath, "dummy", "dummy_base.yml")
    dummy_rtl_dpath = os.path.join(f"{asic_dse_inputs_dpath}","dummy","rtl","src")
    
    for input_path in [tool_env_conf_fpath, dummy_flow_conf_fpath, *base_configs, dummy_rtl_dpath]:
        assert os.path.exists(input_path), f"Input path {input_path} does not exist"
    # Dummy output manual obj dpath
    manual_obj_dpath = os.path.join(
        asic_dse_inputs_dpath, "dummy", "obj_dir"
    )
    # Create drivers for RAD-Gen dummy flow to get proj_tree for generic asic_flow
    asic_dse_args = rg_ds.AsicDseArgs(
        tool_env_conf_fpaths = [tool_env_conf_fpath],
        flow_conf_fpaths = base_configs + [dummy_flow_conf_fpath],
        common_asic_flow__top_lvl_module = "dummy",
        common_asic_flow__hdl_path = dummy_rtl_dpath,
        stdcell_lib__pdk_name = "asap7",
        mode__vlsi__flow = "hammer",
        mode__vlsi__run = "serial",
    )
    dummy_asic_flow_args = rg_ds.RadGenArgs(
        project_name = "dummy",
        subtools = ["asic_dse"],
        subtool_args = asic_dse_args,
        manual_obj_dir = manual_obj_dpath,
        just_config_init = True,
    )
    _, proj_tree = driver.run_rad_gen(dummy_asic_flow_args, rg_home)
    # Removing unneeded arguments from the dummy run 

    # Get the dummy flow paths and remove the flow conf with 'dummy' in the name (still keeping cad_tools & pdk)
    flow_conf_fpaths: List[str] = [
        fpath for fpath in dummy_asic_flow_args.subtool_args.flow_conf_fpaths if "dummy" not in os.path.basename(fpath)
    ]
    dummy_asic_flow_args.subtool_args.flow_conf_fpaths = flow_conf_fpaths
    # Remove the rtl path + top_lvl_module
    dummy_asic_flow_args.subtool_args.common_asic_flow__top_lvl_module = None
    dummy_asic_flow_args.subtool_args.common_asic_flow__hdl_path = None
    # Remove just_config_init
    dummy_asic_flow_args.just_config_init = False
    # Set all stages of asic flow to run
    dummy_asic_flow_args.subtool_args.common_asic_flow__flow_stages__syn__run = True
    dummy_asic_flow_args.subtool_args.common_asic_flow__flow_stages__par__run = True
    dummy_asic_flow_args.subtool_args.common_asic_flow__flow_stages__pt__run = True

    return dummy_asic_flow_args, proj_tree

