
import os, sys
import time
import xmltodict 
import pprint
import dataclasses
from typing import Dict, Any, List, Tuple
from collections import defaultdict
import statistics as stats
import csv
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import scipy.stats as stats
import copy

from timeit import default_timer as timer 
import argparse

import multiprocessing as mp

import src.common.utils as rg_utils


@dataclasses.dataclass
class Switch:
    name: str
    id: int
    type: str
    timing: dict

@dataclasses.dataclass
class Segment:
    name: str
    id: int
    length: int
    timing: dict

@dataclasses.dataclass
class Node:
    id: int
    direction: str
    type: str
    capacity: int
    loc: dict
    timing: dict
    segment: dict

@dataclasses.dataclass
class Edge:
    sink_node: int
    src_node: int
    switch_id: int


def parse_xml_to_dict(xml_file: str, tags: List[str]):
    from lxml import etree
    result: Dict[str, Dict[str, Any]] = defaultdict(dict)

    # Create an iterator for streaming parsing
    context = etree.iterparse(xml_file, events=('start', 'end'))

    # Iterate over the XML elements
    for event, elem in context:
        if event == 'end' and elem.tag in tags:
            # Convert the element to a dictionary
            element_dict = {}
            element_dict.update(elem.attrib)  # Add attributes
            # element_dict['text'] = elem.text  # Add text content
            result[elem.tag] = element_dict
            elem.clear()  # Clear the element from memory

    return result


def typecast_input_to_dataclass(input_value: dict, dataclass_type: Any) -> Any:
    """
    Typecasts input_value to the corresponding dataclass_type.
    """
    fields = dataclasses.fields(dataclass_type)
    output = {}

    for field in fields:
        field_name = field.name
        field_type = field.type
        # print(f"Field Name: {field_name}, Field Type: {field_type}, Input Value: {input_value.get(field_name)}")

        if input_value.get(field_name) is None:
            output[field_name] = None
            continue
        # Perform typecasting based on field type
        elif isinstance(input_value.get(field_name), field_type):
            output[field_name] = input_value.get(field_name)
        else:
            try:
                output[field_name] = field_type(input_value.get(field_name))
            except (ValueError, TypeError):
                output[field_name] = None  # If typecasting fails, set to None
    
    return dataclass_type(**output)




