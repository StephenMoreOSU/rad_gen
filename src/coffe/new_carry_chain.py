from __future__ import annotations
from dataclasses import dataclass, field, InitVar

import math, os, sys
from typing import List, Dict, Any, Tuple, Union, Type

import src.coffe.data_structs as c_ds
import src.coffe.utils as utils

import src.coffe.lut_subcircuits as lut_subcircuits

import src.coffe.mux as mux
import src.coffe.constants as consts

# import src.coffe.new_logic_block as lb_lib
# import src.coffe.new_fpga as fpga

@dataclass
class CarryChainMux(mux.Mux2to1):
    """ Carry Chain Multiplexer class.    """
    name: str = "carry_chain_mux"
    use_finfet: bool = False
    use_fluts: bool = False
    use_tgate: bool = False
    
    # assert use_fluts
    
    def generate(self, subckt_lib_fpath: str) -> Dict[str, int | float]:
        # Call Parent Mux generate, does correct generation but has incorrect initial tx sizes
        self.initial_transistor_sizes = super().generate(subckt_lib_fpath)
        # Set initial transistor sizes to values appropriate for an SB mux
        for tx_name in self.initial_transistor_sizes:
            # Set size of transistors making up switches
            # nmos
            if f"{self.sp_name}_nmos" in tx_name:
                self.initial_transistor_sizes[tx_name] = 2
            # pmos
            elif f"{self.sp_name}_pmos" in tx_name:
                self.initial_transistor_sizes[tx_name] = 2
            # Set 1st stage inverter pmos
            elif "inv" in tx_name and "_1_pmos" in tx_name:
                self.initial_transistor_sizes[tx_name] = 1
            # Set 1st stage inverter nmos
            elif "inv" in tx_name and "_1_nmos" in tx_name:
                self.initial_transistor_sizes[tx_name] = 1
            # Set 2nd stage inverter pmos
            elif "inv" in tx_name and "_2_pmos" in tx_name:
                self.initial_transistor_sizes[tx_name] = 5
            # Set 2nd stage inverter nmos
            elif "inv" in tx_name and "_2_nmos" in tx_name:
                self.initial_transistor_sizes[tx_name] = 5
            # Set level restorer if this is a pass transistor mux
            elif "rest" in tx_name:
                self.initial_transistor_sizes[tx_name] = 1
            
        # Assert that all transistors in this mux have been updated with initial_transistor_sizes
        assert set(list(self.initial_transistor_sizes.keys())) == set(self.transistor_names)
        
        # Will be dict of ints if FinFET or discrete Tx, can be floats if bulk
        return self.initial_transistor_sizes


    def update_wires(self, width_dict: Dict[str, int], wire_lengths: Dict[str, float], wire_layers: Dict[str, int]):
        """ Update the wires of the mux. """
        # Update the wires of the mux
        super().update_wires(width_dict, wire_lengths, wire_layers)
        wire_layers["wire_lut_to_flut_mux"] = consts.LOCAL_WIRE_LAYER

