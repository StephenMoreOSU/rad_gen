import os, sys
import subprocess as sp
from dataclasses import dataclass, field
from typing import Dict, Tuple, List

# from buffer_dse_structs import *

import plotly.graph_objects as go
import plotly.subplots as subplots
import plotly.express as px

import shapely as sh
# from shapely.geometry.mapping import to_shape

from itertools import combinations
# import matplotlib.pyplot as plt

from functools import reduce

import io
import pandas as pd

import argparse

import numpy as np

import math

import yaml

from decimal import Decimal

from src.ic_3d.buffer_dse_structs import *
# import src.ic_3d.buffer_dse_structs as buffer_dse_structs

import src.ic_3d.pdn_modeling as pdn

import csv

#################### GENERAL UTILS ####################
def create_bordered_lines(text: str = "", border_char: str = "#", total_len: int = 150) -> list:
    text = f"  {text}  "
    text_len = len(text)
    if(text_len > total_len):
        total_len = text_len + 10 
    border_size = (total_len - text_len) // 2
    return [ border_char * total_len, f"{border_char * border_size}{text}{border_char * border_size}", border_char * total_len]

def get_df_output_lines(df: pd.DataFrame) -> List[str]:
    cell_chars = 40
    ncols = len(df.columns)
    seperator = "+".join(["-"*cell_chars]*ncols)
    format_str = f"{{:^{cell_chars}}}"
    df_output_lines = [
        seperator,
        "|".join([format_str for _ in range(len(df.columns))]).format(*df.columns),
        seperator,
        *["|".join([format_str for _ in range(len(df.columns))]).format(*row.values) for _, row in df.iterrows()],
        seperator,
    ]
    return df_output_lines


# From https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber=9221557
def finfet_tx_area_model(num_fins: int) -> float: #nm^2
    """ Returns the area of a finfet transistor in nm^2 """
    return 0.3694 + 0.0978 * num_fins + 0.5368 * math.sqrt(num_fins)
#################### GENERAL UTILS ####################



####### SPICE SUBCKT GENERATION STRUCT #######


def get_subckt_hdr_lines(subckt_def_str: str) -> list:
    hdr_len = 91
    hdr_buff = "*" * hdr_len
    hdr_lines = [hdr_buff, "* " + subckt_def_str, hdr_buff]
    return hdr_lines

def get_subckt_ports(subckt_name: str, ports: list, params: dict) -> str:
    param_strs = [f"{param}={val}" for param, val in params.items()]
    subckt_inst_sublines = [
        ".SUBCKT",
        subckt_name,
        *ports,
        *param_strs,

    ]
    subckt_inst_str = " ".join(subckt_inst_sublines)
    return subckt_inst_str



def get_subckt_lines(subckt: SpSubCkt) -> list:
    """ Generates the lines for a spice subckt """
    subckt_hdr = get_subckt_hdr_lines(f"{subckt.name} subcircuit")
    subckt_ports = get_subckt_ports(subckt.name, subckt.ports, subckt.params)
    subckt_insts = subckt.raw_sp_insts_lines
    subckt_lines = [
        "\n",
        *subckt_hdr,
        subckt_ports,
        *subckt_insts,
        ".ENDS",
        "\n"  
    ]
    return subckt_lines


# def write_basic_subckts() -> None:

#     """ SPICE NETLIST OF LOADED WIRE """
#     wire_ports = {
#         "in" : "n_in",
#         "out": "n_out",
#         "gnd": "n_gnd"
#     }
#     wire_subckt = SpSubCkt(
#         name="wire",
#         element="subckt",
#         ports=[port_name for port_key, port_name in wire_ports.items()],
#         params={"Rw": "1m", "Cw": "1f"},
#         raw_sp_insts_lines=[
#             # f"C_PAR_IN {wire_ports['in']} gnd Cw",
#             f"R_SER {wire_ports['in']} {wire_ports['out']} Rw",
#             f"C_PAR_OUT {wire_ports['in']} gnd Cw",
#         ]
#     )
#     wire_lines = get_subckt_lines(wire_subckt)
#     """ SPICE NETLIST OF INVERTER """
#     inv_ports = {
#         "in" : "n_in",
#         "out": "n_out",
#         "vdd": "n_vdd",
#         "gnd": "n_gnd",
#     }
#     inv_subckt = SpSubCkt(
#         name="inv",
#         element="subckt",
#         ports=[port_name for port_key, port_name in inv_ports.items()],
#         params={
#             "hfin": "3.5e-008",
#             "lfin": "6.5e-009",
#             "Wn" : "10",
#             "Wp" : "20",
#         },
#         raw_sp_insts_lines=[
#             f"MN_DOWN {inv_ports['out']} {inv_ports['in']} {inv_ports['gnd']} {inv_ports['gnd']} nmos hfin=hfin lfin=lfin L=gate_length nfin=Wn ASEO=Wn*min_tran_width*trans_diffusion_length ADEO=Wn*min_tran_width*trans_diffusion_length PSEO=Wn*min_tran_width+2*trans_diffusion_length PDEO=Wn*min_tran_width+2*trans_diffusion_length",
#             f"MP_UP {inv_ports['out']} {inv_ports['in']} {inv_ports['vdd']} {inv_ports['vdd']} pmos hfin=hfin lfin=lfin L=gate_length nfin=Wp ASEO=Wp*min_tran_width*trans_diffusion_length ADEO=Wp*min_tran_width*trans_diffusion_length PSEO=Wp*min_tran_width+2*trans_diffusion_length PDEO=Wp*min_tran_width+2*trans_diffusion_length"
#         ]
#     )
#     inv_lines = get_subckt_lines(inv_subckt)
#     with open(spice_info.basic_subckts_file,"w") as fd: 
#         for l in get_subckt_hdr_lines("BASIC SUBCIRCUITS"):
#             print(l,file=fd)
#         print(".LIB BASIC_SUBCIRCUITS",file=fd)
#         """ WRITING LOADED WIRE NETLIST """
#         for l in wire_lines:
#             print(l,file=fd)
#         """ WRITING INV WIRE NETLIST """
#         for l in inv_lines:
#             print(l,file=fd)

#         print(".ENDL BASIC_SUBCIRCUITS",file=fd)
#     print(spice_info.basic_subckts_file)
    
def get_metal_via_insts(mlayer: int) -> list:

    metal_via_insts = [
        '',
        f'*** M{mlayer} wire loads',
        f'X_m{mlayer}_wire_load n_m{mlayer-1}_m{mlayer}_via_out n_m{mlayer}_out wire Rw=m{mlayer}_ic_res Cw=m{mlayer}_ic_cap',
        f'X_m{mlayer}_m{mlayer+1}_via_wire_load n_m{mlayer}_out n_m{mlayer}_m{mlayer+1}_via_out wire Rw=m{mlayer}_m{mlayer+1}_via_res Cw=m{mlayer}_m{mlayer+1}_via_cap',
    ]
    
    return metal_via_insts


def get_subckt_ports_new(subckt: SpSubCkt) -> str:
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

def get_inst_line(inst: SpSubCktInst) -> str:
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

def get_subckt_insts_lines(subckt: SpSubCkt) -> list:
    # These two are defined somewhere but will be used to connect disperate 
    
    subckt_insts_lines = []
    for inst in subckt.insts:
        subckt_insts_lines.append(get_inst_line(inst))
    return subckt_insts_lines 


def get_subckt_lines_new(sp_subckt: SpSubCkt) -> list:
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


