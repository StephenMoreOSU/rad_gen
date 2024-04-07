from __future__ import annotations
from dataclasses import dataclass, field, InitVar

import math, os, sys
from typing import List, Dict, Any, Tuple, Union, Type

import src.coffe.data_structs as c_ds
import src.coffe.utils as utils
import src.coffe.mux as mux

import src.coffe.new_ble as ble_lib
import src.coffe.new_lut as lut_lib

import src.coffe.constants as consts

@dataclass
class LocalMux(mux.Mux2Lvl):
    name: str                                       = "local_mux"

    def __post_init__(self):
        super().__post_init__()
        self.delay_weight = consts.DELAY_WEIGHT_LOCAL_MUX

    def __hash__(self):
        return id(self)

    def generate(self, subckt_lib_fpath: str) -> Dict[str, int | float]:
        # Call Parent Mux generate, does correct generation but has incorrect initial tx sizes
        self.initial_transistor_sizes = super().generate(subckt_lib_fpath)
        # Set initial transistor sizes to values appropriate for an CB mux
        for tx_name in self.initial_transistor_sizes:
            # Set size of Level 1 transistors
            if "L1" in tx_name:
                self.initial_transistor_sizes[tx_name] = 2
            # Set size of Level 2 transistors
            elif "L2" in tx_name:
                self.initial_transistor_sizes[tx_name] = 2
            # Set 1st stage inverter pmos
            elif "inv" in tx_name and "_1_pmos" in tx_name:
                self.initial_transistor_sizes[tx_name] = 2
            # Set 1st stage inverter nmos
            elif "inv" in tx_name and "_1_nmos" in tx_name:
                self.initial_transistor_sizes[tx_name] = 2
            # Set level restorer if this is a pass transistor mux
            elif "rest" in tx_name:
                self.initial_transistor_sizes[tx_name] = 1

        # Assert that all transistors in this mux have been updated with initial_transistor_sizes
        assert set(list(self.initial_transistor_sizes.keys())) == set(self.transistor_names)
        
        # Will be dict of ints if FinFET or discrete Tx, can be floats if bulk
        return self.initial_transistor_sizes
    
    def update_wires(self, width_dict: Dict[str, float], wire_lengths: Dict[str, float], wire_layers: Dict[str, int], ratio: float):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """

        # Update wire lengths
        wire_lengths["wire_" + self.sp_name + "_L1"] = width_dict[self.sp_name] * ratio
        wire_lengths["wire_" + self.sp_name + "_L2"] = width_dict[self.sp_name] * ratio
        # Update wire layers
        wire_layers["wire_" + self.sp_name + "_L1"] = consts.LOCAL_WIRE_LAYER
        wire_layers["wire_" + self.sp_name + "_L2"] = consts.LOCAL_WIRE_LAYER




@dataclass
class LocalRoutingWireLoad(c_ds.LoadCircuit):
    """
        Local routing wire load
    """
    name: str = "local_routing_wire_load"
    lut_input_usage_assumption: float = None        # How many LUT inputs are we assuming are used in this logic cluster? (%)
    
    # Input to _compute_load
    local_mux: LocalMux = None      # The localMux instantiated this load + used for compute_load
    
    # Set in _compute_load
    mux_inputs_per_wire: int = None     # Total number of local mux inputs per wire
    on_inputs_per_wire: int = None      # Number of on inputs connected to each wire 
    partial_inputs_per_wire: int = None # Number of partially on inputs connected to each wire
    off_inputs_per_wire: int = None     # Number of off inputs connected to each wire

    def __post_init__(self):
        super().__post_init__()

    def local_routing_load_generate(self, spice_filename: str) -> List[str]:
        """ """

        subckt_local_mux: str = self.local_mux.sp_name

        num_on: int = self.on_inputs_per_wire
        num_partial: int = self.partial_inputs_per_wire
        num_off: int = self.off_inputs_per_wire

        # The first thing we want to figure out is the interval between each on load and each partially on load
        # Number of partially on muxes between each on mux
        interval_partial = int(num_partial/num_on)
        # Number of off muxes between each partially on mux
        interval_off = int(num_off/num_partial)

        # Open SPICE file for appending
        spice_file = open(spice_filename, 'a')
        
        spice_file.write("******************************************************************************************\n")
        spice_file.write("* Local routing wire load\n")
        spice_file.write("******************************************************************************************\n")
        spice_file.write(f".SUBCKT {self.sp_name} n_in n_out n_gate n_gate_n n_vdd n_gnd n_vdd_local_mux_on\n")
        
        num_total = int(num_on + num_partial + num_off)
        interval_counter_partial = 0
        interval_counter_off = 0
        on_counter = 0
        partial_counter = 0
        off_counter = 0
        
        # Initialize nodes
        current_node = "n_in"
        next_node = "n_1"
        
        # Wire defintions
        wire_local_routing: str = f"wire_local_routing_{self.get_param_str()}"

        # Write SPICE file while keeping correct intervals between partial and on muxes
        for i in range(num_total):
            if interval_counter_partial == interval_partial and on_counter < num_on:
                    # Add an on mux
                    interval_counter_partial = 0
                    on_counter = on_counter + 1
                    if on_counter == num_on:
                        spice_file.write(f"X{wire_local_routing}_" + str(i+1) + " " + current_node + " " + next_node + f" wire Rw='{wire_local_routing}_res/" + str(num_total) + f"' Cw='{wire_local_routing}_cap/" + str(num_total) + "'\n")
                        spice_file.write(f"X{subckt_local_mux}_on_" + str(on_counter) + " " + next_node + f" n_out n_gate n_gate_n n_vdd_local_mux_on n_gnd {subckt_local_mux}_on\n")
                    else:
                        spice_file.write(f"X{wire_local_routing}_" + str(i+1) + " " + current_node + " " + next_node + f" wire Rw='{wire_local_routing}_res/" + str(num_total) + f"' Cw='{wire_local_routing}_cap/" + str(num_total) + "'\n")
                        spice_file.write(f"X{subckt_local_mux}_on_" + str(on_counter) + " " + next_node + " n_hang_" + str(on_counter) + f" n_gate n_gate_n n_vdd n_gnd {subckt_local_mux}_on\n")    
            else:
                if interval_counter_off == interval_off and partial_counter < num_partial:
                    # Add a partially on mux
                    interval_counter_off = 0
                    interval_counter_partial = interval_counter_partial + 1
                    partial_counter = partial_counter + 1
                    spice_file.write(f"X{wire_local_routing}_" + str(i+1) + " " + current_node + " " + next_node + f" wire Rw='{wire_local_routing}_res/" + str(num_total) + f"' Cw='{wire_local_routing}_cap/" + str(num_total) + "'\n")
                    spice_file.write(f"X{subckt_local_mux}_partial_" + str(partial_counter) + " " + next_node + f" n_gate n_gate_n n_vdd n_gnd {subckt_local_mux}_partial\n")
                else:
                    # Add an off mux
                    interval_counter_off = interval_counter_off + 1
                    off_counter = off_counter + 1
                    spice_file.write(f"X{wire_local_routing}_" + str(i+1) + " " + current_node + " " + next_node + f" wire Rw='{wire_local_routing}_res/" + str(num_total) + f"' Cw='{wire_local_routing}_cap/" + str(num_total) + "'\n")
                    spice_file.write(f"X{subckt_local_mux}_off_" + str(off_counter) + " " + next_node + f" n_gate n_gate_n n_vdd n_gnd {subckt_local_mux}_off\n")
            # Update current and next nodes        
            current_node = next_node
            next_node = "n_" + str(i+2)
        spice_file.write(".ENDS\n\n\n")

        spice_file.close()
    
    
        # Create a list of all wires used in this subcircuit
        wire_names_list = []
        wire_names_list.append(wire_local_routing)
        
        return wire_names_list

    def generate(self, subcircuit_filename: str, specs: c_ds.Specs):
        print("Generating local routing wire load")
        # Compute load (number of on/partial/off per wire)
        self._compute_load(specs)
        # Generate SPICE deck
        self.wire_names = self.local_routing_load_generate(subcircuit_filename)


    def _compute_load(self, specs: c_ds.Specs):
        """ Compute the load on a local routing wire (number of on/partial/off) """
        # preconditions for this function
        assert self.lut_input_usage_assumption is not None, "lut_input_usage_assumption must be set before computing load"

        # The first thing we are going to compute is how many local mux inputs are connected to a local routing wire
        # This is a function of local_mux size, N, K, I and Ofb
        num_local_routing_wires = specs.I + specs.N * specs.num_ble_local_outputs
        self.mux_inputs_per_wire = self.local_mux.implemented_size * specs.N * specs.K / num_local_routing_wires
        
        # Now we compute how many "on" inputs are connected to each routing wire
        # This is a funtion of lut input usage, number of lut inputs and number of local routing wires
        num_local_muxes_used = self.lut_input_usage_assumption * specs.N * specs.K
        self.on_inputs_per_wire = int(num_local_muxes_used / num_local_routing_wires)
        # We want to model for the case where at least one "on" input is connected to the local wire, so make sure it's at least 1
        if self.on_inputs_per_wire < 1:
            self.on_inputs_per_wire = 1
        
        # Now we compute how many partially on muxes are connected to each wire
        # The number of partially on muxes is equal to (level2_size - 1)*num_local_muxes_used/num_local_routing_wire
        # We can figure out the number of muxes used by using the "on" assumption and the number of local routing wires.
        self.partial_inputs_per_wire = int((self.local_mux.level2_size - 1.0) * num_local_muxes_used / num_local_routing_wires)
        # Make it at least 1
        if self.partial_inputs_per_wire < 1:
            self.partial_inputs_per_wire = 1
        
        # Number of off inputs is simply the difference
        self.off_inputs_per_wire = self.mux_inputs_per_wire - self.on_inputs_per_wire - self.partial_inputs_per_wire


    def update_wires(self, width_dict: Dict[str, float], wire_lengths: Dict[str, float], wire_layers: Dict[str, int], local_routing_wire_load_length: float):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """
        
        # TODO get wire keys from self.wire_names, assert that we update all keys in self.wire_names

        # Update wire lengths
        wire_lengths["wire_local_routing"] = width_dict["logic_cluster"]
        if local_routing_wire_load_length != 0:
            wire_lengths["wire_local_routing"] = local_routing_wire_load_length
        # Update wire layers
        wire_layers["wire_local_routing"] = consts.LOCAL_WIRE_LAYER