def rec_clean_dict_keys(input_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively cleans up dictionary keys by removing the '@' character
    """
    output_dict = {}
    for k, v in input_dict.items():
        if isinstance(v, dict):
            output_dict[k.replace("@","")] = rec_clean_dict_keys(v)
        else:
            output_dict[k.replace("@","")] = v
    return output_dict

# VIRTUAL_PIN_ID = 0
# CB_IPIN_SW_ID = 1
# L4_SW_ID = 2
# L16_SW_ID = 3

def parse_cli_args(argv: List[str] = []) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parses VPR rr_graph.xml file and outputs information on the routing architecture")
    parser.add_argument("-rrg","--rr_xml_fpath", type=str, help="Path to the input rr_graph.xml file", required=True)
    parser.add_argument("-o", "--out_dpath", type=str, help="Path to the output directory", default=os.getcwd())
    parser.add_argument("-p", "--generate_plots", action='store_true', help="Generate RRG Plots", default = True)

    in_args = argv if argv else sys.argv[1:]

    return parser.parse_args(args = in_args)

def main(argv: List[str] = [], kwargs: Dict[str, str] = {}) -> Dict[str, Dict[str, Any]]:
    # input_rr_xml_fpath = "sandbox/rr_graph_ep4sgx110.xml"
    args = parse_cli_args(argv)
    # Get vals from argparse
    input_rr_xml_fpath: str = args.rr_xml_fpath
    out_dpath: str = args.out_dpath
    gen_plots: bool = args.generate_plots

    # Parse the RRG from XML

    rrg_str = input_rr_xml_fpath.split("/")[-1].split(".")[0]
    with open(input_rr_xml_fpath, "r") as f:
        input_rr_xml_text = f.read()

    global_start = timer()
    timer_start = timer()
    print( f"Starting to parse {input_rr_xml_fpath} with xmltodict")
    rr_dict = xmltodict.parse(input_rr_xml_text)
    print( f"Finished parsing {input_rr_xml_fpath} with xmltodict in {timer() - timer_start} seconds")
    
    # LXML parsing information
    # print( f"Starting to parse {input_rr_xml_fpath} with lxml")
    # timer_start = timer()
    # out_tags = ["switches", "segments", "rr_nodes", "rr_edges"]
    # rr_dict = parse_xml_to_dict(input_rr_xml_fpath, out_tags)
    # print( f"Finished parsing {input_rr_xml_fpath} with lxml in {timer() - timer_start} seconds")
    
    switches: Dict[int, Switch] = {}
    segments: Dict[int, Segment] = {}
    nodes: Dict[int, Node] = {}
    edges: List[Edge] = []
    # Required Information
    # For each type of SB mux (type of wire being driven i suppose)
    #   Number of these muxes per SB per direction
    #   size
    #   How many inputs from each wire type / LB output
    # For each segment type
    #   How many Muxes (and which type) are loading the segment -> mux fanout w/specifics



    # Number of edges w common src should be equal to number of muxes attached to the src node, ie mux load on a wire (fanout) 
    common_src_edges: Dict[int, List[Edge]] = defaultdict(list)
    # Number of edges w common sink should all be in the same SB and go into the same Mux (ie mux fanin)
    common_sink_edges: Dict[int, List[Edge]] = defaultdict(list)
    # Common edges with also common sw_ids to determine fanouts of particular wires, indexed with src_node 
    # common_src_sw_id_edges: Dict[int, 

    for k, v in rr_dict["rr_graph"].items():
        # Switch Type info
        if k == "switches":
            for switch in v["switch"]:
                conv_switch = rec_clean_dict_keys(switch)
                switches[int(conv_switch['id'])] = typecast_input_to_dataclass(conv_switch, Switch)
        # Segment Type info
        elif k == "segments":
            for segment in v["segment"]:
                conv_segment = rec_clean_dict_keys(segment)
                segments[int(conv_segment['id'])] = typecast_input_to_dataclass(conv_segment, Segment)

        elif k == "rr_nodes":
            for node in v["node"]:
                conv_node = rec_clean_dict_keys(node)
                # hash nodes by node id
                # out_node: Node = typecast_input_to_dataclass(conv_node, Node)
                # print(out_node.segment)
                # if out_node.segment is not None:
                #     out_node.segment.segment_id = int(out_node.segment.get("segment_id")) 
                nodes[int(conv_node['id'])] = typecast_input_to_dataclass(conv_node, Node)

            
        # Check if this describes a wire inst
        elif k == "rr_edges":
            for edge in v["edge"]:
                conv_edge = rec_clean_dict_keys(edge)
                edge_obj: Edge = typecast_input_to_dataclass(conv_edge, Edge)
                edges.append(
                    edge_obj
                )
                # Hash with node value
                # Add edge to common_src_edges
                common_src_edges[edge_obj.src_node].append(
                    typecast_input_to_dataclass(conv_edge, Edge)
                )
                # Add edge to common_sink_edges
                common_sink_edges[edge_obj.sink_node].append(
                    typecast_input_to_dataclass(conv_edge, Edge)
                )

    # Verifying that we read in the correct number of switches, segments, nodes, and edges

    # print("Switches")
    # print(switches[0:10], switches[-10:] )
    # print("Segments")
    # print(segments[0:10], segments[-10:])
    # print("Nodes")
    # print(nodes[0:10], nodes[-10:])
    # print("Edges")
    # print(edges[0:10], edges[-10:])

    # Device bounds
    # xmax = max([node.loc['xhigh'] for node in nodes.values()])
    # ymax = max([node.loc['yhigh'] for node in nodes.values()])
    # xmin = min([node.loc['xlow'] for node in nodes.values()])
    # ymin = min([node.loc['ylow'] for node in nodes.values()])


    # node_coord_keys = ['xlow', 'xhigh', 'ylow', 'yhigh']
    # # Remove edges of the device
    # # Iterating through the src edges but if we find an edge with src or sink on boundary of device we remove it from both lists
    # for k in list(common_src_edges.keys()):
    #     edges: List[Edge] = common_src_edges[k]
    #     node: Node = nodes[edges[0].src_node]
    #     if node.type == "CHANX" or node.type == "CHANY":
    #         # Check if its on the boundary
    #         if any([node.loc[node_coord_key] == xmin or node.loc[node_coord_key] == xmax or node.loc[node_coord_key] == ymin or node.loc[node_coord_key] == ymax for node_coord_key in node_coord_keys]):
    #             # Prune any node in edge list which has a coordinate on the boundary
    #             del common_src_edges[k]
    #             continue
    #     # # Check if wire destination or source is on boundary
    #     # wire_len = segments[node.segment['segment_id']].length
    # for k in list(common_sink_edges.keys()):
    #     edges: List[Edge] = common_sink_edges[k]
    #     node: Node = nodes[edges[0].sink_node]
    #     if node.type == "CHANX" or node.type == "CHANY":
    #         # Check if its on the boundary
    #         if any([node.loc[node_coord_key] == xmin or node.loc[node_coord_key] == xmax or node.loc[node_coord_key] == ymin or node.loc[node_coord_key] == ymax for node_coord_key in node_coord_keys]):
    #             # Prune any node in edge list which has a coordinate on the boundary
    #             del common_sink_edges[k]
    #             continue

    # remove any common_src which doesnt have a key in common_sinks
    # for k in list(common_src_edges.keys()):
    #     if k not in common_sink_edges.keys():
    #         del common_src_edges[k]
    # # remove any common_sink which doesnt have a key in common_src
    # for k in list(common_sink_edges.keys()):
    #     if k not in common_src_edges.keys():
    #         del common_sink_edges[k]



    # Create a dict of switch 
    switch_lookups = {
        sw_id: (switch.name.upper() if switch.name != "__vpr_delayless_switch__" else "LB_OPIN") for sw_id, switch in switches.items()      
    }

    # Create lookups to find a switch ID from a segment ID
    # To do this I think we have to iterate over all nodes and find thier corresponding segment ids (if they have them)
    # Then we can iterate over all sink edges with that segment id and find thier switch id, then we can make a dict of segment id to switch id
    seg_2_sw_ids_lookup = {
        seg_id: set([edge.switch_id for edge in common_sink_edges[node_id] if edge.switch_id != 0])
            for node_id, node in nodes.items() if node.segment
                for seg_id in set(segment.id for segment in segments.values()) if int(node.segment.get("segment_id")) == seg_id
    }
    # now get int -> int mapping
    seg_2_sw_ids_lookup = {
        seg_id: sw_ids.pop() for seg_id, sw_ids in seg_2_sw_ids_lookup.items()
    }

    # Create a list of nodes which are ignored PRE pruning because of thier strangeness
    error_nodes: Dict[int, Node] = {}
    error_no_fanin_edges: Dict[int, Edge] = {}
    error_no_fanout_edges: Dict[int, Edge] = {}


    # Routing wire driving switches
    # gen_r_wire_sw_ids = set([node. for node in nodes.values() if node.type in ["CHANX", "CHANY"] and node.segment]
    # gen_r_drv_switches = {
    #     sw_id: switch for sw_id, switch in switches.items() if switch.name != "__vpr_delayless_switch__" and switch.type == "mux"
    # }

    # Stdout log formatting
    stdout_col_width = 30
    long_stdout_col_width = 40

    # Sort the common sources by also having the same switch id
    mux_infos: Dict[str, dict] = defaultdict(dict)
    freq_info: Dict[str, dict] = defaultdict(dict)
    for k, v in common_sink_edges.items():
        # If one of its sources has switch id of 2 or 3 then its a SB mux driven edge
        edges: List[Edge] = v
        node_id: int = k 

        # Some nodes have no fanin or fanout, because of them being difficult to deal with we're gonna skip them for now TODO print these to another file to debug
        if not edges:
            continue

        # Make sure that all edges are driving a node with type L4 or L16 
        # all([edge.switch_id in [L4_SW_ID, L16_SW_ID] for edge in edges])

        # Make sure that all edges are driving a node with a type in our segment types (representing general programmable routing)
        # AND Make sure that there exists a common src for the same sink -> Basically is this a non terminal SINK node
        # wire_segment_id: int = int(nodes[edges[0].sink_node].segment.get("segment_id")) if nodes[edges[0].sink_node].segment else None
        wire_segment_id: int = int(nodes[node_id].segment.get("segment_id")) if nodes[node_id].segment else None
        if (wire_segment_id in list(segments.keys()) ) and node_id in common_src_edges.keys():

            # Make sure that all edges have the same switch id
            # In unidirectional routing, all edges which have the same sink should have the same Switch id in most cases
            # There could be edge cases for connection block ipins where this may be wrong
            assert all([edges[0].switch_id == edge.switch_id for edge in edges]), f"Switch ID Mismatch: {edges}"

            # Init to empty dict
            mux_infos[node_id]['fanin'] = {}
            # Once its been initialized put fanin for each switch id and total
            for edge in edges:
                # Find the the switch type of each src going into our common sink
                # print(f"Edge: {edge}")
                # print(f"Common Sink Edges: {common_sink_edges[edge.src_node]}")
                
                # This condition is happening with a fanin 1 wire, seems weird but is edge case so we will skip for now 
                if not common_sink_edges.get(edge.src_node):
                    # If we can't find the src node driving the edge, we can fall back on assuming that there is a single driver per wire type
                    src_sw_id = seg_2_sw_ids_lookup[int(nodes[edge.sink_node].segment.get("segment_id"))]
                else:
                    src_sw_id = common_sink_edges[edge.src_node][0].switch_id
                    # Make sure that all nodes in the common_sink_edges[edge.src_node] have the same switch id, again meaning they all are inputs to the same SB mux 
                    assert all(common_sink_edges[edge.src_node][0].switch_id == sw_edge.switch_id for sw_edge in common_sink_edges[edge.src_node]), f"Switch ID Mismatch: {common_sink_edges[edge.src_node]}"
                
                # Just making sure above is correct
                # assert all(common_sink_edges[edge.src_node][0].switch_id == edge.switch_id for edge in common_sink_edges[edge.src_node]), f"Switch ID Mismatch: {common_sink_edges[edge.src_node]}" 
                
                # Initialize with 0 if not already in dict, if it is we increment by 1
                mux_infos[node_id]['fanin'][src_sw_id] = mux_infos[node_id]['fanin'].get(src_sw_id, 0) + 1

            # Set total fanin from all edges
            mux_infos[node_id]['fanin']['total'] = len(edges)
            # Set the wire type for this node
            mux_infos[node_id]['wire_type'] = segments[wire_segment_id].name
            
            # Assert that the sum of all fanin values is equal to the total fanin
            assert len(edges) == sum(mux_infos[node_id]['fanin'][sw_id] for sw_id in mux_infos[node_id]['fanin'] if sw_id != 'total'), f"Fanin Mismatch: \nEdges ({len(edges)}):{edges}\nmux_infos: {mux_infos[node_id]['fanin']}"
        else:
            # Must be a node with no fanin
            # Assert that this is Starting SOURCE node is of type SOURCE ie Not an IPIN / OPIN / CHANX / CHANY
            # assert nodes[edges[0].sink_node].type in ["SOURCE", "OPIN"], f"Node: {nodes[edges[0].sink_node]} Edge: {edges[0]} is not a SOURCE / OPIN node"
            
            # Assert that this type is NOT in our segment types
            try:
                assert wire_segment_id not in list(segments.keys()), f"Node: {nodes[node_id]} Edge: {edges[0]} is in Segment types with NO Fanout"
            except AssertionError:
                error_nodes[node_id] = (nodes[node_id])
                error_no_fanout_edges[node_id] = edges\
                # print(f"Node: {nodes[edges[0].sink_node]} Edge: {edges[0]} is in Segment types and has NO fanout")


    # switch_lookups = {
    #     0: "LB_OPIN_WIRE",
    #     1: "CB_IPIN_WIRE",
    #     2: "L4_WIRE",
    #     3: "L16_WIRE"
    # }

    for k, v in common_src_edges.items():
        edges: List[Edge] = v
        node_id: int = k
        # any([edge.switch_id in [L4_SW_ID, L16_SW_ID, ] for edge in edges])

        # print(f"Node: {nodes[node_id]}")
        # print(f"Edges: {edges}")

        # Make sure that all src edges are a node with a type in our segment types (representing general programmable routing)
        # wire_segment_id: int = int(nodes[edges[0].src_node].segment.get("segment_id")) if nodes[edges[0].src_node].segment else None
        
        wire_segment_id: int = int(nodes[node_id].segment.get("segment_id")) if nodes[node_id].segment else None
        # Make sure that our source nodes correspond to a SB mux (filtered in fanins)
        if (wire_segment_id in list(segments.keys()) ) and node_id in common_sink_edges.keys():
            # Init to empty dict
            mux_infos[node_id]['fanout'] = {}
            # Once its been initialized put fanin for each switch id and total
            for edge in edges:
                # Initialize with 0 if not already in dict, if it is we increment by 1
                mux_infos[node_id]['fanout'][edge.switch_id] = mux_infos[node_id]['fanout'].get(edge.switch_id, 0) + 1
            # Set total fanout from all edges
            mux_infos[node_id]['fanout']['total'] = len(v)

            # Assert that the sum of all fanout values is equal to the total fanout
            assert len(edges) == sum(mux_infos[node_id]['fanout'][sw_id] for sw_id in mux_infos[node_id]['fanout'] if sw_id != 'total'), f"Fanout Mismatch: {edges}"
            
            # If we can't find the src node in common sinks then it has no fanin and we use our segment 2 switch lookup to find the right value
            if not common_sink_edges.get(node_id):
                mux_infos[node_id]['drv_mux_type'] = switch_lookups[seg_2_sw_ids_lookup[wire_segment_id]]
            else:
                # Make sure that these common src edges have the same sw id, and the same wire type if not there's a bug in vpr
                mux_infos[node_id]['drv_mux_type'] = switch_lookups[common_sink_edges[node_id][0].switch_id]
            
            # assert all(edge.switch_id == edges[0].switch_id for edge in edges)
        else: 
            # Must be a node edge with no fanout
            # Assert that this Terminal SINK node is of type SINK ie Not an IPIN / OPIN / CHANX / CHANY
            # assert nodes[edges[0].sink_node].type == "SINK", f"Node: {nodes[edges[0].sink_node]} Edge: {edges[0]} is not a SINK node"

            # This assertion is failing with some nets not sure why
            try:
                 # Assert that this type is NOT in our segment types
                assert wire_segment_id not in list(segments.keys()), f"Node: {nodes[node_id]} Edge: {edges[0]} is in Segment types"
            except AssertionError:
                error_nodes[node_id] = (nodes[node_id])
                error_no_fanin_edges[node_id] = edges
                # print(f"Node: {nodes[edges[0].src_node]} Edge: {edges[0]} is in Segment types and has NO fanin")


    # Uncommented below as filtering switch_ids should take care of this
    # Remove any nets which don't have a fanout or fanin. These are SINK or SOURCE nodes which used for Logical Equivalence.
    for k in sorted(mux_infos):
        fanout = mux_infos[k].get('fanout')
        fanin = mux_infos[k].get('fanin')
        # Condition which probably means this is an I/O or something thats not represented as either a SRC or SINK 
        if not fanout or not fanin:
            del mux_infos[k]


        
        # If Mux is Driving general programmable routing
        # if nodes[node_id].segment:
        #     # Get the segment id for the node
        #     # seg_id = int(nodes[node_id].segment.get("segment_id"))
        #     # # Get the switch id for the node
        #     # sw_id = seg_2_sw_ids_lookup[seg_id]
        #     # sw_type = switch_lookups[sw_id]
        #     # Sanity Assertion
        #     # assert sw_type == switch_lookups[common_sink_edges[nodes[node_id]].switch_id]

        # # If its not we should only look for connection block ipins 
        # elif common_sink_edges.get(nodes[node_id]) and switch_lookups[ common_sink_edges[nodes[node_id]].switch_id] == "ipin_cblock":
        #     mux_freq_info["ipin_cblock"]
            


    # Get list of gen wire segment ids
    seg_ids = list(segments.keys())

    # Device bounds
    xmax = max(
        [
            int(nodes[node_id].loc[range_key]) for node_id in list(nodes.keys()) 
                for range_key in ['xhigh','xlow']
                if nodes[node_id].type in ["CHANX"] and int(nodes[node_id].segment["segment_id"]) in seg_ids
        ]
    )
    ymax = max(
        [
            int(nodes[node_id].loc[range_key]) for node_id in list(nodes.keys())
                for range_key in ['yhigh','ylow']
                if nodes[node_id].type in ["CHANY"] and int(nodes[node_id].segment["segment_id"]) in seg_ids
        ]
    )
    xmin = min(
        [
            int(nodes[node_id].loc[range_key]) for node_id in list(nodes.keys())
                for range_key in ['xhigh','xlow']
                if nodes[node_id].type in ["CHANX"] and int(nodes[node_id].segment["segment_id"]) in seg_ids
        ]
    )
    ymin = min(
        [
            int(nodes[node_id].loc[range_key]) for node_id in list(nodes.keys())
                for range_key in ['yhigh','ylow']
                if nodes[node_id].type in ["CHANY"] and int(nodes[node_id].segment["segment_id"]) in seg_ids
        ]
    )

    # Delete any mux infos from list that are on or have input / output on the boundary
    node_coord_xkeys = ['xlow', 'xhigh']
    node_coord_ykeys = ['ylow', 'yhigh']
    for k in sorted(mux_infos):
        node: Node = nodes[k]
        if node.type == "CHANX" or node.type == "CHANY":
            # Check if its on the boundary
            chans_on_bounds = [
                int(node.loc[xkey]) <= xmin or int(node.loc[xkey]) >= xmax or \
                    int(node.loc[ykey]) <= ymin or int(node.loc[ykey]) >= ymax 
                    for xkey, ykey in zip(node_coord_xkeys, node_coord_ykeys)
            ]
            if any(chans_on_bounds):
                    # Prune any node in edge list which has a coordinate on the boundary
                    del mux_infos[k]
                    continue
    
    device_num_tiles_no_bounds = ((xmax-1) - (xmin + 1)) * ((ymax - 1) - (ymin + 1) )

    mux_freq_info = defaultdict(dict)
    # Use the common sink edges to find the number of muxes of each type (filtered with bounds)
    for node_id in mux_infos.keys():
        # Get the switch type for the node
        sw_type = switch_lookups[common_sink_edges[node_id][0].switch_id]
        # Count the number of Muxes of this  
        mux_freq_info[sw_type]["FREQ"] = mux_freq_info[sw_type].get("FREQ", 0) + 1

    # This calculates the frequency of Switches per tile but does not account for Hardblocks ie 
    #   Assumes that the same number of switches exist in a hard block + a regular tile (could over estimate)
    for sw_type in mux_freq_info.keys():
        mux_freq_info[sw_type]["FREQ_PER_TILE"] = mux_freq_info[sw_type]["FREQ"] / device_num_tiles_no_bounds


    # Getting fanout fanin freq information
    for k in mux_infos.keys():
        for param_key in ['fanout', 'fanin']:
            # if not mux_infos[k].get(param_key):
            #     continue
            if not freq_info.get(param_key):
                freq_info[param_key] = {} 
            # If fanout / fanin val not in freq_info[param_key] then add it and set to 0
            # freq_info ["fanin/fanout"] [SWITCH_ID]
            # iterate over sw_ids in the parameter keys
            for sw_id in mux_infos[k][param_key].keys():
                if freq_info[param_key].get(sw_id) is None:
                    freq_info[param_key][sw_id] = {}
                # freq_info [fanin/fanout] [SWITCH_ID] [FANIN/FANOUT_VAL] = freq_info [fanin/fanout] [SWITCH_ID] [FANIN/FANOUT_VAL] + 1
                param_val = mux_infos[k][param_key][sw_id]
                freq_info[param_key][sw_id][param_val] = freq_info[param_key][sw_id].get(param_val, 0) + 1

    # fanout_col_str = f"{'WIRE_FANOUT_TOTAL':<{stdout_col_width}}{'WIRE_FANOUT_L4_MUX':<{stdout_col_width}}{'WIRE_FANOUT_L16_MUX':<{stdout_col_width}}{'WIRE_FANOUT_CB_IPIN':<{stdout_col_width}}"
    # fanin_col_str = f"{'WIRE_FANIN_TOTAL':<{stdout_col_width}}{'WIRE_FANIN_L4_MUX':<{stdout_col_width}}{'WIRE_FANIN_L16_MUX':<{stdout_col_width}}{'WIRE_FANIN_CB_IPIN':<{stdout_col_width}}"

    # print(f"{'RR_NODE':<{stdout_col_width}}{fanout_col_str}{fanin_col_str}")
    
    # Make dir to store outputs
    assert os.path.isdir(out_dpath), f"Output directory {out_dpath} does not exist"
    result_dpath = os.path.join(out_dpath, f"{rrg_str}")
    os.makedirs(result_dpath, exist_ok=True)
    plot_dpath = os.path.join(result_dpath, "plots")
    os.makedirs(plot_dpath, exist_ok=True)
    print(f"Writing results to {result_dpath}")

    # Output results for frequency of muxes
    rg_utils.write_dict_to_csv([{"SWITCH_TYPE": k, "FREQ": v["FREQ"], "FREQ_PER_TILE": v["FREQ_PER_TILE"]} for k, v in mux_freq_info.items()], os.path.join(result_dpath, "rr_mux_freqs"))

    # We need to get fanin / fanout catagories for each switch type that exists in device
    fanin_label_sw_pairs = list(set([
        (sw_id, f"fanin_num_{switch_lookups[sw_id]}")
            for node_id in mux_infos.keys()
                for sw_id in mux_infos[node_id]['fanin'].keys() if sw_id != 'total' 
    ]))
    fanout_label_sw_pairs = list(set([
        (sw_id, f"fanout_{switch_lookups[sw_id]}")
            for node_id in mux_infos.keys()
                for sw_id in mux_infos[node_id]['fanout'].keys() if sw_id != 'total' 
    ]))
    # print(fanin_label_sw_pairs)
    # print(fanout_label_sw_pairs)
    # exit()
    # fanin_switch_keys = list(set([
    #     f"fanin_num_{switch_lookups.get(sw_id, sw_id)}" 
    #         for node_id in mux_infos.keys() for sw_id in mux_infos[node_id]['fanin'].keys() if sw_id != 'total'
    # ]))
    # fanout_switch_keys = list(set([
    #     f"fanout_{switch_lookups.get(sw_id, sw_id)}" 
    #         for node_id in mux_infos.keys() for sw_id in mux_infos[node_id]['fanout'].keys() if sw_id != 'total'
    # ]))

    # fanout_switch_keys = set([f"fanout_{switch_lookups[sw_id]}" for node_id in mux_infos.keys() for sw_id in mux_infos[node_id]['fanout'].keys()  ])
    
    out_dict_cats = [
        "rr_node",
        "wire_type",
        "drv_mux_type",
        *[fanin_label_sw_pair[1] for fanin_label_sw_pair in fanin_label_sw_pairs],
        'fanin_num_total',
        *[fanout_label_sw_pair[1] for fanout_label_sw_pair in fanout_label_sw_pairs],
        'fanout_total',
        # "fanout_total",
        # "fanout_l4_mux",
        # "fanout_l16_mux",
        # "fanout_cb_ipin",
        # "fanout_num_vir_ipin",
        # "fanin_total",
        # "fanin_num_l4",
        # "fanin_num_l16",
        # "fanin_num_cb_ipin",
        # "fanin_num_vir_opin",
    ]
    header = ''.join([ f"{cat_str:<{stdout_col_width}}" for cat_str in out_dict_cats ])
    print(header)

    # CSV written out and used to generate pandas df for plotting + analysis
    csv_out_dicts = []
    for k in sorted(mux_infos):
        # mux_info_keys = [sw_key for sw_key in mux_infos[k]['fanout'].keys() if sw_key != 'total']
        # assert len(mux_info_keys) == len(fanout_switch_keys), f"Fanout Switch Keys Mismatch: {mux_info_keys} != {fanout_switch_keys}"

        # fanout_eles = []
        # for fanout_sw_key in fanout_switch_keys:
        #     fanout_eles.append(mux_infos[k]['fanout'].get(sw_id, 0))

        csv_out_row = {
                "rr_node": k,
                'wire_type': mux_infos[k].get('wire_type'),
                'drv_mux_type': mux_infos[k].get('drv_mux_type'),
                **{
                    fanout_sw_key: mux_infos[k]['fanout'].get(sw_id, 0) for sw_id, fanout_sw_key in fanout_label_sw_pairs
                },
                'fanout_total': mux_infos[k]['fanout']['total'],
                **{
                    fanin_sw_key: mux_infos[k]['fanin'].get(sw_id, 0) for sw_id, fanin_sw_key in fanin_label_sw_pairs
                },
                'fanin_num_total': mux_infos[k]['fanin']['total'],
            }

                # **{
                    
                # },
                # **{
                #     f"fanin_{switch_lookups[sw_id]}": mux_infos[k]['fanin'].get(sw_id, 0) for sw_id in mux_infos[k]['fanin'].keys()
                # },
                # 'wire_type': mux_infos[k].get('wire_type'),
                # 'drv_mux_type': mux_infos[k].get('drv_mux_type'),
                # "fanout_total": mux_infos[k]['fanout']['total'],
                # "fanout_l4_mux": mux_infos[k]['fanout'].get(L4_SW_ID, 0),
                # "fanout_l16_mux": mux_infos[k]['fanout'].get(L16_SW_ID, 0),
                # "fanout_cb_ipin": mux_infos[k]['fanout'].get(CB_IPIN_SW_ID, 0),
                # "fanout_num_virtual_ipin" : mux_infos[k]['fanout'].get(VIRTUAL_PIN_ID, 0),
                # "fanin_total": mux_infos[k]['fanin']['total'],
                # "fanin_num_l4": mux_infos[k]['fanin'].get(L4_SW_ID, 0),
                # "fanin_num_l16": mux_infos[k]['fanin'].get(L16_SW_ID, 0),
                # "fanin_num_cb_ipin": mux_infos[k]['fanin'].get(CB_IPIN_SW_ID, 0),
                # "fanin_num_virtual_opin" : mux_infos[k]['fanout'].get(VIRTUAL_PIN_ID, 0),
            
        # )
        # log_out_row = []
        # print(csv_out_dicts[-1])
        # print(mux_infos[k])

        csv_out_dicts.append(
            csv_out_row
        )

        # log_out_row = []
        # for cat_str in out_dict_cats:
        #     ele_val = f"{csv_out_row[cat_str]:<{stdout_col_width}}"
        #     print(f"{cat_str}:{ele_val}")
        #     log_out_row.append()

        log_out_row = ''.join([ f"{csv_out_row[k]:<{stdout_col_width}}" for k in out_dict_cats ])
        print(log_out_row)

        # fanout_vals_str = f"{mux_infos[k]['wire_type']:<{stdout_col_width}}{mux_infos[k]['fanout']['total']:<{stdout_col_width}}{mux_infos[k]['fanout'].get(L4_SW_ID, 0):<{stdout_col_width}}{mux_infos[k]['fanout'].get(L16_SW_ID, 0):<{stdout_col_width}}{mux_infos[k]['fanout'].get(CB_IPIN_SW_ID, 0):<{stdout_col_width}}{mux_infos[k]['fanout'].get(VIRTUAL_PIN_ID, 0):<{stdout_col_width}}"
        # fanin_vals_str = f"{mux_infos[k]['fanin']['total']:<{stdout_col_width}}{mux_infos[k]['fanin'].get(L4_SW_ID, 0):<{stdout_col_width}}{mux_infos[k]['fanin'].get(L16_SW_ID, 0):<{stdout_col_width}}{mux_infos[k]['fanin'].get(CB_IPIN_SW_ID, 0):<{stdout_col_width}}{mux_infos[k]['fanin'].get(VIRTUAL_PIN_ID, 0):<{stdout_col_width}}"
        # print(f"{k:<{stdout_col_width}}{fanout_vals_str}{fanin_vals_str}")

    rg_utils.write_dict_to_csv(csv_out_dicts, os.path.join(result_dpath,"rr_wires_detailed"))

    # Print out frequency of occurances

    # Print out the frequency of occurances of fanouts of each wire type 
    # print(f"{'L4_DRV_FANOUT_WIRE_FREQ_KEY':<{long_stdout_col_width}}{'FREQ':<{long_stdout_col_width}}")
    # for fanout_key in sorted(freq_info['fanout'][L4_SW_ID]):
    #     print(f"{fanout_key:<{long_stdout_col_width}}{freq_info['fanout'][L4_SW_ID][fanout_key]:<{long_stdout_col_width}}")
    # print(f"{'L16_DRV_FANOUT_WIRE_FREQ_KEY':<{long_stdout_col_width}}{'FREQ':<{long_stdout_col_width}}")
    # for fanout_key in sorted(freq_info['fanout'][L16_SW_ID]):
    #     print(f"{fanout_key:<{long_stdout_col_width}}{freq_info['fanout'][L16_SW_ID][fanout_key]:<{long_stdout_col_width}}")
    # print(f"{'CB_IPIN_FANOUT_WIRE_FREQ_KEY':<{long_stdout_col_width}}{'FREQ':<{long_stdout_col_width}}")
    # for fanout_key in sorted(freq_info['fanout'][CB_IPIN_SW_ID]):
    #     print(f"{fanout_key:<{long_stdout_col_width}}{freq_info['fanout'][CB_IPIN_SW_ID][fanout_key]:<{long_stdout_col_width}}")
    # print(f"{'TOTAL_FANOUT_WIRE_FREQ_KEY':<{long_stdout_col_width}}{'FREQ':<{long_stdout_col_width}}")
    # for fanout_key in sorted(freq_info['fanout']['total']):
    #     print(f"{fanout_key:<{long_stdout_col_width}}{freq_info['fanout']['total'][fanout_key]:<{long_stdout_col_width}}")

    # # Print out the frequency of occurances of fanins of each wire type
    # print(f"{'L4_DRV_FANIN_WIRE_FREQ_KEY':<{long_stdout_col_width}}{'FREQ':<{long_stdout_col_width}}")
    # for fanout_key in sorted(freq_info['fanin'][L4_SW_ID]):
    #     print(f"{fanout_key:<{long_stdout_col_width}}{freq_info['fanin'][L4_SW_ID][fanout_key]:<{long_stdout_col_width}}")
    # print(f"{'L16_DRV_FANIN_WIRE_FREQ_KEY':<{long_stdout_col_width}}{'FREQ':<{long_stdout_col_width}}")
    # for fanout_key in sorted(freq_info['fanin'][L16_SW_ID]):
    #     print(f"{fanout_key:<{long_stdout_col_width}}{freq_info['fanin'][L16_SW_ID][fanout_key]:<{long_stdout_col_width}}")
    # print(f"{'TOTAL_FANIN_WIRE_FREQ_KEY':<{long_stdout_col_width}}{'FREQ':<{long_stdout_col_width}}")
    # for fanout_key in sorted(freq_info['fanin']['total']):
    #     print(f"{fanout_key:<{long_stdout_col_width}}{freq_info['fanin']['total'][fanout_key]:<{long_stdout_col_width}}")    

    routing_arch_df: pd.DataFrame = pd.DataFrame.from_dict(csv_out_dicts)

    wire_specific_dfs: List[pd.DataFrame] = [
        routing_arch_df[routing_arch_df['drv_mux_type'] == drv_mux_type] for drv_mux_type in switch_lookups.values()
    ]
    # Plotting & Analysis
    wire_analysis_stats: Dict[str, Dict[str, dict]] = {} # Statistics that apply to an entire df column

    for wire_df in wire_specific_dfs:
        if not wire_df.empty:
            for col in wire_df.columns:
                # We dont want to get normal dists for these data types
                if col not in ["rr_node", "wire_type", "drv_mux_type"]:
                    num_bins = 50
                    # Get mean and std dev for normal dist
                    mean = np.mean(wire_df[col])
                    std_dev = np.std(wire_df[col])
                    # Init wire_analysis stats element for this wire type
                    col_wire_stats = {}
                    # wire_stats['wire_type'] = wire_df['fanout_wire_type'].values[0]
                    col_wire_stats['mean'] = mean
                    col_wire_stats['std_dev'] = std_dev
                    # col_wire_stats['mode'] = stats.mode(wire_df[col])
                    col_wire_stats['min'] = min(wire_df[col])
                    col_wire_stats['max'] = max(wire_df[col])

                    cur_wire_type = wire_df['wire_type'].values[0]
                    cur_drv_type = wire_df['drv_mux_type'].values[0]

                    # Create bounds and prune the data to be within 2 std devs IF standard deviation is over a threshold
                    upper_bound = mean + 2*std_dev
                    lower_bound = mean - 2*std_dev
                    std_dev_threshold = 1
                    # Only prune if std_dev is over a certain threshold
                    if std_dev > std_dev_threshold:
                        pruned_wire_df = wire_df[(wire_df[col] > lower_bound) & (wire_df[col] < upper_bound)]
                        col_wire_stats['pruned_mean'] = np.mean(pruned_wire_df[col])
                        col_wire_stats['pruned_std_dev'] = np.std(pruned_wire_df[col])
                    else:
                        col_wire_stats['pruned_mean'] = mean
                        col_wire_stats['pruned_std_dev'] = std_dev
                    
                    col_wire_stats['mean_prune_diff'] = (col_wire_stats['mean'] - col_wire_stats['pruned_mean']) / (col_wire_stats['mean'] + .00001)

                    if not wire_analysis_stats.get(cur_wire_type):
                        wire_analysis_stats[cur_wire_type] = {}

                    # In case there are multiple values
                    if not wire_analysis_stats[cur_wire_type].get(cur_drv_type):
                        wire_analysis_stats[cur_wire_type][cur_drv_type] = {}
                    
                    assert wire_analysis_stats[cur_wire_type][cur_drv_type].get(col) is None, f"Column {col} already exists in wire_analysis_stats"
                    wire_analysis_stats[cur_wire_type][cur_drv_type][col] = col_wire_stats


                    # wire_stats[col]['mode'] = stats.mode(wire_df[col])
                    # wire_stats[col]['min'] = min(wire_df[col])
                    # wire_stats[col]['max'] = max(wire_df[col])
                    # wire_stats[col]['std_dev'] = std_dev

                    # wire_stats[col]['hist'] = {}
                    # wire_stats[col]['hist']['freqs'], wire_stats[col]['hist']['bins'] = np.histogram(wire_df[col], bins=num_bins)
                    # Generate normal distribution based on mean and standard deviation
                    pdf = stats.norm.pdf(wire_df[col].sort_values(), mean, std_dev)
                    # Generate cdf
                    cdf = stats.norm.cdf(wire_df[col].sort_values(), mean, std_dev)
                    # Saving to data struct to use later
                    # wire_analysis_dfs += pd.DataFrame(
                    #     {
                    #         'pdf': pdf,
                    #         'cdf': cdf
                    #     }
                    # )
                    dists = [
                        {
                            'fname_key': "pdf",
                            'fn': pdf,
                            'label': 'Probablility Distribution'
                        },
                        # Uncomment to add CDF plots
                        # {
                        #     'fname_key': "cdf",
                        #     'fn': cdf,
                        #     'label': 'Cumulative Distribution'
                        # },
                    ]
                    for dist in dists:
                        # Plotting
                        fig, ax1 = plt.subplots()

                        # Plot histogram
                        ax1.hist(wire_df[col], bins=num_bins, alpha=0.7, color='b', label='Histogram', edgecolor='black')

                        # Parse the col name for 
                        xlabel = "Num Muxes Loading Wire" if "fanout" in col.lower() else "Num Mux Inputs"
                        ax1.set_xlabel(xlabel)
                        ax1.set_ylabel('Frequency')

                        # Add vlines for standard deviations
                        ax1.axvline(mean, color='k', linestyle='dashed', linewidth=1)
                        ax1.axvline(mean + std_dev, color='y', linestyle='dashed', linewidth=1)
                        ax1.axvline(mean - std_dev, color='y', linestyle='dashed', linewidth=1)
                        ax1.axvline(mean + 2*std_dev, color='g', linestyle='dashed', linewidth=1)
                        ax1.axvline(mean - 2*std_dev, color='g', linestyle='dashed', linewidth=1)

                        # Create secondary y-axis for normal distribution
                        ax2 = ax1.twinx()
                        ax2.plot(wire_df[col].sort_values(), dist['fn'], color='r', label=dist['label'])
                        ax2.set_ylabel(dist['label'])

                        # Combine legends
                        lines1, labels1 = ax1.get_legend_handles_labels()
                        lines2, labels2 = ax2.get_legend_handles_labels()
                        lines = lines1 + lines2
                        labels = labels1 + labels2
                        leg_loc = 'upper right' if "pdf" in dist['fname_key'] else 'upper left'
                        ax1.legend(lines, labels, loc=leg_loc)

                        # Set only integer values displayed on Xaxis
                        ax1.xaxis.set_major_locator(plt.MaxNLocator(integer=True))
                        # Adjust layout to provide more space around y-axis labels
                        plt.subplots_adjust(right=0.9)
                        plt.title(f"{wire_df['wire_type'].values[0]} {col}")
                        plt.tight_layout()
                        fig.savefig(
                            os.path.join(plot_dpath, f"{dist['fname_key']}_{wire_df['wire_type'].values[0]}_{col}_dist.png")
                        )
            
    print("FPGA TILE BOUNDS")
    print(f"XMIN: {xmin}, XMAX: {xmax}, YMIN: {ymin}, YMAX: {ymax}")
    print(f"NUM RR_NODES: {len(nodes)}")

    stats_header_cols = ["WIRE_TYPE", "DRV_TYPE", "COL_TYPE", "MEAN", "STD_DEV", "MIN", "MAX", "PRUNED_MEAN", "PRUNED_STD_DEV", "PRUNE_CHANGE_%"]
    stats_header = ''.join([ f"{col:<{stdout_col_width}}" for col in stats_header_cols ])
    print(stats_header)


    # print(f'{"WIRE_TYPE":<{stdout_col_width}}{"DRV_TYPE":<{stdout_col_width}}{"COL_TYPE":<{stdout_col_width}}{"MEAN":<{stdout_col_width}}{"STD_DEV":<{stdout_col_width}}{"MODE":<{stdout_col_width}}{"MIN":<{stdout_col_width}}{"MAX":<{stdout_col_width}}{"PRUNED_MEAN":<{stdout_col_width}}{"PRUNED_STD_DEV":<{stdout_col_width}}')
    # pprint.pprint(wire_analysis_stats)
    wire_info_out_csv_rows: List[Dict[str, Any]] = []
    for wire_type in wire_analysis_stats.keys():
        for drv_type in wire_analysis_stats[wire_type].keys():
            for col_type in wire_analysis_stats[wire_type][drv_type].keys():
                # Print wire type and col type portion of the row
                print(f"{wire_type:<{stdout_col_width}}{drv_type:<{stdout_col_width}}{col_type:<{stdout_col_width}}", end='')
                for param_key in wire_analysis_stats[wire_type][drv_type][col_type].keys():
                    # Print the rest of the row
                    print(f"{wire_analysis_stats[wire_type][drv_type][col_type][param_key]:<{stdout_col_width}}", end='')
                print()
                # Append to list of dicts to write to csv
                wire_info_out_csv_rows.append(
                    {
                        "WIRE_TYPE": wire_type,
                        "DRV_TYPE": drv_type,
                        "COL_TYPE": col_type,
                        **wire_analysis_stats[wire_type][drv_type][col_type]
                    }
                )
    
    # Output the wire analysis as another CSV
    rg_utils.write_dict_to_csv(wire_info_out_csv_rows, os.path.join(result_dpath,"rr_wire_stats"))
    
    # Put the wire analysis info as well as segment/switches extracted from rr graph to return dict
    rr_info: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
    rr_info["wire_analysis"] = wire_analysis_stats

    # Output segment + switch information to csv
    seg_out_dicts = [dataclasses.asdict(seg) for seg in segments.values()]
    # Destructively modify seg_out_dicts to flatten nested dict
    for seg_out_dict in seg_out_dicts:
        for k in list(seg_out_dict.keys()):
            if isinstance(seg_out_dict[k], dict):
                for sub_k in list(seg_out_dict[k].keys()):
                    seg_out_dict[sub_k] = seg_out_dict[k][sub_k]
                del seg_out_dict[k]
    # Get largest dict in list of dicts and fill in missing values
    seg_keys = set()
    for i in range(len(seg_out_dicts)):
        for k in list(seg_out_dicts[i].keys()):
            seg_keys.add(k)

    for i in range(len(seg_out_dicts)):
        for k in seg_keys:
            if k not in seg_out_dicts[i]:
                seg_out_dicts[i][k] = None
    
    switch_out_dicts = [dataclasses.asdict(sw) for sw in switches.values()]
    # Destructively modify seg_out_dicts to flatten nested dict
    for sw_out_dict in switch_out_dicts:
        for k in list(sw_out_dict.keys()):
            if isinstance(sw_out_dict[k], dict):
                for sub_k in list(sw_out_dict[k].keys()):
                    sw_out_dict[sub_k] = sw_out_dict[k][sub_k]
                del sw_out_dict[k]
    # Get largest dict in list of dicts and fill in missing values
    sw_keys = set()
    for i in range(len(switch_out_dicts)):
        for k in list(switch_out_dicts[i].keys()):
            sw_keys.add(k)
    for i in range(len(switch_out_dicts)):
        for k in sw_keys:
            if k not in switch_out_dicts[i]:
                switch_out_dicts[i][k] = None

    rg_utils.write_dict_to_csv(seg_out_dicts, os.path.join(result_dpath,"rr_segments"))
    rg_utils.write_dict_to_csv(switch_out_dicts, os.path.join(result_dpath,"rr_switches"))
    rr_info["segments"] = {seg_id: dataclasses.asdict(segment) for seg_id, segment in segments.items()}
    rr_info["switches"] = {sw_id: dataclasses.asdict(sw) for sw_id, sw in switches.items()}

    # pprint.pprint(rr_info)    
    print(f"Finished parsing {input_rr_xml_fpath} in {timer() - global_start} seconds")
    # Now we need to return the wire statistics required for creating wire loads from the RR graph data
    return rr_info


if __name__ == "__main__":
    main()