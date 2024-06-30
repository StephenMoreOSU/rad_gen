from __future__ import annotations
from dataclasses import dataclass, field, InitVar

import math, os, sys
import re
from typing import List, Dict, Any, Tuple, Union, Type

import src.coffe.data_structs as c_ds
import src.common.data_structs as rg_ds
import src.common.spice_parser as sp_parser
import src.common.utils as rg_utils
import src.coffe.utils as utils
import src.coffe.mux as mux
import src.coffe.carry_chain as cc_lib
# import src.coffe.fpga as fpga

import src.coffe.lut as lut_lib
import src.coffe.gen_routing_loads as gen_r_load_lib
import src.coffe.logic_block as lb_lib

import src.coffe.constants as consts



# This is a mux but it doesn't inherit from Mux because it's a simple 2:1
@dataclass
class LocalBLEOutput(mux.Mux2to1):
    name: str = "local_ble_output"
    delay_weight: float = consts.DELAY_WEIGHT_LOCAL_BLE_OUTPUT
    
    def __hash__(self) -> int:
        return super().__hash__()

    def __post_init__(self):
        return super().__post_init__()

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
                self.initial_transistor_sizes[tx_name] = 4
            # Set 2nd stage inverter nmos
            elif "inv" in tx_name and "_2_nmos" in tx_name:
                self.initial_transistor_sizes[tx_name] = 4
            # Set level restorer if this is a pass transistor mux
            elif "rest" in tx_name:
                self.initial_transistor_sizes[tx_name] = 1
            
        # Assert that all transistors in this mux have been updated with initial_transistor_sizes
        assert set(list(self.initial_transistor_sizes.keys())) == set(self.transistor_names)
        
        # Will be dict of ints if FinFET or discrete Tx, can be floats if bulk
        return self.initial_transistor_sizes

