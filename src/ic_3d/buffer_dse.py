# General imports
from typing import List, Dict, Tuple, Set, Union, Any, Type
import os, sys
from dataclasses import dataclass, asdict
import datetime
import yaml
import re
import subprocess as sp
from pathlib import Path
import json
import copy
import math
import pandas as pd
import io
from functools import reduce

import plotly.graph_objects as go
import plotly.subplots as subplots
import plotly.express as px
import shapely as sh


import src.common.utils as rg_utils
import src.common.data_structs as rg_ds


# UTILS

def convert_value(val, suffix, unit_lookup):
    if suffix in unit_lookup:
        return float(val) * unit_lookup[suffix]
    else:
        return float(val)

def get_inst_line(inst: rg_ds.SpSubCktInst) -> str:
    """ Generates the instance line for a spice subckt """
    subckt_inst_sublines = [
        f"{inst.subckt.prefix}_{inst.name}",
    ]
    # create list of connections of length of inst ports
    port_conns = [None]*len(inst.subckt.ports)
    # iterate over connections and top level subckt io ports
    for conn_key, conn_val in inst.conns.items():
        for port_key, port_val in inst.subckt.ports.items():
            if conn_key == port_key:
                # create a connection at the right idx
                # subckt_inst_sublines.append(conn_val)
                port_conns[port_val["idx"]] = conn_val
                break
    subckt_inst_sublines.extend(port_conns)
    param_strs = [f"{param}={val}" for param, val in inst.param_values.items()]
    assert None not in subckt_inst_sublines, print("Not all connections made in instantiation:", *subckt_inst_sublines)
    
    # subckt or mfet
    if inst.subckt.prefix == "X" or inst.subckt.prefix == "M":
        subckt_inst_sublines = [*subckt_inst_sublines, inst.subckt.name, *param_strs]
    else:
        subckt_inst_sublines = [*subckt_inst_sublines, *param_strs]

    return " ".join(subckt_inst_sublines)


def get_subckt_hdr_lines(subckt_def_str: str) -> list:
    hdr_len = 91
    hdr_buff = "*" * hdr_len
    hdr_lines = [hdr_buff, "* " + subckt_def_str, hdr_buff]
    return hdr_lines

def get_subckt_ports_new(subckt: rg_ds.SpSubCkt) -> str:
    """ Generates the ports for a spice subckt """
    ports_strs = [port_dict["name"] for port_dict in sorted(subckt.ports.values(), key = lambda x: x['idx']) ]
    param_strs = [f"{param}={val}" for param, val in subckt.params.items()]
    subckt_ports_sublines = [
        f".SUBCKT",
        f"{subckt.name}",
        *ports_strs,
        *param_strs,
    ]
    subckt_port_line = " ".join(subckt_ports_sublines)
    return subckt_port_line

def get_subckt_insts_lines(subckt: rg_ds.SpSubCkt) -> list:
    # These two are defined somewhere but will be used to connect disperate     
    subckt_insts_lines = []
    for inst in subckt.insts:
        subckt_insts_lines.append(get_inst_line(inst))
    return subckt_insts_lines 



def get_subckt_lines_new(sp_subckt: rg_ds.SpSubCkt) -> list:
    """ Generates the lines for a spice subckt """
    subckt_hdr = get_subckt_hdr_lines(f"{sp_subckt.name} subcircuit")
    subckt_port_line = get_subckt_ports_new(sp_subckt)
    subckt_insts_lines = get_subckt_insts_lines(sp_subckt)
    subckt_lines = [
        "\n",
        *subckt_hdr,
        subckt_port_line,
        *subckt_insts_lines,
        ".ENDS",
        "\n" 
    ]
    return subckt_lines

def direct_connect_insts(inst_list: list) -> list:
    # Input and output nodes are set manually outside of this function
    for idx, inst in enumerate(inst_list):
        prev_tmp_int_node = f"n_{idx}"
        cur_tmp_int_node = f"n_{idx+1}"
        if idx == 0:
            inst.conns["out"] = cur_tmp_int_node
        elif idx == len(inst_list) - 1:
            inst.conns["in"] = prev_tmp_int_node
        else:
            inst.conns["in"] = prev_tmp_int_node
            inst.conns["out"] = cur_tmp_int_node
    return inst_list


def get_prop_del_meas_lines(ic_3d_info: rg_ds.Ic3d, in_nodes: List[str], out_nodes: List[str], meas_range: List[int]) -> List[str]:
    """
    This will return spice measure lines measuring the rising and falling propegation delay from:
    1. in_nodes to out_nodes Ex. in_nodes[0] -> out_nodes[0], in_nodes[1] -> out_nodes[1] ...
    2. range specified in meas_range from node_in[meas_range[0]] -> node_out[meas_range[1]] 
    """
    
    if (len(in_nodes)-1) % 2 != 0:
        total_falling_trig_targ = ["RISE","FALL"]
        total_rising_trig_targ = ["FALL","RISE"]
    else:
        total_falling_trig_targ = ["FALL","FALL"]
        total_rising_trig_targ = ["RISE","RISE"]

    # assert len(in_nodes) == len(out_nodes), "ERROR: in_nodes and out_nodes must be the same length"
    
    
    prop_del_meas_lines = rg_utils.flatten_mixed_list([
        [
            f'.MEASURE TRAN falling_prop_delay_{node_idx}',
            f'+    TRIG v({in_nodes[node_idx]}) VAL="{ic_3d_info.driver_model_info.v_supply_param}/2" RISE=1',
            f'+    TARG v({out_nodes[node_idx]}) VAL="{ic_3d_info.driver_model_info.v_supply_param}/2" FALL=1',
            # f'+    TD=TRIG',
            f'.MEASURE TRAN rising_prop_delay_{node_idx}',
            f'+    TRIG v({in_nodes[node_idx]}) VAL="{ic_3d_info.driver_model_info.v_supply_param}/2" FALL=1',
            f'+    TARG v({out_nodes[node_idx]}) VAL="{ic_3d_info.driver_model_info.v_supply_param}/2" RISE=1',
            # f'+    TD=TRIG',
            f'.MEASURE max_prop_delay_{node_idx} param="max(abs(rising_prop_delay_{node_idx}),abs(falling_prop_delay_{node_idx}))"',
            # we will measure the change in voltage from 20% to 80% of the supply voltage
            # Add the t_rise and t_fall for fidelity
            f'.MEASURE TRAN t_rise_{node_idx}',
            f'+      TRIG V({out_nodes[node_idx]}) VAL="0.2*{ic_3d_info.driver_model_info.v_supply_param}" RISE=1',
            f'+      TARG V({out_nodes[node_idx]}) VAL="0.8*{ic_3d_info.driver_model_info.v_supply_param}" RISE=1',
            #f'+    TD=TRIG',
            f'.MEASURE TRAN t_fall_{node_idx}',
            f'+      TRIG V({out_nodes[node_idx]}) VAL="0.8*{ic_3d_info.driver_model_info.v_supply_param}" FALL=1',
            f'+      TARG V({out_nodes[node_idx]}) VAL="0.2*{ic_3d_info.driver_model_info.v_supply_param}" FALL=1',
            #f'+    TD=TRIG',
        ] for node_idx in range(len(in_nodes))
        ])
    # add the range specified in meas_range
    prop_del_meas_lines += [
        f'.MEASURE TRAN falling_prop_delay_{in_nodes[meas_range[0]]}_{out_nodes[meas_range[1]]}',
        f'+    TRIG v({in_nodes[meas_range[0]]}) VAL="{ic_3d_info.driver_model_info.v_supply_param}/2" {total_falling_trig_targ[0]}=1',
        f'+    TARG v({out_nodes[meas_range[1]]}) VAL="{ic_3d_info.driver_model_info.v_supply_param}/2" {total_falling_trig_targ[1]}=1',
        f'+    TD=TRIG',

        f'.MEASURE TRAN rising_prop_delay_{in_nodes[meas_range[0]]}_{out_nodes[meas_range[1]]}',
        f'+    TRIG v({in_nodes[meas_range[0]]}) VAL="{ic_3d_info.driver_model_info.v_supply_param}/2" {total_rising_trig_targ[0]}=1',
        f'+    TARG v({out_nodes[meas_range[1]]}) VAL="{ic_3d_info.driver_model_info.v_supply_param}/2" {total_rising_trig_targ[1]}=1',
        f'+    TD=TRIG',

        # Add maximum total rising/falling prop delay to find critical path
        f'.MEASURE max_prop_delay param="max(rising_prop_delay_{in_nodes[meas_range[0]]}_{out_nodes[meas_range[1]]},falling_prop_delay_{in_nodes[meas_range[0]]}_{out_nodes[meas_range[1]]})"',
    ]

    return prop_del_meas_lines


def get_meas_lines_new(ic_3d_info: rg_ds.Ic3d, sp_testing_model: rg_ds.SpTestingModel) -> list:
    

    inv_isnts_in_nodes = [inst.conns["in"] for inst in sp_testing_model.insts if inst.subckt.name == "inv"]
    inv_insts_out_nodes = [inst.conns["out"] for inst in sp_testing_model.insts if inst.subckt.name == "inv"]
    inv_insts_nodes = list(set(inv_insts_out_nodes + inv_isnts_in_nodes))
    # meas range starts at output of last shape inv and ends at output of last inverter
    meas_range = [ic_3d_info.design_info.shape_nstages, len(inv_isnts_in_nodes)-1]

    sp_meas_lines = [
        *get_subckt_hdr_lines("Measurement"),
        *get_prop_del_meas_lines(ic_3d_info, inv_isnts_in_nodes, inv_insts_out_nodes, meas_range),
        
        #f'.PRINT v({driver_model_info.global_in_node}) ' + ' '.join([f"v({node})" for node in inv_insts_out_nodes[1:len(inv_insts_out_nodes)]])

        f'.PRINT ' + ' '.join([f"v({node})" for node in inv_insts_nodes ]),
        # Measure statements for optimization but still should be printed either way
        f".measure tpd param='max(rising_prop_delay_{inv_isnts_in_nodes[ic_3d_info.design_info.shape_nstages]}_{inv_insts_out_nodes[-1]},falling_prop_delay_{inv_isnts_in_nodes[ic_3d_info.design_info.shape_nstages]}_{inv_insts_out_nodes[-1]})' goal = 0",
        f".measure diff param='rising_prop_delay_{inv_isnts_in_nodes[ic_3d_info.design_info.shape_nstages]}_{inv_insts_out_nodes[-1]} - falling_prop_delay_{inv_isnts_in_nodes[ic_3d_info.design_info.shape_nstages]}_{inv_insts_out_nodes[-1]}' goal = 0",

        #f'.GRAPH v({driver_model_info.global_in_node}) ' + ' '.join([f"v({node})" for node in inv_insts_out_nodes[1:len(inv_insts_out_nodes)]]) + ' title "inv_out_node_voltage" '
        # f'.PRINT ' + ' '.join([f"cap({node})" for node in inv_isnts_in_nodes])  
        # f'.plot v({driver_model_info.global_in_node}) v({inv_insts_out_nodes[1]}) v({inv_insts_out_nodes[-1]}) ',
    ]
    return sp_meas_lines


