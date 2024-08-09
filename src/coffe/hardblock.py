# -*- coding: utf-8 -*-
"""
    This module contains implementations for custom circuitry, loading, and testbenches for hardblocks in the FPGA.
"""

import math

import src.coffe.mux_subcircuits as mux_subcircuits
import src.coffe.memory_subcircuits as memory_subcircuits
import src.coffe.load_subcircuits as load_subcircuits
import src.coffe.utils as utils

from src.coffe.circuit_baseclasses import _SizableCircuit, _CompoundCircuit
import src.coffe.top_level as top_level

import src.common.data_structs as rg_ds
import src.asic_dse.asic_dse as asic_dse

import src.coffe.fpga as fpga

from typing import List, Dict, Tuple

class _HBLocalMUX(_SizableCircuit):
    """ Hard block Local MUX Class: Pass-transistor 2-level mux with driver """
    
    def __init__(self, required_size, num_per_tile, use_tgate, hb_parameters):
        
        self.hb_parameters = hb_parameters
        # Subcircuit name
        self.name = hb_parameters['name'] + "_local_mux"
        # How big should this mux be (dictated by architecture specs)
        self.required_size = required_size 
        # How big did we make the mux (it is possible that we had to make the mux bigger for level sizes to work out, this is how big the mux turned out)
        self.implemented_size = -1
        # This is simply the implemented_size-required_size
        self.num_unused_inputs = -1
        # Number of hardblock local muxes in one FPGA tile
        self.num_per_tile = num_per_tile
        # Number of SRAM cells per mux
        self.sram_per_mux = -1
        # Size of the first level of muxing
        self.level1_size = -1
        # Size of the second level of muxing
        self.level2_size = -1
        # Delay weight in a representative critical path
        self.delay_weight = fpga.DELAY_WEIGHT_RAM
        # use pass transistor or transmission gates
        self.use_tgate = use_tgate
    
    
    def generate(self, subcircuit_filename, min_tran_width):
        print("Generating HB local mux")
        
        # Calculate level sizes and number of SRAMs per mux
        self.level2_size = int(math.sqrt(self.required_size))
        self.level1_size = int(math.ceil(float(self.required_size)/self.level2_size))
        self.implemented_size = self.level1_size*self.level2_size
        self.num_unused_inputs = self.implemented_size - self.required_size
        self.sram_per_mux = self.level1_size + self.level2_size
        
        if not self.use_tgate :
            # Call generation function
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
            # Call MUX generation function
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

    def generate_top(self):
        print("Generating top-level HB local mux")
        self.top_spice_path = top_level.generate_HB_local_mux_top(self.name, self.hb_parameters['name'])

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
        self.area = area
        width_dict[self.name] = width
        area_dict[self.name + "_sram"] = area_with_sram
        width_dict[self.name + "_sram"] = width_with_sram

    def update_wires(self, width_dict, wire_lengths, wire_layers):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """

        # Update wire lengths
        wire_lengths["wire_" + self.name + "_driver"] = (width_dict["inv_" + self.name + "_1"] + width_dict["inv_" + self.name + "_2"])/4
        wire_lengths["wire_" + self.name + "_L1"] = width_dict[self.name]
        wire_lengths["wire_" + self.name + "_L2"] = width_dict[self.name]
        
        # Update wire layers
        wire_layers["wire_" + self.name + "_driver"] = 0
        wire_layers["wire_" + self.name + "_L1"] = 0
        wire_layers["wire_" + self.name + "_L2"] = 0  

    def print_details(self, report_file):
        """ Print hardblock local mux details """
        utils.print_and_write(report_file, "  Style: two-level MUX")
        utils.print_and_write(report_file, "  Required MUX size: " + str(self.required_size) + ":1")
        utils.print_and_write(report_file, "  Implemented MUX size: " + str(self.implemented_size) + ":1")
        utils.print_and_write(report_file, "  Level 1 size = " + str(self.level1_size))
        utils.print_and_write(report_file, "  Level 2 size = " + str(self.level2_size))
        utils.print_and_write(report_file, "  Number of unused inputs = " + str(self.num_unused_inputs))
        utils.print_and_write(report_file, "  Number of MUXes per tile: " + str(self.num_per_tile))
        utils.print_and_write(report_file, "  Number of SRAM cells per MUX: " + str(self.sram_per_mux))
        utils.print_and_write(report_file, "")



class _HBLocalRoutingWireLoad:
    """ Hard Block Local routing wire load """
    
    def __init__(self, hb_parameters):
        self.hb_parameters = hb_parameters
        # Name of this wire
        self.name = hb_parameters['name'] + "_local_routing_wire_load"
        # This is obtained from the user)
        self.RAM_input_usage_assumption = hb_parameters['input_usage']
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


    def generate(self, subcircuit_filename, specs, HB_local_mux):
        print("Generating local routing wire load")
        # Compute load (number of on/partial/off per wire)
        self._compute_load(specs, HB_local_mux)
        # Generate SPICE deck
        self.wire_names = load_subcircuits.hb_local_routing_load_generate(subcircuit_filename, self.on_inputs_per_wire, self.partial_inputs_per_wire, self.off_inputs_per_wire, self.name, HB_local_mux.name)
    
    
    def update_wires(self, width_dict, wire_lengths, wire_layers):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """
        
        # Update wire lengths
        wire_lengths["wire_"+self.hb_parameters['name']+"_local_routing"] = width_dict[self.hb_parameters['name']]
        # Update wire layers
        wire_layers["wire_"+self.hb_parameters['name']+"_local_routing"] = 0
    
        
    def _compute_load(self, specs, HB_local_mux):
        """ Compute the load on a local routing wire (number of on/partial/off) """
        
        # The first thing we are going to compute is how many local mux inputs are connected to a local routing wire
        # FOR a ram block its the number of inputs
        num_local_routing_wires = self.hb_parameters['num_gen_inputs']
        self.mux_inputs_per_wire = HB_local_mux.implemented_size
        
        # Now we compute how many "on" inputs are connected to each routing wire
        # Right now I assume the hard block doesn't have any local feedbacks. If that's the case the following line should be changed
        num_local_muxes_used = self.RAM_input_usage_assumption*self.hb_parameters['num_gen_inputs']
        self.on_inputs_per_wire = int(num_local_muxes_used/num_local_routing_wires)
        # We want to model for the case where at least one "on" input is connected to the local wire, so make sure it's at least 1
        if self.on_inputs_per_wire < 1:
            self.on_inputs_per_wire = 1
        
        # Now we compute how many partially on muxes are connected to each wire
        # The number of partially on muxes is equal to (level2_size - 1)*num_local_muxes_used/num_local_routing_wire
        # We can figure out the number of muxes used by using the "on" assumption and the number of local routing wires.
        self.partial_inputs_per_wire = int((HB_local_mux.level2_size - 1.0)*num_local_muxes_used/num_local_routing_wires)
        # Make it at least 1
        if self.partial_inputs_per_wire < 1:
            self.partial_inputs_per_wire = 1
        
        # Number of off inputs is simply the difference
        self.off_inputs_per_wire = self.mux_inputs_per_wire - self.on_inputs_per_wire - self.partial_inputs_per_wire



