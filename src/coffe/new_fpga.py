from __future__ import annotations
from dataclasses import dataclass, field, InitVar

import os
import sys
import math
import logging
import random

from typing import List, Dict, Any, Tuple, Union, Type, NamedTuple, Set
from collections import defaultdict
import csv
import traceback

# Subcircuit Modules
import src.coffe.basic_subcircuits as basic_subcircuits
import src.coffe.mux_subcircuits as mux_subcircuits
import src.coffe.lut_subcircuits as lut_subcircuits
import src.coffe.ff_subcircuits as ff_subcircuits
import src.coffe.load_subcircuits as load_subcircuits
import src.coffe.memory_subcircuits as memory_subcircuits
import src.coffe.utils as utils
import src.coffe.cost as cost

from src.coffe.circuit_baseclasses import _SizableCircuit, _CompoundCircuit

# Top level file generation module
import src.coffe.top_level as top_level

# HSPICE handling module
import src.coffe.spice as spice

# Rad Gen data structures
import src.common.data_structs as rg_ds
import src.common.utils as rg_utils

import src.common.spice_parser as sp_parser

from collections import OrderedDict

# ASIC DSE imports
import src.asic_dse.asic_dse as asic_dse

# Importing individual constructors for subckt classes
# from src.coffe.sb_mux import _SwitchBlockMUX
# from src.coffe.cb_mux import _ConnectionBlockMUX 
# from src.coffe.logic_block import _LogicCluster
# from src.coffe.gen_routing_loads import _GeneralBLEOutputLoad, _RoutingWireLoad
# from src.coffe.carry_chain import _CarryChain, _CarryChainMux, _CarryChainInterCluster, _CarryChainPer, _CarryChainSkipMux, _CarryChainSkipAnd

import src.coffe.data_structs as c_ds
import src.coffe.new_sb_mux as sb_mux_lib
import src.coffe.new_cb_mux as cb_mux_lib
import src.coffe.new_gen_routing_loads as gen_r_load_lib
# from src.coffe.new_sb_mux import SwitchBlockMuxModel, SwitchBlockMux, SwitchBlockModel

import src.common.rr_parse as rrg_parse

# Track-access locality constants
OUTPUT_TRACK_ACCESS_SPAN = 0.25
INPUT_TRACK_ACCESS_SPAN = 0.50

# Delay weight constants:
DELAY_WEIGHT_SB_MUX = 0.4107
DELAY_WEIGHT_CB_MUX = 0.0989
DELAY_WEIGHT_LOCAL_MUX = 0.0736
DELAY_WEIGHT_LUT_A = 0.0396
DELAY_WEIGHT_LUT_B = 0.0379
DELAY_WEIGHT_LUT_C = 0.0704 # This one is higher because we had register-feedback coming into this mux.
DELAY_WEIGHT_LUT_D = 0.0202
DELAY_WEIGHT_LUT_E = 0.0121
DELAY_WEIGHT_LUT_F = 0.0186
DELAY_WEIGHT_LUT_FRAC = 0.0186
DELAY_WEIGHT_LOCAL_BLE_OUTPUT = 0.0267
DELAY_WEIGHT_GENERAL_BLE_OUTPUT = 0.0326
# The res of the ~15% came from memory, DSP, IO and FF based on my delay profiling experiments.
DELAY_WEIGHT_RAM = 0.15
HEIGHT_SPAN = 0.5

# Metal Layer definitions
LOCAL_WIRE_LAYER = 0

# Global Constants
CHAN_USAGE_ASSUMPTION = 0.5
CLUSTER_INPUT_USAGE_ASSUMPTION = 0.5
LUT_INPUT_USAGE_ASSUMPTION = 0.85

# This parameter determines if RAM core uses the low power transistor technology
# It is strongly suggested to keep it this way since our
# core RAM modules were designed to operate with low power transistors.
# Therefore, changing it might require other code changes.
# I have included placeholder functions in case someone really insists to remove it
# The easier alternative to removing it is to just provide two types of transistors which are actually the same
# In that case the user doesn't need to commit any code changes.
use_lp_transistor = 1





# General Notes:
# - It would be a good idea to have some assertion that when we write out a spice file using a particular parameter for wires / tx_sizes,
#     we return exhaustive list of all unique parameters written out from the generate function.
#     When doing things to all tx_params / wire params in the component
#     assert:
#     - An action performed for each param in exhaustive list -> set( [param for param in all_params] ) == set( [param for param in action_params] )