# GLOBALS

# deps for spice_simulation_setup
def init_subckt_libs(design_info: rg_ds.DesignInfo) -> rg_ds.SpSubCktLibs:
    # PORT DEFS
    io_ports = {
        "in" : { 
            "name" : "n_in",
            "idx" : 0
        },
        "out" : { 
            "name" : "n_out",
            "idx" : 1
        }
    }

    io_vdd_gnd_ports = {
        "in" : { 
            "name" : "n_in",
            "idx" : 0
        },
        "out" : { 
            "name" : "n_out",
            "idx" : 1
        },
        "gnd" : { 
            "name" : "n_gnd",
            "idx" : 2
        },
        "vdd" : { 
            "name" : "n_vdd",
            "idx" : 3
        }
    }

    mfet_ports = {
        "base" : {
            "name" : "n_b",
            "idx": 3,
        },
        "drain" : {
            "name" : "n_d",
            "idx": 0,
        },
        "gate" : {
            "name" : "n_g",
            "idx": 1,
        },
        "source" : {
            "name" : "n_s",
            "idx": 2,
        },
    }

    nfet_width_param = "Wn"
    pfet_width_param = "Wp"
    # global subckt_libs
    """
        Atomic subckts are from spice syntax and are not defined anywhere
        This means that the parameters used are always assigned during an instantiation of atomic subckts
    """    
    min_tx_contact_width_key = "min_tx_contact_width"
    tx_diffusion_length_key = "tx_diffusion_length"
    sp_subckt_atomic_lib = {
        "cap" : rg_ds.SpSubCkt(
            element = "cap",
            ports = io_ports,
            params = {
                "C" : "1f"
            }
        ),
        "res" : rg_ds.SpSubCkt(
            element = "res",
            ports = io_ports,
            params = {
                "R" : "1m"
            }
        ),
        "ind" : rg_ds.SpSubCkt(
            element = "ind",
            ports = io_ports,
            params = {
                "L" : "1p"
            }
        ),
        "mnfet" : rg_ds.SpSubCkt(
            name = "nmos",
            element = "mnfet",
            ports = mfet_ports,
            params = {
                # "hfin" : "hfin",
                "L" : "gate_length",
                "M" : "1",
                "nfin" : f"'{nfet_width_param}'",
                "ASEO" : f"'{nfet_width_param}*{min_tx_contact_width_key}*{tx_diffusion_length_key}'",
                "ADEO" : f"'{nfet_width_param}*{min_tx_contact_width_key}*{tx_diffusion_length_key}'",
                "PSEO" : f"'{nfet_width_param}*({min_tx_contact_width_key}+2*{tx_diffusion_length_key})'",
                "PDEO" : f"'{nfet_width_param}*({min_tx_contact_width_key}+2*{tx_diffusion_length_key})'",
            }
        ),
        "mpfet" : rg_ds.SpSubCkt(
            name = "pmos",
            element = "mpfet",
            ports = mfet_ports,
            params = {
                # "hfin" : "hfin",
                "L" : "gate_length",
                "M" : "1",
                "nfin" : f"'{pfet_width_param}'",
                "ASEO" : f"'{pfet_width_param}*{min_tx_contact_width_key}*{tx_diffusion_length_key}'",
                "ADEO" : f"'{pfet_width_param}*{min_tx_contact_width_key}*{tx_diffusion_length_key}'",
                "PSEO" : f"'{pfet_width_param}*({min_tx_contact_width_key}+2*{tx_diffusion_length_key})'",
                "PDEO" : f"'{pfet_width_param}*({min_tx_contact_width_key}+2*{tx_diffusion_length_key})'",
            }
        )
    }
    #TODO make sure that the number of conn keys are equal to the number of ports in inst 
    basic_subckts = {
        "inv" : rg_ds.SpSubCkt(
            name = "inv",
            element = "subckt",
            ports = io_vdd_gnd_ports,
            params = {
                # "hfin": "3.5e-008",
                "Wn" : "1",
                "Wp" : "2",
                "fanout" : "1",
            },
            insts = [
                rg_ds.SpSubCktInst(
                    subckt = sp_subckt_atomic_lib["mnfet"],
                    name = "N_DOWN",
                    # Connecting the io_gnd_vdd_ports to the mnfet ports
                    # Key will be mnfet port and value will be io_gnd_vdd_ports OR internal node
                    conns = {
                        "gate" : io_vdd_gnd_ports["in"]["name"],
                        "base" : io_vdd_gnd_ports["gnd"]["name"],
                        "drain" : io_vdd_gnd_ports["out"]["name"],
                        "source" : io_vdd_gnd_ports["gnd"]["name"],
                    },
                    param_values = {
                        # "hfin" : "hfin",
                        "L" : "gate_length",
                        "M" : "fanout",
                        "nfin" : f"'{nfet_width_param}'",
                        "ASEO" : f"'{nfet_width_param}*{min_tx_contact_width_key}*{tx_diffusion_length_key}'",
                        "ADEO" : f"'{nfet_width_param}*{min_tx_contact_width_key}*{tx_diffusion_length_key}'",
                        "PSEO" : f"'{nfet_width_param}*({min_tx_contact_width_key}+2*{tx_diffusion_length_key})'",
                        "PDEO" : f"'{nfet_width_param}*({min_tx_contact_width_key}+2*{tx_diffusion_length_key})'",
                    }
                    # if param values are not defined they are set to default
                ),
                rg_ds.SpSubCktInst(
                    subckt = sp_subckt_atomic_lib["mpfet"],
                    name = "P_UP",
                    # Connecting the io_gnd_vdd_ports to the mnfet ports
                    # Key will be mnfet port and value will be io_gnd_vdd_ports OR internal node
                    conns = {
                        "drain" : io_vdd_gnd_ports["out"]["name"],
                        "gate" : io_vdd_gnd_ports["in"]["name"],
                        "source" : io_vdd_gnd_ports["vdd"]["name"],
                        "base" : io_vdd_gnd_ports["vdd"]["name"],
                    },
                    param_values = {
                        # "hfin" : "hfin",
                        "L" : "gate_length",
                        "M" : "fanout",
                        "nfin" : f"'{pfet_width_param}'",
                        "ASEO" : f"'{pfet_width_param}*{min_tx_contact_width_key}*{tx_diffusion_length_key}'",
                        "ADEO" : f"'{pfet_width_param}*{min_tx_contact_width_key}*{tx_diffusion_length_key}'",
                        "PSEO" : f"'{pfet_width_param}*({min_tx_contact_width_key}+2*{tx_diffusion_length_key})'",
                        "PDEO" : f"'{pfet_width_param}*({min_tx_contact_width_key}+2*{tx_diffusion_length_key})'",
                    }
                    # if param values are not defined they are set to default
                ),
            ]
        ),
        "wire" : rg_ds.SpSubCkt(
            name = "wire",
            element = "subckt",
            ports = io_ports,
            params = {
                "Rw" : "1m",
                "Cw" : "1f",
            },
            insts = [
                rg_ds.SpSubCktInst(
                    subckt = sp_subckt_atomic_lib["cap"],
                    name = "PAR_IN",
                    conns = { 
                        "in" : io_ports["in"]["name"],
                        "out" : "gnd", # TODO globally defined gnd, use data structure to access instead of hardcoding                    
                    },
                    param_values = {
                        "C" : "Cw",
                    }
                ),
                rg_ds.SpSubCktInst(
                    subckt = sp_subckt_atomic_lib["res"],
                    name = "SER",
                    conns = { 
                        "in" : io_ports["in"]["name"],
                        "out" : io_ports["out"]["name"],          
                    },
                    param_values = {
                        "R" : "Rw",
                    }
                ),
                rg_ds.SpSubCktInst(
                    subckt = sp_subckt_atomic_lib["cap"],
                    name = "PAR_OUT",
                    conns = { 
                        "in" : io_ports["out"]["name"],
                        "out" : "gnd", # TODO globally defined gnd, use data structure to access instead of hardcoding                    
                    },
                    param_values = {
                        "C" : "Cw",
                    }
                ),
            ],
        ),
    }
    subckts = {
        ##### This works for only a specific metal stack, TODO fix this for all processes #####
        f"bottom_to_top_via_stack": rg_ds.SpSubCkt( 
            name = f"bottom_to_top_via_stack",
            element = "subckt",
            ports = io_ports,
            direct_conn_insts = True,
            # Via stack capacitance estimated by using the wire capacitance of highest layer and multplitlying by height of via stack (conservative)
            insts = rg_utils.flatten_mixed_list(
                [
                    #Via stack going from bottom metal to top metal - num pwr mlayers (leaving 2 layers for X and Y traversal on top metal layers)
                    rg_ds.SpSubCktInst(
                        subckt = basic_subckts["wire"],
                        name = f"m{via_stack_info.mlayer_range[0]}_to_m{via_stack_info.mlayer_range[1]}_via_stack",
                        param_values = {
                            "Rw" : via_stack_info.sp_params["res"].name,
                            "Cw" : via_stack_info.sp_params["cap"].name,
                        }
                    ) for via_stack_info in design_info.process_info.via_stack_infos   
                ]
            )
        )
    }
    
    subckt_libs = rg_ds.SpSubCktLibs(
        atomic_subckts= sp_subckt_atomic_lib,
        basic_subckts = basic_subckts,
        subckts = subckts,
    )
    return subckt_libs


def write_sp_process_data(ic_3d_info: rg_ds.Ic3d) -> None:
    # USES GLOBALS
    sp_process_data_lines = [
        '*** PROCESS DATA AND VOLTAGE LEVELS',
        '.LIB PROCESS_DATA',
        '',
        '*** Voltage levels',
        # Voltage params
        *[f".PARAM {v_param} = {v_val}" for v_param, v_val in ic_3d_info.process_data.voltage_info.items()],
        '',
        '*** Geometry',
        *[f".PARAM {v_param} = {v_val}" for v_param, v_val in ic_3d_info.process_data.geometry_info.items()],
        '',
        '*** Technology (Metal Layers / Vias / uBumps)',
        *[f".PARAM {v_param} = {v_val}" for v_param, v_val in ic_3d_info.process_data.tech_info.items()],
        '',
        '*** Driver params',
        *[f".PARAM {v_param} = {v_val}" for v_param, v_val in ic_3d_info.process_data.driver_info.items()],
        '',
        '*** Supply voltage.',
        'VSUPPLY vdd gnd supply_v',
        '.global ' + " ".join([node for node in ic_3d_info.process_data.global_nodes.keys()]),
        #'VSUPPLYLP vdd_lp gnd supply_v_lp',
        '',
        '*** Device models',
        f'.LIB "{ic_3d_info.spice_info.model_file}" 7NM_FINFET_HP',
        '.ENDL PROCESS_DATA',
    ]
    with open(ic_3d_info.spice_info.process_data_file,"w") as fd:
        for l in sp_process_data_lines:
            print(l, file=fd)

