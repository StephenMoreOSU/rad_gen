from __future__ import annotations
import os, sys
import subprocess as sp
import re
import shutil
import glob

import argparse
import importlib
import json

from typing import List, Tuple, Dict, Any, Callable, Sequence

import pytest
import inspect

import src.common.data_structs as rg_ds
import tests.common.common as tests_common

def asic_flow_gen(
    test_data_dpaths: str,
    pytest_fpaths: List[str],
):
    # Need to map the obj dirs substrs (named with top_lvl_modules) to a substr of test names
    test_2_obj_map: dict = {
        "noc_sw_pt": "router_wrap_bk",
        "alu_sw_pt": "alu_ver",
        "single_macro": "wrapper", # Will just look for dir with _wrapper in it (should only be 1)
        "stitched_sram": "sram_macro_map",
    }
    all_tests = set()
    evald_tests = set()
    for test_idx, data_dpath in enumerate(test_data_dpaths):
        out_dpath = os.path.join(data_dpath, "outputs")
        if not os.path.exists(out_dpath):
            continue
        # There should be a golden result dir for each test in the file, we can find these tests with a pytest command
        test_fpath = pytest_fpaths[test_idx]
        # Find all the names of tests in the file
        result = sp.run(["pytest", "--collect-only", test_fpath], stdin=sp.PIPE, stdout=sp.PIPE, stderr=sp.PIPE, text=True)
        grab_test_names_re = re.compile(r"(?<=::)test_(\w+)")
        test_names = [ match for match in grab_test_names_re.findall(result.stdout) ]
        all_tests.update( set(test_names))
        # Look at all the output directories for the test
        for obj_dname in sorted(os.listdir(out_dpath), len):
            results_dpath: str = os.path.join(out_dpath, obj_dname, "reports")
            test_golden_res_dpaths = []
            for test_substr, obj_substr in test_2_obj_map.items():
                # Check to see if the obj_dname has a test mapping
                if obj_substr in obj_dname:
                    # If it does we use that test mapping to find the golden result directory
                    golden_res_dnames = os.listdir(os.path.join(data_dpath, "golden_results"))
                    test_golden_res_dpath = [
                        os.path.join(
                            data_dpath,
                            "golden_results",
                            golden_res_dname
                        ) for golden_res_dname in golden_res_dnames if test_substr in golden_res_dname
                    ]
                    obj_test_names = [ test_name for test_name in test_names if test_substr in test_name ]
                    if len(test_golden_res_dpath) != 0:
                        test_golden_res_dpaths.append(test_golden_res_dpath[0])
                    else:
                        print(f"No golden results directory found for {obj_dname}")
                    break
            evald_tests_set = set()
            # Check to see if there is a mapping between the obj_dname and the test name
            if test_golden_res_dpaths:
                print("Overriding golden results for the following tests:")
                for test_name in obj_test_names:
                    evald_tests_set.add(test_name)
                    print(f"*\t{test_name}")
                for dpath in test_golden_res_dpaths:
                    print(f"{results_dpath} --> {dpath}")
                    csv_fpaths = glob.glob(f"{results_dpath}/*.csv")
                    for csv_fpath in csv_fpaths:
                        shutil.copy(csv_fpath, dpath)
            else:
                print(f"echo 'No golden results directory found for {obj_dname}'")
            evald_tests.update(evald_tests_set)
    print("Tests without golden results directories:")
    for test_name in all_tests.difference(evald_tests):
        print(f"*\t{test_name}")


