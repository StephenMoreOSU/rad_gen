import csv
import pandas as pd

import plotly.subplots as subplots
import plotly.graph_objects as go
import plotly.subplots as subplots
import plotly.express as px

# import src.ic_3d.buffer_dse as buff_dse
import src.ic_3d.ic_3d as ic_3d
import src.common.data_structs as rg_ds
import src.common.utils as rg_utils
import src.ic_3d.buffer_dse as buff_dse

from typing import List, Dict, Any, Tuple, Type, NamedTuple, Set, Optional, Union

import re
# Sp Process for CONTROL SB_MUX
import os
import pandas as pd

import argparse
import time
import multiprocessing as mp
# def parse_cli_args():
#     parser = argparse.ArgumentParser(description="Parse the command line arguments for the script")
#     parser.add_argument(
#         '-d', '--dut_subckt', action='store_true',
#         help="If a dut subckt is specified, the <category>.log files in current dir will be parsed to create timestep output for that particular subckt"
#     )
#     return parser.parse_args()



def file_negative_union():
    sandbox_dpath = os.path.expanduser("~/Documents/rad_gen/unit_tests/sandbox")
    # Comparing parameter files
    tracked_params_fpath = os.path.join(sandbox_dpath, "uniq_tracked_params.txt")
    all_params_fpath = os.path.join(sandbox_dpath, "all_sb_mux_params.txt")
    out_lines: List[str] = []
    with open(tracked_params_fpath, "r") as f1:
        with open(all_params_fpath, "r") as f2:
            lines1: List[str] = f1.readlines()
            lines2: List[str] = f2.readlines()
            for line2 in lines2:
                matches = []
                for line1 in lines1:
                    # if the lines match we want to remove them from our outputs
                    matches.append(line1.strip().lower() == line2.strip().lower())
                # if no match for against line2 comp to all of line 1
                if not any(matches):
                    out_lines.append(line2.strip())
            
    for l in out_lines:
        print(l)



# def cmp_coffe_runs(ctrl_dir: str, dut_dir: str):
#     """
#         Takes two coffe output directories. 
#         First will find which keys to compare between the two runs.  
#     """
#     # TAKES DUT AND CTRL COFFE OUTPUT DIRECTORIES AND CREATES LOG FILES COMPARING KEYS FOR EACH CATAGORY

#     # Compare each of the {area/delay/tx_sizes/wire_length}_debug.csv files in the control & test directories at each timestep
#     debug_csv_file_strs = ["area","tx_size","wire_length", "delay"]

#     # Check to make sure the output csvs exist in the control and test directories
#     for dpath in [ctrl_dir, dut_dir]:
#         for cat in debug_csv_file_strs:
#             csv_fpath = os.path.join(dpath, f"{cat}_debug.csv")
#             assert os.path.exists(csv_fpath), f"Error, {csv_fpath} does not exist in {dpath}"


    


