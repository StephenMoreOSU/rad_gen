
# General imports
from typing import List, Dict, Tuple, Set, Union, Any, Type
import os, sys
from dataclasses import dataclass, asdict
import datetime
import yaml
import re
import subprocess as sp
from pathlib import Path
import json
import copy
import math
import pandas as pd
import csv
import random


import plotly.subplots as subplots
import plotly.graph_objects as go
import plotly.subplots as subplots
import plotly.express as px


# rad gen utils imports
import src.common.utils as rg_utils
import src.common.data_structs as rg_ds


# ic 3d imports
import src.ic_3d.buffer_dse as buff_dse
import src.ic_3d.pdn_modeling as pdn




def run_buffer_sens_study(ic_3d_info: rg_ds.Ic3d):
    """
        This function performs a sensitivity study using the various parameters which can affect buffer delay
        It doesn't perform optimization of the P N sizes, just uses a heuristically determined sizing (7/5) which makes decent sense in 7nm finfet
        It sweeps the following parameters:
            - ubump pitch
            - top metal layer distance -> this is the distance traveled after the first inverter chain, before passing b/w dies
            - via factor -> this is the factor by which the via pitch is multiplied, so if the via pitch is 1um and the via factor is 2, the via pitch is 2um
    """
    output_csv = "sens_study_out.csv"

    # initializations of basic assumptions TODO some of these should be moved to the user level
    ic_3d_info.design_info.shape_nstages = 1
    ic_3d_info.design_info.sink_die_nstages = 1
    ic_3d_info.design_info.dut_buffer_nstages = 2
    
    for process_info in ic_3d_info.process_infos:
        ic_3d_info.design_info.process_info = process_info
        for ubump_info in ic_3d_info.ubump_infos:
            ic_3d_info.design_info.package_info = rg_ds.PackageInfo( 
                ubump_info=ubump_info,
                esd_rc_params=ic_3d_info.esd_rc_params,
            )
            # Setup Simulation For Sensitivity Analysis of Process and Ubump
            ic_3d_info.design_info = buff_dse.spice_simulation_setup(ic_3d_info)
            # Sweep ranges for sensitivity
            sens_sweep_vals = [i+1 for i in range(10)]
            # Setup Buffer Parameters
            buffer_params = {
                "num_stages" : 2,
                "stage_ratio": 2,
                "pn_ratios": [] # 1 value for each stage + 1 for shape + 1 for final stage
            }
            # These values can be parameters (strings) or integer values
            buffer_params["pn_ratios"] = [
                {
                    "wp": 7,
                    "wn": 5,
                } for _ in range(ic_3d_info.design_info.shape_nstages + ic_3d_info.design_info.dut_buffer_nstages + ic_3d_info.design_info.sink_die_nstages)
            ]
            sim_params = {
                "period": 20 # ns
            }
            process_package_params = {
                "buffer_params" : buffer_params,
                "sim_params" : sim_params,
            }
            ######################## dict to store results ########################
            delay_results = []
            max_macro_dist = max(rg_utils.flatten_mixed_list([[sram.width/2 + sram.height/2] for sram in ic_3d_info.design_info.srams]))

            for ubump_fac in sens_sweep_vals:
                result_dict = buff_dse.sens_study_run(ic_3d_info, process_package_params, metal_dist = max_macro_dist, mlayer_idx = -1, via_fac = 1, ubump_fac = ubump_fac)
                result_dict["ubump_pitch"] = ubump_info.pitch
                delay_results.append(result_dict)
                
                with open(output_csv, "a", newline="") as csvfile:
                    writer = csv.DictWriter(csvfile, fieldnames=delay_results[0].keys())
                    if ubump_fac == 1:
                        writer.writeheader()
                    writer.writerow(result_dict)
            for via_fac in sens_sweep_vals:
                result_dict = buff_dse.sens_study_run(ic_3d_info, process_package_params, metal_dist = max_macro_dist, mlayer_idx = -1, via_fac = via_fac, ubump_fac = 1)
                result_dict["ubump_pitch"] = ubump_info.pitch
                delay_results.append(result_dict)
                with open(output_csv, "a", newline="") as csvfile:
                    writer = csv.DictWriter(csvfile, fieldnames=delay_results[0].keys())
                    writer.writerow(result_dict)
            for metal_dist in sens_sweep_vals:
                for mlayer_idx in range(len(ic_3d_info.design_info.process_info.mlayers)):
                    result_dict = buff_dse.sens_study_run(ic_3d_info, process_package_params, metal_dist = metal_dist * max_macro_dist, mlayer_idx = mlayer_idx, via_fac = 1, ubump_fac = 1)
                    result_dict["ubump_pitch"] = ubump_info.pitch
                    delay_results.append(result_dict)
                    with open(output_csv, "a", newline="") as csvfile:
                        writer = csv.DictWriter(csvfile, fieldnames=delay_results[0].keys())
                        writer.writerow(result_dict)

            res_df = pd.DataFrame(delay_results)
            fig = px.line(
                res_df, 
                x="mlayer_dist",
                y="max_total_delay",
                color="mlayer_idx",
                markers=True,
            )
            fig.write_image(f"ubump_pitch_{ic_3d_info.design_info.package_info.ubump_info.pitch}_mlayer_sens_study.png")
            fig = px.line(
                res_df,
                x="via_factor",
                y="max_total_delay",
                markers=True,
            )
            fig.write_image(f"ubump_pitch_{ic_3d_info.design_info.package_info.ubump_info.pitch}_via_factor_sens_study.png")
            fig = px.line(
                res_df,
                x="ubump_factor",
                y="max_total_delay",
                markers=True,
            )
            fig.write_image(f"ubump_pitch_{ic_3d_info.design_info.package_info.ubump_info.pitch}_via_factor_sens_study.png")
            # fig.show()

