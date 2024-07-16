# -*- coding: utf-8 -*-
"""
    This module contains implementations for logic cluster circuits, loads and testbenches.
"""

from __future__ import annotations
from dataclasses import dataclass, field, InitVar

import math, os, sys
import re

from typing import List, Dict, Any, Tuple, Union, Type
import src.common.spice_parser as sp_parser
import src.coffe.data_structs as c_ds
import src.common.utils as rg_utils
import src.common.data_structs as rg_ds
import src.coffe.utils as utils
import src.coffe.mux as mux

import src.coffe.sb_mux as sb_mux_lib
import src.coffe.gen_routing_loads as gen_r_load_lib
import src.coffe.ble as ble_lib
import src.coffe.lut as lut_lib

import src.coffe.carry_chain as cc_lib
import src.coffe.constants as consts

@dataclass
class LocalMux(mux.Mux2Lvl):
    name: str                                       = "local_mux"

    def __post_init__(self):
        super().__post_init__()
        self.delay_weight = consts.DELAY_WEIGHT_LOCAL_MUX

    def __hash__(self):
        return id(self)

    def generate(self, subckt_lib_fpath: str) -> Dict[str, int | float]:
        # Call Parent Mux generate, does correct generation but has incorrect initial tx sizes
        self.initial_transistor_sizes = super().generate(subckt_lib_fpath)
        # Set initial transistor sizes to values appropriate for an CB mux
        for tx_name in self.initial_transistor_sizes:
            # Set size of Level 1 transistors
            if "L1" in tx_name:
                self.initial_transistor_sizes[tx_name] = 2
            # Set size of Level 2 transistors
            elif "L2" in tx_name:
                self.initial_transistor_sizes[tx_name] = 2
            # Set 1st stage inverter pmos
            elif "inv" in tx_name and "_1_pmos" in tx_name:
                self.initial_transistor_sizes[tx_name] = 2
            # Set 1st stage inverter nmos
            elif "inv" in tx_name and "_1_nmos" in tx_name:
                self.initial_transistor_sizes[tx_name] = 2
            # Set level restorer if this is a pass transistor mux
            elif "rest" in tx_name:
                self.initial_transistor_sizes[tx_name] = 1

        # Assert that all transistors in this mux have been updated with initial_transistor_sizes
        assert set(list(self.initial_transistor_sizes.keys())) == set(self.transistor_names)
        
        # Will be dict of ints if FinFET or discrete Tx, can be floats if bulk
        return self.initial_transistor_sizes
    
    def update_wires(self, width_dict: Dict[str, float], wire_lengths: Dict[str, float], wire_layers: Dict[str, int], ratio: float):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """
        super().update_wires(width_dict, wire_lengths, wire_layers, ratio)
        # Update wire lengths
        # wire_lengths["wire_" + self.sp_name + "_L1"] = width_dict[self.sp_name] * ratio
        # wire_lengths["wire_" + self.sp_name + "_L2"] = width_dict[self.sp_name] * ratio
        # # Update wire layers
        # wire_layers["wire_" + self.sp_name + "_L1"] = consts.LOCAL_WIRE_LAYER
        # wire_layers["wire_" + self.sp_name + "_L2"] = consts.LOCAL_WIRE_LAYER

    def print_details(self, report_fpath: str):
        """ Print switch block details """

        utils.print_and_write(report_fpath, "  LOCAL MUX DETAILS:")
        super().print_details(report_fpath)


@dataclass
class LocalMuxTB(c_ds.SimTB):
    """
    The Local Mux testbench
    """

    # Simulated path is from the output of CB Mux at end of a wire load to input of local mux
    start_sb_mux: sb_mux_lib.SwitchBlockMux = None
    gen_r_wire_load: gen_r_load_lib.RoutingWireLoad = None
    local_r_wire_load: LocalRoutingWireLoad = None
    lut_input_driver: lut_lib.LUTInputDriver = None

    subckt_lib: InitVar[Dict[str, rg_ds.SpSubCkt]] = None
    
    # Initialized in __post_init__
    dut_ckt: LocalMux = None
    def __hash__(self):
        return super().__hash__()    

    def __post_init__(self, subckt_lib: Dict[str, rg_ds.SpSubCkt]):
        super().__post_init__()
        self.meas_points = []
        pwr_v_node: str = "vdd_local_mux"

        # Define the standard voltage sources for the simulation
        # STIM PULSE Voltage SRC
        self.stim_vsrc: c_ds.SpVoltageSrc = c_ds.SpVoltageSrc(
                name = "IN",
                out_node = "n_in",
                type = "PULSE",
                init_volt = c_ds.Value(0),
                peak_volt = c_ds.Value(name = self.supply_v_param), # TODO get this from defined location
                pulse_width = c_ds.Value(2), # ns
                period = c_ds.Value(4), # ns
        )
        # DUT DC Voltage Source
        self.dut_dc_vsrc: c_ds.SpVoltageSrc = c_ds.SpVoltageSrc(
            name = "_LOCAL_MUX",
            out_node = pwr_v_node,
            init_volt = c_ds.Value(name = self.supply_v_param),
        )
            
        # Initialize the DUT from our inputted wire loads
        self.dut_ckt = self.local_r_wire_load.local_mux
        self.top_insts = [
            # Mux taking STIM input and driving the source routing wire load
            rg_ds.SpSubCktInst(
                name = f"X{self.start_sb_mux.sp_name}_on_1",
                subckt = subckt_lib[f"{self.start_sb_mux.sp_name}_on"],
                conns = { 
                    "n_in": "n_in",
                    "n_out": "n_1_1",
                    "n_gate": self.sram_vdd_node,
                    "n_gate_n": self.sram_vss_node,
                    "n_vdd": self.vdd_node,
                    "n_gnd": self.gnd_node
                }
            ),
            # Routing Wire Load, driven by start mux and terminates with CB mux driving logic cluster
            # Power VDD attached to the terminal CB mux as this is our DUT
            rg_ds.SpSubCktInst(
                name = f"X{self.gen_r_wire_load.sp_name}_1",
                subckt = subckt_lib[self.gen_r_wire_load.sp_name],
                conns = {
                    "n_in": "n_1_1",
                    "n_out": "n_hang_1",
                    "n_cb_out": "n_1_2",
                    "n_gate": self.sram_vdd_node,
                    "n_gate_n": self.sram_vss_node,
                    "n_vdd": self.vdd_node,
                    "n_gnd": self.gnd_node,
                    "n_vdd_sb_mux_on": self.vdd_node,
                    "n_vdd_cb_mux_on": self.vdd_node
                }
            ),
            # Local Routing Wire Load, driven by general routing wire load and terminates with LUT input driver
            rg_ds.SpSubCktInst(
                name = f"X{self.local_r_wire_load.sp_name}_1",
                subckt = subckt_lib[self.local_r_wire_load.sp_name],
                conns = {
                    "n_in" : "n_1_2",
                    "n_out" : "n_1_3",
                    "n_gate" : self.sram_vdd_node,
                    "n_gate_n" : self.sram_vss_node,
                    "n_vdd" : self.vdd_node,
                    "n_gnd" : self.gnd_node,
                    "n_vdd_local_mux_on" : pwr_v_node,
                }
            ),
            # LUT Input Driver
            rg_ds.SpSubCktInst(
                name = f"X{self.lut_input_driver.name}_1",
                subckt = subckt_lib[self.lut_input_driver.sp_name],
                conns = {
                    "n_in": "n_1_3",
                    "n_out": "n_hang_2",
                    "n_gate": self.sram_vdd_node,
                    "n_gate_n": self.sram_vss_node,
                    "n_rsel": "n_hang_3",
                    "n_not_input": "n_hang_4",
                    "n_vdd": self.vdd_node,
                    "n_gnd": self.gnd_node,
                }
            ),   
        ]

    def generate_top(self) -> str:
        dut_sp_name: str = self.dut_ckt.sp_name

        # Instance path from our TB to the ON Local Mux inst
        local_mux_path: List[rg_ds.SpSubCktInst] = sp_parser.rec_find_inst(
            self.top_insts, 
            [ re.compile(re_str, re.MULTILINE | re.IGNORECASE) 
                for re_str in [
                    r"local_routing_wire_load(?:.*)_1",
                    r"local_mux(?:.*)_on", # TODO update the naming convension of terminal local mux
                ]
            ],
            []
        )

        delay_names = [
            f"inv_{dut_sp_name}_1",
            "total",
        ]
        trig_node: str = ".".join(
            [inst.name for inst in local_mux_path] + ["n_in"]
        )
        targ_nodes: List[str] = [
            "n_1_3",
            "n_1_3",
        ]
        # Base class generate top does all common functionality 
        return super().generate_top(
            delay_names = delay_names,
            trig_node = trig_node, 
            targ_nodes = targ_nodes,
            low_v_node = "n_1_1",
        )


@dataclass
class LocalRoutingWireLoad(c_ds.LoadCircuit):
    """
        Local routing wire load
    """
    name: str = "local_routing_wire_load"
    lut_input_usage_assumption: float = None        # How many LUT inputs are we assuming are used in this logic cluster? (%)
    
    # Input to _compute_load
    local_mux: LocalMux = None      # The localMux instantiated this load + used for compute_load
    
    # Set in _compute_load
    mux_inputs_per_wire: int = None     # Total number of local mux inputs per wire
    on_inputs_per_wire: int = None      # Number of on inputs connected to each wire 
    partial_inputs_per_wire: int = None # Number of partially on inputs connected to each wire
    off_inputs_per_wire: int = None     # Number of off inputs connected to each wire

    def __post_init__(self):
        super().__post_init__()

    def local_routing_load_generate(self, spice_filename: str) -> List[str]:
        """ """

        subckt_local_mux: str = self.local_mux.sp_name

        num_on: int = self.on_inputs_per_wire
        num_partial: int = self.partial_inputs_per_wire
        num_off: int = self.off_inputs_per_wire

        # The first thing we want to figure out is the interval between each on load and each partially on load
        # Number of partially on muxes between each on mux
        interval_partial = int(num_partial/num_on)
        # Number of off muxes between each partially on mux
        interval_off = int(num_off/num_partial)

        # Open SPICE file for appending
        spice_file = open(spice_filename, 'a')
        
        spice_file.write("******************************************************************************************\n")
        spice_file.write("* Local routing wire load\n")
        spice_file.write("******************************************************************************************\n")
        spice_file.write(f".SUBCKT {self.sp_name} n_in n_out n_gate n_gate_n n_vdd n_gnd n_vdd_local_mux_on\n")
        
        num_total = int(num_on + num_partial + num_off)
        interval_counter_partial = 0
        interval_counter_off = 0
        on_counter = 0
        partial_counter = 0
        off_counter = 0
        
        # Initialize nodes
        current_node = "n_in"
        next_node = "n_1"
        
        # Wire defintions
        wire_local_routing: str = f"wire_local_routing_{self.get_param_str()}"

        # Write SPICE file while keeping correct intervals between partial and on muxes
        for i in range(num_total):
            if interval_counter_partial == interval_partial and on_counter < num_on:
                    # Add an on mux
                    interval_counter_partial = 0
                    on_counter = on_counter + 1
                    if on_counter == num_on:
                        spice_file.write(f"X{wire_local_routing}_" + str(i+1) + " " + current_node + " " + next_node + f" wire Rw='{wire_local_routing}_res/" + str(num_total) + f"' Cw='{wire_local_routing}_cap/" + str(num_total) + "'\n")
                        spice_file.write(f"X{subckt_local_mux}_on_" + str(on_counter) + " " + next_node + f" n_out n_gate n_gate_n n_vdd_local_mux_on n_gnd {subckt_local_mux}_on\n")
                    else:
                        spice_file.write(f"X{wire_local_routing}_" + str(i+1) + " " + current_node + " " + next_node + f" wire Rw='{wire_local_routing}_res/" + str(num_total) + f"' Cw='{wire_local_routing}_cap/" + str(num_total) + "'\n")
                        spice_file.write(f"X{subckt_local_mux}_on_" + str(on_counter) + " " + next_node + " n_hang_" + str(on_counter) + f" n_gate n_gate_n n_vdd n_gnd {subckt_local_mux}_on\n")    
            else:
                if interval_counter_off == interval_off and partial_counter < num_partial:
                    # Add a partially on mux
                    interval_counter_off = 0
                    interval_counter_partial = interval_counter_partial + 1
                    partial_counter = partial_counter + 1
                    spice_file.write(f"X{wire_local_routing}_" + str(i+1) + " " + current_node + " " + next_node + f" wire Rw='{wire_local_routing}_res/" + str(num_total) + f"' Cw='{wire_local_routing}_cap/" + str(num_total) + "'\n")
                    spice_file.write(f"X{subckt_local_mux}_partial_" + str(partial_counter) + " " + next_node + f" n_gate n_gate_n n_vdd n_gnd {subckt_local_mux}_partial\n")
                else:
                    # Add an off mux
                    interval_counter_off = interval_counter_off + 1
                    off_counter = off_counter + 1
                    spice_file.write(f"X{wire_local_routing}_" + str(i+1) + " " + current_node + " " + next_node + f" wire Rw='{wire_local_routing}_res/" + str(num_total) + f"' Cw='{wire_local_routing}_cap/" + str(num_total) + "'\n")
                    spice_file.write(f"X{subckt_local_mux}_off_" + str(off_counter) + " " + next_node + f" n_gate n_gate_n n_vdd n_gnd {subckt_local_mux}_off\n")
            # Update current and next nodes        
            current_node = next_node
            next_node = "n_" + str(i+2)
        spice_file.write(".ENDS\n\n\n")

        spice_file.close()
    
    
        # Create a list of all wires used in this subcircuit
        wire_names_list = []
        wire_names_list.append(wire_local_routing)
        
        return wire_names_list

    def generate(self, subcircuit_filename: str, specs: c_ds.Specs):
        print("Generating local routing wire load")
        # Compute load (number of on/partial/off per wire)
        self._compute_load(specs)
        # Generate SPICE deck
        self.wire_names = self.local_routing_load_generate(subcircuit_filename)


    def _compute_load(self, specs: c_ds.Specs):
        """ Compute the load on a local routing wire (number of on/partial/off) """
        # preconditions for this function
        assert self.lut_input_usage_assumption is not None, "lut_input_usage_assumption must be set before computing load"

        # The first thing we are going to compute is how many local mux inputs are connected to a local routing wire
        # This is a function of local_mux size, N, K, I and Ofb
        num_local_routing_wires = specs.I + specs.N * specs.num_ble_local_outputs
        self.mux_inputs_per_wire = self.local_mux.implemented_size * specs.N * specs.K / num_local_routing_wires
        
        # Now we compute how many "on" inputs are connected to each routing wire
        # This is a funtion of lut input usage, number of lut inputs and number of local routing wires
        num_local_muxes_used = self.lut_input_usage_assumption * specs.N * specs.K
        self.on_inputs_per_wire = int(num_local_muxes_used / num_local_routing_wires)
        # We want to model for the case where at least one "on" input is connected to the local wire, so make sure it's at least 1
        if self.on_inputs_per_wire < 1:
            self.on_inputs_per_wire = 1
        
        # Now we compute how many partially on muxes are connected to each wire
        # The number of partially on muxes is equal to (level2_size - 1)*num_local_muxes_used/num_local_routing_wire
        # We can figure out the number of muxes used by using the "on" assumption and the number of local routing wires.
        self.partial_inputs_per_wire = int((self.local_mux.level2_size - 1.0) * num_local_muxes_used / num_local_routing_wires)
        # Make it at least 1
        if self.partial_inputs_per_wire < 1:
            self.partial_inputs_per_wire = 1
        
        # Number of off inputs is simply the difference
        self.off_inputs_per_wire = self.mux_inputs_per_wire - self.on_inputs_per_wire - self.partial_inputs_per_wire


    def update_wires(self, width_dict: Dict[str, float], wire_lengths: Dict[str, float], wire_layers: Dict[str, int], local_routing_wire_load_length: float = None):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """
        
        # TODO get wire keys from self.wire_names, assert that we update all keys in self.wire_names
        wire_loc_routing: str = rg_utils.get_unique_obj(
            self.wire_names,
            rg_utils.str_match_condition,
            "wire_local_routing",
        )
        # Update wire lengths
        wire_lengths[wire_loc_routing] = width_dict["logic_cluster"]
        if local_routing_wire_load_length:
            wire_lengths[wire_loc_routing] = local_routing_wire_load_length
        # Update wire layers
        wire_layers[wire_loc_routing] = consts.LOCAL_WIRE_LAYER


