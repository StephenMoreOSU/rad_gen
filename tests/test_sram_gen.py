from __future__ import annotations
import os, sys

from typing import List, Tuple, Dict

# Try appending rg base path to sys.path (this worked)
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import src.common.data_structs as rg_ds
import src.common.utils as rg_utils
import tests.common.driver as driver
import tests.common.common as tests_common

import tests.conftest as conftest
from tests.conftest import skip_if_fixtures_only

import pytest

import pandas as pd
import copy


@pytest.fixture
def sram_gen() -> rg_ds.RadGenArgs:
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
    sram_sweep_path = os.path.join(cur_test_input_dpath, "sram_sweep.yml")
    assert os.path.exists(sram_sweep_path), f"Input path {sram_sweep_path} does not exist"
    asic_dse_args = rg_ds.AsicDseArgs(
        sweep_conf_fpath = sram_sweep_path,
    )
    sram_gen_args = rg_ds.RadGenArgs(
        override_outputs = True,
        subtools = ["asic_dse"],
        subtool_args = asic_dse_args,
    )
    tests_common.write_fixture_json(sram_gen_args)
    return sram_gen_args

@pytest.fixture
def sram_gen_output(sram_gen: rg_ds.RadGenArgs) -> Tuple[
    List[rg_ds.RadGenArgs],
    rg_ds.Tree,
    rg_ds.RadGenArgs
]:
    """
        Fixture to ingest the SRAM sweep generation driver, run the sweep command, and return its output

        Args:
            sram_gen: The driver for generating SRAM configs + RTL

        Returns:
            Tuple of the output of the SRAM sweep. 
                [0] is the list of all RadGenArgs that can be used to run each individual generated SRAM through asic flow.
                [1] is the project tree that has been initialized through the RAD-Gen sweep command.
                [2] is the original input RadGenArgs (`sram_gen`) that was used to generate the sweep
    """
    return tests_common.run_sweep(sram_gen)

@pytest.fixture
def get_stitched_srams() -> List[Dict[str, int]]:
    """
        Fixture to generate a list of dictionaries of all stitched SRAM macros to be generated.
        
        Returns:
            List of dictionaries of stitched SRAM macros to be generated / verified
    """
    stitched_macros: List[Dict[str, int]] = [
        {
            # for now this will only support RW not either R or W
            "rw_ports": 2,
            # size in [w,d]
            "w": 1024,
            "d": 256
        },
        ################## DEPTH 512 ##################
        {
            # for now this will only support RW not either R or W
            "rw_ports": 2,
            # size in [w,d]
            "w": 256,
            "d": 512
        },
        {
            # for now this will only support RW not either R or W
            "rw_ports": 2,
            # size in [w,d]
            "w": 512,
            "d": 512
        },
        {
            # for now this will only support RW not either R or W
            "rw_ports": 2,
            # size in [w,d]
            "w": 1024,
            "d": 512
        },
        ################## DEPTH 1024 ##################
        {
            # for now this will only support RW not either R or W
            "rw_ports": 2,
            # size in [w,d]
            "w": 256,
            "d": 1024
        },
        {
            # for now this will only support RW not either R or W
            "rw_ports": 2,
            # size in [w,d]
            "w": 512,
            "d": 1024
        },
        {
            # for now this will only support RW not either R or W
            "rw_ports": 2,
            # size in [w,d]
            "w": 1024,
            "d": 1024
        },
        ################## DEPTH 2048 ##################
        {
            # for now this will only support RW not either R or W
            "rw_ports": 2,
            # size in [w,d]
            "w": 256,
            "d": 2048
        },
        {
            # for now this will only support RW not either R or W
            "rw_ports": 2,
            # size in [w,d]
            "w": 512,
            "d": 2048
        },
        {
            # for now this will only support RW not either R or W
            "rw_ports": 2,
            # size in [w,d]
            "w": 1024,
            "d": 2048
        },
        ################## DEPTH 64 ##################
        {
            # for now this will only support RW not either R or W
            "rw_ports": 2,
            # size in [w,d]
            "w": 256,
            "d": 64
        },
        {
            # for now this will only support RW not either R or W
            "rw_ports": 2,
            # size in [w,d]
            "w": 512,
            "d": 64
        },
        {
            # for now this will only support RW not either R or W
            "rw_ports": 2,
            # size in [w,d]
            "w": 1024,
            "d": 64
        }
    ]
    return stitched_macros

