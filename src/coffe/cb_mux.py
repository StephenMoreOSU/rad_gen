# -*- coding: utf-8 -*-
"""
    Implementations for Connection Block Mux sizeable circuits and thier corresponding testbenches
"""
from __future__ import annotations
from dataclasses import dataclass, field, InitVar
from typing import List, Dict, Any, Tuple, Union, Type
import os, re, sys


import src.coffe.data_structs as c_ds
import src.common.data_structs as rg_ds
import src.common.utils as rg_utils
import src.common.spice_parser as sp_parser

import src.coffe.utils as utils

import src.coffe.mux as mux

import src.coffe.sb_mux as sb_mux_lib
import src.coffe.gen_routing_loads as gen_r_load_lib
import src.coffe.logic_block as lb_lib
import src.coffe.lut as lut_lib
# import src.coffe.fpga as fpga
import src.coffe.constants as consts


@dataclass
class ConnectionBlockMux(mux.Mux2Lvl):
    name: str                                       = "cb_mux"
    # src_wires: Dict[Type[c_ds.Wire], int]       = None
    # sink_wire: c_ds.Wire        = None

    def __post_init__(self):
        super().__post_init__()
        self.sp_name = self.get_sp_name()
        self.delay_weight = consts.DELAY_WEIGHT_CB_MUX

    def __hash__(self):
        return id(self)

    def update_area(self, area_dict: Dict[str, float], width_dict: Dict[str, float]):
        super().update_area(area_dict, width_dict)
        self.update_vpr_areas(area_dict)

    # Only need to deal w/ vpr areas as regular update areas all handled from Mux class
    def update_vpr_areas(self, area_dict: Dict[str, float]):
        # Update VPR area numbers
        if not self.use_tgate :
            area_dict["ipin_mux_trans_size"] = area_dict["ptran_" + self.sp_name + "_L1"]
            area_dict["cb_buf_size"] = area_dict["rest_" + self.sp_name + ""] + area_dict["inv_" + self.sp_name + "_1"] + area_dict["inv_" + self.sp_name + "_2"]
        else :
            area_dict["ipin_mux_trans_size"] = area_dict["tgate_" + self.sp_name + "_L1"]
            area_dict["cb_buf_size"] = area_dict["inv_" + self.sp_name + "_1"] + area_dict["inv_" + self.sp_name + "_2"]  
    
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
            # Set 2nd stage inverter pmos
            elif "inv" in tx_name and "_2_pmos" in tx_name:
                self.initial_transistor_sizes[tx_name] = 12
            # Set 2nd stage inverter nmos
            elif "inv" in tx_name and "_2_nmos" in tx_name:
                self.initial_transistor_sizes[tx_name] = 6
            # Set level restorer if this is a pass transistor mux
            elif "rest" in tx_name:
                self.initial_transistor_sizes[tx_name] = 1

        # Assert that all transistors in this mux have been updated with initial_transistor_sizes
        assert set(list(self.initial_transistor_sizes.keys())) == set(self.transistor_names)
        
        # Will be dict of ints if FinFET or discrete Tx, can be floats if bulk
        return self.initial_transistor_sizes


    def print_details(self, report_fpath: str):
        """ Print switch block details """

        utils.print_and_write(report_fpath, "  CONNECTION BLOCK DETAILS:")
        super().print_details(report_fpath)


