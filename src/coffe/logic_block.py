from src.coffe.circuit_baseclasses import _SizableCircuit, _CompoundCircuit
import src.coffe.fpga as fpga


import src.coffe.mux_subcircuits as mux_subcircuits
import src.coffe.load_subcircuits as load_subcircuits
import src.coffe.utils as utils

from src.coffe.sb_mux import _SwitchBlockMUX
from src.coffe.gen_routing_loads import _RoutingWireLoad
from src.coffe.gen_routing_loads import _GeneralBLEOutputLoad
from src.coffe.ble import _BLE

import src.common.data_structs as rg_ds

# import src.coffe.sb_mux as sb_mux
# import src.coffe.gen_routing_loads as gen_
# import src.coffe.ble as 


from typing import Dict, List, Tuple, Union, Any
import math, os

class _LocalMUX(_SizableCircuit):
    """ Local Routing MUX Class: Pass-transistor 2-level mux with no driver """
    
    def __init__(self, required_size, num_per_tile, use_tgate, gen_wire_load: _RoutingWireLoad, sb_mux: _SwitchBlockMUX):
        # Subcircuit name
        # self.name = f"local_mux_L{gen_r_wire['len']}_uid{gen_r_wire['id']}"
        self.name = "local_mux"
        # Associated Gen Programmable Routing Wire
        self.gen_wire_load = gen_wire_load
        # SB mux used for circuit model
        self.sb_mux = sb_mux
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
        self.delay_weight = fpga.DELAY_WEIGHT_LOCAL_MUX
        # use pass transistor or transmission gates
        self.use_tgate = use_tgate
    
    
    def generate(self, subcircuit_filename, min_tran_width):
        print("Generating local mux")
        
        # Calculate level sizes and number of SRAMs per mux
        self.level2_size = int(math.sqrt(self.required_size))
        self.level1_size = int(math.ceil(float(self.required_size)/self.level2_size))
        self.implemented_size = self.level1_size*self.level2_size
        self.num_unused_inputs = self.implemented_size - self.required_size
        self.sram_per_mux = self.level1_size + self.level2_size
        
        if not self.use_tgate :
            # Call MUX generation function
            self.transistor_names, self.wire_names = mux_subcircuits.generate_ptran_2lvl_mux_no_driver(subcircuit_filename, self.name, self.implemented_size, self.level1_size, self.level2_size)
            
            # Initialize transistor sizes (to something more reasonable than all min size, but not necessarily a good choice, depends on architecture params)
            self.initial_transistor_sizes["ptran_" + self.name + "_L1_nmos"] = 2
            self.initial_transistor_sizes["ptran_" + self.name + "_L2_nmos"] = 2
            self.initial_transistor_sizes["rest_" + self.name + "_pmos"] = 1
            self.initial_transistor_sizes["inv_" + self.name + "_1_nmos"] = 2
            self.initial_transistor_sizes["inv_" + self.name + "_1_pmos"] = 2
        else :
            # Call MUX generation function
            self.transistor_names, self.wire_names = mux_subcircuits.generate_tgate_2lvl_mux_no_driver(subcircuit_filename, self.name, self.implemented_size, self.level1_size, self.level2_size)
            
            # Initialize transistor sizes (to something more reasonable than all min size, but not necessarily a good choice, depends on architecture params)
            self.initial_transistor_sizes["tgate_" + self.name + "_L1_nmos"] = 2
            self.initial_transistor_sizes["tgate_" + self.name + "_L1_pmos"] = 2
            self.initial_transistor_sizes["tgate_" + self.name + "_L2_nmos"] = 2
            self.initial_transistor_sizes["tgate_" + self.name + "_L2_pmos"] = 2
            self.initial_transistor_sizes["inv_" + self.name + "_1_nmos"] = 2
            self.initial_transistor_sizes["inv_" + self.name + "_1_pmos"] = 2
       
        return self.initial_transistor_sizes



    def generate_local_mux_top(self):
        """ Generate the top level local mux SPICE file """
        
        # Create directories
        if not os.path.exists(self.name):
            os.makedirs(self.name)  
        # Change to directory    
        os.chdir(self.name)
        
        subckt_sb_mux_on_str = f"{self.sb_mux.name}_on"

        # TODO link with other definiions elsewhere, duplicated
        # p_str = f"_wire_uid{self.gen_r_wire['id']}"
        # subckt_routing_wire_load_str =  f"{self.gen_wire_load.name}"


        connection_block_filename = self.name + ".sp"
        local_mux_file = open(connection_block_filename, 'w')
        local_mux_file.write(".TITLE Local routing multiplexer\n\n") 
        
        local_mux_file.write("********************************************************************************\n")
        local_mux_file.write("** Include libraries, parameters and other\n")
        local_mux_file.write("********************************************************************************\n\n")
        local_mux_file.write(".LIB \"../includes.l\" INCLUDES\n\n")
        
        local_mux_file.write("********************************************************************************\n")
        local_mux_file.write("** Setup and input\n")
        local_mux_file.write("********************************************************************************\n\n")
        local_mux_file.write(".TRAN 1p 4n SWEEP DATA=sweep_data\n")
        local_mux_file.write(".OPTIONS BRIEF=1\n\n")
        local_mux_file.write("* Input signal\n")
        local_mux_file.write("VIN n_in gnd PULSE (0 supply_v 0 0 0 2n 4n)\n\n")
        
        local_mux_file.write("* Power rail for the circuit under test.\n")
        local_mux_file.write("* This allows us to measure power of a circuit under test without measuring the power of wave shaping and load circuitry.\n")
        local_mux_file.write("V_LOCAL_MUX vdd_local_mux gnd supply_v\n\n")

        local_mux_file.write("********************************************************************************\n")
        local_mux_file.write("** Measurement\n")
        local_mux_file.write("********************************************************************************\n\n")
        local_mux_file.write("* inv_local_mux_1 delay\n")
        local_mux_file.write(".MEASURE TRAN meas_inv_local_mux_1_tfall TRIG V(Xlocal_routing_wire_load_1.Xlocal_mux_on_1.n_in) VAL='supply_v/2' RISE=1\n")
        local_mux_file.write("+    TARG V(n_1_4) VAL='supply_v/2' FALL=1\n")
        local_mux_file.write(".MEASURE TRAN meas_inv_local_mux_1_trise TRIG V(Xlocal_routing_wire_load_1.Xlocal_mux_on_1.n_in) VAL='supply_v/2' FALL=1\n")
        local_mux_file.write("+    TARG V(n_1_4) VAL='supply_v/2' RISE=1\n\n")
        local_mux_file.write("* Total delays\n")
        local_mux_file.write(".MEASURE TRAN meas_total_tfall TRIG V(Xlocal_routing_wire_load_1.Xlocal_mux_on_1.n_in) VAL='supply_v/2' RISE=1\n")
        local_mux_file.write("+    TARG V(n_1_4) VAL='supply_v/2' FALL=1\n")
        local_mux_file.write(".MEASURE TRAN meas_total_trise TRIG V(Xlocal_routing_wire_load_1.Xlocal_mux_on_1.n_in) VAL='supply_v/2' FALL=1\n")
        local_mux_file.write("+    TARG V(n_1_4) VAL='supply_v/2' RISE=1\n\n")

        local_mux_file.write(".MEASURE TRAN meas_logic_low_voltage FIND V(n_1_1) AT=3n\n\n")

        local_mux_file.write("* Measure the power required to propagate a rise and a fall transition through the subcircuit at 250MHz.\n")
        local_mux_file.write(".MEASURE TRAN meas_current INTEGRAL I(V_LOCAL_MUX) FROM=0ns TO=4ns\n")
        local_mux_file.write(".MEASURE TRAN meas_avg_power PARAM = '-(meas_current/4n)*supply_v'\n\n")
        
        local_mux_file.write("********************************************************************************\n")
        local_mux_file.write("** Circuit\n")
        local_mux_file.write("********************************************************************************\n\n")
        local_mux_file.write(f"Xsb_mux_on_1 n_in n_1_1 vsram vsram_n vdd gnd {subckt_sb_mux_on_str}\n")
        local_mux_file.write(f"Xrouting_wire_load_1 n_1_1 n_1_2 n_1_3 vsram vsram_n vdd gnd vdd vdd {self.gen_wire_load.name}\n")
        local_mux_file.write("Xlocal_routing_wire_load_1 n_1_3 n_1_4 vsram vsram_n vdd gnd vdd_local_mux local_routing_wire_load\n")
        local_mux_file.write("Xlut_A_driver_1 n_1_4 n_hang1 vsram vsram_n n_hang2 n_hang3 vdd gnd lut_A_driver\n\n")
        local_mux_file.write(".END")
        local_mux_file.close()

        # Come out of top-level directory
        os.chdir("../")
        
        return (self.name + "/" + self.name + ".sp")

    def generate_top(self):
        print("Generating top-level local mux")
        self.top_spice_path = self.generate_local_mux_top()
        
   
    def update_area(self, area_dict, width_dict):
        """ Update area. To do this, we use area_dict which is a dictionary, maintained externally, that contains
            the area of everything. It is expected that area_dict will have all the information we need to calculate area.
            We update area_dict and width_dict with calculations performed in this function. """        
        
        # MUX area
        if not self.use_tgate :
            area = ((self.level1_size*self.level2_size)*area_dict["ptran_" + self.name + "_L1"] +
                    self.level2_size*area_dict["ptran_" + self.name + "_L2"] +
                    area_dict["rest_" + self.name + ""] +
                    area_dict["inv_" + self.name + "_1"])
        else :
            area = ((self.level1_size*self.level2_size)*area_dict["tgate_" + self.name + "_L1"] +
                    self.level2_size*area_dict["tgate_" + self.name + "_L2"] +
                    # area_dict["rest_" + self.name + ""] +
                    area_dict["inv_" + self.name + "_1"])
          
        # MUX area including SRAM
        area_with_sram = (area + (self.level1_size + self.level2_size)*area_dict["sram"])
          
        width = math.sqrt(area)
        width_with_sram = math.sqrt(area_with_sram)
        area_dict[self.name] = area
        width_dict[self.name] = width
        area_dict[self.name + "_sram"] = area_with_sram
        width_dict[self.name + "_sram"] = width_with_sram



    
    def update_wires(self, width_dict, wire_lengths, wire_layers, ratio):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """

        # Update wire lengths
        wire_lengths["wire_" + self.name + "_L1"] = width_dict[self.name] * ratio
        wire_lengths["wire_" + self.name + "_L2"] = width_dict[self.name] * ratio
        # Update wire layers
        wire_layers["wire_" + self.name + "_L1"] = fpga.LOCAL_WIRE_LAYER
        wire_layers["wire_" + self.name + "_L2"] = fpga.LOCAL_WIRE_LAYER
        
   
    def print_details(self, report_file):
        """ Print local mux details """
    
        utils.print_and_write(report_file, "  LOCAL MUX DETAILS:")
        utils.print_and_write(report_file, "  Style: two-level MUX")
        utils.print_and_write(report_file, "  Required MUX size: " + str(self.required_size) + ":1")
        utils.print_and_write(report_file, "  Implemented MUX size: " + str(self.implemented_size) + ":1")
        utils.print_and_write(report_file, "  Level 1 size = " + str(self.level1_size))
        utils.print_and_write(report_file, "  Level 2 size = " + str(self.level2_size))
        utils.print_and_write(report_file, "  Number of unused inputs = " + str(self.num_unused_inputs))
        utils.print_and_write(report_file, "  Number of MUXes per tile: " + str(self.num_per_tile))
        utils.print_and_write(report_file, "  Number of SRAM cells per MUX: " + str(self.sram_per_mux))
        utils.print_and_write(report_file, "")


class _LocalRoutingWireLoad:
    """ Local routing wire load """
    
    def __init__(self):
        # Name of this wire
        self.name = "local_routing_wire_load"
        # How many LUT inputs are we assuming are used in this logic cluster? (%)
        self.lut_input_usage_assumption = 0.85
        # Total number of local mux inputs per wire
        self.mux_inputs_per_wire = -1
        # Number of on inputs connected to each wire 
        self.on_inputs_per_wire = -1
        # Number of partially on inputs connected to each wire
        self.partial_inputs_per_wire = -1
        #Number of off inputs connected to each wire
        self.off_inputs_per_wire = -1
        # List of wire names in the SPICE circuit
        self.wire_names = []
    

    def generate(self, subcircuit_filename, specs, local_mux):
        print("Generating local routing wire load")
        # Compute load (number of on/partial/off per wire)
        self._compute_load(specs, local_mux)
        #print(self.off_inputs_per_wire)
        # Generate SPICE deck
        self.wire_names = load_subcircuits.local_routing_load_generate(subcircuit_filename, self.on_inputs_per_wire, self.partial_inputs_per_wire, self.off_inputs_per_wire)
    
    
    def update_wires(self, width_dict, wire_lengths, wire_layers, local_routing_wire_load_length):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """
        
        # TODO get wire keys from self.wire_names

        # Update wire lengths
        wire_lengths["wire_local_routing"] = width_dict["logic_cluster"]
        if local_routing_wire_load_length !=0:
            wire_lengths["wire_local_routing"] = local_routing_wire_load_length
        # Update wire layers
        wire_layers["wire_local_routing"] = fpga.LOCAL_WIRE_LAYER
    
        
    def print_details(self):
        print("LOCAL ROUTING WIRE LOAD DETAILS")
        print("")
        
        
    def _compute_load(self, specs, local_mux):
        """ Compute the load on a local routing wire (number of on/partial/off) """
        
        # The first thing we are going to compute is how many local mux inputs are connected to a local routing wire
        # This is a function of local_mux size, N, K, I and Ofb
        num_local_routing_wires = specs.I+specs.N*specs.num_ble_local_outputs
        self.mux_inputs_per_wire = local_mux.implemented_size*specs.N*specs.K/num_local_routing_wires
        
        # Now we compute how many "on" inputs are connected to each routing wire
        # This is a funtion of lut input usage, number of lut inputs and number of local routing wires
        num_local_muxes_used = self.lut_input_usage_assumption*specs.N*specs.K
        self.on_inputs_per_wire = int(num_local_muxes_used/num_local_routing_wires)
        # We want to model for the case where at least one "on" input is connected to the local wire, so make sure it's at least 1
        if self.on_inputs_per_wire < 1:
            self.on_inputs_per_wire = 1
        
        # Now we compute how many partially on muxes are connected to each wire
        # The number of partially on muxes is equal to (level2_size - 1)*num_local_muxes_used/num_local_routing_wire
        # We can figure out the number of muxes used by using the "on" assumption and the number of local routing wires.
        self.partial_inputs_per_wire = int((local_mux.level2_size - 1.0)*num_local_muxes_used/num_local_routing_wires)
        # Make it at least 1
        if self.partial_inputs_per_wire < 1:
            self.partial_inputs_per_wire = 1
        
        # Number of off inputs is simply the difference
        self.off_inputs_per_wire = self.mux_inputs_per_wire - self.on_inputs_per_wire - self.partial_inputs_per_wire
        