# We need four classes for a hard block
# The high-level, the input crossbar, and possibly dedicated routing links and the local routing wireload
class _dedicated_routing_driver(_SizableCircuit):
    """ dedicated routing driver class"""

    def __init__(self, name, top_name, num_buffers):

        # Subcircuit name
        self.name = name
        # hard block name
        self.top_name = top_name
        
        self.num_buffers = num_buffers
    def generate(self, subcircuit_filename, min_tran_width):
        print("Generating hard block " + self.name +" dedicated routing driver")

        self.transistor_names, self.wire_names = mux_subcircuits.generate_dedicated_driver(subcircuit_filename, self.name, self.num_buffers, self.top_name)
            
        for i in range(1, self.num_buffers * 2 + 1):
            self.initial_transistor_sizes["inv_" + self.name + "_"+str(i)+"_nmos"] = 2
            self.initial_transistor_sizes["inv_" + self.name + "_"+str(i)+"_pmos"] = 2
  

        return self.initial_transistor_sizes

    def generate_top(self):
        print("Generating top-level submodules")

        self.top_spice_path = top_level.generate_dedicated_driver_top(self.name, self.top_name, self.num_buffers)

   
    def update_area(self, area_dict, width_dict):
        """ Update area. To do this, we use area_dict which is a dictionary, maintained externally, that contains
            the area of everything. It is expected that area_dict will have all the information we need to calculate area.
            We update area_dict and width_dict with calculations performed in this function. """        

        area = 0.0
        for i in range(1, self.num_buffers * 2 + 1):
            area += area_dict["inv_" + self.name +"_"+ str(i) ]

        area_with_sram = area
        self.area = area

        width = math.sqrt(area)
        width_with_sram = math.sqrt(area_with_sram)
        area_dict[self.name] = area
        width_dict[self.name] = width
        area_dict[self.name + "_sram"] = area_with_sram
        width_dict[self.name + "_sram"] = width_with_sram


