from __future__ import annotations
from dataclasses import dataclass, field, InitVar

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
import src.coffe.mux_subcircuits as mux_subcircuits
import src.coffe.lut_subcircuits as lut_subcircuits
import src.coffe.ff_subcircuits as ff_subcircuits
import src.coffe.load_subcircuits as load_subcircuits
import src.coffe.memory_subcircuits as memory_subcircuits
import src.coffe.utils as utils
import src.coffe.cost as cost

# from src.coffe.circuit_baseclasses import _SizableCircuit, _CompoundCircuit

# Top level file generation module
import src.coffe.top_level as top_level

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
import src.coffe.new_gen_routing_loads as gen_r_load_lib
import src.coffe.new_sb_mux as sb_mux_lib
import src.coffe.new_cb_mux as cb_mux_lib
import src.coffe.new_logic_block as lb_lib
import src.coffe.new_carry_chain as carry_chain_lib
import src.coffe.ram as ram_lib
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
    log_out_catagories: List[str] = field(
        default_factory=lambda: []
    )

    ######################################################################################
    ### LISTS CONTAINING ALL CREATED SUBCIRCUITS (ALL MAY NOT BE SIMULATED AND SIZED)  ###
    ######################################################################################

    # Switch Block Muxes
    sb_mux: c_ds.Block = None
    sb_muxes: List[sb_mux_lib.SwitchBlockMux] = field(
        default_factory=lambda: []
    )
    sb_mux_tbs: List[sb_mux_lib.SwitchBlockMuxTB] = field(
        default_factory=lambda: []
    )
    # Connection Block Muxes
    cb_mux: c_ds.Block = None
    cb_muxes: List[cb_mux_lib.ConnectionBlockMux] = field(
        default_factory=lambda: []
    )
    cb_mux_tbs: List[cb_mux_lib.ConnectionBlockMuxTB] = field(
        default_factory=lambda: []
    )
    # BLE General Output Loads
    gen_ble_output_loads: List[gen_r_load_lib.GeneralBLEOutputLoad] = field(
        default_factory=lambda: []
    )
    # General Programmable Routing Loads
    gen_routing_loads: List[gen_r_load_lib.RoutingWireLoad] = field(
        default_factory=lambda: []
    )
    # Logic Clusters
    logic_cluster: c_ds.Block = None
    logic_clusters: List[lb_lib.LogicCluster] = field(
        default_factory=lambda: []
    )

    # Carry Chain Info, used in update_area and other functions
    carry_skip_periphery_count: int = None
    skip_size: int = None

    # Carry Chain Circuits 
    # TODO consolidate into a single object and conform to format used by other circuits
    carrychain: carry_chain_lib.CarryChain = None
    carrychainperf: carry_chain_lib.CarryChainPer = None
    carrychainmux: carry_chain_lib.CarryChainMux = None
    carrychaininter: carry_chain_lib.CarryChainInterCluster = None
    carrychainand: carry_chain_lib.CarryChainSkipAnd = None
    carrychainskipmux: carry_chain_lib.CarryChainSkipMux = None

    # Ram Circuits
    # TODO consolidate into a single object and conform to format used by other circuits
    RAM: ram_lib._RAM = None
    

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

        # Telemetry Info
        self.log_out_catagories = [
            "wire_length",
            "area",
            "tx_size",
            "delay",
        ]

        # Optimization Weights
        self.area_opt_weight = run_options.area_opt_weight
        self.delay_opt_weight = run_options.delay_opt_weight

        # Init Specs
        self.specs = c_ds.Specs(
            coffe_info.fpga_arch_conf["fpga_arch_params"], 
            run_options.quick_mode
        )

        self.use_tgate = self.specs.use_tgate

        # Init height of logic block to 0 (representing uninitialized)
        # TODO update all initializations to None instead of some other value
        self.lb_height = 0.0


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
                sb_mux: sb_mux_lib.SwitchBlockMux = sb_mux_lib.SwitchBlockMux(
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
                # self.sb_muxes[0], self.routing_wire_loads[0]
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

                    # [
                    #     sb_mux for sb_mux in self.sb_muxes if sb_mux.sink_wire.type == drv_2_seg_lookup[load_info.mux_type]
                    # ][0]



            # Iterate over CB muxes and determine which is capable of having taking each gen_r_wire as an input


            # Create the Routing Wire Load Objects
            self.routing_wire_loads: List[gen_r_load_lib.RoutingWireLoad] = []
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
                    self.routing_wire_loads.append(routing_wire_load)

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
            )
            self.logic_clusters.append(logic_cluster)
            ##################################
            ### CREATE CARRY CHAIN OBJECTS ###
            ##################################
            # TODO: Why is the carry chain created here and not in the logic cluster object?

            if self.specs.enable_carry_chain == 1:
                self.carrychain = carry_chain_lib.CarryChain(
                    id = 0,
                    cluster_size = self.specs.N, 
                    FAs_per_flut = self.specs.FAs_per_flut,
                    use_finfet = self.specs.use_finfet,
                )
                self.carrychainperf = carry_chain_lib.CarryChainPer(
                    id = 0,
                    use_tgate = self.specs.use_tgate,
                    use_finfet = self.specs.use_finfet, 
                )
                self.carrychainmux = carry_chain_lib.CarryChainMux(
                    id = 0,
                    use_fluts = self.specs.use_fluts,
                    use_tgate = self.specs.use_tgate,
                    use_finfet = self.specs.use_finfet, 
                )
                self.carrychaininter = carry_chain_lib.CarryChainInterCluster(
                    id = 0,
                    use_finfet = self.specs.use_finfet, 
                    carry_chain_type = self.specs.carry_chain_type,    
                    inter_wire_length = inter_wire_length,
                )
                if self.specs.carry_chain_type == "skip":
                    self.carrychainand = carry_chain_lib.CarryChainSkipAnd(
                        id = 0,
                        use_tgate = self.specs.use_tgate,
                        use_finfet = self.specs.use_finfet, 
                        carry_chain_type = self.specs.carry_chain_type,    
                        cluster_size = self.specs.N, 
                        FAs_per_flut = self.specs.FAs_per_flut,
                        skip_size = self.skip_size,
                    )
                    self.carrychainskipmux = carry_chain_lib.CarryChainSkipMux(
                        id = 0,
                        use_tgate = self.specs.use_tgate,
                        use_finfet = self.specs.use_finfet, 
                        carry_chain_type = self.specs.carry_chain_type,    
                    )
            
            #########################
            ### CREATE RAM OBJECT ###
            #########################
            # TODO update to dataclasses
            RAM_local_mux_size_required = float(self.specs.ram_local_mux_size)
            RAM_num_mux_per_tile = (3 + 2*(self.specs.row_decoder_bits + self.specs.col_decoder_bits + self.specs.conf_decoder_bits ) + 2** (self.specs.conf_decoder_bits))
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

                                                          

        # Once we have our Routing Mux + Wire Statistics we can create RoutingWireLoads and SwitchblockMuxes
        # elif self.specs.wire_types and self.specs.Fs_mtx:
        #     # Not using an RR graph but getting our wire load information from an Fs matrix and user inputted wire types
        #     # TODO implement
        #     use_rrg = False
        #     pass 
        # else:
        #     assert False, "No RR graph or wire types and Fs matrix provided. Cannot proceed."

        
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
        sb_mux: sb_mux_lib.SwitchBlockMux
        for sb_mux in self.sb_muxes:
            self.transistor_sizes.update(
                sb_mux.generate(
                    self.subcircuits_filename
                )
            )
       
        # Iterate over all existing sb muxes and generate them + cluster / gen routing load collateral 
        # for sb_mux in self.sb_muxes:

        #     # self.transistor_sizes.update(cb_mux.generate(self.subcircuits_filename, 
        #     #                                               self.specs.min_tran_width))
            
        #     # self.transistor_sizes.update(logic_cluster.generate(self.subcircuits_filename, 
        #     #                                                      self.specs.min_tran_width, 
        #     #                                                      self.specs))

        #     self.transistor_sizes.update(
        #         sb_mux.generate(
        #             self.subcircuits_filename, 
        #             self.specs.min_tran_width
        #         )
        #     )
            # sb_mux.generate_top()
        gen_ble_output_load: gen_r_load_lib.GeneralBLEOutputLoad
        for gen_ble_output_load in self.gen_ble_output_loads:
            gen_ble_output_load.generate(self.subcircuits_filename, self.specs)

        routing_wire_load: gen_r_load_lib.RoutingWireLoad
        for routing_wire_load in self.routing_wire_loads:
            routing_wire_load.generate(self.subcircuits_filename, self.specs)
        
        if self.specs.enable_carry_chain == 1:
            self.transistor_sizes.update(self.carrychain.generate(self.subcircuits_filename))
            self.transistor_sizes.update(self.carrychainperf.generate(self.subcircuits_filename))
            self.transistor_sizes.update(self.carrychainmux.generate(self.subcircuits_filename))
            self.transistor_sizes.update(self.carrychaininter.generate(self.subcircuits_filename))
            if self.specs.carry_chain_type == "skip":
                self.transistor_sizes.update(self.carrychainand.generate(self.subcircuits_filename))
                self.transistor_sizes.update(self.carrychainskipmux.generate(self.subcircuits_filename))

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
        # parser_args = {
        #     "input_sp_files": [self.basic_subcircuits_filename, self.subcircuits_filename],
        #     "get_structs": True,
        # }

        parser_args = [
            "--input_sp_files",  self.basic_subcircuits_filename, self.subcircuits_filename,
            "--get_structs",
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
            "BRIEF": "1"
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
        # Certain simulations may run at lower / higher clock freqs? The only reason I could see for this would be make sure the meas statements voltage triggers hit
        sb_mux_sim_mode.sim_time = c_ds.Value(8, units = sb_mux_sim_mode.sim_time.units) # ns

        print("Creating SB Mux TB Objects:")
        src_r_wire_load: gen_r_load_lib.RoutingWireLoad
        for src_r_wire_load in self.routing_wire_loads:
            sink_r_wire_load: gen_r_load_lib.RoutingWireLoad
            for sink_r_wire_load in self.routing_wire_loads:
                # Make sure this general routing wire load is driving the wire we expect
                if src_r_wire_load.terminal_sb_mux.sink_wire == sink_r_wire_load.gen_r_wire:
                    def condition(sb_mux: sb_mux_lib.SwitchBlockMux) -> bool:
                        return sb_mux.sink_wire == src_r_wire_load.gen_r_wire
                    start_sb_mux: sb_mux_lib.SwitchBlockMux = rg_utils.get_unique_obj(
                        self.sb_muxes,
                        condition,
                    )
                    print((
                        f"{start_sb_mux.sink_wire.type} DUT[ -> "
                        f"{src_r_wire_load.terminal_sb_mux.sink_wire.type}] -> "
                        f"{sink_r_wire_load.terminal_sb_mux.sink_wire.type}"
                    ))
                    # Create a testbench for this legal combination
                    sb_mux_tb: sb_mux_lib.SwitchBlockMuxTB = sb_mux_lib.SwitchBlockMuxTB(
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
                    # For now only append to the list for each uniq comb of src_routing_wire_load & sink_routing_wire_load
                    # ie ignore unique start sb_muxes
                    # TODO implement TB filtering somewhere else
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
        print("Creating CB Mux TB Object")
        
        cb_mux_sim_mode: c_ds.SpSimMode = copy.deepcopy(base_sim_mode)
        # Certain simulations may run at lower / higher clock freqs? The only reason I could see for this would be make sure the meas statements voltage triggers hit
        cb_mux_sim_mode.sim_time = c_ds.Value(4, units = sb_mux_sim_mode.sim_time.units) # ns
        
        # Num TBs = number of unique terminating CB muxes * num unique routing wire loads that can drive them * \
        #           * num unique terminating local muxes * num unique local routing wire load that can drive them
        
        # TODO implement for the above, but for now we're just going to assume we only have a single CB mux type in the device
        # Find all legal gen routing wire load components
        cb_tb_gen_r_wire_loads: List[gen_r_load_lib.RoutingWireLoad] = []
        cb_tb_local_r_wire_loads: List[lb_lib.LocalRoutingWireLoad] = []
        cb_tb_local_muxes: List[lb_lib.LocalMux] = []
        cb_tb_lut_input_drivers: List[lb_lib.ble_lib.lut_lib.LUTInputDriver] = []
        for cb_mux in self.cb_muxes:
            for gen_r_wire_load in self.routing_wire_loads:
                if gen_r_wire_load.terminal_cb_mux and gen_r_wire_load.terminal_cb_mux == cb_mux and \
                    gen_r_wire_load.tile_cb_load_assignments[0][gen_r_wire_load.terminal_cb_mux]["num_on"] > 0:
                    cb_tb_gen_r_wire_loads.append(gen_r_wire_load)
        # TODO find all legal local routing wire loads that can be driven by the CB mux
        # We just assume as many types as we have logic clusters TODO circuits should be split up and indivdualized for more clarity + modularity
        cb_tb_local_r_wire_loads = [lb.local_routing_wire_load for lb in self.logic_clusters]
        cb_tb_local_muxes = [lb.local_mux for lb in self.logic_clusters]
        cb_tb_lut_input_drivers = [lb.ble.lut.input_drivers["a"].driver for lb in self.logic_clusters]
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
                cb_tb_gen_r_wire_loads,
                cb_tb_local_r_wire_loads, 
                cb_tb_local_muxes, 
                cb_tb_lut_input_drivers
            )
        )
        for cb_tb_in_ckt_combo in cb_tb_in_ckt_combos:
            gen_r_wire_load: gen_r_load_lib.RoutingWireLoad = cb_tb_in_ckt_combo[0]
            local_r_wire_load: lb_lib.LocalRoutingWireLoad = cb_tb_in_ckt_combo[1]
            lut_input_driver: lb_lib.ble_lib.lut_lib.LUTInputDriver = cb_tb_in_ckt_combo[3]
            # Find SB mux corresponding to the wire load
            def condition (sb_mux: sb_mux_lib.SwitchBlockMux) -> bool:
                return sb_mux.sink_wire == gen_r_wire_load.gen_r_wire
            start_sb_mux: sb_mux_lib.SwitchBlockMux = rg_utils.get_unique_obj(
                self.sb_muxes,
                condition,
            )
            cb_mux_tb: cb_mux_lib.ConnectionBlockMuxTB = cb_mux_lib.ConnectionBlockMuxTB(
                # CB Mux Specific args
                start_sb_mux = start_sb_mux,
                gen_r_wire_load = gen_r_wire_load,
                local_r_wire_load = local_r_wire_load,
                lut_input_driver = lut_input_driver,
                # General SimTB args
                inc_libs = inc_libs,
                mode = cb_mux_sim_mode,
                options = sim_options,
                # Pass in library of all subckts 
                subckt_lib = self.subckt_lib,
            )
            self.cb_mux_tbs.append(cb_mux_tb)

        # Generate top-level files. These top-level files are the files that COFFE uses to measure 
        # the delay of FPGA circuitry
        for sb_mux_tb in self.sb_mux_tbs:
            sb_mux_tb.generate_top()

        for cb_mux_tb in self.cb_mux_tbs:
            cb_mux_tb.generate_top()
        
        self.logic_cluster.generate_top(self.subckt_lib)

        #   _    ___   ___ ___ ___    ___ _   _   _ ___ _____ ___ ___ 
        #  | |  / _ \ / __|_ _/ __|  / __| | | | | / __|_   _| __| _ \
        #  | |_| (_) | (_ || | (__  | (__| |_| |_| \__ \ | | | _||   /
        #  |____\___/ \___|___\___|  \___|____\___/|___/ |_| |___|_|_\
                                                            

        if self.specs.enable_carry_chain == 1:
            self.carrychain.generate_top()
            self.carrychainperf.generate_top()
            self.carrychainmux.generate_top(self.min_len_wire)
            self.carrychaininter.generate_top()
            if self.specs.carry_chain_type == "skip":
                self.carrychainand.generate_top()
                self.carrychainskipmux.generate_top()

        # RAM
        if self.specs.enable_bram_block == 1:
            self.RAM.generate_top()

        for hardblock in self.hardblocklist:
            hardblock.generate_top(size_hb_interfaces)

        # Calculate area, and wire data.
        print("Calculating area...")
        # Update area values
        self.update_area()
        print("Calculating wire lengths...")
        self.update_wires()
        print("Calculating wire resistance and capacitance...")
        self.update_wire_rc()
    
        print("")
            

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
      
      
    def _update_area_per_transistor(self):
        """ We use self.transistor_sizes to calculate area
            Using the area model, we calculate the transistor area in minimum width transistor areas.
            We also calculate area in nm and transistor width in nm. Nanometer values are needed for wire length calculations.
            For each transistor, this data forms a tuple (tran_name, tran_channel_width_nm, tran_drive_strength, tran_area_min_areas, tran_area_nm, tran_width_nm)
            The FPGAs transistor_area_list is updated once these values are computed."""
        
        # Initialize transistor area list
        tran_area_list = []
        
        # For each transistor, calculate area
        for tran_name, tran_size in self.transistor_sizes.items():
                # Get transistor drive strength (drive strength is = xMin width)
                tran_drive = tran_size
                # Get tran area in min transistor widths
                tran_area = self._area_model(tran_name, tran_drive)
                # Get area in nm square
                tran_area_nm = tran_area*self.specs.min_width_tran_area
                # Get width of transistor in nm
                tran_width = math.sqrt(tran_area_nm)
                # Add this as a tuple to the tran_area_list
                # TODO: tran_size and tran_drive are the same thing?!
                tran_area_list.append((tran_name, tran_size, tran_drive, tran_area, 
                                                tran_area_nm, tran_width))    
                                                                                   
        # Assign list to FPGA object
        self.transistor_area_list = tran_area_list
        

    def _update_area_and_width_dicts(self):
        """ Calculate area for basic subcircuits like inverters, pass transistor, 
            transmission gates, etc. Update area_dict and width_dict with this data."""
        
        # Initialize component area list of tuples (component name, component are, component width)
        comp_area_list = []
        
        # Create a dictionary to store component sizes for multi-transistor components
        comp_dict = {}
        
        # For each transistor in the transistor_area_list
        # tran is a tuple having the following formate (tran_name, tran_channel_width_nm, 
        # tran_drive_strength, tran_area_min_areas, tran_area_nm, tran_width_nm)
        for tran in self.transistor_area_list:
            # those components should have an nmos and a pmos transistors in them
            if "inv_" in tran[0] or "tgate_" in tran[0]:
                # Get the component name; transistors full name example: inv_lut_out_buffer_2_nmos.
                # so the component name after the next two lines will be inv_lut_out_buffe_2.
                comp_name = tran[0].replace("_nmos", "")
                comp_name = comp_name.replace("_pmos", "")
                
                # If the component is already in the dictionary
                if comp_name in comp_dict:
                    if "_nmos" in tran[0]:
                        # tran[4] is tran_area_nm
                        comp_dict[comp_name]["nmos"] = tran[4]
                    else:
                        comp_dict[comp_name]["pmos"] = tran[4]
                        
                    # At this point we should have both NMOS and PMOS sizes in the dictionary
                    # We can calculate the area of the inverter or tgate by doing the sum
                    comp_area = comp_dict[comp_name]["nmos"] + comp_dict[comp_name]["pmos"]
                    comp_width = math.sqrt(comp_area)
                    comp_area_list.append((comp_name, comp_area, comp_width))                 
                else:
                    # Create a dict for this component to store nmos and pmos sizes
                    comp_area_dict = {}
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
                comp_name = tran[0].replace("_nmos", "")
                comp_name = comp_name.replace("_pmos", "")               
                # Add this to comp_area_list directly
                comp_area_list.append((comp_name, tran[4], tran[5]))            
        
        # Convert comp_area_list to area_dict and width_dict
        area_dict = {}
        width_dict = {}
        for component in comp_area_list:
            area_dict[component[0]] = component[1]
            width_dict[component[0]] = component[2]
        
        # Set the FPGA object area and width dict
        self.area_dict = area_dict
        self.width_dict = width_dict
  
        return




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