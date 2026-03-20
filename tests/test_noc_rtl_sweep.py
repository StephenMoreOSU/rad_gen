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
import shutil

@pytest.fixture(scope='session')
def noc_rtl_sweep() ->  type[rg_ds.MetaDataclass]:
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

@pytest.fixture(scope='session')
def noc_rtl_sweep_parse() ->  type[rg_ds.MetaDataclass]:
    """
        Returns:
            The driver for generating SRAM configs + RTL
    """
    tests_tree: rg_ds.Tree
    tests_tree, _, test_name, _, _ = tests_common.get_test_info()
    
    # TODO make below string replacement more robust
    # We want to use the same directory as used by the noc_rtl_sweep run
    test_name = test_name.replace("_parse","")
    cur_test_input_dpath: str = tests_tree.search_subtrees(
        f"tests.data.{test_name}.inputs",
        is_hier_tag = True,
    )[0].path
    # Inputs 
    noc_sweep_path = os.path.join(cur_test_input_dpath, "noc_sweep.yml")
    assert os.path.exists(noc_sweep_path), f"Input path {noc_sweep_path} does not exist"
    asic_dse_args = rg_ds.AsicDseArgs(
        sweep_conf_fpath = noc_sweep_path,
        compile_results = True,
        # stdcell_lib__pdk_rundir_path = os.path.expanduser(os.path.join("~","ASAP_7_IC","asap7_rundir")),
        # scripts__virtuoso_setup_path = os.path.join(tests_common.get_rg_home(),"scripts","setup_virtuoso_env.sh"),
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


@pytest.fixture(scope='session')
def noc_rtl_sweep_output(noc_rtl_sweep) -> Tuple[List[ type[rg_ds.MetaDataclass]], rg_ds.Tree]:
    """
        Runs the NoC configs + RTL generation
        Returns:
            - List of RadGenArgs drivers that can be used to run sweep points
            - The project tree
    """
    return tests_common.run_sweep(noc_rtl_sweep)

@pytest.fixture(scope='session')
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

@pytest.fixture(scope='session')
def noc_sw_pt_asic_flow_tb(
    hammer_flow_template,
    get_sw_info,
) ->  type[rg_ds.MetaDataclass]:
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

@pytest.fixture(scope='session')
def noc_sw_pt_asic_flow_gds_tb(
    noc_sw_pt_asic_flow_tb: type[rg_ds.MetaDataclass],
    request: pytest.FixtureRequest
) ->  type[rg_ds.MetaDataclass]:
    # Requires the `test_noc_sw_pt_asic_flow` to be run first to get results to convert to gds in virtuoso as only timing + gds conversion is run in this stage
    rg_args = copy.deepcopy(noc_sw_pt_asic_flow_tb)
    rg_args.subtool_args.common_asic_flow__flow_stages__sram__run = False
    rg_args.subtool_args.common_asic_flow__flow_stages__syn__run = False
    rg_args.subtool_args.common_asic_flow__flow_stages__par__run = False
    rg_args.subtool_args.common_asic_flow__flow_stages__pt__run = True
    rg_args.subtool_args.scripts__virtuoso_setup_path = os.path.join(
        tests_common.get_rg_home(),"scripts","setup_virtuoso_env.sh"
    )
    # TODO figure out a good place to tell people to make this rundir
    rg_args.subtool_args.stdcell_lib__pdk_rundir_path = os.path.expanduser(
        os.path.join("~","ASAP_7_IC","asap7_rundir")
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
    tests_common.run_verif_hammer_asic_flow(
        rg_args = noc_sw_pt_asic_flow_tb,
        backup_flag = True,
    )

@pytest.fixture(scope='session')
def noc_sw_pt_parse_tb(noc_sw_pt_asic_flow_tb) ->  type[rg_ds.MetaDataclass]:
    rg_args = copy.deepcopy(noc_sw_pt_asic_flow_tb)
    rg_args.subtool_args.compile_results = True
    tests_common.write_fixture_json(rg_args)
    return rg_args

noc_sw_pt_parse_conf_init_tb = conftest.create_rg_fixture(
    input_fixture = 'noc_sw_pt_parse_tb',
    fixture_type = 'conf_init',
)

# SM: Removed the below test as it requires a specific parse golden results directory which could add confusion and it doesn't give us a ton of coverage anyway
# @pytest.mark.noc
# @pytest.mark.asic_flow
# @pytest.mark.init
# @skip_if_fixtures_only
# def test_noc_sw_pt_parse_conf_init(noc_sw_pt_parse_conf_init_tb, request):
#     tests_common.run_and_verif_conf_init(noc_sw_pt_parse_conf_init_tb)


@pytest.mark.noc
@pytest.mark.parse
@skip_if_fixtures_only
def test_noc_sw_pt_parse(noc_sw_pt_parse_tb, request):
    """
        Todos:
            * Add dependancy on the sweep point run as it must be run before this test
    """
    tests_common.run_verif_hammer_asic_flow(
        rg_args = noc_sw_pt_parse_tb,
        backup_flag = False, # Don't backup as this is for parsing existing results
    )

@pytest.mark.noc
@pytest.mark.asic_flow
@pytest.mark.gds
@skip_if_fixtures_only
def test_noc_sw_pt_asic_flow_virtuoso_gds(noc_sw_pt_asic_flow_gds_tb, request):
    if not os.path.exists(noc_sw_pt_asic_flow_gds_tb.subtool_args.stdcell_lib__pdk_rundir_path):
        pytest.skip(f"Path {noc_sw_pt_asic_flow_gds_tb.subtool_args.stdcell_lib__pdk_rundir_path} does not exist")    
    # Because this comes from a common parent tb we need to set the manual obj_dir to the new location
    top_lvl_module: str = os.path.basename(noc_sw_pt_asic_flow_gds_tb.manual_obj_dir)
    updated_obj_dir: str = tests_common.get_obj_dir_tb(top_lvl_module = top_lvl_module)
    # if updated obj dir already exists, then we want to do a manual backup before copying over new results, 
    #   otherwise we may have old results from a previous test run that will mess with our parsing and assertions
    if os.path.isdir(updated_obj_dir):
        backup_obj_dpath = f"{updated_obj_dir}_backup_{rg_ds.create_timestamp()}"
        shutil.move(updated_obj_dir, backup_obj_dpath)
    shutil.copytree(noc_sw_pt_asic_flow_gds_tb.manual_obj_dir, updated_obj_dir)
    noc_sw_pt_asic_flow_gds_tb.manual_obj_dir = updated_obj_dir
    tests_common.run_verif_hammer_asic_flow(
        rg_args = noc_sw_pt_asic_flow_gds_tb,
        backup_flag = False,
    )


# TODO add dependancy on the sweep point run as it must be run before this test
@pytest.mark.noc
@pytest.mark.parse
@skip_if_fixtures_only
def test_noc_rtl_sweep_parse(noc_rtl_sweep_parse: type[rg_ds.MetaDataclass] 
) -> Tuple[List[ type[rg_ds.MetaDataclass]], rg_ds.Tree]:
    """
        Parses results after running the NoC Sweep
    """
    # noc_rtl_sweep_parse.subtool_args.common.project_tree
    _, proj_tree, _ = tests_common.run_sweep(noc_rtl_sweep_parse)
    reports_dpath: str = os.path.join(
        proj_tree.search_subtrees(f"projects.{noc_rtl_sweep_parse.project_name}.outputs", is_hier_tag = True)[0].path,
        "router_wrap_bk", #TODO remove this hardcoding
        "reports"
    )

    tests_tree: rg_ds.Tree
    tests_tree, test_grp_name, test_name, test_out_dpath, rg_home = tests_common.get_test_info(stack_lvl = 2)
    golden_dpath = tests_tree.search_subtrees(
        f"tests.data.{test_grp_name}.golden_results.{test_name}", is_hier_tag = True
    )[0].path
    for key in ["summary", "detailed"]:
        gold_results_fpath = os.path.join(golden_dpath, f"{key}.csv")
        test_results_fpath = os.path.join(reports_dpath, f"{key}.csv")
        
        results_df = pd.read_csv(test_results_fpath)
        gold_results_df = pd.read_csv(gold_results_fpath)
        cmp_df = rg_utils.compare_results(test_results_fpath, gold_results_fpath).T.reset_index()
        print(rg_utils.text2ascii(f"{key}"))
        print(f"{f"{'#'*10} {rg_utils.pr_green('Golden')} @ {gold_results_fpath} {'#'*10}":^200}")
        for l in rg_utils.get_df_output_lines(gold_results_df):
            print(l)
        print(f"{'#'*200:^200}")
        print(f"{f"{'#'*10} {rg_utils.pr_yellow('Test')} @ {test_results_fpath} {'#'*10}":^200}")
        for l in rg_utils.get_df_output_lines(results_df):
            print(l)
        print(f"{'#'*200:^200}")
        print(f"{f'{"#"*10} {rg_utils.pr_cyan('Comparison')} {"#"*10}':^200}")    
        for l in rg_utils.get_df_output_lines(cmp_df):
            print(l)

        # The row index will always be 0 since the comparison is for a single run
        row_idx: int = 0
        # % tolerance allowed
        tolerance: float = 2.0 # Just set to 2% for now
        for col in cmp_df.columns:
            if col == "index":
                continue
            cmp_val: float | str = cmp_df[col].values[row_idx]
            try:
                if isinstance(cmp_val, float):
                    assert (cmp_val < tolerance and cmp_val > 0) or (cmp_val > -tolerance and cmp_val < 0 ) or cmp_val == 0.0 # % difference tolerance we allow
                elif isinstance(cmp_val, str):
                    assert cmp_val == "Matching"
                else:
                    assert False, f"Unexpected type {type(cmp_val)} for comparison value {cmp_val}"
            except AssertionError:
                print(rg_utils.pr_red(f"Golden and test results for {key} do not match within tolerance!"))
                assert False, f"Value for {col} does not match within tolerance: {cmp_val}"
        print(rg_utils.pr_green(f"Golden and test results for {key} match within tolerance!"))


    # proj_tree.search_subtrees(f"NoC.outputs.{noc_rtl_sweep_parse.subtool_args.}")
    # Comapare against golden
