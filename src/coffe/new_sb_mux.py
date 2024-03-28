from __future__ import annotations
from dataclasses import dataclass, field

from typing import List, Dict, Any, Tuple, Union, Type

import src.coffe.data_structs as c_ds
import src.coffe.utils as utils

import src.coffe.mux as mux


import src.coffe.new_fpga as fpga

# @dataclass
# class SwitchBlock(Model):
#     # Model describing FPGA switchblock,
#     #   assumption of each model is that for a particular run, all instances in the list exist in the device
#     name: str                                   # Name of the model, will be used to generate the "base" subckt names of insts, the inst name will be the model name + the inst uid
#                                                 #       Ex. "sb"
#     muxes: List[Mux]                            # List of switch block muxes for each wire length


@dataclass
class SwitchBlockMux(mux.Mux):
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
        self.delay_weight = fpga.DELAY_WEIGHT_SB_MUX

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
            area_dict["switch_mux_trans_size"] = area_dict["ptran_" + self.sp_name + "_L1"]
            area_dict["switch_buf_size"] = area_dict["rest_" + self.sp_name + ""] + area_dict["inv_" + self.sp_name + "_1"] + area_dict["inv_" + self.sp_name + "_2"]
        else :
            area_dict["switch_mux_trans_size"] = area_dict["tgate_" + self.sp_name + "_L1"]
            area_dict["switch_buf_size"] = area_dict["inv_" + self.sp_name + "_1"] + area_dict["inv_" + self.sp_name + "_2"]
    
    def print_details(self, report_fpath: str):
        """ Print switch block details """

        utils.print_and_write(report_fpath, "  SWITCH BLOCK DETAILS:")
        utils.print_and_write(report_fpath, "  Style: two-level MUX")
        utils.print_and_write(report_fpath, "  Required MUX size: " + str(self.required_size) + ":1")
        utils.print_and_write(report_fpath, "  Implemented MUX size: " + str(self.implemented_size) + ":1")
        utils.print_and_write(report_fpath, "  Level 1 size = " + str(self.level1_size))
        utils.print_and_write(report_fpath, "  Level 2 size = " + str(self.level2_size))
        utils.print_and_write(report_fpath, "  Number of unused inputs = " + str(self.num_unused_inputs))
        utils.print_and_write(report_fpath, "  Number of MUXes per tile: " + str(self.num_per_tile))
        utils.print_and_write(report_fpath, "  Number of SRAM cells per MUX: " + str(self.sram_per_mux))
        utils.print_and_write(report_fpath, "")
    

# @dataclass
# class SwitchBlockMuxTB(c_ds.SimTB):
#     # In here we need to list all the peripherial circuits required to be simulated 



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