def run_buffer_dse_updated(ic_3d_info: rg_ds.Ic3d):
    """
        This function is a work in progress to update the buffer dse to use the new data structures and be generally more reusable, almost done but there's copies of all the other functions in case I break stuff
    """
    # initializations of basic assumptions TODO some of these should be moved to the user level
    ic_3d_info.design_info.shape_nstages = 1
    ic_3d_info.design_info.sink_die_nstages = 1

    # Tx sizing params
    ic_3d_info.tx_sizing.opt_goal = "diff"
    ic_3d_info.tx_sizing.nmos_sz = 1
    ic_3d_info.tx_sizing.pmos_sz = 2
    ic_3d_info.tx_sizing.p_opt_params = {
        "init": 2,
        "range": [1, 16],
        "step": 1,
    }
    ic_3d_info.tx_sizing.n_opt_params = {
        "init": 1,
        "range": [1, 16],
        "step": 1,
    }
    ic_3d_info.tx_sizing.iters = 25


    # Either way the P & N params will be stored as opt params which lets them be represented
    parse_flags = {
        "voltage": True,
        "delay": True,
    }
    show_flags = {
        "voltage": False,
        "delay": False,
    }
    

    # make the dir structure
    sp.run(["mkdir", "-p", f"{ic_3d_info.spice_info.subckt_lib_dir}"])
    sp.run(["mkdir", "-p", f"{ic_3d_info.spice_info.includes_dir}"])

    csv_headers_written = False
    for process_info in ic_3d_info.process_infos:
        ####################### INIT DATA STRUCTS #######################
        ic_3d_info.design_info.process_info = process_info
        ####################### BUFFER DOMAIN SPACE EXPLORATION #######################
        # Written from the tech_info struct out to spice files
        # Maybe we can get rid of tech_info ? Lets try
        for ubump_info in ic_3d_info.ubump_infos:
            
            ic_3d_info.design_info.package_info = rg_ds.PackageInfo( 
                ubump_info=ubump_info,
                esd_rc_params=ic_3d_info.esd_rc_params,
            )

            # This function initializes subcircuits / libraries and writes out to spice files
            ic_3d_info.design_info = buff_dse.spice_simulation_setup(ic_3d_info)

            # Initial guess of target frequency for the inverter chain
            init_tfreq = 1000
            # final_report_rows = []
            # final_fig = subplots.make_subplots(cols = len(ic_3d_info.stage_range), rows=1)
            # cur_best_cost = sys.float_info.max 
            # best_sp_run = None

            # TODO instead of looping over specific values, look for all values specified bty users and sweep over those
            for add_wlen in ic_3d_info.add_wlens:
                for n_stages in ic_3d_info.stage_range:
                    ic_3d_info.design_info.dut_buffer_nstages = n_stages
                    # Init the parameters for this size of buffer chain
                    ic_3d_info.design_info.total_nstages = ic_3d_info.design_info.shape_nstages + ic_3d_info.design_info.dut_buffer_nstages + ic_3d_info.design_info.sink_die_nstages

                    # fanout_sweep_fig = go.Figure()
                    for buff_fanout in ic_3d_info.fanout_range:
                        # final_report_row = {}
                        sweep_params = {
                            # sim params
                            "target_freq": init_tfreq,
                            # buffer params
                            "add_wlen": add_wlen, # wire length added to the top metal layers of each die
                            "n_stages": n_stages,
                            "stage_ratio": buff_fanout,
                            # package params
                            "ubump_info": ubump_info,
                            # process params
                            "process_info" : process_info,
                        }
                        ### OPT PN SIZES BEFORE RUNNING SIM ###
                        cur_tfreq = init_tfreq
                        sim_iters = 0
                        inv_sizes = []
                        while True:
                            # print(f"Running sim for {n_stages} stages, {buff_fanout} fanout, {cur_tfreq} target freq")
                            pn_opt_process = buff_dse.write_sp_buffer_updated(ic_3d_info, sweep_params, "pn-opt")
                            buff_dse.run_spice(sp_process = pn_opt_process)
                            # Measurements inputted in spice file are also our determination of simulation success, there should be no failed measurements
                            plot_df, measurements, opt_params, _ = buff_dse.parse_spice(ic_3d_info.res, sp_process = pn_opt_process)
                            # We probably don't want to plot the voltage waveforms for every run but if we did one would do it here
                            # Check to make sure all measurements are captured AND they all have non "failed" values
                            if any( [m["val"] == "failed" for m in measurements] ):
                                # IF we get failed measurements, it may have been due to clock frequency being too fast for this load RC, so we try it again with half the clk freq
                                cur_tfreq /= 2
                                sweep_params["target_freq"] = cur_tfreq
                                print(f"Delay measure statements not captured, trying again with reduced target frequency {cur_tfreq}")
                            else:
                                # Lets capture the optimized pn sizes and other information from measurements
                                for opt_param in opt_params:
                                    inv_size = {}
                                    name = opt_param["name"]
                                    # convert to int as we are using finfets
                                    val = int(float(opt_param["val"]))
                                    # Make sure the result is actually an int in the first place
                                    assert int(float(opt_param["val"])) == float(opt_param["val"]), f"Finfet Width {name} is not an integer, got {opt_param['val']}, check your HSpice optimization settings"
                                    # we assume that wn & wp are somewhere in the optimization params
                                    if "wn" in name:
                                        inv_size["wn"] = val
                                    elif "wp" in name:
                                        inv_size["wp"] = val
                                    else:
                                        raise ValueError(f"Optimization parameter {name} not recognized")
                                    # if the user defined a particular inv to be static we will use that value 
                                    if "wn" not in inv_size.keys() and "N" not in ic_3d_info.tx_sizing.opt_mode:
                                        inv_size["wn"] = ic_3d_info.tx_sizing.nmos_sz
                                    if "wp" not in inv_size.keys() and "P" not in ic_3d_info.tx_sizing.opt_mode:
                                        inv_size["wn"] = ic_3d_info.tx_sizing.pmos_sz
                                    assert ("wn" in inv_size.keys() and "wp" in inv_size.keys() and len(inv_size.keys()) == 2), f"inv_size dict keys are malformed, got {inv_size.keys()}"
                                    inv_sizes.append(inv_size)
                                # if all measurements are there we can break out of loop
                                break 

                            if sim_iters > 15:
                                print(f"Failed to get delay measure statements after {sim_iters} iterations")
                                print(f"Opening Voltage vs Time plot for debugging...")
                                buff_dse.plot_time_vs_voltage(ic_3d_info.sp_sim_settings, plot_df)
                                for l in rg_utils.get_df_output_lines(pd.DataFrame(measurements)):
                                    print(l)
                                print("Exiting...")
                                sys.exit(1)

                            sim_iters += 1                                    

                        # TODO come back to this to get delay plots working again
                        # buff_dse.plot_sp_run(ic_3d_info, show_flags, sp_run_info, sp_run_df)

                        # Write the simulation with the optimized pn sizes found above, this is just to prevent weirdness between hspice opt commands and our results
                        sized_buffer_process = buff_dse.write_sp_buffer_updated(ic_3d_info, sweep_params, "sized", inv_sizes)
                        buff_dse.run_spice(sp_process = sized_buffer_process)
                        plot_df, measurements, _, _ = buff_dse.parse_spice(ic_3d_info.res, sp_process = sized_buffer_process)
                        
                        ####################### CREATE CIRCUIT ITERATION INFO #######################
                        # Store all measurements not found in key substrs into a dict
                        circuit_info = {}
                        # Create invs info list, this is a list of attributes for each inverter in the chain
                        inv_infos = [{} for _ in range(ic_3d_info.design_info.total_nstages)]
                        # Go through measurements dict and populate invs_info with relevant keys
                        # TODO remove hardcoding of these strings
                        neg_circuit_info_key_substrs = ["best_ratio", "falling_prop_delay", "rising_prop_delay", "tpd", "diff"]
                        inv_info_key_substrs = ["rising_prop_delay", "falling_prop_delay", "max_prop_delay", "t_rise", "t_fall"]
                        inv_idx = 0
                        for meas in measurements:
                            if any(f"{key_substr}_{inv_idx}" == meas["name"] for key_substr in inv_info_key_substrs):
                                # Assumes not more than 1 key substr in a measurement name
                                key = [key_substr for key_substr in inv_info_key_substrs if key_substr in meas["name"]][0]
                                inv_infos[inv_idx][key] = float(meas["val"])                                
                                # increment inverter we are saving data into once we get a copy of each key
                                if len(inv_infos[inv_idx].keys()) == len(inv_info_key_substrs):
                                    inv_idx += 1
                            else:
                                # TODO remove this hardcoding
                                # This is just to not include the best ratios in circuit info, they should really be in inv_infos but dont want to break plotting
                                if not any(key_substr in meas["name"] for key_substr in neg_circuit_info_key_substrs):
                                    circuit_info[meas["name"]] = float(meas["val"])
                        
                        #    _   ___ ___   _      ___   _   _    ___ 
                        #   /_\ | _ \ __| /_\    / __| /_\ | |  / __|
                        #  / _ \|   / _| / _ \  | (__ / _ \| |_| (__ 
                        # /_/ \_\_|_\___/_/ \_\  \___/_/ \_\____\___|
                        inv_areas = []
                        for i, inv_size in enumerate(inv_sizes):
                            # Calculate the multiplier for the stage ratio of each stage, we reset the stage ratio back to 1 after the last stage of driver buffer, these are the sizes for inverters on the sink die
                            inv_mult_factor = sweep_params["stage_ratio"] ** i if i < ic_3d_info.design_info.total_nstages - ic_3d_info.design_info.sink_die_nstages else buff_fanout ** (i - (ic_3d_info.design_info.total_nstages - ic_3d_info.design_info.sink_die_nstages) )
                            # multiply the fanout factor by the width of the n/pmos tx 
                            nfet_numfins = int(float(inv_size["wn"]) * inv_mult_factor)
                            pfet_numfins = int(float(inv_size["wp"]) * inv_mult_factor)
                            # area of a specific inverter uses f(nfet) + f(pfet) * min_tx_area
                            # min_width_tx_area is in nm^2 so we need to convert to um^2 -> 1e-6 
                            # TODO <TAG> <CONVERT CLEANUP>
                            inv_area = (buff_dse.finfet_tx_area_model(nfet_numfins) + buff_dse.finfet_tx_area_model(pfet_numfins))*(ic_3d_info.design_info.process_info.tx_geom_info.min_width_tx_area*1e-6)
                            inv_areas.append(inv_area)
                            # update inv_infos w/ area info
                            inv_infos[i]["area"] = round(inv_area, 6)
                             # update inv_infos w/ P/N sizes and inv_idx
                            inv_infos[i]["Wp"] = inv_size['wp']
                            inv_infos[i]["Wn"] = inv_size['wn']
                            inv_infos[i]["inv_idx"] = i
                            # Add buffer chain related info (duplication of whats in circuit_info) useful for sorting later
                            inv_infos[i]["n_stages"] = sweep_params["n_stages"]
                            inv_infos[i]["stage_ratio"] = sweep_params["stage_ratio"]
                            inv_infos[i]["add_wlen"] = sweep_params["add_wlen"]
                            inv_infos[i]["ubump_pitch"] = sweep_params["ubump_info"].pitch
                            inv_infos[i]["process"] = sweep_params["process_info"].name

                        
                        # Select only the inverters which we want to evaluate results for (i.e. not the shape inverters) as we include sink inverters in model
                        meas_invs = inv_infos[ic_3d_info.design_info.shape_nstages:len(inv_infos)]
                        circuit_info["area"] = round(sum( [ inv["area"] for inv in meas_invs] ), 6)                        
                        circuit_info["cost"] = round(buff_dse.calc_cost_updated(ic_3d_info.design_info, ic_3d_info.cost_fx_exps, circuit_info), 6)         
                        # convert circuit_info to a report format
                        # circuit_report = {}
                        # for key, val in circuit_info.items():
                        #     if 
                        # Create a df for printout of the sweep parameters used in this run
                        sweep_param_report = {}
                        for key, val in sweep_params.items():
                            ret_key, ret_val = rg_utils.key_val_2_report(key, val)
                            sweep_param_report[ret_key] = ret_val 

                        # vertically concat dfs for reporting
                        sw_iter_report_df = pd.concat([ 
                            pd.DataFrame(sweep_param_report, index=[0]),
                            pd.DataFrame(circuit_info, index=[0]),    
                        ], axis=1)

                        invs_df = pd.DataFrame(inv_infos)
                        
                        # buff_dse.unit_conversion(ic_3d_info.sp_sim_settings.unit_lookup_factors["time"], x, ic_3d_info.sp_sim_settings.abs_unit_lookups, sig_figs = 5)
                        sw_iter_report_lines = rg_utils.get_df_output_lines(sw_iter_report_df)
                        for lines in rg_utils.create_bordered_str("Circuit Sweep Iteration Information") + sw_iter_report_lines:
                            print(lines)
                        
                        inv_report_lines = rg_utils.get_df_output_lines(invs_df)
                        for lines in rg_utils.create_bordered_str("Buffer Chain Inverter Information") + inv_report_lines:
                            print(lines)

                        # Output to csv
                        report_output = "ic_3d_reports"
                        os.makedirs(report_output, exist_ok=True)
                        if not csv_headers_written:
                            with open(f"{report_output}/buffer_summary_report.csv", "w", newline="") as csvfile:
                                writer = csv.DictWriter(csvfile, fieldnames=sw_iter_report_df.columns)
                                writer.writeheader()
                            with open(f"{report_output}/buffer_inv_report.csv", "w", newline="") as csvfile:
                                writer = csv.DictWriter(csvfile, fieldnames=invs_df.columns)
                                writer.writeheader()
                            csv_headers_written = True
                        
                        sw_iter_report_df.to_csv(os.path.join(report_output, f"buffer_summary_report.csv"), mode = "a", header=False, index=False)
                        invs_df.to_csv(os.path.join(report_output, f"buffer_inv_report.csv"), mode = "a", header=False, index=False)
                        

                        
                        


                        
                    
                

                            
                            