class _hard_block(_CompoundCircuit):
    """ hard block class"""

    def __init__(self, hardblock_info: rg_ds.Hardblock, use_tgate):
        self.hardblock_info = hardblock_info
        # Hack to convert hardblock dataclass to dict
        hb_params = {}
        for _field in rg_ds.Hardblock.__dataclass_fields__:
            hb_params[_field] = getattr(hardblock_info, _field)
        #Call the hard block parameter parser
        self.parameters = hb_params

        # Subcircuit name
        self.name = self.parameters['name']
        #create the inner objects
        self.mux = _HBLocalMUX(int(math.ceil(self.parameters['num_gen_inputs']/self.parameters['num_crossbars'] * self.parameters['crossbar_population'])), self.parameters['num_gen_inputs'], use_tgate, self.parameters)
        self.load = _HBLocalRoutingWireLoad(self.parameters)
        if self.parameters['num_dedicated_outputs'] > 0:
            # the user can change this line to add more buffers to their dedicated links. In my case 2 will do.
            self.dedicated =_dedicated_routing_driver(self.name + "_ddriver", self.name, 2)

        self.flow_results = (-1.0,-1.0,-1.0)

    def generate(self, subcircuit_filename: str, min_tran_width) -> Dict[str, float]:
        print("Generating hard block " + self.name)

        # generate subblocks
        init_tran_sizes = {}
        init_tran_sizes.update(self.mux.generate(subcircuit_filename, min_tran_width))
        if self.parameters['num_dedicated_outputs'] > 0:
            init_tran_sizes.update(self.dedicated.generate(subcircuit_filename, min_tran_width))
        # wireload
        self.load.generate(subcircuit_filename, min_tran_width, self.mux)

        return init_tran_sizes

    def generate_top(self, size_hb_interfaces):

        print("Generating top-level submodules")

        self.mux.generate_top()
        if self.parameters['num_dedicated_outputs'] > 0:
            self.dedicated.generate_top()

        # hard block flow
        if size_hb_interfaces == 0.0:
            self.flow_results = asic_dse.run_asic_dse(self.hardblock_info.asic_dse_cli)
            # The area returned by the hardblock flow is in um^2. In area_dict, all areas are in nm^2 
            self.area = self.flow_results[0] * self.parameters['area_scale_factor'] * (1e+6) 
            self.mux.lowerbounddelay = self.flow_results[1] * (1.0/self.parameters['freq_scale_factor']) * 1e-9
        
            if self.parameters['num_dedicated_outputs'] > 0:
                self.dedicated.lowerbounddelay = self.flow_results[1] * (1.0/self.parameters['freq_scale_factor']) * 1e-9
        else:
            # Ask Andrew what this code is doing, why would we not want to run asic flow when even if we aren't sizing hb interfaces
            self.area = 0.0
            self.mux.lowerbounddelay = size_hb_interfaces  * 1e-9
            if self.parameters['num_dedicated_outputs'] > 0:
                self.dedicated.lowerbounddelay = size_hb_interfaces  * 1e-9

    # def generate_hb_scripts(self):
    #     print("Generating hardblock tcl scripts for Synthesis, Place and Route, and Static Timing Analysis")
    #     hardblock_functions.hardblock_script_gen(self.parameters)
    #     print("Finished Generating scripts, exiting...")
    
    # def generate_top_parallel(self):
    #     print("Generating top-level submodules")
    #     # UNCOMMENT BELOW WHEN PLL FLOW RETURNS BEST RESULT TODO integrate into custom flow
    #     # self.mux.generate_top()
    #     # if self.parameters['num_dedicated_outputs'] > 0:
    #     #     self.dedicated.generate_top()

    #     ## hard block flow
    #     print("Running Parallel ASIC flow for hardblock...")
    #     #self.flow_results = 
    #     hardblock_functions.hardblock_parallel_flow(self.parameters)
    #     print("Finished hardblock flow run")

    #     ##the area returned by the hardblock flow is in um^2. In area_dict, all areas are in nm^2 
    #     # self.area = self.flow_results[0] * self.parameters['area_scale_factor'] * (1e+6) 

    #     # self.mux.lowerbounddelay = self.flow_results[1] * (1.0/self.parameters['freq_scale_factor']) * 1e-9
		
    #     # if self.parameters['num_dedicated_outputs'] > 0:
    #     #     self.dedicated.lowerbounddelay = self.flow_results[1] * (1.0/self.parameters['freq_scale_factor']) * 1e-9

    # def generate_parallel_results(self):
    #     print("Generating hardblock parallel results by parsing existing outputs...")
    #     report_csv_fname, out_dict = hardblock_functions.parse_parallel_outputs(self.parameters)
    #     #lowest_cost_dict = hardblock_functions.find_lowest_cost_in_result_dict(self.parameters,out_dict)
    #     plot_return = hardblock_functions.run_plot_script(self.parameters,report_csv_fname)


    def update_area(self, area_dict, width_dict):
        """ Update area. To do this, we use area_dict which is a dictionary, maintained externally, that contains
            the area of everything. It is expected that area_dict will have all the information we need to calculate area.
            We update area_dict and width_dict with calculations performed in this function. """        
        
        # update the area of subblocks:
        self.mux.update_area(area_dict, width_dict)

        if self.parameters['num_dedicated_outputs'] > 0:
            self.dedicated.update_area(area_dict, width_dict) 

        # area of the block itself
        if self.parameters['num_dedicated_outputs'] > 0:
            area = self.parameters['num_dedicated_outputs'] * area_dict[self.name + "_ddriver"] + self.parameters['num_gen_inputs'] * area_dict[self.mux.name] + self.area
            area_with_sram = self.parameters['num_dedicated_outputs'] * area_dict[self.name + "_ddriver"] + self.parameters['num_gen_inputs'] * area_dict[self.mux.name + "_sram"] + self.area
        else :
            area = self.parameters['num_gen_inputs'] * area_dict[self.mux.name] + self.area
            area_with_sram = self.parameters['num_gen_inputs'] * area_dict[self.mux.name + "_sram"] + self.area

        width = math.sqrt(area)
        width_with_sram = math.sqrt(area_with_sram)
        area_dict[self.name] = area
        width_dict[self.name] = width
        area_dict[self.name + "_sram"] = area_with_sram
        width_dict[self.name + "_sram"] = width_with_sram

    def update_wires(self, width_dict, wire_lengths, wire_layers):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """

        # Update wire lengths
        wire_lengths["wire_" + self.name + "_1"] = width_dict[self.name]
        wire_lengths["wire_" + self.name + "_2"] = width_dict["tile"] * self.parameters['soft_logic_per_block']
        wire_lengths["wire_" + self.name + "_local_routing_wire_load"] = width_dict[self.name]
        
        # Update wire layers
        wire_layers["wire_" + self.name + "_1"] = 0
        wire_layers["wire_" + self.name + "_2"] = 1  
        wire_layers["wire_" + self.name + "_local_routing_wire_load"] = 0

    def print_details(self, report_file):
        """ Print hardblock details """
        utils.print_and_write(report_file, "  DETAILS OF HARD BLOCK: " + self.name)
        utils.print_and_write(report_file, "  Localmux:")
        self.mux.print_details(report_file)
        #utils.print_and_write(report_file, "  Wireload:")
        #self.load.print_details(report_file)
        #if self.parameters['num_dedicated_outputs'] > 0:
        #    utils.print_and_write(report_file, "  Dedicated output routing:")
        #    self.dedicated.print_details(report_file)

