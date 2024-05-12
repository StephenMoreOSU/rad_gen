import os
import sys
import argparse
import time
# import src.coffe.fpga as fpga
import src.coffe.new_fpga as fpga
import src.coffe.spice as spice
import src.coffe.new_tran_sizing as tran_sizing
import src.coffe.utils as utils
import src.coffe.vpr as coffe_vpr
import datetime
import math
import src.common.data_structs as rg_ds
import logging

from collections import namedtuple
from dataclasses import fields

def run_coffe_flow(coffe_info: rg_ds.Coffe):
    arch_folder = utils.create_output_dir(coffe_info.arch_name, coffe_info.fpga_arch_conf["fpga_arch_params"]['arch_out_folder'])

    is_size_transistors = not coffe_info.no_sizing
    size_hb_interfaces = coffe_info.size_hb_interfaces


    # Path to output telemetry file
    telemetry_file_path = os.path.join(arch_folder, "telemetry.csv")
    # Print the options to both terminal and report file
    report_file_path = os.path.join(arch_folder, "report.txt") 

    # hack to convert coffe_info into form that COFFE functions can accept (without refactoring)
    RunOpts = namedtuple('RunOpts', [_field for _field in type(coffe_info).__dataclass_fields__])
    args = RunOpts(*[getattr(coffe_info, _field) for _field in type(coffe_info).__dataclass_fields__])

    utils.print_run_options(args, report_file_path)

    # Print architecture and process details to terminal and report file
    utils.print_architecture_params(coffe_info.fpga_arch_conf["fpga_arch_params"], report_file_path)

    # Default_dir is the dir you ran COFFE from. COFFE will be switching directories 
    # while running HSPICE, this variable is so that we can get back to our starting point
    default_dir = os.getcwd()

    # Create an HSPICE interface
    spice_interface = spice.SpiceInterface()

    # Record start time
    total_start_time = time.time()

    # Create an FPGA instance
    fpga_inst = fpga.FPGA(coffe_info, args, spice_interface, telemetry_file_path)   
    #     coffe_info = coffe_info,
    #     run_options = args,
    #     spice_interface = spice_interface
    # )
        #coffe_info, args, spice_interface) #, telemetry_file_path)                 
    
    ###############################################################
    ## GENERATE FILES
    ###############################################################

    # Change to the architecture directory
    os.chdir(arch_folder)  

    # Generate FPGA and associated SPICE files
    fpga_inst.generate(size_hb_interfaces) 

    # Go back to the base directory
    os.chdir(default_dir)

    # Extract initial transistor sizes from file and overwrite the 
    # default initial sizes if this option was used.
    if coffe_info.initial_sizes != None: #"default" :
        utils.use_initial_tran_size(args.initial_sizes, fpga_inst, tran_sizing, coffe_info.fpga_arch_conf["fpga_arch_params"]['use_tgate'])

    # Print FPGA implementation details
    report_file = open(report_file_path, 'a')
    fpga_inst.print_details(report_file)  
    report_file.close()

    # Go to architecture directory
    os.chdir(arch_folder)

    ###############################################################
    ## TRANSISTOR SIZING
    ###############################################################

    sys.stdout.flush()

    # Size FPGA transistors
    if is_size_transistors:
        tran_sizing.size_fpga_transistors(fpga_inst, args, spice_interface)                                    
    else:
        # in case of disabling floorplanning there is no need to 
        # update delays before updating area. Tried both ways and 
        # they give exactly the same results
        #fpga_inst.update_delays(spice_interface)

        # same thing here no need to update area before calculating 
        # the lb_height value. Also tested and gave same results
        #fpga_inst.update_area()
        fpga_inst.lb_height = math.sqrt(fpga_inst.area_dict["tile"])
        fpga_inst.update_area()
        fpga_inst.compute_distance()
        fpga_inst.update_wires()
        fpga_inst.update_wire_rc()

        # commented this part to avoid doing floorplannig for
        # a non-sizing run
        #fpga_inst.determine_height()

        fpga_inst.update_delays(spice_interface)

    # Obtain Memory core power
    if coffe_info.fpga_arch_conf["fpga_arch_params"]['enable_bram_module'] == 1:
        fpga_inst.update_power(spice_interface)

    # Go back to the base directory
    os.chdir(default_dir)

    # Print out final COFFE report to file
    utils.print_summary(arch_folder, fpga_inst, total_start_time)

    # Print vpr architecure file
    # coffe_vpr.print_vpr_file(fpga_inst, arch_folder, coffe_info.fpga_arch_conf["fpga_arch_params"]['enable_bram_module'])