@dataclass
class CarryChainPer(c_ds.SizeableCircuit):
    """ Carry Chain Peripherals class. Used to measure the delay from the Cin to Sout.  """
    name: str = "carry_chain_per"
    
    # Transistor Params
    use_finfet: bool = None
    use_tgate: bool = None

    def generate(self, subcircuit_filename: str) -> Dict[str, int | float]:
        """ Generate the SPICE netlists."""  

        # if type is skip, we need to generate two levels of nand + not for the and tree
        # if type is ripple, we need to add the delay of one inverter for the final sum.
        self.transistor_names, self.wire_names = lut_subcircuits.generate_carry_chain_perf_ripple(subcircuit_filename, self.sp_name, self.use_finfet)
        self.initial_transistor_sizes["inv_" + self.name + "_1_nmos"] = 1
        self.initial_transistor_sizes["inv_" + self.name + "_1_pmos"] = 1

        return self.initial_transistor_sizes


    def update_area(self, area_dict: Dict[str, float], width_dict: Dict[str, float]) -> float:
        """ Calculate Carry Chain area and update dictionaries. """

        area = area_dict["inv_carry_chain_perf_1"]
        area_with_sram = area
        width = math.sqrt(area)
        area_dict[self.name] = area
        width_dict[self.name] = width


    def update_wires(self, width_dict: Dict[str, float], wire_lengths: Dict[str, float], wire_layers: Dict[str, float]) -> List[str]:
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """
        pass

@dataclass
class CarryChain(c_ds.SizeableCircuit):
    """ Carry Chain class.    """
    name: str = "carry_chain"
    
    cluster_size: int = None
    FAs_per_flut: bool = None

    use_finfet: bool = None 

    def generate(self, subcircuit_filename: str) -> Dict[str, int | float]:
        """ Generate Carry chain SPICE netlists."""  

        self.transistor_names, self.wire_names = lut_subcircuits.generate_full_adder_simplified(subcircuit_filename, self.name, self.use_finfet)

        # if type is skip, we need to generate two levels of nand + not for the and tree
        # if type is ripple, we need to add the delay of one inverter for the final sum.

        self.initial_transistor_sizes["inv_carry_chain_1_nmos"] = 1
        self.initial_transistor_sizes["inv_carry_chain_1_pmos"] = 1
        self.initial_transistor_sizes["inv_carry_chain_2_nmos"] = 1
        self.initial_transistor_sizes["inv_carry_chain_2_pmos"] = 1
        self.initial_transistor_sizes["tgate_carry_chain_1_nmos"] = 1
        self.initial_transistor_sizes["tgate_carry_chain_1_pmos"] = 1
        self.initial_transistor_sizes["tgate_carry_chain_2_nmos"] = 1
        self.initial_transistor_sizes["tgate_carry_chain_2_pmos"] = 1

        return self.initial_transistor_sizes

    def update_area(self, area_dict: Dict[str, float], width_dict: Dict[str, float]) -> float:
        """ Calculate Carry Chain area and update dictionaries. """
        area = area_dict["inv_carry_chain_1"] * 2 + area_dict["inv_carry_chain_2"] + area_dict["tgate_carry_chain_1"] * 4 + area_dict["tgate_carry_chain_2"] * 4
        area = area + area_dict["carry_chain_perf"]
        area_with_sram = area
        width = math.sqrt(area)
        area_dict[self.name] = area
        width_dict[self.name] = width

    def update_wires(self, width_dict: Dict[str, float], wire_lengths: Dict[str, float], wire_layers: Dict[str, float]) -> List[str]:
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """
        if self.FAs_per_flut == 2:
            wire_lengths["wire_" + self.name + "_1"] = width_dict["lut_and_drivers"] # Wire for input A
        else:
            wire_lengths["wire_" + self.name + "_1"] = width_dict[self.name] # Wire for input A
        wire_layers["wire_" + self.name + "_1"] = consts.LOCAL_WIRE_LAYER
        wire_lengths["wire_" + self.name + "_2"] = width_dict[self.name] # Wire for input B
        wire_layers["wire_" + self.name + "_2"] = consts.LOCAL_WIRE_LAYER
        if self.FAs_per_flut == 1:
            wire_lengths["wire_" + self.name + "_3"] = width_dict["logic_cluster"]/(2 * self.cluster_size) # Wire for input Cin
        else:
            wire_lengths["wire_" + self.name + "_3"] = width_dict["logic_cluster"]/(4 * self.cluster_size) # Wire for input Cin
        wire_layers["wire_" + self.name + "_3"] = consts.LOCAL_WIRE_LAYER
        if self.FAs_per_flut == 1:
            wire_lengths["wire_" + self.name + "_4"] = width_dict["logic_cluster"]/(2 * self.cluster_size) # Wire for output Cout
        else:
            wire_lengths["wire_" + self.name + "_4"] = width_dict["logic_cluster"]/(4 * self.cluster_size) # Wire for output Cout
        wire_layers["wire_" + self.name + "_4"] = consts.LOCAL_WIRE_LAYER
        wire_lengths["wire_" + self.name + "_5"] = width_dict[self.name] # Wire for output Sum
        wire_layers["wire_" + self.name + "_5"] = consts.LOCAL_WIRE_LAYER

    def print_details(self):
        print(" Carry Chain DETAILS:")