class _LocalBLEOutputLoad:

    def __init__(self):
        self.name = "local_ble_output_load"
        
    def generate_local_ble_output_load(self, spice_filename):

        # Open SPICE file for appending
        spice_file = open(spice_filename, 'a')
        
        spice_file.write("******************************************************************************************\n")
        spice_file.write("* Local BLE output load\n")
        spice_file.write("******************************************************************************************\n")
        spice_file.write(".SUBCKT local_ble_output_load n_in n_gate n_gate_n n_vdd n_gnd\n")
        spice_file.write("Xwire_local_ble_output_feedback n_in n_1_1 wire Rw='wire_local_ble_output_feedback_res' Cw='wire_local_ble_output_feedback_cap'\n")
        spice_file.write("Xlocal_routing_wire_load_1 n_1_1 n_1_2 n_gate n_gate_n n_vdd n_gnd n_vdd local_routing_wire_load\n")
        spice_file.write("Xlut_a_driver_1 n_1_2 n_hang1 vsram vsram_n n_hang2 n_hang3 n_vdd n_gnd lut_a_driver\n\n")
        spice_file.write(".ENDS\n\n\n")
        
        spice_file.close()
        
        # Create a list of all wires used in this subcircuit
        wire_names_list = []
        wire_names_list.append("wire_local_ble_output_feedback")
        
        return wire_names_list

    def generate(self, subcircuit_filename):
        self.generate_local_ble_output_load(subcircuit_filename)
     
     
    def update_wires(self, width_dict, wire_lengths, wire_layers, ble_ic_dis):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """
        
        # Update wire lengths
        wire_lengths["wire_local_ble_output_feedback"] = width_dict["logic_cluster"]
        if ble_ic_dis !=0:
            wire_lengths["wire_local_ble_output_feedback"] = ble_ic_dis
        # Update wire layers
        wire_layers["wire_local_ble_output_feedback"] = fpga.LOCAL_WIRE_LAYER



class _LogicCluster(_CompoundCircuit):
    
    def __init__(
            self, N, K, Or, Ofb, Rsel, Rfb, local_mux_size_required,
            num_local_mux_per_tile, use_tgate, use_finfet, use_fluts,
            enable_carry_chain, FAs_per_flut, carry_skip_periphery_count, 
            gen_r_wire: dict,
            gen_r_wire_load: _RoutingWireLoad,
            gen_ble_output_load: _GeneralBLEOutputLoad,
            drv_sb_mux: _SwitchBlockMUX
        ):
        # Name of logic cluster
        # self.name = f"logic_cluster_{gen_r_wire['len']}_uid{gen_r_wire['id']}"
        self.name = "logic_cluster"
        # Set general ble ouput load passed into constructor
        self.gen_ble_output_load = gen_ble_output_load
        # Set SB mux which drives local mux
        self.drv_sb_mux = drv_sb_mux
        # General routing wire associated with this logic cluster
        self.gen_r_wire = gen_r_wire
        # General routing wire load associated with this logic cluster
        self.gen_r_wire_load = gen_r_wire_load
        # Cluster size
        self.N = N
        # Create local BLE output load object
        self.local_ble_output_load = _LocalBLEOutputLoad()
        # Create BLE object
        self.ble = _BLE(
            K, Or, Ofb, Rsel, Rfb, use_tgate, use_finfet, use_fluts, enable_carry_chain,
            FAs_per_flut, carry_skip_periphery_count, N,
            gen_r_wire,
            self.local_ble_output_load,
            self.gen_ble_output_load
        )
        # Create local mux object
        self.local_mux = _LocalMUX(
            local_mux_size_required, num_local_mux_per_tile,
            use_tgate, 
            gen_r_wire_load,
            self.drv_sb_mux
        )
        # Create local routing wire load object
        self.local_routing_wire_load = _LocalRoutingWireLoad()

        self.use_fluts = use_fluts
        self.enable_carry_chain = enable_carry_chain

        
    def generate(self, subcircuits_filename, min_tran_width, specs):
        print("Generating logic cluster")
        init_tran_sizes = {}
        init_tran_sizes.update(self.ble.generate(subcircuits_filename, min_tran_width))
        init_tran_sizes.update(self.local_mux.generate(subcircuits_filename, min_tran_width))
        self.local_routing_wire_load.generate(subcircuits_filename, specs, self.local_mux)
        self.local_ble_output_load.generate(subcircuits_filename)
        
        return init_tran_sizes


    def generate_top(self, all_subckts: Dict[str, rg_ds.SpSubCkt]):
        # pass min_len_wire to our local mux 
        # gen programmable routing -> local mux -> ble 
        # We assume that the shortest wire of our options is loading the input of our local muxes
        self.local_mux.generate_top()
        self.ble.generate_top(all_subckts)
        
        
    def update_area(self, area_dict, width_dict):
        self.ble.update_area(area_dict, width_dict)
        self.local_mux.update_area(area_dict, width_dict)       
        
    
    def update_wires(self, width_dict, wire_lengths, wire_layers, ic_ratio, lut_ratio, ble_ic_dis, local_routing_wire_load_length):
        """ Update wires of things inside the logic cluster. """
        
        # Call wire update functions of member objects.
        self.ble.update_wires(width_dict, wire_lengths, wire_layers, lut_ratio)
        self.local_mux.update_wires(width_dict, wire_lengths, wire_layers, ic_ratio)
        self.local_routing_wire_load.update_wires(width_dict, wire_lengths, wire_layers, local_routing_wire_load_length)
        self.local_ble_output_load.update_wires(width_dict, wire_lengths, wire_layers, ble_ic_dis)
        
        
    def print_details(self, report_file):
        self.local_mux.print_details(report_file)
        self.ble.print_details(report_file)


