# This module contains classes that describe FPGA circuitry. 
#
# The most important class (and the only one that should be instantiated outside this 
# file) is the 'fpga' class defined at the bottom of the file. 
#
# An 'fpga' object describes the FPGA that we want to design. A tile-based FPGA is 
# assumed, which consists of a switch block, a connection block and a logic cluster.
# Likewise, the 'fpga' object contains a 'SwitchBlockMUX' object, a 'ConnectionBlockMUX' 
# and a 'LogicCluster' object, each of which describe those parts of the FPGA in more detail.
# The 'LogicCluster' contains other objects that describe the various parts of its circuitry
# (local routing multiplexers, LUTs, FF, etc.) When you create an 'fpga' object, you 
# specify architecture parameters along with a few process parameters which are stored 
# in the 'fpga' object. 
#
# The 'fpga' does more than just hold information about the FPGA.
#
#      - It uses this information to generate the SPICE netlists that COFFE uses to 
#        measure delay. These netlists are generated with the appropriate transistor and
#        wire loading, which are a function of architecture parameters, transistor sizes as
#        well as some hard-coded layout assumptions (see [1] for layout assumption details).
#        It is important to note that these netlists only contain 'transistor-size' and 
#        'wire-load' VARIABLES and not hard-coded sizes and wire loads. These variables are
#        defined in their own external files. This allows us to create a single set of netlists. 
#        As COFFE changes the sizes of transistors, it only has to modify these external
#        files and the netlist will behave appropriately (transistor and wire loads depend on 
#        transistor sizes). 
#
#      - It can calculate the physical area of each circuit and structure inside the FPGA 
#        (transistors, MUXes, LUTs, BLE, Logic Cluster, FPGA tile, etc.) based on the sizes of
#        transistors and circuit topologies.
#
#      - It can calculate the length of wires in the FPGA circuitry based on the area of 
#        the circuitry and the layout assumptions.
#
#      - It can report the delay of each subcircuit in the FPGA.
#
# COFFE's transistor sizing engine uses the 'fpga' object to evaluate the impact of different transistor
# sizing combinations on the area and delay of the FPGA.
#
# [1] C. Chiasson and V. Betz, "COFFE: Fully-Automated Transistor Sizing for FPGAs", FPT2013
from __future__ import annotations

import os
import sys
import math
import logging
import random

from typing import List, Dict, Any, Tuple, Union, Set
from collections import defaultdict
from dataclasses import dataclass
import csv
import traceback

# Subcircuit Modules
import src.coffe.basic_subcircuits as basic_subcircuits
import src.coffe.mux_subcircuits as mux_subcircuits
import src.coffe.lut_subcircuits as lut_subcircuits
import src.coffe.ff_subcircuits as ff_subcircuits
import src.coffe.load_subcircuits as load_subcircuits
import src.coffe.memory_subcircuits as memory_subcircuits
import src.coffe.utils as utils
import src.coffe.cost as cost

from src.coffe.circuit_baseclasses import _SizableCircuit, _CompoundCircuit

# Top level file generation module
import src.coffe.top_level as top_level

# HSPICE handling module
import src.coffe.spice as spice

# Rad Gen data structures
import src.common.data_structs as rg_ds
import src.common.utils as rg_utils

import src.common.spice_parser as sp_parser

from collections import OrderedDict

# ASIC DSE imports
import src.asic_dse.asic_dse as asic_dse

# Importing individual constructors for subckt classes
from src.coffe.sb_mux import _SwitchBlockMUX
from src.coffe.cb_mux import _ConnectionBlockMUX 
from src.coffe.logic_block import _LogicCluster
from src.coffe.gen_routing_loads import _GeneralBLEOutputLoad, _RoutingWireLoad
from src.coffe.carry_chain import _CarryChain, _CarryChainMux, _CarryChainInterCluster, _CarryChainPer, _CarryChainSkipMux, _CarryChainSkipAnd

# Track-access locality constants
OUTPUT_TRACK_ACCESS_SPAN = 0.25
INPUT_TRACK_ACCESS_SPAN = 0.50

# Delay weight constants:
DELAY_WEIGHT_SB_MUX = 0.4107
DELAY_WEIGHT_CB_MUX = 0.0989
DELAY_WEIGHT_LOCAL_MUX = 0.0736
DELAY_WEIGHT_LUT_A = 0.0396
DELAY_WEIGHT_LUT_B = 0.0379
DELAY_WEIGHT_LUT_C = 0.0704 # This one is higher because we had register-feedback coming into this mux.
DELAY_WEIGHT_LUT_D = 0.0202
DELAY_WEIGHT_LUT_E = 0.0121
DELAY_WEIGHT_LUT_F = 0.0186
DELAY_WEIGHT_LUT_FRAC = 0.0186
DELAY_WEIGHT_LOCAL_BLE_OUTPUT = 0.0267
DELAY_WEIGHT_GENERAL_BLE_OUTPUT = 0.0326
# The res of the ~15% came from memory, DSP, IO and FF based on my delay profiling experiments.
DELAY_WEIGHT_RAM = 0.15
HEIGHT_SPAN = 0.5

LOCAL_WIRE_LAYER = 0
# This parameter determines if RAM core uses the low power transistor technology
# It is strongly suggested to keep it this way since our
# core RAM modules were designed to operate with low power transistors.
# Therefore, changing it might require other code changes.
# I have included placeholder functions in case someone really insists to remove it
# The easier alternative to removing it is to just provide two types of transistors which are actually the same
# In that case the user doesn't need to commit any code changes.
use_lp_transistor = 1

# Minimum length wire object
# Used for modeling LB ipins
min_len_wire: dict = {}
class _Specs:
    """ General FPGA specs. """
 
    def __init__(self, arch_params_dict, quick_mode_threshold):
        
        # FPGA architecture specs
        self.N                       = arch_params_dict['N']
        self.K                       = arch_params_dict['K']
        self.W                       = arch_params_dict['W']
        # self.L                       = arch_params_dict['L']
        self.wire_types:            List[Dict[str, Any]]                = arch_params_dict['wire_types']
        self.Fs_mtx:                List[Dict[str, Any]]                = arch_params_dict['Fs_mtx']
        self.sb_muxes:              List[Dict[str, Any]]                = arch_params_dict['sb_muxes']
        self.I                       = arch_params_dict['I']
        self.Fs                      = arch_params_dict['Fs']
        self.Fcin                    = arch_params_dict['Fcin']
        self.Fcout                   = arch_params_dict['Fcout']
        self.Fclocal                 = arch_params_dict['Fclocal']
        self.num_ble_general_outputs = arch_params_dict['Or']
        self.num_ble_local_outputs   = arch_params_dict['Ofb']
        self.num_cluster_outputs     = self.N*self.num_ble_general_outputs
        self.Rsel                    = arch_params_dict['Rsel']
        self.Rfb                     = arch_params_dict['Rfb']
        self.use_fluts               = arch_params_dict['use_fluts']
        self.independent_inputs      = arch_params_dict['independent_inputs']
        self.enable_carry_chain      = arch_params_dict['enable_carry_chain']
        self.carry_chain_type        = arch_params_dict['carry_chain_type']
        self.FAs_per_flut            = arch_params_dict['FAs_per_flut']

        # BRAM specs
        self.row_decoder_bits     = arch_params_dict['row_decoder_bits']
        self.col_decoder_bits     = arch_params_dict['col_decoder_bits']
        self.conf_decoder_bits    = arch_params_dict['conf_decoder_bits']
        self.sense_dv             = arch_params_dict['sense_dv']
        self.worst_read_current   = arch_params_dict['worst_read_current']
        self.quick_mode_threshold = quick_mode_threshold
        self.vdd_low_power        = arch_params_dict['vdd_low_power']
        self.vref                 = arch_params_dict['vref']
        self.number_of_banks      = arch_params_dict['number_of_banks']
        self.memory_technology    = arch_params_dict['memory_technology']
        self.SRAM_nominal_current = arch_params_dict['SRAM_nominal_current']
        self.MTJ_Rlow_nominal     = arch_params_dict['MTJ_Rlow_nominal']
        self.MTJ_Rlow_worstcase   = arch_params_dict['MTJ_Rlow_worstcase']
        self.MTJ_Rhigh_worstcase  = arch_params_dict['MTJ_Rhigh_worstcase']
        self.MTJ_Rhigh_nominal    = arch_params_dict['MTJ_Rhigh_nominal']
        self.vclmp                = arch_params_dict['vclmp']
        self.read_to_write_ratio  = arch_params_dict['read_to_write_ratio']
        self.enable_bram_block    = arch_params_dict['enable_bram_module']
        self.ram_local_mux_size   = arch_params_dict['ram_local_mux_size']


        # Technology specs
        self.vdd                      = arch_params_dict['vdd']
        self.vsram                    = arch_params_dict['vsram']
        self.vsram_n                  = arch_params_dict['vsram_n']
        self.gate_length              = arch_params_dict['gate_length']
        self.min_tran_width           = arch_params_dict['min_tran_width']
        self.min_width_tran_area      = arch_params_dict['min_width_tran_area']
        self.sram_cell_area           = arch_params_dict['sram_cell_area']
        self.trans_diffusion_length   = arch_params_dict['trans_diffusion_length']
        self.metal_stack              = arch_params_dict['metal']
        self.model_path               = arch_params_dict['model_path']
        self.model_library            = arch_params_dict['model_library']
        self.rest_length_factor       = arch_params_dict['rest_length_factor']
        self.use_tgate                = arch_params_dict['use_tgate']
        self.use_finfet               = arch_params_dict['use_finfet']
        self.gen_routing_metal_pitch  = arch_params_dict['gen_routing_metal_pitch']
        self.gen_routing_metal_layers = arch_params_dict['gen_routing_metal_layers']

        # Specs post init

        # If the user directly provides the freq of each wire type, then don't manually calculate the num_tracks
        if all(wire.get("freq") is not None for wire in self.wire_types):
            for i, wire in enumerate(self.wire_types):
                wire["num_tracks"] = wire["freq"]
                wire["id"] = i
        else:
            tracks = []
            for id, wire in enumerate(self.wire_types):
                tracks.append( int(self.W * wire["perc"]) )

            remaining_wires = self.W - sum(tracks)
            # Adjust tracks to distribute remaining wires proportionally
            while remaining_wires != 0:
                for idx, wire in enumerate(self.wire_types):
                    # Calculate the adjustment based on the remaining wires & freq of wire types
                    adjustment = round((self.W * wire["perc"] - tracks[idx]) * remaining_wires / sum(tracks))
                    # if we are reducing wires flip the sign of adjustment
                    if remaining_wires < 0:
                        adjustment = -adjustment
                    tracks[idx] += adjustment
                    remaining_wires -= adjustment
                    if remaining_wires == 0:
                        break
            # set it back in wire types
            for i, (wire, num_tracks) in enumerate(zip(self.wire_types, tracks)):
                wire["num_tracks"] = num_tracks
                wire["id"] = i

        

class _pgateoutputcrossbar(_SizableCircuit):
    """ RAM outputcrossbar using pass transistors"""
    
    def __init__(self, maxwidth):
        # Subcircuit name
        self.name = "pgateoutputcrossbar"
        self.delay_weight = DELAY_WEIGHT_RAM
        self.maxwidth = maxwidth
        self.def_use_tgate = 0
    
    def generate(self, subcircuit_filename, min_tran_width):
        print("Generating BRAM output crossbar")
        

        # Call MUX generation function
        self.transistor_names, self.wire_names = memory_subcircuits.generate_pgateoutputcrossbar(subcircuit_filename, self.name, self.maxwidth, self.def_use_tgate)

        # Initialize transistor sizes (to something more reasonable than all min size, but not necessarily a good choice, depends on architecture params)
        self.initial_transistor_sizes["inv_" + self.name + "_1_nmos"] = 3
        self.initial_transistor_sizes["inv_" + self.name + "_1_pmos"] = 3
        self.initial_transistor_sizes["inv_" + self.name + "_2_nmos"] = 6
        self.initial_transistor_sizes["inv_" + self.name + "_2_pmos"] = 9
        if self.def_use_tgate == 0:
            self.initial_transistor_sizes["inv_" + self.name + "_3_nmos"] = 20
            self.initial_transistor_sizes["inv_" + self.name + "_3_pmos"] = 56
        else:
            self.initial_transistor_sizes["tgate_" + self.name + "_3_nmos"] = 1
            self.initial_transistor_sizes["tgate_" + self.name + "_3_pmos"] = 1
        self.initial_transistor_sizes["ptran_" + self.name + "_4_nmos"] = 1


        return self.initial_transistor_sizes

    def generate_top(self):
        print("Generating top-level path for BRAM crossbar evaluation")
        self.top_spice_path = top_level.generate_pgateoutputcrossbar_top(self.name, self.maxwidth, self.def_use_tgate)


    def update_area(self, area_dict, width_dict):
        """ Update area. To do this, we use area_dict which is a dictionary, maintained externally, that contains
            the area of everything. It is expected that area_dict will have all the information we need to calculate area.
            We update area_dict and width_dict with calculations performed in this function. """        
        
        current_count = self.maxwidth
        ptran_count = self.maxwidth

        while current_count >1:
            ptran_count += current_count//2
            current_count //=2

        ptran_count *=2
        ptran_count += self.maxwidth // 2

        area = (area_dict["inv_" + self.name + "_1"] + area_dict["inv_" + self.name + "_2"] + area_dict["inv_" + self.name + "_3"] * 2) * self.maxwidth + area_dict["ptran_" + self.name + "_4"]  * ptran_count
        #I'll use half of the area to obtain the width. This makes the process of defining wires easier for this crossbar
        width = math.sqrt(area)
        area *= 2
        area_with_sram = area + 2 * (self.maxwidth*2-1) * area_dict["sram"]
        width_with_sram = math.sqrt(area_with_sram)
        area_dict[self.name] = area
        width_dict[self.name] = width
        area_dict[self.name + "_sram"] = area_with_sram
        width_dict[self.name + "_sram"] = width_with_sram


    def update_wires(self, width_dict, wire_lengths, wire_layers):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """
        # Update wire lengths
        # We assume that the length of wire is the square root of output crossbar size
        # Another reasonable assumption is to assume it is equal to ram height or width
        # The latter, however, will result in very high delays for the output crossbar
        wire_lengths["wire_" + self.name] = width_dict[self.name + "_sram"]
        wire_layers["wire_" + self.name] = 0  


class _configurabledecoderiii(_SizableCircuit):
    """ Final stage of the configurable decoder"""
    
    def __init__(self, use_tgate, nand_size, fanin1, fanin2, tgatecount):
        # Subcircuit name
        self.name = "xconfigurabledecoderiii"
        self.required_size = nand_size
        self.use_tgate = use_tgate
        self.fanin1 = fanin1
        self.fanin2 = fanin2
        self.delay_weight = DELAY_WEIGHT_RAM
        self.tgatecount = tgatecount
    
    
    def generate(self, subcircuit_filename, min_tran_width):
        print("Generating stage of the configurable decoder " + self.name)
        

        # Call generation function
        if use_lp_transistor == 0:
            self.transistor_names, self.wire_names = memory_subcircuits.generate_configurabledecoderiii(subcircuit_filename, self.name, self.required_size)
        else:
            self.transistor_names, self.wire_names = memory_subcircuits.generate_configurabledecoderiii_lp(subcircuit_filename, self.name, self.required_size)

            #print(self.transistor_names)
        # Initialize transistor sizes (to something more reasonable than all min size, but not necessarily a good choice, depends on architecture params)
        self.initial_transistor_sizes["inv_nand"+str(self.required_size)+"_" + self.name + "_1_nmos"] = 1
        self.initial_transistor_sizes["inv_nand"+str(self.required_size)+"_" + self.name + "_1_pmos"] = 1
        self.initial_transistor_sizes["inv_" + self.name + "_2_nmos"] = 5
        self.initial_transistor_sizes["inv_" + self.name + "_2_pmos"] = 5
       # there is a wire in this cell, make sure to set its area to entire decoder

        return self.initial_transistor_sizes

    def generate_top(self):
        print("Generating top-level evaluation path for final stage of the configurable decoder")
        if use_lp_transistor == 0:
            self.top_spice_path = top_level.generate_configurabledecoderiii_top(self.name, self.fanin1,self.fanin2, self.required_size, self.tgatecount)
        else:
            self.top_spice_path = top_level.generate_configurabledecoderiii_top_lp(self.name, self.fanin1,self.fanin2, self.required_size, self.tgatecount)

        
        

    def update_area(self, area_dict, width_dict):
        """ Update area. To do this, we use area_dict which is a dictionary, maintained externally, that contains
            the area of everything. It is expected that area_dict will have all the information we need to calculate area.
            We update area_dict and width_dict with calculations performed in this function. """        
        
        # predecoder area
        area = area_dict["inv_nand"+str(self.required_size)+"_" + self.name + "_1"]*self.required_size + area_dict["inv_" + self.name + "_2"]
        area_with_sram = area
          
        width = math.sqrt(area)
        width_with_sram = math.sqrt(area_with_sram)
        area_dict[self.name] = area
        width_dict[self.name] = width
        area_dict[self.name + "_sram"] = area_with_sram
        width_dict[self.name + "_sram"] = width_with_sram


    
    def update_wires(self, width_dict, wire_lengths, wire_layers):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """

        # Update wire lengths
        wire_lengths["wire_" + self.name] = width_dict[self.name]
        wire_layers["wire_" + self.name] = 0


class _configurabledecoder3ii(_SizableCircuit):
    """ Second part of the configurable decoder"""
    
    def __init__(self, use_tgate, required_size, fan_out, fan_out_type, areafac):
        # Subcircuit name
        self.name = "xconfigurabledecoder3ii"
        self.required_size = required_size
        self.fan_out = fan_out
        self.fan_out_type = fan_out_type
        self.use_tgate = use_tgate
        self.areafac = areafac
    
    
    def generate(self, subcircuit_filename, min_tran_width):
        print("Generating second part of the configurable decoder" + self.name)
        

        # Call generation function
        if use_lp_transistor == 0:
            self.transistor_names, self.wire_names = memory_subcircuits.generate_configurabledecoder3ii(subcircuit_filename, self.name)
        else:
            self.transistor_names, self.wire_names = memory_subcircuits.generate_configurabledecoder3ii_lp(subcircuit_filename, self.name)
        # Initialize transistor sizes (to something more reasonable than all min size, but not necessarily a good choice, depends on architecture params)
        self.initial_transistor_sizes["inv_nand3_" + self.name + "_1_nmos"] = 1
        self.initial_transistor_sizes["inv_nand3_" + self.name + "_1_pmos"] = 1
        self.initial_transistor_sizes["inv_" + self.name + "_2_nmos"] = 1
        self.initial_transistor_sizes["inv_" + self.name + "_2_pmos"] = 1


        return self.initial_transistor_sizes

    def generate_top(self):
        print("Generating top-level evalation path for second part of the configurable decoder")
        if use_lp_transistor == 0:
            self.top_spice_path = top_level.generate_configurabledecoder2ii_top(self.name, self.fan_out, 3)
        else:
            self.top_spice_path = top_level.generate_configurabledecoder2ii_top_lp(self.name, self.fan_out, 3)
   
    def update_area(self, area_dict, width_dict):
        """ Update area. To do this, we use area_dict which is a dictionary, maintained externally, that contains
            the area of everything. It is expected that area_dict will have all the information we need to calculate area.
            We update area_dict and width_dict with calculations performed in this function. """        
        
        # predecoder area
        area = (area_dict["inv_nand3_" + self.name + "_1"]*3 + area_dict["inv_" + self.name + "_2"])*self.areafac
        area_with_sram = area
          
        width = math.sqrt(area)
        width_with_sram = math.sqrt(area_with_sram)
        area_dict[self.name] = area
        width_dict[self.name] = width
        area_dict[self.name + "_sram"] = area_with_sram
        width_dict[self.name + "_sram"] = width_with_sram




class _configurabledecoder2ii(_SizableCircuit):
    """ second part of the configurable decoder"""
    
    def __init__(self, use_tgate, required_size, fan_out, fan_out_type, areafac):
        # Subcircuit name
        self.name = "xconfigurabledecoder2ii"
        self.required_size = required_size
        self.fan_out = fan_out
        self.fan_out_type = fan_out_type
        self.use_tgate = use_tgate
        self.areafac = areafac
    
    
    def generate(self, subcircuit_filename, min_tran_width):
        print("Generating the second part of the configurable decoder" + self.name)
        

        # Call generation function
        if use_lp_transistor == 0:
            self.transistor_names, self.wire_names = memory_subcircuits.generate_configurabledecoder2ii(subcircuit_filename, self.name)
        else:
            self.transistor_names, self.wire_names = memory_subcircuits.generate_configurabledecoder2ii_lp(subcircuit_filename, self.name)

            #print(self.transistor_names)
        # Initialize transistor sizes (to something more reasonable than all min size, but not necessarily a good choice, depends on architecture params)
        self.initial_transistor_sizes["inv_nand2_" + self.name + "_1_nmos"] = 1
        self.initial_transistor_sizes["inv_nand2_" + self.name + "_1_pmos"] = 1
        self.initial_transistor_sizes["inv_" + self.name + "_2_nmos"] = 1
        self.initial_transistor_sizes["inv_" + self.name + "_2_pmos"] = 1

       # there is a wire in this cell, make sure to set its area to entire decoder

        return self.initial_transistor_sizes

    def generate_top(self):
        print("Generating top-level evaluation path for second part of the configurable decoder")
        if use_lp_transistor == 0:
            self.top_spice_path = top_level.generate_configurabledecoder2ii_top(self.name, self.fan_out, 2)
        else:
            self.top_spice_path = top_level.generate_configurabledecoder2ii_top_lp(self.name, self.fan_out, 2)
        
   
    def update_area(self, area_dict, width_dict):
        """ Update area. To do this, we use area_dict which is a dictionary, maintained externally, that contains
            the area of everything. It is expected that area_dict will have all the information we need to calculate area.
            We update area_dict and width_dict with calculations performed in this function. """        
        
        # predecoder area
        area = (area_dict["inv_nand2_" + self.name + "_1"]*2 + area_dict["inv_" + self.name + "_2"])*self.areafac
        area_with_sram = area
          
        width = math.sqrt(area)
        width_with_sram = math.sqrt(area_with_sram)
        area_dict[self.name] = area
        width_dict[self.name] = width
        area_dict[self.name + "_sram"] = area_with_sram
        width_dict[self.name + "_sram"] = width_with_sram




class _configurabledecoderinvmux(_SizableCircuit):
    """ First stage of the configurable decoder"""
    # I assume that the configurable decoder has 2 stages. Hence it has between 4 bits and 9.
    # I don't think anyone would want to exceed that range!
    def __init__(self, use_tgate, numberofgates2,numberofgates3, ConfiDecodersize):
        self.name = "xconfigurabledecoderi"
        self.use_tgate = use_tgate
        self.ConfiDecodersize = ConfiDecodersize
        self.numberofgates2 = numberofgates2
        self.numberofgates3 = numberofgates3


    def generate(self, subcircuit_filename, min_tran_width):
        print("Generating first stage of the configurable decoder") 
        if use_lp_transistor == 0:
            self.transistor_names, self.wire_names = memory_subcircuits.generate_configurabledecoderi(subcircuit_filename, self.name)
        else:
            self.transistor_names, self.wire_names = memory_subcircuits.generate_configurabledecoderi_lp(subcircuit_filename, self.name)
        self.initial_transistor_sizes["inv_xconfigurabledecoderi_1_nmos"] = 1 
        self.initial_transistor_sizes["inv_xconfigurabledecoderi_1_pmos"] = 1
        self.initial_transistor_sizes["tgate_xconfigurabledecoderi_2_nmos"] = 1 
        self.initial_transistor_sizes["tgate_xconfigurabledecoderi_2_pmos"] = 1
     
        return self.initial_transistor_sizes

    def generate_top(self):
        print("Generating top-level evaluation path for the stage of the configurable decoder") 
        if use_lp_transistor == 0:
            self.top_spice_path = top_level.generate_configurabledecoderi_top(self.name,  self.numberofgates2, self.numberofgates3, self.ConfiDecodersize)
        else:
            self.top_spice_path = top_level.generate_configurabledecoderi_top_lp(self.name,  self.numberofgates2, self.numberofgates3, self.ConfiDecodersize)
    def update_area(self, area_dict, width_dict):
        """ Update area. To do this, we use area_dict which is a dictionary, maintained externally, that contains
            the area of everything. It is expected that area_dict will have all the information we need to calculate area.
            We update area_dict and width_dict with calculations performed in this function. """     

        area = (area_dict["inv_xconfigurabledecoderi_1"] * self.ConfiDecodersize + 2* area_dict["tgate_xconfigurabledecoderi_2"])* self.ConfiDecodersize
        area_with_sram = area + self.ConfiDecodersize * area_dict["sram"] 

        width = math.sqrt(area)
        width_with_sram = math.sqrt(area_with_sram)
        area_dict[self.name] = area
        width_dict[self.name] = width
        area_dict[self.name + "_sram"] = area_with_sram
        width_dict[self.name + "_sram"] = width_with_sram

    def update_wires(self, width_dict, wire_lengths, wire_layers):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """
        
        wire_lengths["wire_" + self.name] = width_dict["configurabledecoder_wodriver"]
        wire_layers["wire_" + self.name] = 0

class _rowdecoder0(_SizableCircuit):
    """ Initial stage of the row decoder ( named stage 0) """
    def __init__(self, use_tgate, numberofgates3, valid_label_gates3, numberofgates2, valid_label_gates2, decodersize):
        self.name = "rowdecoderstage0"
        self.use_tgate = use_tgate
        self.decodersize = decodersize
        self.numberofgates2 = numberofgates2
        self.numberofgates3 = numberofgates3
        self.label3 = valid_label_gates3
        self.label2 = valid_label_gates2


    def generate(self, subcircuit_filename, min_tran_width):
        print("Generating row decoder initial stage") 
        if use_lp_transistor == 0:
            self.transistor_names, self.wire_names = memory_subcircuits.generate_rowdecoderstage0(subcircuit_filename, self.name)
        else:
            self.transistor_names, self.wire_names = memory_subcircuits.generate_rowdecoderstage0_lp(subcircuit_filename, self.name)
        self.initial_transistor_sizes["inv_rowdecoderstage0_1_nmos"] = 9
        self.initial_transistor_sizes["inv_rowdecoderstage0_1_pmos"] = 9
     
        return self.initial_transistor_sizes

    def generate_top(self):
        print("Generating row decoder initial stage") 
        if use_lp_transistor == 0:
            self.top_spice_path = top_level.generate_rowdecoderstage0_top(self.name, self.numberofgates2, self.numberofgates3, self.decodersize, self.label2, self.label3)
        else:
            self.top_spice_path = top_level.generate_rowdecoderstage0_top_lp(self.name, self.numberofgates2, self.numberofgates3, self.decodersize, self.label2, self.label3)
    def update_area(self, area_dict, width_dict):
        """ Update area. To do this, we use area_dict which is a dictionary, maintained externally, that contains
            the area of everything. It is expected that area_dict will have all the information we need to calculate area.
            We update area_dict and width_dict with calculations performed in this function. """     

        area = area_dict["inv_rowdecoderstage0_1"] * self.decodersize
        area_with_sram = area
        width = math.sqrt(area)
        width_with_sram = math.sqrt(area_with_sram)
        area_dict[self.name] = area
        width_dict[self.name] = width
        area_dict[self.name + "_sram"] = area_with_sram
        width_dict[self.name + "_sram"] = width_with_sram

    def update_wires(self, width_dict, wire_lengths, wire_layers):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """
        
        # I assume that the wire in the row decoder is the sqrt of the area of the row decoder, including the wordline driver
        wire_lengths["wire_" + self.name] = math.sqrt(width_dict["decoder"]*width_dict["decoder"] + width_dict["wordline_total"]*width_dict["wordline_total"])
        wire_layers["wire_" + self.name] = 0



class _rowdecoder1(_SizableCircuit):
    """ Generating the first stage of the row decoder  """
    def __init__(self, use_tgate, fan_out, fan_out_type, nandtype, areafac):
        self.name = "rowdecoderstage1" + str(nandtype)
        self.use_tgate = use_tgate
        self.fanout = fan_out
        self.fanout_type = fan_out_type
        self.nandtype = nandtype
        self.areafac = areafac


    def generate(self, subcircuit_filename, min_tran_width):
        print("Generating row decoder first stage") 

        if use_lp_transistor == 0:
            self.transistor_names, self.wire_names = memory_subcircuits.generate_rowdecoderstage1(subcircuit_filename, self.name, self.nandtype)
        else:
            self.transistor_names, self.wire_names = memory_subcircuits.generate_rowdecoderstage1_lp(subcircuit_filename, self.name, self.nandtype)

        self.initial_transistor_sizes["inv_nand" + str(self.nandtype) + "_" + self.name + "_1_nmos"] = 1
        self.initial_transistor_sizes["inv_nand" + str(self.nandtype) + "_" + self.name + "_1_pmos"] = 1
        self.initial_transistor_sizes["inv_" + self.name + "_2_nmos"] = 1
        self.initial_transistor_sizes["inv_" + self.name + "_2_pmos"] = 1

     
        return self.initial_transistor_sizes

    def generate_top(self):
        print("Generating top-level evaluation path for row decoder first stage") 
        pass
        if use_lp_transistor == 0:
            self.top_spice_path = top_level.generate_rowdecoderstage1_top(self.name, self.fanout, self.nandtype)
        else:
            self.top_spice_path = top_level.generate_rowdecoderstage1_top_lp(self.name, self.fanout, self.nandtype)
    def update_area(self, area_dict, width_dict):
        """ Update area. To do this, we use area_dict which is a dictionary, maintained externally, that contains
            the area of everything. It is expected that area_dict will have all the information we need to calculate area.
            We update area_dict and width_dict with calculations performed in this function. """ 

        area = (area_dict["inv_nand" + str(self.nandtype) + "_" + self.name + "_1"] + area_dict["inv_" + self.name + "_2"]) * self.areafac
        area_with_sram = area
        width = math.sqrt(area)
        width_with_sram = math.sqrt(area_with_sram)
        area_dict[self.name] = area
        width_dict[self.name] = width
        area_dict[self.name + "_sram"] = area_with_sram
        width_dict[self.name + "_sram"] = width_with_sram




