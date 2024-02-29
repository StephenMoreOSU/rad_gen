
from src.coffe.circuit_baseclasses import _SizableCircuit
import src.coffe.fpga as fpga

import src.coffe.mux_subcircuits as mux_subcircuits
import src.coffe.lut_subcircuits as lut_subcircuits

import src.coffe.utils as utils

import src.coffe.gen_routing_loads as gen_r_loads

from typing import Dict, List, Tuple, Union, Any
import math, os




class _CarryChainMux(_SizableCircuit):
    """ Carry Chain Multiplexer class.    """
    def __init__(self, use_finfet, use_fluts, use_tgate, gen_ble_out_load: gen_r_loads._GeneralBLEOutputLoad):
        self.name = "carry_chain_mux"
        self.use_finfet = use_finfet
        self.use_fluts = use_fluts
        self.use_tgate = use_tgate      
        self.gen_ble_out_load: gen_r_loads._GeneralBLEOutputLoad = gen_ble_out_load
        # handled in the check_arch_params function in the utils.py file
        # assert use_fluts
        

    def generate(self, subcircuit_filename, min_tran_width, use_finfet):
        """ Generate the SPICE netlists."""  

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


    def generate_cc_mux_top(self):
        """ Creating the SPICE netlist for calculating the delay of the carry chain mux"""
        
        # p_str = f"_L{gen_r_wire['len']}_uid{gen_r_wire['id']}"
        # subckt_gen_ble_out_load_str = f"general_ble_output_load{p_str}"

        # Create directories
        if not os.path.exists(self.name):
            os.makedirs(self.name)  
        # Change to directory    
        os.chdir(self.name)  
        
        filename = self.name + ".sp"
        top_file = open(filename, 'w')
        top_file.write(".TITLE Carry chain mux\n\n") 
        
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
        top_file.write("V_FLUT vdd_test gnd supply_v\n\n")

        top_file.write("********************************************************************************\n")
        top_file.write("** Measurement\n")
        top_file.write("********************************************************************************\n\n")
        top_file.write("* inv_"+ self.name +"_1 delay\n")
        top_file.write(".MEASURE TRAN meas_inv_"+ self.name +"_1_tfall TRIG V(n_1_4) VAL='supply_v/2' RISE=1\n")
        top_file.write("+    TARG V(Xthemux.n_2_1) VAL='supply_v/2' FALL=1\n")
        top_file.write(".MEASURE TRAN meas_inv_"+ self.name +"_1_trise TRIG V(n_1_4) VAL='supply_v/2' FALL=1\n")
        top_file.write("+    TARG V(Xthemux.n_2_1) VAL='supply_v/2' RISE=1\n\n")
        top_file.write("* inv_"+ self.name +"_2 delays\n")
        top_file.write(".MEASURE TRAN meas_inv_"+ self.name +"_2_tfall TRIG V(n_1_4) VAL='supply_v/2' FALL=1\n")
        top_file.write("+    TARG V(n_local_out) VAL='supply_v/2' FALL=1\n")
        top_file.write(".MEASURE TRAN meas_inv_"+ self.name +"_2_trise TRIG V(n_1_4) VAL='supply_v/2' RISE=1\n")
        top_file.write("+    TARG V(n_local_out) VAL='supply_v/2' RISE=1\n\n")
        top_file.write("* Total delays\n")
        top_file.write(".MEASURE TRAN meas_total_tfall TRIG V(n_1_4) VAL='supply_v/2' FALL=1\n")
        #top_file.write("+    TARG V(n_1_3) VAL='supply_v/2' FALL=1\n")
        top_file.write("+    TARG V(n_local_out) VAL='supply_v/2' FALL=1\n")
        top_file.write(".MEASURE TRAN meas_total_trise TRIG V(n_1_4) VAL='supply_v/2' RISE=1\n")
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
        
        top_file.write("Xcarrychain_shape1 vdd gnd n_in n_1_1 n_hang n_p_1 vdd gnd FA_carry_chain\n")
        top_file.write("Xcarrychain_shape2 vdd gnd n_1_1 n_1_2 n_hang_2 n_p_2 vdd gnd FA_carry_chain\n")
        top_file.write("Xcarrychain_shape3 vdd gnd n_1_2 n_hang_3 n_1_3 n_p_3 vdd gnd FA_carry_chain\n")
        top_file.write("Xinv_shape n_1_3 n_1_4 vdd gnd carry_chain_perf\n")
        top_file.write("Xthemux n_1_4 n_1_5 vdd gnd vdd_test gnd carry_chain_mux\n")       
        top_file.write("Xlut_output_load n_1_5 n_local_out n_general_out vsram vsram_n vdd gnd vdd vdd lut_output_load\n\n")


        top_file.write(f"Xgeneral_ble_output_load n_general_out n_hang1 vsram vsram_n vdd gnd {self.gen_ble_out_load.name}\n")
        top_file.write(".END")
        top_file.close()

        # Come out of top-level directory
        os.chdir("../")
        
        return (self.name + "/" + self.name + ".sp")

    def generate_top(self, gen_r_wire):       

        print("Generating top-level " + self.name)
        self.top_spice_path = self.generate_cc_mux_top()

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
        """ Update wire of member objects. """
        # Update wire lengths
        if not self.use_tgate :
            wire_lengths["wire_" + self.name] = width_dict["ptran_" + self.name]
        else :
            wire_lengths["wire_" + self.name] = width_dict["tgate_" + self.name]

        wire_lengths["wire_" + self.name + "_driver"] = (width_dict["inv_" + self.name + "_1"] + width_dict["inv_" + self.name + "_1"])/4
        
        # Update wire layers
        wire_layers["wire_" + self.name] = 0
        wire_layers["wire_lut_to_flut_mux"] = 0
        wire_layers["wire_" + self.name + "_driver"] = 0

