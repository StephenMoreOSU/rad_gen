
from src.coffe.circuit_baseclasses import _SizableCircuit, _CompoundCircuit
import src.coffe.fpga as fpga

import src.coffe.lut_subcircuits as lut_subcircuits
import src.coffe.utils as utils

from typing import Dict, List, Tuple, Union, Any
import math, os



class _LUTInputDriver(_SizableCircuit):
    """ LUT input driver class. LUT input drivers can optionally support register feedback.
        They can also be connected to FF register input select. 
        Thus, there are 4  types of LUT input drivers: "default", "default_rsel", "reg_fb" and "reg_fb_rsel".
        When a LUT input driver is created in the '__init__' function, it is given one of these types.
        All subsequent processes (netlist generation, area calculations, etc.) will use this type attribute.
        """

    def __init__(self, name, type, delay_weight, use_tgate, use_fluts):
        self.name = "lut_" + name + "_driver"
        # LUT input driver type ("default", "default_rsel", "reg_fb" and "reg_fb_rsel")
        self.type = type
        # Delay weight in a representative critical path
        self.delay_weight = delay_weight
        # use pass transistor or transmission gate
        self.use_tgate = use_tgate
        self.use_fluts = use_fluts
        
    def generate(self, subcircuit_filename, min_tran_width):
        """ Generate SPICE netlist based on type of LUT input driver. """
        if not self.use_tgate :
            self.transistor_names, self.wire_names = lut_subcircuits.generate_ptran_lut_driver(subcircuit_filename, self.name, self.type)
        else :
            self.transistor_names, self.wire_names = lut_subcircuits.generate_tgate_lut_driver(subcircuit_filename, self.name, self.type)
        
        # Initialize transistor sizes (to something more reasonable than all min size, but not necessarily a good choice, depends on architecture params)
        if not self.use_tgate :
            if self.type != "default":
                self.initial_transistor_sizes["inv_" + self.name + "_0_nmos"] = 2
                self.initial_transistor_sizes["inv_" + self.name + "_0_pmos"] = 2
            if self.type == "reg_fb" or self.type == "reg_fb_rsel":
                self.initial_transistor_sizes["ptran_" + self.name + "_0_nmos"] = 2
                self.initial_transistor_sizes["rest_" + self.name + "_pmos"] = 1
            if self.type != "default":
                self.initial_transistor_sizes["inv_" + self.name + "_1_nmos"] = 1
                self.initial_transistor_sizes["inv_" + self.name + "_1_pmos"] = 1
            self.initial_transistor_sizes["inv_" + self.name + "_2_nmos"] = 2
            self.initial_transistor_sizes["inv_" + self.name + "_2_pmos"] = 2
        else :
            if self.type != "default":
                self.initial_transistor_sizes["inv_" + self.name + "_0_nmos"] = 2
                self.initial_transistor_sizes["inv_" + self.name + "_0_pmos"] = 2
            if self.type == "reg_fb" or self.type == "reg_fb_rsel":
                self.initial_transistor_sizes["tgate_" + self.name + "_0_nmos"] = 2
                self.initial_transistor_sizes["tgate_" + self.name + "_0_pmos"] = 2
            if self.type != "default":
                self.initial_transistor_sizes["inv_" + self.name + "_1_nmos"] = 1
                self.initial_transistor_sizes["inv_" + self.name + "_1_pmos"] = 1
            self.initial_transistor_sizes["inv_" + self.name + "_2_nmos"] = 2
            self.initial_transistor_sizes["inv_" + self.name + "_2_pmos"] = 2
               
        return self.initial_transistor_sizes



    def generate_lut_driver_top(self):
        """ Generate the top level lut input driver SPICE file """
        
        # Create directories
        if not os.path.exists(self.name):
            os.makedirs(self.name)  
        # Change to directory    
        os.chdir(self.name) 
    
        lut_driver_filename = self.name + ".sp"
        input_driver_file = open(lut_driver_filename, 'w')
        input_driver_file.write(".TITLE " + self.name + " \n\n") 
    
        input_driver_file.write("********************************************************************************\n")
        input_driver_file.write("** Include libraries, parameters and other\n")
        input_driver_file.write("********************************************************************************\n\n")
        input_driver_file.write(".LIB \"../includes.l\" INCLUDES\n\n")
        
        input_driver_file.write("********************************************************************************\n")
        input_driver_file.write("** Setup and input\n")
        input_driver_file.write("********************************************************************************\n\n")
        input_driver_file.write(".TRAN 1p 4n SWEEP DATA=sweep_data\n")
        input_driver_file.write(".OPTIONS BRIEF=1\n\n")
        input_driver_file.write("* Input signal\n")
        input_driver_file.write("VIN n_in gnd PULSE (0 supply_v 0 0 0 2n 4n)\n\n")
        input_driver_file.write("* Power rail for the circuit under test.\n")
        input_driver_file.write("* This allows us to measure power of a circuit under test without measuring the power of wave shaping and load circuitry.\n")
        input_driver_file.write("V_LUT_DRIVER vdd_lut_driver gnd supply_v\n\n")

        input_driver_file.write("********************************************************************************\n")
        input_driver_file.write("** Measurement\n")
        input_driver_file.write("********************************************************************************\n\n")
        # We measure different things based on the input driver type
        if self.type != "default":
            input_driver_file.write("* inv_" + self.name + "_0 delays\n")
            input_driver_file.write(".MEASURE TRAN meas_inv_" + self.name + "_0_tfall TRIG V(n_1_2) VAL='supply_v/2' RISE=1\n")
            input_driver_file.write("+    TARG V(X" + self.name + "_1.n_1_1) VAL='supply_v/2' FALL=1\n")
            input_driver_file.write(".MEASURE TRAN meas_inv_" + self.name + "_0_trise TRIG V(n_1_2) VAL='supply_v/2' FALL=1\n")
            input_driver_file.write("+    TARG V(X" + self.name + "_1.n_1_1) VAL='supply_v/2' RISE=1\n\n")
            input_driver_file.write("* inv_" + self.name + "_1 delays\n")
            input_driver_file.write(".MEASURE TRAN meas_inv_" + self.name + "_1_tfall TRIG V(n_1_2) VAL='supply_v/2' FALL=1\n")
            input_driver_file.write("+    TARG V(X" + self.name + "_1.n_3_1) VAL='supply_v/2' FALL=1\n")
            input_driver_file.write(".MEASURE TRAN meas_inv_" + self.name + "_1_trise TRIG V(n_1_2) VAL='supply_v/2' RISE=1\n")
            input_driver_file.write("+    TARG V(X" + self.name + "_1.n_3_1) VAL='supply_v/2' RISE=1\n\n")
        input_driver_file.write("* inv_" + self.name + "_2 delays\n")
        input_driver_file.write(".MEASURE TRAN meas_inv_" + self.name + "_2_tfall TRIG V(n_1_2) VAL='supply_v/2' RISE=1\n")
        input_driver_file.write("+    TARG V(n_out) VAL='supply_v/2' FALL=1\n")
        input_driver_file.write(".MEASURE TRAN meas_inv_" + self.name + "_2_trise TRIG V(n_1_2) VAL='supply_v/2' FALL=1\n")
        input_driver_file.write("+    TARG V(n_out) VAL='supply_v/2' RISE=1\n\n")
        input_driver_file.write("* Total delays\n")
        input_driver_file.write(".MEASURE TRAN meas_total_tfall TRIG V(n_1_2) VAL='supply_v/2' RISE=1\n")
        input_driver_file.write("+    TARG V(n_out) VAL='supply_v/2' FALL=1\n")
        input_driver_file.write(".MEASURE TRAN meas_total_trise TRIG V(n_1_2) VAL='supply_v/2' FALL=1\n")
        input_driver_file.write("+    TARG V(n_out) VAL='supply_v/2' RISE=1\n\n")

        input_driver_file.write(".MEASURE TRAN meas_logic_low_voltage FIND V(n_out) AT=3n\n\n")

        input_driver_file.write("* Measure the power required to propagate a rise and a fall transition through the lut driver at 250MHz.\n")
        input_driver_file.write(".MEASURE TRAN meas_current INTEGRAL I(V_LUT_DRIVER) FROM=0ns TO=4ns\n")
        input_driver_file.write(".MEASURE TRAN meas_avg_power PARAM = '-((meas_current)/4n)*supply_v'\n\n")

        input_driver_file.write("********************************************************************************\n")
        input_driver_file.write("** Circuit\n")
        input_driver_file.write("********************************************************************************\n\n")
        input_driver_file.write("Xcb_mux_on_1 n_in n_1_1 vsram vsram_n vdd gnd cb_mux_on\n")
        input_driver_file.write("Xlocal_routing_wire_load_1 n_1_1 n_1_2 vsram vsram_n vdd gnd vdd local_routing_wire_load\n")
        input_driver_file.write("X" + self.name + "_1 n_1_2 n_out vsram vsram_n n_rsel n_2_1 vdd_lut_driver gnd " + self.name + "\n")
        if self.type == "default_rsel" or self.type == "reg_fb_rsel":
            # Connect a load to n_rsel node
            input_driver_file.write("Xff n_rsel n_ff_out vsram vsram_n gnd vdd gnd vdd gnd vdd vdd gnd ff\n")
        input_driver_file.write("X" + self.name + "_not_1 n_2_1 n_out_n vdd gnd " + self.name + "_not\n")
        input_driver_file.write("X" + self.name + "_load_1 n_out vdd gnd " + self.name + "_load\n")
        input_driver_file.write("X" + self.name + "_load_2 n_out_n vdd gnd " + self.name + "_load\n\n")
        input_driver_file.write(".END")
        input_driver_file.close()

        # Come out of lut_driver directory
        os.chdir("../")
        
        return (self.name + "/" + self.name + ".sp")

    def generate_lut_and_driver_top(self):
        """ Generate the top level lut with driver SPICE file. We use this to measure final delays of paths through the LUT. """
        
        # Create directories
        if not os.path.exists(self.name):
            os.makedirs(self.name)  
        # Change to directory    
        os.chdir(self.name)  
        
        lut_driver_filename = self.name + "_with_lut.sp"
        spice_file = open(lut_driver_filename, 'w')
        spice_file.write(".TITLE " + self.name + " \n\n") 
        
        spice_file.write("********************************************************************************\n")
        spice_file.write("** Include libraries, parameters and other\n")
        spice_file.write("********************************************************************************\n\n")
        spice_file.write(".LIB \"../includes.l\" INCLUDES\n\n")
        # spice_file.write(".OPTIONS POST=2\n\n")
        
        spice_file.write("********************************************************************************\n")
        spice_file.write("** Setup and input\n")
        spice_file.write("********************************************************************************\n\n")
        spice_file.write(".TRAN 1p 16n SWEEP DATA=sweep_data\n")
        spice_file.write(".OPTIONS BRIEF=1\n\n")
        spice_file.write("* Input signal\n")
        spice_file.write("VIN_SRAM n_in_sram gnd PULSE (0 supply_v 4n 0 0 4n 8n)\n")
        spice_file.write("VIN_GATE n_in_gate gnd PULSE (supply_v 0 3n 0 0 2n 4n)\n\n")
        spice_file.write("* Power rail for the circuit under test.\n")
        spice_file.write("* This allows us to measure power of a circuit under test without measuring the power of wave shaping and load circuitry.\n")
        spice_file.write("V_LUT vdd_lut gnd supply_v\n\n")

        spice_file.write("********************************************************************************\n")
        spice_file.write("** Measurement\n")
        spice_file.write("********************************************************************************\n\n")
        spice_file.write("* Total delays\n")
        spice_file.write(".MEASURE TRAN meas_total_tfall TRIG V(n_3_1) VAL='supply_v/2' RISE=2\n")
        spice_file.write("+    TARG V(n_out) VAL='supply_v/2' FALL=1\n")
        spice_file.write(".MEASURE TRAN meas_total_trise TRIG V(n_3_1) VAL='supply_v/2' RISE=1\n")
        spice_file.write("+    TARG V(n_out) VAL='supply_v/2' RISE=1\n\n")
        
        spice_file.write(".MEASURE TRAN meas_logic_low_voltage FIND V(n_out) AT=3n\n\n")

        spice_file.write("* Measure the power required to propagate a rise and a fall transition through the lut at 250MHz.\n")
        spice_file.write(".MEASURE TRAN meas_current1 INTEGRAL I(V_LUT) FROM=5ns TO=7ns\n")
        spice_file.write(".MEASURE TRAN meas_current2 INTEGRAL I(V_LUT) FROM=9ns TO=11ns\n")
        spice_file.write(".MEASURE TRAN meas_avg_power PARAM = '-((meas_current1 + meas_current2)/4n)*supply_v'\n\n")

        spice_file.write("********************************************************************************\n")
        spice_file.write("** Circuit\n")
        spice_file.write("********************************************************************************\n\n")    
        spice_file.write("Xcb_mux_on_1 n_in_gate n_1_1 vsram vsram_n vdd gnd cb_mux_on\n")
        spice_file.write("Xlocal_routing_wire_load_1 n_1_1 n_1_2 vsram vsram_n vdd gnd vdd local_routing_wire_load\n")
        spice_file.write("X" + self.name + "_1 n_1_2 n_3_1 vsram vsram_n n_rsel n_2_1 vdd gnd " + self.name + "\n")

        # Connect a load to n_rsel node
        if self.type == "default_rsel" or self.type == "reg_fb_rsel":
            spice_file.write("Xff n_rsel n_ff_out vsram vsram_n gnd vdd gnd vdd gnd vdd vdd gnd ff\n")
        spice_file.write("X" + self.name + "_not_1 n_2_1 n_1_4 vdd gnd " + self.name + "_not\n")

        # Connect the LUT driver to a different LUT input based on LUT driver name and connect the other inputs to vdd
        # pass- transistor ----> "Xlut n_in_sram n_out a b c d e f vdd_lut gnd lut"
        # transmission gate ---> "Xlut n_in_sram n_out a a_not b b_not c c_not d d_not e e_not f f_not vdd_lut gnd lut"
        lut_letter = self.name.replace("_driver", "")
        lut_letter = lut_letter.replace("lut_", "")
        # string holding lut input connections depending on the driver letter
        lut_input_nodes = ""
        # loop over the letters a -> f
        for letter in range(97,103):
            # if this is the driver connect it to n_3_1 else connect it to vdd
            if chr(letter) == lut_letter:
                lut_input_nodes += "n_3_1 "
                # if tgate connect the complement input to n_1_4
                if self.use_tgate: lut_input_nodes += "n_1_4 "
            else:
                lut_input_nodes += "vdd "
                # if tgate connect the complement to gnd
                if self.use_tgate: lut_input_nodes += "gnd "

        spice_file.write("Xlut n_in_sram n_out " + lut_input_nodes + "vdd_lut gnd lut\n")
        
        if self.use_fluts:
            spice_file.write("Xwireflut n_out n_out2 wire Rw=wire_lut_to_flut_mux_res Cw=wire_lut_to_flut_mux_cap\n") 
            spice_file.write("Xthemux n_out2 n_out3 vdd gnd vdd gnd flut_mux\n") 
        else:
            spice_file.write("Xlut_output_load n_out n_local_out n_general_out vsram vsram_n vdd gnd vdd vdd lut_output_load\n\n")
        
        
        spice_file.write(".END")
        spice_file.close()

        # Come out of lut_driver directory
        os.chdir("../")  



    def generate_top(self):
        """ Generate top-level SPICE file based on type of LUT input driver. """
        
        # Generate top level files based on what type of driver this is.
        self.top_spice_path = self.generate_lut_driver_top()
        # And, generate the LUT driver + LUT path top level file. We use this file to measure total delay through the LUT.
        self.generate_lut_and_driver_top()       
     
     
    def update_area(self, area_dict, width_dict):
        """ Update area. To do this, we use area_dict which is a dictionary, maintained externally, that contains
            the area of everything. It is expected that area_dict will have all the information we need to calculate area.
            We update area_dict and width_dict with calculations performed in this function. 
            We also return the area of this driver, which is calculated based on driver type. """
        
        area = 0.0
        
        if not self.use_tgate :  
            # Calculate area based on input type
            if self.type != "default":
                area += area_dict["inv_" + self.name + "_0"]
            if self.type == "reg_fb" or self.type == "reg_fb_rsel":
                area += 2*area_dict["ptran_" + self.name + "_0"]
                area += area_dict["rest_" + self.name]
            if self.type != "default":
                area += area_dict["inv_" + self.name + "_1"]
            area += area_dict["inv_" + self.name + "_2"]
        
        else :
            # Calculate area based on input type
            if self.type != "default":
                area += area_dict["inv_" + self.name + "_0"]
            if self.type == "reg_fb" or self.type == "reg_fb_rsel":
                area += 2*area_dict["tgate_" + self.name + "_0"]
            if self.type != "default":
                area += area_dict["inv_" + self.name + "_1"]
            area += area_dict["inv_" + self.name + "_2"]

        # Add SRAM cell if this is a register feedback input
        if self.type == "reg_fb" or self.type == "ref_fb_rsel":
            area += area_dict["sram"]
        
        # Calculate layout width
        width = math.sqrt(area)
        
        # Add to dictionaries
        area_dict[self.name] = area
        width_dict[self.name] = width
        
        return area
        

    def update_wires(self, width_dict, wire_lengths, wire_layers):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict.
            Wires differ based on input type. """
        
        # getting name of min len wire local mux from global to just save myself the pain of changing all these variable names
        # global min_len_wire
        min_len_wire = fpga.min_len_wire
        local_mux_key = f"local_mux_L{min_len_wire['len']}_uid{min_len_wire['id']}"
        local_mux_key = "local_mux"

        if not self.use_tgate :  
            # Update wire lengths and wire layers
            if self.type == "default_rsel" or self.type == "reg_fb_rsel":
                wire_lengths["wire_" + self.name + "_0_rsel"] = width_dict[self.name]/4 + width_dict["lut"] + width_dict["ff"]/4 
                wire_layers["wire_" + self.name + "_0_rsel"] = 0
            if self.type == "default_rsel":
                wire_lengths["wire_" + self.name + "_0_out"] = width_dict["inv_" + self.name + "_0"]/4 + width_dict["inv_" + self.name + "_2"]/4
                wire_layers["wire_" + self.name + "_0_out"] = 0
            if self.type == "reg_fb" or self.type == "reg_fb_rsel":
                wire_lengths["wire_" + self.name + "_0_out"] = width_dict["inv_" + self.name + "_0"]/4 + width_dict["ptran_" + self.name + "_0"]/4
                wire_layers["wire_" + self.name + "_0_out"] = 0
                wire_lengths["wire_" + self.name + "_0"] = width_dict["ptran_" + self.name + "_0"]
                wire_layers["wire_" + self.name + "_0"] = 0
            if self.type == "default":
                wire_lengths["wire_" + self.name] = width_dict[local_mux_key]/4 + width_dict["inv_" + self.name + "_2"]/4
                wire_layers["wire_" + self.name] = 0
            else:
                wire_lengths["wire_" + self.name] = width_dict["inv_" + self.name + "_1"]/4 + width_dict["inv_" + self.name + "_2"]/4
                wire_layers["wire_" + self.name] = 0

        else :
            # Update wire lengths and wire layers
            if self.type == "default_rsel" or self.type == "reg_fb_rsel":
                wire_lengths["wire_" + self.name + "_0_rsel"] = width_dict[self.name]/4 + width_dict["lut"] + width_dict["ff"]/4 
                wire_layers["wire_" + self.name + "_0_rsel"] = 0
            if self.type == "default_rsel":
                wire_lengths["wire_" + self.name + "_0_out"] = width_dict["inv_" + self.name + "_0"]/4 + width_dict["inv_" + self.name + "_2"]/4
                wire_layers["wire_" + self.name + "_0_out"] = 0
            if self.type == "reg_fb" or self.type == "reg_fb_rsel":
                wire_lengths["wire_" + self.name + "_0_out"] = width_dict["inv_" + self.name + "_0"]/4 + width_dict["tgate_" + self.name + "_0"]/4
                wire_layers["wire_" + self.name + "_0_out"] = 0
                wire_lengths["wire_" + self.name + "_0"] = width_dict["tgate_" + self.name + "_0"]
                wire_layers["wire_" + self.name + "_0"] = 0
            if self.type == "default":
                wire_lengths["wire_" + self.name] = width_dict[local_mux_key]/4 + width_dict["inv_" + self.name + "_2"]/4
                wire_layers["wire_" + self.name] = 0
            else:
                wire_lengths["wire_" + self.name] = width_dict["inv_" + self.name + "_1"]/4 + width_dict["inv_" + self.name + "_2"]/4
                wire_layers["wire_" + self.name] = 0
            

class _LUTInputNotDriver(_SizableCircuit):
    """ LUT input not-driver. This is the complement driver. """

    def __init__(self, name, type, delay_weight, use_tgate):
        self.name = "lut_" + name + "_driver_not"
        # LUT input driver type ("default", "default_rsel", "reg_fb" and "reg_fb_rsel")
        self.type = type
        # Delay weight in a representative critical path
        self.delay_weight = delay_weight
        # use pass transistor or transmission gates
        self.use_tgate = use_tgate
   
    
    def generate(self, subcircuit_filename, min_tran_width):
        """ Generate not-driver SPICE netlist """
        if not self.use_tgate :
            self.transistor_names, self.wire_names = lut_subcircuits.generate_ptran_lut_not_driver(subcircuit_filename, self.name)
        else :
            self.transistor_names, self.wire_names = lut_subcircuits.generate_tgate_lut_not_driver(subcircuit_filename, self.name)
        
        # Initialize transistor sizes (to something more reasonable than all min size, but not necessarily a good choice, depends on architecture params)
        self.initial_transistor_sizes["inv_" + self.name + "_1_nmos"] = 1
        self.initial_transistor_sizes["inv_" + self.name + "_1_pmos"] = 1
        self.initial_transistor_sizes["inv_" + self.name + "_2_nmos"] = 2
        self.initial_transistor_sizes["inv_" + self.name + "_2_pmos"] = 2
       
        return self.initial_transistor_sizes


    def generate_lut_driver_not_top(self):
        """ Generate the top level lut input not driver SPICE file """
    
        # Create directories
        input_driver_name_no_not = self.name.replace("_not", "")
        if not os.path.exists(input_driver_name_no_not):
            os.makedirs(input_driver_name_no_not)  
        # Change to directory    
        os.chdir(input_driver_name_no_not)    
        
        lut_driver_filename = self.name + ".sp"
        input_driver_file = open(lut_driver_filename, 'w')
        input_driver_file.write(".TITLE " + self.name + " \n\n") 
        
        input_driver_file.write("********************************************************************************\n")
        input_driver_file.write("** Include libraries, parameters and other\n")
        input_driver_file.write("********************************************************************************\n\n")
        input_driver_file.write(".LIB \"../includes.l\" INCLUDES\n\n")
        
        input_driver_file.write("********************************************************************************\n")
        input_driver_file.write("** Setup and input\n")
        input_driver_file.write("********************************************************************************\n\n")
        input_driver_file.write(".TRAN 1p 4n SWEEP DATA=sweep_data\n")
        input_driver_file.write(".OPTIONS BRIEF=1\n\n")
        input_driver_file.write("* Input signal\n")
        input_driver_file.write("VIN n_in gnd PULSE (0 supply_v 0 0 0 2n 4n)\n\n")
        input_driver_file.write("* Power rail for the circuit under test.\n")
        input_driver_file.write("* This allows us to measure power of a circuit under test without measuring the power of wave shaping and load circuitry.\n")
        input_driver_file.write("V_LUT_DRIVER vdd_lut_driver gnd supply_v\n\n")
        
        input_driver_file.write("********************************************************************************\n")
        input_driver_file.write("** Measurement\n")
        input_driver_file.write("********************************************************************************\n\n")
        input_driver_file.write("* inv_" + self.name + "_1 delays\n")
        input_driver_file.write(".MEASURE TRAN meas_inv_" + self.name + "_1_tfall TRIG V(n_1_2) VAL='supply_v/2' RISE=1\n")
        input_driver_file.write("+    TARG V(X" + self.name + "_1.n_1_1) VAL='supply_v/2' FALL=1\n")
        input_driver_file.write(".MEASURE TRAN meas_inv_" + self.name + "_1_trise TRIG V(n_1_2) VAL='supply_v/2' FALL=1\n")
        input_driver_file.write("+    TARG V(X" + self.name + "_1.n_1_1) VAL='supply_v/2' RISE=1\n\n")
        input_driver_file.write("* inv_" + self.name + "_2 delays\n")
        input_driver_file.write(".MEASURE TRAN meas_inv_" + self.name + "_2_tfall TRIG V(n_1_2) VAL='supply_v/2' FALL=1\n")
        input_driver_file.write("+    TARG V(n_out_n) VAL='supply_v/2' FALL=1\n")
        input_driver_file.write(".MEASURE TRAN meas_inv_" + self.name + "_2_trise TRIG V(n_1_2) VAL='supply_v/2' RISE=1\n")
        input_driver_file.write("+    TARG V(n_out_n) VAL='supply_v/2' RISE=1\n\n")
        input_driver_file.write("* Total delays\n")
        input_driver_file.write(".MEASURE TRAN meas_total_tfall TRIG V(n_1_2) VAL='supply_v/2' FALL=1\n")
        input_driver_file.write("+    TARG V(n_out_n) VAL='supply_v/2' FALL=1\n")
        input_driver_file.write(".MEASURE TRAN meas_total_trise TRIG V(n_1_2) VAL='supply_v/2' RISE=1\n")
        input_driver_file.write("+    TARG V(n_out_n) VAL='supply_v/2' RISE=1\n\n")

        input_driver_file.write(".MEASURE TRAN meas_logic_low_voltage FIND V(n_out) AT=3n\n\n")
        
        input_driver_file.write("* Measure the power required to propagate a rise and a fall transition through the lut driver at 250MHz.\n")
        input_driver_file.write(".MEASURE TRAN meas_current INTEGRAL I(V_LUT_DRIVER) FROM=0ns TO=4ns\n")
        input_driver_file.write(".MEASURE TRAN meas_avg_power PARAM = '-((meas_current)/4n)*supply_v'\n\n")

        input_driver_file.write("********************************************************************************\n")
        input_driver_file.write("** Circuit\n")
        input_driver_file.write("********************************************************************************\n\n")
        input_driver_file.write("Xcb_mux_on_1 n_in n_1_1 vsram vsram_n vdd gnd cb_mux_on\n")
        input_driver_file.write("Xlocal_routing_wire_load_1 n_1_1 n_1_2 vsram vsram_n vdd gnd vdd local_routing_wire_load\n")
        input_driver_file.write("X" + input_driver_name_no_not + "_1 n_1_2 n_out vsram vsram_n n_rsel n_2_1 vdd gnd " + input_driver_name_no_not + "\n")
        if self.type == "default_rsel" or self.type == "reg_fb_rsel":
            # Connect a load to n_rsel node
            input_driver_file.write("Xff n_rsel n_ff_out vsram vsram_n gnd vdd gnd vdd gnd vdd vdd gnd ff\n")
        input_driver_file.write("X" + self.name + "_1 n_2_1 n_out_n vdd_lut_driver gnd " + self.name + "\n")
        input_driver_file.write("X" + input_driver_name_no_not + "_load_1 n_out n_vdd n_gnd " + input_driver_name_no_not + "_load\n")
        input_driver_file.write("X" + input_driver_name_no_not + "_load_2 n_out_n n_vdd n_gnd " + input_driver_name_no_not + "_load\n\n")
        input_driver_file.write(".END")
        input_driver_file.close()

        # Come out of lut_driver directory
        os.chdir("../")
        
        return (input_driver_name_no_not + "/" + self.name + ".sp")  

    def generate_top(self):
        """ Generate top-level SPICE file for LUT not driver """

        self.top_spice_path = self.generate_lut_driver_not_top()
        
    
    def update_area(self, area_dict, width_dict):
        """ Update area. To do this, we use area_dict which is a dictionary, maintained externally, that contains
            the area of everything. It is expected that area_dict will have all the information we need to calculate area.
            We update area_dict and width_dict with calculations performed in this function. 
            We also return the area of this not_driver."""
        
        area = (area_dict["inv_" + self.name + "_1"] +
                area_dict["inv_" + self.name + "_2"])
        width = math.sqrt(area)
        area_dict[self.name] = area
        width_dict[self.name] = width
        
        return area
    
    
    def update_wires(self, width_dict, wire_lengths, wire_layers):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """
        
        # Update wire lengths
        wire_lengths["wire_" + self.name] = (width_dict["inv_" + self.name + "_1"] + width_dict["inv_" + self.name + "_2"])/4
        # Update wire layers
        wire_layers["wire_" + self.name] = 0
    