class _wordlinedriver(_SizableCircuit):
    """ Wordline driver"""
    
    def __init__(self, use_tgate, rowsram, number_of_banks, areafac, is_rowdecoder_2stage, memory_technology):
        # Subcircuit name
        self.name = "wordline_driver"
        self.delay_weight = DELAY_WEIGHT_RAM
        self.rowsram = rowsram
        self.memory_technology = memory_technology
        self.number_of_banks = number_of_banks
        self.areafac = areafac
        self.is_rowdecoder_2stage = is_rowdecoder_2stage
        self.wl_repeater = 0
        if self.rowsram > 128:
            self.rowsram //= 2
            self.wl_repeater = 1
    
    def generate(self, subcircuit_filename, min_tran_width):
        print("Generating the wordline driver" + self.name)

        # Call generation function
        if use_lp_transistor == 0:
            self.transistor_names, self.wire_names = memory_subcircuits.generate_wordline_driver(subcircuit_filename, self.name, self.number_of_banks + 1, self.wl_repeater)
        else:
            self.transistor_names, self.wire_names = memory_subcircuits.generate_wordline_driver_lp(subcircuit_filename, self.name, self.number_of_banks + 1, self.wl_repeater)

            #print(self.transistor_names)
        # Initialize transistor sizes (to something more reasonable than all min size, but not necessarily a good choice, depends on architecture params)

        if self.number_of_banks == 1:
            self.initial_transistor_sizes["inv_nand2_" + self.name + "_1_nmos"] = 1
            self.initial_transistor_sizes["inv_nand2_" + self.name + "_1_pmos"] = 1
            self.initial_transistor_sizes["inv_" + self.name + "_2_nmos"] = 1
            self.initial_transistor_sizes["inv_" + self.name + "_2_pmos"] = 1
        else:
            self.initial_transistor_sizes["inv_nand3_" + self.name + "_1_nmos"] = 1 
            self.initial_transistor_sizes["inv_nand3_" + self.name + "_1_pmos"] = 1
            self.initial_transistor_sizes["inv_" + self.name + "_2_nmos"] = 1
            self.initial_transistor_sizes["inv_" + self.name + "_2_pmos"] = 1        

        self.initial_transistor_sizes["inv_" + self.name + "_3_nmos"] = 1
        self.initial_transistor_sizes["inv_" + self.name + "_3_pmos"] = 1
        self.initial_transistor_sizes["inv_" + self.name + "_4_nmos"] = 5
        self.initial_transistor_sizes["inv_" + self.name + "_4_pmos"] = 5
       # there is a wire in this cell, make sure to set its area to entire decoder

        return self.initial_transistor_sizes

    def generate_top(self):
        print("Generating top-level evaluation path for the wordline driver")
        pass 
        if use_lp_transistor == 0:
            self.top_spice_path = top_level.generate_wordline_driver_top(self.name, self.rowsram, self.number_of_banks + 1, self.is_rowdecoder_2stage, self.wl_repeater)
        else:
            self.top_spice_path = top_level.generate_wordline_driver_top_lp(self.name, self.rowsram, self.number_of_banks + 1, self.is_rowdecoder_2stage, self.wl_repeater)

    def update_area(self, area_dict, width_dict):
        """ Update area. To do this, we use area_dict which is a dictionary, maintained externally, that contains
            the area of everything. It is expected that area_dict will have all the information we need to calculate area.
            We update area_dict and width_dict with calculations performed in this function. """        
        
        # predecoder area
        #nand should be different than inv change later 
        area = area_dict["inv_" + self.name + "_3"] + area_dict["inv_" + self.name + "_4"]
        if self.wl_repeater == 1:
            area *=2
        if self.number_of_banks == 1:
            area+= area_dict["inv_nand2_" + self.name + "_1"]*2 + area_dict["inv_" + self.name + "_2"]
        else:
            area+= area_dict["inv_nand3_" + self.name + "_1"]*3 + area_dict["inv_" + self.name + "_2"]
        area = area * self.areafac

        area_with_sram = area
        width = math.sqrt(area)
        width_with_sram = math.sqrt(area_with_sram)
        area_dict[self.name] = area
        width_dict[self.name] = width
        area_dict[self.name + "_sram"] = area_with_sram
        width_dict[self.name + "_sram"] = width_with_sram

    def update_wires(self, width_dict, wire_lengths, wire_layers):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """
        
        # Update wire lengths
        wire_lengths["wire_" + self.name] = wire_lengths["wire_memorycell_horizontal"]

        if self.memory_technology == "SRAM":
            wire_layers["wire_" + self.name] = 2
        else:
            wire_layers["wire_" + self.name] = 3



class _rowdecoderstage3(_SizableCircuit):
    """ third stage inside the row decoder"""
    
    def __init__(self, use_tgate, fanin1, fanin2, rowsram, gatesize, fanouttype, areafac):
        # Subcircuit name
        self.name = "rowdecoderstage3"
        self.fanin1 = fanin1
        self.fanin2 = fanin2
        self.fanout = fanouttype
        self.delay_weight = DELAY_WEIGHT_RAM
        self.rowsram = rowsram
        self.gatesize = gatesize
        self.areafac = areafac
    
    
    def generate(self, subcircuit_filename, min_tran_width):
        print("Generating last stage of the row decoder" + self.name)

        # Call generation function
        if use_lp_transistor == 0:
            self.transistor_names, self.wire_names = memory_subcircuits.generate_rowdecoderstage3(subcircuit_filename, self.name, self.fanout, self.gatesize - 1)
        else:
            self.transistor_names, self.wire_names = memory_subcircuits.generate_rowdecoderstage3(subcircuit_filename, self.name, self.fanout, self.gatesize - 1)
        # Initialize transistor sizes (to something more reasonable than all min size, but not necessarily a good choice, depends on architecture params)
        self.initial_transistor_sizes["inv_nand" + str(self.fanout) + "_" + self.name + "_1_nmos"] = 1
        self.initial_transistor_sizes["inv_nand" + str(self.fanout) + "_" + self.name + "_1_pmos"] = 1
        self.initial_transistor_sizes["inv_" + self.name + "_2_nmos"] = 1
        self.initial_transistor_sizes["inv_" + self.name + "_2_pmos"] = 1
        if self.gatesize == 3:
            self.initial_transistor_sizes["inv_nand2_" + self.name + "_3_nmos"] = 1
            self.initial_transistor_sizes["inv_nand2_" + self.name + "_3_pmos"] = 1
            self.initial_transistor_sizes["inv_" + self.name + "_4_nmos"] = 1
            self.initial_transistor_sizes["inv_" + self.name + "_4_pmos"] = 1
        else:
            self.initial_transistor_sizes["inv_nand3_" + self.name + "_3_nmos"] = 1 
            self.initial_transistor_sizes["inv_nand3_" + self.name + "_3_pmos"] = 1
            self.initial_transistor_sizes["inv_" + self.name + "_4_nmos"] = 1
            self.initial_transistor_sizes["inv_" + self.name + "_4_pmos"] = 1        

        self.initial_transistor_sizes["inv_" + self.name + "_5_nmos"] = 1
        self.initial_transistor_sizes["inv_" + self.name + "_5_pmos"] = 1
        self.initial_transistor_sizes["inv_" + self.name + "_6_nmos"] = 5
        self.initial_transistor_sizes["inv_" + self.name + "_6_pmos"] = 5


        return self.initial_transistor_sizes

    def generate_top(self):
        print("Generating top-level evaluation path for last stage of row decoder")
        pass 
        if use_lp_transistor == 0:
            self.top_spice_path = top_level.generate_rowdecoderstage3_top(self.name, self.fanin1, self.fanin2, self.rowsram, self.gatesize - 1, self.fanout)
        else:
            self.top_spice_path = top_level.generate_rowdecoderstage3_top_lp(self.name, self.fanin1, self.fanin2, self.rowsram, self.gatesize - 1, self.fanout)

    def update_area(self, area_dict, width_dict):
        """ Update area. To do this, we use area_dict which is a dictionary, maintained externally, that contains
            the area of everything. It is expected that area_dict will have all the information we need to calculate area.
            We update area_dict and width_dict with calculations performed in this function. """        
        
        area = (area_dict["inv_nand" + str(self.fanout) + "_" + self.name + "_1"] + area_dict["inv_" + self.name + "_2"] + area_dict["inv_" + self.name + "_5"] + area_dict["inv_" + self.name + "_6"])
        if self.gatesize == 3:
            area+= area_dict["inv_nand2_" + self.name + "_3"]*2 + area_dict["inv_" + self.name + "_4"]
        else:
            area+= area_dict["inv_nand3_" + self.name + "_3"]*3 + area_dict["inv_" + self.name + "_4"]

        area = area * self.areafac
        area_with_sram = area
          
        width = math.sqrt(area)
        width_with_sram = math.sqrt(area_with_sram)
        area_dict[self.name] = area
        width_dict[self.name] = width
        area_dict[self.name + "_sram"] = area_with_sram
        width_dict[self.name + "_sram"] = width_with_sram


class _powermtjread(_SizableCircuit):
    """ This class measures MTJ-based memory read power """
    def __init__(self, SRAM_per_column):

        self.name = "mtj_read_power"
        self.SRAM_per_column = SRAM_per_column
    def generate_top(self):
        print("Generating top level module to measure MTJ read power")
        if use_lp_transistor == 0:
            self.top_spice_path = top_level.generate_mtj_read_power_top(self.name, self.SRAM_per_column)
        else:
            self.top_spice_path = top_level.generate_mtj_read_power_top_lp(self.name, self.SRAM_per_column)


class _powermtjwrite(_SizableCircuit):
    """ This class measures MTJ-based memory write power """
    def __init__(self, SRAM_per_column):

        self.name = "mtj_write_power"
        self.SRAM_per_column = SRAM_per_column
    def generate_top(self):
        print("Generating top level module to measure MTJ write power")
        if use_lp_transistor == 0:
            self.top_spice_path = top_level.generate_mtj_write_power_top(self.name, self.SRAM_per_column)
        else:
            self.top_spice_path = top_level.generate_mtj_write_power_top_lp(self.name, self.SRAM_per_column)


class _powersramwritehh(_SizableCircuit):
    """ This class measures SRAM-based memory write power """
    def __init__(self, SRAM_per_column, column_multiplexity):

        self.name = "sram_writehh_power"
        self.SRAM_per_column = SRAM_per_column
        self.column_multiplexity = column_multiplexity

    def generate_top(self):
        print("Generating top level module to measure SRAM write power")
        if use_lp_transistor == 0:
            self.top_spice_path = top_level.generate_sram_writehh_power_top(self.name, self.SRAM_per_column, self.column_multiplexity - 1)
        else:
            self.top_spice_path = top_level.generate_sram_writehh_power_top_lp(self.name, self.SRAM_per_column, self.column_multiplexity - 1)


class _powersramwritep(_SizableCircuit):
    """ This class measures SRAM-based memory write power """
    def __init__(self, SRAM_per_column, column_multiplexity):

        self.name = "sram_writep_power"
        self.SRAM_per_column = SRAM_per_column
        self.column_multiplexity = column_multiplexity

    def generate_top(self):
        print("Generating top level module to measure SRAM write power")
        if use_lp_transistor == 0:
            self.top_spice_path = top_level.generate_sram_writep_power_top(self.name, self.SRAM_per_column, self.column_multiplexity - 1)
        else:
            self.top_spice_path = top_level.generate_sram_writep_power_top_lp(self.name, self.SRAM_per_column, self.column_multiplexity - 1)


class _powersramwritelh(_SizableCircuit):
    """ This class measures SRAM-based memory write power """
    def __init__(self, SRAM_per_column, column_multiplexity):

        self.name = "sram_writelh_power"
        self.SRAM_per_column = SRAM_per_column
        self.column_multiplexity = column_multiplexity

    def generate_top(self):
        print("Generating top level module to measure SRAM write power")
        if use_lp_transistor == 0:
            self.top_spice_path = top_level.generate_sram_writelh_power_top(self.name, self.SRAM_per_column, self.column_multiplexity - 1)
        else:
            self.top_spice_path = top_level.generate_sram_writelh_power_top_lp(self.name, self.SRAM_per_column, self.column_multiplexity - 1)


class _powersramread(_SizableCircuit):
    """ This class measures SRAM-based memory read power """
    def __init__(self, SRAM_per_column, column_multiplexity):

        self.name = "sram_read_power"
        self.SRAM_per_column = SRAM_per_column
        self.column_multiplexity = column_multiplexity

    def generate_top(self):
        print("Generating top level module to measure SRAM read power")
        if use_lp_transistor == 0:
            self.top_spice_path = top_level.generate_sram_read_power_top(self.name, self.SRAM_per_column, self.column_multiplexity - 1)
        else:
            self.top_spice_path = top_level.generate_sram_read_power_top_lp(self.name, self.SRAM_per_column, self.column_multiplexity - 1)

class _columndecoder(_SizableCircuit):
    """ Column decoder"""

    def __init__(self, use_tgate, numberoftgates, col_decoder_bitssize):
        self.name = "columndecoder"
        self.use_tgate = use_tgate
        self.col_decoder_bitssize = col_decoder_bitssize
        self.numberoftgates = numberoftgates


    def generate(self, subcircuit_filename, min_tran_width):
        print("Generating column decoder ") 
        if use_lp_transistor == 0:
            self.transistor_names, self.wire_names = memory_subcircuits.generate_columndecoder(subcircuit_filename, self.name, self.col_decoder_bitssize)
        else:
            self.transistor_names, self.wire_names = memory_subcircuits.generate_columndecoder_lp(subcircuit_filename, self.name, self.col_decoder_bitssize)
        self.initial_transistor_sizes["inv_columndecoder_1_nmos"] = 1 
        self.initial_transistor_sizes["inv_columndecoder_1_pmos"] = 1
        self.initial_transistor_sizes["inv_columndecoder_2_nmos"] = 1 
        self.initial_transistor_sizes["inv_columndecoder_2_pmos"] = 1
        self.initial_transistor_sizes["inv_columndecoder_3_nmos"] = 2 
        self.initial_transistor_sizes["inv_columndecoder_3_pmos"] = 2

        return self.initial_transistor_sizes

    def generate_top(self):
        print("Generating top-level evaluation path for column decoder")
        if use_lp_transistor == 0:
            self.top_spice_path = top_level.generate_columndecoder_top(self.name,  self.numberoftgates, self.col_decoder_bitssize)
        else:
            self.top_spice_path = top_level.generate_columndecoder_top_lp(self.name,  self.numberoftgates, self.col_decoder_bitssize)

    def update_area(self, area_dict, width_dict):
        """ Update area. To do this, we use area_dict which is a dictionary, maintained externally, that contains
            the area of everything. It is expected that area_dict will have all the information we need to calculate area.
            We update area_dict and width_dict with calculations performed in this function. """     

        area = area_dict["inv_columndecoder_1"] * self.col_decoder_bitssize +area_dict["inv_columndecoder_2"]*self.col_decoder_bitssize * 2**self.col_decoder_bitssize + area_dict["inv_columndecoder_3"] * 2**self.col_decoder_bitssize
        area_with_sram = area
        width = math.sqrt(area)
        width_with_sram = math.sqrt(area_with_sram)
        area_dict[self.name] = area
        width_dict[self.name] = width
        area_dict[self.name + "_sram"] = area_with_sram
        width_dict[self.name + "_sram"] = width_with_sram

    def update_wires(self, width_dict, wire_lengths, wire_layers):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """
        pass


class _writedriver(_SizableCircuit):
    """ SRAM-based BRAM Write driver"""

    def __init__(self, use_tgate, numberofsramsincol):
        self.name = "writedriver"
        self.use_tgate = use_tgate
        self.numberofsramsincol = numberofsramsincol


    def generate(self, subcircuit_filename, min_tran_width):
        print("Generating write driver") 
        if use_lp_transistor == 0:
            self.transistor_names, self.wire_names = memory_subcircuits.generate_writedriver(subcircuit_filename, self.name)
        else:
            self.transistor_names, self.wire_names = memory_subcircuits.generate_writedriver_lp(subcircuit_filename, self.name)

        # Sizing according to Kosuke
        self.initial_transistor_sizes["inv_writedriver_1_nmos"] = 1.222 
        self.initial_transistor_sizes["inv_writedriver_1_pmos"] = 2.444
        self.initial_transistor_sizes["inv_writedriver_2_nmos"] = 1.222
        self.initial_transistor_sizes["inv_writedriver_2_pmos"] = 2.444
        self.initial_transistor_sizes["tgate_writedriver_3_nmos"] = 5.555
        self.initial_transistor_sizes["tgate_writedriver_3_pmos"] = 3.333
        

        return self.initial_transistor_sizes

    def generate_top(self):
        print("Generating top-level evaluation for write driver")
        if use_lp_transistor == 0:
            self.top_spice_path = top_level.generate_writedriver_top(self.name, self.numberofsramsincol)
        else:
            self.top_spice_path = top_level.generate_writedriver_top_lp(self.name, self.numberofsramsincol)

    def update_area(self, area_dict, width_dict):
        """ Update area. To do this, we use area_dict which is a dictionary, maintained externally, that contains
            the area of everything. It is expected that area_dict will have all the information we need to calculate area.
            We update area_dict and width_dict with calculations performed in this function. """     

        area = area_dict["inv_writedriver_1"] + area_dict["inv_writedriver_2"] + area_dict["tgate_writedriver_3"]* 4
        area_with_sram = area
        width = math.sqrt(area)
        width_with_sram = math.sqrt(area_with_sram)
        area_dict[self.name] = area
        width_dict[self.name] = width
        area_dict[self.name + "_sram"] = area_with_sram
        width_dict[self.name + "_sram"] = width_with_sram


class _samp(_SizableCircuit):
    """ sense amplifier circuit"""

    def __init__(self, use_tgate, numberofsramsincol, mode, difference):
        self.name = "samp1"
        self.use_tgate = use_tgate
        self.numberofsramsincol = numberofsramsincol
        self.mode = mode
        self.difference = difference

    def generate(self, subcircuit_filename, min_tran_width):
        print("Generating sense amplifier circuit") 
        if use_lp_transistor == 0:
            self.transistor_names, self.wire_names = memory_subcircuits.generate_samp(subcircuit_filename, self.name)
        else:
            self.transistor_names, self.wire_names = memory_subcircuits.generate_samp_lp(subcircuit_filename, self.name)
        self.initial_transistor_sizes["inv_samp_output_1_nmos"] = 1 
        self.initial_transistor_sizes["inv_samp_output_1_pmos"] = 1
        #its not actually a PTRAN. Doing this only for area calculation:
        self.initial_transistor_sizes["ptran_samp_output_1_pmos"] = 5.555
        self.initial_transistor_sizes["ptran_samp_output_2_nmos"] = 2.222
        self.initial_transistor_sizes["ptran_samp_output_3_nmos"] = 20.0
        self.initial_transistor_sizes["ptran_samp_output_4_nmos"] = 5.555
        return self.initial_transistor_sizes

    def generate_top(self):
        print("Generating sense amplifier circuit")
        if use_lp_transistor == 0:
            self.top_spice_path = top_level.generate_samp_top_part1(self.name, self.numberofsramsincol, self.difference)
        else:
            self.top_spice_path = top_level.generate_samp_top_part1_lp(self.name, self.numberofsramsincol, self.difference)
    def update_area(self, area_dict, width_dict):
        """ Update area. To do this, we use area_dict which is a dictionary, maintained externally, that contains
            the area of everything. It is expected that area_dict will have all the information we need to calculate area.
            We update area_dict and width_dict with calculations performed in this function. """     

        area = area_dict["inv_samp_output_1"] + area_dict["ptran_samp_output_1"]*2 +  area_dict["ptran_samp_output_2"]*2 + area_dict["ptran_samp_output_3"]*2 +  area_dict["ptran_samp_output_1"]
        area_with_sram = area
        width = math.sqrt(area)
        width_with_sram = math.sqrt(area_with_sram)
        area_dict[self.name] = area
        width_dict[self.name] = width
        area_dict[self.name + "_sram"] = area_with_sram
        width_dict[self.name + "_sram"] = width_with_sram



class _samp_part2(_SizableCircuit):
    """ sense amplifier circuit (second evaluation stage)"""

    def __init__(self, use_tgate, numberofsramsincol, difference):
        self.name = "samp1part2"
        self.use_tgate = use_tgate
        self.numberofsramsincol = numberofsramsincol
        self.difference = difference


    def generate_top(self):
        print("Generating top-level evaluation path for the second stage of sense amplifier")
        if use_lp_transistor == 0:
            self.top_spice_path = top_level.generate_samp_top_part2(self.name, self.numberofsramsincol, self.difference)
        else:
            self.top_spice_path = top_level.generate_samp_top_part2_lp(self.name, self.numberofsramsincol, self.difference)



class _prechargeandeq(_SizableCircuit):
    """ precharge and equalization circuit"""

    def __init__(self, use_tgate, numberofsrams):
        self.name = "precharge"
        self.use_tgate = use_tgate
        self.numberofsrams = numberofsrams


    def generate(self, subcircuit_filename, min_tran_width):
        print("Generating precharge and equalization circuit") 
        if use_lp_transistor == 0:
            self.transistor_names, self.wire_names = memory_subcircuits.generate_precharge(subcircuit_filename, self.name)
        else:
            self.transistor_names, self.wire_names = memory_subcircuits.generate_precharge_lp(subcircuit_filename, self.name)

        self.initial_transistor_sizes["ptran_precharge_side_nmos"] = 15
        self.initial_transistor_sizes["ptran_equalization_nmos"] = 1

        return self.initial_transistor_sizes

    def generate_top(self):
        print("Generating precharge and equalization circuit")
        if use_lp_transistor == 0:
            self.top_spice_path = top_level.generate_precharge_top(self.name, self.numberofsrams)
        else:
            self.top_spice_path = top_level.generate_precharge_top_lp(self.name, self.numberofsrams)
    def update_area(self, area_dict, width_dict):
        """ Update area. To do this, we use area_dict which is a dictionary, maintained externally, that contains
            the area of everything. It is expected that area_dict will have all the information we need to calculate area.
            We update area_dict and width_dict with calculations performed in this function. """     

        area = area_dict["ptran_precharge_side"]*2 + area_dict["ptran_equalization"]
        area_with_sram = area
        width = math.sqrt(area)
        width_with_sram = math.sqrt(area_with_sram)
        area_dict[self.name] = area
        width_dict[self.name] = width
        area_dict[self.name + "_sram"] = area_with_sram
        width_dict[self.name + "_sram"] = width_with_sram

    def update_wires(self, width_dict, wire_lengths, wire_layers):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """
        pass


class _levelshifter(_SizableCircuit):
    "Level Shifter"

    def __init__(self):
        self.name = "level_shifter"

    def generate(self, subcircuit_filename):
        print("Generating the level shifter") 

        self.transistor_names = []
        self.transistor_names.append(memory_subcircuits.generate_level_shifter(subcircuit_filename, self.name))

        self.initial_transistor_sizes["inv_level_shifter_1_nmos"] = 1
        self.initial_transistor_sizes["inv_level_shifter_1_pmos"] = 1.6667
        self.initial_transistor_sizes["ptran_level_shifter_2_nmos"] = 1
        self.initial_transistor_sizes["ptran_level_shifter_3_pmos"] = 1

        return self.initial_transistor_sizes

    def update_area(self, area_dict, width_dict):
        """ Update area. To do this, we use area_dict which is a dictionary, maintained externally, that contains
            the area of everything. It is expected that area_dict will have all the information we need to calculate area.
            We update area_dict and width_dict with calculations performed in this function. """

        area_dict[self.name] = area_dict["inv_level_shifter_1"] * 3 + area_dict["ptran_level_shifter_2"] * 2 + area_dict["ptran_level_shifter_3"] * 2



class _mtjsamp(_SizableCircuit):
    "MTJ sense amplifier operation"

    def __init__(self, colsize):
        self.name = "mtj_samp_m"
        self.colsize = colsize

    def generate_top(self):
        print("generating MTJ sense amp operation")

        self.top_spice_path = top_level.generate_mtj_sa_top(self.name, self.colsize)


class _mtjblcharging(_SizableCircuit):
    "Bitline charging in MTJ"

    def __init__(self, colsize):
        self.name = "mtj_charge"
        self.colsize = colsize

    def generate_top(self):
        print("generating top level circuit for MTJ charging process")

        self.top_spice_path = top_level.generate_mtj_charge(self.name, self.colsize)

class _mtjbldischarging(_SizableCircuit):
    "Bitline discharging in MTJ"

    def __init__(self, colsize):
        self.name = "mtj_discharge"
        self.colsize = colsize


    def generate(self, subcircuit_filename, min_tran_width):
        "Bitline discharging in MTJ"
        self.transistor_names = []
        self.transistor_names.append("ptran_mtj_subcircuits_mtjcs_0_nmos")

        self.initial_transistor_sizes["ptran_mtj_subcircuits_mtjcs_0_nmos"] = 5

        return self.initial_transistor_sizes


    def generate_top(self):
        print("generating top level circuit for MTJ discharging process")

        self.top_spice_path = top_level.generate_mtj_discharge(self.name, self.colsize)


class _mtjbasiccircuits(_SizableCircuit):
    """ MTJ subcircuits"""
    def __init__(self):
        self.name = "mtj_subcircuits"

    def generate(self, subcircuit_filename):
        print("Generating MTJ subcircuits") 

        self.transistor_names = []
        self.transistor_names.append(memory_subcircuits.generate_mtj_sa_lp(subcircuit_filename, self.name))
        self.transistor_names.append(memory_subcircuits.generate_mtj_writedriver_lp(subcircuit_filename, self.name))
        self.transistor_names.append(memory_subcircuits.generate_mtj_cs_lp(subcircuit_filename, self.name))


        self.initial_transistor_sizes["ptran_mtj_subcircuits_mtjsa_1_pmos"] = 6.6667
        self.initial_transistor_sizes["inv_mtj_subcircuits_mtjsa_2_nmos"] = 17.7778
        self.initial_transistor_sizes["inv_mtj_subcircuits_mtjsa_2_pmos"] = 2.2222
        self.initial_transistor_sizes["ptran_mtj_subcircuits_mtjsa_3_nmos"] = 5.5556
        self.initial_transistor_sizes["ptran_mtj_subcircuits_mtjsa_4_nmos"] = 3.6667
        self.initial_transistor_sizes["ptran_mtj_subcircuits_mtjsa_5_nmos"] = 4.4444
        self.initial_transistor_sizes["inv_mtj_subcircuits_mtjsa_6_nmos"] = 1
        self.initial_transistor_sizes["inv_mtj_subcircuits_mtjsa_6_pmos"] = 1

        self.initial_transistor_sizes["inv_mtj_subcircuits_mtjwd_1_nmos"] = 13.3333
        self.initial_transistor_sizes["inv_mtj_subcircuits_mtjwd_1_pmos"] = 13.3333
        self.initial_transistor_sizes["inv_mtj_subcircuits_mtjwd_2_nmos"] = 13.3333
        self.initial_transistor_sizes["inv_mtj_subcircuits_mtjwd_2_pmos"] = 13.3333
        self.initial_transistor_sizes["inv_mtj_subcircuits_mtjwd_3_nmos"] = 1
        self.initial_transistor_sizes["inv_mtj_subcircuits_mtjwd_3_pmos"] = 2

        self.initial_transistor_sizes["tgate_mtj_subcircuits_mtjcs_1_pmos"] = 13.3333
        self.initial_transistor_sizes["tgate_mtj_subcircuits_mtjcs_1_nmos"] = 13.3333
        

        return self.initial_transistor_sizes

    
    def update_area(self, area_dict, width_dict):
        """ Update area. To do this, we use area_dict which is a dictionary, maintained externally, that contains
            the area of everything. It is expected that area_dict will have all the information we need to calculate area.
            We update area_dict and width_dict with calculations performed in this function. """

        area_dict[self.name + "_sa"] = 2* (area_dict["ptran_mtj_subcircuits_mtjsa_1"] + area_dict["inv_mtj_subcircuits_mtjsa_2"] + area_dict["ptran_mtj_subcircuits_mtjsa_3"] + area_dict["ptran_mtj_subcircuits_mtjsa_4"] + area_dict["ptran_mtj_subcircuits_mtjsa_3"] * 2)
        area_dict[self.name + "_sa"] += area_dict["inv_mtj_subcircuits_mtjsa_6"] * 2
        width_dict[self.name + "_sa"] = math.sqrt(area_dict[self.name + "_sa"])

        area_dict[self.name + "_writedriver"] = area_dict["inv_mtj_subcircuits_mtjwd_1"] + area_dict["inv_mtj_subcircuits_mtjwd_2"] + area_dict["inv_mtj_subcircuits_mtjwd_3"]
        width_dict[self.name + "_writedriver"] = math.sqrt(area_dict[self.name + "_writedriver"])

        area_dict[self.name + "_cs"] = area_dict["tgate_mtj_subcircuits_mtjcs_1"]  + area_dict["ptran_mtj_subcircuits_mtjcs_0"]
        width_dict[self.name + "_cs"] = math.sqrt(area_dict[self.name + "_cs"])

        # this is a dummy area for the timing path that I size in transistor sizing stage.
        # the purpose of adding this is to avoid changing the code in transistor sizing stage as this is the only exception.
        area_dict["mtj_discharge"] = 0


class _memorycell(_SizableCircuit):
    """ Memory cell"""

    def __init__(self, use_tgate, RAMwidth, RAMheight, sram_area, number_of_banks, memory_technology):
        self.name = "memorycell"
        self.use_tgate = use_tgate
        self.RAMwidth = RAMwidth
        self.RAMheight = RAMheight
        if memory_technology == "SRAM":
            self.wirevertical =  204 * RAMheight
            self.wirehorizontal = 830 * RAMwidth
        else:
            self.wirevertical =  204 * RAMheight
            self.wirehorizontal = 205 * RAMwidth            
        self.number_of_banks = number_of_banks
        self.memory_technology = memory_technology

    def generate(self, subcircuit_filename, min_tran_width):
        print("Generating BRAM memorycell") 

        if self.memory_technology == "SRAM":
            if use_lp_transistor == 0:
                self.transistor_names, self.wire_names = memory_subcircuits.generate_memorycell(subcircuit_filename, self.name)
            else:
                self.transistor_names, self.wire_names = memory_subcircuits.generate_memorycell_lp(subcircuit_filename, self.name)
        else:
            memory_subcircuits.generate_mtj_memorycell_high_lp(subcircuit_filename, self.name)
            memory_subcircuits.generate_mtj_memorycell_low_lp(subcircuit_filename, self.name)
            memory_subcircuits.generate_mtj_memorycell_reference_lp(subcircuit_filename, self.name)
            memory_subcircuits.generate_mtj_memorycellh_reference_lp(subcircuit_filename, self.name)
            memory_subcircuits.generate_mtj_memorycell_reference_lp_target(subcircuit_filename, self.name)


    def update_area(self, area_dict, width_dict):
        """ Update area. To do this, we use area_dict which is a dictionary, maintained externally, that contains
            the area of everything. It is expected that area_dict will have all the information we need to calculate area.
            We update area_dict and width_dict with calculations performed in this function. """
        if self.memory_technology == "SRAM":     
            area = area_dict["ramsram"] * self.RAMheight * self.RAMwidth * self.number_of_banks
        else:
            area = area_dict["rammtj"] * self.RAMheight * self.RAMwidth * self.number_of_banks
        area_with_sram = area
        width = math.sqrt(area)
        width_with_sram = math.sqrt(area_with_sram)
        area_dict[self.name] = area
        width_dict[self.name] = width
        area_dict[self.name + "_sram"] = area_with_sram
        width_dict[self.name + "_sram"] = width_with_sram

    def update_wires(self, width_dict, wire_lengths, wire_layers):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """
        
        # In this function, we determine the size of two wires and use them very frequently
        # The horizontal and vertical wires are determined by width and length of memory cells and their physical arrangement
        wire_lengths["wire_" + self.name + "_horizontal"] = self.wirehorizontal
        wire_layers["wire_" + self.name + "_horizontal"] = 2
        wire_lengths["wire_" + self.name + "_vertical"] = self.wirevertical
        wire_layers["wire_" + self.name + "_vertical"] = 2



