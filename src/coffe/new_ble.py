from __future__ import annotations
from dataclasses import dataclass, field, InitVar

import math, os, sys
from typing import List, Dict, Any, Tuple, Union, Type

import src.coffe.data_structs as c_ds
import src.coffe.utils as utils

import src.coffe.mux as mux

import src.coffe.new_fpga as fpga



# This is a mux but it doesn't inherit from Mux because it's a simple 2:1
@dataclass
class LocalBLEOutput(mux.Mux2to1):
    name: str = "local_ble_output"
    delay_weight: float = fpga.DELAY_WEIGHT_LOCAL_BLE_OUTPUT
    
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
class GeneralBLEOutput(mux.Mux2to1):
    name: str = "general_ble_output"
    delay_weight: float = fpga.DELAY_WEIGHT_GENERAL_BLE_OUTPUT

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

    def __post__init__(self):
        # Initialize times to basically NULL for the cost function == 1
        if self.t_setup is None:
            self.t_setup = 1
        if self.t_clk_to_q is None:
            self.t_clk_to_q = 1
        

    def generate_ptran_2_input_select_d_ff(spice_filename: str, use_finfet: bool) -> Tuple[List[str], List[str]]:
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
        
        
    def generate_ptran_d_ff(spice_filename: str, use_finfet: bool) -> Tuple[List[str], List[str]]:
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

    def generate_tgate_2_input_select_d_ff(spice_filename: str, use_finfet: bool) -> Tuple[List[str], List[str]]:
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
        
        
    def generate_tgate_d_ff(spice_filename: str, use_finfet: bool) -> Tuple[List[str], List[str]]:
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
            wire_layers["wire_ff_input_select"] = fpga.LOCAL_WIRE_LAYER 
            
        wire_layers["wire_ff_input_out"] = fpga.LOCAL_WIRE_LAYER 
        wire_layers["wire_ff_tgate_1_out"] = fpga.LOCAL_WIRE_LAYER 
        wire_layers["wire_ff_cc1_out"] = fpga.LOCAL_WIRE_LAYER 
        wire_layers["wire_ff_tgate_2_out"] = fpga.LOCAL_WIRE_LAYER 
        wire_layers["wire_ff_cc2_out"] = fpga.LOCAL_WIRE_LAYER 

    
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