def gen_cmp_info_from_coarse_csvs(debug_str: str, ctrl_dir: str, dut_dir: str, out_dir: str):
    in_file = f"{debug_str}.csv"
    ctrl_fpath = os.path.join(ctrl_dir, in_file)
    dut_fpath = os.path.join(dut_dir, in_file)
    dut_dicts = rg_utils.read_csv_to_list(dut_fpath)
    ctrl_dicts = rg_utils.read_csv_to_list(ctrl_fpath)
    out_fname = f"{os.path.splitext(os.path.basename(in_file))[0]}_coarse.log"
    print(f"CTRL fpath: {ctrl_fpath}")
    print(f"DUT fpath: {dut_fpath}")
    
    out_col_spacing = 50
    idx_col_spacing = 25

    params = [
        "ble_outputs", 
        "sb_mux",
        "cb_load",
        "sb_load",
        "gen_routing",
        "general_ble_output_load"
    ]

    fd = open(f"{os.path.join(out_dir, out_fname)}", "w")
    print(f"{'TAG':<{idx_col_spacing}}{'OUTER_ITER':<{idx_col_spacing}}{'SIZING_SBCKT':<{idx_col_spacing}}{'INNER_ITER':<{idx_col_spacing}}{'TRAN_SET_ITER':<{out_col_spacing}}\
          {'CTRL_KEY':<{out_col_spacing}}{'CTRL_VAL':<{out_col_spacing}}{'DUT_KEY':<{out_col_spacing}}{'DUT_VAL':<{out_col_spacing}}{'%_DIFF':<{idx_col_spacing}}", file=fd)
    # print(f"{'TAG':<{idx_col_spacing}}{'OUTER_ITER':<{idx_col_spacing}}{'SIZING_SBCKT':<{idx_col_spacing}}{'INNER_ITER':<{idx_col_spacing}}{'TRAN_SET_ITER':<{out_col_spacing}}\
    #       {'CTRL_KEY':<{out_col_spacing}}{'CTRL_VAL':<{out_col_spacing}}{'DUT_KEY':<{out_col_spacing}}{'DUT_VAL':<{out_col_spacing}}{'%_DIFF':<{idx_col_spacing}}")



    i: int = 0
    j: int = 0
    while i < len(dut_dicts) and j < len(ctrl_dicts):

        # Save the iteration information to a seperate dict which we'll iterate and compare with ctrl key val pairs to ensure the same timestep, if they are different we keep looking for a matching timestep
        cur_iter_book: dict = {}

        # These have the iteration keys which we know will be equal regardless of additional or different subckts in comparison
        iter_keys = [
            "TAG",
            "OUTER_ITER",
            "INNER_ITER",
            "TRAN_SET_ITER"
        ]
        # The SIZING_SUBCKT key could be different so we deal with it differently

        dut_keys = list(dut_dicts[0].keys())
        ctrl_keys = list(ctrl_dicts[0].keys())
        # Check to make sure that whatever row we happen to be on its the same length as previous rows
        assert len(dut_keys) == len(dut_dicts[i].keys()), f"{len(dut_keys)} != {len(dut_dicts[i].keys())}, {dut_keys} != {dut_keys[i].keys()}"
        assert len(ctrl_keys) == len(ctrl_dicts[j].keys()), f"{len(ctrl_keys)} != {len(ctrl_dicts[j].keys())}, {ctrl_keys} != {ctrl_dicts[j].keys()}"

        for dut_key in dut_keys:
            # Assumed that keys are read in LEFT -> RIGHT order of CSV Header
            equiv_timestep: bool = False
            # Make sure we compare the same timestep & other tag & iter information
            if dut_key in iter_keys:
                # These should be equal regardless of other run parameters
                cur_iter_book[dut_key] = dut_dicts[i][dut_key]
            elif dut_key == "SIZING_SBCKT":
                dut_val = dut_dicts[i][dut_key]
                # Check if the current sizing_subckt is a substr of our listed parameterized subckts
                if any([param in dut_val for param in params]):
                    sizing_subckt = re.sub(r"_uid\d", "", dut_val)
                else:
                    sizing_subckt = dut_val
                cur_iter_book[dut_key] = sizing_subckt

            # Check to see if the current iteration is ready to be compared
            if set(iter_keys + ["SIZING_SBCKT"]) == set(list(cur_iter_book.keys())):
                # If all keys are equivalent then we have the right timestep and we're good to go with printing out the comparison
                equiv_timestep = all([ctrl_dicts[j].get(iter_key) == cur_iter_book.get(iter_key) for iter_key in iter_keys + ["SIZING_SBCKT"]])
                assert equiv_timestep, f"Error, could not find all keys in {iter_keys + ['SIZING_SBCKT']} in {cur_iter_book.keys()}"

            if equiv_timestep:
                # Skip the iteration if we are looking at a timestep value
                if dut_key in iter_keys + ["SIZING_SBCKT"]:
                    continue
                # Find a CTRL key DUT pair even if they dont have exact same string (matching multiple DUT to one CTRL)
                if "general_ble_output_sb_mux_uid" in dut_key:
                    ctrl_key = re.sub(r"_sb_mux_uid\d", "", dut_key)
                # For older COFFE runs which doesnt have wire_general_ble_output_load
                if "wire_general_ble_output_load" == dut_key and "_uid" not in dut_key:
                    ctrl_key = "wire_general_ble_output"
                # Any parameterized key should just have a _uidX suffix so we can remove that to compare to a CTRL with no parameterization
                elif any(param in dut_key for param in params):
                    ctrl_key = re.sub(r"_uid\d", "", dut_key)
                else:
                    ctrl_key = dut_key

                # Set values for this comparison row
                try:
                    ctrl_val = ctrl_dicts[j][ctrl_key]
                    dut_val = dut_dicts[i][dut_key]
                except:
                    print(f"Error, could not find key {ctrl_key} in {ctrl_fpath}")
                    print(f"    or {dut_key} in {dut_fpath}")
                    continue

                # Try to get difference, possible div 0 exception so we catch that
                try:
                    perc_diff = round(
                        (100 * (float(dut_val) - float(ctrl_val)) / float(ctrl_val)),
                        3
                    )
                except:
                    perc_diff = "N/A"
                # Gets the current iteration information to print out
                cur_iter_ids = ''.join([
                    f"{cur_iter_book[iter_key]:<{idx_col_spacing}}" for iter_key in cur_iter_book.keys()
                ])
                # Prints the line to the log file
                print(f"{cur_iter_ids}\
                    {ctrl_key:<{out_col_spacing}}{ctrl_val:<{out_col_spacing}}{dut_key:<{out_col_spacing}}{dut_val:<{out_col_spacing}}{perc_diff:<{idx_col_spacing}}",file=fd)
                # print(f"{cur_iter_ids}\
                    # {ctrl_key:<{out_col_spacing}}{ctrl_val:<{out_col_spacing}}{dut_key:<{out_col_spacing}}{dut_val:<{out_col_spacing}}{perc_diff:<{idx_col_spacing}}")
        i += 1
        j += 1
    
    fd.close()


