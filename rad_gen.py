"""@package docstring
RADGen documentation can be found at https://rad-gen.readthedocs.io/en/latest/

"""


#import ..hammer.src.hammer_config 
# The below function parses hammer IR
# load_config_from_paths([config.yamls])

import argparse
import logging
import sys, os
import subprocess as sp
import shlex
import re

import json
import yaml


import time
import math

import copy

import csv
import pandas as pd

import src.common.data_structs as rg_ds
import src.common.utils as rg_utils


import datetime

from dataclasses import dataclass

from typing import List, Dict, Any, Tuple, Type, NamedTuple, Set, Optional, Union




# import gds funcs (for asap7)



###### ASIC DSE IMPORTS ######
import src.asic_dse.asic_dse as asic_dse


##### COFFE IMPORTS ##### 
import src.coffe.coffe as coffe
# import COFFE.coffe.utils as coffe_utils 


##### 3D IC IMPORTS ##### 
import src.ic_3d.ic_3d as ic_3d


rad_gen_log_fd = "rad_gen.log"
log_verbosity = 2
cur_env = os.environ.copy()

# ██╗      ██████╗  ██████╗  ██████╗ ██╗███╗   ██╗ ██████╗ 
# ██║     ██╔═══██╗██╔════╝ ██╔════╝ ██║████╗  ██║██╔════╝ 
# ██║     ██║   ██║██║  ███╗██║  ███╗██║██╔██╗ ██║██║  ███╗
# ██║     ██║   ██║██║   ██║██║   ██║██║██║╚██╗██║██║   ██║
# ███████╗╚██████╔╝╚██████╔╝╚██████╔╝██║██║ ╚████║╚██████╔╝
# ╚══════╝ ╚═════╝  ╚═════╝  ╚═════╝ ╚═╝╚═╝  ╚═══╝ ╚═════╝ 


def init_logger():
    # Init Logger
    logger = logging.getLogger("rad_gen_root")
    
    logger.root.setLevel(logging.DEBUG)
    # Create Stream Handler
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.DEBUG) # Set this handler to print out everything (debug is lowest level)
    file_handler = logging.FileHandler(os.path.abspath(f"rad_gen_logging_{rg_ds.create_timestamp()}.log"))
    file_handler.setLevel(logging.DEBUG)
    fmt = logging.Formatter('%(message)s')
    stream_handler.setFormatter(fmt)
    file_handler.setFormatter(fmt)     
    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)


    return logger

# ██████╗  █████╗ ██████╗      ██████╗ ███████╗███╗   ██╗    ███████╗██╗  ██╗███████╗ ██████╗    ███╗   ███╗ ██████╗ ██████╗ ███████╗███████╗
# ██╔══██╗██╔══██╗██╔══██╗    ██╔════╝ ██╔════╝████╗  ██║    ██╔════╝╚██╗██╔╝██╔════╝██╔════╝    ████╗ ████║██╔═══██╗██╔══██╗██╔════╝██╔════╝
# ██████╔╝███████║██║  ██║    ██║  ███╗█████╗  ██╔██╗ ██║    █████╗   ╚███╔╝ █████╗  ██║         ██╔████╔██║██║   ██║██║  ██║█████╗  ███████╗
# ██╔══██╗██╔══██║██║  ██║    ██║   ██║██╔══╝  ██║╚██╗██║    ██╔══╝   ██╔██╗ ██╔══╝  ██║         ██║╚██╔╝██║██║   ██║██║  ██║██╔══╝  ╚════██║
# ██║  ██║██║  ██║██████╔╝    ╚██████╔╝███████╗██║ ╚████║    ███████╗██╔╝ ██╗███████╗╚██████╗    ██║ ╚═╝ ██║╚██████╔╝██████╔╝███████╗███████║
# ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝      ╚═════╝ ╚══════╝╚═╝  ╚═══╝    ╚══════╝╚═╝  ╚═╝╚══════╝ ╚═════╝    ╚═╝     ╚═╝ ╚═════╝ ╚═════╝ ╚══════╝╚══════╝

def main(args: Optional[argparse.Namespace] = None) -> Union[None, Any]:
    global cur_env
    global rad_gen_log_fd
    global log_verbosity

    # Get logger into main
    logger = init_logger()

    #Clear rad gen log
    fd = open(rad_gen_log_fd, 'w')
    fd.close()

    # Parse command line arguments
    # args = parse_cli_args()

    args, default_arg_vals = rg_utils.parse_rad_gen_top_cli_args(args)

    # rad_gen_settings = init_structs(args)
    rad_gen_info = rg_utils.init_structs_top(args, default_arg_vals)

    arg_dict = vars(args)
    # If we want to return initialized data structs for a subtool, just return here
    if arg_dict["common.just_config_init"]:
        return rad_gen_info

    cur_env = os.environ.copy()

    """ Ex. args python3 rad_gen.py -s param_sweep/configs/noc_sweep.yml -c """
    if "asic_dse" in rad_gen_info.keys():
        if rad_gen_info["asic_dse"].mode.result_parse:
            asic_dse.compile_results(rad_gen_info["asic_dse"])
        # If a design sweep config file is specified, modify the flow settings for each design in sweep
        elif rad_gen_info["asic_dse"].mode.sweep_gen:
            asic_dse.design_sweep(rad_gen_info["asic_dse"])
        elif rad_gen_info["asic_dse"].mode.vlsi_flow.enable:
            asic_dse.run_asic_flow(rad_gen_info["asic_dse"])
    elif "coffe" in rad_gen_info.keys():
        # COFFE RUN OPTIONS
        coffe.run_coffe_flow(rad_gen_info["coffe"])
    elif "ic_3d" in rad_gen_info.keys():
        if rad_gen_info["ic_3d"].args.buffer_dse:
            # ic_3d.run_buffer_dse(rad_gen_info["ic_3d"])
            ic_3d.run_buffer_dse_updated(rad_gen_info["ic_3d"]) 
        if rad_gen_info["ic_3d"].args.pdn_modeling:
            ic_3d.run_pdn_modeling(rad_gen_info["ic_3d"])
        if rad_gen_info["ic_3d"].args.buffer_sens_study:
            ic_3d.run_buffer_sens_study(rad_gen_info["ic_3d"])
        if rad_gen_info["ic_3d"].args.debug_spice != None:
            debug_procs = [ 
                rg_ds.SpProcess(
                    top_sp_dir = rg_utils.clean_path("~/rad_gen/spice_sim"),
                    title = title
                ) for title in rad_gen_info["ic_3d"].cli_args.debug_spice
            ]
            for sp_process in debug_procs:
                ic_3d.run_spice_debug(rad_gen_info["ic_3d"], sp_process)
        
        


    
    
if __name__ == '__main__':
    main()