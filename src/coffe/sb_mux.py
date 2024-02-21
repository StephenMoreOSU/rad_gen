
from src.coffe.circuit_baseclasses import _SizableCircuit
import src.coffe.fpga as fpga

import src.coffe.mux_subcircuits as mux_subcircuits
import src.coffe.utils as utils

from typing import Dict, List, Tuple, Union, Any
import math, os



class _SwitchBlockMUX(_SizableCircuit):
    """ Switch Block MUX Class: Pass-transistor 2-level mux with output driver """
    
    def __init__(self, required_size, num_per_tile, use_tgate, sb_mux_name: str, dst_r_wire: dict):
        # Basename of subckt, will be concatted with a suffix describing the parameters used for generation of this subckt
        self.basename = "sb_mux"
        # Subcircuit name
        self.name = sb_mux_name
        # Parameter String
        self.param_str = self.name.replace(self.basename,"") # remove basename to get parameter string
        # Which wire length is this sb mux driving?
        self.dst_r_wire = dst_r_wire
        # How big should this mux be (dictated by architecture specs)
        self.required_size = required_size 
        # How big did we make the mux (it is possible that we had to make the mux bigger for level sizes to work out, this is how big the mux turned out)
        self.implemented_size = -1
        # This is simply the implemented_size-required_size
        self.num_unused_inputs = -1
        # Number of switch block muxes in one FPGA tile
        self.num_per_tile = num_per_tile
        # Number of SRAM cells per mux
        self.sram_per_mux = -1
        # Size of the first level of muxing
        self.level1_size = -1
        # Size of the second level of muxing
        self.level2_size = -1
        # Delay weight in a representative critical path
        self.delay_weight = fpga.DELAY_WEIGHT_SB_MUX
        # use pass transistor or transmission gates
        self.use_tgate = use_tgate
        
        
    def generate(self, subcircuit_filename, min_tran_width):
        """ 
        Generate switch block mux. 
        Calculates implementation specific details and write the SPICE subcircuit. 
        """
        
        print("Generating switch block mux")
        
        # Calculate level sizes and number of SRAMs per mux
        self.level2_size = int(math.sqrt(self.required_size))
        self.level1_size = int(math.ceil(float(self.required_size)/self.level2_size))
        self.implemented_size = self.level1_size*self.level2_size
        self.num_unused_inputs = self.implemented_size - self.required_size
        self.sram_per_mux = self.level1_size + self.level2_size
        
        # TODO: wouldn't be better for inv 1 to start with pmos = 8 and nmos = 4
        # Call MUX generation function
        if not self.use_tgate :
            self.transistor_names, self.wire_names = mux_subcircuits.generate_ptran_2lvl_mux(subcircuit_filename, self.name, self.implemented_size, self.level1_size, self.level2_size)
            # Initialize transistor sizes (to something more reasonable than all min size, but not necessarily a good choice, depends on architecture params)
            self.initial_transistor_sizes["ptran_" + self.name + "_L1_nmos"] = 3
            self.initial_transistor_sizes["ptran_" + self.name + "_L2_nmos"] = 4
            self.initial_transistor_sizes["rest_" + self.name + "_pmos"] = 1
            self.initial_transistor_sizes["inv_" + self.name + "_1_nmos"] = 8
            self.initial_transistor_sizes["inv_" + self.name + "_1_pmos"] = 4
            self.initial_transistor_sizes["inv_" + self.name + "_2_nmos"] = 10
            self.initial_transistor_sizes["inv_" + self.name + "_2_pmos"] = 20

        else :
            self.transistor_names, self.wire_names = mux_subcircuits.generate_tgate_2lvl_mux(subcircuit_filename, self.name, self.implemented_size, self.level1_size, self.level2_size)
            # Initialize transistor sizes (to something more reasonable than all min size, but not necessarily a good choice, depends on architecture params)
            self.initial_transistor_sizes["tgate_" + self.name + "_L1_nmos"] = 3
            self.initial_transistor_sizes["tgate_" + self.name + "_L1_pmos"] = 3
            self.initial_transistor_sizes["tgate_" + self.name + "_L2_nmos"] = 4
            self.initial_transistor_sizes["tgate_" + self.name + "_L2_pmos"] = 4
            self.initial_transistor_sizes["inv_" + self.name + "_1_nmos"] = 8
            self.initial_transistor_sizes["inv_" + self.name + "_1_pmos"] = 4
            self.initial_transistor_sizes["inv_" + self.name + "_2_nmos"] = 10
            self.initial_transistor_sizes["inv_" + self.name + "_2_pmos"] = 20



       
        return self.initial_transistor_sizes


    def generate_switch_block_top(self):
        """ Generate the top level switch block SPICE file """
        
        # Create directories
        if not os.path.exists(self.name):
            os.makedirs(self.name)  
        # Change to directory    
        os.chdir(self.name)  
        
        # get wire information from dict
        # wire_length = gen_r_wire["len"]
        # wire_id = gen_r_wire["id"]
        # param string default format used by wire
        # TODO remove duplicates
        # p_str = f"_L{wire_length}_uid{wire_id}"

        switch_block_filename = self.name + ".sp"
        sb_file = open(switch_block_filename, 'w')
        sb_file.write(f".TITLE Switch block multiplexer\n\n") 
        
        sb_file.write("********************************************************************************\n")
        sb_file.write("** Include libraries, parameters and other\n")
        sb_file.write("********************************************************************************\n\n")
        sb_file.write(".LIB \"../includes.l\" INCLUDES\n\n")
        
        sb_file.write("********************************************************************************\n")
        sb_file.write("** Setup and input\n")
        sb_file.write("********************************************************************************\n\n")
        sb_file.write(".TRAN 1p 8n SWEEP DATA=sweep_data\n")
        sb_file.write(".OPTIONS BRIEF=1\n\n")
        sb_file.write("* Input signal\n")
        sb_file.write("VIN n_in gnd PULSE (0 supply_v 0 0 0 2n 8n)\n\n")

        sb_file.write("* Power rail for the circuit under test.\n")
        sb_file.write("* This allows us to measure power of a circuit under test without measuring the power of wave shaping and load circuitry.\n")
        sb_file.write("V_SB_MUX vdd_sb_mux gnd supply_v\n\n")

        
        sb_file.write("********************************************************************************\n")
        sb_file.write("** Measurement\n")
        sb_file.write("********************************************************************************\n\n")
        sb_file.write("* inv_sb_mux_1 delay\n")
        sb_file.write(".MEASURE TRAN meas_inv_sb_mux_1_tfall TRIG V(Xrouting_wire_load_1.Xrouting_wire_load_tile_1.Xsb_mux_on_out.n_in) VAL='supply_v/2' RISE=1\n")
        sb_file.write("+    TARG V(Xrouting_wire_load_1.Xrouting_wire_load_tile_1.Xsb_mux_on_out.Xsb_mux_driver.n_1_1) VAL='supply_v/2' FALL=1\n")
        sb_file.write(".MEASURE TRAN meas_inv_sb_mux_1_trise TRIG V(Xrouting_wire_load_1.Xrouting_wire_load_tile_1.Xsb_mux_on_out.n_in) VAL='supply_v/2' FALL=1\n")
        sb_file.write("+    TARG V(Xrouting_wire_load_1.Xrouting_wire_load_tile_1.Xsb_mux_on_out.Xsb_mux_driver.n_1_1) VAL='supply_v/2' RISE=1\n\n")
        sb_file.write("* inv_sb_mux_2 delays\n")
        sb_file.write(".MEASURE TRAN meas_inv_sb_mux_2_tfall TRIG V(Xrouting_wire_load_1.Xrouting_wire_load_tile_1.Xsb_mux_on_out.n_in) VAL='supply_v/2' FALL=1\n")
        sb_file.write("+    TARG V(Xrouting_wire_load_2.Xrouting_wire_load_tile_1.Xsb_mux_on_out.n_in) VAL='supply_v/2' FALL=1\n")
        sb_file.write(".MEASURE TRAN meas_inv_sb_mux_2_trise TRIG V(Xrouting_wire_load_1.Xrouting_wire_load_tile_1.Xsb_mux_on_out.n_in) VAL='supply_v/2' RISE=1\n")
        sb_file.write("+    TARG V(Xrouting_wire_load_2.Xrouting_wire_load_tile_1.Xsb_mux_on_out.n_in) VAL='supply_v/2' RISE=1\n\n")
        sb_file.write("* Total delays\n")
        sb_file.write(".MEASURE TRAN meas_total_tfall TRIG V(Xrouting_wire_load_1.Xrouting_wire_load_tile_1.Xsb_mux_on_out.n_in) VAL='supply_v/2' FALL=1\n")
        sb_file.write("+    TARG V(Xrouting_wire_load_2.Xrouting_wire_load_tile_1.Xsb_mux_on_out.n_in) VAL='supply_v/2' FALL=1\n")
        sb_file.write(".MEASURE TRAN meas_total_trise TRIG V(Xrouting_wire_load_1.Xrouting_wire_load_tile_1.Xsb_mux_on_out.n_in) VAL='supply_v/2' RISE=1\n")
        sb_file.write("+    TARG V(Xrouting_wire_load_2.Xrouting_wire_load_tile_1.Xsb_mux_on_out.n_in) VAL='supply_v/2' RISE=1\n\n")

        sb_file.write(".MEASURE TRAN meas_logic_low_voltage FIND V(Xrouting_wire_load_2.Xrouting_wire_load_tile_1.Xsb_mux_on_out.n_in) AT=7nn\n\n")

        sb_file.write("* Measure the power required to propagate a rise and a fall transition through the subcircuit at 250MHz.\n")
        sb_file.write(".MEASURE TRAN meas_current INTEGRAL I(V_SB_MUX) FROM=0ns TO=4ns\n")
        sb_file.write(".MEASURE TRAN meas_avg_power PARAM = '-(meas_current/4n)*supply_v'\n\n")

        sb_file.write("********************************************************************************\n")
        sb_file.write("** Circuit\n")
        sb_file.write("********************************************************************************\n\n")
        sb_file.write(f"Xsb_mux_on_1 n_in n_1_1 vsram vsram_n vdd gnd {self.name}_on\n\n")
        sb_file.write(f"Xrouting_wire_load_1 n_1_1 n_2_1 n_hang_1 vsram vsram_n vdd gnd vdd_sb_mux vdd routing_wire_load{self.param_str}\n\n")
        sb_file.write(f"Xrouting_wire_load_2 n_2_1 n_3_1 n_hang_2 vsram vsram_n vdd gnd vdd vdd routing_wire_load{self.param_str}\n\n")
        sb_file.write(".END")
        sb_file.close()
        
        # Come out of swich block directory
        os.chdir("../")
        
        return (self.name + "/" + self.name + ".sp")


    def generate_top(self):
        """ Generate top level SPICE file """
        
        print("Generating top-level switch block mux")
        self.top_spice_path = self.generate_switch_block_top()

   
   
    def update_area(self, area_dict, width_dict):
        """ Update area. To do this, we use area_dict which is a dictionary, maintained externally, that contains
            the area of everything. It is expected that area_dict will have all the information we need to calculate area.
            We update area_dict and width_dict with calculations performed in this function. """
        
        # MUX area
        if not self.use_tgate :
            area = ((self.level1_size*self.level2_size)*area_dict["ptran_" + self.name + "_L1"] +
                    self.level2_size*area_dict["ptran_" + self.name + "_L2"] +
                    area_dict["rest_" + self.name + ""] +
                    area_dict["inv_" + self.name + "_1"] +
                    area_dict["inv_" + self.name + "_2"])
        else :
            area = ((self.level1_size*self.level2_size)*area_dict["tgate_" + self.name + "_L1"] +
                    self.level2_size*area_dict["tgate_" + self.name + "_L2"] +
                    area_dict["inv_" + self.name + "_1"] +
                    area_dict["inv_" + self.name + "_2"])

        # MUX area including SRAM
        area_with_sram = (area + (self.level1_size + self.level2_size) * area_dict["sram"])
        
        width = math.sqrt(area)
        width_with_sram = math.sqrt(area_with_sram)
        area_dict[self.name] = area
        width_dict[self.name] = width
        area_dict[self.name + "_sram"] = area_with_sram
        width_dict[self.name + "_sram"] = width_with_sram
        
        # Update VPR areas
        if not self.use_tgate :
            area_dict["switch_mux_trans_size"] = area_dict["ptran_" + self.name + "_L1"]
            area_dict["switch_buf_size"] = area_dict["rest_" + self.name + ""] + area_dict["inv_" + self.name + "_1"] + area_dict["inv_" + self.name + "_2"]
        else :
            area_dict["switch_mux_trans_size"] = area_dict["tgate_" + self.name + "_L1"]
            area_dict["switch_buf_size"] = area_dict["inv_" + self.name + "_1"] + area_dict["inv_" + self.name + "_2"]


    def update_wires(self, width_dict: Dict[str, float], wire_lengths: Dict[str, float], wire_layers: Dict[str, int], ratio: float):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """

        # Update wire lengths
        # Divide both driver widths by 4 to get wire from pin -> driver input? Maybe just a back of envelope estimate 
        wire_lengths["wire_" + self.name + "_driver"] = (width_dict["inv_" + self.name + "_1"] + width_dict["inv_" + self.name + "_2"])/4
        wire_lengths["wire_" + self.name + "_L1"] = width_dict[self.name] * ratio
        wire_lengths["wire_" + self.name + "_L2"] = width_dict[self.name] * ratio
        
        # Update set wire layers
        wire_layers["wire_" + self.name + "_driver"] = fpga.LOCAL_WIRE_LAYER
        wire_layers["wire_" + self.name + "_L1"] = fpga.LOCAL_WIRE_LAYER
        wire_layers["wire_" + self.name + "_L2"] = fpga.LOCAL_WIRE_LAYER
    
    
    def print_details(self, report_file):
        """ Print switch block details """

        utils.print_and_write(report_file, "  SWITCH BLOCK DETAILS:")
        utils.print_and_write(report_file, "  Style: two-level MUX")
        utils.print_and_write(report_file, "  Required MUX size: " + str(self.required_size) + ":1")
        utils.print_and_write(report_file, "  Implemented MUX size: " + str(self.implemented_size) + ":1")
        utils.print_and_write(report_file, "  Level 1 size = " + str(self.level1_size))
        utils.print_and_write(report_file, "  Level 2 size = " + str(self.level2_size))
        utils.print_and_write(report_file, "  Number of unused inputs = " + str(self.num_unused_inputs))
        utils.print_and_write(report_file, "  Number of MUXes per tile: " + str(self.num_per_tile))
        utils.print_and_write(report_file, "  Number of SRAM cells per MUX: " + str(self.sram_per_mux))
        utils.print_and_write(report_file, "")