def gen_cmp_info_from_debug_csvs(debug_str: str, ctrl_dir: str, dut_dir: str, out_dir: str):
    in_file = f"{debug_str}_debug.csv"
    ctrl_fpath = os.path.join(ctrl_dir, in_file)
    dut_fpath = os.path.join(dut_dir, in_file)
    dut_dicts = rg_utils.read_csv_to_list(dut_fpath)
    ctrl_dicts = rg_utils.read_csv_to_list(ctrl_fpath)


    out_fname = os.path.splitext(os.path.basename(in_file))[0]
    print(f"CTRL fpath: {ctrl_fpath}")
    print(f"DUT fpath: {dut_fpath}")

    params = [
        "ble_outputs", 
        "sb_mux",
        "cb_load",
        "sb_load",
        "gen_routing",
        "general_ble_output_load"
    ]
    
    # ctrl_cols = set(list(ctrl_dicts[0].keys))
    # dut_cols = set(list(dut_dicts[0].keys))
    # dijoint_cols = (ctrl_cols | dut_cols) - (ctrl_cols & dut_cols)

    out_col_spacing = 50
    idx_col_spacing = 20

    os.makedirs(out_dir, exist_ok=True)
    print(f"Writing comparison log files to {os.path.join(out_dir, out_fname)}.log")
    fd = open(f"{os.path.join(out_dir, out_fname)}.log", "w")
    # Print header for the type of debug info we are looking at
    print(f"{'AREA_IDX':<{idx_col_spacing}}{'WIRE_IDX':<{idx_col_spacing}}{'DELAY_IDX':<{idx_col_spacing}}{'COMPUTE_DIST_IDX':<{idx_col_spacing}}\
            {'CTRL_KEY':<{out_col_spacing}}{'CTRL_VAL':<{out_col_spacing}}{'DUT_KEY':<{out_col_spacing}}{'DUT_VAL':<{out_col_spacing}}{'%_DIFF':<{idx_col_spacing}}", file=fd)
    # print(f"{'AREA_IDX':<{idx_col_spacing}}{'WIRE_IDX':<{idx_col_spacing}}{'DELAY_IDX':<{idx_col_spacing}}{'COMPUTE_DIST_IDX':<{idx_col_spacing}}\
    #         {'CTRL_KEY':<{out_col_spacing}}{'CTRL_VAL':<{out_col_spacing}}{'DUT_KEY':<{out_col_spacing}}{'DUT_VAL':<{out_col_spacing}}{'%_DIFF':<{idx_col_spacing}}")

    
    iter_keys = [
        "AREA",
        "WIRE",
        "DELAY",
        "COMPUTE_DIST"
    ]
    debug_iter_keys = [
        "AREA_UPDATE_ITER",
        "WIRE_UPDATE_ITER",
        "DELAY_UPDATE_ITER",
        "COMPUTE_DISTANCE_ITER"
    ]
    # for param_re in param_res:
    i: int = 0
    j: int = 0
    while i < len(dut_dicts) and j < len(ctrl_dicts):

        cur_iter_book: dict = {}

        dut_keys = list(dut_dicts[0].keys())
        ctrl_keys = list(ctrl_dicts[0].keys())
        assert len(dut_keys) == len(dut_dicts[i].keys()), f"{len(dut_keys)} != {len(dut_dicts[i].keys())}, {dut_keys} != {dut_keys[i].keys()}"
        assert len(ctrl_keys) == len(ctrl_dicts[j].keys()), f"{len(ctrl_keys)} != {len(ctrl_dicts[j].keys())}, {ctrl_keys} != {ctrl_dicts[j].keys()}"


        # If there were uneven number of print statements between runs we can skip until we find a matching timestep
        # Make sure we compare the same timestep & iter keys have been set

        # row_mismatch = False
        # ctrl_iter_idx = sum(int(ctrl_dicts[j].get(iter_key)) for iter_key in debug_iter_keys)
        # dut_iter_idx = sum(int(dut_dicts[i].get(iter_key)) for iter_key in debug_iter_keys)
        # while ctrl_iter_idx != dut_iter_idx:
        #     print(f"Error, attempting to compare mismatching timesteps: {ctrl_iter_idx} != {dut_iter_idx}")
        #     if ctrl_iter_idx > dut_iter_idx:
        #         i += 1
        #     else:
        #         j += 1

        # try:
        #     assert ctrl_iter_idx == dut_iter_idx, f"Error, attempting to compare mismatching timesteps: {ctrl_iter_idx} != {dut_iter_idx}"
        # except AssertionError as e:
        #     row_mismatch = True
        #     print(e)
        # if row_mismatch:
        #     if ctrl_iter_idx > dut_iter_idx:
        #         i += 1
        #     else:
        #         j += 1
        #     continue
        

        # for debug_iter_key in debug_iter_keys:
        #     try:
        #         assert ctrl_dicts[j].get(debug_iter_key) == dut_dicts[i].get(debug_iter_key), f"Error, attempting to compare mismatching timesteps: {ctrl_dicts[j].get(debug_iter_key)} != {dut_dicts[i].get(debug_iter_key)}"
        #     except AssertionError as e:
        #         print(e)
        #         row_mismatch = True
        #         break
        #         # i += 1
        #         # j += 1 # Works if the CTRL is behind the DUT?
        # if row_mismatch:
        #     if i > 

        for dut_key in dut_keys:
            if "TAG" in dut_key:
                # Skip over call stack tags
                continue
            if "ITER" in dut_key:
                if "COMPUTE_DIST" in dut_key:
                    iter_key = "compute_dist"
                    cur_iter_book["compute_dist"] = dut_dicts[i][dut_key]
                else:
                    iter_key = dut_key.replace("_UPDATE_ITER","").lower()
                    # Assigns the iteration to a book to be used in later prints
                    cur_iter_book[iter_key] = dut_dicts[i][dut_key]

                continue
            # Find a CTRL key DUT pair even if they dont have exact same string (matching multiple DUT to one CTRL)
            elif "general_ble_output_sb_mux_uid" in dut_key:
                ctrl_key = re.sub(r"_sb_mux_uid\d", "", dut_key)
            # For older COFFE runs which doesnt have wire_general_ble_output_load
            elif "wire_general_ble_output_load" == dut_key and "_uid" not in dut_key:
                ctrl_key = "wire_general_ble_output"
            elif any(param in dut_key for param in params):
                ctrl_key = re.sub(r"_uid\d", "", dut_key)
            # if "uid1" in dut_key:
            #     ctrl_key = dut_key.replace("uid1","uid3") # Comparing L4 -> L16 Mux w/ L16 -> L16
            else:
                # If comparing exact same keys between runs we can set them to be the same 
                ctrl_key = dut_key

            # Make sure we compare the same timestep & iter keys have been set
            for iter_key, debug_iter_key in zip(iter_keys, debug_iter_keys):
                try:
                    assert cur_iter_book.get(iter_key.lower()) == ctrl_dicts[j].get(debug_iter_key), f"Error, attempting to compare mismatching timesteps: {cur_iter_book.get(iter_key.lower())} != {ctrl_dicts[j].get(debug_iter_key)}"
                    assert cur_iter_book.get(iter_key.lower()) == dut_dicts[i].get(debug_iter_key), f"Error, attempting to compare mismatching timesteps: {cur_iter_book.get(iter_key.lower())} != {dut_dicts[i].get(debug_iter_key)}"
                except AssertionError as e:
                    print(e)
                    print(f"Assertion Error: CTRL: {ctrl_dir}, DUT: {dut_dir}, in_file: {in_file}")
                    # i += 1
                    # j += 1 # Works if the CTRL is behind the DUT?
                    return
            # Set values for this comparison row
            try:
                ctrl_val = ctrl_dicts[j][ctrl_key]
                dut_val = dut_dicts[i][dut_key]
            except:
                print(f"Error, could not find key {ctrl_key} in {ctrl_fpath} or {dut_key} in {dut_fpath}")
                print(f"CTRL {ctrl_dicts[j].keys()}")
                print(f"DUT {dut_dicts[i].keys()}")
                continue
                
            try:
                perc_diff = round(
                    (100 * (float(dut_val) - float(ctrl_val)) / float(ctrl_val)),
                    3
                )
            except:
                perc_diff = "N/A"
            cur_iter_ids = ''.join([
                f"{cur_iter_book['area']:<{idx_col_spacing}}", 
                f"{cur_iter_book['wire']:<{idx_col_spacing}}",
                f"{cur_iter_book['delay']:<{idx_col_spacing}}",
                f"{cur_iter_book['compute_dist']:<{idx_col_spacing}}"
            ])
            print(f"{cur_iter_ids}\
                {ctrl_key:<{out_col_spacing}}{ctrl_val:<{out_col_spacing}}{dut_key:<{out_col_spacing}}{dut_val:<{out_col_spacing}}{perc_diff:<{idx_col_spacing}}",file=fd)
            # print(f"{cur_iter_ids}\
            #     {ctrl_key:<{out_col_spacing}}{ctrl_val:<{out_col_spacing}}{dut_key:<{out_col_spacing}}{dut_val:<{out_col_spacing}}{perc_diff:<{idx_col_spacing}}")
        i += 1
        j += 1

    fd.close()