@dataclass
class ConnectionBlockMuxTB(c_ds.SimTB):
    # Simulated path is from the output of CB Mux at end of a wire load to input of local mux
    start_sb_mux: sb_mux_lib.SwitchBlockMux = None
    gen_r_wire_load: gen_r_load_lib.RoutingWireLoad = None
    local_r_wire_load: lb_lib.LocalRoutingWireLoad           = None
    lut_input_driver: lut_lib.LUTInputDriver = None

    subckt_lib: InitVar[Dict[str, rg_ds.SpSubCkt]] = None
    
    # Initialized in __post_init__
    dut_ckt: ConnectionBlockMux = None
    def __hash__(self):
        return super().__hash__()
    def __post_init__(self, subckt_lib: Dict[str, rg_ds.SpSubCkt]):
        super().__post_init__()
        self.meas_points = []

        pwr_v_node: str = "vdd_cb_mux"

        # STIM PULSE Voltage SRC
        self.stim_vsrc = c_ds.SpVoltageSrc(
            name = "IN",
            out_node = "n_in",
            type = "PULSE",
            init_volt = c_ds.Value(0),
            peak_volt = c_ds.Value(name = self.supply_v_param), # TODO get this from defined location
            pulse_width = c_ds.Value(2), # ns
            period = c_ds.Value(4), # ns
        )
        # DC Voltage SRC for measuring power
        self.dut_dc_vsrc = c_ds.SpVoltageSrc(
            name = "_CB_MUX",
            out_node = pwr_v_node,
            init_volt = c_ds.Value(name = self.supply_v_param),
        )
        # Initialize the DUT from our inputted wire loads
        self.dut_ckt = self.gen_r_wire_load.terminal_cb_mux

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
                    "n_vdd_sb_mux_on": pwr_v_node,
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
                    "n_vdd_local_mux_on" : self.vdd_node
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
        """
            Generates the SPICE file for the Connection Block Mux Test Bench, returns the path to the file
        """
        dut_sp_name: str = self.dut_ckt.sp_name
        
        # TODO make the naming convension for insts consistent or these will break 
        #   (the "_1" at the end of each is currently how we name the insts from top to bottom)

        # Getting instance paths in this method creates a dependancy on the naming convensions of modules
        #   Yet does not create a dep on actual modules names so its a decent intermediate solution
    
        # Instance path from our TB to the ON Connection Block Mux driver inst
        cb_mux_driver_path: List[rg_ds.SpSubCktInst] = sp_parser.rec_find_inst(
            self.top_insts, 
            [ re.compile(re_str, re.MULTILINE | re.IGNORECASE) 
                for re_str in [
                    r"routing_wire_load(?:.*)_1",
                    r"routing_wire_load_tile_1_(?:.*)", # Makes sure 1 has to be the last char in regex
                    r"cb_mux(?:.*)_on_term",
                    r"cb_mux(?:.*)driver"
                ]
            ],
                # # General fmt of insts is "X{sp_name}_{instantiation_idx}"
                # f"{self.gen_r_wire_load.sp_name}_1"
                # f"routing_wire_load_tile_1_{self.gen_r_wire_load.get_param_str()}", # TODO define this subckt name somewhere
                # f"{self.gen_r_wire_load.terminal_cb_mux.sp_name}_on_out", # TODO rename terminal cb mux
                # f"{self.gen_r_wire_load.terminal_cb_mux.sp_name}_driver", # TODO create consistent convension and define somewhere
            []
        )
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
        # Input of DUT CB mux
        meas_inv_cb_mux_in_node: str = ".".join(
            [inst.name for inst in cb_mux_driver_path[:-1]] + ["n_in"]
        )
        # Output of DUT CB mux inv
        meas_inv_cb_mux_drv_out: str = ".".join(
            [inst.name for inst in cb_mux_driver_path] + ["n_1_1"]
        )
        # Input of Local Mux
        meas_local_mux_in_node: str = ".".join(
            [inst.name for inst in local_mux_path] + ["n_in"]
        )
        delay_names: List[str] = [
            f"inv_{dut_sp_name}_1",
            f"inv_{dut_sp_name}_2",
            f"total",
        ]
        targ_nodes: List[str] = [
            meas_inv_cb_mux_drv_out, 
            meas_local_mux_in_node,
            meas_local_mux_in_node
        ]
        # Base class generate top does all common functionality 
        return super().generate_top(
            delay_names = delay_names,
            trig_node = meas_inv_cb_mux_in_node, 
            targ_nodes = targ_nodes,
            low_v_node = meas_local_mux_in_node,
        )
