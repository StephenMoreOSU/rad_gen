
from src.coffe.circuit_baseclasses import _SizableCircuit, _CompoundCircuit
import src.coffe.fpga as fpga

import src.coffe.mux_subcircuits as mux_subcircuits
import src.coffe.ff_subcircuits as ff_subcircuits
import src.coffe.load_subcircuits as load_subcircuits

import src.coffe.utils as utils

from src.coffe.lut import _LUT
# CIRC IMPORT ERROR
# from src.coffe.logic_block import _LocalBLEOutputLoad
from src.coffe.gen_routing_loads import _GeneralBLEOutputLoad
from src.coffe.sb_mux import _SwitchBlockMUX

import src.common.data_structs as rg_ds
import src.common.spice_parser as sp_parser
import re

from typing import Dict, List, Tuple, Union, Any
import math, os

class _LocalBLEOutput(_SizableCircuit):
    """ Local BLE Output class """
    
    def __init__(self, use_tgate, gen_r_wire: dict, local_ble_output_load: Any):
        self.name = f"local_ble_output" #_wire_uid{gen_r_wire['id']}"
        # load obj onto the local_ble_output
        self.local_ble_output_load = local_ble_output_load
        # load obj into the general_ble_output
        # self.gen_ble_output = gen_ble_output

        self.gen_r_wire = gen_r_wire
        # Delay weight in a representative critical path
        self.delay_weight = fpga.DELAY_WEIGHT_LOCAL_BLE_OUTPUT
        # use pass transistor or transmission gates
        self.use_tgate = use_tgate
        
        
    def generate(self, subcircuit_filename, min_tran_width):
        print("Generating local BLE output")
        if not self.use_tgate :
            self.transistor_names, self.wire_names = mux_subcircuits.generate_ptran_2_to_1_mux(subcircuit_filename, self.name)
            # Initialize transistor sizes (to something more reasonable than all min size, but not necessarily a good choice, depends on architecture params)
            self.initial_transistor_sizes["ptran_" + self.name + "_nmos"] = 2
            self.initial_transistor_sizes["rest_" + self.name + "_pmos"] = 1
            self.initial_transistor_sizes["inv_" + self.name + "_1_nmos"] = 1
            self.initial_transistor_sizes["inv_" + self.name + "_1_pmos"] = 1
            self.initial_transistor_sizes["inv_" + self.name + "_2_nmos"] = 4
            self.initial_transistor_sizes["inv_" + self.name + "_2_pmos"] = 4
        else :
            self.transistor_names, self.wire_names = mux_subcircuits.generate_tgate_2_to_1_mux(subcircuit_filename, self.name)
            # Initialize transistor sizes (to something more reasonable than all min size, but not necessarily a good choice, depends on architecture params)
            self.initial_transistor_sizes["tgate_" + self.name + "_nmos"] = 2
            self.initial_transistor_sizes["tgate_" + self.name + "_pmos"] = 2
            self.initial_transistor_sizes["inv_" + self.name + "_1_nmos"] = 1
            self.initial_transistor_sizes["inv_" + self.name + "_1_pmos"] = 1
            self.initial_transistor_sizes["inv_" + self.name + "_2_nmos"] = 4
            self.initial_transistor_sizes["inv_" + self.name + "_2_pmos"] = 4
      
        return self.initial_transistor_sizes

    def generate_local_ble_output_top(self):
        """ Generate the top level local ble output SPICE file """
        
        # Create directories
        if not os.path.exists(self.name):
            os.makedirs(self.name)  
        # Change to directory    
        os.chdir(self.name)   
        
        subckt_local_ble_output_load: str = self.local_ble_output_load.name

        local_ble_output_filename = self.name + ".sp"
        top_file = open(local_ble_output_filename, 'w')
        top_file.write(".TITLE Local BLE output\n\n") 
        
        top_file.write("********************************************************************************\n")
        top_file.write("** Include libraries, parameters and other\n")
        top_file.write("********************************************************************************\n\n")
        top_file.write(".LIB \"../includes.l\" INCLUDES\n\n")
        
        top_file.write("********************************************************************************\n")
        top_file.write("** Setup and input\n")
        top_file.write("********************************************************************************\n\n")
        top_file.write(".TRAN 1p 4n SWEEP DATA=sweep_data\n")
        top_file.write(".OPTIONS BRIEF=1\n\n")
        top_file.write("* Input signal\n")
        top_file.write("VIN n_in gnd PULSE (0 supply_v 0 0 0 2n 4n)\n\n")
        top_file.write("* Power rail for the circuit under test.\n")
        top_file.write("* This allows us to measure power of a circuit under test without measuring the power of wave shaping and load circuitry.\n")
        top_file.write("V_LOCAL_OUTPUT vdd_local_output gnd supply_v\n\n")

        top_file.write("********************************************************************************\n")
        top_file.write("** Measurement\n")
        top_file.write("********************************************************************************\n\n")
        top_file.write("* inv_local_ble_output_1 delay\n")
        top_file.write(".MEASURE TRAN meas_inv_local_ble_output_1_tfall TRIG V(n_1_1) VAL='supply_v/2' RISE=1\n")
        top_file.write("+    TARG V(Xlut_output_load.Xble_outputs.Xlocal_ble_output_1.n_2_1) VAL='supply_v/2' FALL=1\n")
        top_file.write(".MEASURE TRAN meas_inv_local_ble_output_1_trise TRIG V(n_1_1) VAL='supply_v/2' FALL=1\n")
        top_file.write("+    TARG V(Xlut_output_load.Xble_outputs.Xlocal_ble_output_1.n_2_1) VAL='supply_v/2' RISE=1\n\n")
        top_file.write("* inv_local_ble_output_2 delays\n")
        top_file.write(".MEASURE TRAN meas_inv_local_ble_output_2_tfall TRIG V(n_1_1) VAL='supply_v/2' FALL=1\n")
        top_file.write("+    TARG V(Xlocal_ble_output_load.n_1_2) VAL='supply_v/2' RISE=1\n")
        top_file.write(".MEASURE TRAN meas_inv_local_ble_output_2_trise TRIG V(n_1_1) VAL='supply_v/2' RISE=1\n")
        top_file.write("+    TARG V(Xlocal_ble_output_load.n_1_2) VAL='supply_v/2' FALL=1\n\n")
        top_file.write("* Total delays\n")
        top_file.write(".MEASURE TRAN meas_total_tfall TRIG V(n_1_1) VAL='supply_v/2' FALL=1\n")
        top_file.write("+    TARG V(Xlocal_ble_output_load.n_1_2) VAL='supply_v/2' RISE=1\n")
        top_file.write(".MEASURE TRAN meas_total_trise TRIG V(n_1_1) VAL='supply_v/2' RISE=1\n")
        top_file.write("+    TARG V(Xlocal_ble_output_load.n_1_2) VAL='supply_v/2' FALL=1\n\n")

        top_file.write(".MEASURE TRAN meas_logic_low_voltage FIND V(n_local_out) AT=3n\n\n")

        top_file.write("* Measure the power required to propagate a rise and a fall transition through the subcircuit at 250MHz.\n")
        top_file.write(".MEASURE TRAN meas_current INTEGRAL I(V_LOCAL_OUTPUT) FROM=0ns TO=4ns\n")
        top_file.write(".MEASURE TRAN meas_avg_power PARAM = '-((meas_current)/4n)*supply_v'\n\n")

        top_file.write("********************************************************************************\n")
        top_file.write("** Circuit\n")
        top_file.write("********************************************************************************\n\n")
        if not self.use_tgate :
            top_file.write("Xlut n_in n_1_1 vdd vdd vdd vdd vdd vdd vdd gnd lut\n\n")
            top_file.write("Xlut_output_load n_1_1 n_local_out n_general_out vsram vsram_n vdd gnd vdd_local_output vdd lut_output_load\n\n")
        else :
            top_file.write("Xlut n_in n_1_1 vdd gnd vdd gnd vdd gnd vdd gnd vdd gnd vdd gnd vdd gnd lut\n\n")
            top_file.write("Xlut_output_load n_1_1 n_local_out n_general_out vsram vsram_n vdd gnd vdd_local_output vdd lut_output_load\n\n")

        top_file.write("Xlocal_ble_output_load n_local_out vsram vsram_n vdd gnd local_ble_output_load\n")
        top_file.write(".END")
        top_file.close()

        # Come out of top-level directory
        os.chdir("../")
        
        return (self.name + "/" + self.name + ".sp")


    def generate_top(self):
        print("Generating top-level " + self.name)
        self.top_spice_path = self.generate_local_ble_output_top()
        
        
    def update_area(self, area_dict, width_dict):
        if not self.use_tgate :
            area = (2*area_dict["ptran_" + self.name] +
                    area_dict["rest_" + self.name] +
                    area_dict["inv_" + self.name + "_1"] +
                    area_dict["inv_" + self.name + "_2"])
        else :
            area = (2*area_dict["tgate_" + self.name] +
                    area_dict["inv_" + self.name + "_1"] +
                    area_dict["inv_" + self.name + "_2"])

        area = area + area_dict["sram"]
        width = math.sqrt(area)
        area_dict[self.name] = area
        width_dict[self.name] = width

        return area
        
    
    def update_wires(self, width_dict, wire_lengths, wire_layers):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """
    
        # Update wire lengths
        if not self.use_tgate :
            wire_lengths["wire_" + self.name] = width_dict["ptran_" + self.name]
        else :
            wire_lengths["wire_" + self.name] = width_dict["tgate_" + self.name]

        wire_lengths["wire_" + self.name + "_driver"] = (width_dict["inv_" + self.name + "_1"] + width_dict["inv_" + self.name + "_1"])/4
        
        # Update wire layers
        wire_layers["wire_" + self.name] = 0
        wire_layers["wire_" + self.name + "_driver"] = 0
        
        
    def print_details(self):
        print("Local BLE output details.")

      
class _GeneralBLEOutput(_SizableCircuit):
    """ General BLE Output """
    
    def __init__(self, use_tgate, gen_r_wire: dict, gen_ble_output_load: _GeneralBLEOutputLoad):
        self.gen_r_wire = gen_r_wire
        # load obj onto the general_ble_output
        self.output_load: _GeneralBLEOutputLoad = gen_ble_output_load
        # default name format for general BLE output
        self.name = f"general_ble_output_sb_mux_uid{gen_ble_output_load.sb_on_idx}"
        # self.name = "general_ble_output"
        self.delay_weight = fpga.DELAY_WEIGHT_GENERAL_BLE_OUTPUT
        self.use_tgate = use_tgate
        # Insts in the top level spice file
        self.top_insts: List[rg_ds.SpSubCktInst] = []
        # Stores parameter name of wire loads & transistors
        self.wire_names: List[str] = []
        self.transistor_names: List[str] = []
        
    def generate(self, subcircuit_filename, min_tran_width):
        print("Generating general BLE output")
        if not self.use_tgate :
            self.transistor_names, self.wire_names = mux_subcircuits.generate_ptran_2_to_1_mux(subcircuit_filename, self.name)
            # Initialize transistor sizes (to something more reasonable than all min size, but not necessarily a good choice, depends on architecture params)
            self.initial_transistor_sizes["ptran_" + self.name + "_nmos"] = 2
            self.initial_transistor_sizes["rest_" + self.name + "_pmos"] = 1
            self.initial_transistor_sizes["inv_" + self.name + "_1_nmos"] = 1
            self.initial_transistor_sizes["inv_" + self.name + "_1_pmos"] = 1
            self.initial_transistor_sizes["inv_" + self.name + "_2_nmos"] = 5
            self.initial_transistor_sizes["inv_" + self.name + "_2_pmos"] = 5
        else :
            self.transistor_names, self.wire_names = mux_subcircuits.generate_tgate_2_to_1_mux(subcircuit_filename, self.name)      
            # Initialize transistor sizes (to something more reasonable than all min size, but not necessarily a good choice, depends on architecture params)
            self.initial_transistor_sizes["tgate_" + self.name + "_nmos"] = 2
            self.initial_transistor_sizes["tgate_" + self.name + "_pmos"] = 2
            self.initial_transistor_sizes["inv_" + self.name + "_1_nmos"] = 1
            self.initial_transistor_sizes["inv_" + self.name + "_1_pmos"] = 1
            self.initial_transistor_sizes["inv_" + self.name + "_2_nmos"] = 5
            self.initial_transistor_sizes["inv_" + self.name + "_2_pmos"] = 5
       
        return self.initial_transistor_sizes

    def generate_general_ble_output_top(self):
        """ """
        
        #   __  __ ___   _   ___ _   _ ___ ___   ___ _____ _ _____ ___ __  __ ___ _  _ _____ ___ 
        #  |  \/  | __| /_\ / __| | | | _ \ __| / __|_   _/_\_   _| __|  \/  | __| \| |_   _/ __|
        #  | |\/| | _| / _ \\__ \ |_| |   / _|  \__ \ | |/ _ \| | | _|| |\/| | _|| .` | | | \__ \
        #  |_|  |_|___/_/ \_\___/\___/|_|_\___| |___/ |_/_/ \_\_| |___|_|  |_|___|_|\_| |_| |___/
        
        # Get list of insts to get to the general_ble_output inst in lut_output_load
        inst_path_lut_out_load_to_gen_ble_out: List[rg_ds.SpSubCktInst] = sp_parser.rec_find_inst(
            self.top_insts, 
            [ re.compile(re_str, re.MULTILINE | re.IGNORECASE) for re_str in ["lut_output_load", "ble_outputs", "general_ble_output"] ], #"general_ble_output" is the param_inst but param is suffix ie no change
            [] # You need to pass in an empty list to init function, if you don't weird things will happen (like getting previous results from other function calls)
        )

        meas_gen_ble_out_mux_drv_in_node: str = ".".join([inst.name for inst in inst_path_lut_out_load_to_gen_ble_out] + ["n_2_1"])

        # Not needed unless the "Xgeneral_ble_output_load" inst name changes
        # inst_path_top_gen_ble_out_load: List[rg_ds.SpSubCktInst] = sp_parser.rec_find_inst(
        #     self.top_insts, 
        #     [ re.compile(re_str, re.MULTILINE | re.IGNORECASE) for re_str in ["general_ble_output_load"] ],
        #     [] # You need to pass in an empty list to init function, if you don't weird things will happen (like getting previous results from other function calls)
        # )
        # meas_top_gen_ble_out_load_meas_node: str = ".".join([inst.name for inst in inst_path_top_gen_ble_out_load] + ["n_2_1"])

        # Create directories
        if not os.path.exists(self.name):
            os.makedirs(self.name)  
        # Change to directory    
        os.chdir(self.name)  
        
        # p_str = f"_wire_uid{self.gen_r_wire['id']}"
        # subckt_gen_ble_out_load_str = f"general_ble_output_load{p_str}"

        general_ble_output_filename = self.name + ".sp"
        top_file = open(general_ble_output_filename, 'w')
        top_file.write(".TITLE General BLE output\n\n") 
        
        top_file.write("********************************************************************************\n")
        top_file.write("** Include libraries, parameters and other\n")
        top_file.write("********************************************************************************\n\n")
        top_file.write(".LIB \"../includes.l\" INCLUDES\n\n")
        
        top_file.write("********************************************************************************\n")
        top_file.write("** Setup and input\n")
        top_file.write("********************************************************************************\n\n")
        top_file.write(".TRAN 1p 4n SWEEP DATA=sweep_data\n")
        top_file.write(".OPTIONS BRIEF=1\n\n")
        top_file.write("* Input signal\n")
        top_file.write("VIN n_in gnd PULSE (0 supply_v 0 0 0 2n 4n)\n\n")
        top_file.write("* Power rail for the circuit under test.\n")
        top_file.write("* This allows us to measure power of a circuit under test without measuring the power of wave shaping and load circuitry.\n")
        top_file.write("V_GENERAL_OUTPUT vdd_general_output gnd supply_v\n\n")

        top_file.write("********************************************************************************\n")
        top_file.write("** Measurement\n")
        top_file.write("********************************************************************************\n\n")
        top_file.write("* inv_general_ble_output_1 delay\n")
        top_file.write(".MEASURE TRAN meas_inv_general_ble_output_1_tfall TRIG V(n_1_1) VAL='supply_v/2' RISE=1\n")
        top_file.write(f"+    TARG V({meas_gen_ble_out_mux_drv_in_node}) VAL='supply_v/2' FALL=1\n")
        top_file.write(".MEASURE TRAN meas_inv_general_ble_output_1_trise TRIG V(n_1_1) VAL='supply_v/2' FALL=1\n")
        top_file.write(f"+    TARG V({meas_gen_ble_out_mux_drv_in_node}) VAL='supply_v/2' RISE=1\n\n")
        top_file.write("* inv_general_ble_output_2 delays\n")
        top_file.write(".MEASURE TRAN meas_inv_general_ble_output_2_tfall TRIG V(n_1_1) VAL='supply_v/2' FALL=1\n")
        top_file.write("+    TARG V(Xgeneral_ble_output_load.n_meas_point) VAL='supply_v/2' FALL=1\n")
        top_file.write(".MEASURE TRAN meas_inv_general_ble_output_2_trise TRIG V(n_1_1) VAL='supply_v/2' RISE=1\n")
        top_file.write("+    TARG V(Xgeneral_ble_output_load.n_meas_point) VAL='supply_v/2' RISE=1\n\n")
        top_file.write("* Total delays\n")
        top_file.write(".MEASURE TRAN meas_total_tfall TRIG V(n_1_1) VAL='supply_v/2' FALL=1\n")
        top_file.write("+    TARG V(Xgeneral_ble_output_load.n_meas_point) VAL='supply_v/2' FALL=1\n")
        top_file.write(".MEASURE TRAN meas_total_trise TRIG V(n_1_1) VAL='supply_v/2' RISE=1\n")
        top_file.write("+    TARG V(Xgeneral_ble_output_load.n_meas_point) VAL='supply_v/2' RISE=1\n\n")

        top_file.write(".MEASURE TRAN meas_logic_low_voltage FIND V(n_general_out) AT=3n\n\n")

        top_file.write("* Measure the power required to propagate a rise and a fall transition through the subcircuit at 250MHz.\n")
        top_file.write(".MEASURE TRAN meas_current INTEGRAL I(V_GENERAL_OUTPUT) FROM=0ns TO=4ns\n")
        top_file.write(".MEASURE TRAN meas_avg_power PARAM = '-((meas_current)/4n)*supply_v'\n\n")

        top_file.write("********************************************************************************\n")
        top_file.write("** Circuit\n")
        top_file.write("********************************************************************************\n\n")
        if not self.use_tgate :
            top_file.write("Xlut n_in n_1_1 vdd vdd vdd vdd vdd vdd vdd gnd lut\n\n")
            top_file.write("Xlut_output_load n_1_1 n_local_out n_general_out vsram vsram_n vdd gnd vdd vdd_general_output lut_output_load\n\n")
        else :
            top_file.write("Xlut n_in n_1_1 vdd gnd vdd gnd vdd gnd vdd gnd vdd gnd vdd gnd vdd gnd lut\n\n")
            top_file.write("Xlut_output_load n_1_1 n_local_out n_general_out vsram vsram_n vdd gnd vdd vdd_general_output lut_output_load\n\n")

        top_file.write(f"Xgeneral_ble_output_load n_general_out n_hang1 vsram vsram_n vdd gnd {self.output_load.name}\n")
        top_file.write(".END")
        top_file.close()

        # Come out of top-level directory
        os.chdir("../")
        
        return (self.name + "/" + self.name + ".sp")


    def generate_top(self, all_subckts: Dict[str, rg_ds.SpSubCkt]):

        self.top_insts: List[rg_ds.SpSubCktInst] = [
            # LUT
            rg_ds.SpSubCktInst(
                name="Xlut",
                subckt=all_subckts["lut"],
                # port : node
                conns = {
                    "n_in": "n_1_1",
                    "n_out": "vdd",
                    "n_a" : "gnd",
                    "n_a_n": "vdd",
                    "n_b": "gnd",
                    "n_b_n": "vdd",
                    "n_c": "gnd",
                    "n_c_n": "vdd",
                    "n_d": "gnd",
                    "n_d_n": "vdd",
                    "n_e": "gnd",
                    "n_e_n": "vdd",
                    "n_f": "gnd",
                    "n_f_n": "vdd",
                    "n_vdd": "gnd",
                    "n_gnd": "lut",
                }
            ),
            # LUT LOAD
            rg_ds.SpSubCktInst(
                name="Xlut_output_load",
                subckt=all_subckts["lut_output_load"],
                conns = {
                    "n_in": "n_1_1",
                    "n_local_out": "n_local_out",
                    "n_general_out": "n_general_out",
                    "n_gate": "vsram",
                    "n_gate_n": "vsram_n",
                    "n_vdd": "vdd",
                    "n_gnd": "gnd",
                    "n_vdd_local_output_on": "vdd",
                    "n_vdd_general_output_on": "vdd_general_output",
                }
            ),
            # GENERAL BLE OUTPUT LOAD
            rg_ds.SpSubCktInst(
                name="Xgeneral_ble_output_load",
                subckt = all_subckts[self.output_load.name],
                conns = {
                    "n_1_1": "n_general_out",
                    "n_out": "n_hang1",
                    "n_gate": "vsram",
                    "n_gate_n": "vsram_n",
                    "n_vdd": "vdd",
                    "n_gnd": "gnd",
                }
            )
        ]

        print("Generating top-level " + self.name)
        self.top_spice_path = self.generate_general_ble_output_top()
        
     
    def update_area(self, area_dict, width_dict):
        if not self.use_tgate :
            area = (2*area_dict["ptran_" + self.name] +
                    area_dict["rest_" + self.name] +
                    area_dict["inv_" + self.name + "_1"] +
                    area_dict["inv_" + self.name + "_2"])
        else :
            area = (2*area_dict["tgate_" + self.name] +
                    area_dict["inv_" + self.name + "_1"] +
                    area_dict["inv_" + self.name + "_2"])

        area = area + area_dict["sram"]
        width = math.sqrt(area)
        area_dict[self.name] = area
        width_dict[self.name] = width

        return area
        
    
    def update_wires(self, width_dict, wire_lengths, wire_layers):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """
    
        # Update wire lengths
        if not self.use_tgate :
            wire_lengths["wire_" + self.name] = width_dict["ptran_" + self.name]
        else :
            wire_lengths["wire_" + self.name] = width_dict["tgate_" + self.name]

        wire_lengths["wire_" + self.name + "_driver"] = (width_dict["inv_" + self.name + "_1"] + width_dict["inv_" + self.name + "_1"])/4
        
        # Update wire layers
        wire_layers["wire_" + self.name] = 0
        wire_layers["wire_" + self.name + "_driver"] = 0
        
   
    def print_details(self):
        print("General BLE output details.")


