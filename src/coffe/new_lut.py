from __future__ import annotations
from dataclasses import dataclass, field, InitVar

import math, os, sys
from typing import List, Dict, Any, Tuple, Union, Type

import src.coffe.data_structs as c_ds
import src.coffe.utils as utils

import src.coffe.lut_subcircuits as lut_subcircuits

import src.coffe.mux as mux

import src.coffe.new_logic_block as lb_lib

import src.coffe.constants as consts

@dataclass
class LUTInputDriver(c_ds.SizeableCircuit):
    """ LUT input driver class. LUT input drivers can optionally support register feedback.
        They can also be connected to FF register input select. 
        Thus, there are 4  types of LUT input drivers: "default", "default_rsel", "reg_fb" and "reg_fb_rsel".
        When a LUT input driver is created in the '__init__' function, it is given one of these types.
        All subsequent processes (netlist generation, area calculations, etc.) will use this type attribute.
        """
    name: str = None
    lut_input_key: str = None # 'a' 'b' 'c', etc -> which input of the LUT this driver is connected to
    type: str = None # LUT input driver type ("default", "default_rsel", "reg_fb" and "reg_fb_rsel")
    delay_weight: float = None         # Delay weight in a representative critical path
    use_tgate: bool = None
    
    # Update wire dependancies -> basically circuits that would be required to estimate the layout of wires within the self circuit
    local_mux: lb_lib.LocalMux = None

    def __post_init__(self):
        self.name = f"lut_{self.lut_input_key}_driver"
        super().__post_init__()


    def generate(self, subcircuit_filename: str) -> Dict[str, float | int]:
        """ Generate SPICE netlist based on type of LUT input driver. """
        if not self.use_tgate :
            self.transistor_names, self.wire_names = lut_subcircuits.generate_ptran_lut_driver(subcircuit_filename, self.sp_name, self.type)
        else :
            self.transistor_names, self.wire_names = lut_subcircuits.generate_tgate_lut_driver(subcircuit_filename, self.sp_name, self.type)
        
        # Initialize transistor sizes (to something more reasonable than all min size, but not necessarily a good choice, depends on architecture params)
        if not self.use_tgate :
            if self.type != "default":
                self.initial_transistor_sizes["inv_" + self.sp_name + "_0_nmos"] = 2
                self.initial_transistor_sizes["inv_" + self.sp_name + "_0_pmos"] = 2
            if self.type == "reg_fb" or self.type == "reg_fb_rsel":
                self.initial_transistor_sizes["ptran_" + self.sp_name + "_0_nmos"] = 2
                self.initial_transistor_sizes["rest_" + self.sp_name + "_pmos"] = 1
            if self.type != "default":
                self.initial_transistor_sizes["inv_" + self.sp_name + "_1_nmos"] = 1
                self.initial_transistor_sizes["inv_" + self.sp_name + "_1_pmos"] = 1
            self.initial_transistor_sizes["inv_" + self.sp_name + "_2_nmos"] = 2
            self.initial_transistor_sizes["inv_" + self.sp_name + "_2_pmos"] = 2
        else :
            if self.type != "default":
                self.initial_transistor_sizes["inv_" + self.sp_name + "_0_nmos"] = 2
                self.initial_transistor_sizes["inv_" + self.sp_name + "_0_pmos"] = 2
            if self.type == "reg_fb" or self.type == "reg_fb_rsel":
                self.initial_transistor_sizes["tgate_" + self.sp_name + "_0_nmos"] = 2
                self.initial_transistor_sizes["tgate_" + self.sp_name + "_0_pmos"] = 2
            if self.type != "default":
                self.initial_transistor_sizes["inv_" + self.sp_name + "_1_nmos"] = 1
                self.initial_transistor_sizes["inv_" + self.sp_name + "_1_pmos"] = 1
            self.initial_transistor_sizes["inv_" + self.sp_name + "_2_nmos"] = 2
            self.initial_transistor_sizes["inv_" + self.sp_name + "_2_pmos"] = 2
               
        return self.initial_transistor_sizes
     
    def update_area(self, area_dict: Dict[str, float], width_dict: Dict[str, float]) -> float:
        """ Update area. To do this, we use area_dict which is a dictionary, maintained externally, that contains
            the area of everything. It is expected that area_dict will have all the information we need to calculate area.
            We update area_dict and width_dict with calculations performed in this function. 
            We also return the area of this driver, which is calculated based on driver type. """
        
        area = 0.0
        
        if not self.use_tgate :  
            # Calculate area based on input type
            if self.type != "default":
                area += area_dict["inv_" + self.sp_name + "_0"]
            if self.type == "reg_fb" or self.type == "reg_fb_rsel":
                area += 2*area_dict["ptran_" + self.sp_name + "_0"]
                area += area_dict["rest_" + self.sp_name]
            if self.type != "default":
                area += area_dict["inv_" + self.sp_name + "_1"]
            area += area_dict["inv_" + self.sp_name + "_2"]
        
        else :
            # Calculate area based on input type
            if self.type != "default":
                area += area_dict["inv_" + self.sp_name + "_0"]
            if self.type == "reg_fb" or self.type == "reg_fb_rsel":
                area += 2*area_dict["tgate_" + self.sp_name + "_0"]
            if self.type != "default":
                area += area_dict["inv_" + self.sp_name + "_1"]
            area += area_dict["inv_" + self.sp_name + "_2"]

        # Add SRAM cell if this is a register feedback input
        if self.type == "reg_fb" or self.type == "ref_fb_rsel":
            area += area_dict["sram"]
        
        # Calculate layout width
        width = math.sqrt(area)
        
        # Add to dictionaries
        area_dict[self.sp_name] = area
        width_dict[self.sp_name] = width
        
        return area
        
    def update_wires(self, width_dict: Dict[str, float], wire_lengths: Dict[str, float], wire_layers: Dict[str, float]) -> List[str]:
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict.
            Wires differ based on input type. """
        
        # getting name of min len wire local mux from global to just save myself the pain of changing all these variable names
        # global min_len_wire
        # min_len_wire = consts.min_len_wire
        # local_mux_key = f"local_mux_L{min_len_wire['len']}_uid{min_len_wire['id']}"

        # TODO assert that all wires being updated
        local_mux_key = self.local_mux.sp_name

        if not self.use_tgate :  
            # Update wire lengths and wire layers
            if self.type == "default_rsel" or self.type == "reg_fb_rsel":
                wire_lengths["wire_" + self.sp_name + "_0_rsel"] = width_dict[self.sp_name]/4 + width_dict["lut"] + width_dict["ff"]/4 
                wire_layers["wire_" + self.sp_name + "_0_rsel"] = consts.LOCAL_WIRE_LAYER
            if self.type == "default_rsel":
                wire_lengths["wire_" + self.sp_name + "_0_out"] = width_dict["inv_" + self.sp_name + "_0"]/4 + width_dict["inv_" + self.sp_name + "_2"]/4
                wire_layers["wire_" + self.sp_name + "_0_out"] = consts.LOCAL_WIRE_LAYER
            if self.type == "reg_fb" or self.type == "reg_fb_rsel":
                wire_lengths["wire_" + self.sp_name + "_0_out"] = width_dict["inv_" + self.sp_name + "_0"]/4 + width_dict["ptran_" + self.sp_name + "_0"]/4
                wire_layers["wire_" + self.sp_name + "_0_out"] = consts.LOCAL_WIRE_LAYER
                wire_lengths["wire_" + self.sp_name + "_0"] = width_dict["ptran_" + self.sp_name + "_0"]
                wire_layers["wire_" + self.sp_name + "_0"] = consts.LOCAL_WIRE_LAYER
            if self.type == "default":
                wire_lengths["wire_" + self.sp_name] = width_dict[local_mux_key]/4 + width_dict["inv_" + self.sp_name + "_2"]/4
                wire_layers["wire_" + self.sp_name] = consts.LOCAL_WIRE_LAYER
            else:
                wire_lengths["wire_" + self.sp_name] = width_dict["inv_" + self.sp_name + "_1"]/4 + width_dict["inv_" + self.sp_name + "_2"]/4
                wire_layers["wire_" + self.sp_name] = consts.LOCAL_WIRE_LAYER

        else :
            # Update wire lengths and wire layers
            if self.type == "default_rsel" or self.type == "reg_fb_rsel":
                wire_lengths["wire_" + self.sp_name + "_0_rsel"] = width_dict[self.sp_name]/4 + width_dict["lut"] + width_dict["ff"]/4 
                wire_layers["wire_" + self.sp_name + "_0_rsel"] = consts.LOCAL_WIRE_LAYER
            if self.type == "default_rsel":
                wire_lengths["wire_" + self.sp_name + "_0_out"] = width_dict["inv_" + self.sp_name + "_0"]/4 + width_dict["inv_" + self.sp_name + "_2"]/4
                wire_layers["wire_" + self.sp_name + "_0_out"] = consts.LOCAL_WIRE_LAYER
            if self.type == "reg_fb" or self.type == "reg_fb_rsel":
                wire_lengths["wire_" + self.sp_name + "_0_out"] = width_dict["inv_" + self.sp_name + "_0"]/4 + width_dict["tgate_" + self.sp_name + "_0"]/4
                wire_layers["wire_" + self.sp_name + "_0_out"] = consts.LOCAL_WIRE_LAYER
                wire_lengths["wire_" + self.sp_name + "_0"] = width_dict["tgate_" + self.sp_name + "_0"]
                wire_layers["wire_" + self.sp_name + "_0"] = consts.LOCAL_WIRE_LAYER
            if self.type == "default":
                wire_lengths["wire_" + self.sp_name] = width_dict[local_mux_key]/4 + width_dict["inv_" + self.sp_name + "_2"]/4
                wire_layers["wire_" + self.sp_name] = consts.LOCAL_WIRE_LAYER
            else:
                wire_lengths["wire_" + self.sp_name] = width_dict["inv_" + self.sp_name + "_1"]/4 + width_dict["inv_" + self.sp_name + "_2"]/4
                wire_layers["wire_" + self.sp_name] = consts.LOCAL_WIRE_LAYER
            

@dataclass
class LUTInputNotDriver(c_ds.SizeableCircuit):
    """ LUT input not-driver. This is the complement driver. """
    name: str = None
    lut_input_key: str = None # 'a' 'b' 'c', etc -> which input of the LUT this driver is connected to
    type: str = None # LUT input driver type ("default", "default_rsel", "reg_fb" and "reg_fb_rsel")
    delay_weight: float = None         # Delay weight in a representative critical path
    use_tgate: bool = None

    def __post_init__(self):
        self.name = f"lut_{self.lut_input_key}_driver_not"
        super().__post_init__()

    
    def generate(self, subcircuit_filename: str) -> Dict[str, float | int]:
        """ Generate not-driver SPICE netlist """
        if not self.use_tgate :
            self.transistor_names, self.wire_names = lut_subcircuits.generate_ptran_lut_not_driver(subcircuit_filename, self.sp_name)
        else :
            self.transistor_names, self.wire_names = lut_subcircuits.generate_tgate_lut_not_driver(subcircuit_filename, self.sp_name)
        
        # Initialize transistor sizes (to something more reasonable than all min size, but not necessarily a good choice, depends on architecture params)
        self.initial_transistor_sizes[f"inv_{self.sp_name}_1_nmos"] = 1
        self.initial_transistor_sizes[f"inv_{self.sp_name}_1_pmos"] = 1
        self.initial_transistor_sizes[f"inv_{self.sp_name}_2_nmos"] = 2
        self.initial_transistor_sizes[f"inv_{self.sp_name}_2_pmos"] = 2
       
        return self.initial_transistor_sizes

    
    def update_area(self, area_dict: Dict[str, float], width_dict: Dict[str, float]) -> float:
        """ Update area. To do this, we use area_dict which is a dictionary, maintained externally, that contains
            the area of everything. It is expected that area_dict will have all the information we need to calculate area.
            We update area_dict and width_dict with calculations performed in this function. 
            We also return the area of this not_driver."""
        
        area = (area_dict["inv_" + self.sp_name + "_1"] +
                area_dict["inv_" + self.sp_name + "_2"])
        width = math.sqrt(area)
        area_dict[self.sp_name] = area
        width_dict[self.sp_name] = width
        
        return area
    
    
    def update_wires(self, width_dict: Dict[str, float], wire_lengths: Dict[str, float], wire_layers: Dict[str, float]) -> List[str]:
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """
        
        # Update wire lengths
        wire_lengths["wire_" + self.sp_name] = (width_dict["inv_" + self.sp_name + "_1"] + width_dict["inv_" + self.sp_name + "_2"])/4
        # Update wire layers
        wire_layers["wire_" + self.sp_name] = consts.LOCAL_WIRE_LAYER
    
