# -*- coding: utf-8 -*-
"""
    Implementations for Switch Block Mux sizeable circuit and thier corresponding testbenches
"""
from __future__ import annotations
from dataclasses import dataclass, field, InitVar
from typing import List, Dict, Any, Tuple, Union, Type
import os, sys
import re


import src.coffe.data_structs as c_ds
import src.common.data_structs as rg_ds
import src.common.utils as rg_utils
import src.common.spice_parser as sp_parser
import src.coffe.utils as utils
import src.coffe.mux as mux
import src.coffe.gen_routing_loads as gen_r_load_lib
import src.coffe.constants as consts


@dataclass
class SwitchBlockMux(mux.Mux2Lvl):
    name: str                                       = "sb_mux" # Basename of the Spice subckt, identifies the circuit type itself
    sp_name: str                                = None # Name of the SPICE subckt, Ex. sb_mux_uid_0
    # This info is not required to create the circuit definition
    src_wires: Dict[Type[c_ds.Wire], int]                         = None # Dict of source wires and the number of mux inputs they occupy
    sink_wire: c_ds.GenRoutingWire                  = None # The sink wire for this mux

    # subckt_defs: SpSubCkt                         # Subcircuit definition for the mux, could also get this from parsing a SpSubCktLib of all components or defining here
    def __post_init__(self):
        # If we derive our mux parameters from the source wires, we can calculate the mux size
        if self.src_wires is not None and self.required_size is None:
            self.required_size = sum(self.src_wires.values())
        # Infer num_per_tile if its not already set
        if self.num_per_tile is None and self.sink_wire is not None:
            self.num_per_tile = self.sink_wire.num_starting_per_tile

        super().__post_init__()
        self.sp_name = self.get_sp_name()
        self.delay_weight = consts.DELAY_WEIGHT_SB_MUX

    def __hash__(self):
        return id(self)

    def generate(self, subckt_lib_fpath: str) -> Dict[str, int | float]:
        # Call Parent Mux generate, does correct generation but has incorrect initial tx sizes
        self.initial_transistor_sizes = super().generate(subckt_lib_fpath)
        # Set initial transistor sizes to values appropriate for an SB mux
        for tx_name in self.initial_transistor_sizes:
            # Set size of Level 1 transistors
            if "L1" in tx_name:
                self.initial_transistor_sizes[tx_name] = 3
            # Set size of Level 2 transistors
            elif "L2" in tx_name:
                self.initial_transistor_sizes[tx_name] = 4
            # Set 1st stage inverter pmos
            elif "inv" in tx_name and "_1_pmos" in tx_name:
                self.initial_transistor_sizes[tx_name] = 8
            # Set 1st stage inverter nmos
            elif "inv" in tx_name and "_1_nmos" in tx_name:
                self.initial_transistor_sizes[tx_name] = 4
            # Set 2nd stage inverter pmos
            elif "inv" in tx_name and "_2_pmos" in tx_name:
                self.initial_transistor_sizes[tx_name] = 20
            # Set 2nd stage inverter nmos
            elif "inv" in tx_name and "_2_nmos" in tx_name:
                self.initial_transistor_sizes[tx_name] = 10
            # Set level restorer if this is a pass transistor mux
            elif "rest" in tx_name:
                self.initial_transistor_sizes[tx_name] = 1
            
        # Assert that all transistors in this mux have been updated with initial_transistor_sizes
        assert set(list(self.initial_transistor_sizes.keys())) == set(self.transistor_names)
        
        # Will be dict of ints if FinFET or discrete Tx, can be floats if bulk
        return self.initial_transistor_sizes

    # Only need to deal w/ vpr areas as regular update areas all handled from Mux class
    def update_vpr_areas(self, area_dict: Dict[str, float]):
        # Update VPR areas
        if not self.use_tgate :
            area_dict[f"switch_mux_trans_size_{self.sink_wire.type}"] = area_dict["ptran_" + self.sp_name + "_L1"]
            area_dict[f"switch_buf_size_{self.sink_wire.type}"] = area_dict["rest_" + self.sp_name + ""] + area_dict["inv_" + self.sp_name + "_1"] + area_dict["inv_" + self.sp_name + "_2"]
        else :
            area_dict[f"switch_mux_trans_size_{self.sink_wire.type}"] = area_dict["tgate_" + self.sp_name + "_L1"]
            area_dict[f"switch_buf_size_{self.sink_wire.type}"] = area_dict["inv_" + self.sp_name + "_1"] + area_dict["inv_" + self.sp_name + "_2"]
    
    def update_area(self, area_dict: Dict[str, float], width_dict: Dict[str, float]):
        super().update_area(area_dict, width_dict)
        self.update_vpr_areas(area_dict)

    def print_details(self, report_fpath: str):
        """ Print switch block details """

        utils.print_and_write(report_fpath, "  SWITCH BLOCK DETAILS:")
        super().print_details(report_fpath)
    