class _FlipFlop:
    """ FlipFlop class.
        COFFE does not do transistor sizing for the flip flop. Therefore, the FF is not a SizableCircuit.
        Regardless of that, COFFE has a FlipFlop object that is used to obtain FF area and delay.
        COFFE creates a SPICE netlist for the FF. The 'initial_transistor_sizes', defined below, are
        used when COFFE measures T_setup and T_clock_to_Q. Those transistor sizes were obtained
        through manual design for PTM 22nm process technology. If you use a different process technology,
        you may need to re-size the FF transistors. """
    
    def __init__(self, Rsel, use_tgate, use_finfet):
        # Flip-Flop name
        self.name = "ff"
        # Register select mux, Rsel = LUT input (e.g. 'a', 'b', etc.) or 'z' if no register select 
        self.register_select = Rsel
        # A list of the names of transistors in this subcircuit.
        self.transistor_names = []
        # A list of the names of wires in this subcircuit
        self.wire_names = []
        # A dictionary of the initial transistor sizes
        self.initial_transistor_sizes = {}
        # Path to the top level spice file
        self.top_spice_path = ""    
        # 
        self.t_setup = 1
        # 
        self.t_clk_to_q = 1
        # Delay weight used to calculate delay of representative critical path
        self.delay_weight = 1
        self.use_finfet = use_finfet
        self.use_tgate = use_tgate
        
         
    def generate(self, subcircuit_filename, min_tran_width):
        """ Generate FF SPICE netlists. Optionally includes register select. """
        
        # Generate FF with optional register select
        if self.register_select == 'z':
            print("Generating FF")
            if not self.use_tgate :
                self.transistor_names, self.wire_names = ff_subcircuits.generate_ptran_d_ff(subcircuit_filename, self.use_finfet)
            else :
                self.transistor_names, self.wire_names = ff_subcircuits.generate_tgate_d_ff(subcircuit_filename, self.use_finfet)

        else:
            print("Generating FF with register select on BLE input " + self.register_select)
            if not self.use_tgate :
                self.transistor_names, self.wire_names = ff_subcircuits.generate_ptran_2_input_select_d_ff(subcircuit_filename, self.use_finfet)
            else :
                self.transistor_names, self.wire_names = ff_subcircuits.generate_tgate_2_input_select_d_ff(subcircuit_filename, self.use_finfet)
        
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


    def generate_top(self):
        """ """
        # TODO for T_setup and T_clock_to_Q
        pass
        

    def update_area(self, area_dict, width_dict):
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
        
        
    def update_wires(self, width_dict, wire_lengths, wire_layers):
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
            wire_layers["wire_ff_input_select"] = 0
            
        wire_layers["wire_ff_input_out"] = 0
        wire_layers["wire_ff_tgate_1_out"] = 0
        wire_layers["wire_ff_cc1_out"] = 0
        wire_layers["wire_ff_tgate_2_out"] = 0
        wire_layers["wire_ff_cc2_out"] = 0
        
        
    def print_details(self):
        print("  FF DETAILS:")
        if self.register_select == 'z':
            print("  Register select: None")
        else:
            print("  Register select: BLE input " + self.register_select)