def cmp_dut_ctrl_coffe_runs(cmp_inputs: List[Dict[str, str]]):
    # TAKES DUT AND CTRL COFFE OUTPUT DIRECTORIES AND CREATES LOG FILES COMPARING KEYS FOR EACH CATAGORY
    # Compare each of the {area/delay/tx_sizes/wire_length}_debug.csv files in the control & test directories at each timestep
    debug_csv_file_strs = ["area","tx_size","wire_length", "delay"]

    # Check to make sure the output csvs exist in the control and test directories
    for cmp_input in cmp_inputs:
        ctrl_dir = cmp_input["ctrl"]
        dut_dir = cmp_input["dut"]
        for dpath in [ctrl_dir, dut_dir]:
            for cat in debug_csv_file_strs:
                csv_fpath = os.path.join(dpath, f"{cat}_debug.csv") # Fine grained debug information
                csv_fpath = os.path.join(dpath, f"{cat}.csv") # Coarse grained debug information
                assert os.path.exists(csv_fpath), f"Error, {csv_fpath} does not exist in {dpath}"

    starmap_inputs = [
            (debug_str, cmp_input["ctrl"], cmp_input["dut"], cmp_input["out"]) 
                for debug_str in debug_csv_file_strs
                     for cmp_input in cmp_inputs
    ]
    with mp.Pool(mp.cpu_count()) as p:
        # Map the function to the list of debug strings and pass additional arguments using `starmap`
        p.starmap(
            # gen_cmp_info_from_debug_csvs, starmap_inputs
            gen_cmp_info_from_coarse_csvs, starmap_inputs
        )
        