def init_subckt_libs(design_info: DesignInfo) -> None:
    # global subckt_libs
    """
        Atomic subckts are from spice syntax and are not defined anywhere
        This means that the parameters used are always assigned during an instantiation of atomic subckts
    """    
    sp_subckt_atomic_lib = {
        "cap" : SpSubCkt(
            element = "cap",
            ports = io_ports,
            params = {
                "C" : "1f"
            }
        ),
        "res" : SpSubCkt(
            element = "res",
            ports = io_ports,
            params = {
                "R" : "1m"
            }
        ),
        "ind" : SpSubCkt(
            element = "ind",
            ports = io_ports,
            params = {
                "L" : "1p"
            }
        ),
        "mnfet" : SpSubCkt(
            name = "nmos",
            element = "mnfet",
            ports = mfet_ports,
            params = {
                # "hfin" : "hfin",
                "L" : "gate_length",
                "M" : "1",
                "nfin" : f"{nfet_width_param}",
                "ASEO" : f"{nfet_width_param} * min_tran_width * trans_diffusion_length",
                "ADEO" : f"{nfet_width_param} * min_tran_width * trans_diffusion_length",
                "PSEO" : f"{nfet_width_param} * (min_tran_width + 2 * trans_diffusion_length)",
                "PDEO" : f"{nfet_width_param} * (min_tran_width + 2 * trans_diffusion_length)",
            }
        ),
        "mpfet" : SpSubCkt(
            name = "pmos",
            element = "mpfet",
            ports = mfet_ports,
            params = {
                # "hfin" : "hfin",
                "L" : "gate_length",
                "M" : "1",
                "nfin" : f"{pfet_width_param}",
                "ASEO" : f"{pfet_width_param} * min_tran_width * trans_diffusion_length",
                "ADEO" : f"{pfet_width_param} * min_tran_width * trans_diffusion_length",
                "PSEO" : f"{pfet_width_param} * (min_tran_width + 2 * trans_diffusion_length)",
                "PDEO" : f"{pfet_width_param} * (min_tran_width + 2 * trans_diffusion_length)",
            }
        )
    }
    #TODO make sure that the number of conn keys are equal to the number of ports in inst 
    basic_subckts = {
        "inv" : SpSubCkt(
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
                SpSubCktInst(
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
                        "nfin" : f"{nfet_width_param}",
                        "ASEO" : f"{nfet_width_param} * min_tran_width * trans_diffusion_length",
                        "ADEO" : f"{nfet_width_param} * min_tran_width * trans_diffusion_length",
                        "PSEO" : f"{nfet_width_param} * (min_tran_width + 2 * trans_diffusion_length)",
                        "PDEO" : f"{nfet_width_param} * (min_tran_width + 2 * trans_diffusion_length)",
                    }
                    # if param values are not defined they are set to default
                ),
                SpSubCktInst(
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
                        "nfin" : f"{pfet_width_param}",
                        "ASEO" : f"{pfet_width_param} * min_tran_width * trans_diffusion_length",
                        "ADEO" : f"{pfet_width_param} * min_tran_width * trans_diffusion_length",
                        "PSEO" : f"{pfet_width_param} * (min_tran_width + 2 * trans_diffusion_length)",
                        "PDEO" : f"{pfet_width_param} * (min_tran_width + 2 * trans_diffusion_length)",
                    }
                    # if param values are not defined they are set to default
                ),
            ]
        ),
        "wire" : SpSubCkt(
            name = "wire",
            element = "subckt",
            ports = io_ports,
            params = {
                "Rw" : "1m",
                "Cw" : "1f",
            },
            insts = [
                SpSubCktInst(
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
                SpSubCktInst(
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
                SpSubCktInst(
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
        f"bottom_to_top_via_stack": SpSubCkt( 
            name = f"bottom_to_top_via_stack",
            element = "subckt",
            ports = io_ports,
            direct_conn_insts = True,
            # Via stack capacitance estimated by using the wire capacitance of highest layer and multplitlying by height of via stack (conservative)
            insts = flatten_mixed_list(
                [
                    #Via stack going from bottom metal to top metal - num pwr mlayers (leaving 2 layers for X and Y traversal on top metal layers)
                    SpSubCktInst(
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
    
    subckt_libs = SpSubCktLibs(
        atomic_subckts= sp_subckt_atomic_lib,
        basic_subckts = basic_subckts,
        subckts = subckts,
    )
    return subckt_libs



def write_subckt_libs(subckt_libs) -> None:
    
    basic_subckts_lines = [".LIB BASIC_SUBCIRCUITS"]
    for subckt in subckt_libs.basic_subckts.values():
        basic_subckts_lines += get_subckt_lines_new(subckt)
    basic_subckts_lines.append(".ENDL BASIC_SUBCIRCUITS")

    with open(spice_info.basic_subckts_file, "w") as fd:
        for l in basic_subckts_lines:
            print(l,file=fd)
    
    subckts_lines = [".LIB SUBCIRCUITS"]
    for subckt in subckt_libs.subckts.values():
        subckts_lines += get_subckt_lines_new(subckt)
    subckts_lines.append(".ENDL SUBCIRCUITS")

    with open(spice_info.subckts_file, "w") as fd:
        for l in subckts_lines:
            print(l,file=fd)


# def write_subckts() -> None:
#     num_mlayers = tech_info.num_mlayers
#     driver_ports = {
#         "in" : "n_in",
#         "out" : "n_out",
#         "vdd" : "n_vdd",
#         "gnd" : "n_gnd"
#     }
#     driver_params = {
#         "fanout" : "1",
#         "Wn" : "1",
#         "Wp" : "2",
#     }
#     ubump_mlayer_driver = SpSubCkt(
#         name = "ubump_mlayer_driver",
#         element="subckt",
#         ports = [port_name for _, port_name in driver_ports.items()],
#         params = driver_params,
#         raw_sp_insts_lines=[
#             '',
#             '*** Input wire load',
#             f'X_in_wire_load {driver_ports["in"]} n_in_inv_1 wire Rw=dvr_ic_in_res Cw=dvr_ic_in_cap',
#             '',
#             '*** Driver inverters',
#             'X_inv_1 n_in_inv_1 mlayers_in_1 n_vdd n_gnd inv Wn=Wn*fanout Wp=Wp*fanout',
#             '',
#             '*** Top Die Metal Layers Load',
#             'X_top_die_mlayers_load mlayers_in_1 n_ubump_in wire_metal_stack_sz_9_w_vias_load',            
#             '',
#             '*** uBump Capacitance x2 for capacitance of other size ubump',
#             'X_ubump_wire_load n_ubump_in n_bottom_die_mlayers_load_in wire Rw=2*ubump_res Cw=2*ubump_cap',
#             '',
#             '*** Bottom Die Metal Layers Load',
#             f'X_bot_die_mlayers_load n_bottom_die_mlayers_load_in {driver_ports["out"]} wire_metal_stack_sz_9_w_vias_load',
#             '',
#         ]
#     )
#     driver_subckt_lines = get_subckt_lines(ubump_mlayer_driver)
#     # driver_subckt_lines = [
#     #     # PARAMS COMING FROM .PARAM DIRECTIVES 
#     #     # init_Wn, init_Wp -> initial widths (in fins for finfets) for n and p fets
#     #     # dvr_ic_in_res, dvr_ic_in_cap -> input load of driver resistance/capacitance
#     #     # M1:
#     #     # m1_ic_res, m1_ic_cap -> metal 1 res and cap
#     #     # m1_m2_via_res, m1_m2_via_cap -> m1 to m2 via res and cap
#     #     # MX ...
#     #     '******************************************************************************************',
#     #     '* ubump_ic_driver subcircuit ',
#     #     '******************************************************************************************',
#     #     '',
#     #     '.SUBCKT ubump_ic_driver n_in n_out n_vdd n_gnd drv_fac=1',
#     #     # TODO MOVE BELOW TO THE SP SIM FILE
#     #     '',
#     #     '** Input wire load',
#     #     'X_in_wire_load n_in n_in_inv_1 wire Rw=dvr_ic_in_res Cw=dvr_ic_in_cap',
#     #     '',
#     #     '** Driver inverters',
#     #     'X_inv_1 n_in_inv_1 n_out_1 n_vdd n_gnd inv Wn=init_Wn*drv_fac Wp=init_Wn*drv_fac',
#     #     '',
#     #     # # METAL 1 CONNECTING TO DRIVER
#     #     # '*** Metal layer used after the active elements (drivers)',
#     #     # 'X_drv_out_m1_wire_load n_inv_out_1 n_m1_out wire Rw=m1_ic_res Cw=m1_ic_cap',
#     #     # 'X_m1_m2_via_wire_load n_m1_out n_m1_m2_via_out wire Rw=m1_m2_via_res Cw=m1_m2_via_cap',
#     #     # # The get_metal_via_insts function only works for connections between metal layers 
#     #     # # As there are 9 Metal Layers so function is called for M2 -> M8
#     #     # *[inst_line for mlayer in range(num_mlayers-2) for inst_line in get_metal_via_insts(mlayer+2)],
#     #     # '',
#     #     # '*** Last Metal Layer',
#     #     # f'X_m{num_mlayers}_wire_load n_m{num_mlayers-1}_m{num_mlayers}_via_out n_m{num_mlayers}_ubump_via_out wire Rw=m{num_mlayers}_ic_res Cw=m{num_mlayers}_ic_cap',
#     #     # f'X_m9_ubump_via_wire_load n_m{num_mlayers}_ubump_via_out n_ubump_in wire Rw=m9_ubump_via_res Cw=m9_ubump_via_cap',
#     #     # '',
#     #     '*** uBump Capacitance',
#     #     'X_ubump_wire_load n_ubump_in n_out wire Rw=ubump_res Cw=ubump_cap',        
#     #     # 'X_inv_2 n_out_inv_1 n_out n_vdd n_gnd inv Wn=init_Wn*drv_fac Wp=init_Wn*drv_fac',
#     #     '.ENDS',
#     # ]
#     """ SPICE NETLIST FOR METAL STACK LOAD OF <num_mlayers> LAYERS"""
#     wire_ports = {
#         "in" : "n_in",
#         "out" : "n_out"
#     }
#     metal_via_wire = SpSubCkt(
#         name=f"wire_metal_stack_sz_{num_mlayers}_w_vias_load",
#         element="subckt",
#         ports=[port_name for _, port_name in wire_ports.items()],
#         params={},
#         raw_sp_insts_lines = [
#             # METAL 1 CONNECTING TO DRIVER
#             '*** Metal layer used after the active elements (drivers)',
#             f'X_drv_out_m1_wire_load {wire_ports["in"]} n_m1_out wire Rw=m1_ic_res Cw=m1_ic_cap',
#             'X_m1_m2_via_wire_load n_m1_out n_m1_m2_via_out wire Rw=m1_m2_via_res Cw=m1_m2_via_cap',
#             # The get_metal_via_insts function only works for connections between metal layers 
#             # As there are 9 Metal Layers so function is called for M2 -> M8
#             *[inst_line for mlayer in range(num_mlayers-2) for inst_line in get_metal_via_insts(mlayer+2)],
#             '',
#             '*** Last Metal Layer',
#             f'X_m{num_mlayers}_wire_load n_m{num_mlayers-1}_m{num_mlayers}_via_out n_m{num_mlayers}_ubump_via_out wire Rw=m{num_mlayers}_ic_res Cw=m{num_mlayers}_ic_cap',
#             f'X_m9_ubump_via_wire_load n_m{num_mlayers}_ubump_via_out {wire_ports["out"]} wire Rw=m9_ubump_via_res Cw=m9_ubump_via_cap',
#             '',
#         ]
#     )   
#     metal_stack_wire_lines = get_subckt_lines(metal_via_wire)
#     die_to_die_wire_load=SpSubCkt(
#         name=f"die_to_die_wire_load",
#         element="subckt",
#         ports=[port_name for _, port_name in wire_ports.items()],
#         params={"M": 1},
#         raw_sp_insts_lines = []
#     )


#     subckt_lib_wrap = [
#         *get_subckt_hdr_lines("SUBCIRCUITS"),
#         '.LIB SUBCIRCUITS',
#         *metal_stack_wire_lines,
#         *driver_subckt_lines,
#         '.ENDL SUBCIRCUITS',
#     ]

#     with open(spice_info.subckts_file,"w") as fd:
#         for l in subckt_lib_wrap:
#             print(l,file=fd)


def write_sp_includes() -> None:

    sp_includes_lines = [
        f'*** INCLUDE ALL LIBRARIES',
        f'.LIB INCLUDES',
        f'*** Include process data (voltage levels, gate length and device models library)',
        f'.LIB "{spice_info.process_data_file}" PROCESS_DATA',
        f'*** Include transistor parameters',
        f'*** Include wire resistance and capacitance',
        f'*** Include basic subcircuits',
        f'.LIB "{spice_info.basic_subckts_file}" BASIC_SUBCIRCUITS',
        f'*** Include subcircuits',
        f'.LIB "{spice_info.subckts_file}" SUBCIRCUITS',
        f'.ENDL INCLUDES',
    ]
    with open(spice_info.include_sp_file,"w") as fd:
        for l in sp_includes_lines:
            print(l,file = fd)
    

def write_sp_process_data() -> None:
    sp_process_data_lines = [
        '*** PROCESS DATA AND VOLTAGE LEVELS',
        '.LIB PROCESS_DATA',
        '',
        '*** Voltage levels',
        # Voltage params
        *[f".PARAM {v_param} = {v_val}" for v_param, v_val in process_data.voltage_info.items()],
        '',
        '*** Geometry',
        *[f".PARAM {v_param} = {v_val}" for v_param, v_val in process_data.geometry_info.items()],
        '',
        '*** Technology (Metal Layers / Vias / uBumps)',
        *[f".PARAM {v_param} = {v_val}" for v_param, v_val in process_data.tech_info.items()],
        '',
        '*** Driver params',
        *[f".PARAM {v_param} = {v_val}" for v_param, v_val in process_data.driver_info.items()],
        '',
        '*** Supply voltage.',
        'VSUPPLY vdd gnd supply_v',
        '.global ' + " ".join([node for node in process_data.global_nodes.keys()]),
        #'VSUPPLYLP vdd_lp gnd supply_v_lp',
        '',
        '*** Device models',
        f'.LIB "{spice_info.model_file}" 7NM_FINFET_HP',
        '.ENDL PROCESS_DATA',
    ]
    with open(spice_info.process_data_file,"w") as fd:
        for l in sp_process_data_lines:
            print(l, file=fd)



def get_input_signal(vsrc_ports: dict, vsrc_args: dict ) -> str:
    input_signal_sublines = [
        "VIN",
        vsrc_ports["in"],
        vsrc_ports["gnd"],
        vsrc_args["type"],
        "(",
            vsrc_args["init_volt"],
            vsrc_args["peak_volt"],
            vsrc_args["delay_time"],
            vsrc_args["rise_time"],
            vsrc_args["fall_time"],
            vsrc_args["pulse_width"],
            vsrc_args["period"],
        ")",
    ]
    input_signal_str = " ".join(input_signal_sublines)
    return input_signal_str


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


def write_sp_process_package_dse(design_info: DesignInfo, process_package_params: dict) -> None:

    sim_inst_lines, sp_testing_model = buffer_sim_setup(design_info, process_package_params)

    sp_sim_lines = [
        *get_subckt_hdr_lines(f"Sensitivity Study for Process {design_info.process_info.name} and Ubump Sweep"),
        f".TITLE sensitivity_study",
        *get_subckt_hdr_lines("Include libraries, parameters and other"),
        f'.LIB "{spice_info.include_sp_file}" INCLUDES',
        *get_subckt_hdr_lines("Setup and input"),
        *get_sim_setup_lines(design_info, process_package_params["buffer_params"]["num_stages"], sp_testing_model),
        *sim_inst_lines,
        '.END',
    ]

    with open(spice_info.process_package_dse.sp_file,"w") as fd:
        for l in sp_sim_lines:
            print(l,file=fd)

def buffer_sim_setup(design_info: DesignInfo, process_package_params: dict) -> Tuple[List[str], SpTestingModel]:
    
    sp_testing_model = SpTestingModel(
        insts = [],
        target_freq = (1 / (process_package_params["sim_params"]["period"]))*1e3,
    )

    # Shape Inverter + Num Stages + Inverter on bottom die
    total_inv_stages = 1 + process_package_params["buffer_params"]["num_stages"] + design_info.bot_die_nstages  
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

    sim_insts = flatten_mixed_list([
        # For the first inst in the chain we need to manually define the input signal
        SpSubCktInst(
            name = "shape_inv",
            subckt = design_info.subckt_libs.basic_subckts["inv"],
            # if the param values aren't specified then the default values are used
            param_values = {
                **pn_params[0],
                "fanout" : "1",
            },
            conns = {
                "in" : "n_in", # TODO define this using a more global definition rather than hardcoding
                "vdd" : f"{process_data.global_nodes['vdd']}",
                "gnd" : f"{process_data.global_nodes['gnd']}",
            }
        ),
        [
            SpSubCktInst(
                name = f"inv_stage_{stage_num}",
                subckt = design_info.subckt_libs.basic_subckts["inv"],
                param_values = {
                    **pn_params[stage_num],
                    "fanout" : f"{process_package_params['buffer_params']['stage_ratio'] ** stage_num}",
                },
                conns = {
                    "vdd" : f"{process_data.global_nodes['vdd']}",
                    "gnd" : f"{process_data.global_nodes['gnd']}",
                }
            )
            for stage_num in range(1, process_package_params["buffer_params"]["num_stages"] + 1, 1)
        ],
        [
            SpSubCktInst(
                name = f"base_die_active_to_top_via_totem_{i}",
                subckt = design_info.subckt_libs.subckts["bottom_to_top_via_stack"],
            ) for i in range(via_factor)
        ],
        # Now we define the wire loads and ubumps which are connected to the last stage of the buffer chain
        SpSubCktInst(
            name = f"top_metal_layer_wire_load",
            subckt = design_info.subckt_libs.basic_subckts["wire"],
            param_values = {
                "Rw" : f"{design_info.process_info.mlayers[mlayer_idx].sp_params['wire_res_per_um'].name}*{mlayer_dist}",
                "Cw" : f"{design_info.process_info.mlayers[mlayer_idx].sp_params['wire_cap_per_um'].name}*{mlayer_dist}",
            },
        ),
        SpSubCktInst(
            name = f"ubump_load_1",
            subckt = design_info.subckt_libs.basic_subckts["wire"],
            param_values = {
                "Rw" : f"{design_info.package_info.ubump_info.sp_params['res'].name}*{ubump_factor}",
                "Cw" : f"{design_info.package_info.ubump_info.sp_params['cap'].name}*{ubump_factor}",
            },
        ),
        [
            SpSubCktInst(
                name = f"top_die_to_active_via_totem_{i}",
                subckt = design_info.subckt_libs.subckts["bottom_to_top_via_stack"],
            ) for i in range(via_factor)
        ],
        SpSubCktInst(
            name = f"bot_metal_layer_wire_load",
            subckt = design_info.subckt_libs.basic_subckts["wire"],
            param_values = {
                "Rw" : f"{design_info.process_info.mlayers[mlayer_idx].sp_params['wire_res_per_um'].name}*{mlayer_dist}",
                "Cw" : f"{design_info.process_info.mlayers[mlayer_idx].sp_params['wire_cap_per_um'].name}*{mlayer_dist}",
            },
        ),
        # Now we connect to the inverter chain on the base die
        [
            SpSubCktInst(
                name = f"bottom_die_inv_{stage_num}",
                subckt = design_info.subckt_libs.basic_subckts["inv"],
                param_values = {
                    **pn_params[process_package_params["buffer_params"]["num_stages"] + 1 + stage_num],
                    "fanout" : f"{process_package_params['buffer_params']['stage_ratio']**stage_num}",
                },
                conns = {
                    "vdd" : f"{process_data.global_nodes['vdd']}",
                    "gnd" : f"{process_data.global_nodes['gnd']}", 
                }
            )
            for stage_num in range(design_info.bot_die_nstages)
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






def get_buffer_sim_lines(design_info: DesignInfo, num_stages: int, buff_fanout: int, add_wlen: int, pn_size_mode: str = "manual", in_sp_sim_df: pd.DataFrame = None) -> Tuple[list, list]:
    
    # Find largest Macro in design, will have to route at least half the largest dimension on top metal layer
    max_macro_dist = max(flatten_mixed_list([[sram.width/2 + sram.height/2] for sram in design_info.srams]))

    # Shape Inverter + Num Stages + Inverter on bottom die
    total_inv_stages = 1 + num_stages + design_info.bot_die_nstages



    # if noc_idx >= len(design_info.nocs):
    driver_to_ubump_dist = add_wlen
    # else:
        # driver_to_ubump_dist = design_info.nocs[noc_idx].add_wire_len
    
    # Metal Distance for top and bottom metal layers
    routing_mlayer_params = {
        "Rw" : f"'{design_info.process_info.mlayers[design_info.buffer_routing_mlayer_idx].sp_params['wire_res_per_um'].name}*({max_macro_dist} + {driver_to_ubump_dist})'",
        "Cw" : f"'{design_info.process_info.mlayers[design_info.buffer_routing_mlayer_idx].sp_params['wire_cap_per_um'].name}*({max_macro_dist} + {driver_to_ubump_dist})'",
    }


    # This means we're assigning optimizing params to the Wn and Wp Sizes 
    if pn_size_mode == "find_opt":
        pn_params = [
            {
                "Wn" : f"{pn_opt_model.wn_param}_{inv_stage}",
                "Wp" : f"{pn_opt_model.wp_param}_{inv_stage}",
            } 
            for inv_stage in range(total_inv_stages) # TODO fix hardcoding of number of inv stages
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
        pn_params = [{
            "Wn" : f"init_Wn_{inv_stage}",
            "Wp" : f"init_Wp_{inv_stage}",
        } for inv_stage in range(total_inv_stages)
        ]

    test_iteration_isnts = flatten_mixed_list([
        # For the first inst in the chain we need to manually define the input signal
        SpSubCktInst(
            name = "shape_inv",
            subckt = design_info.subckt_libs.basic_subckts["inv"],
            # if the param values aren't specified then the default values are used
            param_values = {
                **pn_params[0],
                "fanout" : "1",
            },
            conns = {
                "in" : "n_in", # TODO define this using a more global definition rather than hardcoding
                "vdd" : f"{process_data.global_nodes['vdd']}",
                "gnd" : f"{process_data.global_nodes['gnd']}",
            }
        ),
        [
            SpSubCktInst(
                name = f"inv_stage_{stage_num}",
                subckt = design_info.subckt_libs.basic_subckts["inv"],
                param_values = {
                    **pn_params[stage_num],
                    "fanout" : f"{buff_fanout**stage_num}",
                },
                conns = {
                    "vdd" : f"{process_data.global_nodes['vdd']}",
                    "gnd" : f"{process_data.global_nodes['gnd']}",
                }
            )
            for stage_num in range(1, num_stages + 1, 1)
        ],
        SpSubCktInst(
            name = f"ESD_load_top",
            subckt = design_info.subckt_libs.basic_subckts["wire"],
            param_values = design_info.package_info.esd_rc_params,
        ),
        SpSubCktInst(
            name = f"base_die_active_to_top_via_totem",
            subckt = design_info.subckt_libs.subckts["bottom_to_top_via_stack"],
        ),
        # Now we define the wire loads and ubumps which are connected to the last stage of the buffer chain
        SpSubCktInst(
            name = f"top_metal_layer_wire_load",
            subckt = design_info.subckt_libs.basic_subckts["wire"],
            param_values = routing_mlayer_params,
        ),
        SpSubCktInst(
            name = f"ubump_load_1",
            subckt = design_info.subckt_libs.basic_subckts["wire"],
            param_values = {
                "Rw" : f"{design_info.package_info.ubump_info.sp_params['res'].name}",
                "Cw" : f"{design_info.package_info.ubump_info.sp_params['cap'].name}",
            },
        ),
        SpSubCktInst(
            name = f"bot_metal_layer_wire_load",
            subckt = design_info.subckt_libs.basic_subckts["wire"],
            param_values = routing_mlayer_params,
        ),
        SpSubCktInst(
            name = f"top_die_to_active_via_totem",
            subckt = design_info.subckt_libs.subckts["bottom_to_top_via_stack"],
        ),
        SpSubCktInst(
            name = f"ESD_load_bot",
            subckt = design_info.subckt_libs.basic_subckts["wire"],
            param_values = design_info.package_info.esd_rc_params,
        ),
        # Now we connect to the inverter chain on the base die
        [
            SpSubCktInst(
                name = f"bottom_die_inv_{stage_num}",
                subckt = design_info.subckt_libs.basic_subckts["inv"],
                param_values = {
                    **pn_params[num_stages + 1 + stage_num],
                    "fanout" : f"{buff_fanout**stage_num}",
                },
                conns = {
                    "vdd" : f"{process_data.global_nodes['vdd']}",
                    "gnd" : f"{process_data.global_nodes['gnd']}", 
                }
            )
            for stage_num in range(design_info.bot_die_nstages)
        ]
    ])
    
    # manually assigning the last connection of last inst to output in spice sime:
    test_iteration_isnts[-1].conns["out"] = "n_out"
    test_iteration_isnts = direct_connect_insts(test_iteration_isnts)

    test_circuit_inst_lines = []
    for test_iteration_isnt in test_iteration_isnts:
        test_circuit_inst_lines.append(get_inst_line(test_iteration_isnt))

    return test_iteration_isnts, test_circuit_inst_lines

def get_test_circuit_lines() -> list:
    sp_test_circuit_lines = [
        f'*** Shape Input Inverters',
        f'X_shape_input_inv_1 {driver_model_info.global_in_node} n_shape_inv_1_out {driver_model_info.global_vdd_node} {driver_model_info.gnd_node} inv Wn=init_Wn*1 Wp=init_Wp*1',
        f'X_shape_input_inv_2 n_shape_inv_1_out {driver_model_info.dut_in_node} {driver_model_info.global_vdd_node} {driver_model_info.gnd_node} inv Wn=init_Wn*2 Wp=init_Wp*2',
        f'*** Dut (containing inverter driving metal layer load and 2x ubumps)',
        f'X_dut_inv_mlayers_ubump {driver_model_info.dut_in_node} {driver_model_info.dut_out_node} {driver_model_info.global_vdd_node} {driver_model_info.gnd_node} ubump_mlayer_driver fanout=4',
        f'*** Load on dut',
        f'X_load_inv_1 {driver_model_info.dut_out_node} n_inv_load_out_1 {driver_model_info.global_vdd_node} {driver_model_info.gnd_node} inv Wn=init_Wn*8 Wp=init_Wp*8',
        f'X_load_inv_2 n_inv_load_out_1 n_inv_load_out_2 {driver_model_info.global_vdd_node} {driver_model_info.gnd_node} inv Wn=init_Wn*16 Wp=init_Wp*16',
    ]
    return sp_test_circuit_lines


def get_prop_del_meas_lines(design_info: DesignInfo, in_nodes: List[str], out_nodes: List[str], meas_range: List[int]) -> List[str]:
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
    
    
    prop_del_meas_lines = flatten_mixed_list([
        [
            f'.MEASURE TRAN falling_prop_delay_{node_idx}',
            f'+    TRIG v({in_nodes[node_idx]}) VAL="{driver_model_info.v_supply_param}/2" RISE=1',
            f'+    TARG v({out_nodes[node_idx]}) VAL="{driver_model_info.v_supply_param}/2" FALL=1',
            # f'+    TD=TRIG',
            f'.MEASURE TRAN rising_prop_delay_{node_idx}',
            f'+    TRIG v({in_nodes[node_idx]}) VAL="{driver_model_info.v_supply_param}/2" FALL=1',
            f'+    TARG v({out_nodes[node_idx]}) VAL="{driver_model_info.v_supply_param}/2" RISE=1',
            # f'+    TD=TRIG',
            f'.MEASURE max_prop_delay_{node_idx} param="max(abs(rising_prop_delay_{node_idx}),abs(falling_prop_delay_{node_idx}))"',
            # we will measure the change in voltage from 20% to 80% of the supply voltage
            # Add the t_rise and t_fall for fidelity
            f'.MEASURE TRAN t_rise_{node_idx}',
            f'+      TRIG V({out_nodes[node_idx]}) VAL="0.2*{driver_model_info.v_supply_param}" RISE=1',
            f'+      TARG V({out_nodes[node_idx]}) VAL="0.8*{driver_model_info.v_supply_param}" RISE=1',
            #f'+    TD=TRIG',
            f'.MEASURE TRAN t_fall_{node_idx}',
            f'+      TRIG V({out_nodes[node_idx]}) VAL="0.8*{driver_model_info.v_supply_param}" FALL=1',
            f'+      TARG V({out_nodes[node_idx]}) VAL="0.2*{driver_model_info.v_supply_param}" FALL=1',
            #f'+    TD=TRIG',
        ] for node_idx in range(len(in_nodes))
        ])
    # add the range specified in meas_range
    prop_del_meas_lines += [
        f'.MEASURE TRAN falling_prop_delay_{in_nodes[meas_range[0]]}_{out_nodes[meas_range[1]]}',
        f'+    TRIG v({in_nodes[meas_range[0]]}) VAL="{driver_model_info.v_supply_param}/2" {total_falling_trig_targ[0]}=1',
        f'+    TARG v({out_nodes[meas_range[1]]}) VAL="{driver_model_info.v_supply_param}/2" {total_falling_trig_targ[1]}=1',
        f'+    TD=TRIG',

        f'.MEASURE TRAN rising_prop_delay_{in_nodes[meas_range[0]]}_{out_nodes[meas_range[1]]}',
        f'+    TRIG v({in_nodes[meas_range[0]]}) VAL="{driver_model_info.v_supply_param}/2" {total_rising_trig_targ[0]}=1',
        f'+    TARG v({out_nodes[meas_range[1]]}) VAL="{driver_model_info.v_supply_param}/2" {total_rising_trig_targ[1]}=1',
        f'+    TD=TRIG',

        # Add maximum total rising/falling prop delay to find critical path
        f'.MEASURE max_prop_delay param="max(rising_prop_delay_{in_nodes[meas_range[0]]}_{out_nodes[meas_range[1]]},falling_prop_delay_{in_nodes[meas_range[0]]}_{out_nodes[meas_range[1]]})"',
    ]

    return prop_del_meas_lines


def get_meas_lines_new(design_info: DesignInfo, sp_testing_model: SpTestingModel) -> list:
    

    inv_isnts_in_nodes = [inst.conns["in"] for inst in sp_testing_model.insts if inst.subckt.name == "inv"]
    inv_insts_out_nodes = [inst.conns["out"] for inst in sp_testing_model.insts if inst.subckt.name == "inv"]
    inv_insts_nodes = list(set(inv_insts_out_nodes + inv_isnts_in_nodes))
    # first input is shape inverter so we start at the input of 2nd inverter
    meas_range = [1,len(inv_isnts_in_nodes)-1]

    sp_meas_lines = [
        *get_subckt_hdr_lines("Measurement"),
        *get_prop_del_meas_lines(design_info, inv_isnts_in_nodes, inv_insts_out_nodes, meas_range),
        #f'.PRINT v({driver_model_info.global_in_node}) ' + ' '.join([f"v({node})" for node in inv_insts_out_nodes[1:len(inv_insts_out_nodes)]])
        f'.PRINT ' + ' '.join([f"v({node})" for node in inv_insts_nodes ]),
        
        
        #f'.GRAPH v({driver_model_info.global_in_node}) ' + ' '.join([f"v({node})" for node in inv_insts_out_nodes[1:len(inv_insts_out_nodes)]]) + ' title "inv_out_node_voltage" '
        # f'.PRINT ' + ' '.join([f"cap({node})" for node in inv_isnts_in_nodes])  
        # f'.plot v({driver_model_info.global_in_node}) v({inv_insts_out_nodes[1]}) v({inv_insts_out_nodes[-1]}) ',
    ]
    return sp_meas_lines

def get_meas_lines() -> list:
    sp_meas_lines = [
        *get_subckt_hdr_lines("Measurement"),
        # set fall time measurement to 
        # start on edge of dut input
        # stop on edge of dut output
        f'.MEASURE rising_prop_delay',
        f'+     TRIG V({driver_model_info.dut_in_node}) VAL="{driver_model_info.v_supply_param}/2" RISE=1',
        f'+     TARG V({driver_model_info.dut_out_node}) VAL="{driver_model_info.v_supply_param}/2" FALL=1',
        f'.MEASURE falling_prop_delay',
        f'+     TRIG V({driver_model_info.dut_in_node}) VAL="{driver_model_info.v_supply_param}/2" FALL=1',
        f'+     TARG V({driver_model_info.dut_out_node}) VAL="{driver_model_info.v_supply_param}/2" RISE=1',
        f'.MEASURE avg_prop_delay param="(rising_prop_delay + falling_prop_delay)/2"',
        f'.MEASURE t_rise',
        f'+      TRIG V({driver_model_info.dut_out_node}) VAL="0.2*{driver_model_info.v_supply_param}" RISE=1',
        f'+      TARG V({driver_model_info.dut_out_node}) VAL="0.8*{driver_model_info.v_supply_param}" RISE=1',
        f'.MEASURE t_fall',
        f'+      TRIG V({driver_model_info.dut_out_node}) VAL="0.8*{driver_model_info.v_supply_param}" FALL=1',
        f'+      TARG V({driver_model_info.dut_out_node}) VAL="0.2*{driver_model_info.v_supply_param}" FALL=1',
        f'.plot v({driver_model_info.global_in_node}) v(n_shape_inv_1_out) v({driver_model_info.dut_in_node}) v({driver_model_info.dut_out_node}) v(n_inv_load_out_1)',
    ]
    return sp_meas_lines

def get_sim_setup_lines(design_info: DesignInfo, num_stages: int, sp_testing_model: SpTestingModel) -> List[str]:
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
    total_num_stages = 1 + num_stages + design_info.bot_die_nstages
    sim_setup_lines = [
        f".TRAN {sim_prec}p {sim_length}n",
        # SWEEP DATA=sweep_data",
        f'.OPTIONS BRIEF=1',
        "*** Input Signal",
        f"VIN {dut_in_node} {gnd_node} {vsrc_args['type']} ({vsrc_args['init_volt']} {vsrc_args['peak_volt']} {vsrc_args['delay_time']} {vsrc_args['rise_time']} {vsrc_args['fall_time']} {vsrc_args['pulse_width']} {vsrc_args['period']})",
        "*** Voltage source for device under test, this is used s.t. the power of the circuit can be measured without measring power of wave shaping and input load circuit",
        # Create a voltage source for each inverter index to get current for each of them
        *[f"V_DRIVER_{inv_idx}_SRC vdd_driver_{inv_idx} {gnd_node} {vdd_supply_node}" for inv_idx in range(1,total_num_stages,1)], 
        *get_meas_lines_new(design_info, sp_testing_model),
    ]

    return sim_setup_lines
    

def write_loaded_driver_sp_sim(design_info: DesignInfo, num_stages: int, buff_fanout: int, targ_freq: int, add_wlen: int, in_sp_sim_df: pd.DataFrame = None) -> None:
    """ Writes the spice file for evaluating a driver with a ubump and wireload """

    sim_dir = os.path.join(spice_info.sp_dir,spice_info.sp_sim_title)
    sp.run(["mkdir", "-p", f"{sim_dir}"])
    # num_mlayers = tech_info.num_mlayers

    if in_sp_sim_df is not None:
        test_insts, insts_lines = get_buffer_sim_lines(design_info, num_stages, buff_fanout, add_wlen, pn_size_mode="assign_opt", in_sp_sim_df=in_sp_sim_df)

    
    sp_testing_model = SpTestingModel(
        insts = test_insts,
        target_freq= targ_freq,
    )

    sp_sim_file_lines = [
        f'.TITLE {spice_info.sp_sim_title}',
        *get_subckt_hdr_lines("Include libraries, parameters and other"),
        f'.LIB "{spice_info.include_sp_file}" INCLUDES',
        *get_subckt_hdr_lines("Setup and input"),
        *get_sim_setup_lines(design_info, num_stages, sp_testing_model), 
        *insts_lines,
        '.END',
    ]
    # for l in sp_sim_file_lines:
    #     print(l)
    with open(os.path.join(sim_dir,f"{spice_info.sp_sim_title}.sp"),"w") as fd:
        for l in sp_sim_file_lines:
            print(l,file=fd)
    

def get_opt_sim_setup_lines(design_info: DesignInfo, sp_testing_model: SpTestingModel):
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
    sim_time = targ_period + 1 # Added a litte to the sim duration to make sure crossings are captured
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
        f'.OPTIONS BRIEF=1', # AUTOSTOP=1',
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
        *get_meas_lines_new(design_info, sp_testing_model),
        f".measure tpd param='max(rising_prop_delay_{inv_isnts_in_nodes[1]}_{inv_isnts_out_nodes[-1]},falling_prop_delay_{inv_isnts_in_nodes[1]}_{inv_isnts_out_nodes[-1]})' goal = 0",
        f".measure diff param='rising_prop_delay_{inv_isnts_in_nodes[1]}_{inv_isnts_out_nodes[-1]} - falling_prop_delay_{inv_isnts_in_nodes[1]}_{inv_isnts_out_nodes[-1]}' goal = 0",

        
        #f".measure tpd param='(rising_prop_delay + falling_prop_delay)/2' goal=0 * average prop delay",
        #f".measure diff param='rising_prop_delay-falling_prop_delay' goal = 0 * diff between delays",

    ]
    return sim_setup_lines

def write_pn_sizing_opt_sp_sim(design_info: DesignInfo, num_stages: int, buff_fanout: int, targ_freq: int, add_wlen:int) -> List[SpSubCktInst]:
    """ Writes the spice file for evaluating a driver with a ubump and wireload """

    sim_dir = os.path.join(spice_info.sp_dir,spice_info.sp_sim_title)
    sp.run(["mkdir", "-p", f"{sim_dir}"])

    test_insts, insts_lines = get_buffer_sim_lines(design_info, num_stages, buff_fanout, add_wlen, pn_size_mode="find_opt")
    
    sp_testing_model = SpTestingModel(
        insts = test_insts,
        target_freq= targ_freq,
    )

    sp_sim_file_lines = [
        f'.TITLE {spice_info.sp_sim_title}_pn_opt',
        *get_subckt_hdr_lines("Include libraries, parameters and other"),
        f'.LIB "{spice_info.include_sp_file}" INCLUDES',
        *get_subckt_hdr_lines("Setup and input"),
        *get_opt_sim_setup_lines(design_info, sp_testing_model), 
        *insts_lines,
        '.END',
    ]
    with open(os.path.join(sim_dir,f"opt_pn_{spice_info.sp_sim_title}.sp"),"w") as fd:
        for l in sp_sim_file_lines:
            print(l,file=fd)
            # print(l)


def init_globals() -> None:
    global spice_info
    global process_data
    # global tech_info
    global driver_model_info
    # new sp libs
    global subckt_libs
    global pn_opt_model
    global res
    # sp sim settings
    global sp_sim_settings


def run_spice(sp_work_dir: str = None, sim_sp_files: list = None, sp_process: SpProcess = None) -> str:
    cwd = os.getcwd()
    if sp_process is None:
        os.chdir(os.path.join(spice_info.sp_dir, sp_work_dir))
        for sp_file in sim_sp_files:
            outfile = open(f"{os.path.splitext(sp_file)[0]}.lis","w")
            print(f"Running {os.path.join(spice_info.sp_dir,sp_work_dir,sp_file)}")
            sp.call(["hspice",os.path.join(spice_info.sp_dir,sp_work_dir,sp_file)], stdout=outfile, stderr=outfile)   
    else:
        os.chdir(sp_process.sp_dir)
        outfile = open(f"{sp_process.sp_outfile}","w")
        print(f"Running {sp_process.sp_file}")
        sp.call(["hspice",sp_process.sp_file], stdout=outfile, stderr=outfile)     
    os.chdir(cwd)
    return outfile

def convert_value(val, suffix, unit_lookup):
    if suffix in unit_lookup:
        return float(val) * unit_lookup[suffix]
    else:
        return float(val)

def parse_sp_output(design_info: DesignInfo, parse_flags: dict, buff_fanout: int, n_stages: int, sp_outfile: str) -> Tuple[pd.DataFrame, dict, pd.DataFrame]:

    sp_run_info = {
        "buff_fanout" : buff_fanout,
        "n_stages" : n_stages,
        "total_max_prop_delay" : 0,
        "invs_info": [],
        "inv_chain_area" : 0,
    }
    total_num_invs = 1 + n_stages + design_info.bot_die_nstages

    """ Parses the spice output file and returns a dict with the results """
    ##################### NODE VOLTAGE GRABS #####################
    fd = open(sp_outfile,"r")
    sp_out_text = fd.read()
    fd.close()
    print_line_groups = res.sp_grab_print_vals_re.findall(sp_out_text)
    heading = ""
    dfs = []


    if parse_flags["voltage"]:
        for group in print_line_groups:
            data_lines = group.split('\n')[2:]
            data_lines = data_lines[:-2]
            header_0 = res.wspace_re.split(data_lines[0])  # Extract the column names
            header_1 = res.wspace_re.split(data_lines[1])
            header = [ key for key in [header_0[1]] + header_1 if key != ""]
            df = pd.read_csv(io.StringIO('\n'.join(data_lines)), delim_whitespace=True, skiprows=[0,1], header=None)
            df.columns = header
            # print(df.columns)
            df[["time"]] = df[["time"]].applymap(lambda x: convert_value(x[:-1], x[-1], sp_sim_settings.unit_lookups["time"]))
            # go through voltage keys
            for key in header[1:]:
                df[[key]] = df[[key]].applymap(lambda x: convert_value(x[:-1], x[-1], sp_sim_settings.unit_lookups["voltage"]))
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
                match = res.sp_del_grab_info_re.search(l)
                meas_name = match.group('var1')
                meas_val = match.group('val1')
                meas_units = match.group('unit1')
                # print(l)
                # print(meas_name,meas_val,meas_units)
                if meas_name == "max_prop_delay":
                    sp_run_info["total_max_prop_delay"] = float(meas_val) * sp_sim_settings.unit_lookups["time"][meas_units]
                    continue

                if inv_idx < total_num_invs:
                    for var in var_keys:
                        if var in meas_name:
                            invs_info[inv_idx][var] = float(meas_val) * sp_sim_settings.unit_lookups["time"][meas_units]
                            break
                    if len(invs_info[inv_idx]) == len(var_keys):
                        inv_idx += 1 
                # elif "max_prop_delay" in meas_name:
                #     sp_run_info["total_max_prop_delay"] = float(meas_val) * sp_sim_settings.unit_lookups["time"][meas_units]
    


    sp_run_info["invs_info"] = invs_info
    ##################### PN OPT GRABS #####################
    match_iter = res.sp_grab_inv_pn_vals_re.finditer(sp_out_text)
    nfet_widths = [match.group('value') for match in match_iter if "wn" in str(match.group('name'))]
    match_iter = res.sp_grab_inv_pn_vals_re.finditer(sp_out_text)
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


def sens_study_run(design_info: DesignInfo, process_package_params: dict, metal_dist: int, mlayer_idx: int, via_fac: int, ubump_fac: int):
    ####################### SETUP FOR SWEEPING DSE #######################
    load_params = { 
        "mlayer_dist": metal_dist,
        "mlayer_idx": mlayer_idx,
        "via_factor": via_fac,
        "ubump_factor": ubump_fac,
    }
    process_package_params["load_params"] = load_params
    # Make sure mlayer idx is valid
    assert process_package_params["load_params"]["mlayer_idx"] < len(design_info.process_info.mlayers)
    assert len(process_package_params["buffer_params"]["pn_ratios"]) == 1 + process_package_params["buffer_params"]["num_stages"] + design_info.bot_die_nstages
    sim_success = False
    while not sim_success:
        ####################### SETUP FOR SWEEPING DSE #######################
        write_sp_process_package_dse(design_info, process_package_params)
        ####################### RUN SWEEPING DSE #######################
        # sp_sim = {
        #     "sp_work_dir": spice_info.process_package_dse.sp_dir,
        #     "sim_sp_files": [spice_info.process_package_dse.sp_file]
        # }
        run_spice(sp_process = spice_info.process_package_dse)
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
                design_info,
                parse_flags, 
                process_package_params["buffer_params"]["num_stages"],
                process_package_params["buffer_params"]["stage_ratio"],
                spice_info.process_package_dse.sp_outfile,
            )
        except:
            process_package_params["sim_params"]["period"] *= 2
            continue

        result_dict = {}
        result_dict["max_total_delay"] = sp_run_info["total_max_prop_delay"]
        result_dict = {**result_dict, **load_params}

        if result_dict["mlayer_idx"] == -1: 
            result_dict["mlayer_idx"] = f"M{len(design_info.process_info.mlayers)}"
        else:
            result_dict["mlayer_idx"] = "M" + str(result_dict["mlayer_idx"])

        sim_success = True


    return result_dict

def plot_sp_run(show_flags: dict, sp_run_info: dict, sp_run_df: pd.DataFrame) -> go.Figure:
    
    volt_def_unit = next(iter({k:v for k,v in sp_sim_settings.unit_lookups["voltage"].items() if v == 1}), None)
    time_def_unit = next(iter({k:v for k,v in sp_sim_settings.unit_lookups["time"].items() if v == 1}), None)

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
        

def parse_cli_args() -> tuple:
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--plot_spice', help="takes the ubump output.lis file and plots single run values, is used for manual spice editing, does not write spice", action="store_true")
    parser.add_argument('-t', '--tsv_model', help="performs tsv modeling", action="store_true")
    parser.add_argument('-e', '--buffer_param_dse', help="sweeps parameters for buffer chain wire load, plots results", action="store_true")
    parser.add_argument('-c', '--input_config', help="top level input config file", type=str, default=None)
    args = parser.parse_args()
    return args 



def calc_cost(design_info: DesignInfo, cost_fx_exps: dict, sp_run_info: dict) -> float:
    # prop delay in ps (1000ps is 1 unit of delay cost), area normalized to almost average sized buffer chain (5 tx sizes) (1 unit of area cost)
    delay_cost_unit = 1000 #ps
    area_cost_unit = 2 * 2 * finfet_tx_area_model(3) * design_info.process_info.tx_geom_info.min_width_tx_area * 1e-6 # minimum area inverter
    return ((sp_run_info["total_max_prop_delay"] / delay_cost_unit) ** cost_fx_exps["delay"] ) + ( (sp_run_info["inv_chain_area"] / area_cost_unit) ** (cost_fx_exps["area"]))


def spice_simulation_setup(design_info: DesignInfo) -> DesignInfo:

    # process data is what spice process data gets written out
    process_data.tech_info = {
        # Metal layer & Vias Spice Parameters
        ** { f"{sp_param.name}": f"{sp_param.value}{sp_param.suffix}" for mlayer in design_info.process_info.mlayers for sp_param in mlayer.sp_params.values() },
        # Via Stack Parameters
        ** { f"{sp_param.name}": f"{sp_param.value}{sp_param.suffix}" for via_stack_info in design_info.process_info.via_stack_infos for sp_param in via_stack_info.sp_params.values() },                    
        # Ubump Parameters
        **{ f"{sp_param.name}": f"{sp_param.value}{sp_param.suffix}" for sp_param in design_info.package_info.ubump_info.sp_params.values()}, 
    }
    
    process_data.geometry_info = {
        **{ f"{sp_param.name}": f"{sp_param.value}{sp_param.suffix}" for sp_param in design_info.process_info.tx_geom_info.sp_params.values()},
    }

    # Write out spice parameters for the process parameters
    write_sp_process_data()
    # Initialize and write out spice files for this run
    subckt_libs = init_subckt_libs(design_info)
    write_subckt_libs(subckt_libs)
    write_sp_includes()
    design_info.subckt_libs = subckt_libs

    return design_info

def main():

    init_globals()
    args = parse_cli_args()

    # load top level config
    if args.input_config != None:
        top_level_config = yaml.safe_load(open(args.input_config))

    
    # make the dir structure
    sp.run(["mkdir", "-p", f"{spice_info.subckt_lib_dir}"])
    sp.run(["mkdir", "-p", f"{spice_info.includes_dir}"])

    # Initialize the process information list for all processes used
    cap_suffix = "f"
    # SWEEPING OVER PROCESSES
    beol_infos = [
        # ASAP 7
        {
            "name": "ASAP7",
            "pitch": [80],
            # Mlayers	M1-M3	M4-M5	M6-M7	M8-M9
            "mlayer_ic_res_list": [131.2]*3 + [58.49]*2 + [27.08]*2 + [15.27]*2,
            # Mlayers	M1-M5	M6-M9
            "mlayer_ic_cap_list": [f"{cap}{cap_suffix}" for cap in [0.22]*5 + [0.24]*4],
            # Mlayers	     M1-M3	  M3-M4	    M4-M5	  M5-M6	  M6-M7	    M7-M8	M8-M9-uBump
            "via_res_list": [13.08]*2 + [9.17] + [7.31] + [5.17] + [4.19] + [3.22] + [2.77]*2,
            "via_cap_list": [f"{cap}{cap_suffix}" for cap in [0.22]*5 + [0.24]*4],
        },
        # TSMC 7 LIKE
        {
            "name": "TSMC7",
            # Mlayers	Mx (1x pitch): M1-M5	My (1.9x pitch): M6-M10   (18x pitch): M11-M13
            "mlayer_ic_res_list": [128.7]*5 + [21.6]*5,
            # Mlayers	Mx (1x pitch): M1-M5	My (1.9x pitch): M6-M10   (18x pitch): M11-M13
            "mlayer_ic_cap_list": [f"{cap}{cap_suffix}" for cap in [0.22]*5 + [0.24]*4],
            # Mlayers	     M1-M3	  M3-M4	    M4-M5	  M5-M6	  M6-M7	    M7-M8	M8-M9-uBump
            "via_res_list": [34.8]*5 + [10.32]*5,
            "via_cap_list": [f"{cap}{cap_suffix}" for cap in [0.11]*5 + [0.12]*4],
        }
    ]

    # check that inputs are in proper format (all metal layer lists are of same length)
    for process_info in top_level_config["process_infos"]:
        if not (all(length == process_info["mlayers"] for length in [len(v) for v in process_info["mlayer_lists"].values()])\
                and all(length == process_info["mlayers"] for length in [len(v) for v in process_info["via_lists"].values()])
                # and len(top_level_config["design_info"]["pwr_rail_info"]["mlayer_dist"]) == process_info["mlayers"]
                ):
            raise ValueError("All metal layer and via lists must be of the same length (mlayers)")
    

    ####################### INIT DATA STRUCTS #######################

    # Load in process information from yaml
    process_infos = [
        ProcessInfo(
            name=process_info["name"],
            num_mlayers=process_info["mlayers"],
            contact_poly_pitch=process_info["contact_poly_pitch"],
            # min_width_tx_area=process_info["min_width_tx_area"],
            # tx_dims=process_info["tx_dims"],
            mlayers=[
                MlayerInfo(
                    idx=layer,
                    wire_res_per_um=process_info["mlayer_lists"]["wire_res_per_um"][layer],
                    wire_cap_per_um=process_info["mlayer_lists"]["wire_cap_per_um"][layer],
                    via_res=process_info["via_lists"]["via_res"][layer],
                    via_cap=process_info["via_lists"]["via_cap"][layer],
                    via_pitch=process_info["via_lists"]["via_pitch"][layer],
                    pitch=process_info["mlayer_lists"]["pitch"][layer],
                    height=process_info["mlayer_lists"]["hcu"][layer],
                    width=process_info["mlayer_lists"]["wcu"][layer],
                    t_barrier=process_info["mlayer_lists"]["t_barrier"][layer],
                ) for layer in range(process_info["mlayers"])
            ],
            via_stack_infos = [
                ViaStackInfo(
                    mlayer_range = via_stack["mlayer_range"],
                    res = via_stack["res"],
                    height = via_stack["height"],
                    # Using the average of the metal layer cap per um for the layers used in via stack (this would assume parallel plate cap as much as metal layers so divide by 2)
                    # This should be a conservative estimate with a bit too much capacitance
                    avg_mlayer_cap_per_um = (sum(process_info["mlayer_lists"]["wire_cap_per_um"][via_stack["mlayer_range"][0]:via_stack["mlayer_range"][1]])/len(process_info["mlayer_lists"]["wire_cap_per_um"][via_stack["mlayer_range"][0]:via_stack["mlayer_range"][1]]))*0.5,
                )
                for via_stack in process_info["via_stacks"]
            ],
            tx_geom_info = TxGeometryInfo( 
                min_tx_contact_width = float(process_info["geometry_info"]["min_tx_contact_width"]),
                tx_diffusion_length = float(process_info["geometry_info"]["tx_diffusion_length"]),
                gate_length = float(process_info["geometry_info"]["gate_length"]),
                min_width_tx_area = float(process_info["geometry_info"]["min_width_tx_area"]),
            )
        ) for process_info in top_level_config["process_infos"]
    ]
    ####################### INIT DATA STRUCTS #######################

    stage_range = range(*top_level_config["d2d_buffer_dse"]["stage_range"])
    fanout_range = range(*top_level_config["d2d_buffer_dse"]["stage_ratio_range"])
    cost_fx_exps = {
        "delay": top_level_config["d2d_buffer_dse"]["cost_fx_exps"]["delay"],
        "area": top_level_config["d2d_buffer_dse"]["cost_fx_exps"]["area"],
        "power": top_level_config["d2d_buffer_dse"]["cost_fx_exps"]["power"],
    }
    
    # check that inputs are in proper format (all metal layer lists are of same length)
    if not (all(length == len(top_level_config["package_info"]["ubump"]["sweeps"]["pitch"]) for length in [len(v) for v in top_level_config["package_info"]["ubump"]["sweeps"].values()])):
        raise ValueError("All ubump parameter lists must have the same length")
    
    ubump_infos = [
        SolderBumpInfo(
            pitch=top_level_config["package_info"]["ubump"]["sweeps"]["pitch"][idx],
            diameter=float(top_level_config["package_info"]["ubump"]["sweeps"]["pitch"][idx])/2,
            height=top_level_config["package_info"]["ubump"]["sweeps"]["height"][idx],
            cap=top_level_config["package_info"]["ubump"]["sweeps"]["cap"][idx],
            res=top_level_config["package_info"]["ubump"]["sweeps"]["res"][idx],
            tag="ubump",
        ) for idx in range(len(top_level_config["package_info"]["ubump"]["sweeps"]["pitch"]))
    ]


    design_info = DesignInfo(
        srams=[
            SRAMInfo(
                width=float(macro_info["dims"][0]),
                height=float(macro_info["dims"][1]),
            ) for macro_info in top_level_config["design_info"]["macro_infos"]
        ],
        # nocs = [
        #     NoCInfo(
        #         area = float(noc_info["area"]),
        #         rtl_params = noc_info["rtl_params"],
        #         # flit_width = int(noc_info["flit_width"])
        #     ) for noc_info in top_level_config["design_info"]["noc_infos"]
        # ],
        logic_block = HwModuleInfo(
            name = "logic_block",
            area = float(top_level_config["design_info"]["logic_block_info"]["area"]),
            # dims = top_level_config["design_info"]["logic_block_info"]["dims"],
            width = float(top_level_config["design_info"]["logic_block_info"]["dims"][0]),
            height = float(top_level_config["design_info"]["logic_block_info"]["dims"][1]),
        ),
        process_info=process_info,
        subckt_libs=SpSubCktLibs(),
        bot_die_nstages = 1,
        buffer_routing_mlayer_idx = int(top_level_config["design_info"]["buffer_routing_mlayer_idx"]),
    )

    esd_rc_params = top_level_config["design_info"]["esd_load_rc_wire_params"]
    add_wlens = top_level_config["design_info"]["add_wire_lengths"]

    ####################### INIT DATA STRUCTS #######################

    if args.plot_spice:

        show_parse_flags = {
            "voltage": True,
            "delay": False,
        }
        n_stages = 1
        buff_fanout = 3
        cur_tfreq = 100
        # design_info.process_info = process_infos[0]
        # ubump_info = ubump_infos[0]
        # design_info.package_info = PackageInfo(
        #     ubump_info=ubump_info,
        #     esd_rc_params=esd_rc_params,      
        # )
        # noc_idx = len(design_info.nocs) + 1
        # design_info = spice_simulation_setup(design_info)
        # write_pn_sizing_opt_sp_sim(design_info, num_stages=n_stages, buff_fanout=buff_fanout, noc_idx=noc_idx, targ_freq=cur_tfreq)
        sims = {
            "sp_work_dir":"ubump_ic_driver",
            "sim_sp_files": [f"ubump_ic_driver.sp"]
        }
        run_spice(**sims)
        # sp_run_df, sp_run_info, sp_sim_df = parse_sp_output(max(fanout_range), max(stage_range), spice_info.sp_sim_outfile)
        sp_run_df, sp_run_info, sp_sim_df = parse_sp_output(design_info, show_parse_flags, buff_fanout, n_stages, os.path.join(spice_info.sp_dir,spice_info.sp_sim_title,"opt_pn_ubump_ic_driver.lis"))
        bar_fig = plot_sp_run(show_parse_flags, sp_run_info, sp_run_df)
        # bar_fig.show()
    elif args.tsv_model:
        pdn.pdn_modeling(top_level_config, process_infos[0])
    elif args.buffer_param_dse:
        output_csv = "sens_study_out.csv"
        for process_info in process_infos:
            design_info.process_info = process_info
            for ubump_info in ubump_infos:
                design_info.package_info = PackageInfo( 
                    ubump_info=ubump_info,
                )
                # Setup Simulation For Sensitivity Analysis of Process and Ubump
                design_info = spice_simulation_setup(design_info)
                # Sweep ranges for sensitivity
                sens_sweep_vals = [i+1 for i in range(10)]
                # Setup Buffer Parameters
                buffer_params = {
                    "num_stages" : 1,
                    "stage_ratio": 2,
                    "pn_ratios": [] # 1 value for each stage + 1 for shape + 1 for final stage
                }
                # These values can be parameters (strings) or integer values
                buffer_params["pn_ratios"] = [
                    {
                        "wp": 7,
                        "wn": 5,
                    } for _ in range(1 + buffer_params["num_stages"] + design_info.bot_die_nstages)
                ]
                sim_params = {
                    "period": 20 # ns
                }
                process_package_params = {
                    "buffer_params" : buffer_params,
                    "sim_params" : sim_params,
                }
                ######################## dict to store results ########################
                delay_results = []
                max_macro_dist = max(flatten_mixed_list([[sram.width/2 + sram.height/2] for sram in design_info.srams]))

                for ubump_fac in sens_sweep_vals:
                    result_dict = sens_study_run(design_info, process_package_params, metal_dist = max_macro_dist, mlayer_idx = -1, via_fac = 1, ubump_fac = ubump_fac)
                    result_dict["ubump_pitch"] = ubump_info.pitch
                    delay_results.append(result_dict)
                    
                    with open(output_csv, "a", newline="") as csvfile:
                        writer = csv.DictWriter(csvfile, fieldnames=delay_results[0].keys())
                        if ubump_fac == 1:
                            writer.writeheader()
                        writer.writerow(result_dict)
                for via_fac in sens_sweep_vals:
                    result_dict = sens_study_run(design_info, process_package_params, metal_dist = max_macro_dist, mlayer_idx = -1, via_fac = via_fac, ubump_fac = 1)
                    result_dict["ubump_pitch"] = ubump_info.pitch
                    delay_results.append(result_dict)
                    with open(output_csv, "a", newline="") as csvfile:
                        writer = csv.DictWriter(csvfile, fieldnames=delay_results[0].keys())
                        writer.writerow(result_dict)
                for metal_dist in sens_sweep_vals:
                    for mlayer_idx in range(len(design_info.process_info.mlayers)):
                        result_dict = sens_study_run(design_info, process_package_params, metal_dist = metal_dist * max_macro_dist, mlayer_idx = mlayer_idx, via_fac = 1, ubump_fac = 1)
                        result_dict["ubump_pitch"] = ubump_info.pitch
                        delay_results.append(result_dict)
                        with open(output_csv, "a", newline="") as csvfile:
                            writer = csv.DictWriter(csvfile, fieldnames=delay_results[0].keys())
                            writer.writerow(result_dict)

                res_df = pd.DataFrame(delay_results)
                fig = px.line(
                    res_df, 
                    x="mlayer_dist",
                    y="max_total_delay",
                    color="mlayer_idx",
                    markers=True,
                )
                fig.write_image(f"ubump_pitch_{design_info.package_info.ubump_info.pitch}_mlayer_sens_study.png")
                fig = px.line(
                    res_df,
                    x="via_factor",
                    y="max_total_delay",
                    markers=True,
                )
                fig.write_image(f"ubump_pitch_{design_info.package_info.ubump_info.pitch}_via_factor_sens_study.png")
                fig = px.line(
                    res_df,
                    x="ubump_factor",
                    y="max_total_delay",
                    markers=True,
                )
                fig.write_image(f"ubump_pitch_{design_info.package_info.ubump_info.pitch}_via_factor_sens_study.png")
                # fig.show()
    else: 
        for process_info in process_infos:
            ####################### INIT DATA STRUCTS #######################
            design_info.process_info = process_info
            ####################### BUFFER DOMAIN SPACE EXPLORATION #######################
            # Written from the tech_info struct out to spice files
            # Maybe we can get rid of tech_info ? Lets try
            for ubump_info in ubump_infos:
                
                design_info.package_info = PackageInfo( 
                    ubump_info=ubump_info,
                    esd_rc_params=esd_rc_params,
                )
                # design_info.calc_add_wlen()

                # This function initializes subcircuits / libraries and writes out to spice files
                design_info = spice_simulation_setup(design_info)


                target_freq = 1000
                final_df_rows = []
                final_fig = subplots.make_subplots(cols=len(stage_range),rows=1)
                cur_best_cost = sys.float_info.max 
                best_sp_run = None

                # if design_info.nocs:
                #     noc_len = len(design_info.nocs)
                # else:
                #     noc_len = 0
                # for noc_idx in range(noc_len + 1):
                for add_wlen in add_wlens:
                    for stage_idx, n_stages in enumerate(stage_range):
                        total_nstages = 1 + n_stages + design_info.bot_die_nstages
                        # if n_stages % 2 != 0:
                        fanout_sweep_fig = go.Figure()
                        for buff_fanout in fanout_range:
                            final_df_row = {}
                            # write_loaded_driver_sp_sim(num_stages=n_stages, buff_fanout=buff_fanout, targ_freq=1000)
                            ### OPT PN SIZES BEFORE RUNNING SIM ###
                            sim_success = False
                            cur_tfreq = target_freq
                            parse_flags = {
                                "voltage": True,
                                "delay": True,
                            }
                            show_flags = {
                                "voltage": False,
                                "delay": False,
                            }
                            while not sim_success and cur_tfreq > 0:
                                # print(f"Running sim for {n_stages} stages, {buff_fanout} fanout, {cur_tfreq} target freq")
                                write_pn_sizing_opt_sp_sim(design_info, num_stages=n_stages, buff_fanout=buff_fanout, add_wlen=add_wlen, targ_freq=cur_tfreq)
                                pn_sim = {
                                    "sp_work_dir":"ubump_ic_driver",
                                    "sim_sp_files": ["opt_pn_ubump_ic_driver.sp"]
                                }
                                run_spice(**pn_sim)

                                try:
                                    sp_run_df, sp_run_info, opt_sp_sim_df = parse_sp_output(design_info, parse_flags, buff_fanout, n_stages, os.path.join(spice_info.sp_dir,spice_info.sp_sim_title,"opt_pn_ubump_ic_driver.lis"))
                                    sim_success = True
                                except:
                                    cur_tfreq /= 2

                            plot_sp_run(show_flags, sp_run_info, sp_run_df)

                            ### WRITE SIM WITH OPTIMIZED PN VALUES ###
                            write_loaded_driver_sp_sim(design_info=design_info, num_stages=n_stages, buff_fanout=buff_fanout, add_wlen=add_wlen, targ_freq=cur_tfreq, in_sp_sim_df=opt_sp_sim_df)
                            sims = {
                                "sp_work_dir":"ubump_ic_driver",
                                "sim_sp_files": [f"{spice_info.sp_sim_title}.sp"]
                            }
                            _ = run_spice(**sims)
                            print("**************************************************************************************************")
                            print(f"BUFF FANOUT: {buff_fanout}, NUM STAGES: {n_stages}")
                            # sys.exit(1)
                            # sp_run_df contains the Voltage information for each node in the circuit
                            # sp_run_info is the information that is a superset of sp_sim_df, with both the single run information and the information for each inverter
                            # sp_sim_df is the information for each inverter in the circuit in form of dataframe
                            sp_run_df, sp_run_info, sp_sim_df = parse_sp_output(design_info, parse_flags, buff_fanout, n_stages, spice_info.sp_sim_outfile)                        
                            sp_sim_df["pmos_width"] = opt_sp_sim_df["pmos_width"]
                            sp_sim_df["nmos_width"] = opt_sp_sim_df["nmos_width"]
                            # from the pmos, nmos info and the fanout of each stage of the circuit calculate the area
                            ################# AREA CALCULATION #################
                            inv_areas = []
                            for i, row in sp_sim_df.iterrows():
                                inv_mult_factor = (buff_fanout ** i) if i != total_nstages - 1 else 1
                                # multiply the fanout factor by the
                                nfet_tx_size = int(float(row["nmos_width"]) * inv_mult_factor)
                                pfet_tx_size = int(float(row["pmos_width"]) * inv_mult_factor)
                                # print(inv_mult_factor, nfet_tx_size, pfet_tx_size)
                                inv_area = (finfet_tx_area_model(nfet_tx_size) + finfet_tx_area_model(pfet_tx_size))*(design_info.process_info.tx_geom_info.min_width_tx_area*1e-6)
                                inv_areas.append(inv_area)
                            sp_sim_df["area"] = inv_areas
                            sp_run_info["inv_chain_area"] = sum(inv_areas[1:len(inv_areas)])
                            cur_cost = calc_cost(design_info, cost_fx_exps, sp_run_info)
                            final_df_row["cost"] = cur_cost
                            final_df_row["buff_fanout"] = buff_fanout
                            final_df_row["n_stages"] = n_stages
                            # if noc_idx >= noc_len:
                            #     final_df_row["add_wire_length"] = 0
                            # else:
                            #     final_df_row["add_wire_length"] = design_info.nocs[noc_idx].add_wire_len
                            final_df_row["add_wire_length"] = add_wlen
                            final_df_row["e2e_max_prop_delay"] = sp_run_info["total_max_prop_delay"]
                            final_df_row["area"] = round(sp_run_info["inv_chain_area"],4)
                            

                            final_df_rows.append(final_df_row)
                            print("\n".join(get_df_output_lines(sp_sim_df)))
                            if cur_cost < cur_best_cost:
                                cur_best_cost = cur_cost
                                print(f"NEW BEST COST: {cur_best_cost}")
                                best_sp_run = sp_run_info
                                best_sp_run_df = sp_sim_df
                                print("**************************************************************************************************")
                            bar_fig = plot_sp_run(show_flags, sp_run_info, sp_run_df)
                            for trace in bar_fig.data:
                                fanout_sweep_fig.add_trace(trace)

                        time_def_unit = next(iter({k:v for k,v in sp_sim_settings.unit_lookups["time"].items() if v == 1}), None)

                        fanout_sweep_fig.update_layout(
                            title=f"Num Stages: {sp_run_info['n_stages']} Max Prop Delay by Inv Stage",
                            xaxis_title='Stage Ratio',
                            yaxis_title=f"Time ({time_def_unit}s)",
                            barmode='group',
                            bargap=0.3
                        )

                        # fanout_sweep_fig.show()
                        for i in range(len(fanout_sweep_fig.data)):
                            final_fig.add_trace(fanout_sweep_fig.data[i], row=1, col=stage_idx+1)

                    print(f"****************************** Ubump Pitch {ubump_info.pitch} Ubump Cap {ubump_info.cap} Process Info {process_info.name} ********************************************")
                    print(f"BEST SP RUN:")
                    print(f"NUM STAGES: {best_sp_run['n_stages']}, BUFF FANOUT: {best_sp_run['buff_fanout']}")
                    for l in get_df_output_lines(best_sp_run_df):
                        print(l)
                    print("****************************************** SWEEP SUMMARY: ******************************************")
                    final_df = pd.DataFrame(final_df_rows)
                    for l in get_df_output_lines(final_df):
                        print(l)
                    # perform write of sp netlist and simulation of best sp run found
                    write_loaded_driver_sp_sim(design_info, best_sp_run["n_stages"], best_sp_run["buff_fanout"], targ_freq=cur_tfreq, add_wlen=add_wlen, in_sp_sim_df=best_sp_run_df)
                    _ = run_spice(**sims)
                    print("**************************************************************************************************")
                    # final_fig.show()
                    # sys.exit(1)

if __name__ == "__main__":
    main()