class _LUTOutputLoad:
    """ LUT output load is the load seen by the output of the LUT in the basic case if Or = 1 and Ofb = 1 (see [1])
        then the output load will be the regster select mux of the flip-flop, the mux connecting the output signal
        to the output routing and the mux connecting the output signal to the feedback mux """

    def __init__(self, num_local_outputs, num_general_outputs):
        self.name = "lut_output_load"
        self.num_local_outputs = num_local_outputs
        self.num_general_outputs = num_general_outputs
        self.wire_names = []
        

    def generate_lut_output_load(self, spice_filename):
        """ Create the LUT output load subcircuit. It consists of a FF which 
            has the register select mux at its input and all BLE outputs which 
            include the output routing mux (Or) and the output feedback mux (Ofb) """


        # Total number of BLE outputs
        total_outputs = self.num_local_outputs + self.num_general_outputs

        # Open SPICE file for appending
        spice_file = open(spice_filename, 'a')
        
        spice_file.write("******************************************************************************************\n")
        spice_file.write("* LUT output load\n")
        spice_file.write("******************************************************************************************\n")
        spice_file.write(".SUBCKT lut_output_load n_in n_local_out n_general_out n_gate n_gate_n n_vdd n_gnd n_vdd_local_output_on n_vdd_general_output_on\n")
        spice_file.write("Xwire_lut_output_load_1 n_in n_1_1 wire Rw='wire_lut_output_load_1_res' Cw='wire_lut_output_load_1_cap'\n")
        spice_file.write("Xff n_1_1 n_hang1 n_gate n_gate_n n_vdd n_gnd n_gnd n_vdd n_gnd n_vdd n_vdd n_gnd ff\n")
        spice_file.write("Xwire_lut_output_load_2 n_1_1 n_1_2 wire Rw='wire_lut_output_load_2_res' Cw='wire_lut_output_load_2_cap'\n")
        spice_file.write("Xble_outputs n_1_2 n_local_out n_general_out n_gate n_gate_n n_vdd n_gnd n_vdd_local_output_on n_vdd_general_output_on ble_outputs\n")
        spice_file.write(".ENDS\n\n\n")

        spice_file.close()
        
        # Create a list of all wires used in this subcircuit
        wire_names_list = []
        wire_names_list.append("wire_lut_output_load_1")
        wire_names_list.append("wire_lut_output_load_2")
        
        return wire_names_list
        
    def generate(self, subcircuit_filename, min_tran_width):
        print("Generating LUT output load")
        self.wire_names = self.generate_lut_output_load(subcircuit_filename)
        
     
    def update_wires(self, width_dict, wire_lengths, wire_layers):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """
        
        # Update wire lengths
        wire_lengths["wire_lut_output_load_1"] = (width_dict["ff"] + width_dict["lut_and_drivers"])/8
        wire_lengths["wire_lut_output_load_2"] = width_dict["ff"]
        
        # Update wire layers
        wire_layers["wire_lut_output_load_1"] = fpga.LOCAL_WIRE_LAYER
        wire_layers["wire_lut_output_load_2"] = fpga.LOCAL_WIRE_LAYER

class _flut_mux(_CompoundCircuit):
    
    def __init__(self, use_tgate, use_finfet, enable_carry_chain, gen_ble_output_load: _GeneralBLEOutputLoad):
        # name
        self.name = "flut_mux"
        # Gen ble output load that is loading the flut_mux
        self.gen_ble_output_load = gen_ble_output_load
        # self.name = f"flut_mux_L{gen_r_wire['len']}_uid{gen_r_wire['id']}"
        # self.gen_r_wire = gen_r_wire
        # use tgate
        self.use_tgate = use_tgate
        # A dictionary of the initial transistor sizes
        self.initial_transistor_sizes = {}
        # todo: change to enable finfet support, should be rather straightforward as it's just a mux
        # use finfet
        self.use_finfet = use_finfet 
        self.enable_carry_chain = enable_carry_chain
        
        # this condition was added to the check_arch_params in utils.py
        # assert use_finfet == False


    def generate(self, subcircuit_filename, min_tran_width):
        print("Generating flut added mux")   

        if not self.use_tgate :
            self.transistor_names, self.wire_names = mux_subcircuits.generate_ptran_2_to_1_mux(subcircuit_filename, self.name)
            # Initialize transistor sizes (to something more reasonable than all min size, but not necessarily a good choice, depends on architecture params)
            self.initial_transistor_sizes["ptran_" + self.name + "_nmos"] = 2
            self.initial_transistor_sizes["rest_" + self.name + "_pmos"] = 1
            self.initial_transistor_sizes["inv_" + self.name + "_1_nmos"] = 1
            self.initial_transistor_sizes["inv_" + self.name + "_1_pmos"] = 1
            self.initial_transistor_sizes["inv_" + self.name + "_2_nmos"] = 5
            self.initial_transistor_sizes["inv_" + self.name + "_2_pmos"] = 5
        else :
            self.transistor_names, self.wire_names = mux_subcircuits.generate_tgate_2_to_1_mux(subcircuit_filename, self.name)      
            # Initialize transistor sizes (to something more reasonable than all min size, but not necessarily a good choice, depends on architecture params)
            self.initial_transistor_sizes["tgate_" + self.name + "_nmos"] = 2
            self.initial_transistor_sizes["tgate_" + self.name + "_pmos"] = 2
            self.initial_transistor_sizes["inv_" + self.name + "_1_nmos"] = 1
            self.initial_transistor_sizes["inv_" + self.name + "_1_pmos"] = 1
            self.initial_transistor_sizes["inv_" + self.name + "_2_nmos"] = 5
            self.initial_transistor_sizes["inv_" + self.name + "_2_pmos"] = 5
       
        self.wire_names.append("wire_lut_to_flut_mux")
        return self.initial_transistor_sizes

    def generate_flut_mux_top(self):
        
        #TODO: 
        #- I think the general ble output load should be removed from this ciruit in case of an ALM
        #  with carry chain. Since, the load in this case is only the carry chain mux. 
        #- I also think that in both cases whether there is a carry chain mux or not the delay should 
        #  be measured between the n_1_1 and n_1_3 and not between n_1_1 and n_local_out.
        
        # p_str = f"_wire_uid{self.gen_r_wire['id']}"
        # subckt_gen_ble_out_load_str = f"general_ble_output_load{p_str}"

        # Create directories
        if not os.path.exists(self.name):
            os.makedirs(self.name)  
        # Change to directory    
        os.chdir(self.name)  
        
        filename = self.name + ".sp"
        top_file = open(filename, 'w')
        top_file.write(".TITLE General BLE output\n\n") 
        
        top_file.write("********************************************************************************\n")
        top_file.write("** Include libraries, parameters and other\n")
        top_file.write("********************************************************************************\n\n")
        top_file.write(".LIB \"../includes.l\" INCLUDES\n\n")
        
        top_file.write("********************************************************************************\n")
        top_file.write("** Setup and input\n")
        top_file.write("********************************************************************************\n\n")
        top_file.write(".TRAN 1p 4n SWEEP DATA=sweep_data\n")
        top_file.write(".OPTIONS BRIEF=1\n\n")
        top_file.write("* Input signal\n")
        top_file.write("VIN n_in gnd PULSE (0 supply_v 0 0 0 2n 4n)\n\n")
        top_file.write("* Power rail for the circuit under test.\n")
        top_file.write("* This allows us to measure power of a circuit under test without measuring the power of wave shaping and load circuitry.\n")
        top_file.write("V_FLUT vdd_f gnd supply_v\n\n")

        top_file.write("********************************************************************************\n")
        top_file.write("** Measurement\n")
        top_file.write("********************************************************************************\n\n")
        top_file.write("* inv_"+ self.name +"_1 delay\n")
        top_file.write(".MEASURE TRAN meas_inv_"+ self.name +"_1_tfall TRIG V(n_1_2) VAL='supply_v/2' RISE=1\n")
        top_file.write("+    TARG V(Xthemux.n_2_1) VAL='supply_v/2' FALL=1\n")
        top_file.write(".MEASURE TRAN meas_inv_"+ self.name +"_1_trise TRIG V(n_1_2) VAL='supply_v/2' FALL=1\n")
        top_file.write("+    TARG V(Xthemux.n_2_1) VAL='supply_v/2' RISE=1\n\n")
        top_file.write("* inv_"+ self.name +"_2 delays\n")
        top_file.write(".MEASURE TRAN meas_inv_"+ self.name +"_2_tfall TRIG V(n_1_2) VAL='supply_v/2' FALL=1\n")
        top_file.write("+    TARG V(n_local_out) VAL='supply_v/2' FALL=1\n")
        top_file.write(".MEASURE TRAN meas_inv_"+ self.name +"_2_trise TRIG V(n_1_2) VAL='supply_v/2' RISE=1\n")
        top_file.write("+    TARG V(n_local_out) VAL='supply_v/2' RISE=1\n\n")
        top_file.write("* Total delays\n")
        top_file.write(".MEASURE TRAN meas_total_tfall TRIG V(n_1_1) VAL='supply_v/2' FALL=1\n")
        #top_file.write("+    TARG V(n_1_3) VAL='supply_v/2' FALL=1\n")
        top_file.write("+    TARG V(n_local_out) VAL='supply_v/2' FALL=1\n")
        top_file.write(".MEASURE TRAN meas_total_trise TRIG V(n_1_1) VAL='supply_v/2' RISE=1\n")
        #top_file.write("+    TARG V(n_1_3) VAL='supply_v/2' RISE=1\n\n")
        top_file.write("+    TARG V(n_local_out) VAL='supply_v/2' RISE=1\n\n")
        top_file.write(".MEASURE TRAN meas_logic_low_voltage FIND V(n_general_out) AT=3n\n\n")

        top_file.write("* Measure the power required to propagate a rise and a fall transition through the subcircuit at 250MHz.\n")
        top_file.write(".MEASURE TRAN meas_current INTEGRAL I(V_FLUT) FROM=0ns TO=4ns\n")
        top_file.write(".MEASURE TRAN meas_avg_power PARAM = '-((meas_current)/4n)*supply_v'\n\n")

        top_file.write("********************************************************************************\n")
        top_file.write("** Circuit\n")
        top_file.write("********************************************************************************\n\n")
        # lut, wire from lut to the mux, the mux, and the load same output load as before
        if not self.use_tgate :
            top_file.write("Xlut n_in n_1_1 vdd vdd vdd vdd vdd vdd vdd gnd lut\n")
            top_file.write("Xwireflut n_1_1 n_1_2 wire Rw=wire_lut_to_flut_mux_res Cw=wire_lut_to_flut_mux_cap\n")  
            top_file.write("Xthemux n_1_2 n_1_3 vdd gnd vdd_f gnd flut_mux\n")       
            if self.enable_carry_chain == 1:
                top_file.write("Xwireovercc n_1_3 n_1_4 wire Rw=wire_carry_chain_5_res Cw=wire_carry_chain_5_cap\n")
                top_file.write("Xccmux n_1_4 n_local_out vdd gnd vdd gnd carry_chain_mux\n")   
            else:
                top_file.write("Xlut_output_load n_1_3 n_local_out n_general_out vsram vsram_n vdd gnd vdd vdd lut_output_load\n\n")
        else :
            top_file.write("Xlut n_in n_1_1 vdd gnd vdd gnd vdd gnd vdd gnd vdd gnd vdd gnd vdd gnd lut\n\n")
            top_file.write("Xwireflut n_1_1 n_1_2 wire Rw=wire_lut_to_flut_mux_res Cw=wire_lut_to_flut_mux_cap\n") 
            top_file.write("Xthemux n_1_2 n_1_3 vdd gnd vdd_f gnd flut_mux\n")  
            if self.enable_carry_chain == 1:
                top_file.write("Xwireovercc n_1_3 n_1_4 wire Rw=wire_carry_chain_5_res Cw=wire_carry_chain_5_cap\n") 
                top_file.write("Xccmux n_1_4 n_local_out vdd gnd vdd gnd carry_chain_mux\n")
            else:
                top_file.write("Xlut_output_load n_1_3 n_local_out n_general_out vsram vsram_n vdd gnd vdd vdd lut_output_load\n\n")

        top_file.write(f"Xgeneral_ble_output_load n_general_out n_hang1 vsram vsram_n vdd gnd {self.gen_ble_output_load.name}\n")
        top_file.write(".END")
        top_file.close()

        # Come out of top-level directory
        os.chdir("../")
        
        return (self.name + "/" + self.name + ".sp")


    def generate_top(self):       

        print("Generating top-level " + self.name)
        self.top_spice_path = self.generate_flut_mux_top()

    def update_area(self, area_dict, width_dict):

        if not self.use_tgate :
            area = (2*area_dict["ptran_" + self.name] +
                    area_dict["rest_" + self.name] +
                    area_dict["inv_" + self.name + "_1"] +
                    area_dict["inv_" + self.name + "_2"])
        else :
            area = (2*area_dict["tgate_" + self.name] +
                    area_dict["inv_" + self.name + "_1"] +
                    area_dict["inv_" + self.name + "_2"])

        area = area #+ area_dict["sram"]
        width = math.sqrt(area)
        area_dict[self.name] = area
        width_dict[self.name] = width

        return area
                

    def update_wires(self, width_dict, wire_lengths, wire_layers, lut_ratio):
        """ Update wire of member objects. """
        
        # TODO get wires from self.wire_names instead

        # Update wire lengths
        if not self.use_tgate :
            wire_lengths["wire_" + self.name] = width_dict["ptran_" + self.name]
            wire_lengths["wire_lut_to_flut_mux"] = width_dict["lut"]/2 * lut_ratio
        else :
            wire_lengths["wire_" + self.name] = width_dict["tgate_" + self.name]
            wire_lengths["wire_lut_to_flut_mux"] = width_dict["lut"]/2 * lut_ratio

        wire_lengths["wire_" + self.name + "_driver"] = (width_dict["inv_" + self.name + "_1"] + width_dict["inv_" + self.name + "_1"])/4
        
        # Update wire layers
        wire_layers["wire_" + self.name] = 0
        wire_layers["wire_lut_to_flut_mux"] = 0
        wire_layers["wire_" + self.name + "_driver"] = 0



class _BLE(_CompoundCircuit):

    def __init__(
            self, K, Or, Ofb, Rsel, Rfb, use_tgate, use_finfet, use_fluts, 
            enable_carry_chain, FAs_per_flut, 
            carry_skip_periphery_count, N, 
            gen_r_wire: dict,
            local_ble_output_load: Any,
            gen_ble_output_load: _GeneralBLEOutputLoad
        ):
        # BLE name
        self.name = "ble"
        # General routing wire associated
        self.gen_r_wire: dict = gen_r_wire
        # local ble output load object
        self.local_ble_output_load: Any = local_ble_output_load
        # General ble output load object
        self.gen_ble_output_load: _GeneralBLEOutputLoad = gen_ble_output_load
        # Switch block mux loading the g
        # number of bles in a cluster
        self.N = N
        # Size of LUT
        self.K = K
        # Number of inputs to the BLE
        self.num_inputs = K
        # Number of local outputs
        self.num_local_outputs = Ofb
        # Number of general outputs
        self.num_general_outputs = Or
        # Create BLE local output object
        self.local_output = _LocalBLEOutput(use_tgate, gen_r_wire, self.local_ble_output_load)
        # Create BLE general output object
        self.general_output = _GeneralBLEOutput(use_tgate, gen_r_wire, self.gen_ble_output_load)

        # Creating a BLE general output object for each type of wire we have
        # self.general_outputs = [_GeneralBLEOutput(use_tgate, wire) for wire in wire_types]
        # Create LUT object
        self.lut = _LUT(K, Rsel, Rfb, use_tgate, use_finfet, use_fluts)
        # Create FF object
        self.ff = _FlipFlop(Rsel, use_tgate, use_finfet)
        # Create LUT output load object
        self.lut_output_load = _LUTOutputLoad(self.num_local_outputs, self.num_general_outputs)
        # Are the LUTs fracturable?
        self.use_fluts = use_fluts
        # The extra mux for the fracturable luts
        if use_fluts:
            self.fmux = _flut_mux(use_tgate, use_finfet, enable_carry_chain, self.gen_ble_output_load)

        # TODO: why is the carry chain object not defined here?
        self.enable_carry_chain = enable_carry_chain
        self.FAs_per_flut = FAs_per_flut
        self.carry_skip_periphery_count = carry_skip_periphery_count

        # wire_names
        self.wire_names: List[str] = []



    def generate_ble_outputs(self, spice_filename):
        """ Create the BLE outputs block. Contains 'num_local_out' local outputs and 'num_gen_out' general outputs. """
        
        #TODO: The order of the wires is weird in this netlist, have a look at it later.
        # Total number of BLE outputs
        total_outputs = self.num_local_outputs + self.num_general_outputs
        

        subckt_local_ble_output_name = f"{self.local_output.name}" # f"local_ble_output_wire_uid{self.gen_r_wire['id']}"
        subckt_general_ble_output_name = f"{self.general_output.name}" #f"general_ble_output_wire_uid{self.gen_r_wire['id']}"
        # Typically the param string coming from the gen_ble_output load is coming from ON SB loading it
        wire_gen_ble_outputs = f"wire_ble_outputs{self.gen_ble_output_load.param_str}"
        # wire_gen_ble_outputs = f"wire_ble_outputs_wire_uid{self.gen_r_wire['id']}"

        # Open SPICE file for appending
        spice_file = open(spice_filename, 'a')
        
        spice_file.write("******************************************************************************************\n")
        spice_file.write("* BLE outputs\n")
        spice_file.write("******************************************************************************************\n")
        spice_file.write(".SUBCKT ble_outputs n_1_" + str(int((total_outputs + 1)/2)+1) + " n_local_out n_general_out n_gate n_gate_n n_vdd n_gnd n_vdd_local_output_on n_vdd_general_output_on\n")
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
        
    def generate(self, subcircuit_filename, min_tran_width):
        print("Generating BLE")
        
        # Generate LUT and FF
        init_tran_sizes = {}
        init_tran_sizes.update(self.lut.generate(subcircuit_filename, min_tran_width))
        init_tran_sizes.update(self.ff.generate(subcircuit_filename, min_tran_width))

        # Generate BLE outputs
        init_tran_sizes.update(self.local_output.generate(subcircuit_filename, 
                                                          min_tran_width))
        init_tran_sizes.update(self.general_output.generate(subcircuit_filename, 
                                                            min_tran_width))
        # for gen_output in self.general_outputs:
        #     init_tran_sizes.update(gen_output.generate(subcircuit_filename, 
        #                                                 min_tran_width))
        self.wire_names = self.generate_ble_outputs(subcircuit_filename)
 
        #flut mux
        if self.use_fluts:
            init_tran_sizes.update(self.fmux.generate(subcircuit_filename, min_tran_width))           
        # Generate LUT load
        self.lut_output_load.generate(subcircuit_filename, min_tran_width)
       
        return init_tran_sizes

     
    def generate_top(self, all_subckts: Dict[str, rg_ds.SpSubCkt]):
        self.lut.generate_top()
        self.local_output.generate_top()
        self.general_output.generate_top(all_subckts)

        if self.use_fluts:
            self.fmux.generate_top()   
    
    def update_area(self, area_dict, width_dict):
    


        ff_area = self.ff.update_area(area_dict, width_dict)

        if self.use_fluts:
            fmux_area = self.fmux.update_area(area_dict, width_dict) 
            fmux_width = math.sqrt(fmux_area)
            area_dict["flut_mux"] = fmux_area
            width_dict["flut_mux"] = fmux_width    

        lut_area = self.lut.update_area(area_dict, width_dict)




        # Calculate area of BLE outputs
        local_ble_output_area = self.num_local_outputs*self.local_output.update_area(area_dict, width_dict)
        general_ble_output_area = self.num_general_outputs*self.general_output.update_area(area_dict, width_dict)
        
        ble_output_area = local_ble_output_area + general_ble_output_area
        ble_output_width = math.sqrt(ble_output_area)
        area_dict["ble_output"] = ble_output_area
        width_dict["ble_output"] = ble_output_width

        if self.use_fluts:
            ble_area = lut_area + 2*ff_area + ble_output_area# + fmux_area
        else:
            ble_area = lut_area + ff_area + ble_output_area

        if self.enable_carry_chain == 1:
            if self.carry_skip_periphery_count ==0:
                ble_area = ble_area + area_dict["carry_chain"] * self.FAs_per_flut + (self.FAs_per_flut) * area_dict["carry_chain_mux"]
            else:
                ble_area = ble_area + area_dict["carry_chain"] * self.FAs_per_flut + (self.FAs_per_flut) * area_dict["carry_chain_mux"]
                ble_area = ble_area + ((area_dict["xcarry_chain_and"] + area_dict["xcarry_chain_mux"]) * self.carry_skip_periphery_count)/self.N

        ble_width = math.sqrt(ble_area)
        area_dict["ble"] = ble_area
        width_dict["ble"] = ble_width


        
        
    def update_wires(self, width_dict, wire_lengths, wire_layers, lut_ratio):
        """ Update wire of member objects. """
        
        # Filter wire names list to get the name of ble_output_wire (with any parameters added to suffix)
        ble_outputs_wire_key = [ wire_name for wire_name in self.wire_names if "wire_ble_outputs" in wire_name][0]


        # Assert keys exist in wire_names, unneeded but following convension if wire keys not coming from wire_names
        assert ble_outputs_wire_key in self.wire_names

        # Update lut and ff wires.
        self.lut.update_wires(width_dict, wire_lengths, wire_layers, lut_ratio)
        self.ff.update_wires(width_dict, wire_lengths, wire_layers)
        
        # Update BLE output wires
        self.local_output.update_wires(width_dict, wire_lengths, wire_layers)
        self.general_output.update_wires(width_dict, wire_lengths, wire_layers)
        
        # Wire connecting all BLE output mux-inputs together
        wire_lengths[ble_outputs_wire_key] = self.num_local_outputs * width_dict[self.local_output.name] + self.num_general_outputs * width_dict[self.general_output.name]
        wire_layers[ble_outputs_wire_key] = fpga.LOCAL_WIRE_LAYER

        # Update LUT load wires
        self.lut_output_load.update_wires(width_dict, wire_lengths, wire_layers)

        # Fracturable luts:
        if self.use_fluts:
            self.fmux.update_wires(width_dict, wire_lengths, wire_layers, lut_ratio)
        
        
    def print_details(self, report_file):
    
        self.lut.print_details(report_file)
        