@pytest.fixture
def get_dut_single_macro(sram_gen_output) -> Tuple[
    rg_ds.Tree, 
    str,
    Dict[str, int],
]:
    """
        Fixture to generate information required to test a single DUT SRAM macro defined by the `macro_params` dict.

        Args:
            sram_gen_output: The output of the SRAM sweep generation driver
        
        Returns:
            Tuple of the project tree (taken from `sram_gen_output`), the path to the macro config file, and the macro parameters

    """
    macro_params: dict = {
        "rw_ports": 2,
        "w": 32,
        "d": 128,
    }
    proj_tree: rg_ds.Tree
    sw_pt_args_list, proj_tree, _ = sram_gen_output
    # We want to test the asic flow for a single sram macro
    sram_gen_conf_dpath: str = proj_tree.search_subtrees(
        "shared_resources.sram_lib.configs.gen",
        is_hier_tag = True
    )[0].path
    macro_conf_fpath: str = os.path.join(
        sram_gen_conf_dpath, 
        # concat str over mult lines
        (
            f"sram_SRAM{macro_params['rw_ports']}"
            f"RW{macro_params['d']}x{macro_params['w']}.json"
        )
    )
    return proj_tree, macro_conf_fpath, macro_params

@pytest.fixture
def get_dut_stitched_sram(sram_gen_output) ->Tuple[
    rg_ds.Tree, 
    str,
    Dict[str, int],
]:
    """
        Fixture to generate information required to test a previously generated stitched DUT SRAM macro defined by the `sram_params` dict.

        Args:
            sram_gen_output: The output of the SRAM sweep generation driver

        Returns:
            Tuple of the project tree (taken from `sram_gen_output`), the path to the stitched macro config file, and the stitch macro SRAM parameters
    """
    sram_params = {
        "rw_ports": 2,
        "w": 256,
        "d": 512,
    }
    proj_tree: rg_ds.Tree
    sw_pt_args_list, proj_tree, _ = sram_gen_output
    # We want to test the asic flow for a single sram macro
    sram_gen_conf_dpath: str = proj_tree.search_subtrees(
        "shared_resources.sram_lib.configs.gen",
        is_hier_tag = True
    )[0].path
    sram_conf_fpath: str = os.path.join(
        sram_gen_conf_dpath, 
        # concat str over mult lines
        (
            f"sram_config_sram_macro_map_"
            # TODO macros need to swap order of w and d
            f"{sram_params['rw_ports']}x{sram_params['w']}x{sram_params['d']}.json" 
        )
    )
    return proj_tree, sram_conf_fpath, sram_params


sram_gen_conf_init_tb = conftest.create_rg_fixture(
    input_fixture = 'sram_gen',
    fixture_type = 'conf_init',
)

@pytest.mark.sram
@pytest.mark.asic_sweep
@pytest.mark.init
@skip_if_fixtures_only
def test_sram_gen_conf_init(sram_gen_conf_init_tb, request):
    """
        Test the data struct initialization of the SRAM generation test `test_sram_gen`
        
        Args:
            sram_gen_conf_init_tb: rg_ds.RadGenArgs obj from conf_init fixture generated from the `sram_gen` fixture
            request: pytest request, for @skip_if_fixtures_only decorator, to skip if only fixtures are being run
        
    """
    tests_common.run_and_verif_conf_init(sram_gen_conf_init_tb)