class _RAMLocalMUX(_SizableCircuit):
    """ RAM Local MUX Class: Pass-transistor 2-level mux with no driver """
    
    def __init__(self, required_size, num_per_tile, use_tgate):
        # Subcircuit name
        #sadegh
        self.name = "ram_local_mux"
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
        self.delay_weight = DELAY_WEIGHT_RAM
        # use pass transistor or transmission gates
        self.use_tgate = use_tgate
    
    
    def generate(self, subcircuit_filename, min_tran_width):
        print("Generating RAM local mux")
        
        # Calculate level sizes and number of SRAMs per mux
        self.level2_size = int(math.sqrt(self.required_size))
        self.level1_size = int(math.ceil(float(self.required_size)/self.level2_size))
        self.implemented_size = self.level1_size*self.level2_size
        self.num_unused_inputs = self.implemented_size - self.required_size
        self.sram_per_mux = self.level1_size + self.level2_size
        
        if not self.use_tgate :
            # Call generation function
            self.transistor_names, self.wire_names = mux_subcircuits.generate_ptran_2lvl_mux_no_driver(subcircuit_filename, self.name, self.implemented_size, self.level1_size, self.level2_size)
            
            # Initialize transistor sizes (to something more reasonable than all min size, but not necessarily a good choice, depends on architecture params)
            self.initial_transistor_sizes["ptran_" + self.name + "_L1_nmos"] = 2
            self.initial_transistor_sizes["ptran_" + self.name + "_L2_nmos"] = 2
            self.initial_transistor_sizes["rest_" + self.name + "_pmos"] = 1
            self.initial_transistor_sizes["inv_" + self.name + "_1_nmos"] = 1
            self.initial_transistor_sizes["inv_" + self.name + "_1_pmos"] = 2

        else :
            # Call MUX generation function
            self.transistor_names, self.wire_names = mux_subcircuits.generate_tgate_2lvl_mux_no_driver(subcircuit_filename, self.name, self.implemented_size, self.level1_size, self.level2_size)
            
            # Initialize transistor sizes (to something more reasonable than all min size, but not necessarily a good choice, depends on architecture params)
            self.initial_transistor_sizes["tgate_" + self.name + "_L1_nmos"] = 2
            self.initial_transistor_sizes["tgate_" + self.name + "_L1_pmos"] = 2
            self.initial_transistor_sizes["tgate_" + self.name + "_L2_nmos"] = 2
            self.initial_transistor_sizes["tgate_" + self.name + "_L2_pmos"] = 2
            self.initial_transistor_sizes["inv_" + self.name + "_1_nmos"] = 1
            self.initial_transistor_sizes["inv_" + self.name + "_1_pmos"] = 2


        return self.initial_transistor_sizes

    def generate_top(self):
        print("Generating top-level RAM local mux")

        self.top_spice_path = top_level.generate_RAM_local_mux_top(self.name)

   
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



    
    def update_wires(self, width_dict, wire_lengths, wire_layers):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """

        # Update wire lengths

        wire_lengths["wire_" + self.name + "_L1"] = width_dict[self.name]
        wire_lengths["wire_" + self.name + "_L2"] = width_dict[self.name]
        
        # Update wire layers
        wire_layers["wire_" + self.name + "_L1"] = 0
        wire_layers["wire_" + self.name + "_L2"] = 0  



   
    def print_details(self, report_file):
        """ Print RAM local mux details """
        
        utils.print_and_write(report_file, "  RAM LOCAL MUX DETAILS:")
        utils.print_and_write(report_file, "  Style: two-level MUX")
        utils.print_and_write(report_file, "  Required MUX size: " + str(self.required_size) + ":1")
        utils.print_and_write(report_file, "  Implemented MUX size: " + str(self.implemented_size) + ":1")
        utils.print_and_write(report_file, "  Level 1 size = " + str(self.level1_size))
        utils.print_and_write(report_file, "  Level 2 size = " + str(self.level2_size))
        utils.print_and_write(report_file, "  Number of unused inputs = " + str(self.num_unused_inputs))
        utils.print_and_write(report_file, "  Number of MUXes per tile: " + str(self.num_per_tile))
        utils.print_and_write(report_file, "  Number of SRAM cells per MUX: " + str(self.sram_per_mux))
        utils.print_and_write(report_file, "")


class _RAMLocalRoutingWireLoad:
    """ Local routing wire load """
    
    def __init__(self, row_decoder_bits, col_decoder_bits, conf_decoder_bits):
        # Name of this wire
        self.name = "local_routing_wire_load"
        # This is calculated for the widest mode (worst case scenario. Other modes have less usage)
        self.RAM_input_usage_assumption = float((2 + 2*(row_decoder_bits + col_decoder_bits) + 2** (conf_decoder_bits))//(2 + 2*(row_decoder_bits + col_decoder_bits+ conf_decoder_bits) + 2** (conf_decoder_bits)))
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
        self.row_decoder_bits = row_decoder_bits
        self.col_decoder_bits = col_decoder_bits
        self.conf_decoder_bits = conf_decoder_bits


    def generate(self, subcircuit_filename, specs, RAM_local_mux):
        print("Generating local routing wire load")
        # Compute load (number of on/partial/off per wire)
        self._compute_load(specs, RAM_local_mux)
        # Generate SPICE deck
        self.wire_names = load_subcircuits.RAM_local_routing_load_generate(subcircuit_filename, self.on_inputs_per_wire, self.partial_inputs_per_wire, self.off_inputs_per_wire)
    
    
    def update_wires(self, width_dict, wire_lengths, wire_layers):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """
        
        # Update wire lengths
        # wire_lengths["wire_ram_local_routing"] = width_dict["ram_local_mux_total"]
        wire_lengths["wire_ram_local_routing"] = width_dict["ram_local_mux_total"]
        # Update wire layers
        wire_layers["wire_ram_local_routing"] = 0
    
        
        
        
    def _compute_load(self, specs, RAM_local_mux):
        """ Compute the load on a local routing wire (number of on/partial/off) """
        
        # The first thing we are going to compute is how many local mux inputs are connected to a local routing wire
        # FOR a ram block its the number of inputs
        num_local_routing_wires = (2 + 2*(self.row_decoder_bits + self.col_decoder_bits+ self.conf_decoder_bits) + 2** (self.conf_decoder_bits))
        self.mux_inputs_per_wire = RAM_local_mux.implemented_size
        
        # Now we compute how many "on" inputs are connected to each routing wire
        # This is a funtion of lut input usage, number of lut inputs and number of local routing wires
        num_local_muxes_used = self.RAM_input_usage_assumption*(2 + 2*(self.row_decoder_bits + self.col_decoder_bits+ self.conf_decoder_bits) + 2** (self.conf_decoder_bits))
        self.on_inputs_per_wire = int(num_local_muxes_used/num_local_routing_wires)
        # We want to model for the case where at least one "on" input is connected to the local wire, so make sure it's at least 1
        if self.on_inputs_per_wire < 1:
            self.on_inputs_per_wire = 1
        
        # Now we compute how many partially on muxes are connected to each wire
        # The number of partially on muxes is equal to (level2_size - 1)*num_local_muxes_used/num_local_routing_wire
        # We can figure out the number of muxes used by using the "on" assumption and the number of local routing wires.
        self.partial_inputs_per_wire = int((RAM_local_mux.level2_size - 1.0)*num_local_muxes_used/num_local_routing_wires)
        # Make it at least 1
        if self.partial_inputs_per_wire < 1:
            self.partial_inputs_per_wire = 1
        
        # Number of off inputs is simply the difference
        self.off_inputs_per_wire = self.mux_inputs_per_wire - self.on_inputs_per_wire - self.partial_inputs_per_wire