def cmp_sp_subckt():
    # Think this is currently set for comparing the runs of sb_mux but could be adapted for other subckts

    run_ctrl = 1
    run_test = 1

    if run_ctrl:
        sp_process = rg_ds.SpProcess(
            title = "sb_mux",
            top_sp_dir = "/fs1/eecg/vaughn/morestep/Documents/rad_gen/unit_tests/outputs/coffe/finfet_7nm_fabric_w_hbs/arch_out_COFFE_CONTROL",
        )

        ctrl_gen_params: Dict[str, List[Dict[int, float]]] = {}

        _, _, ctrl_gen_params = ic_3d.run_spice_debug(sp_process)


    # Sp Process for TEST SB_MUX
    if run_test:

        sp_process = rg_ds.SpProcess(
            title = "sb_mux_uid0",
            top_sp_dir = "/fs1/eecg/vaughn/morestep/Documents/rad_gen/unit_tests/outputs/coffe/finfet_7nm_fabric_w_hbs/arch_out_dir_multi_L_test",
        ) 

        dut_gen_params: Dict[str, List[Dict[int, float]]] = {}
        _, _, dut_gen_params = ic_3d.run_spice_debug(sp_process)


    mux_load_keys = [
        "cb(?:.*?)_load_on", "cb(?:.*?)_load_partial", "cb(?:.*?)_load_off",
        "sb(?:.*?)_load_on", "sb(?:.*?)_load_partial", "sb(?:.*?)_load_off"
    ]
    mux_keys = ["sb_mux", "cb_mux"]
    level_keys = ["l1", "l2"]
    pn_keys = ["pmos", "nmos"]
    rc_keys = ["res", "cap"]


    # mux_wire_load_keys: List[str] = [
    #     f"wire_{mux_load_key}(?:.*?)_{rc_keys}" for mux_load_key in mux_load_keys
    # ]
    mux_wire_load_keys: List[str] = [
        "wire_sb_load_on_res",
        "wire_sb_load_on_cap",
        "wire_sb_load_partial_res",
        "wire_sb_load_partial_cap",
        "wire_sb_load_off_res",
        "wire_sb_load_off_cap",
        "wire_cb_load_on_res",
        "wire_cb_load_on_cap",
        "wire_cb_load_partial_res",
        "wire_cb_load_partial_cap",
        "wire_cb_load_off_res",
        "wire_cb_load_off_cap",
    ]


    mux_wire_keys: List[str] = [
        f"wire_{mux_key}(?:.*?)_{level_key}_{rc_key}" for mux_key in mux_keys 
            for level_key in level_keys + ["driver"] for rc_key in rc_keys
    ]

    # Currently putting param string after module names ie put non capture lazy wildcard after mux_name & before
    tx_size_keys: List[str] = [
        f"{tx_key}_{mux_key}(?:.*?)_{level_key}_{pn_key}" for tx_key in ["tgate", "ptran"]
            for mux_key in mux_keys for level_key in level_keys for pn_key in pn_keys
    ] + [
        f"inv_{mux_key}(?:.*?)_{idx}_{pn_key}"
        for mux_key in mux_keys for idx in range(1, 3) for pn_key in pn_keys
    ]

    gen_routing_wire_keys: List[str] = [
        f"wire_gen_routing(?:.*?)_{rc_key}" for rc_key in rc_keys
    ]

    param_res = [ re.compile(key) for key in mux_wire_keys + tx_size_keys + gen_routing_wire_keys + mux_wire_load_keys]

    # Compare subckt specific components with one another
    print(f"{'CTRL_KEY':<30}{'CTRL_VAL':<30}{'DUT_KEY':<30}{'DUT_VAL':<30}{'%_DIFF':<20}")
    for param_re in param_res:
        for ctrl_key in ctrl_gen_params.keys():
            for dut_key in dut_gen_params.keys():
                # This means we will print a table comparing the values side by side
                if param_re.search(ctrl_key) and param_re.search(dut_key):
                    if len(ctrl_gen_params[ctrl_key]) == 1 and len(dut_gen_params[dut_key]) == 1:
                        perc = round(abs(float(ctrl_gen_params[ctrl_key][0]['0']) - float(dut_gen_params[dut_key][0]['0']))/float(ctrl_gen_params[ctrl_key][0]['0']))
                        print(f"{ctrl_key:<30}{ctrl_gen_params[ctrl_key][0]['0']:<30}{dut_key:<30}{dut_gen_params[dut_key][0]['0']:<30}{perc:<20}")

    print(f"{'DUT KEY':<50}{'DUT VAL':<30}")
    for dut_key in dut_gen_params.keys():
        for param_re in param_res:
            if len(dut_gen_params[dut_key]) == 1 and param_re.search(dut_key):
                print(f"{dut_key:<50}{dut_gen_params[dut_key][0]['0']:<30}")