@dataclass
class LocalBLEOutputLoad(c_ds.LoadCircuit):
    name: str = "local_ble_output_load"

    # Child Subckts
    local_routing_wire_load: LocalRoutingWireLoad = None
    lut_input_driver: lut_lib.LUTInputDriver = None

    def __post_init__(self):
        super().__post_init__()

    def generate_local_ble_output_load(self, spice_filename: str) -> List[str]:
        # Open SPICE file for appending
        spice_file = open(spice_filename, 'a')
        
        wire_loc_ble_out_fb = f"wire_local_ble_output_{self.get_param_str()}_feedback"

        spice_file.write("******************************************************************************************\n")
        spice_file.write("* Local BLE output load\n")
        spice_file.write("******************************************************************************************\n")
        spice_file.write(f".SUBCKT {self.sp_name} n_in n_gate n_gate_n n_vdd n_gnd\n")
        spice_file.write(f"X{wire_loc_ble_out_fb} n_in n_1_1 wire Rw='{wire_loc_ble_out_fb}_res' Cw='{wire_loc_ble_out_fb}_cap'\n")
        spice_file.write(f"X{self.local_routing_wire_load.sp_name}_1 n_1_1 n_1_2 n_gate n_gate_n n_vdd n_gnd n_vdd {self.local_routing_wire_load.sp_name}\n")
        spice_file.write(f"X{self.lut_input_driver.sp_name}_1 n_1_2 n_hang1 vsram vsram_n n_hang2 n_hang3 n_vdd n_gnd {self.lut_input_driver.sp_name}\n\n")
        spice_file.write(".ENDS\n\n\n")
        
        spice_file.close()
        
        # Create a list of all wires used in this subcircuit
        wire_names_list = []
        wire_names_list.append("wire_local_ble_output_feedback")
        
        return wire_names_list

    def generate(self, subcircuit_filename):
        self.wire_names = self.generate_local_ble_output_load(subcircuit_filename)
    
    
    def update_wires(self, width_dict: Dict[str, float], wire_lengths: Dict[str, float], wire_layers: Dict[str, int], ble_ic_dis: float):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """
        
        # Update wire lengths
        wire_lengths["wire_local_ble_output_feedback"] = width_dict["logic_cluster"]
        if ble_ic_dis != 0:
            wire_lengths["wire_local_ble_output_feedback"] = ble_ic_dis
        # Update wire layers
        wire_layers["wire_local_ble_output_feedback"] = consts.LOCAL_WIRE_LAYER


@dataclass
class LogicCluster(c_ds.CompoundCircuit):
    """
        Logic Cluster
    """
    name: str = "logic_cluster"

    # General FPGA Parameters relevant to the logic cluster
    num_lc_inputs: int = None # Number of total inputs to the logic cluster (I)
    cluster_size: int = None # cluster size (N)
    
    # General Circuit Params
    use_tgate: bool = None
    use_finfet: bool = None
    use_fluts: bool = None
    
    # Local Mux specific params
    local_mux_size_required: int = None
    num_local_mux_per_tile: int = None
    
    # BLE specific Params   
    enable_carry_chain: bool = None     # Enable carry chain in BLEs
    FAs_per_flut: int = None            # Hard Adders per fracturable LUT
    carry_skip_periphery_count: int = None # TODO figure out 
    
    num_inputs_per_ble: int = None # Number of inputs per BLE in cluster (K)
    num_fb_outputs_per_ble: int = None #Number of outputs per BLE that feed back to local muxes (Ofb)
    num_gen_outputs_per_ble: int = None # Number of general outputs sent to SBs per BLE (Or)
    Rsel: str = None # Rsel value for the BLEs in this logic cluster
    Rfb: str = None # Rfb value for the BLEs in this logic cluster


    # SizeableCircuits (created in __post_init__) in rough order of input -> outputs
    local_mux: LocalMux = None # Local Mux
    local_routing_wire_load: LocalRoutingWireLoad = None # Local Routing Wire Load
    ble: ble_lib.BLE = None # BLE sizeable circuit
    local_ble_output_load: LocalBLEOutputLoad = None # Output load of BLE load circuit

    def __post_init__(self):
        # Create BLE
        self.ble = ble_lib.BLE(
            id = 0,
            cluster_size = self.cluster_size,
            # Per BLE Params
            num_lut_inputs = self.num_inputs_per_ble,
            num_local_outputs = self.num_fb_outputs_per_ble,
            num_general_outputs = self.num_gen_outputs_per_ble,
            Rsel = self.Rsel,
            Rfb = self.Rfb,
            enable_carry_chain = self.enable_carry_chain,
            FAs_per_flut = self.FAs_per_flut,
            carry_skip_periphery_count = self.carry_skip_periphery_count,
            # Transistor Parameters
            use_tgate = self.use_tgate,
            use_finfet = self.use_finfet,
            use_fluts = self.use_fluts,
        )
        # Create Local Mux
        self.local_mux = LocalMux(
            id = 0,
            required_size = self.local_mux_size_required,
        )
        # Create Local Routing Wire Load (load on a single wire going into local muxes)
        self.local_routing_wire_load = LocalRoutingWireLoad(
            id = 0,
            lut_input_usage_assumption = consts.LUT_INPUT_USAGE_ASSUMPTION,
            local_mux = self.local_mux,
        )
        self.local_ble_output_load = LocalBLEOutputLoad(
            id = 0,
            local_routing_wire_load = self.local_routing_wire_load,
            lut_input_driver = self.ble.lut.input_drivers["a"].driver, # Pass in the LUT input driver for "a" input
        )
        # OLD BLE
        # self.ble = _BLE(
        #     K, Or, Ofb, Rsel, Rfb, use_tgate, use_finfet, use_fluts, enable_carry_chain,
        #     FAs_per_flut, carry_skip_periphery_count, N,
        #     gen_r_wire,
        #     self.local_ble_output_load,
        #     self.gen_ble_output_load
        # )



    def generate(self, subcircuits_filename: str, min_tran_width, specs: c_ds.Specs) -> Dict[str, int | float]:
        print("Generating logic cluster")
        init_tran_sizes = {}
        init_tran_sizes.update(
            self.ble.generate(subcircuits_filename, min_tran_width)
        )
        init_tran_sizes.update(
            self.local_mux.generate(subcircuits_filename)
        )
        # Don't pass these into init_tran sizes as they are only load circuits
        self.local_routing_wire_load.generate(subcircuits_filename, specs)
        self.local_ble_output_load.generate(subcircuits_filename)
        
        return init_tran_sizes


