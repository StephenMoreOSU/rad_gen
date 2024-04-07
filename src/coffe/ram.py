import math

import src.coffe.mux_subcircuits as mux_subcircuits
import src.coffe.memory_subcircuits as memory_subcircuits
import src.coffe.load_subcircuits as load_subcircuits
import src.coffe.utils as utils

from src.coffe.circuit_baseclasses import _SizableCircuit, _CompoundCircuit
import src.coffe.top_level as top_level

import src.coffe.constants as consts


class _pgateoutputcrossbar(_SizableCircuit):
    """ RAM outputcrossbar using pass transistors"""
    
    def __init__(self, maxwidth):
        # Subcircuit name
        self.name = "pgateoutputcrossbar"
        self.delay_weight = consts.DELAY_WEIGHT_RAM
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
        self.delay_weight = consts.DELAY_WEIGHT_RAM
        self.tgatecount = tgatecount
    
    
    def generate(self, subcircuit_filename, min_tran_width):
        print("Generating stage of the configurable decoder " + self.name)
        

        # Call generation function
        if consts.use_lp_transistor == 0:
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
        if consts.use_lp_transistor == 0:
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
        if consts.use_lp_transistor == 0:
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
        if consts.use_lp_transistor == 0:
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
        if consts.use_lp_transistor == 0:
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
        if consts.use_lp_transistor == 0:
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
        if consts.use_lp_transistor == 0:
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
        if consts.use_lp_transistor == 0:
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
        if consts.use_lp_transistor == 0:
            self.transistor_names, self.wire_names = memory_subcircuits.generate_rowdecoderstage0(subcircuit_filename, self.name)
        else:
            self.transistor_names, self.wire_names = memory_subcircuits.generate_rowdecoderstage0_lp(subcircuit_filename, self.name)
        self.initial_transistor_sizes["inv_rowdecoderstage0_1_nmos"] = 9
        self.initial_transistor_sizes["inv_rowdecoderstage0_1_pmos"] = 9
     
        return self.initial_transistor_sizes

    def generate_top(self):
        print("Generating row decoder initial stage") 
        if consts.use_lp_transistor == 0:
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

        if consts.use_lp_transistor == 0:
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
        if consts.use_lp_transistor == 0:
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
        self.delay_weight = consts.DELAY_WEIGHT_RAM
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
        if consts.use_lp_transistor == 0:
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
        if consts.use_lp_transistor == 0:
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
        self.delay_weight = consts.DELAY_WEIGHT_RAM
        self.rowsram = rowsram
        self.gatesize = gatesize
        self.areafac = areafac
    
    
    def generate(self, subcircuit_filename, min_tran_width):
        print("Generating last stage of the row decoder" + self.name)

        # Call generation function
        if consts.use_lp_transistor == 0:
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
        if consts.use_lp_transistor == 0:
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
        if consts.use_lp_transistor == 0:
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
        if consts.use_lp_transistor == 0:
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
        if consts.use_lp_transistor == 0:
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
        if consts.use_lp_transistor == 0:
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
        if consts.use_lp_transistor == 0:
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
        if consts.use_lp_transistor == 0:
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
        if consts.use_lp_transistor == 0:
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
        if consts.use_lp_transistor == 0:
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
        if consts.use_lp_transistor == 0:
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
        if consts.use_lp_transistor == 0:
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
        if consts.use_lp_transistor == 0:
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
        if consts.use_lp_transistor == 0:
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
        if consts.use_lp_transistor == 0:
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
        if consts.use_lp_transistor == 0:
            self.transistor_names, self.wire_names = memory_subcircuits.generate_precharge(subcircuit_filename, self.name)
        else:
            self.transistor_names, self.wire_names = memory_subcircuits.generate_precharge_lp(subcircuit_filename, self.name)

        self.initial_transistor_sizes["ptran_precharge_side_nmos"] = 15
        self.initial_transistor_sizes["ptran_equalization_nmos"] = 1

        return self.initial_transistor_sizes

    def generate_top(self):
        print("Generating precharge and equalization circuit")
        if consts.use_lp_transistor == 0:
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
            if consts.use_lp_transistor == 0:
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
        self.delay_weight = consts.DELAY_WEIGHT_RAM
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
        self.delay_weight = consts.DELAY_WEIGHT_RAM

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


        if consts.use_lp_transistor == 0 :
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