def key_cmp(log_dpath: str, cat: str, cmp: Dict[str, Any]):
    cmp_dpath = os.path.join(log_dpath, "key_cmps")
    os.makedirs(cmp_dpath, exist_ok=True)
    print_col_width = 40
    # If the cmp is relevant to current catagory
    if cmp.get("cats") and cat in cmp.get("cats"):
        ctrl_cmp_key = cmp.get("ctrl")
        dut_cmp_key = cmp.get("dut")

        out_csv_rows: List[Dict[str, Any]] = []
        cmp_outlog = os.path.join(cmp_dpath, cat, f"{ctrl_cmp_key}_vs_{dut_cmp_key}_cmp.log")
        fd = open(cmp_outlog, "w")
        split_dir = os.path.join(log_dpath, f"{cat}_splits")

        # print(f"{'ITER_IDX':<{print_col_width}}{'CTRL_KEY':<{print_col_width}}{'CTRL_VAL':<{print_col_width}}{'DUT_KEY':<{print_col_width}}{'DUT_VAL':<{print_col_width}}{'%_DIFF':<{print_col_width}}")
        print(f"{'ITER_IDX':<{print_col_width}}{'CTRL_KEY':<{print_col_width}}{'CTRL_VAL':<{print_col_width}}{'DUT_KEY':<{print_col_width}}{'DUT_VAL':<{print_col_width}}{'%_DIFF':<{print_col_width}}", file=fd)
        prev_row: Dict[str, Any] = None
        sorted_csvs = sorted(os.listdir(split_dir))
        for i, csv_file in enumerate(sorted_csvs):
            csv_fpath: str = os.path.join(split_dir, csv_file)
            cat_dicts: list = rg_utils.read_csv_to_list(csv_fpath)
            row: Dict[str, Any]
            any_change: bool = True
            for j, row in enumerate(cat_dicts):
                out_row: Dict[str, Any] = {}
                # Too many outputs so we should prune them to only be values that change

                ctrl_key = row.get("CTRL_KEY")
                ctrl_val = row.get("CTRL_VAL")
                dut_key = row.get("DUT_KEY")
                dut_val = row.get("DUT_VAL")
                diff = row.get("%_DIFF")

                iter_idx = sum([ int(idx) for idx in [row.get("AREA_IDX"), row.get("WIRE_IDX"), row.get("DELAY_IDX"), row.get("COMPUTE_DIST_IDX")] ])
                
                # Area specific keys
                if cat == "area" or cat == "delay":
                    # We want to track a specific pair of keys
                    if dut_cmp_key == dut_key and ctrl_cmp_key == ctrl_key:
                        if prev_row and any(prev_row[key] != row[key] for key in ["CTRL_VAL", "DUT_VAL", "%_DIFF"]):
                            # for key in ["CTRL VAL", "DUT VAL", "% DIFF"]:
                            #     if key in prev_row and row[key] != prev_row[key]:
                            #         print(f"{key} has changed from {prev_row[key]} to {row[key]}", end = "     ")
                            any_change = True
                        else:
                            any_change = False
                        if any_change or not prev_row:
                            # print(f"{iter_idx:<{print_col_width}}{ctrl_key:<{print_col_width}}{ctrl_val:<{print_col_width}}{dut_key:<{print_col_width}}{dut_val:<{print_col_width}}{diff:<{print_col_width}}")
                            out_row["ITER_IDX"] = iter_idx
                            out_row["CTRL_KEY"] = ctrl_key
                            out_row["CTRL_VAL"] = ctrl_val
                            out_row["DUT_KEY"] = dut_key
                            out_row["DUT_VAL"] = dut_val
                            out_row["%_DIFF"] = diff
                            out_csv_rows.append(out_row)
                            print(f"{iter_idx:<{print_col_width}}{ctrl_key:<{print_col_width}}{ctrl_val:<{print_col_width}}{dut_key:<{print_col_width}}{dut_val:<{print_col_width}}{diff:<{print_col_width}}", file = fd)

                        # Update previous row only if its a valid row of our DUT subckt & DUT key 
                        prev_row = row
                # Wire length specific keys
                # elif cat == "wire_length":
                #     # Lets try and only focus on a single key per catagory and we can see how they change
                #     if any([ param == dut_key for param in dut_wire_params ]):
                #     # if dut_key == dut_wire_params[0]:
                #         print(f"{iter_idx:<{print_col_width}}{dut_val:<{print_col_width}}")
                # # Delay specific keys
                # elif cat == "tx_sizes":
                #     if any([ param == dut_key for param in dut_tx_sz_params ]):
                #         print(f"{iter_idx:<{print_col_width}}{dut_val:<{print_col_width}}")

                # time.sleep(1)
        fd.close()
        # Write to CSV as well as log
        rg_utils.write_dict_to_csv(out_csv_rows, os.path.join(cmp_dpath, cat, f"{ctrl_cmp_key}_vs_{dut_cmp_key}_cmp"))