@dataclass
class SwitchBlockMuxTB(c_ds.SimTB):
    # In here we need to list all the peripherial circuits required to be simulated 
    # These are used as hashes for top_insts field 
    start_sb_mux: SwitchBlockMux = None                             # This SB drives the src_routing_wire_load
    src_routing_wire_load: gen_r_load_lib.RoutingWireLoad = None    # This is a wire load ending in SB mux driving sink routing wire load
    sink_routing_wire_load: gen_r_load_lib.RoutingWireLoad = None

    subckt_lib: InitVar[Dict[str, rg_ds.SpSubCkt]] = None
    # Initialized in __post_init__
    dut_ckt: SwitchBlockMux = None
    def __hash__(self):
        return super().__hash__()
    def __post_init__(self, subckt_lib: Dict[str, rg_ds.SpSubCkt]):
        super().__post_init__()
        self.meas_points = []
        pwr_v_node = "vdd_sb_mux"
        # Define the standard voltage sources for the simulation
        self.stim_vsrc = c_ds.SpVoltageSrc(
            name = "IN",
            out_node = "n_in",
            type = "PULSE",
            init_volt = c_ds.Value(0),
            peak_volt = c_ds.Value(name = self.supply_v_param), # TODO get this from defined location
            pulse_width = c_ds.Value(2), # ns
            period = c_ds.Value(8), # ns
        )
        # DC Voltage SRC for measuring power
        self.dut_dc_vsrc = c_ds.SpVoltageSrc(
            name = "_SB_MUX",
            out_node = pwr_v_node,
            init_volt = c_ds.Value(name = self.supply_v_param),
        )
        # Initialize the DUT from our inputted wire loads
        self.dut_ckt = self.src_routing_wire_load.terminal_sb_mux
        # Initialize the top level instances from subckt_lib 

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
            # Source Routing Wire Load, driven by start mux and driving sink routing wire load
            # Power VDD attached to the terminal SB mux as this is our DUT
            rg_ds.SpSubCktInst(
                name = f"X{self.src_routing_wire_load.sp_name}_1",
                subckt = subckt_lib[self.src_routing_wire_load.sp_name],
                conns = {
                    "n_in": "n_1_1",
                    "n_out": "n_2_1",
                    "n_cb_out": "n_hang_2",
                    "n_gate": self.sram_vdd_node,
                    "n_gate_n": self.sram_vss_node,
                    "n_vdd": self.vdd_node,
                    "n_gnd": self.gnd_node,
                    "n_vdd_sb_mux_on": pwr_v_node,
                    "n_vdd_cb_mux_on": self.vdd_node
                }
            ),
            # Sink Routing Wire Load, driven by source routing wire load the main wire load in our delay path
            rg_ds.SpSubCktInst(
                name = f"X{self.sink_routing_wire_load.sp_name}_2",
                subckt = subckt_lib[self.sink_routing_wire_load.sp_name],
                conns = {
                    "n_in": "n_2_1",
                    "n_out": "n_3_1",
                    "n_cb_out": "n_hang_1",
                    "n_gate": self.sram_vdd_node,
                    "n_gate_n": self.sram_vss_node,
                    "n_vdd": self.vdd_node,
                    "n_gnd": self.gnd_node,
                    "n_vdd_sb_mux_on": self.vdd_node,
                    "n_vdd_cb_mux_on": self.vdd_node
                }
            )
        ]
    def generate_top(self) -> str:
        """
            Generates the SPICE file for the Switch Block Mux Test Bench, returns the path to the file
        """
        # TODO define at better place
        # meas_val_prefix: str = "meas"

        # Get list of insts which makes up the hier path from the TB to the terminal SB mux driver in the routing wire load
        # TODO make the naming convension for insts consistent or these will break 
        #   (the "_1" at the end of each is currently how we name the insts from top to bottom)
        meas_src_r_load_sb_mux_path: List[rg_ds.SpSubCktInst] = sp_parser.rec_find_inst(
            self.top_insts, 
            [ re.compile(re_str, re.MULTILINE | re.IGNORECASE) 
                for re_str in [
                    r"routing_wire_load(?:.*)_1",
                    r"routing_wire_load_tile_1_(?:.*)", # Makes sure 1 has to be the last char in regex
                    r"sb_mux(?:.*)_on_term",
                    r"sb_mux(?:.*)driver"
                ]
            ],
            []
        )
        meas_sink_r_load_sb_mux_path: List[rg_ds.SpSubCktInst] = sp_parser.rec_find_inst(
            self.top_insts, 
            [ re.compile(re_str, re.MULTILINE | re.IGNORECASE) 
                for re_str in [
                    r"routing_wire_load(?:.*)_2",
                    r"routing_wire_load_tile_1_(?:.*)",
                    r"sb_mux(?:.*)_on_term"
                ]
            ],
            []
        )

        # Get parameterized inst names from above function and manually add the nodes we want to measure from at the end
        meas_inv_sb_mux_1_in_node: str = ".".join(
            [inst.name for inst in meas_src_r_load_sb_mux_path[:-1]] + ["n_in"]
        )
        meas_inv_sb_mux_1_drv_out_node: str = ".".join(
            [inst.name for inst in meas_src_r_load_sb_mux_path] + ["n_1_1"]
        )
        meas_inv_sb_mux_2_in_node: str = ".".join(
            [inst.name for inst in meas_sink_r_load_sb_mux_path] + ["n_in"]
        )
        delay_names: List[str] = [
            f"inv_{self.dut_ckt.sp_name}_1",
            f"inv_{self.dut_ckt.sp_name}_2",
            f"total",
        ]
        targ_nodes: List[str] = [
            meas_inv_sb_mux_1_drv_out_node, 
            meas_inv_sb_mux_2_in_node, 
            meas_inv_sb_mux_2_in_node
        ]
        # Base class generate top does all common functionality 
        return super().generate_top(
            delay_names = delay_names,
            trig_node = meas_inv_sb_mux_1_in_node, 
            targ_nodes = targ_nodes,
            low_v_node = meas_inv_sb_mux_2_in_node,
        )
        
