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

# @dataclass
# class SwitchBlock(Model):
#     # Model describing FPGA switchblock,
#     #   assumption of each model is that for a particular run, all instances in the list exist in the device
#     name: str                                   # Name of the model, will be used to generate the "base" subckt names of insts, the inst name will be the model name + the inst uid
#                                                 #       Ex. "sb"
#     muxes: List[Mux]                            # List of switch block muxes for each wire length


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
        

        # Compressed format for generating measurement statements for each inverter and tfall / trise combo
        # total trise / tfall is same as the last inverter
        # for i, meas_name in enumerate(delay_names):
        #     for trans_state in ["rise", "fall"]:
        #         # Define variables to determine which nodes to use for trig / targ in the case of rising / falling
        #         trig_trans: bool = trans_state == "rise"
        #         if i == 0:
        #             targ_node: str = meas_inv_sb_mux_1_drv_out_node
        #         else:
        #             targ_node: str = meas_inv_sb_mux_2_in_node

        #         # If we measure total delay we just use the index of the last inverter
        #         delay_idx: int = i + 1 if meas_name != "total" else i
        #         # Rise and fall combo, based on how many inverters in the chain
        #         # If its even we set both to rise or both to fall
        #         if delay_idx % 2 == 0:
        #             rise_fall_combo: Tuple[bool] = (trig_trans, trig_trans)
        #         else:
        #             rise_fall_combo: Tuple[bool] = (not trig_trans, trig_trans)

        #         delay_bounds: Dict[str, c_ds.SpDelayBound] = {
        #             del_str: c_ds.SpDelayBound(
        #                 probe = c_ds.SpNodeProbe(
        #                     node = node,
        #                     type = "voltage",
        #                 ),
        #                 eval_cond = self.delay_eval_cond,
        #                 rise = rise_fall_combo[i],
        #             ) for (i, node), del_str in zip(enumerate([trig_node, targ_node]), ["trig", "targ"])
        #         }
        #         # Create measurement object
        #         measurement: c_ds.SpMeasure = c_ds.SpMeasure(
        #             value = c_ds.Value(
        #                 name = f"{self.meas_val_prefix}_{meas_name}_t{trans_state}",
        #             ),
        #             trig = delay_bounds["trig"],
        #             targ = delay_bounds["targ"],
        #         )
        #         self.meas_points.append(measurement)
        # # Create pwr, current, low_voltage measurements
        # meas_logic_low_voltage_lines: List[str] = [
        #     f".MEASURE TRAN meas_logic_low_voltage FIND V({meas_inv_sb_mux_2_in_node}) AT=7n",
        # ]
        # meas_power_lines: List[str] = [ 
        #     f"* Measure the power required to propagate a rise and a fall transition through the subcircuit at 250MHz",
        #     f".MEASURE TRAN meas_current INTEGRAL I(V_SB_MUX) FROM=0ns TO=4ns",
        #     f".MEASURE TRAN meas_avg_power PARAM = '-(meas_current/4n)*supply_v'",
        # ]

        # # Create the SPICE file
        # top_sp_lines: str = [
        #     f".TITLE Switch Block Mux {self.dut_ckt.sp_name} TB #{self.id} Simulation",
        #     # Library includes
        #     *self.inc_hdr_lines,
        #     *[ lib.get_sp_str() for lib in self.inc_libs],
        #     # Stimulus, Simulation Settings, and Voltage Sources
        #     *self.setup_hdr_lines,
        #     self.mode.get_sp_str(), # Analysis + Simulation Mode
        #     # Options for the simulation
        #     self.get_option_str(),
        #     "*** Input Signal & Power Supply ***",
        #     "* Power rail for the circuit under test.",
        #     "* This allows us to measure power of a circuit under test without measuring the power of wave shaping and load circuitry.",
        #     *[ src.get_sp_str() for src in self.voltage_srcs], # Voltage sources
        #     # Measurements
        #     *self.meas_hdr_lines,
        #     *rg_utils.flatten_mixed_list(
        #         [ meas.get_sp_lines() for meas in self.meas_points]
        #     ),
        #     # Raw Measure statements
        #     *meas_logic_low_voltage_lines,
        #     *meas_power_lines,
        #     # Circuit Inst Definitions
        #     *self.ckt_hdr_lines,
        #     *[ inst.get_sp_str() for inst in self.top_insts],
        #     ".END",
        # ]
        # # Write the SPICE file
        # sp_fpath: str = os.path.join(self.tb_fname, f"{self.tb_fname}.sp")
        # with open(sp_fpath, "w") as f:
        #     f.write("\n".join(top_sp_lines))
        
        # return sp_fpath



@dataclass
class SwitchBlockMuxModel(c_ds.Model):
    # Some way to represent which peripherial circuits are instantiated in the simulation test bench 
    # param_hash: Any     
    # basename: str = None
    ckt_def: SwitchBlockMux = None
    drv_wire: c_ds.GenRoutingWire = None   # Routing wire being driven by this mux

    # Parameters which determine some higher level behaviors
    #    or information about the circuit in the larger FPGA that may be cumbersome to store in circuit definition

@dataclass
class SwitchBlockModel():
    # Way to describe the actual switch block in the device
    #   As the device may have different switch blocks in reality this just represents our estimation of the switch block
    # name: str                                   # Name of the model, will be used to generate the "base" subckt names of insts, the inst name will be the model name + the inst uid
                                                #       Ex. "sb"
    mux_models: List[SwitchBlockMuxModel]       # List of each unique SwitchBlockMux in device
