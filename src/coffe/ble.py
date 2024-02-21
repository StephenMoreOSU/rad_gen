
from src.coffe.circuit_baseclasses import _SizableCircuit, _CompoundCircuit
import src.coffe.fpga as fpga

import src.coffe.mux_subcircuits as mux_subcircuits
import src.coffe.ff_subcircuits as ff_subcircuits
import src.coffe.load_subcircuits as load_subcircuits

import src.coffe.utils as utils

from src.coffe.lut import _LUT


from typing import Dict, List, Tuple, Union, Any
import math, os

class _LocalBLEOutput(_SizableCircuit):
    """ Local BLE Output class """
    
    def __init__(self, use_tgate, gen_r_wire: dict):
        self.name = f"local_ble_output_L{gen_r_wire['len']}_uid{gen_r_wire['id']}"
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
    
    def __init__(self, use_tgate, gen_r_wire: dict):
        self.gen_r_wire = gen_r_wire
        # default name format for general BLE output
        self.name = f"general_ble_output_L{gen_r_wire['len']}_uid{gen_r_wire['id']}"
        # self.name = "general_ble_output"
        self.delay_weight = fpga.DELAY_WEIGHT_GENERAL_BLE_OUTPUT
        self.use_tgate = use_tgate
        
        
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
        
        # Create directories
        if not os.path.exists(self.name):
            os.makedirs(self.name)  
        # Change to directory    
        os.chdir(self.name)  
        
        p_str = f"_L{self.gen_r_wire['len']}_uid{self.gen_r_wire['id']}"
        subckt_gen_ble_out_load_str = f"general_ble_output_load{p_str}"

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
        top_file.write("+    TARG V(Xlut_output_load.Xble_outputs.Xgeneral_ble_output_1.n_2_1) VAL='supply_v/2' FALL=1\n")
        top_file.write(".MEASURE TRAN meas_inv_general_ble_output_1_trise TRIG V(n_1_1) VAL='supply_v/2' FALL=1\n")
        top_file.write("+    TARG V(Xlut_output_load.Xble_outputs.Xgeneral_ble_output_1.n_2_1) VAL='supply_v/2' RISE=1\n\n")
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

        top_file.write(f"Xgeneral_ble_output_load n_general_out n_hang1 vsram vsram_n vdd gnd {subckt_gen_ble_out_load_str}\n")
        top_file.write(".END")
        top_file.close()

        # Come out of top-level directory
        os.chdir("../")
        
        return (self.name + "/" + self.name + ".sp")


    def generate_top(self):
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
        
        
    def generate(self, subcircuit_filename, min_tran_width):
        print("Generating LUT output load")
        self.wire_names = load_subcircuits.generate_lut_output_load(subcircuit_filename, self.num_local_outputs, self.num_general_outputs)
        
     
    def update_wires(self, width_dict, wire_lengths, wire_layers):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """
        
        # Update wire lengths
        wire_lengths["wire_lut_output_load_1"] = (width_dict["ff"] + width_dict["lut_and_drivers"])/8
        wire_lengths["wire_lut_output_load_2"] = width_dict["ff"]
        
        # Update wire layers
        wire_layers["wire_lut_output_load_1"] = 0
        wire_layers["wire_lut_output_load_2"] = 0

class _flut_mux(_CompoundCircuit):
    
    def __init__(self, use_tgate, use_finfet, enable_carry_chain, gen_r_wire: dict):
        # name
        self.name = "flut_mux"
        # self.name = f"flut_mux_L{gen_r_wire['len']}_uid{gen_r_wire['id']}"
        self.gen_r_wire = gen_r_wire
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
        
        p_str = f"_L{self.gen_r_wire['len']}_uid{self.gen_r_wire['id']}"
        subckt_gen_ble_out_load_str = f"general_ble_output_load{p_str}"

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

        top_file.write(f"Xgeneral_ble_output_load n_general_out n_hang1 vsram vsram_n vdd gnd {subckt_gen_ble_out_load_str}\n")
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

    def __init__(self, K, Or, Ofb, Rsel, Rfb, use_tgate, use_finfet, use_fluts, enable_carry_chain, FAs_per_flut, carry_skip_periphery_count, N, gen_r_wire: dict):
        # BLE name
        self.name = "ble"
        # General routing wire associated
        self.gen_r_wire = gen_r_wire
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
        self.local_output = _LocalBLEOutput(use_tgate, gen_r_wire)
        # Create BLE general output object
        self.general_output = _GeneralBLEOutput(use_tgate, gen_r_wire)
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
            self.fmux = _flut_mux(use_tgate, use_finfet, enable_carry_chain, gen_r_wire)

        # TODO: why is the carry chain object not defined here?
        self.enable_carry_chain = enable_carry_chain
        self.FAs_per_flut = FAs_per_flut
        self.carry_skip_periphery_count = carry_skip_periphery_count

        
        
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
        load_subcircuits.generate_ble_outputs(subcircuit_filename, self.num_local_outputs, self.num_general_outputs, self.gen_r_wire)
 
        #flut mux
        if self.use_fluts:
            init_tran_sizes.update(self.fmux.generate(subcircuit_filename, min_tran_width))           
        # Generate LUT load
        self.lut_output_load.generate(subcircuit_filename, min_tran_width)
       
        return init_tran_sizes

     
    def generate_top(self):
        self.lut.generate_top()
        self.local_output.generate_top()
        self.general_output.generate_top()

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
        
        

        # Update lut and ff wires.
        self.lut.update_wires(width_dict, wire_lengths, wire_layers, lut_ratio)
        self.ff.update_wires(width_dict, wire_lengths, wire_layers)
        
        # Update BLE output wires
        self.local_output.update_wires(width_dict, wire_lengths, wire_layers)
        self.general_output.update_wires(width_dict, wire_lengths, wire_layers)
        
        # Wire connecting all BLE output mux-inputs together
        wire_lengths["wire_ble_outputs"] = self.num_local_outputs*width_dict[self.local_output.name] + self.num_general_outputs*width_dict[self.general_output.name]
        wire_layers["wire_ble_outputs"] = fpga.LOCAL_WIRE_LAYER

        # Update LUT load wires
        self.lut_output_load.update_wires(width_dict, wire_lengths, wire_layers)

        # Fracturable luts:
        if self.use_fluts:
            self.fmux.update_wires(width_dict, wire_lengths, wire_layers, lut_ratio)
        
        
    def print_details(self, report_file):
    
        self.lut.print_details(report_file)
        