# RRG data structures are taken from csvs generated via the rr_parse script
# @dataclass
# class SegmentRRG():
#     """ 
#         This class describes a segment in the routing resource graph (RRG). 
#     """
#     # Required fields
#     name: str            # Name of the segment
#     id: int               
#     length: int          # Length of the segment in number of tiles
#     C_per_meter: float  # Capacitance per meter of the segment (FROM VTR)
#     R_per_meter: float  # Resistance per meter of the segment (FROM VTR)

# @dataclass
# class SwitchRRG():
#     name: str
#     id: int
#     type: str
#     R: float        = None 
#     Cin: float      = None 
#     Cout: float     = None 
#     Tdel: float     = None 


# @dataclass
# class MuxLoadRRG():
#     mux_type: str   # What mux are we referring to?
#     freq: int       # How many of these muxes are attached?

# @dataclass
# class MuxIPIN():
#     wire_type: str      # What is the wire type going into this mux IPIN?
#     drv_type: str       # What is the driver type of the wire going into this mux IPIN?
#     freq: int          # How many of these muxes are attached?

# @dataclass
# class MuxWireStatRRG():
#     wire_type: str            # What wire are we referring to?
#     drv_type: str             # What mux is driving this wire?
#     mux_ipins: List[MuxIPIN]  # What are the mux types / frequency attached to this wire?
#     mux_loads: List[MuxLoadRRG]   # What are mux types / frequency attached to this wire?
#     total_mux_inputs: int         = None  # How many mux inputs for mux driving this wire?
#     total_wire_loads: int         = None       # How many wires are loading this mux in total of all types?
#     def __post_init__(self):
#         self.total_mux_inputs = sum([mux_ipin.freq for mux_ipin in self.mux_ipins])
#         self.total_wire_loads = sum([mux_load.freq for mux_load in self.mux_loads])
#     #     # Make suer that all the MuxIPINs in list add up to our total mux inputs
#     #     assert sum([mux_ipin.freq for mux_ipin in self.mux_ipins]) == self.total_mux_inputs, "Mux IPIN frequencies do not add up to total mux inputs"
#     #     # Make sure that all the MuxLoadRRGs in list add up to our total wire loads
#     #     assert sum([mux_load.freq for mux_load in self.mux_loads]) == self.total_wire_loads, "Mux loads do not add up to total wire loads"

# @dataclass
# class Wire:
#     # Describes a wire type in the FPGA
#     name: str           = None            # Name of the wire type, used for the SpParameter globally across circuits Ex. "gen_routing_wire_L4", "intra_tile_ble_2_sb"    
#     layer: int          = None            # What RC index do we use for this wire (what metal layer does this corresond to?)
#     id: int             = None            # Unique identifier for this wire type, used to generate the wire name Ex. "gen_routing_wire_L4_0", "intra_tile_ble_2_sb_0"
#     def __post_init__(self):
#         # Struct verif checks
#         assert self.id >= 0, "uid must be a non-negative integer"

# @dataclass
# class GenRoutingWire(Wire):
#     """ 
#         This class describes a general routing wire in an FPGA. 
#     """
#     # Required fields
#     length: int              = None # Length of the general routing wire in number of tiles
#     mux_info: MuxWireStatRRG = None



# @dataclass 
# class RoutingWireLoad(c_ds.SizeableCircuit):

    

# Managing List of Configuration States for COFFE:
# use_rrg: bool -> If true we use RRG data to calculate wire loads + SB Mux sizes
# 