def write_subckt_libs(ic_3d_info : rg_ds.Ic3d, subckt_libs: rg_ds.SpSubCktLibs) -> None:
    
    basic_subckts_lines = [".LIB BASIC_SUBCIRCUITS"]
    for subckt in subckt_libs.basic_subckts.values():
        basic_subckts_lines += get_subckt_lines_new(subckt)
    basic_subckts_lines.append(".ENDL BASIC_SUBCIRCUITS")

    with open(ic_3d_info.spice_info.basic_subckts_file, "w") as fd:
        for l in basic_subckts_lines:
            print(l,file=fd)
    
    subckts_lines = [".LIB SUBCIRCUITS"]
    for subckt in subckt_libs.subckts.values():
        subckts_lines += get_subckt_lines_new(subckt)
    subckts_lines.append(".ENDL SUBCIRCUITS")

    with open(ic_3d_info.spice_info.subckts_file, "w") as fd:
        for l in subckts_lines:
            print(l,file=fd)


def write_sp_includes(ic_3d_info : rg_ds.Ic3d) -> None:

    sp_includes_lines = [
        f'*** INCLUDE ALL LIBRARIES',
        f'.LIB INCLUDES',
        f'*** Include process data (voltage levels, gate length and device models library)',
        f'.LIB "{ic_3d_info.spice_info.process_data_file}" PROCESS_DATA',
        f'*** Include transistor parameters',
        f'*** Include wire resistance and capacitance',
        f'*** Include basic subcircuits',
        f'.LIB "{ic_3d_info.spice_info.basic_subckts_file}" BASIC_SUBCIRCUITS',
        f'*** Include subcircuits',
        f'.LIB "{ic_3d_info.spice_info.subckts_file}" SUBCIRCUITS',
        f'.ENDL INCLUDES',
    ]
    with open(ic_3d_info.spice_info.include_sp_file,"w") as fd:
        for l in sp_includes_lines:
            print(l,file = fd)
    

def spice_simulation_setup(ic_3d_info: rg_ds.Ic3d) -> rg_ds.DesignInfo:
    """ 
        Inputs:
            - ic_3d_info: contains information needed to generate spice files for a particular process (information in the same data structure)
        Outputs: 
            - Spice files:
                - process_data library -> contains process parameters, voltage levels, and device models
                - various subckt libs -> subckt definitions for basic spice components and subckts needed for evaluation
                - include file -> includes all the libraries needed for spice simulation
            - design_info: data structure updated with new information / spice libs we just created
    """
    design_info = ic_3d_info.design_info
    # process data is what spice process data gets written out
    ic_3d_info.process_data.tech_info = {
        # Metal layer & Vias Spice Parameters
        ** { f"{sp_param.name}": f"{sp_param.value}{sp_param.suffix}" for mlayer in ic_3d_info.design_info.process_info.mlayers for sp_param in mlayer.sp_params.values() },
        # Via Stack Parameters
        ** { f"{sp_param.name}": f"{sp_param.value}{sp_param.suffix}" for via_stack_info in ic_3d_info.design_info.process_info.via_stack_infos for sp_param in via_stack_info.sp_params.values() },                    
        # Ubump Parameters
        **{ f"{sp_param.name}": f"{sp_param.value}{sp_param.suffix}" for sp_param in ic_3d_info.design_info.package_info.ubump_info.sp_params.values()}, 
    }
    
    ic_3d_info.process_data.geometry_info = {
        **{ f"{sp_param.name}": f"{sp_param.value}{sp_param.suffix}" for sp_param in ic_3d_info.design_info.process_info.tx_geom_info.sp_params.values()},
    }

    # Write out spice parameters for the process parameters
    write_sp_process_data(ic_3d_info)
    # Initialize and write out spice files for this run
    subckt_libs = init_subckt_libs(design_info)
    write_subckt_libs(ic_3d_info, subckt_libs)
    write_sp_includes(ic_3d_info)
    design_info.subckt_libs = subckt_libs

    return design_info


# deps for write_pn_sizing_opt_sp_sim

def get_buffer_sim_lines(ic_3d_info: rg_ds.Ic3d, num_stages: int, buff_fanout: int, add_wlen: int, pn_size_mode: str = "default", in_sp_sim_df: pd.DataFrame = None) -> Tuple[list, list]:
    
    # Find largest Macro in design, will have to route at least half the largest dimension on top metal layer
    max_macro_dist = max(rg_utils.flatten_mixed_list([[sram.width/2 + sram.height/2] for sram in ic_3d_info.design_info.srams]))

    # Shape Inverter + Num Stages + Inverter on bottom die
    total_inv_stages = 1 + num_stages + ic_3d_info.design_info.bot_die_nstages



    # if noc_idx >= len(design_info.nocs):
    driver_to_ubump_dist = add_wlen
    # else:
        # driver_to_ubump_dist = design_info.nocs[noc_idx].add_wire_len
    
    # Metal Distance for top and bottom metal layers
    routing_mlayer_params = {
        "Rw" : f"'{ic_3d_info.design_info.process_info.mlayers[ic_3d_info.design_info.buffer_routing_mlayer_idx].sp_params['wire_res_per_um'].name}*({max_macro_dist} + {driver_to_ubump_dist})'",
        "Cw" : f"'{ic_3d_info.design_info.process_info.mlayers[ic_3d_info.design_info.buffer_routing_mlayer_idx].sp_params['wire_cap_per_um'].name}*({max_macro_dist} + {driver_to_ubump_dist})'",
    }


    # This means we're assigning optimizing params to the Wn and Wp Sizes 
    if pn_size_mode == "find_opt":
        pn_params = [
            {
                "Wn" : f"{ic_3d_info.pn_opt_model.wn_param}_{inv_stage}",
                "Wp" : f"{ic_3d_info.pn_opt_model.wp_param}_{inv_stage}",
            } 
            for inv_stage in range(total_inv_stages)
        ]
    # This means we're using manually defined sizes found in the process data file
    elif pn_size_mode == "assign_opt" and in_sp_sim_df is not None:
        # TODO int could be changed if not using finfet
        pn_params = [{
            "Wn" : f"{wn}",
            "Wp" : f"{wp}",
        } for wn, wp in zip(in_sp_sim_df["nmos_width"], in_sp_sim_df["pmos_width"])
        ]
    else:   
        # This last one is if the Wn and Wp are assigned within process data lib file
        # for "default" setting
        pn_params = [{
            "Wn" : f"init_Wn_{inv_stage}",
            "Wp" : f"init_Wp_{inv_stage}",
        } for inv_stage in range(total_inv_stages)
        ]

    test_iteration_isnts = rg_utils.flatten_mixed_list([
        # For the first inst in the chain we need to manually define the input signal
        rg_ds.SpSubCktInst(
            name = "shape_inv",
            subckt = ic_3d_info.design_info.subckt_libs.basic_subckts["inv"],
            # if the param values aren't specified then the default values are used
            param_values = {
                **pn_params[0],
                "fanout" : "1",
            },
            conns = {
                "in" : "n_in", # TODO define this using a more global definition rather than hardcoding
                "vdd" : f"{ic_3d_info.process_data.global_nodes['vdd']}",
                "gnd" : f"{ic_3d_info.process_data.global_nodes['gnd']}",
            }
        ),
        [
            rg_ds.SpSubCktInst(
                name = f"inv_stage_{stage_num}",
                subckt = ic_3d_info.design_info.subckt_libs.basic_subckts["inv"],
                param_values = {
                    **pn_params[stage_num],
                    "fanout" : f"{buff_fanout**stage_num}",
                },
                conns = {
                    "vdd" : f"{ic_3d_info.process_data.global_nodes['vdd']}",
                    "gnd" : f"{ic_3d_info.process_data.global_nodes['gnd']}",
                }
            )
            for stage_num in range(1, num_stages + 1, 1)
        ],
        rg_ds.SpSubCktInst(
            name = f"ESD_load_top",
            subckt = ic_3d_info.design_info.subckt_libs.basic_subckts["wire"],
            param_values = ic_3d_info.design_info.package_info.esd_rc_params,
        ),
        rg_ds.SpSubCktInst(
            name = f"base_die_active_to_top_via_totem",
            subckt = ic_3d_info.design_info.subckt_libs.subckts["bottom_to_top_via_stack"],
        ),
        # Now we define the wire loads and ubumps which are connected to the last stage of the buffer chain
        rg_ds.SpSubCktInst(
            name = f"top_metal_layer_wire_load",
            subckt = ic_3d_info.design_info.subckt_libs.basic_subckts["wire"],
            param_values = routing_mlayer_params,
        ),
        rg_ds.SpSubCktInst(
            name = f"ubump_load_1",
            subckt = ic_3d_info.design_info.subckt_libs.basic_subckts["wire"],
            param_values = {
                "Rw" : f"{ic_3d_info.design_info.package_info.ubump_info.sp_params['res'].name}",
                "Cw" : f"{ic_3d_info.design_info.package_info.ubump_info.sp_params['cap'].name}",
            },
        ),
        rg_ds.SpSubCktInst(
            name = f"bot_metal_layer_wire_load",
            subckt = ic_3d_info.design_info.subckt_libs.basic_subckts["wire"],
            param_values = routing_mlayer_params,
        ),
        rg_ds.SpSubCktInst(
            name = f"top_die_to_active_via_totem",
            subckt = ic_3d_info.design_info.subckt_libs.subckts["bottom_to_top_via_stack"],
        ),
        rg_ds.SpSubCktInst(
            name = f"ESD_load_bot",
            subckt = ic_3d_info.design_info.subckt_libs.basic_subckts["wire"],
            param_values = ic_3d_info.design_info.package_info.esd_rc_params,
        ),
        # Now we connect to the inverter chain on the base die
        [
            rg_ds.SpSubCktInst(
                name = f"bottom_die_inv_{stage_num}",
                subckt = ic_3d_info.design_info.subckt_libs.basic_subckts["inv"],
                param_values = {
                    **pn_params[num_stages + 1 + stage_num],
                    "fanout" : f"{buff_fanout**stage_num}",
                },
                conns = {
                    "vdd" : f"{ic_3d_info.process_data.global_nodes['vdd']}",
                    "gnd" : f"{ic_3d_info.process_data.global_nodes['gnd']}", 
                }
            )
            for stage_num in range(ic_3d_info.design_info.bot_die_nstages)
        ]
    ])
    
    # manually assigning the last connection of last inst to output in spice sime:
    test_iteration_isnts[-1].conns["out"] = "n_out"
    test_iteration_isnts = direct_connect_insts(test_iteration_isnts)

    test_circuit_inst_lines = []
    for test_iteration_isnt in test_iteration_isnts:
        test_circuit_inst_lines.append(get_inst_line(test_iteration_isnt))

    return test_iteration_isnts, test_circuit_inst_lines



