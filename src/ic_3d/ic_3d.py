
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


import plotly.subplots as subplots
import plotly.graph_objects as go
import plotly.subplots as subplots
import plotly.express as px


# rad gen utils imports
import src.utils as rg_utils
import src.data_structs as rg_ds


# ic 3d imports
import src.ic_3d.buffer_dse as buff_dse
import src.ic_3d.pdn_modeling as pdn




def run_buffer_sens_study(ic_3d_info: rg_ds.Ic3d):
    output_csv = "sens_study_out.csv"
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
                "num_stages" : 1,
                "stage_ratio": 2,
                "pn_ratios": [] # 1 value for each stage + 1 for shape + 1 for final stage
            }
            # These values can be parameters (strings) or integer values
            buffer_params["pn_ratios"] = [
                {
                    "wp": 7,
                    "wn": 5,
                } for _ in range(1 + buffer_params["num_stages"] + ic_3d_info.design_info.bot_die_nstages)
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
                                in_val = input("d to plot the waveforms from the failing simulation, any other key to continue: ")
                                if in_val == "d":
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
                        # sys.exit(1)
                        # sp_run_df contains the Voltage information for each node in the circuit
                        # sp_run_info is the information that is a superset of sp_sim_df, with both the single run information and the information for each inverter
                        # sp_sim_df is the information for each inverter in the circuit in form of dataframe
                        sp_run_df, sp_run_info, sp_sim_df = buff_dse.parse_sp_output(ic_3d_info, parse_flags, buff_fanout, n_stages, ic_3d_info.spice_info.sp_sim_outfile)                        
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
                        # if noc_idx >= noc_len:
                        #     final_df_row["add_wire_length"] = 0
                        # else:
                        #     final_df_row["add_wire_length"] = design_info.nocs[noc_idx].add_wire_len
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
                buff_dse.write_loaded_driver_sp_sim(ic_3d_info, best_sp_run["n_stages"], best_sp_run["buff_fanout"], targ_freq=cur_tfreq, add_wlen=add_wlen, in_sp_sim_df=best_sp_run_df)
                _ = buff_dse.run_spice(**sims)
                print("**************************************************************************************************")


def run_pdn_modeling(ic_3d_info: rg_ds.Ic3d):
    pdn.pdn_modeling(ic_3d_info)


def run_spice_debug(ic_3d_info: rg_ds.Ic3d, spProcess: rg_ds.SpProcess):
    buff_dse.run_spice(sp_process = spProcess)
    parse_flags = {
        "plot": True,
        "measure": True
    }
    plot_df, measurements = buff_dse.parse_spice(ic_3d_info.res, spProcess, parse_flags)
    # Unit conversion
    # plot_df[["time"]] = plot_df[["time"]].apply(lambda x: buff_dse.unit_conversion(ic_3d_info.sp_sim_settings.unit_lookup_factors["time"], x, "time"))
    plot_df["time"] = buff_dse.unit_conversion(ic_3d_info.sp_sim_settings.unit_lookup_factors["time"], plot_df["time"], ic_3d_info.sp_sim_settings.abs_unit_lookups )
    for key in plot_df.columns[1:]:
        plot_df[key] = buff_dse.unit_conversion(ic_3d_info.sp_sim_settings.unit_lookup_factors["voltage"], plot_df[key], ic_3d_info.sp_sim_settings.abs_unit_lookups )
    
    fig = go.Figure()

    # Add traces for each element being plotted
    for col in plot_df.columns:
        if col != "time":
            fig.add_trace(go.Scatter(x=plot_df["time"], y=plot_df[col], name=col))

    # This will be invalid if the user wants to look at something other than voltage
    fig.update_layout(
        title=f"Spice {spProcess.title} Waveforms @ {spProcess.sp_file}",
        xaxis_title=f"Time ({ic_3d_info.sp_sim_settings.unit_lookup_factors['time']}s)", 
        yaxis_title=f"Voltage ({ic_3d_info.sp_sim_settings.unit_lookup_factors['voltage']}V)",
    )
    fig.show()
    meas_df = pd.DataFrame(measurements)
    for l in rg_utils.get_df_output_lines(meas_df):
        print(l)

    pass


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
    