@dataclass
class CarryChainSkipAnd(c_ds.SizeableCircuit):
    """ Part of peripherals used in carry chain class.    """
    name: str = "xcarry_chain_and"

    use_finfet: bool = None
    use_tgate: bool = None
    
    carry_chain_type: str = None
    skip_size: int = None

    FAs_per_flut: int = None
    cluster_size: int = None
    nand1_size: int = None
    nand2_size: int = None


    def __post_init__(self):
        super().__post_init__()
        
        self.nand1_size = 2
        self.nand2_size = 2

        assert self.carry_chain_type == "skip"
        # this size is currently a limit due to how the and tree is being generated
        assert self.skip_size >= 4 and self.skip_size <= 9

        if self.skip_size == 6:
            self.nand2_size = 3
        elif self.skip_size == 5:
            self.nand1_size = 3
        elif self.skip_size > 6:
            self.nand1_size = 3
            self.nand2_size = 3


    def generate(self, subcircuit_filename: str) -> Dict[str, int | float]:
        """ Generate Carry chain SPICE netlists."""  

        self.transistor_names, self.wire_names = lut_subcircuits.generate_skip_and_tree(subcircuit_filename, self.name, self.use_finfet, self.nand1_size, self.nand2_size)

        self.initial_transistor_sizes["inv_nand"+str(self.nand1_size)+"_xcarry_chain_and_1_nmos"] = 1
        self.initial_transistor_sizes["inv_nand"+str(self.nand1_size)+"_xcarry_chain_and_1_pmos"] = 1
        self.initial_transistor_sizes["inv_xcarry_chain_and_2_nmos"] = 1
        self.initial_transistor_sizes["inv_xcarry_chain_and_2_pmos"] = 1
        self.initial_transistor_sizes["inv_nand"+str(self.nand2_size)+"_xcarry_chain_and_3_nmos"] = 1
        self.initial_transistor_sizes["inv_nand"+str(self.nand2_size)+"_xcarry_chain_and_3_pmos"] = 1
        self.initial_transistor_sizes["inv_xcarry_chain_and_4_nmos"] = 1
        self.initial_transistor_sizes["inv_xcarry_chain_and_4_pmos"] = 1

        return self.initial_transistor_sizes

    def update_area(self, area_dict, width_dict):
        """ Calculate Carry Chain area and update dictionaries. """
        area_1 = (area_dict["inv_nand"+str(self.nand1_size)+"_xcarry_chain_and_1"] + area_dict["inv_xcarry_chain_and_2"])* int(math.ceil(float(int(self.skip_size/self.nand1_size))))
        area_2 = area_dict["inv_nand"+str(self.nand2_size)+"_xcarry_chain_and_3"] + area_dict["inv_xcarry_chain_and_4"]
        area = area_1 + area_2
        area_with_sram = area
        width = math.sqrt(area)
        area_dict[self.name] = area
        width_dict[self.name] = width

    def update_wires(self, width_dict, wire_lengths, wire_layers):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """
        if self.FAs_per_flut == 2:
            wire_lengths["wire_" + self.name + "_1"] = (width_dict["ble"]*self.skip_size)/4.0
        else:
            wire_lengths["wire_" + self.name + "_1"] = (width_dict["ble"]*self.skip_size)/2.0
        wire_layers["wire_" + self.name + "_1"] = consts.LOCAL_WIRE_LAYER
        wire_lengths["wire_" + self.name + "_2"] = width_dict[self.name]/2.0
        wire_layers["wire_" + self.name + "_2"] = consts.LOCAL_WIRE_LAYER

    def print_details(self):
        print(" Carry Chain DETAILS:")

@dataclass
class CarryChainInterCluster(c_ds.SizeableCircuit):
    """ Wire dirvers of carry chain path between clusters"""

    name: str = "carry_chain_inter"

    use_finfet: bool = None
    carry_chain_type: str = None # Ripple or skip?
    inter_wire_length: float = None # Length of wire between Cout of a cluster and Cin of the next cluster

    def generate(self, subcircuit_filename: str) -> Dict[str, int | float]:
        """ Generate Carry chain SPICE netlists."""  

        self.transistor_names, self.wire_names = lut_subcircuits.generate_carry_inter(subcircuit_filename, self.name, self.use_finfet)

        self.initial_transistor_sizes["inv_" + self.name + "_1_nmos"] = 1
        self.initial_transistor_sizes["inv_" + self.name + "_1_pmos"] = 1
        self.initial_transistor_sizes["inv_" + self.name + "_2_nmos"] = 2
        self.initial_transistor_sizes["inv_" + self.name + "_2_pmos"] = 2

        return self.initial_transistor_sizes

    def update_area(self, area_dict, width_dict):
        """ Calculate Carry Chain area and update dictionaries. """
        area = area_dict["inv_" + self.name + "_1"] + area_dict["inv_" + self.name + "_2"]
        area_with_sram = area
        width = math.sqrt(area)
        area_dict[self.name] = area
        width_dict[self.name] = width

    def update_wires(self, width_dict, wire_lengths, wire_layers):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """

        wire_lengths["wire_" + self.name + "_1"] = width_dict["tile"] * self.inter_wire_length
        wire_layers["wire_" + self.name + "_1"] = consts.LOCAL_WIRE_LAYER

    def print_details(self):
        pass

@dataclass
class CarryChainSkipMux(mux.Mux2to1):
    """ Part of peripherals used in carry chain class.    """
    name: str = "xcarry_chain_mux"
    use_finfet: bool = None
    use_tgate: bool = None

    carry_chain_type: str = None # Ripple or skip?

    def update_wires(self, width_dict: Dict[str, int], wire_lengths: Dict[str, float], wire_layers: Dict[str, int]):
        """ Update the wires of the mux. """
        # Update the wires of the mux
        super().update_wires(width_dict, wire_lengths, wire_layers)
        wire_layers["wire_lut_to_flut_mux"] = consts.LOCAL_WIRE_LAYER