def get_opt_sim_setup_lines(ic_3d_info: rg_ds.Ic3d, sp_testing_model: rg_ds.SpTestingModel):
    """ Generates lines in the spice file to specify the inputs and type of analysis """
    # defining nodes used for sim inputs
    vdd_supply_node = "supply_v" #TODO Access through data structure
    dut_in_node = "n_in"
    gnd_node = "gnd"

    # target period in ns
    targ_period = 1/float(sp_testing_model.target_freq)*1e3
    sim_prec = 0.001*targ_period*1e3
    vsrc_args = {
        "type": "PULSE",
        "init_volt" : "0",
        "peak_volt" : f"{vdd_supply_node}", 
        "delay_time" : "0",
        "rise_time" : "0",
        "fall_time" : "0",
        "pulse_width" : f"{targ_period/2}n",
        "period" : f"{targ_period}n",
    }
    # sim time
    sim_time = targ_period * 1.05 # Added 5% to the sim duration to make sure crossings are captured
    opt_args = {
        "Wp" : {
            "init" : "2",
            "range" : [1,16],
            "step" : 1,
        },
        # Setting the Wn value to a constant such that the P/N sizing can be normalized and not just increasing drive strength of Tx
        "Wn" : {
            "init" : "1",
            "range" : [1,1],
            "step" : 0,
        },
        "iters" : 25,
    }

    inv_isnts_in_nodes = [inst.conns["in"] for inst in sp_testing_model.insts if inst.subckt.name == "inv"]
    inv_isnts_out_nodes = [inst.conns["out"] for inst in sp_testing_model.insts if inst.subckt.name == "inv"]

    sim_setup_lines = [
        # SWEEP DATA=sweep_data",
        f'.OPTIONS BRIEF', # POST LIST NODE INGOLD AUTOSTOP, # AUTOSTOP=1',
        "*** Input Signal",
        f"VIN {dut_in_node} {gnd_node} {vsrc_args['type']} ({vsrc_args['init_volt']} {vsrc_args['peak_volt']} {vsrc_args['delay_time']} {vsrc_args['rise_time']} {vsrc_args['fall_time']} {vsrc_args['pulse_width']} {vsrc_args['period']})",
        f'*** Opt setup ',
        *[f".param inv_Wp_{i} = optw({opt_args['Wp']['init']},{opt_args['Wp']['range'][0]},{opt_args['Wp']['range'][1]},{opt_args['Wp']['step']})" for i in range(len(inv_isnts_in_nodes))],
        *[f".param inv_Wn_{i} = optw({opt_args['Wn']['init']},{opt_args['Wn']['range'][0]},{opt_args['Wn']['range'][1]},{opt_args['Wn']['step']})" for i in range(len(inv_isnts_in_nodes))],
        
        # *[f".param inv_Wn_{i} = 4" for i in range(len(inv_isnts_in_nodes))],
        
        f".model optmod opt itropt={opt_args['iters']}",
        *[f".measure best_ratio_{i} param='inv_Wp_{i}/inv_Wn_{i}'" for i in range(len(inv_isnts_in_nodes))],
        
        f".TRAN {sim_prec}p {sim_time}n SWEEP OPTIMIZE=optw RESULTS=diff MODEL=optmod",
        # get_input_signal(vsrc_ports, vsrc_args),
        "*** Voltage source for device under test, this is used s.t. the power of the circuit can be measured without measring power of wave shaping and input load circuit",
        # f"V_DRIVER_SRC vdd_driver {gnd_node} {vdd_supply_node}", 
        *get_meas_lines_new(ic_3d_info, sp_testing_model),
        
        # f".measure tpd param='max(rising_prop_delay_{inv_isnts_in_nodes[1]}_{inv_isnts_out_nodes[-1]},falling_prop_delay_{inv_isnts_in_nodes[1]}_{inv_isnts_out_nodes[-1]})' goal = 0",
        # f".measure diff param='rising_prop_delay_{inv_isnts_in_nodes[1]}_{inv_isnts_out_nodes[-1]} - falling_prop_delay_{inv_isnts_in_nodes[1]}_{inv_isnts_out_nodes[-1]}' goal = 0",

        
        #f".measure tpd param='(rising_prop_delay + falling_prop_delay)/2' goal=0 * average prop delay",
        #f".measure diff param='rising_prop_delay-falling_prop_delay' goal = 0 * diff between delays",

    ]
    return sim_setup_lines


# def write_sp_sim(design_info: rg_ds.DesignInfo):
#     """
#         Inputs:
#             - design_info: DesignInfo object containing all the information about the design
#             - sim_type: string specifying the type of simulation to run, these could be .tran 
#     """



def write_pn_sizing_opt_sp_sim(ic_3d_info: rg_ds.Ic3d, num_stages: int, buff_fanout: int, targ_freq: int, add_wlen:int) -> List[rg_ds.SpSubCktInst]:
    """ Writes the spice file for evaluating a driver with a ubump and wireload """

    # Create simulation directory
    sim_dir = os.path.join(ic_3d_info.spice_info.sp_dir, ic_3d_info.spice_info.sp_sim_title)
    sp.run(["mkdir", "-p", f"{sim_dir}"])

    # sim_dir = sp_process.sp_dir
    # os.makedirs(sp_process.sp_dir, exist_ok=True)


    test_insts, insts_lines = get_buffer_sim_lines(ic_3d_info, num_stages, buff_fanout, add_wlen, pn_size_mode="find_opt")
    
    sp_testing_model = rg_ds.SpTestingModel(
        insts = test_insts,
        target_freq= targ_freq,
    )



    sp_sim_file_lines = [
        f'.TITLE {ic_3d_info.spice_info.sp_sim_title}_pn_opt',
        *get_subckt_hdr_lines("Include libraries, parameters and other"),
        f'.LIB "{ic_3d_info.spice_info.include_sp_file}" INCLUDES',
        *get_subckt_hdr_lines("Setup and input"),
        *get_opt_sim_setup_lines(ic_3d_info, sp_testing_model), 
        *insts_lines,
        '.END',
    ]
    with open(os.path.join(sim_dir,f"opt_pn_{ic_3d_info.spice_info.sp_sim_title}.sp"),"w") as fd:
        for l in sp_sim_file_lines:
            print(l,file=fd)
            # print(l)

def run_spice(ic_3d_info: rg_ds.Ic3d = None, sp_work_dir: str = None, sim_sp_files: list = None, sp_process: rg_ds.SpProcess = None) -> str:
    cwd = os.getcwd()
    if sp_process is None and ic_3d_info != None:
        os.chdir(os.path.join(ic_3d_info.spice_info.sp_dir, sp_work_dir))
        for sp_file in sim_sp_files:
            outfile = f"{os.path.splitext(sp_file)[0]}.lis"
            out_fd = open(outfile , "w")
            print(f"Running {os.path.join(ic_3d_info.spice_info.sp_dir,sp_work_dir,sp_file)}")
            sp.call(["hspice",os.path.join(ic_3d_info.spice_info.sp_dir,sp_work_dir,sp_file)], stdout=out_fd, stderr=out_fd)   
            out_fd.close()
    else:
        os.chdir(sp_process.sp_dir)
        outfile = f"{sp_process.sp_outfile}"
        out_fd = open(outfile,"w")
        print(f"Running {sp_process.sp_file}")
        sp.call(["hspice",sp_process.sp_file], stdout=out_fd, stderr=out_fd)
        out_fd.close()     
    os.chdir(cwd)
    return outfile



def parse_sp_output(ic_3d_info: rg_ds.Ic3d, parse_flags: dict, buff_fanout: int, n_stages: int, sp_outfile: str) -> Tuple[pd.DataFrame, dict, pd.DataFrame]:

    sp_run_info = {
        "buff_fanout" : buff_fanout,
        "n_stages" : n_stages,
        "total_max_prop_delay" : 0,
        "invs_info": [],
        "inv_chain_area" : 0,
    }
    total_num_invs = 1 + n_stages + ic_3d_info.design_info.bot_die_nstages

    """ Parses the spice output file and returns a dict with the results """
    ##################### NODE VOLTAGE GRABS #####################
    fd = open(sp_outfile,"r")
    sp_out_text = fd.read()
    fd.close()
    print_line_groups = ic_3d_info.res.sp_grab_print_vals_re.findall(sp_out_text)
    heading = ""
    dfs = []


    if parse_flags["voltage"]:
        for group in print_line_groups:
            data_lines = group.split('\n')[2:]
            data_lines = data_lines[:-2]
            header_0 = ic_3d_info.res.wspace_re.split(data_lines[0])  # Extract the column names
            header_1 = ic_3d_info.res.wspace_re.split(data_lines[1])
            header = [ key for key in [header_0[1]] + header_1 if key != ""]
            df = pd.read_csv(io.StringIO('\n'.join(data_lines)), delim_whitespace=True, skiprows=[0,1], header=None)
            df.columns = header
            # print(df.columns)
            df[["time"]] = df[["time"]].applymap(lambda x: convert_value(x[:-1], x[-1], ic_3d_info.sp_sim_settings.unit_lookups["time"]))
            # go through voltage keys
            for key in header[1:]:
                df[[key]] = df[[key]].applymap(lambda x: convert_value(x[:-1], x[-1], ic_3d_info.sp_sim_settings.unit_lookups["voltage"]))
            dfs.append(df)

    merged_df = reduce(lambda left, right: pd.merge(left , right, on="time"), dfs)

    # This will be a list of dicts containing info for each inverter
    # keys in var_keys will be searched for in the sp output .lis file
    # ["t_fall", "t_rise"]
    var_keys = ["rising_prop_delay", "falling_prop_delay", "max_prop_delay"] #,"area"]
    invs_info = [{} for _ in range(total_num_invs)]
    ##################### DELAY GRABS #####################
    with open(sp_outfile,"r") as fd:
        lines = fd.readlines()
    inv_idx = 0
    if parse_flags["delay"]:
        for l in lines:
            if "prop_delay" in l or "t_rise" in l or "t_fall" in l:
                # break
                match = ic_3d_info.res.sp_del_grab_info_re.search(l)
                meas_name = match.group('var1')
                meas_val = match.group('val1')
                meas_units = match.group('unit1')
                # print(l)
                # print(meas_name,meas_val,meas_units)
                if meas_name == "max_prop_delay":
                    sp_run_info["total_max_prop_delay"] = float(meas_val) * ic_3d_info.sp_sim_settings.unit_lookups["time"][meas_units]
                    continue

                if inv_idx < total_num_invs:
                    for var in var_keys:
                        if var in meas_name:
                            invs_info[inv_idx][var] = float(meas_val) * ic_3d_info.sp_sim_settings.unit_lookups["time"][meas_units]
                            break
                    if len(invs_info[inv_idx]) == len(var_keys):
                        inv_idx += 1 
                # elif "max_prop_delay" in meas_name:
                #     sp_run_info["total_max_prop_delay"] = float(meas_val) * sp_sim_settings.unit_lookups["time"][meas_units]
    


    sp_run_info["invs_info"] = invs_info
    ##################### PN OPT GRABS #####################
    match_iter = ic_3d_info.res.sp_grab_inv_pn_vals_re.finditer(sp_out_text)
    nfet_widths = [match.group('value') for match in match_iter if "wn" in str(match.group('name'))]
    match_iter = ic_3d_info.res.sp_grab_inv_pn_vals_re.finditer(sp_out_text)
    pfet_widths = [match.group('value') for match in match_iter if "wp" in str(match.group('name'))]    
    
    # inv_idx = 0
    # for p_w, n_w in zip(pfet_widths, nfet_widths):
    #     # print(f"Opt PN Sizes for inv_{inv_idx}: P:{p_w}, N:{n_w}")
    #     inv_idx += 1
    ##################### DF GENERATION #####################
    sp_sim_df = pd.DataFrame(sp_run_info["invs_info"])
    sp_sim_df["inv_idx"] = sp_sim_df.index
    if len(nfet_widths) > 0 and len(pfet_widths) > 0:
        sp_sim_df["nmos_width"] = [f"{wn}" for wn in nfet_widths]
        sp_sim_df["pmos_width"] = [f"{wp}" for wp in pfet_widths]
    # print("\n".join(df_output_lines(sp_sim_df)))

    # get area estimate
    # Going from the first inverter in buffer chain (1 as there is shape inv)
    # for i in range(1, total_num_invs):
    #     inv_area = tech_info.min_width_trans_area*(buff_fanout ** (i % n_stages))
    #     sp_run_info["inv_chain_area"] += inv_area
    #     invs_info[i]["area"] = inv_area
    # add area info to invs_info


    return merged_df, sp_run_info, sp_sim_df