@pytest.mark.sram
@pytest.mark.asic_sweep
@skip_if_fixtures_only
def test_sram_gen(sram_gen_output, get_stitched_srams, request):
    """
        Test the generation of SRAM configs and RTL for a list of stitched SRAM macros

        Args:
            sram_gen_output: The output of the SRAM sweep generation driver
            get_stitched_srams: The list of stitched SRAM macros to be generated / verified
            request: pytest request, for @skip_if_fixtures_only decorator, to skip if only fixtures are being run
    """
    proj_tree: rg_ds.Tree
    _, proj_tree, _ = sram_gen_output
    stitched_mems: List[Dict[str, int]] = get_stitched_srams

    conf_gen_dpath: str = proj_tree.search_subtrees("shared_resources.sram_lib.configs.gen", is_hier_tag = True)[0].path
    rtl_gen_dpath: str = proj_tree.search_subtrees("shared_resources.sram_lib.rtl.gen", is_hier_tag = True)[0].path

    for stitched_mem in stitched_mems:
        # Get the key for the test sram
        test_sram_key: str = f"{stitched_mem['rw_ports']}x{stitched_mem['w']}x{stitched_mem['d']}"
        sram_gen_conf_fpaths: List[str] = [
            # TODO get the composition of macros for each mapped SRAM and perform some check
            # os.path.join(conf_gen_dpath, f"mem_params_SRAM{test_gen_sram_params['rw_ports']}RW{test_gen_sram_params['w']}x{test_gen_sram_params['d']}.json"),
            os.path.join(conf_gen_dpath, f"sram_config_sram_macro_map_{test_sram_key}.json")
        ]
        # Assert expected files were generated
        # Configs
        for sram_gen_conf_fpath in sram_gen_conf_fpaths:
            assert os.path.exists(sram_gen_conf_fpath), f"SRAM config file {sram_gen_conf_fpath} does not exist"
        # RTL
        rtl_gen_fpath: str = os.path.join(rtl_gen_dpath, f"sram_macro_map_{test_sram_key}",f"sram_macro_map_{test_sram_key}.sv")
        assert os.path.exists(rtl_gen_fpath), f"SRAM RTL file {rtl_gen_fpath} does not exist"


#   ___ ___    _   __  __   ___ ___ _  _  ___ _    ___   __  __   _   ___ ___  ___  
#  / __| _ \  /_\ |  \/  | / __|_ _| \| |/ __| |  | __| |  \/  | /_\ / __| _ \/ _ \ 
#  \__ \   / / _ \| |\/| | \__ \| || .` | (_ | |__| _|  | |\/| |/ _ \ (__|   / (_) |
#  |___/_|_\/_/ \_\_|  |_| |___/___|_|\_|\___|____|___| |_|  |_/_/ \_\___|_|_\\___/ 

@pytest.fixture
def single_macro_asic_flow_tb(
    hammer_flow_template, 
    get_dut_single_macro
) -> rg_ds.RadGenArgs:
    """
        
    """
    proj_tree: rg_ds.Tree
    subtool_fields: dict = {
        "common_asic_flow__flow_stages__sram__run": True,
    }
    # We want to test the asic flow for a single sram macro
    proj_tree, test_macro_conf_fpath, test_sram_macro_params = get_dut_single_macro
    rg_args: rg_ds.RadGenArgs = tests_common.gen_hammer_flow_rg_args(
        hammer_flow_template = hammer_flow_template,
        proj_name = "sram",
        top_lvl_module = "SRAM2RW128x32_wrapper",
        design_conf_fpath = test_macro_conf_fpath,
        subtool_fields = subtool_fields,
    )
    tests_common.write_fixture_json(rg_args)
    return rg_args

single_macro_asic_flow_conf_init_tb = conftest.create_rg_fixture(
    input_fixture = 'single_macro_asic_flow_tb',
    fixture_type = 'conf_init',
)

@pytest.mark.sram
@pytest.mark.asic_flow
@pytest.mark.init
@skip_if_fixtures_only
def test_single_macro_asic_flow_conf_init(single_macro_asic_flow_conf_init_tb, request):
    tests_common.run_and_verif_conf_init(single_macro_asic_flow_conf_init_tb)

@pytest.mark.sram
@pytest.mark.asic_flow
@skip_if_fixtures_only
def test_single_macro_asic_flow(single_macro_asic_flow_tb, request):
    tests_common.run_verif_hammer_asic_flow(rg_args = single_macro_asic_flow_tb)


@pytest.fixture
def single_macro_parse_tb(single_macro_asic_flow_tb) -> rg_ds.RadGenArgs:
    rg_args = copy.deepcopy(single_macro_asic_flow_tb)
    rg_args.subtool_args.compile_results = True
    tests_common.write_fixture_json(rg_args)
    return rg_args