@dataclass
class LocalBLEOutputTB(c_ds.SimTB):
    lut: lut_lib.LUT = None
    lut_output_load: LUTOutputLoad = None
    local_ble_output_load: lb_lib.LocalBLEOutputLoad = None

    subckt_lib: InitVar[Dict[str, rg_ds.SpSubCkt]] = None
    
    # Initialized in __post_init__
    dut_ckt: LocalBLEOutput = None
    local_out_node: str = None
    general_out_node: str = None

    def __hash__(self) -> int:
        return super().__hash__()

    def __post_init__(self, subckt_lib: Dict[str, rg_ds.SpSubCkt]):
        super().__post_init__()
        self.meas_points = []
        pwr_v_node: str = "vdd_local_output"
        # node definitions
        self.local_out_node: str = "n_local_out"
        self.general_out_node: str = "n_general_out"
        # DUT DC Voltage Source
        self.dut_dc_vsrc: c_ds.SpVoltageSrc = c_ds.SpVoltageSrc(
            name = "_LOCAL_OUTPUT",
            out_node = pwr_v_node,
            init_volt = c_ds.Value(name = self.supply_v_param),
        )
        
        # Initialize the DUT from our inputted wire loads
        self.dut_ckt = self.lut_output_load.ble_outputs.local_output
        
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
        self.top_insts = [
            # LUT
            rg_ds.SpSubCktInst(
                name = f"X{self.lut.name}", # TODO update to sp_name
                subckt = subckt_lib[self.lut.name], # TODO update to sp_name
                conns = lut_conns,
            ),
            # LUT OUTPUT LOAD
            rg_ds.SpSubCktInst(
                name = f"X{self.lut_output_load.sp_name}",
                subckt = subckt_lib[self.lut_output_load.sp_name],
                conns = {
                    "n_in": "n_1_1",
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
            # LOCAL BLE OUTPUT LOAD
            rg_ds.SpSubCktInst(
                name = f"X{self.local_ble_output_load.sp_name}",
                subckt = subckt_lib[self.local_ble_output_load.sp_name],
                conns = {
                    "n_in": self.local_out_node,
                    "n_gate": self.sram_vdd_node,
                    "n_gate_n": self.sram_vss_node,
                    "n_vdd": self.vdd_node,
                    "n_gnd": self.gnd_node,
                }
            ), 
        ]

    def generate_top(self) -> str:
        dut_sp_name: str = self.dut_ckt.sp_name
        # Get list of insts to get to the general_ble_output inst in lut_output_load
        loc_ble_out_in_path: List[rg_ds.SpSubCktInst] = sp_parser.rec_find_inst(
            self.top_insts, 
            [ re.compile(re_str, re.MULTILINE | re.IGNORECASE) 
                for re_str in [
                    "lut_output_load",
                    "ble_outputs", 
                    "local_ble_output"
                ] 
            ], #"general_ble_output" is the param_inst but param is suffix ie no change
            [] # You need to pass in an empty list to init function, if you don't weird things will happen (like getting previous results from other function calls)
        )
        loc_ble_out_load_path: List[rg_ds.SpSubCktInst] = sp_parser.rec_find_inst(
            self.top_insts,
            [ re.compile(re_str, re.MULTILINE | re.IGNORECASE) for re_str in ["local_ble_output"] ],
            []
        )
        meas_loc_ble_out_in_node: str = ".".join(
            [inst.name for inst in loc_ble_out_in_path] + ["n_2_1"]
        )
        meas_loc_ble_out_term_node: str = ".".join(
            [inst.name for inst in loc_ble_out_load_path] + ["n_1_2"]
        )
        delay_names: List[str] = [
            f"inv_{dut_sp_name}_1",
            f"inv_{dut_sp_name}_2",
            f"total",
        ]
        targ_nodes: List[str] = [
            meas_loc_ble_out_in_node, 
            meas_loc_ble_out_term_node,
            meas_loc_ble_out_term_node,
        ]
        trig_node: str = "n_1_1"
        RISE = True
        FALL = False
        rise_fall_states = [
            (FALL, RISE), # inv1_trise 
            (RISE, FALL), # inv1_tfall
            (RISE, FALL), # inv2_trise
            (FALL, RISE), # inv2_tfall
            (RISE, FALL), # total_trise
            (FALL, RISE), # total_tfall
        ]
        # Base class generate top does all common functionality 
        return super().generate_top(
            delay_names = delay_names,
            trig_node = trig_node, 
            targ_nodes = targ_nodes,
            low_v_node = self.local_out_node,
            rise_fall_states = rise_fall_states,
        )



@dataclass
class GeneralBLEOutput(mux.Mux2to1):
    name: str = "general_ble_output"
    delay_weight: float = consts.DELAY_WEIGHT_GENERAL_BLE_OUTPUT
    
    def __post_init__(self):
        super().__post_init__()

    def __hash__(self) -> int:
        return super().__hash__()

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

@dataclass
class GeneralBLEOutputTB(c_ds.SimTB):
    lut: lut_lib.LUT = None
    lut_output_load: LUTOutputLoad = None
    gen_ble_output_load: gen_r_load_lib.GeneralBLEOutputLoad = None

    subckt_lib: InitVar[Dict[str, rg_ds.SpSubCkt]] = None
    
    # Initialized in __post_init__
    dut_ckt: GeneralBLEOutput = None
    local_out_node: str = None
    general_out_node: str = None
    
    def __hash__(self) -> int:
        return super().__hash__()
    
    def __post_init__(self, subckt_lib: Dict[str, rg_ds.SpSubCkt]):
        super().__post_init__()
        self.meas_points = []
        pwr_v_node: str = "vdd_general_output"
        # node definitions
        self.local_out_node: str = "n_local_out"
        self.general_out_node: str = "n_general_out"
        # DUT DC Voltage Source
        self.dut_dc_vsrc: c_ds.SpVoltageSrc = c_ds.SpVoltageSrc(
            name = "_GENERAL_OUTPUT",
            out_node = pwr_v_node,
            init_volt = c_ds.Value(name = self.supply_v_param),
        )
        
        # Initialize the DUT from our inputted wire loads
        self.dut_ckt = self.lut_output_load.ble_outputs.general_output
        
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
        self.top_insts = [
            # LUT
            rg_ds.SpSubCktInst(
                name = f"X{self.lut.name}", # TODO update to sp_name
                subckt = subckt_lib[self.lut.name], # TODO update to sp_name
                conns = lut_conns,
            ),
            # LUT OUTPUT LOAD
            rg_ds.SpSubCktInst(
                name = f"X{self.lut_output_load.sp_name}",
                subckt = subckt_lib[self.lut_output_load.sp_name],
                conns = {
                    "n_in": "n_1_1",
                    "n_local_out": self.local_out_node,
                    "n_general_out": self.general_out_node,
                    "n_gate": self.sram_vdd_node,
                    "n_gate_n": self.sram_vss_node,
                    "n_vdd": self.vdd_node,
                    "n_gnd": self.gnd_node,
                    "n_vdd_local_output_on": self.vdd_node,
                    "n_vdd_general_output_on": pwr_v_node,
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

    def generate_top(self) -> str:
        dut_sp_name: str = self.dut_ckt.sp_name
        # Create directory for this sim
        if not os.path.exists(dut_sp_name):
            os.makedirs(dut_sp_name)
        # Get list of insts to get to the general_ble_output inst in lut_output_load
        # TODO update these for parametrization, non single Logic Cluster
        gen_ble_out_in_path: List[rg_ds.SpSubCktInst] = sp_parser.rec_find_inst(
            self.top_insts, 
            [ re.compile(re_str, re.MULTILINE | re.IGNORECASE) for re_str in ["lut_output_load", "ble_outputs", "general_ble_output"] ], #"general_ble_output" is the param_inst but param is suffix ie no change
            [] # You need to pass in an empty list to init function, if you don't weird things will happen (like getting previous results from other function calls)
        )
        gen_ble_out_load_path: List[rg_ds.SpSubCktInst] = sp_parser.rec_find_inst(
            self.top_insts,
            [ re.compile(re_str, re.MULTILINE | re.IGNORECASE) for re_str in ["general_ble_output_load"] ],
            []
        )
        meas_gen_ble_out_in_node: str = ".".join(
            [inst.name for inst in gen_ble_out_in_path] + ["n_2_1"]
        )
        meas_gen_ble_out_term_node: str = ".".join(
            [inst.name for inst in gen_ble_out_load_path] + ["n_meas_point"]
        )
        delay_names = [
            f"inv_{dut_sp_name}_1",
            f"inv_{dut_sp_name}_2",
            f"total",
        ]
        targ_nodes: List[str] = [
            meas_gen_ble_out_in_node, 
            meas_gen_ble_out_term_node,
            meas_gen_ble_out_term_node,
        ]
        trig_node: str = "n_1_1"
        # Base class generate top does all common functionality 
        return super().generate_top(
            delay_names = delay_names,
            trig_node = trig_node, 
            targ_nodes = targ_nodes,
            low_v_node = self.general_out_node,
        )



@dataclass
class FlipFlop(c_ds.SizeableCircuit):
    """ FlipFlop class.
    COFFE does not do transistor sizing for the flip flop. Therefore, the FF is not a SizableCircuit.
    Regardless of that, COFFE has a FlipFlop object that is used to obtain FF area and delay.
    COFFE creates a SPICE netlist for the FF. The 'initial_transistor_sizes', defined below, are
    used when COFFE measures T_setup and T_clock_to_Q. Those transistor sizes were obtained
    through manual design for PTM 22nm process technology. If you use a different process technology,
    you may need to re-size the FF transistors. """

    name: str = "ff"
    # Register select mux, Rsel = LUT input (e.g. 'a', 'b', etc.) or 'z' if no register select 
    register_select: str = None

    # Time characteristics for ff
    t_setup: float = None
    t_clk_to_q: float = None
    use_finfet: bool = None
    use_tgate: bool = None

    def __hash__(self) -> int:
        return super().__hash__()

    def __post__init__(self):
        self.sp_name = self.name # TODO update to sp_name
        # Initialize times to basically NULL for the cost function == 1
        if self.t_setup is None:
            self.t_setup = 1
        if self.t_clk_to_q is None:
            self.t_clk_to_q = 1
        

    def generate_ptran_2_input_select_d_ff(self, spice_filename: str, use_finfet: bool) -> Tuple[List[str], List[str]]:
        """ Generates a D Flip-Flop SPICE deck """
        
        # This script has to create the SPICE subcircuits required.
        # It has to return a list of the transistor names used as well as a list of the wire names used.
        
        # Open SPICE file for appending
        spice_file = open(spice_filename, 'a')
        
        # Create the FF circuit
        spice_file.write("******************************************************************************************\n")
        spice_file.write("* FF subcircuit \n")
        spice_file.write("******************************************************************************************\n")
        spice_file.write(".SUBCKT ff n_in n_out n_gate n_gate_n n_clk n_clk_n n_set n_set_n n_reset n_reset_n n_vdd n_gnd\n")
        spice_file.write("* Input selection MUX\n")
        spice_file.write("Xptran_ff_input_select n_in n_1_1 n_gate n_gnd ptran Wn=ptran_ff_input_select_nmos\n")
        spice_file.write("Xwire_ff_input_select n_1_1 n_1_2 wire Rw='wire_ff_input_select_res/2' Cw='wire_ff_input_select_cap/2'\n")
        spice_file.write("Xwire_ff_input_select_h n_1_2 n_1_3 wire Rw='wire_ff_input_select_res/2' Cw='wire_ff_input_select_cap/2'\n")
        spice_file.write("Xptran_ff_input_select_h n_gnd n_1_3 n_gate_n n_gnd ptran Wn=ptran_ff_input_select_nmos\n")
        spice_file.write("Xrest_ff_input_select n_1_2 n_2_1 n_vdd n_gnd rest Wp=rest_ff_input_select_pmos\n")
        spice_file.write("Xinv_ff_input_1 n_1_2 n_2_1 n_vdd n_gnd inv Wn=inv_ff_input_1_nmos Wp=inv_ff_input_1_pmos\n\n")
        spice_file.write("* First T-gate and cross-coupled inverters\n") 
        spice_file.write("Xwire_ff_input_out n_2_1 n_2_2 wire Rw=wire_ff_input_out_res Cw=wire_ff_input_out_cap\n")    
        spice_file.write("Xtgate_ff_1 n_2_2 n_3_1 n_clk_n n_clk n_vdd n_gnd tgate Wn=tgate_ff_1_nmos Wp=tgate_ff_1_pmos\n")
        if not use_finfet :
            spice_file.write("MPtran_ff_set_n n_3_1 n_set_n n_vdd n_vdd pmos L=gate_length W=tran_ff_set_n_pmos\n")
            spice_file.write("MNtran_ff_reset n_3_1 n_reset n_gnd n_gnd nmos L=gate_length W=tran_ff_reset_nmos\n")
        else :
            spice_file.write("MPtran_ff_set_n n_3_1 n_set_n n_vdd n_vdd pmos L=gate_length nfin=tran_ff_set_n_pmos\n")
            spice_file.write("MNtran_ff_reset n_3_1 n_reset n_gnd n_gnd nmos L=gate_length nfin=tran_ff_reset_nmos\n")

        spice_file.write("Xwire_ff_tgate_1_out n_3_1 n_3_2 wire Rw=wire_ff_tgate_1_out_res Cw=wire_ff_tgate_1_out_cap\n")
        spice_file.write("Xinv_ff_cc1_1 n_3_2 n_4_1 n_vdd n_gnd inv Wn=inv_ff_cc1_1_nmos Wp=inv_ff_cc1_1_pmos\n")
        spice_file.write("Xinv_ff_cc1_2 n_4_1 n_3_2 n_vdd n_gnd inv Wn=inv_ff_cc1_2_nmos Wp=inv_ff_cc1_2_pmos\n")
        spice_file.write("Xwire_ff_cc1_out n_4_1 n_4_2 wire Rw=wire_ff_cc1_out_res Cw=wire_ff_cc1_out_cap\n\n")
        spice_file.write("* Second T-gate and cross-coupled inverters\n")
        spice_file.write("Xtgate_ff_2 n_4_2 n_5_1 n_clk n_clk_n n_vdd n_gnd tgate Wn=tgate_ff_2_nmos Wp=tgate_ff_2_pmos\n")
        if not use_finfet :
            spice_file.write("MPtran_ff_reset_n n_5_1 n_reset_n n_vdd n_vdd pmos L=gate_length W=tran_ff_reset_n_pmos\n")
            spice_file.write("MNtran_ff_set n_5_1 n_set n_gnd n_gnd nmos L=gate_length W=tran_ff_set_nmos\n")
        else :
            spice_file.write("MPtran_ff_reset_n n_5_1 n_reset_n n_vdd n_vdd pmos L=gate_length nfin=tran_ff_reset_n_pmos\n")
            spice_file.write("MNtran_ff_set n_5_1 n_set n_gnd n_gnd nmos L=gate_length nfin=tran_ff_set_nmos\n")

        spice_file.write("Xwire_ff_tgate_2_out n_5_1 n_5_2 wire Rw=wire_ff_tgate_2_out_res Cw=wire_ff_tgate_2_out_cap\n")
        spice_file.write("Xinv_ff_cc2_1 n_5_2 n_6_1 n_vdd n_gnd inv Wn=inv_ff_cc2_1_nmos Wp=inv_ff_cc2_1_pmos\n")
        spice_file.write("Xinv_ff_cc2_2 n_6_1 n_5_2 n_vdd n_gnd inv Wn=inv_ff_cc2_2_nmos Wp=inv_ff_cc2_2_pmos\n")
        spice_file.write("Xwire_ff_cc2_out n_6_1 n_6_2 wire Rw=wire_ff_cc2_out_res Cw=wire_ff_cc2_out_cap\n\n")
        spice_file.write("* Output driver\n")
        spice_file.write("Xinv_ff_output_driver n_6_2 n_out n_vdd n_gnd inv Wn=inv_ff_output_driver_nmos Wp=inv_ff_output_driver_pmos\n\n")
        spice_file.write(".ENDS\n\n\n")
        
        # Create a list of all transistors used in this subcircuit
        tran_names_list = []
        tran_names_list.append("ptran_ff_input_select_nmos")
        tran_names_list.append("rest_ff_input_select_pmos")
        tran_names_list.append("inv_ff_input_1_nmos")
        tran_names_list.append("inv_ff_input_1_pmos")
        tran_names_list.append("tgate_ff_1_nmos")
        tran_names_list.append("tgate_ff_1_pmos")
        tran_names_list.append("tran_ff_set_n_pmos")
        tran_names_list.append("tran_ff_reset_nmos")
        tran_names_list.append("inv_ff_cc1_1_nmos")
        tran_names_list.append("inv_ff_cc1_1_pmos")
        tran_names_list.append("inv_ff_cc1_2_nmos")
        tran_names_list.append("inv_ff_cc1_2_pmos")
        tran_names_list.append("tgate_ff_2_nmos")
        tran_names_list.append("tgate_ff_2_pmos")
        tran_names_list.append("tran_ff_reset_n_pmos")
        tran_names_list.append("tran_ff_set_nmos")
        tran_names_list.append("inv_ff_cc2_1_nmos")
        tran_names_list.append("inv_ff_cc2_1_pmos")
        tran_names_list.append("inv_ff_cc2_2_nmos")
        tran_names_list.append("inv_ff_cc2_2_pmos")
        tran_names_list.append("inv_ff_output_driver_nmos")
        tran_names_list.append("inv_ff_output_driver_pmos")
        
        # Create a list of all wires used in this subcircuit
        wire_names_list = []
        wire_names_list.append("wire_ff_input_select")
        wire_names_list.append("wire_ff_input_out")
        wire_names_list.append("wire_ff_tgate_1_out")
        wire_names_list.append("wire_ff_cc1_out")
        wire_names_list.append("wire_ff_tgate_2_out")
        wire_names_list.append("wire_ff_cc2_out")
    
        return tran_names_list, wire_names_list
        
        
    def generate_ptran_d_ff(self, spice_filename: str, use_finfet: bool) -> Tuple[List[str], List[str]]:
        """ Generates a D Flip-Flop SPICE deck """
        
        # This script has to create the SPICE subcircuits required.
        # It has to return a list of the transistor names used as well as a list of the wire names used.
        
        # Open SPICE file for appending
        spice_file = open(spice_filename, 'a')
        
        # Create the FF circuit
        spice_file.write("******************************************************************************************\n")
        spice_file.write("* FF subcircuit \n")
        spice_file.write("******************************************************************************************\n")
        spice_file.write(".SUBCKT ff n_in n_out n_gate n_gate_n n_clk n_clk_n n_set n_set_n n_reset n_reset_n n_vdd n_gnd\n")
        spice_file.write("* FF input driver\n")
        spice_file.write("Xinv_ff_input n_1_2 n_2_1 n_vdd n_gnd inv Wn=inv_ff_input_1_nmos Wp=inv_ff_input_1_pmos\n\n")
        spice_file.write("* First T-gate and cross-coupled inverters\n") 
        spice_file.write("Xwire_ff_input_out n_2_1 n_2_2 wire Rw=wire_ff_input_out_res Cw=wire_ff_input_out_cap\n")    
        spice_file.write("Xtgate_ff_1 n_2_2 n_3_1 n_clk_n n_clk n_vdd n_gnd tgate Wn=tgate_ff_1_nmos Wp=tgate_ff_1_pmos\n")
        if not use_finfet :
            spice_file.write("MPtran_ff_set_n n_3_1 n_set_n n_vdd n_vdd pmos L=gate_length W=tran_ff_set_n_pmos\n")
            spice_file.write("MNtran_ff_reset n_3_1 n_reset n_gnd n_gnd nmos L=gate_length W=tran_ff_reset_nmos\n")
        else :
            spice_file.write("MPtran_ff_set_n n_3_1 n_set_n n_vdd n_vdd pmos L=gate_length nfin=tran_ff_set_n_pmos\n")
            spice_file.write("MNtran_ff_reset n_3_1 n_reset n_gnd n_gnd nmos L=gate_length nfin=tran_ff_reset_nmos\n")

        spice_file.write("Xwire_ff_tgate_1_out n_3_1 n_3_2 wire Rw=wire_ff_tgate_1_out_res Cw=wire_ff_tgate_1_out_cap\n")
        spice_file.write("Xinv_ff_cc1_1 n_3_2 n_4_1 n_vdd n_gnd inv Wn=inv_ff_cc1_1_nmos Wp=inv_ff_cc1_1_pmos\n")
        spice_file.write("Xinv_ff_cc1_2 n_4_1 n_3_2 n_vdd n_gnd inv Wn=inv_ff_cc1_2_nmos Wp=inv_ff_cc1_2_pmos\n")
        spice_file.write("Xwire_ff_cc1_out n_4_1 n_4_2 wire Rw=wire_ff_cc1_out_res Cw=wire_ff_cc1_out_cap\n\n")
        spice_file.write("* Second T-gate and cross-coupled inverters\n")
        spice_file.write("Xtgate_ff_2 n_4_2 n_5_1 n_clk n_clk_n n_vdd n_gnd tgate Wn=tgate_ff_2_nmos Wp=tgate_ff_2_pmos\n")
        if not use_finfet : 
            spice_file.write("MPtran_ff_reset_n n_5_1 n_reset_n n_vdd n_vdd pmos L=gate_length W=tran_ff_reset_n_pmos\n")
            spice_file.write("MNtran_ff_set n_5_1 n_set n_gnd n_gnd nmos L=gate_length W=tran_ff_set_nmos\n")
        else :
            spice_file.write("MPtran_ff_reset_n n_5_1 n_reset_n n_vdd n_vdd pmos L=gate_length W=tran_ff_reset_n_pmos\n")
            spice_file.write("MNtran_ff_set n_5_1 n_set n_gnd n_gnd nmos L=gate_length W=tran_ff_set_nmos\n")
        spice_file.write("Xwire_ff_tgate_2_out n_5_1 n_5_2 wire Rw=wire_ff_tgate_2_out_res Cw=wire_ff_tgate_2_out_cap\n")
        spice_file.write("Xinv_ff_cc2_1 n_5_2 n_6_1 n_vdd n_gnd inv Wn=inv_ff_cc2_1_nmos Wp=inv_ff_cc2_1_pmos\n")
        spice_file.write("Xinv_ff_cc2_2 n_6_1 n_5_2 n_vdd n_gnd inv Wn=inv_ff_cc2_2_nmos Wp=inv_ff_cc2_2_pmos\n")
        spice_file.write("Xwire_ff_cc2_out n_6_1 n_6_2 wire Rw=wire_ff_cc2_out_res Cw=wire_ff_cc2_out_cap\n\n")
        spice_file.write("* Output driver\n")
        spice_file.write("Xinv_ff_output_driver n_6_2 n_out n_vdd n_gnd inv Wn=inv_ff_output_driver_nmos Wp=inv_ff_output_driver_pmos\n\n")
        spice_file.write(".ENDS\n\n\n")
        
        # Create a list of all transistors used in this subcircuit
        tran_names_list = []
        tran_names_list.append("inv_ff_input_1_nmos")
        tran_names_list.append("inv_ff_input_1_pmos")
        tran_names_list.append("tgate_ff_1_nmos")
        tran_names_list.append("tgate_ff_1_pmos")
        tran_names_list.append("tran_ff_set_n_pmos")
        tran_names_list.append("tran_ff_reset_nmos")
        tran_names_list.append("inv_ff_cc1_1_nmos")
        tran_names_list.append("inv_ff_cc1_1_pmos")
        tran_names_list.append("inv_ff_cc1_2_nmos")
        tran_names_list.append("inv_ff_cc1_2_pmos")
        tran_names_list.append("tgate_ff_2_nmos")
        tran_names_list.append("tgate_ff_2_pmos")
        tran_names_list.append("tran_ff_reset_n_pmos")
        tran_names_list.append("tran_ff_set_nmos")
        tran_names_list.append("inv_ff_cc2_1_nmos")
        tran_names_list.append("inv_ff_cc2_1_pmos")
        tran_names_list.append("inv_ff_cc2_2_nmos")
        tran_names_list.append("inv_ff_cc2_2_pmos")
        tran_names_list.append("inv_ff_output_driver_nmos")
        tran_names_list.append("inv_ff_output_driver_pmos")
        
        # Create a list of all wires used in this subcircuit
        wire_names_list = []
        wire_names_list.append("wire_ff_input_out")
        wire_names_list.append("wire_ff_tgate_1_out")
        wire_names_list.append("wire_ff_cc1_out")
        wire_names_list.append("wire_ff_tgate_2_out")
        wire_names_list.append("wire_ff_cc2_out")
    
        return tran_names_list, wire_names_list

    def generate_tgate_2_input_select_d_ff(self, spice_filename: str, use_finfet: bool) -> Tuple[List[str], List[str]]:
        """ Generates a D Flip-Flop SPICE deck """
        
        # This script has to create the SPICE subcircuits required.
        # It has to return a list of the transistor names used as well as a list of the wire names used.
        
        # Open SPICE file for appending
        spice_file = open(spice_filename, 'a')
        
        # Create the FF circuit
        spice_file.write("******************************************************************************************\n")
        spice_file.write("* FF subcircuit \n")
        spice_file.write("******************************************************************************************\n")
        spice_file.write(".SUBCKT ff n_in n_out n_gate n_gate_n n_clk n_clk_n n_set n_set_n n_reset n_reset_n n_vdd n_gnd\n")
        spice_file.write("* Input selection MUX\n")

        spice_file.write("Xtgate_ff_input_select n_in n_1_1 n_gate n_gate_n n_vdd n_gnd tgate Wn=tgate_ff_input_select_nmos Wp=tgate_ff_input_select_pmos\n")
        
        spice_file.write("Xwire_ff_input_select n_1_1 n_1_2 wire Rw='wire_ff_input_select_res/2' Cw='wire_ff_input_select_cap/2'\n")
        spice_file.write("Xwire_ff_input_select_h n_1_2 n_1_3 wire Rw='wire_ff_input_select_res/2' Cw='wire_ff_input_select_cap/2'\n")

        spice_file.write("Xtgate_ff_input_select_h n_gnd n_1_3 n_gate_n n_gate n_vdd n_gnd tgate Wn=tgate_ff_input_select_nmos Wp=tgate_ff_input_select_pmos\n")
        # spice_file.write("Xrest_ff_input_select n_1_2 n_2_1 n_vdd n_gnd rest Wp=rest_ff_input_select_pmos\n")

        spice_file.write("Xinv_ff_input_1 n_1_2 n_2_1 n_vdd n_gnd inv Wn=inv_ff_input_1_nmos Wp=inv_ff_input_1_pmos\n\n")
        spice_file.write("* First T-gate and cross-coupled inverters\n") 
        spice_file.write("Xwire_ff_input_out n_2_1 n_2_2 wire Rw=wire_ff_input_out_res Cw=wire_ff_input_out_cap\n")    
        spice_file.write("Xtgate_ff_1 n_2_2 n_3_1 n_clk_n n_clk n_vdd n_gnd tgate Wn=tgate_ff_1_nmos Wp=tgate_ff_1_pmos\n")
        if not use_finfet :
            spice_file.write("MPtran_ff_set_n n_3_1 n_set_n n_vdd n_vdd pmos L=gate_length W=tran_ff_set_n_pmos\n")
            spice_file.write("MNtran_ff_reset n_3_1 n_reset n_gnd n_gnd nmos L=gate_length W=tran_ff_reset_nmos\n")
        else :
            spice_file.write("MPtran_ff_set_n n_3_1 n_set_n n_vdd n_vdd pmos L=gate_length nfin=tran_ff_set_n_pmos\n")
            spice_file.write("MNtran_ff_reset n_3_1 n_reset n_gnd n_gnd nmos L=gate_length nfin=tran_ff_reset_nmos\n")

        spice_file.write("Xwire_ff_tgate_1_out n_3_1 n_3_2 wire Rw=wire_ff_tgate_1_out_res Cw=wire_ff_tgate_1_out_cap\n")
        spice_file.write("Xinv_ff_cc1_1 n_3_2 n_4_1 n_vdd n_gnd inv Wn=inv_ff_cc1_1_nmos Wp=inv_ff_cc1_1_pmos\n")
        spice_file.write("Xinv_ff_cc1_2 n_4_1 n_3_2 n_vdd n_gnd inv Wn=inv_ff_cc1_2_nmos Wp=inv_ff_cc1_2_pmos\n")
        spice_file.write("Xwire_ff_cc1_out n_4_1 n_4_2 wire Rw=wire_ff_cc1_out_res Cw=wire_ff_cc1_out_cap\n\n")
        spice_file.write("* Second T-gate and cross-coupled inverters\n")
        spice_file.write("Xtgate_ff_2 n_4_2 n_5_1 n_clk n_clk_n n_vdd n_gnd tgate Wn=tgate_ff_2_nmos Wp=tgate_ff_2_pmos\n")
        if not use_finfet :
            spice_file.write("MPtran_ff_reset_n n_5_1 n_reset_n n_vdd n_vdd pmos L=gate_length W=tran_ff_reset_n_pmos\n")
            spice_file.write("MNtran_ff_set n_5_1 n_set n_gnd n_gnd nmos L=gate_length W=tran_ff_set_nmos\n")
        else :
            spice_file.write("MPtran_ff_reset_n n_5_1 n_reset_n n_vdd n_vdd pmos L=gate_length nfin=tran_ff_reset_n_pmos\n")
            spice_file.write("MNtran_ff_set n_5_1 n_set n_gnd n_gnd nmos L=gate_length nfin=tran_ff_set_nmos\n")

        spice_file.write("Xwire_ff_tgate_2_out n_5_1 n_5_2 wire Rw=wire_ff_tgate_2_out_res Cw=wire_ff_tgate_2_out_cap\n")
        spice_file.write("Xinv_ff_cc2_1 n_5_2 n_6_1 n_vdd n_gnd inv Wn=inv_ff_cc2_1_nmos Wp=inv_ff_cc2_1_pmos\n")
        spice_file.write("Xinv_ff_cc2_2 n_6_1 n_5_2 n_vdd n_gnd inv Wn=inv_ff_cc2_2_nmos Wp=inv_ff_cc2_2_pmos\n")
        spice_file.write("Xwire_ff_cc2_out n_6_1 n_6_2 wire Rw=wire_ff_cc2_out_res Cw=wire_ff_cc2_out_cap\n\n")
        spice_file.write("* Output driver\n")
        spice_file.write("Xinv_ff_output_driver n_6_2 n_out n_vdd n_gnd inv Wn=inv_ff_output_driver_nmos Wp=inv_ff_output_driver_pmos\n\n")
        spice_file.write(".ENDS\n\n\n")
        
        # Create a list of all transistors used in this subcircuit
        tran_names_list = []
        tran_names_list.append("tgate_ff_input_select_nmos")
        tran_names_list.append("tgate_ff_input_select_pmos")
        # tran_names_list.append("rest_ff_input_select_pmos")
        tran_names_list.append("inv_ff_input_1_nmos")
        tran_names_list.append("inv_ff_input_1_pmos")
        tran_names_list.append("tgate_ff_1_nmos")
        tran_names_list.append("tgate_ff_1_pmos")
        tran_names_list.append("tran_ff_set_n_pmos")
        tran_names_list.append("tran_ff_reset_nmos")
        tran_names_list.append("inv_ff_cc1_1_nmos")
        tran_names_list.append("inv_ff_cc1_1_pmos")
        tran_names_list.append("inv_ff_cc1_2_nmos")
        tran_names_list.append("inv_ff_cc1_2_pmos")
        tran_names_list.append("tgate_ff_2_nmos")
        tran_names_list.append("tgate_ff_2_pmos")
        tran_names_list.append("tran_ff_reset_n_pmos")
        tran_names_list.append("tran_ff_set_nmos")
        tran_names_list.append("inv_ff_cc2_1_nmos")
        tran_names_list.append("inv_ff_cc2_1_pmos")
        tran_names_list.append("inv_ff_cc2_2_nmos")
        tran_names_list.append("inv_ff_cc2_2_pmos")
        tran_names_list.append("inv_ff_output_driver_nmos")
        tran_names_list.append("inv_ff_output_driver_pmos")
        
        # Create a list of all wires used in this subcircuit
        wire_names_list = []
        wire_names_list.append("wire_ff_input_select")
        wire_names_list.append("wire_ff_input_out")
        wire_names_list.append("wire_ff_tgate_1_out")
        wire_names_list.append("wire_ff_cc1_out")
        wire_names_list.append("wire_ff_tgate_2_out")
        wire_names_list.append("wire_ff_cc2_out")
    
        return tran_names_list, wire_names_list
        
        
    def generate_tgate_d_ff(self, spice_filename: str, use_finfet: bool) -> Tuple[List[str], List[str]]:
        """ Generates a D Flip-Flop SPICE deck """
        
        # This script has to create the SPICE subcircuits required.
        # It has to return a list of the transistor names used as well as a list of the wire names used.
        
        # Open SPICE file for appending
        spice_file = open(spice_filename, 'a')
        
        # Create the FF circuit
        spice_file.write("******************************************************************************************\n")
        spice_file.write("* FF subcircuit \n")
        spice_file.write("******************************************************************************************\n")
        spice_file.write(".SUBCKT ff n_in n_out n_gate n_gate_n n_clk n_clk_n n_set n_set_n n_reset n_reset_n n_vdd n_gnd\n")
        spice_file.write("* FF input driver\n")
        spice_file.write("Xinv_ff_input n_1_2 n_2_1 n_vdd n_gnd inv Wn=inv_ff_input_1_nmos Wp=inv_ff_input_1_pmos\n\n")
        spice_file.write("* First T-gate and cross-coupled inverters\n") 
        spice_file.write("Xwire_ff_input_out n_2_1 n_2_2 wire Rw=wire_ff_input_out_res Cw=wire_ff_input_out_cap\n")    
        spice_file.write("Xtgate_ff_1 n_2_2 n_3_1 n_clk_n n_clk n_vdd n_gnd tgate Wn=tgate_ff_1_nmos Wp=tgate_ff_1_pmos\n")
        if not use_finfet :
            spice_file.write("MPtran_ff_set_n n_3_1 n_set_n n_vdd n_vdd pmos L=gate_length W=tran_ff_set_n_pmos\n")
            spice_file.write("MNtran_ff_reset n_3_1 n_reset n_gnd n_gnd nmos L=gate_length W=tran_ff_reset_nmos\n")
        else :
            spice_file.write("MPtran_ff_set_n n_3_1 n_set_n n_vdd n_vdd pmos L=gate_length nfin=tran_ff_set_n_pmos\n")
            spice_file.write("MNtran_ff_reset n_3_1 n_reset n_gnd n_gnd nmos L=gate_length nfin=tran_ff_reset_nmos\n")

        spice_file.write("Xwire_ff_tgate_1_out n_3_1 n_3_2 wire Rw=wire_ff_tgate_1_out_res Cw=wire_ff_tgate_1_out_cap\n")
        spice_file.write("Xinv_ff_cc1_1 n_3_2 n_4_1 n_vdd n_gnd inv Wn=inv_ff_cc1_1_nmos Wp=inv_ff_cc1_1_pmos\n")
        spice_file.write("Xinv_ff_cc1_2 n_4_1 n_3_2 n_vdd n_gnd inv Wn=inv_ff_cc1_2_nmos Wp=inv_ff_cc1_2_pmos\n")
        spice_file.write("Xwire_ff_cc1_out n_4_1 n_4_2 wire Rw=wire_ff_cc1_out_res Cw=wire_ff_cc1_out_cap\n\n")
        spice_file.write("* Second T-gate and cross-coupled inverters\n")
        spice_file.write("Xtgate_ff_2 n_4_2 n_5_1 n_clk n_clk_n n_vdd n_gnd tgate Wn=tgate_ff_2_nmos Wp=tgate_ff_2_pmos\n")
        if not use_finfet : 
            spice_file.write("MPtran_ff_reset_n n_5_1 n_reset_n n_vdd n_vdd pmos L=gate_length W=tran_ff_reset_n_pmos\n")
            spice_file.write("MNtran_ff_set n_5_1 n_set n_gnd n_gnd nmos L=gate_length W=tran_ff_set_nmos\n")
        else :
            spice_file.write("MPtran_ff_reset_n n_5_1 n_reset_n n_vdd n_vdd pmos L=gate_length W=tran_ff_reset_n_pmos\n")
            spice_file.write("MNtran_ff_set n_5_1 n_set n_gnd n_gnd nmos L=gate_length W=tran_ff_set_nmos\n")
        spice_file.write("Xwire_ff_tgate_2_out n_5_1 n_5_2 wire Rw=wire_ff_tgate_2_out_res Cw=wire_ff_tgate_2_out_cap\n")
        spice_file.write("Xinv_ff_cc2_1 n_5_2 n_6_1 n_vdd n_gnd inv Wn=inv_ff_cc2_1_nmos Wp=inv_ff_cc2_1_pmos\n")
        spice_file.write("Xinv_ff_cc2_2 n_6_1 n_5_2 n_vdd n_gnd inv Wn=inv_ff_cc2_2_nmos Wp=inv_ff_cc2_2_pmos\n")
        spice_file.write("Xwire_ff_cc2_out n_6_1 n_6_2 wire Rw=wire_ff_cc2_out_res Cw=wire_ff_cc2_out_cap\n\n")
        spice_file.write("* Output driver\n")
        spice_file.write("Xinv_ff_output_driver n_6_2 n_out n_vdd n_gnd inv Wn=inv_ff_output_driver_nmos Wp=inv_ff_output_driver_pmos\n\n")
        spice_file.write(".ENDS\n\n\n")
        
        # Create a list of all transistors used in this subcircuit
        tran_names_list = []
        tran_names_list.append("inv_ff_input_1_nmos")
        tran_names_list.append("inv_ff_input_1_pmos")
        tran_names_list.append("tgate_ff_1_nmos")
        tran_names_list.append("tgate_ff_1_pmos")
        tran_names_list.append("tran_ff_set_n_pmos")
        tran_names_list.append("tran_ff_reset_nmos")
        tran_names_list.append("inv_ff_cc1_1_nmos")
        tran_names_list.append("inv_ff_cc1_1_pmos")
        tran_names_list.append("inv_ff_cc1_2_nmos")
        tran_names_list.append("inv_ff_cc1_2_pmos")
        tran_names_list.append("tgate_ff_2_nmos")
        tran_names_list.append("tgate_ff_2_pmos")
        tran_names_list.append("tran_ff_reset_n_pmos")
        tran_names_list.append("tran_ff_set_nmos")
        tran_names_list.append("inv_ff_cc2_1_nmos")
        tran_names_list.append("inv_ff_cc2_1_pmos")
        tran_names_list.append("inv_ff_cc2_2_nmos")
        tran_names_list.append("inv_ff_cc2_2_pmos")
        tran_names_list.append("inv_ff_output_driver_nmos")
        tran_names_list.append("inv_ff_output_driver_pmos")
        
        # Create a list of all wires used in this subcircuit
        wire_names_list = []
        wire_names_list.append("wire_ff_input_out")
        wire_names_list.append("wire_ff_tgate_1_out")
        wire_names_list.append("wire_ff_cc1_out")
        wire_names_list.append("wire_ff_tgate_2_out")
        wire_names_list.append("wire_ff_cc2_out")
    
        return tran_names_list, wire_names_list

    # Generate FF with optional register select
    def generate(self, subcircuit_filename: str) -> Dict[str, int | float]:
        if self.register_select == 'z':
            print("Generating FF")
            if not self.use_tgate :
                self.transistor_names, self.wire_names = self.generate_ptran_d_ff(subcircuit_filename, self.use_finfet)
            else :
                self.transistor_names, self.wire_names = self.generate_tgate_d_ff(subcircuit_filename, self.use_finfet)

        else:
            print("Generating FF with register select on BLE input " + self.register_select)
            if not self.use_tgate :
                self.transistor_names, self.wire_names = self.generate_ptran_2_input_select_d_ff(subcircuit_filename, self.use_finfet)
            else :
                self.transistor_names, self.wire_names = self.generate_tgate_2_input_select_d_ff(subcircuit_filename, self.use_finfet)

        # Give initial transistor sizes
        if self.register_select:
            # These only exist if there is a register select MUX
            if not self.use_tgate :
                self.initial_transistor_sizes["ptran_ff_input_select_nmos"] = 4
                self.initial_transistor_sizes["rest_ff_input_select_pmos"] = 1
            else :
                self.initial_transistor_sizes["tgate_ff_input_select_nmos"] = 4
                self.initial_transistor_sizes["tgate_ff_input_select_pmos"] = 4

        # These transistors always exists regardless of register select
        if not self.use_finfet :
            self.initial_transistor_sizes["inv_ff_input_1_nmos"] = 3
            self.initial_transistor_sizes["inv_ff_input_1_pmos"] = 8.2
            self.initial_transistor_sizes["tgate_ff_1_nmos"] = 1
            self.initial_transistor_sizes["tgate_ff_1_pmos"] = 1
            self.initial_transistor_sizes["tran_ff_set_n_pmos"] = 1
            self.initial_transistor_sizes["tran_ff_reset_nmos"] = 1
            self.initial_transistor_sizes["inv_ff_cc1_1_nmos"] = 3
            self.initial_transistor_sizes["inv_ff_cc1_1_pmos"] = 4
            self.initial_transistor_sizes["inv_ff_cc1_2_nmos"] = 1
            self.initial_transistor_sizes["inv_ff_cc1_2_pmos"] = 1.3
            self.initial_transistor_sizes["tgate_ff_2_nmos"] = 1
            self.initial_transistor_sizes["tgate_ff_2_pmos"] = 1
            self.initial_transistor_sizes["tran_ff_reset_n_pmos"] = 1
            self.initial_transistor_sizes["tran_ff_set_nmos"] = 1
            self.initial_transistor_sizes["inv_ff_cc2_1_nmos"] = 1
            self.initial_transistor_sizes["inv_ff_cc2_1_pmos"] = 1.3
            self.initial_transistor_sizes["inv_ff_cc2_2_nmos"] = 1
            self.initial_transistor_sizes["inv_ff_cc2_2_pmos"] = 1.3
            self.initial_transistor_sizes["inv_ff_output_driver_nmos"] = 4
            self.initial_transistor_sizes["inv_ff_output_driver_pmos"] = 9.7
        else :
            self.initial_transistor_sizes["inv_ff_input_1_nmos"] = 3
            self.initial_transistor_sizes["inv_ff_input_1_pmos"] = 9
            self.initial_transistor_sizes["tgate_ff_1_nmos"] = 1
            self.initial_transistor_sizes["tgate_ff_1_pmos"] = 1
            self.initial_transistor_sizes["tran_ff_set_n_pmos"] = 1
            self.initial_transistor_sizes["tran_ff_reset_nmos"] = 1
            self.initial_transistor_sizes["inv_ff_cc1_1_nmos"] = 3
            self.initial_transistor_sizes["inv_ff_cc1_1_pmos"] = 4
            self.initial_transistor_sizes["inv_ff_cc1_2_nmos"] = 1
            self.initial_transistor_sizes["inv_ff_cc1_2_pmos"] = 2
            self.initial_transistor_sizes["tgate_ff_2_nmos"] = 1
            self.initial_transistor_sizes["tgate_ff_2_pmos"] = 1
            self.initial_transistor_sizes["tran_ff_reset_n_pmos"] = 1
            self.initial_transistor_sizes["tran_ff_set_nmos"] = 1
            self.initial_transistor_sizes["inv_ff_cc2_1_nmos"] = 1
            self.initial_transistor_sizes["inv_ff_cc2_1_pmos"] = 2
            self.initial_transistor_sizes["inv_ff_cc2_2_nmos"] = 1
            self.initial_transistor_sizes["inv_ff_cc2_2_pmos"] = 2
            self.initial_transistor_sizes["inv_ff_output_driver_nmos"] = 4
            self.initial_transistor_sizes["inv_ff_output_driver_pmos"] = 10

        return self.initial_transistor_sizes


    def update_area(self, area_dict: Dict[str, float], width_dict: Dict[str, float]) -> float:
        """ Calculate FF area and update dictionaries. """
        
        area = 0.0
        
        # Calculates area of the FF input select if applicable (we add the SRAM bit later)
        # If there is no input select, we just add the area of the input inverter
        if self.register_select != 'z':
            if not self.use_tgate :
                area += (2*area_dict["ptran_ff_input_select"] +
                        area_dict["rest_ff_input_select"] +
                        area_dict["inv_ff_input_1"])
            else :
                area += (2*area_dict["tgate_ff_input_select"] +
                        area_dict["inv_ff_input_1"])
        else:
            area += area_dict["inv_ff_input_1"]

        # Add area of FF circuitry
        area += (area_dict["tgate_ff_1"] +
                area_dict["tran_ff_set_n"] +
                area_dict["tran_ff_reset"] +
                area_dict["inv_ff_cc1_1"] +
                area_dict["inv_ff_cc1_2"] +
                area_dict["tgate_ff_2"] +
                area_dict["tran_ff_reset_n"] +
                area_dict["tran_ff_set"] +
                area_dict["inv_ff_cc2_1"] +
                area_dict["inv_ff_cc2_2"]+
                area_dict["inv_ff_output_driver"])        

        # Add the SRAM bit if FF input select is on
        if self.register_select != 'z':
            area += area_dict["sram"]
        
        # Calculate width and add to dictionaries
        width = math.sqrt(area)
        area_dict["ff"] = area
        width_dict["ff"] = width
        
        return area
        
        
    def update_wires(self, width_dict: Dict[str, float], wire_lengths: Dict[str, float], wire_layers: Dict[str, float]) -> List[str]:
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """
        
        # TODO get these keys from self.wire_names and assert we update all of them

        # Update wire lengths
        if self.register_select != 'z':
            if not self.use_tgate :
                wire_lengths["wire_ff_input_select"] = width_dict["ptran_ff_input_select"]
            else :
                wire_lengths["wire_ff_input_select"] = width_dict["tgate_ff_input_select"]
            
        wire_lengths["wire_ff_input_out"] = (width_dict["inv_ff_input_1"] + width_dict["tgate_ff_1"])/4
        wire_lengths["wire_ff_tgate_1_out"] = (width_dict["tgate_ff_1"] + width_dict["inv_ff_cc1_1"])/4
        wire_lengths["wire_ff_cc1_out"] = (width_dict["inv_ff_cc1_1"] + width_dict["tgate_ff_2"])/4
        wire_lengths["wire_ff_tgate_2_out"] = (width_dict["tgate_ff_2"] + width_dict["inv_ff_cc1_2"])/4
        wire_lengths["wire_ff_cc2_out"] = (width_dict["inv_ff_cc1_2"] + width_dict["inv_ff_output_driver"])/4
    
        # Update wire layers
        if self.register_select != 'z':
            wire_layers["wire_ff_input_select"] = consts.LOCAL_WIRE_LAYER 
            
        wire_layers["wire_ff_input_out"] = consts.LOCAL_WIRE_LAYER 
        wire_layers["wire_ff_tgate_1_out"] = consts.LOCAL_WIRE_LAYER 
        wire_layers["wire_ff_cc1_out"] = consts.LOCAL_WIRE_LAYER 
        wire_layers["wire_ff_tgate_2_out"] = consts.LOCAL_WIRE_LAYER 
        wire_layers["wire_ff_cc2_out"] = consts.LOCAL_WIRE_LAYER 

    
    def print_details(self):
        print("  FF DETAILS:")
        if self.register_select == 'z':
            print("  Register select: None")
        else:
            print("  Register select: BLE input " + self.register_select)


@dataclass
class LUTOutputLoad(c_ds.LoadCircuit):
    """ LUT output load is the load seen by the output of the LUT in the basic case if Or = 1 and Ofb = 1 (see [1])
            then the output load will be the regster select mux of the flip-flop, the mux connecting the output signal
            to the output routing and the mux connecting the output signal to the feedback mux """
    name: str = "lut_output_load"
    # For below two values, each of them determine how many 2:1 muxes are created taking inputs from output of FF and output of LUT
    num_local_outputs: int = None # Number of local outputs (feedback to cluster local mux)
    num_general_outputs: int = None # Number of outputs to Switch Block Muxes (SB muxes)

    # Child Subckts
    ble_outputs: BLE = None

    def __hash__(self) -> int:
        return super().__hash__()
    
    def __post_init__(self):
        super().__post_init__()

    def generate_lut_output_load(self, spice_filename: str) -> List[str]:
        """ Create the LUT output load subcircuit. It consists of a FF which 
            has the register select mux at its input and all BLE outputs which 
            include the output routing mux (Or) and the output feedback mux (Ofb) """
        # TODO update this for multi ckt support

        # Total number of BLE outputs
        total_outputs = self.num_local_outputs + self.num_general_outputs

        # Open SPICE file for appending
        spice_file = open(spice_filename, 'a')
        
        spice_file.write("******************************************************************************************\n")
        spice_file.write("* LUT output load\n")
        spice_file.write("******************************************************************************************\n")
        spice_file.write(f".SUBCKT {self.sp_name} n_in n_local_out n_general_out n_gate n_gate_n n_vdd n_gnd n_vdd_local_output_on n_vdd_general_output_on\n")
        spice_file.write("Xwire_lut_output_load_1 n_in n_1_1 wire Rw='wire_lut_output_load_1_res' Cw='wire_lut_output_load_1_cap'\n")
        spice_file.write("Xff n_1_1 n_hang1 n_gate n_gate_n n_vdd n_gnd n_gnd n_vdd n_gnd n_vdd n_vdd n_gnd ff\n")
        spice_file.write("Xwire_lut_output_load_2 n_1_1 n_1_2 wire Rw='wire_lut_output_load_2_res' Cw='wire_lut_output_load_2_cap'\n")
        spice_file.write(f"Xble_outputs n_1_2 n_local_out n_general_out n_gate n_gate_n n_vdd n_gnd n_vdd_local_output_on n_vdd_general_output_on {self.ble_outputs.sp_name}\n")
        spice_file.write(".ENDS\n\n\n")

        spice_file.close()
        
        # Create a list of all wires used in this subcircuit
        wire_names_list = []
        wire_names_list.append("wire_lut_output_load_1")
        wire_names_list.append("wire_lut_output_load_2")
        
        return wire_names_list
        
    def generate(self, subcircuit_filename: str):
        print("Generating LUT output load")
        self.wire_names = self.generate_lut_output_load(subcircuit_filename)
        
     
    def update_wires(self,width_dict: Dict[str, float], wire_lengths: Dict[str, float], wire_layers: Dict[str, float]) -> List[str]:
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """
        
        # Update wire lengths
        wire_lengths["wire_lut_output_load_1"] = (width_dict["ff"] + width_dict["lut_and_drivers"]) / 8
        wire_lengths["wire_lut_output_load_2"] = width_dict["ff"]
        
        # Update wire layers
        wire_layers["wire_lut_output_load_1"] = consts.LOCAL_WIRE_LAYER
        wire_layers["wire_lut_output_load_2"] = consts.LOCAL_WIRE_LAYER


@dataclass
class FlutMux(mux.Mux2to1):
    name: str = "flut_mux"

    delay_weight: float = consts.DELAY_WEIGHT_LUT_FRAC
    # Circuit Dependencies
    lut: lut_lib.LUT = None # used in update_wires
    
    def __hash__(self) -> int:
        return super().__hash__()
    
    def __post_init__(self):
        super().__post_init__()

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
        
        self.wire_names.append("wire_lut_to_flut_mux") # TODO update for multi ckt support
        # Will be dict of ints if FinFET or discrete Tx, can be floats if bulk
        return self.initial_transistor_sizes

    def update_wires(self, width_dict: Dict[str, float], wire_lengths: Dict[str, float], wire_layers: Dict[str, float]) -> List[str]:
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """
        super().update_wires(width_dict, wire_lengths, wire_layers)

        # Update wire lengths
        wire_lengths["wire_lut_to_flut_mux"] = width_dict[self.lut.name] #TODO change to sp_name
        
        # Update wire layers
        wire_layers["wire_lut_to_flut_mux"] = consts.LOCAL_WIRE_LAYER
    
@dataclass
class FlutMuxTB(c_ds.SimTB):
    lut: lut_lib.LUT = None
    flut_mux: FlutMux = None
    cc: cc_lib.CarryChain = None # Used to find wire length key
    cc_mux: cc_lib.CarryChainMux = None
    lut_output_load: LUTOutputLoad = None
    gen_ble_output_load: gen_r_load_lib.GeneralBLEOutputLoad = None

    subckt_lib: InitVar[Dict[str, rg_ds.SpSubCkt]] = None
    
    # Initialized in __post_init__
    dut_ckt: FlutMux = None
    local_out_node: str = None
    general_out_node: str = None

    def __hash__(self):
        return super().__hash__()
    def __post_init__(self, subckt_lib: Dict[str, rg_ds.SpSubCkt]):
        super().__post_init__()
        # Make sure its valid
        assert self.cc_mux or self.lut_output_load, "Must have either a carry chain mux or lut output load"

        self.meas_points = []
        pwr_v_node: str = "vdd_flut_mux"
        # node definitions
        self.local_out_node: str = "n_local_out"
        self.general_out_node: str = "n_general_out"
        # DUT DC Voltage Source
        self.dut_dc_vsrc: c_ds.SpVoltageSrc = c_ds.SpVoltageSrc(
            name = "_FLUX_MUX",
            out_node = pwr_v_node,
            init_volt = c_ds.Value(name = self.supply_v_param),
        )
        # Initialize the DUT 
        self.dut_ckt = self.flut_mux
        # LUT conditionals
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
        
        cur_top_insts: List[rg_ds.SpSubCktInst] = [
            # LUT
            rg_ds.SpSubCktInst(
                name = f"X{self.lut.name}", # TODO update to sp_name
                subckt = subckt_lib[self.lut.name], # TODO update to sp_name
                conns = lut_conns,
            ),
            # lut -> flut wire
            rg_ds.SpSubCktInst(
                name = f"Xwire_{self.flut_mux.sp_name}",
                subckt = subckt_lib["wire"],
                conns = {
                    "n_in": "n_1_1",
                    "n_out": "n_1_2",
                },
                param_values = {
                    "Rw": "wire_lut_to_flut_mux_res",
                    "Cw": "wire_lut_to_flut_mux_cap",
                }
            ),
            # FLUT Mux
            rg_ds.SpSubCktInst(
                name = f"X{self.flut_mux.sp_name}",
                subckt = subckt_lib[self.flut_mux.sp_name],
                conns = {
                   "n_in": "n_1_2", 
                    "n_out": "n_1_3",
                    "n_gate": self.vdd_node,
                    "n_gate_n": self.gnd_node,
                    "n_vdd": pwr_v_node,
                    "n_gnd": self.gnd_node, 
                }
            )
        ]
        # If cc_mux was passed in carry chain assumed to be enabled
        if self.cc_mux:
            cur_top_insts += [
                # flut -> cc_mux wire
                rg_ds.SpSubCktInst(
                    name = f"Xwire_{self.cc_mux.sp_name}",
                    subckt = subckt_lib["wire"],
                    conns = {
                        "n_in": "n_1_3",
                        "n_out": "n_1_4",
                    },
                    param_values = {
                        "Rw": f"wire_{self.cc.sp_name}_5_res",
                        "Cw": f"wire_{self.cc.sp_name}_5_cap",
                    }
                ),
                # CC Mux
                rg_ds.SpSubCktInst(
                    name = f"X{self.cc_mux.sp_name}",
                    subckt = subckt_lib[self.cc_mux.sp_name],
                    conns = {
                        "n_in": "n_1_4", 
                        "n_out": self.local_out_node,
                        "n_gate": self.vdd_node,
                        "n_gate_n": self.gnd_node,
                        "n_vdd": self.vdd_node,
                        "n_gnd": self.gnd_node, 
                    }
                )
            ]
        # If no carry chain we load with lut output load
        elif self.lut_output_load:
            cur_top_insts += [
                rg_ds.SpSubCktInst(
                    name = f"X{self.lut_output_load.sp_name}",
                    subckt = subckt_lib[self.lut_output_load.sp_name],
                    conns = {
                        "n_in": "n_1_4",
                        "n_local_out": self.local_out_node,
                        "n_general_out": self.general_out_node, 
                        "n_gate": self.sram_vdd_node,
                        "n_gate_n": self.sram_vss_node,
                        "n_vdd": self.vdd_node,
                        "n_gnd": self.gnd_node,
                        "n_vdd_local_output_on": self.vdd_node,
                        "n_vdd_general_output_on": self.vdd_node,
                    }
                ),
            ]
        # After cc mux conditional we attach a general_ble_output_load
        self.top_insts = cur_top_insts + [
            # GENERAL BLE OUTPUT LOAD
            rg_ds.SpSubCktInst(
                name = f"X{self.gen_ble_output_load.sp_name}",
                subckt = subckt_lib[self.gen_ble_output_load.sp_name],
                conns = {
                    "n_1_1": self.general_out_node, # TODO figure this out, node only driven when carry chain enabled
                    "n_out": "n_hang_1",
                    "n_gate": self.sram_vdd_node,
                    "n_gate_n": self.sram_vss_node,
                    "n_vdd": self.vdd_node,
                    "n_gnd": self.gnd_node,
                }
            ), 
        ]
    def generate_top(self):
        dut_sp_name: str = self.dut_ckt.sp_name
        # meas paths
        flut_mux_inv_1_out_node: str = ".".join(
            [f"X{self.flut_mux.sp_name}", "n_2_1"]
        )
        flut_mux_inv_2_out_node: str = self.local_out_node
        delay_names: List[str] = [
            f"inv_{dut_sp_name}_1",
            f"inv_{dut_sp_name}_2",
            f"total",
        ]
        targ_nodes: List[str] = [
            flut_mux_inv_1_out_node,
            flut_mux_inv_2_out_node,
            flut_mux_inv_2_out_node,
        ]
        trig_node: str = "n_1_2"
        # Base class generate top does all common functionality 
        return super().generate_top(
            delay_names = delay_names,
            trig_node = trig_node, 
            targ_nodes = targ_nodes,
            low_v_node = self.general_out_node,
        )




@dataclass
class BLE(c_ds.CompoundCircuit):
    name: str = "ble"
    cluster_size: int = None # Number of BLEs per Cluster
    num_lut_inputs: int = None # Size of a LUT
    num_local_outputs: int = None # Number of feedback outputs
    num_general_outputs: int = None # Number of general outputs

    # Transistor Parameters
    use_tgate: bool = None
    use_finfet: bool = None

    # BLE Parameters
    use_fluts: bool = None
    Rsel: str = None
    Rfb: str = None
    enable_carry_chain: bool = None
    FAs_per_flut: int = None
    carry_skip_periphery_count: int = None

    # Circuits
    local_output: LocalBLEOutput = None
    general_output: GeneralBLEOutput = None
    lut: lut_lib.LUT = None
    ff: FlipFlop = None
    lut_output_load: LUTOutputLoad = None
    fmux: FlutMux = None
    # Carry Chain
    cc_mux: cc_lib.CarryChainMux = None
    cc: cc_lib.CarryChain = None
    cc_skip_and: cc_lib.CarryChainSkipAnd = None
    cc_skip_mux: cc_lib.CarryChainSkipMux = None
    # Local Mux (required by lut input area calculation)
    local_mux: lb_lib.LocalMux = None

    def __hash__(self) -> int:
        return super().__hash__()

    def __post_init__(self):
        # TODO update this to be consistent, this is weird case where base name is different from sp_name
        self.sp_name = f"ble_outputs_{self.get_param_str()}" 
        # super().__post_init__()
        # Local BLE output Mux (2:1) going from FF & LUT output feeding back to local mux
        self.local_output = LocalBLEOutput(
            id = 0,
            use_tgate = self.use_tgate
        )
        # General BLE output Mux (2:1) going from FF & LUT output feeding to SB muxes
        self.general_output = GeneralBLEOutput(
            id = 0,
            use_tgate = self.use_tgate
        )
        # Flip Flop 
        self.ff = FlipFlop(
            id = 0,
            register_select = self.Rsel,
            use_tgate = self.use_tgate
        )
        # Load Circuit on output of lut
        self.lut_output_load = LUTOutputLoad(
            id = 0,
            num_local_outputs = self.num_local_outputs,
            num_general_outputs = self.num_general_outputs,
            ble_outputs = self,
        )
        # LUT
        self.lut = lut_lib.LUT(
            id = 0,
            K = self.num_lut_inputs,
            Rfb = self.Rfb,
            Rsel = self.Rsel,
            use_finfet = self.use_finfet,
            use_fluts = self.use_fluts,
            use_tgate = self.use_tgate,
            local_mux = self.local_mux,
        )
        # Fracturable LUT mux (2:1)
        if self.use_fluts:
            self.fmux = FlutMux(
                id = 0,
                use_tgate = self.use_tgate,
                lut = self.lut
            )

    def generate_ble_outputs(self, spice_filename: str) -> List[str]:
        """ Create the BLE outputs block. Contains 'num_local_out' local outputs and 'num_gen_out' general outputs. """
        
        #TODO: The order of the wires is weird in this netlist, have a look at it later.
        # Total number of BLE outputs
        total_outputs = self.num_local_outputs + self.num_general_outputs
        

        subckt_local_ble_output_name = f"{self.local_output.sp_name}" # f"local_ble_output_wire_uid{self.gen_r_wire['id']}"
        subckt_general_ble_output_name = f"{self.general_output.sp_name}" #f"general_ble_output_wire_uid{self.gen_r_wire['id']}"
        # Typically the param string coming from the gen_ble_output load is coming from ON SB loading it
        wire_gen_ble_outputs = f"wire_ble_outputs_{self.get_param_str()}"
        # wire_gen_ble_outputs = f"wire_ble_outputs_wire_uid{self.gen_r_wire['id']}"

        # Open SPICE file for appending
        spice_file = open(spice_filename, 'a')
        
        spice_file.write("******************************************************************************************\n")
        spice_file.write("* BLE outputs\n")
        spice_file.write("******************************************************************************************\n")
        spice_file.write(f".SUBCKT {self.sp_name} n_1_" + str(int((total_outputs + 1)/2)+1) + " n_local_out n_general_out n_gate n_gate_n n_vdd n_gnd n_vdd_local_output_on n_vdd_general_output_on\n")
        # Create the BLE output bar
        current_node = 2
        for i in range(self.num_local_outputs):
            #if it is the first 2:1 local ble feedback mux then attach the n_local_out signal to its output else assign a random signal to it
            if i == 0:
                spice_file.write("Xlocal_ble_output_" + str(i+1) + " n_1_" + str(current_node) + f" n_local_out n_gate n_gate_n n_vdd_local_output_on n_gnd {subckt_local_ble_output_name}\n")
            else:
                spice_file.write("Xlocal_ble_output_" + str(i+1) + " n_1_" + str(current_node) + " n_hang_" + str(current_node) + f" n_gate n_gate_n n_vdd n_gnd {subckt_local_ble_output_name}\n")
            spice_file.write("Xwire_ble_outputs_" + str(i+1) + " n_1_" + str(current_node) + " n_1_" + str(current_node + 1) + f" wire Rw='{wire_gen_ble_outputs}_res/" + str(total_outputs-1) + f"' Cw='{wire_gen_ble_outputs}_cap/" + str(total_outputs-1) + "'\n")
            current_node = current_node + 1
        for i in range(self.num_general_outputs):
            #if it is the first 2:1 general ble output mux then attach the n_general_out signal to its output else assign a random signal to it
            if i == 0:
                spice_file.write("Xgeneral_ble_output_" + str(i+1) + " n_1_" + str(current_node) + f" n_general_out n_gate n_gate_n n_vdd_general_output_on n_gnd {subckt_general_ble_output_name}\n")
            else:
                spice_file.write("Xgeneral_ble_output_" + str(i+1) + " n_1_" + str(current_node) + f" n_hang_" + str(current_node) + f" n_gate n_gate_n n_vdd n_gnd {subckt_general_ble_output_name}\n")
            # Only add wire if this is not the last ble output.
            if (i+1) != self.num_general_outputs:
                spice_file.write("Xwire_ble_outputs_" + str(self.num_local_outputs+i+1) + " n_1_" + str(current_node) + " n_1_" + str(current_node + 1) + f" wire Rw='{wire_gen_ble_outputs}_res/" + str(total_outputs-1) + f"' Cw='{wire_gen_ble_outputs}_cap/" + str(total_outputs-1) + "'\n")
            current_node = current_node + 1
        spice_file.write(".ENDS\n\n\n")

        spice_file.close()
        
        # Create a list of all wires used in this subcircuit
        wire_names_list = []
        wire_names_list.append(wire_gen_ble_outputs)
        
        return wire_names_list
        
    def generate(self, subcircuit_filename: str, min_tran_width) -> Dict[str, int | float]:
        print("Generating BLE")
        
        # Generate LUT and FF
        init_tran_sizes = {}
        init_tran_sizes.update(self.lut.generate(subcircuit_filename, min_tran_width))
        init_tran_sizes.update(self.ff.generate(subcircuit_filename))

        # Generate BLE outputs
        init_tran_sizes.update(
            self.local_output.generate(subcircuit_filename)
        )
        init_tran_sizes.update(
            self.general_output.generate(subcircuit_filename)
        )
        # for gen_output in self.general_outputs:
        #     init_tran_sizes.update(gen_output.generate(subcircuit_filename, 
        #                                                 min_tran_width))
        self.wire_names = self.generate_ble_outputs(subcircuit_filename)
 
        #flut mux
        if self.use_fluts:
            init_tran_sizes.update(
                self.fmux.generate(subcircuit_filename)
            )           
        # Generate LUT load
        self.lut_output_load.generate(subcircuit_filename)
       
        return init_tran_sizes
    
    def update_area(self, area_dict: Dict[str, float], width_dict: Dict[str, float]):

        ff_area = self.ff.update_area(area_dict, width_dict)

        if self.use_fluts:
            fmux_area = self.fmux.update_area(area_dict, width_dict) 
            fmux_width = math.sqrt(fmux_area)
            area_dict["flut_mux"] = fmux_area
            width_dict["flut_mux"] = fmux_width    

        lut_area = self.lut.update_area(area_dict, width_dict)

        # Calculate area of BLE outputs
        local_ble_output_area = self.num_local_outputs * self.local_output.update_area(area_dict, width_dict)
        general_ble_output_area = self.num_general_outputs * self.general_output.update_area(area_dict, width_dict)
        
        ble_output_area = local_ble_output_area + general_ble_output_area
        ble_output_width = math.sqrt(ble_output_area)
        area_dict["ble_output"] = ble_output_area
        width_dict["ble_output"] = ble_output_width

        if self.use_fluts:
            ble_area = lut_area + 2 * ff_area + ble_output_area # + fmux_area
        else:
            ble_area = lut_area + ff_area + ble_output_area

        if self.enable_carry_chain == 1:
            ble_area = ble_area + area_dict[self.cc.sp_name] * self.FAs_per_flut + (self.FAs_per_flut) * area_dict[self.cc_mux.sp_name]
            if self.carry_skip_periphery_count != 0:
                ble_area = ble_area + ((area_dict[self.cc_skip_and.sp_name] + area_dict[self.cc_skip_mux.sp_name]) * self.carry_skip_periphery_count) / self.cluster_size

        ble_width = math.sqrt(ble_area)
        area_dict["ble"] = ble_area
        width_dict["ble"] = ble_width

    def update_wires(self, width_dict: Dict[str, float], wire_lengths: Dict[str, float], wire_layers: Dict[str, int], lut_ratio: float):
        """ Update wire of member objects. """
        
        # Filter wire names list to get the name of ble_output_wire (with any parameters added to suffix)
        
        ble_outputs_wire_key = rg_utils.get_unique_obj(
            self.wire_names,
            rg_utils.str_match_condition,
            "wire_ble_outputs", 
        )
        # ble_outputs_wire_key = [ wire_name for wire_name in self.wire_names if "wire_ble_outputs" in wire_name][0]

        # Assert keys exist in wire_names, unneeded but following convension if wire keys not coming from wire_names
        assert ble_outputs_wire_key in self.wire_names

        # Update lut and ff wires.
        self.lut.update_wires(width_dict, wire_lengths, wire_layers, lut_ratio)
        self.ff.update_wires(width_dict, wire_lengths, wire_layers)
        
        # Update BLE output wires
        self.local_output.update_wires(width_dict, wire_lengths, wire_layers)
        self.general_output.update_wires(width_dict, wire_lengths, wire_layers)
        
        # Wire connecting all BLE output mux-inputs together
        wire_lengths[ble_outputs_wire_key] = (
            self.num_local_outputs * width_dict[self.local_output.sp_name] 
                + self.num_general_outputs * width_dict[self.general_output.sp_name]
        )
        wire_layers[ble_outputs_wire_key] = consts.LOCAL_WIRE_LAYER

        # Update LUT load wires
        self.lut_output_load.update_wires(width_dict, wire_lengths, wire_layers)

        # Fracturable luts:
        if self.use_fluts:
            self.fmux.update_wires(width_dict, wire_lengths, wire_layers)
        
        
    def print_details(self, report_file):
    
        self.lut.print_details(report_file)
     