def plot_sp_run(ic_3d_info: rg_ds.Ic3d, show_flags: dict, sp_run_info: dict, sp_run_df: pd.DataFrame) -> go.Figure:
    
    volt_def_unit = next(iter({k:v for k,v in ic_3d_info.sp_sim_settings.unit_lookups["voltage"].items() if v == 1}), None)
    time_def_unit = next(iter({k:v for k,v in ic_3d_info.sp_sim_settings.unit_lookups["time"].items() if v == 1}), None)

    fig = go.Figure()
    for col in sp_run_df.columns:
        if col != "time":
            fig.add_trace(go.Scatter(x=sp_run_df['time'], y=sp_run_df[col], name=col))

    fig.update_layout(
        title=f"Stage Ratio: {sp_run_info['buff_fanout']}, Num Stages: {sp_run_info['n_stages']} Inv Node Voltages vs Time",
        xaxis_title=f"Time ({time_def_unit}s)",
        yaxis_title=f"Voltage ({volt_def_unit}V)",
    )
    if show_flags["voltage"]:
        fig.show()
    fig.write_image("inv_node_voltages.png",format="png")
    
    colors = px.colors.sequential.Agsunset

    sp_delay_df = pd.DataFrame(sp_run_info['invs_info'])
    # print(sp_delay_df.head())
    sp_delay_df.index.name = 'idx'
    # total_del_bar_fig = go.Figure()
    # total_del_bar_fig.add_trace(go.Bar()
    #     name=f"Inv Chain Max Prop Delay",
    #     x=
    # )

    del_bar_fig = go.Figure()
    for col in sp_delay_df.columns:
        if "max_prop_delay" in col:
            for inv_idx in sp_delay_df.index:
                del_bar_fig.add_trace(go.Bar(
                    name=f"Inv Prop Delay {inv_idx}",
                    x=[sp_run_info["buff_fanout"] for _ in range(len(sp_delay_df.index))],
                    y=[sp_delay_df[col].values[inv_idx]],
                    offsetgroup=inv_idx,                    
                    legendgroup=sp_run_info["buff_fanout"],
                    marker=dict(color=colors[inv_idx*2 % len(colors)]),
                ))
            # fig2.add_trace(go.Bar(
            #     name=col,
            #     x=[sp_run_info["buff_fanout"] for _ in range(len(sp_delay_df.index))],
            #     y=sp_delay_df[col].values[inv_idx],
            #     offsetgroup=
            #     ))
    if show_flags["delay"]:
        del_bar_fig.show()
    # del_bar_fig.update_layout(
    #     title=f"Stage Ratio: {sp_run_info['buff_fanout']}, Num Stages: {sp_run_info['n_stages']} Max Prop Delay by Inv Stage",
    #     xaxis_title='Index',
    #     yaxis_title=f"Time ({time_def_unit}s)",
    #     barmode='group',
    #     bargroupgap=0.05,
    #     bargap=0.1
    # )

    # fig2.show()
    return del_bar_fig



def write_sp_buffer_updated(ic_3d_info: rg_ds.Ic3d, sweep_params: Dict[str, Any], title: str, inv_sizes: List[Dict[str, float]] = None) -> rg_ds.SpProcess:
    """
        Inputs: 
            - ic_3d_info: object containing high level information needed to write out files and interact w process / design parameters
            - process_package_params: dict containing parameters being swept for this particular buffer iteration
        Outputs:
            - Writes out a spice file for this buffer simulation, returns a SpProcess object to run that simulation
    """
    # Check for valid inv_sizes input
    if isinstance(inv_sizes, list) and len(inv_sizes) != ic_3d_info.design_info.total_nstages:
        raise ValueError(f"inv_sizes must be a list of dicts with length equal to the total number of stages in the buffer chain, {ic_3d_info.design_info.total_nstages}")

    sp_testing_model = buffer_sim_setup_updated(ic_3d_info, sweep_params, inv_sizes)

    sp_title = f"buffer-{title}-{rg_ds.create_timestamp()}"

    if ic_3d_info.common.override_outputs:
        obj_dir_path = rg_utils.find_newest_obj_dir(search_dir = ic_3d_info.spice_info.sp_dir, obj_dir_fmt = f"buffer-{title}-{rg_ds.create_timestamp(fmt_only_flag = True)}")
        if obj_dir_path != None:
            sp_title = os.path.basename(obj_dir_path)


    sp_sim_lines = [
        f".TITLE {sp_title}",
        *get_subckt_hdr_lines("Include libraries, parameters and other"),
        f'.LIB "{ic_3d_info.spice_info.include_sp_file}" INCLUDES',
        *get_subckt_hdr_lines("Setup and input"),
        *get_sim_setup_lines_updated(ic_3d_info, sp_testing_model),
        *get_meas_lines_new(ic_3d_info, sp_testing_model),
        *[get_inst_line(inst) for inst in sp_testing_model.insts],
        '.END',
    ]

    # Make workding dir if it doesnt exist
    work_dir = os.path.join(ic_3d_info.spice_info.sp_dir, sp_title)
    os.makedirs(work_dir, exist_ok=True)
    with open(os.path.join(work_dir,f"{sp_title}.sp"),"w") as fd:
        for l in sp_sim_lines:
            print(l,file=fd)

    # Make an SpProcess object so one can run this simulation
    sp_out_process = rg_ds.SpProcess(
        title = sp_title,
        top_sp_dir = ic_3d_info.spice_info.sp_dir, 
    )
    return sp_out_process