single_macro_parse_conf_init_tb = conftest.create_rg_fixture(
    input_fixture = 'single_macro_parse_tb',
    fixture_type = 'conf_init',
)

@pytest.mark.sram
@pytest.mark.parse
@pytest.mark.init
@skip_if_fixtures_only
def test_single_macro_parse_conf_init(single_macro_parse_conf_init_tb, request):
    tests_common.run_and_verif_conf_init(single_macro_parse_conf_init_tb)

@pytest.mark.sram
@pytest.mark.parse
@skip_if_fixtures_only
def test_single_macro_parse(single_macro_parse_tb, request):
    tests_common.run_verif_hammer_asic_flow(
        rg_args = single_macro_parse_tb,
        backup_flag = False, # Don't backup as this is for parsing existing results
    )

#   ___ ___    _   __  __   ___ _____ ___ _____ ___ _  _ ___ ___    __  __   _   ___ ___  ___  
#  / __| _ \  /_\ |  \/  | / __|_   _|_ _|_   _/ __| || | __|   \  |  \/  | /_\ / __| _ \/ _ \ 
#  \__ \   / / _ \| |\/| | \__ \ | |  | |  | || (__| __ | _|| |) | | |\/| |/ _ \ (__|   / (_) |
#  |___/_|_\/_/ \_\_|  |_| |___/ |_| |___| |_| \___|_||_|___|___/  |_|  |_/_/ \_\___|_|_\\___/ 

@pytest.fixture
def stitched_sram_asic_flow_tb(
    hammer_flow_template,
    get_dut_stitched_sram
) -> rg_ds.RadGenArgs:
    proj_tree: rg_ds.Tree
    proj_tree, test_stitched_conf_fpath, test_stitched_sram_params = get_dut_stitched_sram
    subtool_fields: dict = {
        "common_asic_flow__flow_stages__sram__run": True,
    }
    rg_args: rg_ds.RadGenArgs = tests_common.gen_hammer_flow_rg_args(
        hammer_flow_template = hammer_flow_template,
        proj_name = "sram",
        top_lvl_module = "sram_macro_map_2x256x512",
        design_conf_fpath = test_stitched_conf_fpath,
        subtool_fields = subtool_fields,
        # proj_tree = proj_tree,
    )
    tests_common.write_fixture_json(rg_args)
    return rg_args


stitched_sram_asic_flow_conf_init_tb = conftest.create_rg_fixture(
    input_fixture = 'stitched_sram_asic_flow_tb',
    fixture_type = 'conf_init',
)

@pytest.mark.sram
@pytest.mark.asic_flow
@pytest.mark.init
@skip_if_fixtures_only
def test_stitched_sram_asic_flow_conf_init(stitched_sram_asic_flow_conf_init_tb, request):
    tests_common.run_and_verif_conf_init(stitched_sram_asic_flow_conf_init_tb)

@pytest.mark.sram
@pytest.mark.asic_flow
@skip_if_fixtures_only
def test_stitched_sram_asic_flow(stitched_sram_asic_flow_tb, request):
    tests_common.run_verif_hammer_asic_flow(rg_args = stitched_sram_asic_flow_tb)

@pytest.fixture
def stitched_sram_parse(stitched_sram_asic_flow_tb) -> rg_ds.RadGenArgs:
    rg_args = copy.deepcopy(stitched_sram_asic_flow_tb)
    rg_args.subtool_args.compile_results = True
    tests_common.write_fixture_json(rg_args)
    return rg_args

stitched_sram_parse_conf_init_tb = conftest.create_rg_fixture(
    input_fixture = 'stitched_sram_parse',
    fixture_type = 'conf_init',
)

@pytest.mark.sram
@pytest.mark.parse
@pytest.mark.init
@skip_if_fixtures_only
def test_stitched_sram_parse_conf_init(stitched_sram_parse_conf_init_tb, request):
    tests_common.run_and_verif_conf_init(stitched_sram_parse_conf_init_tb)

@pytest.mark.sram
@pytest.mark.parse
@skip_if_fixtures_only
def test_stitched_sram_parse(stitched_sram_parse, request):
    tests_common.run_verif_hammer_asic_flow(
        rg_args = stitched_sram_parse,
        backup_flag = False, # Don't backup as this is for parsing existing results
    )