def cmp_key_pairs(log_dpath: str):
    # Log file strs
    # log_file_strs = ["area","tx_size","wire_length", "delay"]
    # for file in log_file_strs:
    #     log_fpath = os.path.join(log_dpath, f"{file}.log")
    #     assert os.path.exists(log_fpath), f"Error, {log_fpath} does not exist"
    cmp_dpath = os.path.join(log_dpath, "key_cmps")
    os.makedirs(cmp_dpath, exist_ok=True)

    sb_cmps = [
        {
        
            "ctrl": "sb_mux",
            "dut": f"sb_mux_uid{i}",
            "cats": ["delay", "area"],
        } for i in range(4)
    ]

    cmps = [
        {
            "ctrl": "tile",
            "dut": "tile",
            "cats": ["area"],
        },
        {
            "ctrl": "rep_crit_path",
            "dut": "rep_crit_path",
            "cats": ["delay"],
        },
        *sb_cmps,
    ]


    # Look through our directories of split up csv files and sort them by type of subckt & iteration
    ctrl_cmp_key = "rep_crit_path" #"sb_mux"
    dut_cmp_key = "rep_crit_path" #"sb_mux_uid0"
    num_sb_muxes = [f"{i+1}" for i in range(4)]


    mux_lvls = ["L1", "L2"]
    fet_type = ["pmos", "nmos"]
    # These are the number of unique muxes in the subckt
    # Used for keys in tx_size.log

    # dut_tx_sz_params = [
    #     f"tgate_{dut_subckt}_{mux_lvl}_{pn}"
    #     for mux_lvl in mux_lvls
    #         for pn in fet_type
    # ]
    # # Used for keys in wire_length.log
    # dut_wire_params = [
    #     f"wire_{dut_subckt}_{mux_lvl}"
    #     for mux_lvl in mux_lvls
    # ]
    # dut_wire_params += [
    #     f"wire_{dut_subckt}_driver"
    # ]

    # For area we use the name of our dut_subckt
    catagories = ["area", "delay"]   #, "tx_size", "wire_length"]
    for cat in catagories:
        os.makedirs(os.path.join(cmp_dpath, cat), exist_ok=True)
        with mp.Pool(mp.cpu_count()) as p:
            # Map the function to the list of debug strings and pass additional arguments using `starmap`
            p.starmap(key_cmp, [(log_dpath, cat, cmp) for cmp in cmps])
        # for cmp in cmps:
            # key_cmp(log_dpath, cat, cmp)