def conf_init_gen(
    tests_dpath: str,
    test_arg: str = None,
    init_marker_str: str = None
):
    """
        Generates golden results for every test case that performs data structure initialization
        If a test fixture writes out a .json file to its corresponding `fixtures` directory in format `<fixture_name>.json`, 
        then a test case is considered to perform data structure initialization.

        A side effect of assumptions in this function is that we expect there to be a fixture produce a rg_ds.RadGenArgs object and pass it to its corresponding test.
    """
    # TODO define created dirs with Tree data structures for flexibility into future
    rg_home: str = os.environ.get("RAD_GEN_HOME")

    # Test tree to traverse test dir / files
    tests_tree = tests_common.init_tests_tree()
    # Get all the tests which we want to generate a golden init struct for
    pytest_collect_args = ["pytest", "--collect-only"]
    if init_marker_str:
        # markers_or: str = " or ".join([f"{marker}" for marker in init_markers])
        if test_arg:
            # If test arg is a path to a particular test file
            if os.path.isfile(test_arg):
                test_args = [test_arg, "-m", init_marker_str]
            # If the test is a function in a test file, markers don't do anything
            else:
                test_args = [test_arg]
        else:
            # If no test arg is given, run all tests with the markers
            test_args = [tests_dpath, "-m", init_marker_str]
    # No markers provided but a test arg is given and its either a test file or a test function
    elif test_arg and (os.path.isfile(test_arg) or os.path.isfile(test_arg.split("::")[0])):
        test_args = [test_arg]
    # If none of the above we run for all tests
    else:
        test_args = [tests_dpath]
    pytest_collect_args += test_args
    result = sp.run(pytest_collect_args, stdin=sp.PIPE, stdout=sp.PIPE, stderr=sp.PIPE, text=True)
    grab_test_info_re = re.compile(r"(.*)::(.*)")
    # List of tuples with [0] = relative path to test file and [1] = test function name 
    tests_info: List[Tuple[str, str]] = [ match for match in grab_test_info_re.findall(result.stdout) ]
    test_fixture_mapping_fpath: str = os.path.join(tests_dpath, "data", "meta", "test_fixture_mapping.json")

    # Run all fixtures that are dependencies for test markers
    # They will output a json file with the arguments to run rad_gen
    # Lots of errors will be generated but it works if rg_args json files are written out
    tests_common.run_fixtures(rg_home, test_args = test_args)
    
    # Remove any 'conf_init' tests from the list
    tests_info = [ test_info for test_info in tests_info if "conf_init" not in test_info[1] ]

    for test_info in tests_info:
        test_fn_name: str = test_info[1]
        test_dname: str = os.path.splitext(
            os.path.basename(test_info[0]).replace("_test","").replace("test_","")
        )[0]
        golden_res_dname: str = test_info[1].replace("_test","").replace("test_","")
        # Get output path to write the new golden confs to and create test specific dir if doesn't exist
        golden_res_out_dpath = os.path.join(tests_dpath, "data", test_dname, "golden_results", golden_res_dname)
        os.makedirs(golden_res_out_dpath, exist_ok=True)
        # Parse the test -> test_fixture mapping file to determine which fixtures to call to generate the init struct for each tests
        test_fixture_mappings: dict = json.load(open(test_fixture_mapping_fpath))
        fixtures: List[str] = test_fixture_mappings.get(test_fn_name)
        # Loop through fixture function names and search for the corresponding output json file (the dump of intialized data structures)
        for fixture_fn_name in fixtures:
            conf_gen_rg_args_fpath: str = os.path.join(
                tests_tree.search_subtrees(
                    f"tests.data.{test_dname}.fixtures",
                    is_hier_tag = True,
                )[0].path,
                f"{fixture_fn_name}.json"
            )
            # If it exists it means its a valid test:fixture combo to be generated
            if os.path.exists(conf_gen_rg_args_fpath):
                # Get raw dict
                rg_args_dict = json.load(open(conf_gen_rg_args_fpath, "r"))
                # Convert its fields into thier respective dataclasses
                rg_args_dict["cli_args"] = [
                    rg_ds.GeneralCLI(**cli_arg) for cli_arg in rg_args_dict["cli_args"]
                ]
                rg_args_dict["subtool_args"]["cli_args"] = [
                    rg_ds.GeneralCLI(**cli_arg) for cli_arg in rg_args_dict["subtool_args"]["cli_args"]
                ]
                # Classes are in camel case by default
                subtool_cli_str: str = str(rg_args_dict["subtools"][0]).replace("_","")
                # Look through data structures and find the CLI corresponding to the subtool
                members = inspect.getmembers(rg_ds, inspect.isclass)
                subtool_cli_cls = None
                for member in members:
                    if (subtool_cli_str.lower() in member[0].lower()) and ("Args".lower() in member[0].lower()):
                        subtool_cli_cls = getattr(rg_ds, member[0])
                # TODO find a way to get subtool data structure from subtool str
                rg_args_dict["subtool_args"] = subtool_cli_cls(**rg_args_dict["subtool_args"])
                test_rg_args = rg_ds.RadGenArgs(**rg_args_dict)
            else:
                print(f"Fixture '{fixture_fn_name}' does not exist for test '{test_fn_name}'")
                continue
            # Call main with the RadGenArgs obj to get the initialized data structures
            test_rg_args.just_config_init = True # Set flag to only init configs and exit early
            rg_info, _ = tests_common.run_rad_gen(test_rg_args, rg_home)
            # convert rg_info into subtool struct
            subtool: str = test_rg_args.subtools[0]
            init_struct = rg_info[subtool]
            json_text = json.dumps(tests_common.rec_convert_dataclass_to_dict(init_struct), cls=tests_common.EnhancedJSONEncoder, indent=4)
            golden_res_out_fpath = os.path.join(
                golden_res_out_dpath,
                f"init_struct_{fixture_fn_name}.json"
            )
            with open(golden_res_out_fpath, "w") as f:
                f.write(json_text)
            print(f"Writing out golden result to '{golden_res_out_fpath}'")
            # Break out of loop as we assume the first fixture arg is the only one that we compare against
            # TODO validate above lines assumption
            break


