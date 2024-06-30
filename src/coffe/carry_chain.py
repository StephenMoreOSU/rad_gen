from __future__ import annotations
from dataclasses import dataclass, field, InitVar

import math, os, sys
import re
from typing import List, Dict, Any, Tuple, Union, Type

import src.common.data_structs as rg_ds
import src.common.utils as rg_utils
import src.coffe.data_structs as c_ds
import src.common.spice_parser as sp_parser
import src.coffe.utils as utils

import src.coffe.lut_subcircuits as lut_subcircuits

import src.coffe.mux as mux
import src.coffe.constants as consts

import src.coffe.new_lut as lut_lib
import src.coffe.new_ble as ble_lib
import src.coffe.new_gen_routing_loads as gen_r_loads_lib
# import src.coffe.new_logic_block as lb_lib
# import src.coffe.new_fpga as fpga

@dataclass
class CarryChainMux(mux.Mux2to1):
    """ Carry Chain Multiplexer class.    """
    name: str = "carry_chain_mux"
    use_finfet: bool = False
    use_fluts: bool = False
    use_tgate: bool = False
    
    def __hash__(self) -> int:
        return super().__hash__()

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
        # TODO update for multi ckt support
        wire_layers["wire_lut_to_flut_mux"] = consts.LOCAL_WIRE_LAYER

@dataclass
class CarryChainMuxTB(c_ds.SimTB):
    FA_carry_chain: CarryChain = None
    carry_chain_periph: CarryChainPer = None
    carry_chain_mux: CarryChainMux = None
    lut_output_load: ble_lib.LUTOutputLoad = None
    gen_ble_output_load: gen_r_loads_lib.GeneralBLEOutputLoad = None
    
    subckt_lib: InitVar[Dict[str, rg_ds.SpSubCkt]] = None
    # Initialized in __post_init__
    dut_ckt: CarryChainMux = None

    def __hash__(self) -> int:
        return super().__hash__()
    
    def __post_init__(self, subckt_lib):
        super().__post_init__()
        self.meas_points = []
        pwr_v_node: str = "vdd_cc_mux"
        self.local_out_node: str = "n_local_out"
        self.general_out_node: str = "n_general_out"
        self.dut_ckt = self.carry_chain_mux
        # STIM PULSE Voltage SRC
        self.stim_vsrc = c_ds.SpVoltageSrc(
            name = "IN",
            out_node = "n_in",
            type = "PULSE",
            init_volt = c_ds.Value(name = self.supply_v_param),
            peak_volt = c_ds.Value(0), # V
            pulse_width = c_ds.Value(2), # ns
            period = c_ds.Value(4), # ns
        )
        # DUT DC Voltage Source
        self.dut_dc_vsrc = c_ds.SpVoltageSrc(
            name = "_CC",
            out_node = pwr_v_node,
            init_volt = c_ds.Value(name = self.supply_v_param),
        )
        # Top insts
        self.top_insts = [
            # Wave Shaping Circuitry
            rg_ds.SpSubCktInst(
                name = f"X{self.FA_carry_chain.sp_name}_shape_1",  # TODO update to sp_name
                subckt = subckt_lib[self.FA_carry_chain.sp_name], # TODO update to sp_name
                conns = {
                    "n_a": self.vdd_node,
                    "n_b": self.gnd_node,
                    "n_cin": "n_in",
                    "n_cout":"n_1_1",
                    "n_sum_out": "n_hang",
                    "n_p": "n_p_1",
                    "n_vdd": self.vdd_node,
                    "n_gnd": self.gnd_node,
                }
            ),
            rg_ds.SpSubCktInst(
                name = f"X{self.FA_carry_chain.sp_name}_shape_2",  # TODO update to sp_name
                subckt = subckt_lib[self.FA_carry_chain.sp_name], # TODO update to sp_name
                conns = {
                    "n_a": self.vdd_node,
                    "n_b": self.gnd_node,
                    "n_cin": "n_1_1",
                    "n_cout":"n_1_2",
                    "n_sum_out": "n_hang_2",
                    "n_p": "n_p_2",
                    "n_vdd": self.vdd_node,
                    "n_gnd": self.gnd_node,
                }
            ),
            rg_ds.SpSubCktInst(
                name = f"X{self.FA_carry_chain.sp_name}_shape_3",  # TODO update to sp_name
                subckt = subckt_lib[self.FA_carry_chain.sp_name], # TODO update to sp_name
                conns = {
                    "n_a": self.vdd_node,
                    "n_b": self.gnd_node,
                    "n_cin": "n_1_2",
                    "n_cout":"n_hang_3",
                    "n_sum_out": "n_1_3",
                    "n_p": "n_p_3",
                    "n_vdd": self.vdd_node,
                    "n_gnd": self.gnd_node,
                }
            ),
            # Carry Chain Per (inverter) 
            rg_ds.SpSubCktInst(
                name = f"X{self.carry_chain_periph.sp_name}",  
                subckt = subckt_lib[self.carry_chain_periph.sp_name], 
                conns = {
                    "n_in": "n_1_3",
                    "n_out": "n_1_4",
                    "n_vdd": self.vdd_node,
                    "n_gnd": self.gnd_node,
                }
            ),
            # Carry Chain MUX DUT
            rg_ds.SpSubCktInst(
                name = f"X{self.carry_chain_mux.sp_name}_dut", 
                subckt = subckt_lib[self.carry_chain_mux.sp_name], 
                conns = {
                    "n_in": "n_1_4",
                    "n_out": "n_1_5",
                    "n_gate": self.vdd_node,
                    "n_gate_n": self.gnd_node,
                    "n_vdd": pwr_v_node,
                    "n_gnd": self.gnd_node,
                }
            ),
            # LUT Output Load
            rg_ds.SpSubCktInst(
                name = f"X{self.lut_output_load.sp_name}", 
                subckt = subckt_lib[self.lut_output_load.sp_name], 
                conns = {
                    "n_in": "n_1_5",
                    "n_local_out": self.local_out_node,
                    "n_general_out": self.general_out_node,
                    "n_gate": self.sram_vdd_node,
                    "n_gate_n": self.sram_vss_node,
                    "n_vdd": self.vdd_node,
                    "n_gnd": self.gnd_node,
                    "n_vdd_local_output_on": pwr_v_node,
                    "n_vdd_general_output_on": self.vdd_node,
                }
            ),
            # GENERAL BLE OUTPUT LOAD
            rg_ds.SpSubCktInst(
                name = f"X{self.gen_ble_output_load.sp_name}",
                subckt = subckt_lib[self.gen_ble_output_load.sp_name],
                conns = {
                    "n_1_1": self.general_out_node,
                    "n_out": "n_hang_1",
                    "n_gate": self.sram_vdd_node,
                    "n_gate_n": self.sram_vss_node,
                    "n_vdd": self.vdd_node,
                    "n_gnd": self.gnd_node,
                }
            ), 
        ]
    def generate_top(self):
        # dut_sp_name: str = self.dut_ckt.sp_name # TODO update to sp_name
        trig_node: str = "n_1_4"
        delay_names: List[str] = [
            f"inv_{self.dut_ckt.sp_name}_1",
            f"inv_{self.dut_ckt.sp_name}_2",
            f"total",
        ]
        # Instance path from our TB to the ON Local Mux inst
        cc_dut_path: List[rg_ds.SpSubCktInst] = sp_parser.rec_find_inst(
            self.top_insts, 
            [ re.compile(re_str, re.MULTILINE | re.IGNORECASE) 
                for re_str in [
                    r"carry_chain_mux(?:.*_dut)",
                ]
            ],
            []
        )
        targ_nodes: List[str] = [
            ".".join([inst.name for inst in cc_dut_path] + ["n_2_1"]),
            self.local_out_node,
            self.local_out_node,
        ]
        # Base class generate top does all common functionality 
        return super().generate_top(
            delay_names = delay_names,
            trig_node = trig_node, 
            targ_nodes = targ_nodes,
            low_v_node = self.general_out_node, # TODO figure out why tf we are measuring the low value of gnd...
        )




