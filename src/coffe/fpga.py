from __future__ import annotations
from dataclasses import dataclass, field, fields, InitVar

import os
import sys
import math
import logging
import random
from collections import OrderedDict
import itertools
import csv
import traceback
import copy

from typing import List, Dict, Any, Tuple, Union, Type, NamedTuple, Set, Callable
from collections import defaultdict


# Subcircuit Modules
import src.coffe.basic_subcircuits as basic_subcircuits
# import src.coffe.mux_subcircuits as mux_subcircuits
# import src.coffe.lut_subcircuits as lut_subcircuits
# import src.coffe.ff_subcircuits as ff_subcircuits
# import src.coffe.load_subcircuits as load_subcircuits
# import src.coffe.memory_subcircuits as memory_subcircuits
import src.coffe.utils as utils
import src.coffe.cost as cost
import src.coffe.constants as consts

# HSPICE handling module
import src.coffe.spice as spice

# Rad Gen data structures
import src.common.data_structs as rg_ds
import src.common.utils as rg_utils

import src.common.spice_parser as sp_parser


# ASIC DSE imports
import src.asic_dse.asic_dse as asic_dse

# Importing individual constructors for subckt classes

import src.coffe.data_structs as c_ds
import src.coffe.gen_routing_loads as gen_r_load_lib
import src.coffe.sb_mux as sb_mux_lib
import src.coffe.cb_mux as cb_mux_lib
import src.coffe.lut as lut_lib
import src.coffe.ble as ble_lib
import src.coffe.logic_block as lb_lib
import src.coffe.carry_chain as cc_lib
import src.coffe.ram as ram_lib
# import src.coffe.new_ram as ram_lib
import src.coffe.hardblock as hb_lib
import src.coffe.constants as constants

import src.common.rr_parse as rrg_parse



# # Track-access locality constants
# OUTPUT_TRACK_ACCESS_SPAN = 0.25
# INPUT_TRACK_ACCESS_SPAN = 0.50

# # Delay weight constants:
# DELAY_WEIGHT_SB_MUX = 0.4107
# DELAY_WEIGHT_CB_MUX = 0.0989
# DELAY_WEIGHT_LOCAL_MUX = 0.0736
# DELAY_WEIGHT_LUT_A = 0.0396
# DELAY_WEIGHT_LUT_B = 0.0379
# DELAY_WEIGHT_LUT_C = 0.0704 # This one is higher because we had register-feedback coming into this mux.
# DELAY_WEIGHT_LUT_D = 0.0202
# DELAY_WEIGHT_LUT_E = 0.0121
# DELAY_WEIGHT_LUT_F = 0.0186
# DELAY_WEIGHT_LUT_FRAC = 0.0186
# DELAY_WEIGHT_LOCAL_BLE_OUTPUT = 0.0267
# DELAY_WEIGHT_GENERAL_BLE_OUTPUT = 0.0326
# # The res of the ~15% came from memory, DSP, IO and FF based on my delay profiling experiments.
# DELAY_WEIGHT_RAM = 0.15
# HEIGHT_SPAN = 0.5

# # Metal Layer definitions
# LOCAL_WIRE_LAYER = 0

# # Global Constants
# CHAN_USAGE_ASSUMPTION = 0.5
# CLUSTER_INPUT_USAGE_ASSUMPTION = 0.5
# LUT_INPUT_USAGE_ASSUMPTION = 0.85

# # This parameter determines if RAM core uses the low power transistor technology
# # It is strongly suggested to keep it this way since our
# # core RAM modules were designed to operate with low power transistors.
# # Therefore, changing it might require other code changes.
# # I have included placeholder functions in case someone really insists to remove it
# # The easier alternative to removing it is to just provide two types of transistors which are actually the same
# # In that case the user doesn't need to commit any code changes.
# use_lp_transistor = 1





# General Notes:
# - It would be a good idea to have some assertion that when we write out a spice file using a particular parameter for wires / tx_sizes,
#     we return exhaustive list of all unique parameters written out from the generate function.
#     When doing things to all tx_params / wire params in the component
#     assert:
#     - An action performed for each param in exhaustive list -> set( [param for param in all_params] ) == set( [param for param in action_params] )

# Defining type aliases -> these dont work in python 3.9 :( 
# SpMeasOut = Dict[str, List[float | bool]]    
# SpMeasTbsOut = Dict[Type[c_ds.SimTB], SpMeasOut]


# Make FPGA class with "models" for each component
# Each model would have a list of possible base components, generated from user params
# From that list of components, we can iterate and swap out components while we run simulations to test multiple types of components
# When looking at multiple "models" we can determine if we need to do a geometric or linear sweep of them to accurately represent the FPGA


def fpga_state_fmt(fpga_inst:'FPGA', tag: str) -> dict:
    """
        Get a timestamp for the current FPGA state to use when outputting debug info, s.t. users can know when things are happening

        Args:
            fpga_inst (FPGA): The FPGA instance to get the timestamp for
            tag (str): The tag to use for the timestamp
        
        Returns:
            a dictionary of the current timestamp
    """
    row_data = { 
        "TAG": tag, 
        "AREA_UPDATE_ITER": fpga_inst.update_area_cnt, 
        "WIRE_UPDATE_ITER": fpga_inst.update_wires_cnt, 
        "DELAY_UPDATE_ITER": fpga_inst.update_delays_cnt, 
        "COMPUTE_DISTANCE_ITER": fpga_inst.compute_distance_cnt, 
    }
    return row_data

def fpga_state_to_csv(fpga_inst: 'FPGA', tag: str, catagory: str, ckt: Type[c_ds.SizeableCircuit] | None = None) -> None:
    """ 
        Update the FPGA telemetry CSV file with the current FPGA telemetry, Create CSV if it doesnt exist     

        Args:
            fpga_inst (FPGA): The FPGA instance to get the telemetry from
            tag (str): The tag to use for the timestamp
            catagory (str): The catagory of information to output to the CSV
            ckt (Type[c_ds.SizeableCircuit]): The circuit to output telemetry for, if None output all circuits
    """

    out_catagories = {
        "wire_length": fpga_inst.wire_lengths,
        "area": fpga_inst.area_dict,
        "tx_size": fpga_inst.transistor_sizes,
        "delay": fpga_inst.delay_dict
    }

    # Make sure these keys are same ones in FPGA object
    assert set(list(out_catagories.keys())) == set(fpga_inst.log_out_catagories)

    # Check to see if any repeating keys in any of these dicts
    # if not set(fpga_inst.wire_lengths.keys()) & set(fpga_inst.area_dict.keys()) fpga_inst.transistor_sizes.keys()
    # Write a CSV for each catagory of information we want to track
    # for cat_k, cat_v in out_catagories.items():

    # Open the CSV file
    out_dir = "debug"
    os.makedirs(out_dir, exist_ok=True)
    cat_v: dict
    fpath: str
    if ckt is None:
        cat_v = out_catagories[catagory]
        fpath = os.path.join(out_dir,f"{catagory}_detailed.csv")
    else:
        sp_name: str = ckt.sp_name if (hasattr(ckt, "sp_name") and ckt.sp_name) else ckt.name
        if catagory == "wire_length": 
            cat_v = {wire_name: fpga_inst.wire_lengths[wire_name] for wire_name in ckt.wire_names}
        elif catagory == "area":
            cat_v = {area_key: fpga_inst.area_dict[area_key] for area_key in fpga_inst.area_dict.keys() if sp_name in area_key}
        elif catagory == "tx_size":
            cat_v = {tx_key: fpga_inst.transistor_sizes[tx_key] for tx_key in fpga_inst.transistor_sizes.keys() if sp_name in tx_key} 
        
        # Output path stuff
        os.makedirs(os.path.join(out_dir, sp_name), exist_ok = True)
        fpath = os.path.join(os.path.join(out_dir, sp_name),f"{catagory}_{sp_name}.csv")
    # Sort it for easy comparison
    sorted_cat = OrderedDict(sorted(cat_v.items())) 
    row_data = { 
        "TAG": tag, 
        "AREA_UPDATE_ITER": fpga_inst.update_area_cnt, 
        "WIRE_UPDATE_ITER": fpga_inst.update_wires_cnt, 
        "DELAY_UPDATE_ITER": fpga_inst.update_delays_cnt, 
        "COMPUTE_DISTANCE_ITER": fpga_inst.compute_distance_cnt, 
        **sorted_cat
    }
    
    with open(fpath, "a") as csv_file:
        header = list(row_data.keys())
        writer = csv.DictWriter(csv_file, fieldnames = header)
        # Check if the file is empty and write header if needed
        if csv_file.tell() == 0:
            writer.writeheader()
        writer.writerow(row_data)


def sim_tbs( 
    tbs: List[Type[c_ds.SimTB]],
    sp_interface: spice.SpiceInterface,
    parameter_dict: Dict[str, List[str]],
) -> Dict[
    Type[c_ds.SimTB], 
    Dict[str, 
        List[float] | List[bool]
    ]
]:
    """
        Runs HSPICE on all testbenches in the list with the corresponding parameter dict
        Returns a dict hashed by each testbench with its corresponding results (delay, power)

        Args:
            tbs (List[Type[c_ds.SimTB]]): The list of testbenches to simulate
            sp_interface (spice.SpiceInterface): The interface to the HSPICE (or other SPICE) simulator(s)
            parameter_dict (Dict[str, List[str]]): The parameter dictionary to use for the simulation
        
        Returns:
            A dict containing the simulation results hashed by testbench which got those values
    """
    
    # Create a default dict of dicts of lists to store measurements for each tb sweep point
    tb_meas: Dict[Type[c_ds.SimTB], Dict[str, float]] = defaultdict(lambda: defaultdict(list))
    
    for tb in tbs:
        sp_name: str = tb.dut_ckt.sp_name if (hasattr(tb.dut_ckt, "sp_name") and tb.dut_ckt.sp_name) else tb.dut_ckt.name
        print(f"Updating delay for {sp_name} with TB {tb.tb_fname.replace('.sp','')}")
        if not consts.PASSTHROUGH_DEBUG_FLAG:
            spice_meas = sp_interface.run(tb.sp_fpath, parameter_dict)
        else:
            spice_meas = {
                "trise": [1]*len(list(parameter_dict.values())[0]),
                "tfall": [1]*len(list(parameter_dict.values())[0]),
                "meas_avg_power": [1]*len(list(parameter_dict.values())[0]),
                "meas_logic_low_voltage": [0]*len(list(parameter_dict.values())[0]),
                "delay": [1]*len(list(parameter_dict.values())[0]),
                "valid": True*len(list(parameter_dict.values())[0]),
                # Add the inverter / other measurements
                **{mp.value.name: [1]*len(list(parameter_dict.values())[0]) for mp in tb.meas_points}
            }
        
        valid_delays: List[bool] | None = None
        # Account for additional measurements which are not explictly asked for
        for key in spice_meas.keys():
            # if key not in ["valid", "trise", "tfall", "power"]:
            if key not in ["valid"]:
                # Checks to see if the prefix used to define measure statement is in the key (ie its something we want to look for not random crap)
                if tb.meas_val_prefix in key:
                    # Our total trise / tfall delays will be checked for validity and set to 1 if invalid (high cost function value)
                    if key in [f"{tb.meas_val_prefix}_total_trise", f"{tb.meas_val_prefix}_total_tfall"]:
                        new_valid_delays: List[bool] = [ val != "failed" and float(val) > 0 for val in spice_meas[key] ]
                        if valid_delays is not None:
                            # Do element wise AND with prev valid delays and new ones to get updated delay validity
                            valid_delays = [ 
                                (prev_vd and new_vd) for prev_vd, new_vd in zip(
                                    valid_delays,
                                    new_valid_delays,
                                ) 
                            ]     
                        else:
                            valid_delays = new_valid_delays         
                        trise_tfall_delays: List[float] = [ 
                            float(val) if val != "failed" else 1 for val in spice_meas[key] 
                        ]
                        # Convert the tb specific tfall / trise keys into a standard used for all tb post processing
                        if "tfall" in key:
                            tb_meas[tb]['tfall'] = trise_tfall_delays
                        elif "trise" in key:
                            tb_meas[tb]['trise'] = trise_tfall_delays
                        # Set valids, if they already exist 
                    elif key == "meas_avg_power":
                        tb_meas[tb]['power'] += [ float(val) for val in spice_meas[key] ]
                    else:
                        # if its an implicit key we will take all sweep measurement points and append them to the list for this key
                        # TODO change to allow implicit meas statements to fail if they are not found 
                        #   (valid delay may still be asserted if the measure statement is unneeded)
                        tb_meas[tb][key] += [ float(sw_pt_val) for sw_pt_val in spice_meas[key] ]
        # After this point the trise / tfall delays will be set in tb_meas so we can calculate the max delay
        tb_meas[tb]["valid"] += valid_delays
        tb_meas[tb]["delay"] += [ 
            max(tfall, trise) for (tfall, trise) in zip(
                    tb_meas[tb]['tfall'],
                    tb_meas[tb]['trise']
                )
        ]
    return tb_meas

def merge_tb_meas(
    in_tb_meas: Dict[
        Type[c_ds.SimTB],
        Dict[Type[c_ds.SimTB], 
            Dict[str, 
                List[float] | List[bool]
            ]
        ]
    ], 
) -> Dict[ Type[c_ds.SizeableCircuit], Dict[str, List[float] | List[bool]]]:
    """
        Takes result dictionary which is hashed by testbenches (from `sim_tbs`),
            merges delays and power for each unique circuit to set them
            merge function is specific to a testbench / subckt combo
    """
    # Calculate the portion of the critical path this circuit should contribute
    # repr_crit_path_delay: float = None
    # Find all unique circuits in testbenches
    unique_ckts: Set[Type[c_ds.SizeableCircuit]] = set([tb.dut_ckt for tb in in_tb_meas.keys()])
    merged_meas: Dict[Type[c_ds.SizeableCircuit] , Dict[str, List[float] | List[bool]]] = {}
    # Iterate through results for these circuits across different TB environments and set the circuit delay + power
    for ckt in unique_ckts:
        # Get all the testbenches that have this circuit
        tb_meas: Dict[Type[c_ds.SimTB], Dict[str, List[float] | List[bool]]] = {
            tb: meas for tb, meas in in_tb_meas.items() if tb.dut_ckt == ckt
        }
        # Merge & Set the measurements for the circuit
        # merge_fn(tb_meas) # The other unique ckts may or may not be needed depending on the merge fn
        
        # tfall: float = 0
        # trise: float = 0
        # delay: float = 0
        # pwr: float = 0
        float_measures: Dict[str, List[float]] = defaultdict(lambda: [])
        valids: List[bool] = []
        # Iterate through tbs 
        for tb in tb_meas.keys():
            # We use a delay weight factor (required from user) to weight the delay of the subckt in this particular tb environment
            # tfall += tb_meas[tb]["tfall"] / len(tb_meas.keys()) # TODO initialize delay_weights somewhere rather than evenly weighting by dividing by len
            # trise += tb_meas[tb]["trise"] / len(tb_meas.keys()) # TODO initialize delay_weights somewhere rather than evenly weighting by dividing by len
            # pwr += tb_meas[tb]["power"] * tb.power_weight # This may be unecessary TODO figure out
            for key in tb_meas[tb].keys():
                if key != "valid":
                    # Iterate through sweep points (should assert that len(trise) == len(all other keys))
                    for i in range(len(tb_meas[tb]["trise"])):
                        weighted_sw_pt_val: float = tb_meas[tb][key][i] / len(tb_meas.keys()) # TODO initialize delay_weights somewhere rather than evenly weighting by dividing by len
                        if len(float_measures[key]) > i: # from > 0
                            float_measures[key][i] += weighted_sw_pt_val
                        else:
                            float_measures[key].append(weighted_sw_pt_val)
                else:
                    # And the tb valids togther to get a single merged one
                    if len(valids) > i: # from > 0
                        valids = [ 
                            valid and tb_meas[tb]["valid"][i] 
                                for i, valid in enumerate(valids) 
                        ]
                    else:
                        valids = tb_meas[tb]["valid"]

                    # Already accounted for these keys manually
                    # if key not in ["tfall", "trise", "power", "valid", "delay"]:
                        # extra_measures[key] += tb_meas[tb][key] / len(tb_meas.keys())  # TODO initialize delay_weights somewhere rather than evenly weighting by dividing by len
            
            for i in range(len(float_measures["trise"])):
                delay: float = max(float_measures["tfall"][i], float_measures["trise"][i])
                if len(float_measures[key]) > 0:
                    float_measures["delay"][i] = delay 
                else:
                    float_measures["delay"].append(delay)


        # delay = max(tfall, trise)
        # Set the measurements for the circuit
        # if set_flag:
        #     # if we're setting the circuit delays there shouldnt be a point sweep going on
        #     #   ie all key lists should be of len 1 
        #     assert all(len(val == 1) for val in float_measures.values())
        #     ckt.trise = float_measures["trise"][0]
        #     ckt.tfall = float_measures["tfall"][0]
        #     ckt.delay = float_measures["delay"][0]
        #     ckt.power = float_measures["power"][0]
        #     if delay_dict:
        #         delay_dict[ckt.sp_name] = float_measures["delay"][0]
        #     repr_crit_path_delay = float_measures["delay"][0]


        # Return the merged TB measurements into a dict hashed by subckt objects
        merged_meas[ckt] = {
            **float_measures,
            "valid": valids, 
        }
        # merged_meas[ckt] = {
        #     "trise": trise,
        #     "tfall": tfall,
        #     "delay": delay,
        #     "power": pwr,
        #     "valid": all([tb_meas[tb]["valid"] for tb in tb_meas.keys()]), # TODO make sure its fine to invalidate other TB envs if one is invalid
        #     **extra_measures,
        # }

        # Now we account for the weight of a particular circuit in the repr crit path calculation
        # If this weight is calculated specific to like SBs rather than L4 SBs we would want to divide it by the number of ckts to keep it fair
        # TODO change the / len(unique_ckts) if we want to set all weights according to thier instance (SB Mux L4, L16... )
        # repr_crit_path_delay += (delay * ckt.delay_weight / len(unique_ckts) )
    return merged_meas