@dataclass
class LocalBLEOutputLoad(c_ds.LoadCircuit):
    name: str = "local_ble_output_load"

    # Child Subckts
    local_routing_wire_load: LocalRoutingWireLoad = None
    lut_input_driver: lut_lib.LUTInputDriver = None

    def __post_init__(self):
        super().__post_init__()

    def generate_local_ble_output_load(self, spice_filename: str) -> List[str]:
        # Open SPICE file for appending
        spice_file = open(spice_filename, 'a')
        
        wire_loc_ble_out_fb = f"wire_local_ble_output_feedback_{self.get_param_str()}"

        spice_file.write("******************************************************************************************\n")
        spice_file.write("* Local BLE output load\n")
        spice_file.write("******************************************************************************************\n")
        spice_file.write(f".SUBCKT {self.sp_name} n_in n_gate n_gate_n n_vdd n_gnd\n")
        spice_file.write(f"X{wire_loc_ble_out_fb} n_in n_1_1 wire Rw='{wire_loc_ble_out_fb}_res' Cw='{wire_loc_ble_out_fb}_cap'\n")
        spice_file.write(f"X{self.local_routing_wire_load.sp_name}_1 n_1_1 n_1_2 n_gate n_gate_n n_vdd n_gnd n_vdd {self.local_routing_wire_load.sp_name}\n")
        spice_file.write(f"X{self.lut_input_driver.sp_name}_1 n_1_2 n_hang1 vsram vsram_n n_hang2 n_hang3 n_vdd n_gnd {self.lut_input_driver.sp_name}\n\n")
        spice_file.write(".ENDS\n\n\n")
        
        spice_file.close()
        
        # Create a list of all wires used in this subcircuit
        wire_names_list = []
        wire_names_list.append(wire_loc_ble_out_fb)
        
        return wire_names_list

    def generate(self, subcircuit_filename):
        self.wire_names = self.generate_local_ble_output_load(subcircuit_filename)
    
    
    def update_wires(self, width_dict: Dict[str, float], wire_lengths: Dict[str, float], wire_layers: Dict[str, int], ble_ic_dis: float = None):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """
        
        # Update wire lengths
        wire_loc_ble_out_fb: str = rg_utils.get_unique_obj(
            self.wire_names,
            rg_utils.str_match_condition,
            "wire_local_ble_output_feedback",
        )
        
        wire_lengths[wire_loc_ble_out_fb] = width_dict["logic_cluster"]
        if ble_ic_dis:
            wire_lengths[wire_loc_ble_out_fb] = ble_ic_dis
        # Update wire layers
        wire_layers[wire_loc_ble_out_fb] = consts.LOCAL_WIRE_LAYER


@dataclass
class LogicCluster(c_ds.CompoundCircuit):
    """
        Logic Cluster
    """
    name: str = "logic_cluster"

    # General FPGA Parameters relevant to the logic cluster
    num_lc_inputs: int = None # Number of total inputs to the logic cluster (I)
    cluster_size: int = None # cluster size (N)
    
    # General Circuit Params
    use_tgate: bool = None
    use_finfet: bool = None
    use_fluts: bool = None
    
    # Local Mux specific params
    local_mux_size_required: int = None
    num_local_mux_per_tile: int = None
    
    # BLE specific Params   
    enable_carry_chain: bool = None     # Enable carry chain in BLEs
    FAs_per_flut: int = None            # Hard Adders per fracturable LUT
    carry_skip_periphery_count: int = None # TODO figure out 
    
    num_inputs_per_ble: int = None # Number of inputs per BLE in cluster (K)
    num_fb_outputs_per_ble: int = None #Number of outputs per BLE that feed back to local muxes (Ofb)
    num_gen_outputs_per_ble: int = None # Number of general outputs sent to SBs per BLE (Or)
    Rsel: str = None # Rsel value for the BLEs in this logic cluster
    Rfb: str = None # Rfb value for the BLEs in this logic cluster


    # SizeableCircuits (created in __post_init__) in rough order of input -> outputs
    local_mux: LocalMux = None # Local Mux
    local_routing_wire_load: LocalRoutingWireLoad = None # Local Routing Wire Load
    ble: ble_lib.BLE = None # BLE sizeable circuit
    local_ble_output_load: LocalBLEOutputLoad = None # Output load of BLE load circuit
    
    # Carry Chain
    cc_mux: cc_lib.CarryChainMux = None
    cc: cc_lib.CarryChain = None
    cc_skip_and: cc_lib.CarryChainSkipAnd = None
    cc_skip_mux: cc_lib.CarryChainSkipMux = None

    def __post_init__(self):
        # Create Local Mux
        self.local_mux = LocalMux(
            id = 0,
            num_per_tile = self.num_local_mux_per_tile,
            required_size = self.local_mux_size_required,
            use_driver = False,
            use_tgate = self.use_tgate,
        )
        # Create BLE
        self.ble = ble_lib.BLE(
            id = 0,
            cluster_size = self.cluster_size,
            # Per BLE Params
            num_lut_inputs = self.num_inputs_per_ble,
            num_local_outputs = self.num_fb_outputs_per_ble,
            num_general_outputs = self.num_gen_outputs_per_ble,
            Rsel = self.Rsel,
            Rfb = self.Rfb,
            enable_carry_chain = self.enable_carry_chain,
            FAs_per_flut = self.FAs_per_flut,
            carry_skip_periphery_count = self.carry_skip_periphery_count,
            # Circuit Dependancies
            cc = self.cc,
            cc_mux = self.cc_mux,
            cc_skip_and = self.cc_skip_and,
            cc_skip_mux = self.cc_skip_mux,
            local_mux = self.local_mux,
            # Transistor Parameters
            use_tgate = self.use_tgate,
            use_finfet = self.use_finfet,
            use_fluts = self.use_fluts,
        )
        # Create Local Routing Wire Load (load on a single wire going into local muxes)
        self.local_routing_wire_load = LocalRoutingWireLoad(
            id = 0,
            lut_input_usage_assumption = consts.LUT_INPUT_USAGE_ASSUMPTION,
            local_mux = self.local_mux,
        )
        self.local_ble_output_load = LocalBLEOutputLoad(
            id = 0,
            local_routing_wire_load = self.local_routing_wire_load,
            lut_input_driver = self.ble.lut.input_drivers["a"].driver, # Pass in the LUT input driver for "a" input
        )
        # OLD BLE
        # self.ble = _BLE(
        #     K, Or, Ofb, Rsel, Rfb, use_tgate, use_finfet, use_fluts, enable_carry_chain,
        #     FAs_per_flut, carry_skip_periphery_count, N,
        #     gen_r_wire,
        #     self.local_ble_output_load,
        #     self.gen_ble_output_load
        # )

    def update_area(self, area_dict: Dict[str, float], width_dict: Dict[str, float]):
        self.ble.update_area(area_dict, width_dict)
        self.local_mux.update_area(area_dict, width_dict) 

    def update_wires(self, width_dict: Dict[str, float], wire_lengths: Dict[str, float], wire_layers: Dict[str, int], ic_ratio: float, lut_ratio: float, ble_ic_dis: float = None, local_routing_wire_load_length: float = None):
        """ Update wires of things inside the logic cluster. """
        
        # Call wire update functions of member objects.
        self.ble.update_wires(width_dict, wire_lengths, wire_layers, lut_ratio)
        self.local_mux.update_wires(width_dict, wire_lengths, wire_layers, ic_ratio)
        self.local_routing_wire_load.update_wires(width_dict, wire_lengths, wire_layers, local_routing_wire_load_length)
        self.local_ble_output_load.update_wires(width_dict, wire_lengths, wire_layers, ble_ic_dis)

    def generate(self, subcircuits_filename: str, min_tran_width, specs: c_ds.Specs) -> Dict[str, int | float]:
        print("Generating logic cluster")
        init_tran_sizes = {}
        init_tran_sizes.update(
            self.ble.generate(subcircuits_filename, min_tran_width)
        )
        init_tran_sizes.update(
            self.local_mux.generate(subcircuits_filename)
        )
        # Don't pass these into init_tran sizes as they are only load circuits
        self.local_routing_wire_load.generate(subcircuits_filename, specs)
        self.local_ble_output_load.generate(subcircuits_filename)
        
        return init_tran_sizes


    def print_details(self, report_file):
        self.local_mux.print_details(report_file)
        self.ble.print_details(report_file)