def buffer_sim_setup_updated(ic_3d_info: rg_ds.Ic3d, sweep_params: Dict[str, Any], inv_sizes: List[Dict[str, float]] = None) -> rg_ds.SpTestingModel:
    # inv_sizes is a list of dicts in the following format
    # [ 
    #   {
    #       "wn": float,
    #       "wp": float,  
    #   }
    # ... ]


    # Metal Distance for top metal layer for each die, assuming it has to travel half the distance of largest SRAM Macro + User defined additional wire length if any
    routing_mlayer_params = {
        "Rw" : f"'{ic_3d_info.design_info.process_info.mlayers[ic_3d_info.design_info.buffer_routing_mlayer_idx].sp_params['wire_res_per_um'].name}*({ic_3d_info.design_info.max_macro_dist} + {sweep_params['add_wlen']})'",
        "Cw" : f"'{ic_3d_info.design_info.process_info.mlayers[ic_3d_info.design_info.buffer_routing_mlayer_idx].sp_params['wire_cap_per_um'].name}*({ic_3d_info.design_info.max_macro_dist} + {sweep_params['add_wlen']})'",
    }

    opt_params = []
    static_params = []

    # if inv_sizes is provided then, they will always be used rather than creating opt params
    if inv_sizes == None:
        # Pmos parameter definitions
        if "P" in ic_3d_info.tx_sizing.opt_mode:
            wp_params = [ 
                rg_ds.SpParam(
                    name = f"{ic_3d_info.pn_opt_model.wp_param}_{i}",
                    opt_settings = rg_ds.SpOptSettings(
                        init = ic_3d_info.tx_sizing.p_opt_params["init"],
                        range = ic_3d_info.tx_sizing.p_opt_params["range"],
                        step = ic_3d_info.tx_sizing.p_opt_params["step"],
                    ),
                ) for i in range(ic_3d_info.design_info.total_nstages)
            ]
            opt_params += wp_params
        else:
            wp_params = [ rg_ds.SpParam(
                    name = f"{ic_3d_info.pn_opt_model.wp_param}_{i}",
                    value = ic_3d_info.tx_sizing.pmos_sz
                ) for i in range(ic_3d_info.design_info.total_nstages) 
            ]
            static_params += wp_params
        # Nmos parameter definitions
        if "N" in ic_3d_info.tx_sizing.opt_mode:
            wn_params = [ 
                rg_ds.SpParam(
                    name = f"{ic_3d_info.pn_opt_model.wn_param}_{i}",
                    opt_settings = rg_ds.SpOptSettings(
                        init = ic_3d_info.tx_sizing.n_opt_params["init"],
                        range = ic_3d_info.tx_sizing.n_opt_params["range"],
                        step = ic_3d_info.tx_sizing.n_opt_params["step"],
                    ),
                ) for i in range(ic_3d_info.design_info.total_nstages)
            ]
            opt_params += wn_params
        else:
            wn_params = [ rg_ds.SpParam(
                    name = f"{ic_3d_info.pn_opt_model.wn_param}_{i}",
                    value = ic_3d_info.tx_sizing.nmos_sz
                ) for i in range(ic_3d_info.design_info.total_nstages) 
            ] 
            static_params += wn_params
    else:
        # inv_sizes defined, meaning we want to assign specific values to transistors
        wn_params = [
            rg_ds.SpParam( 
                name = f"{ic_3d_info.pn_opt_model.wn_param}_{i}",
                value = inv_sizes[i]["wn"],
            ) for i in range(ic_3d_info.design_info.total_nstages)
        ]
        wp_params = [
            rg_ds.SpParam( 
                name = f"{ic_3d_info.pn_opt_model.wp_param}_{i}",
                value = inv_sizes[i]["wp"],
            ) for i in range(ic_3d_info.design_info.total_nstages)
        ]
        static_params += wn_params + wp_params

    local_sim_settings = rg_ds.SpLocalSimSettings(
        target_freq = sweep_params["target_freq"],
        # Create a voltage source for this simulation
        dut_in_vsrc = rg_ds.SpVoltageSrc(
            name = "IN",
            type = "PULSE",
            init_volt = "0",
            peak_volt = f"{ic_3d_info.sp_sim_settings.vdd_param}", 
            delay_time = "0",
            rise_time = "0",
            fall_time = "0",
            # These will be set in post init
            out_node = None, 
            pulse_width = None,
            period = None
        )
    )

    # Create a spice testing model object which has some of the intial values we require to instantiate the below circuits
    sp_testing_model = rg_ds.SpTestingModel(
        insts = None, 
        opt_params = opt_params,
        static_params = static_params,
        sim_settings = local_sim_settings
    )



    test_iteration_isnts = rg_utils.flatten_mixed_list([
        # For the first inst in the chain we need to manually define the input signal
        [
            rg_ds.SpSubCktInst(
                name = "shape_inv",
                subckt = ic_3d_info.design_info.subckt_libs.basic_subckts["inv"],
                # if the param values aren't specified then the default values are used
                param_values = {
                    "Wn" : f"{wn_params[stage_idx].name}",
                    "Wp" : f"{wp_params[stage_idx].name}",
                    "fanout" : f"{sweep_params['stage_ratio']**stage_idx}",
                },
                conns = {
                    "in" : "n_in", # TODO define this using a more global definition rather than hardcoding
                    "vdd" : f"{ic_3d_info.process_data.global_nodes['vdd']}",
                    "gnd" : f"{ic_3d_info.process_data.global_nodes['gnd']}",
                }
            ) for stage_idx in range(ic_3d_info.design_info.shape_nstages)
        ],
        [
            rg_ds.SpSubCktInst(
                name = f"dut_inv_stage_{stage_idx}",
                subckt = ic_3d_info.design_info.subckt_libs.basic_subckts["inv"],
                param_values = {
                    "Wn" : f"{wn_params[stage_idx].name}",
                    "Wp" : f"{wp_params[stage_idx].name}",
                    "fanout" : f"{sweep_params['stage_ratio']**stage_idx}",
                },
                conns = {
                    "vdd" : f"{ic_3d_info.process_data.global_nodes['vdd']}",
                    "gnd" : f"{ic_3d_info.process_data.global_nodes['gnd']}",
                }
            )
            for stage_idx in range(ic_3d_info.design_info.shape_nstages, ic_3d_info.design_info.dut_buffer_nstages + ic_3d_info.design_info.shape_nstages, 1)
        ],
        rg_ds.SpSubCktInst(
            name = f"ESD_load_top",
            subckt = ic_3d_info.design_info.subckt_libs.basic_subckts["wire"],
            param_values = ic_3d_info.design_info.package_info.esd_rc_params,
        ),
        rg_ds.SpSubCktInst(
            name = f"base_die_active_to_top_via_totem",
            subckt = ic_3d_info.design_info.subckt_libs.subckts["bottom_to_top_via_stack"],
        ),
        # Now we define the wire loads and ubumps which are connected to the last stage of the buffer chain
        rg_ds.SpSubCktInst(
            name = f"top_metal_layer_wire_load",
            subckt = ic_3d_info.design_info.subckt_libs.basic_subckts["wire"],
            param_values = routing_mlayer_params,
        ),
        rg_ds.SpSubCktInst(
            name = f"ubump_load_1",
            subckt = ic_3d_info.design_info.subckt_libs.basic_subckts["wire"],
            param_values = {
                "Rw" : f"{ic_3d_info.design_info.package_info.ubump_info.sp_params['res'].name}",
                "Cw" : f"{ic_3d_info.design_info.package_info.ubump_info.sp_params['cap'].name}",
            },
        ),
        rg_ds.SpSubCktInst(
            name = f"bot_metal_layer_wire_load",
            subckt = ic_3d_info.design_info.subckt_libs.basic_subckts["wire"],
            param_values = routing_mlayer_params,
        ),
        rg_ds.SpSubCktInst(
            name = f"top_die_to_active_via_totem",
            subckt = ic_3d_info.design_info.subckt_libs.subckts["bottom_to_top_via_stack"],
        ),
        rg_ds.SpSubCktInst(
            name = f"ESD_load_bot",
            subckt = ic_3d_info.design_info.subckt_libs.basic_subckts["wire"],
            param_values = ic_3d_info.design_info.package_info.esd_rc_params,
        ),
        # Now we connect to the inverter chain on the base die
        [
            rg_ds.SpSubCktInst(
                name = f"bottom_die_inv_{stage_idx}",
                subckt = ic_3d_info.design_info.subckt_libs.basic_subckts["inv"],
                param_values = {
                    "Wn": f"{wn_params[ic_3d_info.design_info.shape_nstages + ic_3d_info.design_info.dut_buffer_nstages + stage_idx].name}", 
                    "Wp": f"{wp_params[ic_3d_info.design_info.shape_nstages + ic_3d_info.design_info.dut_buffer_nstages + stage_idx].name}",
                    "fanout" : f"{sweep_params['stage_ratio']**stage_idx}",
                },
                conns = {
                    "vdd" : f"{ic_3d_info.process_data.global_nodes['vdd']}",
                    "gnd" : f"{ic_3d_info.process_data.global_nodes['gnd']}", 
                }
            )
            for stage_idx in range(ic_3d_info.design_info.sink_die_nstages)
        ]
    ])
    
    # manually assigning the last connection of last inst to output in spice sime:
    test_iteration_isnts[-1].conns["out"] = sp_testing_model.dut_out_node
    # Connect all of the instantiations Ex. out node for inst[0] is "in" node for inst[1]
    test_iteration_isnts = direct_connect_insts(test_iteration_isnts)

    sp_testing_model.insts = test_iteration_isnts
    
    # test_circuit_inst_lines = []
    # for test_iteration_isnt in test_iteration_isnts:
    #     test_circuit_inst_lines.append(get_inst_line(test_iteration_isnt))

    return sp_testing_model


def get_sim_setup_lines_updated(ic_3d_info: rg_ds.Ic3d, sp_testing_model: rg_ds.SpTestingModel) -> List[str]:
    """ Generates lines in the spice file to specify the inputs and type of analysis """

    # Just to shorten the way we access this struct
    dut_in_vsrc = sp_testing_model.sim_settings.dut_in_vsrc


    # TODO define these static params in the sp_testing_model initialization
    # if "P" in ic_3d_info.tx_sizing.opt_mode and "N" not in ic_3d_info.tx_sizing.opt_mode:
    #     ratio_meas_lines = [f".MEASURE best_ratio_{i} param='{ic_3d_info.pn_opt_model.wp_param}_{i}/{ic_3d_info.pn_opt_model.wn_param}'" for i in range(ic_3d_info.design_info.total_nstages)]
    # elif "N" in ic_3d_info.tx_sizing.opt_mode and "P" not in ic_3d_info.tx_sizing.opt_mode:
    #     ratio_meas_lines = [f".MEASURE best_ratio_{i} param='{ic_3d_info.pn_opt_model.wp_param}/{ic_3d_info.pn_opt_model.wn_param}_{i}'" for i in range(ic_3d_info.design_info.total_nstages)]
    # elif "N" in ic_3d_info.tx_sizing.opt_mode and "P" in ic_3d_info.tx_sizing.opt_mode:
    #     ratio_meas_lines = [f".MEASURE best_ratio_{i} param='{ic_3d_info.pn_opt_model.wp_param}_{i}/{ic_3d_info.pn_opt_model.wn_param}_{i}'" for i in range(ic_3d_info.design_info.total_nstages)]
    # else:
    #     # best and only ratio
    #     ratio_meas_lines = [f".MEASURE best_ratio param='{ic_3d_info.pn_opt_model.wp_param}/{ic_3d_info.pn_opt_model.wn_param}'" ]



    static_param_setup_lines = [
        "*** Static Param Setup",
        *[f".PARAM {static_param.name} = {static_param.value}" for static_param in sp_testing_model.static_params],
    ]
    # param_setup_lines = [
    #     "*** Param Setup",
    #     f".PARAM {ic_3d_info.pn_opt_model.wn_param} = {ic_3d_info.tx_sizing.nmos_sz}",
    #     f".PARAM {ic_3d_info.pn_opt_model.wp_param} = {ic_3d_info.tx_sizing.pmos_sz}",
    # ]




    opt_setup_lines = [
        "*** Opt setup ",
        # Assign opt params 
        *[f".PARAM {opt_param.name} = optw( {opt_param.opt_settings.init}, {opt_param.opt_settings.range[0]}, {opt_param.opt_settings.range[1]}, {opt_param.opt_settings.step} )" for opt_param in sp_testing_model.opt_params],
        f".MODEL optmod opt itropt={ic_3d_info.tx_sizing.iters}", # set up optimization model
        *[f".MEASURE best_ratio_{i} param='{ic_3d_info.pn_opt_model.wp_param}_{i}/{ic_3d_info.pn_opt_model.wn_param}_{i}'" for i in range(ic_3d_info.design_info.total_nstages)],
    ]

    analysis_lines = [ f".TRAN {sp_testing_model.sim_settings.sim_prec}p {sp_testing_model.sim_settings.sim_time}n" ]
    if sp_testing_model.opt_params is not None and len(sp_testing_model.opt_params) > 0:
        analysis_lines[0] += f" SWEEP OPTIMIZE=optw RESULTS={ic_3d_info.tx_sizing.opt_goal} MODEL=optmod"
        analysis_lines = opt_setup_lines + analysis_lines

    sim_setup_lines = [
        f"*** Hspice Options",
        f".OPTIONS " + " ".join([f"{k}={v}" for k,v in ic_3d_info.sp_sim_settings.sp_options.items()]),
        "*** Input Signal",
        f"V{dut_in_vsrc.name} {sp_testing_model.dut_in_node} {ic_3d_info.sp_sim_settings.gnd_node} {dut_in_vsrc.type} " +\
            f"({dut_in_vsrc.init_volt} {dut_in_vsrc.peak_volt} {dut_in_vsrc.delay_time} " +\
            f"{dut_in_vsrc.rise_time} {dut_in_vsrc.fall_time} {dut_in_vsrc.pulse_width} {dut_in_vsrc.period})",
        "*** Voltage source for device under test, this is used s.t. the power of the circuit can be measured without measring power of wave shaping and input load circuit",
        # Create a voltage source for each inverter index to get current for each of them
        # TODO return this V_DRIVER_<idx>_SRC names somewhere so we can use it to generate measure statements
        *[f"V_DRIVER_{inv_idx}_SRC vdd_driver_{inv_idx} {ic_3d_info.sp_sim_settings.gnd_node} {ic_3d_info.sp_sim_settings.vdd_param}" for inv_idx in range(ic_3d_info.design_info.total_nstages)],
        *static_param_setup_lines,
        *analysis_lines,
    ]

    ## TODO figure out why this causes the simulation to fail,
    ## replacing the vdd connections with v_driver causes strange behavior, but is required for power measurements
    ## Connect newly defined voltage sources to each instantiation
    # for idx, inst in enumerate(sp_testing_model.insts):
    #     inst.conns["vdd"] = f"vdd_driver_{idx}"
    
    return sim_setup_lines

