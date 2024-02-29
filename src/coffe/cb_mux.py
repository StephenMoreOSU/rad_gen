
from src.coffe.circuit_baseclasses import _SizableCircuit
import src.coffe.fpga as fpga

import src.coffe.mux_subcircuits as mux_subcircuits
import src.coffe.utils as utils

# import src.coffe.sb_mux as sb_mux
# import src.coffe.gen_routing_loads as gen_routing_loads

from src.coffe.sb_mux import _SwitchBlockMUX
# from src.coffe.gen_routing_loads import _RoutingWireLoad 
# import src.coffe.gen_routing_loads as gen_routing_loads

from typing import Dict, List, Tuple, Union, Any
import math, os



class _ConnectionBlockMUX(_SizableCircuit):
    # import src.coffe.sb_mux as sb_mux
    # from src.coffe.sb_mux import _SwitchBlockMUX
    # from src.coffe.gen_routing_loads import _RoutingWireLoad 
    """ Connection Block MUX Class: Pass-transistor 2-level mux """
    
    def __init__(self, required_size, num_per_tile, use_tgate, gen_r_wire: dict, sb_mux: _SwitchBlockMUX, gen_r_wire_load: Any):
        # Name of SB mux loading this CB mux 
        self.sb_mux : _SwitchBlockMUX = sb_mux
        # Subcircuit name
        # self.name = f"cb_mux_L{gen_r_wire['len']}_uid{gen_r_wire['id']}"
        self.name = "cb_mux"
        # Associated Gen Programmable Routing Wire
        self.gen_r_wire = gen_r_wire
        # Associated Gen Programmable Routing Wire Load
        self.gen_r_wire_load : Any = gen_r_wire_load
        # How big should this mux be (dictated by architecture specs)
        self.required_size = required_size 
        # How big did we make the mux (it is possible that we had to make the mux bigger for level sizes to work out, this is how big the mux turned out)
        self.implemented_size = -1
        # This is simply the implemented_size-required_size
        self.num_unused_inputs = -1
        # Number of connection block muxes in one FPGA tile
        self.num_per_tile = num_per_tile
        # Number of SRAM cells per mux
        self.sram_per_mux = -1
        # Size of the first level of muxing
        self.level1_size = -1
        # Size of the second level of muxing
        self.level2_size = -1
        # Delay weight in a representative critical path
        self.delay_weight = fpga.DELAY_WEIGHT_CB_MUX
        # use pass transistor or transmission gates
        self.use_tgate = use_tgate
        # Stores parameter name of wire loads & transistors
        self.wire_names: List[str] = []
        self.transistor_names: List[str] = []
    
    def generate(self, subcircuit_filename, min_tran_width):
        print("Generating connection block mux")
        
        # Calculate level sizes and number of SRAMs per mux
        self.level2_size = int(math.sqrt(self.required_size))
        self.level1_size = int(math.ceil(float(self.required_size)/self.level2_size))
        self.implemented_size = self.level1_size*self.level2_size
        self.num_unused_inputs = self.implemented_size - self.required_size
        self.sram_per_mux = self.level1_size + self.level2_size
        
        # Call MUX generation function
        if not self.use_tgate :
            self.transistor_names, self.wire_names = mux_subcircuits.generate_ptran_2lvl_mux(subcircuit_filename, self.name, self.implemented_size, self.level1_size, self.level2_size)
            # Initialize transistor sizes (to something more reasonable than all min size, but not necessarily a good choice, depends on architecture params)
            self.initial_transistor_sizes["ptran_" + self.name + "_L1_nmos"] = 2
            self.initial_transistor_sizes["ptran_" + self.name + "_L2_nmos"] = 2
            self.initial_transistor_sizes["rest_" + self.name + "_pmos"] = 1
            self.initial_transistor_sizes["inv_" + self.name + "_1_nmos"] = 2
            self.initial_transistor_sizes["inv_" + self.name + "_1_pmos"] = 2
            self.initial_transistor_sizes["inv_" + self.name + "_2_nmos"] = 6
            self.initial_transistor_sizes["inv_" + self.name + "_2_pmos"] = 12
        else :
            self.transistor_names, self.wire_names = mux_subcircuits.generate_tgate_2lvl_mux(subcircuit_filename, self.name, self.implemented_size, self.level1_size, self.level2_size)
            # Initialize transistor sizes (to something more reasonable than all min size, but not necessarily a good choice, depends on architecture params)
            self.initial_transistor_sizes["tgate_" + self.name + "_L1_nmos"] = 2
            self.initial_transistor_sizes["tgate_" + self.name + "_L1_pmos"] = 2
            self.initial_transistor_sizes["tgate_" + self.name + "_L2_nmos"] = 2
            self.initial_transistor_sizes["tgate_" + self.name + "_L2_pmos"] = 2
            self.initial_transistor_sizes["inv_" + self.name + "_1_nmos"] = 2
            self.initial_transistor_sizes["inv_" + self.name + "_1_pmos"] = 2
            self.initial_transistor_sizes["inv_" + self.name + "_2_nmos"] = 6
            self.initial_transistor_sizes["inv_" + self.name + "_2_pmos"] = 12
       
        return self.initial_transistor_sizes

    def generate_connection_block_top(self):
        """ Generate the top level switch block SPICE file """
        
        min_len_wire = fpga.min_len_wire

        # Create directories
        if not os.path.exists(self.name):
            os.makedirs(self.name)  
        # Change to directory    
        os.chdir(self.name)
        
        # TODO link with other definiions elsewhere, duplicated
        subckt_sb_mux_on_str = f"{self.sb_mux.name}_on"
        # p_str = f"_wire_uid{min_len_wire['id']}"
        subckt_routing_wire_load_str =  f"{self.gen_r_wire_load.name}"

        connection_block_filename = self.name + ".sp"
        cb_file = open(connection_block_filename, 'w')
        cb_file.write(".TITLE Connection block multiplexer\n\n") 
        
        cb_file.write("********************************************************************************\n")
        cb_file.write("** Include libraries, parameters and other\n")
        cb_file.write("********************************************************************************\n\n")
        cb_file.write(".LIB \"../includes.l\" INCLUDES\n\n")
        
        cb_file.write("********************************************************************************\n")
        cb_file.write("** Setup and input\n")
        cb_file.write("********************************************************************************\n\n")
        cb_file.write(".TRAN 1p 4n SWEEP DATA=sweep_data\n")
        cb_file.write(".OPTIONS BRIEF=1\n\n")
        cb_file.write("* Input signal\n")
        cb_file.write("VIN n_in gnd PULSE (0 supply_v 0 0 0 2n 4n)\n\n")
        
        cb_file.write("* Power rail for the circuit under test.\n")
        cb_file.write("* This allows us to measure power of a circuit under test without measuring the power of wave shaping and load circuitry.\n")
        cb_file.write("V_CB_MUX vdd_cb_mux gnd supply_v\n\n")
        
        cb_file.write("********************************************************************************\n")
        cb_file.write("** Measurement\n")
        cb_file.write("********************************************************************************\n\n")
        cb_file.write("* inv_cb_mux_1 delay\n")
        cb_file.write(".MEASURE TRAN meas_inv_cb_mux_1_tfall TRIG V(Xrouting_wire_load_1.Xrouting_wire_load_tile_1.Xcb_load_on_1.n_in) VAL='supply_v/2' RISE=1\n")
        cb_file.write("+    TARG V(Xrouting_wire_load_1.Xrouting_wire_load_tile_1.Xcb_load_on_1.Xcb_mux_driver.n_1_1) VAL='supply_v/2' FALL=1\n")
        cb_file.write(".MEASURE TRAN meas_inv_cb_mux_1_trise TRIG V(Xrouting_wire_load_1.Xrouting_wire_load_tile_1.Xcb_load_on_1.n_in) VAL='supply_v/2' FALL=1\n")
        cb_file.write("+    TARG V(Xrouting_wire_load_1.Xrouting_wire_load_tile_1.Xcb_load_on_1.Xcb_mux_driver.n_1_1) VAL='supply_v/2' RISE=1\n\n")
        cb_file.write("* inv_cb_mux_2 delays\n")
        cb_file.write(".MEASURE TRAN meas_inv_cb_mux_2_tfall TRIG V(Xrouting_wire_load_1.Xrouting_wire_load_tile_1.Xcb_load_on_1.n_in) VAL='supply_v/2' FALL=1\n")
        cb_file.write("+    TARG V(Xlocal_routing_wire_load_1.Xlocal_mux_on_1.n_in) VAL='supply_v/2' FALL=1\n")
        cb_file.write(".MEASURE TRAN meas_inv_cb_mux_2_trise TRIG V(Xrouting_wire_load_1.Xrouting_wire_load_tile_1.Xcb_load_on_1.n_in) VAL='supply_v/2' RISE=1\n")
        cb_file.write("+    TARG V(Xlocal_routing_wire_load_1.Xlocal_mux_on_1.n_in) VAL='supply_v/2' RISE=1\n\n")
        cb_file.write("* Total delays\n")
        cb_file.write(".MEASURE TRAN meas_total_tfall TRIG V(Xrouting_wire_load_1.Xrouting_wire_load_tile_1.Xcb_load_on_1.n_in) VAL='supply_v/2' FALL=1\n")
        cb_file.write("+    TARG V(Xlocal_routing_wire_load_1.Xlocal_mux_on_1.n_in) VAL='supply_v/2' FALL=1\n")
        cb_file.write(".MEASURE TRAN meas_total_trise TRIG V(Xrouting_wire_load_1.Xrouting_wire_load_tile_1.Xcb_load_on_1.n_in) VAL='supply_v/2' RISE=1\n")
        cb_file.write("+    TARG V(Xlocal_routing_wire_load_1.Xlocal_mux_on_1.n_in) VAL='supply_v/2' RISE=1\n\n")

        cb_file.write(".MEASURE TRAN meas_logic_low_voltage FIND V(Xlocal_routing_wire_load_1.Xlocal_mux_on_1.n_in) AT=3n\n\n")
        
        cb_file.write("* Measure the power required to propagate a rise and a fall transition through the subcircuit at 250MHz.\n")
        cb_file.write(".MEASURE TRAN meas_current INTEGRAL I(V_CB_MUX) FROM=0ns TO=4ns\n")
        cb_file.write(".MEASURE TRAN meas_avg_power PARAM = '-(meas_current/4n)*supply_v'\n\n")

        cb_file.write("********************************************************************************\n")
        cb_file.write("** Circuit\n")
        cb_file.write("********************************************************************************\n\n")
        cb_file.write(f"Xsb_mux_on_1 n_in n_1_1 vsram vsram_n vdd gnd {subckt_sb_mux_on_str}\n")
        cb_file.write(f"Xrouting_wire_load_1 n_1_1 n_1_2 n_1_3 vsram vsram_n vdd gnd vdd vdd_cb_mux {subckt_routing_wire_load_str}\n")
        cb_file.write("Xlocal_routing_wire_load_1 n_1_3 n_1_4 vsram vsram_n vdd gnd vdd local_routing_wire_load\n")
        cb_file.write("Xlut_a_driver_1 n_1_4 n_hang1 vsram vsram_n n_hang2 n_hang3 vdd gnd lut_a_driver\n\n")
        cb_file.write(".END")
        cb_file.close()

        # Come out of connection block directory
        os.chdir("../")
        
        return (self.name + "/" + self.name + ".sp")


    def generate_top(self):
        print("Generating top-level connection block mux")
        self.top_spice_path = self.generate_connection_block_top() # self.gen_r_wire
        
   
    def update_area(self, area_dict, width_dict):
        """ Update area. To do this, we use area_dict which is a dictionary, maintained externally, that contains
            the area of everything. It is expected that area_dict will have all the information we need to calculate area.
            We update area_dict and width_dict with calculations performed in this function. 
 						The keys in these dictionaries are the names of the various components of the fpga like muxes, switches, etc.
            For each component, generally there are two keys entries: one contains the area without the controlling sram bits
            (this key is just the <component_name>) and the second contains the area with the controlling sram bits (this key 
            is <component_name>_sram). The area associated with "component_name" generally does not include the controlling 
            sram area (but includes everything else like buffers and pass transistors, while 
            the area of "component_name_sram" is the sum of the area of this element including the controlling sram.
        """
            
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
                    # area_dict["rest_" + self.name + ""] +
                    area_dict["inv_" + self.name + "_1"] +
                    area_dict["inv_" + self.name + "_2"])
        
        # MUX area including SRAM
        area_with_sram = (area + (self.level1_size + self.level2_size)*area_dict["sram"])
        
        width = math.sqrt(area)
        width_with_sram = math.sqrt(area_with_sram)
        area_dict[self.name] = area
        width_dict[self.name] = width
        area_dict[self.name + "_sram"] = area_with_sram
        width_dict[self.name + "_sram"] = width_with_sram
        
        # Update VPR area numbers
        if not self.use_tgate :
            area_dict["ipin_mux_trans_size"] = area_dict["ptran_" + self.name + "_L1"]
            area_dict["cb_buf_size"] = area_dict["rest_" + self.name + ""] + area_dict["inv_" + self.name + "_1"] + area_dict["inv_" + self.name + "_2"]
        else :
            area_dict["ipin_mux_trans_size"] = area_dict["tgate_" + self.name + "_L1"]
            area_dict["cb_buf_size"] = area_dict["inv_" + self.name + "_1"] + area_dict["inv_" + self.name + "_2"]  
    
    def update_wires(self, width_dict, wire_lengths, wire_layers, ratio):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """
    
        # Verify that indeed the wires we will update come from the ones initialized in the generate function
        drv_wire_key = [key for key in self.wire_names if f"wire_{self.name}_driver" in key][0]
        l1_wire_key = [key for key in self.wire_names if f"wire_{self.name}_L1" in key][0]
        l2_wire_key = [key for key in self.wire_names if f"wire_{self.name}_L2" in key][0]

        # Not sure where these keys are coming from TODO figure that out and verify them
        s1_inv_key = f"inv_{self.name}_1"
        s2_inv_key = f"inv_{self.name}_2"

       # Assert keys exist in wire_names, unneeded but following convension if wire keys not coming from wire_names
        for wire_key in [drv_wire_key, l1_wire_key, l2_wire_key]:
            assert wire_key in self.wire_names

        # Update wire lengths
        # Divide both driver widths by 4 to get wire from pin -> driver input? Maybe just a back of envelope estimate 
        wire_lengths[drv_wire_key] = (width_dict[s1_inv_key] + width_dict[s2_inv_key]) / 4
        wire_lengths[l1_wire_key] = width_dict[self.name] * ratio
        wire_lengths[l2_wire_key] = width_dict[self.name] * ratio
        
        # Update set wire layers
        wire_layers[drv_wire_key] = fpga.LOCAL_WIRE_LAYER
        wire_layers[l1_wire_key] = fpga.LOCAL_WIRE_LAYER
        wire_layers[l2_wire_key] = fpga.LOCAL_WIRE_LAYER   
        
   
    def print_details(self, report_file):
        """ Print connection block details """

        utils.print_and_write(report_file, "  CONNECTION BLOCK DETAILS:")
        utils.print_and_write(report_file, "  Style: two-level MUX")
        utils.print_and_write(report_file, "  Required MUX size: " + str(self.required_size) + ":1")
        utils.print_and_write(report_file, "  Implemented MUX size: " + str(self.implemented_size) + ":1")
        utils.print_and_write(report_file, "  Level 1 size = " + str(self.level1_size))
        utils.print_and_write(report_file, "  Level 2 size = " + str(self.level2_size))
        utils.print_and_write(report_file, "  Number of unused inputs = " + str(self.num_unused_inputs))
        utils.print_and_write(report_file, "  Number of MUXes per tile: " + str(self.num_per_tile))
        utils.print_and_write(report_file, "  Number of SRAM cells per MUX: " + str(self.sram_per_mux))
        utils.print_and_write(report_file, "")