class _CarryChainPer(_SizableCircuit):
    """ Carry Chain Peripherals class. Used to measure the delay from the Cin to Sout.  """
    def __init__(self, use_finfet, carry_chain_type, N, FAs_per_flut, use_tgate):
        self.name = "carry_chain_perf"
        self.use_finfet = use_finfet
        self.carry_chain_type = carry_chain_type
        # handled in the check_arch_params funciton in utils.py
        # assert FAs_per_flut <= 2
        self.FAs_per_flut = FAs_per_flut
        # how many Fluts do we have in a cluster?
        self.N = N        
        self.use_tgate = use_tgate



    def generate(self, subcircuit_filename, min_tran_width, use_finfet):
        """ Generate the SPICE netlists."""  


        # if type is skip, we need to generate two levels of nand + not for the and tree
        # if type is ripple, we need to add the delay of one inverter for the final sum.
        self.transistor_names, self.wire_names = lut_subcircuits.generate_carry_chain_perf_ripple(subcircuit_filename, self.name, use_finfet)
        self.initial_transistor_sizes["inv_" + self.name + "_1_nmos"] = 1
        self.initial_transistor_sizes["inv_" + self.name + "_1_pmos"] = 1

        return self.initial_transistor_sizes

        
    def generate_carry_chain_ripple_top(self):

        # Create directories
        if not os.path.exists(self.name):
            os.makedirs(self.name)  
        # Change to directory    
        os.chdir(self.name)  
        
        filename = self.name + ".sp"
        top_file = open(filename, 'w')
        top_file.write(".TITLE Carry Chain\n\n") 
        
        top_file.write("********************************************************************************\n")
        top_file.write("** Include libraries, parameters and other\n")
        top_file.write("********************************************************************************\n\n")
        top_file.write(".LIB \"../includes.l\" INCLUDES\n\n")
        
        top_file.write("********************************************************************************\n")
        top_file.write("** Setup and input\n")
        top_file.write("********************************************************************************\n\n")
        top_file.write(".TRAN 1p 26n SWEEP DATA=sweep_data\n")
        top_file.write(".OPTIONS BRIEF=1\n\n")
        top_file.write("* Input signals\n")


        top_file.write("VIN n_in gnd PULSE (0 supply_v 0 0 0 2n 4n)\n\n")
        top_file.write("* Power rail for the circuit under test.\n")
        top_file.write("* This allows us to measure power of a circuit under test without measuring the power of wave shaping and load circuitry.\n")
        top_file.write("V_test vdd_test gnd supply_v\n\n")

        top_file.write("********************************************************************************\n")
        top_file.write("** Measurement\n")
        top_file.write("********************************************************************************\n\n")
        top_file.write("* inv_carry_chain_1 delay\n")
        top_file.write(".MEASURE TRAN meas_inv_carry_chain_perf_1_tfall TRIG V(n_1_2) VAL='supply_v/2' FALL=1\n")
        top_file.write("+    TARG V(n_out) VAL='supply_v/2' FALL=1\n")
        top_file.write(".MEASURE TRAN meas_inv_carry_chain_perf_1_trise TRIG V(n_1_2) VAL='supply_v/2' RISE=1\n")
        top_file.write("+    TARG V(n_out) VAL='supply_v/2' RISE=1\n\n")


        top_file.write(".MEASURE TRAN meas_total_tfall TRIG V(n_1_2) VAL='supply_v/2' FALL=1\n")
        top_file.write("+    TARG V(n_out) VAL='supply_v/2' FALL=1\n")
        top_file.write(".MEASURE TRAN meas_total_trise TRIG V(n_1_2) VAL='supply_v/2' RISE=1\n")
        top_file.write("+    TARG V(n_out) VAL='supply_v/2' RISE=1\n\n")

        top_file.write(".MEASURE TRAN meas_logic_low_voltage FIND V(gnd) AT=3n\n\n")

        top_file.write("* Measure the power required to propagate a rise and a fall transition through the subcircuit at 250MHz.\n")
        top_file.write(".MEASURE TRAN meas_current INTEGRAL I(V_test) FROM=0ns TO=26ns\n")
        top_file.write(".MEASURE TRAN meas_avg_power PARAM = '-((meas_current)/26n)*supply_v'\n\n")

        top_file.write("********************************************************************************\n")
        top_file.write("** Circuit\n")
        top_file.write("********************************************************************************\n\n")

        # Generate Cin as part of wave-shaping circuitry:
        top_file.write("Xcarrychain_shape1 vdd gnd n_in n_1_1 n_hang n_p_1 vdd gnd FA_carry_chain\n")
        top_file.write("Xcarrychain_shape2 vdd gnd n_1_1 n_1_2 n_hang_s n_p_2 vdd gnd FA_carry_chain\n")
        
        
        # Generate the uni under test:
        top_file.write("Xcarrychain_main vdd gnd n_1_2 n_hang_2 n_1_3 n_p_3 vdd gnd FA_carry_chain\n")
        top_file.write("Xinv n_1_3 n_out vdd_test gnd carry_chain_perf\n")
        
        # generate typical load
        top_file.write("Xthemux n_out n_out2 vdd gnd vdd gnd carry_chain_mux\n")  

        top_file.write(".END")
        top_file.close()

        # Come out of top-level directory
        os.chdir("../")
        
        return (self.name + "/" + self.name + ".sp")
        


    def generate_carry_chain_skip_top(self):

        # Create directories
        if not os.path.exists(self.name):
            os.makedirs(self.name)  
        # Change to directory    
        os.chdir(self.name)  
        
        filename = self.name + ".sp"
        top_file = open(filename, 'w')
        top_file.write(".TITLE Carry Chain\n\n") 
        
        top_file.write("********************************************************************************\n")
        top_file.write("** Include libraries, parameters and other\n")
        top_file.write("********************************************************************************\n\n")
        top_file.write(".LIB \"../includes.l\" INCLUDES\n\n")
        
        top_file.write("********************************************************************************\n")
        top_file.write("** Setup and input\n")
        top_file.write("********************************************************************************\n\n")
        top_file.write(".TRAN 1p 26n SWEEP DATA=sweep_data\n")
        top_file.write(".OPTIONS BRIEF=1\n\n")
        top_file.write("* Input signals\n")


        top_file.write("VIN n_in gnd PULSE (0 supply_v 0 0 0 2n 4n)\n\n")
        top_file.write("* Power rail for the circuit under test.\n")
        top_file.write("* This allows us to measure power of a circuit under test without measuring the power of wave shaping and load circuitry.\n")
        top_file.write("V_test vdd_test gnd supply_v\n\n")

        top_file.write("********************************************************************************\n")
        top_file.write("** Measurement\n")
        top_file.write("********************************************************************************\n\n")
        top_file.write("* inv_carry_chain_1 delay\n")
        top_file.write(".MEASURE TRAN meas_inv_carry_chain_perf_1_tfall TRIG V(n_1_2) VAL='supply_v/2' FALL=1\n")
        top_file.write("+    TARG V(n_out) VAL='supply_v/2' FALL=1\n")
        top_file.write(".MEASURE TRAN meas_inv_carry_chain_perf_1_trise TRIG V(n_1_2) VAL='supply_v/2' RISE=1\n")
        top_file.write("+    TARG V(n_out) VAL='supply_v/2' RISE=1\n\n")


        top_file.write(".MEASURE TRAN meas_total_tfall TRIG V(n_1_2) VAL='supply_v/2' FALL=1\n")
        top_file.write("+    TARG V(n_out) VAL='supply_v/2' FALL=1\n")
        top_file.write(".MEASURE TRAN meas_total_trise TRIG V(n_1_2) VAL='supply_v/2' RISE=1\n")
        top_file.write("+    TARG V(n_out) VAL='supply_v/2' RISE=1\n\n")

        top_file.write(".MEASURE TRAN meas_logic_low_voltage FIND V(gnd) AT=3n\n\n")

        top_file.write("* Measure the power required to propagate a rise and a fall transition through the subcircuit at 250MHz.\n")
        top_file.write(".MEASURE TRAN meas_current INTEGRAL I(V_test) FROM=0ns TO=26ns\n")
        top_file.write(".MEASURE TRAN meas_avg_power PARAM = '-((meas_current)/26n)*supply_v'\n\n")

        top_file.write("********************************************************************************\n")
        top_file.write("** Circuit\n")
        top_file.write("********************************************************************************\n\n")

        # Generate Cin as part of wave-shaping circuitry:
        top_file.write("Xcarrychain_shape1 vdd gnd n_in n_1_1 n_hang n_p_1 vdd gnd FA_carry_chain\n")
        top_file.write("Xcarrychain_shape2 vdd gnd n_1_1 n_1_2 n_hang_s n_p_2 vdd gnd FA_carry_chain\n")
        
        
        # Generate the uni under test:
        top_file.write("Xcarrychain_main vdd gnd n_1_2 n_hang_2 n_1_3 n_p_3 vdd gnd FA_carry_chain\n")
        top_file.write("Xinv n_1_3 n_out vdd_test gnd carry_chain_perf\n")

        # generate typical load
        top_file.write("Xthemux n_out n_out2 vdd gnd vdd gnd carry_chain_mux\n")  

        top_file.write(".END")
        top_file.close()

        # Come out of top-level directory
        os.chdir("../")
        
        return (self.name + "/" + self.name + ".sp")

    def generate_top(self):
        """ Generate Top-level Evaluation Path for the Carry chain """

        if self.carry_chain_type == "ripple":
            self.top_spice_path = self.generate_carry_chain_ripple_top()
        else:
            self.top_spice_path = self.generate_carry_chain_skip_top()


    def update_area(self, area_dict, width_dict):
        """ Calculate Carry Chain area and update dictionaries. """

        area = area_dict["inv_carry_chain_perf_1"]    
        area_with_sram = area
        width = math.sqrt(area)
        area_dict[self.name] = area
        width_dict[self.name] = width


    def update_wires(self, width_dict, wire_lengths, wire_layers):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """
        pass


class _CarryChain(_SizableCircuit):
    """ Carry Chain class.    """
    def __init__(self, use_finfet, carry_chain_type, N, FAs_per_flut):
        # Carry chain name
        self.name = "carry_chain"
        self.use_finfet = use_finfet
        # ripple or skip?
        self.carry_chain_type = carry_chain_type
        # added to the check_arch_params function
        # assert FAs_per_flut <= 2      
        self.FAs_per_flut = FAs_per_flut
        # how many Fluts do we have in a cluster?
        self.N = N


    def generate(self, subcircuit_filename, min_tran_width, use_finfet):
        """ Generate Carry chain SPICE netlists."""  

        self.transistor_names, self.wire_names = lut_subcircuits.generate_full_adder_simplified(subcircuit_filename, self.name, use_finfet)

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

    def generate_carrychain_top(self):
        """ """
        
        # Create directories
        if not os.path.exists(self.name):
            os.makedirs(self.name)  
        # Change to directory    
        os.chdir(self.name)  
        
        filename = self.name + ".sp"
        top_file = open(filename, 'w')
        top_file.write(".TITLE Carry Chain\n\n") 
        
        top_file.write("********************************************************************************\n")
        top_file.write("** Include libraries, parameters and other\n")
        top_file.write("********************************************************************************\n\n")
        top_file.write(".LIB \"../includes.l\" INCLUDES\n\n")
        
        top_file.write("********************************************************************************\n")
        top_file.write("** Setup and input\n")
        top_file.write("********************************************************************************\n\n")
        top_file.write(".TRAN 1p 26n SWEEP DATA=sweep_data\n")
        top_file.write(".OPTIONS BRIEF=1\n\n")
        top_file.write("* Input signals\n")

        #top_file.write("VIN n_a gnd PWL (0 0 1.999n 0 2n 'supply_v' 3.999n 'supply_v' 4n 0 13.999n 0 14n 'supply_v' 23.999n 'supply_v' 24n 0)\n\n")
        #top_file.write("VIN2 n_b gnd PWL (0 0 5.999n 0 6n supply_v 7.999n supply_v 8n 0 17.999n 0 18n supply_v 19.999n supply_v 20n 0 21.999n 0 22n supply_v)\n\n")
        #top_file.write("VIN3 n_cin gnd PWL (0 0 9.999n 0 10n supply_v 11.999n supply_v 12n 0 13.999n 0 14n supply_v 15.999n supply_v 16n 0 )\n\n")
        #top_file.write("VIN n_a gnd PWL (0 0 1.999n 0 2n 'supply_v' 3.999n 'supply_v' 4n 0 13.999n 0 14n 'supply_v' 23.999n 'supply_v' 24n 0)\n\n")
        #top_file.write("VIN2 n_b gnd PWL (0 0 5.999n 0 6n supply_v 7.999n supply_v 8n 0 17.999n 0 18n supply_v 19.999n supply_v 20n 0 21.999n 0 22n supply_v)\n\n")
        #top_file.write("VIN3 n_cin gnd PWL (0 0 9.999n 0 10n supply_v 11.999n supply_v 12n 0 13.999n 0 14n supply_v 15.999n supply_v 16n 0 )\n\n")
        
        top_file.write("VIN n_in gnd PULSE (0 supply_v 0 0 0 2n 4n)\n\n")
        top_file.write("* Power rail for the circuit under test.\n")
        top_file.write("* This allows us to measure power of a circuit under test without measuring the power of wave shaping and load circuitry.\n")
        top_file.write("V_test vdd_test gnd supply_v\n\n")

        top_file.write("********************************************************************************\n")
        top_file.write("** Measurement\n")
        top_file.write("********************************************************************************\n\n")
        top_file.write("* inv_carry_chain_1 delay\n")
        top_file.write(".MEASURE TRAN meas_inv_carry_chain_1_tfall TRIG V(n_1_1) VAL='supply_v/2' RISE=1\n")
        top_file.write("+    TARG V(Xcarrychain.n_cin_in_bar) VAL='supply_v/2' FALL=1\n")
        top_file.write(".MEASURE TRAN meas_inv_carry_chain_1_trise TRIG V(n_1_1) VAL='supply_v/2' FALL=1\n")
        top_file.write("+    TARG V(Xcarrychain.n_cin_in_bar) VAL='supply_v/2' RISE=1\n\n")

        top_file.write("* inv_carry_chain_2 delays\n")
        top_file.write(".MEASURE TRAN meas_inv_carry_chain_2_tfall TRIG V(n_1_1) VAL='supply_v/2' RISE=1\n")
        top_file.write("+    TARG V(n_sum_out) VAL='supply_v/2' FALL=1\n")
        top_file.write(".MEASURE TRAN meas_inv_carry_chain_2_trise TRIG V(n_1_1) VAL='supply_v/2' FALL=1\n")
        top_file.write("+    TARG V(n_sum_out) VAL='supply_v/2' RISE=1\n\n")
        top_file.write("* Total delays\n")


        top_file.write(".MEASURE TRAN meas_total_tfall TRIG V(n_1_1) VAL='supply_v/2' RISE=1\n")
        top_file.write("+    TARG V(n_1_2) VAL='supply_v/2' FALL=1\n")
        top_file.write(".MEASURE TRAN meas_total_trise TRIG V(n_1_1) VAL='supply_v/2' FALL=1\n")
        top_file.write("+    TARG V(n_1_2) VAL='supply_v/2' RISE=1\n\n")

        top_file.write(".MEASURE TRAN meas_logic_low_voltage FIND V(gnd) AT=3n\n\n")

        top_file.write("* Measure the power required to propagate a rise and a fall transition through the subcircuit at 250MHz.\n")
        top_file.write(".MEASURE TRAN meas_current INTEGRAL I(V_test) FROM=0ns TO=26ns\n")
        top_file.write(".MEASURE TRAN meas_avg_power PARAM = '-((meas_current)/26n)*supply_v'\n\n")

        top_file.write("********************************************************************************\n")
        top_file.write("** Circuit\n")
        top_file.write("********************************************************************************\n\n")

        # Generate Cin as part of wave-shaping circuitry:
        top_file.write("Xcarrychain_shape vdd gnd n_in n_0_1 n_hang n_p_1 vdd gnd FA_carry_chain\n")
        top_file.write("Xcarrychain_shape1 vdd gnd n_0_1 n_0_2 n_hangz n_p_0 vdd gnd FA_carry_chain\n")
        top_file.write("Xcarrychain_shape2 vdd gnd n_0_2 n_1_1 n_hangzz n_p_z vdd gnd FA_carry_chain\n")
        
        # Generate the adder under test:
        top_file.write("Xcarrychain vdd gnd n_1_1 n_1_2 n_sum_out n_p_2 vdd_test gnd FA_carry_chain\n")
        
        # cout typical load
        top_file.write("Xcarrychain_load vdd gnd n_1_2 n_1_3 n_sum_out2 n_p_3 vdd gnd FA_carry_chain\n")      

        top_file.write(".END")
        top_file.close()

        # Come out of top-level directory
        os.chdir("../")
        
        return (self.name + "/" + self.name + ".sp")


    def generate_top(self):
        """ Generate Top-level Evaluation Path for Carry chain """

        self.top_spice_path = self.generate_carrychain_top()

    def update_area(self, area_dict, width_dict):
        """ Calculate Carry Chain area and update dictionaries. """
        area = area_dict["inv_carry_chain_1"] * 2 + area_dict["inv_carry_chain_2"] + area_dict["tgate_carry_chain_1"] * 4 + area_dict["tgate_carry_chain_2"] * 4
        area = area + area_dict["carry_chain_perf"]
        area_with_sram = area
        width = math.sqrt(area)
        area_dict[self.name] = area
        width_dict[self.name] = width

    def update_wires(self, width_dict, wire_lengths, wire_layers):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """
        if self.FAs_per_flut ==2:
            wire_lengths["wire_" + self.name + "_1"] = width_dict["lut_and_drivers"] # Wire for input A
        else:
            wire_lengths["wire_" + self.name + "_1"] = width_dict[self.name] # Wire for input A
        wire_layers["wire_" + self.name + "_1"] = 0
        wire_lengths["wire_" + self.name + "_2"] = width_dict[self.name] # Wire for input B
        wire_layers["wire_" + self.name + "_2"] = 0
        if self.FAs_per_flut ==1:
            wire_lengths["wire_" + self.name + "_3"] = width_dict["logic_cluster"]/(2 * self.N) # Wire for input Cin
        else:
            wire_lengths["wire_" + self.name + "_3"] = width_dict["logic_cluster"]/(4 * self.N) # Wire for input Cin
        wire_layers["wire_" + self.name + "_3"] = 0
        if self.FAs_per_flut ==1:
            wire_lengths["wire_" + self.name + "_4"] = width_dict["logic_cluster"]/(2 * self.N) # Wire for output Cout
        else:
            wire_lengths["wire_" + self.name + "_4"] = width_dict["logic_cluster"]/(4 * self.N) # Wire for output Cout
        wire_layers["wire_" + self.name + "_4"] = 0
        wire_lengths["wire_" + self.name + "_5"] = width_dict[self.name] # Wire for output Sum
        wire_layers["wire_" + self.name + "_5"] = 0

    def print_details(self):
        print(" Carry Chain DETAILS:")

          
