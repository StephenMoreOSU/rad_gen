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
import src.common.utils as rg_utils
import tests.common.common as tests_common


def get_tests_info(
    tests_dpath: str,
    test_arg: str = None,
    init_marker_str: str = None
) -> list[dict]:
    # Get all the tests which we want to generate a golden init struct for
    pytest_collect_args = ["pytest", "--collect-only-with-markers", "--disable-pytest-warnings"]
    
    test_args = []
    if test_arg:
        test_args += test_arg.split(" ")
    else:
        test_args.append(tests_dpath)
    
    if init_marker_str:
        test_args += ["-m", init_marker_str]
    
    pytest_collect_args += test_args
    result = sp.run(pytest_collect_args, stdin=sp.PIPE, stdout=sp.PIPE, stderr=sp.PIPE, text=True)

    # Grabs all text before the last ']' character (should all be json parsable)
    grab_test_info_re = re.compile(r".*\]", re.DOTALL)
    test_info_json_text = grab_test_info_re.findall(result.stdout)[0]

    tests_info: list[dict] = json.loads(test_info_json_text)

    # Remove any 'conf_init' tests from the list
    tests_info = [ test_info for test_info in tests_info if "conf_init" not in test_info["name"] ]

    return tests_info


def update_golden_results(
    tests_info: list[dict],
    tests_dpath: str,
):
    # Tests follow naming convension so if we strip "test_" and each of possible type fn strs we get name to group tests by
    test_type_fn_strs = [
        # Common
        "parse",
        "conf_init",
        # ASIC DSE
        "asic_flow",
    ]
    # Find a string for each group of tests.
    # Group defined currently as test + parse + conf_init of a single test
    test_group_tags: set = set()
    for test_info in tests_info:
        group_name = str(test_info["name"]).replace("test_", "")
        for type_fn_str in test_type_fn_strs:
            group_name = group_name.replace(f"_{type_fn_str}", "")
        test_group_tags.add(group_name)
    # Create the test groups
    test_groups: dict = {}
    for tag in test_group_tags:
        # Get all tests that have the tag in their name, put them in a dict entry
        test_groups[tag] = [ test_info for test_info in tests_info if tag in test_info["name"] ]
    
    group_test_infos: list[dict]
    for tag, group_test_infos in test_groups.items():
        # Find the non "conf_init" and non "parse" test
        core_test: list[dict] = [ 
            test_info for test_info in group_test_infos 
                if all(marker not in test_info["markers"] for marker in ["init", "parse"])  
        ]
        parse_test: list[dict] = [ 
            test_info for test_info in group_test_infos 
                if any(marker in test_info["markers"] for marker in ["parse"])  
        ]
        init_test: list[dict] = [
            test_info for test_info in group_test_infos 
                if any(marker in test_info["markers"] for marker in ["init"])
        ]

        if not core_test:
            print(f"No core test found for group '{tag}'")
            continue

        core_test: dict = core_test[0]
        parse_test: dict = parse_test[0] if len(parse_test) > 0 else None
        init_test: dict = init_test[0] if len(init_test) > 0 else None

        # Tests which don't have a golden result directory
        if any( marker in core_test["markers"] for marker in ["asic_sweep", "buff_3d"]):
            print(f"one of marked tests in {core_test['markers']} do not have a golden result directory")
            continue


        core_test_fname: str = os.path.basename(core_test["file"])
        core_test_dname: str = str(os.path.splitext(core_test_fname)[0]).replace("test_","")
        # Where we get our golden results from 
        core_test_data_dpath: str = os.path.join(
            tests_dpath, 
            "data", 
            core_test_dname
        )
        os.makedirs(core_test_data_dpath, exist_ok=True)
        core_out_dpath = os.path.join(core_test_data_dpath, "outputs", str(core_test["name"]).replace("test_",""))
        # Paths we are will be sending output results to
        golden_res_dpaths: list[str] = []
        for test_info in [core_test, parse_test]:
            # If there is not a parse test just skip that part
            if not test_info:
                continue
            test_fname = os.path.basename(test_info["file"])
            test_dname = str(os.path.splitext(test_fname)[0]).replace("test_","")
            test_data_dpath: str = os.path.join(tests_dpath, "data", test_dname)
            golden_res_dpath = os.path.join(test_data_dpath, "golden_results", str(test_info["name"]).replace("test_",""))
            golden_res_dpaths.append(golden_res_dpath)

        if not os.path.isdir(core_test_data_dpath):
            print(f"No data directory found for test '{core_test['name']}'")
            continue
        elif not os.path.exists(core_out_dpath):
            print(f"No output directory found for test '{core_test['name']}'")
            continue
        
        # Depending on the core test type we will copy over golden results from the output directory
        if "asic_flow" in core_test["markers"]:
            # Take obj dir w shortest name as this one will be the newest version if backups exist
            obj_dname: str = sorted(os.listdir(core_out_dpath), key=len)[0]
            results_dpath: str = os.path.join(core_out_dpath, obj_dname, "reports")
            for dpath in golden_res_dpaths:
                print(f"{results_dpath} --> {dpath}")
                csv_fpaths = glob.glob(f"{results_dpath}/*.csv")
                for csv_fpath in csv_fpaths:
                    shutil.copy(csv_fpath, dpath)
        elif "coffe" in core_test["markers"]:
            raise NotImplementedError("COFFE test golden result updating not implemented")
        elif "ic_3d" in core_test["markers"]:
            raise NotImplementedError("IC 3D test golden result updating not implemented")


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
    test_args = []
    if test_arg:
        test_args += test_arg.split(" ")
    else:
        test_args.append(tests_dpath)    
    if init_marker_str:
        test_args += ["-m", init_marker_str]
    
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
            json_text = json.dumps(rg_utils.rec_convert_dataclass_to_dict(init_struct), cls=tests_common.EnhancedJSONEncoder, indent=4)
            golden_res_out_fpath = os.path.join(
                golden_res_out_dpath,
                f"init_struct_{fixture_fn_name}.json"
            )
            with open(golden_res_out_fpath, "w") as f:
                f.write(json_text)
            # Hack but just in case there's still any non $RAD_GEN_HOME replaced paths, replace them again
            repl_script_result = sp.run([os.path.join(rg_home, "scripts", "rg_home_path_repl.sh"), golden_res_out_fpath], stdout=sp.PIPE, stderr=sp.PIPE, text=True)
            print(f"Writing out golden result to '{golden_res_out_fpath}'")
            # Break out of loop as we assume the first fixture arg is the only one that we compare against
            # TODO validate above lines assumption
            break


def clean_fixtures(tests_dpath: str):
    """
        Remove all the fixture json files generated by running pytest --fixtures-only
    """
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
        In the future we should remove the various <run_option> flags and simply provide the test specification (directory/file/test) and marker filter string
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
    

    
    # For generating struct initialization golden results
    if parsed_args.get("struct_init"):
        conf_init_gen(
            tests_dpath, 
            test_arg = parsed_args.get("test_arg"),
            init_marker_str = parsed_args.get("markers"))
    else:
        # Get test info from collecting pytests
        tests_info: list[dict] = get_tests_info(
            tests_dpath,
            test_arg = parsed_args.get("test_arg"),
            init_marker_str = parsed_args.get("markers")
        )
        update_golden_results(tests_info, tests_dpath)


    # Full cleanup of test + fixture outputs
    if parsed_args.get("clean_fixtures"):
        clean_fixtures(tests_dpath)

    

if __name__ == "__main__":
    # Called from cmd line
    arguments: dict = parse_args()
    main(**arguments)