@dataclass
class CarryChainPer(c_ds.SizeableCircuit):
    """ Carry Chain Peripherals class. Used to measure the delay from the Cin to Sout.  """
    name: str = "carry_chain_per"
    
    # Transistor Params
    use_finfet: bool = None
    use_tgate: bool = None

    def __hash__(self) -> int:
        return super().__hash__()

    def generate(self, subcircuit_filename: str) -> Dict[str, int | float]:
        """ Generate the SPICE netlists."""  

        # if type is skip, we need to generate two levels of nand + not for the and tree
        # if type is ripple, we need to add the delay of one inverter for the final sum.
        self.transistor_names, self.wire_names = lut_subcircuits.generate_carry_chain_perf_ripple(subcircuit_filename, self.sp_name, self.use_finfet)
        self.initial_transistor_sizes["inv_" + self.sp_name + "_1_nmos"] = 1
        self.initial_transistor_sizes["inv_" + self.sp_name + "_1_pmos"] = 1

        return self.initial_transistor_sizes


    def update_area(self, area_dict: Dict[str, float], width_dict: Dict[str, float]) -> float:
        """ Calculate Carry Chain area and update dictionaries. """

        # Find the name of inv carry chain peripheral 
        # TODO have this be less hard coded (corresponds to generate ) 
        area: float = area_dict[f"inv_{self.sp_name}_1"]
        area_with_sram: float = area
        width: float = math.sqrt(area)
        area_dict[self.sp_name] = area
        width_dict[self.sp_name] = width


    def update_wires(self, width_dict: Dict[str, float], wire_lengths: Dict[str, float], wire_layers: Dict[str, float]) -> List[str]:
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """
        pass

@dataclass
class CarryChainPerTB(c_ds.SimTB):
    FA_carry_chain: CarryChain = None
    carry_chain_periph: CarryChainPer = None
    carry_chain_mux: CarryChainMux = None
    
    subckt_lib: InitVar[Dict[str, rg_ds.SpSubCkt]] = None
    # Initialized in __post_init__
    dut_ckt: CarryChain = None

    def __hash__(self) -> int:
        return super().__hash__()

    def __post_init__(self, subckt_lib):
        super().__post_init__()
        self.meas_points = []
        pwr_v_node: str = "vdd_cc_mux"
        self.local_out_node: str = "n_local_out"
        self.general_out_node: str = "n_general_out"

        self.dut_ckt = self.carry_chain_periph
        # STIM PULSE Voltage SRC
        self.stim_vsrc = c_ds.SpVoltageSrc(
            name = "IN",
            out_node = "n_in",
            type = "PULSE",
            init_volt = c_ds.Value(0),
            peak_volt = c_ds.Value(name = self.supply_v_param), # V
            pulse_width = c_ds.Value(2), # ns
            period = c_ds.Value(4), # ns
        )
        # DUT DC Voltage Source
        self.dut_dc_vsrc = c_ds.SpVoltageSrc(
            name = "_CC",
            out_node = pwr_v_node,
            init_volt = c_ds.Value(name = self.supply_v_param),
        )
        # Top insts
        self.top_insts = [
            # Wave Shaping Circuitry
            rg_ds.SpSubCktInst(
                name = f"X{self.FA_carry_chain.sp_name}_shape_1",  
                subckt = subckt_lib[self.FA_carry_chain.sp_name], 
                conns = {
                    "n_a": self.vdd_node,
                    "n_b": self.gnd_node,
                    "n_cin": "n_in",
                    "n_cout":"n_1_1",
                    "n_sum_out": "n_hang",
                    "n_p": "n_p_1",
                    "n_vdd": self.vdd_node,
                    "n_gnd": self.gnd_node,
                }
            ),
            rg_ds.SpSubCktInst(
                name = f"X{self.FA_carry_chain.sp_name}_shape_2",  
                subckt = subckt_lib[self.FA_carry_chain.sp_name], 
                conns = {
                    "n_a": self.vdd_node,
                    "n_b": self.gnd_node,
                    "n_cin": "n_1_1",
                    "n_cout":"n_1_2",
                    "n_sum_out": "n_hang_2",
                    "n_p": "n_p_2",
                    "n_vdd": self.vdd_node,
                    "n_gnd": self.gnd_node,
                }
            ),
            rg_ds.SpSubCktInst(
                name = f"X{self.FA_carry_chain.sp_name}_shape_3",  
                subckt = subckt_lib[self.FA_carry_chain.sp_name], 
                conns = {
                    "n_a": self.vdd_node,
                    "n_b": self.gnd_node,
                    "n_cin": "n_1_2",
                    "n_cout":"n_hang_3",
                    "n_sum_out": "n_1_3",
                    "n_p": "n_p_3",
                    "n_vdd": self.vdd_node,
                    "n_gnd": self.gnd_node,
                }
            ),
            # Carry Chain Per (inverter) DUT
            rg_ds.SpSubCktInst(
                name = f"X{self.carry_chain_periph.sp_name}_dut",  
                subckt = subckt_lib[self.carry_chain_periph.sp_name], 
                conns = {
                    "n_in": "n_1_3",
                    "n_out": "n_out",
                    "n_vdd": pwr_v_node,
                    "n_gnd": self.gnd_node,
                }
            ),
            # Carry Chain MUX DUT
            rg_ds.SpSubCktInst(
                name = f"X{self.carry_chain_mux.sp_name}", 
                subckt = subckt_lib[self.carry_chain_mux.sp_name], 
                conns = {
                    "n_in": "n_out",
                    "n_out": "n_out_2",
                    "n_gate": self.vdd_node,
                    "n_gate_n": self.gnd_node,
                    "n_vdd": pwr_v_node,
                    "n_gnd": self.gnd_node,
                }
            )
        ]
    def generate_top(self) -> str:
        dut_sp_name: str = self.dut_ckt.sp_name
        trig_node: str = "n_1_2"
        delay_names: List[str] = [
            f"inv_{dut_sp_name}_1",
            f"total",
        ]
        targ_nodes: List[str] = [
            "n_out",
            "n_out",
        ]
        meas_inv_list: List[bool] = [False] * len(delay_names)
        # Base class generate top does all common functionality 
        return super().generate_top(
            delay_names = delay_names,
            trig_node = trig_node, 
            targ_nodes = targ_nodes,
            low_v_node = self.gnd_node, # TODO figure out why tf we are measuring the low value of gnd...
            meas_inv_list = meas_inv_list,
        )





@dataclass
class CarryChain(c_ds.SizeableCircuit):
    """ Carry Chain class.    """
    name: str = "fa_carry_chain"
    
    cluster_size: int = None
    FAs_per_flut: bool = None

    use_finfet: bool = None 

    # Circuit Dependancies
    carry_chain_periph: CarryChainPer = None

    def __hash__(self) -> int:
        return super().__hash__()

    def generate(self, subcircuit_filename: str) -> Dict[str, int | float]:
        """ Generate Carry chain SPICE netlists."""  

        self.transistor_names, self.wire_names = lut_subcircuits.generate_full_adder_simplified(subcircuit_filename, self.sp_name, self.use_finfet)

        # if type is skip, we need to generate two levels of nand + not for the and tree
        # if type is ripple, we need to add the delay of one inverter for the final sum.

        # self.initial_transistor_sizes["inv_carry_chain_1_nmos"] = 1
        # self.initial_transistor_sizes["inv_carry_chain_1_pmos"] = 1
        # self.initial_transistor_sizes["inv_carry_chain_2_nmos"] = 1
        # self.initial_transistor_sizes["inv_carry_chain_2_pmos"] = 1
        # self.initial_transistor_sizes["tgate_carry_chain_1_nmos"] = 1
        # self.initial_transistor_sizes["tgate_carry_chain_1_pmos"] = 1
        # self.initial_transistor_sizes["tgate_carry_chain_2_nmos"] = 1
        # self.initial_transistor_sizes["tgate_carry_chain_2_pmos"] = 1
        for tx_name in self.transistor_names:
            self.initial_transistor_sizes[tx_name] = 1

        return self.initial_transistor_sizes

    def update_area(self, area_dict: Dict[str, float], width_dict: Dict[str, float]) -> float:
        """ Calculate Carry Chain area and update dictionaries. """
        area = (
            area_dict[f"inv_{self.sp_name}_1"] * 2
                + area_dict[f"inv_{self.sp_name}_2"] 
                + area_dict[f"tgate_{self.sp_name}_1"] * 4 
                + area_dict[f"tgate_{self.sp_name}_2"] * 4
        )
        area = area + area_dict[f"{self.carry_chain_periph.sp_name}"]
        area_with_sram = area
        width = math.sqrt(area)
        area_dict[self.sp_name] = area
        width_dict[self.sp_name] = width

    def update_wires(self, width_dict: Dict[str, float], wire_lengths: Dict[str, float], wire_layers: Dict[str, float]) -> List[str]:
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """
        if self.FAs_per_flut == 2:
            wire_lengths["wire_" + self.sp_name + "_1"] = width_dict["lut_and_drivers"] # Wire for input A
        else:
            wire_lengths["wire_" + self.sp_name + "_1"] = width_dict[self.sp_name] # Wire for input A
        wire_layers["wire_" + self.sp_name + "_1"] = consts.LOCAL_WIRE_LAYER
        wire_lengths["wire_" + self.sp_name + "_2"] = width_dict[self.sp_name] # Wire for input B
        wire_layers["wire_" + self.sp_name + "_2"] = consts.LOCAL_WIRE_LAYER
        # TODO update below "local_cluster" call to the width dict for multi ckt support
        if self.FAs_per_flut == 1:
            wire_lengths["wire_" + self.sp_name + "_3"] = width_dict["logic_cluster"]/(2 * self.cluster_size) # Wire for input Cin
        else:
            wire_lengths["wire_" + self.sp_name + "_3"] = width_dict["logic_cluster"]/(4 * self.cluster_size) # Wire for input Cin
        wire_layers["wire_" + self.sp_name + "_3"] = consts.LOCAL_WIRE_LAYER
        if self.FAs_per_flut == 1:
            wire_lengths["wire_" + self.sp_name + "_4"] = width_dict["logic_cluster"]/(2 * self.cluster_size) # Wire for output Cout
        else:
            wire_lengths["wire_" + self.sp_name + "_4"] = width_dict["logic_cluster"]/(4 * self.cluster_size) # Wire for output Cout
        wire_layers["wire_" + self.sp_name + "_4"] = consts.LOCAL_WIRE_LAYER
        wire_lengths["wire_" + self.sp_name + "_5"] = width_dict[self.sp_name] # Wire for output Sum
        wire_layers["wire_" + self.sp_name + "_5"] = consts.LOCAL_WIRE_LAYER

    def print_details(self):
        print(" Carry Chain DETAILS:")