class _CarryChainSkipAnd(_SizableCircuit):
    """ Part of peripherals used in carry chain class.    """
    def __init__(self, use_finfet, use_tgate, carry_chain_type, N, FAs_per_flut, skip_size):
        # Carry chain name
        self.name = "xcarry_chain_and"
        self.use_finfet = use_finfet
        self.use_tgate = use_tgate
        # ripple or skip?
        self.carry_chain_type = carry_chain_type
        assert self.carry_chain_type == "skip"
        # size of the skip
        self.skip_size = skip_size
        # 1 FA per FA or 2?
        self.FAs_per_flut = FAs_per_flut
        # how many Fluts do we have in a cluster?
        self.N = N

        self.nand1_size = 2
        self.nand2_size = 2

        # this size is currently a limit due to how the and tree is being generated
        assert skip_size >= 4 and skip_size <=9

        if skip_size == 6:
            self.nand2_size = 3
        elif skip_size == 5:
            self.nand1_size = 3
        elif skip_size > 6:
            self.nand1_size = 3
            self.nand2_size = 3


    def generate(self, subcircuit_filename, min_tran_width, use_finfet):
        """ Generate Carry chain SPICE netlists."""  

        self.transistor_names, self.wire_names = lut_subcircuits.generate_skip_and_tree(subcircuit_filename, self.name, use_finfet, self.nand1_size, self.nand2_size)

        self.initial_transistor_sizes["inv_nand"+str(self.nand1_size)+"_xcarry_chain_and_1_nmos"] = 1
        self.initial_transistor_sizes["inv_nand"+str(self.nand1_size)+"_xcarry_chain_and_1_pmos"] = 1
        self.initial_transistor_sizes["inv_xcarry_chain_and_2_nmos"] = 1
        self.initial_transistor_sizes["inv_xcarry_chain_and_2_pmos"] = 1
        self.initial_transistor_sizes["inv_nand"+str(self.nand2_size)+"_xcarry_chain_and_3_nmos"] = 1
        self.initial_transistor_sizes["inv_nand"+str(self.nand2_size)+"_xcarry_chain_and_3_pmos"] = 1
        self.initial_transistor_sizes["inv_xcarry_chain_and_4_nmos"] = 1
        self.initial_transistor_sizes["inv_xcarry_chain_and_4_pmos"] = 1

        return self.initial_transistor_sizes

    def generate_carrychainand_top(self):
        # Create directories
        if not os.path.exists(self.name):
            os.makedirs(self.name)  
        # Change to directory    
        os.chdir(self.name)  
        
        filename = self.name + ".sp"
        top_file = open(filename, 'w')
        top_file.write(".TITLE Carry Chain\n\n") 
        
        top_file.write("********************************************************************************\n")
        top_file.write("** Include libraries, parameters and other\n")
        top_file.write("********************************************************************************\n\n")
        top_file.write(".LIB \"../includes.l\" INCLUDES\n\n")
        
        top_file.write("********************************************************************************\n")
        top_file.write("** Setup and input\n")
        top_file.write("********************************************************************************\n\n")
        top_file.write(".TRAN 1p 26n SWEEP DATA=sweep_data\n")
        top_file.write(".OPTIONS BRIEF=1\n\n")
        top_file.write("* Input signals\n")

        top_file.write("VIN n_in gnd PULSE (0 supply_v 0 0 0 2n 4n)\n\n")
        top_file.write("* Power rail for the circuit under test.\n")
        top_file.write("* This allows us to measure power of a circuit under test without measuring the power of wave shaping and load circuitry.\n")
        top_file.write("V_test vdd_test gnd supply_v\n\n")

        top_file.write("********************************************************************************\n")
        top_file.write("** Measurement\n")
        top_file.write("********************************************************************************\n\n")
        top_file.write("* inv_nand"+self.name+"_1 delay\n")
        top_file.write(".MEASURE TRAN meas_inv_nand"+str(self.nand1_size)+"_"+self.name+"_1_tfall TRIG V(n_1_2) VAL='supply_v/2' RISE=1\n")
        top_file.write("+    TARG V(Xandtree.n_1_2) VAL='supply_v/2' FALL=1\n")
        top_file.write(".MEASURE TRAN meas_inv_nand"+str(self.nand1_size)+"_"+self.name+"_1_trise TRIG V(n_1_2) VAL='supply_v/2' FALL=1\n")
        top_file.write("+    TARG V(Xandtree.n_1_2) VAL='supply_v/2' RISE=1\n\n")

        top_file.write("* inv_"+self.name+"_2 delays\n")
        top_file.write(".MEASURE TRAN meas_inv_"+self.name+"_2_tfall TRIG V(n_1_2) VAL='supply_v/2' FALL=1\n")
        top_file.write("+    TARG V(Xandtree.n_1_3) VAL='supply_v/2' FALL=1\n")
        top_file.write(".MEASURE TRAN meas_inv_"+self.name+"_2_trise TRIG V(n_1_2) VAL='supply_v/2' RISE=1\n")
        top_file.write("+    TARG V(Xandtree.n_1_3) VAL='supply_v/2' RISE=1\n\n")
        top_file.write("* Total delays\n")


        top_file.write("* inv_nand"+self.name+"_3 delay\n")
        top_file.write(".MEASURE TRAN meas_inv_nand"+str(self.nand2_size)+"_"+self.name+"_3_tfall TRIG V(n_1_2) VAL='supply_v/2' RISE=1\n")
        top_file.write("+    TARG V(Xandtree.n_1_5) VAL='supply_v/2' FALL=1\n")
        top_file.write(".MEASURE TRAN meas_inv_nand"+str(self.nand2_size)+"_"+self.name+"_3_trise TRIG V(n_1_2) VAL='supply_v/2' FALL=1\n")
        top_file.write("+    TARG V(Xandtree.n_1_5) VAL='supply_v/2' RISE=1\n\n")

        top_file.write("* inv_"+self.name+"_4 delays\n")
        top_file.write(".MEASURE TRAN meas_inv_"+self.name+"_4_tfall TRIG V(n_1_2) VAL='supply_v/2' FALL=1\n")
        top_file.write("+    TARG V(n_1_3) VAL='supply_v/2' FALL=1\n")
        top_file.write(".MEASURE TRAN meas_inv_"+self.name+"_4_trise TRIG V(n_1_2) VAL='supply_v/2' RISE=1\n")
        top_file.write("+    TARG V(n_1_3) VAL='supply_v/2' RISE=1\n\n")
        top_file.write("* Total delays\n")

        top_file.write(".MEASURE TRAN meas_total_tfall TRIG V(n_1_2) VAL='supply_v/2' FALL=1\n")
        top_file.write("+    TARG V(n_1_3) VAL='supply_v/2' FALL=1\n")
        top_file.write(".MEASURE TRAN meas_total_trise TRIG V(n_1_2) VAL='supply_v/2' RISE=1\n")
        top_file.write("+    TARG V(n_1_3) VAL='supply_v/2' RISE=1\n\n")

        top_file.write(".MEASURE TRAN meas_logic_low_voltage FIND V(gnd) AT=3n\n\n")

        top_file.write("* Measure the power required to propagate a rise and a fall transition through the subcircuit at 250MHz.\n")
        top_file.write(".MEASURE TRAN meas_current INTEGRAL I(V_test) FROM=0ns TO=26ns\n")
        top_file.write(".MEASURE TRAN meas_avg_power PARAM = '-((meas_current)/26n)*supply_v'\n\n")

        top_file.write("********************************************************************************\n")
        top_file.write("** Circuit\n")
        top_file.write("********************************************************************************\n\n")

        # Generate Cin as part of wave-shaping circuitry:
        if not self.use_tgate:
            top_file.write("Xlut n_in n_1_1 vdd vdd vdd vdd vdd vdd vdd gnd lut\n")
        else :
            top_file.write("Xlut n_in n_1_1 vdd gnd vdd gnd vdd gnd vdd gnd vdd gnd vdd gnd vdd gnd lut\n\n")
        
        top_file.write("Xcarrychain n_1_1 vdd gnd n_hang n_sum_out n_1_2 vdd gnd FA_carry_chain\n")
        # Generate the unit under test:
        top_file.write("Xandtree n_1_2 n_1_3 vdd_test gnd xcarry_chain_and\n")
        # typical load
        top_file.write("Xcarrychainskip_mux n_1_3 n_1_4 vdd gnd vdd gnd xcarry_chain_mux\n")   
        top_file.write("Xcarrychain_mux n_1_4 n_1_5 vdd gnd vdd gnd carry_chain_mux\n")     

        top_file.write(".END")
        top_file.close()

        # Come out of top-level directory
        os.chdir("../")
        
        return (self.name + "/" + self.name + ".sp")


    def generate_top(self):
        """ Generate Top-level Evaluation Path for Carry chain """

        self.top_spice_path = self.generate_carrychainand_top()

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
        if self.FAs_per_flut ==2:
            wire_lengths["wire_" + self.name + "_1"] = (width_dict["ble"]*self.skip_size)/4.0
        else:
            wire_lengths["wire_" + self.name + "_1"] = (width_dict["ble"]*self.skip_size)/2.0
        wire_layers["wire_" + self.name + "_1"] = 0
        wire_lengths["wire_" + self.name + "_2"] = width_dict[self.name]/2.0
        wire_layers["wire_" + self.name + "_2"] = 0

    def print_details(self):
        print(" Carry Chain DETAILS:")