def run_buffer_dse(ic_3d_info: rg_ds.Ic3d):

    # make the dir structure
    sp.run(["mkdir", "-p", f"{ic_3d_info.spice_info.subckt_lib_dir}"])
    sp.run(["mkdir", "-p", f"{ic_3d_info.spice_info.includes_dir}"])

    for process_info in ic_3d_info.process_infos:
        ####################### INIT DATA STRUCTS #######################
        ic_3d_info.design_info.process_info = process_info
        ####################### BUFFER DOMAIN SPACE EXPLORATION #######################
        # Written from the tech_info struct out to spice files
        # Maybe we can get rid of tech_info ? Lets try
        for ubump_info in ic_3d_info.ubump_infos:
            
            ic_3d_info.design_info.package_info = rg_ds.PackageInfo( 
                ubump_info=ubump_info,
                esd_rc_params=ic_3d_info.esd_rc_params,
            )

            # This function initializes subcircuits / libraries and writes out to spice files
            ic_3d_info.design_info = buff_dse.spice_simulation_setup(ic_3d_info)

            # Initial guess of target frequency for the inverter chain
            target_freq = 1000
            final_df_rows = []
            final_fig = subplots.make_subplots(cols = len(ic_3d_info.stage_range), rows=1)
            cur_best_cost = sys.float_info.max 
            best_sp_run = None

            for add_wlen in ic_3d_info.add_wlens:
                for stage_idx, n_stages in enumerate(ic_3d_info.stage_range):
                    # shape invterer + num driver stages + num stages in opposite die catching signal
                    total_nstages = 1 + n_stages + ic_3d_info.design_info.bot_die_nstages
                    # if n_stages % 2 != 0:
                    fanout_sweep_fig = go.Figure()
                    for buff_fanout in ic_3d_info.fanout_range:
                        final_df_row = {}
                        ### OPT PN SIZES BEFORE RUNNING SIM ###
                        sim_success = False
                        cur_tfreq = target_freq
                        parse_flags = {
                            "voltage": True,
                            "delay": True,
                        }
                        show_flags = {
                            "voltage": False,
                            "delay": False,
                        }
                        sim_iters = 0
                        while not sim_success and cur_tfreq > 0:
                            # print(f"Running sim for {n_stages} stages, {buff_fanout} fanout, {cur_tfreq} target freq")
                            buff_dse.write_pn_sizing_opt_sp_sim(ic_3d_info, num_stages=n_stages, buff_fanout=buff_fanout, add_wlen=add_wlen, targ_freq=cur_tfreq)
                            pn_sim = {
                                "ic_3d_info": ic_3d_info,
                                "sp_work_dir":"ubump_ic_driver",
                                "sim_sp_files": ["opt_pn_ubump_ic_driver.sp"]
                            }
                            buff_dse.run_spice(**pn_sim)

                            try:
                                sp_run_df, sp_run_info, opt_sp_sim_df = buff_dse.parse_sp_output(ic_3d_info, parse_flags, buff_fanout, n_stages, os.path.join(ic_3d_info.spice_info.sp_dir,ic_3d_info.spice_info.sp_sim_title,"opt_pn_ubump_ic_driver.lis"))
                                sim_success = True
                            except:
                                cur_tfreq /= 2
                                print(f"Delay measure statements not captured, trying again with target frequency {cur_tfreq}")
                            sim_iters += 1
                            if sim_iters > 15:
                                print(f"Failed to get delay measure statements after {sim_iters} iterations, exiting")
                                print(f"Plotting waveforms for failed run...")
                                parse_flags["delay"] = False
                                show_flags["voltage"] = True
                                sp_run_df, sp_run_info, opt_sp_sim_df = buff_dse.parse_sp_output(ic_3d_info, parse_flags, buff_fanout, n_stages, os.path.join(ic_3d_info.spice_info.sp_dir,ic_3d_info.spice_info.sp_sim_title,"opt_pn_ubump_ic_driver.lis"))
                                buff_dse.plot_sp_run(ic_3d_info, show_flags, sp_run_info, sp_run_df)
                                parse_flags["delay"] = True
                                show_flags["voltage"] = False

                                    


                        buff_dse.plot_sp_run(ic_3d_info, show_flags, sp_run_info, sp_run_df)

                        ### WRITE SIM WITH OPTIMIZED PN VALUES ###
                        buff_dse.write_loaded_driver_sp_sim(ic_3d_info=ic_3d_info, num_stages=n_stages, buff_fanout=buff_fanout, add_wlen=add_wlen, targ_freq=cur_tfreq, in_sp_sim_df=opt_sp_sim_df)
                        sims = {
                            "ic_3d_info": ic_3d_info,
                            "sp_work_dir":"ubump_ic_driver",
                            "sim_sp_files": [f"{ic_3d_info.spice_info.sp_sim_title}.sp"]
                        }
                        _ = buff_dse.run_spice(**sims)
                        print("**************************************************************************************************")
                        print(f"BUFF FANOUT: {buff_fanout}, NUM STAGES: {n_stages}")
                        # sp_run_df contains the Voltage information for each node in the circuit
                        # sp_run_info is the information that is a superset of sp_sim_df, with both the single run information and the information for each inverter
                        # sp_sim_df is the information for each inverter in the circuit in form of dataframe

                        # Wrap this in a try catch as theres a weird edge case in which the P N sizes of inverters are not an integer, no idea why, I set the step to 1 but Hspice is hard :( 
                        # If it fails we just use the results from the opt_pn run which should be pretty close
                        try:
                            sp_run_df, sp_run_info, sp_sim_df = buff_dse.parse_sp_output(ic_3d_info, parse_flags, buff_fanout, n_stages, ic_3d_info.spice_info.sp_sim_outfile)                        
                        except:
                            pass
                        
                        sp_sim_df["pmos_width"] = opt_sp_sim_df["pmos_width"]
                        sp_sim_df["nmos_width"] = opt_sp_sim_df["nmos_width"]
                        # from the pmos, nmos info and the fanout of each stage of the circuit calculate the area
                        ################# AREA CALCULATION #################
                        inv_areas = []
                        for i, row in sp_sim_df.iterrows():
                            inv_mult_factor = (buff_fanout ** i) if i != total_nstages - 1 else 1
                            # multiply the fanout factor by the
                            nfet_tx_size = int(float(row["nmos_width"]) * inv_mult_factor)
                            pfet_tx_size = int(float(row["pmos_width"]) * inv_mult_factor)
                            # print(inv_mult_factor, nfet_tx_size, pfet_tx_size)
                            inv_area = (buff_dse.finfet_tx_area_model(nfet_tx_size) + buff_dse.finfet_tx_area_model(pfet_tx_size))*(ic_3d_info.design_info.process_info.tx_geom_info.min_width_tx_area*1e-6)
                            inv_areas.append(inv_area)
                        sp_sim_df["area"] = inv_areas
                        sp_run_info["inv_chain_area"] = sum(inv_areas[1:len(inv_areas)])
                        cur_cost = buff_dse.calc_cost(ic_3d_info.design_info, ic_3d_info.cost_fx_exps, sp_run_info)
                        final_df_row["cost"] = cur_cost
                        final_df_row["buff_fanout"] = buff_fanout
                        final_df_row["n_stages"] = n_stages
                        final_df_row["add_wire_length"] = add_wlen
                        final_df_row["e2e_max_prop_delay"] = sp_run_info["total_max_prop_delay"]
                        final_df_row["area"] = round(sp_run_info["inv_chain_area"],4)
                        

                        final_df_rows.append(final_df_row)
                        print("\n".join(rg_utils.get_df_output_lines(sp_sim_df)))
                        if cur_cost < cur_best_cost:
                            cur_best_cost = cur_cost
                            print(f"NEW BEST COST: {cur_best_cost}")
                            best_sp_run = sp_run_info
                            best_sp_run_df = sp_sim_df
                            print("**************************************************************************************************")
                        bar_fig = buff_dse.plot_sp_run(ic_3d_info, show_flags, sp_run_info, sp_run_df)
                        for trace in bar_fig.data:
                            fanout_sweep_fig.add_trace(trace)

                    time_def_unit = next(iter({k:v for k,v in ic_3d_info.sp_sim_settings.unit_lookups["time"].items() if v == 1}), None)

                    fanout_sweep_fig.update_layout(
                        title=f"Num Stages: {sp_run_info['n_stages']} Max Prop Delay by Inv Stage",
                        xaxis_title='Stage Ratio',
                        yaxis_title=f"Time ({time_def_unit}s)",
                        barmode='group',
                        bargap=0.3
                    )
                    fanout_sweep_fig.write_image(f"ubump_pitch_{ubump_info.pitch}_num_stages_{n_stages}_prop_delay_vs_stage_ratio.png", format="png")
                    # fanout_sweep_fig.show()
                    for i in range(len(fanout_sweep_fig.data)):
                        final_fig.add_trace(fanout_sweep_fig.data[i], row=1, col=stage_idx+1)

                print(f"****************************** Ubump Pitch {ubump_info.pitch} Ubump Cap {ubump_info.cap} Process Info {process_info.name} ********************************************")
                print(f"BEST SP RUN:")
                print(f"NUM STAGES: {best_sp_run['n_stages']}, BUFF FANOUT: {best_sp_run['buff_fanout']}")
                for l in rg_utils.get_df_output_lines(best_sp_run_df):
                    print(l)
                print("****************************************** SWEEP SUMMARY: ******************************************")
                final_df = pd.DataFrame(final_df_rows)
                for l in rg_utils.get_df_output_lines(final_df):
                    print(l)
                # perform write of sp netlist and simulation of best sp run found
                # buff_dse.write_loaded_driver_sp_sim(ic_3d_info, best_sp_run["n_stages"], best_sp_run["buff_fanout"], targ_freq=cur_tfreq, add_wlen=add_wlen, in_sp_sim_df=best_sp_run_df)
                # _ = buff_dse.run_spice(**sims)
                print("**************************************************************************************************")