@dataclass
class CarryChainTB(c_ds.SimTB):
    """  """
    FA_carry_chain: CarryChain = None

    subckt_lib: InitVar[Dict[str, rg_ds.SpSubCkt]] = None
    # Initialized in __post_init__
    dut_ckt: CarryChain = None

    def __hash__(self) -> int:
        return super().__hash__()
    
    def __post_init__(self, subckt_lib):
        super().__post_init__()
        self.meas_points = []
        pwr_v_node: str = "vdd_carry_chain"
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
            name = "_CC",
            out_node = pwr_v_node,
            init_volt = c_ds.Value(name = self.supply_v_param),
        )
        # Initialize the DUT 
        self.dut_ckt = self.FA_carry_chain
        # Top Instances
        self.top_insts = [
            # Wave Shaping Circuitry
            rg_ds.SpSubCktInst(
                name = f"X{self.FA_carry_chain.sp_name}_shape_1",  # TODO update to sp_name
                subckt = subckt_lib[self.FA_carry_chain.sp_name], # TODO update to sp_name
                conns = {
                    "n_a": self.vdd_node,
                    "n_b": self.gnd_node,
                    "n_cin": "n_in",
                    "n_cout":"n_0_1",
                    "n_sum_out": "n_hang",
                    "n_p": "n_p_1",
                    "n_vdd": self.vdd_node,
                    "n_gnd": self.gnd_node,
                }
            ),
            rg_ds.SpSubCktInst(
                name = f"X{self.FA_carry_chain.sp_name}_shape_2",  # TODO update to sp_name
                subckt = subckt_lib[self.FA_carry_chain.sp_name], # TODO update to sp_name
                conns = {
                    "n_a": self.vdd_node,
                    "n_b": self.gnd_node,
                    "n_cin": "n_0_1",
                    "n_cout":"n_0_2",
                    "n_sum_out": "n_hangz",
                    "n_p": "n_p_0",
                    "n_vdd": self.vdd_node,
                    "n_gnd": self.gnd_node,
                }
            ),
            rg_ds.SpSubCktInst(
                name = f"X{self.FA_carry_chain.sp_name}_shape_3",  # TODO update to sp_name
                subckt = subckt_lib[self.FA_carry_chain.sp_name], # TODO update to sp_name
                conns = {
                    "n_a": self.vdd_node,
                    "n_b": self.gnd_node,
                    "n_cin": "n_0_2",
                    "n_cout":"n_1_1",
                    "n_sum_out": "n_hangz",
                    "n_p": "n_p_2",
                    "n_vdd": self.vdd_node,
                    "n_gnd": self.gnd_node,
                }
            ),
            # DUT
            rg_ds.SpSubCktInst(
                name = f"X{self.FA_carry_chain.sp_name}_dut",  # TODO update to sp_name
                subckt = subckt_lib[self.FA_carry_chain.sp_name], # TODO update to sp_name
                conns = {
                    "n_a": self.vdd_node,
                    "n_b": self.gnd_node,
                    "n_cin": "n_1_1",
                    "n_cout":"n_1_2",
                    "n_sum_out": "n_sum_out",
                    "n_p": "n_p_2",
                    "n_vdd": self.vdd_node,
                    "n_gnd": self.gnd_node,
                }
            ),
            # DUT load
            rg_ds.SpSubCktInst(
                name = f"X{self.FA_carry_chain.sp_name}_load",  # TODO update to sp_name
                subckt = subckt_lib[self.FA_carry_chain.sp_name], # TODO update to sp_name
                conns = {
                    "n_a": self.vdd_node,
                    "n_b": self.gnd_node,
                    "n_cin": "n_1_2",
                    "n_cout":"n_1_3",
                    "n_sum_out": "n_sum_out2",
                    "n_p": "n_p_3",
                    "n_vdd": self.vdd_node,
                    "n_gnd": self.gnd_node,
                }
            )
        ]
    def generate_top(self):
        dut_sp_name: str = self.dut_ckt.sp_name # TODO update to sp_name
        trig_node: str = "n_1_1"
        delay_names: List[str] = [
            f"inv_{dut_sp_name}_1",
            f"inv_{dut_sp_name}_2",
            f"total",
        ] 
        # Instance path from our TB to the ON Local Mux inst
        cc_dut_path: List[rg_ds.SpSubCktInst] = sp_parser.rec_find_inst(
            self.top_insts, 
            [ re.compile(re_str, re.MULTILINE | re.IGNORECASE) 
                for re_str in [
                    r"carry_chain_(?:.*)dut",
                ]
            ],
            []
        )
        targ_nodes: List[str] = [
            ".".join([inst.name for inst in cc_dut_path] + ["n_cin_in_bar"]),
            "n_sum_out",
            "n_1_2",
        ]
        meas_inv_list: List[bool] = [True] + [False] * (len(delay_names)-1)
        low_v_node: str = "gnd"
        cust_pwr_meas_lines: List[str] = [
            f".MEASURE TRAN meas_logic_low_voltage FIND V({low_v_node}) AT=25n",
            f"* Measure the power required to propagate a rise and a fall transition through the subcircuit at 250MHz.",
            f".MEASURE TRAN meas_current INTEGRAL I({self.dut_dc_vsrc.get_sp_name()}) FROM=0ns TO=26ns",
            f".MEASURE TRAN meas_avg_power PARAM = '-((meas_current)/26n)*supply_v'",
        ]
        # Base class generate top does all common functionality 
        return super().generate_top(
            delay_names = delay_names,
            trig_node = trig_node, 
            targ_nodes = targ_nodes,
            low_v_node = "gnd", # TODO figure out why tf we are measuring the low value of gnd...
            pwr_meas_lines = cust_pwr_meas_lines,
            meas_inv_list = meas_inv_list,
        )

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

    def __hash__(self) -> int:
        return super().__hash__()

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

        self.transistor_names, self.wire_names = lut_subcircuits.generate_skip_and_tree(subcircuit_filename, self.sp_name, self.use_finfet, self.nand1_size, self.nand2_size)


        self.initial_transistor_sizes["inv_nand"+str(self.nand1_size)+f"_{self.sp_name}_1_nmos"] = 1
        self.initial_transistor_sizes["inv_nand"+str(self.nand1_size)+f"_{self.sp_name}_1_pmos"] = 1
        self.initial_transistor_sizes[f"inv_{self.sp_name}_2_nmos"] = 1
        self.initial_transistor_sizes[f"inv_{self.sp_name}_2_pmos"] = 1
        self.initial_transistor_sizes["inv_nand"+str(self.nand2_size)+f"_{self.sp_name}_3_nmos"] = 1
        self.initial_transistor_sizes["inv_nand"+str(self.nand2_size)+f"_{self.sp_name}_3_pmos"] = 1
        self.initial_transistor_sizes[f"inv_{self.sp_name}_4_nmos"] = 1
        self.initial_transistor_sizes[f"inv_{self.sp_name}_4_pmos"] = 1

        return self.initial_transistor_sizes

    def update_area(self, area_dict, width_dict):
        """ Calculate Carry Chain area and update dictionaries. """
        area_1 = (area_dict["inv_nand"+str(self.nand1_size)+f"_{self.sp_name}_1"] + area_dict[f"inv_{self.sp_name}_2"])* int(math.ceil(float(int(self.skip_size/self.nand1_size))))
        area_2 = area_dict["inv_nand"+str(self.nand2_size)+f"_{self.sp_name}_3"] + area_dict[f"inv_{self.sp_name}_4"]
        area = area_1 + area_2
        area_with_sram = area
        width = math.sqrt(area)
        area_dict[self.sp_name] = area
        width_dict[self.sp_name] = width

    def update_wires(self, width_dict, wire_lengths, wire_layers):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """
        if self.FAs_per_flut == 2:
            wire_lengths["wire_" + self.sp_name + "_1"] = (width_dict["ble"]*self.skip_size)/4.0
        else:
            wire_lengths["wire_" + self.sp_name + "_1"] = (width_dict["ble"]*self.skip_size)/2.0
        wire_layers["wire_" + self.sp_name + "_1"] = consts.LOCAL_WIRE_LAYER
        wire_lengths["wire_" + self.sp_name + "_2"] = width_dict[self.sp_name]/2.0
        wire_layers["wire_" + self.sp_name + "_2"] = consts.LOCAL_WIRE_LAYER

    def print_details(self):
        print(" Carry Chain DETAILS:")


@dataclass
class CarryChainSkipAndTB(c_ds.SimTB):
    lut: lut_lib.LUT = None
    FA_carry_chain: CarryChain = None
    carry_chain_and: CarryChainSkipAnd = None
    carry_chain_skip_mux: CarryChainSkipMux = None
    carry_chain_mux: CarryChainMux = None
    
    subckt_lib: InitVar[Dict[str, rg_ds.SpSubCkt]] = None
    
    # Initialized in __post_init__
    dut_ckt: CarryChainSkipAnd = None
    
    def __hash__(self) -> int:
        return super().__hash__()
    
    def __post_init__(self, subckt_lib):
        super().__post_init__()
        self.meas_points = []
        self.pwr_v_node: str = "vdd_cc_and"

        # Specify lut connections
        if self.lut.use_tgate:
            lut_conns: Dict[str, str] = {
                "n_in": "n_in",
                "n_out": "n_1_1",
                "n_a": self.vdd_node,
                "n_a_n": self.gnd_node,
                "n_b": self.vdd_node,
                "n_b_n": self.gnd_node,
                "n_c": self.vdd_node,
                "n_c_n": self.gnd_node,
                "n_d": self.vdd_node,
                "n_d_n": self.gnd_node,
                "n_e": self.vdd_node,
                "n_e_n": self.gnd_node,
                "n_f": self.vdd_node,
                "n_f_n": self.gnd_node,
                "n_vdd": self.vdd_node,
                "n_gnd": self.gnd_node,
            }
        else:
            lut_conns: Dict[str, str] = {
                "n_in": "n_in",
                "n_out": "n_1_1",
                "n_a": self.vdd_node,
                "n_a_n": self.gnd_node,
                "n_b": self.vdd_node,
                "n_b_n": self.gnd_node,
                "n_vdd": self.vdd_node,
                "n_gnd": self.gnd_node,
            }
        # STIM PULSE Voltage SRC
        self.stim_vsrc = c_ds.SpVoltageSrc(
            name = "IN",
            out_node = "n_in",
            type = "PULSE",
            init_volt = c_ds.Value(0), #V
            peak_volt = c_ds.Value(name = self.supply_v_param), # TODO get this from defined location
            pulse_width = c_ds.Value(2), # ns
            period = c_ds.Value(4), # ns
        )
        # DUT DC Voltage Source
        self.dut_dc_vsrc = c_ds.SpVoltageSrc(
            name = "_CC_AND",
            out_node = self.pwr_v_node,
            init_volt = c_ds.Value(name = self.supply_v_param),
        )
        # Init DUT
        self.dut_ckt = self.carry_chain_and

        self.top_insts = [
            # LUT
            rg_ds.SpSubCktInst(
                name = f"X{self.lut.name}", # TODO update to sp_name
                subckt = subckt_lib[self.lut.name], # TODO update to sp_name
                conns = lut_conns,
            ),
            # FA Carry Chain
            rg_ds.SpSubCktInst(
                name = f"X{self.FA_carry_chain.sp_name}", # TODO update to sp_name
                subckt = subckt_lib[self.FA_carry_chain.sp_name], # TODO update to sp_name
                conns = {
                    "n_a": "n_1_1",
                    "n_b": self.vdd_node,
                    "n_cin": self.gnd_node,
                    "n_cout": "n_hang",
                    "n_sum_out": "n_sum_out",
                    "n_p": "n_1_2",
                    "n_vdd": self.vdd_node,
                    "n_gnd": self.gnd_node,
                }
            ),
            # DUT And Tree
            rg_ds.SpSubCktInst(
                name = f"X{self.carry_chain_and.sp_name}", # TODO update to sp_name
                subckt = subckt_lib[self.carry_chain_and.sp_name], # TODO update to sp_name
                conns = {
                    "n_in": "n_1_2",
                    "n_out": "n_1_3",
                    "n_vdd": self.pwr_v_node,
                    "n_gnd": self.gnd_node,
                }
            ),
            # Carry Chain Skip Mux
            rg_ds.SpSubCktInst(
                name = f"X{self.carry_chain_skip_mux.sp_name}", 
                subckt = subckt_lib[self.carry_chain_skip_mux.sp_name], 
                conns = {
                    "n_in": "n_1_3",
                    "n_out": "n_1_4",
                    "n_gate": self.vdd_node,
                    "n_gate_n": self.gnd_node,
                    "n_vdd": self.vdd_node,
                    "n_gnd": self.gnd_node,
                }
            ),
            # Carry Chain Mux
            rg_ds.SpSubCktInst(
                name = f"X{self.carry_chain_mux.sp_name}", 
                subckt = subckt_lib[self.carry_chain_mux.sp_name], 
                conns = {
                    "n_in": "n_1_4",
                    "n_out": "n_1_5",
                    "n_gate": self.vdd_node,
                    "n_gate_n": self.gnd_node,
                    "n_vdd": self.vdd_node,
                    "n_gnd": self.gnd_node,
                }
            ),
        ]
    def generate_top(self):
        # dut_sp_name: str = self.dut_ckt.sp_name # TODO update to sp_name
        trig_node: str = "n_1_2"
        delay_names: List[str] = [
            f"inv_nand{self.carry_chain_and.nand1_size}_{self.carry_chain_and.sp_name}_1",
            f"inv_{self.carry_chain_and.sp_name}_2",
            f"inv_nand{self.carry_chain_and.nand2_size}_{self.carry_chain_and.sp_name}_3",
            f"inv_{self.carry_chain_and.sp_name}_4",
            f"total",
        ] 
        # Instance path from our TB to the ON Local Mux inst
        cc_and_dut_path: List[rg_ds.SpSubCktInst] = sp_parser.rec_find_inst(
            self.top_insts, 
            [ re.compile(re_str, re.MULTILINE | re.IGNORECASE) 
                for re_str in [
                    f"{self.carry_chain_and.sp_name}",
                ]
            ],
            []
        )
        targ_nodes: List[str] = [
            ".".join([inst.name for inst in cc_and_dut_path] + ["n_1_2"]),
            ".".join([inst.name for inst in cc_and_dut_path] + ["n_1_3"]),
            ".".join([inst.name for inst in cc_and_dut_path] + ["n_1_5"]),
            "n_1_3",
            "n_1_3",
        ]
        low_v_node: str = "gnd"
        cust_pwr_meas_lines: List[str] = [
            f".MEASURE TRAN meas_logic_low_voltage FIND V({low_v_node}) AT=25n",
            f"* Measure the power required to propagate a rise and a fall transition through the subcircuit at 250MHz.",
            f".MEASURE TRAN meas_current INTEGRAL I({self.dut_dc_vsrc.get_sp_name()}) FROM=0ns TO=26ns",
            f".MEASURE TRAN meas_avg_power PARAM = '-((meas_current)/26n)*supply_v'",
        ]
        tb_fname: str = f"{self.dut_ckt.sp_name}_tb_{self.id}"
        # Base class generate top does all common functionality 
        return super().generate_top(
            delay_names = delay_names,
            trig_node = trig_node, 
            targ_nodes = targ_nodes,
            low_v_node = "gnd", # TODO figure out why tf we are measuring the low value of gnd...
            pwr_meas_lines = cust_pwr_meas_lines,
            tb_fname = tb_fname,
        )


@dataclass
class CarryChainInterCluster(c_ds.SizeableCircuit):
    """ Wire dirvers of carry chain path between clusters"""

    name: str = "carry_chain_inter"

    use_finfet: bool = None
    carry_chain_type: str = None # Ripple or skip?
    inter_wire_length: float = None # Length of wire between Cout of a cluster and Cin of the next cluster

    def __hash__(self) -> int:
        return super().__hash__()

    def generate(self, subcircuit_filename: str) -> Dict[str, int | float]:
        """ Generate Carry chain SPICE netlists."""  

        self.transistor_names, self.wire_names = lut_subcircuits.generate_carry_inter(subcircuit_filename, self.sp_name, self.use_finfet)

        self.initial_transistor_sizes["inv_" + self.sp_name + "_1_nmos"] = 1
        self.initial_transistor_sizes["inv_" + self.sp_name + "_1_pmos"] = 1
        self.initial_transistor_sizes["inv_" + self.sp_name + "_2_nmos"] = 2
        self.initial_transistor_sizes["inv_" + self.sp_name + "_2_pmos"] = 2

        return self.initial_transistor_sizes

    def update_area(self, area_dict, width_dict):
        """ Calculate Carry Chain area and update dictionaries. """
        area = area_dict["inv_" + self.sp_name + "_1"] + area_dict["inv_" + self.sp_name + "_2"]
        area_with_sram = area
        width = math.sqrt(area)
        area_dict[self.sp_name] = area
        width_dict[self.sp_name] = width

    def update_wires(self, width_dict, wire_lengths, wire_layers):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """

        wire_lengths["wire_" + self.sp_name + "_1"] = width_dict["tile"] * self.inter_wire_length
        wire_layers["wire_" + self.sp_name + "_1"] = consts.LOCAL_WIRE_LAYER

    def print_details(self):
        pass