class _RAM(_CompoundCircuit):
    
    def __init__(self, row_decoder_bits, col_decoder_bits, conf_decoder_bits, RAM_local_mux_size_required, RAM_num_local_mux_per_tile, use_tgate ,sram_area, number_of_banks, memory_technology, cspecs, process_data_filename, read_to_write_ratio):
        # Name of RAM block
        self.name = "ram"
        # use tgates or pass transistors
        self.use_tgate = use_tgate
        # RAM info such as docoder size, crossbar population, number of banks and output crossbar fanout
        self.row_decoder_bits = row_decoder_bits
        self.col_decoder_bits = col_decoder_bits
        self.conf_decoder_bits = conf_decoder_bits
        self.number_of_banks = number_of_banks
        self.cspecs = cspecs
        self.target_bl = 0.04
        self.process_data_filename = process_data_filename
        self.memory_technology = memory_technology

        # timing components
        self.T1 = 0.0
        self.T2 = 0.0
        self.T3 = 0.0
        self.frequency = 0.0

        # Energy components
        self.read_to_write_ratio = read_to_write_ratio
        self.core_energy = 0.0
        self.peripheral_energy_read = 0.0
        self.peripheral_energy_write = 0.0

        # This is the estimated row decoder delay
        self.estimated_rowdecoder_delay = 0.0

        if number_of_banks == 2:
            self.row_decoder_bits = self.row_decoder_bits - 1

        # delay weight of the RAM module in total delay measurement
        self.delay_weight = DELAY_WEIGHT_RAM

        # Create local mux object
        self.RAM_local_mux = _RAMLocalMUX(RAM_local_mux_size_required, RAM_num_local_mux_per_tile, use_tgate)
        # Create the local routing wire load module
        self.RAM_local_routing_wire_load = _RAMLocalRoutingWireLoad(self.row_decoder_bits, col_decoder_bits, conf_decoder_bits)
        # Create memory cells
        self.memorycells = _memorycell(self.use_tgate, 2**(conf_decoder_bits + col_decoder_bits), 2**(self.row_decoder_bits), sram_area, self.number_of_banks, self.memory_technology)
        # calculat the number of input ports for the ram module
        self.ram_inputs = (3 + 2*(self.row_decoder_bits + col_decoder_bits + number_of_banks ) + 2** (self.conf_decoder_bits))
        
        #initialize decoder object sizes
        # There are two predecoders, each of which can have up two three internal predecoders as well:
        self.predecoder1 = 1
        self.predecoder2 = 2
        self.predecoder3 = 0
        # Create decoder object
        # determine the number of predecoders, 2 predecoders are needed
        # inside each predecoder, 2 or 3 nandpaths are required as first stage.
        # the second stage, is a 2 input or 3 input nand gate, there are lots of 2nd stage nand gates as load for the first stage
        # a width of less than 8  will use smaller decoder (2 levels) while a larger decoder uses 3 levels



        # If there are two banks, the rowdecoder size is reduced in half (number of bits is reduced by 1)

        # Bounds on row decoder size:
        assert self.row_decoder_bits >= 5
        assert self.row_decoder_bits <= 9

        # determine decoder object sizes
        # The reason why I'm allocating predecoder size like this is that it gives the user a better flexibility to determine how to make their decoders
        # For example, if the user doesn't want to have 2 predecoders when decoding 6 bits, they can simply change the number below.
        # Feel free to change the following to determine how your decoder is generated.
        if self.row_decoder_bits == 5:
            self.predecoder1 = 3
            self.predecoder2 = 2
        if self.row_decoder_bits == 6:
            self.predecoder1 = 3
            self.predecoder2 = 3
        if self.row_decoder_bits == 7:
            self.predecoder1 = 3
            self.predecoder2 = 2
            self.predecoder3 = 2
        if self.row_decoder_bits == 8:
            self.predecoder1 = 3
            self.predecoder2 = 3
            self.predecoder3 = 2
        if self.row_decoder_bits == 9:
            self.predecoder1 = 3
            self.predecoder2 = 3
            self.predecoder3 = 3



        # some variables to determine size of decoder stages and their numbers
        self.valid_row_dec_size2 = 0
        self.valid_row_dec_size3 = 0
        self.count_row_dec_size2 = 0
        self.count_row_dec_size3 = 0
        self.fanout_row_dec_size2 = 0
        self.fanout_row_dec_size3 = 0
        self.fanouttypeforrowdec = 2

        

        #small row decoder
        #figure out how many stage 0 nand gates u have and of what type
        self.count_small_row_dec_nand2 = 0
        self.count_small_row_dec_nand3 = 0
        if self.predecoder1 == 3:
            self.count_small_row_dec_nand3 = self.count_small_row_dec_nand3 + 3
        else:
            self.count_small_row_dec_nand2 = self.count_small_row_dec_nand2 + 2

        if self.predecoder2 == 3:
            self.count_small_row_dec_nand3 = self.count_small_row_dec_nand3 + 3
        else:
            self.count_small_row_dec_nand2 = self.count_small_row_dec_nand2 + 2               

        if self.predecoder3 == 3:
            self.count_small_row_dec_nand3 = self.count_small_row_dec_nand3 + 3
        elif self.predecoder3 == 2:
            self.count_small_row_dec_nand2 = self.count_small_row_dec_nand2 + 2 

        self.rowdecoder_stage0 = _rowdecoder0(use_tgate, self.count_small_row_dec_nand3,0 , self.count_small_row_dec_nand2, 0 , self.row_decoder_bits)
        #generate stage 0 , just an inverter that connects to half of the gates
        #call a function to generate it!!
        # Set up the wordline driver
        self.wordlinedriver = _wordlinedriver(use_tgate, 2**(self.col_decoder_bits + self.conf_decoder_bits), self.number_of_banks, 2**self.row_decoder_bits, 1, self.memory_technology)

        # create stage 1 similiar to configurable decoder

        if self.predecoder3 !=0:
            self.fanouttypeforrowdec = 3

        self.area2 = 0
        self.area3 = 0

        if self.predecoder2 == 2:
            self.area2 += 4
        else:
            self.area3 +=8

        if self.predecoder1 == 2:
            self.area2 += 4
        else:
            self.area3 +=8             

        if self.predecoder3 == 2:
            self.area2 += 4
        elif self.predecoder3 ==3:
            self.area3 +=8

        #check if nand2 exists, call a function
        if self.predecoder1 == 2 or self.predecoder2 == 2 or self.predecoder3 == 2:
            self.rowdecoder_stage1_size2 = _rowdecoder1(use_tgate, 2 ** (self.row_decoder_bits - 2), self.fanouttypeforrowdec, 2, self.area2)
            self.valid_row_dec_size2 = 1

        #check if nand3 exists, call a function
        if self.predecoder1 == 3 or self.predecoder2 == 3 or self.predecoder3 == 3:
            self.rowdecoder_stage1_size3 = _rowdecoder1(use_tgate, 2 ** (self.row_decoder_bits - 3), self.fanouttypeforrowdec, 3, self.area3)
            self.valid_row_dec_size3 = 1

        # there is no intermediate stage, connect what you generated directly to stage 3
        self.gatesize_stage3 = 2
        if self.row_decoder_bits > 6:
            self.gatesize_stage3 = 3

        self.rowdecoder_stage3 = _rowdecoderstage3(use_tgate, self.area2, self.area3, 2**(self.col_decoder_bits + self.conf_decoder_bits), self.gatesize_stage3, self.fanouttypeforrowdec, 2** self.row_decoder_bits)



        # measure memory core power:
        if self.memory_technology == "SRAM":
            self.power_sram_read = _powersramread(2**self.row_decoder_bits, 2**self.col_decoder_bits)
            self.power_sram_writelh = _powersramwritelh(2**self.row_decoder_bits, 2**self.col_decoder_bits)
            self.power_sram_writehh = _powersramwritehh(2**self.row_decoder_bits, 2**self.col_decoder_bits)
            self.power_sram_writep = _powersramwritep(2**self.row_decoder_bits, 2**self.col_decoder_bits)

        elif self.memory_technology == "MTJ":
            self.power_mtj_write = _powermtjwrite(2**self.row_decoder_bits)
            self.power_mtj_read = _powermtjread(2**self.row_decoder_bits)


        # Create precharge and equalization
        if self.memory_technology == "SRAM":
            self.precharge = _prechargeandeq(self.use_tgate, 2**self.row_decoder_bits)
            self.samp_part2 = _samp_part2(self.use_tgate, 2**self.row_decoder_bits, 0.3)
            self.samp = _samp(self.use_tgate, 2**self.row_decoder_bits, 0, 0.3)
            self.writedriver = _writedriver(self.use_tgate, 2**self.row_decoder_bits)

        elif self.memory_technology == "MTJ":
            self.mtjbasics = _mtjbasiccircuits()
            self.bldischarging = _mtjbldischarging(2**self.row_decoder_bits)
            self.blcharging = _mtjblcharging(2**self.row_decoder_bits)
            self.mtjsamp = _mtjsamp(2**self.row_decoder_bits)


        self.columndecoder = _columndecoder(self.use_tgate, 2**(self.col_decoder_bits + self.conf_decoder_bits), self.col_decoder_bits)
        #create the level shifter

        self.levelshift = _levelshifter()
        #the configurable decoder:


        self.cpredecoder = 1
        self.cpredecoder1 = 0
        self.cpredecoder2 = 0
        self.cpredecoder3 = 0

        assert self.conf_decoder_bits >= 4
        assert self.conf_decoder_bits <= 9

        # Same as the row decoder
        #determine decoder object sizes
        if self.conf_decoder_bits == 4:
            self.cpredecoder = 4
            self.cpredecoder1 = 2
            self.cpredecoder2 = 2  
        if self.conf_decoder_bits == 5:
            self.cpredecoder = 5
            self.cpredecoder1 = 3
            self.cpredecoder2 = 2
        if self.conf_decoder_bits == 6:
            self.cpredecoder = 6
            self.cpredecoder1 = 3
            self.cpredecoder2 = 3
        if self.conf_decoder_bits == 7:
            self.cpredecoder = 7
            self.cpredecoder1 = 2
            self.cpredecoder2 = 2
            self.cpredecoder3 = 3
        if self.conf_decoder_bits == 8:
            self.cpredecoder = 8
            self.cpredecoder1 = 3
            self.cpredecoder2 = 3
            self.cpredecoder3 = 2
        if self.conf_decoder_bits == 9:
            self.cpredecoder = 9
            self.cpredecoder1 = 3
            self.cpredecoder2 = 3
            self.cpredecoder3 = 3

        self.cfanouttypeconf = 2
        if self.cpredecoder3 != 0:
            self.cfanouttypeconf = 3

        self.cfanin1 = 0
        self.cfanin2 = 0
        self.cvalidobj1 = 0
        self.cvalidobj2 = 0

        self.stage1output3 = 0
        self.stage1output2 = 0

        if self.cpredecoder1 == 3:
            self.stage1output3+=8
        if self.cpredecoder2 == 3:
            self.stage1output3+=8 
        if self.cpredecoder3 == 3:
            self.stage1output3+=8

        if self.cpredecoder1 == 2:
            self.stage1output2+=4
        if self.cpredecoder2 == 2:
            self.stage1output2+=4 
        if self.cpredecoder3 == 2:
            self.stage1output2+=4              

        if self.cpredecoder1 == 3 or self.cpredecoder2 == 3 or self.cpredecoder3 == 3:
            self.configurabledecoder3ii =  _configurabledecoder3ii(use_tgate, 3, 2**(self.cpredecoder1+self.cpredecoder1+self.cpredecoder1 - 3), self.cfanouttypeconf, self.stage1output3)
            self.cfanin1 = 2**(self.cpredecoder1+self.cpredecoder2+self.cpredecoder3 - 3)
            self.cvalidobj1 = 1

        if self.cpredecoder2 == 2 or self.cpredecoder2 == 2 or self.cpredecoder3 == 2:
            self.configurabledecoder2ii =  _configurabledecoder2ii(use_tgate, 2, 2**(self.cpredecoder1+self.cpredecoder1+self.cpredecoder1 - 2), self.cfanouttypeconf, self.stage1output2)
            self.cfanin2 = 2**(self.cpredecoder1+self.cpredecoder2+self.cpredecoder3 - 2)
            self.cvalidobj2 = 1

        self.configurabledecoderi = _configurabledecoderinvmux(use_tgate, int(self.stage1output2//2), int(self.stage1output3//2), self.conf_decoder_bits)
        self.configurabledecoderiii = _configurabledecoderiii(use_tgate, self.cfanouttypeconf , self.cfanin1 , self.cfanin2, 2**self.conf_decoder_bits)

        self.pgateoutputcrossbar = _pgateoutputcrossbar(2**self.conf_decoder_bits)
        
    def generate(self, subcircuits_filename, min_tran_width, specs):
        print("Generating RAM block")
        init_tran_sizes = {}
        init_tran_sizes.update(self.RAM_local_mux.generate(subcircuits_filename, min_tran_width))

        if self.valid_row_dec_size2 == 1:
            init_tran_sizes.update(self.rowdecoder_stage1_size2.generate(subcircuits_filename, min_tran_width))

        if self.valid_row_dec_size3 == 1:
            init_tran_sizes.update(self.rowdecoder_stage1_size3.generate(subcircuits_filename, min_tran_width))

        init_tran_sizes.update(self.rowdecoder_stage3.generate(subcircuits_filename, min_tran_width))
        
        init_tran_sizes.update(self.rowdecoder_stage0.generate(subcircuits_filename, min_tran_width))
        init_tran_sizes.update(self.wordlinedriver.generate(subcircuits_filename, min_tran_width))
        self.RAM_local_routing_wire_load.generate(subcircuits_filename, specs, self.RAM_local_mux)

        self.memorycells.generate(subcircuits_filename, min_tran_width)

        if self.memory_technology == "SRAM":
            init_tran_sizes.update(self.precharge.generate(subcircuits_filename, min_tran_width))
            self.samp.generate(subcircuits_filename, min_tran_width)
            init_tran_sizes.update(self.writedriver.generate(subcircuits_filename, min_tran_width))
        else:
            init_tran_sizes.update(self.bldischarging.generate(subcircuits_filename, min_tran_width))
            init_tran_sizes.update(self.mtjbasics.generate(subcircuits_filename))


        init_tran_sizes.update(self.levelshift.generate(subcircuits_filename))
        
        init_tran_sizes.update(self.columndecoder.generate(subcircuits_filename, min_tran_width))

        init_tran_sizes.update(self.configurabledecoderi.generate(subcircuits_filename, min_tran_width))

        init_tran_sizes.update(self.configurabledecoderiii.generate(subcircuits_filename, min_tran_width))

        
        if self.cvalidobj1 == 1:
            init_tran_sizes.update(self.configurabledecoder3ii.generate(subcircuits_filename, min_tran_width))
        if self.cvalidobj2 == 1:
            init_tran_sizes.update(self.configurabledecoder2ii.generate(subcircuits_filename, min_tran_width))


        init_tran_sizes.update(self.pgateoutputcrossbar.generate(subcircuits_filename, min_tran_width))

        return init_tran_sizes

        
    def _update_process_data(self):
        """ I'm using this file to update several timing variables after measuring them. """
        
        process_data_file = open(self.process_data_filename, 'w')
        process_data_file.write("*** PROCESS DATA AND VOLTAGE LEVELS\n\n")
        process_data_file.write(".LIB PROCESS_DATA\n\n")
        process_data_file.write("* Voltage levels\n")
        process_data_file.write(".PARAM supply_v = " + str(self.cspecs.vdd) + "\n")
        process_data_file.write(".PARAM sram_v = " + str(self.cspecs.vsram) + "\n")
        process_data_file.write(".PARAM sram_n_v = " + str(self.cspecs.vsram_n) + "\n")
        process_data_file.write(".PARAM Rcurrent = " + str(self.cspecs.worst_read_current) + "\n")
        process_data_file.write(".PARAM supply_v_lp = " + str(self.cspecs.vdd_low_power) + "\n\n")


        if use_lp_transistor == 0 :
            process_data_file.write(".PARAM sense_v = " + str(self.cspecs.vdd - self.cspecs.sense_dv) + "\n\n")
        else:
            process_data_file.write(".PARAM sense_v = " + str(self.cspecs.vdd_low_power - self.cspecs.sense_dv) + "\n\n")


        process_data_file.write(".PARAM mtj_worst_high = " + str(self.cspecs.MTJ_Rhigh_worstcase) + "\n")
        process_data_file.write(".PARAM mtj_worst_low = " + str(self.cspecs.MTJ_Rlow_worstcase) + "\n")
        process_data_file.write(".PARAM mtj_nominal_low = " + str(self.cspecs.MTJ_Rlow_nominal) + "\n\n")
        process_data_file.write(".PARAM mtj_nominal_high = " + str(6250) + "\n\n") 
        process_data_file.write(".PARAM vref = " + str(self.cspecs.vref) + "\n")
        process_data_file.write(".PARAM vclmp = " + str(self.cspecs.vclmp) + "\n")

        process_data_file.write("* Misc parameters\n")

        process_data_file.write(".PARAM ram_frequency = " + str(self.frequency) + "\n")
        process_data_file.write(".PARAM precharge_max = " + str(self.T1) + "\n")
        if self.cspecs.memory_technology == "SRAM":
            process_data_file.write(".PARAM wl_eva = " + str(self.T1 + self.T2) + "\n")
            process_data_file.write(".PARAM sa_xbar_ff = " + str(self.frequency) + "\n")
        elif self.cspecs.memory_technology == "MTJ":
            process_data_file.write(".PARAM target_bl = " + str(self.target_bl) + "\n")
            process_data_file.write(".PARAM time_bl = " + str(self.blcharging.delay) + "\n")
            process_data_file.write(".PARAM sa_se1 = " + str(self.T2) + "\n")
            process_data_file.write(".PARAM sa_se2 = " + str(self.T3) + "\n")

        process_data_file.write("* Geometry\n")
        process_data_file.write(".PARAM gate_length = " + str(self.cspecs.gate_length) + "n\n")
        process_data_file.write(".PARAM trans_diffusion_length = " + str(self.cspecs.trans_diffusion_length) + "n\n")
        process_data_file.write(".PARAM min_tran_width = " + str(self.cspecs.min_tran_width) + "n\n")
        process_data_file.write(".param rest_length_factor=" + str(self.cspecs.rest_length_factor) + "\n")
        process_data_file.write("\n")

        process_data_file.write("* Supply voltage.\n")
        process_data_file.write("VSUPPLY vdd gnd supply_v\n")
        process_data_file.write("VSUPPLYLP vdd_lp gnd supply_v_lp\n")
        process_data_file.write("* SRAM voltages connecting to gates\n")
        process_data_file.write("VSRAM vsram gnd sram_v\n")
        process_data_file.write("VrefMTJn vrefmtj gnd vref\n")
        process_data_file.write("Vclmomtjn vclmpmtj gnd vclmp\n")
        process_data_file.write("VSRAM_N vsram_n gnd sram_n_v\n\n")
        process_data_file.write("* Device models\n")
        process_data_file.write(".LIB \"" + self.cspecs.model_path + "\" " + self.cspecs.model_library + "\n\n")
        process_data_file.write(".ENDL PROCESS_DATA")
        process_data_file.close()
        

    def generate_top(self):

        # Generate top-level evaluation paths for all components:

        self.RAM_local_mux.generate_top()

        self.rowdecoder_stage0.generate_top()


        self.rowdecoder_stage3.generate_top()

        if self.valid_row_dec_size2 == 1:
            self.rowdecoder_stage1_size2.generate_top()
        if self.valid_row_dec_size3 == 1:
            self.rowdecoder_stage1_size3.generate_top()


        if self.memory_technology == "SRAM":
            self.precharge.generate_top()
            self.samp_part2.generate_top()
            self.samp.generate_top()
            self.writedriver.generate_top()
            self.power_sram_read.generate_top()
            self.power_sram_writelh.generate_top()
            self.power_sram_writehh.generate_top()
            self.power_sram_writep.generate_top()
        else:
            self.bldischarging.generate_top()
            self.blcharging.generate_top()
            self.mtjsamp.generate_top()
            self.power_mtj_write.generate_top()
            self.power_mtj_read.generate_top()

        self.columndecoder.generate_top()
        self.configurabledecoderi.generate_top()
        self.configurabledecoderiii.generate_top()

        
        if self.cvalidobj1 == 1:
            self.configurabledecoder3ii.generate_top()
        if self.cvalidobj2 == 1:
            self.configurabledecoder2ii.generate_top()

        self.pgateoutputcrossbar.generate_top()
        self.wordlinedriver.generate_top()

    def update_area(self, area_dict, width_dict):

        
        self.RAM_local_mux.update_area(area_dict, width_dict)

        self.rowdecoder_stage0.update_area(area_dict, width_dict) 

        self.rowdecoder_stage3.update_area(area_dict, width_dict)

        if self.valid_row_dec_size2 == 1:
            self.rowdecoder_stage1_size2.update_area(area_dict, width_dict)
        if self.valid_row_dec_size3 == 1:
            self.rowdecoder_stage1_size3.update_area(area_dict, width_dict)

        self.memorycells.update_area(area_dict, width_dict)

        if self.memory_technology == "SRAM":
            self.precharge.update_area(area_dict, width_dict)
            self.samp.update_area(area_dict, width_dict)
            self.writedriver.update_area(area_dict, width_dict)
        else:
            self.mtjbasics.update_area(area_dict, width_dict)

        self.columndecoder.update_area(area_dict, width_dict)
        self.configurabledecoderi.update_area(area_dict, width_dict)
        if self.cvalidobj1 == 1:
            self.configurabledecoder3ii.update_area(area_dict, width_dict)
        if self.cvalidobj2 == 1:    
            self.configurabledecoder2ii.update_area(area_dict, width_dict)

        self.configurabledecoderiii.update_area(area_dict, width_dict)
        self.pgateoutputcrossbar.update_area(area_dict, width_dict)
        self.wordlinedriver.update_area(area_dict, width_dict)
        self.levelshift.update_area(area_dict, width_dict)
    
        
    
    def update_wires(self, width_dict, wire_lengths, wire_layers):
        """ Update wires of things inside the RAM block. """
        
        self.RAM_local_mux.update_wires(width_dict, wire_lengths, wire_layers)
        self.RAM_local_routing_wire_load.update_wires(width_dict, wire_lengths, wire_layers)
        self.rowdecoder_stage0.update_wires(width_dict, wire_lengths, wire_layers)
        self.memorycells.update_wires(width_dict, wire_lengths, wire_layers)
        self.wordlinedriver.update_wires(width_dict, wire_lengths, wire_layers)
        self.configurabledecoderi.update_wires(width_dict, wire_lengths, wire_layers)
        self.pgateoutputcrossbar.update_wires(width_dict, wire_lengths, wire_layers)
        self.configurabledecoderiii.update_wires(width_dict, wire_lengths, wire_layers)

        
        
    def print_details(self, report_file):
        self.RAM_local_mux.print_details(report_file)




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
        self.delay_weight = DELAY_WEIGHT_RAM
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

    def generate(self, subcircuit_filename, min_tran_width):
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


def get_current_stack_trace(max_height: int = None) -> str:
    stack = traceback.extract_stack()
    if max_height is not None:
        # Take last N function calls from the bottom to top of call stack
        fn_calls = [f.name for f in stack]
        fn_calls = fn_calls[-(max_height+1):-1]
    return '/'.join(fn_calls)  # Exclude the current function call itself

def update_fpga_telemetry_csv(fpga_inst: 'FPGA', tag:str, exclusive_cat: str = None):
    """ Update the FPGA telemetry CSV file with the current FPGA telemetry, Create CSV if it doesnt exist """


    out_catagories = {
        "wire_length": fpga_inst.wire_lengths,
        "area": fpga_inst.area_dict,
        "tx_size": fpga_inst.transistor_sizes,
        "delay": fpga_inst.delay_dict
    }
    # Make sure these keys are same ones in FPGA object
    assert set(list(out_catagories.keys())) == set(fpga_inst.log_out_catagories)

    # Check to see if any repeating keys in any of these dicts
    # if not set(fpga_inst.wire_lengths.keys()) & set(fpga_inst.area_dict.keys()) fpga_inst.transistor_sizes.keys()
    # Write a CSV for each catagory of information we want to track
    for cat_k, cat_v in out_catagories.items():
        # cat_sorted_keys = list(cat_v.keys()).sort()
        # sorted_cat = {k: cat_v[k] for k in cat_sorted_keys}
        if not cat_v or (exclusive_cat and cat_k != exclusive_cat): 
            continue
        sorted_cat = OrderedDict(sorted(cat_v.items())) 
        row_data = { "TAG": tag, "AREA_UPDATE_ITER": fpga_inst.update_area_cnt, "WIRE_UPDATE_ITER": fpga_inst.update_wires_cnt, "DELAY_UPDATE_ITER": fpga_inst.update_delays_cnt, "COMPUTE_DISTANCE_ITER": fpga_inst.compute_distance_cnt, **sorted_cat}
        # Open the CSV file
        with open(f"{cat_k}_debug.csv", "a") as csv_file:
            header = list(row_data.keys())
            writer = csv.DictWriter(csv_file, fieldnames = header)
            # Check if the file is empty and write header if needed
            if csv_file.tell() == 0:
                writer.writeheader()
            writer.writerow(row_data)


# RRG data structures are taken from csvs generated via the rr_parse script
@dataclass
class SegmentRRG():
    """ 
        This class describes a segment in the routing resource graph (RRG). 
    """
    # Required fields
    name: str            # Name of the segment
    id: int               
    length: int          # Length of the segment in number of tiles
    C_per_meter: float  # Capacitance per meter of the segment (FROM VTR)
    R_per_meter: float  # Resistance per meter of the segment (FROM VTR)

@dataclass
class SwitchRRG():
    name: str
    id: int
    type: str
    R: float        = None 
    Cin: float      = None 
    Cout: float     = None 
    Tdel: float     = None 


@dataclass
class MuxLoadRRG():
    mux_type: str   # What mux are we referring to?
    freq: int       # How many of these muxes are attached?

@dataclass
class MuxIPIN():
    wire_type: str      # What is the wire type going into this mux IPIN?
    drv_type: str       # What is the driver type of the wire going into this mux IPIN?
    freq: int          # How many of these muxes are attached?

@dataclass
class MuxWireStatRRG():
    wire_type: str            # What wire are we referring to?
    drv_type: str             # What mux is driving this wire?
    mux_ipins: List[MuxIPIN]  # What are the mux types / frequency attached to this wire?
    mux_loads: List[MuxLoadRRG]   # What are mux types / frequency attached to this wire?
    total_mux_inputs: int         = None  # How many mux inputs for mux driving this wire?
    total_wire_loads: int         = None       # How many wires are loading this mux in total of all types?
    def __post_init__(self):
        self.total_mux_inputs = sum([mux_ipin.freq for mux_ipin in self.mux_ipins])
        self.total_wire_loads = sum([mux_load.freq for mux_load in self.mux_loads])
    #     # Make suer that all the MuxIPINs in list add up to our total mux inputs
    #     assert sum([mux_ipin.freq for mux_ipin in self.mux_ipins]) == self.total_mux_inputs, "Mux IPIN frequencies do not add up to total mux inputs"
    #     # Make sure that all the MuxLoadRRGs in list add up to our total wire loads
    #     assert sum([mux_load.freq for mux_load in self.mux_loads]) == self.total_wire_loads, "Mux loads do not add up to total wire loads"


@dataclass
class Wire:
    # Describes a wire type in the FPGA
    name: str                       # Name of the wire type, used for the SpParameter globally across circuits Ex. "gen_routing_wire_L4", "intra_tile_ble_2_sb"    
    layer: int          # What RC index do we use for this wire (what metal layer does this corresond to?)
    id: int                        # Unique identifier for this wire type, used to generate the wire name Ex. "gen_routing_wire_L4_0", "intra_tile_ble_2_sb_0"
    def __post_init__(self):
        # Struct verif checks
        assert self.id >= 0, "uid must be a non-negative integer"

@dataclass
class GenRoutingWire(Wire):
    """ 
        This class describes a general routing wire in an FPGA. 
    """
    # Required fields
    length: int         # Length of the general routing wire in number of tiles
    mux_info: MuxWireStatRRG

class FPGA:
    """ This class describes an FPGA. """
        
    def __init__(self, coffe_info: rg_ds.Coffe, run_options, spice_interface, telemetry_fpath):
        
        # Telemetry file path
        self.telemetry_fpath = telemetry_fpath

        # Get our global logger
        self.logger = logging.getLogger("rad_gen_root")

        # Counters for various update functions
        self.update_area_cnt = 0
        self.update_wires_cnt = 0
        self.compute_distance_cnt = 0
        self.update_delays_cnt = 0

        self.log_out_catagories: List[str] = [
            "wire_length",
            "area",
            "tx_size",
            "delay",
        ]

        # Stuff for multi wire length support
        # self.num_sb_muxes_per_tile = 0
        # self.avg_sb_mux_area = 0
        self.num_cb_muxes_per_tile = 0
        # self.avg_cb_mux_area = 0
        self.num_local_muxes_per_tile = 0
        # self.avg_local_mux_area = 0
        # Delay stuff
        # self.avg_sb_mux_delay = 0

        # Lists of subcircuits which we have to consider for each wire length
        self.sb_muxes: List[_SwitchBlockMUX] = [] # List of switch block muxes for each wire length
        self.cb_muxes: List[_ConnectionBlockMUX] = [] 
        # self.local_muxes: List[]
        self.routing_wire_loads : List[_RoutingWireLoad] = []
        self.cluster_output_loads : List[_GeneralBLEOutputLoad] = []
        self.logic_clusters: List[_LogicCluster] = []
        
        # Data structure contianing all of subckts structs parsed POST - generate phase
        self.all_subckts: Dict[str, rg_ds.SpSubCkt] = {}


        # Initialize the specs
        self.specs = _Specs(coffe_info.fpga_arch_conf["fpga_arch_params"], run_options.quick_mode)


        # From specs init
        # We need the minimum length wire to use for some circuits
        # Currently we are just using the minimum length wire type as the input to connection block mux
        wire_lens = [ wire["len"] for wire in self.specs.wire_types]
        self.min_len_wire = self.specs.wire_types[wire_lens.index(min(wire_lens))]
        global min_len_wire
        min_len_wire = self.min_len_wire

        ######################################
        ### INITIALIZE SPICE LIBRARY NAMES ###
        ######################################

        self.wire_RC_filename           = "wire_RC.l"
        self.process_data_filename      = "process_data.l"
        self.includes_filename          = "includes.l"
        self.basic_subcircuits_filename = "basic_subcircuits.l"
        self.subcircuits_filename       = "subcircuits.l"
        self.sweep_data_filename        = "sweep_data.l"

        #   ___  _   ___  ___ ___   ___  ___  _   _ _____ ___ _  _  ___     _     ___ ___   __  __ _   ___  __  ___ _  _ ___ ___  
        #  | _ \/_\ | _ \/ __| __| | _ \/ _ \| | | |_   _|_ _| \| |/ __|  _| |_  / __| _ ) |  \/  | | | \ \/ / |_ _| \| | __/ _ \ 
        #  |  _/ _ \|   /\__ \ _|  |   / (_) | |_| | | |  | || .` | (_ | |_   _| \__ \ _ \ | |\/| | |_| |>  <   | || .` | _| (_) |
        #  |_|/_/ \_\_|_\|___/___| |_|_\\___/ \___/  |_| |___|_|\_|\___|   |_|   |___/___/ |_|  |_|\___//_/\_\ |___|_|\_|_| \___/ 
        # All general routing wires in the FPGA 
        self.gen_r_wires: List[GenRoutingWire] = []
        # Parse the rrg_file if its passed in and put results into the specs
        if coffe_info.rrg_data_dpath:
            use_rrg = True # Use RRG info for load calculations
            rrg_data_dpath: str = coffe_info.rrg_data_dpath
            seg_csv_fpath = os.path.join(rrg_data_dpath, "rr_segments.csv")
            sw_csv_fpath = os.path.join(rrg_data_dpath, "rr_switches.csv")
            wire_stats_fpath = os.path.join(rrg_data_dpath, "rr_wire_stats.csv")
            # Get in RR segment data
            rr_segments: List[SegmentRRG] = []
            for in_rr_segment in rg_utils.read_csv_to_list(seg_csv_fpath):
                rr_segment: SegmentRRG = rg_utils.typecast_input_to_dataclass(
                    in_rr_segment,
                    SegmentRRG
                )
                rr_segments.append(rr_segment)
            rr_switches: List[SwitchRRG] = []
            for in_rr_sw in rg_utils.read_csv_to_list(sw_csv_fpath):
                rr_sw: SwitchRRG = rg_utils.typecast_input_to_dataclass(
                    in_rr_sw,
                    SwitchRRG
                )
                rr_switches.append(rr_sw)
            # drv_type: num_of_this_mux
            mux_freqs: Dict[str, int] = {}

            rr_wire_stats: List[dict] = rg_utils.read_csv_to_list(wire_stats_fpath)
            
            mux_stats: List[MuxWireStatRRG] = []
            mux_loads: Dict[str, List[MuxLoadRRG]] = defaultdict(list)
            mux_ipins: Dict[str, List[MuxIPIN]] = defaultdict(list)
            total_mux_inputs: Dict[str, int] = {}
            total_mux_loads: Dict[str, int] = {}

            # list of all possible drive types in csv
            drv_types: List[str] = list(set([wire_stat["DRV_TYPE"].lower() for wire_stat in rr_wire_stats]))
            wire_types: List[str] = list(set([wire_stat["WIRE_TYPE"].lower() for wire_stat in rr_wire_stats]))
            drv_wire_pairs: Set[Tuple[str]] = set()
            # Seperate the input wire statistics into wire types
            for wire_stat in rr_wire_stats:
                # Create a WireStatRRG object for each combination of DRV and WIRE types (Assumpion only one drv type per wire type)
                stat_type: str = (wire_stat["COL_TYPE"]).lower()
                wire_drv_type: str = (wire_stat["DRV_TYPE"]).lower()
                wire_type: str = (wire_stat["WIRE_TYPE"]) # Not lowered as its matching name in config.yml
                # Check if this is component or total fanout
                drv_wire_pairs.add((wire_drv_type, wire_type))
                # Mux load from fanout info
                if "fanout" in stat_type:
                    drv_type = stat_type.replace("fanout_","").lower()
                    if drv_type in stat_type and "total" not in drv_type:
                        # this is component fanout
                        mux_load: MuxLoadRRG = MuxLoadRRG(
                            mux_type=drv_type,
                            freq=int(round(float(wire_stat["mean"])))
                        )
                        mux_loads[wire_type].append(mux_load)
                    elif "total" in stat_type:
                        # For total fanout / fanin values
                        total_mux_loads[wire_type] = int(round(float(wire_stat["mean"])))
                    else:
                        assert False, f"Unknown stat_type {stat_type} in wire_stats.csv"
                elif "fanin" in stat_type:
                    drv_type = stat_type.replace("fanin_","").lower()
                    if drv_type in stat_type and "total" not in drv_type:
                        # this is component fanin
                        mux_ipin: MuxIPIN = MuxIPIN(
                            wire_type=wire_type,
                            drv_type=drv_type,
                            freq=int(round(float(wire_stat["mean"])))
                        )
                        mux_ipins[wire_type].append(mux_ipin)
                    elif "total" in stat_type:
                        # For total fanout / fanin values
                        total_mux_inputs[wire_type] = int(round(float(wire_stat["mean"])))
                    else:
                        assert False, f"Unknown stat_type {stat_type} in wire_stats.csv"
                else:
                    assert False, f"Unknown stat_type {stat_type} in wire_stats.csv"
            for wire_type in mux_loads.keys():
                drv_wire_pair: Tuple[str] = [drv_wire_pair for drv_wire_pair in drv_wire_pairs if drv_wire_pair[1] == wire_type][0]
                # We need to fix the wire types of MUX IPINs as they are showing up as the type of driven wires
                # TODO fix this later in another way
                drv_type: str = drv_wire_pair[0]

                assert wire_type == drv_wire_pair[1], f"Wire type {wire_type} does not match drv type {drv_type}"
                # Create a WireStatRRG object for each wire types
                mux_stat: MuxWireStatRRG = MuxWireStatRRG(
                    wire_type=wire_type,
                    drv_type=drv_type,
                    mux_ipins=mux_ipins[wire_type],
                    mux_loads=mux_loads[wire_type],
                    # total_mux_inputs=total_mux_inputs[wire_type],
                    # total_wire_loads=total_mux_loads[wire_type]
                )
                mux_stats.append(mux_stat)

            # Match up our parsed information for wire information with the wire RC 
            for i, wire_type in enumerate(self.specs.wire_types):
                gen_r_wire: GenRoutingWire
                for seg in rr_segments:
                    if seg.name == wire_type["name"]:
                        # Find the corresponding mux_stat
                        mux_stat: MuxWireStatRRG = [mux_stat for mux_stat in mux_stats if mux_stat.wire_type == wire_type["name"]][0]
                        gen_r_wire = GenRoutingWire(
                            name=seg.name,
                            id=i, # Uses index of this wire_type in conf.yml file
                            length=seg.length,
                            layer=int(wire_type["metal"]),
                            mux_info=mux_stat
                        )
                        self.gen_r_wires.append(gen_r_wire)
                                        
        ##################################
        ### CREATE SWITCH BLOCK OBJECT ###
        ##################################
        # if this list is non empty
        elif self.specs.wire_types:
            # If user specifies sb muxes explicitly priorize that
            if self.specs.sb_muxes: 
                for i, sb_mux_conf in enumerate(self.specs.sb_muxes):
                    # How many inputs does this mux have
                    sb_mux_size_required: int = sum(int(val) for val in sb_mux_conf["srcs"].values()) + int(sb_mux_conf["lb_inputs"])
                    # Make sure its equal to user specified size
                    assert sb_mux_size_required == sb_mux_conf["size"]
                    # How many muxes drive this wire type
                    dst_wire: dict = self.specs.wire_types[sb_mux_conf["dst"]]
                    # Counting the number of muxes in the config with the same dst wire type
                    num_muxes_per_dst_wire: int = sum(1 for sb_mux_cmp in self.specs.sb_muxes if sb_mux_cmp["dst"] == sb_mux_conf["dst"])
                    # How many tracks is this mux type driving per SB
                    # TODO change name this is number of tracks per SB type
                    num_driven_tracks: int = int(dst_wire["num_tracks"] / num_muxes_per_dst_wire )
                    # I Don't think we need to consider the switch points in a wire type, those should be accounted for in the MUX size from user
                    # How many muxes of this type in a tile?
                    num_sb_mux_per_tile: int = int( 4 * num_driven_tracks // (2 * dst_wire["len"]) )
                    # Create the switch block mux
                    sb_mux_name = f"sb_mux_uid{i}"
                    self.sb_muxes.append(
                        _SwitchBlockMUX(sb_mux_conf["size"], num_sb_mux_per_tile, self.specs.use_tgate, sb_mux_name, self.specs.wire_types[sb_mux_conf["srcs"]], dst_wire)
                    )
            # if we specify multiple wire types, we need an Fs_mtx of quadratic length to specify each wire type Fs in switch block
            elif len(self.specs.wire_types)**2 == len(self.specs.Fs_mtx):
                # We create this many muxes that exist in the FPGA
                # <TAG><SWEEP GENERATE>
                No = self.specs.num_cluster_outputs
                # Calculate Mux size for each combination of wire types
                for i, Fs_ele in enumerate(self.specs.Fs_mtx):
                    # If the Fs is 0, it means we don't have a SB for this wire to wire connection type, ie don't create an SB mux 
                    if Fs_ele["Fs"] == 0:
                        continue
                    # use wire index of source wire for wire length
                    # This determines number of starting / non starting connections 
                    src_wire_length = self.specs.wire_types[Fs_ele["src"]]["len"] # wire going into SB
                    dst_wire_length = self.specs.wire_types[Fs_ele["dst"]]["len"] # wire driven from SB mux
                    r_to_r_sb_mux_size = self.specs.Fs + (self.specs.Fs-1) * (src_wire_length-1) # use the src wire length, as this determines the number of starting wires @ SB
                    # To calculate the num of sb muxes per side we first calculate the number of logic cluster opins per side
                    # dst_chan_width = dst_wire_type_fraction_of_channel * channel_width
                    # num_opins_per_side = cluster_outputs * Fcout * dst_chan_width / 2
                    # the above div by 2 is coming from half the cluster outputs being sent to SBs on each side of the LC (think of the channel above it)
                    # num_sb_muxes_per_side = dst_chan_width / 2 * src_wire_length
                    # the above div by 2 is from the unidirectional routing, meaning half of channel width is being driven 
                    # Below division by two is because we send our outputs to SBs on both sides (L/R) of the LC
                    clb_to_r_sb_mux_size = No * self.specs.Fcout * src_wire_length / 2 # should this be ceiled? TODO this needs to be updated to distribute these connections to the SBs
                    sb_mux_size_required = int(r_to_r_sb_mux_size + clb_to_r_sb_mux_size)
                    # Num tracks driven by this type of SB, if there are N wire types then there will be N^2 SBs, the sum of all SBs driving the same wire type should 
                    #       be equal to the number of tracks of that wire type, so we divide by the sqrt of the number of SBs to get the number of tracks driven by each SB
                    num_driven_tracks = int( self.specs.wire_types[Fs_ele["dst"]]["num_tracks"] / math.sqrt(len(self.specs.Fs_mtx)) )
                    # Calculate number of this switch block mux per tile
                    num_sb_mux_per_tile = 4 * num_driven_tracks // (2 * src_wire_length)
                    # above 4 factor is from number of sides of SB driving wires, 2 is from the unidirectional routing
                    # Sb mux names are based on wire type they are driving
                    sb_mux_name = f"sb_mux_uid{i}" # f"sb_mux_L{dst_wire_length}_Fs_uid{i}"
                    # Initialize the switch block, pass in our dst wire for the load
                    self.sb_muxes.append(
                        _SwitchBlockMUX(sb_mux_size_required, num_sb_mux_per_tile, self.specs.use_tgate, sb_mux_name, self.specs.wire_types[Fs_ele["src"]], self.specs.wire_types[Fs_ele["dst"]])
                    )

        
        ###########################
        ### CREATE LOAD OBJECTS ###
        ###########################

        for i, sb_mux in enumerate(self.sb_muxes):
            # For each type of switch block mux we have in SB we should model a BLE load using that switch block
            #       This is because BLEs are loaded by SB muxes, and we want to know the delay / area of BLE outputs for each of such muxes
            #       Note: We are not assuming that there are this many seperate BLE outputs existing in the device 
            # <TAG><SWEEP MODEL>
            self.cluster_output_loads.append(
                _GeneralBLEOutputLoad(self.sb_muxes, i)
            )
            # Pass in the wire type that the SB mux is driving
            self.routing_wire_loads.append(
                _RoutingWireLoad(sb_mux.dst_r_wire, self.sb_muxes, i)
            )
            # Add the routing wire load objects to the Sb muxes
            self.sb_muxes[i].routing_wire_load = self.routing_wire_loads[i]

        ######################################
        ### CREATE CONNECTION BLOCK OBJECT ###
        ######################################

        # Calculate connection block mux size
        # Size is W*Fcin
        cb_mux_size_required = int(self.specs.W * self.specs.Fcin)
        num_cb_mux_per_tile = self.specs.I
        self.num_cb_muxes_per_tile = num_cb_mux_per_tile
        # # Initialize the connection block
        self.cb_mux = _ConnectionBlockMUX(
            cb_mux_size_required, num_cb_mux_per_tile, 
            self.specs.use_tgate, self.min_len_wire, 
            self.sb_muxes[0], self.routing_wire_loads[0]
        )
        
        ###################################
        ### CREATE LOGIC CLUSTER OBJECT ###
        ###################################

        # Calculate local mux size
        # Local mux size is (inputs + feedback) * population
        local_mux_size_required = int((self.specs.I + self.specs.num_ble_local_outputs * self.specs.N) * self.specs.Fclocal)
        num_local_mux_per_tile = self.specs.N * (self.specs.K + self.specs.independent_inputs)
        self.num_local_muxes_per_tile = num_local_mux_per_tile

        inter_wire_length = 0.5
        # Todo: make this a parameter
        self.skip_size = 5
        self.carry_skip_periphery_count = 0
        if self.specs.enable_carry_chain == 1 and self.specs.carry_chain_type == "skip":
            self.carry_skip_periphery_count = int(math.floor((self.specs.N * self.specs.FAs_per_flut)/self.skip_size))
        
        # initialize the logic cluster
        self.logic_cluster = _LogicCluster(
            self.specs.N, self.specs.K, self.specs.num_ble_general_outputs, self.specs.num_ble_local_outputs, self.specs.Rsel, self.specs.Rfb, 
            local_mux_size_required, num_local_mux_per_tile, self.specs.use_tgate, self.specs.use_finfet, self.specs.use_fluts, 
            self.specs.enable_carry_chain, self.specs.FAs_per_flut, self.carry_skip_periphery_count,
            self.min_len_wire, self.routing_wire_loads[0], self.cluster_output_loads[0], self.sb_muxes[0]
        )
        
 

        # Create cluster output load object (for each wire type)
        # Create routing wire load object (for each wire type)
        # for i, wire in enumerate(self.specs.wire_types):
        #     # Initialize the connection block
        #     # self.cb_muxes.append(
        #     #     _ConnectionBlockMUX(cb_mux_size_required, num_cb_mux_per_tile, self.specs.use_tgate, wire)
        #     # )
        #     # Initialize the logic clusters
        #     # self.logic_clusters.append(
        #     #     _LogicCluster(
        #     #         self.specs.N, self.specs.K, self.specs.num_ble_general_outputs, self.specs.num_ble_local_outputs, self.specs.Rsel, self.specs.Rfb, 
        #     #         local_mux_size_required, num_local_mux_per_tile, self.specs.use_tgate, self.specs.use_finfet, self.specs.use_fluts, 
        #     #         self.specs.enable_carry_chain, self.specs.FAs_per_flut, self.carry_skip_periphery_count,
        #     #         wire
        #     #     )
        #     # )
            
        #     # We create a 
        #     self.cluster_output_loads.append(
        #         _GeneralBLEOutputLoad(wire)
        #     )
        #     self.routing_wire_loads.append(
        #         # Pass in wire length + unique id used for metal_layers dict
        #         _RoutingWireLoad(wire)
        #     )


        ##################################
        ### CREATE CARRY CHAIN OBJECTS ###
        ##################################
        # TODO: Why is the carry chain created here and not in the logic cluster object?

        if self.specs.enable_carry_chain == 1:
            self.carrychain = _CarryChain(self.specs.use_finfet, self.specs.carry_chain_type, self.specs.N, self.specs.FAs_per_flut)
            self.carrychainperf = _CarryChainPer(self.specs.use_finfet, self.specs.carry_chain_type, self.specs.N, self.specs.FAs_per_flut, self.specs.use_tgate)
            self.carrychainmux = _CarryChainMux(self.specs.use_finfet, self.specs.use_fluts, self.specs.use_tgate, self.cluster_output_loads[0])
            self.carrychaininter = _CarryChainInterCluster(self.specs.use_finfet, self.specs.carry_chain_type, inter_wire_length)
            if self.specs.carry_chain_type == "skip":
                self.carrychainand = _CarryChainSkipAnd(self.specs.use_finfet, self.specs.use_tgate, self.specs.carry_chain_type, self.specs.N, self.specs.FAs_per_flut, self.skip_size)
                self.carrychainskipmux = _CarryChainSkipMux(self.specs.use_finfet, self.specs.carry_chain_type, self.specs.use_tgate)
        

        #########################
        ### CREATE RAM OBJECT ###
        #########################

        RAM_local_mux_size_required = float(self.specs.ram_local_mux_size)
        RAM_num_mux_per_tile = (3 + 2*(self.specs.row_decoder_bits + self.specs.col_decoder_bits + self.specs.conf_decoder_bits ) + 2** (self.specs.conf_decoder_bits))
        self.RAM = _RAM(self.specs.row_decoder_bits, self.specs.col_decoder_bits, self.specs.conf_decoder_bits, RAM_local_mux_size_required, 
                        RAM_num_mux_per_tile , self.specs.use_tgate, self.specs.sram_cell_area*self.specs.min_width_tran_area, self.specs.number_of_banks,
                        self.specs.memory_technology, self.specs, self.process_data_filename, self.specs.read_to_write_ratio)
        self.number_of_banks = self.specs.number_of_banks

        
        ################################
        ### CREATE HARD BLOCK OBJECT ###
        ################################


        self.hardblocklist = []
        # create hardblocks if the hardblock list is not None
        if coffe_info.hardblocks != None:
            # Check to see which mode of asic flow was specified by the user
            for hb_conf in coffe_info.hardblocks:
                hard_block = _hard_block(hb_conf, self.specs.use_tgate)
                self.hardblocklist.append(hard_block)
        # if("asic_hardblock_params" in coffe_params.keys()):
        #     for hb_params in coffe_params["asic_hardblock_params"]["hardblocks"]:
        #         hard_block = _hard_block(hb_params, self.specs.use_tgate, run_options)
        #         self.hardblocklist.append(hard_block)


        ##########################################################
        ### INITIALIZE OTHER VARIABLES, LISTS AND DICTIONARIES ###
        ##########################################################

        self.area_opt_weight = run_options.area_opt_weight
        self.delay_opt_weight = run_options.delay_opt_weight
        self.spice_interface = spice_interface        
        # This is a dictionary of all the transistor sizes in the FPGA ('name': 'size')
        # It will contain the data in xMin transistor width, e.g. 'inv_sb_mux_1_nmos': '2'
        # That means inv_sb_mux_1_nmos is a transistor with 2x minimum width
        self.transistor_sizes = {}
        # This is a list of tuples containing area information for each transistor in the FPGA
        # Tuple: (tran_name, tran_channel_width_nm, tran_drive_strength, tran_area_min_areas, tran_area_nm, tran_width_nm)
        self.transistor_area_list = []
        
        # A note on the following 5 dictionaries
        # (area_dict, width_dict, wire_lengths, wire_layers, wire_rc_dict)
        #
        # Transistor sizes and wire lengths are needed at many different places in the SPICE netlists
        # that COFFE creates (e.g. the size of a particular transistor might be needed in many 
        # different files or multiple times in the same file). Since it would be a pain to have to 
        # go through every single line in every single file each time we want to change the size of 
        # a transistor (which will happen many thousands of times), COFFE inserts variables in the
        # SPICE netlists that it creates. These variables, which describe transistor sizes and wire 
        # loads, are assigned values in external files (one file for transistor sizes, one for wire loads). 
        # That way, when we change the size of a transistor (or a wire load), we only need to change
        # it in one place, and this change is seen by all SPICE netlists. 
        # The data structures that COFFE uses to keep track of transistor/circuit areas and wire data 
        # use a similar philosophy. That is, the following 5 dictionaries contain information about 
        # all element in the FPGA (all in one place). For ex., if we want to know the area of a switch block
        # multiplexer we ask 'area_dict' (e.g. area_dict['sb_mux']). One of the reasons for doing this
        # is that it makes outputing this data easier. For example, when we want to update that 'wire
        # load file' that the SPICE netlists use, all we need to do is write out wire_rc_dict to that file.
        # But, the 'fpga' object does not know how to update the area and wire data of each subcircuit.
        # Therefore, these dictionaries will be passed into member objects who will populate them as needed.
        # So, that's just something to keep in mind as you go through this code. You'll likely see these
        # dictionaries a lot.
        #
        # This is a dictionary that contains the area of everything for all levels of hierarchy in the FPGA. 
        # It has transistor area, inverter areas, mux areas, switch_block area, tile area.. etc. 
        # ('entity_name': area) All these areas are in nm^2
        self.area_dict = {}
        # This is a dictionary that contains the width of everything (much like area_dict has the areas).
        # ('entity_name': width) All widths are in nm. The width_dict is useful for figuring out wire lengths.
        self.width_dict = {}
        # This dictionary contains the lengths of all the wires in the FPGA. ('wire_name': length). Lengths in nm.
        self.wire_lengths = {}
        # This dictionary contains the metal layer for each wire. ('wire_name': layer)
        # The layer number (an int) is an index that will be used to select the right metal data
        # from the 'metal_stack' (list described below).
        self.wire_layers = {}
        # This dictionary contains wire resistance and capacitance for each wire as a tuple ('wire_name': (R, C))
        self.wire_rc_dict = {}
        
        # This dictionary contains the delays of all subcircuits (i.e. the max of rise and fall)
        # Contrary to the above 5 dicts, this one is not passed down into the other objects.
        # This dictionary is updated by calling 'update_delays()'
        self.delay_dict = {}
        
        # Metal stack. Lowest index is lowest metal layer. COFFE assumes that wire widths increase as we use higher metal layers.
        # For example, wires in metal_stack[1] are assumed to be wider (and/or more spaced) than wires in metal_stack[0]
        # e.g. metal_stack[0] = (R0, C0)
        self.metal_stack = self.specs.metal_stack
        
        # whether or not to use transmission gates
        self.use_tgate = self.specs.use_tgate

        # This is the height of the logic block, once an initial floorplanning solution has been determined, it will be assigned a non-zero value.
        self.lb_height =  0.0

    def debug_print(self,member_str):
        """ This function prints various FPGA class members in a static order s.t they can be easily compared with one another"""
        #wire lengths
        title_buffer = "#"*35
        if(member_str == "wire_lengths"):
            print("%s WIRE LENGTHS %s" % (title_buffer,title_buffer))
            if(not bool(self.wire_lengths)):
                #if empty dict print that
                print("EMPTY PARAM")
            else:
                for k,v in self.wire_lengths.items():
                    print("%s---------------%f" % (k,v))
            print("%s WIRE LENGTHS %s" % (title_buffer,title_buffer))
        elif(member_str == "width_dict"):
            print("%s WIDTH DICTS %s" % (title_buffer,title_buffer))
            if(not bool(self.width_dict)):
                #if empty dict print that
                print("EMPTY PARAM")
            else:
                for k,v in self.width_dict.items():
                    print("%s---------------%f" % (k,v))
            print("%s WIDTH DICTS %s" % (title_buffer,title_buffer))
        

        

    def generate(self, is_size_transistors, size_hb_interfaces):
        """ This function generates all SPICE netlists and library files. """
    
        # Here's a file-stack that shows how COFFE organizes its SPICE files.
        # We'll talk more about each one as we generate them below.
    
        # ---------------------------------------------------------------------------------
        # |                                                                               |
        # |                top-level spice files (e.g. sb_mux.sp)                         |
        # |                                                                               |
        # ---------------------------------------------------------------------------------
        # |                                                                               |
        # |                                includes.l                                     |
        # |                                                                               |
        # ---------------------------------------------------------------------------------
        # |                                                                               |
        # |                               subcircuits.l                                   |
        # |                                                                               |
        # ---------------------------------------------------------------------------------
        # |                         |                               |                     |
        # |     process_data.l      |     basic_subcircuits.l       |     sweep_data.l    |
        # |                         |                               |                     |
        # ---------------------------------------------------------------------------------
    
        # For our logging files we want to clear them on the invocation of COFFE in the arch_out_folder
        # Create empty file
        for cat_k in self.log_out_catagories:
            fd = open(f"{cat_k}_debug.csv", "w")
            fd.close()
        
        # Generate basic subcircuit library (pass-transistor, inverter, wire, etc.).
        # This library will be used to build other netlists.
        self._generate_basic_subcircuits()
        
        # Create 'subcircuits.l' library.
        # The subcircuit generation functions between 'self._create_lib_files()'
        # and 'self._end_lib_files()' will add things to these library files. 
        self._create_lib_files()
        
        # Generate the various subcircuits netlists of the FPGA (call members)

        self.transistor_sizes.update(self.cb_mux.generate(self.subcircuits_filename, 
                                                          self.specs.min_tran_width))
        self.transistor_sizes.update(self.logic_cluster.generate(self.subcircuits_filename, 
                                                                 self.specs.min_tran_width, 
                                                                 self.specs))        
        # Iterate over all existing sb muxes and generate them + cluster / gen routing load collateral 
        for sb_mux in self.sb_muxes:

            # self.transistor_sizes.update(cb_mux.generate(self.subcircuits_filename, 
            #                                               self.specs.min_tran_width))
            
            # self.transistor_sizes.update(logic_cluster.generate(self.subcircuits_filename, 
            #                                                      self.specs.min_tran_width, 
            #                                                      self.specs))

            self.transistor_sizes.update(
                sb_mux.generate(
                    self.subcircuits_filename, 
                    self.specs.min_tran_width
                )
            )
            # sb_mux.generate_top()

        for cluster_output_load in self.cluster_output_loads:
            cluster_output_load.generate(self.subcircuits_filename, self.specs)

        for routing_wire_load in self.routing_wire_loads:
            routing_wire_load.generate(self.subcircuits_filename, self.specs, sb_mux, self.cb_mux)
        

        # self.cb_mux.generate_top()
        # self.logic_cluster.generate_top()
            

        if self.specs.enable_carry_chain == 1:
            self.transistor_sizes.update(self.carrychain.generate(self.subcircuits_filename, self.specs.min_tran_width, self.specs.use_finfet))
            self.transistor_sizes.update(self.carrychainperf.generate(self.subcircuits_filename, self.specs.min_tran_width, self.specs.use_finfet))
            self.transistor_sizes.update(self.carrychainmux.generate(self.subcircuits_filename, self.specs.min_tran_width, self.specs.use_finfet))
            self.transistor_sizes.update(self.carrychaininter.generate(self.subcircuits_filename, self.specs.min_tran_width, self.specs.use_finfet))
            if self.specs.carry_chain_type == "skip":
                self.transistor_sizes.update(self.carrychainand.generate(self.subcircuits_filename, self.specs.min_tran_width, self.specs.use_finfet))
                self.transistor_sizes.update(self.carrychainskipmux.generate(self.subcircuits_filename, self.specs.min_tran_width, self.specs.use_finfet))

        if self.specs.enable_bram_block == 1:
            self.transistor_sizes.update(self.RAM.generate(self.subcircuits_filename, self.specs.min_tran_width, self.specs))

        for hardblock in self.hardblocklist:
            self.transistor_sizes.update(hardblock.generate(self.subcircuits_filename, self.specs.min_tran_width))
        
        # Add file footers to 'subcircuits.l' and 'transistor_sizes.l' libraries.
        self._end_lib_files()
        
        # Create SPICE library that contains process data and voltage level information
        self._generate_process_data()
        
        # This generates an include file. Top-level SPICE netlists only need to include
        # this 'include' file to include all libraries (for convenience).
        self._generate_includes()
        
        # Create the sweep_data.l file. COFFE will use this to perform multi-variable sweeps.
        self._generate_sweep_data()
        

        # Post generation of spice libraries we need to parse them into our data structures to be able to write the circuit testing environments
        # Setting up inputs for the parser function
        # parser_args = {
        #     "input_sp_files": [self.basic_subcircuits_filename, self.subcircuits_filename],
        #     "get_structs": True,
        # }
        parser_args = [
            "--input_sp_files",  self.basic_subcircuits_filename, self.subcircuits_filename,
            "--get_structs",
        ]
        self.all_subckts = sp_parser.main(parser_args)


        # Generate top-level files. These top-level files are the files that COFFE uses to measure 
        # the delay of FPGA circuitry
        for sb_mux in self.sb_muxes:
            sb_mux.generate_top(self.all_subckts)
        
        self.cb_mux.generate_top()
        self.logic_cluster.generate_top(self.all_subckts)

        if self.specs.enable_carry_chain == 1:
            self.carrychain.generate_top()
            self.carrychainperf.generate_top()
            self.carrychainmux.generate_top(self.min_len_wire)
            self.carrychaininter.generate_top()
            if self.specs.carry_chain_type == "skip":
                self.carrychainand.generate_top()
                self.carrychainskipmux.generate_top()

        # RAM
        if self.specs.enable_bram_block == 1:
            self.RAM.generate_top()

        for hardblock in self.hardblocklist:
            hardblock.generate_top(size_hb_interfaces)

        # Calculate area, and wire data.
        print("Calculating area...")
        # Update area values
        self.update_area()
        print("Calculating wire lengths...")
        self.update_wires()
        print("Calculating wire resistance and capacitance...")
        self.update_wire_rc()
    
        print("")
        

    def update_area(self):
        """ This function updates self.area_dict. It passes area_dict to member objects (like sb_mux)
            to update their area. Then, with an up-to-date area_dict it, calculate total tile area. """
        
        # FPGA level update area log str
        # top_log_str = "AREA"

        # We use the self.transistor_sizes to compute area. This dictionary has the form 'name': 'size'
        # And it knows the transistor sizes of all transistors in the FPGA
        # We first need to calculate the area for each transistor.
        # This function stores the areas in the transistor_area_list
        self._update_area_per_transistor()
        # Now, we have to update area_dict and width_dict with the new transistor area values
        # for the basic subcircuits which are inverteres, ptran, tgate, restorers and transistors
        self._update_area_and_width_dicts()
        #I found that printing width_dict here and comparing against golden results was helpful
        #self.debug_print("width_dict")

        # Calculate area of SRAM
        self.area_dict["sram"] = self.specs.sram_cell_area * self.specs.min_width_tran_area
        self.area_dict["ramsram"] = 5 * self.specs.min_width_tran_area
        #MTJ in terms of min transistor width
        self.area_dict["rammtj"] = 1.23494 * self.specs.min_width_tran_area
        self.area_dict["mininv"] =  3 * self.specs.min_width_tran_area
        self.area_dict["ramtgate"] =  3 * self.area_dict["mininv"]


        # carry chain:
        if self.specs.enable_carry_chain == 1:
            self.carrychainperf.update_area(self.area_dict, self.width_dict)
            self.carrychainmux.update_area(self.area_dict, self.width_dict)
            self.carrychaininter.update_area(self.area_dict, self.width_dict)
            self.carrychain.update_area(self.area_dict, self.width_dict)
            if self.specs.carry_chain_type == "skip":
                self.carrychainand.update_area(self.area_dict, self.width_dict)
                self.carrychainskipmux.update_area(self.area_dict, self.width_dict)


        # Call area calculation functions of sub-blocks
        for sb_mux in self.sb_muxes:
            sb_mux.update_area(self.area_dict, self.width_dict)
        # Connection Block Mux
        self.cb_mux.update_area(self.area_dict, self.width_dict)
        # Logic Cluster Mux
        self.logic_cluster.update_area(self.area_dict, self.width_dict)



        for hardblock in self.hardblocklist:
            hardblock.update_area(self.area_dict, self.width_dict)
        
        if self.specs.enable_bram_block == 1:
            self.RAM.update_area(self.area_dict, self.width_dict)
        
        # Calculate total area of switch block
        switch_block_area = 0
        switch_block_area_no_sram = 0
        switch_block_avg_area = 0
        # weighted avg area of switch blocks based on percentage of SB mux occurances
        # Add up areas of all switch blocks of all types
        for i, sb_mux in enumerate(self.sb_muxes):
            # For weighted average use the number of tracks per wire length corresponding SB / total tracks as the weight 
            # Weight Factor * SB Mux Area w/ SRAM
            switch_block_avg_area += ((sb_mux.num_per_tile) / sum([sb_mux.num_per_tile for sb_mux in self.sb_muxes])) * self.area_dict[sb_mux.name]
            switch_block_area += sb_mux.num_per_tile * self.area_dict[sb_mux.name + "_sram"]
            switch_block_area_no_sram += sb_mux.num_per_tile * self.area_dict[sb_mux.name]

        # SB should never have area of 0 after this point
        assert switch_block_area != 0 and switch_block_area_no_sram != 0 and switch_block_avg_area != 0, "Switch block area is 0, error in SB area calculation"
        self.area_dict["sb_mux_avg"] = switch_block_avg_area # avg_sb_mux area with NO SRAM 
        self.area_dict["sb_total_no_sram"] = switch_block_area_no_sram
        self.area_dict["sb_total"] = switch_block_area
        self.width_dict["sb_total"] = math.sqrt(switch_block_area)
        
        # connection_block_area = 0
        # connection_block_area_no_sram = 0
        # <CB TAG> Change here to change how combined area of different connection blocks is calculated
        # Calculate total area of connection block
        # for i, cb_mux in enumerate(self.cb_muxes):
        #     # The number of connection blocks per tile will always be the same regardless of channel width / wire length but to get the area we should take weighted average of multiple wire types
        #     connection_block_area += (self.specs.wire_types[i]["num_tracks"]/self.specs.W) * cb_mux.num_per_tile * self.area_dict[cb_mux.name + "_sram"]
        #     connection_block_area_no_sram += (self.specs.wire_types[i]["num_tracks"]/self.specs.W) * cb_mux.num_per_tile*self.area_dict[cb_mux.name]
        
        
        
        connection_block_area = self.cb_mux.num_per_tile * self.area_dict[self.cb_mux.name + "_sram"]
        connection_block_area_no_sram = self.cb_mux.num_per_tile * self.area_dict[self.cb_mux.name]
        self.area_dict["cb_total"] = connection_block_area
        self.area_dict["cb_total_no_sram"] = connection_block_area_no_sram
        self.width_dict["cb_total"] = math.sqrt(connection_block_area)
        
        # This is checking if we are intializing the areas or iterating on them, self.lb_height should only == 0 if the FPGA object was just intialized
        if self.lb_height == 0.0:        
            # Again take weighted average for each wire type
            # The number of local muxes per tile will always be the same regardless of channel width / wire length but to get the area we should take weighted average of multiple wire types
            
            # UNCOMMENT FOR MULTI LOCAL MUX & LOGIC CLUSTER
            # local_mux_area = 0
            # local_mux_area_no_sram = 0
            # ff_area = 0
            # for i, logic_cluster in enumerate(self.logic_clusters):
            #     # Calculate total area of local muxes
            #     local_mux_area += (logic_cluster.gen_r_wire["num_tracks"] / self.specs.W) * logic_cluster.local_mux.num_per_tile * self.area_dict[logic_cluster.local_mux.name + "_sram"]
            #     local_mux_area_no_sram += (logic_cluster.gen_r_wire["num_tracks"] / self.specs.W) * logic_cluster.local_mux.num_per_tile * self.area_dict[logic_cluster.local_mux.name]
            #     # Calculate total ff area
            #     ff_area += (logic_cluster.gen_r_wire["num_tracks"] / self.specs.W) * self.specs.N * self.area_dict[logic_cluster.ble.ff.name]

            # local_mux_area = self.logic_cluster.local_mux.num_per_tile*self.area_dict[self.logic_cluster.local_mux.name + "_sram"]
            # Local Muxes
            # self.area_dict["local_mux_total"] = local_mux_area
            # self.width_dict["local_mux_total"] = math.sqrt(local_mux_area)
            
            # Flip FLops
            # self.area_dict["ff_total"] = ff_area
            # self.width_dict["ff_total"] = math.sqrt(ff_area)
            
            # Calculate total area of local muxes
            local_mux_area = self.logic_cluster.local_mux.num_per_tile * self.area_dict[self.logic_cluster.local_mux.name + "_sram"]
            local_mux_area_no_sram = self.logic_cluster.local_mux.num_per_tile * self.area_dict[self.logic_cluster.local_mux.name]
            self.area_dict["local_mux_total_no_sram"] = local_mux_area_no_sram
            self.area_dict["local_mux_total"] = local_mux_area
            self.width_dict["local_mux_total"] = math.sqrt(local_mux_area)
            
            # Calculate total lut area
            lut_area = self.specs.N * self.area_dict["lut_and_drivers"]
            self.area_dict["lut_total"] = lut_area
            self.width_dict["lut_total"] = math.sqrt(lut_area)

            # Calculate total ff area
            ff_area = self.specs.N * self.area_dict[self.logic_cluster.ble.ff.name]
            self.area_dict["ff_total"] = ff_area
            self.width_dict["ff_total"] = math.sqrt(ff_area)
            
            # Calcualte total ble output area
            ble_output_area = self.specs.N * self.area_dict["ble_output"]
            self.area_dict["ble_output_total"] = ble_output_area
            self.width_dict["ble_output_total"] = math.sqrt(ble_output_area)
            
            # Calculate area of logic cluster
            cluster_area = local_mux_area + self.specs.N * self.area_dict["ble"]
            if self.specs.enable_carry_chain == 1:
                cluster_area += self.area_dict["carry_chain_inter"]

            # Init these here to keep our csv dimensions consistent
            self.area_dict["cc_area_total"] = 0
            self.width_dict["cc_area_total"] = 0

            self.area_dict["ffableout_area_total"] = 0
            self.width_dict["ffableout_area_total"] = 0

        else:

            # lets do it assuming a given order for the wire updates and no minimum width on sram size.
            # sb_area_total = self.sb_mux.num_per_tile*self.area_dict[self.sb_mux.name]
            # sb_area_sram =  self.sb_mux.num_per_tile*self.area_dict[self.sb_mux.name + "_sram"] - sb_area_total
            # cb_area_total = self.cb_mux.num_per_tile*self.area_dict[self.cb_mux.name]
            # cb_area_total_sram = self.cb_mux.num_per_tile*self.area_dict[self.cb_mux.name + "_sram"] - cb_area_total

            # local_mux_area = 0
            # local_mux_sram_area = 0
            # ff_total_area = 0

            # This is the local mux area without srams
            # for logic_cluster in self.logic_clusters:
            #     # local mux area calculation
            #     local_mux_area += (logic_cluster.gen_r_wire["num_tracks"] / self.specs.W) * logic_cluster.local_mux.num_per_tile * self.area_dict[logic_cluster.local_mux.name]            
            #     local_mux_sram_area += (logic_cluster.gen_r_wire["num_tracks"] / self.specs.W) * logic_cluster.local_mux.num_per_tile * (self.area_dict[logic_cluster.local_mux.name + "_sram"] - self.area_dict[logic_cluster.local_mux.name])
            #     # BLE flip flop area calculation
            #     ff_total_area += (logic_cluster.gen_r_wire["num_tracks"] / self.specs.W) * self.specs.N * self.area_dict[logic_cluster.ble.ff.name]

            # Overriding above
            local_mux_area = self.logic_cluster.local_mux.num_per_tile * self.area_dict[self.logic_cluster.local_mux.name]            
            local_mux_sram_area = self.logic_cluster.local_mux.num_per_tile * (self.area_dict[self.logic_cluster.local_mux.name + "_sram"] - self.area_dict[self.logic_cluster.local_mux.name])
            # Calculate total area of local muxes
            self.area_dict["local_mux_total_no_sram"] = local_mux_area


            lut_area = self.specs.N * self.area_dict["lut_and_drivers"] - self.specs.N * (2**self.specs.K) * self.area_dict["sram"]
            lut_area_sram = self.specs.N * (2**self.specs.K) * self.area_dict["sram"]

            # For some reason we multiply the FF area by two if its a finfet?
            ffableout_area_total = self.specs.N * self.area_dict[self.logic_cluster.ble.ff.name]
            if self.specs.use_fluts:
                ffableout_area_total = 2 * ffableout_area_total
            ffableout_area_total = ffableout_area_total + self.specs.N * (self.area_dict["ble_output"])

            cc_area_total = 0.0
            skip_size = 5
            self.carry_skip_periphery_count = int(math.floor((self.specs.N * self.specs.FAs_per_flut)//skip_size))
            if self.specs.enable_carry_chain == 1:
                if self.carry_skip_periphery_count == 0 or self.specs.carry_chain_type == "ripple":
                    cc_area_total =  self.specs.N * (self.area_dict["carry_chain"] * self.specs.FAs_per_flut + (self.specs.FAs_per_flut) * self.area_dict["carry_chain_mux"])
                else:
                    cc_area_total =  self.specs.N *(self.area_dict["carry_chain"] * self.specs.FAs_per_flut + (self.specs.FAs_per_flut) * self.area_dict["carry_chain_mux"])
                    cc_area_total = cc_area_total + ((self.area_dict["xcarry_chain_and"] + self.area_dict["xcarry_chain_mux"]) * self.carry_skip_periphery_count)
                cc_area_total = cc_area_total + self.area_dict["carry_chain_inter"]

            cluster_area = local_mux_area + local_mux_sram_area + ffableout_area_total + cc_area_total + lut_area + lut_area_sram


            self.area_dict["cc_area_total"] = cc_area_total
            self.width_dict["cc_area_total"] = math.sqrt(cc_area_total)

            self.area_dict["local_mux_total"] = local_mux_area + local_mux_sram_area
            self.width_dict["local_mux_total"] = math.sqrt(local_mux_area + local_mux_sram_area)

            self.area_dict["lut_total"] = lut_area + self.specs.N * (2**self.specs.K) * self.area_dict["sram"]
            self.width_dict["lut_total"] = math.sqrt(lut_area + self.specs.N * (2**self.specs.K) * self.area_dict["sram"])

            self.area_dict["ff_total"] = self.specs.N * self.area_dict[self.logic_cluster.ble.ff.name]
            self.width_dict["ff_total"] = math.sqrt(self.specs.N * self.area_dict[self.logic_cluster.ble.ff.name])

            self.area_dict["ffableout_area_total"] = ffableout_area_total
            self.width_dict["ffableout_area_total"] = math.sqrt(ffableout_area_total)

            self.area_dict["ble_output_total"] = self.specs.N * (self.area_dict["ble_output"])
            self.width_dict["ble_output_total"] = math.sqrt(self.specs.N * (self.area_dict["ble_output"]))

        self.area_dict["logic_cluster"] = cluster_area
        self.width_dict["logic_cluster"] = math.sqrt(cluster_area)

        if self.specs.enable_carry_chain == 1:
            # Calculate Carry Chain Area
            # already included in bles, extracting for the report
            carry_chain_area = self.specs.N * ( self.specs.FAs_per_flut * self.area_dict["carry_chain"] + (self.specs.FAs_per_flut) * self.area_dict["carry_chain_mux"]) + self.area_dict["carry_chain_inter"]
            if self.specs.carry_chain_type == "skip":
                self.carry_skip_periphery_count = int(math.floor((self.specs.N * self.specs.FAs_per_flut) / self.skip_size))
                carry_chain_area += self.carry_skip_periphery_count *(self.area_dict["xcarry_chain_and"] + self.area_dict["xcarry_chain_mux"])
            self.area_dict["total_carry_chain"] = carry_chain_area
        
        # Calculate tile area
        tile_area = switch_block_area + connection_block_area + cluster_area 

        self.area_dict["tile"] = tile_area
        self.width_dict["tile"] = math.sqrt(tile_area)

        
        if self.specs.enable_bram_block == 1:
            # TODO update this for multi wire types
            # Calculate RAM area:

            # LOCAL MUX + FF area
            RAM_local_mux_area = self.RAM.RAM_local_mux.num_per_tile * self.area_dict[self.RAM.RAM_local_mux.name + "_sram"] + self.area_dict[self.logic_cluster.ble.ff.name]
            self.area_dict["ram_local_mux_total"] = RAM_local_mux_area
            self.width_dict["ram_local_mux_total"] = math.sqrt(RAM_local_mux_area)

            # SB and CB in the RAM tile:
            RAM_area =(RAM_local_mux_area + self.area_dict[self.cb_mux.name + "_sram"] * self.RAM.ram_inputs + (2** (self.RAM.conf_decoder_bits + 3)) *self.area_dict[self.sb_mux.name + "_sram"]) 
            RAM_SB_area = 2 ** (self.RAM.conf_decoder_bits + 3) * self.area_dict[self.sb_mux.name + "_sram"] 
            RAM_CB_area =  self.area_dict[self.cb_mux.name + "_sram"] * self.RAM.ram_inputs 


            self.area_dict["level_shifters"] = self.area_dict["level_shifter"] * self.RAM.RAM_local_mux.num_per_tile
            self.area_dict["RAM_SB"] = RAM_SB_area
            self.area_dict["RAM_CB"] = RAM_CB_area
            # Row decoder area calculation
 
            RAM_decoder_area = 0.0
            RAM_decoder_area += self.area_dict["rowdecoderstage0"]
            #if there is a predecoder, add its area
            if self.RAM.valid_row_dec_size3 == 1:
                RAM_decoder_area += self.area_dict["rowdecoderstage13"]
            #if there is a predecoder, add its area
            if self.RAM.valid_row_dec_size2 == 1:
                RAM_decoder_area += self.area_dict["rowdecoderstage12"]
            #if there is a predecoder, add its area
            RAM_decoder_area += self.area_dict["rowdecoderstage3"]
            # There are two decoders in a dual port circuit:
            RAM_area += RAM_decoder_area * 2 
            # add the actual array area to total RAM area
            self.area_dict["memorycell_total"] = self.area_dict["memorycell"]
            RAM_area += self.area_dict["memorycell_total"]

            if self.RAM.memory_technology == "SRAM":
            # add precharge, write driver, and sense amp area to total RAM area
                self.area_dict["precharge_total"] = (self.area_dict[self.RAM.precharge.name] * 2* (2**(self.RAM.conf_decoder_bits+self.RAM.col_decoder_bits))) * self.number_of_banks
                # several components will be doubled for the largest decoder size to prevent a large amount of delay.
                if self.RAM.row_decoder_bits == 9:
                    self.area_dict["precharge_total"] = 2 * self.area_dict["precharge_total"]
                self.area_dict["samp_total"] = self.area_dict[self.RAM.samp.name] * 2* 2**(self.RAM.conf_decoder_bits) * self.number_of_banks 
                self.area_dict["writedriver_total"] = self.area_dict[self.RAM.writedriver.name] * 2* 2**(self.RAM.conf_decoder_bits) * self.number_of_banks 
                RAM_area += (self.area_dict["precharge_total"] + self.area_dict["samp_total"] + self.area_dict["writedriver_total"])
                self.area_dict["columndecoder_total"] = ((self.area_dict["ramtgate"] * 4 *  (2**(self.RAM.conf_decoder_bits+self.RAM.col_decoder_bits))) / (2**(self.RAM.col_decoder_bits))) + self.area_dict["columndecoder"] * 2 
            
            else:
                # In case of MTJ, banks can share sense amps so we don't have mutlitplication by two
                self.area_dict["samp_total"] = self.area_dict["mtj_subcircuits_sa"] * 2**(self.RAM.conf_decoder_bits) * self.number_of_banks 
                # Write driver can't be shared:
                self.area_dict["writedriver_total"] = self.area_dict["mtj_subcircuits_writedriver"] * 2* 2**(self.RAM.conf_decoder_bits) * self.number_of_banks 
                self.area_dict["cs_total"] = self.area_dict["mtj_subcircuits_cs"] * 2* 2**(self.RAM.conf_decoder_bits +self.RAM.col_decoder_bits) * self.number_of_banks 
                if self.RAM.row_decoder_bits == 9:
                    self.area_dict["cs_total"] = 2 * self.area_dict["cs_total"]

                self.area_dict["columndecoder_total"] = self.area_dict["columndecoder"] * 2 
                RAM_area +=  self.area_dict["samp_total"] + self.area_dict["writedriver_total"] + self.area_dict["cs_total"]

            self.area_dict["columndecoder_sum"] = self.area_dict["columndecoder_total"] * self.number_of_banks 
            RAM_area += self.area_dict["columndecoder_sum"]
            #configurable decoder:
            RAM_configurabledecoder_area = self.area_dict[self.RAM.configurabledecoderi.name + "_sram"]
            if self.RAM.cvalidobj1 == 1:
                RAM_configurabledecoder_area += self.area_dict[self.RAM.configurabledecoder3ii.name]
            if self.RAM.cvalidobj2 == 1:
                RAM_configurabledecoder_area += self.area_dict[self.RAM.configurabledecoder2ii.name]
            self.area_dict["configurabledecoder_wodriver"] = RAM_configurabledecoder_area
            self.width_dict["configurabledecoder_wodriver"] = math.sqrt(self.area_dict["configurabledecoder_wodriver"])
            RAM_configurabledecoder_area += self.area_dict[self.RAM.configurabledecoderiii.name]
            if self.number_of_banks == 2:
                RAM_configurabledecoder_area = RAM_configurabledecoder_area * 2
            RAM_area += 2 * RAM_configurabledecoder_area 

            # add the output crossbar area:
            RAM_area += self.area_dict[self.RAM.pgateoutputcrossbar.name + "_sram"] 
            # add the wordline drivers:
            RAM_wordlinedriver_area = self.area_dict[self.RAM.wordlinedriver.name] * self.number_of_banks
            # we need 2 wordline drivers per row, since there are 2 wordlines in each row to control 2 BRAM ports, respectively
            RAM_wordlinedriver_area = RAM_wordlinedriver_area * 2 
            RAM_area += self.area_dict["level_shifters"]
            RAM_area += RAM_wordlinedriver_area

            # write into dictionaries:
            self.area_dict["wordline_total"] = RAM_wordlinedriver_area
            self.width_dict["wordline_total"] = math.sqrt(RAM_wordlinedriver_area)
            self.area_dict["configurabledecoder"] = RAM_configurabledecoder_area
            self.width_dict["configurabledecoder"] = math.sqrt(RAM_configurabledecoder_area)
            self.area_dict["decoder"] = RAM_decoder_area 
            self.area_dict["decoder_total"] = RAM_decoder_area * 2 
            self.width_dict["decoder"] = math.sqrt(RAM_decoder_area)
            self.area_dict["ram"] = RAM_area
            self.area_dict["ram_core"] = RAM_area - RAM_SB_area - RAM_CB_area
            self.width_dict["ram"] = math.sqrt(RAM_area) 
        
        if self.lb_height != 0.0:  
            self.compute_distance()

        # Area logging
        self.update_area_cnt += 1
        # for area_key, area_value in self.area_dict.items():
        #     rg_utils.custom_log(self.logger, area_value, top_log_str, area_key)

        # Width Logging
        # for area_key, area_value in self.area_dict.items():
        #     rg_utils.custom_log(self.logger, area_value, top_log_str, area_key)
        #self.debug_print("width_dict")

    def compute_distance(self):
        """ This function computes distances for different stripes for the floorplanner:

        """
        # todo: move these to user input
        self.stripe_order = ["sb_sram","sb","sb", "cb", "cb_sram","ic_sram", "ic","lut_sram", "lut", "cc","ffble", "lut", "lut_sram", "ic", "ic_sram", "cb_sram", "cb", "sb","sb", "sb_sram"]
        #self.stripe_order = ["cb", "cb_sram","ic_sram", "ic","lut_sram", "lut", "cc","ffble", "sb", "sb_sram"]
        self.span_stripe_fraction = 10


        self.num_cb_stripes = 0
        self.num_sb_stripes = 0
        self.num_ic_stripes = 0
        self.num_lut_stripes = 0
        self.num_ffble_stripes = 0
        self.num_cc_stripes = 0
        self.num_cbs_stripes = 0
        self.num_sbs_stripes = 0
        self.num_ics_stripes = 0
        self.num_luts_stripes = 0
        #find the number of each stripe type in the given arrangement:
        for item in self.stripe_order:
            if item == "sb":
                self.num_sb_stripes =  self.num_sb_stripes + 1
            elif item == "cb":
                self.num_cb_stripes =  self.num_cb_stripes + 1
            elif item == "ic":
                self.num_ic_stripes =  self.num_ic_stripes + 1
            elif item == "lut":
                self.num_lut_stripes =  self.num_lut_stripes + 1
            elif item == "cc":
                self.num_cc_stripes =  self.num_cc_stripes + 1
            elif item == "ffble":
                self.num_ffble_stripes =  self.num_ffble_stripes + 1
            elif item == "sb_sram":
                self.num_sbs_stripes =  self.num_sbs_stripes + 1
            elif item == "cb_sram":
                self.num_cbs_stripes =  self.num_cbs_stripes + 1
            elif item == "ic_sram":
                self.num_ics_stripes =  self.num_ics_stripes + 1
            elif item == "lut_sram":
                self.num_luts_stripes =  self.num_luts_stripes + 1

        # measure the width of each stripe:
        self.w_cb = self.cb_mux.num_per_tile * self.area_dict[self.cb_mux.name] / (self.num_cb_stripes * self.lb_height)
        # width of switch block
        num_sbs_all_types_per_tile = sum([sb_mux.num_per_tile for sb_mux in self.sb_muxes])
        # We take the summed avg of sb area to determine the width of each sb (this is a simplification)
        self.w_sb = num_sbs_all_types_per_tile * self.area_dict["sb_mux_avg"] / (self.num_sb_stripes * self.lb_height)
        self.w_ic = (self.logic_cluster.local_mux.num_per_tile * self.area_dict[self.logic_cluster.local_mux.name]) / (self.num_ic_stripes * self.lb_height)
        self.w_lut = (self.specs.N * self.area_dict["lut_and_drivers"] - self.specs.N * (2**self.specs.K) * self.area_dict["sram"]) / (self.num_lut_stripes * self.lb_height)
        #if self.specs.enable_carry_chain == 1:
        self.w_cc = self.area_dict["cc_area_total"] / (self.num_cc_stripes * self.lb_height)
        self.w_ffble = self.area_dict["ffableout_area_total"] / (self.num_ffble_stripes * self.lb_height)
        # These are SRAM widths from subcircuits
        self.w_scb = (self.area_dict["cb_total"] - self.area_dict["cb_total_no_sram"]) / (self.num_cbs_stripes * self.lb_height)
        self.w_ssb = (self.area_dict["sb_total"] - self.area_dict["sb_total_no_sram"]) / (self.num_sbs_stripes * self.lb_height)

        self.w_sic = (self.logic_cluster.local_mux.num_per_tile * (self.area_dict[self.logic_cluster.local_mux.name + "_sram"] - self.area_dict[self.logic_cluster.local_mux.name])) / (self.num_ics_stripes * self.lb_height)
        self.w_slut = (self.specs.N * (2**self.specs.K) * self.area_dict["sram"]) / (self.num_luts_stripes * self.lb_height)

        # create a temporary dictionary of stripe width to use in distance calculation:
        self.dict_real_widths = {}
        self.dict_real_widths["sb_sram"] = self.w_ssb
        self.dict_real_widths["sb"] = self.w_sb
        self.dict_real_widths["cb"] = self.w_cb
        self.dict_real_widths["cb_sram"] = self.w_scb
        self.dict_real_widths["ic_sram"] = self.w_sic
        self.dict_real_widths["ic"] = self.w_ic
        self.dict_real_widths["lut_sram"] = self.w_slut
        self.dict_real_widths["lut"] = self.w_lut
        #if self.specs.enable_carry_chain == 1:
        self.dict_real_widths["cc"] = self.w_cc
        self.dict_real_widths["ffble"] = self.w_ffble

        # what distances do we need?
        self.d_cb_to_ic = 0.0 # Used in Logic Cluster update_wires
        self.d_ic_to_lut = 0.0 # Unused
        self.d_lut_to_cc = 0.0 # Unused
        self.d_cc_to_ffble = 0.0 # Unused
        self.d_ffble_to_sb = 0.0 # Used in Cluster Output Load
        self.d_ffble_to_ic = 0.0 # Used in Logic Cluster 

        # worst-case distance between two stripes:
        for index1, item1 in enumerate(self.stripe_order):
            for index2, item2 in enumerate(self.stripe_order):
                if item1 != item2:
                    if (item1 == "cb" and item2 == "ic") or (item1 == "ic" and item2 == "cb"):
                        if index1 < index2:
                            distance_temp = self.dict_real_widths[self.stripe_order[index1]]/self.span_stripe_fraction
                            for i in range(index1 + 1, index2):
                                distance_temp = distance_temp + self.dict_real_widths[self.stripe_order[i]]/self.span_stripe_fraction
                            distance_temp = distance_temp +  self.dict_real_widths[self.stripe_order[index2]]/self.span_stripe_fraction
                        else:
                            distance_temp = self.dict_real_widths[self.stripe_order[index2]]/self.span_stripe_fraction
                            for i in range(index2 + 1, index1):
                                distance_temp = distance_temp + self.dict_real_widths[self.stripe_order[i]]/self.span_stripe_fraction
                            distance_temp = distance_temp + self.dict_real_widths[self.stripe_order[index1]]/self.span_stripe_fraction
                        if self.d_cb_to_ic < distance_temp:
                            self.d_cb_to_ic = distance_temp

                    if (item1 == "lut" and item2 == "ic") or (item1 == "ic" and item2 == "lut"):
                        if index1 < index2:
                            distance_temp = self.dict_real_widths[self.stripe_order[index1]]/self.span_stripe_fraction
                            for i in range(index1 + 1, index2):
                                distance_temp = distance_temp + self.dict_real_widths[self.stripe_order[i]]/self.span_stripe_fraction
                            distance_temp = distance_temp +  self.dict_real_widths[self.stripe_order[index2]]/self.span_stripe_fraction
                        else:
                            distance_temp = self.dict_real_widths[self.stripe_order[index2]]/self.span_stripe_fraction
                            for i in range(index2 + 1, index1):
                                distance_temp = distance_temp + self.dict_real_widths[self.stripe_order[i]]/self.span_stripe_fraction
                            distance_temp = distance_temp + self.dict_real_widths[self.stripe_order[index1]]/self.span_stripe_fraction
                        if self.d_ic_to_lut < distance_temp:
                            self.d_ic_to_lut = distance_temp

                    if (item1 == "lut" and item2 == "cc") or (item1 == "cc" and item2 == "lut"):
                        if index1 < index2:
                            distance_temp = self.dict_real_widths[self.stripe_order[index1]]/self.span_stripe_fraction
                            for i in range(index1 + 1, index2):
                                distance_temp = distance_temp + self.dict_real_widths[self.stripe_order[i]]/self.span_stripe_fraction
                            distance_temp = distance_temp +  self.dict_real_widths[self.stripe_order[index2]]/self.span_stripe_fraction
                        else:
                            distance_temp = self.dict_real_widths[self.stripe_order[index2]]/self.span_stripe_fraction
                            for i in range(index2 + 1, index1):
                                distance_temp = distance_temp + self.dict_real_widths[self.stripe_order[i]]/self.span_stripe_fraction
                            distance_temp = distance_temp + self.dict_real_widths[self.stripe_order[index1]]/self.span_stripe_fraction
                        if self.d_lut_to_cc < distance_temp:
                            self.d_lut_to_cc = distance_temp

                    if (item1 == "ffble" and item2 == "cc") or (item1 == "cc" and item2 == "ffble"):
                        if index1 < index2:
                            distance_temp = self.dict_real_widths[self.stripe_order[index1]]/self.span_stripe_fraction
                            for i in range(index1 + 1, index2):
                                distance_temp = distance_temp + self.dict_real_widths[self.stripe_order[i]]/self.span_stripe_fraction
                            distance_temp = distance_temp +  self.dict_real_widths[self.stripe_order[index2]]/self.span_stripe_fraction
                        else:
                            distance_temp = self.dict_real_widths[self.stripe_order[index2]]/self.span_stripe_fraction
                            for i in range(index2 + 1, index1):
                                distance_temp = distance_temp + self.dict_real_widths[self.stripe_order[i]]/self.span_stripe_fraction
                            distance_temp = distance_temp + self.dict_real_widths[self.stripe_order[index1]]/self.span_stripe_fraction
                        if self.d_cc_to_ffble < distance_temp:
                            self.d_cc_to_ffble = distance_temp                                                                                    

                    if (item1 == "ffble" and item2 == "sb") or (item1 == "sb" and item2 == "ffble"):
                        if index1 < index2:
                            distance_temp = self.dict_real_widths[self.stripe_order[index1]]/self.span_stripe_fraction
                            for i in range(index1 + 1, index2):
                                distance_temp = distance_temp + self.dict_real_widths[self.stripe_order[i]]/self.span_stripe_fraction
                            distance_temp = distance_temp +  self.dict_real_widths[self.stripe_order[index2]]/self.span_stripe_fraction
                        else:
                            distance_temp = self.dict_real_widths[self.stripe_order[index2]]/self.span_stripe_fraction
                            for i in range(index2 + 1, index1):
                                distance_temp = distance_temp + self.dict_real_widths[self.stripe_order[i]]/self.span_stripe_fraction
                            distance_temp = distance_temp + self.dict_real_widths[self.stripe_order[index1]]/self.span_stripe_fraction
                        if self.d_ffble_to_sb < distance_temp:
                            self.d_ffble_to_sb = distance_temp

                    if (item1 == "ffble" and item2 == "ic") or (item1 == "ic" and item2 == "ffble"):
                        if index1 < index2:
                            distance_temp = self.dict_real_widths[self.stripe_order[index1]]/self.span_stripe_fraction
                            for i in range(index1 + 1, index2):
                                distance_temp = distance_temp + self.dict_real_widths[self.stripe_order[i]]/self.span_stripe_fraction
                            distance_temp = distance_temp +  self.dict_real_widths[self.stripe_order[index2]]/self.span_stripe_fraction
                        else:
                            distance_temp = self.dict_real_widths[self.stripe_order[index2]]/self.span_stripe_fraction
                            for i in range(index2 + 1, index1):
                                distance_temp = distance_temp + self.dict_real_widths[self.stripe_order[i]]/self.span_stripe_fraction
                            distance_temp = distance_temp + self.dict_real_widths[self.stripe_order[index1]]/self.span_stripe_fraction
                        if self.d_ffble_to_ic < distance_temp:
                            self.d_ffble_to_ic = distance_temp       
        # Compute Dist logging
        self.compute_distance_cnt += 1
        #print str(self.dict_real_widths["sb"])
        #print str(self.dict_real_widths["cb"])
        #print str(self.dict_real_widths["ic"])
        #print str(self.dict_real_widths["lut"])
        #print str(self.dict_real_widths["cc"])
        #print str(self.dict_real_widths["ffble"])
        #print str(self.lb_height)


    def determine_height(self):

        # if no previous floorplan exists, get an initial height:
        if self.lb_height == 0.0:
            self.lb_height = math.sqrt(self.area_dict["tile"])

        is_done = False
        current_iteration = 0
        max_iteration = 10
        # tweak the current height to find a better one, possibly:
        while is_done == False and current_iteration < max_iteration:
            print("searching for a height for the logic tile " + str(self.lb_height))
            old_height = self.lb_height
            current_best_index = 0
            self.update_area()
            self.update_wires()
            self.update_wire_rc()
            self.update_delays(self.spice_interface)
            old_cost = cost.cost_function(cost.get_eval_area(self, "global", self.sb_mux, 0, 0), cost.get_current_delay(self, 0), self.area_opt_weight, self.delay_opt_weight)
            for i in range (-10,11):
                self.lb_height = old_height + ((0.01 * (i))* old_height)
                self.update_area()
                self.update_wires()
                self.update_wire_rc()
                self.update_delays(self.spice_interface)
                new_cost = cost.cost_function(cost.get_eval_area(self, "global", self.sb_mux, 0, 0), cost.get_current_delay(self, 0), self.area_opt_weight, self.delay_opt_weight)
                if new_cost < old_cost:
                    old_cost = new_cost
                    current_best_index = i
            self.lb_height = (0.01 * (current_best_index))* old_height + old_height
            current_iteration = current_iteration + 1
            if current_best_index == 0:
                is_done = True

        print("found the best tile height: " + str(self.lb_height))

        

    def update_wires(self):
        """ This function updates self.wire_lengths and self.wire_layers. It passes wire_lengths and wire_layers to member 
            objects (like sb_mux) to update their wire lengths and layers. """
        
        # Update wire lengths and layers for all subcircuits



        if self.lb_height == 0:
            # iterate through subcircuits associated with wire types
            for sb_mux, cluster_output_load, routing_wire_load in zip(self.sb_muxes, self.cluster_output_loads, self.routing_wire_loads): 
                sb_mux.update_wires(self.width_dict, self.wire_lengths, self.wire_layers, 1.0)
                cluster_output_load.update_wires(self.width_dict, self.wire_lengths, self.wire_layers, 0.0, 0.0)
                routing_wire_load.update_wires(self.width_dict, self.wire_lengths, self.wire_layers, 0.0, 2.0, 2.0)

            self.cb_mux.update_wires(self.width_dict, self.wire_lengths, self.wire_layers, 1.0)
            self.logic_cluster.update_wires(self.width_dict, self.wire_lengths, self.wire_layers, 1.0, 1.0, 0.0, 0.0)
        else:
            # These ratios seem to be in units of stripes per switch block 
            total_num_sbs_all_types: int = sum([sb_mux.num_per_tile for sb_mux in self.sb_muxes])
            sb_ratio = (self.lb_height / (total_num_sbs_all_types / self.num_sb_stripes)) / self.dict_real_widths["sb"]
            if sb_ratio < 1.0:
                sb_ratio = 1/sb_ratio
			
			#if the ratio is larger than 2.0, we can look at this stripe as two stripes put next to each other and partly fix the ratio:
				
            cb_ratio = (self.lb_height / (self.num_cb_muxes_per_tile / self.num_cb_stripes)) / self.dict_real_widths["cb"]
            if cb_ratio < 1.0:
                cb_ratio = 1/cb_ratio
				
			#if the ratio is larger than 2.0, we can look at this stripe as two stripes put next to each other and partly fix the ratio:

            ic_ratio = (self.lb_height /(self.num_local_muxes_per_tile / self.num_ic_stripes)) / self.dict_real_widths["ic"]
            if ic_ratio < 1.0:
                ic_ratio = 1/ic_ratio
				
			#if the ratio is larger than 2.0, we can look at this stripe as two stripes put next to each other and partly fix the ratio:			

            lut_ratio = (self.lb_height /(self.specs.N / self.num_lut_stripes)) / self.dict_real_widths["lut"]
            if lut_ratio < 1.0:
                lut_ratio = 1/lut_ratio
				
			#if the ratio is larger than 2.0, we can look at this stripe as two stripes put next to each other and partly fix the ratio:
            #sb_ratio = 1.0
            #cb_ratio = 1.0
            #ic_ratio = 1.0
            #lut_ratio = 1.0

            #this was used for debugging so I commented it
            #print "ratios " + str(sb_ratio) +" "+ str(cb_ratio) +" "+ str(ic_ratio) +" "+ str(lut_ratio)
            
            # iterate thorough subckts associated with wire types
            for sb_mux, cluster_output_load, routing_wire_load in zip(self.sb_muxes, self.cluster_output_loads, self.routing_wire_loads):
                sb_mux.update_wires(self.width_dict, self.wire_lengths, self.wire_layers, sb_ratio)
                cluster_output_load.update_wires(self.width_dict, self.wire_lengths, self.wire_layers, self.d_ffble_to_sb, self.lb_height)
                routing_wire_load.update_wires(self.width_dict, self.wire_lengths, self.wire_layers, self.lb_height, self.num_sb_stripes, self.num_cb_stripes)
                # cb_mux.update_wires(self.width_dict, self.wire_lengths, self.wire_layers, cb_ratio)
                # logic_cluster.update_wires(self.width_dict, self.wire_lengths, self.wire_layers, ic_ratio, lut_ratio, self.d_ffble_to_ic, self.d_cb_to_ic + self.lb_height)

            # self.cluster_output_load.update_wires(self.width_dict, self.wire_lengths, self.wire_layers, self.d_ffble_to_sb, self.lb_height)
            # self.sb_mux.update_wires(self.width_dict, self.wire_lengths, self.wire_layers, sb_ratio)
            self.cb_mux.update_wires(self.width_dict, self.wire_lengths, self.wire_layers, cb_ratio)
            self.logic_cluster.update_wires(self.width_dict, self.wire_lengths, self.wire_layers, ic_ratio, lut_ratio, self.d_ffble_to_ic, self.d_cb_to_ic + self.lb_height)
            # self.routing_wire_load.update_wires(self.width_dict, self.wire_lengths, self.wire_layers, self.lb_height, self.num_sb_stripes, self.num_cb_stripes)


        
        if self.specs.enable_carry_chain == 1:
            self.carrychain.update_wires(self.width_dict, self.wire_lengths, self.wire_layers)
            self.carrychainperf.update_wires(self.width_dict, self.wire_lengths, self.wire_layers)
            self.carrychainmux.update_wires(self.width_dict, self.wire_lengths, self.wire_layers)
            self.carrychaininter.update_wires(self.width_dict, self.wire_lengths, self.wire_layers)
            if self.specs.carry_chain_type == "skip":
                self.carrychainand.update_wires(self.width_dict, self.wire_lengths, self.wire_layers)
                self.carrychainskipmux.update_wires(self.width_dict, self.wire_lengths, self.wire_layers)                
        if self.specs.enable_bram_block == 1:
            self.RAM.update_wires(self.width_dict, self.wire_lengths, self.wire_layers)


        for hardblock in self.hardblocklist:
            hardblock.update_wires(self.width_dict, self.wire_lengths, self.wire_layers)  
            hardblock.mux.update_wires(self.width_dict, self.wire_lengths, self.wire_layers)   

        # Update Wires logging
        self.update_wires_cnt += 1
        #self.debug_print("wire_lengths")  

    def update_wire_rc(self):
        """ This function updates self.wire_rc_dict based on the FPGA's self.wire_lengths and self.wire_layers."""
            
        # Calculate R and C for each wire
        for wire, length in self.wire_lengths.items():
            # Get wire layer
            layer = self.wire_layers[wire]
            # Get R and C per unit length for wire layer
            rc = self.metal_stack[layer]
            # Calculate total wire R and C
            resistance = rc[0]*length
            capacitance = rc[1]*length/2
            # Add to wire_rc dictionary
            self.wire_rc_dict[wire] = (resistance, capacitance)    

        # Debug print, this update function is almost always called after update_area and update_wires 
        update_fpga_telemetry_csv(self, get_current_stack_trace(max_height=5))


    #TODO: break this into different functions or form a loop out of it; it's too long
    def update_delays(self, spice_interface):
        """ 
        Get the HSPICE delays for each subcircuit. 
        This function returns "False" if any of the HSPICE simulations failed.
        """
        
        print("*** UPDATING DELAYS ***")
        crit_path_delay = 0
        valid_delay = True

        # Create parameter dict of all current transistor sizes and wire rc
        parameter_dict = {}
        for tran_name, tran_size in self.transistor_sizes.items():
            if not self.specs.use_finfet:
                parameter_dict[tran_name] = [1e-9*tran_size*self.specs.min_tran_width]
            else :
                parameter_dict[tran_name] = [tran_size]

        for wire_name, rc_data in self.wire_rc_dict.items():
            parameter_dict[wire_name + "_res"] = [rc_data[0]]
            parameter_dict[wire_name + "_cap"] = [rc_data[1]*1e-15]

        # Run HSPICE on all subcircuits and collect the total tfall and trise for that 
        # subcircuit. We are only doing a single run on HSPICE so we expect the result
        # to be in [0] of the spice_meas dictionary. We check to make sure that the 
        # HSPICE simulation was successful by checking if any of the SPICE measurements
        # were "failed". If that is the case, we set the delay of that subcircuit to 1
        # second and set our valid_delay flag to False.

        # Switch Block MUX 
        # For each SB mux type in our switch block update delay
        for sb_mux in self.sb_muxes:
            # Debug run this to see what the output is looking like
            print("  Updating delay for " + sb_mux.name)
            spice_meas = spice_interface.run(sb_mux.top_spice_path, parameter_dict)
            if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
                valid_delay = False
                tfall = 1
                trise = 1
            else :  
                tfall = float(spice_meas["meas_total_tfall"][0])
                trise = float(spice_meas["meas_total_trise"][0])
            if tfall < 0 or trise < 0 :
                valid_delay = False
            sb_mux.tfall = tfall
            sb_mux.trise = trise
            sb_mux.delay = max(tfall, trise)
            # sb_mux.avg_crit_path_delay += sb_mux.delay * sb_mux.delay_weight

            # Weighted average depending on how often we would encounter these switch blocks
            sb_mux_ipin_freq_ratio = (sb_mux.num_per_tile * sb_mux.required_size) / sum([sb_mux.num_per_tile * sb_mux.required_size for sb_mux in self.sb_muxes])
            crit_path_delay += sb_mux.delay * sb_mux.delay_weight * sb_mux_ipin_freq_ratio
            # append to FPGA delay
            self.delay_dict[sb_mux.name] = sb_mux.delay 
            sb_mux.power = float(spice_meas["meas_avg_power"][0])
        
        # Connection Block MUX
        print("  Updating delay for " + self.cb_mux.name)
        spice_meas = spice_interface.run(self.cb_mux.top_spice_path, parameter_dict) 
        if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
            valid_delay = False
            tfall = 1
            trise = 1
        else :  
            tfall = float(spice_meas["meas_total_tfall"][0])
            trise = float(spice_meas["meas_total_trise"][0])
        if tfall < 0 or trise < 0 :
            valid_delay = False
        self.cb_mux.tfall = tfall
        self.cb_mux.trise = trise
        self.cb_mux.delay = max(tfall, trise)
        crit_path_delay += self.cb_mux.delay*self.cb_mux.delay_weight
        self.delay_dict[self.cb_mux.name] = self.cb_mux.delay
        self.cb_mux.power = float(spice_meas["meas_avg_power"][0])
        
        # Local MUX
        print("  Updating delay for " + self.logic_cluster.local_mux.name)
        spice_meas = spice_interface.run(self.logic_cluster.local_mux.top_spice_path, 
                                         parameter_dict) 
        if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
            valid_delay = False
            tfall = 1
            trise = 1
        else :  
            tfall = float(spice_meas["meas_total_tfall"][0])
            trise = float(spice_meas["meas_total_trise"][0])
        if tfall < 0 or trise < 0 :
            valid_delay = False
        self.logic_cluster.local_mux.tfall = tfall
        self.logic_cluster.local_mux.trise = trise
        self.logic_cluster.local_mux.delay = max(tfall, trise)
        crit_path_delay += (self.logic_cluster.local_mux.delay*
                            self.logic_cluster.local_mux.delay_weight)
        self.delay_dict[self.logic_cluster.local_mux.name] = self.logic_cluster.local_mux.delay
        self.logic_cluster.local_mux.power = float(spice_meas["meas_avg_power"][0])
        
        # Local BLE output
        print("  Updating delay for " + self.logic_cluster.ble.local_output.name) 
        spice_meas = spice_interface.run(self.logic_cluster.ble.local_output.top_spice_path, 
                                         parameter_dict) 
        if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
            valid_delay = False
            tfall = 1
            trise = 1
        else:  
            tfall = float(spice_meas["meas_total_tfall"][0])
            trise = float(spice_meas["meas_total_trise"][0])
        if tfall < 0 or trise < 0 :
            valid_delay = False
        self.logic_cluster.ble.local_output.tfall = tfall
        self.logic_cluster.ble.local_output.trise = trise
        self.logic_cluster.ble.local_output.delay = max(tfall, trise)
        crit_path_delay += (self.logic_cluster.ble.local_output.delay*
                            self.logic_cluster.ble.local_output.delay_weight)
        self.delay_dict[self.logic_cluster.ble.local_output.name] = self.logic_cluster.ble.local_output.delay
        self.logic_cluster.ble.local_output.power = float(spice_meas["meas_avg_power"][0])
        
        # General BLE output
        print("  Updating delay for " + self.logic_cluster.ble.general_output.name)
        spice_meas = spice_interface.run(self.logic_cluster.ble.general_output.top_spice_path, 
                                         parameter_dict) 
        if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
            valid_delay = False
            tfall = 1
            trise = 1
        else :  
            tfall = float(spice_meas["meas_total_tfall"][0])
            trise = float(spice_meas["meas_total_trise"][0])
        if tfall < 0 or trise < 0 :
            valid_delay = False
        self.logic_cluster.ble.general_output.tfall = tfall
        self.logic_cluster.ble.general_output.trise = trise
        self.logic_cluster.ble.general_output.delay = max(tfall, trise)
        crit_path_delay += (self.logic_cluster.ble.general_output.delay*
                            self.logic_cluster.ble.general_output.delay_weight)
        self.delay_dict[self.logic_cluster.ble.general_output.name] = self.logic_cluster.ble.general_output.delay
        self.logic_cluster.ble.general_output.power = float(spice_meas["meas_avg_power"][0])
        

        #fmux
        #print self.specs.use_fluts 
        # fracturable lut mux
        if self.specs.use_fluts:
            print("  Updating delay for " + self.logic_cluster.ble.fmux.name)
            spice_meas = spice_interface.run(self.logic_cluster.ble.fmux.top_spice_path, 
                                             parameter_dict) 
            if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
                valid_delay = False
                tfall = 1
                trise = 1
            else :  
                tfall = float(spice_meas["meas_total_tfall"][0])
                trise = float(spice_meas["meas_total_trise"][0])
            if tfall < 0 or trise < 0 :
                valid_delay = False
            self.logic_cluster.ble.fmux.tfall = tfall
            self.logic_cluster.ble.fmux.trise = trise
            self.logic_cluster.ble.fmux.delay = max(tfall, trise)
            self.delay_dict[self.logic_cluster.ble.fmux.name] = self.logic_cluster.ble.fmux.delay
            self.logic_cluster.ble.fmux.power = float(spice_meas["meas_avg_power"][0])
 

        # LUT delay
        print("  Updating delay for " + self.logic_cluster.ble.lut.name)
        spice_meas = spice_interface.run(self.logic_cluster.ble.lut.top_spice_path, 
                                         parameter_dict) 
        if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
            valid_delay = False
            tfall = 1
            trise = 1
        else :  
            tfall = float(spice_meas["meas_total_tfall"][0])
            trise = float(spice_meas["meas_total_trise"][0])
        if tfall < 0 or trise < 0 :
            valid_delay = False
        self.logic_cluster.ble.lut.tfall = tfall
        self.logic_cluster.ble.lut.trise = trise
        self.logic_cluster.ble.lut.delay = max(tfall, trise)
        self.delay_dict[self.logic_cluster.ble.lut.name] = self.logic_cluster.ble.lut.delay


        
        # Get delay for all paths through the LUT.
        # We get delay for each path through the LUT as well as for the LUT input drivers.
        for lut_input_name, lut_input in self.logic_cluster.ble.lut.input_drivers.items():
            driver = lut_input.driver
            not_driver = lut_input.not_driver
            print("  Updating delay for " + driver.name.replace("_driver", ""))
            driver_and_lut_sp_path = driver.top_spice_path.replace(".sp", "_with_lut.sp")

            if (lut_input_name == "f" and self.specs.use_fluts and self.specs.K == 6) or (lut_input_name == "e" and self.specs.use_fluts and self.specs.K == 5):
                lut_input.tfall = self.logic_cluster.ble.fmux.tfall
                lut_input.trise = self.logic_cluster.ble.fmux.trise
                tfall = lut_input.tfall
                trise = lut_input.trise
                lut_input.delay = max(tfall, trise)
            else:

            # Get the delay for a path through the LUT (we do it for each input)
                spice_meas = spice_interface.run(driver_and_lut_sp_path, parameter_dict) 
                if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
                    valid_delay = False
                    tfall = 1
                    trise = 1
                else :  
                    tfall = float(spice_meas["meas_total_tfall"][0])
                    trise = float(spice_meas["meas_total_trise"][0])
                if tfall < 0 or trise < 0 :
                    valid_delay = False
                if self.specs.use_fluts:
                    tfall = tfall + self.logic_cluster.ble.fmux.tfall
                    trise = trise + self.logic_cluster.ble.fmux.trise
                lut_input.tfall = tfall
                lut_input.trise = trise
                lut_input.delay = max(tfall, trise)
            lut_input.power = float(spice_meas["meas_avg_power"][0])

            if lut_input.delay < 0 :
                print("*** Lut input delay is negative : " + str(lut_input.delay) + "in path: " + driver_and_lut_sp_path +  "***")
                exit(2)

            self.delay_dict[lut_input.name] = lut_input.delay
            
            # Now, we want to get the delay and power for the driver
            print("  Updating delay for " + driver.name) 
            spice_meas = spice_interface.run(driver.top_spice_path, parameter_dict) 
            if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
                valid_delay = False
                tfall = 1
                trise = 1
            else :  
                tfall = float(spice_meas["meas_total_tfall"][0])
                trise = float(spice_meas["meas_total_trise"][0])
            if tfall < 0 or trise < 0 :
                valid_delay = False
            driver.tfall = tfall
            driver.trise = trise
            driver.delay = max(tfall, trise)
            driver.power = float(spice_meas["meas_avg_power"][0])
            self.delay_dict[driver.name] = driver.delay

            if driver.delay < 0 :
                print("*** Lut driver delay is negative : " + str(lut_input.delay) + " ***")
                exit(2)

            # ... and the not_driver
            print("  Updating delay for " + not_driver.name)
            spice_meas = spice_interface.run(not_driver.top_spice_path, parameter_dict) 
            if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
                valid_delay = False
                tfall = 1
                trise = 1
            else :  
                tfall = float(spice_meas["meas_total_tfall"][0])
                trise = float(spice_meas["meas_total_trise"][0])
            if tfall < 0 or trise < 0 :
                valid_delay = False
            not_driver.tfall = tfall
            not_driver.trise = trise
            not_driver.delay = max(tfall, trise)
            not_driver.power = float(spice_meas["meas_avg_power"][0])
            self.delay_dict[not_driver.name] = not_driver.delay
            if not_driver.delay < 0 :
                print("*** Lut not driver delay is negative : " + str(lut_input.delay) + " ***")
                exit(2)
            
            lut_delay = lut_input.delay + max(driver.delay, not_driver.delay)
            if self.specs.use_fluts:
                lut_delay += self.logic_cluster.ble.fmux.delay

            if lut_delay < 0 :
                print("*** Lut delay is negative : " + str(lut_input.delay) + " ***")
                exit(2)
            #print lut_delay
            crit_path_delay += lut_delay*lut_input.delay_weight
        
        if self.specs.use_fluts:
            crit_path_delay += self.logic_cluster.ble.fmux.delay * DELAY_WEIGHT_LUT_FRAC
        self.delay_dict["rep_crit_path"] = crit_path_delay  



        # Carry Chain
        
        if self.specs.enable_carry_chain == 1:
            print("  Updating delay for " + self.carrychain.name)
            spice_meas = spice_interface.run(self.carrychain.top_spice_path, 
                                             parameter_dict) 
            if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
                valid_delay = False
                tfall = 1
                trise = 1
            else :  
                tfall = float(spice_meas["meas_total_tfall"][0])
                trise = float(spice_meas["meas_total_trise"][0])
            if tfall < 0 or trise < 0 :
                valid_delay = False
            self.carrychain.tfall = tfall
            self.carrychain.trise = trise
            self.carrychain.delay = max(tfall, trise)
            crit_path_delay += (self.carrychain.delay*
                                self.carrychain.delay_weight)
            self.delay_dict[self.carrychain.name] = self.carrychain.delay
            self.carrychain.power = float(spice_meas["meas_avg_power"][0])


            spice_meas = spice_interface.run(self.carrychainperf.top_spice_path, 
                                             parameter_dict) 
            if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
                valid_delay = False
                tfall = 1
                trise = 1
            else :  
                tfall = float(spice_meas["meas_total_tfall"][0])
                trise = float(spice_meas["meas_total_trise"][0])
            if tfall < 0 or trise < 0 :
                valid_delay = False
            self.carrychainperf.tfall = tfall
            self.carrychainperf.trise = trise
            self.carrychainperf.delay = max(tfall, trise)
            crit_path_delay += (self.carrychainperf.delay*
                                self.carrychainperf.delay_weight)
            self.delay_dict[self.carrychainperf.name] = self.carrychainperf.delay
            self.carrychainperf.power = float(spice_meas["meas_avg_power"][0])

            spice_meas = spice_interface.run(self.carrychainmux.top_spice_path, 
                                             parameter_dict) 
            if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
                valid_delay = False
                tfall = 1
                trise = 1
            else :  
                tfall = float(spice_meas["meas_total_tfall"][0])
                trise = float(spice_meas["meas_total_trise"][0])
            if tfall < 0 or trise < 0 :
                valid_delay = False
            self.carrychainmux.tfall = tfall
            self.carrychainmux.trise = trise
            self.carrychainmux.delay = max(tfall, trise)
            crit_path_delay += (self.carrychainmux.delay*
                                self.carrychainmux.delay_weight)
            self.delay_dict[self.carrychainmux.name] = self.carrychainmux.delay
            self.carrychainmux.power = float(spice_meas["meas_avg_power"][0])


            spice_meas = spice_interface.run(self.carrychaininter.top_spice_path, 
                                             parameter_dict) 
            if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
                valid_delay = False
                tfall = 1
                trise = 1
            else :  
                tfall = float(spice_meas["meas_total_tfall"][0])
                trise = float(spice_meas["meas_total_trise"][0])
            if tfall < 0 or trise < 0 :
                valid_delay = False
            self.carrychaininter.tfall = tfall
            self.carrychaininter.trise = trise
            self.carrychaininter.delay = max(tfall, trise)
            crit_path_delay += (self.carrychaininter.delay*
                                self.carrychaininter.delay_weight)
            self.delay_dict[self.carrychaininter.name] = self.carrychaininter.delay
            self.carrychaininter.power = float(spice_meas["meas_avg_power"][0])


            if self.specs.carry_chain_type == "skip":

                spice_meas = spice_interface.run(self.carrychainand.top_spice_path, 
                                                 parameter_dict) 
                if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
                    valid_delay = False
                    tfall = 1
                    trise = 1
                else :  
                    tfall = float(spice_meas["meas_total_tfall"][0])
                    trise = float(spice_meas["meas_total_trise"][0])
                if tfall < 0 or trise < 0 :
                    valid_delay = False
                self.carrychainand.tfall = tfall
                self.carrychainand.trise = trise
                self.carrychainand.delay = max(tfall, trise)
                crit_path_delay += (self.carrychainand.delay*
                                    self.carrychainand.delay_weight)
                self.delay_dict[self.carrychainand.name] = self.carrychainand.delay
                self.carrychainand.power = float(spice_meas["meas_avg_power"][0])

                spice_meas = spice_interface.run(self.carrychainskipmux.top_spice_path, 
                                                 parameter_dict) 
                if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
                    valid_delay = False
                    tfall = 1
                    trise = 1
                else :  
                    tfall = float(spice_meas["meas_total_tfall"][0])
                    trise = float(spice_meas["meas_total_trise"][0])
                if tfall < 0 or trise < 0 :
                    valid_delay = False
                self.carrychainskipmux.tfall = tfall
                self.carrychainskipmux.trise = trise
                self.carrychainskipmux.delay = max(tfall, trise)
                crit_path_delay += (self.carrychainskipmux.delay*
                                    self.carrychainskipmux.delay_weight)
                self.delay_dict[self.carrychainskipmux.name] = self.carrychainskipmux.delay
                self.carrychainskipmux.power = float(spice_meas["meas_avg_power"][0])
        

        for hardblock in self.hardblocklist:

            spice_meas = spice_interface.run(hardblock.mux.top_spice_path, 
                                             parameter_dict) 
            if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
                valid_delay = False
                tfall = 1
                trise = 1
            else :  
                tfall = float(spice_meas["meas_total_tfall"][0])
                trise = float(spice_meas["meas_total_trise"][0])
            if tfall < 0 or trise < 0 :
                valid_delay = False
            hardblock.mux.tfall = tfall
            hardblock.mux.trise = trise
            hardblock.mux.delay = max(tfall, trise)

            self.delay_dict[hardblock.mux.name] = hardblock.mux.delay
            hardblock.mux.power = float(spice_meas["meas_avg_power"][0])
            if hardblock.parameters['num_dedicated_outputs'] > 0:
                spice_meas = spice_interface.run(hardblock.dedicated.top_spice_path, parameter_dict) 
                if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
                    valid_delay = False
                    tfall = 1
                    trise = 1
                else :  
                    tfall = float(spice_meas["meas_total_tfall"][0])
                    trise = float(spice_meas["meas_total_trise"][0])
                if tfall < 0 or trise < 0 :
                    valid_delay = False
                hardblock.dedicated.tfall = tfall
                hardblock.dedicated.trise = trise
                hardblock.dedicated.delay = max(tfall, trise)

                self.delay_dict[hardblock.dedicated.name] = hardblock.dedicated.delay
                hardblock.dedicated.power = float(spice_meas["meas_avg_power"][0])      


        # If there is no need for memory simulation, end here.
        if self.specs.enable_bram_block == 0:
            # Delay Logging
            self.update_delays_cnt += 1
            update_fpga_telemetry_csv(self, get_current_stack_trace(max_height=5))
            return valid_delay
        # Local RAM MUX
        print("  Updating delay for " + self.RAM.RAM_local_mux.name)
        spice_meas = spice_interface.run(self.RAM.RAM_local_mux.top_spice_path, 
                                         parameter_dict) 
        if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
            valid_delay = False
            tfall = 1
            trise = 1
        else :  
            tfall = float(spice_meas["meas_total_tfall"][0])
            trise = float(spice_meas["meas_total_trise"][0])
        if tfall < 0 or trise < 0 :
            valid_delay = False
        self.RAM.RAM_local_mux.tfall = tfall
        self.RAM.RAM_local_mux.trise = trise
        self.RAM.RAM_local_mux.delay = max(tfall, trise)
        self.delay_dict[self.RAM.RAM_local_mux.name] = self.RAM.RAM_local_mux.delay
        self.RAM.RAM_local_mux.power = float(spice_meas["meas_avg_power"][0])

        #RAM decoder units
        print("  Updating delay for " + self.RAM.rowdecoder_stage0.name)
        spice_meas = spice_interface.run(self.RAM.rowdecoder_stage0.top_spice_path, parameter_dict) 
        if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
            valid_delay = False
            tfall = 1
            trise = 1
        else :  
            tfall = float(spice_meas["meas_total_tfall"][0])
            trise = float(spice_meas["meas_total_trise"][0])
        if tfall < 0 or trise < 0 :
            valid_delay = False
        self.RAM.rowdecoder_stage0.tfall = tfall
        self.RAM.rowdecoder_stage0.trise = trise
        self.RAM.rowdecoder_stage0.delay = max(tfall, trise)
        #crit_path_delay += (self.RAM.rowdecoder_stage0.delay* self.RAM.delay_weight)
        self.delay_dict[self.RAM.rowdecoder_stage0.name] = self.RAM.rowdecoder_stage0.delay
        self.RAM.rowdecoder_stage0.power = float(spice_meas["meas_avg_power"][0])


        if self.RAM.valid_row_dec_size2 == 1:
            print("  Updating delay for " + self.RAM.rowdecoder_stage1_size2.name)
            spice_meas = spice_interface.run(self.RAM.rowdecoder_stage1_size2.top_spice_path, parameter_dict) 
            if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
                valid_delay = False
                tfall = 1
                trise = 1
            else :  
                tfall = float(spice_meas["meas_total_tfall"][0])
                trise = float(spice_meas["meas_total_trise"][0])
            if tfall < 0 or trise < 0 :
                valid_delay = False
            self.RAM.rowdecoder_stage1_size2.tfall = tfall
            self.RAM.rowdecoder_stage1_size2.trise = trise
            self.RAM.rowdecoder_stage1_size2.delay = max(tfall, trise)
            #crit_path_delay += (self.RAM.rowdecoder_stage1_size2.delay* self.RAM.delay_weight)
            self.delay_dict[self.RAM.rowdecoder_stage1_size2.name] = self.RAM.rowdecoder_stage1_size2.delay
            self.RAM.rowdecoder_stage1_size2.power = float(spice_meas["meas_avg_power"][0])

        if self.RAM.valid_row_dec_size3 == 1:
            print("  Updating delay for " + self.RAM.rowdecoder_stage1_size3.name)
            spice_meas = spice_interface.run(self.RAM.rowdecoder_stage1_size3.top_spice_path, parameter_dict) 
            if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
                valid_delay = False
                tfall = 1
                trise = 1
            else :  
                tfall = float(spice_meas["meas_total_tfall"][0])
                trise = float(spice_meas["meas_total_trise"][0])
            if tfall < 0 or trise < 0 :
                valid_delay = False
            self.RAM.rowdecoder_stage1_size3.tfall = tfall
            self.RAM.rowdecoder_stage1_size3.trise = trise
            self.RAM.rowdecoder_stage1_size3.delay = max(tfall, trise)
            #crit_path_delay += (self.RAM.rowdecoder_stage1_size3.delay* self.RAM.delay_weight)
            self.delay_dict[self.RAM.rowdecoder_stage1_size3.name] = self.RAM.rowdecoder_stage1_size3.delay
            self.RAM.rowdecoder_stage1_size3.power = float(spice_meas["meas_avg_power"][0])


        print("  Updating delay for " + self.RAM.rowdecoder_stage3.name)
        spice_meas = spice_interface.run(self.RAM.rowdecoder_stage3.top_spice_path, parameter_dict) 
        if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
            valid_delay = False
            tfall = 1
            trise = 1
        else :  
            tfall = float(spice_meas["meas_total_tfall"][0])
            trise = float(spice_meas["meas_total_trise"][0])
        if tfall < 0 or trise < 0 :
            valid_delay = False
        self.RAM.rowdecoder_stage3.tfall = tfall
        self.RAM.rowdecoder_stage3.trise = trise
        self.RAM.rowdecoder_stage3.delay = max(tfall, trise)
        self.delay_dict[self.RAM.rowdecoder_stage3.name] = self.RAM.rowdecoder_stage3.delay
        self.RAM.rowdecoder_stage3.power = float(spice_meas["meas_avg_power"][0])


        if self.RAM.memory_technology == "SRAM":
            print("  Updating delay for " + self.RAM.precharge.name)
            spice_meas = spice_interface.run(self.RAM.precharge.top_spice_path, parameter_dict) 
            if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
                valid_delay = False
                tfall = 1
                trise = 1
            else :  
                tfall = float(spice_meas["meas_total_tfall"][0])
                trise = float(spice_meas["meas_total_trise"][0])
            if tfall < 0 or trise < 0 :
                valid_delay = False
            self.RAM.precharge.tfall = tfall
            self.RAM.precharge.trise = trise
            self.RAM.precharge.delay = max(tfall, trise)
            #crit_path_delay += (self.RAM.precharge.delay* self.RAM.delay_weight)
            self.delay_dict[self.RAM.precharge.name] = self.RAM.precharge.delay
            self.RAM.precharge.power = float(spice_meas["meas_avg_power"][0])

            print("  Updating delay for " + self.RAM.samp_part2.name)
            spice_meas = spice_interface.run(self.RAM.samp_part2.top_spice_path, parameter_dict) 
            if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
                valid_delay = False
                tfall = 1
                trise = 1
            else :  
                tfall = float(spice_meas["meas_total_tfall"][0])
                trise = float(spice_meas["meas_total_trise"][0])
            if tfall < 0 or trise < 0 :
                valid_delay = False
            self.RAM.samp_part2.tfall = tfall
            self.RAM.samp_part2.trise = trise 
            self.RAM.samp_part2.delay = max(tfall, trise)

            self.delay_dict[self.RAM.samp_part2.name] = self.RAM.samp_part2.delay
            self.RAM.samp_part2.power = float(spice_meas["meas_avg_power"][0])

            print("  Updating delay for " + self.RAM.samp.name)
            spice_meas = spice_interface.run(self.RAM.samp.top_spice_path, parameter_dict) 
            if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
                valid_delay = False
                tfall = 1
                trise = 1
            else :  
                tfall = float(spice_meas["meas_total_tfall"][0])
                trise = float(spice_meas["meas_total_trise"][0])

            if tfall < 0 or trise < 0 :
                valid_delay = False
            self.RAM.samp.tfall = tfall + self.RAM.samp_part2.tfall
            self.RAM.samp.trise = trise + self.RAM.samp_part2.trise

            self.RAM.samp.delay = max(tfall, trise)
            #crit_path_delay += (self.RAM.samp.delay* self.RAM.delay_weight)
            self.delay_dict[self.RAM.samp.name] = self.RAM.samp.delay
            self.RAM.samp.power = float(spice_meas["meas_avg_power"][0])

            print("  Updating delay for " + self.RAM.writedriver.name)
            spice_meas = spice_interface.run(self.RAM.writedriver.top_spice_path, parameter_dict) 
            if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
                valid_delay = False
                tfall = 1
                trise = 1
            else :  
                tfall = float(spice_meas["meas_total_tfall"][0])
                trise = float(spice_meas["meas_total_trise"][0])
            if tfall < 0 or trise < 0 :
                valid_delay = False
            self.RAM.writedriver.tfall = tfall
            self.RAM.writedriver.trise = trise
            self.RAM.writedriver.delay = max(tfall, trise)
            #crit_path_delay += (self.RAM.writedriver.delay* self.RAM.delay_weight)
            self.delay_dict[self.RAM.writedriver.name] = self.RAM.writedriver.delay
            self.RAM.writedriver.power = float(spice_meas["meas_avg_power"][0])

        else:
            print("  Updating delay for " + self.RAM.bldischarging.name)
            spice_meas = spice_interface.run(self.RAM.bldischarging.top_spice_path, parameter_dict) 
            if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
                valid_delay = False
                tfall = 1
                trise = 1
            else :  
                tfall = float(spice_meas["meas_total_tfall"][0])
                trise = float(spice_meas["meas_total_trise"][0])
            if tfall < 0 or trise < 0 :
                valid_delay = False
            self.RAM.bldischarging.tfall = tfall
            self.RAM.bldischarging.trise = trise
            self.RAM.bldischarging.delay = max(tfall, trise)
            #crit_path_delay += (self.RAM.bldischarging.delay* self.RAM.delay_weight)
            self.delay_dict[self.RAM.bldischarging.name] = self.RAM.bldischarging.delay
            self.RAM.bldischarging.power = float(spice_meas["meas_avg_power"][0])

            print("  Updating delay for " + self.RAM.blcharging.name)
            spice_meas = spice_interface.run(self.RAM.blcharging.top_spice_path, parameter_dict) 
            if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
                valid_delay = False
                tfall = 1
                trise = 1
            else :  
                tfall = float(spice_meas["meas_total_tfall"][0])
                trise = float(spice_meas["meas_total_trise"][0])
            if tfall < 0 or trise < 0 :
                valid_delay = False
            self.RAM.blcharging.tfall = tfall
            self.RAM.blcharging.trise = trise
            self.RAM.blcharging.delay = max(tfall, trise)
            #crit_path_delay += (self.RAM.blcharging.delay* self.RAM.delay_weight)
            self.delay_dict[self.RAM.blcharging.name] = self.RAM.blcharging.delay
            self.RAM.blcharging.power = float(spice_meas["meas_avg_power"][0])

            self.RAM.target_bl = 0.99* float(spice_meas["meas_outputtarget"][0])

            self.RAM._update_process_data()

            print("  Updating delay for " + self.RAM.blcharging.name)
            spice_meas = spice_interface.run(self.RAM.blcharging.top_spice_path, parameter_dict) 
            if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
                valid_delay = False
                tfall = 1
                trise = 1
            else :  
                tfall = float(spice_meas["meas_total_tfall"][0])
                trise = float(spice_meas["meas_total_trise"][0])
            if tfall < 0 or trise < 0 :
                valid_delay = False
            self.RAM.blcharging.tfall = tfall
            self.RAM.blcharging.trise = trise
            self.RAM.blcharging.delay = max(tfall, trise)
            #crit_path_delay += (self.RAM.blcharging.delay* self.RAM.delay_weight)
            self.delay_dict[self.RAM.blcharging.name] = self.RAM.blcharging.delay
            self.RAM.blcharging.power = float(spice_meas["meas_avg_power"][0])
            self.RAM.target_bl = 0.99*float(spice_meas["meas_outputtarget"][0])

            self.RAM._update_process_data()

            print("  Updating delay for " + self.RAM.mtjsamp.name)
            spice_meas = spice_interface.run(self.RAM.mtjsamp.top_spice_path, parameter_dict) 
            if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
                valid_delay = False
                tfall = 1
                trise = 1
            else :  
                tfall = float(spice_meas["meas_total_tfall"][0])
                trise = float(spice_meas["meas_total_trise"][0])
            if tfall < 0 or trise < 0 :
                valid_delay = False
            self.RAM.mtjsamp.tfall = tfall
            self.RAM.mtjsamp.delay = tfall
            self.RAM.mtjsamp.trise = max(tfall, trise)
            #crit_path_delay += (self.RAM.mtjsamp.delay* self.RAM.delay_weight)
            self.delay_dict[self.RAM.mtjsamp.name] = self.RAM.mtjsamp.delay
            self.RAM.mtjsamp.power = float(spice_meas["meas_avg_power"][0])

    
        print("  Updating delay for " + self.RAM.columndecoder.name)
        spice_meas = spice_interface.run(self.RAM.columndecoder.top_spice_path, parameter_dict) 
        if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
            valid_delay = False
            tfall = 1
            trise = 1
        else :  
            tfall = float(spice_meas["meas_total_tfall"][0])
            trise = float(spice_meas["meas_total_trise"][0])
        if tfall < 0 or trise < 0 :
            valid_delay = False
        self.RAM.columndecoder.tfall = tfall
        self.RAM.columndecoder.trise = trise
        self.RAM.columndecoder.delay = max(tfall, trise)
        #crit_path_delay += (self.RAM.columndecoder.delay* self.RAM.delay_weight)
        self.delay_dict[self.RAM.columndecoder.name] = self.RAM.columndecoder.delay
        self.RAM.columndecoder.power = float(spice_meas["meas_avg_power"][0])


        print("  Updating delay for " + self.RAM.configurabledecoderi.name)
        spice_meas = spice_interface.run(self.RAM.configurabledecoderi.top_spice_path, parameter_dict) 
        if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
            valid_delay = False
            tfall = 1
            trise = 1
        else :  
            tfall = float(spice_meas["meas_total_tfall"][0])
            trise = float(spice_meas["meas_total_trise"][0])
        if tfall < 0 or trise < 0 :
            valid_delay = False
        self.RAM.configurabledecoderi.tfall = tfall
        self.RAM.configurabledecoderi.trise = trise
        self.RAM.configurabledecoderi.delay = max(tfall, trise)
        #crit_path_delay += (self.RAM.configurabledecoderi.delay* self.RAM.delay_weight)
        self.delay_dict[self.RAM.configurabledecoderi.name] = self.RAM.configurabledecoderi.delay
        self.RAM.configurabledecoderi.power = float(spice_meas["meas_avg_power"][0])


        if self.RAM.cvalidobj1 ==1:
            print("  Updating delay for " + self.RAM.configurabledecoder3ii.name)
            spice_meas = spice_interface.run(self.RAM.configurabledecoder3ii.top_spice_path, parameter_dict) 
            if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
                valid_delay = False
                tfall = 1
                trise = 1
            else :  
                tfall = float(spice_meas["meas_total_tfall"][0])
                trise = float(spice_meas["meas_total_trise"][0])
            if tfall < 0 or trise < 0 :
                valid_delay = False
            self.RAM.configurabledecoder3ii.tfall = tfall
            self.RAM.configurabledecoder3ii.trise = trise
            self.RAM.configurabledecoder3ii.delay = max(tfall, trise)
            #crit_path_delay += (self.RAM.configurabledecoder3ii.delay* self.RAM.delay_weight)
            self.delay_dict[self.RAM.configurabledecoder3ii.name] = self.RAM.configurabledecoder3ii.delay
            self.RAM.configurabledecoder3ii.power = float(spice_meas["meas_avg_power"][0])


        if self.RAM.cvalidobj2 ==1:
            print("  Updating delay for " + self.RAM.configurabledecoder2ii.name)
            spice_meas = spice_interface.run(self.RAM.configurabledecoder2ii.top_spice_path, parameter_dict) 
            if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
                valid_delay = False
                tfall = 1
                trise = 1
            else :  
                tfall = float(spice_meas["meas_total_tfall"][0])
                trise = float(spice_meas["meas_total_trise"][0])
            if tfall < 0 or trise < 0 :
                valid_delay = False
            self.RAM.configurabledecoder2ii.tfall = tfall
            self.RAM.configurabledecoder2ii.trise = trise
            self.RAM.configurabledecoder2ii.delay = max(tfall, trise)
            #crit_path_delay += (self.RAM.configurabledecoder2ii.delay* self.RAM.delay_weight)
            self.delay_dict[self.RAM.configurabledecoder2ii.name] = self.RAM.configurabledecoder2ii.delay
            self.RAM.configurabledecoder2ii.power = float(spice_meas["meas_avg_power"][0])

        print("  Updating delay for " + self.RAM.configurabledecoderiii.name)
        spice_meas = spice_interface.run(self.RAM.configurabledecoderiii.top_spice_path, parameter_dict) 
        if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
            valid_delay = False
            tfall = 1
            trise = 1
        else :  
            tfall = float(spice_meas["meas_total_tfall"][0])
            trise = float(spice_meas["meas_total_trise"][0])
        if tfall < 0 or trise < 0 :
            valid_delay = False
        self.RAM.configurabledecoderiii.tfall = tfall
        self.RAM.configurabledecoderiii.trise = trise
        self.RAM.configurabledecoderiii.delay = max(tfall, trise)
        #crit_path_delay += (self.RAM.configurabledecoderiii.delay* self.RAM.delay_weight)
        self.delay_dict[self.RAM.configurabledecoderiii.name] = self.RAM.configurabledecoderiii.delay
        self.RAM.configurabledecoderiii.power = float(spice_meas["meas_avg_power"][0])
  

        print("  Updating delay for " + self.RAM.pgateoutputcrossbar.name)
        spice_meas = spice_interface.run(self.RAM.pgateoutputcrossbar.top_spice_path, parameter_dict) 
        if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
            valid_delay = False
            tfall = 1
            trise = 1
        else :  
            tfall = float(spice_meas["meas_total_tfall"][0])
            trise = float(spice_meas["meas_total_trise"][0])
        if tfall < 0 or trise < 0 :
            valid_delay = False
        self.RAM.pgateoutputcrossbar.tfall = tfall
        self.RAM.pgateoutputcrossbar.trise = trise
        self.RAM.pgateoutputcrossbar.delay = max(tfall, trise)
        #crit_path_delay += (self.RAM.pgateoutputcrossbar.delay* self.RAM.delay_weight)
        self.delay_dict[self.RAM.pgateoutputcrossbar.name] = self.RAM.pgateoutputcrossbar.delay
        self.RAM.pgateoutputcrossbar.power = float(spice_meas["meas_avg_power"][0])
        # sets the our representative critical path
        self.delay_dict["rep_crit_path"] = crit_path_delay    

        print("  Updating delay for " + self.RAM.wordlinedriver.name)
        spice_meas = spice_interface.run(self.RAM.wordlinedriver.top_spice_path, parameter_dict) 
        if spice_meas["meas_total_tfall"][0] == "failed" or spice_meas["meas_total_trise"][0] == "failed" :
            valid_delay = False
            tfall = 1
            trise = 1
        else :  
            tfall = float(spice_meas["meas_total_tfall"][0])
            trise = float(spice_meas["meas_total_trise"][0])
        if tfall < 0 or trise < 0 :
            valid_delay = False
        self.RAM.wordlinedriver.tfall = tfall
        self.RAM.wordlinedriver.trise = trise
        self.RAM.wordlinedriver.delay = max(tfall, trise)
        #crit_path_delay += (self.RAM.wordlinedriver.delay* self.RAM.delay_weight)
        self.delay_dict[self.RAM.wordlinedriver.name] = self.RAM.wordlinedriver.delay
        self.RAM.wordlinedriver.power = float(spice_meas["meas_avg_power"][0])
        if self.RAM.wordlinedriver.wl_repeater == 1:
            self.RAM.wordlinedriver.power *=2

        # TODO put delay logging here for BRAM support
        # Delay Logging
        self.update_delays_cnt += 1
        update_fpga_telemetry_csv(self, get_current_stack_trace(max_height=5))
        return valid_delay


                  
    def update_power(self, spice_interface):
        """This funciton measures RAM core power once sizing has finished.
        It also sums up power consumed by the peripheral circuitry and converts it to energy per bit"""
        # Several timing parameters need to be updated before power can be measured accurately
        # The following will compute and store the current values for these delays
        # Create parameter dict of all current transistor sizes and wire rc

        parameter_dict = {}
        for tran_name, tran_size in self.transistor_sizes.items():
            if not self.specs.use_finfet:
                parameter_dict[tran_name] = [1e-9*tran_size*self.specs.min_tran_width]
            else :
                parameter_dict[tran_name] = [tran_size]

        for wire_name, rc_data in self.wire_rc_dict.items():
            parameter_dict[wire_name + "_res"] = [rc_data[0]]
            parameter_dict[wire_name + "_cap"] = [rc_data[1]*1e-15]

        # Update the file
        ram_decoder_stage1_delay = 0
        if self.RAM.valid_row_dec_size2 == 1:
            ram_decoder_stage1_delay = max(ram_decoder_stage1_delay, self.RAM.rowdecoder_stage1_size2.delay)
        if self.RAM.valid_row_dec_size3 == 1:
            ram_decoder_stage1_delay = max(self.RAM.rowdecoder_stage1_size3.delay, ram_decoder_stage1_delay)
        self.RAM.estimated_rowdecoder_delay = ram_decoder_stage1_delay    
        self.RAM.estimated_rowdecoder_delay += self.RAM.rowdecoder_stage3.delay
        ram_decoder_stage0_delay = self.RAM.rowdecoder_stage0.delay
        self.RAM.estimated_rowdecoder_delay += ram_decoder_stage0_delay

        # Measure the configurable decoder delay:
        configurable_decoder_delay = 0.0
        if self.RAM.cvalidobj1 == 1:
            configurable_decoder_delay = max(self.RAM.configurabledecoder3ii.delay, configurable_decoder_delay)
        if self.RAM.cvalidobj2 == 1:
            configurable_decoder_delay = max(self.RAM.configurabledecoder2ii.delay, configurable_decoder_delay)
        configurable_decoder_delay += self.RAM.configurabledecoderi.delay
        # This is the driving part of the configurable decoder.
        configurable_decoder_drive = self.RAM.configurabledecoderiii.delay

        # ###############################################
        # Overall frequency calculation of the RAM
        # ###############################################
        # Ref [1]: "High Density, Low Energy, Magnetic Tunnel Junction Based Block RAMs for Memory-rich FPGAs",
        # Tatsumara et al, FPT'16
        # Ref [2]: "Don't Forget the Memory: Automatic Block RAM Modelling, Optimization, and Architecture Exploration",
        # Yazdanshenas et al, FPGA'17
        # 
        # -----------------------------------------------
        # For SRAM
        # -----------------------------------------------
        # From [1]:
        # Delay of the RAM read path is a sum of 3 delays:
        # Tread = T1 + T2 + T3
        # = max (row decoder, pre-charge time) + (wordline driver + bit line delay) + (sense amp + output crossbar)
        # For an output registered SRAM (assumed here), the cycle time of the RAM is limited by:
        # Tread' = Tread + Tmicro_reg_setup
        # The write path delay (Twrite) is always faster than Tread so it doesn't affect the cycle time.
        #
        # The formulae below use a slightly different terminology/notation:
        # 1. They include configurable decoder related delays as well, which are required because RAM blocks on FPGAs
        #    have configurable decoders for providing configurable depths and widths.
        # 2. Instead of breaking down the delay into 3 components,the delay is broken down into 2 components (T1 and T2).
        # 3. Bit line delay (a part of T2 from the paper) is self.RAM.samp.delay in the code below.
        # 4. Sense amp delay (a part of T3 from the paper) is self.RAM.samp_part2.delay in the code below.
        # 5. The Tmicro_reg_setup value is hardcoded as 2e-11

        if self.RAM.memory_technology == "SRAM":
            self.RAM.T1 = max(self.RAM.estimated_rowdecoder_delay, configurable_decoder_delay, self.RAM.precharge.delay)
            self.RAM.T2 = self.RAM.wordlinedriver.delay + self.RAM.samp.delay + self.RAM.samp_part2.delay  
            self.RAM.frequency = max(self.RAM.T1 + self.RAM.T2 , configurable_decoder_delay + configurable_decoder_drive)
            self.RAM.frequency += self.RAM.pgateoutputcrossbar.delay + 2e-11

        # -----------------------------------------------
        # For MTJ
        # -----------------------------------------------
        # From [1]:
        # The write operation consists of precharge (T1) and cell-write (T2) phases. 
        # T1 is the maximum of BL-discharging time and the row decoder delay. 
        # T2 is the sum of word line delay and the MTJ cell writing time. 
        # Twrite = T1 + T2.
        #
        # The read operation consists of precharge (T1), stabilize (T3), sense (T4) and latch (T5) phases. 
        # T1 is the same as the write operation.
        # T3 is the sum of wordline delay and the BL-charging time.
        # T4 is the sense amp delay.
        # T5 is the sum of crossbar delay and Tmicro_reg_setup.
        # Tread = T1 + T3 + T4 + T5
        #
        # Overall frequency = max(Tread, Twrite)
        # 
        # The formulae below use a different terminology/notation:
        # 1. They include confgurable decoder related delays as well, which are required because RAM blocks on FPGAs
        #    have configurable decoders for providing configurable depths and widths.
        # 2. There is no separation of Tread and Twrite and the T1/T2/etc components are not the same.
        # 3. The Tmicro_reg_setup value is hardcoded as 3e-9

        elif self.RAM.memory_technology == "MTJ":

            self.RAM.T1 = max(self.RAM.estimated_rowdecoder_delay, configurable_decoder_delay, self.RAM.bldischarging.delay)
            self.RAM.T2 = self.RAM.T1 +  max(self.RAM.wordlinedriver.delay , configurable_decoder_drive) + self.RAM.blcharging.delay
            self.RAM.T3 = self.RAM.T2 + self.RAM.mtjsamp.delay
            self.RAM.frequency = self.RAM.T2 - self.RAM.blcharging.delay + 3e-9

        self.RAM._update_process_data()

        if self.RAM.memory_technology == "SRAM":
            print("Measuring SRAM power " + self.RAM.power_sram_read.name)
            spice_meas = spice_interface.run(self.RAM.power_sram_read.top_spice_path, parameter_dict) 
            self.RAM.power_sram_read.power_selected = float(spice_meas["meas_avg_power_selected"][0])
            self.RAM.power_sram_read.power_unselected = float(spice_meas["meas_avg_power_unselected"][0])

            spice_meas = spice_interface.run(self.RAM.power_sram_writelh.top_spice_path, parameter_dict) 
            self.RAM.power_sram_writelh.power_selected_writelh = float(spice_meas["meas_avg_power_selected"][0])

            spice_meas = spice_interface.run(self.RAM.power_sram_writehh.top_spice_path, parameter_dict) 
            self.RAM.power_sram_writehh.power_selected_writehh = float(spice_meas["meas_avg_power_selected"][0])

            spice_meas = spice_interface.run(self.RAM.power_sram_writep.top_spice_path, parameter_dict) 
            self.RAM.power_sram_writep.power_selected_writep = float(spice_meas["meas_avg_power_selected"][0])

            # can be used to help with debugging:
            #print "T1: " +str(self.RAM.T1)
            #print "T2: " + str(self.RAM.T2)
            #print "freq " + str(self.RAM.frequency)
            #print "selected " + str(self.RAM.power_sram_read.power_selected)
            #print "unselected " + str(self.RAM.power_sram_read.power_unselected)

            #print "selected_writelh " + str(self.RAM.power_sram_writelh.power_selected_writelh)
            #print "selected_writehh " + str(self.RAM.power_sram_writehh.power_selected_writehh)
            #print "selected_writep " + str(self.RAM.power_sram_writep.power_selected_writep)

            #print "power per bit read SRAM: " + str(self.RAM.power_sram_read.power_selected + self.RAM.power_sram_read.power_unselected)
            #print "Energy " + str((self.RAM.power_sram_read.power_selected + self.RAM.power_sram_read.power_unselected) * self.RAM.frequency)
            #print "Energy Writelh " + str(self.RAM.power_sram_writelh.power_selected_writelh * self.RAM.frequency)
            #print "Energy Writehh " + str(self.RAM.power_sram_writehh.power_selected_writehh * self.RAM.frequency)
            print("Energy Writep " + str(self.RAM.power_sram_writep.power_selected_writep * self.RAM.frequency))

            read_energy = (self.RAM.power_sram_read.power_selected + self.RAM.power_sram_read.power_unselected) * self.RAM.frequency
            write_energy = ((self.RAM.power_sram_writelh.power_selected_writelh + self.RAM.power_sram_writehh.power_selected_writehh)/2 + self.RAM.power_sram_read.power_unselected) * self.RAM.frequency

            self.RAM.core_energy = (self.RAM.read_to_write_ratio * read_energy + write_energy) /(1 + self.RAM.read_to_write_ratio)

        else:
            print("Measuring MTJ power ")
            spice_meas = spice_interface.run(self.RAM.power_mtj_write.top_spice_path, parameter_dict) 
            self.RAM.power_mtj_write.powerpl = float(spice_meas["meas_avg_power_selected"][0])
            self.RAM.power_mtj_write.powernl = float(spice_meas["meas_avg_power_selectedn"][0])
            self.RAM.power_mtj_write.powerph = float(spice_meas["meas_avg_power_selectedh"][0])
            self.RAM.power_mtj_write.powernh = float(spice_meas["meas_avg_power_selectedhn"][0])

            # can be used to help with debugging:
            #print "Energy Negative Low " + str(self.RAM.power_mtj_write.powernl * self.RAM.frequency)
            #print "Energy Positive Low " + str(self.RAM.power_mtj_write.powerpl * self.RAM.frequency)
            #print "Energy Negative High " + str(self.RAM.power_mtj_write.powernh * self.RAM.frequency)
            #print "Energy Positive High " + str(self.RAM.power_mtj_write.powerph * self.RAM.frequency)
            #print "Energy " + str(((self.RAM.power_mtj_write.powerph - self.RAM.power_mtj_write.powernh + self.RAM.power_mtj_write.powerpl - self.RAM.power_mtj_write.powernl) * self.RAM.frequency)/4)

            spice_meas = spice_interface.run(self.RAM.power_mtj_read.top_spice_path, parameter_dict) 
            self.RAM.power_mtj_read.powerl = float(spice_meas["meas_avg_power_readl"][0])
            self.RAM.power_mtj_read.powerh = float(spice_meas["meas_avg_power_readh"][0])

            # can be used to help with debugging:
            #print "Energy Low Read " + str(self.RAM.power_mtj_read.powerl * self.RAM.frequency)
            #print "Energy High Read " + str(self.RAM.power_mtj_read.powerh * self.RAM.frequency)
            #print "Energy Read " + str(((self.RAM.power_mtj_read.powerl + self.RAM.power_mtj_read.powerh) * self.RAM.frequency))

            read_energy = ((self.RAM.power_mtj_read.powerl + self.RAM.power_mtj_read.powerh) * self.RAM.frequency)
            write_energy = ((self.RAM.power_mtj_write.powerph - self.RAM.power_mtj_write.powernh + self.RAM.power_mtj_write.powerpl - self.RAM.power_mtj_write.powernl) * self.RAM.frequency)/4
            self.RAM.core_energy = (self.RAM.read_to_write_ratio * read_energy + write_energy) /(1 + self.RAM.read_to_write_ratio)


        # Peripherals are not technology-specific
        # Different components powers are multiplied by the number of active components for each toggle:
        peripheral_energy = self.RAM.row_decoder_bits / 2 * self.RAM.rowdecoder_stage0.power * self.RAM.number_of_banks
        if self.RAM.valid_row_dec_size2 == 1 and self.RAM.valid_row_dec_size3 == 1:
            peripheral_energy += (self.RAM.rowdecoder_stage1_size3.power + self.RAM.rowdecoder_stage1_size2.power)/2
        elif self.RAM.valid_row_dec_size3 == 1:
            peripheral_energy += self.RAM.rowdecoder_stage1_size3.power
        else:
            peripheral_energy += self.RAM.rowdecoder_stage1_size2.power

        peripheral_energy += self.RAM.wordlinedriver.power + self.RAM.columndecoder.power

        peripheral_energy += self.RAM.configurabledecoderi.power * self.RAM.conf_decoder_bits / 2 * self.RAM.number_of_banks
        peripheral_energy += self.RAM.configurabledecoderiii.power * (1 + 2**self.RAM.conf_decoder_bits)/2

        # Convert to energy
        peripheral_energy = peripheral_energy * self.RAM.frequency

        # Add read-specific components
        self.RAM.peripheral_energy_read = peripheral_energy + self.RAM.pgateoutputcrossbar.power * (1 + 2**self.RAM.conf_decoder_bits)/2 * self.RAM.frequency
        # We need energy PER BIT. Hence:
        self.RAM.peripheral_energy_read /= 2** self.RAM.conf_decoder_bits
        # Add write-specific components (input FF to WD)
        self.RAM.peripheral_energy_write = peripheral_energy + (2** self.RAM.conf_decoder_bits * self.RAM.configurabledecoderiii.power /2) * self.RAM.frequency
        # Add write-specific components (Write enable wires)
        self.RAM.peripheral_energy_write += ((1 + 2** self.RAM.conf_decoder_bits) * self.RAM.configurabledecoderiii.power) * self.RAM.frequency
        # We want energy per bit per OP:
        self.RAM.peripheral_energy_write /= 2** self.RAM.conf_decoder_bits

        print("Core read and write energy: " +str(read_energy) + " and " +str(write_energy))
        print("Core energy per bit: " + str(self.RAM.core_energy))
        print("Peripheral energy per bit: " + str((self.RAM.peripheral_energy_read * self.RAM.read_to_write_ratio + self.RAM.peripheral_energy_write)/ (1 + self.RAM.read_to_write_ratio)))

    def print_specs(self):

        print("|------------------------------------------------------------------------------|")
        print("|   FPGA Architecture Specs                                                    |")
        print("|------------------------------------------------------------------------------|")
        print("")
        print("  Number of BLEs per cluster (N): " + str(self.specs.N))
        print("  LUT size (K): " + str(self.specs.K))
        print("  Channel width (W): " + str(self.specs.W))
        print("  Wire segment length (L): " + str(self.specs.L))
        print("  Number cluster inputs (I): " + str(self.specs.I))
        print("  Number of BLE outputs to general routing: " + str(self.specs.num_ble_general_outputs))
        print("  Number of BLE outputs to local routing: " + str(self.specs.num_ble_local_outputs))
        print("  Number of cluster outputs: " + str(self.specs.num_cluster_outputs))
        print("  Switch block flexibility (Fs): " + str(self.specs.Fs))
        print("  Cluster input flexibility (Fcin): " + str(self.specs.Fcin))
        print("  Cluster output flexibility (Fcout): " + str(self.specs.Fcout))
        print("  Local MUX population (Fclocal): " + str(self.specs.Fclocal))
        print("")
        print("|------------------------------------------------------------------------------|")
        print("")
        
        
    def print_details(self, report_file):

        utils.print_and_write(report_file, "|------------------------------------------------------------------------------|")
        utils.print_and_write(report_file, "|   FPGA Implementation Details                                                |")
        utils.print_and_write(report_file, "|------------------------------------------------------------------------------|")
        utils.print_and_write(report_file, "")

        for sb_mux, cluster_output_load, routing_wire_load in zip(self.sb_muxes, self.cluster_output_loads, self.routing_wire_loads):
            sb_mux.print_details(report_file)
            cluster_output_load.print_details(report_file)
            routing_wire_load.print_details(report_file)
        # self.sb_mux.print_details(report_file)
        # self.cluster_output_load.print_details(report_file)
        # self.routing_wire_load.print_details(report_file)

        self.cb_mux.print_details(report_file)
        self.logic_cluster.print_details(report_file)
        if self.specs.enable_bram_block == 1:
            self.RAM.print_details(report_file)
        for hb in self.hardblocklist:
            hb.print_details(report_file)

        utils.print_and_write(report_file, "|------------------------------------------------------------------------------|")
        utils.print_and_write(report_file, "")

        return
    
    
    def _area_model(self, tran_name, tran_size):
        """ Transistor area model. 'tran_size' is the transistor drive strength in min. width transistor drive strengths. 
            Transistor area is calculated bsed on 'tran_size' and transistor type, which is determined by tags in 'tran_name'.
            Return valus is the transistor area in minimum width transistor areas. """
    
        # If inverter or transmission gate, use larger area to account for N-well spacing
        # If pass-transistor, use regular area because they don't need N-wells.
        if "inv_" in tran_name or "tgate_" in tran_name:
            if not self.specs.use_finfet :
                area = 0.518 + 0.127*tran_size + 0.428*math.sqrt(tran_size)
            # This is the finfet Tx model we used in ASAP7, not sure why it should be different than other finfet Tx models
            elif (self.specs.min_tran_width == 7): 
                area = 0.3694 + 0.0978*tran_size + 0.5368*math.sqrt(tran_size)
            else :
                area = 0.034 + 0.414*tran_size + 0.735*math.sqrt(tran_size)

        else:
            if not self.specs.use_finfet :
                area = 0.447 + 0.128*tran_size + 0.391*math.sqrt(tran_size)
            elif (self.specs.min_tran_width == 7):
                area = 0.3694 + 0.0978*tran_size + 0.5368*math.sqrt(tran_size)
            else :
                area = -0.013 + 0.414*tran_size + 0.665*math.sqrt(tran_size)
    
        return area    
    
     
    def _create_lib_files(self):
        """ Create SPICE library files and add headers. """

        # Create Subcircuits file
        sc_file = open(self.subcircuits_filename, 'w')
        sc_file.write("*** SUBCIRCUITS\n\n")
        sc_file.write(".LIB SUBCIRCUITS\n\n")
        sc_file.close()
       

    def _end_lib_files(self):
        """ End the SPICE library files. """

        # Subcircuits file
        sc_file = open(self.subcircuits_filename, 'a')
        sc_file.write(".ENDL SUBCIRCUITS")
        sc_file.close()
       

    def _generate_basic_subcircuits(self):
        """ Generates the basic subcircuits SPICE file (pass-transistor, inverter, etc.) """
        
        print("Generating basic subcircuits")
        
        # Open basic subcircuits file and write heading
        basic_sc_file = open(self.basic_subcircuits_filename, 'w')
        basic_sc_file.write("*** BASIC SUBCIRCUITS\n\n")
        basic_sc_file.write(".LIB BASIC_SUBCIRCUITS\n\n")
        basic_sc_file.close()

        # Generate wire subcircuit
        basic_subcircuits.wire_generate(self.basic_subcircuits_filename)
        # Generate pass-transistor subcircuit
        basic_subcircuits.ptran_generate(self.basic_subcircuits_filename, self.specs.use_finfet)
        basic_subcircuits.ptran_pmos_generate(self.basic_subcircuits_filename, self.specs.use_finfet)
        # Generate transmission gate subcircuit
        basic_subcircuits.tgate_generate(self.basic_subcircuits_filename, self.specs.use_finfet)
        basic_subcircuits.tgate_generate_lp(self.basic_subcircuits_filename, self.specs.use_finfet)
        # Generate level-restore subcircuit
        basic_subcircuits.rest_generate(self.basic_subcircuits_filename, self.specs.use_finfet)
        # Generate inverter subcircuit
        basic_subcircuits.inverter_generate(self.basic_subcircuits_filename, self.specs.use_finfet, self.specs.memory_technology)
        # Generate nand2
        basic_subcircuits.nand2_generate(self.basic_subcircuits_filename, self.specs.use_finfet)
        basic_subcircuits.nand2_generate_lp(self.basic_subcircuits_filename, self.specs.use_finfet)
        # Generate nand3 
        basic_subcircuits.nand3_generate(self.basic_subcircuits_filename, self.specs.use_finfet)
        basic_subcircuits.nand3_generate_lp(self.basic_subcircuits_filename, self.specs.use_finfet)
        #generate ram tgate
        basic_subcircuits.RAM_tgate_generate(self.basic_subcircuits_filename, self.specs.use_finfet)
        basic_subcircuits.RAM_tgate_generate_lp(self.basic_subcircuits_filename, self.specs.use_finfet)

        # Write footer
        basic_sc_file = open(self.basic_subcircuits_filename, 'a')
        basic_sc_file.write(".ENDL BASIC_SUBCIRCUITS")
        basic_sc_file.close()
        
        
    def _generate_process_data(self):
        """ Write the process data library file. It contains voltage levels, gate length and device models. """
        
        print("Generating process data file")

        
        process_data_file = open(self.process_data_filename, 'w')
        process_data_file.write("*** PROCESS DATA AND VOLTAGE LEVELS\n\n")
        process_data_file.write(".LIB PROCESS_DATA\n\n")
        process_data_file.write("* Voltage levels\n")
        process_data_file.write(".PARAM supply_v = " + str(self.specs.vdd) + "\n")
        process_data_file.write(".PARAM sram_v = " + str(self.specs.vsram) + "\n")
        process_data_file.write(".PARAM sram_n_v = " + str(self.specs.vsram_n) + "\n")
        process_data_file.write(".PARAM Rcurrent = " + str(self.specs.worst_read_current) + "\n")
        process_data_file.write(".PARAM supply_v_lp = " + str(self.specs.vdd_low_power) + "\n\n")


        if self.specs.memory_technology == "MTJ":
            process_data_file.write(".PARAM target_bl = " + str(0.04) + "\n\n")

        if use_lp_transistor == 0 :
            process_data_file.write(".PARAM sense_v = " + str(self.specs.vdd - self.specs.sense_dv) + "\n\n")
        else:
            process_data_file.write(".PARAM sense_v = " + str(self.specs.vdd_low_power - self.specs.sense_dv) + "\n\n")


        process_data_file.write(".PARAM mtj_worst_high = " + str(self.specs.MTJ_Rhigh_worstcase) + "\n")
        process_data_file.write(".PARAM mtj_worst_low = " + str(self.specs.MTJ_Rlow_worstcase) + "\n")
        process_data_file.write(".PARAM mtj_nominal_low = " + str(self.specs.MTJ_Rlow_nominal) + "\n\n")
        process_data_file.write(".PARAM mtj_nominal_high = " + str(6250) + "\n\n") 
        process_data_file.write(".PARAM vref = " + str(self.specs.vref) + "\n")
        process_data_file.write(".PARAM vclmp = " + str(self.specs.vclmp) + "\n")

        process_data_file.write("* Geometry\n")
        process_data_file.write(".PARAM gate_length = " + str(self.specs.gate_length) + "n\n")
        process_data_file.write(".PARAM trans_diffusion_length = " + str(self.specs.trans_diffusion_length) + "n\n")
        process_data_file.write(".PARAM min_tran_width = " + str(self.specs.min_tran_width) + "n\n")
        process_data_file.write(".param rest_length_factor=" + str(self.specs.rest_length_factor) + "\n")
        process_data_file.write("\n")

        process_data_file.write("* Supply voltage.\n")
        process_data_file.write("VSUPPLY vdd gnd supply_v\n")
        process_data_file.write("VSUPPLYLP vdd_lp gnd supply_v_lp\n")
        process_data_file.write("* SRAM voltages connecting to gates\n")
        process_data_file.write("VSRAM vsram gnd sram_v\n")
        process_data_file.write("VrefMTJn vrefmtj gnd vref\n")
        process_data_file.write("Vclmomtjn vclmpmtj gnd vclmp\n")
        process_data_file.write("VSRAM_N vsram_n gnd sram_n_v\n\n")
        process_data_file.write("* Device models\n")
        process_data_file.write(".LIB \"" + self.specs.model_path + "\" " + self.specs.model_library + "\n\n")
        process_data_file.write(".ENDL PROCESS_DATA")
        process_data_file.close()
        
        
    def _generate_includes(self):
        """ Generate the includes file. Top-level SPICE decks should only include this file. """
    
        print("Generating includes file")
    
        includes_file = open(self.includes_filename, 'w')
        includes_file.write("*** INCLUDE ALL LIBRARIES\n\n")
        includes_file.write(".LIB INCLUDES\n\n")
        includes_file.write("* Include process data (voltage levels, gate length and device models library)\n")
        includes_file.write(".LIB \"process_data.l\" PROCESS_DATA\n\n")
        includes_file.write("* Include transistor parameters\n")
        includes_file.write("* Include wire resistance and capacitance\n")
        #includes_file.write(".LIB \"wire_RC.l\" WIRE_RC\n\n")
        includes_file.write("* Include basic subcircuits\n")
        includes_file.write(".LIB \"basic_subcircuits.l\" BASIC_SUBCIRCUITS\n\n")
        includes_file.write("* Include subcircuits\n")
        includes_file.write(".LIB \"subcircuits.l\" SUBCIRCUITS\n\n")
        includes_file.write("* Include sweep data file for .DATA sweep analysis\n")
        includes_file.write(".INCLUDE \"sweep_data.l\"\n\n")
        includes_file.write(".ENDL INCLUDES")
        includes_file.close()
        
        
    def _generate_sweep_data(self):
        """ Create the sweep_data.l file that COFFE uses to perform 
            multi-variable HSPICE parameter sweeping. """

        sweep_data_file = open(self.sweep_data_filename, 'w')
        sweep_data_file.close()
        

    def _update_transistor_sizes(self, element_names, combo, use_finfet, inv_ratios=None):
        """ This function is used to update self.transistor_sizes for a particular transistor sizing combination.
            'element_names' is a list of elements (ptran, inv, etc.) that need their sizes updated.
            'combo' is a particular transistor sizing combination for the transistors in 'element_names'
            'inv_ratios' are the inverter P/N ratios for this transistor sizing combination.
            'combo' will typically describe only a small group of transistors. Other transistors retain their current size."""
        
        # We start by making a dictionary of the transistor sizes we need to update
        new_sizes = {}
        for i in range(len(combo)):
            element_name = element_names[i]
            # If it's a pass-transistor, we just add the NMOS size
            if "ptran_" in element_name:
                new_sizes[element_name + "_nmos"] = combo[i]
            # If it's a level-restorer, we just add the PMOS size
            elif "rest_" in element_name:
                new_sizes[element_name + "_pmos"] = combo[i]
            # If it's a transmission gate, we just add the PMOS and NMOS sizes
            elif "tgate_" in element_name:
                new_sizes[element_name + "_pmos"] = combo[i]
                new_sizes[element_name + "_nmos"] = combo[i]
            # If it's an inverter, we have to add both NMOS and PMOS sizes
            elif "inv_" in element_name:
                if inv_ratios == None:
                    # If no inverter ratios are specified, NMOS and PMOS are equal size
                    new_sizes[element_name + "_nmos"] = combo[i]
                    new_sizes[element_name + "_pmos"] = combo[i]
                else:
                    # If there are inverter ratios, we use them to give different sizes to NMOS and PMOS
                    if inv_ratios[element_name] < 1:
                        # NMOS is larger than PMOS
                        if not use_finfet:
                            new_sizes[element_name + "_nmos"] = combo[i]/inv_ratios[element_name]
                        else :
                            new_sizes[element_name + "_nmos"] = round(combo[i]/inv_ratios[element_name])
                            # new_sizes[element_name + "_nmos"] = combo[i]
                        new_sizes[element_name + "_pmos"] = combo[i]
                    else:
                        # PMOS is larger than NMOS
                        new_sizes[element_name + "_nmos"] = combo[i]
                        if not use_finfet :
                            new_sizes[element_name + "_pmos"] = combo[i]*inv_ratios[element_name]
                        else :
                            new_sizes[element_name + "_pmos"] = round(combo[i]*inv_ratios[element_name])
                            # new_sizes[element_name + "_pmos"] = combo[i]

        # Now, update self.transistor_sizes with these new sizes
        self.transistor_sizes.update(new_sizes)
      
      
    def _update_area_per_transistor(self):
        """ We use self.transistor_sizes to calculate area
            Using the area model, we calculate the transistor area in minimum width transistor areas.
            We also calculate area in nm and transistor width in nm. Nanometer values are needed for wire length calculations.
            For each transistor, this data forms a tuple (tran_name, tran_channel_width_nm, tran_drive_strength, tran_area_min_areas, tran_area_nm, tran_width_nm)
            The FPGAs transistor_area_list is updated once these values are computed."""
        
        # Initialize transistor area list
        tran_area_list = []
        
        # For each transistor, calculate area
        for tran_name, tran_size in self.transistor_sizes.items():
                # Get transistor drive strength (drive strength is = xMin width)
                tran_drive = tran_size
                # Get tran area in min transistor widths
                tran_area = self._area_model(tran_name, tran_drive)
                # Get area in nm square
                tran_area_nm = tran_area*self.specs.min_width_tran_area
                # Get width of transistor in nm
                tran_width = math.sqrt(tran_area_nm)
                # Add this as a tuple to the tran_area_list
                # TODO: tran_size and tran_drive are the same thing?!
                tran_area_list.append((tran_name, tran_size, tran_drive, tran_area, 
                                                tran_area_nm, tran_width))    
                                                                                   
        # Assign list to FPGA object
        self.transistor_area_list = tran_area_list
        

    def _update_area_and_width_dicts(self):
        """ Calculate area for basic subcircuits like inverters, pass transistor, 
            transmission gates, etc. Update area_dict and width_dict with this data."""
        
        # Initialize component area list of tuples (component name, component are, component width)
        comp_area_list = []
        
        # Create a dictionary to store component sizes for multi-transistor components
        comp_dict = {}
        
        # For each transistor in the transistor_area_list
        # tran is a tuple having the following formate (tran_name, tran_channel_width_nm, 
        # tran_drive_strength, tran_area_min_areas, tran_area_nm, tran_width_nm)
        for tran in self.transistor_area_list:
            # those components should have an nmos and a pmos transistors in them
            if "inv_" in tran[0] or "tgate_" in tran[0]:
                # Get the component name; transistors full name example: inv_lut_out_buffer_2_nmos.
                # so the component name after the next two lines will be inv_lut_out_buffe_2.
                comp_name = tran[0].replace("_nmos", "")
                comp_name = comp_name.replace("_pmos", "")
                
                # If the component is already in the dictionary
                if comp_name in comp_dict:
                    if "_nmos" in tran[0]:
                        # tran[4] is tran_area_nm
                        comp_dict[comp_name]["nmos"] = tran[4]
                    else:
                        comp_dict[comp_name]["pmos"] = tran[4]
                        
                    # At this point we should have both NMOS and PMOS sizes in the dictionary
                    # We can calculate the area of the inverter or tgate by doing the sum
                    comp_area = comp_dict[comp_name]["nmos"] + comp_dict[comp_name]["pmos"]
                    comp_width = math.sqrt(comp_area)
                    comp_area_list.append((comp_name, comp_area, comp_width))                 
                else:
                    # Create a dict for this component to store nmos and pmos sizes
                    comp_area_dict = {}
                    # Add either the nmos or pmos item
                    if "_nmos" in tran[0]:
                        comp_area_dict["nmos"] = tran[4]
                    else:
                        comp_area_dict["pmos"] = tran[4]
                        
                    # Add this inverter to the inverter dictionary    
                    comp_dict[comp_name] = comp_area_dict
            # those components only have one transistor in them
            elif "ptran_" in tran[0] or "rest_" in tran[0] or "tran_" in tran[0]:   
                # Get the comp name
                comp_name = tran[0].replace("_nmos", "")
                comp_name = comp_name.replace("_pmos", "")               
                # Add this to comp_area_list directly
                comp_area_list.append((comp_name, tran[4], tran[5]))            
        
        # Convert comp_area_list to area_dict and width_dict
        area_dict = {}
        width_dict = {}
        for component in comp_area_list:
            area_dict[component[0]] = component[1]
            width_dict[component[0]] = component[2]
        
        # Set the FPGA object area and width dict
        self.area_dict = area_dict
        self.width_dict = width_dict
  
        return

