
import src.coffe.fpga as fpga


from src.coffe.sb_mux import _SwitchBlockMUX
from src.coffe.cb_mux import _ConnectionBlockMUX


import src.coffe.utils as utils

from typing import Dict, List, Tuple, Union, Any
from dataclasses import dataclass
import copy
import math, os

# @dataclass
# class BLEOutputLoadSBInfo:
#     sb_mux: _SwitchBlockMUX
#     num_on_assumption: int 
#     num_partial: int
#     num_off: int


class _GeneralBLEOutputLoad:
    """ Logic cluster output load (i.e. general BLE output load). 
        Made up of a wire loaded by SB muxes. """

    def __init__(self, sb_muxes: List[_SwitchBlockMUX], sb_on_idx: int ):
        # switch block mux thats ON at the output of this load
        self.sb_mux_on: _SwitchBlockMUX = sb_muxes[sb_on_idx]
        # Subcircuit name
        self.name: str = f"general_ble_output_load{self.sb_mux_on.param_str}"
        # basename for this subckt, name without the parameter suffix
        self.basename: str = f"general_ble_output_load"
        self.param_str: str = self.name.replace(self.basename, "")
        # Associated switch block mux which loads the BLE
        # self.sb_muxes = sb_muxes
        # Assumed routing channel usage, we need this for load calculation 
        self.channel_usage_assumption = 0.5
        # Assumed number of 'on' SB muxes on cluster output, needed for load calculation
        self.num_sb_mux_on_assumption = 1
        # Number of 'partially on' SB muxes on cluster output (calculated in compute_load)
        self.num_sb_mux_partial = -1
        # Number of 'off' SB muxes on cluster output (calculated in compute_load)
        self.num_sb_mux_off = -1
        # List of wires in this subcircuit
        self.wire_names = []
        # The general routing wire length associated with this output load
        # self.gen_r_wire : dict = gen_r_wire 
        # Multi Wire Length Support
        # Variables used for SB support
        # Which SB in our list of SBs do we assume is ON in this case? or in other words, which SB is connected to BLE output?
        self.sb_on_idx = sb_on_idx
        self.sb_muxes_info = [ {"sb_mux": sb_mux, "num_on": None, "num_partial": None, "num_off": None} for sb_mux in sb_muxes]
        self.total_sb_muxes = None



    def generate_general_ble_output_load(self, spice_filename: str):
        """ Create the cluster output load SPICE deck. We assume 2-level muxes. The load is distributed as
            off, then partial, then on. 
            Inputs are SPICE file, number of SB muxes that are off, then partially on, then on.
            Returns wire names used in this SPICE circuit."""
        
        # Get gen routing wire information
        # wire_length = self.gen_r_wire["len"]
        # wire_id = self.gen_r_wire["id"]

        # for ease defining subckt names here
        # p_str = f"_L{wire_length}_uid{wire_id}"

        # Create a certain number of PARTIAL & OFF SB muxes for each SB type, create a single ON mux for the ON SB mux in this class
        # for sb_mux_info in self.sb_muxes_info:
            
        sb_mux_on = self.sb_muxes_info[self.sb_on_idx]["sb_mux"]
        # sb_mux_name = sb_mux_on.name

        # subckt_sb_mux_on_str = f"{sb_mux_name}_on"
        # subckt_sb_mux_partial_str = f"{sb_mux_name}_partial"
        # subckt_sb_mux_off_str = f"{sb_mux_name}_off"


        # Total number of sb muxes connected to this logic cluster output
        # sb_mux_total = self.num_sb_mux_off + self.num_sb_mux_partial + self.num_sb_mux_on_assumption
        

        # Open SPICE file for appending
        # spice_file = open(spice_filename, 'a')

        # Define the parameters for wire RCs, these will be returned from this function
        # Commenting out while testing to see if the multi sb mux itself is working, dont want to have to change LUT stuff
        wire_general_ble_output_pstr = f"wire_{self.name}"
        
        # wire_general_ble_output_pstr = f"wire_general_ble_output"
        # subckt_general_ble_output_str
        
        # Node definitions
        gnd_node = "n_gnd"
        vdd_node = "n_vdd" 
        # For transmission gates
        nfet_g_node = "n_gate"
        pfet_g_node = "n_gate_n"
        in_node = "n_1_1"
        out_node = "n_out"
        meas_node = "n_meas_point"


        spice_file_lines = []
        # Generating lines of spice file in order of netlist connectivity...
        spice_file_lines += [
            "******************************************************************************************",
            "* General BLE output load",
            "******************************************************************************************",
            # Subckt named based on which sb mux is ON in the path, there exists other SB muxes (OFF + PARTIAL) on the path as well      
            f".SUBCKT general_ble_output_load{sb_mux_on.param_str} {in_node} {out_node} {nfet_g_node} {pfet_g_node} {vdd_node} {gnd_node}"  
        ]
        # For multi wire change to --> general_ble_output_load_L{gen_routing_wire_length}
        # spice_file.write(f".SUBCKT general_ble_output_load{self.sb_mux.param_str} n_1_1 n_out n_gate n_gate_n n_vdd n_gnd\n")
        current_node = "n_1_1"
        next_node = "n_1_2"
        # Write out all of the OFF SB muxes
        total_num_sb_mux_off = 0
        node_it = 0
        for sb_id, sb_mux_info in enumerate(self.sb_muxes_info):
            cur_sb_mux = sb_mux_info["sb_mux"]
            subckt_sb_mux_off_str: str = f"{cur_sb_mux.name}_off"
            for i in range(sb_mux_info["num_off"]):
                spice_file_lines += [
                    f"Xwire_general_ble_output_sb_{sb_id}_{i+1} {current_node} {next_node} wire Rw='{wire_general_ble_output_pstr}_res/{self.total_sb_muxes}' Cw='{wire_general_ble_output_pstr}_cap/{self.total_sb_muxes}'",
                    f"X{cur_sb_mux.name}_off_{i+1} {next_node} {nfet_g_node} {pfet_g_node} {vdd_node} {gnd_node} {subckt_sb_mux_off_str}",
                ]
                current_node = next_node
                next_node = f"n_1_{node_it+3}"
                node_it += 1
                total_num_sb_mux_off += 1
        # Write out all of the partial SB muxes
        total_num_sb_partial = 0
        for sb_id, sb_mux_info in enumerate(self.sb_muxes_info):
            cur_sb_mux = sb_mux_info["sb_mux"]
            subckt_sb_mux_partial_str: str = f"{cur_sb_mux.name}_partial"
            for i in range(sb_mux_info["num_partial"]):
                spice_file_lines += [
                    f"Xwire_general_ble_output_sb_{sb_id}_{i + 1 + total_num_sb_mux_off} {current_node} {next_node} wire Rw='{wire_general_ble_output_pstr}_res/{self.total_sb_muxes}' Cw='{wire_general_ble_output_pstr}_cap/{self.total_sb_muxes}'",
                    f"X{cur_sb_mux.name}_partial_{i + 1} {next_node} {nfet_g_node} {pfet_g_node} {vdd_node} {gnd_node} {subckt_sb_mux_partial_str}",
                ]
                current_node = next_node
                next_node = f"n_1_{node_it + total_num_sb_mux_off + 3}"
                node_it += 1
                total_num_sb_partial += 1
        # Write out all of the ON SB muxes
        total_num_sb_on = 0
        for sb_id, sb_mux_info in enumerate(self.sb_muxes_info):
            cur_sb_mux = sb_mux_info["sb_mux"]
            subckt_sb_mux_on_str: str = f"{cur_sb_mux.name}_on"
            for i in range(sb_mux_info["num_on"]):
                if i == sb_mux_info["num_on"] - 1:
                    spice_file_lines += [
                        f"Xwire_general_ble_output_sb_{sb_id}_{i + 1 + total_num_sb_mux_off + total_num_sb_partial} {current_node} {meas_node} wire Rw='{wire_general_ble_output_pstr}_res/{self.total_sb_muxes}' Cw='{wire_general_ble_output_pstr}_cap/{self.total_sb_muxes}'",
                        f"X{cur_sb_mux.name}_on_{i + 1} {meas_node} {out_node} {nfet_g_node} {pfet_g_node} {vdd_node} {gnd_node} {subckt_sb_mux_on_str}",
                    ]
                else:
                    spice_file_lines += [
                        f"Xwire_general_ble_output_{i + 1 + total_num_sb_mux_off + total_num_sb_partial} {current_node} {next_node} wire Rw='{wire_general_ble_output_pstr}_res/{self.total_sb_muxes}' Cw='{wire_general_ble_output_pstr}_cap/{self.total_sb_muxes}'",
                        f"X{cur_sb_mux.name}_on_{i + 1} {next_node} n_hang_{i} {nfet_g_node} {pfet_g_node} {vdd_node} {gnd_node} {subckt_sb_mux_on_str}",
                    ]    
            current_node = next_node
            next_node = f"n_1_{node_it + total_num_sb_mux_off + total_num_sb_partial + 3}"
            node_it += 1
            total_num_sb_on += 1
        
        # End of Subckt
        spice_file_lines.append(".ENDS\n\n")

        # Write out lines to the file
        with open(spice_filename, 'a') as spice_file:
            for line in spice_file_lines:
                spice_file.write(line + "\n")

        # for i in range(self.num_sb_mux_off):
        #     spice_file.write("Xwire_general_ble_output_" + str(i+1) + " " + current_node + " " + next_node + f" wire Rw='{wire_general_ble_output_pstr}_res/" + str(sb_mux_total) + f"' Cw='{wire_general_ble_output_pstr}_cap/" + str(sb_mux_total) + "'\n")
        #     spice_file.write("Xsb_mux_off_" + str(i+1) + " " + next_node + f" n_gate n_gate_n n_vdd n_gnd {sb_mux_off_str}\n")
        #     current_node = next_node
        #     next_node = "n_1_" + str(i+3)
        # for i in range(self.num_sb_mux_partial):
        #     spice_file.write("Xwire_general_ble_output_" + str(i+self.num_sb_mux_off+1) + " " + current_node + " " + next_node + f" wire Rw='{wire_general_ble_output_pstr}_res/" + str(sb_mux_total) + f"' Cw='{wire_general_ble_output_pstr}_cap/" + str(sb_mux_total) + "'\n")
        #     spice_file.write("Xsb_mux_partial_" + str(i+1) + " " + next_node + f" n_gate n_gate_n n_vdd n_gnd {sb_mux_partial_str}\n")
        #     current_node = next_node
        #     next_node = "n_1_" + str(i+self.num_sb_mux_off+3)
        # for i in range(self.num_sb_mux_on_assumption):
            
        #     # The last 'on' sb_mux needs to have special node names to be able to connect it to the output and also for measurements.
        #     if i == (self.num_sb_mux_on_assumption - 1):
        #         spice_file.write(f"Xwire_general_ble_output_" + str(i + self.num_sb_mux_off + self.num_sb_mux_partial + 1) + " " + current_node + " n_meas_point" 
        #                         + f" wire Rw='{wire_general_ble_output_pstr}_res/" + str(sb_mux_total) + f"' Cw='{wire_general_ble_output_pstr}_cap/" + str(sb_mux_total) + "'\n")
        #         spice_file.write("Xsb_mux_on_" + str(i+1) + f" n_meas_point n_out n_gate n_gate_n n_vdd n_gnd {sb_mux_on_str}\n")
        #     else:
        #         spice_file.write("Xwire_general_ble_output_" + str(i + self.num_sb_mux_off + self.num_sb_mux_partial + 1) + " " + current_node + " " + next_node 
        #                         + f" wire Rw='{wire_general_ble_output_pstr}_res/" + str(sb_mux_total) + f"' Cw='{wire_general_ble_output_pstr}_cap/" + str(sb_mux_total) + "'\n")
        #         spice_file.write("Xsb_mux_on_" + str(i+1) + " " + next_node + " n_hang_" + str(i) + f" n_gate n_gate_n n_vdd n_gnd {sb_mux_on_str}\n")
        #     current_node = next_node
        #     next_node = "n_1_" + str(i+self.num_sb_mux_off + self.num_sb_mux_partial + 3)

        # spice_file.write(".ENDS\n\n\n")
        
        # spice_file.close()
        
        # Create a list of all wires used in this subcircuit
        wire_names_list = []
        wire_names_list.append(wire_general_ble_output_pstr)
        
        return wire_names_list
        
    def generate(self, subcircuit_filename, specs):
        """ Compute cluster output load load and generate SPICE netlist. """
        
        self._compute_load(specs)
        self.wire_names = self.generate_general_ble_output_load(subcircuit_filename)
        
        
    def update_wires(self, width_dict: dict, wire_lengths: dict, wire_layers: dict, h_dist: float, height: float):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """
        
        # The BLE output wire is the wire that allows a BLE output to reach routing wires in
        # the routing channels. This wire spans some fraction of a tile. We can set what that
        # fraction is with the output track-access span (track-access locality).


        # gen_ble_out_wire_key = f"wire_general_ble_output_wire_uid{self.gen_r_wire['id']}"

        # Look for keys in the wire names which would be suffixed by some parameter string
        filt_wires = [key for key in self.wire_names if "wire_general_ble_output" in key]
        assert len(filt_wires) == 1, f"Expected 1 wire, found {len(filt_wires)} wires"
        gen_ble_out_wire_key = filt_wires[0]

        # Make sure it exists in the class definition, unncessesary here but just maintaining convention as some wire keys are not coming from wire_names
        assert gen_ble_out_wire_key in self.wire_names, f"Wire {gen_ble_out_wire_key} not found in wire names list"
        
        # height is the lb_height, I wonder why once we have initialized the lb_height we no longer use the output track locality
        wire_lengths[gen_ble_out_wire_key] = width_dict["tile"] * fpga.OUTPUT_TRACK_ACCESS_SPAN
        if height != 0.0:
            wire_lengths[gen_ble_out_wire_key] = (h_dist)

        # Update wire layers
        wire_layers[gen_ble_out_wire_key] = fpga.LOCAL_WIRE_LAYER
      

    def print_details(self, report_file):
        """ Print cluster output load details """
        
        utils.print_and_write(report_file, "  CLUSTER OUTPUT LOAD DETAILS:")
        utils.print_and_write(report_file, "  Total number of SB inputs connected to cluster output: " + str(self.num_sb_mux_off + self.num_sb_mux_partial + self.num_sb_mux_on_assumption))
        utils.print_and_write(report_file, "  Number of 'on' SB MUXes (assumed): " + str(self.num_sb_mux_on_assumption))
        utils.print_and_write(report_file, "  Number of 'partial' SB MUXes: " + str(self.num_sb_mux_partial))
        utils.print_and_write(report_file, "  Number of 'off' SB MUXes: " + str(self.num_sb_mux_off))
        utils.print_and_write(report_file, "")
        
      
    def _compute_load(self, specs):
        """ Calculate how many on/partial/off switch block multiplexers are connected to each cluster output.
            Inputs are FPGA specs object, switch block mux object, assumed channel usage and assumed number of on muxes.
            The function will update the object's off & partial attributes."""
        
        #  _    ___   ___ ___ ___ ___ ___ ___ ___ ___ 
        # | |  | _ ) / __| _ \ __/ __|_ _| __|_ _/ __|
        # | |__| _ \ \__ \  _/ _| (__ | || _| | | (__ 
        # |____|___/ |___/_| |___\___|___|_| |___\___|

        # Number of tracks in the channel connected to LB opins
        num_tracks = specs.W

        # Total number of switch block multiplexers connected to cluster output
        total_load = int(specs.Fcout * num_tracks)
        
        # list of all sbs
        sb_muxes = [sb_mux_info["sb_mux"] for sb_mux_info in self.sb_muxes_info]

        # most frequent SB mux in SBs connected to BLE output
        most_freq_sb_mux_idx = max(range(len(sb_muxes)), key=lambda i: sb_muxes[i].num_per_tile)
        #   ___ ___   ___ ___ ___ ___ ___ ___ ___ ___ 
        #  / __| _ ) / __| _ \ __/ __|_ _| __|_ _/ __|
        #  \__ \ _ \ \__ \  _/ _| (__ | || _| | | (__ 
        #  |___/___/ |___/_| |___\___|___|_| |___\___|
        
        for i, sb_mux_info in enumerate(self.sb_muxes_info):
            
            sb_mux = sb_mux_info["sb_mux"]
            # Let's calculate how many partially on muxes are connected to each output
            # Based on our channel usage assumption, we can determine how many muxes are in use in a tile.
            # The number of used SB muxes equals the number of SB muxes per tile multiplied by the channel usage.
            used_sb_muxes_per_tile = int(self.channel_usage_assumption * sb_mux.num_per_tile)
            
            # TODO make sure that this is the correct sb size to use
            # If we are figuring out how many muxes have the same wire we are using for this BLE output, then they could be all
            # SB muxes that are capable of accepting this wire type as an input. 

            # Size of second level of switch block mux, need this to figure out how many partially on muxes are connected
            sb_level2_size = sb_mux.level2_size

            # Each one of these used muxes comes with a certain amount of partially on paths.
            # We calculate this based on the size of the 2nd muxing level of the switch block muxes
            total_partial_paths = used_sb_muxes_per_tile * (sb_level2_size-1)

            # The partially on paths are connected to both routing wires and cluster outputs
            # We assume that they are distributed evenly across both, which means we need to use the
            # ratio of sb_mux inputs coming from routing wires and coming from cluster outputs to determine
            # how many partially on paths would be connected to cluster outputs
            # total_load * num_cluster_outputs = the total number of LB outputs which will connect to some SB mux 
            # To calc the number of inputs from LB to a specific SB mux, we divide the current num of SB mux by the num of all SB muxes per tile
            # ASSUMPTION: Each LB output connects to a different SB mux input
            sb_mux_freq_ratio = (sb_mux.num_per_tile / sum([sb_mux.num_per_tile for sb_mux in sb_muxes]))
            num_cluster_outputs_per_sb = specs.num_cluster_outputs * sb_mux_freq_ratio
            sb_inputs_from_cluster_outputs = total_load * num_cluster_outputs_per_sb
            
            # We use the required size here because we assume that extra inputs that may be present in the "implemented" mux
            # might be connected to GND or VDD and not to routing wires
            sb_inputs_from_routing = sb_mux.required_size * sb_mux.num_per_tile - sb_inputs_from_cluster_outputs
        
            # Percentage of sb inputs which are used for cluster outputs
            frac_partial_paths_on_cluster_out = float(sb_inputs_from_cluster_outputs)/(sb_inputs_from_cluster_outputs + sb_inputs_from_routing)

            # The total number of partial paths on the cluster outputs is calculated using that fraction
            total_cluster_output_partial_paths = int(frac_partial_paths_on_cluster_out * total_partial_paths)

            # And we divide by the number of cluster outputs (for this switch block) to get partial paths per output
            # We want to have at least 1 partial path per output so we'll ceil it, but only for the sb mux type in question
            # This is a choice we make, and could be done differently, open to exploration

            # Determine which sb_mux_type should be partially ON BLE output based on the most frequent one
            if i == most_freq_sb_mux_idx:
                cluster_output_partial_paths = int(math.ceil(float(total_cluster_output_partial_paths) / num_cluster_outputs_per_sb))
            else:
                cluster_output_partial_paths = int(total_cluster_output_partial_paths / num_cluster_outputs_per_sb)
            # Turn on this mux if it is the one connected to the cluster output
            num_sb_mux_on = 1 if i == self.sb_on_idx else 0
            self.sb_muxes_info[i]["num_partial"] = cluster_output_partial_paths
            self.sb_muxes_info[i]["num_off"] = int(total_load * sb_mux_freq_ratio) - cluster_output_partial_paths - num_sb_mux_on
            self.sb_muxes_info[i]["num_on"] = num_sb_mux_on
        # Add up all the SB muxes which were created
        self.total_sb_muxes = sum([sb_mux_info["num_off"] + sb_mux_info["num_partial"] + sb_mux_info["num_on"] for sb_mux_info in self.sb_muxes_info])
    