@dataclass
class LUTInput(c_ds.CompoundCircuit):
    """ LUT input. It contains a LUT input driver and a LUT input not driver (complement). 
        The muxing on the LUT input is defined here """

    name: str = None
    lut_input_key: str = None # 'a' 'b' 'c', etc -> which input of the LUT this driver is connected to
    delay_weight: float = None         # Delay weight in a representative critical path

    Rsel: str = None # Register select signal, if the FF can get its input directly from this LUT input
    Rfb: str = None

    use_tgate: bool = None

    # Initialized in __post_init__
    driver: LUTInputDriver = None
    not_driver: LUTInputNotDriver = None
    type: str = None # LUT input driver type ("default", "default_rsel", "reg_fb" and "reg_fb_rsel")

    def __post_init__(self):
        # super().__post_init__()
        # Use self.name here as its just looking to see if the input key 'a', 'b', etc is a substr inside of the Rfb string
        if self.Rfb and self.name in self.Rfb:
            if self.Rsel == self.name:
                self.type = "reg_fb_rsel"
            else:
                self.type = "reg_fb"
        else:
            if self.Rsel == self.name:
                self.type = "default_rsel"
            else:
                self.type = "default"
        self.driver = LUTInputDriver(
            id = 0,
            lut_input_key = self.lut_input_key, 
            type = self.type, 
            delay_weight = self.delay_weight,
            use_tgate = self.use_tgate, 
        )
        self.not_driver = LUTInputNotDriver(
            id = 0,
            lut_input_key = self.lut_input_key, 
            type = self.type, 
            delay_weight = self.delay_weight,
            use_tgate = self.use_tgate, 
        )
        

    def generate(self, subcircuit_filename: str) -> Dict[str, float | int]:
        """ Generate both driver and not-driver SPICE netlists. """
        
        print("Generating lut " + self.name + "-input driver (" + self.type + ")")

        # Generate the driver
        init_tran_sizes = self.driver.generate(subcircuit_filename)
        # Generate the not driver
        init_tran_sizes.update(self.not_driver.generate(subcircuit_filename))

        return init_tran_sizes

     
    def update_area(self, area_dict: Dict[str, float], width_dict: Dict[str, float]) -> float:
        """ Update area. We update the area of the the driver and the not driver by calling area update functions
            inside these objects. We also return the total area of this input driver."""        
        
        # Calculate area of driver
        driver_area = self.driver.update_area(area_dict, width_dict)
        # Calculate area of not driver
        not_driver_area = self.not_driver.update_area(area_dict, width_dict)
        # Return the sum
        return driver_area + not_driver_area
    
    
    def update_wires(self, width_dict: Dict[str, float], wire_lengths: Dict[str, float], wire_layers: Dict[str, float]) -> List[str]:
        """ Update wire lengths and wire layers for input driver and not_driver """
        
        # Update driver wires
        self.driver.update_wires(width_dict, wire_lengths, wire_layers)
        # Update not driver wires
        self.not_driver.update_wires(width_dict, wire_lengths, wire_layers)
        
        
    def print_details(self, report_file):
        """ Print LUT input driver details """
        
        utils.print_and_write(report_file, "  LUT input " + self.sp_name + " type: " + self.type)


