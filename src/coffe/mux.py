from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple, Union, Type

import src.coffe.mux_subcircuits as mux_subcircuits
import src.coffe.data_structs as c_ds
# import src.coffe.fpga as fpga
import src.coffe.constants as consts


@dataclass
class Mux2Lvl(c_ds.SizeableCircuit):
    # Describes a MUX circuit, could be for any of the many muxes in an FPGA
    name: str                       = None # Used during spMux write out to determine the names of Tx size parameters & subckt names, Ex. sb_mux_uid_0
    required_size: int              = None # How big should this mux be (dictated by architecture specs)
    # Below are initialized during __post_init__
    implemented_size: int           = None # How big did we make the mux (it is possible that we had to make the mux bigger for level sizes to work out, this is how big the mux turned out)
    num_unused_inputs: int          = None # This is simply the implemented_size-required_size
    sram_per_mux: int               = None # Number of SRAM cells per mux
    level1_size: int                = None # Size of the first level of muxing
    level2_size: int                = None # Size of the second level of muxing
    use_tgate: bool                 = None # use pass transistor or transmission gates -> coming from Model class

    def __post_init__(self):
        # Calculate level sizes and number of SRAMs per mux
        self.level2_size = int( math.sqrt( self.required_size ) )
        self.level1_size = int( math.ceil( float(self.required_size) / self.level2_size ) )
        self.implemented_size = self.level1_size * self.level2_size
        self.num_unused_inputs = self.implemented_size - self.required_size
        self.sram_per_mux = self.level1_size + self.level2_size
        
        self.sp_name = self.get_sp_name()


    def generate_tgate_2lvl_mux(self, sp_fpath: str) -> Tuple[ List[str], List[str] ]:
        """ 
            Creates two-level MUX circuits
            There are 3 different types of MUX that are generated depending on how 'on' the mux is
                1. Fully on (both levels are on) circuit name: mux_name + "_on"
                2. Partially on (only level 1 is on) circuit name: mux_name + "_partial"
                3. Off (both levels are off) circuit name: mux_name + "_off"
        """
        # Write out spice netlist for this mux
        #   Includes:
        #   - mux_off       -> mux sp circuit when all inputs OFF                                                       -> LOAD
        #   - mux_on_only   -> mux sp circuit when a single input path is ON, all others OFF, input passes to output    -> IN/OUT
        #   - mux_partial   -> mux sp circuit when the input connects to an ON level 1 switch and an OFF level 2 switch -> LOAD
        #   - mux_on        -> mux on only with 2 stage driver @ the end                                                -> IN/OUT
    
        # Open SPICE file for appending
        spice_file = open(sp_fpath, 'a')
        
        # Get spice name with id string suffix
        sp_name = self.get_sp_name()

        # Generate SPICE subcircuits
        mux_subcircuits._generate_tgate_driver(spice_file, sp_name, self.implemented_size)
        mux_subcircuits._generate_tgate_2lvl_mux_off(spice_file, sp_name, self.implemented_size)
        mux_subcircuits._generate_tgate_2lvl_mux_partial(spice_file, sp_name, self.implemented_size, self.level1_size)
        mux_subcircuits._generate_tgate_2lvl_mux_on(spice_file, sp_name, self.implemented_size, self.level1_size, self.level2_size)
        
        # Create the fully-on MUX circuit
        spice_file.write("******************************************************************************************\n")
        spice_file.write("* " + sp_name + " subcircuit (" + str(self.implemented_size) + ":1), fully turned on \n")
        spice_file.write("******************************************************************************************\n")
        spice_file.write(".SUBCKT " + sp_name + "_on n_in n_out n_gate n_gate_n n_vdd n_gnd\n")
        spice_file.write("X" + sp_name + "_on_mux_only n_in n_1_1 n_gate n_gate_n n_vdd n_gnd " + sp_name + "_on_mux_only\n")
        spice_file.write("X" + sp_name + "_driver n_1_1 n_out n_vdd n_gnd " + sp_name + "_driver\n")
        spice_file.write(".ENDS\n\n\n")
        
        # Close SPICE file
        spice_file.close()
        
        # Create a list of all transistors used in this subcircuit
        tran_names_list = []
        tran_names_list.append(f"tgate_{sp_name}_L1_nmos")
        tran_names_list.append(f"tgate_{sp_name}_L1_pmos")
        tran_names_list.append(f"tgate_{sp_name}_L2_nmos")
        tran_names_list.append(f"tgate_{sp_name}_L2_pmos")
        # tran_names_list.append("rest_" + sp_name + "_pmos")
        tran_names_list.append(f"inv_{sp_name}_1_nmos")
        tran_names_list.append(f"inv_{sp_name}_1_pmos")
        tran_names_list.append(f"inv_{sp_name}_2_nmos")
        tran_names_list.append(f"inv_{sp_name}_2_pmos")
        
        # Create a list of all wires used in this subcircuit
        wire_names_list = []
        wire_names_list.append(f"wire_{sp_name}_driver")
        wire_names_list.append(f"wire_{sp_name}_L1")
        wire_names_list.append(f"wire_{sp_name}_L2")
        
        return tran_names_list, wire_names_list
    
    def generate_ptran_2lvl_mux(self, sp_fpath: str) -> Tuple[ List[str], List[str] ]:
        """ 
        Creates two-level MUX circuits
        There are 3 different types of MUX that are generated depending on how 'on' the mux is
            1. Fully on (both levels are on) circuit name: mux_name + "_on"
            2. Partially on (only level 1 is on) circuit name: mux_name + "_partial"
            3. Off (both levels are off) circuit name: mux_name + "_off"
        """
    
        # Write out spice netlist for this mux
        #   Includes:
        #   - mux_off       -> mux sp circuit when all inputs OFF                                                       -> LOAD
        #   - mux_on_only   -> mux sp circuit when a single input path is ON, all others OFF, input passes to output    -> IN/OUT
        #   - mux_partial   -> mux sp circuit when the input connects to an ON level 1 switch and an OFF level 2 switch -> LOAD
        #   - mux_on        -> mux on only with 2 stage driver @ the end                                                -> IN/OUT
        # ...

        # Open SPICE file for appending
        spice_file = open(sp_fpath, 'a')

        # Get spice name with id string suffix
        sp_name = self.get_sp_name()

        
        # Generate SPICE subcircuits
        mux_subcircuits._generate_ptran_driver(spice_file, sp_name, self.implemented_size)
        mux_subcircuits._generate_ptran_2lvl_mux_off(spice_file, sp_name, self.implemented_size)
        mux_subcircuits._generate_ptran_2lvl_mux_partial(spice_file, sp_name, self.implemented_size, self.level1_size)
        mux_subcircuits._generate_ptran_2lvl_mux_on(spice_file, sp_name, self.implemented_size, self.level1_size, self.level2_size)
        
        # Create the fully-on MUX circuit
        spice_file.write("******************************************************************************************\n")
        spice_file.write("* " + sp_name + " subcircuit (" + str(self.implemented_size) + ":1), fully turned on \n")
        spice_file.write("******************************************************************************************\n")
        spice_file.write(".SUBCKT " + sp_name + "_on n_in n_out n_gate n_gate_n n_vdd n_gnd\n")
        spice_file.write("X" + sp_name + "_on_mux_only n_in n_1_1 n_gate n_gate_n n_vdd n_gnd " + sp_name + "_on_mux_only\n")
        spice_file.write("X" + sp_name + "_driver n_1_1 n_out n_vdd n_gnd " + sp_name + "_driver\n")
        spice_file.write(".ENDS\n\n\n")
        
        # Close SPICE file
        spice_file.close()
        
        # Create a list of all transistors used in this subcircuit
        tran_names_list = []
        tran_names_list.append("ptran_" + sp_name + "_L1_nmos")
        tran_names_list.append("ptran_" + sp_name + "_L2_nmos")
        tran_names_list.append("rest_" + sp_name + "_pmos")
        tran_names_list.append("inv_" + sp_name + "_1_nmos")
        tran_names_list.append("inv_" + sp_name + "_1_pmos")
        tran_names_list.append("inv_" + sp_name + "_2_nmos")
        tran_names_list.append("inv_" + sp_name + "_2_pmos")
        
        # Create a list of all wires used in this subcircuit
        wire_names_list = []
        wire_names_list.append("wire_" + sp_name + "_driver")
        wire_names_list.append("wire_" + sp_name + "_L1")
        wire_names_list.append("wire_" + sp_name + "_L2")
        
        return tran_names_list, wire_names_list

    def generate(self, subckt_lib_fpath: str) -> Dict[str, int | float]:

        # Get spice name with id string suffix
        sp_name = self.get_sp_name()
        
        # Write out the spice netlist for this SubCkt definition
        if not self.use_tgate:
            self.transistor_names, self.wire_names = self.generate_ptran_2lvl_mux(subckt_lib_fpath)
            # Initialize transistor sizes (to something more reasonable than all min size, but not necessarily a good choice, depends on architecture params)
            self.initial_transistor_sizes["ptran_" + sp_name + "_L1_nmos"] = 3
            self.initial_transistor_sizes["ptran_" + sp_name + "_L2_nmos"] = 4
            self.initial_transistor_sizes["rest_" + sp_name + "_pmos"] = 1
            self.initial_transistor_sizes["inv_" + sp_name + "_1_nmos"] = 8
            self.initial_transistor_sizes["inv_" + sp_name + "_1_pmos"] = 4
            self.initial_transistor_sizes["inv_" + sp_name + "_2_nmos"] = 10
            self.initial_transistor_sizes["inv_" + sp_name + "_2_pmos"] = 20

        else:
            self.transistor_names, self.wire_names = self.generate_tgate_2lvl_mux(subckt_lib_fpath)
            # Initialize transistor sizes (to something more reasonable than all min size, but not necessarily a good choice, depends on architecture params)
            self.initial_transistor_sizes["tgate_" + sp_name + "_L1_nmos"] = 3
            self.initial_transistor_sizes["tgate_" + sp_name + "_L1_pmos"] = 3
            self.initial_transistor_sizes["tgate_" + sp_name + "_L2_nmos"] = 4
            self.initial_transistor_sizes["tgate_" + sp_name + "_L2_pmos"] = 4
            self.initial_transistor_sizes["inv_" + sp_name + "_1_nmos"] = 8
            self.initial_transistor_sizes["inv_" + sp_name + "_1_pmos"] = 4
            self.initial_transistor_sizes["inv_" + sp_name + "_2_nmos"] = 10
            self.initial_transistor_sizes["inv_" + sp_name + "_2_pmos"] = 20
        
        # Assert that all transistors in this mux have been updated with initial_transistor_sizes
        assert set(list(self.initial_transistor_sizes.keys())) == set(self.transistor_names)
        
        # Will be dict of ints if FinFET or discrete Tx, can be floats if bulk
        return self.initial_transistor_sizes

    def update_area(self, area_dict: dict, width_dict: dict):

        # Get spice name with id string suffix
        sp_name = self.get_sp_name()

        # Calculate & update the area and widths of this mux
        # Find all area keys associated with inverters in this mux
        inv_id = 1
        inv_area_keys = []
        for tx_param in self.transistor_names:
            if "inv" in tx_param:
                assert tx_param == f"inv_{sp_name}_{inv_id}", f"Invalid inv name {tx_param} for mux {sp_name}"
                inv_area_keys.append(
                    f"inv_{sp_name}_{inv_id}"
                )
                inv_id += 1
        
        tx_type_key = "ptran" if not self.use_tgate else "tgate"

        # Pass Gate
        if not self.use_tgate:
            area = (
                (self.level1_size * self.level2_size) * area_dict[f"{tx_type_key}_{sp_name}_L1"] +    # Level 1 Mux Area = L1_size * L2_size * Area of a single L1 switch
                self.level2_size * area_dict[f"{tx_type_key}_{sp_name}_L2"] +                         # Level 2 Mux Area = L2_size * Area of a single L2 switch
                area_dict[f"rest_{sp_name}"] +                                                        # Level Restorer Mux Area -> Pass tran mux requires a level restorer that pulls voltage back up to VDD
                sum(area_dict[inv_area_key] for inv_area_key in inv_area_keys)                          # Inv Area = Sum of all invs in the mux -> These drive the mux output load
            )
        # Transmission Gate
        else: 
            area = (
                (self.level1_size * self.level2_size) * area_dict[f"{tx_type_key}_{sp_name}_L1"] +    # Level 1 Mux Area = L1_size * L2_size * Area of a single L1 switch
                self.level2_size * area_dict[f"{tx_type_key}_{sp_name}_L2"] +                         # Level 2 Mux Area = L2_size * Area of a single L2 switch
                sum(area_dict[inv_area_key] for inv_area_key in inv_area_keys)                          # Inv Area = Sum of all invs in the mux -> These drive the mux output load
            )
        width = math.sqrt(area)                                 # Width w/o SRAM = sqrt(area)           -> Assumes square aspect ratio here
        width_with_sram = math.sqrt(area_with_sram)             # Width w/ SRAM  = sqrt(area_with_sram) -> Assumes square aspect ratio here

        # Mux area including SRAM
        area_with_sram = (
            area +                                                          # Logic area calculated above
            (self.level1_size + self.level2_size) * area_dict["sram"]       # SRAM area = (L1_size + L2_size) * Area of a single SRAM cell
        )      

        # Update the width & area dicts
        width_dict[sp_name] = width                           
        area_dict[sp_name] = area
        area_dict[f"{sp_name}_sram"] = area_with_sram
        width_dict[f"{sp_name}_sram"] = width_with_sram

    def update_wires(self, width_dict: Dict[str, float], wire_lengths: Dict[str, float], wire_layers: Dict[str, int], ratio: float):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """
        
        # Get spice name with id string suffix
        sp_name = self.get_sp_name()

        # Verify that indeed the wires we will update come from the ones initialized in the generate function
        drv_wire_key = [key for key in self.wire_names if f"wire_{sp_name}_driver" in key][0]
        l1_wire_key = [key for key in self.wire_names if f"wire_{sp_name}_L1" in key][0]
        l2_wire_key = [key for key in self.wire_names if f"wire_{sp_name}_L2" in key][0]

        # Not sure where these keys are coming from TODO figure that out and verify them
        s1_inv_key = f"inv_{sp_name}_1"
        s2_inv_key = f"inv_{sp_name}_2"
        
        # Assert keys exist in wire_names, unneeded but following convension if wire keys not coming from wire_names
        assert set(self.wire_names) == set([drv_wire_key, l1_wire_key, l2_wire_key]), "Only updating a subset of all wires"

        # Update wire lengths
        # Divide both driver widths by 4 to get wire from pin -> driver input? Maybe just a back of envelope estimate 
        wire_lengths[drv_wire_key] = (width_dict[s1_inv_key] + width_dict[s2_inv_key]) / 4
        wire_lengths[l1_wire_key] = width_dict[sp_name] * ratio
        wire_lengths[l2_wire_key] = width_dict[sp_name] * ratio
        
        # Update set wire layers
        wire_layers[drv_wire_key] = consts.consts.LOCAL_WIRE_LAYER
        wire_layers[l1_wire_key] = consts.consts.LOCAL_WIRE_LAYER
        wire_layers[l2_wire_key] = consts.consts.LOCAL_WIRE_LAYER



@dataclass
class Mux2to1(c_ds.SizeableCircuit):
    # Describes a simple 2:1 Mux circuit
    use_tgate: bool                 = None # use pass transistor or transmission gates -> coming from Model class

    def __post_init__(self):
        super().__post_init__()

    def generate_ptran_2_to_1_mux(self, spice_filename: str) -> Tuple[ List[str], List[str] ]:
        """ Generate a 2:1 pass-transistor MUX with shared SRAM """
        mux_name = self.sp_name

        # Open SPICE file for appending
        spice_file = open(spice_filename, 'a')
        
        # Create the 2:1 MUX circuit
        spice_file.write("******************************************************************************************\n")
        spice_file.write("* " + mux_name + " subcircuit (2:1)\n")
        spice_file.write("******************************************************************************************\n")
        spice_file.write(".SUBCKT " + mux_name + " n_in n_out n_gate n_gate_n n_vdd n_gnd\n")
        spice_file.write("Xptran_" + mux_name + " n_in n_1_1 n_gate n_gnd ptran Wn=ptran_" + mux_name + "_nmos\n")
        spice_file.write("Xwire_" + mux_name + " n_1_1 n_1_2 wire Rw='wire_" + mux_name + "_res/2' Cw='wire_" + mux_name + "_cap/2'\n")
        spice_file.write("Xwire_" + mux_name + "_h n_1_2 n_1_3 wire Rw='wire_" + mux_name + "_res/2' Cw='wire_" + mux_name + "_cap/2'\n")
        spice_file.write("Xptran_" + mux_name + "_h n_gnd n_1_3 n_gnd n_gnd ptran Wn=ptran_" + mux_name + "_nmos\n")
        spice_file.write("Xrest_" + mux_name + " n_1_2 n_2_1 n_vdd n_gnd rest Wp=rest_" + mux_name + "_pmos\n")
        spice_file.write("Xinv_" + mux_name + "_1 n_1_2 n_2_1 n_vdd n_gnd inv Wn=inv_" + mux_name + "_1_nmos Wp=inv_" + mux_name + "_1_pmos\n")
        spice_file.write("Xwire_" + mux_name + "_driver n_2_1 n_2_2 wire Rw=wire_" + mux_name + "_driver_res Cw=wire_" + mux_name + "_driver_cap\n")
        spice_file.write("Xinv_" + mux_name + "_2 n_2_2 n_out n_vdd n_gnd inv Wn=inv_" + mux_name + "_2_nmos Wp=inv_" + mux_name + "_2_pmos\n")
        spice_file.write(".ENDS\n\n\n")
        spice_file.close()
        
        # Create a list of all transistors used in this subcircuit
        tran_names_list = []
        tran_names_list.append("ptran_" + mux_name + "_nmos")
        tran_names_list.append("rest_" + mux_name + "_pmos")
        tran_names_list.append("inv_" + mux_name + "_1_nmos")
        tran_names_list.append("inv_" + mux_name + "_1_pmos")
        tran_names_list.append("inv_" + mux_name + "_2_nmos")
        tran_names_list.append("inv_" + mux_name + "_2_pmos")
        
        # Create a list of all wires used in this subcircuit
        wire_names_list = []
        wire_names_list.append("wire_" + mux_name)
        wire_names_list.append("wire_" + mux_name + "_driver")
        
        return tran_names_list, wire_names_list 

    def generate_tgate_2_to_1_mux(self, spice_filename: str) -> Tuple[ List[str], List[str] ]:
        """ Generate a 2:1 pass-transistor MUX with shared SRAM """

        mux_name = self.sp_name
        # Open SPICE file for appending
        spice_file = open(spice_filename, 'a')
        
        # Create the 2:1 MUX circuit
        spice_file.write("******************************************************************************************\n")
        spice_file.write("* " + mux_name + " subcircuit (2:1)\n")
        spice_file.write("******************************************************************************************\n")
        spice_file.write(".SUBCKT " + mux_name + " n_in n_out n_gate n_gate_n n_vdd n_gnd\n")
        spice_file.write("Xtgate_" + mux_name + " n_in n_1_1 n_gate n_gate_n n_vdd n_gnd tgate Wn=tgate_" + mux_name + "_nmos Wp=tgate_" + mux_name + "_pmos\n")
        spice_file.write("Xwire_" + mux_name + " n_1_1 n_1_2 wire Rw='wire_" + mux_name + "_res/2' Cw='wire_" + mux_name + "_cap/2'\n")
        spice_file.write("Xwire_" + mux_name + "_h n_1_2 n_1_3 wire Rw='wire_" + mux_name + "_res/2' Cw='wire_" + mux_name + "_cap/2'\n")
        spice_file.write("Xtgate_" + mux_name + "_h n_gnd n_1_3 n_gnd n_vdd n_vdd n_gnd tgate Wn=tgate_" + mux_name + "_nmos Wp=tgate_" + mux_name + "_pmos\n")
        # spice_file.write("Xrest_" + mux_name + " n_1_2 n_2_1 n_vdd n_gnd rest Wp=rest_" + mux_name + "_pmos\n")
        spice_file.write("Xinv_" + mux_name + "_1 n_1_2 n_2_1 n_vdd n_gnd inv Wn=inv_" + mux_name + "_1_nmos Wp=inv_" + mux_name + "_1_pmos\n")
        spice_file.write("Xwire_" + mux_name + "_driver n_2_1 n_2_2 wire Rw=wire_" + mux_name + "_driver_res Cw=wire_" + mux_name + "_driver_cap\n")
        spice_file.write("Xinv_" + mux_name + "_2 n_2_2 n_out n_vdd n_gnd inv Wn=inv_" + mux_name + "_2_nmos Wp=inv_" + mux_name + "_2_pmos\n")
        spice_file.write(".ENDS\n\n\n")
        spice_file.close()
        
        # Create a list of all transistors used in this subcircuit
        tran_names_list = []
        tran_names_list.append("tgate_" + mux_name + "_nmos")
        tran_names_list.append("tgate_" + mux_name + "_pmos")
        # tran_names_list.append("rest_" + mux_name + "_pmos")
        tran_names_list.append("inv_" + mux_name + "_1_nmos")
        tran_names_list.append("inv_" + mux_name + "_1_pmos")
        tran_names_list.append("inv_" + mux_name + "_2_nmos")
        tran_names_list.append("inv_" + mux_name + "_2_pmos")
        
        # Create a list of all wires used in this subcircuit
        wire_names_list = []
        wire_names_list.append("wire_" + mux_name)
        wire_names_list.append("wire_" + mux_name + "_driver")
        
        return tran_names_list, wire_names_list  

    def generate(self, subcircuit_filename: str):
        # Write out the spice netlist for this SubCkt definition        
        if not self.use_tgate :
            self.transistor_names, self.wire_names = self.generate_ptran_2_to_1_mux(subcircuit_filename)
            # Initialize transistor sizes (to something more reasonable than all min size, but not necessarily a good choice, depends on architecture params)
            self.initial_transistor_sizes["ptran_" + self.sp_name + "_nmos"] = 2
            self.initial_transistor_sizes["rest_" + self.sp_name + "_pmos"] = 1
            self.initial_transistor_sizes["inv_" + self.sp_name + "_1_nmos"] = 1
            self.initial_transistor_sizes["inv_" + self.sp_name + "_1_pmos"] = 1
            self.initial_transistor_sizes["inv_" + self.sp_name + "_2_nmos"] = 4
            self.initial_transistor_sizes["inv_" + self.sp_name + "_2_pmos"] = 4
        else :
            self.transistor_names, self.wire_names = self.generate_tgate_2_to_1_mux(subcircuit_filename)
            # Initialize transistor sizes (to something more reasonable than all min size, but not necessarily a good choice, depends on architecture params)
            self.initial_transistor_sizes["tgate_" + self.sp_name + "_nmos"] = 2
            self.initial_transistor_sizes["tgate_" + self.sp_name + "_pmos"] = 2
            self.initial_transistor_sizes["inv_" + self.sp_name + "_1_nmos"] = 1
            self.initial_transistor_sizes["inv_" + self.sp_name + "_1_pmos"] = 1
            self.initial_transistor_sizes["inv_" + self.sp_name + "_2_nmos"] = 4
            self.initial_transistor_sizes["inv_" + self.sp_name + "_2_pmos"] = 4
      
        return self.initial_transistor_sizes 

    def update_area(self, area_dict: Dict[str, float], width_dict: Dict[str, float]) -> float:
        if not self.use_tgate:
            area = (2*area_dict["ptran_" + self.sp_name] +
                    area_dict["rest_" + self.sp_name] +
                    area_dict["inv_" + self.sp_name + "_1"] +
                    area_dict["inv_" + self.sp_name + "_2"])
        else :
            area = (2*area_dict["tgate_" + self.sp_name] +
                    area_dict["inv_" + self.sp_name + "_1"] +
                    area_dict["inv_" + self.sp_name + "_2"])

        area = area + area_dict["sram"]
        width = math.sqrt(area)
        area_dict[self.sp_name] = area
        width_dict[self.sp_name] = width

        return area
    
    def update_wires(self, width_dict: Dict[str, float], wire_lengths: Dict[str, float], wire_layers: Dict[str, int]):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """
    
        # Update wire lengths
        if not self.use_tgate :
            wire_lengths["wire_" + self.name] = width_dict["ptran_" + self.name]
        else :
            wire_lengths["wire_" + self.name] = width_dict["tgate_" + self.name]

        wire_lengths["wire_" + self.name + "_driver"] = (width_dict["inv_" + self.name + "_1"] + width_dict["inv_" + self.name + "_1"])/4
        
        # Update wire layers
        wire_layers["wire_" + self.name] = consts.LOCAL_WIRE_LAYER
        wire_layers["wire_" + self.name + "_driver"] = consts.LOCAL_WIRE_LAYER