def get_sim_setup_lines(ic_3d_info: rg_ds.Ic3d, num_stages: int, sp_testing_model: rg_ds.SpTestingModel) -> List[str]:
    """ Generates lines in the spice file to specify the inputs and type of analysis """
    # defining nodes used for sim inputs
    vdd_supply_node = "supply_v" #TODO Access through data structure
    gnd_node = "gnd"
    dut_in_node = "n_in"

    # target period in ns
    targ_period = 1/float(sp_testing_model.target_freq)*1e3
    sim_prec = 0.001*targ_period*1e3
    vsrc_args = {
        "type": "PULSE",
        "init_volt" : "0",
        "peak_volt" : f"{vdd_supply_node}", 
        "delay_time" : "0",
        "rise_time" : "0",
        "fall_time" : "0",
        "pulse_width" : f"{targ_period/2}n",
        "period" : f"{targ_period}n",
    }
    sim_length = targ_period + 1 # Added a litte to the sim duration to make sure crossings are captured
    total_num_stages = 1 + num_stages + ic_3d_info.design_info.bot_die_nstages
    sim_setup_lines = [
        f".TRAN {sim_prec}p {sim_length}n",
        # SWEEP DATA=sweep_data",
        f'.OPTIONS BRIEF=1',
        "*** Input Signal",
        f"VIN {dut_in_node} {gnd_node} {vsrc_args['type']} ({vsrc_args['init_volt']} {vsrc_args['peak_volt']} {vsrc_args['delay_time']} {vsrc_args['rise_time']} {vsrc_args['fall_time']} {vsrc_args['pulse_width']} {vsrc_args['period']})",
        "*** Voltage source for device under test, this is used s.t. the power of the circuit can be measured without measring power of wave shaping and input load circuit",
        # Create a voltage source for each inverter index to get current for each of them
        *[f"V_DRIVER_{inv_idx}_SRC vdd_driver_{inv_idx} {gnd_node} {vdd_supply_node}" for inv_idx in range(1,total_num_stages,1)], 
        *get_meas_lines_new(ic_3d_info, sp_testing_model),
    ]

    return sim_setup_lines
    

def write_loaded_driver_sp_sim(ic_3d_info: rg_ds.Ic3d, num_stages: int, buff_fanout: int, targ_freq: int, add_wlen: int, in_sp_sim_df: pd.DataFrame = None) -> None:
    """ Writes the spice file for evaluating a driver with a ubump and wireload """

    sim_dir = os.path.join(ic_3d_info.spice_info.sp_dir, ic_3d_info.spice_info.sp_sim_title)
    sp.run(["mkdir", "-p", f"{sim_dir}"])
    # num_mlayers = tech_info.num_mlayers

    if in_sp_sim_df is not None:
        test_insts, insts_lines = get_buffer_sim_lines(ic_3d_info, num_stages, buff_fanout, add_wlen, pn_size_mode="assign_opt", in_sp_sim_df=in_sp_sim_df)

    
    sp_testing_model = rg_ds.SpTestingModel(
        insts = test_insts,
        target_freq= targ_freq,
    )

    sp_sim_file_lines = [
        f'.TITLE {ic_3d_info.spice_info.sp_sim_title}',
        *get_subckt_hdr_lines("Include libraries, parameters and other"),
        f'.LIB "{ic_3d_info.spice_info.include_sp_file}" INCLUDES',
        *get_subckt_hdr_lines("Setup and input"),
        *get_sim_setup_lines(ic_3d_info, num_stages, sp_testing_model), 
        *insts_lines,
        '.END',
    ]
    # for l in sp_sim_file_lines:
    #     print(l)
    with open(os.path.join(sim_dir,f"{ic_3d_info.spice_info.sp_sim_title}.sp"),"w") as fd:
        for l in sp_sim_file_lines:
            print(l,file=fd)


# From https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber=9221557
def finfet_tx_area_model(num_fins: int) -> float: #nm^2
    """ Returns the area of a finfet transistor in nm^2 """
    return 0.3694 + 0.0978 * num_fins + 0.5368 * math.sqrt(num_fins)


def calc_cost(design_info: rg_ds.DesignInfo, cost_fx_exps: dict, sp_run_info: dict) -> float:
    # TODO check out this cost function (not being used to make important decisions rn as flow is brute forced)
    # prop delay in ps (1000ps is 1 unit of delay cost), area normalized to almost average sized buffer chain (5 tx sizes) (1 unit of area cost)
    delay_cost_unit = 100 #ps
    area_cost_unit = 2 * 2 * finfet_tx_area_model(3) * design_info.process_info.tx_geom_info.min_width_tx_area * 1e-6 # minimum area inverter * 2 stages * 2 stage ratio
    # TODO change the normalization factors on each term to be the geometric mean of a previous run (which will be saved somewhere)
    return ((sp_run_info["total_max_prop_delay"] / delay_cost_unit) ** cost_fx_exps["delay"] ) + ( (sp_run_info["inv_chain_area"] / area_cost_unit) ** (cost_fx_exps["area"]))

def calc_cost_updated(design_info: rg_ds.DesignInfo, cost_fx_exps: dict, circuit_info: dict) -> float:
    # TODO check out this cost function (not being used to make important decisions rn as flow is brute forced)
    # prop delay in ps (1000ps is 1 unit of delay cost), area normalized to almost average sized buffer chain (5 tx sizes) (1 unit of area cost)
    delay_cost_unit = 100 #ps
    area_cost_unit = 2 * 2 * finfet_tx_area_model(3) * design_info.process_info.tx_geom_info.min_width_tx_area * 1e-6 # minimum area inverter * 2 stages * 2 stage ratio
    # TODO change the normalization factors on each term to be the geometric mean of a previous run (which will be saved somewhere)
    return ((circuit_info["max_prop_delay"] / delay_cost_unit) ** cost_fx_exps["delay"] ) + ( (circuit_info["area"] / area_cost_unit) ** (cost_fx_exps["area"]))



def buffer_sim_setup(ic_3d_info: rg_ds.Ic3d, process_package_params: dict) -> Tuple[List[str], rg_ds.SpTestingModel]:
    
    sp_testing_model = rg_ds.SpTestingModel(
        insts = [],
        target_freq = (1 / (process_package_params["sim_params"]["period"]))*1e3,
    )

    # Shape Inverter + Num Stages + Inverter on bottom die
    total_inv_stages = 1 + process_package_params["buffer_params"]["num_stages"] + ic_3d_info.design_info.bot_die_nstages  
    mlayer_idx = process_package_params["load_params"]["mlayer_idx"]
    via_factor = process_package_params["load_params"]["via_factor"]
    ubump_factor = process_package_params["load_params"]["via_factor"]
    mlayer_dist = process_package_params["load_params"]["mlayer_dist"]

    # Set Pn Param values
    pn_params = [
        {
            "Wp" : process_package_params["buffer_params"]["pn_ratios"][i]["wn"],
            "Wn" : process_package_params["buffer_params"]["pn_ratios"][i]["wp"],
        } for i in range(len(process_package_params["buffer_params"]["pn_ratios"]))
    ]

    sim_insts = rg_utils.flatten_mixed_list([
        # For the first inst in the chain we need to manually define the input signal
        rg_ds.SpSubCktInst(
            name = "shape_inv",
            subckt = ic_3d_info.design_info.subckt_libs.basic_subckts["inv"],
            # if the param values aren't specified then the default values are used
            param_values = {
                **pn_params[0],
                "fanout" : "1",
            },
            conns = {
                "in" : "n_in", # TODO define this using a more global definition rather than hardcoding
                "vdd" : f"{ic_3d_info.process_data.global_nodes['vdd']}",
                "gnd" : f"{ic_3d_info.process_data.global_nodes['gnd']}",
            }
        ),
        [
            rg_ds.SpSubCktInst(
                name = f"inv_stage_{stage_num}",
                subckt = ic_3d_info.design_info.subckt_libs.basic_subckts["inv"],
                param_values = {
                    **pn_params[stage_num],
                    "fanout" : f"{process_package_params['buffer_params']['stage_ratio'] ** stage_num}",
                },
                conns = {
                    "vdd" : f"{ic_3d_info.process_data.global_nodes['vdd']}",
                    "gnd" : f"{ic_3d_info.process_data.global_nodes['gnd']}",
                }
            )
            for stage_num in range(1, process_package_params["buffer_params"]["num_stages"] + 1, 1)
        ],
        [
            rg_ds.SpSubCktInst(
                name = f"base_die_active_to_top_via_totem_{i}",
                subckt = ic_3d_info.design_info.subckt_libs.subckts["bottom_to_top_via_stack"],
            ) for i in range(via_factor)
        ],
        # Now we define the wire loads and ubumps which are connected to the last stage of the buffer chain
        rg_ds.SpSubCktInst(
            name = f"top_metal_layer_wire_load",
            subckt = ic_3d_info.design_info.subckt_libs.basic_subckts["wire"],
            param_values = {
                "Rw" : f"{ic_3d_info.design_info.process_info.mlayers[mlayer_idx].sp_params['wire_res_per_um'].name}*{mlayer_dist}",
                "Cw" : f"{ic_3d_info.design_info.process_info.mlayers[mlayer_idx].sp_params['wire_cap_per_um'].name}*{mlayer_dist}",
            },
        ),
        rg_ds.SpSubCktInst(
            name = f"ubump_load_1",
            subckt = ic_3d_info.design_info.subckt_libs.basic_subckts["wire"],
            param_values = {
                "Rw" : f"{ic_3d_info.design_info.package_info.ubump_info.sp_params['res'].name}*{ubump_factor}",
                "Cw" : f"{ic_3d_info.design_info.package_info.ubump_info.sp_params['cap'].name}*{ubump_factor}",
            },
        ),
        [
            rg_ds.SpSubCktInst(
                name = f"top_die_to_active_via_totem_{i}",
                subckt = ic_3d_info.design_info.subckt_libs.subckts["bottom_to_top_via_stack"],
            ) for i in range(via_factor)
        ],
        rg_ds.SpSubCktInst(
            name = f"bot_metal_layer_wire_load",
            subckt = ic_3d_info.design_info.subckt_libs.basic_subckts["wire"],
            param_values = {
                "Rw" : f"{ic_3d_info.design_info.process_info.mlayers[mlayer_idx].sp_params['wire_res_per_um'].name}*{mlayer_dist}",
                "Cw" : f"{ic_3d_info.design_info.process_info.mlayers[mlayer_idx].sp_params['wire_cap_per_um'].name}*{mlayer_dist}",
            },
        ),
        # Now we connect to the inverter chain on the base die
        [
            rg_ds.SpSubCktInst(
                name = f"bottom_die_inv_{stage_num}",
                subckt = ic_3d_info.design_info.subckt_libs.basic_subckts["inv"],
                param_values = {
                    **pn_params[process_package_params["buffer_params"]["num_stages"] + 1 + stage_num],
                    "fanout" : f"{process_package_params['buffer_params']['stage_ratio']**stage_num}",
                },
                conns = {
                    "vdd" : f"{ic_3d_info.process_data.global_nodes['vdd']}",
                    "gnd" : f"{ic_3d_info.process_data.global_nodes['gnd']}", 
                }
            )
            for stage_num in range(ic_3d_info.design_info.bot_die_nstages)
        ]
    ])


    # manually assigning the last connection of last inst to output in spice sime:
    sim_insts[-1].conns["out"] = "n_out"
    sim_insts = direct_connect_insts(sim_insts)

    sim_inst_lines  = []
    for sim_inst in sim_insts:
        sim_inst_lines.append(get_inst_line(sim_inst))

    sp_testing_model.insts = sim_insts

    return sim_inst_lines, sp_testing_model