@dataclass
class LUTInputDriverLoad(c_ds.LoadCircuit):
    """ LUT input driver load. This load consists of a wire as well as the gates
        of a particular level in the LUT. """

    # TODO update to use sp_name instead of name
    name: str = None
    use_tgate: bool = None
    use_fluts: bool = None

    # def __post_init__(self):
    #     super().__post_init__()
    
    def update_wires(self, width_dict: Dict[str, float], wire_lengths: Dict[str, float], wire_layers: Dict[str, float], ratio: float):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """

        # Update wire lengths
        wire_lengths["wire_lut_" + self.name + "_driver_load"] = width_dict["lut"] * ratio
        
        # Update set wire layers
        wire_layers["wire_lut_" + self.name + "_driver_load"] = consts.LOCAL_WIRE_LAYER
        
        
    def generate(self, subcircuit_filename: str, K: int):
        
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

@dataclass
class LUT(c_ds.SizeableCircuit):
    """ Lookup table. """

    name: str = "lut"

    # transistor parameters
    use_tgate: bool = None
    use_finfet: bool = None

    # LUT related parameters
    use_fluts: bool = None
    K: int = None
    Rfb: str = None
    Rsel: str = None

    # Dicts to store related circuits (yet not in a compound circuit fashion?)
    input_drivers: Dict[str, LUTInputDriver] = field(default_factory=dict)
    input_driver_loads: Dict[str, LUTInputDriverLoad] = field(default_factory=dict)

    def __post_init__(self):
        # This should just set our sp_name and other common functionality to all sizeable circuits
        super().__post_init__()
        assert self.K >= 4, "COFFE currently supports LUTs with 4 or more inputs"
        self.delay_weight = consts.DELAY_WEIGHT_LUT_A + consts.DELAY_WEIGHT_LUT_B + consts.DELAY_WEIGHT_LUT_C + consts.DELAY_WEIGHT_LUT_D
        if self.K >= 5:
            self.delay_weight += consts.DELAY_WEIGHT_LUT_E
        if self.K >= 6:
            self.delay_weight += consts.DELAY_WEIGHT_LUT_F
        # Create a LUT input driver and load for each LUT input

        tempK: int = self.K
        if self.use_fluts:
            tempK = self.K - 1

        for i in range(tempK):
            name: str = chr(i+97)
            if name == "a":
                delay_weight = consts.DELAY_WEIGHT_LUT_A
            elif name == "b":
                delay_weight = consts.DELAY_WEIGHT_LUT_B
            elif name == "c":
                delay_weight = consts.DELAY_WEIGHT_LUT_C
            elif name == "d":
                delay_weight = consts.DELAY_WEIGHT_LUT_D
            elif name == "e":
                delay_weight = consts.DELAY_WEIGHT_LUT_E
            elif name == "f":
                delay_weight = consts.DELAY_WEIGHT_LUT_F
            else:
                raise Exception("No delay weight definition for LUT input " + name)
            # TODO update input drivers to use sp_name and get rid of this hackiness
            self.input_drivers[name] = LUTInput(
                id = 0,
                name = name,
                lut_input_key = name,
                Rsel = self.Rsel,
                Rfb = self.Rfb,
                delay_weight = delay_weight,
            )
            self.input_driver_loads[name] = LUTInputDriverLoad(
                id = 0,
                name = name,
                use_tgate = self.use_tgate,
                use_fluts = self.use_fluts,
            )

        if self.use_fluts:
            if self.K == 5:
                name = "e"
                delay_weight = consts.DELAY_WEIGHT_LUT_E
            else:
                name = "f"
                delay_weight = consts.DELAY_WEIGHT_LUT_F
            self.input_drivers[name] = LUTInput(
                id = 0,
                name = name,
                lut_input_key = name,
                Rsel = self.Rsel,
                Rfb = self.Rfb,
                delay_weight = delay_weight,
            )
            self.input_driver_loads[name] = LUTInputDriverLoad(
                id = 0,
                name = name,
                use_tgate = self.use_tgate,
                use_fluts = self.use_fluts,
            )           
        
    
    def generate(self, subcircuit_filename: str, min_tran_width: float) -> Dict[str, float | int]:
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

   
    def update_area(self, area_dict: Dict[str, float], width_dict: Dict[str, float]) -> float:
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
                wire_layers["wire_lut_sram_driver"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_sram_driver_out"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_L1"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_L2"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_L3"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_int_buffer"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_int_buffer_out"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_L4"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_L5"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_L6"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_out_buffer"] = consts.LOCAL_WIRE_LAYER
              
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
                wire_layers["wire_lut_sram_driver"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_sram_driver_out"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_L1"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_L2"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_L3"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_int_buffer"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_int_buffer_out"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_L4"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_L5"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_out_buffer"] = consts.LOCAL_WIRE_LAYER
                
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
                wire_layers["wire_lut_sram_driver"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_sram_driver_out"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_L1"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_L2"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_int_buffer"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_int_buffer_out"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_L3"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_L4"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_out_buffer"] = consts.LOCAL_WIRE_LAYER

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
                wire_layers["wire_lut_sram_driver"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_sram_driver_out"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_L1"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_L2"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_L3"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_int_buffer"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_int_buffer_out"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_L4"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_L5"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_L6"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_out_buffer"] = consts.LOCAL_WIRE_LAYER
              
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
                wire_layers["wire_lut_sram_driver"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_sram_driver_out"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_L1"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_L2"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_L3"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_int_buffer"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_int_buffer_out"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_L4"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_L5"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_out_buffer"] = consts.LOCAL_WIRE_LAYER
                
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
                wire_layers["wire_lut_sram_driver"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_sram_driver_out"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_L1"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_L2"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_int_buffer"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_int_buffer_out"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_L3"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_L4"] = consts.LOCAL_WIRE_LAYER
                wire_layers["wire_lut_out_buffer"] = consts.LOCAL_WIRE_LAYER
          
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
        
    
    def _generate_6lut(self, subcircuit_filename: str, min_tran_width: float):
        """ This function created the lut subcircuit and all the drivers and driver not subcircuits """
        print("Generating 6-LUT")

        # COFFE doesn't support 7-input LUTs check_arch_params in utils.py will handle this
        # we currently don't support 7-input LUTs that are fracturable, that would require more code changes but can be done with reasonable effort.
        # assert use_fluts == False
        
        # Call the generation function
        if not self.use_tgate :
            # use pass transistors
            self.transistor_names, self.wire_names = lut_subcircuits.generate_ptran_lut6(subcircuit_filename, min_tran_width, self.use_finfet)

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
            self.transistor_names, self.wire_names = lut_subcircuits.generate_tgate_lut6(subcircuit_filename, min_tran_width, self.use_finfet)

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
        self.input_drivers["a"].generate(subcircuit_filename)
        self.input_drivers["b"].generate(subcircuit_filename)
        self.input_drivers["c"].generate(subcircuit_filename)
        self.input_drivers["d"].generate(subcircuit_filename)
        self.input_drivers["e"].generate(subcircuit_filename)
        self.input_drivers["f"].generate(subcircuit_filename)
        
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
        self.input_drivers["a"].generate(subcircuit_filename)
        self.input_drivers["b"].generate(subcircuit_filename)
        self.input_drivers["c"].generate(subcircuit_filename)
        self.input_drivers["d"].generate(subcircuit_filename)
        self.input_drivers["e"].generate(subcircuit_filename)

        if use_fluts:
            self.input_drivers["f"].generate(subcircuit_filename)
        
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
        self.input_drivers["a"].generate(subcircuit_filename)
        self.input_drivers["b"].generate(subcircuit_filename)
        self.input_drivers["c"].generate(subcircuit_filename)
        self.input_drivers["d"].generate(subcircuit_filename)
        
        # Generate input driver loads
        self.input_driver_loads["a"].generate(subcircuit_filename, self.K)
        self.input_driver_loads["b"].generate(subcircuit_filename, self.K)
        self.input_driver_loads["c"].generate(subcircuit_filename, self.K)
        self.input_driver_loads["d"].generate(subcircuit_filename, self.K)

        # *TODO: Add the second level of fracturability where the input f also will be used
        # If this is one level fracutrable LUT then the e input will still be used
        if use_fluts:
            self.input_drivers["e"].generate(subcircuit_filename)
            self.input_driver_loads["e"].generate(subcircuit_filename, self.K)
        
        return self.initial_transistor_sizes