from __future__ import annotations
import os, sys

from typing import List, Tuple

# Try appending rg base path to sys.path (this worked)
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import src.common.data_structs as rg_ds
import src.common.utils as rg_utils
import tests.common.driver as driver
import tests.common.common as tests_common

import copy

import pytest
from functools import wraps

def pytest_addoption(parser: pytest.Parser):
    parser.addoption(
        "--fixtures-only", action="store_true", help="Run all fixtures (current tests depend on) without running tests"
    )

def skip_if_fixtures_only(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        request = kwargs.get('request')
        if request and request.config.getoption("--fixtures-only"):
            pytest.skip("Skipping test as --fixtures-only option is set")
        return func(*args, **kwargs)
    return wrapper


# Generic fixture that takes another fixture as an argument
def create_rg_fixture(
    input_fixture: str,
    fixture_type: str
):
    @pytest.fixture
    @skip_if_fixtures_only
    def parse_fixture(request):
        input_data = request.getfixturevalue(input_fixture)
        rg_args = copy.deepcopy(input_data)
        rg_args.subtool_args.compile_results = True
        tests_common.write_fixture_json(rg_args, stack_lvl = 7)
        return rg_args
    
    @pytest.fixture
    @skip_if_fixtures_only
    def conf_init_fixture(request):
        input_data = request.getfixturevalue(input_fixture)
        rg_args = copy.deepcopy(input_data)
        rg_args.just_config_init = True
        return rg_args
    
    if fixture_type == "conf_init":
        return conf_init_fixture
    elif fixture_type == "parse":
        return parse_fixture

# Dict which maps tests to the fixtures which they use as inputs
test_fixture_mapping = {}

def pytest_collection_modifyitems(session: pytest.Session, config: pytest.Config, items: List[pytest.Item]):
    """
    Pytest hook that runs during the collection phase of pytest.
    """
    item: pytest.Item
    for item in items:
        # Get the test name
        test_name = item.name
        # Get the fixture names used by the test
        fixture_names = item.fixturenames
        # print(f"Collected test {test_name} uses fixtures: {fixture_names}")
        # Store the mapping
        test_fixture_mapping[test_name] = fixture_names

# def pytest_runtest_setup(item: pytest.Item):
#     # Kinda a hacky way to get fixtures to run for specific tests yet it seems to work
#     # Errors are thrown when running pytest with --fixtures-only 
#     #   Yet we only want the fixtures to be run and thier object jsons to be outputted (which works as expected)
#     if item.config.getoption("--fixtures-only"):
#         # Ensure the fixture is executed
#         for fixturedef in item._fixtureinfo.name2fixturedefs.values():
#             # Assume fixtures in fixturedef are sorted in order of dependency
#             for fixture in fixturedef:
#                 # "Setup" the fixture
#                 fixture.execute(request=item._request)

def pytest_sessionfinish(session: pytest.Session, exitstatus: pytest.ExitCode):
    # Mapping out fpath
    mapping_fpath: str = os.path.join(
        os.environ.get("RAD_GEN_HOME"),
        "tests", "data", "meta",
        "test_fixture_mapping.json"
    )
    os.makedirs(os.path.dirname(mapping_fpath), exist_ok=True)
    with open( mapping_fpath, 'w') as f:
        import json
        json.dump(test_fixture_mapping, f, indent=4)

# Make sure to include the necessary pytest hooks
pytest.hookimpl(tryfirst=True)(pytest_collection_modifyitems)
pytest.hookimpl(trylast=True)(pytest_sessionfinish)

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
    _, proj_tree = tests_common.run_rad_gen(dummy_asic_flow_args, rg_home)
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