def write_sp_process_package_dse(ic_3d_info: rg_ds.Ic3d, process_package_params: dict) -> None:

    sim_inst_lines, sp_testing_model = buffer_sim_setup(ic_3d_info, process_package_params)

    sp_sim_lines = [
        *get_subckt_hdr_lines(f"Sensitivity Study for Process {ic_3d_info.design_info.process_info.name} and Ubump Sweep"),
        f".TITLE sensitivity_study",
        *get_subckt_hdr_lines("Include libraries, parameters and other"),
        f'.LIB "{ic_3d_info.spice_info.include_sp_file}" INCLUDES',
        *get_subckt_hdr_lines("Setup and input"),
        *get_sim_setup_lines(ic_3d_info, process_package_params["buffer_params"]["num_stages"], sp_testing_model),
        *sim_inst_lines,
        '.END',
    ]

    with open(ic_3d_info.spice_info.process_package_dse.sp_file,"w") as fd:
        for l in sp_sim_lines:
            print(l,file=fd)


def sens_study_run(ic_3d_info: rg_ds.Ic3d, process_package_params: dict, metal_dist: int, mlayer_idx: int, via_fac: int, ubump_fac: int):
    ####################### SETUP FOR SWEEPING DSE #######################
    load_params = { 
        "mlayer_dist": metal_dist,
        "mlayer_idx": mlayer_idx,
        "via_factor": via_fac,
        "ubump_factor": ubump_fac,
    }
    process_package_params["load_params"] = load_params
    # Make sure mlayer idx is valid
    assert abs(process_package_params["load_params"]["mlayer_idx"]) < len(ic_3d_info.design_info.process_info.mlayers)
    assert len(process_package_params["buffer_params"]["pn_ratios"]) == 1 + process_package_params["buffer_params"]["num_stages"] + ic_3d_info.design_info.bot_die_nstages
    sim_success = False
    print(f"Running sim with params: {load_params}")
    while not sim_success:
        ####################### SETUP FOR SWEEPING DSE #######################
        write_sp_process_package_dse(ic_3d_info, process_package_params)
        run_spice(ic_3d_info, sp_process = ic_3d_info.spice_info.process_package_dse)
        ####################### PARSE SPICE RESULTS #######################
        parse_flags = {
            "voltage": True,
            "delay": True,
        }
        show_flags = {
            "voltage": False,
            "delay": True,
        }
        try:
            sp_run_df, sp_run_info, sp_sim_df = parse_sp_output(
                ic_3d_info,
                parse_flags, 
                process_package_params["buffer_params"]["num_stages"],
                process_package_params["buffer_params"]["stage_ratio"],
                ic_3d_info.spice_info.process_package_dse.sp_outfile,
            )
        except:
            process_package_params["sim_params"]["period"] *= 2
            continue

        result_dict = {}
        result_dict["max_total_delay"] = sp_run_info["total_max_prop_delay"]
        result_dict = {**result_dict, **load_params}

        if result_dict["mlayer_idx"] == -1: 
            result_dict["mlayer_idx"] = f"M{len(ic_3d_info.design_info.process_info.mlayers)-1}"
        else:
            result_dict["mlayer_idx"] = "M" + str(result_dict["mlayer_idx"])

        sim_success = True


    return result_dict



def unit_conversion(unit: str, val: float, unit_lookup: Dict[str, float], sig_figs: int = None) -> float:
    """
        Converts a value from one unit to another using a unit lookup dict
        Assumptions:
            - val will should not be in a unit, ie should always be in seconds not mS or pS etc
        Inputs:
            - unit str ex. "m", "p" ... (all definitions defined in SpGlobalSettings at the moment)
        Outputs:
            - converted value in new unit
        Example:
            - unit = "m", val = "1.32e-6 seconds" -> "1.32e-3 milliseconds"
    """
    try: 
        if sig_figs != None:
            ret_val = round(float(val) / unit_lookup[unit], sig_figs)
        else:
            ret_val = float(val) / unit_lookup[unit]
    except:
        ret_val = val
    return ret_val


def parse_spice(res: rg_ds.Regexes, sp_process: rg_ds.SpProcess, parse_flags: Dict[str, bool] = None) -> Tuple[ pd.DataFrame, Dict[str, str], Dict[str, str], Dict[str, List[Dict[int, float]]] ]:
    """
        Parses spice output ".lis" file

        Assumptions:
            - Spice performed transient analysis
        Inputs:
            - sp_process: spice process object which gives us our output file to parse
            - parse_flags: dict of bools which specify what to parse from the spice output file
        Outputs:
            - plot_df: dataframe of the plotting data, this is created in spice by a .PRINT statement
            - measurements: list of dicts containing the measurement statement names, values, & triggers

    """
    plot_df = None # get from "plot" flag
    measurements = []
    opt_params = []
    gen_params: Dict[List[Dict[int, float]]] = {}

    if parse_flags is None:
        parse_flags = {
            "plot": True,
            "measure": True,
            "opt": True,
            "gen_params" : True,
        }

    with open(sp_process.sp_outfile,"r") as lis_fd:
        lis_text = lis_fd.read()

    # grab_tr_analysis_re_pattern = f"{res.sp_grab_tran_analysis_ub_str}{sp_process.title}"
    # grab_tr_analysis_re = re.compile(grab_tr_analysis_re_pattern, re.DOTALL)
    tr_analysis_texts = res.sp_grab_tran_analysis_re.findall(lis_text)
    # Each tran analysis should be bordered by the above regex
    for tr_analysis_text in tr_analysis_texts:
        measure_text = tr_analysis_text
        # no groupds so findall returns strs
        if parse_flags.get("plot"):
            # Assumes tran analysis ie a "time" feild
            dfs = []
            plotting_print_texts = res.sp_grab_print_vals_re.findall(tr_analysis_text)
            for idx, plot_text in enumerate(plotting_print_texts):
                # filter out the plotting text, only relevant for measurement parsing
                measure_text = measure_text.replace(plot_text, "")
                
                # parse plotting texts
                # removes leading and trailing blank lines text to get data lines
                data_lines = plot_text.split("\n")[2:]
                data_lines = data_lines[:-2]
                # Extract the column names, should always be only 2 rows even if more than 2 rows worth of plotting data
                header_0 = res.wspace_re.split(data_lines[0])
                header_1 = res.wspace_re.split(data_lines[1])
                # Maybe TODO make it so the field of individual plot columns are captured, the below line assumes they are all the same (maybe thats ok)
                header = [ key for key in [header_0[1]] + header_1 if key != ""]
                df = pd.read_csv(io.StringIO('\n'.join(data_lines)), delim_whitespace=True, skiprows=[0,1], header=None)
                df.columns = header
                dfs.append(df)
            if len(dfs) > 0:
                plot_df = reduce(lambda left, right: pd.merge(left , right, on="time"), dfs)

        if parse_flags.get("measure"):
            # measurement statement parsing
            line_number_skip_list = [0]
            for idx, line in enumerate(measure_text.split("\n")):
                if idx in line_number_skip_list:
                    continue
                meas_dict = {
                    "name": None, # measure statement name
                    "val": None, # measure statement value
                }
                line_meas_matches = res.sp_grab_measure_re.findall(line)
                if len(line_meas_matches) > 0:
                    meas_dict["name"] = line_meas_matches[0][0]
                    meas_dict["val"] = line_meas_matches[0][1]
                    # Assumes triggers exist in same line as associated measure statement, 
                    for i in range(len(line_meas_matches) - 1):
                        meas_dict[line_meas_matches[i+1][0]] = line_meas_matches[i+1][1]
                    measurements.append(meas_dict)
        if parse_flags.get("opt"):
            # Think this regex is pretty safe so were gonna just use the raw text of the whole thing
            opt_matches = res.sp_grab_param_re.findall(lis_text)
            for match in opt_matches:
                # unpack match (contains 2 groups)
                name, val = match
                opt_dict = {
                    "name": name, # opt param name
                    "val": val, # opt param value
                }
                opt_params.append(opt_dict)
        if parse_flags.get("gen_params"):
            param_matches = res.sp_coffe_grab_params_re.findall(lis_text)
            for match in param_matches:
                # unpack match (contains 3 groups)
                param_id, name, val = match
                # print(param_id, name)
                if not gen_params.get(name):
                    gen_params[name] = [{param_id : val}]
                elif isinstance(gen_params.get(name), list):
                    gen_params[name].append({f"{param_id}": val})
                else:
                    raise ValueError(f"params[{name}] is undefined as a list")



        # Now we use the captured parameters


        return plot_df, measurements, opt_params, gen_params


def plot_time_vs_voltage(sp_sim_settings: rg_ds.SpGlobalSimSettings, plot_df: pd.DataFrame):
    # Unit conversion
    plot_df["time"] = unit_conversion(sp_sim_settings.unit_lookup_factors["time"], plot_df["time"], sp_sim_settings.abs_unit_lookups )
    for key in plot_df.columns[1:]:
        plot_df[key] = unit_conversion(sp_sim_settings.unit_lookup_factors["voltage"], plot_df[key], sp_sim_settings.abs_unit_lookups )
    
    fig = go.Figure()

    # Add traces for each element being plotted
    for col in plot_df.columns:
        if col != "time":
            fig.add_trace(go.Scatter(x=plot_df["time"], y=plot_df[col], name=col))

    # This will be invalid if the user wants to look at something other than voltage
    fig.update_layout(
        title=f"Time vs Voltage",
        xaxis_title=f"Time ({sp_sim_settings.unit_lookup_factors['time']}s)", 
        yaxis_title=f"Voltage ({sp_sim_settings.unit_lookup_factors['voltage']}V)",
    )
    fig.show()