class _RoutingWireLoad:
    """ This is the routing wire load for an architecture with direct drive and only one segment length.
        Two-level muxes are assumed and we model for partially on paths. """
        
    def __init__(self, gen_r_wire: dict, sb_muxes: List[_SwitchBlockMUX], driven_sb_mux_idx: int):
        self.sb_mux_on = sb_muxes[driven_sb_mux_idx]
        # Name of this wire
        self.name = f"routing_wire_load{self.sb_mux_on.param_str}"
        # What length of wire is this routing wire load representing?
        self.gen_r_wire = gen_r_wire
        # We assume that half of the wires in a routing channel are used (limited by routability)
        self.channel_usage_assumption = 0.5
        # We assume that half of the cluster inputs are used
        self.cluster_input_usage_assumption = 0.5
        # Switch block load per wire
        self.sb_load_on = -1
        self.sb_load_partial = -1
        self.sb_load_off = -1
        # Connection block load per wire
        self.cb_load_on = -1
        self.cb_load_partial = -1
        self.cb_load_off = -1
        # Switch block per tile
        self.tile_sb_on = []
        self.tile_sb_partial = []
        self.tile_sb_off = []
        # Connection block per tile
        self.tile_cb_on = []
        self.tile_cb_partial = []
        self.tile_cb_off = []
        # List of wire names in the SPICE circuit
        self.wire_names = []
        # Multi Wire Length Support
        # Which SB in our list of SBs do we assume is ON in this case? or in other words, which SB is connected to BLE output?
        self.driven_sb_mux_idx = driven_sb_mux_idx
        # For each tile in load we need an sb_muxes_info object
        self.tile_info = {
            "sb_muxes_info": [ 
                {
                    "sb_mux": sb_mux,
                    "id" : i,
                    # budget of each mode of sb mux for this type
                    "on_budget": None, 
                    "partial_budget": None, 
                    "off_budget": None,
                    # frequency of sb mux type in this tile (percentage)
                    "freq_ratio": sb_mux.num_per_tile / sum([sb_mux_i.num_per_tile for sb_mux_i in sb_muxes])# if sb_mux_i.src_r_wire["id"] == gen_r_wire["id"]])
                # We only want to use muxes which sink this wire type, so only the ones which have a src_r_wire of this type...
                } for i, sb_mux in enumerate(sb_muxes) if sb_mux.src_r_wire["id"] == gen_r_wire["id"]
            ]
        }
        # self.total_sb_muxes = None
        
    def general_routing_load_generate(self, spice_filename: str, sb_mux: _SwitchBlockMUX) -> List[str]:
        """ Generates a routing wire load SPICE deck  """
        
        tile_sb_on = self.tile_sb_on
        tile_sb_partial = self.tile_sb_partial
        tile_sb_off = self.tile_sb_off
        tile_cb_on = self.tile_cb_on
        tile_cb_partial = self.tile_cb_partial
        tile_cb_off = self.tile_cb_off
        gen_r_wire = self.gen_r_wire


        # Open SPICE file for appending
        # spice_file = open(spice_filename, 'a')
        
        ###############################################################
        ## ROUTING WIRE LOAD
        ###############################################################


        # Get gen routing wire information
        wire_length = gen_r_wire["len"]
        wire_id = gen_r_wire["id"]

        # param string suffixes
        p_str_suffix = f"{self.sb_mux_on.param_str}"
        routing_wire_load_pstr = f"wire_gen_routing{p_str_suffix}"
        wire_sb_load_on_pstr = f"wire_sb_load_on{p_str_suffix}"
        wire_sb_load_partial_pstr = f"wire_sb_load_partial{p_str_suffix}"
        wire_sb_load_off_pstr = f"wire_sb_load_off{p_str_suffix}"
        
        # for ease defining subckt names here
        sb_mux_on_str = f"{sb_mux.name}_on"
        sb_mux_partial_str = f"{sb_mux.name}_partial"
        sb_mux_off_str = f"{sb_mux.name}_off"

        # Not using a seperate cb mux for each wire type
        wire_cb_load_on_pstr = f"wire_cb_load_on{p_str_suffix}"
        wire_cb_load_partial_pstr = f"wire_cb_load_partial{p_str_suffix}"
        wire_cb_load_off_pstr = f"wire_cb_load_off{p_str_suffix}"

        subckt_cb_mux_on_str = f"cb_mux_on"
        subckt_cb_mux_partial_str = f"cb_mux_partial"
        subckt_cb_mux_off_str = f"cb_mux_off"

        # wire load sbckt name
        routing_wire_load_subckt_str = f"routing_wire_load{p_str_suffix}"

        spice_file_lines = []
        # First we write the individual tile loads
        # Tiles are generated such that if you drive a wire from the left you get
        #   driver -> tile 4 -> tile 3 -> tile 2 -> tile 1 (driver) -> tile 4 -> etc.
        for i in range(wire_length):
            spice_file_lines += [
                "******************************************************************************************",
                f"* Routing wire load tile {i+1}",
                "******************************************************************************************",
            ]
            # spice_file.write("******************************************************************************************\n")
            # spice_file.write("* Routing wire load tile " + str(i+1) + "\n")
            # spice_file.write("******************************************************************************************\n")
            # If this is Tile 1, we need to add a nodes to which we can connect the ON sb_mux and cb_mux so that we can measure power.
            if i == 0:
                spice_file_lines += [ f".SUBCKT routing_wire_load_tile_{i+1}{p_str_suffix} n_in n_out n_cb_out n_gate n_gate_n n_vdd n_gnd n_vdd_sb_mux_on n_vdd_cb_mux_on" ]
                # spice_file.write(f".SUBCKT routing_wire_load_tile_{i+1}{p_str_suffix} n_in n_out n_cb_out n_gate n_gate_n n_vdd n_gnd n_vdd_sb_mux_on n_vdd_cb_mux_on\n")
            else:
                spice_file_lines += [ f".SUBCKT routing_wire_load_tile_{i+1}{p_str_suffix} n_in n_out n_cb_out n_gate n_gate_n n_vdd n_gnd" ]
                # spice_file.write(f".SUBCKT routing_wire_load_tile_{i+1}{p_str_suffix} n_in n_out n_cb_out n_gate n_gate_n n_vdd n_gnd\n")
            spice_file_lines += [ f"Xwire_gen_routing_1 n_in n_1_1 wire Rw='{routing_wire_load_pstr}_res/{2*wire_length}' Cw='{routing_wire_load_pstr}_cap/{2*wire_length}'\n" ]
            # spice_file.write(f"Xwire_gen_routing_1 n_in n_1_1 wire Rw='{routing_wire_load_pstr}_res/" + str(2*wire_length) + f"' Cw='{routing_wire_load_pstr}_cap/" + str(2*wire_length) + "'\n\n")
            
            # SWITCH BLOCK LOAD
            # Write the ON switch block loads 
            # Loop through all SB types that can load this wire
            for sb_mux_info in self.tile_info["sb_muxes_info"]:
                for sb_on in range(tile_sb_on[i][sb_mux_info["id"]]):
                    # Tile 1 is terminated by a on SB, if this is tile 1 and sb_on 1, we ignore it because we put that one at the end.
                    # if i == 0 and sb_on == self.driven_sb_mux_idx:
                    #     continue

                    sb_mux_on_str = f"{sb_mux_info['sb_mux'].name}_on"
                    spice_file_lines += [ 
                        f"Xwire_sb_uid_{sb_mux_info['id']}_load_on_{sb_on+1} n_1_1 n_1_sb_on_{sb_on+1} wire Rw={wire_sb_load_on_pstr}_res Cw={wire_sb_load_on_pstr}_cap",
                        f"Xsb{sb_mux_info['id']}_load_on_{sb_on+1} n_1_sb_on_{sb_on+1} n_sb_mux_on_{sb_on+1}_hang n_gate n_gate_n n_vdd n_gnd {sb_mux_on_str}\n"
                    ]
                # if i == 0:
                #     if sb_on != 0:
                #         spice_file.write("Xwire_sb_load_on_" + str(sb_on+1) + " n_1_1 n_1_sb_on_" + str(sb_on+1) + f" wire Rw={wire_sb_load_on_pstr}_res Cw={wire_sb_load_on_pstr}_cap\n")
                #         spice_file.write("Xsb_load_on_" + str(sb_on+1) + " n_1_sb_on_" + str(sb_on+1) + " n_sb_mux_on_" + str(sb_on+1) + f"_hang n_gate n_gate_n n_vdd n_gnd {sb_mux_on_str}\n\n")
                # else:
                # spice_file.write("Xwire_sb_load_on_" + str(sb_on+1) + " n_1_1 n_1_sb_on_" + str(sb_on+1) + f" wire Rw={wire_sb_load_on_pstr}_res Cw={wire_sb_load_on_pstr}_cap\n")
                # spice_file.write("Xsb_load_on_" + str(sb_on+1) + " n_1_sb_on_" + str(sb_on+1) + " n_sb_mux_on_" + str(sb_on+1) + f"_hang n_gate n_gate_n n_vdd n_gnd {sb_mux_on_str}\n\n")
            # 
            
            # Write partially on switch block loads
            for sb_mux_info in self.tile_info["sb_muxes_info"]:
                for sb_partial in range(tile_sb_partial[i][sb_mux_info["id"]]):
                    sb_mux_partial_str = f"{sb_mux_info['sb_mux'].name}_partial"
                    spice_file_lines += [
                        f"Xwire_sb{sb_mux_info['id']}_load_partial_{sb_partial+1} n_1_1 n_1_sb_partial_{sb_partial+1} wire Rw={wire_sb_load_partial_pstr}_res Cw={wire_sb_load_partial_pstr}_cap",
                        f"Xsb{sb_mux_info['id']}_load_partial_{sb_partial+1} n_1_sb_partial_{sb_partial+1} n_gate n_gate_n n_vdd n_gnd {sb_mux_partial_str}\n"
                    ]
                # spice_file.write("Xwire_sb_load_partial_" + str(sb_partial+1) + " n_1_1 n_1_sb_partial_" + str(sb_partial+1) + f" wire Rw={wire_sb_load_partial_pstr}_res Cw={wire_sb_load_partial_pstr}_cap\n")
                # spice_file.write("Xsb_load_partial_" + str(sb_partial+1) + " n_1_sb_partial_" + str(sb_partial+1) + f" n_gate n_gate_n n_vdd n_gnd {sb_mux_partial_str}\n\n")
            # Write off switch block loads
            for sb_mux_info in self.tile_info["sb_muxes_info"]:
                for sb_off in range(tile_sb_off[i][sb_mux_info["id"]]):
                    sb_mux_off_str = f"{sb_mux_info['sb_mux'].name}_off"
                    spice_file_lines += [
                        f"Xwire_sb{sb_mux_info['id']}_load_off_{sb_off+1} n_1_1 n_1_sb_off_{sb_off+1} wire Rw={wire_sb_load_off_pstr}_res Cw={wire_sb_load_off_pstr}_cap",
                        f"Xsb{sb_mux_info['id']}_load_off_{sb_off+1} n_1_sb_off_{sb_off+1} n_gate n_gate_n n_vdd n_gnd {sb_mux_off_str}\n"
                    ]
                # spice_file.write("Xwire_sb_load_off_" + str(sb_off+1) + " n_1_1 n_1_sb_off_" + str(sb_off+1) + f" wire Rw={wire_sb_load_off_pstr}_res Cw={wire_sb_load_off_pstr}_cap\n")
                # spice_file.write("Xsb_load_off_" + str(sb_off+1) + " n_1_sb_off_" + str(sb_off+1) + f" n_gate n_gate_n n_vdd n_gnd {sb_mux_off_str}\n\n")
            
            # CONNECTION BLOCK LOAD
            # Write the ON connection block load
            for cb_on in range(tile_cb_on[i]):
                # If this is tile 1, we need to connect the connection block to the n_cb_out net
                if i == 0:
                    # We only connect one of them, so the first one in this case.
                    # This cb_mux is connected to a different power rail so that we can measure power.
                    if cb_on == 0:
                        spice_file_lines += [ 
                            f"Xwire_cb_load_on_{cb_on+1} n_1_1 n_1_cb_on_{cb_on+1} wire Rw={wire_cb_load_on_pstr}_res Cw={wire_cb_load_on_pstr}_cap",
                            f"Xcb_load_on_{cb_on+1} n_1_cb_on_{cb_on+1} n_cb_out n_gate n_gate_n n_vdd_cb_mux_on n_gnd {subckt_cb_mux_on_str}\n"
                        ]
                        # spice_file.write("Xwire_cb_load_on_" + str(cb_on+1) + " n_1_1 n_1_cb_on_" + str(cb_on+1) + f" wire Rw={wire_cb_load_on_pstr}_res Cw={wire_cb_load_on_pstr}_cap\n")
                        # spice_file.write("Xcb_load_on_" + str(cb_on+1) + " n_1_cb_on_" + str(cb_on+1) + f" n_cb_out n_gate n_gate_n n_vdd_cb_mux_on n_gnd {subckt_cb_mux_on_str}\n\n")
                else:
                    spice_file_lines += [
                        f"Xwire_cb_load_on_{cb_on+1} n_1_1 n_1_cb_on_{cb_on+1} wire Rw={wire_cb_load_on_pstr}_res Cw={wire_cb_load_on_pstr}_cap",
                        f"Xcb_load_on_{cb_on+1} n_1_cb_on_{cb_on+1} n_cb_mux_on_{cb_on+1}_hang n_gate n_gate_n n_vdd n_gnd {subckt_cb_mux_on_str}\n"
                    ]
                    # spice_file.write("Xwire_cb_load_on_" + str(cb_on+1) + " n_1_1 n_1_cb_on_" + str(cb_on+1) + f" wire Rw={wire_cb_load_on_pstr}_res Cw={wire_cb_load_on_pstr}_cap\n")
                    # spice_file.write("Xcb_load_on_" + str(cb_on+1) + " n_1_cb_on_" + str(cb_on+1) + " n_cb_mux_on_" + str(cb_on+1) + f"_hang n_gate n_gate_n n_vdd n_gnd {subckt_cb_mux_on_str}\n\n")
            # Write partially on connection block loads
            for cb_partial in range(tile_cb_partial[i]):
                spice_file_lines += [
                    f"Xwire_cb_load_partial_{cb_partial+1} n_1_1 n_1_cb_partial_{cb_partial+1} wire Rw={wire_cb_load_partial_pstr}_res Cw={wire_cb_load_partial_pstr}_cap",
                    f"Xcb_load_partial_{cb_partial+1} n_1_cb_partial_{cb_partial+1} n_gate n_gate_n n_vdd n_gnd {subckt_cb_mux_partial_str}\n"
                ]
                # spice_file.write("Xwire_cb_load_partial_" + str(cb_partial+1) + " n_1_1 n_1_cb_partial_" + str(cb_partial+1) + f" wire Rw={wire_cb_load_partial_pstr}_res Cw={wire_cb_load_partial_pstr}_cap\n")
                # spice_file.write("Xcb_load_partial_" + str(cb_partial+1) + " n_1_cb_partial_" + str(cb_partial+1) + f" n_gate n_gate_n n_vdd n_gnd {subckt_cb_mux_partial_str}\n\n")
            # Write off connection block loads
            for cb_off in range(tile_cb_off[i]):
                spice_file_lines += [
                    f"Xwire_cb_load_off_{cb_off+1} n_1_1 n_1_cb_off_{cb_off+1} wire Rw={wire_cb_load_off_pstr}_res Cw={wire_cb_load_off_pstr}_cap",
                    f"Xcb_load_off_{cb_off+1} n_1_cb_off_{cb_off+1} n_gate n_gate_n n_vdd n_gnd {subckt_cb_mux_off_str}\n"
                ]
                # spice_file.write("Xwire_cb_load_off_" + str(cb_off+1) + " n_1_1 n_1_cb_off_" + str(cb_off+1) + f" wire Rw={wire_cb_load_off_pstr}_res Cw={wire_cb_load_off_pstr}_cap\n")
                # spice_file.write("Xcb_load_off_" + str(cb_off+1) + " n_1_cb_off_" + str(cb_off+1) + f" n_gate n_gate_n n_vdd n_gnd {subckt_cb_mux_off_str}\n\n")
            
            # Tile 1 is terminated by a on switch block, other tiles just connect the wire to the output
            # Tile 1's sb_mux is connected to a different power rail so that we can measure dynamic power.
            driven_sb_mux_str = f"{self.sb_mux_on.name}_on"
            if i == 0:
                spice_file_lines += [
                    f"Xwire_gen_routing_2 n_1_1 n_1_2 wire Rw='{routing_wire_load_pstr}_res/{2*wire_length}' Cw='{routing_wire_load_pstr}_cap/{2*wire_length}'",
                    f"Xsb_mux_on_out n_1_2 n_out n_gate n_gate_n n_vdd_sb_mux_on n_gnd {driven_sb_mux_str}"
                ]
                # spice_file.write(f"Xwire_gen_routing_2 n_1_1 n_1_2 wire Rw='{routing_wire_load_pstr}_res/" + str(2*wire_length) + f"' Cw='{routing_wire_load_pstr}_cap/" + str(2*wire_length) + "'\n")
                # spice_file.write(f"Xsb_mux_on_out n_1_2 n_out n_gate n_gate_n n_vdd_sb_mux_on n_gnd {sb_mux_on_str}\n")
            else:
                spice_file_lines += [ f"Xwire_gen_routing_2 n_1_1 n_out wire Rw='{routing_wire_load_pstr}_res/{2*wire_length}' Cw='{routing_wire_load_pstr}_cap/{2*wire_length}'" ]
                # spice_file.write(f"Xwire_gen_routing_2 n_1_1 n_out wire Rw='{routing_wire_load_pstr}_res/" + str(2*wire_length) + f"' Cw='{routing_wire_load_pstr}_cap/" + str(2*wire_length) + "'\n")
        
            spice_file_lines += [ ".ENDS\n\n" ]
            # spice_file.write(".ENDS\n\n\n")
        
        
        # Now write a subcircuit for the complete routing wire
        spice_file_lines += [
            "******************************************************************************************",
            f"* Routing wire load",
            "******************************************************************************************",
            f".SUBCKT {routing_wire_load_subckt_str} n_in n_out n_cb_out n_gate n_gate_n n_vdd n_gnd n_vdd_sb_mux_on n_vdd_cb_mux_on"
        ]
        
        # spice_file.write("******************************************************************************************\n")
        # spice_file.write("* Routing wire load tile " + str(i+1) + "\n")
        # spice_file.write("******************************************************************************************\n")
        # spice_file.write(f".SUBCKT {routing_wire_load_subckt_str} n_in n_out n_cb_out n_gate n_gate_n n_vdd n_gnd n_vdd_sb_mux_on n_vdd_cb_mux_on\n")
        # Iterate through tiles backwards
        in_node = "n_in"
        for tile in range(wire_length, 1, -1):
            out_node = "n_" + str(tile)
            spice_file_lines += [ f"Xrouting_wire_load_tile_{tile} {in_node} {out_node} n_hang_{tile} n_gate n_gate_n n_vdd n_gnd routing_wire_load_tile_{tile}{p_str_suffix}" ]
            # spice_file.write("Xrouting_wire_load_tile_" + str(tile) + " " + in_node + " " + out_node + " n_hang_" + str(tile) + f" n_gate n_gate_n n_vdd n_gnd routing_wire_load_tile_{tile}{p_str_suffix}\n")
            in_node = out_node
        # Write tile 1
        spice_file_lines += [
            f"Xrouting_wire_load_tile_1 {in_node} n_out n_cb_out n_gate n_gate_n n_vdd n_gnd n_vdd_sb_mux_on n_vdd_cb_mux_on routing_wire_load_tile_1{p_str_suffix}",
            ".ENDS\n\n"
        ]
        # spice_file.write("Xrouting_wire_load_tile_1 " + in_node + f" n_out n_cb_out n_gate n_gate_n n_vdd n_gnd n_vdd_sb_mux_on n_vdd_cb_mux_on routing_wire_load_tile_1{p_str_suffix}\n")
        # spice_file.write(".ENDS\n\n\n")
        
        # spice_file.close()
        
        # Write out subckt to spice file
        with open(spice_filename, 'a') as spice_file:
            spice_file.write("\n".join(spice_file_lines))

        
        # Create a list of all wires used in this subcircuit
        wire_names_list = []
        wire_names_list.append(routing_wire_load_pstr)
        wire_names_list.append(wire_sb_load_on_pstr)
        wire_names_list.append(wire_sb_load_partial_pstr)
        wire_names_list.append(wire_sb_load_off_pstr)
        wire_names_list.append(wire_cb_load_on_pstr)
        wire_names_list.append(wire_cb_load_partial_pstr)
        wire_names_list.append(wire_cb_load_off_pstr)
        
        return wire_names_list
        
    def generate(self, subcircuit_filename: str, specs: Any, sb_mux: _SwitchBlockMUX, cb_mux: _ConnectionBlockMUX):
        """ Generate the SPICE circuit for general routing wire load
            Need specs object, switch block object and connection block object """
        print("Generating routing wire load")
        # Calculate wire load based on architecture parameters
        self._compute_load(specs, sb_mux, cb_mux, self.channel_usage_assumption, self.cluster_input_usage_assumption)
        # Generate SPICE deck
        self.wire_names = self.general_routing_load_generate(subcircuit_filename, sb_mux)
    
    
    def update_wires(self, width_dict: Dict[str, float], wire_lengths: Dict[str, float], wire_layers: Dict[str, int], height: float, num_sb_stripes: int, num_cb_stripes: int):
        """ Calculate wire lengths and wire layers. """

        # Get information from the general routing wire
        wire_length = self.gen_r_wire["len"]
        wire_id = self.gen_r_wire["id"]
        wire_layer = self.gen_r_wire["metal"]

        # key_str_suffix = f"_wire_uid{wire_id}"
        # Get get keys for wires
        # TODO remove duplication figure out somewhere to define and save these keys
        wire_gen_routing_load_key = [key for key in self.wire_names if f"wire_gen_routing" in key][0]
        wire_sb_load_on_key = [key for key in self.wire_names if f"wire_sb_load_on" in key][0]
        wire_sb_load_partial_key = [key for key in self.wire_names if f"wire_sb_load_partial" in key][0]
        wire_sb_load_off_key = [key for key in self.wire_names if f"wire_sb_load_off" in key][0]

        wire_cb_load_on_key = [key for key in self.wire_names if f"wire_cb_load_on" in key][0]
        wire_cb_load_partial_key = [key for key in self.wire_names if f"wire_cb_load_partial" in key][0]
        wire_cb_load_off_key = [key for key in self.wire_names if f"wire_cb_load_off" in key][0]

        wire_keys = [
            wire_gen_routing_load_key, wire_sb_load_on_key, wire_sb_load_partial_key, 
            wire_sb_load_off_key, wire_cb_load_on_key, wire_cb_load_partial_key, 
            wire_cb_load_off_key]
        
        # check if there are any wires left over
        assert wire_keys.sort() == self.wire_names.sort(), "Wire keys do not match wire names"

        # wire_gen_routing_load_key = f"wire_gen_routing{key_str_suffix}"
        # wire_sb_load_on_key = f"wire_sb_load_on{key_str_suffix}"
        # wire_sb_load_partial_key = f"wire_sb_load_partial{key_str_suffix}"
        # wire_sb_load_off_key = f"wire_sb_load_off{key_str_suffix}"

        # wire_cb_load_on_key = f"wire_cb_load_on{key_str_suffix}"
        # wire_cb_load_partial_key = f"wire_cb_load_partial{key_str_suffix}"
        # wire_cb_load_off_key = f"wire_cb_load_off{key_str_suffix}"


        # This is the general routing wire that spans L tiles
        wire_lengths[wire_gen_routing_load_key] = wire_length*width_dict["tile"]
        # if lb_height has been initialized
        if height != 0.0:
            # If the height is greater than the width of the tile, then the wire length is the height, else width
            # This takes the larger of the two values to get wirelength, worst case?
            if height > ((width_dict["tile"]*width_dict["tile"])/height):
                wire_lengths[wire_gen_routing_load_key] = wire_length*(height)
            else:
                wire_lengths[wire_gen_routing_load_key] = wire_length*((width_dict["tile"]*width_dict["tile"])/height)

        # These are the pieces of wire that are required to connect routing wires to switch 
        # block inputs. We assume that on average, they span half a tile.
        wire_lengths[wire_sb_load_on_key] = width_dict["tile"]/2
        wire_lengths[wire_sb_load_partial_key] = width_dict["tile"]/2
        wire_lengths[wire_sb_load_off_key] = width_dict["tile"]/2 
        if height != 0.0:
            # This is saying that if we have a single stripe we have to travel the entire width of the LB to get from the routing wire to the SB input
            if num_sb_stripes == 1:
                wire_lengths[wire_sb_load_on_key] = wire_lengths[wire_gen_routing_load_key]/wire_length
                wire_lengths[wire_sb_load_partial_key] = wire_lengths[wire_gen_routing_load_key]/wire_length
                wire_lengths[wire_sb_load_off_key] = wire_lengths[wire_gen_routing_load_key]/wire_length
            # I guess this says if there are more than 1 then just estimate by traveling half of the width of the LB
            else:
                wire_lengths[wire_sb_load_on_key] = wire_lengths[wire_gen_routing_load_key]/(2*wire_length)
                wire_lengths[wire_sb_load_partial_key] = wire_lengths[wire_gen_routing_load_key]/(2*wire_length)
                wire_lengths[wire_sb_load_off_key] = wire_lengths[wire_gen_routing_load_key]/(2*wire_length)			
        
        # These are the pieces of wire that are required to connect routing wires to 
        # connection block multiplexer inputs. They span some fraction of a tile that is 
        # given my the input track-access span (track-access locality). 
        wire_lengths[wire_cb_load_on_key] = width_dict["tile"] * fpga.INPUT_TRACK_ACCESS_SPAN
        wire_lengths[wire_cb_load_partial_key] = width_dict["tile"] * fpga.INPUT_TRACK_ACCESS_SPAN
        wire_lengths[wire_cb_load_off_key] = width_dict["tile"] * fpga.INPUT_TRACK_ACCESS_SPAN
        # Doing something similar to switch blocks, if we have an initialized lb_height & single stripe then use full width of LB as base wire length being multiplied by input track access factor
        if height != 0 and num_cb_stripes == 1:
            wire_lengths[wire_cb_load_on_key] = (wire_lengths[wire_gen_routing_load_key]/wire_length) * fpga.INPUT_TRACK_ACCESS_SPAN
            wire_lengths[wire_cb_load_partial_key] = (wire_lengths[wire_gen_routing_load_key]/wire_length) * fpga.INPUT_TRACK_ACCESS_SPAN
            wire_lengths[wire_cb_load_off_key] = (wire_lengths[wire_gen_routing_load_key]/wire_length) * fpga.INPUT_TRACK_ACCESS_SPAN
        elif height != 0 :
            wire_lengths[wire_cb_load_on_key] = (wire_lengths[wire_gen_routing_load_key]/(2*wire_length)) * fpga.INPUT_TRACK_ACCESS_SPAN
            wire_lengths[wire_cb_load_partial_key] = (wire_lengths[wire_gen_routing_load_key]/(2*wire_length)) * fpga.INPUT_TRACK_ACCESS_SPAN
            wire_lengths[wire_cb_load_off_key] = (wire_lengths[wire_gen_routing_load_key]/(2*wire_length)) * fpga.INPUT_TRACK_ACCESS_SPAN
			
       # Update wire layers
        wire_layers[wire_gen_routing_load_key] = wire_layer # used to be 1 -> the first metal layer above local
        wire_layers[wire_sb_load_on_key] = fpga.LOCAL_WIRE_LAYER 
        wire_layers[wire_sb_load_partial_key] = fpga.LOCAL_WIRE_LAYER
        wire_layers[wire_sb_load_off_key] = fpga.LOCAL_WIRE_LAYER
        wire_layers[wire_cb_load_on_key] = fpga.LOCAL_WIRE_LAYER
        wire_layers[wire_cb_load_partial_key] = fpga.LOCAL_WIRE_LAYER
        wire_layers[wire_cb_load_off_key] = fpga.LOCAL_WIRE_LAYER
    
    
    def print_details(self, report_file):
        
        utils.print_and_write(report_file, "  ROUTING WIRE LOAD DETAILS:")
        utils.print_and_write(report_file, "  Number of SB inputs connected to routing wire = " + str(self.sb_load_on + self.sb_load_partial + self.sb_load_off))
        utils.print_and_write(report_file, "  Wire: SB (on = " + str(self.sb_load_on) + ", partial = " + str(self.sb_load_partial) + ", off = " + str(self.sb_load_off) + ")")
        utils.print_and_write(report_file, "  Number of CB inputs connected to routing wire = " + str(self.cb_load_on + self.cb_load_partial + self.cb_load_off))
        utils.print_and_write(report_file, "  Wire: CB (on = " + str(self.cb_load_on) + ", partial = " + str(self.cb_load_partial) + ", off = " + str(self.cb_load_off) + ")")

        for i in range(self.gen_r_wire["len"]):
            utils.print_and_write(report_file, "  Tile " + str(i+1) + ": SB (on = " + str(self.tile_sb_on[i]) + ", partial = " + str(self.tile_sb_partial[i]) + 
            ", off = " + str(self.tile_sb_off[i]) + "); CB (on = " + str(self.tile_cb_on[i]) + ", partial = " + str(self.tile_cb_partial[i]) + ", off = " + str(self.tile_cb_off[i]) + ")")
        utils.print_and_write(report_file, "")
        
       
    def _compute_load(self, specs: Any, sb_mux: _SwitchBlockMUX, cb_mux: _ConnectionBlockMUX, channel_usage: float, cluster_input_usage: float):
        """ Computes the load on a routing wire """
        
        # Local variables
        # W = self.gen_r_wire["num_tracks"]
        W = specs.W
        L = self.gen_r_wire["len"]
        I = specs.I
        Fs = specs.Fs

        # sb_mux_size = sb_mux.implemented_size
        # cb_mux_size = cb_mux.implemented_size
        # sb_level1_size = sb_mux.level1_size
        # sb_level2_size = sb_mux.level2_size
        # cb_level1_size = cb_mux.level1_size
        # cb_level2_size = cb_mux.level2_size
        
        # List of muxes which can be use this wire as an input
        sb_muxes = [sb_mux_info["sb_mux"] for sb_mux_info in self.tile_info["sb_muxes_info"] if sb_mux_info["sb_mux"].src_r_wire["id"] == self.gen_r_wire["id"]]
        # Find the most frequently used SB mux
        most_freq_sb_mux_idx = max(range(len(sb_muxes)), key=lambda i: sb_muxes[i].num_per_tile)
        # For each sb_mux and its respective Fs
        for i, sb_mux_info in enumerate(self.tile_info["sb_muxes_info"]):
            
            Fs = specs.Fs_mtx[sb_mux_info["id"]]["Fs"]
            sb_mux = sb_mux_info["sb_mux"]
            # The wire in this load is the source wire of all attached SBS
            L = sb_mux.src_r_wire["len"]
            assert L == self.gen_r_wire["len"], f"The length of the switch block mux src wire does not match the length of the routing wire {L} != {self.gen_r_wire['len']}"
            
            # init cb / sb mux size variables
            # sb_mux_size = sb_mux.implemented_size
            cb_mux_size = cb_mux.implemented_size
            sb_level2_size = sb_mux.level2_size
            cb_level2_size = cb_mux.level2_size
            
            # # This is the ON sb mux driven by this load
            # if i == self.driven_sb_mux_idx:
            #     self.tiles_info["sb_muxes_info"][i]["num_on"] = 1
            # else:
            #     self.tiles_info["sb_muxes_info"][i]["num_on"] = 0
            
            # num sb partial loads which are loading the gen routing wire for single tile (will be assigned at the end for worst case)
            # Why is this not for every tile? If we assume channels to be turned on at X % across device there would be way more partial on muxes
            # TODO change this from just choosing a random SB idx to a weighted round robin
            if i == most_freq_sb_mux_idx:
                sb_load_partial = int(math.ceil((round(float(sb_level2_size - 1.0) * channel_usage))))
            else:
                sb_load_partial = int(round(float(sb_level2_size - 1.0) * channel_usage))
            
            sb_load_per_intermediate_tile = (Fs - 1)
            # This rounding could result in some accuracy loss due to fragmentation, but it is a decent estimate
            sb_load_off = int(math.ceil((sb_load_per_intermediate_tile * L - sb_load_partial) * sb_mux_info["freq_ratio"]))
            
            # The driven_sb_mux index indicates which SB mux is at the end of the gen wire load
            # Now we don't account for the one thats driven @ end of load
            sb_mux_info["on_budget"] = 0 #1 if i == self.driven_sb_mux_idx else 0
            sb_mux_info["partial_budget"] = sb_load_partial
            sb_mux_info["off_budget"] = sb_load_off

        # TODO add weighted round robin to assign most frequent SB if the numbers from prev calculations are off
        # Don't include the ON as its accounted for in below calculation
        tiles_off_path_sb_budget = sum([sb_mux_info["on_budget"] + sb_mux_info["partial_budget"] + sb_mux_info["off_budget"] for sb_mux_info in self.tile_info["sb_muxes_info"]])
        # Now we are just going to do some adjustment to make sure that each tile has at least (Fs - 1) SB loads
        if tiles_off_path_sb_budget < sb_load_per_intermediate_tile * L:
            remaining_sb_assignments = sb_load_per_intermediate_tile * L - tiles_off_path_sb_budget
            while remaining_sb_assignments != 0:
                # cur_total_budget = sum([sb_mux_info["on_budget"] + sb_mux_info["partial_budget"] + sb_mux_info["off_budget"] for sb_mux_info in self.tile_info["sb_muxes_info"]])
                # Going from 
                for i, sb_mux_info in enumerate(self.tile_info["sb_muxes_info"]):
                    tile_cur_total_budget = sb_mux_info["on_budget"] + sb_mux_info["partial_budget"] + sb_mux_info["off_budget"]
                    # Adjustment of a particular SB type would be how different is from the desired freq_ratio, if > 0 too many muxes assigned, if < 0 too few
                    adjustment = sb_mux_info["freq_ratio"] - (tile_cur_total_budget / sb_load_per_intermediate_tile)
                    if adjustment < 0:
                        # If we have too few, we can add one to the off budget
                        sb_mux_info["off_budget"] += 1
                        remaining_sb_assignments -= 1
                        if remaining_sb_assignments == 0:
                            break
                tiles_off_path_sb_budget = sum([sb_mux_info["on_budget"] + sb_mux_info["partial_budget"] + sb_mux_info["off_budget"] for sb_mux_info in self.tile_info["sb_muxes_info"]])
            assert tiles_off_path_sb_budget == sb_load_per_intermediate_tile * L, f"Tile {i} has {tiles_off_path_sb_budget} SB loads, expected {sb_load_per_intermediate_tile * L}"

            # If we have less than (Fs - 1) loads, we need to add some off loads
            # TODO change the mux type to be weighted round robin
            # self.tile_info["sb_muxes_info"][0]["off_budget"] += sb_load_per_intermediate_tile * L - tile_off_path_sb_budget

        # Calculate switch block load per tile
        # Each tile has Fs-1 switch blocks hanging off of it exept the last one which has 3 (because the wire is ending)
        # sb_load_per_intermediate_tile = (Fs - 1)
        # Calculate number of on/partial/off
        # We assume that each routing wire is only driving one more routing wire (at the end)
        # self.sb_load_on = 1
        # Each used routing multiplexer comes with (sb_level2_size - 1) partially on paths. 
        # If all wires were used, we'd have (sb_level2_size - 1) partially on paths per wire, TODO: Is this accurate? See ble output load
        # but since we are just using a fraction of the wires, each wire has (sb_level2_size - 1)*channel_usage partially on paths connected to it.
        
        # Stratix had around 50% channel usage, 60-70% is pushing it for most FPGAs
        # Channel usage is correction factor because we dont turn all muxes on, if we use half of our routing wires we put 0.5 for channel usage
        # self.sb_load_partial = int(round(float(sb_level2_size - 1.0) * channel_usage))
        # The number of off sb_mux is (total - partial)
        # Everything that is not partially on will be off
        # The one ON swtich was already considered so we dont include it in the load
        # self.sb_load_off = sb_load_per_intermediate_tile * L - self.sb_load_partial
        

        # We assume CB muxes always take in the minimal wire length type
        # min_len_wire = fpga.min_len_wire
        # cb_in_L = min_len_wire["len"]

        # Calculate connection block load per tile
        # We assume that cluster inputs are divided evenly between horizontal and vertical routing channels
        # We can get the total number of CB inputs connected to the channel segment by multiplying cluster inputs by cb_mux_size, then divide by W to get cb_inputs/wire
        cb_load_per_tile = int(round((I / 2 * cb_mux_size) // W))
        # Now we got to find out how many are on, how many are partially on and how many are off
        # For each tile, we have half of the cluster inputs connecting to a routing channel and only a fraction of these inputs are actually used
        # It is logical to assume that used cluster inputs will be connected to used routing wires, so we have I/2*input_usage inputs per tile,
        # we have L tiles so, I/2*input_usage*L fully on cluster inputs connected to W*channel_usage routing wires
        # If we look at the whole wire, we are selecting I/2*input_usage*L signals from W*channel_usage wires
        # Even though all the wires are not of minimum length, we use the same W for all wires 
        #       because it would be innacurate to just use the portion of channel of minimum length (we are doing an estimate)
        cb_load_on_probability = float((I / 2.0 * cluster_input_usage * L)) / (W * channel_usage)
        self.cb_load_on = int(round(cb_load_on_probability))
        # If < 1, we round up to one because at least one wire will have a fully on path connected to it and we model for that case.
        if self.cb_load_on == 0:
            self.cb_load_on = 1 
        # Each fully turned on cb_mux comes with (cb_level2_size - 1) partially on paths
        # The number of partially on paths per tile is I/2*input_usage * (cb_level2_size - 1) 
        # Number of partially on paths per wire is (I/2*input_usage * (cb_level2_size - 1) * L) / W
        cb_load_partial_probability = (I / 2 * cluster_input_usage * (cb_level2_size - 1) * L) / W
        self.cb_load_partial = int(round(cb_load_partial_probability))
        # If < 1, we round up to one because at least one wire will have a partially on path connected to it and we model for that case.
        if self.cb_load_partial == 0:
            self.cb_load_partial = 1 
        # Number of off paths is just number connected to routing wire - on - partial
        self.cb_load_off = cb_load_per_tile * L - self.cb_load_partial - self.cb_load_on
     
        # Now we want to figure out how to distribute this among the tiles. We have L tiles.
        # tile_sb_on_budget = self.sb_load_on
        # tile_sb_partial_budget = self.sb_load_partial
        # tile_sb_off_budget = self.sb_load_off
        # tile_sb_total_budget = tile_sb_on_budget + tile_sb_partial_budget + tile_sb_off_budget
        
        # tile_sb_total_budget = {}
        # tile_sb_max = {}

        # tile_sb_on_budget = {}
        # tile_sb_partial_budget = {}
        # tile_sb_off_budget = {}
        # for sb_mux_info in self.tile_info["sb_muxes_info"]:
        #     tile_sb_on_budget[sb_mux_info["id"]] = sb_mux_info["on_budget"]
        #     tile_sb_partial_budget[sb_mux_info["id"]] = sb_mux_info["partial_budget"]
        #     tile_sb_off_budget[sb_mux_info["id"]] = sb_mux_info["off_budget"]

        # Assert that the number of ON SBs is only 1
        # assert sum([sb_mux_info["on_budget"] for sb_mux_info in self.tile_info["sb_muxes_info"]]) == 1, "There should only be a single ON SB Mux in the path"

        tile_sb_total_budget = sum([sb_mux_info["on_budget"] + sb_mux_info["partial_budget"] + sb_mux_info["off_budget"] for sb_mux_info in self.tile_info["sb_muxes_info"]])
        tile_sb_max = math.ceil(float(tile_sb_total_budget / L))


        tile_sb_on = []
        tile_sb_partial = []
        tile_sb_off = []
        tile_sb_total = []

        # How this works: We have a certain amount of switch block mux connections to give to the wire,
        # we start at the furthest tile from the drive point and we allocate one mux input per tile iteratively until we run out of mux inputs.
        # The result of this is that on and partial mux inputs will be spread evenly along the wire with a bias towards putting 
        # them farthest away from the driver first (simulating a worst case).
        # while sum([tile_sb_total_budget[k] for k in tile_sb_total_budget.keys()]) != 0:
        while tile_sb_total_budget != 0:
            # For each tile distribute load
            for i in range(L):
                sb_assignment = {
                    sb_mux_info["id"]: 0 for sb_mux_info in self.tile_info["sb_muxes_info"]
                }
                # Add to lists
                if len(tile_sb_on) < (i+1):
                    tile_sb_on.append(copy.deepcopy(sb_assignment))
                if len(tile_sb_partial) < (i+1):
                    tile_sb_partial.append(copy.deepcopy(sb_assignment))
                if len(tile_sb_off) < (i+1):
                    tile_sb_off.append(copy.deepcopy(sb_assignment))
                if len(tile_sb_total) < (i+1):
                    tile_sb_total.append(0)
                # Distribute loads
                for sb_mux_info in self.tile_info["sb_muxes_info"]:
                    if tile_sb_total[i] != tile_sb_max:
                        if sb_mux_info["on_budget"] != 0:
                            tile_sb_on[i][sb_mux_info["id"]] += 1
                            sb_mux_info["on_budget"] -= 1
                            tile_sb_total[i] += 1
                            tile_sb_total_budget -= 1
                for sb_mux_info in self.tile_info["sb_muxes_info"]:
                    if tile_sb_total[i] != tile_sb_max:
                        if sb_mux_info["partial_budget"] != 0:
                            tile_sb_partial[i][sb_mux_info["id"]] += 1
                            sb_mux_info["partial_budget"] -= 1
                            tile_sb_total[i] += 1
                            tile_sb_total_budget -= 1
                for sb_mux_info in self.tile_info["sb_muxes_info"]:
                    if tile_sb_total[i] != tile_sb_max:
                        if sb_mux_info["off_budget"] != 0:
                            tile_sb_off[i][sb_mux_info["id"]] += 1
                            sb_mux_info["off_budget"] -= 1
                            tile_sb_total[i] += 1
                            tile_sb_total_budget -= 1
                
                # Checking if the total budget of sbs for this tile have been exhausted
                # if tile_sb_total[i] != tile_sb_max:
                #     # For each, check if on / partial / off budgets have been exhausted, if not add one of the mux types
                #     if tile_sb_on_budget != 0:
                #         tile_sb_on[i] += 1
                #         tile_sb_on_budget -= 1
                #         tile_sb_total[i] += 1
                #         tile_sb_total_budget -= 1
                # if tile_sb_total[i] != tile_sb_max:
                #     if tile_sb_partial_budget != 0:
                #         tile_sb_partial[i] += 1
                #         tile_sb_partial_budget -= 1
                #         tile_sb_total[i] += 1
                #         tile_sb_total_budget -= 1
                # if tile_sb_total[i] != tile_sb_max:
                #     if tile_sb_off_budget != 0:
                #         tile_sb_off[i] += 1
                #         tile_sb_off_budget -= 1
                #         tile_sb_total[i] += 1
                #         tile_sb_total_budget -= 1

                # if tile_sb_on_budget != 0:
                #     if tile_sb_total[i] != tile_sb_max:
                #         tile_sb_on[i] += 1
                #         tile_sb_on_budget -= 1
                #         tile_sb_total[i] += 1
                #         tile_sb_total_budget -= 1
                # if tile_sb_partial_budget != 0:
                #     if tile_sb_total[i] != tile_sb_max:
                #         tile_sb_partial[i] += 1
                #         tile_sb_partial_budget -= 1
                #         tile_sb_total[i] += 1
                #         tile_sb_total_budget -= 1
                # if tile_sb_off_budget != 0:
                #     if tile_sb_total[i] != tile_sb_max:
                #         tile_sb_off[i] += 1
                #         tile_sb_off_budget -= 1
                #         tile_sb_total[i] += 1
                #         tile_sb_total_budget -= 1
         
        # Assign these per-tile counts to the object
        self.tile_sb_on = tile_sb_on
        self.tile_sb_partial = tile_sb_partial
        self.tile_sb_off = tile_sb_off
         
        tile_cb_on_budget = self.cb_load_on
        tile_cb_partial_budget = self.cb_load_partial
        tile_cb_off_budget = self.cb_load_off
        tile_cb_total_budget = tile_cb_on_budget + tile_cb_partial_budget + tile_cb_off_budget
        tile_cb_max = math.ceil(float(tile_cb_total_budget) / L)
        tile_cb_on = []
        tile_cb_partial = []
        tile_cb_off = []
        tile_cb_total = []

        while tile_cb_total_budget != 0:
            # For each tile distribute load
            for i in range(L):
                # Add to lists
                if len(tile_cb_on) < (i+1):
                    tile_cb_on.append(0)
                if len(tile_cb_partial) < (i+1):
                    tile_cb_partial.append(0)
                if len(tile_cb_off) < (i+1):
                    tile_cb_off.append(0)
                if len(tile_cb_total) < (i+1):
                    tile_cb_total.append(0)
                # Distribute loads
                if tile_cb_on_budget != 0:
                    if tile_cb_total[i] != tile_cb_max:
                        tile_cb_on[i] = tile_cb_on[i] + 1
                        tile_cb_on_budget = tile_cb_on_budget - 1
                        tile_cb_total[i] = tile_cb_total[i] + 1
                        tile_cb_total_budget = tile_cb_total_budget - 1
                if tile_cb_partial_budget != 0:
                    if tile_cb_total[i] != tile_cb_max:
                        tile_cb_partial[i] = tile_cb_partial[i] + 1
                        tile_cb_partial_budget = tile_cb_partial_budget - 1
                        tile_cb_total[i] = tile_cb_total[i] + 1
                        tile_cb_total_budget = tile_cb_total_budget - 1
                if tile_cb_off_budget != 0:
                    if tile_cb_total[i] != tile_cb_max:
                        tile_cb_off[i] = tile_cb_off[i] + 1
                        tile_cb_off_budget = tile_cb_off_budget - 1
                        tile_cb_total[i] = tile_cb_total[i] + 1
                        tile_cb_total_budget = tile_cb_total_budget - 1
        
        # Assign these per-tile counts to the object
        self.tile_cb_on = tile_cb_on
        self.tile_cb_partial = tile_cb_partial
        self.tile_cb_off = tile_cb_off