class _CarryChainInterCluster(_SizableCircuit):
    """ Wire dirvers of carry chain path between clusters"""
    def __init__(self, use_finfet, carry_chain_type, inter_wire_length):
        # Carry chain name
        self.name = "carry_chain_inter"
        self.use_finfet = use_finfet
        # Ripple or Skip?
        self.carry_chain_type = carry_chain_type
        # length of the wire between cout of a cluster to cin of the other
        self.inter_wire_length = inter_wire_length

    def generate(self, subcircuit_filename, min_tran_width, use_finfet):
        """ Generate Carry chain SPICE netlists."""  

        self.transistor_names, self.wire_names = lut_subcircuits.generate_carry_inter(subcircuit_filename, self.name, use_finfet)

        self.initial_transistor_sizes["inv_" + self.name + "_1_nmos"] = 1
        self.initial_transistor_sizes["inv_" + self.name + "_1_pmos"] = 1
        self.initial_transistor_sizes["inv_" + self.name + "_2_nmos"] = 2
        self.initial_transistor_sizes["inv_" + self.name + "_2_pmos"] = 2

        return self.initial_transistor_sizes

    def generate_carry_inter_top(self):

        # Create directories
        if not os.path.exists(self.name):
            os.makedirs(self.name)  
        # Change to directory    
        os.chdir(self.name)  
        
        filename = self.name + ".sp"
        top_file = open(filename, 'w')
        top_file.write(".TITLE Carry Chain\n\n") 
        
        top_file.write("********************************************************************************\n")
        top_file.write("** Include libraries, parameters and other\n")
        top_file.write("********************************************************************************\n\n")
        top_file.write(".LIB \"../includes.l\" INCLUDES\n\n")
        
        top_file.write("********************************************************************************\n")
        top_file.write("** Setup and input\n")
        top_file.write("********************************************************************************\n\n")
        top_file.write(".TRAN 1p 26n SWEEP DATA=sweep_data\n")
        top_file.write(".OPTIONS BRIEF=1\n\n")
        top_file.write("* Input signals\n")

        top_file.write("VIN n_in gnd PULSE (0 supply_v 0 0 0 2n 4n)\n\n")
        top_file.write("* Power rail for the circuit under test.\n")
        top_file.write("* This allows us to measure power of a circuit under test without measuring the power of wave shaping and load circuitry.\n")
        top_file.write("V_test vdd_test gnd supply_v\n\n")

        top_file.write("********************************************************************************\n")
        top_file.write("** Measurement\n")
        top_file.write("********************************************************************************\n\n")
        top_file.write("* inv_nand"+self.name+"_1 delay\n")
        top_file.write(".MEASURE TRAN meas_inv_"+self.name+"_1_tfall TRIG V(n_1_2) VAL='supply_v/2' RISE=1\n")
        top_file.write("+    TARG V(Xdrivers.n_1_1) VAL='supply_v/2' FALL=1\n")
        top_file.write(".MEASURE TRAN meas_inv_"+self.name+"_1_trise TRIG V(n_1_2) VAL='supply_v/2' FALL=1\n")
        top_file.write("+    TARG V(Xdrivers.n_1_1) VAL='supply_v/2' RISE=1\n\n")

        top_file.write("* inv_"+self.name+"_2 delays\n")
        top_file.write(".MEASURE TRAN meas_inv_"+self.name+"_2_tfall TRIG V(n_1_2) VAL='supply_v/2' FALL=1\n")
        top_file.write("+    TARG V(n_1_3) VAL='supply_v/2' FALL=1\n")
        top_file.write(".MEASURE TRAN meas_inv_"+self.name+"_2_trise TRIG V(n_1_2) VAL='supply_v/2' RISE=1\n")
        top_file.write("+    TARG V(n_1_3) VAL='supply_v/2' RISE=1\n\n")
        top_file.write("* Total delays\n")

        top_file.write(".MEASURE TRAN meas_total_tfall TRIG V(n_1_2) VAL='supply_v/2' FALL=1\n")
        top_file.write("+    TARG V(n_1_3) VAL='supply_v/2' FALL=1\n")
        top_file.write(".MEASURE TRAN meas_total_trise TRIG V(n_1_2) VAL='supply_v/2' RISE=1\n")
        top_file.write("+    TARG V(n_1_3) VAL='supply_v/2' RISE=1\n\n")

        top_file.write(".MEASURE TRAN meas_logic_low_voltage FIND V(gnd) AT=3n\n\n")

        top_file.write("* Measure the power required to propagate a rise and a fall transition through the subcircuit at 250MHz.\n")
        top_file.write(".MEASURE TRAN meas_current INTEGRAL I(V_test) FROM=0ns TO=26ns\n")
        top_file.write(".MEASURE TRAN meas_avg_power PARAM = '-((meas_current)/26n)*supply_v'\n\n")

        top_file.write("********************************************************************************\n")
        top_file.write("** Circuit\n")
        top_file.write("********************************************************************************\n\n")

        # Generate Cin as part of wave-shaping circuitry:
        top_file.write("Xcarrychain_0 vdd gnd n_in n_1_1 n_sum_out n_1p vdd gnd FA_carry_chain\n")   
        top_file.write("Xcarrychain vdd gnd n_1_1 n_1_2 n_sum_out2 n_2p vdd gnd FA_carry_chain\n")

        # Generate the unit under test:
        top_file.write("Xdrivers n_1_2 n_1_3 vdd_test gnd carry_chain_inter\n")
        # typical load (next carry chain)
        top_file.write("Xcarrychain_l n_1_3 vdd gnd n_hangl n_sum_out3 n_3p vdd gnd FA_carry_chain\n")   
        

        top_file.write(".END")
        top_file.close()

        # Come out of top-level directory
        os.chdir("../")
        
        return (self.name + "/" + self.name + ".sp")


    def generate_top(self):
        """ Generate Top-level Evaluation Path for Carry chain """

        self.top_spice_path = self.generate_carry_inter_top()

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
        wire_layers["wire_" + self.name + "_1"] = 0