def run_pdn_modeling(ic_3d_info: rg_ds.Ic3d):
    pdn.pdn_modeling(ic_3d_info)


def run_spice_debug(spProcess: rg_ds.SpProcess) -> Tuple[pd.DataFrame, dict, Dict[str, List[Dict[int, float]]] ]:
    res = rg_ds.Regexes()
    sp_sim_settings = rg_ds.SpGlobalSimSettings()
    
    buff_dse.run_spice(sp_process = spProcess)
    parse_flags = {
        "plot": True,
        "measure": True,
        "gen_params": True,
    }
    plot_df, measurements, _, gen_params = buff_dse.parse_spice(res, spProcess, parse_flags)
    # Unit conversion
    plot_df["time"] = buff_dse.unit_conversion(sp_sim_settings.unit_lookup_factors["time"], plot_df["time"], sp_sim_settings.abs_unit_lookups )
    for key in plot_df.columns[1:]:
        plot_df[key] = buff_dse.unit_conversion(sp_sim_settings.unit_lookup_factors["voltage"], plot_df[key], sp_sim_settings.abs_unit_lookups )
    
    fig = go.Figure()

    # Add traces for each element being plotted
    for col in plot_df.columns:
        if col != "time":
            fig.add_trace(go.Scatter(x=plot_df["time"], y=plot_df[col], name=col))

    # This will be invalid if the user wants to look at something other than voltage
    fig.update_layout(
        title=f"Spice {spProcess.title} Waveforms @ {spProcess.sp_file}",
        xaxis_title=f"Time ({sp_sim_settings.unit_lookup_factors['time']}s)", 
        yaxis_title=f"Voltage ({sp_sim_settings.unit_lookup_factors['voltage']}V)",
    )
    fig.show()
    # assuming all measurements are delays we can convert to ps
    meas_df = pd.DataFrame(measurements)
    for l in rg_utils.get_df_output_lines(meas_df):
        print(l)

    # Filter out delays with other measurements
    delay_substrings = ["delay", "t_rise", "t_fall"]
    delay_df = meas_df[meas_df['name'].str.contains('|'.join(delay_substrings))]
    # Uncomment for unit conversion
    # delay_df.loc[:, 'val'] = delay_df.loc[:,'val'].apply(lambda x: buff_dse.unit_conversion(sp_sim_settings.unit_lookup_factors["time"], x, sp_sim_settings.abs_unit_lookups, sig_figs = 5)) 
    # delay_df.loc[:, 'targ'] = delay_df.loc[:,'targ'].apply(lambda x: buff_dse.unit_conversion(sp_sim_settings.unit_lookup_factors["time"], x, sp_sim_settings.abs_unit_lookups, sig_figs = 5)) 
    # delay_df.loc[:, 'trig'] = delay_df.loc[:,'trig'].apply(lambda x: buff_dse.unit_conversion(sp_sim_settings.unit_lookup_factors["time"], x, sp_sim_settings.abs_unit_lookups, sig_figs = 5)) 
    
    # print(delay_df)
    # for l in rg_utils.get_df_output_lines(delay_df):
    #     print(l)

    return plot_df, measurements, gen_params


def run_ic_3d_dse(ic_3d_cli: rg_ds.Ic3dCLI) -> Tuple[float]:
    # Hack to convert asic_dse_cli to dict as input for init_structs function
    ic_3d_conf = asdict(ic_3d_cli)
    ic_3d_info = rg_utils.init_ic_3d_structs(ic_3d_conf)
    
    if ic_3d_cli.buffer_dse:
        run_buffer_dse(ic_3d_info)
    if ic_3d_cli.pdn_modeling:
        run_pdn_modeling(ic_3d_info)
    if ic_3d_cli.buffer_sens_study:
        run_buffer_sens_study(ic_3d_info)
    