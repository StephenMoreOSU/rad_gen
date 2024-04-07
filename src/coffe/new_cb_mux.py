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

import src.coffe.new_sb_mux as sb_mux_lib
import src.coffe.new_gen_routing_loads as gen_r_load_lib
import src.coffe.new_logic_block as lb_lib
import src.coffe.new_lut as lut_lib
# import src.coffe.new_fpga as fpga
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


    def print_details(self, report_file):
        """ Print connection block details """

        utils.print_and_write(report_file, "  CONNECTION BLOCK DETAILS:")
        utils.print_and_write(report_file, "  Style: two-level MUX")
        utils.print_and_write(report_file, "  Required MUX size: " + str(self.required_size) + ":1")
        utils.print_and_write(report_file, "  Implemented MUX size: " + str(self.implemented_size) + ":1")
        utils.print_and_write(report_file, "  Level 1 size = " + str(self.level1_size))
        utils.print_and_write(report_file, "  Level 2 size = " + str(self.level2_size))
        utils.print_and_write(report_file, "  Number of unused inputs = " + str(self.num_unused_inputs))
        utils.print_and_write(report_file, "  Number of MUXes per tile: " + str(self.num_per_tile))
        utils.print_and_write(report_file, "  Number of SRAM cells per MUX: " + str(self.sram_per_mux))
        utils.print_and_write(report_file, "")


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

    def __post_init__(self, subckt_lib: Dict[str, rg_ds.SpSubCkt]):
        super().__post_init__()
        self.meas_points = []

        pwr_v_node: str = "vdd_cb_mux"
        # Define the standard voltage sources for the simulation
        self.voltage_srcs = [
            # STIM PULSE Voltage SRC
            c_ds.SpVoltageSrc(
                name = "IN",
                out_node = "n_in",
                type = "PULSE",
                init_volt = c_ds.Value(0),
                peak_volt = c_ds.Value(name = self.supply_v_param), # TODO get this from defined location
                pulse_width = c_ds.Value(2), # ns
                period = c_ds.Value(4), # ns
            ),
            # DC Voltage SRC for measuring power
            c_ds.SpVoltageSrc(
                name = "_CB_MUX",
                out_node = pwr_v_node,
                init_volt = c_ds.Value(name = self.supply_v_param),
            )
        ]
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
        # Create directory for this sim
        if not os.path.exists(dut_sp_name):
            os.makedirs(dut_sp_name)
        
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
                    r"routing_wire_load_tile(?:.*)_1",
                    r"Xcb_load(?:.*)_on",
                    r"cb_mux(?:.*)driver",
                ]
                # # General fmt of insts is "X{sp_name}_{instantiation_idx}"
                # f"{self.gen_r_wire_load.sp_name}_1"
                # f"routing_wire_load_tile_1_{self.gen_r_wire_load.get_param_str()}", # TODO define this subckt name somewhere
                # f"{self.gen_r_wire_load.terminal_cb_mux.sp_name}_on_out", # TODO rename terminal cb mux
                # f"{self.gen_r_wire_load.terminal_cb_mux.sp_name}_driver", # TODO create consistent convension and define somewhere
            ],
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
        inv_names = [
            f"inv_{dut_sp_name}_1",
            f"inv_{dut_sp_name}_2"
        ]        

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

        # Compressed format for generating measurement statements for each inverter and tfall / trise combo
        # total trise / tfall is same as the last inverter
        for i, meas_name in enumerate(inv_names + ["total"]):
            for trans_state in ["rise", "fall"]:
                # Define variables to determine which nodes to use for trig / targ in the case of rising / falling
                trig_trans: bool = trans_state == "rise"
                if i == 0:
                    targ_node: str = meas_inv_cb_mux_drv_out
                else:
                    targ_node: str = meas_local_mux_in_node
                # Create measurement object
                measurement: c_ds.SpMeasure = c_ds.SpMeasure(
                    value = c_ds.Value(
                        name = f"{self.meas_val_prefix}_{meas_name}_t{trans_state}",
                    ),
                    trig = c_ds.SpDelayBound(
                        probe = c_ds.SpNodeProbe(
                            node = meas_inv_cb_mux_in_node,
                            type = "voltage",
                        ),
                        eval_cond = self.delay_eval_cond,
                        rise = trig_trans,
                    ),
                    targ = c_ds.SpDelayBound(
                        probe = c_ds.SpNodeProbe(
                            node = targ_node,
                            type = "voltage",
                        ),
                        eval_cond = self.delay_eval_cond,
                        rise = not trig_trans,
                    )
                )
                self.meas_points.append(measurement)
        pwr_meas_lines: List[str] = [
            f".MEASURE TRAN meas_logic_low_voltage FIND V({meas_local_mux_in_node}) AT=3n",
            f"* Measure the power required to propagate a rise and a fall transition through the subcircuit at 250MHz",
            f".MEASURE TRAN meas_current INTEGRAL I(V_CB_MUX) FROM=0ns TO=4ns",
            f".MEASURE TRAN meas_avg_power PARAM = '-(meas_current/4n)*supply_v'",
        ]

        # Create the spice file
        top_sp_lines: List[str] = [
            f".TITLE Connection Block Mux Test Bench",
            # Library includes
            *self.inc_hdr_lines,
            *[ lib.get_sp_str() for lib in self.inc_libs],
            # Stimulus, Simulation Settings, and Voltage Sources
            *self.setup_hdr_lines,
            self.mode.get_sp_str(), # Analysis + Simulation Mode
            # Options for the simulation
            self.get_option_str(),
            "*** Input Signal & Power Supply ***",
            "* Power rail for the circuit under test.",
            "* This allows us to measure power of a circuit under test without measuring the power of wave shaping and load circuitry.",
            *[ src.get_sp_str() for src in self.voltage_srcs], # Voltage sources
            # Measurements
            *self.meas_hdr_lines,
            *rg_utils.flatten_mixed_list(
                [ meas.get_sp_lines() for meas in self.meas_points]
            ),
            # Raw Measure statements
            *pwr_meas_lines,
            # Circuit Inst Definitions
            *self.ckt_hdr_lines,
            *[ inst.get_sp_str() for inst in self.top_insts],
            ".END",
        ]
        # Write the SPICE file
        sp_fpath: str = os.path.join(dut_sp_name, f"{dut_sp_name}.sp")
        with open(sp_fpath, "w") as f:
            f.write("\n".join(top_sp_lines))
        
        return sp_fpath