# To get from log to csv files use this command
#   sed -E 's/ {2,}/,/g; s/, *\n/\n/g' < log_file.log > log_file.csv
                
# To split up csv files into smaller ones use this command
# ./split_csv.sh unity_verif/area_verif.csv unity_verif/area_splits 20

def main():
    rad_gen_home = os.path.expanduser("~/Documents/rad_gen")
    coffe_unit_test_outputs = os.path.join(
        rad_gen_home,
        "unit_tests/outputs/coffe/finfet_7nm_fabric_w_hbs"
    )
    ctrl_outdir = os.path.join(
        coffe_unit_test_outputs,
        "arch_out_COFFE_CONTROL_NEW_DEBUG_4_iters"
    )
    dut_outdir = os.path.join(
        coffe_unit_test_outputs,
        "arch_out_dir_multi_L_test_v2"
    )
    # This is where our area_debug.log, ... files are
    sandbox_dir = os.path.join(
        rad_gen_home,
        "unit_tests/sandbox/unity_verif"
    )
    # Control + Test outdir pairs
    cmp_inputs = [
        {
            "ctrl": ctrl_outdir, # L4
            "dut": dut_outdir, # L4
            "out": "unity_l4",
        },
        # {
        #     "ctrl": os.path.join(coffe_unit_test_outputs, "arch_out_COFFE_CONTROL_L16"),
        #     "dut": os.path.join(coffe_unit_test_outputs, "arch_out_dir_FPT_L16_only"),
        #     "out": "unity_l16"
        # },
        # {
        #     "ctrl": ctrl_outdir,
        #     "dut": os.path.join(coffe_unit_test_outputs, "arch_out_dir_FPT23_v2"),
        #     "out": "l4_vs_fpt23"
        # },
        # {
        #     "ctrl": os.path.join(coffe_unit_test_outputs, "arch_out_dir_FPT23"),
        #     "dut": os.path.join(coffe_unit_test_outputs,  "arch_out_dir_FPT23_full_conn"),
        #     "out": "fpt_semi_conn_vs_full_conn"
        # }
    ]


    # Outputs log files comparing keys from control and tests
    cmp_dut_ctrl_coffe_runs(cmp_inputs)

    # After running log 2 csv and csv splitter scripts we can call this function to compare specific keys
    # cmp_key_pairs("unity_l4")
    

                    
        








if __name__ == "__main__":
    main()





