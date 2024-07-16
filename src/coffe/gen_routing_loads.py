# -*- coding: utf-8 -*-
"""
    This module contains implementations for general programmable routing loads.
"""

import src.coffe.utils as utils

from typing import Dict, List, Tuple, Union, Any, Set
from dataclasses import dataclass, field
import copy
import math, os
import src.coffe.data_structs as c_ds
import src.common.utils as rg_utils
import src.coffe.sb_mux as sb_mux_lib
import src.coffe.cb_mux as cb_mux_lib

import src.coffe.constants as consts
import src.coffe.fpga as fpga

from collections import defaultdict

@dataclass
class GeneralBLEOutputLoad(c_ds.LoadCircuit):
    name: str = "general_ble_output_load"                              # Used during spMux write out to determine the names of Tx size parameters & subckt names, Ex. sb_mux_uid_0
    channel_usage_assumption: float = None                             # Assumed routing channel usage, what % of routing wires are driven?
    # num_sb_mux_on_assumption: int = None                             # Assumed number of 'on' SB muxes on cluster output, needed for load calculation
    # sb_mux_on: sb_mux_lib.SwitchBlockMux = None                      # Which SB mux is on? This data structure is used
    
    # There could be a larger number of ON muxes if the fanout at that particular net leaving the BLE is high
    sb_mux_on_assumption_freqs: Dict[sb_mux_lib.SwitchBlockMux, int] = None  # Which SB muxes (and how many of each) are driving an ON mux in this load?
    sb_mux_load_dist: Dict[sb_mux_lib.SwitchBlockMux, float] = None  # What is the likelyhood for each SB mux in this dict to be loading a BLE output?

    # Used as inputs to compute_load, Initialized in __post_init__
    # Calculated in compute_load
    sb_load_types: Dict[sb_mux_lib.SwitchBlockMux, Dict[str, int]] = None # Dict of each SB Mux type and the number of on, partial, and off muxes of that type 
    total_sb_muxes: int = None             # total number of SB muxes on cluster output

    def __post_init__(self):
        self.sp_name = self.get_sp_name()
        self.sb_load_types = defaultdict(lambda: {"num_on": 0, "num_partial": 0, "num_off": 0})
    
    def __hash__(self) -> int:
        return id(self)

    def generate(self, subcircuit_filename: str, specs: c_ds.Specs):
        """ Compute cluster output load load and generate SPICE netlist. """
        
        self._compute_load(specs)
        self.wire_names = self.generate_general_ble_output_load(subcircuit_filename)

    def _compute_load(self, specs: c_ds.Specs):
        """ 
            Calculate how many on/partial/off switch block multiplexers are connected to each cluster output.
            Inputs are FPGA specs object, switch block mux object, assumed channel usage and assumed number of on muxes.
            The function will update the object's off & partial attributes.
            
        """
        
        # Number of tracks in the channel connected to LB opins
        num_tracks = specs.W

        # Total number of switch block multiplexers connected to cluster output
        total_load = int(specs.Fcout * num_tracks)

        # Total On SB muxes connected to cluster output
        # total_on_sb_muxes = sum(self.sb_mux_on_assumption_freqs.values())
        
        # Calculate the number of on, partial, and off SB Mux paths for each SB mux type in sb_mux_load_dist keys
        for sb_mux_load in self.sb_mux_load_dist.keys():
            self.sb_load_types[sb_mux_load]["num_on"] = self.sb_mux_on_assumption_freqs.get(sb_mux_load, 0)
            self.sb_load_types[sb_mux_load]["num_partial"] = int(
                total_load * self.channel_usage_assumption \
                    * self.sb_mux_load_dist[sb_mux_load] * (1 / sb_mux_load.level1_size)
            )
            self.sb_load_types[sb_mux_load]["num_off"] = total_load - (self.sb_load_types[sb_mux_load]["num_on"] + self.sb_load_types[sb_mux_load]["num_partial"])

        # Add up all the SB muxes which were created, used for calculating wire lengths between SB mux loads
        self.total_sb_muxes = sum([sb_mux_info["num_off"] + sb_mux_info["num_partial"] + sb_mux_info["num_on"] for sb_mux_info in self.sb_load_types.values()])
    

    def generate_general_ble_output_load(self, spice_filename: str):
        """ Create the cluster output load SPICE deck. We assume 2-level muxes. The load is distributed as
            off, then partial, then on. 
            Inputs are SPICE file, number of SB muxes that are off, then partially on, then on.
            Returns wire names used in this SPICE circuit."""
        
        # Define the parameters for wire RCs, these will be returned from this function
        # Commenting out while testing to see if the multi sb mux itself is working, dont want to have to change LUT stuff
        
        # TODO get this wire name from the SB Mux objects themselves for consistency of where dependancies come from
        wire_general_ble_output_pstr = f"wire_{self.sp_name}"
        
        # Node definitions
        gnd_node = "n_gnd"
        vdd_node = "n_vdd" 
        # For transmission gates
        nfet_g_node = "n_gate"
        pfet_g_node = "n_gate_n"
        in_node = "n_1_1"
        out_node = "n_out"
        meas_node = "n_meas_point"

        spice_file_lines = []
        # Generating lines of spice file in order of netlist connectivity...
        spice_file_lines += [
            "******************************************************************************************",
            "* General BLE output load",
            "******************************************************************************************",
            # Subckt named based on which sb mux is ON in the path, there exists other SB muxes (OFF + PARTIAL) on the path as well      
            f".SUBCKT {self.sp_name} {in_node} {out_node} {nfet_g_node} {pfet_g_node} {vdd_node} {gnd_node}"  
        ]
        current_node = "n_1_1"
        next_node = "n_1_2"
        # Write out all of the OFF SB muxes
        total_num_sb_mux_off = 0
        node_it = 0
        sb_mux_load: sb_mux_lib.SwitchBlockMux
        for sb_id, sb_mux_load in enumerate(self.sb_load_types.keys()):
            # TODO standardize some function call which determines these names for OFF / ON / PARTIAL muxes
            subckt_sb_mux_off_str: str = f"{sb_mux_load.sp_name}_off"
            for i in range(self.sb_load_types[sb_mux_load]["num_off"]):
                spice_file_lines += [
                    f"Xwire_{subckt_sb_mux_off_str}_{i+1} {current_node} {next_node} wire Rw='{wire_general_ble_output_pstr}_res/{self.total_sb_muxes}' Cw='{wire_general_ble_output_pstr}_cap/{self.total_sb_muxes}'",
                    f"X{subckt_sb_mux_off_str}_{i+1} {next_node} {nfet_g_node} {pfet_g_node} {vdd_node} {gnd_node} {subckt_sb_mux_off_str}",
                ]
                current_node = next_node
                next_node = f"n_1_{node_it+3}"
                node_it += 1
                total_num_sb_mux_off += 1

        # Write out all of the partial SB muxes
        total_num_sb_partial = 0
        sb_mux_load: sb_mux_lib.SwitchBlockMux
        for sb_id, sb_mux_load in enumerate(self.sb_load_types.keys()):
            subckt_sb_mux_partial_str: str = f"{sb_mux_load.sp_name}_partial"
            for i in range(self.sb_load_types[sb_mux_load]["num_partial"]):
                spice_file_lines += [
                    f"Xwire_{subckt_sb_mux_partial_str}_{i + 1 + total_num_sb_mux_off} {current_node} {next_node} wire Rw='{wire_general_ble_output_pstr}_res/{self.total_sb_muxes}' Cw='{wire_general_ble_output_pstr}_cap/{self.total_sb_muxes}'",
                    f"X{subckt_sb_mux_partial_str}_{i + 1} {next_node} {nfet_g_node} {pfet_g_node} {vdd_node} {gnd_node} {subckt_sb_mux_partial_str}",
                ]
                current_node = next_node
                next_node = f"n_1_{node_it+3}"
                node_it += 1
                total_num_sb_partial += 1
        # Write out all of the ON SB muxes
        total_num_sb_on = 0
        sb_mux_load: sb_mux_lib.SwitchBlockMux
        for sb_id, sb_mux_load in enumerate(self.sb_load_types.keys()):
            subckt_sb_mux_on_str: str = f"{sb_mux_load.sp_name}_on"
            for i in range(self.sb_load_types[sb_mux_load]["num_on"]):
                if i == self.sb_load_types[sb_mux_load]["num_on"] - 1:
                    spice_file_lines += [
                        f"Xwire_{subckt_sb_mux_on_str}_{i + 1 + total_num_sb_mux_off + total_num_sb_partial} {current_node} {meas_node} wire Rw='{wire_general_ble_output_pstr}_res/{self.total_sb_muxes}' Cw='{wire_general_ble_output_pstr}_cap/{self.total_sb_muxes}'",
                        f"X{subckt_sb_mux_on_str}_{i + 1} {meas_node} {out_node} {nfet_g_node} {pfet_g_node} {vdd_node} {gnd_node} {subckt_sb_mux_on_str}",
                    ]
                else:
                    spice_file_lines += [
                        f"Xwire_{subckt_sb_mux_on_str}_{i + 1 + total_num_sb_mux_off + total_num_sb_partial} {current_node} {next_node} wire Rw='{wire_general_ble_output_pstr}_res/{self.total_sb_muxes}' Cw='{wire_general_ble_output_pstr}_cap/{self.total_sb_muxes}'",
                        f"X{subckt_sb_mux_on_str}_{i + 1} {next_node} n_hang_{i} {nfet_g_node} {pfet_g_node} {vdd_node} {gnd_node} {subckt_sb_mux_on_str}",
                    ]   
            current_node = next_node
            next_node = f"n_1_{node_it + total_num_sb_mux_off + total_num_sb_partial + 3}"
            node_it += 1
            total_num_sb_on += 1
        
        # End of Subckt
        spice_file_lines.append(".ENDS\n\n")

        # Write out lines to the file
        with open(spice_filename, 'a') as spice_file:
            for line in spice_file_lines:
                spice_file.write(line + "\n")
        
        # Create a list of all wires used in this subcircuit
        wire_names_list = []
        wire_names_list.append(wire_general_ble_output_pstr)
        
        return wire_names_list

    def update_wires(self, width_dict: Dict[str, float], wire_lengths: Dict[str, float], wire_layers: Dict[str, int], h_dist: float = None, height: float = None):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """
        
        # The BLE output wire is the wire that allows a BLE output to reach routing wires in
        # the routing channels. This wire spans some fraction of a tile. We can set what that
        # fraction is with the output track-access span (track-access locality).


        # gen_ble_out_wire_key = f"wire_general_ble_output_wire_uid{self.gen_r_wire['id']}"

        # Look for keys in the wire names which would be suffixed by some parameter string
        def condition (wire_key: str) -> bool:
            return "wire_general_ble_output" in wire_key
        gen_ble_out_wire_key = rg_utils.get_unique_obj(self.wire_names, condition)

        # Make sure it exists in the class definition, unncessesary here but just maintaining convention as some wire keys are not coming from wire_names
        assert gen_ble_out_wire_key in self.wire_names, f"Wire {gen_ble_out_wire_key} not found in wire names list"
        
        # height is the lb_height, I wonder why once we have initialized the lb_height we no longer use the output track locality
        wire_lengths[gen_ble_out_wire_key] = width_dict["tile"] * consts.OUTPUT_TRACK_ACCESS_SPAN
        # It's not possible for the wire to be longer than the output track access span * tile width
        if height and h_dist:
            # if h_dist <= width_dict["tile"]:
            wire_lengths[gen_ble_out_wire_key] = h_dist
            # else:
            #     print(f"Warning: The distance between the BLE output and the routing channel is greater than the tile width * OUTPUT_TRACK_ACCESS_SPAN. Setting wire length to tile width.")
            #     print(f"Distance: {h_dist}, Tile Width: {width_dict['tile']}")

        # Update wire layers
        wire_layers[gen_ble_out_wire_key] = consts.LOCAL_WIRE_LAYER

    def print_details(self, report_fpath: str):
        """ Print cluster output load details """
        
        utils.print_and_write(report_fpath, "  CLUSTER OUTPUT LOAD DETAILS:")
        # utils.print_and_write(report_file, "  Total number of SB inputs connected to cluster output: " + str(self.num_sb_mux_off + self.num_sb_mux_partial + self.num_sb_mux_on_assumption))
        # utils.print_and_write(report_file, "  Number of 'on' SB MUXes (assumed): " + str(self.num_sb_mux_on_assumption))
        # utils.print_and_write(report_file, "  Number of 'partial' SB MUXes: " + str(self.num_sb_mux_partial))
        # utils.print_and_write(report_file, "  Number of 'off' SB MUXes: " + str(self.num_sb_mux_off))
        # utils.print_and_write(report_file, "")
    

@dataclass
class RoutingWireLoad(c_ds.LoadCircuit):
    """ 
        This is the routing wire load for an architecture with direct drive and only one segment length.
        Two-level muxes are assumed and we model for partially on paths. 
    """
    name: str = "routing_wire_load"                              # Used during spMux write out to determine the names of Tx size parameters & subckt names, Ex. sb_mux_uid_0
    gen_r_wire: c_ds.GenRoutingWire = None                       # What wire are we driving?
    channel_usage_assumption: float = None                             # Assumed routing channel usage, what % of routing wires are driven?
    cluster_input_usage_assumption: float = None
    # sb_mux_isbd: Dict[sb_mux_lib.SwitchBlockMux, int] = None  # For each SB mux how frequently does it branch out to 
    terminal_sb_mux: sb_mux_lib.SwitchBlockMux = None                       # What SB mux is driven at the end of this wire load?
    sb_mux_load_freqs: Dict[sb_mux_lib.SwitchBlockMux, int] = None               # W.r.t the SB muxes loading this wire, how many of each type are there?
    sb_mux_on_assumption_freqs: Dict[sb_mux_lib.SwitchBlockMux, int] = field(
        default_factory = lambda: {}
    )  # Which SB muxes (and how many of each) are driving an ON mux in this load?
    terminal_cb_mux: cb_mux_lib.ConnectionBlockMux = None # What is the terminal CB mux driven
    cb_mux_load_freqs: Dict[cb_mux_lib.ConnectionBlockMux, int] = None # W.r.t the SB muxes loading this wire, how many of each type are there?
    cb_mux_on_assumption_freqs: Dict[cb_mux_lib.ConnectionBlockMux, int] = field(
        default_factory = lambda: {}
    )  # Which SB muxes (and how many of each) are driving an ON mux in this load?

    # Used as inputs to compute_load, Initialized in __post_init__
    # Calculated in compute_load
    sb_load_budgets: Dict[sb_mux_lib.SwitchBlockMux, Dict[str, int]] = None
    cb_load_budgets: Dict[cb_mux_lib.ConnectionBlockMux, Dict[str, int]] = None

    tile_sb_load_assignments: List[Dict[sb_mux_lib.SwitchBlockMux, Dict[str, int]]] = None
    tile_cb_load_assignments: List[Dict[cb_mux_lib.ConnectionBlockMux, Dict[str, int]]] = None
    
    # How many of each SB mux type are connected to each tile, and how many are on, partial, and off
    # cb_load_budgets: 
    def __post_init__(self):
        self.sp_name = self.get_sp_name()

    def __hash__(self) -> int:
        return id(self)

    def _compute_load(self, specs: c_ds.Specs):
        # Local variables
        W: int = specs.W
        I: int = specs.I
        L: int = self.gen_r_wire.length
 
        # Get the total number of partial, on, off muxes for each type across all tiles in load
        # SB Mux Budget Calc
        self.sb_load_budgets = defaultdict(lambda: {"num_on": 0, "num_partial": 0, "num_off": 0})
        sb_load: sb_mux_lib.SwitchBlockMux
        for sb_load, freq in self.sb_mux_load_freqs.items():
            self.sb_load_budgets[sb_load]["num_on"] = self.sb_mux_on_assumption_freqs.get(sb_load, 0)
            self.sb_load_budgets[sb_load]["num_partial"] = int(freq * self.channel_usage_assumption * (1 / sb_load.level1_size))
            self.sb_load_budgets[sb_load]["num_off"] = freq - (self.sb_load_budgets[sb_load]["num_on"] + self.sb_load_budgets[sb_load]["num_partial"])

        # Create dict for the target frequency we'd like to achieve for each type of SB mux
        sb_mux_load_targ_dist: Dict[sb_mux_lib.SwitchBlockMux, float] = {
            sb_load: freq / sum(self.sb_mux_load_freqs.values()) 
                for sb_load, freq in self.sb_mux_load_freqs.items()
        }
        # Total budget in ON, OFF, PARTIALs across all SB types
        # sb_load_state_budget_totals = {
        #     "num_on": sum([sb_info["num_on"] for sb_info in self.sb_load_budgets.values()]),
        #     "num_partial": sum([sb_info["num_partial"] for sb_info in self.sb_load_budgets.values()]),
        #     "num_off": sum([sb_info["num_off"] for sb_info in self.sb_load_budgets.values()])
        # }
        # Total budget for each type of SB mux, not broken down by ON, OFF, PARTIAL
        sb_load_type_budget_totals = {
            sb_load: sb_info["num_on"] + sb_info["num_partial"] + sb_info["num_off"]
                for sb_load, sb_info in self.sb_load_budgets.items()
        }
        # If the number of partial muxes is 0, we round up to 1 to model a worst case
        # Choose the highest freq sb mux to round up partial load
        most_freq_sb_mux = max(self.sb_load_budgets, key=sb_load_type_budget_totals.get)
        if self.sb_load_budgets[most_freq_sb_mux]["num_partial"] == 0:
            self.sb_load_budgets[most_freq_sb_mux]["num_partial"] = 1

        self.cb_load_budgets = defaultdict(lambda: {"num_on": 0, "num_partial": 0, "num_off": 0})
        # CB Mux Budget Calc
        cb_load: cb_mux_lib.ConnectionBlockMux
        # TODO update to take an inputted freq rather than calculating it ourselves 
        for cb_load, freq in self.cb_mux_load_freqs.items():

            cb_load_on_probability = float((I / 2.0 * self.cluster_input_usage_assumption * L)) / (W * self.channel_usage_assumption)
            cb_load_on = int(round(cb_load_on_probability))

            cb_load_partial_probability = (I / 2 * self.cluster_input_usage_assumption * (cb_load.level2_size - 1) * L) / W
            cb_load_partial = int(round(cb_load_partial_probability))

            if freq == 0:
                for cb_state in self.cb_load_budgets.keys():
                    self.cb_load_budgets[cb_load][cb_state] = 0
            else:
                self.cb_load_budgets[cb_load]["num_on"] = cb_load_on
                self.cb_load_budgets[cb_load]["num_partial"] = cb_load_partial
                self.cb_load_budgets[cb_load]["num_off"] = freq - (self.cb_load_budgets[cb_load]["num_on"] + self.cb_load_budgets[cb_load]["num_partial"])

            # # Calculate connection block load per tile
            # # We assume that cluster inputs are divided evenly between horizontal and vertical routing channels
            # # We can get the total number of CB inputs connected to the channel segment by multiplying cluster inputs by cb_mux_size, then divide by W to get cb_inputs/wire
            # cb_load_per_tile = int(round(float(I / 2 * cb_load.implemented_size) / W))

            # Now we got to find out how many are on, how many are partially on and how many are off
            # For each tile, we have half of the cluster inputs connecting to a routing channel and only a fraction of these inputs are actually used
            # It is logical to assume that used cluster inputs will be connected to used routing wires, so we have I/2*input_usage inputs per tile,
            # we have L tiles so, I/2*input_usage*L fully on cluster inputs connected to W*channel_usage routing wires
            # If we look at the whole wire, we are selecting I/2*input_usage*L signals from W*channel_usage wires
            # Even though all the wires are not of minimum length, we use the same W for all wires 
            #       because it would be innacurate to just use the portion of channel of minimum length (we are doing an estimate)

            # cb_load_on_probability = float((I / 2.0 * self.cluster_input_usage_assumption * L)) / (W * self.channel_usage_assumption)
            # cb_load_on = int(round(cb_load_on_probability))
            # # If < 1, we round up to one because at least one wire will have a fully on path connected to it and we model for that case.
            # if cb_load_on == 0:
            #     self.cb_load_budgets[cb_load]["num_on"] = 1
            # # Each fully turned on cb_mux comes with (cb_level2_size - 1) partially on paths
            # # The number of partially on paths per tile is I/2*input_usage * (cb_level2_size - 1) 
            # # Number of partially on paths per wire is (I/2*input_usage * (cb_level2_size - 1) * L) / W
            # cb_load_partial_probability = (I / 2 * self.cluster_input_usage_assumption * (cb_load.level2_size - 1) * L) / W
            # cb_load_partial = int(round(cb_load_partial_probability))
            # # If < 1, we round up to one because at least one wire will have a partially on path connected to it and we model for that case.
            # if cb_load_partial == 0:
            #     self.cb_load_budgets[cb_load]["num_partial"] = 1
            # # Number of off paths is just number connected to routing wire - on - partial
            # self.cb_load_budgets[sb_load]["num_off"] = cb_load_per_tile * L - (self.sb_load_budgets[sb_load]["num_on"] + self.sb_load_budgets[sb_load]["num_partial"])


        # From calculated budget assign the loads to each tile
        # We take the total number of sb loads of all types and divide by the number of tiles to get the max number of sb muxes per tile
        # tile_sb_total_budget = sum([sb_info["num_off"] + sb_info["num_partial"] + sb_info["num_on"] for sb_info in self.sb_load_budgets.values()])
        # tile_sb_max = math.ceil(float(tile_sb_total_budget) / L)
        
        # Max of each type of sb per tile
        tile_sb_type_maxes = {
            sb_load: math.ceil(total_freq / L)
            for sb_load, total_freq in sb_load_type_budget_totals.items()
        }
        tile_cb_type_maxes = {
            cb_load: math.ceil(total_freq / L)
            for cb_load, total_freq in self.cb_mux_load_freqs.items()
        }

        # Initialize assigments for each tile
        self.tile_sb_load_assignments = [
            defaultdict(lambda: {"num_on": 0, "num_partial": 0, "num_off": 0})
            for i in range(self.gen_r_wire.length)
        ]

        self.tile_cb_load_assignments = [
            defaultdict(lambda: {"num_on": 0, "num_partial": 0, "num_off": 0})
            for i in range(self.gen_r_wire.length)
        ]

        # sb_loads_state_assigned_totals = {
        #     "num_on": 0,
        #     "num_partial": 0,
        #     "num_off": 0
        # }

        # Create assignment totals which will be compared with budget
        sb_loads_type_state_assigned_totals = {
            sb_load: {"num_on": 0, "num_partial": 0, "num_off": 0}
            for sb_load in self.sb_load_budgets.keys()
        }
        cb_loads_type_state_assigned_totals = {
            cb_load: {"num_on": 0, "num_partial": 0, "num_off": 0}
            for cb_load in self.cb_load_budgets.keys()
        }
        # Create assigment totals by sb type
        sb_loads_type_assigned_totals = {
            sb_load: 0
            for sb_load in self.sb_load_budgets.keys()
        }
        cb_loads_type_assigned_totals = {
            cb_load: 0
            for cb_load in self.cb_load_budgets.keys()
        }
        # Total assignment
        # tile_sb_mux_total_assignment = 0

        # Distribute SB Mux Loads across tiles
        for i in range(self.gen_r_wire.length):
            # tile @ index 0 will be driving the terminal SB mux so we account for it before other calculations
            if i == 0:
                self.tile_sb_load_assignments[i][self.terminal_sb_mux]["num_on"] = 1
            # Distribute loads in priority ON -> PARTIAL -> OFF, starting from furthest to closest tile
            for sb_load in self.sb_load_budgets.keys():
                for mux_state in ["num_on", "num_partial", "num_off"]:
                    # If the budget has not been met, and we can still fit more SB muxes of this type in a tile
                    while sb_loads_type_state_assigned_totals[sb_load][mux_state] < self.sb_load_budgets[sb_load][mux_state] and\
                        sum(list(self.tile_sb_load_assignments[i][sb_load].values())) < tile_sb_type_maxes[sb_load]:
                        # Assign ON loads
                        num_assignments = int(float(self.sb_load_budgets[sb_load][mux_state]) / L)
                        # Basically if the int rounded avg number of ON sb muxes is 0 OR the number of ON sb muxes in this assignment would go over budget AND we can still fit one more ON sb mux in the tile, then we set on_assignment to 1
                        if (num_assignments == 0 or \
                            (num_assignments + self.tile_sb_load_assignments[i][sb_load][mux_state] > self.sb_load_budgets[sb_load][mux_state])) and \
                            (1 + self.tile_sb_load_assignments[i][sb_load][mux_state] <= self.sb_load_budgets[sb_load][mux_state]):
                                num_assignments = 1
                        # assign loads
                        self.tile_sb_load_assignments[i][sb_load][mux_state] += num_assignments
                        # update assignment totals
                        sb_loads_type_state_assigned_totals[sb_load][mux_state] += num_assignments
                        sb_loads_type_assigned_totals[sb_load] += num_assignments
                # If there are less total SB Muxes than the tile_sb_max, we assign the remaining muxes based on reaching the desired distribution of each SB mux type
                # while sb_loads_type_state_assigned_totals[sb_load][mux_state] < self.sb_load_budgets[sb_load][mux_state] and\
                #         sum(list(self.tile_sb_load_assignments[i][sb_load].values())) < tile_sb_type_maxes[sb_load]:
                #     # Check current assignments and compare against desired distribution
                #     # cur_dist = (sb_loads_type_assigned_totals[sb_load] / tile_sb_total_budget)
                #     # if cur_dist < sb_mux_load_targ_dist[sb_load]:
                #     # assign loads
                #     self.tile_sb_load_assignments[i][sb_load]["num_off"] += 1
                #     # update assignment totals
                #     sb_loads_type_state_assigned_totals[sb_load]["num_off"] += 1
                #     sb_loads_type_assigned_totals[sb_load] += 1


        # cb_loads_type_assigned_totals = {
        #     cb_load: {"num_on": 0, "num_partial": 0, "num_off": 0}
        #     for cb_load in self.cb_load_budgets.keys()
        # }

        # Distribute CB Mux Loads across tiles
        for i in range(self.gen_r_wire.length):
            # Distribute loads in priority ON -> PARTIAL -> OFF, starting from furthest to closest tile
            for cb_load in self.cb_load_budgets.keys():
                for mux_state in ["num_on", "num_partial", "num_off"]:
                    # If the budget has not been met, and we can still fit more cb muxes of this type in a tile
                    while cb_loads_type_state_assigned_totals[cb_load][mux_state] < self.cb_load_budgets[cb_load][mux_state] and\
                        sum(list(self.tile_cb_load_assignments[i][cb_load].values())) < tile_cb_type_maxes[cb_load]:
                        # Assign ON loads
                        num_assignments = int(float(self.cb_load_budgets[cb_load][mux_state]) / L)
                        # Basically if the int rounded avg number of ON cb muxes is 0 OR the number of ON cb muxes in this assignment would go over budget AND we can still fit one more ON cb mux in the tile, then we set on_assignment to 1
                        if (num_assignments == 0 or \
                            (num_assignments + self.tile_cb_load_assignments[i][cb_load][mux_state] > self.cb_load_budgets[cb_load][mux_state]) or \
                            (num_assignments + sum(list(self.tile_cb_load_assignments[i][cb_load].values())) > tile_cb_type_maxes[cb_load])) and \
                            (1 + self.tile_cb_load_assignments[i][cb_load][mux_state] <= self.cb_load_budgets[cb_load][mux_state]):
                                num_assignments = 1
                        # assign loads
                        self.tile_cb_load_assignments[i][cb_load][mux_state] += num_assignments
                        # update assignment totals
                        cb_loads_type_state_assigned_totals[cb_load][mux_state] += num_assignments
                        cb_loads_type_assigned_totals[cb_load] += num_assignments

        pass
        # # Distribute CB Mux Loads across tiles
        # for i in range(self.gen_r_wire.length):
        #     # Distribute loads in priority ON -> PARTIAL -> OFF, starting from furthest to closest tile
        #     for cb_load in self.cb_load_budgets.keys():
        #         for mux_state in ["num_on", "num_partial", "num_off"]:
        #             # If the budget has not been met
        #             if cb_loads_type_assigned_totals[cb_load][mux_state] < self.cb_load_budgets[cb_load][mux_state]:
        #                 # Assign ON loads
        #                 num_assignments = int(float(self.cb_load_budgets[cb_load][mux_state]) / L)
        #                 # Basically if the int rounded avg number of ON sb muxes is 0 OR the number of ON sb muxes in this assignment would go over budget AND we can still fit one more ON sb mux in the tile, then we set on_assignment to 1
        #                 if (num_assignments == 0 or \
        #                     (num_assignments + self.tile_cb_load_assignments[i][cb_load][mux_state] > self.cb_load_budgets[cb_load][mux_state])) and \
        #                     (1 + self.tile_cb_load_assignments[i][cb_load][mux_state] <= self.cb_load_budgets[cb_load][mux_state]):
        #                         num_assignments = 1
        #                 # assign loads
        #                 self.tile_cb_load_assignments[i][cb_load][mux_state] += num_assignments
        #                 # update assignment totals
        #                 cb_loads_type_assigned_totals[cb_load][mux_state] += num_assignments

                
    def general_routing_load_generate(self, spice_filename: str) -> List[str]:
        """ Generates a routing wire load SPICE deck  """
        

        # First make sure that the terminal_mux driven by this wire load is valid
        # Check the src_wires to see if self.gen_r_wire is in there
        assert any(src_wire == self.gen_r_wire for src_wire in self.terminal_sb_mux.src_wires.keys()), "Terminal SB mux cannot be driven by this wire type!"

        ###############################################################
        ## ROUTING WIRE LOAD
        ###############################################################

        # Get gen routing wire information
        wire_length = self.gen_r_wire.length

        # Set containing all wire params used in this circuit
        wire_param_strs: Set[str] = set()
        wire_routing_load_param_str: str = f"wire_gen_routing_{self.get_param_str()}"

        # wire load sbckt name
        routing_wire_load_subckt_str = f"{self.sp_name}"

        spice_file_lines = []
        # First we write the individual tile loads
        # Tiles are generated such that if you drive a wire from the left you get
        #   driver -> tile 4 -> tile 3 -> tile 2 -> tile 1 (driver) -> tile 4 -> etc.
        for i in range(wire_length):
            spice_file_lines += [
                "******************************************************************************************",
                f"* Routing wire load tile {i+1}",
                "******************************************************************************************",
            ]
            # If this is Tile 1 (LAST TILE IN LOAD), we need to add a nodes to which we can connect the ON sb_mux and cb_mux so that we can measure power.
            if i == 0:
                spice_file_lines += [ f".SUBCKT routing_wire_load_tile_{i+1}_{self.get_param_str()} n_in n_out n_cb_out n_gate n_gate_n n_vdd n_gnd n_vdd_sb_mux_on n_vdd_cb_mux_on" ]
            else:
                spice_file_lines += [ f".SUBCKT routing_wire_load_tile_{i+1}_{self.get_param_str()} n_in n_out n_cb_out n_gate n_gate_n n_vdd n_gnd" ]
            # Wire to first SB Load
            spice_file_lines += [ f"Xwire_gen_routing_1 n_in n_1_1 wire Rw='{wire_routing_load_param_str}_res/{2*wire_length}' Cw='{wire_routing_load_param_str}_cap/{2*wire_length}'\n" ]
            
            # Add the parameter name of routing_wire_load to our wire_param set as we used it in above line
            wire_param_strs.add(wire_routing_load_param_str)

            # SWITCH BLOCK LOAD
            # Write SB Loads in netlist connectivity order of ON -> PARTIAL -> OFF 
            sb_load: sb_mux_lib.SwitchBlockMux
            for mux_state in ["num_on", "num_partial", "num_off"]:
                for sb_load, assignments in self.tile_sb_load_assignments[i].items():
                    # We write this one out at the end of the file so we skip it here
                    # Assumes without this if statement an ON SB mux would be written out
                    if i == 0 and mux_state == "num_on":
                        continue
                    # Iterate over mux states (ON, PARTIAL, OFF)
                    for sb_state_idx in range(assignments[mux_state]):
                        state_str: str = mux_state.replace("num_","")
                        sb_mux_str: str = f"{sb_load.sp_name}_{state_str}"
                        wire_param_str: str = f"wire_sb_load_{state_str}_{self.get_param_str()}"
                        mux_nodes: List[str] = [
                            f"n_1_sb_{state_str}_{sb_state_idx + 1}",
                        ]
                        if "on" in mux_state:
                            mux_nodes.append(
                                f"n_sb_mux_{state_str}_{sb_state_idx + 1}_hang"
                            )
                        mux_nodes += [
                            f"n_gate",
                            f"n_gate_n", 
                            f"n_vdd",
                            f"n_gnd",
                        ]
                        spice_file_lines += [
                            f"Xwire_{sb_mux_str}_{sb_state_idx + 1} n_1_1 n_1_sb_{state_str}_{sb_state_idx + 1} wire Rw={wire_param_str}_res Cw={wire_param_str}_cap",
                            f"X{sb_mux_str}_{sb_state_idx + 1} {' '.join(mux_nodes)} {sb_mux_str}\n"
                        ]
                        wire_param_strs.add(wire_param_str)

            # CONNECTION BLOCK LOAD
            # Write CB Loads in netlist connectivity order of ON -> PARTIAL -> OFF 
            
            # Terminal CB Mux, this is in the tile at the end of the load and would be driving the input to a logic cluster
            # This cb_mux is connected to a different power rail so that we can measure power.
            # TODO update this to accomodate multiple types of connection blocks
            cb_load: cb_mux_lib.ConnectionBlockMux = self.terminal_cb_mux
            wire_cb_load_on_param_str: str = f"wire_cb_load_on_{self.get_param_str()}"
            cb_mux_on_str: str = f"{cb_load.sp_name}_on"
            if i == 0 and self.tile_cb_load_assignments[i][cb_load]["num_on"] > 0:
                spice_file_lines += [ 
                    f"Xwire_{cb_mux_on_str}_{1} n_1_1 n_1_cb_on_{1} wire Rw={wire_cb_load_on_param_str}_res Cw={wire_cb_load_on_param_str}_cap",
                    f"X{cb_mux_on_str}_term n_1_cb_on_{1} n_cb_out n_gate n_gate_n n_vdd_cb_mux_on n_gnd {cb_mux_on_str}\n"
                ]
                wire_param_strs.add(wire_cb_load_on_param_str)
            cb_load: cb_mux_lib.ConnectionBlockMux
            for mux_state in ["num_on", "num_partial", "num_off"]:
                for cb_load, assignments in self.tile_cb_load_assignments[i].items():
                    # Iterate over mux states (ON, PARTIAL, OFF)
                    for cb_state_idx in range(assignments[mux_state]):
                        # If its the non starting tile
                        state_str: str = mux_state.replace("num_","")
                        cb_mux_str: str = f"{cb_load.sp_name}_{state_str}"
                        wire_param_str: str = f"wire_cb_load_{state_str}_{self.get_param_str()}"
                        # We already wrote out Tile 1, so we skip it here
                        if i == 0 and mux_state == "num_on":
                            continue
                        mux_nodes: List[str] = [
                            f"n_1_cb_{state_str}_{sb_state_idx + 1}",
                        ]
                        if "on" in mux_state:
                            mux_nodes.append(
                                f"n_cb_mux_{state_str}_{sb_state_idx + 1}_hang"
                            )
                        mux_nodes += [
                            f"n_gate",
                            f"n_gate_n", 
                            f"n_vdd",
                            f"n_gnd",
                        ]
                        spice_file_lines += [
                            f"Xwire_{cb_mux_str}_{cb_state_idx+1} n_1_1 n_1_cb_{state_str}_{cb_state_idx+1} wire Rw={wire_param_str}_res Cw={wire_param_str}_cap",
                            f"X{cb_mux_str}_{cb_state_idx+1} {' '.join(mux_nodes)} {cb_mux_str}\n" # n_cb_mux_{state_str}_{cb_state_idx+1}_hang
                        ]
                        wire_param_strs.add(wire_param_str)
                        
            
            # Tile 1 is terminated by a on switch block, other tiles just connect the wire to the output
            # Tile 1's sb_mux is connected to a different power rail so that we can measure dynamic power.
            driven_sb_mux_str = f"{self.terminal_sb_mux.sp_name}_on"
            if i == 0:
                spice_file_lines += [
                    f"Xwire_gen_routing_2 n_1_1 n_1_2 wire Rw='{wire_routing_load_param_str}_res/{2*wire_length}' Cw='{wire_routing_load_param_str}_cap/{2*wire_length}'",
                    f"X{driven_sb_mux_str}_term n_1_2 n_out n_gate n_gate_n n_vdd_sb_mux_on n_gnd {driven_sb_mux_str}"
                ]
                # Some of these are not necessary but its good practice to make sure we don't miss any wire params
                wire_param_strs.add(wire_routing_load_param_str)
            else:
                spice_file_lines += [ f"Xwire_gen_routing_2 n_1_1 n_out wire Rw='{wire_routing_load_param_str}_res/{2*wire_length}' Cw='{wire_routing_load_param_str}_cap/{2*wire_length}'" ]
                wire_param_strs.add(wire_routing_load_param_str)

            spice_file_lines += [ ".ENDS\n\n" ]
        
        
        # Now write a subcircuit for the complete routing wire
        spice_file_lines += [
            "******************************************************************************************",
            f"* Routing wire load {str(i+1)}",
            "******************************************************************************************",
            f".SUBCKT {routing_wire_load_subckt_str} n_in n_out n_cb_out n_gate n_gate_n n_vdd n_gnd n_vdd_sb_mux_on n_vdd_cb_mux_on"
        ]
        
        # Iterate through tiles backwards
        in_node = "n_in"
        for tile in range(wire_length, 1, -1):
            out_node = "n_" + str(tile)
            spice_file_lines += [ f"Xrouting_wire_load_tile_{tile}_{self.get_param_str()} {in_node} {out_node} n_hang_{tile} n_gate n_gate_n n_vdd n_gnd routing_wire_load_tile_{tile}_{self.get_param_str()}" ]
            in_node = out_node
        # Write tile 1
        spice_file_lines += [
            f"Xrouting_wire_load_tile_1_{self.get_param_str()} {in_node} n_out n_cb_out n_gate n_gate_n n_vdd n_gnd n_vdd_sb_mux_on n_vdd_cb_mux_on routing_wire_load_tile_1_{self.get_param_str()}",
            ".ENDS\n\n"
        ]
        
        # Write out subckt to spice file
        with open(spice_filename, 'a') as spice_file:
            spice_file.write("\n".join(spice_file_lines))

        
        # Create a list of all wires used in this subcircuit
        wire_names_list = []
        for wire_param_str in wire_param_strs:
            wire_names_list.append(wire_param_str)
        
        return wire_names_list
                

    def generate(self, subcircuit_filename: str, specs: c_ds.Specs):
        """ Compute routing wire load and generate SPICE netlist. """
        print("Generating routing wire load")
        self._compute_load(specs)
        self.wire_names = self.general_routing_load_generate(subcircuit_filename)

    def update_wires(self, width_dict: Dict[str, float], wire_lengths: Dict[str, float], wire_layers: Dict[str, int], num_sb_stripes: int, num_cb_stripes: int, height: float = None):
        """ Calculate wire lengths and wire layers. """

        # Get information from the general routing wire
        wire_length: int = self.gen_r_wire.length
        wire_layer: int = self.gen_r_wire.layer

        # key_str_suffix = f"_wire_uid{wire_id}"
        # Get get keys for wires
        # TODO remove duplication figure out somewhere to define and save these keys
        
        wire_gen_routing_load_key = rg_utils.get_unique_obj(self.wire_names, rg_utils.str_match_condition, "wire_gen_routing")

        # SB mux wire keys
        wire_sb_keys: List[str] = []
        wire_cb_keys: List[str] = []
        for mux_state in ["on", "partial", "off"]:
            for wire in self.wire_names:
                if "wire_sb_load" in wire and mux_state in wire:
                    wire_sb_keys.append(wire)
                elif "wire_cb_load" in wire and mux_state in wire:
                    wire_cb_keys.append(wire)
        # make sure they are unique
        assert len(set(wire_sb_keys)) == len(wire_sb_keys), "SB Wire keys are not unique"
        assert len(set(wire_cb_keys)) == len(wire_cb_keys), "CB Wire keys are not unique"

        # wire_sb_load_on_key = rg_utils.get_unique_obj(self.wire_names, rg_utils.str_match_condition , "wire_sb_load_on")
        # wire_sb_load_partial_key = rg_utils.get_unique_obj(self.wire_names, rg_utils.str_match_condition, "wire_sb_load_partial")
        # wire_sb_load_off_key = rg_utils.get_unique_obj(self.wire_names, rg_utils.str_match_condition, "wire_sb_load_off")

        # wire_cb_load_on_key = rg_utils.get_unique_obj(self.wire_names, rg_utils.str_match_condition, "wire_cb_load_on")
        # wire_cb_load_partial_key = rg_utils.get_unique_obj(self.wire_names, rg_utils.str_match_condition, "wire_cb_load_partial")
        # wire_cb_load_off_key = rg_utils.get_unique_obj(self.wire_names, rg_utils.str_match_condition, "wire_cb_load_off")

        mod_wire_keys: List[str] = [
            wire_gen_routing_load_key, 
            *wire_sb_keys,
            *wire_cb_keys            
        ]
        
        # check if there are any wires left over
        assert set(mod_wire_keys) == set(self.wire_names), "Wire keys do not match wire names"

        # This is the general routing wire that spans L tiles
        wire_lengths[wire_gen_routing_load_key] = wire_length * width_dict["tile"]
        # if lb_height has been initialized
        if height:
            width: float = ((width_dict["tile"] * width_dict["tile"]) / height)
            # If the height is greater than the width of the tile, then the wire length is the height, else width
            # This takes the larger of the two values to get wirelength, worst case?
            if height > width:
                wire_lengths[wire_gen_routing_load_key] = wire_length * height
            else:
                wire_lengths[wire_gen_routing_load_key] = wire_length * width

        # TODO make these assumptions more accurate, we have layout why assume half
        # These are the pieces of wire that are required to connect routing wires to switch 
        # block inputs. We assume that on average, they span half a tile.
        for wire_sb_key in wire_sb_keys:
            wire_lengths[wire_sb_key] = width_dict["tile"] / 2
        if height:
            # This is saying that if we have a single stripe we have to travel the entire width of the LB to get from the routing wire to the SB input (worst case)
            if num_sb_stripes == 1:
                for wire_sb_key in wire_sb_keys:
                    wire_lengths[wire_sb_key] = wire_lengths[wire_gen_routing_load_key] / wire_length
            # I guess this says if there are more than 1 then just estimate by traveling half of the width of the LB
            else:
                for wire_sb_key in wire_sb_keys:
                    wire_lengths[wire_sb_key] = wire_lengths[wire_gen_routing_load_key] / ( 2 * wire_length)
        
        # These are the pieces of wire that are required to connect routing wires to 
        # connection block multiplexer inputs. They span some fraction of a tile that is 
        # given my the input track-access span (track-access locality). 
        for wire_cb_key in wire_cb_keys:
            wire_lengths[wire_cb_key] = width_dict["tile"] * consts.INPUT_TRACK_ACCESS_SPAN
        # Doing something similar to switch blocks, if we have an initialized lb_height & single stripe then use full width of LB as base wire length being multiplied by input track access factor
        if height and num_cb_stripes == 1:
            for wire_cb_key in wire_cb_keys:
                wire_lengths[wire_cb_key] = (wire_lengths[wire_gen_routing_load_key] / wire_length) * consts.INPUT_TRACK_ACCESS_SPAN
        elif height:
            for wire_cb_key in wire_cb_keys:
                wire_lengths[wire_cb_key] = (wire_lengths[wire_gen_routing_load_key] / (2 * wire_length)) * consts.INPUT_TRACK_ACCESS_SPAN
			
       # Update wire layers
        wire_layers[wire_gen_routing_load_key] = wire_layer # used to be 1 -> the first metal layer above local
        for wire_sb_key in wire_sb_keys:
            wire_layers[wire_sb_key] = consts.LOCAL_WIRE_LAYER
        for wire_cb_key in wire_cb_keys:
            wire_layers[wire_cb_key] = consts.LOCAL_WIRE_LAYER

        # wire_layers[wire_sb_load_on_key] = consts.LOCAL_WIRE_LAYER 
        # wire_layers[wire_sb_load_partial_key] = consts.LOCAL_WIRE_LAYER
        # wire_layers[wire_sb_load_off_key] = consts.LOCAL_WIRE_LAYER
        # wire_layers[wire_cb_load_on_key] = consts.LOCAL_WIRE_LAYER
        # wire_layers[wire_cb_load_partial_key] = consts.LOCAL_WIRE_LAYER
        # wire_layers[wire_cb_load_off_key] = consts.LOCAL_WIRE_LAYER
    def print_details(self, report_fpath: str):
        """ Print General Routing Wire Load Details """
        
        utils.print_and_write(report_fpath, "  GEN ROUTING WIRE LOAD DETAILS:")