@dataclass
class CarryChainInterClusterTB(c_ds.SimTB):
    FA_carry_chain: CarryChain = None
    carry_chain_inter: CarryChainInterCluster = None

    subckt_lib: InitVar[Dict[str, rg_ds.SpSubCkt]] = None
    
    # Initialized in __post_init__
    dut_ckt: CarryChainSkipAnd = None
    
    def __hash__(self) -> int:
        return super().__hash__() 
    
    def __post_init__(self, subckt_lib):
        super().__post_init__()
        self.meas_points = []
        self.pwr_v_node: str = "vdd_cc_inter_cluster"
        self.dut_ckt = self.carry_chain_inter
        # STIM PULSE Voltage SRC
        self.stim_vsrc = c_ds.SpVoltageSrc(
            name = "IN",
            out_node = "n_in",
            type = "PULSE",
            init_volt = c_ds.Value(0), #V
            peak_volt = c_ds.Value(name = self.supply_v_param), # TODO get this from defined location
            pulse_width = c_ds.Value(2), # ns
            period = c_ds.Value(4), # ns
        )
        # DUT DC Voltage Source
        self.dut_dc_vsrc = c_ds.SpVoltageSrc(
            name = "_CC_INTER",
            out_node = self.pwr_v_node,
            init_volt = c_ds.Value(name = self.supply_v_param),
        )
        self.top_insts = [
            # FA Carry Chain Shape Circuitry
            # Wave Shaping Circuitry
            rg_ds.SpSubCktInst(
                name = f"X{self.FA_carry_chain.sp_name}_shape_1",  # TODO update to sp_name
                subckt = subckt_lib[self.FA_carry_chain.sp_name], # TODO update to sp_name
                conns = {
                    "n_a": self.vdd_node,
                    "n_b": self.gnd_node,
                    "n_cin": "n_in",
                    "n_cout":"n_1_1",
                    "n_sum_out": "n_sum_out",
                    "n_p": "n_p_0",
                    "n_vdd": self.vdd_node,
                    "n_gnd": self.gnd_node,
                }
            ),
            rg_ds.SpSubCktInst(
                name = f"X{self.FA_carry_chain.sp_name}_shape_2",  # TODO update to sp_name
                subckt = subckt_lib[self.FA_carry_chain.sp_name], # TODO update to sp_name
                conns = {
                    "n_a": self.vdd_node,
                    "n_b": self.gnd_node,
                    "n_cin": "n_1_1",
                    "n_cout":"n_1_2",
                    "n_sum_out": "n_sum_out_2",
                    "n_p": "n_p_1",
                    "n_vdd": self.vdd_node,
                    "n_gnd": self.gnd_node,
                }
            ),
            # DUT Carry Chain Inter
            rg_ds.SpSubCktInst(
                name = f"X{self.carry_chain_inter.sp_name}_dut", # TODO update to sp_name
                subckt = subckt_lib[self.carry_chain_inter.sp_name], # TODO update to sp_name
                conns = {
                    "n_in": "n_1_2",
                    "n_out": "n_1_3",
                    "n_vdd": self.pwr_v_node,
                    "n_gnd": self.gnd_node,
                }
            ),
            # Load (FA Carry Chain)
            # DUT load
            rg_ds.SpSubCktInst(
                name = f"X{self.FA_carry_chain.sp_name}_load",  # TODO update to sp_name
                subckt = subckt_lib[self.FA_carry_chain.sp_name], # TODO update to sp_name
                conns = {
                    "n_a": "n_1_3", 
                    "n_b": self.vdd_node,
                    "n_cin": self.gnd_node,
                    "n_cout": "n_hang_l",
                    "n_sum_out": "n_sum_out_3",
                    "n_p": "n_p_2",
                    "n_vdd": self.vdd_node,
                    "n_gnd": self.gnd_node,
                }
            )
        ]
    def generate_top(self):
        dut_sp_name: str = self.dut_ckt.name
        trig_node: str = "n_1_2"
        # Instance path from our TB to the ON Local Mux inst
        cc_inter_dut_path: List[rg_ds.SpSubCktInst] = sp_parser.rec_find_inst(
            self.top_insts, 
            [ re.compile(re_str, re.MULTILINE | re.IGNORECASE) 
                for re_str in [
                    r"carry_chain_inter(?:.*)_dut",
                ]
            ],
            []
        )
        delay_nodes: List[str] = [
            f"inv_{self.carry_chain_inter.sp_name}_1",
            f"inv_{self.carry_chain_inter.sp_name}_2",
            f"total",
        ]
        targ_nodes: List[str] = [
            ".".join([inst.name for inst in cc_inter_dut_path] + ["n_1_1"]),
            "n_1_3",
            "n_1_3",
        ]
        low_v_node: str = "gnd"
        cust_pwr_meas_lines: List[str] = [
            f".MEASURE TRAN meas_logic_low_voltage FIND V({low_v_node}) AT=25n",
            f"* Measure the power required to propagate a rise and a fall transition through the subcircuit at 250MHz.",
            f".MEASURE TRAN meas_current INTEGRAL I({self.dut_dc_vsrc.get_sp_name()}) FROM=0ns TO=26ns",
            f".MEASURE TRAN meas_avg_power PARAM = '-((meas_current)/26n)*supply_v'",
        ]
        tb_fname: str = f"{dut_sp_name}_tb_{self.id}"
        # Base class generate top does all common functionality
        return super().generate_top(
            delay_names = delay_nodes,
            trig_node = trig_node,
            targ_nodes = targ_nodes,
            low_v_node = "gnd", # TODO figure out why tf we are measuring the low value of gnd...
            pwr_meas_lines = cust_pwr_meas_lines,
            tb_fname = tb_fname,
        )