class _LUTInput(_CompoundCircuit):
    """ LUT input. It contains a LUT input driver and a LUT input not driver (complement). 
        The muxing on the LUT input is defined here """

    def __init__(self, name, Rsel, Rfb, delay_weight, use_tgate, use_fluts):
        # Subcircuit name (should be driver letter like a, b, c...)
        self.name = name
        # The type is either 'default': a normal input or 'reg_fb': a register feedback input 
        # In addition, the input can (optionally) drive the register input 'default_rsel' or do both 'reg_fb_rsel'
        # Therefore, there are 4 different types, which are controlled by Rsel and Rfb
        # The register select (Rsel) could only be one signal. While the feedback could be used with multiple signals
        if name in Rfb:
            if Rsel == name:
                self.type = "reg_fb_rsel"
            else:
                self.type = "reg_fb"
        else:
            if Rsel == name:
                self.type = "default_rsel"
            else:
                self.type = "default"
        # Create LUT input driver
        self.driver = _LUTInputDriver(name, self.type, delay_weight, use_tgate, use_fluts)
        # Create LUT input not driver
        self.not_driver = _LUTInputNotDriver(name, self.type, delay_weight, use_tgate)
        
        # LUT input delays are the delays through the LUT for specific input (doesn't include input driver delay)
        self.tfall = 1
        self.trise = 1
        self.delay = 1
        self.delay_weight = delay_weight
        
        
    def generate(self, subcircuit_filename, min_tran_width):
        """ Generate both driver and not-driver SPICE netlists. """
        
        print("Generating lut " + self.name + "-input driver (" + self.type + ")")

        # Generate the driver
        init_tran_sizes = self.driver.generate(subcircuit_filename, min_tran_width)
        # Generate the not driver
        init_tran_sizes.update(self.not_driver.generate(subcircuit_filename, min_tran_width))

        return init_tran_sizes
  
            
    def generate_top(self):
        """ Generate top-level SPICE file for driver and not-driver. """
        
        print("Generating top-level lut " + self.name + "-input")
        
        # Generate the driver top
        self.driver.generate_top()
        # Generate the not driver top
        self.not_driver.generate_top()

     
    def update_area(self, area_dict, width_dict):
        """ Update area. We update the area of the the driver and the not driver by calling area update functions
            inside these objects. We also return the total area of this input driver."""        
        
        # Calculate area of driver
        driver_area = self.driver.update_area(area_dict, width_dict)
        # Calculate area of not driver
        not_driver_area = self.not_driver.update_area(area_dict, width_dict)
        # Return the sum
        return driver_area + not_driver_area
    
    
    def update_wires(self, width_dict, wire_lengths, wire_layers):
        """ Update wire lengths and wire layers for input driver and not_driver """
        
        # Update driver wires
        self.driver.update_wires(width_dict, wire_lengths, wire_layers)
        # Update not driver wires
        self.not_driver.update_wires(width_dict, wire_lengths, wire_layers)
        
        
    def print_details(self, report_file):
        """ Print LUT input driver details """
        
        utils.print_and_write(report_file, "  LUT input " + self.name + " type: " + self.type)