def clean_fixtures(tests_dpath: str):
    # Remove all the fixture json files generated by running pytest --fixtures-only
    for root, dirs, files in os.walk(tests_dpath):
        for file in files:
            if file.endswith(".json") and os.path.basename(root) == "fixtures":
                print(f"deleting '{os.path.join(root, file)}'")
                os.remove(os.path.join(root, file))
    # Remove all generated conf init golden json files
    # Find golden result directories
    find_golden_results = sp.run(
        ["find", f"{tests_dpath}", "-type", "d", "-name", "golden_results", "-print0"],
        capture_output=True,
        text=True
    )
    golden_dirs = find_golden_results.stdout.split('\0')
    json_files = []
    for golden_dir in golden_dirs:
        if golden_dir:  # avoid processing empty strings
            find_json_files = sp.run(
                ["find", golden_dir, "-name", "*.json", "-print0"],
                capture_output=True,
                text=True
            )
            json_files.extend(find_json_files.stdout.split('\0'))
    for json_file in json_files:
        if json_file:
            print(f"deleting '{json_file}'")
            os.remove(json_file)

def parse_args(arguments: Sequence | None = None) -> dict:
    """
        In the future we should remove the various \<run_option\> flags and simply provide the test specification (directory/file/test) and marker filter string
        as arguments s.t. based on the type of marker, the script will understand which directory structure it will have to traverse to obtain comparison results
        and override the goldens.
    """
    parser = argparse.ArgumentParser(description="Update golden results for tests")
    parser.add_argument(
        "--asic_flow",
        action="store_true",
        help="Update golden results for ASIC flow tests"
    )
    parser.add_argument(
        "--struct_init",
        action="store_true",
        help="Update golden results for struct initialization tests",
        default = True
    )
    parser.add_argument(
        "--clean_fixtures",
        action="store_true",
        help="Clean up all fixture json files"
    )
    parser.add_argument(
        "-m",
        "--markers",
        type=str,
        help="Marker string to pass to pytest to select tests with specific markers, e.g. 'init or asic_flow'"
    )
    parser.add_argument(
        "-t",
        "--test_arg",
        type=str,
        help="Test argument to pass to pytest to select test file or test function"
    )
    parsed_args: dict
    if arguments is None:
        parsed_args = vars(parser.parse_args())
    else:
        parsed_args = vars(parser.parse_args(arguments))
    return parsed_args

def main(*args, **kwargs):
    parsed_args: dict
    if args and isinstance(args[0], list):
        # If called with a list of arguments
        parsed_args = parse_args(args[0])
    else:
        # If called with keyword arguments
        parsed_args = kwargs

    # Only works for ASIC tests atm TODO update
    rg_home = os.environ.get("RAD_GEN_HOME")
    tests_dpath = os.path.join(rg_home, "tests")
    
    # Search through files in test dir and see if they have a corresponding dir in data dir
    test_data_dpaths: List[str] = []
    pytest_fpaths: List[str] = []
    for fname in os.listdir(tests_dpath):
        test_data_dpath: str = os.path.join(
            tests_dpath, 
            "data", 
            os.path.splitext(fname)[0].replace("_test","").replace("test_","")
        )
        if os.path.isdir(test_data_dpath):
            test_data_dpaths.append(test_data_dpath)
            # Append corresponding pytest fpath to same index as test_data_dpath
            pytest_fpaths.append(
                os.path.join(
                    tests_dpath,
                    fname
                )
            )
    # For generating golden results for ASIC flow tests
    if parsed_args.get("asic_flow"):
        asic_flow_gen(test_data_dpaths, pytest_fpaths)
    
    # For generating struct initialization golden results
    if parsed_args.get("struct_init"):
        conf_init_gen(
            tests_dpath, 
            test_arg = parsed_args.get("test_arg"),
            init_markers = parsed_args.get("markers"))
    
    # Full cleanup of test + fixture outputs
    if parsed_args.get("clean_fixtures"):
        clean_fixtures(tests_dpath)

    








if __name__ == "__main__":
    # Called from cmd line
    arguments: dict = parse_args()
    main(**arguments)