@dataclass
class CarryChainSkipMux(mux.Mux2to1):
    """ Part of peripherals used in carry chain class.    """
    name: str = "xcarry_chain_mux"
    use_finfet: bool = None
    use_tgate: bool = None

    carry_chain_type: str = None # Ripple or skip?

    def __hash__(self) -> int:
        return super().__hash__()

    def update_wires(self, width_dict: Dict[str, int], wire_lengths: Dict[str, float], wire_layers: Dict[str, int]):
        """ Update the wires of the mux. """
        # Update the wires of the mux
        super().update_wires(width_dict, wire_lengths, wire_layers)
        wire_layers["wire_lut_to_flut_mux"] = consts.LOCAL_WIRE_LAYER

@dataclass
class CarryChainSkipMuxTB(c_ds.SimTB):
    lut: lut_lib.LUT = None
    FA_carry_chain: CarryChain = None
    carry_chain_and: CarryChainSkipAnd = None
    carry_chain_skip_mux: CarryChainSkipMux = None
    carry_chain_mux: CarryChainMux = None
    
    subckt_lib: InitVar[Dict[str, rg_ds.SpSubCkt]] = None
    
    # Initialized in __post_init__
    dut_ckt: CarryChainSkipAnd = None
    
    def __hash__(self) -> int:
        return super().__hash__()
      
    def __post_init__(self, subckt_lib):
        super().__post_init__()
        self.meas_points = []
        self.pwr_v_node: str = "vdd_skip_mux"

        # Specify lut connections
        if self.lut.use_tgate:
            lut_conns: Dict[str, str] = {
                "n_in": "n_in",
                "n_out": "n_1_1",
                "n_a": self.vdd_node,
                "n_a_n": self.gnd_node,
                "n_b": self.vdd_node,
                "n_b_n": self.gnd_node,
                "n_c": self.vdd_node,
                "n_c_n": self.gnd_node,
                "n_d": self.vdd_node,
                "n_d_n": self.gnd_node,
                "n_e": self.vdd_node,
                "n_e_n": self.gnd_node,
                "n_f": self.vdd_node,
                "n_f_n": self.gnd_node,
                "n_vdd": self.vdd_node,
                "n_gnd": self.gnd_node,
            }
        else:
            lut_conns: Dict[str, str] = {
                "n_in": "n_in",
                "n_out": "n_1_1",
                "n_a": self.vdd_node,
                "n_a_n": self.gnd_node,
                "n_b": self.vdd_node,
                "n_b_n": self.gnd_node,
                "n_vdd": self.vdd_node,
                "n_gnd": self.gnd_node,
            }
        # STIM PULSE Voltage SRC
        self.stim_vsrc = c_ds.SpVoltageSrc(
            name = "IN",
            out_node = "n_in",
            type = "PULSE",
            init_volt = c_ds.Value(0), #V
            peak_volt = c_ds.Value(name = self.supply_v_param), # TODO get this from defined location
            pulse_width = c_ds.Value(2), # ns
            period = c_ds.Value(4), # ns
        )
        # DUT DC Voltage Source
        self.dut_dc_vsrc = c_ds.SpVoltageSrc(
            name = "_CC_SKIP_MUX",
            out_node = self.pwr_v_node,
            init_volt = c_ds.Value(name = self.supply_v_param),
        )
        # Init DUT
        self.dut_ckt = self.carry_chain_skip_mux

        self.top_insts = [
            # LUT
            rg_ds.SpSubCktInst(
                name = f"X{self.lut.name}", # TODO update to sp_name
                subckt = subckt_lib[self.lut.name], # TODO update to sp_name
                conns = lut_conns,
            ),
            # FA Carry Chain
            rg_ds.SpSubCktInst(
                name = f"X{self.FA_carry_chain.sp_name}", # TODO update to sp_name
                subckt = subckt_lib[self.FA_carry_chain.sp_name], # TODO update to sp_name
                conns = {
                    "n_a": "n_1_1",
                    "n_b": self.vdd_node,
                    "n_cin": self.gnd_node,
                    "n_cout": "n_hang",
                    "n_sum_out": "n_sum_out",
                    "n_p": "n_1_2",
                    "n_vdd": self.vdd_node,
                    "n_gnd": self.gnd_node,
                }
            ),
            # And Tree
            rg_ds.SpSubCktInst(
                name = f"X{self.carry_chain_and.sp_name}", # TODO update to sp_name
                subckt = subckt_lib[self.carry_chain_and.sp_name], # TODO update to sp_name
                conns = {
                    "n_in": "n_1_2",
                    "n_out": "n_1_3",
                    "n_vdd": self.vdd_node,
                    "n_gnd": self.gnd_node,
                }
            ),
            # DUT Carry Chain Skip Mux
            rg_ds.SpSubCktInst(
                name = f"X{self.carry_chain_skip_mux.sp_name}_dut", 
                subckt = subckt_lib[self.carry_chain_skip_mux.sp_name], 
                conns = {
                    "n_in": "n_1_3",
                    "n_out": "n_1_4",
                    "n_gate": self.vdd_node,
                    "n_gate_n": self.gnd_node,
                    "n_vdd": self.pwr_v_node,
                    "n_gnd": self.gnd_node,
                }
            ),
            # Carry Chain Mux
            rg_ds.SpSubCktInst(
                name = f"X{self.carry_chain_mux.sp_name}", 
                subckt = subckt_lib[self.carry_chain_mux.sp_name], 
                conns = {
                    "n_in": "n_1_4",
                    "n_out": "n_1_5",
                    "n_gate": self.vdd_node,
                    "n_gate_n": self.gnd_node,
                    "n_vdd": self.vdd_node,
                    "n_gnd": self.gnd_node,
                }
            ),
        ]

    def generate_top(self):
        # dut_sp_name: str = self.dut_ckt.sp_name
        trig_node: str = "n_1_3"
        delay_names: List[str] = [
            f"inv_{self.dut_ckt.sp_name}_1",
            f"inv_{self.dut_ckt.sp_name}_2",
            f"total",
        ] 
        # Instance path from our TB to the ON Local Mux inst
        cc_skip_mux_path: List[rg_ds.SpSubCktInst] = sp_parser.rec_find_inst(
            self.top_insts, 
            [ re.compile(re_str, re.MULTILINE | re.IGNORECASE) 
                for re_str in [
                    r"carry_chain_mux_(?:.*)_dut",
                ]
            ],
            []
        )
        targ_nodes: List[str] = [
            ".".join([inst.name for inst in cc_skip_mux_path] + ["n_2_1"]),
            "n_1_4",
            "n_1_4",
        ]
        # cust_pwr_meas_lines: List[str] = [
        #     f"* Measure the power required to propagate a rise and a fall transition through the subcircuit at 250MHz.",
        #     f".MEASURE TRAN meas_current INTEGRAL I({self.dut_dc_vsrc.get_sp_name()}) FROM=0ns TO=26ns",
        #     f".MEASURE TRAN meas_avg_power PARAM = '-((meas_current)/26n)*supply_v'",
        # ]
        tb_fname: str = f"{self.dut_ckt.sp_name}_tb_{self.id}"
        # Base class generate top does all common functionality 
        return super().generate_top(
            delay_names = delay_names,
            trig_node = trig_node, 
            targ_nodes = targ_nodes,
            low_v_node = self.gnd_node, # TODO figure out why tf we measure voltage of a floating node...
            # pwr_meas_lines = cust_pwr_meas_lines,
            tb_fname = tb_fname,
        )