class _LUTInputDriverLoad:
    """ LUT input driver load. This load consists of a wire as well as the gates
        of a particular level in the LUT. """

    def __init__(self, name, use_tgate, use_fluts):
        self.name = name
        self.use_tgate = use_tgate
        self.use_fluts = use_fluts
    
    
    def update_wires(self, width_dict, wire_lengths, wire_layers, ratio):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """

        # Update wire lengths
        wire_lengths["wire_lut_" + self.name + "_driver_load"] = width_dict["lut"] * ratio
        
        # Update set wire layers
        wire_layers["wire_lut_" + self.name + "_driver_load"] = 0
        
        
    def generate(self, subcircuit_filename, K):
        
        print("Generating LUT " + self.name + "-input driver load")
        
        if not self.use_tgate :
            # Call generation function based on input
            if self.name == "a":
                self.wire_names = lut_subcircuits.generate_ptran_lut_driver_load(subcircuit_filename, self.name, K, self.use_fluts)
            elif self.name == "b":
                self.wire_names = lut_subcircuits.generate_ptran_lut_driver_load(subcircuit_filename, self.name, K, self.use_fluts)
            elif self.name == "c":
                self.wire_names = lut_subcircuits.generate_ptran_lut_driver_load(subcircuit_filename, self.name, K, self.use_fluts)
            elif self.name == "d":
                self.wire_names = lut_subcircuits.generate_ptran_lut_driver_load(subcircuit_filename, self.name, K, self.use_fluts)
            elif self.name == "e":
                self.wire_names = lut_subcircuits.generate_ptran_lut_driver_load(subcircuit_filename, self.name, K, self.use_fluts)
            elif self.name == "f":
                self.wire_names = lut_subcircuits.generate_ptran_lut_driver_load(subcircuit_filename, self.name, K, self.use_fluts)
        else :
            # Call generation function based on input
            if self.name == "a":
                self.wire_names = lut_subcircuits.generate_tgate_lut_driver_load(subcircuit_filename, self.name, K, self.use_fluts)
            elif self.name == "b":
                self.wire_names = lut_subcircuits.generate_tgate_lut_driver_load(subcircuit_filename, self.name, K, self.use_fluts)
            elif self.name == "c":
                self.wire_names = lut_subcircuits.generate_tgate_lut_driver_load(subcircuit_filename, self.name, K, self.use_fluts)
            elif self.name == "d":
                self.wire_names = lut_subcircuits.generate_tgate_lut_driver_load(subcircuit_filename, self.name, K, self.use_fluts)
            elif self.name == "e":
                self.wire_names = lut_subcircuits.generate_tgate_lut_driver_load(subcircuit_filename, self.name, K, self.use_fluts)
            elif self.name == "f":
                self.wire_names = lut_subcircuits.generate_tgate_lut_driver_load(subcircuit_filename, self.name, K, self.use_fluts)
        
        
    def print_details(self):
        print("LUT input driver load details.")

class _LUT(_SizableCircuit):
    """ Lookup table. """

    def __init__(self, K, Rsel, Rfb, use_tgate, use_finfet, use_fluts):
        # Name of LUT 
        self.name = "lut"
        self.use_fluts = use_fluts
        # Size of LUT
        self.K = K
        # Register feedback parameter
        self.Rfb = Rfb
        # Dictionary of input drivers (keys: "a", "b", etc...)
        self.input_drivers = {}
        # Dictionary of input driver loads
        self.input_driver_loads = {}
        # Delay weight in a representative critical path
        self.delay_weight = fpga.DELAY_WEIGHT_LUT_A + fpga.DELAY_WEIGHT_LUT_B + fpga.DELAY_WEIGHT_LUT_C + fpga.DELAY_WEIGHT_LUT_D
        if K >= 5:
            self.delay_weight += fpga.DELAY_WEIGHT_LUT_E
        if K >= 6:
            self.delay_weight += fpga.DELAY_WEIGHT_LUT_F
        
        # Boolean to use transmission gates 
        self.use_tgate = use_tgate

        # Create a LUT input driver and load for each LUT input

        tempK = self.K
        if self.use_fluts:
            tempK = self.K - 1

        for i in range(tempK):
            name = chr(i+97)
            if name == "a":
                delay_weight = fpga.DELAY_WEIGHT_LUT_A
            elif name == "b":
                delay_weight = fpga.DELAY_WEIGHT_LUT_B
            elif name == "c":
                delay_weight = fpga.DELAY_WEIGHT_LUT_C
            elif name == "d":
                delay_weight = fpga.DELAY_WEIGHT_LUT_D
            elif name == "e":
                delay_weight = fpga.DELAY_WEIGHT_LUT_E
            elif name == "f":
                delay_weight = fpga.DELAY_WEIGHT_LUT_F
            else:
                raise Exception("No delay weight definition for LUT input " + name)
            self.input_drivers[name] = _LUTInput(name, Rsel, Rfb, delay_weight, use_tgate, use_fluts)
            self.input_driver_loads[name] = _LUTInputDriverLoad(name, use_tgate, use_fluts)

        if use_fluts:
            if K == 5:
                name = "e"
                delay_weight = fpga.DELAY_WEIGHT_LUT_E
            else:
                name = "f"
                delay_weight = fpga.DELAY_WEIGHT_LUT_F
            self.input_drivers[name] = _LUTInput(name, Rsel, Rfb, delay_weight, use_tgate, use_fluts)
            self.input_driver_loads[name] = _LUTInputDriverLoad(name, use_tgate, use_fluts)            
    
        self.use_finfet = use_finfet
        
    
    def generate(self, subcircuit_filename, min_tran_width):
        """ Generate LUT SPICE netlist based on LUT size. """
        
        # Generate LUT differently based on K
        tempK = self.K

        # *TODO: this - 1 should depend on the level of fracturability
        #        if the level is one a 6 lut will be two 5 luts if its
        #        a 6 lut will be four 4 input luts
        if self.use_fluts:
            tempK = self.K - 1

        if tempK == 6:
            init_tran_sizes = self._generate_6lut(subcircuit_filename, min_tran_width, self.use_tgate, self.use_finfet, self.use_fluts)
        elif tempK == 5:
            init_tran_sizes = self._generate_5lut(subcircuit_filename, min_tran_width, self.use_tgate, self.use_finfet, self.use_fluts)
        elif tempK == 4:
            init_tran_sizes = self._generate_4lut(subcircuit_filename, min_tran_width, self.use_tgate, self.use_finfet, self.use_fluts)

  
        return init_tran_sizes

    def generate_lut6_top(self):
        """ Generate the top level 6-LUT SPICE file """

        """
        TODO:
        - This should be modified for the case of FLUTs since the LUTs in this case are loaded differently
        they are loaded with a full adder and the input to the flut mux and not with the lut output load.
        """

        # Create directory
        if not os.path.exists(self.name):
            os.makedirs(self.name)  
        # Change to directory    
        os.chdir(self.name) 
        
        lut_filename = self.name + ".sp"
        lut_file = open(lut_filename, 'w')
        lut_file.write(".TITLE 6-LUT\n\n") 
        
        lut_file.write("********************************************************************************\n")
        lut_file.write("** Include libraries, parameters and other\n")
        lut_file.write("********************************************************************************\n\n")
        lut_file.write(".LIB \"../includes.l\" INCLUDES\n\n")
        
        lut_file.write("********************************************************************************\n")
        lut_file.write("** Setup and input\n")
        lut_file.write("********************************************************************************\n\n")
        lut_file.write(".TRAN 1p 4n SWEEP DATA=sweep_data\n")
        lut_file.write(".OPTIONS BRIEF=1\n\n")
        lut_file.write("* Input signal\n")
        lut_file.write("VIN n_in gnd PULSE (0 supply_v 0 0 0 2n 4n)\n\n")
        
        lut_file.write("********************************************************************************\n")
        lut_file.write("** Measurement\n")
        lut_file.write("********************************************************************************\n\n")
        lut_file.write("* inv_lut_0sram_driver_1 delay\n")
        lut_file.write(".MEASURE TRAN meas_inv_lut_0sram_driver_1_tfall TRIG V(n_in) VAL='supply_v/2' RISE=1\n")
        lut_file.write("+    TARG V(Xlut.n_1_1) VAL='supply_v/2' FALL=1\n")
        lut_file.write(".MEASURE TRAN meas_inv_lut_0sram_driver_1_trise TRIG V(n_in) VAL='supply_v/2' FALL=1\n")
        lut_file.write("+    TARG V(Xlut.n_1_1) VAL='supply_v/2' RISE=1\n\n")
        lut_file.write("* inv_lut_sram_driver_2 delay\n")
        lut_file.write(".MEASURE TRAN meas_inv_lut_0sram_driver_2_tfall TRIG V(n_in) VAL='supply_v/2' FALL=1\n")
        lut_file.write("+    TARG V(Xlut.n_2_1) VAL='supply_v/2' FALL=1\n")
        lut_file.write(".MEASURE TRAN meas_inv_lut_0sram_driver_2_trise TRIG V(n_in) VAL='supply_v/2' RISE=1\n")
        lut_file.write("+    TARG V(Xlut.n_2_1) VAL='supply_v/2' RISE=1\n\n")
        lut_file.write("* Xinv_lut_int_buffer_1 delay\n")
        lut_file.write(".MEASURE TRAN meas_inv_lut_int_buffer_1_tfall TRIG V(n_in) VAL='supply_v/2' RISE=1\n")
        lut_file.write("+    TARG V(Xlut.n_6_1) VAL='supply_v/2' FALL=1\n")
        lut_file.write(".MEASURE TRAN meas_inv_lut_int_buffer_1_trise TRIG V(n_in) VAL='supply_v/2' FALL=1\n")
        lut_file.write("+    TARG V(Xlut.n_6_1) VAL='supply_v/2' RISE=1\n\n")
        lut_file.write("* Xinv_lut_int_buffer_2 delay\n")
        lut_file.write(".MEASURE TRAN meas_inv_lut_int_buffer_2_tfall TRIG V(n_in) VAL='supply_v/2' FALL=1\n")
        lut_file.write("+    TARG V(Xlut.n_7_1) VAL='supply_v/2' FALL=1\n")
        lut_file.write(".MEASURE TRAN meas_inv_lut_int_buffer_2_trise TRIG V(n_in) VAL='supply_v/2' RISE=1\n")
        lut_file.write("+    TARG V(Xlut.n_7_1) VAL='supply_v/2' RISE=1\n\n")
        lut_file.write("* Xinv_lut_out_buffer_1 delay\n")
        lut_file.write(".MEASURE TRAN meas_inv_lut_out_buffer_1_tfall TRIG V(n_in) VAL='supply_v/2' RISE=1\n")
        lut_file.write("+    TARG V(Xlut.n_11_1) VAL='supply_v/2' FALL=1\n")
        lut_file.write(".MEASURE TRAN meas_inv_lut_out_buffer_1_trise TRIG V(n_in) VAL='supply_v/2' FALL=1\n")
        lut_file.write("+    TARG V(Xlut.n_11_1) VAL='supply_v/2' RISE=1\n\n")
        lut_file.write("* Xinv_lut_out_buffer_2 delay\n")
        lut_file.write(".MEASURE TRAN meas_inv_lut_out_buffer_2_tfall TRIG V(n_in) VAL='supply_v/2' FALL=1\n")
        lut_file.write("+    TARG V(n_out) VAL='supply_v/2' FALL=1\n")
        lut_file.write(".MEASURE TRAN meas_inv_lut_out_buffer_2_trise TRIG V(n_in) VAL='supply_v/2' RISE=1\n")
        lut_file.write("+    TARG V(n_out) VAL='supply_v/2' RISE=1\n\n")
        lut_file.write("* Total delays\n")
        lut_file.write(".MEASURE TRAN meas_total_tfall TRIG V(n_in) VAL='supply_v/2' FALL=1\n")
        lut_file.write("+    TARG V(n_out) VAL='supply_v/2' FALL=1\n")
        lut_file.write(".MEASURE TRAN meas_total_trise TRIG V(n_in) VAL='supply_v/2' RISE=1\n")
        lut_file.write("+    TARG V(n_out) VAL='supply_v/2' RISE=1\n\n")
        lut_file.write(".MEASURE TRAN meas_logic_low_voltage FIND V(n_out) AT=3n\n\n")
        
        lut_file.write(".MEASURE TRAN info_node1_lut_tfall TRIG V(n_in) VAL='supply_v/2' FALL=1\n")
        lut_file.write("+    TARG V(Xlut.n_3_1) VAL='supply_v/2' FALL=1\n")
        lut_file.write(".MEASURE TRAN info_node1_lut_trise TRIG V(n_in) VAL='supply_v/2' RISE=1\n")
        lut_file.write("+    TARG V(Xlut.n_3_1) VAL='supply_v/2' RISE=1\n\n") 

        lut_file.write(".MEASURE TRAN info_node2_lut_tfall TRIG V(n_in) VAL='supply_v/2' FALL=1\n")
        lut_file.write("+    TARG V(Xlut.n_4_1) VAL='supply_v/2' FALL=1\n")
        lut_file.write(".MEASURE TRAN info_node2_lut_trise TRIG V(n_in) VAL='supply_v/2' RISE=1\n")
        lut_file.write("+    TARG V(Xlut.n_4_1) VAL='supply_v/2' RISE=1\n\n")     

        lut_file.write(".MEASURE TRAN info_node3_lut_tfall TRIG V(n_in) VAL='supply_v/2' FALL=1\n")
        lut_file.write("+    TARG V(Xlut.n_7_1) VAL='supply_v/2' FALL=1\n")
        lut_file.write(".MEASURE TRAN info_node3_lut_trise TRIG V(n_in) VAL='supply_v/2' RISE=1\n")
        lut_file.write("+    TARG V(Xlut.n_7_1) VAL='supply_v/2' RISE=1\n\n")   

        lut_file.write(".MEASURE TRAN info_node4_lut_tfall TRIG V(n_in) VAL='supply_v/2' FALL=1\n")
        lut_file.write("+    TARG V(Xlut.n_8_1) VAL='supply_v/2' FALL=1\n")
        lut_file.write(".MEASURE TRAN info_node4_lut_trise TRIG V(n_in) VAL='supply_v/2' RISE=1\n")
        lut_file.write("+    TARG V(Xlut.n_8_1) VAL='supply_v/2' RISE=1\n\n")   


        lut_file.write(".MEASURE TRAN info_node5_lut_tfall TRIG V(n_in) VAL='supply_v/2' FALL=1\n")
        lut_file.write("+    TARG V(Xlut.n_9_1) VAL='supply_v/2' FALL=1\n")
        lut_file.write(".MEASURE TRAN info_node5_lut_trise TRIG V(n_in) VAL='supply_v/2' RISE=1\n")
        lut_file.write("+    TARG V(Xlut.n_9_1) VAL='supply_v/2' RISE=1\n\n")   
        lut_file.write("********************************************************************************\n")
        lut_file.write("** Circuit\n")
        lut_file.write("********************************************************************************\n\n")

        if not self.use_tgate :
            lut_file.write("Xlut n_in n_out vdd vdd vdd vdd vdd vdd vdd gnd lut\n\n")
            lut_file.write("Xlut_output_load n_out n_local_out n_general_out vsram vsram_n vdd gnd vdd vdd lut_output_load\n\n")
        else :
            lut_file.write("Xlut n_in n_out vdd gnd vdd gnd vdd gnd vdd gnd vdd gnd vdd gnd vdd gnd lut\n\n")
            lut_file.write("Xlut_output_load n_out n_local_out n_general_out vsram vsram_n vdd gnd vdd vdd lut_output_load\n\n")
        
        lut_file.write(".END")
        lut_file.close()

        # Come out of lut directory
        os.chdir("../")
        
        return (self.name + "/" + self.name + ".sp")
    

    def generate_lut5_top(self):
        """ Generate the top level 5-LUT SPICE file """

        
        # TODO:
        # This should be modified for the case of FLUTs since the LUTs in this case are loaded differently
        # they are loaded with a full adder and the input to the flut mux and not with the lut output load.
        

        # Create directory
        if not os.path.exists(self.name):
            os.makedirs(self.name)  
        # Change to directory    
        os.chdir(self.name) 
        
        lut_filename = self.name + ".sp"
        lut_file = open(lut_filename, 'w')
        lut_file.write(".TITLE 5-LUT\n\n") 
        
        lut_file.write("********************************************************************************\n")
        lut_file.write("** Include libraries, parameters and other\n")
        lut_file.write("********************************************************************************\n\n")
        lut_file.write(".LIB \"../includes.l\" INCLUDES\n\n")
        
        lut_file.write("********************************************************************************\n")
        lut_file.write("** Setup and input\n")
        lut_file.write("********************************************************************************\n\n")
        lut_file.write(".TRAN 1p 4n SWEEP DATA=sweep_data\n")
        lut_file.write(".OPTIONS BRIEF=1\n\n")
        lut_file.write("* Input signal\n")
        lut_file.write("VIN n_in gnd PULSE (0 supply_v 0 0 0 2n 4n)\n\n")
        
        lut_file.write("********************************************************************************\n")
        lut_file.write("** Measurement\n")
        lut_file.write("********************************************************************************\n\n")
        lut_file.write("* inv_lut_0sram_driver_1 delay\n")
        lut_file.write(".MEASURE TRAN meas_inv_lut_0sram_driver_1_tfall TRIG V(n_in) VAL='supply_v/2' RISE=1\n")
        lut_file.write("+    TARG V(Xlut.n_1_1) VAL='supply_v/2' FALL=1\n")
        lut_file.write(".MEASURE TRAN meas_inv_lut_0sram_driver_1_trise TRIG V(n_in) VAL='supply_v/2' FALL=1\n")
        lut_file.write("+    TARG V(Xlut.n_1_1) VAL='supply_v/2' RISE=1\n\n")
        lut_file.write("* inv_lut_sram_driver_2 delay\n")
        lut_file.write(".MEASURE TRAN meas_inv_lut_0sram_driver_2_tfall TRIG V(n_in) VAL='supply_v/2' FALL=1\n")
        lut_file.write("+    TARG V(Xlut.n_2_1) VAL='supply_v/2' FALL=1\n")
        lut_file.write(".MEASURE TRAN meas_inv_lut_0sram_driver_2_trise TRIG V(n_in) VAL='supply_v/2' RISE=1\n")
        lut_file.write("+    TARG V(Xlut.n_2_1) VAL='supply_v/2' RISE=1\n\n")
        lut_file.write("* Xinv_lut_int_buffer_1 delay\n")
        lut_file.write(".MEASURE TRAN meas_inv_lut_int_buffer_1_tfall TRIG V(n_in) VAL='supply_v/2' RISE=1\n")
        lut_file.write("+    TARG V(Xlut.n_6_1) VAL='supply_v/2' FALL=1\n")
        lut_file.write(".MEASURE TRAN meas_inv_lut_int_buffer_1_trise TRIG V(n_in) VAL='supply_v/2' FALL=1\n")
        lut_file.write("+    TARG V(Xlut.n_6_1) VAL='supply_v/2' RISE=1\n\n")
        lut_file.write("* Xinv_lut_int_buffer_2 delay\n")
        lut_file.write(".MEASURE TRAN meas_inv_lut_int_buffer_2_tfall TRIG V(n_in) VAL='supply_v/2' FALL=1\n")
        lut_file.write("+    TARG V(Xlut.n_7_1) VAL='supply_v/2' FALL=1\n")
        lut_file.write(".MEASURE TRAN meas_inv_lut_int_buffer_2_trise TRIG V(n_in) VAL='supply_v/2' RISE=1\n")
        lut_file.write("+    TARG V(Xlut.n_7_1) VAL='supply_v/2' RISE=1\n\n")
        lut_file.write("* Xinv_lut_out_buffer_1 delay\n")
        lut_file.write(".MEASURE TRAN meas_inv_lut_out_buffer_1_tfall TRIG V(n_in) VAL='supply_v/2' RISE=1\n")
        lut_file.write("+    TARG V(Xlut.n_11_1) VAL='supply_v/2' FALL=1\n")
        lut_file.write(".MEASURE TRAN meas_inv_lut_out_buffer_1_trise TRIG V(n_in) VAL='supply_v/2' FALL=1\n")
        lut_file.write("+    TARG V(Xlut.n_11_1) VAL='supply_v/2' RISE=1\n\n")
        lut_file.write("* Xinv_lut_out_buffer_2 delay\n")
        lut_file.write(".MEASURE TRAN meas_inv_lut_out_buffer_2_tfall TRIG V(n_in) VAL='supply_v/2' FALL=1\n")
        lut_file.write("+    TARG V(n_out) VAL='supply_v/2' FALL=1\n")
        lut_file.write(".MEASURE TRAN meas_inv_lut_out_buffer_2_trise TRIG V(n_in) VAL='supply_v/2' RISE=1\n")
        lut_file.write("+    TARG V(n_out) VAL='supply_v/2' RISE=1\n\n")
        lut_file.write("* Total delays\n")
        lut_file.write(".MEASURE TRAN meas_total_tfall TRIG V(n_in) VAL='supply_v/2' FALL=1\n")
        lut_file.write("+    TARG V(n_out) VAL='supply_v/2' FALL=1\n")
        lut_file.write(".MEASURE TRAN meas_total_trise TRIG V(n_in) VAL='supply_v/2' RISE=1\n")
        lut_file.write("+    TARG V(n_out) VAL='supply_v/2' RISE=1\n\n")
        lut_file.write(".MEASURE TRAN meas_logic_low_voltage FIND V(n_out) AT=3n\n\n")
        
        lut_file.write("********************************************************************************\n")
        lut_file.write("** Circuit\n")
        lut_file.write("********************************************************************************\n\n")
        if not self.use_tgate :
            lut_file.write("Xlut n_in n_out vdd vdd vdd vdd vdd vdd vdd gnd lut\n\n")
            lut_file.write("Xlut_output_load n_out n_local_out n_general_out vsram vsram_n vdd gnd vdd vdd lut_output_load\n\n")
        else :
            lut_file.write("Xlut n_in n_out vdd gnd vdd gnd vdd gnd vdd gnd vdd gnd vdd gnd vdd gnd lut\n\n")
            lut_file.write("Xlut_output_load n_out n_local_out n_general_out vsram vsram_n vdd gnd vdd vdd lut_output_load\n\n")
        
        lut_file.write(".END")
        lut_file.close()

        # Come out of lut directory
        os.chdir("../")
        
        return (self.name + "/" + self.name + ".sp") 
    

    def generate_lut4_top(self):
        """ Generate the top level 4-LUT SPICE file """

        
        # TODO:
        # This should be modified for the case of FLUTs since the LUTs in this case are loaded differently
        # they are loaded with a full adder and the input to the flut mux and not with the lut output load.
        

        # Create directory
        if not os.path.exists(self.name):
            os.makedirs(self.name)  
        # Change to directory    
        os.chdir(self.name) 
        
        lut_filename = self.name + ".sp"
        lut_file = open(lut_filename, 'w')
        lut_file.write(".TITLE 4-LUT\n\n") 
        
        lut_file.write("********************************************************************************\n")
        lut_file.write("** Include libraries, parameters and other\n")
        lut_file.write("********************************************************************************\n\n")
        lut_file.write(".LIB \"../includes.l\" INCLUDES\n\n")
        
        lut_file.write("********************************************************************************\n")
        lut_file.write("** Setup and input\n")
        lut_file.write("********************************************************************************\n\n")
        lut_file.write(".TRAN 1p 4n SWEEP DATA=sweep_data\n")
        lut_file.write(".OPTIONS BRIEF=1\n\n")
        lut_file.write("* Input signal\n")
        lut_file.write("VIN n_in gnd PULSE (0 supply_v 0 0 0 2n 4n)\n\n")
        
        lut_file.write("********************************************************************************\n")
        lut_file.write("** Measurement\n")
        lut_file.write("********************************************************************************\n\n")
        lut_file.write("* inv_lut_0sram_driver_1 delay\n")
        lut_file.write(".MEASURE TRAN meas_inv_lut_0sram_driver_1_tfall TRIG V(n_in) VAL='supply_v/2' RISE=1\n")
        lut_file.write("+    TARG V(Xlut.n_1_1) VAL='supply_v/2' FALL=1\n")
        lut_file.write(".MEASURE TRAN meas_inv_lut_0sram_driver_1_trise TRIG V(n_in) VAL='supply_v/2' FALL=1\n")
        lut_file.write("+    TARG V(Xlut.n_1_1) VAL='supply_v/2' RISE=1\n\n")
        lut_file.write("* inv_lut_sram_driver_2 delay\n")
        lut_file.write(".MEASURE TRAN meas_inv_lut_0sram_driver_2_tfall TRIG V(n_in) VAL='supply_v/2' FALL=1\n")
        lut_file.write("+    TARG V(Xlut.n_2_1) VAL='supply_v/2' FALL=1\n")
        lut_file.write(".MEASURE TRAN meas_inv_lut_0sram_driver_2_trise TRIG V(n_in) VAL='supply_v/2' RISE=1\n")
        lut_file.write("+    TARG V(Xlut.n_2_1) VAL='supply_v/2' RISE=1\n\n")
        lut_file.write("* Xinv_lut_int_buffer_1 delay\n")
        lut_file.write(".MEASURE TRAN meas_inv_lut_int_buffer_1_tfall TRIG V(n_in) VAL='supply_v/2' RISE=1\n")
        lut_file.write("+    TARG V(Xlut.n_5_1) VAL='supply_v/2' FALL=1\n")
        lut_file.write(".MEASURE TRAN meas_inv_lut_int_buffer_1_trise TRIG V(n_in) VAL='supply_v/2' FALL=1\n")
        lut_file.write("+    TARG V(Xlut.n_5_1) VAL='supply_v/2' RISE=1\n\n")
        lut_file.write("* Xinv_lut_int_buffer_2 delay\n")
        lut_file.write(".MEASURE TRAN meas_inv_lut_int_buffer_2_tfall TRIG V(n_in) VAL='supply_v/2' FALL=1\n")
        lut_file.write("+    TARG V(Xlut.n_6_1) VAL='supply_v/2' FALL=1\n")
        lut_file.write(".MEASURE TRAN meas_inv_lut_int_buffer_2_trise TRIG V(n_in) VAL='supply_v/2' RISE=1\n")
        lut_file.write("+    TARG V(Xlut.n_6_1) VAL='supply_v/2' RISE=1\n\n")
        lut_file.write("* Xinv_lut_out_buffer_1 delay\n")
        lut_file.write(".MEASURE TRAN meas_inv_lut_out_buffer_1_tfall TRIG V(n_in) VAL='supply_v/2' RISE=1\n")
        lut_file.write("+    TARG V(Xlut.n_9_1) VAL='supply_v/2' FALL=1\n")
        lut_file.write(".MEASURE TRAN meas_inv_lut_out_buffer_1_trise TRIG V(n_in) VAL='supply_v/2' FALL=1\n")
        lut_file.write("+    TARG V(Xlut.n_9_1) VAL='supply_v/2' RISE=1\n\n")
        lut_file.write("* Xinv_lut_out_buffer_2 delay\n")
        lut_file.write(".MEASURE TRAN meas_inv_lut_out_buffer_2_tfall TRIG V(n_in) VAL='supply_v/2' FALL=1\n")
        lut_file.write("+    TARG V(n_out) VAL='supply_v/2' FALL=1\n")
        lut_file.write(".MEASURE TRAN meas_inv_lut_out_buffer_2_trise TRIG V(n_in) VAL='supply_v/2' RISE=1\n")
        lut_file.write("+    TARG V(n_out) VAL='supply_v/2' RISE=1\n\n")
        lut_file.write("* Total delays\n")
        lut_file.write(".MEASURE TRAN meas_total_tfall TRIG V(n_in) VAL='supply_v/2' FALL=1\n")
        lut_file.write("+    TARG V(n_out) VAL='supply_v/2' FALL=1\n")
        lut_file.write(".MEASURE TRAN meas_total_trise TRIG V(n_in) VAL='supply_v/2' RISE=1\n")
        lut_file.write("+    TARG V(n_out) VAL='supply_v/2' RISE=1\n\n")
        lut_file.write(".MEASURE TRAN meas_logic_low_voltage FIND V(n_out) AT=3n\n\n")
        
        lut_file.write("********************************************************************************\n")
        lut_file.write("** Circuit\n")
        lut_file.write("********************************************************************************\n\n")
        if not self.use_tgate :
            lut_file.write("Xlut n_in n_out vdd vdd vdd vdd vdd vdd vdd gnd lut\n\n")
            lut_file.write("Xlut_output_load n_out n_local_out n_general_out vsram vsram_n vdd gnd vdd vdd lut_output_load\n\n")
        else :
            lut_file.write("Xlut n_in n_out vdd gnd vdd gnd vdd gnd vdd gnd vdd gnd vdd gnd vdd gnd lut\n\n")
            lut_file.write("Xlut_output_load n_out n_local_out n_general_out vsram vsram_n vdd gnd vdd vdd lut_output_load\n\n")

        lut_file.write(".END")
        lut_file.close()

        # Come out of lut directory
        os.chdir("../")
        
        return (self.name + "/" + self.name + ".sp")


    def generate_top(self):
        print("Generating top-level lut")
        tempK = self.K
        if self.use_fluts:
            tempK = self.K - 1

        if tempK == 6:
            self.top_spice_path = self.generate_lut6_top()
        elif tempK == 5:
            self.top_spice_path = self.generate_lut5_top()
        elif tempK == 4:
            self.top_spice_path = self.generate_lut4_top()
            
        # Generate top-level driver files
        for input_driver_name, input_driver in self.input_drivers.items():
            input_driver.generate_top()
   
   
    def update_area(self, area_dict, width_dict):
        """ Update area. To do this, we use area_dict which is a dictionary, maintained externally, that contains
            the area of everything. It is expected that area_dict will have all the information we need to calculate area.
            We update area_dict and width_dict with calculations performed in this function. 
            We update the area of the LUT as well as the area of the LUT input drivers. """        

        tempK = self.K
        if self.use_fluts:
            tempK = self.K - 1

        area = 0.0
        
        if not self.use_tgate :
            # Calculate area (differs with different values of K)
            if tempK == 6:    
                area += (64*area_dict["inv_lut_0sram_driver_2"] + 
                        64*area_dict["ptran_lut_L1"] + 
                        32*area_dict["ptran_lut_L2"] + 
                        16*area_dict["ptran_lut_L3"] +      
                        8*area_dict["rest_lut_int_buffer"] + 
                        8*area_dict["inv_lut_int_buffer_1"] + 
                        8*area_dict["inv_lut_int_buffer_2"] + 
                        8*area_dict["ptran_lut_L4"] + 
                        4*area_dict["ptran_lut_L5"] + 
                        2*area_dict["ptran_lut_L6"] + 
                        area_dict["rest_lut_out_buffer"] + 
                        area_dict["inv_lut_out_buffer_1"] + 
                        area_dict["inv_lut_out_buffer_2"] +
                        64*area_dict["sram"])
            elif tempK == 5:
                area += (32*area_dict["inv_lut_0sram_driver_2"] + 
                        32*area_dict["ptran_lut_L1"] + 
                        16*area_dict["ptran_lut_L2"] + 
                        8*area_dict["ptran_lut_L3"] + 
                        4*area_dict["rest_lut_int_buffer"] + 
                        4*area_dict["inv_lut_int_buffer_1"] + 
                        4*area_dict["inv_lut_int_buffer_2"] + 
                        4*area_dict["ptran_lut_L4"] + 
                        2*area_dict["ptran_lut_L5"] +  
                        area_dict["rest_lut_out_buffer"] + 
                        area_dict["inv_lut_out_buffer_1"] + 
                        area_dict["inv_lut_out_buffer_2"] +
                        32*area_dict["sram"])
            elif tempK == 4:
                area += (16*area_dict["inv_lut_0sram_driver_2"] + 
                        16*area_dict["ptran_lut_L1"] + 
                        8*area_dict["ptran_lut_L2"] + 
                        4*area_dict["rest_lut_int_buffer"] + 
                        4*area_dict["inv_lut_int_buffer_1"] + 
                        4*area_dict["inv_lut_int_buffer_2"] +
                        4*area_dict["ptran_lut_L3"] + 
                        2*area_dict["ptran_lut_L4"] +   
                        area_dict["rest_lut_out_buffer"] + 
                        area_dict["inv_lut_out_buffer_1"] + 
                        area_dict["inv_lut_out_buffer_2"] +
                        16*area_dict["sram"])
        else :
            # Calculate area (differs with different values of K)
            if tempK == 6:    
                area += (64*area_dict["inv_lut_0sram_driver_2"] + 
                        64*area_dict["tgate_lut_L1"] + 
                        32*area_dict["tgate_lut_L2"] + 
                        16*area_dict["tgate_lut_L3"] + 
                        8*area_dict["inv_lut_int_buffer_1"] + 
                        8*area_dict["inv_lut_int_buffer_2"] + 
                        8*area_dict["tgate_lut_L4"] + 
                        4*area_dict["tgate_lut_L5"] + 
                        2*area_dict["tgate_lut_L6"] + 
                        area_dict["inv_lut_out_buffer_1"] + 
                        area_dict["inv_lut_out_buffer_2"] +
                        64*area_dict["sram"])
            elif tempK == 5:
                area += (32*area_dict["inv_lut_0sram_driver_2"] + 
                        32*area_dict["tgate_lut_L1"] + 
                        16*area_dict["tgate_lut_L2"] + 
                        8*area_dict["tgate_lut_L3"] + 
                        4*area_dict["inv_lut_int_buffer_1"] + 
                        4*area_dict["inv_lut_int_buffer_2"] + 
                        4*area_dict["tgate_lut_L4"] + 
                        2*area_dict["tgate_lut_L5"] +  
                        area_dict["inv_lut_out_buffer_1"] + 
                        area_dict["inv_lut_out_buffer_2"] +
                        32*area_dict["sram"])
            elif tempK == 4:
                area += (16*area_dict["inv_lut_0sram_driver_2"] + 
                        16*area_dict["tgate_lut_L1"] + 
                        8*area_dict["tgate_lut_L2"] + 
                        4*area_dict["inv_lut_int_buffer_1"] + 
                        4*area_dict["inv_lut_int_buffer_2"] +
                        4*area_dict["tgate_lut_L3"] + 
                        2*area_dict["tgate_lut_L4"] +   
                        area_dict["inv_lut_out_buffer_1"] + 
                        area_dict["inv_lut_out_buffer_2"] +
                        16*area_dict["sram"])
        

        #TODO: level of fracturablility will affect this
        if self.use_fluts:
            area = 2*area
            area = area + area_dict["flut_mux"]

        width = math.sqrt(area)
        area_dict["lut"] = area
        width_dict["lut"] = width
        
        # Calculate LUT driver areas
        total_lut_area = 0.0
        for driver_name, input_driver in self.input_drivers.items():
            driver_area = input_driver.update_area(area_dict, width_dict)
            total_lut_area = total_lut_area + driver_area
       
        # Now we calculate total LUT area
        total_lut_area = total_lut_area + area_dict["lut"]

        area_dict["lut_and_drivers"] = total_lut_area
        width_dict["lut_and_drivers"] = math.sqrt(total_lut_area)
        
        return total_lut_area
    

    def update_wires(self, width_dict, wire_lengths, wire_layers, lut_ratio):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """

        if not self.use_tgate :
            if self.K == 6:        
                # Update wire lengths
                wire_lengths["wire_lut_sram_driver"] = (width_dict["inv_lut_0sram_driver_2"] + width_dict["inv_lut_0sram_driver_2"])/4
                wire_lengths["wire_lut_sram_driver_out"] = (width_dict["inv_lut_0sram_driver_2"] + width_dict["ptran_lut_L1"])/4
                wire_lengths["wire_lut_L1"] = width_dict["ptran_lut_L1"]
                wire_lengths["wire_lut_L2"] = 2*width_dict["ptran_lut_L1"]
                wire_lengths["wire_lut_L3"] = 4*width_dict["ptran_lut_L1"]
                wire_lengths["wire_lut_int_buffer"] = (width_dict["inv_lut_int_buffer_1"] + width_dict["inv_lut_int_buffer_2"])/4
                wire_lengths["wire_lut_int_buffer_out"] = (width_dict["inv_lut_int_buffer_2"] + width_dict["ptran_lut_L4"])/4
                wire_lengths["wire_lut_L4"] = 8*width_dict["ptran_lut_L1"]
                wire_lengths["wire_lut_L5"] = 16*width_dict["ptran_lut_L1"]
                wire_lengths["wire_lut_L6"] = 32*width_dict["ptran_lut_L1"]
                wire_lengths["wire_lut_out_buffer"] = (width_dict["inv_lut_out_buffer_1"] + width_dict["inv_lut_out_buffer_2"])/4

                # Update wire layers
                wire_layers["wire_lut_sram_driver"] = 0
                wire_layers["wire_lut_sram_driver_out"] = 0
                wire_layers["wire_lut_L1"] = 0
                wire_layers["wire_lut_L2"] = 0
                wire_layers["wire_lut_L3"] = 0
                wire_layers["wire_lut_int_buffer"] = 0
                wire_layers["wire_lut_int_buffer_out"] = 0
                wire_layers["wire_lut_L4"] = 0
                wire_layers["wire_lut_L5"] = 0
                wire_layers["wire_lut_L6"] = 0
                wire_layers["wire_lut_out_buffer"] = 0
              
            elif self.K == 5:
                # Update wire lengths
                wire_lengths["wire_lut_sram_driver"] = (width_dict["inv_lut_0sram_driver_2"] + width_dict["inv_lut_0sram_driver_2"])/4
                wire_lengths["wire_lut_sram_driver_out"] = (width_dict["inv_lut_0sram_driver_2"] + width_dict["ptran_lut_L1"])/4
                wire_lengths["wire_lut_L1"] = width_dict["ptran_lut_L1"]
                wire_lengths["wire_lut_L2"] = 2*width_dict["ptran_lut_L1"]
                wire_lengths["wire_lut_L3"] = 4*width_dict["ptran_lut_L1"]
                wire_lengths["wire_lut_int_buffer"] = (width_dict["inv_lut_int_buffer_1"] + width_dict["inv_lut_int_buffer_2"])/4
                wire_lengths["wire_lut_int_buffer_out"] = (width_dict["inv_lut_int_buffer_2"] + width_dict["ptran_lut_L4"])/4
                wire_lengths["wire_lut_L4"] = 8*width_dict["ptran_lut_L1"]
                wire_lengths["wire_lut_L5"] = 16*width_dict["ptran_lut_L1"]
                wire_lengths["wire_lut_out_buffer"] = (width_dict["inv_lut_out_buffer_1"] + width_dict["inv_lut_out_buffer_2"])/4

                # Update wire layers
                wire_layers["wire_lut_sram_driver"] = 0
                wire_layers["wire_lut_sram_driver_out"] = 0
                wire_layers["wire_lut_L1"] = 0
                wire_layers["wire_lut_L2"] = 0
                wire_layers["wire_lut_L3"] = 0
                wire_layers["wire_lut_int_buffer"] = 0
                wire_layers["wire_lut_int_buffer_out"] = 0
                wire_layers["wire_lut_L4"] = 0
                wire_layers["wire_lut_L5"] = 0
                wire_layers["wire_lut_out_buffer"] = 0
                
            elif self.K == 4:
                # Update wire lengths
                wire_lengths["wire_lut_sram_driver"] = (width_dict["inv_lut_0sram_driver_2"] + width_dict["inv_lut_0sram_driver_2"])/4
                wire_lengths["wire_lut_sram_driver_out"] = (width_dict["inv_lut_0sram_driver_2"] + width_dict["ptran_lut_L1"])/4
                wire_lengths["wire_lut_L1"] = width_dict["ptran_lut_L1"]
                wire_lengths["wire_lut_L2"] = 2*width_dict["ptran_lut_L1"]
                wire_lengths["wire_lut_int_buffer"] = (width_dict["inv_lut_int_buffer_1"] + width_dict["inv_lut_int_buffer_2"])/4
                wire_lengths["wire_lut_int_buffer_out"] = (width_dict["inv_lut_int_buffer_2"] + width_dict["ptran_lut_L4"])/4
                wire_lengths["wire_lut_L3"] = 4*width_dict["ptran_lut_L1"]
                wire_lengths["wire_lut_L4"] = 8*width_dict["ptran_lut_L1"]
                wire_lengths["wire_lut_out_buffer"] = (width_dict["inv_lut_out_buffer_1"] + width_dict["inv_lut_out_buffer_2"])/4

                # Update wire layers
                wire_layers["wire_lut_sram_driver"] = 0
                wire_layers["wire_lut_sram_driver_out"] = 0
                wire_layers["wire_lut_L1"] = 0
                wire_layers["wire_lut_L2"] = 0
                wire_layers["wire_lut_int_buffer"] = 0
                wire_layers["wire_lut_int_buffer_out"] = 0
                wire_layers["wire_lut_L3"] = 0
                wire_layers["wire_lut_L4"] = 0
                wire_layers["wire_lut_out_buffer"] = 0

        else :
            if self.K == 6:        
                # Update wire lengths
                wire_lengths["wire_lut_sram_driver"] = (width_dict["inv_lut_0sram_driver_2"] + width_dict["inv_lut_0sram_driver_2"])/4
                wire_lengths["wire_lut_sram_driver_out"] = (width_dict["inv_lut_0sram_driver_2"] + width_dict["tgate_lut_L1"])/4
                wire_lengths["wire_lut_L1"] = width_dict["tgate_lut_L1"]
                wire_lengths["wire_lut_L2"] = 2*width_dict["tgate_lut_L1"]
                wire_lengths["wire_lut_L3"] = 4*width_dict["tgate_lut_L1"]
                wire_lengths["wire_lut_int_buffer"] = (width_dict["inv_lut_int_buffer_1"] + width_dict["inv_lut_int_buffer_2"])/4
                wire_lengths["wire_lut_int_buffer_out"] = (width_dict["inv_lut_int_buffer_2"] + width_dict["tgate_lut_L4"])/4
                wire_lengths["wire_lut_L4"] = 8*width_dict["tgate_lut_L1"]
                wire_lengths["wire_lut_L5"] = 16*width_dict["tgate_lut_L1"]
                wire_lengths["wire_lut_L6"] = 32*width_dict["tgate_lut_L1"]
                wire_lengths["wire_lut_out_buffer"] = (width_dict["inv_lut_out_buffer_1"] + width_dict["inv_lut_out_buffer_2"])/4

                # Update wire layers
                wire_layers["wire_lut_sram_driver"] = 0
                wire_layers["wire_lut_sram_driver_out"] = 0
                wire_layers["wire_lut_L1"] = 0
                wire_layers["wire_lut_L2"] = 0
                wire_layers["wire_lut_L3"] = 0
                wire_layers["wire_lut_int_buffer"] = 0
                wire_layers["wire_lut_int_buffer_out"] = 0
                wire_layers["wire_lut_L4"] = 0
                wire_layers["wire_lut_L5"] = 0
                wire_layers["wire_lut_L6"] = 0
                wire_layers["wire_lut_out_buffer"] = 0
              
            elif self.K == 5:
                # Update wire lengths
                wire_lengths["wire_lut_sram_driver"] = (width_dict["inv_lut_0sram_driver_2"] + width_dict["inv_lut_0sram_driver_2"])/4
                wire_lengths["wire_lut_sram_driver_out"] = (width_dict["inv_lut_0sram_driver_2"] + width_dict["tgate_lut_L1"])/4
                wire_lengths["wire_lut_L1"] = width_dict["tgate_lut_L1"]
                wire_lengths["wire_lut_L2"] = 2*width_dict["tgate_lut_L1"]
                wire_lengths["wire_lut_L3"] = 4*width_dict["tgate_lut_L1"]
                wire_lengths["wire_lut_int_buffer"] = (width_dict["inv_lut_int_buffer_1"] + width_dict["inv_lut_int_buffer_2"])/4
                wire_lengths["wire_lut_int_buffer_out"] = (width_dict["inv_lut_int_buffer_2"] + width_dict["tgate_lut_L4"])/4
                wire_lengths["wire_lut_L4"] = 8*width_dict["tgate_lut_L1"]
                wire_lengths["wire_lut_L5"] = 16*width_dict["tgate_lut_L1"]
                wire_lengths["wire_lut_out_buffer"] = (width_dict["inv_lut_out_buffer_1"] + width_dict["inv_lut_out_buffer_2"])/4

                # Update wire layers
                wire_layers["wire_lut_sram_driver"] = 0
                wire_layers["wire_lut_sram_driver_out"] = 0
                wire_layers["wire_lut_L1"] = 0
                wire_layers["wire_lut_L2"] = 0
                wire_layers["wire_lut_L3"] = 0
                wire_layers["wire_lut_int_buffer"] = 0
                wire_layers["wire_lut_int_buffer_out"] = 0
                wire_layers["wire_lut_L4"] = 0
                wire_layers["wire_lut_L5"] = 0
                wire_layers["wire_lut_out_buffer"] = 0
                
            elif self.K == 4:
                # Update wire lengths
                wire_lengths["wire_lut_sram_driver"] = (width_dict["inv_lut_0sram_driver_2"] + width_dict["inv_lut_0sram_driver_2"])/4
                wire_lengths["wire_lut_sram_driver_out"] = (width_dict["inv_lut_0sram_driver_2"] + width_dict["tgate_lut_L1"])/4
                wire_lengths["wire_lut_L1"] = width_dict["tgate_lut_L1"]
                wire_lengths["wire_lut_L2"] = 2*width_dict["tgate_lut_L1"]
                wire_lengths["wire_lut_int_buffer"] = (width_dict["inv_lut_int_buffer_1"] + width_dict["inv_lut_int_buffer_2"])/4
                wire_lengths["wire_lut_int_buffer_out"] = (width_dict["inv_lut_int_buffer_2"] + width_dict["tgate_lut_L4"])/4
                wire_lengths["wire_lut_L3"] = 4*width_dict["tgate_lut_L1"]
                wire_lengths["wire_lut_L4"] = 8*width_dict["tgate_lut_L1"]
                wire_lengths["wire_lut_out_buffer"] = (width_dict["inv_lut_out_buffer_1"] + width_dict["inv_lut_out_buffer_2"])/4

                # Update wire layers
                wire_layers["wire_lut_sram_driver"] = 0
                wire_layers["wire_lut_sram_driver_out"] = 0
                wire_layers["wire_lut_L1"] = 0
                wire_layers["wire_lut_L2"] = 0
                wire_layers["wire_lut_int_buffer"] = 0
                wire_layers["wire_lut_int_buffer_out"] = 0
                wire_layers["wire_lut_L3"] = 0
                wire_layers["wire_lut_L4"] = 0
                wire_layers["wire_lut_out_buffer"] = 0
          
        # Update input driver wires
        for driver_name, input_driver in self.input_drivers.items():
            input_driver.update_wires(width_dict, wire_lengths, wire_layers) 
            
        # Update input driver load wires
        for driver_load_name, input_driver_load in self.input_driver_loads.items():
            input_driver_load.update_wires(width_dict, wire_lengths, wire_layers, lut_ratio)
    
        
    def print_details(self, report_file):
        """ Print LUT details """
    
        utils.print_and_write(report_file, "  LUT DETAILS:")
        utils.print_and_write(report_file, "  Style: Fully encoded MUX tree")
        utils.print_and_write(report_file, "  Size: " + str(self.K) + "-LUT")
        utils.print_and_write(report_file, "  Internal buffering: 2-stage buffer betweens levels 3 and 4")
        utils.print_and_write(report_file, "  Isolation inverters between SRAM and LUT inputs")
        utils.print_and_write(report_file, "")
        utils.print_and_write(report_file, "  LUT INPUT DRIVER DETAILS:")
        for driver_name, input_driver in self.input_drivers.items():
            input_driver.print_details(report_file)
        utils.print_and_write(report_file,"")
        
    
    def _generate_6lut(self, subcircuit_filename, min_tran_width, use_tgate, use_finfet, use_fluts):
        """ This function created the lut subcircuit and all the drivers and driver not subcircuits """
        print("Generating 6-LUT")

        # COFFE doesn't support 7-input LUTs check_arch_params in utils.py will handle this
        # we currently don't support 7-input LUTs that are fracturable, that would require more code changes but can be done with reasonable effort.
        # assert use_fluts == False
        
        # Call the generation function
        if not use_tgate :
            # use pass transistors
            self.transistor_names, self.wire_names = lut_subcircuits.generate_ptran_lut6(subcircuit_filename, min_tran_width, use_finfet)

            # Give initial transistor sizes
            self.initial_transistor_sizes["inv_lut_0sram_driver_2_nmos"] = 4
            self.initial_transistor_sizes["inv_lut_0sram_driver_2_pmos"] = 6
            self.initial_transistor_sizes["ptran_lut_L1_nmos"] = 2
            self.initial_transistor_sizes["ptran_lut_L2_nmos"] = 2
            self.initial_transistor_sizes["ptran_lut_L3_nmos"] = 2
            self.initial_transistor_sizes["rest_lut_int_buffer_pmos"] = 1
            self.initial_transistor_sizes["inv_lut_int_buffer_1_nmos"] = 2
            self.initial_transistor_sizes["inv_lut_int_buffer_1_pmos"] = 2
            self.initial_transistor_sizes["inv_lut_int_buffer_2_nmos"] = 4
            self.initial_transistor_sizes["inv_lut_int_buffer_2_pmos"] = 6
            self.initial_transistor_sizes["ptran_lut_L4_nmos"] = 3
            self.initial_transistor_sizes["ptran_lut_L5_nmos"] = 3
            self.initial_transistor_sizes["ptran_lut_L6_nmos"] = 3
            self.initial_transistor_sizes["rest_lut_out_buffer_pmos"] = 1
            self.initial_transistor_sizes["inv_lut_out_buffer_1_nmos"] = 2
            self.initial_transistor_sizes["inv_lut_out_buffer_1_pmos"] = 2
            self.initial_transistor_sizes["inv_lut_out_buffer_2_nmos"] = 4
            self.initial_transistor_sizes["inv_lut_out_buffer_2_pmos"] = 6

        else :
            # use transmission gates
            self.transistor_names, self.wire_names = lut_subcircuits.generate_tgate_lut6(subcircuit_filename, min_tran_width, use_finfet)

            # Give initial transistor sizes
            self.initial_transistor_sizes["inv_lut_0sram_driver_2_nmos"] = 4
            self.initial_transistor_sizes["inv_lut_0sram_driver_2_pmos"] = 6
            self.initial_transistor_sizes["tgate_lut_L1_nmos"] = 2
            self.initial_transistor_sizes["tgate_lut_L1_pmos"] = 2
            self.initial_transistor_sizes["tgate_lut_L2_nmos"] = 2
            self.initial_transistor_sizes["tgate_lut_L2_pmos"] = 2
            self.initial_transistor_sizes["tgate_lut_L3_nmos"] = 2
            self.initial_transistor_sizes["tgate_lut_L3_pmos"] = 2
            self.initial_transistor_sizes["inv_lut_int_buffer_1_nmos"] = 2
            self.initial_transistor_sizes["inv_lut_int_buffer_1_pmos"] = 2
            self.initial_transistor_sizes["inv_lut_int_buffer_2_nmos"] = 4
            self.initial_transistor_sizes["inv_lut_int_buffer_2_pmos"] = 6
            self.initial_transistor_sizes["tgate_lut_L4_nmos"] = 3
            self.initial_transistor_sizes["tgate_lut_L4_pmos"] = 3
            self.initial_transistor_sizes["tgate_lut_L5_nmos"] = 3
            self.initial_transistor_sizes["tgate_lut_L5_pmos"] = 3
            self.initial_transistor_sizes["tgate_lut_L6_nmos"] = 3
            self.initial_transistor_sizes["tgate_lut_L6_pmos"] = 3
            self.initial_transistor_sizes["inv_lut_out_buffer_1_nmos"] = 2
            self.initial_transistor_sizes["inv_lut_out_buffer_1_pmos"] = 2
            self.initial_transistor_sizes["inv_lut_out_buffer_2_nmos"] = 4
            self.initial_transistor_sizes["inv_lut_out_buffer_2_pmos"] = 6
        
        
        # Generate input drivers (with register feedback if input is in Rfb)
        self.input_drivers["a"].generate(subcircuit_filename, min_tran_width)
        self.input_drivers["b"].generate(subcircuit_filename, min_tran_width)
        self.input_drivers["c"].generate(subcircuit_filename, min_tran_width)
        self.input_drivers["d"].generate(subcircuit_filename, min_tran_width)
        self.input_drivers["e"].generate(subcircuit_filename, min_tran_width)
        self.input_drivers["f"].generate(subcircuit_filename, min_tran_width)
        
        # Generate input driver loads
        self.input_driver_loads["a"].generate(subcircuit_filename, self.K)
        self.input_driver_loads["b"].generate(subcircuit_filename, self.K)
        self.input_driver_loads["c"].generate(subcircuit_filename, self.K)
        self.input_driver_loads["d"].generate(subcircuit_filename, self.K)
        self.input_driver_loads["e"].generate(subcircuit_filename, self.K)
        self.input_driver_loads["f"].generate(subcircuit_filename, self.K)
       
        return self.initial_transistor_sizes

        
    def _generate_5lut(self, subcircuit_filename, min_tran_width, use_tgate, use_finfet, use_fluts):
        """ This function created the lut subcircuit and all the drivers and driver not subcircuits """
        print("Generating 5-LUT")
        
        # Call the generation function
        if not use_tgate :
            # use pass transistor
            self.transistor_names, self.wire_names = lut_subcircuits.generate_ptran_lut5(subcircuit_filename, min_tran_width, use_finfet)
            # Give initial transistor sizes
            self.initial_transistor_sizes["inv_lut_0sram_driver_2_nmos"] = 4
            self.initial_transistor_sizes["inv_lut_0sram_driver_2_pmos"] = 6
            self.initial_transistor_sizes["ptran_lut_L1_nmos"] = 2
            self.initial_transistor_sizes["ptran_lut_L2_nmos"] = 2
            self.initial_transistor_sizes["ptran_lut_L3_nmos"] = 2
            self.initial_transistor_sizes["rest_lut_int_buffer_pmos"] = 1
            self.initial_transistor_sizes["inv_lut_int_buffer_1_nmos"] = 2
            self.initial_transistor_sizes["inv_lut_int_buffer_1_pmos"] = 2
            self.initial_transistor_sizes["inv_lut_int_buffer_2_nmos"] = 4
            self.initial_transistor_sizes["inv_lut_int_buffer_2_pmos"] = 6
            self.initial_transistor_sizes["ptran_lut_L4_nmos"] = 3
            self.initial_transistor_sizes["ptran_lut_L5_nmos"] = 3
            self.initial_transistor_sizes["rest_lut_out_buffer_pmos"] = 1
            self.initial_transistor_sizes["inv_lut_out_buffer_1_nmos"] = 2
            self.initial_transistor_sizes["inv_lut_out_buffer_1_pmos"] = 2
            self.initial_transistor_sizes["inv_lut_out_buffer_2_nmos"] = 4
            self.initial_transistor_sizes["inv_lut_out_buffer_2_pmos"] = 6
        else :
            # use transmission gates
            self.transistor_names, self.wire_names = lut_subcircuits.generate_tgate_lut5(subcircuit_filename, min_tran_width, use_finfet)
            # Give initial transistor sizes
            self.initial_transistor_sizes["inv_lut_0sram_driver_2_nmos"] = 4
            self.initial_transistor_sizes["inv_lut_0sram_driver_2_pmos"] = 6
            self.initial_transistor_sizes["tgate_lut_L1_nmos"] = 2
            self.initial_transistor_sizes["tgate_lut_L1_pmos"] = 2
            self.initial_transistor_sizes["tgate_lut_L2_nmos"] = 2
            self.initial_transistor_sizes["tgate_lut_L2_pmos"] = 2
            self.initial_transistor_sizes["tgate_lut_L3_nmos"] = 2
            self.initial_transistor_sizes["tgate_lut_L3_pmos"] = 2
            self.initial_transistor_sizes["inv_lut_int_buffer_1_nmos"] = 2
            self.initial_transistor_sizes["inv_lut_int_buffer_1_pmos"] = 2
            self.initial_transistor_sizes["inv_lut_int_buffer_2_nmos"] = 4
            self.initial_transistor_sizes["inv_lut_int_buffer_2_pmos"] = 6
            self.initial_transistor_sizes["tgate_lut_L4_nmos"] = 3
            self.initial_transistor_sizes["tgate_lut_L4_pmos"] = 3
            self.initial_transistor_sizes["tgate_lut_L5_nmos"] = 3
            self.initial_transistor_sizes["tgate_lut_L5_pmos"] = 3
            self.initial_transistor_sizes["inv_lut_out_buffer_1_nmos"] = 2
            self.initial_transistor_sizes["inv_lut_out_buffer_1_pmos"] = 2
            self.initial_transistor_sizes["inv_lut_out_buffer_2_nmos"] = 4
            self.initial_transistor_sizes["inv_lut_out_buffer_2_pmos"] = 6

       
        # Generate input drivers (with register feedback if input is in Rfb)
        self.input_drivers["a"].generate(subcircuit_filename, min_tran_width)
        self.input_drivers["b"].generate(subcircuit_filename, min_tran_width)
        self.input_drivers["c"].generate(subcircuit_filename, min_tran_width)
        self.input_drivers["d"].generate(subcircuit_filename, min_tran_width)
        self.input_drivers["e"].generate(subcircuit_filename, min_tran_width)

        if use_fluts:
            self.input_drivers["f"].generate(subcircuit_filename, min_tran_width)
        
        # Generate input driver loads
        self.input_driver_loads["a"].generate(subcircuit_filename, self.K)
        self.input_driver_loads["b"].generate(subcircuit_filename, self.K)
        self.input_driver_loads["c"].generate(subcircuit_filename, self.K)
        self.input_driver_loads["d"].generate(subcircuit_filename, self.K)
        self.input_driver_loads["e"].generate(subcircuit_filename, self.K)

        if use_fluts:
            self.input_driver_loads["f"].generate(subcircuit_filename, self.K)
        
        return self.initial_transistor_sizes

  
    def _generate_4lut(self, subcircuit_filename, min_tran_width, use_tgate, use_finfet, use_fluts):
        """ This function created the lut subcircuit and all the drivers and driver not subcircuits """
        print("Generating 4-LUT")
        
        # Call the generation function
        if not use_tgate :
            # use pass transistor
            self.transistor_names, self.wire_names = lut_subcircuits.generate_ptran_lut4(subcircuit_filename, min_tran_width, use_finfet)
            # Give initial transistor sizes
            self.initial_transistor_sizes["inv_lut_0sram_driver_2_nmos"] = 4
            self.initial_transistor_sizes["inv_lut_0sram_driver_2_pmos"] = 6
            self.initial_transistor_sizes["ptran_lut_L1_nmos"] = 2
            self.initial_transistor_sizes["ptran_lut_L2_nmos"] = 2
            self.initial_transistor_sizes["rest_lut_int_buffer_pmos"] = 1
            self.initial_transistor_sizes["inv_lut_int_buffer_1_nmos"] = 2
            self.initial_transistor_sizes["inv_lut_int_buffer_1_pmos"] = 2
            self.initial_transistor_sizes["inv_lut_int_buffer_2_nmos"] = 4
            self.initial_transistor_sizes["inv_lut_int_buffer_2_pmos"] = 6
            self.initial_transistor_sizes["ptran_lut_L3_nmos"] = 2
            self.initial_transistor_sizes["ptran_lut_L4_nmos"] = 3
            self.initial_transistor_sizes["rest_lut_out_buffer_pmos"] = 1
            self.initial_transistor_sizes["inv_lut_out_buffer_1_nmos"] = 2
            self.initial_transistor_sizes["inv_lut_out_buffer_1_pmos"] = 2
            self.initial_transistor_sizes["inv_lut_out_buffer_2_nmos"] = 4
            self.initial_transistor_sizes["inv_lut_out_buffer_2_pmos"] = 6
        else :
            # use transmission gates
            self.transistor_names, self.wire_names = lut_subcircuits.generate_tgate_lut4(subcircuit_filename, min_tran_width, use_finfet)
            # Give initial transistor sizes
            self.initial_transistor_sizes["inv_lut_0sram_driver_2_nmos"] = 4
            self.initial_transistor_sizes["inv_lut_0sram_driver_2_pmos"] = 6
            self.initial_transistor_sizes["tgate_lut_L1_nmos"] = 2
            self.initial_transistor_sizes["tgate_lut_L1_pmos"] = 2
            self.initial_transistor_sizes["tgate_lut_L2_nmos"] = 2
            self.initial_transistor_sizes["tgate_lut_L2_pmos"] = 2
            self.initial_transistor_sizes["inv_lut_int_buffer_1_nmos"] = 2
            self.initial_transistor_sizes["inv_lut_int_buffer_1_pmos"] = 2
            self.initial_transistor_sizes["inv_lut_int_buffer_2_nmos"] = 4
            self.initial_transistor_sizes["inv_lut_int_buffer_2_pmos"] = 6
            self.initial_transistor_sizes["tgate_lut_L3_nmos"] = 2
            self.initial_transistor_sizes["tgate_lut_L3_pmos"] = 2
            self.initial_transistor_sizes["tgate_lut_L4_nmos"] = 3
            self.initial_transistor_sizes["tgate_lut_L4_pmos"] = 3
            self.initial_transistor_sizes["inv_lut_out_buffer_1_nmos"] = 2
            self.initial_transistor_sizes["inv_lut_out_buffer_1_pmos"] = 2
            self.initial_transistor_sizes["inv_lut_out_buffer_2_nmos"] = 4
            self.initial_transistor_sizes["inv_lut_out_buffer_2_pmos"] = 6
       
        # Generate input drivers (with register feedback if input is in Rfb)
        self.input_drivers["a"].generate(subcircuit_filename, min_tran_width)
        self.input_drivers["b"].generate(subcircuit_filename, min_tran_width)
        self.input_drivers["c"].generate(subcircuit_filename, min_tran_width)
        self.input_drivers["d"].generate(subcircuit_filename, min_tran_width)
        
        # Generate input driver loads
        self.input_driver_loads["a"].generate(subcircuit_filename, self.K)
        self.input_driver_loads["b"].generate(subcircuit_filename, self.K)
        self.input_driver_loads["c"].generate(subcircuit_filename, self.K)
        self.input_driver_loads["d"].generate(subcircuit_filename, self.K)

        # *TODO: Add the second level of fracturability where the input f also will be used
        # If this is one level fracutrable LUT then the e input will still be used
        if use_fluts:
            self.input_drivers["e"].generate(subcircuit_filename, min_tran_width)
            self.input_driver_loads["e"].generate(subcircuit_filename, self.K)
        
        return self.initial_transistor_sizes