class _CarryChainSkipMux(_SizableCircuit):
    """ Part of peripherals used in carry chain class.    """
    def __init__(self, use_finfet, carry_chain_type, use_tgate):
        # Carry chain name
        self.name = "xcarry_chain_mux"
        self.use_finfet = use_finfet
        # ripple or skip?
        self.carry_chain_type = carry_chain_type
        assert self.carry_chain_type == "skip"
        self.use_tgate = use_tgate



    def generate(self, subcircuit_filename, min_tran_width, use_finfet):
        """ Generate the SPICE netlists."""  

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


    def generate_skip_mux_top(self):
        # Create directories
        if not os.path.exists(self.name):
            os.makedirs(self.name)  
        # Change to directory    
        os.chdir(self.name)  
        
        filename = self.name + ".sp"
        top_file = open(filename, 'w')
        top_file.write(".TITLE Carry Chain\n\n")


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
        top_file.write("V_FLUT vdd_test gnd supply_v\n\n")

        top_file.write("********************************************************************************\n")
        top_file.write("** Measurement\n")
        top_file.write("********************************************************************************\n\n")
        top_file.write("* inv_"+ self.name +"_1 delay\n")
        top_file.write(".MEASURE TRAN meas_inv_"+ self.name +"_1_tfall TRIG V(n_1_3) VAL='supply_v/2' RISE=1\n")
        top_file.write("+    TARG V(Xcarrychainskip_mux.n_2_1) VAL='supply_v/2' FALL=1\n")
        top_file.write(".MEASURE TRAN meas_inv_"+ self.name +"_1_trise TRIG V(n_1_3) VAL='supply_v/2' FALL=1\n")
        top_file.write("+    TARG V(Xcarrychainskip_mux.n_2_1) VAL='supply_v/2' RISE=1\n\n")
        top_file.write("* inv_"+ self.name +"_2 delays\n")
        top_file.write(".MEASURE TRAN meas_inv_"+ self.name +"_2_tfall TRIG V(n_1_3) VAL='supply_v/2' FALL=1\n")
        top_file.write("+    TARG V(n_1_4) VAL='supply_v/2' FALL=1\n")
        top_file.write(".MEASURE TRAN meas_inv_"+ self.name +"_2_trise TRIG V(n_1_3) VAL='supply_v/2' RISE=1\n")
        top_file.write("+    TARG V(n_1_4) VAL='supply_v/2' RISE=1\n\n")
        top_file.write("* Total delays\n")
        top_file.write(".MEASURE TRAN meas_total_tfall TRIG V(n_1_3) VAL='supply_v/2' FALL=1\n")
        #top_file.write("+    TARG V(n_1_3) VAL='supply_v/2' FALL=1\n")
        top_file.write("+    TARG V(n_1_4) VAL='supply_v/2' FALL=1\n")
        top_file.write(".MEASURE TRAN meas_total_trise TRIG V(n_1_3) VAL='supply_v/2' RISE=1\n")
        #top_file.write("+    TARG V(n_1_3) VAL='supply_v/2' RISE=1\n\n")
        top_file.write("+    TARG V(n_1_4) VAL='supply_v/2' RISE=1\n\n")
        top_file.write(".MEASURE TRAN meas_logic_low_voltage FIND V(n_general_out) AT=3n\n\n")

        top_file.write("* Measure the power required to propagate a rise and a fall transition through the subcircuit at 250MHz.\n")
        top_file.write(".MEASURE TRAN meas_current INTEGRAL I(V_FLUT) FROM=0ns TO=4ns\n")
        top_file.write(".MEASURE TRAN meas_avg_power PARAM = '-((meas_current)/4n)*supply_v'\n\n")


        top_file.write("********************************************************************************\n")
        top_file.write("** Circuit\n")
        top_file.write("********************************************************************************\n\n")

        # Generate Cin as part of wave-shaping circuitry:
        if not self.use_tgate:
            top_file.write("Xlut n_in n_1_1 vdd vdd vdd vdd vdd vdd vdd gnd lut\n")
        else :
            top_file.write("Xlut n_in n_1_1 vdd gnd vdd gnd vdd gnd vdd gnd vdd gnd vdd gnd vdd gnd lut\n\n")
        
        top_file.write("Xcarrychain n_1_1 vdd gnd n_hang n_sum_out n_1_2 vdd gnd FA_carry_chain\n")
        
        top_file.write("Xandtree n_1_2 n_1_3 vdd gnd xcarry_chain_and\n")
        # Generate the unit under test:
        top_file.write("Xcarrychainskip_mux n_1_3 n_1_4 vdd gnd vdd_test gnd xcarry_chain_mux\n")   
        # typical load
        top_file.write("Xcarrychain_mux n_1_4 n_1_5 vdd gnd vdd gnd carry_chain_mux\n")     

        top_file.write(".END")
        top_file.close()

        # Come out of top-level directory
        os.chdir("../")
        return (self.name + "/" + self.name + ".sp")


    def generate_top(self):       

        print("Generating top-level " + self.name)
        self.top_spice_path = self.generate_skip_mux_top()

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
        """ Update wire of member objects. """
        # Update wire lengths
        if not self.use_tgate :
            wire_lengths["wire_" + self.name] = width_dict["ptran_" + self.name]
        else :
            wire_lengths["wire_" + self.name] = width_dict["tgate_" + self.name]

        wire_lengths["wire_" + self.name + "_driver"] = (width_dict["inv_" + self.name + "_1"] + width_dict["inv_" + self.name + "_1"])/4
        
        # Update wire layers
        wire_layers["wire_" + self.name] = 0
        wire_layers["wire_lut_to_flut_mux"] = 0
        wire_layers["wire_" + self.name + "_driver"] = 0    