@dataclass
class FPGA:
    """ 
        This class describes an FPGA. 
        It contains all the subcircuits (SwitchBlock, ConnectionBlock, LogicCluster, etc.)


        Attributes:
            coffe_info (rg_ds.Coffe): The data structure initialiizes all functionality and user parameters passed to COFFE
            run_options (NamedTuple): The run options for COFFE, i.e. a convience data struct for storing the various modes which COFFE can be run in 
                (ideally seperating these from other input data that could have cascading effects on different data structure fields)
            spice_interface (spice.SpiceInterface): The interface to the HSPICE (or other SPICE) simulator(s)
            subckt_lib (Dict[str, rg_ds.SpSubCkt]): A dictionary of all subcircuits in the FPGA, hashed by their SPICE subckt name (defined by .subckt statement in spice files)
            gen_r_wires (List[c_ds.GenRoutingWire]): A list of all general routing wires in the FPGA



    """
    
    # Init only fields
    coffe_info: InitVar[rg_ds.Coffe]
    run_options: NamedTuple

    # Required fields pre __post_init__
    spice_interface: spice.SpiceInterface

    # Fields below this point are all initialized in __post_init__
    # Data structure contianing all of subckts structs parsed POST - generate phase
    subckt_lib: Dict[str, rg_ds.SpSubCkt] = field(
        default_factory=lambda: {}
    ) 

    # Information about FPGA General Routing Wires
    gen_r_wires: List[c_ds.GenRoutingWire] = field(
        default_factory=lambda: []
    )

    # Models for each subckt in the FPGA, uninitalized 
    # switch_block: SwitchBlockModel = None

    # Telemetry Info
    tele: c_ds.COFFETelemetry = field(
        default_factory=lambda: c_ds.COFFETelemetry(
            logger=logging.getLogger("rad_gen_root")
        )
    )
    log_out_catagories: List[str] = field(
        default_factory = lambda: []
    )

    update_area_cnt: int = 0
    update_wires_cnt: int = 0
    compute_distance_cnt: int = 0
    update_delays_cnt: int = 0

    ######################################################################################
    ### LISTS CONTAINING ALL CREATED SUBCIRCUITS (ALL MAY NOT BE SIMULATED AND SIZED)  ###
    ######################################################################################

    # Switch Block Muxes
    sb_mux_tbs: List[sb_mux_lib.SwitchBlockMuxTB] = field(
        default_factory=lambda: []
    )
    # Connection Block Muxes
    cb_mux_tbs: List[cb_mux_lib.ConnectionBlockMuxTB] = field(
        default_factory=lambda: []
    )
    # Local Mux TBs
    local_mux_tbs: List[lb_lib.LocalMuxTB] = field(
        default_factory=lambda: []
    )
    # Local BLE Output TBs
    local_ble_output_tbs: List[ble_lib.LocalBLEOutputTB] = field(
        default_factory=lambda: []
    )
    # General BLE Output TBs
    general_ble_output_tbs: List[ble_lib.GeneralBLEOutputTB] = field(
        default_factory=lambda: []
    )
    # LUT TBs
    lut_tbs: List[lut_lib.LUTTB] = field(
        default_factory=lambda: []
    )
    # Flut Mux TBs
    flut_mux_tbs: List[ble_lib.FlutMuxTB] = field(
        default_factory=lambda: []
    )
    # Lut Input Driver TBs
    lut_in_driver_tbs: Dict[str, List[lut_lib.LUTInputDriverTB]] = field(
        default_factory=lambda: defaultdict(list)
    )
    # Lut Input Not Driver TBs
    lut_in_not_driver_tbs: Dict[str, List[lut_lib.LUTInputDriverTB]] = field(
        default_factory=lambda: defaultdict(list)
    )
    # Lut Input Driver LUT Load TBs
    lut_input_tbs: Dict[str, List[lut_lib.LUTInputTB]] = field(
        default_factory=lambda: defaultdict(list)
    )
    # Carry Chain Mux TBs
    carry_chain_mux_tbs: List[cc_lib.CarryChainMuxTB] = field(
        default_factory=lambda: []
    )
    # Carry Chain Peripherial TBs
    carry_chain_per_tbs: List[cc_lib.CarryChainPerTB] = field(
        default_factory=lambda: []
    )
    # Carry Chain TBs
    carry_chain_tbs: List[cc_lib.CarryChainTB] = field(
        default_factory=lambda: []
    )
    # Carry Chain Mux Skip TBs
    carry_chain_skip_and_tbs: List[cc_lib.CarryChainSkipAndTB] = field(
        default_factory=lambda: []
    )
    # Carry Chain Inter Cluster TBs
    carry_chain_inter_tbs: List[cc_lib.CarryChainInterClusterTB] = field(
        default_factory=lambda: []
    )
    # Carry Chain Skip Mux TBs
    carry_chain_skip_mux_tbs: List[cc_lib.CarryChainSkipMuxTB] = field(
        default_factory=lambda: []
    )

    # BRAM TBs
    # pgate_output_crossbar_tbs: List[ram_lib.PgateOutputCrossbarTB] = field(
    #     default_factory=lambda: []
    # )
    # configurable_decoder_iii_tbs: List[ram_lib.ConfigurableDecoderIIITB] = field(
    #     default_factory=lambda: []
    # )


    # Dictionary of simulation testbenches hashed by thier dut ckt
    tb_lib: Dict[
        Type[c_ds.SizeableCircuit],
        List[c_ds.SimTB]
    ] = None

    # Carry Chain Info, used in update_area and other functions
    carry_skip_periphery_count: int = None
    skip_size: int = None

    #   ___ ___  ___   _      ___ ___ ___  ___ _   _ ___ _____    ___  ___    _ ___ 
    #  | __| _ \/ __| /_\    / __|_ _| _ \/ __| | | |_ _|_   _|  / _ \| _ )_ | / __|
    #  | _||  _/ (_ |/ _ \  | (__ | ||   / (__| |_| || |  | |   | (_) | _ \ || \__ \
    #  |_| |_|  \___/_/ \_\  \___|___|_|_\\___|\___/|___| |_|    \___/|___/\__/|___/
    
    
    # Switch Block
    sb_mux: c_ds.Block = None
    sb_muxes: List[sb_mux_lib.SwitchBlockMux] = None

    # Routing Wire Load Circuits
    gen_routing_wire_loads: List[gen_r_load_lib.RoutingWireLoad] = None
    gen_ble_output_loads: List[gen_r_load_lib.GeneralBLEOutputLoad] = None

    # Connection Block
    cb_mux: c_ds.Block = None
    cb_muxes: List[cb_mux_lib.ConnectionBlockMux] = None

    # Logic Cluster (higher level group of sizeable ckts)
    logic_cluster: c_ds.Block = None
    logic_clusters: List[lb_lib.LogicCluster] = None

    # Local Interconnect
    local_mux: c_ds.Block = None # Unused TODO remove if necessary
    local_muxes: List[lb_lib.LocalMux] = None
    local_routing_wire_loads: List[lb_lib.LocalRoutingWireLoad] = None
    local_ble_output_loads: List[lb_lib.LocalBLEOutputLoad] = None

    # BLE
    local_ble_outputs: List[ble_lib.LocalBLEOutput] = None
    general_ble_outputs: List[ble_lib.GeneralBLEOutput] = None    
    lut_output_loads: List[ble_lib.LUTOutputLoad] = None
    flut_muxes: List[ble_lib.FlutMux] = None
    flip_flops: List[ble_lib.FlipFlop] = None

    # LUT
    lut: c_ds.Block = None
    luts: List[lut_lib.LUT] = None

    # LUT Input Drivers
    lut_inputs: Dict[str, List[lut_lib.LUTInput]] = None
    lut_input_drivers: Dict[str, List[lut_lib.LUTInputDriver]] = None
    lut_input_not_drivers: Dict[str, List[lut_lib.LUTInputNotDriver]] = None
    lut_input_driver_loads: Dict[str, List[lut_lib.LUTInputDriverLoad]] = None

    # Carry Chain Circuits
    carry_chains: List[cc_lib.CarryChain] = None
    carry_chain_periphs: List[cc_lib.CarryChainPer] = None               
    carry_chain_muxes: List[cc_lib.CarryChainMux] = None
    carry_chain_inter_clusters: List[cc_lib.CarryChainInterCluster] = None
    carry_chain_skip_ands: List[cc_lib.CarryChainSkipAnd] = None
    carry_chain_skip_muxes: List[cc_lib.CarryChainSkipMux] = None

    # Ram Circuits
    # TODO consolidate into a single object and conform to format used by other circuits
    RAM: ram_lib._RAM = None
    # RAM: ram_lib.RAM = None
    
    # Circuits contained within RAM
    # pgate_output_crossbars: List[ram_lib.PgateOutputCrossbar] = None
    # configurable_decoder_iiis: List[ram_lib.ConfigurableDecoderIII] = None
    # configurable_decoder_2iis: List[ram_lib.ConfigurableDecoderII] = None
    # configurable_decoder_3iis: List[ram_lib.ConfigurableDecoderII] = None



    # Hard Block Circuits
    hardblocklist: List[hb_lib._hard_block] = None

    # FPGA Specifications required in later functions
    specs: c_ds.Specs = None
    
    ##########################################################
    ### INITIALIZE OTHER VARIABLES, LISTS AND DICTIONARIES ###
    ##########################################################

    area_opt_weight: int = None
    delay_opt_weight: int = None
    # This is a dictionary of all the transistor sizes in the FPGA ('name': 'size')
    # It will contain the data in xMin transistor width, e.g. 'inv_sb_mux_1_nmos': '2'
    # That means inv_sb_mux_1_nmos is a transistor with 2x minimum width
    transistor_sizes: Dict[str, float | int] = field(
        default_factory=lambda: {}
    )
    # This is a list of tuples containing area information for each transistor in the FPGA
    # Tuple: (tran_name, tran_channel_width_nm, tran_drive_strength, tran_area_min_areas, tran_area_nm, tran_width_nm)
    transistor_area_list: list[Tuple[str, float, int, float, float, float]] = field(
        default_factory=lambda: []
    )
    
    # A note on the following 5 dictionaries
    # (area_dict, width_dict, wire_lengths, wire_layers, wire_rc_dict)
    #
    # Transistor sizes and wire lengths are needed at many different places in the SPICE netlists
    # that COFFE creates (e.g. the size of a particular transistor might be needed in many 
    # different files or multiple times in the same file). Since it would be a pain to have to 
    # go through every single line in every single file each time we want to change the size of 
    # a transistor (which will happen many thousands of times), COFFE inserts variables in the
    # SPICE netlists that it creates. These variables, which describe transistor sizes and wire 
    # loads, are assigned values in external files (one file for transistor sizes, one for wire loads). 
    # That way, when we change the size of a transistor (or a wire load), we only need to change
    # it in one place, and this change is seen by all SPICE netlists. 
    # The data structures that COFFE uses to keep track of transistor/circuit areas and wire data 
    # use a similar philosophy. That is, the following 5 dictionaries contain information about 
    # all element in the FPGA (all in one place). For ex., if we want to know the area of a switch block
    # multiplexer we ask 'area_dict' (e.g. area_dict['sb_mux']). One of the reasons for doing this
    # is that it makes outputing this data easier. For example, when we want to update that 'wire
    # load file' that the SPICE netlists use, all we need to do is write out wire_rc_dict to that file.
    # But, the 'fpga' object does not know how to update the area and wire data of each subcircuit.
    # Therefore, these dictionaries will be passed into member objects who will populate them as needed.
    # So, that's just something to keep in mind as you go through this code. You'll likely see these
    # dictionaries a lot.
    #
    # This is a dictionary that contains the area of everything for all levels of hierarchy in the FPGA. 
    # It has transistor area, inverter areas, mux areas, switch_block area, tile area.. etc. 
    # ('entity_name': area) All these areas are in nm^2
    area_dict: Dict[str, float] = field(
        default_factory=lambda: {}
    )
    # This is a dictionary that contains the width of everything (much like area_dict has the areas).
    # ('entity_name': width) All widths are in nm. The width_dict is useful for figuring out wire lengths.
    width_dict: Dict[str, float] = field(
        default_factory=lambda: {}
    )
    # This dictionary contains the lengths of all the wires in the FPGA. ('wire_name': length). Lengths in nm.
    wire_lengths: Dict[str, float] = field(
        default_factory=lambda: {}
    )
    # This dictionary contains the metal layer for each wire. ('wire_name': layer)
    # The layer number (an int) is an index that will be used to select the right metal data
    # from the 'metal_stack' (list described below).
    wire_layers: Dict[str, int] = field(
        default_factory=lambda: {}
    )
    # This dictionary contains wire resistance and capacitance for each wire as a tuple ('wire_name': (R, C))
    wire_rc_dict: Dict[str, float] = field(
        default_factory=lambda: {}
    )
    
    # This dictionary contains the delays of all subcircuits (i.e. the max of rise and fall)
    # Contrary to the above 5 dicts, this one is not passed down into the other objects.
    # This dictionary is updated by calling 'update_delays()'
    delay_dict: Dict[str, float] = field(
        default_factory=lambda: {}
    )
    
    # Metal stack. Lowest index is lowest metal layer. COFFE assumes that wire widths increase as we use higher metal layers.
    # For example, wires in metal_stack[1] are assumed to be wider (and/or more spaced) than wires in metal_stack[0]
    # e.g. metal_stack[0] = (R0, C0)
    metal_stack: List[Tuple[float, float]] = None # self.specs.metal_stack
    
    # whether or not to use transmission gates
    use_tgate: bool = None # self.specs.use_tgate

    # This is the height of the logic block, once an initial floorplanning solution has been determined, it will be assigned a non-zero value.
    lb_height: float = None # 0.0



    ######################################
    ### INITIALIZE SPICE LIBRARY NAMES ###
    ######################################

    wire_RC_filename: str           = "wire_RC.l"
    process_data_filename: str      = "process_data.l"
    includes_filename: str          = "includes.l"
    basic_subcircuits_filename: str = "basic_subcircuits.l"
    subcircuits_filename: str       = "subcircuits.l"
    sweep_data_filename: str        = "sweep_data.l"


    ########################################
    ### DEFINE CIRCUIT BASENAMES FOR REF ###
    ########################################
    # sb_mux_basename: str = "sb_mux"
    # routing_wire_load_basename: str = "routing_wire_load"



    # These strings are used as the names of various spice subckts in the FPGA
    #   We define thier names here so we can reference them to Simulation TB classes 
    #   before we actually create the subckt objects

    def init_tb_subckt_libs(self):
        """
            Preconditions:
                - All fields with Type[c_ds.SizeableCircuit] objects are initialized
                - All fields with Type[c_ds.SimTB] objects are initialized
            Initialize the testbench & subcircuit libraries
        """
        # Init testbench lib
        tbs = []
        sizeable_ckts = []
        for _field in fields(self):
            cur_obj: Any = getattr(self, _field.name)
            # TODO refactor somewhere to allow for lists + non list definitions of tbs / subckts

            if isinstance(cur_obj, list) and len(cur_obj) > 0 and issubclass(type(cur_obj[0]), c_ds.SimTB):
                tbs += getattr(self, _field.name)
            # Looking for dicts of lists for input driver testbenches
            elif isinstance(cur_obj, dict) and len(cur_obj) > 0 and isinstance(list(cur_obj.values())[0], list) and len(list(cur_obj.values())[0]) > 0 and issubclass(type(list(cur_obj.values())[0][0]), c_ds.SimTB):
                tbs += [tb for tb_list in list(cur_obj.values()) for tb in tb_list]
            # look for sizeable ckts, stored in lists or dicts of lists (input drivers)
            if isinstance(cur_obj, list) and len(cur_obj) > 0 and issubclass(type(cur_obj[0]), c_ds.SizeableCircuit):
                sizeable_ckts += getattr(self, _field.name)            
            elif isinstance(cur_obj, dict) and len(cur_obj) > 0 and isinstance(list(cur_obj.values())[0], list) and len(list(cur_obj.values())[0]) > 0 and issubclass(type(list(cur_obj.values())[0][0]), c_ds.SizeableCircuit):
                sizeable_ckts += [ckt for ckt_list in list(cur_obj.values()) for ckt in ckt_list]

        # Soft assert there are no duplicate testbenches or sizeable circuits
        tb_set = set(tbs)
        ckt_set = set(sizeable_ckts)
        assert len(tb_set) == len(tbs), "Duplicate testbench objects found"
        assert len(ckt_set) == len(sizeable_ckts), "Duplicate sizeable circuit objects found"

        # Iterate through  
        self.tb_lib = defaultdict(list)
        tb: Type[c_ds.SimTB]
        for tb in tbs:
            assert tb.dut_ckt is not None, "Testbench must have a DUT circuit"
            # TODO make this more general (not hacky), we just want to not use the LUTInputTB for transistor sizing which is why we exclude it here
            if not "with_lut_tb" in tb.tb_fname:
                self.tb_lib[tb.dut_ckt].append(tb)
            else:
                print(f"Excluding {tb.tb_fname} from tb_lib")

        



    def __post_init__(self, coffe_info: rg_ds.Coffe):
        """ 
            Post init function for FPGA class. 
            This function is called after the FPGA class is initialized.
            It is responsible for setting up the FPGA object with all the subcircuit models and subcircuit library.
        """

        # Telemetry Info
        self.log_out_catagories = [
            "wire_length",
            "area",
            "tx_size",
            "delay",
        ]

        # TODO refactor
        consts.PASSTHROUGH_DEBUG_FLAG = self.run_options.pass_through

        # TODO refactor
        # Optimization Weights
        self.area_opt_weight = self.run_options.area_opt_weight
        self.delay_opt_weight = self.run_options.delay_opt_weight

        # Init Specs
        self.specs = c_ds.Specs(
            coffe_info.fpga_arch_conf["fpga_arch_params"], 
            self.run_options.quick_mode
        )

        # Global Setting inits
        self.metal_stack = self.specs.metal_stack
        self.use_tgate = self.specs.use_tgate

        # Init height of logic block to 0 (representing uninitialized)
        # TODO update all initializations to None instead of some other value

        # All general routing wires in the FPGA 
        self.gen_r_wires: Dict[str, c_ds.GenRoutingWire] = {}
        # Parse the rrg_file if its passed in and put results into the specs
        if coffe_info.rrg_data_dpath:
            #   ___  _   ___  ___ ___   ___  ___  _   _ _____ ___ _  _  ___     _     ___ ___   __  __ _   ___  __  ___ _  _ ___ ___  
            #  | _ \/_\ | _ \/ __| __| | _ \/ _ \| | | |_   _|_ _| \| |/ __|  _| |_  / __| _ ) |  \/  | | | \ \/ / |_ _| \| | __/ _ \ 
            #  |  _/ _ \|   /\__ \ _|  |   / (_) | |_| | | |  | || .` | (_ | |_   _| \__ \ _ \ | |\/| | |_| |>  <   | || .` | _| (_) |
            #  |_|/_/ \_\_|_\|___/___| |_|_\\___/ \___/  |_| |___|_|\_|\___|   |_|   |___/___/ |_|  |_|\___//_/\_\ |___|_|\_|_| \___/ 
            rrg_data_dpath: str = coffe_info.rrg_data_dpath
            seg_csv_fpath = os.path.join(rrg_data_dpath, "rr_segments.csv")
            sw_csv_fpath = os.path.join(rrg_data_dpath, "rr_switches.csv")
            wire_stats_fpath = os.path.join(rrg_data_dpath, "rr_wire_stats.csv")
            mux_freq_fpath = os.path.join(rrg_data_dpath, "rr_mux_freqs.csv")
            # Get mux freqs
            mux_freqs = defaultdict(dict)
            for mux_freq in rg_utils.read_csv_to_list(mux_freq_fpath):
                mux_freqs[mux_freq["SWITCH_TYPE"].lower()]['freq'] = int(mux_freq["FREQ"])
                mux_freqs[mux_freq["SWITCH_TYPE"].lower()]['freq_per_tile'] = int(round(float(mux_freq["FREQ_PER_TILE"])))
            # Get in RR segment data
            rr_segments: List[c_ds.SegmentRRG] = []
            for in_rr_segment in rg_utils.read_csv_to_list(seg_csv_fpath):
                rr_segment: c_ds.SegmentRRG = rg_utils.typecast_input_to_dataclass(
                    in_rr_segment,
                    c_ds.SegmentRRG
                )
                rr_segments.append(rr_segment)
            rr_switches: List[c_ds.SwitchRRG] = []
            for in_rr_sw in rg_utils.read_csv_to_list(sw_csv_fpath):
                rr_sw: c_ds.SwitchRRG = rg_utils.typecast_input_to_dataclass(
                    in_rr_sw,
                    c_ds.SwitchRRG
                )
                rr_switches.append(rr_sw)
            # drv_type: num_of_this_mux

            rr_wire_stats: List[dict] = rg_utils.read_csv_to_list(wire_stats_fpath)
            
            mux_stats: List[c_ds.MuxWireStatRRG] = []
            mux_loads: Dict[str, List[c_ds.MuxLoadRRG]] = defaultdict(list)
            mux_ipins: Dict[str, List[c_ds.MuxIPIN]] = defaultdict(list)
            total_mux_inputs: Dict[str, int] = {}
            total_mux_loads: Dict[str, int] = {}

            # list of all possible drive types in csv
            # drv_types: List[str] = list(set([wire_stat["DRV_TYPE"].lower() for wire_stat in rr_wire_stats]))
            # wire_types: List[str] = list(set([wire_stat["WIRE_TYPE"].lower() for wire_stat in rr_wire_stats]))
            drv_wire_pairs: Set[Tuple[str]] = set()
            # Seperate the input wire statistics into wire types
            for wire_stat in rr_wire_stats:
                # Create a WireStatRRG object for each combination of DRV and WIRE types (Assumpion only one drv type per wire type)
                stat_type = str(wire_stat["COL_TYPE"]).lower()
                wire_drv_type = str(wire_stat["DRV_TYPE"]).lower()
                wire_type: str = (wire_stat["WIRE_TYPE"]) # Not lowered as its matching name in config.yml
                # Check if this is component or total fanout
                drv_wire_pairs.add((wire_drv_type, wire_type))
                # Mux load from fanout info
                if "fanout" in stat_type:
                    drv_type = stat_type.replace("fanout_","").lower()
                    if drv_type in stat_type and "total" not in drv_type:
                        # this is component fanout
                        mux_load = c_ds.MuxLoadRRG(
                            wire_type = wire_type,
                            mux_type = drv_type,
                            freq=int(round(float(wire_stat["mean"])))
                        )
                        mux_loads[wire_type].append(mux_load)
                    elif "total" in stat_type:
                        # For total fanout / fanin values
                        total_mux_loads[wire_type] = int(round(float(wire_stat["mean"])))
                    else:
                        assert False, f"Unknown stat_type {stat_type} in wire_stats.csv"
                elif "fanin" in stat_type:
                    drv_type = stat_type.replace("fanin_num_","").lower()
                    if drv_type in stat_type and "total" not in drv_type:
                        # this is component fanin
                        mux_ipin = c_ds.MuxIPIN(
                            wire_type=wire_type,
                            drv_type=drv_type,
                            freq=int(round(float(wire_stat["mean"])))
                        )
                        mux_ipins[wire_type].append(mux_ipin)
                    elif "total" in stat_type:
                        # For total fanout / fanin values
                        total_mux_inputs[wire_type] = int(round(float(wire_stat["mean"])))
                    else:
                        assert False, f"Unknown stat_type {stat_type} in wire_stats.csv"
                else:
                    assert False, f"Unknown stat_type {stat_type} in wire_stats.csv"
            
            for wire_type in mux_loads.keys():
                drv_wire_pair: Tuple[str] = [drv_wire_pair for drv_wire_pair in drv_wire_pairs if drv_wire_pair[1] == wire_type][0]
                # We need to fix the wire types of MUX IPINs as they are showing up as the type of driven wires
                # TODO fix this later in another way
                drv_type: str = drv_wire_pair[0]
                mux_freq_per_tile: int = int(mux_freqs[drv_type]['freq_per_tile'])
                mux_freq: int = int(mux_freqs[drv_type]['freq'])

                assert wire_type == drv_wire_pair[1], f"Wire type {wire_type} does not match drv type {drv_type}"
                # Create a WireStatRRG object for each wire types
                mux_stat = c_ds.MuxWireStatRRG(
                    wire_type=wire_type,
                    drv_type=drv_type,
                    mux_ipins=mux_ipins[wire_type],
                    mux_loads=mux_loads[wire_type],
                    num_mux_per_tile = mux_freq_per_tile,
                    num_mux_per_device = mux_freq
                    # total_mux_inputs=total_mux_inputs[wire_type],
                    # total_wire_loads=total_mux_loads[wire_type]
                )
                mux_stats.append(mux_stat)


            # Convience mapping of RRG driver names to RRG Segment names
            drv_2_seg_lookup: Dict[str, str] = {}
            seg_2_drv_lookup: Dict[str, str] = {}
            # Match up our parsed information for wire information with the wire RC 
            for i, wire_type in enumerate(self.specs.wire_types):
                for seg in rr_segments:
                    if seg.name == wire_type["name"]:
                        # Get number of these wires in a channel from user input in wire_type
                        freq: int = wire_type.get("freq")
                        # Find the corresponding mux_stat
                        mux_stat: c_ds.MuxWireStatRRG = [mux_stat for mux_stat in mux_stats if mux_stat.wire_type == wire_type["name"]][0]
                        drv_2_seg_lookup[mux_stat.drv_type] = seg.name
                        seg_2_drv_lookup[seg.name] = mux_stat.drv_type
                        # Convert mux_stat to use sb_mux ids rather than wire / drv names from RRG
                        gen_r_wire = c_ds.GenRoutingWire(
                            id=i, # Uses index of this wire_type in conf.yml file
                            length=seg.length,
                            type=seg.name,
                            num_starting_per_tile = mux_stat.num_mux_per_tile, # TODO take this out of gen_r_wires and put it somewhere that makes more sense
                            freq=freq,
                            layer=int(wire_type["metal"]),
                        )
                        # Hash dict with RRG / wire_type segment name
                        self.gen_r_wires[seg.name] = gen_r_wire
            # Create a Wire type for each drv type in our mux ipins
            sb_muxes_src_wires: Dict[str, Dict[c_ds.Wire, int]] = defaultdict(dict)
            for i, mux_stat in enumerate(mux_stats):
                for mux_ipin in mux_stat.mux_ipins:
                    # If we can't find the drv type of this mux ipin in our list of switches then we assume its an LB Output pin
                    # TODO fix this to work if the key is different than lb_opin from CSV (this was an arbitrary choice in rr_parse.py)
                    if mux_ipin.drv_type == "lb_opin":
                        # LB output pin type
                        src_wire = c_ds.Wire(
                            id=0,
                            name="wire_general_ble_output_load",
                            layer=constants.LOCAL_WIRE_LAYER,
                        )
                        sb_muxes_src_wires[mux_stat.wire_type][src_wire] = mux_ipin.freq
                    # This is a general routing wire that already exists
                    else:
                        src_wire: c_ds.GenRoutingWire = self.gen_r_wires[drv_2_seg_lookup[mux_ipin.drv_type]]
                        sb_muxes_src_wires[mux_stat.wire_type][src_wire] = mux_ipin.freq
            
            # NOTE: After this point we no longer use any RRG specific information, except for general routing wire names which are required in COFFE config file
        
            ##################################
            ### CREATE SWITCH BLOCK OBJECT ###
            ##################################
            # TODO figure out which params are basically inferred entirely from RRG
            #   It would not be logical to use RRG based parameters for routing and SB loading information
            #   While concurrently using user defined parameters affecting the same circuits
                        
            # Create switch block mux SizeableCircuit for each switch type listed in RRG
            self.sb_muxes: List[sb_mux_lib.SwitchBlockMux] = []
            # Create Switch Block Mux Objects using the newly created loading information
            for i, wire_type in enumerate(sb_muxes_src_wires.keys()):
                sink_wire: c_ds.GenRoutingWire = self.gen_r_wires[wire_type]
                # TODO find a better fix for this but RRG was giving like close but not quite enough of the expected SB per tile, so we will use below formula instead
                num_sb_per_tile: int = int( 4 * sink_wire.freq // (2 * sink_wire.length) )

                # Required size inferred from src_wires
                # num_sb_per_tile inferred from sink_wire.num_starting_per_tile -> from RRG
                sb_mux = sb_mux_lib.SwitchBlockMux(
                    id = i,
                    src_wires = sb_muxes_src_wires[wire_type],
                    sink_wire = self.gen_r_wires[wire_type],
                    num_per_tile = num_sb_per_tile,
                    use_tgate = self.specs.use_tgate,
                )
                self.sb_muxes.append(sb_mux)
            self.sb_mux = c_ds.Block(
                ckt_defs = self.sb_muxes,
                total_num_per_tile = sum([sb_mux.num_per_tile for sb_mux in self.sb_muxes])
            )
            ######################################
            ### CREATE CONNECTION BLOCK OBJECT ###
            ######################################
            self.cb_muxes: List[cb_mux_lib.ConnectionBlockMux] = []
            # Calculate connection block mux size
            cb_mux_size_required = int(self.specs.W * self.specs.Fcin)
            num_cb_mux_per_tile = self.specs.I
            # Initialize the connection block
            
            cb_mux = cb_mux_lib.ConnectionBlockMux(
                id = 0,
                required_size = cb_mux_size_required,
                num_per_tile = num_cb_mux_per_tile,
                use_tgate = self.specs.use_tgate,
                # self.sb_muxes[0], self.gen_routing_wire_loads[0]
            )
            self.cb_muxes.append(cb_mux)
            self.cb_mux = c_ds.Block(
                ckt_defs = self.cb_muxes,
                total_num_per_tile = sum([cb_mux.num_per_tile for cb_mux in self.cb_muxes])
            )
            ###########################
            ### CREATE LOAD OBJECTS ###
            ###########################
            # Create Dict holding the % distributions of logic block outputs per mux type
            #   For each BLE output, what is the chance that its going into each mux type? 
            ble_sb_mux_load_dist: Dict[sb_mux_lib.SwitchBlockMux, float] = {}
            ble_sb_mux_load_freq: Dict[sb_mux_lib.SwitchBlockMux, int] = {}
            sb_mux: sb_mux_lib.SwitchBlockMux
            for sb_mux in self.sb_muxes:
                # Check to see if this takes the general_ble_output wire as an input, this means its loading BLEs
                for src_wire, src_wire_freq in sb_mux.src_wires.items():
                    # TODO ideally we wouldn't be using the name of a wire to determine if its a BLE output load but fine for now
                    if src_wire.name == "wire_general_ble_output_load":
                        ble_sb_mux_load_freq[sb_mux] = src_wire_freq
                        # Break because we only care about ble output wires
                        break
            # Calculate the distribution of BLE outputs per SB Mux
            for sb_mux, freq in ble_sb_mux_load_freq.items():
                ble_sb_mux_load_dist[sb_mux] = freq / sum(ble_sb_mux_load_freq.values())
            # Use the distribution to create the BLE Output Load Circuits
            self.gen_ble_output_loads: List[gen_r_load_lib.GeneralBLEOutputLoad] = []
            # TODO bring this to the user level
            # For now we will pick whatever SB mux has the most BLE outputs as inputs to determine which SB mux should be ON in the load
            #   And we assume fanout is 1, with a single SB Mux being ON
            most_likely_on_sb: sb_mux_lib.SwitchBlockMux = max(ble_sb_mux_load_freq, key=ble_sb_mux_load_freq.get)
            sb_mux_on_assumption_freqs: Dict[sb_mux_lib.SwitchBlockMux, int] = { most_likely_on_sb: 1 }
            # Even with multiple SB types we will still create a single BLE output load, containing each type of SB Mux that could act as a load
            ble_output_load: gen_r_load_lib.GeneralBLEOutputLoad = gen_r_load_lib.GeneralBLEOutputLoad(
                id = 0,
                channel_usage_assumption = constants.CHAN_USAGE_ASSUMPTION,
                sb_mux_on_assumption_freqs = sb_mux_on_assumption_freqs,
                sb_mux_load_dist = ble_sb_mux_load_dist
            )
            # We still keep to format of having list for every circuit and during simulation doing some user defined sweep (geometric, linear, etc.) over circuit list combos
            self.gen_ble_output_loads.append(ble_output_load) 

            # Convert fanout information from RRG into a Dict[c_ds.GenRoutingWire, Dict[sb_mux_lib.SwitchBlockMux, Dict[str, int] ] ]
            # The inner most dict will have keys "freq" and "ISBD"

            # TODO implement "ISBD" type metrics from parsing RR_graph data
            # Stores the frequency of sb_mux loads per type of GenRoutingWire
            sb_mux_load_freqs: Dict[
                c_ds.GenRoutingWire, 
                Dict[sb_mux_lib.SwitchBlockMux, int]
            ] = {}
            # Stores the frequency of cb_mux loads per type of GenRoutingWire
            cb_mux_load_freqs: Dict[
                c_ds.GenRoutingWire,
                Dict[cb_mux_lib.ConnectionBlockMux, int]
            ] = {}
            # Again assuming 1 gen_r_wire per 1 SB Mux drive type
            # Iterate over the Muxes driving each general routing wire
            sb_mux: sb_mux_lib.SwitchBlockMux
            for sb_mux in self.sb_muxes:
                gen_r_wire: c_ds.GenRoutingWire = sb_mux.sink_wire
                # Using this wire type find the fanout information stored in mux_stats
                mux_stat: c_ds.MuxWireStatRRG = [mux_stat for mux_stat in mux_stats if mux_stat.wire_type == gen_r_wire.type][0]
                # This convient line initalizes the dictionary if its empty at sb_mux, and will 
                sb_mux_load_freqs[gen_r_wire] = {}
                cb_mux_load_freqs[gen_r_wire] = {}
                # Iterate over SB Muxes which are driving the muxes loading this gen_r_wire
                load_info: c_ds.MuxLoadRRG
                # TODO Look for CB_IPIN loads here
                for load_info in mux_stat.mux_loads:
                    # Find in our existing SB muxes which has the same wire_type as the sb_mux_load
                    if load_info.mux_type == "ipin_cblock":
                        # TODO update for multiple CBs
                        cb_mux_load_freqs[gen_r_wire][self.cb_muxes[0]] = load_info.freq
                    else:
                        # Define the condition which we want to match a unique object with
                        def condition(sb_mux: sb_mux_lib.SwitchBlockMux) -> bool:
                            return sb_mux.sink_wire.type == drv_2_seg_lookup[load_info.mux_type]
                        sb_mux_load: sb_mux_lib.SwitchBlockMux = rg_utils.get_unique_obj(
                            self.sb_muxes,
                            condition,
                        )
                        # Now we can create the dict entry for this gen_r_wire and sb_mux_load
                        sb_mux_load_freqs[gen_r_wire][sb_mux_load] = load_info.freq

            # Iterate over CB muxes and determine which is capable of having taking each gen_r_wire as an input
            # Create the Routing Wire Load Objects
            self.gen_routing_wire_loads: List[gen_r_load_lib.RoutingWireLoad] = []
            # TODO init a similar input as sb_mux_load_freqs except for cb_mux_load_freqs as current version only requires the cb_mux_load_freqs to have all valid cb_muxes as keys
            
            # Connection block mux load freq, TODO make the freq portion accurate and not a stand in, just putting 1 in for now but its not correct OR used
            # cb_mux_load_freqs: Dict[cb_mux_lib.ConnectionBlockMux, int] = { cb_mux: 1 for cb_mux in self.cb_muxes }
            gen_r_wire: c_ds.GenRoutingWire
            cur_id: int = 0
            for i, gen_r_wire in enumerate(sb_mux_load_freqs.keys()):
                # Pass all possible terminal SB muxes and create a RoutingWireLoad object for each
                # Make sure that its a valid terminal SB mux by checking to see if the gen_r_wire is in the SB Mux's src_wires
                terminal_sb_muxes: List[sb_mux_lib.SwitchBlockMux] = [sb_mux for sb_mux in self.sb_muxes if gen_r_wire in sb_mux.src_wires.keys()] 
                term_sb_mux: sb_mux_lib.SwitchBlockMux
                for term_sb_mux in terminal_sb_muxes:
                    # Create the RoutingWireLoad object
                    routing_wire_load: gen_r_load_lib.RoutingWireLoad = gen_r_load_lib.RoutingWireLoad(
                        id = cur_id,
                        channel_usage_assumption = constants.CHAN_USAGE_ASSUMPTION,
                        cluster_input_usage_assumption = constants.CLUSTER_INPUT_USAGE_ASSUMPTION,
                        gen_r_wire = gen_r_wire,
                        sb_mux_load_freqs = sb_mux_load_freqs[gen_r_wire],
                        cb_mux_load_freqs = cb_mux_load_freqs[gen_r_wire],
                        terminal_sb_mux = term_sb_mux,  
                        terminal_cb_mux = self.cb_muxes[0],         # TODO accomodate multiple types of CBs if they exist    
                    )
                    cur_id += 1

                    # Append to the list of RoutingWireLoads
                    self.gen_routing_wire_loads.append(routing_wire_load)

            ###################################
            ### CREATE LOGIC CLUSTER OBJECT ###
            ###################################
            
            # Local mux size is (inputs + feedback) * population
            local_mux_size_required: int = int((self.specs.I + self.specs.num_ble_local_outputs * self.specs.N) * self.specs.Fclocal)
            num_local_mux_per_tile: int = self.specs.N * (self.specs.K + self.specs.independent_inputs)

            # TODO write what this means, is a param for carry chain
            inter_wire_length: float = 0.5
            # TODO make these params
            self.skip_size: int = 5
            self.carry_skip_periphery_count: int = 0
            if self.specs.enable_carry_chain == 1 and self.specs.carry_chain_type == "skip":
                self.carry_skip_periphery_count = int(math.floor((self.specs.N * self.specs.FAs_per_flut)/self.skip_size))
            ##################################
            ### CREATE CARRY CHAIN OBJECTS ###
            ##################################
            self.carry_chains = []
            self.carry_chain_periphs = []
            self.carry_chain_muxes = []
            self.carry_chain_inter_clusters = []
            if self.specs.enable_carry_chain == 1:
                carrychainperiph = cc_lib.CarryChainPer(
                    id = 0,
                    use_tgate = self.specs.use_tgate,
                    use_finfet = self.specs.use_finfet, 
                )
                self.carry_chain_periphs.append(carrychainperiph)
                carrychain = cc_lib.CarryChain(
                    id = 0,
                    cluster_size = self.specs.N, 
                    FAs_per_flut = self.specs.FAs_per_flut,
                    use_finfet = self.specs.use_finfet,
                    carry_chain_periph = self.carry_chain_periphs[0], # TODO update for multi ckt support
                )
                self.carry_chains.append(carrychain)
                carrychainmux = cc_lib.CarryChainMux(
                    id = 0,
                    use_fluts = self.specs.use_fluts,
                    use_tgate = self.specs.use_tgate,
                    use_finfet = self.specs.use_finfet, 
                )
                self.carry_chain_muxes.append(carrychainmux)
                carrychaininter = cc_lib.CarryChainInterCluster(
                    id = 0,
                    use_finfet = self.specs.use_finfet, 
                    carry_chain_type = self.specs.carry_chain_type,    
                    inter_wire_length = inter_wire_length,
                )
                self.carry_chain_inter_clusters.append(carrychaininter)
                if self.specs.carry_chain_type == "skip":
                    self.carry_chain_skip_muxes = []
                    self.carry_chain_skip_ands = []
                    carrychainand = cc_lib.CarryChainSkipAnd(
                        id = 0,
                        use_tgate = self.specs.use_tgate,
                        use_finfet = self.specs.use_finfet, 
                        carry_chain_type = self.specs.carry_chain_type,    
                        cluster_size = self.specs.N, 
                        FAs_per_flut = self.specs.FAs_per_flut,
                        skip_size = self.skip_size,
                    )
                    self.carry_chain_skip_ands.append(carrychainand)
                    carrychainskipmux = cc_lib.CarryChainSkipMux(
                        id = 0,
                        use_tgate = self.specs.use_tgate,
                        use_finfet = self.specs.use_finfet, 
                        carry_chain_type = self.specs.carry_chain_type,    
                    )
                    self.carry_chain_skip_muxes.append(carrychainskipmux)
            # Create a list for all Logic Clusters that could exist in device
            self.logic_clusters: List[lb_lib.LogicCluster] = []
            # Create a Logic Cluster Object
            logic_cluster: lb_lib.LogicCluster = lb_lib.LogicCluster(
                id = 0,
                # Local Mux Params
                local_mux_size_required = local_mux_size_required,
                num_local_mux_per_tile = num_local_mux_per_tile,
                # Cluster Params
                cluster_size = self.specs.N,
                num_lc_inputs = self.specs.I,
                # BLE Params
                num_inputs_per_ble = self.specs.K,
                num_fb_outputs_per_ble = self.specs.num_ble_local_outputs, # Ofb
                num_gen_outputs_per_ble = self.specs.num_ble_general_outputs, # Or
                Rsel = self.specs.Rsel,
                Rfb = self.specs.Rfb,

                enable_carry_chain = self.specs.enable_carry_chain,
                FAs_per_flut = self.specs.FAs_per_flut,
                carry_skip_periphery_count = self.carry_skip_periphery_count,

                use_tgate = self.specs.use_tgate,
                use_finfet = self.specs.use_finfet,
                use_fluts = self.specs.use_fluts,
                # Circuit dependancies
                cc = self.carry_chains[0] if self.specs.enable_carry_chain == 1 else None,
                cc_mux = self.carry_chain_muxes[0] if self.specs.enable_carry_chain == 1 else None,
                cc_skip_and = self.carry_chain_skip_ands[0] if self.specs.enable_carry_chain == 1 and self.specs.carry_chain_type == "skip" else None,
                cc_skip_mux = self.carry_chain_skip_muxes[0] if self.specs.enable_carry_chain == 1 and self.specs.carry_chain_type == "skip" else None,
            )
            self.logic_clusters.append(logic_cluster)
            # TODO make these individual instantiations rather than being derived from logic clusters
            
            # Local Interconnect
            self.local_muxes = [
                lc.local_mux for lc in self.logic_clusters
            ]
            self.local_mux = c_ds.Block(
                ckt_defs = self.local_muxes,
                total_num_per_tile = sum([lc.num_local_mux_per_tile for lc in self.logic_clusters])
            )
            self.local_routing_wire_loads = [
                lc.local_routing_wire_load for lc in self.logic_clusters
            ]
            self.local_ble_output_loads = [ 
                lc.local_ble_output_load for lc in self.logic_clusters
            ]
            # BLE
            self.local_ble_outputs = [
                lc.ble.local_output for lc in self.logic_clusters
            ]
            self.general_ble_outputs = [
                lc.ble.general_output for lc in self.logic_clusters
            ]
            self.lut_output_loads = [
                lc.ble.lut_output_load for lc in self.logic_clusters
            ]
            self.flut_muxes = [
                lc.ble.fmux for lc in self.logic_clusters
            ] 
            self.flip_flops = [ 
                lc.ble.ff for lc in self.logic_clusters 
            ]
            # LUT
            self.luts = [
                lc.ble.lut for lc in self.logic_clusters
            ]
            # LUT Inputs & LUT Input Driver & LUT Not input driver
            self.lut_inputs = defaultdict(list)
            self.lut_input_drivers = defaultdict(list)
            self.lut_input_not_drivers = defaultdict(list)
            for lc in self.logic_clusters:
                lut_in: lut_lib.LUTInput
                for lut_in in lc.ble.lut.input_drivers.values():
                    self.lut_inputs[lut_in.lut_input_key].append(lut_in)
                    self.lut_input_drivers[lut_in.lut_input_key].append(lut_in.driver)
                    self.lut_input_not_drivers[lut_in.lut_input_key].append(lut_in.not_driver)
                            
            #########################
            ### CREATE RAM OBJECT ###
            #########################
            # TODO update to dataclasses
            RAM_local_mux_size_required = float(self.specs.ram_local_mux_size)
            RAM_num_mux_per_tile = (3 + 2*(self.specs.row_decoder_bits + self.specs.col_decoder_bits + self.specs.conf_decoder_bits ) + 2** (self.specs.conf_decoder_bits))
            # NEW INST
            # self.RAM = ram_lib.RAM(
            #     use_tgate = self.specs.use_tgate,
            #     cspecs = self.specs,
            #     # SRAM params
            #     row_decoder_bits = self.specs.row_decoder_bits, 
            #     col_decoder_bits = self.specs.col_decoder_bits,
            #     conf_decoder_bits = self.specs.conf_decoder_bits,
            #     sram_area = self.specs.sram_cell_area * self.specs.min_width_tran_area,
            #     number_of_banks = self.specs.number_of_banks,
            #     process_data_filename = self.process_data_filename,
            #     memory_technology = self.specs.memory_technology,
            #     read_to_write_ratio = self.specs.read_to_write_ratio,
            #     # Local Mux Params
            #     RAM_local_mux_size_required = RAM_local_mux_size_required,
            #     RAM_num_local_mux_per_tile = RAM_num_mux_per_tile,
            # )
            # # Putting BRAM subcircuits into `FPGA` fields
            # # TODO bring these data structures back into top level of FPGA class to allow for full functionality
            # self.pgate_output_crossbars = [self.RAM.pgateoutputcrossbar]
            # self.configurable_decoder_3iis = [self.RAM.configurabledecoder3ii]
            # self.configurable_decoder_2iis = [self.RAM.configurabledecoder2ii]
            # self.configurable_decoder_iiis = [self.RAM.configurabledecoderiii]

            # OLD INST
            self.RAM = ram_lib._RAM(self.specs.row_decoder_bits, self.specs.col_decoder_bits, self.specs.conf_decoder_bits, RAM_local_mux_size_required, 
                RAM_num_mux_per_tile , self.specs.use_tgate, self.specs.sram_cell_area*self.specs.min_width_tran_area, self.specs.number_of_banks,
                self.specs.memory_technology, self.specs, self.process_data_filename, self.specs.read_to_write_ratio)
            self.number_of_banks = self.specs.number_of_banks

            
            ################################
            ### CREATE HARD BLOCK OBJECT ###
            ################################
            # TODO update to dataclasses
            self.hardblocklist = []
            # create hardblocks if the hardblock list is not None
            if coffe_info.hardblocks != None:
                # Check to see which mode of asic flow was specified by the user
                for hb_conf in coffe_info.hardblocks:
                    hard_block = hb_lib._hard_block(hb_conf, self.specs.use_tgate)
                    self.hardblocklist.append(hard_block)

        elif self.specs.wire_types:
            raise NotImplementedError("NON RRG specified wire types has not been fully supported yet")
            # TODO verify and integrate all below options to get legacy functionality back into COFFE without having to specify a RRG directory.
            # If user specifies sb muxes explicitly priorize that
            if self.specs.sb_muxes: 
                for i, sb_mux_conf in enumerate(self.specs.sb_muxes):
                    # How many inputs does this mux have
                    sb_mux_size_required: int = sum(int(val) for val in sb_mux_conf["srcs"].values()) + int(sb_mux_conf["lb_inputs"])
                    # Make sure its equal to user specified size
                    assert sb_mux_size_required == sb_mux_conf["size"]
                    # How many muxes drive this wire type
                    dst_wire: dict = self.specs.wire_types[sb_mux_conf["dst"]]
                    # Counting the number of muxes in the config with the same dst wire type
                    num_muxes_per_dst_wire: int = sum(1 for sb_mux_cmp in self.specs.sb_muxes if sb_mux_cmp["dst"] == sb_mux_conf["dst"])
                    # How many tracks is this mux type driving per SB
                    # TODO change name this is number of tracks per SB type
                    num_driven_tracks: int = int(dst_wire["num_tracks"] / num_muxes_per_dst_wire )
                    # I Don't think we need to consider the switch points in a wire type, those should be accounted for in the MUX size from user
                    # How many muxes of this type in a tile?
                    num_sb_mux_per_tile: int = int( 4 * num_driven_tracks // (2 * dst_wire["len"]) )
                    # Create the switch block mux
                    sb_mux_name = f"sb_mux_uid{i}"
                    self.sb_muxes.append(
                        _SwitchBlockMUX(sb_mux_conf["size"], num_sb_mux_per_tile, self.specs.use_tgate, sb_mux_name, self.specs.wire_types[sb_mux_conf["srcs"]], dst_wire)
                    )
            # if we specify multiple wire types, we need an Fs_mtx of quadratic length to specify each wire type Fs in switch block
            elif len(self.specs.wire_types)**2 == len(self.specs.Fs_mtx):
                # We create this many muxes that exist in the FPGA
                # <TAG><SWEEP GENERATE>
                No = self.specs.num_cluster_outputs
                # Calculate Mux size for each combination of wire types
                for i, Fs_ele in enumerate(self.specs.Fs_mtx):
                    # If the Fs is 0, it means we don't have a SB for this wire to wire connection type, ie don't create an SB mux 
                    if Fs_ele["Fs"] == 0:
                        continue
                    # use wire index of source wire for wire length
                    # This determines number of starting / non starting connections 
                    src_wire_length = self.specs.wire_types[Fs_ele["src"]]["len"] # wire going into SB
                    dst_wire_length = self.specs.wire_types[Fs_ele["dst"]]["len"] # wire driven from SB mux
                    r_to_r_sb_mux_size = self.specs.Fs + (self.specs.Fs-1) * (src_wire_length-1) # use the src wire length, as this determines the number of starting wires @ SB
                    # To calculate the num of sb muxes per side we first calculate the number of logic cluster opins per side
                    # dst_chan_width = dst_wire_type_fraction_of_channel * channel_width
                    # num_opins_per_side = cluster_outputs * Fcout * dst_chan_width / 2
                    # the above div by 2 is coming from half the cluster outputs being sent to SBs on each side of the LC (think of the channel above it)
                    # num_sb_muxes_per_side = dst_chan_width / 2 * src_wire_length
                    # the above div by 2 is from the unidirectional routing, meaning half of channel width is being driven 
                    # Below division by two is because we send our outputs to SBs on both sides (L/R) of the LC
                    clb_to_r_sb_mux_size = No * self.specs.Fcout * src_wire_length / 2 # should this be ceiled? TODO this needs to be updated to distribute these connections to the SBs
                    sb_mux_size_required = int(r_to_r_sb_mux_size + clb_to_r_sb_mux_size)
                    # Num tracks driven by this type of SB, if there are N wire types then there will be N^2 SBs, the sum of all SBs driving the same wire type should 
                    #       be equal to the number of tracks of that wire type, so we divide by the sqrt of the number of SBs to get the number of tracks driven by each SB
                    num_driven_tracks = int( self.specs.wire_types[Fs_ele["dst"]]["num_tracks"] / math.sqrt(len(self.specs.Fs_mtx)) )
                    # Calculate number of this switch block mux per tile
                    num_sb_mux_per_tile = 4 * num_driven_tracks // (2 * src_wire_length)
                    # above 4 factor is from number of sides of SB driving wires, 2 is from the unidirectional routing
                    # Sb mux names are based on wire type they are driving
                    sb_mux_name = f"sb_mux_uid{i}" # f"sb_mux_L{dst_wire_length}_Fs_uid{i}"
                    # Initialize the switch block, pass in our dst wire for the load
                    self.sb_muxes.append(
                        _SwitchBlockMUX(sb_mux_size_required, num_sb_mux_per_tile, self.specs.use_tgate, sb_mux_name, self.specs.wire_types[Fs_ele["src"]], self.specs.wire_types[Fs_ele["dst"]])
                    )

    def generate(self, size_hb_interfaces: bool):
        """ This function generates all SPICE netlists and library files. """
    
        # Here's a file-stack that shows how COFFE organizes its SPICE files.
        # We'll talk more about each one as we generate them below.
    
        # ---------------------------------------------------------------------------------
        # |                                                                               |
        # |                top-level spice files (e.g. sb_mux.sp)                         |
        # |                                                                               |
        # ---------------------------------------------------------------------------------
        # |                                                                               |
        # |                                includes.l                                     |
        # |                                                                               |
        # ---------------------------------------------------------------------------------
        # |                                                                               |
        # |                               subcircuits.l                                   |
        # |                                                                               |
        # ---------------------------------------------------------------------------------
        # |                         |                               |                     |
        # |     process_data.l      |     basic_subcircuits.l       |     sweep_data.l    |
        # |                         |                               |                     |
        # ---------------------------------------------------------------------------------
    
        # For our logging files we want to clear them on the invocation of COFFE in the arch_out_folder
        # Create empty file
        for cat_k in self.log_out_catagories:
            fd = open(f"{cat_k}_debug.csv", "w")
            fd.close()
        
        # Generate basic subcircuit library (pass-transistor, inverter, wire, etc.).
        # This library will be used to build other netlists.
        self._generate_basic_subcircuits()
        
        # Create 'subcircuits.l' library.
        # The subcircuit generation functions between 'self._create_lib_files()'
        # and 'self._end_lib_files()' will add things to these library files. 
        self._create_lib_files()
        
        # Generate the various subcircuits netlists of the FPGA (call members)
        sb_mux: sb_mux_lib.SwitchBlockMux
        for sb_mux in self.sb_muxes:
            self.transistor_sizes.update(
                sb_mux.generate(
                    self.subcircuits_filename
                )
            )
        cb_mux: cb_mux_lib.ConnectionBlockMux
        for cb_mux in self.cb_muxes:
            self.transistor_sizes.update(
                cb_mux.generate(
                    self.subcircuits_filename, 
                )
            )
        lc: lb_lib.LogicCluster
        for lc in self.logic_clusters:
            self.transistor_sizes.update(
                lc.generate(
                    self.subcircuits_filename, 
                    self.specs.min_tran_width,
                    self.specs,
                )
            )

       
        gen_ble_output_load: gen_r_load_lib.GeneralBLEOutputLoad
        for gen_ble_output_load in self.gen_ble_output_loads:
            gen_ble_output_load.generate(self.subcircuits_filename, self.specs)

        routing_wire_load: gen_r_load_lib.RoutingWireLoad
        for routing_wire_load in self.gen_routing_wire_loads:
            routing_wire_load.generate(self.subcircuits_filename, self.specs)
        
        if self.specs.enable_carry_chain == 1:
            for carrychain in self.carry_chains:
                self.transistor_sizes.update(carrychain.generate(self.subcircuits_filename))
            for carrychainperiph in self.carry_chain_periphs:
                self.transistor_sizes.update(carrychainperiph.generate(self.subcircuits_filename))
            for carrychainmux in self.carry_chain_muxes:
                self.transistor_sizes.update(carrychainmux.generate(self.subcircuits_filename))
            for carrychaininter in self.carry_chain_inter_clusters:
                self.transistor_sizes.update(carrychaininter.generate(self.subcircuits_filename))
            if self.specs.carry_chain_type == "skip":
                for carrychainand in self.carry_chain_skip_ands:
                    self.transistor_sizes.update(carrychainand.generate(self.subcircuits_filename))
                for carrychainskipmux in self.carry_chain_skip_muxes:
                    self.transistor_sizes.update(carrychainskipmux.generate(self.subcircuits_filename))

        if self.specs.enable_bram_block == 1:
            self.transistor_sizes.update(self.RAM.generate(self.subcircuits_filename, self.specs.min_tran_width, self.specs))
        
        hardblock: hb_lib._hard_block
        for hardblock in self.hardblocklist:
            self.transistor_sizes.update(hardblock.generate(self.subcircuits_filename, self.specs.min_tran_width))
        
        # Add file footers to 'subcircuits.l' and 'transistor_sizes.l' libraries.
        self._end_lib_files()
        
        # Create SPICE library that contains process data and voltage level information
        self._generate_process_data()
        
        # This generates an include file. Top-level SPICE netlists only need to include
        # this 'include' file to include all libraries (for convenience).
        self._generate_includes()
        
        # Create the sweep_data.l file. COFFE will use this to perform multi-variable sweeps.
        self._generate_sweep_data()
        

        # Post generation of spice libraries we need to parse them into our data structures to be able to write the circuit testing environments
        # Setting up inputs for the parser function

        parser_args = [
            "--input_sp_files",  self.basic_subcircuits_filename, self.subcircuits_filename,
        ]
        self.subckt_lib = sp_parser.main(parser_args)

        # ████████╗███████╗███████╗████████╗██████╗ ███████╗███╗   ██╗ ██████╗██╗  ██╗███████╗███████╗
        # ╚══██╔══╝██╔════╝██╔════╝╚══██╔══╝██╔══██╗██╔════╝████╗  ██║██╔════╝██║  ██║██╔════╝██╔════╝
        #    ██║   █████╗  ███████╗   ██║   ██████╔╝█████╗  ██╔██╗ ██║██║     ███████║█████╗  ███████╗
        #    ██║   ██╔══╝  ╚════██║   ██║   ██╔══██╗██╔══╝  ██║╚██╗██║██║     ██╔══██║██╔══╝  ╚════██║
        #    ██║   ███████╗███████║   ██║   ██████╔╝███████╗██║ ╚████║╚██████╗██║  ██║███████╗███████║
        #    ╚═╝   ╚══════╝╚══════╝   ╚═╝   ╚═════╝ ╚══════╝╚═╝  ╚═══╝ ╚═════╝╚═╝  ╚═╝╚══════╝╚══════╝

        # Global definitions for all testbenches
        inc_libs: List[c_ds.SpLib] = [
            c_ds.SpLib(
                path = f"../{self.includes_filename}",
                inc_libs = ["INCLUDES"],
            )
        ]
        base_sim_mode: c_ds.SpSimMode = c_ds.SpSimMode(
            analysis = "TRAN",
            # TODO would be nice just to specify like "1ps" for the Value() and it to be parsed into proper fields
            sim_prec = c_ds.Value(1), # ps
            sim_time = c_ds.Value(8), # ns
            args = {
                "SWEEP": None,
                "DATA" : "sweep_data",
            }
        )
        sim_options: Dict[str, str] = {
            "BRIEF": "1",
            "POST": "1",
            "INGOLD":"1",
            "NODE":"1",
            "LIST":"1",
        }
        
        #   ___ ___   __  __ _   ___  __
        #  / __| _ ) |  \/  | | | \ \/ /
        #  \__ \ _ \ | |\/| | |_| |>  < 
        #  |___/___/ |_|  |_|\___//_/\_\

        # Based on legal connectivity possibilities between SB Muxes and Routing Wires
        # Create a testbench for each of such legal combinations 
        # Ex. 
        # - L4 SB Mux -> L4 -> L16 SB Mux
        # - L16 SB Mux -> L16 -> L4 SB Mux 
        # We may not want to simulate all of these options but we should have the ability to do so
        sb_mux_sim_mode: c_ds.SpSimMode = copy.deepcopy(base_sim_mode)
        # Certain simulations may run at lower / higher clock freqs? 
        #   The only reason I could see for this would be make sure the meas statements voltage triggers hit
        #   i.e. its probably important that we run sims at different clk freqs :)
        sb_mux_sim_mode.sim_time = c_ds.Value(8, units = sb_mux_sim_mode.sim_time.units) # ns

        print("Creating SB Mux TB Objects:")
        tb_idx: int = 0
        src_r_wire_load: gen_r_load_lib.RoutingWireLoad
        for src_r_wire_load in self.gen_routing_wire_loads:
            sink_r_wire_load: gen_r_load_lib.RoutingWireLoad
            for sink_r_wire_load in self.gen_routing_wire_loads:
                # Make sure this general routing wire load is driving the wire we expect
                if src_r_wire_load.terminal_sb_mux.sink_wire == sink_r_wire_load.gen_r_wire:
                    def condition(sb_mux: sb_mux_lib.SwitchBlockMux) -> bool:
                        return sb_mux.sink_wire == src_r_wire_load.gen_r_wire
                    start_sb_mux: sb_mux_lib.SwitchBlockMux = rg_utils.get_unique_obj(
                        self.sb_muxes,
                        condition,
                    )
                    # print((
                    #     f"{start_sb_mux.sink_wire.type} DUT[ -> "
                    #     f"{src_r_wire_load.terminal_sb_mux.sink_wire.type}] -> "
                    #     f"{sink_r_wire_load.terminal_sb_mux.sink_wire.type}"
                    # ))
                    # Create a testbench for this legal combination
                    sb_mux_tb = sb_mux_lib.SwitchBlockMuxTB(
                        id = tb_idx,
                        # SB Mux Specific args
                        start_sb_mux = start_sb_mux,
                        src_routing_wire_load = src_r_wire_load, 
                        sink_routing_wire_load = sink_r_wire_load,
                        # General SimTB args
                        inc_libs = inc_libs,
                        mode = sb_mux_sim_mode,
                        options = sim_options,
                        # Pass in library of all subckts 
                        subckt_lib = self.subckt_lib,
                    )
                    tb_idx += 1
                    # For now only append to the list for each uniq comb of src_routing_wire_load & sink_routing_wire_load
                    # ie ignore unique start sb_muxes
                    # TODO implement TB filtering somewhere else -> allow us to easily decide which testbenches to actually use vs ones that are legal but not important
                    # Only append if there is no existing TB with the same src and sink routing wire loads 
                    tb_cond: bool = False
                    for tb in self.sb_mux_tbs:
                        if tb.src_routing_wire_load.terminal_sb_mux.sink_wire == sb_mux_tb.src_routing_wire_load.terminal_sb_mux.sink_wire and\
                            tb.sink_routing_wire_load.terminal_sb_mux.sink_wire == sb_mux_tb.sink_routing_wire_load.terminal_sb_mux.sink_wire:
                            tb_cond = True
                    if not tb_cond:
                        self.sb_mux_tbs.append(sb_mux_tb)
        
        #    ___ ___   __  __ _   ___  __
        #   / __| _ ) |  \/  | | | \ \/ /
        #  | (__| _ \ | |\/| | |_| |>  < 
        #   \___|___/ |_|  |_|\___//_/\_\
        
        
        # Again the way we get all possible sim combinations would be to take the circuits in the testbench and combine them geometrically        
        print("Creating CB Mux TB Objects")
        
        gen_sim_mode: c_ds.SpSimMode = copy.deepcopy(base_sim_mode)
        gen_sim_mode.sim_time = c_ds.Value(4, units = sb_mux_sim_mode.sim_time.units) # ns
        
        # Num TBs = number of unique terminating CB muxes * num unique routing wire loads that can drive them * \
        #           * num unique terminating local muxes * num unique local routing wire load that can drive them
        
        # TODO implement for the above, but for now we're just going to assume we only have a single CB mux type in the device
        # Find all legal gen routing wire load components
        tb_gen_r_wire_loads: List[gen_r_load_lib.RoutingWireLoad] = []
        for cb_mux in self.cb_muxes:
            for gen_r_wire_load in self.gen_routing_wire_loads:
                # This filters out general routing wires which have terminal_cb_muxes inside thier struct, yet don't have them assigned
                # TODO really terminal muxes shouldn't be assigned to gen_r_wire_loads thats don't have them
                if gen_r_wire_load.terminal_cb_mux and gen_r_wire_load.terminal_cb_mux == cb_mux and \
                    gen_r_wire_load.tile_cb_load_assignments[0][gen_r_wire_load.terminal_cb_mux]["num_on"] > 0:
                    tb_gen_r_wire_loads.append(gen_r_wire_load)
                
        # TODO find all legal local routing wire loads that can be driven by the CB mux
        # We just assume as many types as we have logic clusters 
        # TODO circuits should be split up and indivdualized for more clarity + modularity
        tb_local_r_wire_loads: List[lb_lib.LocalRoutingWireLoad] = [
            lb.local_routing_wire_load for lb in self.logic_clusters
        ]
        tb_local_muxes: List[lb_lib.LocalMux] = [
            lb.local_mux for lb in self.logic_clusters
        ]
        # TODO make sure its ok to just use the "a" input driver for the SB mux testbench (but I think its fine)
        tb_lut_input_drivers: List[lb_lib.ble_lib.lut_lib.LUTInputDriver] = [
            lb.ble.lut.input_drivers["a"].driver for lb in self.logic_clusters
        ]
        # Create geometric product of these input circuits to get out all possible testbenches
        cb_tb_in_ckt_combos: List[
            Tuple[
                gen_r_load_lib.RoutingWireLoad, 
                lb_lib.LocalRoutingWireLoad, 
                lb_lib.LocalMux, 
                lb_lib.ble_lib.lut_lib.LUTInputDriver
            ]
        ] = list(
            itertools.product(
                tb_gen_r_wire_loads,
                tb_local_r_wire_loads, 
                tb_local_muxes, 
                tb_lut_input_drivers
            )
        )
        for tb_idx, cb_tb_in_ckt_combo in enumerate(cb_tb_in_ckt_combos):
            gen_r_wire_load: gen_r_load_lib.RoutingWireLoad = cb_tb_in_ckt_combo[0]
            local_r_wire_load: lb_lib.LocalRoutingWireLoad = cb_tb_in_ckt_combo[1]
            lut_input_driver: lb_lib.ble_lib.lut_lib.LUTInputDriver = cb_tb_in_ckt_combo[3]
            # Find SB mux driving the wire load
            def condition (sb_mux: sb_mux_lib.SwitchBlockMux) -> bool:
                return sb_mux.sink_wire == gen_r_wire_load.gen_r_wire
            # Its a continuous assertion that there is a 1:1 mapping between SB muxes and gen routing wires
            start_sb_mux: sb_mux_lib.SwitchBlockMux = rg_utils.get_unique_obj(
                self.sb_muxes,
                condition,
            )
            cb_mux_tb = cb_mux_lib.ConnectionBlockMuxTB(
                id = tb_idx,
                # CB Mux Specific args
                start_sb_mux = start_sb_mux,
                gen_r_wire_load = gen_r_wire_load,
                local_r_wire_load = local_r_wire_load,
                lut_input_driver = lut_input_driver,
                # General SimTB args
                inc_libs = inc_libs,
                mode = gen_sim_mode,
                options = sim_options,
                # Pass in library of all subckts 
                subckt_lib = self.subckt_lib,
            )
            self.cb_mux_tbs.append(cb_mux_tb)
            # LOGIC BLOCK TBs
            local_mux_tb = lb_lib.LocalMuxTB(
                id = tb_idx,
                # Local Mux Specific args
                # CB Mux Specific args
                start_sb_mux = start_sb_mux,
                gen_r_wire_load = gen_r_wire_load,
                local_r_wire_load = local_r_wire_load,
                lut_input_driver = lut_input_driver,
                # General SimTB args
                inc_libs = inc_libs,
                mode = gen_sim_mode, # 
                options = sim_options,
                # Pass in library of all subckts 
                subckt_lib = self.subckt_lib,
            )
            self.local_mux_tbs.append(local_mux_tb)

        #   _    ___   ___ ___ ___    ___ _   _   _ ___ _____ ___ ___ 
        #  | |  / _ \ / __|_ _/ __|  / __| | | | | / __|_   _| __| _ \
        #  | |_| (_) | (_ || | (__  | (__| |_| |_| \__ \ | | | _||   /
        #  |____\___/ \___|___\___|  \___|____\___/|___/ |_| |___|_|_\
        
        # Define our ckts that are used in tb
        tb_luts: List[lut_lib.LUT] = [ lb.ble.lut for lb in self.logic_clusters ]
        tb_lut_output_loads: List[ble_lib.LUTOutputLoad] = [ lb.ble.lut_output_load for lb in self.logic_clusters ]
        tb_gen_ble_output_loads: List[gen_r_load_lib.GeneralBLEOutputLoad] = self.gen_ble_output_loads

        # General BLE Output TB
        # TODO implement for all combinations, in the case which we have multiple individual circuit types in a logic cluster
        gen_ble_out_tb_in_ckts: List[
            Tuple[
                lut_lib.LUT, 
                ble_lib.LUTOutputLoad, 
                gen_r_load_lib.GeneralBLEOutputLoad, 
            ]
        ] = list(
            itertools.product(
                tb_luts,
                tb_lut_output_loads,
                tb_gen_ble_output_loads,
            )
        )
        for tb_idx, in_ckt_combo in enumerate(gen_ble_out_tb_in_ckts): 
            # Same combo used for local & general ble output tbs
            lut: lut_lib.LUT = in_ckt_combo[0]
            lut_output_load: ble_lib.LUTOutputLoad = in_ckt_combo[1]
            gen_ble_output_load: gen_r_load_lib.GeneralBLEOutputLoad = in_ckt_combo[2]
            # General BLE Output 
            gen_ble_out_tb = ble_lib.GeneralBLEOutputTB(
                id = tb_idx,
                # BLE Output Specific args
                lut = lut,
                lut_output_load = lut_output_load,
                gen_ble_output_load = gen_ble_output_load,
                # General SimTB args
                inc_libs = inc_libs,
                mode = gen_sim_mode,
                options = sim_options,
                # Pass in library of all subckts 
                subckt_lib = self.subckt_lib,
            )
            self.general_ble_output_tbs.append(gen_ble_out_tb)

            # LUT 
            lut_tb = lut_lib.LUTTB(
                id = tb_idx,
                lut = lut,
                lut_output_load = lut_output_load,
                # General SimTB args
                inc_libs = inc_libs,
                mode = gen_sim_mode,
                options = sim_options,
                # Pass in library of all subckts 
                subckt_lib = self.subckt_lib,
            )
            self.lut_tbs.append(lut_tb)

        loc_ble_out_tb_in_ckts: List[tuple] = list(
            itertools.product(
                tb_luts,
                tb_lut_output_loads,
                self.local_ble_output_loads,
            )
        )
        for tb_idx, in_ckt_combo in enumerate(loc_ble_out_tb_in_ckts):
            lut: lut_lib.LUT = in_ckt_combo[0]
            lut_output_load: ble_lib.LUTOutputLoad = in_ckt_combo[1]
            loc_ble_output_load: lb_lib.LocalBLEOutputLoad = in_ckt_combo[2]
            # Local BLE Output
            local_ble_output_tb = ble_lib.LocalBLEOutputTB(
                id = tb_idx,
                # BLE Output Specific args
                lut = lut,
                lut_output_load = lut_output_load,
                local_ble_output_load = loc_ble_output_load,
                # General SimTB args
                inc_libs = inc_libs,
                mode = gen_sim_mode,
                options = sim_options,
                # Pass in library of all subckts 
                subckt_lib = self.subckt_lib,
            )
            self.local_ble_output_tbs.append(local_ble_output_tb)
        # FLUT MUXES 
        # The circuit deps for the FlutMuxTB are a superset of those in gen_ble_output
        # TODO perform this conditional check for fluts at the ble level for more flexibility
        if self.specs.use_fluts: 
            tb_flut_muxes: List[ble_lib.FlutMux] = [ lb.ble.fmux for lb in self.logic_clusters ]
            tb_cc_muxes: List[cc_lib.CarryChainMux]
            tb_ccs: List[cc_lib.CarryChain]
            if self.specs.enable_carry_chain:
                tb_cc_muxes = self.carry_chain_muxes
                tb_ccs = self.carry_chains
            else:
                tb_cc_muxes = None
                tb_ccs = None 
            flut_in_ckts: List[tuple] = list(
                itertools.product(
                    tb_luts,
                    tb_flut_muxes,
                    tb_cc_muxes,
                    tb_ccs,
                    tb_lut_output_loads,
                    tb_gen_ble_output_loads,
                )
            )
            for tb_idx, in_ckt_combo in enumerate(flut_in_ckts):
                lut : lut_lib.LUT = in_ckt_combo[0]
                flut_mux: ble_lib.FlutMux = in_ckt_combo[1]
                cc_mux: cc_lib.CarryChainMux = in_ckt_combo[2]
                cc: cc_lib.CarryChain = in_ckt_combo[3]
                lut_output_load: ble_lib.LUTOutputLoad = in_ckt_combo[4]
                gen_ble_output_load: gen_r_load_lib.GeneralBLEOutputLoad = in_ckt_combo[5]
                flut_mux_tb = ble_lib.FlutMuxTB(
                    id = tb_idx,
                    # BLE Output Specific args
                    lut = lut,
                    flut_mux = flut_mux,
                    cc = cc,
                    cc_mux = cc_mux,
                    lut_output_load = lut_output_load,
                    gen_ble_output_load = gen_ble_output_load,
                    # General SimTB args
                    inc_libs = inc_libs,
                    mode = gen_sim_mode,
                    options = sim_options,
                    # Pass in library of all subckts 
                    subckt_lib = self.subckt_lib,
                )
                self.flut_mux_tbs.append(flut_mux_tb)

        tb_lut_input_drivers: List[ lut_lib.LUTInputDriver] = []
        tb_lut_input_not_drivers: List[ lut_lib.LUTInputNotDriver] = []

        # Get list of all possible input keys, ONLY WORKS FOR ONE LC
        # Assumes matching keys for all input drivers + not drivers + input drv loads
        # TODO get this to work for multiple LC types
        lut_input_keys: Set[str] = set([   
            key for lb in self.logic_clusters 
                for key in lb.ble.lut.input_drivers.keys() 
        ])

        ## For LCs with an arbitrary number of LUT inputs would do something like this
        # for lb in self.logic_clusters:
        #     for lut_in_key in lb.ble.lut.input_drivers.keys(): 
        #         tb_lut_input_drivers.append(
        #             lb.ble.lut.input_drivers[lut_in_key].driver
        #         )
        #         tb_lut_input_not_drivers.append(
        #             lb.ble.lut.input_drivers[lut_in_key].not_driver
        #         )

        # For each input key create a product of other circuits to get possible LUT configs
        for input_key in lut_input_keys:
            tb_cb_muxes: List[cb_mux_lib.ConnectionBlockMux] = [
                cb_mux for cb_mux in self.cb_muxes
            ]
            tb_ffs: List[ble_lib.FlipFlop] = [ 
                lb.ble.ff for lb in self.logic_clusters 
            ]
            # Assumes the driver loads are the same for all LUT inputs
            tb_lut_in_drv_loads: List[ lut_lib.LUTInputDriverLoad ] = [
                lb.ble.lut.input_driver_loads["a"] for lb in self.logic_clusters
            ]
            # For each instance of each driver of each key 
            tb_lut_input_drivers: List[ lut_lib.LUTInputDriver] = [
                lb.ble.lut.input_drivers[input_key].driver for lb in self.logic_clusters
            ]
            tb_lut_input_not_drivers: List[ lut_lib.LUTInputNotDriver] = [
                lb.ble.lut.input_drivers[input_key].not_driver for lb in self.logic_clusters
            ]
            lut_driver_tb_in_ckts: List[tuple] = list(
                itertools.product(
                    tb_cb_muxes,
                    tb_local_r_wire_loads,
                    tb_ffs,
                    tb_lut_input_drivers,
                    tb_lut_input_not_drivers,
                    tb_lut_in_drv_loads,
                )
            )
            for tb_idx, in_ckt_combo in enumerate(lut_driver_tb_in_ckts):
                cb_mux: cb_mux_lib.ConnectionBlockMux = in_ckt_combo[0]
                local_r_wire_load: lb_lib.LocalRoutingWireLoad = in_ckt_combo[1]
                ff: ble_lib.FlipFlop = in_ckt_combo[2]
                lut_in_driver: lut_lib.LUTInputDriver = in_ckt_combo[3]
                lut_in_not_driver: lut_lib.LUTInputNotDriver = in_ckt_combo[4]
                lut_in_driver_load: lut_lib.LUTInputDriverLoad = in_ckt_combo[5]
                lut_driver_tb = lut_lib.LUTInputDriverTB(
                    id = tb_idx,
                    not_flag = False,
                    # DUT Circuits
                    cb_mux = cb_mux,
                    local_r_wire_load = local_r_wire_load,
                    flip_flop = ff,
                    lut_in_driver = lut_in_driver,
                    lut_in_not_driver = lut_in_not_driver,
                    lut_driver_load = lut_in_driver_load,
                    # General SimTB args
                    inc_libs = inc_libs,
                    mode = gen_sim_mode,
                    options = sim_options,
                    # Pass in library of all subckts 
                    subckt_lib = self.subckt_lib,
                )
                self.lut_in_driver_tbs[lut_in_driver.lut_input_key].append(lut_driver_tb)
                lut_not_driver_tb = lut_lib.LUTInputDriverTB(
                    id = tb_idx,
                    not_flag = True,
                    # DUT Circuits
                    cb_mux = cb_mux,
                    local_r_wire_load = local_r_wire_load,
                    flip_flop = ff,
                    lut_in_driver = lut_in_driver,
                    lut_in_not_driver = lut_in_not_driver,
                    lut_driver_load = lut_in_driver_load,
                    # General SimTB args
                    inc_libs = inc_libs,
                    mode = gen_sim_mode,
                    options = sim_options,
                    # Pass in library of all subckts 
                    subckt_lib = self.subckt_lib,
                )
                self.lut_in_not_driver_tbs[lut_in_driver.lut_input_key].append(lut_not_driver_tb)
                    # LUT input driver with LUT Load
            # TODO refactor this so its not so much duplicated code
            if self.specs.use_fluts:
                # We only want the product of lut_output_loads if we are NOT using fluts
                # We only want the product of flip flops if our LUT input driver type is "default_rsel" || "reg_fb_rsel"
                # TODO accomodate flip flop parameterization for now we assert that only a single FF type exists
                assert len(tb_ffs) == 1, "Only a single flip flop type is supported for now"
                lut_input_tb_in_ckts: List[tuple] = list(
                    itertools.product(
                        tb_cb_muxes,
                        tb_local_r_wire_loads,
                        tb_lut_input_drivers,
                        tb_ffs,
                        tb_lut_input_not_drivers,
                        tb_luts,
                        # tb_lut_in_drv_loads,
                        tb_flut_muxes,
                    )
                )
                lut_load_key = "flut_mux"
            else:
                lut_input_tb_in_ckts: List[tuple] = list(
                    itertools.product(
                        tb_cb_muxes,
                        tb_local_r_wire_loads,
                        tb_lut_input_drivers,
                        tb_ffs,
                        tb_lut_input_not_drivers,
                        tb_luts,
                        tb_lut_output_loads,
                    )
                )
                lut_load_key = "lut_output_load"
            for tb_idx, in_ckt_combo in enumerate(lut_input_tb_in_ckts):
                cb_mux: cb_mux_lib.ConnectionBlockMux = in_ckt_combo[0]
                local_r_wire_load: lb_lib.LocalRoutingWireLoad = in_ckt_combo[1]
                lut_in_driver: lut_lib.LUTInputDriver = in_ckt_combo[2]
                ff: ble_lib.FlipFlop = in_ckt_combo[3]
                lut_in_not_driver: lut_lib.LUTInputNotDriver = in_ckt_combo[4]
                lut: lut_lib.LUT = in_ckt_combo[5]
                # lut_in_driver_load: lut_lib.LUTInputDriverLoad = in_ckt_combo[6]
                if self.specs.use_fluts:
                    lut_output_load: ble_lib.FlutMux = in_ckt_combo[6]
                else:
                    lut_output_load: ble_lib.LUTOutputLoad = in_ckt_combo[6]
                lut_output_load_arg = {
                    lut_load_key: lut_output_load
                }
                # Create a custom mode for this tb as we want to sim to 16p
                lut_input_tb_sim_mode: c_ds.SpSimMode = copy.deepcopy(base_sim_mode)
                lut_input_tb_sim_mode.sim_time = c_ds.Value(16, units = sb_mux_sim_mode.sim_time.units) # ns

                # TODO make sure the RISE=1 is ok previously was RISE=2 for first meas statement
                lut_input_tb = lut_lib.LUTInputTB(
                    id = tb_idx,
                    # DUT Circuits
                    cb_mux = cb_mux,
                    local_r_wire_load = local_r_wire_load,
                    lut_in_driver = lut_in_driver,
                    flip_flop = ff,
                    lut_in_not_driver = lut_in_not_driver,
                    lut = lut,
                    **lut_output_load_arg,
                    # General SimTB args
                    inc_libs = inc_libs,
                    mode = lut_input_tb_sim_mode,
                    options = sim_options,
                    # Pass in library of all subckts 
                    subckt_lib = self.subckt_lib,
                )
                self.lut_input_tbs[lut_in_driver.lut_input_key].append(lut_input_tb)

        if self.specs.enable_carry_chain:
            # Carry Chain
            for cc in self.carry_chains:
                cc: cc_lib.CarryChain
                # Create a custom mode for this tb as we want to sim to 16p
                cc_sim_mode: c_ds.SpSimMode = copy.deepcopy(base_sim_mode)
                cc_sim_mode.sim_time = c_ds.Value(26, units = sb_mux_sim_mode.sim_time.units) # ns
                cc_tb = cc_lib.CarryChainTB(
                    id = tb_idx,
                    # DUT Circuits
                    FA_carry_chain = cc, 
                    # General SimTB args
                    inc_libs = inc_libs,
                    mode = cc_sim_mode,
                    options = sim_options,
                    # Pass in library of all subckts 
                    subckt_lib = self.subckt_lib,
                )
                self.carry_chain_tbs.append(cc_tb)
            cc_periph_in_ckts = list(
                itertools.product(
                    self.carry_chains,
                    self.carry_chain_periphs,
                    self.carry_chain_muxes,
                )
            )
            # CC Peripheials
            for ckt_combo in cc_periph_in_ckts:
                cc: cc_lib.CarryChain = ckt_combo[0]
                cc_periph: cc_lib.CarryChainPer = ckt_combo[1]
                cc_mux: cc_lib.CarryChainMux = ckt_combo[2]
                cc_periph_tb = cc_lib.CarryChainPerTB(
                    id = tb_idx,
                    # TB Circuits
                    FA_carry_chain = cc, 
                    carry_chain_periph = cc_periph,
                    carry_chain_mux = cc_mux,
                    # General SimTB args
                    inc_libs = inc_libs,
                    mode = cc_sim_mode,
                    options = sim_options,
                    # Pass in library of all subckts 
                    subckt_lib = self.subckt_lib,
                )
                self.carry_chain_per_tbs.append(cc_periph_tb)
            cc_inter_in_ckts = list(
                itertools.product(
                    self.carry_chains,
                    self.carry_chain_inter_clusters,
                )
            )
            # CC Interconnect
            for ckt_combo in cc_inter_in_ckts:
                cc: cc_lib.CarryChain = ckt_combo[0]
                cc_inter: cc_lib.CarryChainInterCluster = ckt_combo[1]
                cc_inter_tb = cc_lib.CarryChainInterClusterTB(
                    id = tb_idx,
                    # TB Circuits
                    FA_carry_chain = cc, 
                    carry_chain_inter = cc_inter,
                    # General SimTB args
                    inc_libs = inc_libs,
                    mode = cc_sim_mode,
                    options = sim_options,
                    # Pass in library of all subckts 
                    subckt_lib = self.subckt_lib,
                )
                self.carry_chain_inter_tbs.append(cc_inter_tb)
            # Use product of all possible input circuits to create these TBs
            cc_mux_in_ckts = list(
                itertools.product(
                    self.carry_chains,
                    self.carry_chain_muxes,
                    self.carry_chain_periphs,
                    tb_lut_output_loads,
                    tb_gen_ble_output_loads,
                )
            )
            # CC Mux
            for tb_idx, in_ckt_combo in enumerate(cc_mux_in_ckts):
                fa_cc: cc_lib.CarryChain = in_ckt_combo[0]
                cc_mux: cc_lib.CarryChainMux = in_ckt_combo[1]
                carry_chain_periph: cc_lib.CarryChainPer = in_ckt_combo[2]
                lut_output_load: ble_lib.LUTOutputLoad = in_ckt_combo[3]
                gen_ble_output_load: gen_r_load_lib.GeneralBLEOutputLoad = in_ckt_combo[4]
                cc_mux = cc_lib.CarryChainMuxTB(
                    id = tb_idx,
                    # TB Circuits
                    FA_carry_chain = fa_cc,
                    carry_chain_mux = cc_mux,
                    carry_chain_periph = carry_chain_periph,
                    lut_output_load = lut_output_load,
                    gen_ble_output_load = gen_ble_output_load,
                    # General SimTB args
                    inc_libs = inc_libs,
                    mode = gen_sim_mode, # 4ns sim time
                    options = sim_options,
                    # Pass in library of all subckts 
                    subckt_lib = self.subckt_lib,
                )
                self.carry_chain_mux_tbs.append(cc_mux)
            if self.specs.carry_chain_type == "skip":
                cc_in_ckts = list(
                    itertools.product(
                        tb_luts,
                        self.carry_chains,
                        self.carry_chain_skip_ands,
                        self.carry_chain_skip_muxes,
                        self.carry_chain_muxes,
                    )
                )
                for tb_idx, in_ckt_combo in enumerate(cc_in_ckts):
                    lut: lut_lib.LUT = in_ckt_combo[0]
                    cc: cc_lib.CarryChain = in_ckt_combo[1]
                    cc_and: cc_lib.CarryChainSkipAnd = in_ckt_combo[2]
                    cc_skip_mux: cc_lib.CarryChainSkipMux = in_ckt_combo[3]
                    cc_mux: cc_lib.CarryChainMuxTB = in_ckt_combo[4]
                    # CC Skip And
                    cc_and_tb = cc_lib.CarryChainSkipAndTB(
                        id = tb_idx,
                        # TB Circuits
                        lut = lut,
                        FA_carry_chain = cc,
                        carry_chain_and = cc_and,
                        carry_chain_skip_mux = cc_skip_mux,
                        carry_chain_mux = cc_mux,
                        # General SimTB args
                        inc_libs = inc_libs,
                        mode = cc_sim_mode,
                        options = sim_options,
                        # Pass in library of all subckts 
                        subckt_lib = self.subckt_lib,
                    )
                    self.carry_chain_skip_and_tbs.append(cc_and_tb)
                    # CC Skip Mux
                    cc_skip_mux_tb = cc_lib.CarryChainSkipMuxTB(
                        id = tb_idx,
                        # TB Circuits
                        lut = lut,
                        FA_carry_chain = cc,
                        carry_chain_and = cc_and,
                        carry_chain_skip_mux = cc_skip_mux,
                        carry_chain_mux = cc_mux,
                        # General SimTB args
                        inc_libs = inc_libs,
                        mode = gen_sim_mode, # 4ns sim time
                        options = sim_options,
                        # Pass in library of all subckts 
                        subckt_lib = self.subckt_lib,
                    )
                    self.carry_chain_skip_mux_tbs.append(cc_skip_mux_tb)

        #   ___ ___    _   __  __ 
        #  | _ ) _ \  /_\ |  \/  |
        #  | _ \   / / _ \| |\/| |
        #  |___/_|_\/_/ \_\_|  |_|

        # Kept same format as others for consistency
        
        # Pass gate output crossbar
        # pgate_crossbar_tb_in_ckts = list(
        #     itertools.product(
        #         self.pgate_output_crossbars,
        #         self.flip_flops,
        #     )
        # )
        # for tb_idx, in_ckt_combo in enumerate(pgate_crossbar_tb_in_ckts):
        #     pgate_crossbar: ram_lib.PgateOutputCrossbar = in_ckt_combo[0]
        #     ff: ble_lib.FlipFlop = in_ckt_combo[1]
        #     pgate_crossbar_tb = ram_lib.PgateOutputCrossbarTB(
        #         id = tb_idx,
        #         # TB Circuits
        #         pgate_output_crossbar = pgate_crossbar,
        #         flip_flop = ff,
        #         # General SimTB args
        #         inc_libs = inc_libs,
        #         mode = gen_sim_mode,
        #         options = sim_options,
        #         # Pass in library of all subckts 
        #         subckt_lib = self.subckt_lib,
        #     )
        #     self.pgate_output_crossbar_tbs.append(pgate_crossbar_tb)
        
        # # Configurable decoder III
        # config_decoder_tb_in_ckts = list(
        #     itertools.product(
        #         self.configurable_decoder_3iis,
        #         self.configurable_decoder_2iis,
        #         self.configurable_decoder_iiis,
        #     )
        # )
        # for tb_idx, in_ckt_combo in enumerate(config_decoder_tb_in_ckts):
        #     configurable_decoder_3ii: ram_lib.ConfigurableDecoderII = in_ckt_combo[0]
        #     configurable_decoder_2ii: ram_lib.ConfigurableDecoderII = in_ckt_combo[1]
        #     configurable_decoder_iii: ram_lib.ConfigurableDecoderIII = in_ckt_combo[2]
        #     config_decoder_tb = ram_lib.ConfigurableDecoderIIITB(
        #         id = tb_idx,
        #         # TB Circuits
        #         configurable_decoder_ii_1 = configurable_decoder_3ii,
        #         configurable_decoder_ii_2 = configurable_decoder_2ii,
        #         configurable_decoder_iii = configurable_decoder_iii,
        #         # General SimTB args
        #         inc_libs = inc_libs,
        #         mode = gen_sim_mode,
        #         options = sim_options,
        #         # Pass in library of all subckts 
        #         subckt_lib = self.subckt_lib,
        #     )
        #     self.configurable_decoder_iii_tbs.append(config_decoder_tb)
        
        # Generate top-level files. These top-level files are the files that COFFE uses to measure 
        # the delay of FPGA circuitry
        for sb_mux_tb in self.sb_mux_tbs:
            sb_mux_tb.generate_top()

        for cb_mux_tb in self.cb_mux_tbs:
            cb_mux_tb.generate_top()
        
        for local_mux_tb in self.local_mux_tbs:
            local_mux_tb.generate_top()

        for local_ble_out_tb in self.local_ble_output_tbs:
            local_ble_out_tb.generate_top()
        
        for gen_ble_out_tb in self.general_ble_output_tbs:
            gen_ble_out_tb.generate_top()

        for lut_tb in self.lut_tbs:
            lut_tb.generate_top()
        
        for flut_mux_tb in self.flut_mux_tbs:
            flut_mux_tb.generate_top()

        # For each driver input "a", "b" ... 
        for lut_in_driver_tbs in self.lut_in_driver_tbs.values():
            # for each parameterized instance of input on e.g. "a", generate tb
            for lut_in_driver_tb in lut_in_driver_tbs:
                lut_in_driver_tb.generate_top()

        for lut_in_not_driver_tbs in self.lut_in_not_driver_tbs.values():
            for lut_in_not_driver_tb in lut_in_not_driver_tbs:
                lut_in_not_driver_tb.generate_top()
        
        for lut_input_tbs in self.lut_input_tbs.values():
            for lut_in_tb in lut_input_tbs:
                lut_in_tb.generate_top()
        
        if self.specs.enable_carry_chain:
            for cc_tb in self.carry_chain_tbs:
                cc_tb.generate_top()
            for cc_per_tb in self.carry_chain_per_tbs:
                cc_per_tb.generate_top()
            for cc_inter_tb in self.carry_chain_inter_tbs:
                cc_inter_tb.generate_top()
            for cc_mux_tb in self.carry_chain_mux_tbs:
                cc_mux_tb.generate_top()
            if self.specs.carry_chain_type == "skip":
                for cc_and_tb in self.carry_chain_skip_and_tbs:
                    cc_and_tb.generate_top()
                for cc_skip_mux_tb in self.carry_chain_skip_mux_tbs:
                    cc_skip_mux_tb.generate_top()

        # RAM
        if self.specs.enable_bram_block == 1:
            self.RAM.generate_top()
            # for pgate_crossbar_tb in self.pgate_output_crossbar_tbs:
            #     pgate_crossbar_tb.generate_top()
            # for config_decoder_tb in self.configurable_decoder_iii_tbs:
            #     config_decoder_tb.generate_top()

        for hardblock in self.hardblocklist:
            hardblock.generate_top(size_hb_interfaces)

        # Initialize library of testbenches and sizeable ckts
        self.init_tb_subckt_libs()

        # Calculate area, and wire data.
        print("Calculating area...")
        # Update area values
        self.update_area()
        print("Calculating wire lengths...")
        self.update_wires()
        print("Calculating wire resistance and capacitance...")
        self.update_wire_rc()
    
        print("")
            

    def update_area(self):
        """ This function updates self.area_dict. It passes area_dict to member objects (like sb_mux)
            to update their area. Then, with an up-to-date area_dict it, calculate total tile area. """
        
        # We use the self.transistor_sizes to compute area. This dictionary has the form 'name': 'size'
        # And it knows the transistor sizes of all transistors in the FPGA
        # We first need to calculate the area for each transistor.
        # This function stores the areas in the transistor_area_list
        self._update_area_per_transistor()
        # Now, we have to update area_dict and width_dict with the new transistor area values
        # for the basic subcircuits which are inverteres, ptran, tgate, restorers and transistors
        self._update_area_and_width_dicts()
        #I found that printing width_dict here and comparing against golden results was helpful
        #self.debug_print("width_dict")

        # Calculate area of SRAM
        self.area_dict["sram"] = self.specs.sram_cell_area * self.specs.min_width_tran_area
        self.area_dict["ramsram"] = 5 * self.specs.min_width_tran_area
        # MTJ in terms of min transistor width
        self.area_dict["rammtj"] = 1.23494 * self.specs.min_width_tran_area
        self.area_dict["mininv"] =  3 * self.specs.min_width_tran_area
        self.area_dict["ramtgate"] =  3 * self.area_dict["mininv"]

        # Call Area calculation functions for all FPGA circuit objects
        for sb_mux in self.sb_muxes:
            sb_mux.update_area(self.area_dict, self.width_dict)
        for cb_mux in self.cb_muxes:
            cb_mux.update_area(self.area_dict, self.width_dict)

        if self.specs.enable_carry_chain:
            for carry_chain_periph in self.carry_chain_periphs:
                carry_chain_periph.update_area(self.area_dict, self.width_dict)
            for carry_chain_mux in self.carry_chain_muxes:
                carry_chain_mux.update_area(self.area_dict, self.width_dict)
            for carry_chain_inter in self.carry_chain_inter_clusters:
                carry_chain_inter.update_area(self.area_dict, self.width_dict)
            for carry_chain in self.carry_chains:
                carry_chain.update_area(self.area_dict, self.width_dict)
            if self.specs.carry_chain_type == "skip":
                for carry_chain_skip_and in self.carry_chain_skip_ands:
                    carry_chain_skip_and.update_area(self.area_dict, self.width_dict)
                for carry_chain_skip_mux in self.carry_chain_skip_muxes:
                    carry_chain_skip_mux.update_area(self.area_dict, self.width_dict)

        # TODO bring the local mux update area out here and decouple with logic cluster
        # for local_mux in self.local_muxes:
        #     local_mux.update_area(self.area_dict)
        for logic_cluster in self.logic_clusters:
            logic_cluster.update_area(self.area_dict, self.width_dict)
        
        hardblock: hb_lib._hard_block
        for hardblock in self.hardblocklist:
            hardblock.update_area(self.area_dict, self.width_dict)
        
        if self.specs.enable_bram_block == 1:
            self.RAM.update_area(self.area_dict, self.width_dict)

        # SB Muxes
        # Calculate total area of switch block
        # switch_block_area: float = 0
        # switch_block_area_no_sram: float = 0
        # switch_block_avg_area: float = 0
        # # weighted avg area of switch blocks based on percentage of SB mux occurances
        # # Add up areas of all switch blocks of all types
        # for i, sb_mux in enumerate(self.sb_muxes):
        #     # For weighted average use the number of tracks per wire length corresponding SB / total tracks as the weight 
        #     # Weight Factor * SB Mux Area w/ SRAM
        #     switch_block_avg_area += ((sb_mux.num_per_tile) / sum([sb_mux.num_per_tile for sb_mux in self.sb_muxes])) * self.area_dict[sb_mux.name]
        #     switch_block_area += sb_mux.num_per_tile * self.area_dict[sb_mux.name + "_sram"]
        #     switch_block_area_no_sram += sb_mux.num_per_tile * self.area_dict[sb_mux.name]
        
        # # SB should never have area of 0 after this point
        # assert switch_block_area != 0 and switch_block_area_no_sram != 0 and switch_block_avg_area != 0, "Switch block area is 0, error in SB area calculation"
        # self.area_dict["sb_mux_avg"] = switch_block_avg_area # avg_sb_mux area with NO SRAM 
        # self.area_dict["sb_total_no_sram"] = switch_block_area_no_sram
        # self.area_dict["sb_total"] = switch_block_area
        # self.width_dict["sb_total"] = math.sqrt(switch_block_area)

        # # CB Muxes
        # connection_block_area: float = 0
        # connection_block_area_no_sram: float = 0
        # connection_block_avg_area: float = 0 
        # for cb_mux in self.cb_muxes:
        #     connection_block_avg_area += ((cb_mux.num_per_tile) / sum([cb_mux.num_per_tile for cb_mux in self.cb_muxes])) * self.area_dict[cb_mux.name]
        #     connection_block_area += cb_mux.num_per_tile * self.area_dict[cb_mux.name + "_sram"]
        #     connection_block_area_no_sram += cb_mux.num_per_tile * self.area_dict[cb_mux.name]
        
        # assert connection_block_area != 0 and switch_block_area_no_sram != 0 and switch_block_avg_area != 0, "Connection block area is 0, error in CB area calculation"
        # self.area_dict["cb_total"] = connection_block_area
        # self.area_dict["cb_total_no_sram"] = connection_block_area_no_sram
        # self.width_dict["cb_total"] = math.sqrt(connection_block_area)

        # Switch Block Muxes
        self.sb_mux.set_block_tile_area(self.area_dict, self.width_dict)
        # Connection Block Muxes
        self.cb_mux.set_block_tile_area(self.area_dict, self.width_dict)
        # Local Muxes
        self.local_mux.set_block_tile_area(self.area_dict, self.width_dict)

        # Total Lut area 
        # TODO update for multi ckt support
        lut_area: float = self.specs.N * self.area_dict["lut_and_drivers"]
        lut_area_no_sram: float = self.specs.N * (self.area_dict["lut_and_drivers"] - (2**self.specs.K) * self.area_dict["sram"])
        lut_area_sram: float = self.specs.N * (2**self.specs.K) * self.area_dict["sram"]
        self.area_dict["lut_total"] = lut_area
        self.width_dict["lut_total"] = math.sqrt(lut_area)
        
        # Total FF area
        # TODO update for multi ckt support
        ff_area: float = self.specs.N * self.area_dict[self.logic_clusters[0].ble.ff.name] # TODO sp_name update
        if self.specs.use_fluts:
            ff_area *= 2
        self.area_dict["ff_total"] = ff_area
        self.width_dict["ff_total"] = math.sqrt(ff_area)
        
        # Total BLE area
        # TODO update for multi ckt support
        ble_output_area: float = self.specs.N * self.area_dict["ble_output"] # TODO sp_name update
        self.area_dict["ble_output_total"] = ble_output_area
        self.width_dict["ble_output_total"] = math.sqrt(ble_output_area)

        # TODO add multi wire len support rather than just choosing first index of carry chain
        # Why is the peripheral cc area not included in this? TODO figure out
        cc: cc_lib.CarryChain = self.carry_chains[0]
        cc_skip_and: cc_lib.CarryChainSkipAnd = self.carry_chain_skip_ands[0]
        cc_skip_mux: cc_lib.CarryChainSkipMux = self.carry_chain_skip_muxes[0]
        cc_mux: cc_lib.CarryChainMux = self.carry_chain_muxes[0]
        cc_inter: cc_lib.CarryChainInterCluster = self.carry_chain_inter_clusters[0]

        # If uninitialized logic block height
        if not self.lb_height:
            # Calculate area of logic cluster
            cluster_area = self.local_mux.block_area + self.specs.N * self.area_dict["ble"]
            if self.specs.enable_carry_chain:
                cluster_area += self.specs.N * self.area_dict[f"{cc_inter.sp_name}"]
            # Init these here to keep our csv dimensions consistent
            self.area_dict["cc_area_total"] = 0
            self.width_dict["cc_area_total"] = 0

            self.area_dict["ffableout_area_total"] = 0
            self.width_dict["ffableout_area_total"] = 0
        else:
            # FF ble output area
            ff_ble_output_area: float = ff_area + self.specs.N * self.area_dict["ble_output"] # TODO sp_name update
            cc_area_total: float = 0.0
            # self.skip_size: int = 5
            self.carry_skip_periphery_count = int(math.floor ((self.specs.N * self.specs.FAs_per_flut) // self.skip_size))
            if self.specs.enable_carry_chain == 1:
                cc_area_total = self.specs.N * (self.area_dict[f"{cc.sp_name}"] * self.specs.FAs_per_flut + (self.specs.FAs_per_flut) * self.area_dict[f"{cc_mux.sp_name}"])
                if not (self.carry_skip_periphery_count == 0 or self.specs.carry_chain_type == "ripple"):
                    cc_area_total += ((self.area_dict[f"{cc_skip_and.sp_name}"] + self.area_dict[f"{cc_skip_mux.sp_name}"]) * self.carry_skip_periphery_count)
                cc_area_total += self.area_dict[f"{cc_inter.sp_name}"]
            # Set Carry Chain total area
            self.area_dict["cc_area_total"] = cc_area_total
            self.width_dict["cc_area_total"] = math.sqrt(cc_area_total)
            
            self.area_dict["ffableout_area_total"] = ff_ble_output_area
            self.width_dict["ffableout_area_total"] = math.sqrt(ff_ble_output_area)

            cluster_area: float = self.local_mux.block_area + ff_ble_output_area + cc_area_total + lut_area

        self.area_dict["logic_cluster"] = cluster_area
        self.width_dict["logic_cluster"] = math.sqrt(cluster_area)

        if self.specs.enable_carry_chain == 1:
            # Calculate Carry Chain Area
            # already included in bles, extracting for the report
            carry_chain_area: float = self.specs.N * ( self.specs.FAs_per_flut * self.area_dict[f"{cc.sp_name}"] + (self.specs.FAs_per_flut) * self.area_dict[f"{cc_mux.sp_name}"]) + self.area_dict[f"{cc_inter.sp_name}"]
            if self.specs.carry_chain_type == "skip":
                self.carry_skip_periphery_count = int(math.floor((self.specs.N * self.specs.FAs_per_flut) / self.skip_size))
                carry_chain_area += self.carry_skip_periphery_count *(self.area_dict[f"{cc_skip_and.sp_name}"] + self.area_dict[f"{cc_skip_mux.sp_name}"])
            self.area_dict["total_carry_chain"] = carry_chain_area

        # Calculate tile area
        tile_area: float = self.sb_mux.block_area + self.cb_mux.block_area + cluster_area
        self.area_dict["tile"] = tile_area
        self.width_dict["tile"] = math.sqrt(tile_area)

        # Block RAM updates
        if self.specs.enable_bram_block == 1:
            # TODO bring the sb_mux and cb_mux used in BRAM up to user level
            # just choosing 
            bram_sb_mux = [sb_mux for sb_mux in self.sb_muxes if sb_mux.sink_wire == min(self.gen_r_wires.values(), key=lambda x: x.length) ][0]
            bram_cb_mux = self.cb_muxes[0]
            # Calculate RAM area:

            # LOCAL MUX + FF area
            RAM_local_mux_area = self.RAM.RAM_local_mux.num_per_tile * self.area_dict[self.RAM.RAM_local_mux.name + "_sram"] + self.area_dict[self.logic_clusters[0].ble.ff.name] # TODO update for multi ckt support
            self.area_dict["ram_local_mux_total"] = RAM_local_mux_area
            self.width_dict["ram_local_mux_total"] = math.sqrt(RAM_local_mux_area)

            # SB and CB in the RAM tile:
            RAM_area =(RAM_local_mux_area + self.area_dict[bram_cb_mux.sp_name + "_sram"] * self.RAM.ram_inputs + (2** (self.RAM.conf_decoder_bits + 3)) * self.area_dict[bram_sb_mux.sp_name + "_sram"]) 
            RAM_SB_area = 2 ** (self.RAM.conf_decoder_bits + 3) * self.area_dict[bram_sb_mux.name + "_sram"] 
            RAM_CB_area =  self.area_dict[bram_cb_mux.sp_name + "_sram"] * self.RAM.ram_inputs 


            self.area_dict["level_shifters"] = self.area_dict["level_shifter"] * self.RAM.RAM_local_mux.num_per_tile
            self.area_dict["RAM_SB"] = RAM_SB_area
            self.area_dict["RAM_CB"] = RAM_CB_area
            # Row decoder area calculation
 
            RAM_decoder_area = 0.0
            RAM_decoder_area += self.area_dict["rowdecoderstage0"]
            #if there is a predecoder, add its area
            if self.RAM.valid_row_dec_size3 == 1:
                RAM_decoder_area += self.area_dict["rowdecoderstage13"]
            #if there is a predecoder, add its area
            if self.RAM.valid_row_dec_size2 == 1:
                RAM_decoder_area += self.area_dict["rowdecoderstage12"]
            #if there is a predecoder, add its area
            RAM_decoder_area += self.area_dict["rowdecoderstage3"]
            # There are two decoders in a dual port circuit:
            RAM_area += RAM_decoder_area * 2 
            # add the actual array area to total RAM area
            self.area_dict["memorycell_total"] = self.area_dict["memorycell"]
            RAM_area += self.area_dict["memorycell_total"]

            if self.RAM.memory_technology == "SRAM":
            # add precharge, write driver, and sense amp area to total RAM area
                self.area_dict["precharge_total"] = (self.area_dict[self.RAM.precharge.name] * 2* (2**(self.RAM.conf_decoder_bits+self.RAM.col_decoder_bits))) * self.number_of_banks
                # several components will be doubled for the largest decoder size to prevent a large amount of delay.
                if self.RAM.row_decoder_bits == 9:
                    self.area_dict["precharge_total"] = 2 * self.area_dict["precharge_total"]
                self.area_dict["samp_total"] = self.area_dict[self.RAM.samp.name] * 2* 2**(self.RAM.conf_decoder_bits) * self.number_of_banks 
                self.area_dict["writedriver_total"] = self.area_dict[self.RAM.writedriver.name] * 2* 2**(self.RAM.conf_decoder_bits) * self.number_of_banks 
                RAM_area += (self.area_dict["precharge_total"] + self.area_dict["samp_total"] + self.area_dict["writedriver_total"])
                self.area_dict["columndecoder_total"] = ((self.area_dict["ramtgate"] * 4 *  (2**(self.RAM.conf_decoder_bits+self.RAM.col_decoder_bits))) / (2**(self.RAM.col_decoder_bits))) + self.area_dict["columndecoder"] * 2 
            
            else:
                # In case of MTJ, banks can share sense amps so we don't have mutlitplication by two
                self.area_dict["samp_total"] = self.area_dict["mtj_subcircuits_sa"] * 2**(self.RAM.conf_decoder_bits) * self.number_of_banks 
                # Write driver can't be shared:
                self.area_dict["writedriver_total"] = self.area_dict["mtj_subcircuits_writedriver"] * 2* 2**(self.RAM.conf_decoder_bits) * self.number_of_banks 
                self.area_dict["cs_total"] = self.area_dict["mtj_subcircuits_cs"] * 2* 2**(self.RAM.conf_decoder_bits +self.RAM.col_decoder_bits) * self.number_of_banks 
                if self.RAM.row_decoder_bits == 9:
                    self.area_dict["cs_total"] = 2 * self.area_dict["cs_total"]

                self.area_dict["columndecoder_total"] = self.area_dict["columndecoder"] * 2 
                RAM_area +=  self.area_dict["samp_total"] + self.area_dict["writedriver_total"] + self.area_dict["cs_total"]

            self.area_dict["columndecoder_sum"] = self.area_dict["columndecoder_total"] * self.number_of_banks 
            RAM_area += self.area_dict["columndecoder_sum"]
            #configurable decoder:
            RAM_configurabledecoder_area = self.area_dict[self.RAM.configurabledecoderi.name + "_sram"]
            if self.RAM.cvalidobj1 == 1:
                RAM_configurabledecoder_area += self.area_dict[self.RAM.configurabledecoder3ii.name]
            if self.RAM.cvalidobj2 == 1:
                RAM_configurabledecoder_area += self.area_dict[self.RAM.configurabledecoder2ii.name]
            self.area_dict["configurabledecoder_wodriver"] = RAM_configurabledecoder_area
            self.width_dict["configurabledecoder_wodriver"] = math.sqrt(self.area_dict["configurabledecoder_wodriver"])
            RAM_configurabledecoder_area += self.area_dict[self.RAM.configurabledecoderiii.name]
            if self.number_of_banks == 2:
                RAM_configurabledecoder_area = RAM_configurabledecoder_area * 2
            RAM_area += 2 * RAM_configurabledecoder_area 

            # add the output crossbar area:
            RAM_area += self.area_dict[self.RAM.pgateoutputcrossbar.name + "_sram"] 
            # add the wordline drivers:
            RAM_wordlinedriver_area = self.area_dict[self.RAM.wordlinedriver.name] * self.number_of_banks
            # we need 2 wordline drivers per row, since there are 2 wordlines in each row to control 2 BRAM ports, respectively
            RAM_wordlinedriver_area = RAM_wordlinedriver_area * 2 
            RAM_area += self.area_dict["level_shifters"]
            RAM_area += RAM_wordlinedriver_area

            # write into dictionaries:
            self.area_dict["wordline_total"] = RAM_wordlinedriver_area
            self.width_dict["wordline_total"] = math.sqrt(RAM_wordlinedriver_area)
            self.area_dict["configurabledecoder"] = RAM_configurabledecoder_area
            self.width_dict["configurabledecoder"] = math.sqrt(RAM_configurabledecoder_area)
            self.area_dict["decoder"] = RAM_decoder_area 
            self.area_dict["decoder_total"] = RAM_decoder_area * 2 
            self.width_dict["decoder"] = math.sqrt(RAM_decoder_area)
            self.area_dict["ram"] = RAM_area
            self.area_dict["ram_core"] = RAM_area - RAM_SB_area - RAM_CB_area
            self.width_dict["ram"] = math.sqrt(RAM_area) 

        if self.lb_height:
            self.compute_distance()

        # Area logging
        if consts.VERBOSITY == consts.DEBUG:
            fpga_state_to_csv(self, "VERIF", "area")
            fpga_state_to_csv(self, "VERIF", "tx_size")
            # Area totals logging
            csv_outdir = "debug"
            # The totals for circuits are stored in below keys 
            # TODO add RAM keys
            # TODO remove the hardcoded keys...
            area_total_keys = [
                "sb_mux_total", # Added in the block function
                "cb_mux_total", # Added in the block function
                "local_mux_total", # Added in the block function
                "lut_total",
                "ff_total",
                "ble_output_total",
                "cc_area_total",
                "ffableout_area_total",
                "logic_cluster",
                "total_carry_chain",
                "tile",
            ]
            total_areas = {
                **fpga_state_fmt(self, "VERIF"),
                **{key: self.area_dict[key] for key in area_total_keys},
            }
            totals_csv_out_fpath = os.path.join(csv_outdir, "area_totals.csv")
            # % of area as a portion of the tile area
            # total_area_ratios = {
            #     **fpga_state_fmt(self, "VERIF"),
            #     **{key: self.area_dict[key] / self.area_dict["tile"] for key in area_total_keys if key != "tile"},
            # }
            rg_utils.write_single_dict_to_csv(total_areas, totals_csv_out_fpath, "a")
            # Per circuit area logging
            unique_subckts: List[Type[c_ds.SizeableCircuit]] = list(self.tb_lib.keys())
            for subckt in unique_subckts:
                fpga_state_to_csv(self, "VERIF", "area", subckt)
                fpga_state_to_csv(self, "VERIF", "tx_size", subckt)

        self.update_area_cnt += 1


    def get_dist_bw_stripes(
            self, 
            stripe1: Tuple[str, int], 
            stripe2: Tuple[str, int], 
            stripe_widths: Dict[str, float]
    ):
        """ 
            Preconditions: 
                - self.stripe_order has been set
                - self.span_stripe fraction has been set
            Get the distance between two stripes in a tile.     
        """
        s1_key, s1_idx = stripe1
        s2_key, s2_idx = stripe2
        # We want to get the number of stripes b/w the two NON inclusive
        num_inter_stripes: int = abs(s1_idx - s2_idx) - 1
        # if these stripes are non adjacent, we sum the widths of stripes in between
        tmp_dist: float = 0
        if num_inter_stripes > 0:
            # Get the stripes between the two stripes
            inter_stripes = self.stripe_order[min(s1_idx, s2_idx) + 1: max(s1_idx, s2_idx)]
            # Sum the widths of the stripes in between
            tmp_dist = sum([stripe_widths[stripe] for stripe in inter_stripes])
        # Add the widths of the two stripes, which adds the width of the stripe divided by the self.span_stripe_fraction
        s1_dist: float = (stripe_widths[s1_key] / self.span_stripe_fraction)
        s2_dist: float = (stripe_widths[s2_key] / self.span_stripe_fraction)
        dist: float = s1_dist + tmp_dist + s2_dist
        return dist

    def compute_distance(self):
        """ This function computes distances for different stripes for the floorplanner:

        """
        # todo: move these to user input
        self.stripe_order = ["sb_sram","sb","sb", "cb", "cb_sram","ic_sram", "ic","lut_sram", "lut", "cc","ffble", "lut", "lut_sram", "ic", "ic_sram", "cb_sram", "cb", "sb","sb", "sb_sram"]
        #self.stripe_order = ["cb", "cb_sram","ic_sram", "ic","lut_sram", "lut", "cc","ffble", "sb", "sb_sram"]
        self.span_stripe_fraction = 10


        self.num_cb_stripes = 0
        self.num_sb_stripes = 0
        self.num_ic_stripes = 0
        self.num_lut_stripes = 0
        self.num_ffble_stripes = 0
        self.num_cc_stripes = 0
        self.num_cbs_stripes = 0
        self.num_sbs_stripes = 0
        self.num_ics_stripes = 0
        self.num_luts_stripes = 0
        #find the number of each stripe type in the given arrangement:
        for item in self.stripe_order:
            if item == "sb":
                self.num_sb_stripes =  self.num_sb_stripes + 1
            elif item == "cb":
                self.num_cb_stripes =  self.num_cb_stripes + 1
            elif item == "ic":
                self.num_ic_stripes =  self.num_ic_stripes + 1
            elif item == "lut":
                self.num_lut_stripes =  self.num_lut_stripes + 1
            elif item == "cc":
                self.num_cc_stripes =  self.num_cc_stripes + 1
            elif item == "ffble":
                self.num_ffble_stripes =  self.num_ffble_stripes + 1
            elif item == "sb_sram":
                self.num_sbs_stripes =  self.num_sbs_stripes + 1
            elif item == "cb_sram":
                self.num_cbs_stripes =  self.num_cbs_stripes + 1
            elif item == "ic_sram":
                self.num_ics_stripes =  self.num_ics_stripes + 1
            elif item == "lut_sram":
                self.num_luts_stripes =  self.num_luts_stripes + 1

        # Set widths of various blocks in a tile
        self.sb_mux.set_block_widths(self.area_dict, self.num_sb_stripes, self.num_sbs_stripes, self.lb_height)
        self.cb_mux.set_block_widths(self.area_dict, self.num_cb_stripes, self.num_cbs_stripes, self.lb_height)
        self.local_mux.set_block_widths(self.area_dict, self.num_ic_stripes, self.num_ics_stripes, self.lb_height)

        # measure the width of each stripe:
        self.w_sb = self.sb_mux.stripe_avg_width
        self.w_cb = self.cb_mux.stripe_avg_width
        
        self.w_ic = self.local_mux.stripe_avg_width
        # TODO implement lut in blocks
        self.w_lut = (self.specs.N * self.area_dict["lut_and_drivers"] - self.specs.N * (2**self.specs.K) * self.area_dict["sram"]) / (self.num_lut_stripes * self.lb_height)
        # TODO fix the mode breaking stuff
        # if self.specs.enable_carry_chain == 1:
        self.w_cc = self.area_dict["cc_area_total"] / (self.num_cc_stripes * self.lb_height)
        self.w_ffble = self.area_dict["ffableout_area_total"] / (self.num_ffble_stripes * self.lb_height)
        
        # These are SRAM widths from subcircuits
        self.w_ssb = self.sb_mux.stripe_avg_sram_width
        self.w_scb = self.cb_mux.stripe_avg_sram_width
        self.w_sic = self.local_mux.stripe_avg_sram_width
        self.w_slut = (self.specs.N * (2**self.specs.K) * self.area_dict["sram"]) / (self.num_luts_stripes * self.lb_height)

        # create a temporary dictionary of stripe width to use in distance calculation:
        self.dict_real_widths = {}
        self.dict_real_widths["sb_sram"] = self.w_ssb
        self.dict_real_widths["sb"] = self.w_sb
        self.dict_real_widths["cb"] = self.w_cb
        self.dict_real_widths["cb_sram"] = self.w_scb
        self.dict_real_widths["ic_sram"] = self.w_sic
        self.dict_real_widths["ic"] = self.w_ic
        self.dict_real_widths["lut_sram"] = self.w_slut
        self.dict_real_widths["lut"] = self.w_lut
        #if self.specs.enable_carry_chain == 1:
        self.dict_real_widths["cc"] = self.w_cc
        self.dict_real_widths["ffble"] = self.w_ffble

        # what distances do we need?
        self.d_cb_to_ic = 0.0 # Used in Logic Cluster update_wires
        self.d_ic_to_lut = 0.0 # Unused
        self.d_lut_to_cc = 0.0 # Unused
        self.d_cc_to_ffble = 0.0 # Unused
        self.d_ffble_to_sb = 0.0 # Used in Cluster Output Load
        self.d_ffble_to_ic = 0.0 # Used in Logic Cluster 


        # Calculate the width of tile with the new stripe widths
        real_tile_width: float = sum([self.dict_real_widths[stripe] * self.stripe_order.count(stripe) for stripe in self.stripe_order])

        # Get all unique combos of stripe widths        
        stripe_mappings: List[Tuple[str, int]] = [
            (stripe_key, i) for i, stripe_key in enumerate(self.stripe_order)
        ]
        # get all possible 2 pair combinations
        unique_pairs: List[Tuple[str, int]] =  itertools.combinations(stripe_mappings, 2)

        for pair in unique_pairs:
            stripe1: Tuple[str, int] = pair[0]
            stripe2: Tuple[str, int] = pair[1]
            stripe1_key: str = stripe1[0]
            stripe2_key: str = stripe2[0]
            # stripe1: Tuple[str, int] = (stripe1_key, self.stripe_order.index(stripe1_key) )
            # stripe2: Tuple[str, int] = (stripe2_key, self.stripe_order.index(stripe2_key) )
            # skip over key pairs we don't care about
            if (stripe1_key != "cb" and stripe1_key != "ic" and stripe1_key != "lut" and stripe1_key != "cc" and stripe1_key != "ffble" and stripe1_key != "sb") and (stripe1_key != stripe2_key):
                continue
            dist = self.get_dist_bw_stripes(stripe1, stripe2, self.dict_real_widths)
            
            if (stripe1_key == "cb" and stripe2_key == "ic") or (stripe2_key == "ic" and stripe2_key == "cb"):
                if dist > self.d_cb_to_ic:
                    self.d_cb_to_ic = dist
            elif (stripe1_key == "ic" and stripe2_key == "lut") or (stripe2_key == "lut" and stripe2_key == "ic"):
                if dist > self.d_ic_to_lut:
                    self.d_ic_to_lut = dist
            elif (stripe1_key == "lut" and stripe2_key == "cc") or (stripe2_key == "cc" and stripe2_key == "lut"):
                if dist > self.d_lut_to_cc:
                    self.d_lut_to_cc = dist
            elif (stripe1_key == "cc" and stripe2_key == "ffble") or (stripe2_key == "ffble" and stripe2_key == "cc"):
                if dist > self.d_cc_to_ffble:
                    self.d_cc_to_ffble = dist
            elif (stripe1_key == "ffble" and stripe2_key == "sb") or (stripe2_key == "sb" and stripe2_key == "ffble"):
                if dist > self.d_ffble_to_sb:
                    self.d_ffble_to_sb = dist      

        # Compute Dist logging
        if consts.VERBOSITY == consts.DEBUG:
            csv_outdir = "debug"
            tile_width_keys: List[str] = [
                "sb_sram",
                "sb",
                "cb",
                "cb_sram",
                "ic_sram",
                "ic",
                "lut_sram",
                "lut",
                "cc",
                "ffble",
            ]
            # Absolute widths
            tile_widths: Dict[str, float] = {
                **fpga_state_fmt(self, "VERIF"),
                # Divide the real widths of each block by width dict to get percentage of tile width
                **{key: self.dict_real_widths[key] for key in tile_width_keys},
            }
            width_csv_outfpath = os.path.join(csv_outdir, "tile_width_totals.csv")
            rg_utils.write_single_dict_to_csv(tile_widths, width_csv_outfpath, "a")
            # Tile width as a ratio of the real tile width
            tile_width_ratios: Dict[str, float] = {
                **fpga_state_fmt(self, "VERIF"),
                # Divide the real widths of each block by width dict to get percentage of tile width
                **{key: self.dict_real_widths[key]/(real_tile_width) for key in tile_width_keys},
            }
            width_csv_outfpath = os.path.join(csv_outdir, "tile_width_total_ratios.csv")
            rg_utils.write_single_dict_to_csv(tile_width_ratios, width_csv_outfpath, "a")
            dist_keys: List[str] = [
                "d_cb_to_ic",            
                "d_ic_to_lut",
                "d_lut_to_cc",
                "d_cc_to_ffble",
                "d_ffble_to_sb",
                "d_ffble_to_ic",
            ]


            dists_dict = {
                dist_key: getattr(self, dist_key) for dist_key in dist_keys
            }

            dist_ratios_dict = {
                dist_key: getattr(self, dist_key)/real_tile_width for dist_key in dist_keys
            }

            # Assertion to make sure none of these distances are larger than a tile
            assert all([dist <= real_tile_width for dist in dists_dict.values()]), "Distance is larger than tile width, this is not possible"
        
            tile_dists: Dict[str, float] = {
                **fpga_state_fmt(self, "VERIF"),
                **dists_dict,
            }
            dists_csv_outfpath = os.path.join(csv_outdir, "tile_dist_totals.csv")
            rg_utils.write_single_dict_to_csv(tile_dists, dists_csv_outfpath, "a")
            
            tile_dists: Dict[str, float] = {
                **fpga_state_fmt(self, "VERIF"),
                **dist_ratios_dict,
            }
            dists_csv_outfpath = os.path.join(csv_outdir, "tile_dist_total_ratios.csv")
            rg_utils.write_single_dict_to_csv(tile_dists, dists_csv_outfpath, "a")

        self.compute_distance_cnt += 1


    def update_wires(self):
        """ This function updates self.wire_lengths and self.wire_layers. It passes wire_lengths and wire_layers to member 
            objects (like sb_mux) to update their wire lengths and layers. """
        
        # Update wire lengths and layers for all subcircuits
        if not self.lb_height:
            # Iterate over parameterized ckts AND list of load circuits
            sb_mux: sb_mux_lib.SwitchBlockMux
            for sb_mux in self.sb_muxes:
                sb_mux.update_wires(self.width_dict, self.wire_lengths, self.wire_layers, ratio = 1.0)
            cb_mux: cb_mux_lib.ConnectionBlockMux
            for cb_mux in self.cb_muxes:
                cb_mux.update_wires(self.width_dict, self.wire_lengths, self.wire_layers, ratio = 1.0)
            init_num_cb_stripes: int = 2
            init_num_sb_stripes: int = 2
            # Routing Wire Loads
            gen_r_wire_load: gen_r_load_lib.RoutingWireLoad
            for gen_r_wire_load in self.gen_routing_wire_loads:
                gen_r_wire_load.update_wires(self.width_dict, self.wire_lengths, self.wire_layers, init_num_cb_stripes, init_num_sb_stripes)
            gen_ble_output_load: gen_r_load_lib.GeneralBLEOutputLoad
            for gen_ble_output_load in self.gen_ble_output_loads:
                gen_ble_output_load.update_wires(self.width_dict, self.wire_lengths, self.wire_layers)
            # Logic clusters
            for logic_cluster in self.logic_clusters:
                logic_cluster.update_wires(
                    self.width_dict, 
                    self.wire_lengths, 
                    self.wire_layers, 
                    ic_ratio = 1.0,
                    lut_ratio = 1.0
                )
        else:
            # These ratios seem to be in units of stripes per switch block 
            sb_ratio: float = (self.lb_height / (self.sb_mux.total_num_per_tile / self.num_sb_stripes)) / self.dict_real_widths["sb"]
            if sb_ratio < 1.0:
                sb_ratio = 1 / sb_ratio
            
            #if the ratio is larger than 2.0, we can look at this stripe as two stripes put next to each other and partly fix the ratio:
            cb_ratio: float = (self.lb_height / (self.cb_mux.total_num_per_tile / self.num_cb_stripes)) / self.dict_real_widths["cb"]
            if cb_ratio < 1.0:
                cb_ratio = 1 / cb_ratio
                
            #if the ratio is larger than 2.0, we can look at this stripe as two stripes put next to each other and partly fix the ratio:
            ic_ratio: float = (self.lb_height / (self.local_mux.total_num_per_tile / self.num_ic_stripes)) / self.dict_real_widths["ic"]
            if ic_ratio < 1.0:
                ic_ratio = 1 / ic_ratio
                
            #if the ratio is larger than 2.0, we can look at this stripe as two stripes put next to each other and partly fix the ratio:			
            lut_ratio: float = (self.lb_height / (self.specs.N / self.num_lut_stripes)) / self.dict_real_widths["lut"]
            if lut_ratio < 1.0:
                lut_ratio = 1 / lut_ratio
            

            # Iterate over parameterized ckts AND list of load circuits
            sb_mux: sb_mux_lib.SwitchBlockMux
            for sb_mux in self.sb_muxes:
                sb_mux.update_wires(self.width_dict, self.wire_lengths, self.wire_layers, sb_ratio)
            cb_mux: cb_mux_lib.ConnectionBlockMux
            for cb_mux in self.cb_muxes:
                cb_mux.update_wires(self.width_dict, self.wire_lengths, self.wire_layers, cb_ratio)
            # Routing Wire Loads
            gen_r_wire_load: gen_r_load_lib.RoutingWireLoad
            for gen_r_wire_load in self.gen_routing_wire_loads:
                gen_r_wire_load.update_wires(self.width_dict, self.wire_lengths, self.wire_layers, self.num_sb_stripes, self.num_cb_stripes, self.lb_height)
            gen_ble_output_load: gen_r_load_lib.GeneralBLEOutputLoad
            for gen_ble_output_load in self.gen_ble_output_loads:
                gen_ble_output_load.update_wires(self.width_dict, self.wire_lengths, self.wire_layers, self.d_ffble_to_sb, self.lb_height)
            # Logic clusters
            for logic_cluster in self.logic_clusters:
                logic_cluster.update_wires(
                    self.width_dict, 
                    self.wire_lengths, 
                    self.wire_layers, 
                    ic_ratio, 
                    lut_ratio,
                    self.d_ffble_to_ic,
                    self.d_cb_to_ic + self.lb_height,
                )
        
        if self.specs.enable_carry_chain == 1:
            for carry_chain in self.carry_chains:
                carry_chain.update_wires(self.width_dict, self.wire_lengths, self.wire_layers)
            for carry_chain_periph in self.carry_chain_periphs:
                carry_chain_periph.update_wires(self.width_dict, self.wire_lengths, self.wire_layers)
            for carry_chain_mux in self.carry_chain_muxes:
                carry_chain_mux.update_wires(self.width_dict, self.wire_lengths, self.wire_layers)
            for carry_chain_inter in self.carry_chain_inter_clusters:
                carry_chain_inter.update_wires(self.width_dict, self.wire_lengths, self.wire_layers)
            if self.specs.carry_chain_type == "skip":
                for carry_chain_and in self.carry_chain_skip_ands:
                    carry_chain_and.update_wires(self.width_dict, self.wire_lengths, self.wire_layers)
                for carry_chain_skip_mux in self.carry_chain_skip_muxes:
                    carry_chain_skip_mux.update_wires(self.width_dict, self.wire_lengths, self.wire_layers)

        if self.specs.enable_bram_block == 1:
            self.RAM.update_wires(self.width_dict, self.wire_lengths, self.wire_layers)

        for hardblock in self.hardblocklist:
            hardblock.update_wires(self.width_dict, self.wire_lengths, self.wire_layers)  
            hardblock.mux.update_wires(self.width_dict, self.wire_lengths, self.wire_layers)   

        
        # Update Wires logging
        if consts.VERBOSITY == consts.DEBUG:
            fpga_state_to_csv(self, "VERIF", "wire_length")

            # Per circuit wire logging
            unique_subckts: List[Type[c_ds.SizeableCircuit]] = list(self.tb_lib.keys())
            for subckt in unique_subckts:
                fpga_state_to_csv(self, "VERIF", "wire_length", subckt)

        self.update_wires_cnt += 1

    def update_wire_rc(self):
        """ This function updates self.wire_rc_dict based on the FPGA's self.wire_lengths and self.wire_layers."""
            
        # Calculate R and C for each wire
        for wire, length in self.wire_lengths.items():
            # Get wire layer
            layer: int = self.wire_layers[wire]
            # Get R and C per unit length for wire layer
            rc: Tuple[ float ] = self.metal_stack[layer]
            # Calculate total wire R and C
            resistance: float = rc[0] * length
            capacitance: float = rc[1] * length / 2
            # Add to wire_rc dictionary
            self.wire_rc_dict[wire] = (resistance, capacitance) 

    
        
    def set_ckt_meas(
        self,
        in_ckt_meas : Dict[Type[c_ds.SizeableCircuit], Dict[str, List[float] | List[bool]]],
        sw_idx: int, # What sweep index of our meas data are we using to set values
        update_del_dict: bool = True # Do we update values stored in delay dict?
    ) -> float:
        """ 
        This function sets the measurements of the circuits in the in_ckt_meas dictionary to the delay_dict. 
        It returns the critical path delay of the circuits in in_ckt_meas.
        """
        crit_path_delay: float = 0.0
        for ckt, meas in in_ckt_meas.items():
            for key in ["trise", "tfall", "delay", "power"]:
                setattr(ckt, key, meas[key][sw_idx])
                ## debug print 
                # sp_name = ckt.sp_name if ckt.sp_name else ckt.name 
                # print(f"Setting {sp_name} {key} to {meas[key][sw_idx]}")
            # Get the critical path delay of the circuit
            crit_path_delay += ckt.delay * ckt.delay_weight / len(in_ckt_meas.keys()) # TODO initialize delay_weights somewhere rather than evenly weighting by dividing by len
            # Update the delay dictionary with the measurements
            if update_del_dict:
                sp_name = ckt.sp_name if hasattr(ckt, "sp_name") and ckt.sp_name else ckt.name
                self.delay_dict[sp_name] = ckt.delay
                
        return crit_path_delay
        
    def merge_and_set_meas_sw_pt(
        self,
        in_tb_meas: Dict[Type[c_ds.SimTB], 
            Dict[str, 
                List[float] | List[bool]
            ]
        ],
        *args,
        **kwargs,
    ) -> float:
        """
            Merges and sets delays and circuit sim fields for a single sweep point, if there are multiple sweeps this will fail 
            returns critical path component
        """
        ckt_meas = merge_tb_meas(in_tb_meas)
        assert len( list(ckt_meas.values())[0]['delay'] ) == 1, "This function is only for single sweep point"
        crit_path_delay = self.set_ckt_meas(ckt_meas, 0, *args, **kwargs)
        return crit_path_delay

    def update_delays(self, spice_interface: spice.SpiceInterface):
        """ 
        Get the HSPICE delays for each subcircuit. 
        This function returns "False" if any of the HSPICE simulations failed.
        """
        
        print("*** UPDATING DELAYS ***")
        crit_path_delay: float = 0
        # Dict[
        #     Type[c_ds.SizeableCircuit],
        #     float
        # ]
        valid_delay = True

        # Run HSPICE on all subcircuits and collect the total tfall and trise for that 
        # subcircuit. We are only doing a single run on HSPICE so we expect the result
        # to be in [0] of the spice_meas dictionary. We check to make sure that the 
        # HSPICE simulation was successful by checking if any of the SPICE measurements
        # were "failed". If that is the case, we set the delay of that subcircuit to 1
        # second and set our valid_delay flag to False.

        # Create parameter dict of all current transistor sizes and wire rc
        parameter_dict = {}
        for tran_name, tran_size in self.transistor_sizes.items():
            if not self.specs.use_finfet:
                parameter_dict[tran_name] = [1e-9 * tran_size * self.specs.min_tran_width]
            else :
                parameter_dict[tran_name] = [tran_size]

        for wire_name, rc_data in self.wire_rc_dict.items():
            parameter_dict[wire_name + "_res"] = [rc_data[0]]
            parameter_dict[wire_name + "_cap"] = [rc_data[1]*1e-15]

        # Run HSPICE on all subcircuits and collect the total tfall and trise for that 
        # subcircuit. We are only doing a single run on HSPICE so we expect the result
        # to be in [0] of the spice_meas dictionary. We check to make sure that the 
        # HSPICE simulation was successful by checking if any of the SPICE measurements
        # were "failed". If that is the case, we set the delay of that subcircuit to 1
        # second and set our valid_delay flag to False.

        # SB MUX
        sb_mux_meas: Dict[
            sb_mux_lib.SwitchBlockMuxTB, Dict[str, List[float] | List[bool]]
        ] = sim_tbs(self.sb_mux_tbs, spice_interface, parameter_dict)

        # Sets delays + power in ckt objects 
        crit_path_delay += self.merge_and_set_meas_sw_pt(sb_mux_meas)

        # CB MUX
        cb_mux_meas: Dict[
            cb_mux_lib.ConnectionBlockMuxTB, Dict[str, List[float] | List[bool]]
        ] = sim_tbs(self.cb_mux_tbs, spice_interface, parameter_dict)
        # Sets delays + power in ckt objects 
        crit_path_delay += self.merge_and_set_meas_sw_pt(cb_mux_meas)

        # LOCAL MUX
        local_mux_meas: Dict[
            lb_lib.LocalMuxTB, Dict[str, List[float] | List[bool]]
        ] = sim_tbs(self.local_mux_tbs, spice_interface, parameter_dict)
        # Sets delays + power in ckt objects 
        crit_path_delay += self.merge_and_set_meas_sw_pt(local_mux_meas)

        # Local BLE Output
        local_ble_output_meas: Dict[
           ble_lib.LocalBLEOutputTB, Dict[str, List[float] | List[bool]]
        ] = sim_tbs(self.local_ble_output_tbs, spice_interface, parameter_dict)
        # Sets delays + power in ckt objects 
        crit_path_delay += self.merge_and_set_meas_sw_pt(local_ble_output_meas)

        # General BLE Output
        gen_ble_output_meas: Dict[
            ble_lib.GeneralBLEOutputTB, Dict[str, List[float] | List[bool]]
        ] = sim_tbs(self.general_ble_output_tbs, spice_interface, parameter_dict)
        # Sets delays + power in ckt objects 
        crit_path_delay += self.merge_and_set_meas_sw_pt(gen_ble_output_meas)
        
        # Fracurable LUT MUX
        # TODO make sure even if tbs are empty this is fine
        flut_mux_meas: Dict[
            ble_lib.FlutMuxTB, Dict[str, List[float] | List[bool]]
        ] = sim_tbs(self.flut_mux_tbs, spice_interface, parameter_dict)
        # Sets delays + power in ckt objects
        flut_mux_merged_meas = merge_tb_meas(flut_mux_meas)
        self.set_ckt_meas(flut_mux_merged_meas, sw_idx = 0)
        
        # LUT
        lut_meas: Dict[
            lut_lib.LUTTB, Dict[str, List[float] | List[bool]]
        ] = sim_tbs(self.lut_tbs, spice_interface, parameter_dict)
        # Sets delays + power in ckt objects 
        lut_merged_meas = merge_tb_meas(lut_meas)
        self.set_ckt_meas(lut_merged_meas, sw_idx = 0)

        # LUT Inputs
        # Get delay for all paths through the LUT.
        # We get delay for each path through the LUT as well as for the LUT input drivers.
        lut_input_measures: Dict[
            Dict[ lut_lib.LUTInputTB, Dict[str, List[float] | List[bool]] ]
        ] = {}
        lut_input_driver_meas: Dict[
            lut_lib.LUTInputDriverTB, Dict[str, List[float] | List[bool]]
        ] = {}
        lut_input_not_driver_meas: Dict[
                lut_lib.LUTInputDriverTB, Dict[str, List[float] | List[bool]]
        ] = {}

        # For clairy
        sw_idx: int = 0
        ckt_idx: int = 0        
        
        # only sorting for clarity no real reason
        for lut_in_key in sorted(list(self.lut_input_tbs.keys())):
            # TODO update for multi ckt support
            lut_input: lut_lib.LUTInput = self.lut_inputs[lut_in_key][ckt_idx]
            # LUT Input Driver with LUT loading
            lut_input_meas: Dict[
                lut_lib.LUTInputTB, Dict[str, List[float] | List[bool]]
            ] = sim_tbs(self.lut_input_tbs[lut_in_key], spice_interface, parameter_dict)
            lut_input_measures[lut_in_key] = lut_input_meas

            # TODO make this cleaner, we are kinda doing a workaround way of setting values in the LUTInput obj
            # Get merged delays but DONT set as we do a custom thing for LUT inputs 
            lut_input_merged_meas = merge_tb_meas(lut_input_meas)

            # If we're on the fracturable input which is the last LUT input then we set the fmux delay for this input
            if (lut_in_key == "f" and self.specs.use_fluts and self.specs.K == 6) or \
                (lut_in_key == "e" and self.specs.use_fluts and self.specs.K == 5):
                # TODO update for multi flut ckt support
                lut_input.tfall = list(flut_mux_merged_meas.values())[ckt_idx]["tfall"][sw_idx]
                lut_input.trise = list(flut_mux_merged_meas.values())[ckt_idx]["trise"][sw_idx]
                lut_input.delay = max(lut_input.tfall, lut_input.trise)
                self.delay_dict[lut_input.name] = lut_input.delay
            else:    
                # TODO update for multi ckt support
                meas = list(lut_input_merged_meas.values())[ckt_idx]
                in_meas: Dict[str, List[float] | List[bool]] = copy.deepcopy(meas)
                if self.specs.use_fluts:
                    for del_key in ["tfall", "trise"]:
                        in_meas[del_key][ckt_idx] += list(flut_mux_merged_meas.values())[ckt_idx][del_key][sw_idx]
                    in_meas["delay"] = max(in_meas["tfall"], in_meas["trise"])
                lut_input.tfall = in_meas["tfall"][sw_idx]
                lut_input.trise = in_meas["trise"][sw_idx]
                lut_input.delay = in_meas["delay"][sw_idx]
                self.delay_dict[lut_input.name] = in_meas["delay"][sw_idx]

            # LUT Input drivers
            lut_input_driver_meas: Dict[
                lut_lib.LUTInputDriverTB, Dict[str, List[float] | List[bool]]
            ] = sim_tbs(self.lut_in_driver_tbs[lut_in_key], spice_interface, parameter_dict)
            lut_in_drv_merged_meas = merge_tb_meas(lut_input_driver_meas)
            self.set_ckt_meas(lut_in_drv_merged_meas, sw_idx = 0)            


            # LUT Input Not drivers
            lut_input_not_driver_meas: Dict[
                lut_lib.LUTInputDriverTB, Dict[str, List[float] | List[bool]]
            ] = sim_tbs(self.lut_in_not_driver_tbs[lut_in_key], spice_interface, parameter_dict)
            lut_in_not_drv_merged_meas = merge_tb_meas(lut_input_not_driver_meas)
            self.set_ckt_meas(lut_in_not_drv_merged_meas, sw_idx = 0)

            # Calculate lut delay
            # TODO update for multi ckt support
            lut_in_drv_delay: float = list(lut_in_drv_merged_meas.values())[0]["delay"][0]
            lut_in_not_drv_delay: float = list(lut_in_not_drv_merged_meas.values())[0]["delay"][0]
            lut_delay: float = lut_input.delay + max(lut_in_drv_delay, lut_in_not_drv_delay)
            if self.specs.use_fluts:
                # TODO update for multi ckt support
                flut_mux: ble_lib.FlutMux = list(flut_mux_merged_meas.keys())[0]
                lut_delay += flut_mux.delay 
            
            assert lut_delay > 0, f"LUT delay must be greater than 0 {lut_delay}"

            # Add to critical path
            crit_path_delay += lut_delay * lut_input.delay_weight
        
        # Add flut to critical
        if self.specs.use_fluts:
            # TODO update for multi ckt support
            flut_mux: ble_lib.FlutMux = list(flut_mux_merged_meas.keys())[0]
            crit_path_delay += flut_mux.delay * flut_mux.delay_weight

        self.delay_dict["rep_crit_path"] = crit_path_delay

        # TODO figure out why we don't include cc in crit path
        if self.specs.enable_carry_chain:
            # Carry Chain
            cc_meas: Dict[
                cc_lib.CarryChainTB, Dict[str, List[float] | List[bool]]
            ] = sim_tbs(self.carry_chain_tbs, spice_interface, parameter_dict)
            # Sets delays + power in ckt objects
            crit_path_delay += self.merge_and_set_meas_sw_pt(cc_meas)
                        
            # Carry Chain Peripherial
            cc_periph_meas: Dict[
                cc_lib.CarryChainPerTB, Dict[str, List[float] | List[bool]]
            ] = sim_tbs(self.carry_chain_per_tbs, spice_interface, parameter_dict)
            # Sets delays + power in ckt objects
            crit_path_delay += self.merge_and_set_meas_sw_pt(cc_periph_meas)

            # Carry Chain Mux
            cc_mux_meas: Dict[
                cc_lib.CarryChainMuxTB, Dict[str, List[float] | List[bool]]
            ] = sim_tbs(self.carry_chain_mux_tbs, spice_interface, parameter_dict)
            # Sets delays + power in ckt objects
            crit_path_delay += self.merge_and_set_meas_sw_pt(cc_mux_meas)
            
            # Carry Chain Inter Cluster
            cc_inter_meas: Dict[
                cc_lib.CarryChainInterClusterTB, Dict[str, List[float] | List[bool]]
            ] = sim_tbs(self.carry_chain_inter_tbs, spice_interface, parameter_dict)
            # Sets delays + power in ckt objects
            crit_path_delay += self.merge_and_set_meas_sw_pt(cc_inter_meas)

            if self.specs.carry_chain_type == "skip":
                # Carry Chain Skip AND
                # TODO make sure even if tbs are empty this is fine
                cc_skip_and_meas: Dict[
                    cc_lib.CarryChainSkipAndTB, Dict[str, List[float] | List[bool]]
                ] = sim_tbs(self.carry_chain_skip_and_tbs, spice_interface, parameter_dict)
                # Sets delays + power in ckt objects
                crit_path_delay += self.merge_and_set_meas_sw_pt(cc_skip_and_meas)

                # Carry Chain Skip Mux
                cc_skip_mux_meas: Dict[
                    cc_lib.CarryChainSkipMuxTB, Dict[str, List[float] | List[bool]]
                ] = sim_tbs(self.carry_chain_skip_mux_tbs, spice_interface, parameter_dict)
                # Sets delays + power in ckt objects
                crit_path_delay += self.merge_and_set_meas_sw_pt(cc_skip_mux_meas)

        # Hardblocks
        # TODO add hardblock support
        # hardblock_meas: Dict[
        #     hardblock_lib.HardBlockTB, Dict[str, float]
        # ] = sim_tbs(self.hardblock_tbs, spice_interface, parameter_dict)

        # RAM
        # TODO figure out why all the RAM setting of critical path delay were commented out
        if self.specs.enable_bram_block:
            ram_valid = self.update_ram_delays(parameter_dict, spice_interface)

        # After getting the delays across subckts and tesbenches we need to combine them for each subckt and assign it trise / tfall / delay / power values.

        # Update Delays logging
        if consts.VERBOSITY == consts.DEBUG:
            fpga_state_to_csv(self, "VERIF", "delay")

        self.update_delays_cnt += 1
            

    def print_specs(self):

        print("|------------------------------------------------------------------------------|")
        print("|   FPGA Architecture Specs                                                    |")
        print("|------------------------------------------------------------------------------|")
        print("")
        print("  Number of BLEs per cluster (N): " + str(self.specs.N))
        print("  LUT size (K): " + str(self.specs.K))
        print("  Channel width (W): " + str(self.specs.W))
        # print("  Wire segment length (L): " + str(self.specs.L))
        print("  Number cluster inputs (I): " + str(self.specs.I))
        print("  Number of BLE outputs to general routing: " + str(self.specs.num_ble_general_outputs))
        print("  Number of BLE outputs to local routing: " + str(self.specs.num_ble_local_outputs))
        print("  Number of cluster outputs: " + str(self.specs.num_cluster_outputs))
        print("  Switch block flexibility (Fs): " + str(self.specs.Fs))
        print("  Cluster input flexibility (Fcin): " + str(self.specs.Fcin))
        print("  Cluster output flexibility (Fcout): " + str(self.specs.Fcout))
        print("  Local MUX population (Fclocal): " + str(self.specs.Fclocal))
        print("")
        print("|------------------------------------------------------------------------------|")
        print("")
        
        
    def print_details(self, report_fpath: str):

        utils.print_and_write(report_fpath, "|------------------------------------------------------------------------------|")
        utils.print_and_write(report_fpath, "|   FPGA Implementation Details                                                |")
        utils.print_and_write(report_fpath, "|------------------------------------------------------------------------------|")
        utils.print_and_write(report_fpath, "")

        for sb_mux in self.sb_muxes:
            sb_mux.print_details(report_fpath)
        for cb_mux in self.cb_muxes:
            cb_mux.print_details(report_fpath)
        for gen_r_wire_load in self.gen_routing_wire_loads:
            gen_r_wire_load.print_details(report_fpath)
        for gen_ble_output_load in self.gen_ble_output_loads:
            gen_ble_output_load.print_details(report_fpath)
        for logic_cluster in self.logic_clusters:
            logic_cluster.print_details(report_fpath)

        if self.specs.enable_bram_block == 1:
            self.RAM.print_details(report_fpath)
        for hb in self.hardblocklist:
            hb.print_details(report_fpath)

        utils.print_and_write(report_fpath, "|------------------------------------------------------------------------------|")
        utils.print_and_write(report_fpath, "")

        return


    def _create_lib_files(self):
        """ Create SPICE library files and add headers. """

        # Create Subcircuits file
        sc_file = open(self.subcircuits_filename, 'w')
        sc_file.write("*** SUBCIRCUITS\n\n")
        sc_file.write(".LIB SUBCIRCUITS\n\n")
        sc_file.close()
       

    def _end_lib_files(self):
        """ End the SPICE library files. """

        # Subcircuits file
        sc_file = open(self.subcircuits_filename, 'a')
        sc_file.write(".ENDL SUBCIRCUITS")
        sc_file.close()
       

    def _generate_basic_subcircuits(self):
        """ Generates the basic subcircuits SPICE file (pass-transistor, inverter, etc.) """
        
        print("Generating basic subcircuits")
        
        # Open basic subcircuits file and write heading
        basic_sc_file = open(self.basic_subcircuits_filename, 'w')
        basic_sc_file.write("*** BASIC SUBCIRCUITS\n\n")
        basic_sc_file.write(".LIB BASIC_SUBCIRCUITS\n\n")
        basic_sc_file.close()

        # Generate wire subcircuit
        basic_subcircuits.wire_generate(self.basic_subcircuits_filename)
        # Generate pass-transistor subcircuit
        basic_subcircuits.ptran_generate(self.basic_subcircuits_filename, self.specs.use_finfet)
        basic_subcircuits.ptran_pmos_generate(self.basic_subcircuits_filename, self.specs.use_finfet)
        # Generate transmission gate subcircuit
        basic_subcircuits.tgate_generate(self.basic_subcircuits_filename, self.specs.use_finfet)
        basic_subcircuits.tgate_generate_lp(self.basic_subcircuits_filename, self.specs.use_finfet)
        # Generate level-restore subcircuit
        basic_subcircuits.rest_generate(self.basic_subcircuits_filename, self.specs.use_finfet)
        # Generate inverter subcircuit
        basic_subcircuits.inverter_generate(self.basic_subcircuits_filename, self.specs.use_finfet, self.specs.memory_technology)
        # Generate nand2
        basic_subcircuits.nand2_generate(self.basic_subcircuits_filename, self.specs.use_finfet)
        basic_subcircuits.nand2_generate_lp(self.basic_subcircuits_filename, self.specs.use_finfet)
        # Generate nand3 
        basic_subcircuits.nand3_generate(self.basic_subcircuits_filename, self.specs.use_finfet)
        basic_subcircuits.nand3_generate_lp(self.basic_subcircuits_filename, self.specs.use_finfet)
        #generate ram tgate
        basic_subcircuits.RAM_tgate_generate(self.basic_subcircuits_filename, self.specs.use_finfet)
        basic_subcircuits.RAM_tgate_generate_lp(self.basic_subcircuits_filename, self.specs.use_finfet)

        # Write footer
        basic_sc_file = open(self.basic_subcircuits_filename, 'a')
        basic_sc_file.write(".ENDL BASIC_SUBCIRCUITS")
        basic_sc_file.close()
        
        
    def _generate_process_data(self):
        """ Write the process data library file. It contains voltage levels, gate length and device models. """
        
        print("Generating process data file")

        
        process_data_file = open(self.process_data_filename, 'w')
        process_data_file.write("*** PROCESS DATA AND VOLTAGE LEVELS\n\n")
        process_data_file.write(".LIB PROCESS_DATA\n\n")
        process_data_file.write("* Voltage levels\n")
        process_data_file.write(".PARAM supply_v = " + str(self.specs.vdd) + "\n")
        process_data_file.write(".PARAM sram_v = " + str(self.specs.vsram) + "\n")
        process_data_file.write(".PARAM sram_n_v = " + str(self.specs.vsram_n) + "\n")
        process_data_file.write(".PARAM Rcurrent = " + str(self.specs.worst_read_current) + "\n")
        process_data_file.write(".PARAM supply_v_lp = " + str(self.specs.vdd_low_power) + "\n\n")


        if self.specs.memory_technology == "MTJ":
            process_data_file.write(".PARAM target_bl = " + str(0.04) + "\n\n")

        if constants.use_lp_transistor == 0 :
            process_data_file.write(".PARAM sense_v = " + str(self.specs.vdd - self.specs.sense_dv) + "\n\n")
        else:
            process_data_file.write(".PARAM sense_v = " + str(self.specs.vdd_low_power - self.specs.sense_dv) + "\n\n")


        process_data_file.write(".PARAM mtj_worst_high = " + str(self.specs.MTJ_Rhigh_worstcase) + "\n")
        process_data_file.write(".PARAM mtj_worst_low = " + str(self.specs.MTJ_Rlow_worstcase) + "\n")
        process_data_file.write(".PARAM mtj_nominal_low = " + str(self.specs.MTJ_Rlow_nominal) + "\n\n")
        process_data_file.write(".PARAM mtj_nominal_high = " + str(6250) + "\n\n") 
        process_data_file.write(".PARAM vref = " + str(self.specs.vref) + "\n")
        process_data_file.write(".PARAM vclmp = " + str(self.specs.vclmp) + "\n")

        process_data_file.write("* Geometry\n")
        process_data_file.write(".PARAM gate_length = " + str(self.specs.gate_length) + "n\n")
        process_data_file.write(".PARAM trans_diffusion_length = " + str(self.specs.trans_diffusion_length) + "n\n")
        process_data_file.write(".PARAM min_tran_width = " + str(self.specs.min_tran_width) + "n\n")
        process_data_file.write(".param rest_length_factor=" + str(self.specs.rest_length_factor) + "\n")
        process_data_file.write("\n")

        process_data_file.write("* Supply voltage.\n")
        process_data_file.write("VSUPPLY vdd gnd supply_v\n")
        process_data_file.write("VSUPPLYLP vdd_lp gnd supply_v_lp\n")
        process_data_file.write("* SRAM voltages connecting to gates\n")
        process_data_file.write("VSRAM vsram gnd sram_v\n")
        process_data_file.write("VrefMTJn vrefmtj gnd vref\n")
        process_data_file.write("Vclmomtjn vclmpmtj gnd vclmp\n")
        process_data_file.write("VSRAM_N vsram_n gnd sram_n_v\n\n")
        process_data_file.write("* Device models\n")
        process_data_file.write(".LIB \"" + self.specs.model_path + "\" " + self.specs.model_library + "\n\n")
        process_data_file.write(".ENDL PROCESS_DATA")
        process_data_file.close()
        
        
    def _generate_includes(self):
        """ Generate the includes file. Top-level SPICE decks should only include this file. """
    
        print("Generating includes file")
    
        includes_file = open(self.includes_filename, 'w')
        includes_file.write("*** INCLUDE ALL LIBRARIES\n\n")
        includes_file.write(".LIB INCLUDES\n\n")
        includes_file.write("* Include process data (voltage levels, gate length and device models library)\n")
        includes_file.write(".LIB \"process_data.l\" PROCESS_DATA\n\n")
        includes_file.write("* Include transistor parameters\n")
        includes_file.write("* Include wire resistance and capacitance\n")
        #includes_file.write(".LIB \"wire_RC.l\" WIRE_RC\n\n")
        includes_file.write("* Include basic subcircuits\n")
        includes_file.write(".LIB \"basic_subcircuits.l\" BASIC_SUBCIRCUITS\n\n")
        includes_file.write("* Include subcircuits\n")
        includes_file.write(".LIB \"subcircuits.l\" SUBCIRCUITS\n\n")
        includes_file.write("* Include sweep data file for .DATA sweep analysis\n")
        includes_file.write(".INCLUDE \"sweep_data.l\"\n\n")
        includes_file.write(".ENDL INCLUDES")
        includes_file.close()
        
        
    def _generate_sweep_data(self):
        """ Create the sweep_data.l file that COFFE uses to perform 
            multi-variable HSPICE parameter sweeping. """

        sweep_data_file = open(self.sweep_data_filename, 'w')
        sweep_data_file.close()
        

    def _update_transistor_sizes(self, element_names: List[str], combo: Tuple[float | int], use_finfet: bool, inv_ratios: Dict[str, Any] = None):
        """ This function is used to update self.transistor_sizes for a particular transistor sizing combination.
            'element_names' is a list of elements (ptran, inv, etc.) that need their sizes updated.
            'combo' is a particular transistor sizing combination for the transistors in 'element_names'
            'inv_ratios' are the inverter P/N ratios for this transistor sizing combination.
            'combo' will typically describe only a small group of transistors. Other transistors retain their current size."""
        
        # We start by making a dictionary of the transistor sizes we need to update
        new_sizes = {}
        for i in range(len(combo)):
            element_name = element_names[i]
            # If it's a pass-transistor, we just add the NMOS size
            if "ptran_" in element_name:
                new_sizes[element_name + "_nmos"] = combo[i]
            # If it's a level-restorer, we just add the PMOS size
            elif "rest_" in element_name:
                new_sizes[element_name + "_pmos"] = combo[i]
            # If it's a transmission gate, we just add the PMOS and NMOS sizes
            elif "tgate_" in element_name:
                new_sizes[element_name + "_pmos"] = combo[i]
                new_sizes[element_name + "_nmos"] = combo[i]
            # If it's an inverter, we have to add both NMOS and PMOS sizes
            elif "inv_" in element_name:
                if inv_ratios == None:
                    # If no inverter ratios are specified, NMOS and PMOS are equal size
                    new_sizes[element_name + "_nmos"] = combo[i]
                    new_sizes[element_name + "_pmos"] = combo[i]
                else:
                    # If there are inverter ratios, we use them to give different sizes to NMOS and PMOS
                    if inv_ratios[element_name] < 1:
                        # NMOS is larger than PMOS
                        if not use_finfet:
                            new_sizes[element_name + "_nmos"] = combo[i]/inv_ratios[element_name]
                        else :
                            new_sizes[element_name + "_nmos"] = round(combo[i]/inv_ratios[element_name])
                            # new_sizes[element_name + "_nmos"] = combo[i]
                        new_sizes[element_name + "_pmos"] = combo[i]
                    else:
                        # PMOS is larger than NMOS
                        new_sizes[element_name + "_nmos"] = combo[i]
                        if not use_finfet :
                            new_sizes[element_name + "_pmos"] = combo[i]*inv_ratios[element_name]
                        else :
                            new_sizes[element_name + "_pmos"] = round(combo[i]*inv_ratios[element_name])
                            # new_sizes[element_name + "_pmos"] = combo[i]

        # Now, update self.transistor_sizes with these new sizes
        self.transistor_sizes.update(new_sizes)


    def _area_model(self, tran_name: str, tran_size: int) -> float:
        """ 
            Transistor area model. 'tran_size' is the transistor drive strength in min. width transistor drive strengths. 
            Transistor area is calculated bsed on 'tran_size' and transistor type, which is determined by tags in 'tran_name'.
            Return valus is the transistor area in minimum width transistor areas. 
        """
    
        # If inverter or transmission gate, use larger area to account for N-well spacing
        # If pass-transistor, use regular area because they don't need N-wells.
        if "inv_" in tran_name or "tgate_" in tran_name:
            if not self.specs.use_finfet:
                # Bulk Model
                area = 0.518 + 0.127*tran_size + 0.428*math.sqrt(tran_size)
            # This is the finfet Tx model we used in ASAP7, not sure why it should be different than other finfet Tx models
            elif (self.specs.min_tran_width == 7): 
                # 7nm Finfet Model
                area = 0.3694 + 0.0978*tran_size + 0.5368*math.sqrt(tran_size)
            else:
                # Legacy FinFET model TODO figure out where this came from and attach comment
                area = 0.034 + 0.414*tran_size + 0.735*math.sqrt(tran_size)
        else:
            # Regular transistor, i.e. transistors which don't have P & N types adjacent to one another (I'm guessing)
            if not self.specs.use_finfet :
                # Bulk Model
                area = 0.447 + 0.128*tran_size + 0.391*math.sqrt(tran_size)
            elif (self.specs.min_tran_width == 7):
                # 7nm Finfet Model
                area = 0.3694 + 0.0978*tran_size + 0.5368*math.sqrt(tran_size)
            else:
                # Legacy FinFET model TODO figure out where this came from and attach comment
                area = -0.013 + 0.414*tran_size + 0.665*math.sqrt(tran_size)
    
        return area  

    def _update_area_per_transistor(self):
        """ 
            We use self.transistor_sizes to calculate area
            Using the area model, we calculate the transistor area in minimum width transistor areas.
            We also calculate area in nm and transistor width in nm. Nanometer values are needed for wire length calculations.
            For each transistor, this data forms a tuple (tran_name, tran_channel_width_nm, tran_drive_strength, tran_area_min_areas, tran_area_nm, tran_width_nm)
            The FPGAs transistor_area_list is updated once these values are computed.
        """

        # Initialize transistor area list
        tran_area_list = []
        
        # For each transistor, calculate area
        tran_name: str
        tran_size: int
        for tran_name, tran_size in self.transistor_sizes.items():
                # Get transistor drive strength (drive strength is = xMin width)
                tran_drive: int = tran_size
                # Get tran area in min transistor widths
                tran_area: float = self._area_model(tran_name, tran_drive)
                # Get area in nm square
                tran_area_nm: float = tran_area * self.specs.min_width_tran_area
                # Get width of transistor in nm
                tran_width: float = math.sqrt(tran_area_nm)
                # Add this as a tuple to the tran_area_list
                # TODO: tran_size and tran_drive are the same thing?!
                tran_area_list.append(
                    (
                        tran_name,
                        tran_size, 
                        tran_drive, 
                        tran_area, 
                        tran_area_nm, 
                        tran_width
                    )
                )    
                                                                                
        # Assign list to FPGA object
        self.transistor_area_list: List[ Tuple[str, int, int, float, float, float] ] = tran_area_list

    def _update_area_and_width_dicts(self):
        """ 
            Calculate area for basic subcircuits like inverters, pass transistor, 
            transmission gates, etc. Update area_dict and width_dict with this data.
        """
        # Important info:
        #   The keys which determine if a transistor will be put into the area / width dicts are:
        #   Gets single key for combo of pmos and nmos for transistors:
        #       - "inv_"        ->  With name "inv_XXX"
        #       - "tgate_"      ->  With name "tgate_XXX"
        #   Gets single key for single transistor
        #       - "ptran_"      ->  With name "ptran_XXX"
        #       - "rest_"       ->  With name "rest_XXX"
        #       - "tran_"       ->  With name "tran_XXX"


        
        # Initialize component area list of tuples (component name, component area, component width)
        comp_area_list: List[ Tuple[str, float, float] ] = []
        
        # Create a dictionary to store component sizes for multi-transistor components
        comp_dict: Dict[str, Dict[str, float] ] = {}
        
        # For each transistor in the transistor_area_list
        # tran is a tuple having the following formate: 
        # [0] tran_name
        # [1] tran_channel_width_nm
        # [2] tran_drive_strength
        # [3] tran_area_min_areas
        # [4] tran_area_nm
        # [5] tran_width_nm
        tran: Tuple[str, int, int, float, float, float]
        for tran in self.transistor_area_list:
            # those components should have an nmos and a pmos transistors in them
            if "inv_" in tran[0] or "tgate_" in tran[0]:
                # Get the component name; transistors full name example: inv_lut_out_buffer_2_nmos.
                # so the component name after the next two lines will be inv_lut_out_buffer_2.
                comp_name: str = tran[0].replace("_nmos", "")
                comp_name: str = comp_name.replace("_pmos", "")
                
                # If the component is already in the dictionary
                if comp_name in comp_dict:
                    if "_nmos" in tran[0]:
                        # tran[4] is tran_area_nm
                        comp_dict[comp_name]["nmos"] = tran[4]
                    else:
                        comp_dict[comp_name]["pmos"] = tran[4]
                        
                    # At this point we should have both NMOS and PMOS sizes in the dictionary
                    # We can calculate the area of the inverter or tgate by doing the sum
                    comp_area: float = comp_dict[comp_name]["nmos"] + comp_dict[comp_name]["pmos"]
                    comp_width: float = math.sqrt(comp_area)
                    comp_area_list.append((comp_name, comp_area, comp_width))                 
                else:
                    # Create a dict for this component to store nmos and pmos sizes
                    comp_area_dict: Dict[str, float] = {}
                    # Add either the nmos or pmos item
                    if "_nmos" in tran[0]:
                        comp_area_dict["nmos"] = tran[4]
                    else:
                        comp_area_dict["pmos"] = tran[4]
                        
                    # Add this inverter to the inverter dictionary    
                    comp_dict[comp_name] = comp_area_dict
            # those components only have one transistor in them
            elif "ptran_" in tran[0] or "rest_" in tran[0] or "tran_" in tran[0]:   
                # Get the comp name
                comp_name: str = tran[0].replace("_nmos", "")
                comp_name: str = comp_name.replace("_pmos", "")               
                # Add this to comp_area_list directly
                comp_area_list.append((comp_name, tran[4], tran[5]))            
        
        # Convert comp_area_list to area_dict and width_dict
        area_dict: Dict[str, float] = {}
        width_dict: Dict[str, float] = {}
        for component in comp_area_list:
            area_dict[component[0]] = component[1]
            width_dict[component[0]] = component[2]
        
        # Set the FPGA object area and width dict
        self.area_dict = area_dict
        self.width_dict = width_dict

        return


    




# rr_parse_args = [
#     '--rr_xml_fpath', rg_utils.clean_path(coffe_info.fpga_arch_conf["fpga_arch_params"]['rr_graph_fpath']),
#     '--out_dpath', rg_utils.clean_path(coffe_info.fpga_arch_conf["fpga_arch_params"]["arch_out_folder"]),
# ]
# rr_info: Dict[str, Dict[str, Dict[str, Any]]] = rrg_parse.main(rr_parse_args)

# ASSUMPTION - we have mappings from wire lengths
# From the rr info assert that we have the equivalent wire types to the segments returned
# Conversion from what is returned by rrg parser and data we need to create switch blocks
# gen_r_wires: List[GenRoutingWire] = []
# for wire in self.specs.wire_types:
#     for seg_id, segment in rr_info["segments"].items():
#         # Match wire lengths found in rr with those in wire_types
#         if wire["name"] == segment["name"]:
#             gen_r_wire = {}
#             gen_r_wire["id"] = seg_id
#             gen_r_wire["length"] = segment["length"]
#             gen_r_wire["layer"] = wire["layer"]
#             gen_r_wires.append(
#                 rg_utils.typecast_input_to_dataclass(gen_r_wire, GenRoutingWire)
#             )
#             # Break out after a match
#             break
# # Get switch info & fanouts 

# # Make sure there are no duplicate gen_r_wire ids in gen_r_wires
# assert len(gen_r_wires) == len(set([gen_r_wire["id"] for gen_r_wire in gen_r_wires])), "Duplicate gen_r_wire ids found in gen_r_wires"

    def update_ram_delays(self, parameter_dict: Dict[str, List[str]], spice_interface: spice.SpiceInterface) -> bool:
        # Local RAM MUX
        valid_delay = True
        print("  Updating delay for " + self.RAM.RAM_local_mux.name)
        spice_meas = spice_interface.run(self.RAM.RAM_local_mux.top_spice_path, 
                                         parameter_dict) 
        if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
            valid_delay = False
            tfall = 1
            trise = 1
        else :  
            tfall = float(spice_meas["meas_total_tfall"][0])
            trise = float(spice_meas["meas_total_trise"][0])
        if tfall < 0 or trise < 0 :
            valid_delay = False
        self.RAM.RAM_local_mux.tfall = tfall
        self.RAM.RAM_local_mux.trise = trise
        self.RAM.RAM_local_mux.delay = max(tfall, trise)
        self.delay_dict[self.RAM.RAM_local_mux.name] = self.RAM.RAM_local_mux.delay
        self.RAM.RAM_local_mux.power = float(spice_meas["meas_avg_power"][0])

        #RAM decoder units
        print("  Updating delay for " + self.RAM.rowdecoder_stage0.name)
        spice_meas = spice_interface.run(self.RAM.rowdecoder_stage0.top_spice_path, parameter_dict) 
        if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
            valid_delay = False
            tfall = 1
            trise = 1
        else :  
            tfall = float(spice_meas["meas_total_tfall"][0])
            trise = float(spice_meas["meas_total_trise"][0])
        if tfall < 0 or trise < 0 :
            valid_delay = False
        self.RAM.rowdecoder_stage0.tfall = tfall
        self.RAM.rowdecoder_stage0.trise = trise
        self.RAM.rowdecoder_stage0.delay = max(tfall, trise)
        #crit_path_delay += (self.RAM.rowdecoder_stage0.delay* self.RAM.delay_weight)
        self.delay_dict[self.RAM.rowdecoder_stage0.name] = self.RAM.rowdecoder_stage0.delay
        self.RAM.rowdecoder_stage0.power = float(spice_meas["meas_avg_power"][0])


        if self.RAM.valid_row_dec_size2 == 1:
            print("  Updating delay for " + self.RAM.rowdecoder_stage1_size2.name)
            spice_meas = spice_interface.run(self.RAM.rowdecoder_stage1_size2.top_spice_path, parameter_dict) 
            if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
                valid_delay = False
                tfall = 1
                trise = 1
            else :  
                tfall = float(spice_meas["meas_total_tfall"][0])
                trise = float(spice_meas["meas_total_trise"][0])
            if tfall < 0 or trise < 0 :
                valid_delay = False
            self.RAM.rowdecoder_stage1_size2.tfall = tfall
            self.RAM.rowdecoder_stage1_size2.trise = trise
            self.RAM.rowdecoder_stage1_size2.delay = max(tfall, trise)
            #crit_path_delay += (self.RAM.rowdecoder_stage1_size2.delay* self.RAM.delay_weight)
            self.delay_dict[self.RAM.rowdecoder_stage1_size2.name] = self.RAM.rowdecoder_stage1_size2.delay
            self.RAM.rowdecoder_stage1_size2.power = float(spice_meas["meas_avg_power"][0])

        if self.RAM.valid_row_dec_size3 == 1:
            print("  Updating delay for " + self.RAM.rowdecoder_stage1_size3.name)
            spice_meas = spice_interface.run(self.RAM.rowdecoder_stage1_size3.top_spice_path, parameter_dict) 
            if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
                valid_delay = False
                tfall = 1
                trise = 1
            else :  
                tfall = float(spice_meas["meas_total_tfall"][0])
                trise = float(spice_meas["meas_total_trise"][0])
            if tfall < 0 or trise < 0 :
                valid_delay = False
            self.RAM.rowdecoder_stage1_size3.tfall = tfall
            self.RAM.rowdecoder_stage1_size3.trise = trise
            self.RAM.rowdecoder_stage1_size3.delay = max(tfall, trise)
            #crit_path_delay += (self.RAM.rowdecoder_stage1_size3.delay* self.RAM.delay_weight)
            self.delay_dict[self.RAM.rowdecoder_stage1_size3.name] = self.RAM.rowdecoder_stage1_size3.delay
            self.RAM.rowdecoder_stage1_size3.power = float(spice_meas["meas_avg_power"][0])


        print("  Updating delay for " + self.RAM.rowdecoder_stage3.name)
        spice_meas = spice_interface.run(self.RAM.rowdecoder_stage3.top_spice_path, parameter_dict) 
        if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
            valid_delay = False
            tfall = 1
            trise = 1
        else :  
            tfall = float(spice_meas["meas_total_tfall"][0])
            trise = float(spice_meas["meas_total_trise"][0])
        if tfall < 0 or trise < 0 :
            valid_delay = False
        self.RAM.rowdecoder_stage3.tfall = tfall
        self.RAM.rowdecoder_stage3.trise = trise
        self.RAM.rowdecoder_stage3.delay = max(tfall, trise)
        self.delay_dict[self.RAM.rowdecoder_stage3.name] = self.RAM.rowdecoder_stage3.delay
        self.RAM.rowdecoder_stage3.power = float(spice_meas["meas_avg_power"][0])


        if self.RAM.memory_technology == "SRAM":
            print("  Updating delay for " + self.RAM.precharge.name)
            spice_meas = spice_interface.run(self.RAM.precharge.top_spice_path, parameter_dict) 
            if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
                valid_delay = False
                tfall = 1
                trise = 1
            else :  
                tfall = float(spice_meas["meas_total_tfall"][0])
                trise = float(spice_meas["meas_total_trise"][0])
            if tfall < 0 or trise < 0 :
                valid_delay = False
            self.RAM.precharge.tfall = tfall
            self.RAM.precharge.trise = trise
            self.RAM.precharge.delay = max(tfall, trise)
            #crit_path_delay += (self.RAM.precharge.delay* self.RAM.delay_weight)
            self.delay_dict[self.RAM.precharge.name] = self.RAM.precharge.delay
            self.RAM.precharge.power = float(spice_meas["meas_avg_power"][0])

            print("  Updating delay for " + self.RAM.samp_part2.name)
            spice_meas = spice_interface.run(self.RAM.samp_part2.top_spice_path, parameter_dict) 
            if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
                valid_delay = False
                tfall = 1
                trise = 1
            else :  
                tfall = float(spice_meas["meas_total_tfall"][0])
                trise = float(spice_meas["meas_total_trise"][0])
            if tfall < 0 or trise < 0 :
                valid_delay = False
            self.RAM.samp_part2.tfall = tfall
            self.RAM.samp_part2.trise = trise 
            self.RAM.samp_part2.delay = max(tfall, trise)

            self.delay_dict[self.RAM.samp_part2.name] = self.RAM.samp_part2.delay
            self.RAM.samp_part2.power = float(spice_meas["meas_avg_power"][0])

            print("  Updating delay for " + self.RAM.samp.name)
            spice_meas = spice_interface.run(self.RAM.samp.top_spice_path, parameter_dict) 
            if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
                valid_delay = False
                tfall = 1
                trise = 1
            else :  
                tfall = float(spice_meas["meas_total_tfall"][0])
                trise = float(spice_meas["meas_total_trise"][0])

            if tfall < 0 or trise < 0 :
                valid_delay = False
            self.RAM.samp.tfall = tfall + self.RAM.samp_part2.tfall
            self.RAM.samp.trise = trise + self.RAM.samp_part2.trise

            self.RAM.samp.delay = max(tfall, trise)
            #crit_path_delay += (self.RAM.samp.delay* self.RAM.delay_weight)
            self.delay_dict[self.RAM.samp.name] = self.RAM.samp.delay
            self.RAM.samp.power = float(spice_meas["meas_avg_power"][0])

            print("  Updating delay for " + self.RAM.writedriver.name)
            spice_meas = spice_interface.run(self.RAM.writedriver.top_spice_path, parameter_dict) 
            if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
                valid_delay = False
                tfall = 1
                trise = 1
            else :  
                tfall = float(spice_meas["meas_total_tfall"][0])
                trise = float(spice_meas["meas_total_trise"][0])
            if tfall < 0 or trise < 0 :
                valid_delay = False
            self.RAM.writedriver.tfall = tfall
            self.RAM.writedriver.trise = trise
            self.RAM.writedriver.delay = max(tfall, trise)
            #crit_path_delay += (self.RAM.writedriver.delay* self.RAM.delay_weight)
            self.delay_dict[self.RAM.writedriver.name] = self.RAM.writedriver.delay
            self.RAM.writedriver.power = float(spice_meas["meas_avg_power"][0])

        else:
            print("  Updating delay for " + self.RAM.bldischarging.name)
            spice_meas = spice_interface.run(self.RAM.bldischarging.top_spice_path, parameter_dict) 
            if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
                valid_delay = False
                tfall = 1
                trise = 1
            else :  
                tfall = float(spice_meas["meas_total_tfall"][0])
                trise = float(spice_meas["meas_total_trise"][0])
            if tfall < 0 or trise < 0 :
                valid_delay = False
            self.RAM.bldischarging.tfall = tfall
            self.RAM.bldischarging.trise = trise
            self.RAM.bldischarging.delay = max(tfall, trise)
            #crit_path_delay += (self.RAM.bldischarging.delay* self.RAM.delay_weight)
            self.delay_dict[self.RAM.bldischarging.name] = self.RAM.bldischarging.delay
            self.RAM.bldischarging.power = float(spice_meas["meas_avg_power"][0])

            print("  Updating delay for " + self.RAM.blcharging.name)
            spice_meas = spice_interface.run(self.RAM.blcharging.top_spice_path, parameter_dict) 
            if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
                valid_delay = False
                tfall = 1
                trise = 1
            else :  
                tfall = float(spice_meas["meas_total_tfall"][0])
                trise = float(spice_meas["meas_total_trise"][0])
            if tfall < 0 or trise < 0 :
                valid_delay = False
            self.RAM.blcharging.tfall = tfall
            self.RAM.blcharging.trise = trise
            self.RAM.blcharging.delay = max(tfall, trise)
            #crit_path_delay += (self.RAM.blcharging.delay* self.RAM.delay_weight)
            self.delay_dict[self.RAM.blcharging.name] = self.RAM.blcharging.delay
            self.RAM.blcharging.power = float(spice_meas["meas_avg_power"][0])

            self.RAM.target_bl = 0.99* float(spice_meas["meas_outputtarget"][0])

            self.RAM._update_process_data()

            print("  Updating delay for " + self.RAM.blcharging.name)
            spice_meas = spice_interface.run(self.RAM.blcharging.top_spice_path, parameter_dict) 
            if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
                valid_delay = False
                tfall = 1
                trise = 1
            else :  
                tfall = float(spice_meas["meas_total_tfall"][0])
                trise = float(spice_meas["meas_total_trise"][0])
            if tfall < 0 or trise < 0 :
                valid_delay = False
            self.RAM.blcharging.tfall = tfall
            self.RAM.blcharging.trise = trise
            self.RAM.blcharging.delay = max(tfall, trise)
            #crit_path_delay += (self.RAM.blcharging.delay* self.RAM.delay_weight)
            self.delay_dict[self.RAM.blcharging.name] = self.RAM.blcharging.delay
            self.RAM.blcharging.power = float(spice_meas["meas_avg_power"][0])
            self.RAM.target_bl = 0.99*float(spice_meas["meas_outputtarget"][0])

            self.RAM._update_process_data()

            print("  Updating delay for " + self.RAM.mtjsamp.name)
            spice_meas = spice_interface.run(self.RAM.mtjsamp.top_spice_path, parameter_dict) 
            if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
                valid_delay = False
                tfall = 1
                trise = 1
            else :  
                tfall = float(spice_meas["meas_total_tfall"][0])
                trise = float(spice_meas["meas_total_trise"][0])
            if tfall < 0 or trise < 0 :
                valid_delay = False
            self.RAM.mtjsamp.tfall = tfall
            self.RAM.mtjsamp.delay = tfall
            self.RAM.mtjsamp.trise = max(tfall, trise)
            #crit_path_delay += (self.RAM.mtjsamp.delay* self.RAM.delay_weight)
            self.delay_dict[self.RAM.mtjsamp.name] = self.RAM.mtjsamp.delay
            self.RAM.mtjsamp.power = float(spice_meas["meas_avg_power"][0])

    
        print("  Updating delay for " + self.RAM.columndecoder.name)
        spice_meas = spice_interface.run(self.RAM.columndecoder.top_spice_path, parameter_dict) 
        if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
            valid_delay = False
            tfall = 1
            trise = 1
        else :  
            tfall = float(spice_meas["meas_total_tfall"][0])
            trise = float(spice_meas["meas_total_trise"][0])
        if tfall < 0 or trise < 0 :
            valid_delay = False
        self.RAM.columndecoder.tfall = tfall
        self.RAM.columndecoder.trise = trise
        self.RAM.columndecoder.delay = max(tfall, trise)
        #crit_path_delay += (self.RAM.columndecoder.delay* self.RAM.delay_weight)
        self.delay_dict[self.RAM.columndecoder.name] = self.RAM.columndecoder.delay
        self.RAM.columndecoder.power = float(spice_meas["meas_avg_power"][0])


        print("  Updating delay for " + self.RAM.configurabledecoderi.name)
        spice_meas = spice_interface.run(self.RAM.configurabledecoderi.top_spice_path, parameter_dict) 
        if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
            valid_delay = False
            tfall = 1
            trise = 1
        else :  
            tfall = float(spice_meas["meas_total_tfall"][0])
            trise = float(spice_meas["meas_total_trise"][0])
        if tfall < 0 or trise < 0 :
            valid_delay = False
        self.RAM.configurabledecoderi.tfall = tfall
        self.RAM.configurabledecoderi.trise = trise
        self.RAM.configurabledecoderi.delay = max(tfall, trise)
        #crit_path_delay += (self.RAM.configurabledecoderi.delay* self.RAM.delay_weight)
        self.delay_dict[self.RAM.configurabledecoderi.name] = self.RAM.configurabledecoderi.delay
        self.RAM.configurabledecoderi.power = float(spice_meas["meas_avg_power"][0])


        if self.RAM.cvalidobj1 ==1:
            print("  Updating delay for " + self.RAM.configurabledecoder3ii.name)
            spice_meas = spice_interface.run(self.RAM.configurabledecoder3ii.top_spice_path, parameter_dict) 
            if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
                valid_delay = False
                tfall = 1
                trise = 1
            else :  
                tfall = float(spice_meas["meas_total_tfall"][0])
                trise = float(spice_meas["meas_total_trise"][0])
            if tfall < 0 or trise < 0 :
                valid_delay = False
            self.RAM.configurabledecoder3ii.tfall = tfall
            self.RAM.configurabledecoder3ii.trise = trise
            self.RAM.configurabledecoder3ii.delay = max(tfall, trise)
            #crit_path_delay += (self.RAM.configurabledecoder3ii.delay* self.RAM.delay_weight)
            self.delay_dict[self.RAM.configurabledecoder3ii.name] = self.RAM.configurabledecoder3ii.delay
            self.RAM.configurabledecoder3ii.power = float(spice_meas["meas_avg_power"][0])


        if self.RAM.cvalidobj2 ==1:
            print("  Updating delay for " + self.RAM.configurabledecoder2ii.name)
            spice_meas = spice_interface.run(self.RAM.configurabledecoder2ii.top_spice_path, parameter_dict) 
            if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
                valid_delay = False
                tfall = 1
                trise = 1
            else :  
                tfall = float(spice_meas["meas_total_tfall"][0])
                trise = float(spice_meas["meas_total_trise"][0])
            if tfall < 0 or trise < 0 :
                valid_delay = False
            self.RAM.configurabledecoder2ii.tfall = tfall
            self.RAM.configurabledecoder2ii.trise = trise
            self.RAM.configurabledecoder2ii.delay = max(tfall, trise)
            #crit_path_delay += (self.RAM.configurabledecoder2ii.delay* self.RAM.delay_weight)
            self.delay_dict[self.RAM.configurabledecoder2ii.name] = self.RAM.configurabledecoder2ii.delay
            self.RAM.configurabledecoder2ii.power = float(spice_meas["meas_avg_power"][0])

        print("  Updating delay for " + self.RAM.configurabledecoderiii.name)
        spice_meas = spice_interface.run(self.RAM.configurabledecoderiii.top_spice_path, parameter_dict) 
        if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
            valid_delay = False
            tfall = 1
            trise = 1
        else :  
            tfall = float(spice_meas["meas_total_tfall"][0])
            trise = float(spice_meas["meas_total_trise"][0])
        if tfall < 0 or trise < 0 :
            valid_delay = False
        self.RAM.configurabledecoderiii.tfall = tfall
        self.RAM.configurabledecoderiii.trise = trise
        self.RAM.configurabledecoderiii.delay = max(tfall, trise)
        #crit_path_delay += (self.RAM.configurabledecoderiii.delay* self.RAM.delay_weight)
        self.delay_dict[self.RAM.configurabledecoderiii.name] = self.RAM.configurabledecoderiii.delay
        self.RAM.configurabledecoderiii.power = float(spice_meas["meas_avg_power"][0])
  

        print("  Updating delay for " + self.RAM.pgateoutputcrossbar.name)
        spice_meas = spice_interface.run(self.RAM.pgateoutputcrossbar.top_spice_path, parameter_dict) 
        if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
            valid_delay = False
            tfall = 1
            trise = 1
        else :  
            tfall = float(spice_meas["meas_total_tfall"][0])
            trise = float(spice_meas["meas_total_trise"][0])
        if tfall < 0 or trise < 0 :
            valid_delay = False
        self.RAM.pgateoutputcrossbar.tfall = tfall
        self.RAM.pgateoutputcrossbar.trise = trise
        self.RAM.pgateoutputcrossbar.delay = max(tfall, trise)
        #crit_path_delay += (self.RAM.pgateoutputcrossbar.delay* self.RAM.delay_weight)
        self.delay_dict[self.RAM.pgateoutputcrossbar.name] = self.RAM.pgateoutputcrossbar.delay
        self.RAM.pgateoutputcrossbar.power = float(spice_meas["meas_avg_power"][0])
        # sets the our representative critical path
        # self.delay_dict["rep_crit_path"] = crit_path_delay 

        print("  Updating delay for " + self.RAM.wordlinedriver.name)
        spice_meas = spice_interface.run(self.RAM.wordlinedriver.top_spice_path, parameter_dict) 
        if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
            valid_delay = False
            tfall = 1
            trise = 1
        else :  
            tfall = float(spice_meas["meas_total_tfall"][0])
            trise = float(spice_meas["meas_total_trise"][0])
        if tfall < 0 or trise < 0 :
            valid_delay = False
        self.RAM.wordlinedriver.tfall = tfall
        self.RAM.wordlinedriver.trise = trise
        self.RAM.wordlinedriver.delay = max(tfall, trise)
        #crit_path_delay += (self.RAM.wordlinedriver.delay* self.RAM.delay_weight)
        self.delay_dict[self.RAM.wordlinedriver.name] = self.RAM.wordlinedriver.delay
        self.RAM.wordlinedriver.power = float(spice_meas["meas_avg_power"][0])
        if self.RAM.wordlinedriver.wl_repeater == 1:
            self.RAM.wordlinedriver.power *=2

        return valid_delay


    def update_power(self, spice_interface: spice.SpiceInterface):
        """This funciton measures RAM core power once sizing has finished.
        It also sums up power consumed by the peripheral circuitry and converts it to energy per bit"""
        # Several timing parameters need to be updated before power can be measured accurately
        # The following will compute and store the current values for these delays
        # Create parameter dict of all current transistor sizes and wire rc

        parameter_dict = {}
        for tran_name, tran_size in self.transistor_sizes.items():
            if not self.specs.use_finfet:
                parameter_dict[tran_name] = [1e-9*tran_size*self.specs.min_tran_width]
            else :
                parameter_dict[tran_name] = [tran_size]

        for wire_name, rc_data in self.wire_rc_dict.items():
            parameter_dict[wire_name + "_res"] = [rc_data[0]]
            parameter_dict[wire_name + "_cap"] = [rc_data[1]*1e-15]

        # Update the file
        ram_decoder_stage1_delay = 0
        if self.RAM.valid_row_dec_size2 == 1:
            ram_decoder_stage1_delay = max(ram_decoder_stage1_delay, self.RAM.rowdecoder_stage1_size2.delay)
        if self.RAM.valid_row_dec_size3 == 1:
            ram_decoder_stage1_delay = max(self.RAM.rowdecoder_stage1_size3.delay, ram_decoder_stage1_delay)
        self.RAM.estimated_rowdecoder_delay = ram_decoder_stage1_delay    
        self.RAM.estimated_rowdecoder_delay += self.RAM.rowdecoder_stage3.delay
        ram_decoder_stage0_delay = self.RAM.rowdecoder_stage0.delay
        self.RAM.estimated_rowdecoder_delay += ram_decoder_stage0_delay

        # Measure the configurable decoder delay:
        configurable_decoder_delay = 0.0
        if self.RAM.cvalidobj1 == 1:
            configurable_decoder_delay = max(self.RAM.configurabledecoder3ii.delay, configurable_decoder_delay)
        if self.RAM.cvalidobj2 == 1:
            configurable_decoder_delay = max(self.RAM.configurabledecoder2ii.delay, configurable_decoder_delay)
        configurable_decoder_delay += self.RAM.configurabledecoderi.delay
        # This is the driving part of the configurable decoder.
        configurable_decoder_drive = self.RAM.configurabledecoderiii.delay

        # ###############################################
        # Overall frequency calculation of the RAM
        # ###############################################
        # Ref [1]: "High Density, Low Energy, Magnetic Tunnel Junction Based Block RAMs for Memory-rich FPGAs",
        # Tatsumara et al, FPT'16
        # Ref [2]: "Don't Forget the Memory: Automatic Block RAM Modelling, Optimization, and Architecture Exploration",
        # Yazdanshenas et al, FPGA'17
        # 
        # -----------------------------------------------
        # For SRAM
        # -----------------------------------------------
        # From [1]:
        # Delay of the RAM read path is a sum of 3 delays:
        # Tread = T1 + T2 + T3
        # = max (row decoder, pre-charge time) + (wordline driver + bit line delay) + (sense amp + output crossbar)
        # For an output registered SRAM (assumed here), the cycle time of the RAM is limited by:
        # Tread' = Tread + Tmicro_reg_setup
        # The write path delay (Twrite) is always faster than Tread so it doesn't affect the cycle time.
        #
        # The formulae below use a slightly different terminology/notation:
        # 1. They include configurable decoder related delays as well, which are required because RAM blocks on FPGAs
        #    have configurable decoders for providing configurable depths and widths.
        # 2. Instead of breaking down the delay into 3 components,the delay is broken down into 2 components (T1 and T2).
        # 3. Bit line delay (a part of T2 from the paper) is self.RAM.samp.delay in the code below.
        # 4. Sense amp delay (a part of T3 from the paper) is self.RAM.samp_part2.delay in the code below.
        # 5. The Tmicro_reg_setup value is hardcoded as 2e-11

        if self.RAM.memory_technology == "SRAM":
            self.RAM.T1 = max(self.RAM.estimated_rowdecoder_delay, configurable_decoder_delay, self.RAM.precharge.delay)
            self.RAM.T2 = self.RAM.wordlinedriver.delay + self.RAM.samp.delay + self.RAM.samp_part2.delay  
            self.RAM.frequency = max(self.RAM.T1 + self.RAM.T2 , configurable_decoder_delay + configurable_decoder_drive)
            self.RAM.frequency += self.RAM.pgateoutputcrossbar.delay + 2e-11

        # -----------------------------------------------
        # For MTJ
        # -----------------------------------------------
        # From [1]:
        # The write operation consists of precharge (T1) and cell-write (T2) phases. 
        # T1 is the maximum of BL-discharging time and the row decoder delay. 
        # T2 is the sum of word line delay and the MTJ cell writing time. 
        # Twrite = T1 + T2.
        #
        # The read operation consists of precharge (T1), stabilize (T3), sense (T4) and latch (T5) phases. 
        # T1 is the same as the write operation.
        # T3 is the sum of wordline delay and the BL-charging time.
        # T4 is the sense amp delay.
        # T5 is the sum of crossbar delay and Tmicro_reg_setup.
        # Tread = T1 + T3 + T4 + T5
        #
        # Overall frequency = max(Tread, Twrite)
        # 
        # The formulae below use a different terminology/notation:
        # 1. They include confgurable decoder related delays as well, which are required because RAM blocks on FPGAs
        #    have configurable decoders for providing configurable depths and widths.
        # 2. There is no separation of Tread and Twrite and the T1/T2/etc components are not the same.
        # 3. The Tmicro_reg_setup value is hardcoded as 3e-9

        elif self.RAM.memory_technology == "MTJ":

            self.RAM.T1 = max(self.RAM.estimated_rowdecoder_delay, configurable_decoder_delay, self.RAM.bldischarging.delay)
            self.RAM.T2 = self.RAM.T1 +  max(self.RAM.wordlinedriver.delay , configurable_decoder_drive) + self.RAM.blcharging.delay
            self.RAM.T3 = self.RAM.T2 + self.RAM.mtjsamp.delay
            self.RAM.frequency = self.RAM.T2 - self.RAM.blcharging.delay + 3e-9

        self.RAM._update_process_data()

        if self.RAM.memory_technology == "SRAM":
            print("Measuring SRAM power " + self.RAM.power_sram_read.name)
            spice_meas = spice_interface.run(self.RAM.power_sram_read.top_spice_path, parameter_dict) 
            self.RAM.power_sram_read.power_selected = float(spice_meas["meas_avg_power_selected"][0])
            self.RAM.power_sram_read.power_unselected = float(spice_meas["meas_avg_power_unselected"][0])

            spice_meas = spice_interface.run(self.RAM.power_sram_writelh.top_spice_path, parameter_dict) 
            self.RAM.power_sram_writelh.power_selected_writelh = float(spice_meas["meas_avg_power_selected"][0])

            spice_meas = spice_interface.run(self.RAM.power_sram_writehh.top_spice_path, parameter_dict) 
            self.RAM.power_sram_writehh.power_selected_writehh = float(spice_meas["meas_avg_power_selected"][0])

            spice_meas = spice_interface.run(self.RAM.power_sram_writep.top_spice_path, parameter_dict) 
            self.RAM.power_sram_writep.power_selected_writep = float(spice_meas["meas_avg_power_selected"][0])

            # can be used to help with debugging:
            #print "T1: " +str(self.RAM.T1)
            #print "T2: " + str(self.RAM.T2)
            #print "freq " + str(self.RAM.frequency)
            #print "selected " + str(self.RAM.power_sram_read.power_selected)
            #print "unselected " + str(self.RAM.power_sram_read.power_unselected)

            #print "selected_writelh " + str(self.RAM.power_sram_writelh.power_selected_writelh)
            #print "selected_writehh " + str(self.RAM.power_sram_writehh.power_selected_writehh)
            #print "selected_writep " + str(self.RAM.power_sram_writep.power_selected_writep)

            #print "power per bit read SRAM: " + str(self.RAM.power_sram_read.power_selected + self.RAM.power_sram_read.power_unselected)
            #print "Energy " + str((self.RAM.power_sram_read.power_selected + self.RAM.power_sram_read.power_unselected) * self.RAM.frequency)
            #print "Energy Writelh " + str(self.RAM.power_sram_writelh.power_selected_writelh * self.RAM.frequency)
            #print "Energy Writehh " + str(self.RAM.power_sram_writehh.power_selected_writehh * self.RAM.frequency)
            print("Energy Writep " + str(self.RAM.power_sram_writep.power_selected_writep * self.RAM.frequency))

            read_energy = (self.RAM.power_sram_read.power_selected + self.RAM.power_sram_read.power_unselected) * self.RAM.frequency
            write_energy = ((self.RAM.power_sram_writelh.power_selected_writelh + self.RAM.power_sram_writehh.power_selected_writehh)/2 + self.RAM.power_sram_read.power_unselected) * self.RAM.frequency

            self.RAM.core_energy = (self.RAM.read_to_write_ratio * read_energy + write_energy) /(1 + self.RAM.read_to_write_ratio)

        else:
            print("Measuring MTJ power ")
            spice_meas = spice_interface.run(self.RAM.power_mtj_write.top_spice_path, parameter_dict) 
            self.RAM.power_mtj_write.powerpl = float(spice_meas["meas_avg_power_selected"][0])
            self.RAM.power_mtj_write.powernl = float(spice_meas["meas_avg_power_selectedn"][0])
            self.RAM.power_mtj_write.powerph = float(spice_meas["meas_avg_power_selectedh"][0])
            self.RAM.power_mtj_write.powernh = float(spice_meas["meas_avg_power_selectedhn"][0])

            # can be used to help with debugging:
            #print "Energy Negative Low " + str(self.RAM.power_mtj_write.powernl * self.RAM.frequency)
            #print "Energy Positive Low " + str(self.RAM.power_mtj_write.powerpl * self.RAM.frequency)
            #print "Energy Negative High " + str(self.RAM.power_mtj_write.powernh * self.RAM.frequency)
            #print "Energy Positive High " + str(self.RAM.power_mtj_write.powerph * self.RAM.frequency)
            #print "Energy " + str(((self.RAM.power_mtj_write.powerph - self.RAM.power_mtj_write.powernh + self.RAM.power_mtj_write.powerpl - self.RAM.power_mtj_write.powernl) * self.RAM.frequency)/4)

            spice_meas = spice_interface.run(self.RAM.power_mtj_read.top_spice_path, parameter_dict) 
            self.RAM.power_mtj_read.powerl = float(spice_meas["meas_avg_power_readl"][0])
            self.RAM.power_mtj_read.powerh = float(spice_meas["meas_avg_power_readh"][0])

            # can be used to help with debugging:
            #print "Energy Low Read " + str(self.RAM.power_mtj_read.powerl * self.RAM.frequency)
            #print "Energy High Read " + str(self.RAM.power_mtj_read.powerh * self.RAM.frequency)
            #print "Energy Read " + str(((self.RAM.power_mtj_read.powerl + self.RAM.power_mtj_read.powerh) * self.RAM.frequency))

            read_energy = ((self.RAM.power_mtj_read.powerl + self.RAM.power_mtj_read.powerh) * self.RAM.frequency)
            write_energy = ((self.RAM.power_mtj_write.powerph - self.RAM.power_mtj_write.powernh + self.RAM.power_mtj_write.powerpl - self.RAM.power_mtj_write.powernl) * self.RAM.frequency)/4
            self.RAM.core_energy = (self.RAM.read_to_write_ratio * read_energy + write_energy) /(1 + self.RAM.read_to_write_ratio)


        # Peripherals are not technology-specific
        # Different components powers are multiplied by the number of active components for each toggle:
        peripheral_energy = self.RAM.row_decoder_bits / 2 * self.RAM.rowdecoder_stage0.power * self.RAM.number_of_banks
        if self.RAM.valid_row_dec_size2 == 1 and self.RAM.valid_row_dec_size3 == 1:
            peripheral_energy += (self.RAM.rowdecoder_stage1_size3.power + self.RAM.rowdecoder_stage1_size2.power)/2
        elif self.RAM.valid_row_dec_size3 == 1:
            peripheral_energy += self.RAM.rowdecoder_stage1_size3.power
        else:
            peripheral_energy += self.RAM.rowdecoder_stage1_size2.power

        peripheral_energy += self.RAM.wordlinedriver.power + self.RAM.columndecoder.power

        peripheral_energy += self.RAM.configurabledecoderi.power * self.RAM.conf_decoder_bits / 2 * self.RAM.number_of_banks
        peripheral_energy += self.RAM.configurabledecoderiii.power * (1 + 2**self.RAM.conf_decoder_bits)/2

        # Convert to energy
        peripheral_energy = peripheral_energy * self.RAM.frequency

        # Add read-specific components
        self.RAM.peripheral_energy_read = peripheral_energy + self.RAM.pgateoutputcrossbar.power * (1 + 2**self.RAM.conf_decoder_bits)/2 * self.RAM.frequency
        # We need energy PER BIT. Hence:
        self.RAM.peripheral_energy_read /= 2** self.RAM.conf_decoder_bits
        # Add write-specific components (input FF to WD)
        self.RAM.peripheral_energy_write = peripheral_energy + (2** self.RAM.conf_decoder_bits * self.RAM.configurabledecoderiii.power /2) * self.RAM.frequency
        # Add write-specific components (Write enable wires)
        self.RAM.peripheral_energy_write += ((1 + 2** self.RAM.conf_decoder_bits) * self.RAM.configurabledecoderiii.power) * self.RAM.frequency
        # We want energy per bit per OP:
        self.RAM.peripheral_energy_write /= 2** self.RAM.conf_decoder_bits

        print("Core read and write energy: " +str(read_energy) + " and " +str(write_energy))
        print("Core energy per bit: " + str(self.RAM.core_energy))
        print("Peripheral energy per bit: " + str((self.RAM.peripheral_energy_read * self.RAM.read_to_write_ratio + self.RAM.peripheral_energy_write)/ (1 + self.RAM.read_to_write_ratio)))