# Make FPGA class with "models" for each component
# Each model would have a list of possible base components, generated from user params
# From that list of components, we can iterate and swap out components while we run simulations to test multiple types of components
# When looking at multiple "models" we can determine if we need to do a geometric or linear sweep of them to accurately represent the FPGA
@dataclass
class FPGA:
    """ 
        This class describes an FPGA. 
        It contains all the subcircuits (SwitchBlock, ConnectionBlock, LogicCluster, etc.)
    """
    
    # Init only fields
    coffe_info: InitVar[rg_ds.Coffe]
    run_options: InitVar[NamedTuple]

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

    # FPGA Specifications required in later functions
    specs: c_ds.Specs = None

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
    sb_mux_basename: str = "sb_mux"
    routing_wire_load_basename: str = "routing_wire_load"



    # These strings are used as the names of various spice subckts in the FPGA
    #   We define thier names here so we can reference them to Simulation TB classes 
    #   before we actually create the subckt objects



    def __post_init__(self, coffe_info: rg_ds.Coffe, run_options: NamedTuple):
        """ 
            Post init function for FPGA class. 
            This function is called after the FPGA class is initialized.
            It is responsible for setting up the FPGA object with all the subcircuit models and subcircuit library.
        """





        # Init Specs
        self.specs = c_ds.Specs(
            coffe_info.fpga_arch_conf["fpga_arch_params"], 
            run_options.quick_mode
        )

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
            drv_types: List[str] = list(set([wire_stat["DRV_TYPE"].lower() for wire_stat in rr_wire_stats]))
            wire_types: List[str] = list(set([wire_stat["WIRE_TYPE"].lower() for wire_stat in rr_wire_stats]))
            drv_wire_pairs: Set[Tuple[str]] = set()
            # Seperate the input wire statistics into wire types
            for wire_stat in rr_wire_stats:
                # Create a WireStatRRG object for each combination of DRV and WIRE types (Assumpion only one drv type per wire type)
                stat_type: str = (wire_stat["COL_TYPE"]).lower()
                wire_drv_type: str = (wire_stat["DRV_TYPE"]).lower()
                wire_type: str = (wire_stat["WIRE_TYPE"]) # Not lowered as its matching name in config.yml
                # Check if this is component or total fanout
                drv_wire_pairs.add((wire_drv_type, wire_type))
                # Mux load from fanout info
                if "fanout" in stat_type:
                    drv_type = stat_type.replace("fanout_","").lower()
                    if drv_type in stat_type and "total" not in drv_type:
                        # this is component fanout
                        mux_load: c_ds.MuxLoadRRG = c_ds.MuxLoadRRG(
                            wire_type=wire_type,
                            mux_type=drv_type,
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
                        mux_ipin: c_ds.MuxIPIN = c_ds.MuxIPIN(
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
                mux_stat: c_ds.MuxWireStatRRG = c_ds.MuxWireStatRRG(
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
                        gen_r_wire: c_ds.GenRoutingWire = c_ds.GenRoutingWire(
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
                        src_wire: c_ds.Wire = c_ds.Wire(
                            id=0,
                            name="wire_general_ble_output_load",
                            layer=LOCAL_WIRE_LAYER,
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
            sb_muxes: List[sb_mux_lib.SwitchBlockMux] = []
            # Create Switch Block Mux Objects using the newly created loading information
            for i, wire_type in enumerate(sb_muxes_src_wires.keys()):
                sink_wire: c_ds.GenRoutingWire = self.gen_r_wires[wire_type]
                num_sb_per_tile: int = int( 4 * sink_wire.freq // (2 * sink_wire.length) )
                # Required size inferred from src_wires
                # num_sb_per_tile inferred from sink_wire.num_starting_per_tile -> from RRG
                sb_mux: sb_mux_lib.SwitchBlockMux = sb_mux_lib.SwitchBlockMux(
                    id = i,
                    src_wires = sb_muxes_src_wires[wire_type],
                    sink_wire = self.gen_r_wires[wire_type],
                    use_tgate = self.specs.use_tgate,
                )
                sb_muxes.append(sb_mux)
            
            ######################################
            ### CREATE CONNECTION BLOCK OBJECT ###
            ######################################
            cb_muxes: List[cb_mux_lib.ConnectionBlockMux] = []
            # Calculate connection block mux size
            cb_mux_size_required = int(self.specs.W * self.specs.Fcin)
            num_cb_mux_per_tile = self.specs.I
            # Initialize the connection block
            
            cb_mux = cb_mux_lib.ConnectionBlockMux(
                id = 0,
                required_size = cb_mux_size_required,
                num_per_tile = num_cb_mux_per_tile,
                use_tgate = self.specs.use_tgate,
                # self.sb_muxes[0], self.routing_wire_loads[0]
            )
            cb_muxes.append(cb_mux)

            ###########################
            ### CREATE LOAD OBJECTS ###
            ###########################
            # Create Dict holding the % distributions of logic block outputs per mux type
            #   For each BLE output, what is the chance that its going into each mux type? 
            ble_sb_mux_load_dist: Dict[sb_mux_lib.SwitchBlockMux, float] = {}
            ble_sb_mux_load_freq: Dict[sb_mux_lib.SwitchBlockMux, int] = {}
            sb_mux: sb_mux_lib.SwitchBlockMux
            for sb_mux in sb_muxes:
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
            ble_output_loads: List[gen_r_load_lib.GeneralBLEOutputLoad] = []
            # TODO bring this to the user level
            # For now we will pick whatever SB mux has the most BLE outputs as inputs to determine which SB mux should be ON in the load
            #   And we assume fanout is 1, with a single SB Mux being ON
            most_likely_on_sb: sb_mux_lib.SwitchBlockMux = max(ble_sb_mux_load_freq, key=ble_sb_mux_load_freq.get)
            sb_mux_on_assumption_freqs: Dict[sb_mux_lib.SwitchBlockMux, int] = { most_likely_on_sb: 1 }
            # Even with multiple SB types we will still create a single BLE output load, containing each type of SB Mux that could act as a load
            ble_output_load: gen_r_load_lib.GeneralBLEOutputLoad = gen_r_load_lib.GeneralBLEOutputLoad(
                id = 0,
                channel_usage_assumption = CHAN_USAGE_ASSUMPTION,
                sb_mux_on_assumption_freqs = sb_mux_on_assumption_freqs,
                sb_mux_load_dist = ble_sb_mux_load_dist
            )
            # We still keep to format of having list for every circuit and during simulation doing some user defined sweep (geometric, linear, etc.) over circuit list combos
            ble_output_loads.append(ble_output_load) 

            # Convert fanout information from RRG into a Dict[c_ds.GenRoutingWire, Dict[sb_mux_lib.SwitchBlockMux, Dict[str, int] ] ]
            # The inner most dict will have keys "freq" and "ISBD"

            # TODO implement "ISBD" type metrics from parsing RR_graph data
            gen_r_wire_load_freqs: Dict[c_ds.GenRoutingWire, Dict[sb_mux_lib.SwitchBlockMux, int ] ] = {}
            # Again assuming 1 gen_r_wire per 1 SB Mux drive type
            # Iterate over the Muxes driving each general routing wire
            for sb_mux in sb_muxes:
                gen_r_wire: c_ds.GenRoutingWire = sb_mux.sink_wire
                # Using this wire type find the fanout information stored in mux_stats
                mux_stat: c_ds.MuxWireStatRRG = [mux_stat for mux_stat in mux_stats if mux_stat.wire_type == gen_r_wire.type][0]
                # This convient line initalizes the dictionary if its empty at sb_mux, and will 
                gen_r_wire_load_freqs[gen_r_wire] = {}
                # Iterate over SB Muxes which are driving the muxes loading this gen_r_wire
                load_info: c_ds.MuxLoadRRG
                # TODO Look for CB_IPIN loads here
                for load_info in mux_stat.mux_loads:
                    # Find in our existing SB muxes which has the same wire_type as the sb_mux_load
                    sb_mux_load: sb_mux_lib.SwitchBlockMux = [sb_mux for sb_mux in sb_muxes if sb_mux.sink_wire.type == load_info.wire_type][0]
                    # Now we can create the dict entry for this gen_r_wire and sb_mux_load
                    gen_r_wire_load_freqs[gen_r_wire][sb_mux_load] = load_info.freq


            # Create the Routing Wire Load Objects
            routing_wire_loads: List[gen_r_load_lib.RoutingWireLoad] = []
            # TODO init a similar input as sb_mux_load_freqs except for cb_mux_load_freqs as current version only requires the cb_mux_load_freqs to have all valid cb_muxes as keys

            gen_r_wire: c_ds.GenRoutingWire
            for i, gen_r_wire in enumerate(gen_r_wire_load_freqs.keys()):
                # Pass all possible terminal SB muxes and create a RoutingWireLoad object for each
                # Make sure that its a valid terminal SB mux by checking to see if the gen_r_wire is in the SB Mux's src_wires
                terminal_sb_muxes: List[sb_mux_lib.SwitchBlockMux] = [sb_mux for sb_mux in sb_muxes if gen_r_wire in sb_mux.src_wires.keys()] 
                term_sb_mux: sb_mux_lib.SwitchBlockMux
                for term_sb_mux in terminal_sb_muxes:
                    # Create the RoutingWireLoad object
                    routing_wire_load: gen_r_load_lib.RoutingWireLoad = gen_r_load_lib.RoutingWireLoad(
                        id = i,
                        channel_usage_assumption = CHAN_USAGE_ASSUMPTION,
                        cluster_input_usage_assumption = CLUSTER_INPUT_USAGE_ASSUMPTION,
                        gen_r_wire = gen_r_wire,
                        sb_mux_load_freqs = gen_r_wire_load_freqs[gen_r_wire],     
                        terminal_sb_mux = term_sb_mux,               
                    )

                    # Append to the list of RoutingWireLoads
                    routing_wire_loads.append(routing_wire_load)

            ###################################
            ### CREATE LOGIC CLUSTER OBJECT ###
            ###################################
            




            # Once we have our Routing Mux + Wire Statistics we can create RoutingWireLoads and SwitchblockMuxes
        elif self.specs.wire_types and self.specs.Fs_mtx:
            # Not using an RR graph but getting our wire load information from an Fs matrix and user inputted wire types
            # TODO implement
            use_rrg = False
            pass 
        else:
            assert False, "No RR graph or wire types and Fs matrix provided. Cannot proceed."

        
                
            
            


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