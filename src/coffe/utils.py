import sys
import os
import shutil
import time 
import datetime

import re
import yaml

# Constants used for formatting the subcircuit area/delay/power table. 
# These denote the widths of various columns - first (FIRS), last (LAST) and the rest (MIDL).
# We could use better libraries for pretty printing tables, but currently we use a simple method.
FIRS_COL_WIDTH = 30  #First solu
MIDL_COL_WIDTH = 22
LAST_COL_WIDTH = 22

VPR_DEL_COL_WIDTH = 75

#  ___    _   ___     ___ ___ _  _   ___  _   ___  ___ ___ _  _  ___   _   _ _____ ___ _    ___ 
# | _ \  /_\ |   \   / __| __| \| | | _ \/_\ | _ \/ __|_ _| \| |/ __| | | | |_   _|_ _| |  / __|
# |   / / _ \| |) | | (_ | _|| .` | |  _/ _ \|   /\__ \| || .` | (_ | | |_| | | |  | || |__\__ \
# |_|_\/_/ \_\___/   \___|___|_|\_| |_|/_/ \_\_|_\|___/___|_|\_|\___|  \___/  |_| |___|____|___/
#                                                                                     
#### Parsing Utilities, repeats from RAD-Gen TODO see if they can be removed ####

def check_for_valid_path(path):
    ret_val = False
    if os.path.exists(os.path.abspath(path)):
        ret_val = True
    else:
        raise FileNotFoundError(f"ERROR: {path} does not exist")
    return ret_val

def handle_error(fn, expected_vals: set=None):
    # for fn in funcs:
    if not fn() or (expected_vals is not None and fn() not in expected_vals):
        sys.exit(1)
            
def sanitize_config(config_dict) -> dict:
    """
        Modifies values of yaml config file to do the following:
        - Expand relative paths to absolute paths
    """    
    for param, value in config_dict.copy().items():
        if("path" in param or "sram_parameters" in param):
            if isinstance(value, list):
                config_dict[param] = [os.path.realpath(os.path.expanduser(v)) for v in value]
            elif isinstance(value, str):
                config_dict[param] = os.path.realpath(os.path.expanduser(value))
            else:
                pass
    return config_dict

def parse_yml_config(yaml_file: str) -> dict:
    """
        Takes in possibly unsafe path and returns a sanitized config
    """
    safe_yaml_file = os.path.realpath(os.path.expanduser(yaml_file))
    handle_error(lambda: check_for_valid_path(safe_yaml_file), {True : None})
    with open(safe_yaml_file, 'r') as f:
        config = yaml.safe_load(f)
    
    return sanitize_config(config)

#### end of duplicates


def compare_tfall_trise(tfall, trise):
    """ Compare tfall and trise and returns largest value or -1.0
        -1.0 is return if something went wrong in SPICE """
    
    # Initialize output delay
    delay = -1.0
    
    # Compare tfall and trise
    if (tfall == 0.0) or (trise == 0.0):
        # Couldn't find one of the values in output
        # This is an error because maybe SPICE failed
        delay = -1.0
    elif tfall > trise:
        if tfall > 0.0:
            # tfall is positive and bigger than the trise, this is a valid result
            delay = tfall
        else:
            # Both tfall and trise are negative, this is an invalid result
            delay = -1.0
    elif trise >= tfall:
        if trise > 0.0:
            # trise is positive and larger or equal to tfall, this is value result
            delay = trise
        else:
            delay = -1.0
    else:
        delay = -1.0
        
    return delay
   
    
def print_area_and_delay(report_file, fpga_inst):
    """ Print area and delay per subcircuit """
    
    print_and_write(report_file, "  SUBCIRCUIT AREA, DELAY & POWER")
    print_and_write(report_file, "  ------------------------------")
    
    area_dict = fpga_inst.area_dict

    # I'm using 'ljust' to create neat columns for printing this data. 
    # If subcircuit names are changed, it might make this printing function 
    # not work as well. The 'ljust' constants would have to be adjusted accordingly.
    
    # Print the header
    print_and_write(report_file, "  Subcircuit".ljust(32) + "Area (um^2)".ljust(MIDL_COL_WIDTH) + "Delay (ps)".ljust(MIDL_COL_WIDTH) + "tfall (ps)".ljust(MIDL_COL_WIDTH) + "trise (ps)".ljust(MIDL_COL_WIDTH) + "Power at 250MHz (uW)".ljust(LAST_COL_WIDTH)) 
    
    area_fac: float = 1e6
    del_fac: float = 1e-12
    pwr_fac: float = 1e-6
    sig_figs: int = 3
    
    def ckt_print_and_write(report_file, ckts_key: str = None, ckt_list: list = None):
        del_keys = ["delay", "tfall", "trise"]
        if ckts_key and getattr(fpga_inst, ckts_key):
            ckt_iter = getattr(fpga_inst, ckts_key)
        elif ckt_list:
            ckt_iter = ckt_list
        else:
            return
        for ckt in ckt_iter:
            for area_key in [ckt.sp_name, f"{ckt.sp_name}_sram"]:
                # Don't print out sram versions of things that don't have sram components
                if "sram" in area_key and area_dict.get(area_key) is None:
                    continue
                ckt_name: str = ckt.sp_name if "sram" not in area_key else ckt.sp_name + "(with_sram)"
                ckt_name_ele: str = f"  {ckt_name:<{FIRS_COL_WIDTH}}"

                # if "ff" in ckt_name:
                #     try:
                #         area_ele: str = f"{round(area_dict["ff"]/area_fac, sig_figs):<{MIDL_COL_WIDTH}}"
                #         del_str: str = f"{'n/a':<{MIDL_COL_WIDTH}}"
                #         pwr_str: str = f"{'n/a':<{MIDL_COL_WIDTH}}"
                #     except:
                #         area_ele: str = f"{'n/a':<{MIDL_COL_WIDTH}}"
                #         del_str: str = f"{'n/a':<{MIDL_COL_WIDTH}}"
                #         pwr_str: str = f"{'n/a':<{MIDL_COL_WIDTH}}"
                
                # Area
                try:
                    area_ele: str = f"{round(area_dict[area_key]/area_fac, sig_figs):<{MIDL_COL_WIDTH}}"
                except:
                    area_ele: str = f"{'n/a':<{MIDL_COL_WIDTH}}"
                # Delay
                del_str: str = ""
                for del_key in del_keys:
                    try:
                        del_str += f"{round(getattr(ckt, del_key)/del_fac, sig_figs):<{MIDL_COL_WIDTH}}"
                    except:
                        del_str += f"{'n/a':<{MIDL_COL_WIDTH}}"
                # Power
                try:
                    pwr_str: str = f"{round(ckt.power/pwr_fac, sig_figs):<{LAST_COL_WIDTH}}"
                except:
                    pwr_str: str = f"{'n/a':<{LAST_COL_WIDTH}}"
                print_and_write(
                    report_file, 
                    ckt_name_ele + area_ele + del_str + pwr_str,
                )



    for ckts_key in ["sb_muxes", "cb_muxes", "local_muxes", "local_ble_outputs", "general_ble_outputs", "flip_flops", "luts"]:
        ckt_print_and_write(report_file, ckts_key)

    # Get LUT input names so that we can print inputs in sorted order
    lut_input_names = list(fpga_inst.lut_inputs.keys())
    lut_input_names.sort()
      
    # LUT inputs
    for input_name in lut_input_names:
        ckt_print_and_write(report_file, ckt_list = fpga_inst.lut_inputs[input_name]) # change to sp_name
        # LUT input drivers
        # for lut_input_drivers in fpga_inst.lut_input_drivers.keys():
        ckt_print_and_write(report_file, ckt_list = fpga_inst.lut_input_drivers[input_name])
        # LUT input not drivers
        ckt_print_and_write(report_file, ckt_list = fpga_inst.lut_input_not_drivers[input_name])

    # Carry chain    
    if fpga_inst.specs.enable_carry_chain == 1:
        for cc_ckt_key in ["carry_chains", "carry_chain_periphs", "carry_chain_muxes", "carry_chain_inter_clusters"]:
            ckt_print_and_write(report_file, cc_ckt_key)

        if fpga_inst.specs.carry_chain_type == "skip":
            for cc_skip_ckt_key in ["carry_chain_skip_ands", "carry_chain_skip_muxes"]:
                ckt_print_and_write(report_file, cc_skip_ckt_key)

    for hardblock in fpga_inst.hardblocklist:
        # TODO implement hardblocks
        pass
        ############################################
        ## Size dedicated routing links
        ############################################
        # if hardblock.parameters['num_dedicated_outputs'] > 0:
        #     print_and_write(report_file, ("  " + str(hardblock.parameters['name']).strip()+ "_dedicated_out").ljust(FIRS_COL_WIDTH) + str(round(fpga_inst.area_dict[hardblock.dedicated.sp_name]/1e6,3)).ljust(MIDL_COL_WIDTH) + 
        #         str(round(hardblock.dedicated.delay/1e-12,4)).ljust(MIDL_COL_WIDTH) + str(round(hardblock.dedicated.tfall/1e-12,4)).ljust(MIDL_COL_WIDTH) + 
        #         str(round(hardblock.dedicated.trise/1e-12,4)).ljust(MIDL_COL_WIDTH) + str(hardblock.dedicated.power/1e-6).ljust(LAST_COL_WIDTH))
        
        # print_and_write(report_file, (str("  " + hardblock.parameters['name']) + "_mux").ljust(FIRS_COL_WIDTH) + str(round(fpga_inst.area_dict[hardblock.mux.sp_name +"_sram"]/1e6,3)).ljust(MIDL_COL_WIDTH) + 
        #     str(round(hardblock.mux.delay/1e-12,4)).ljust(MIDL_COL_WIDTH) + str(round(hardblock.mux.tfall/1e-12,4)).ljust(MIDL_COL_WIDTH) + str(round(hardblock.mux.trise/1e-12,4)).ljust(MIDL_COL_WIDTH) + 
        #     str(hardblock.mux.power/1e-6).ljust(LAST_COL_WIDTH))

    if fpga_inst.specs.enable_bram_block == 0:
        print_and_write(report_file, "\n")
        return 


    # RAM

    # RAM local input mux
    print_and_write(report_file, "  " + fpga_inst.RAM.RAM_local_mux.name.ljust(FIRS_COL_WIDTH) + str(round(fpga_inst.area_dict["ram_local_mux_total"]/1e6,3)).ljust(MIDL_COL_WIDTH) + 
        str(round(fpga_inst.RAM.RAM_local_mux.delay/1e-12,4)).ljust(MIDL_COL_WIDTH) + str(round(fpga_inst.RAM.RAM_local_mux.tfall/1e-12,4)).ljust(MIDL_COL_WIDTH) + 
        str(round(fpga_inst.RAM.RAM_local_mux.trise/1e-12,4)).ljust(MIDL_COL_WIDTH) + str(fpga_inst.RAM.RAM_local_mux.power/1e-6).ljust(LAST_COL_WIDTH))
    
    # Row decoder:
    stage1_delay = 0.0
    stage0_delay = 0.0
    stage2_delay = 0.0
    stage3_delay = 0.0
    stage0_delay = fpga_inst.RAM.rowdecoder_stage0.delay

    if fpga_inst.RAM.valid_row_dec_size3 == 1:
        stage1_delay = fpga_inst.RAM.rowdecoder_stage1_size3.delay
    if fpga_inst.RAM.valid_row_dec_size2 == 1:
        if fpga_inst.RAM.rowdecoder_stage1_size2.delay > stage1_delay:
            stage1_delay = fpga_inst.RAM.rowdecoder_stage1_size2.delay
    stage3_delay = fpga_inst.RAM.rowdecoder_stage3.delay

    row_decoder_delay =  stage0_delay + stage1_delay + stage3_delay + stage2_delay

    print_and_write(report_file, "  Row Decoder".ljust(FIRS_COL_WIDTH) + str(round(fpga_inst.area_dict["decoder"]/1e6,3)).ljust(MIDL_COL_WIDTH) + str(round(row_decoder_delay/1e-12,4)).ljust(MIDL_COL_WIDTH) + 
        "n/m".ljust(MIDL_COL_WIDTH) + "n/m".ljust(MIDL_COL_WIDTH) + "n/m".ljust(LAST_COL_WIDTH))    

    print("  Power Breakdown: ".ljust(FIRS_COL_WIDTH) + "stage0".ljust(24)+ str(round(fpga_inst.RAM.rowdecoder_stage0.power/1e-6,4)).ljust(LAST_COL_WIDTH))

    if fpga_inst.RAM.valid_row_dec_size2 == 1:
        print("  Power Breakdown: ".ljust(FIRS_COL_WIDTH) + "stage1".ljust(24)+ str(round(fpga_inst.RAM.rowdecoder_stage1_size2.power/1e-6,4)).ljust(LAST_COL_WIDTH))
    if fpga_inst.RAM.valid_row_dec_size3 == 1:
        print("  Power Breakdown: ".ljust(FIRS_COL_WIDTH) + "stage1".ljust(24)+ str(round(fpga_inst.RAM.rowdecoder_stage1_size3.power/1e-6,4)).ljust(LAST_COL_WIDTH))
    print("  Power Breakdown: ".ljust(FIRS_COL_WIDTH) + "stage2".ljust(24)+ str(round(fpga_inst.RAM.rowdecoder_stage3.power/1e-6,4)).ljust(LAST_COL_WIDTH))        

    # Configurable decoder:
    configdelay = fpga_inst.RAM.configurabledecoderi.delay 

    if fpga_inst.RAM.cvalidobj1 !=0 and fpga_inst.RAM.cvalidobj2 !=0:
        configdelay += max(fpga_inst.RAM.configurabledecoder3ii.delay, fpga_inst.RAM.configurabledecoder2ii.delay)
    elif fpga_inst.RAM.cvalidobj1 !=0:
        configdelay += fpga_inst.RAM.configurabledecoder3ii.delay
    else:
        configdelay += fpga_inst.RAM.configurabledecoder2ii.delay

    # Column decoder:
    print_and_write(report_file, "  Column Decoder".ljust(FIRS_COL_WIDTH) + str(round(fpga_inst.area_dict["columndecoder_total"]/1e6,3)).ljust(MIDL_COL_WIDTH) + 
        str(round(fpga_inst.RAM.columndecoder.delay/1e-12,4)).ljust(MIDL_COL_WIDTH) + str(round(fpga_inst.RAM.columndecoder.tfall/1e-12,4)).ljust(MIDL_COL_WIDTH) + 
        str(round(fpga_inst.RAM.columndecoder.trise/1e-12,4)).ljust(MIDL_COL_WIDTH) + str(fpga_inst.RAM.columndecoder.power/1e-6).ljust(LAST_COL_WIDTH))
    print_and_write(report_file, "  Configurable Decoder".ljust(FIRS_COL_WIDTH) + str(round(fpga_inst.area_dict["configurabledecoder"]/1e6,3)).ljust(MIDL_COL_WIDTH) + 
        str(round(configdelay/1e-12,4)).ljust(MIDL_COL_WIDTH) + "n/m".ljust(MIDL_COL_WIDTH) + "n/m".ljust(MIDL_COL_WIDTH) + "n/m".ljust(LAST_COL_WIDTH))
    print_and_write(report_file, "  CD driver delay ".ljust(FIRS_COL_WIDTH) + "n/a".ljust(MIDL_COL_WIDTH) + 
        str(round(fpga_inst.RAM.configurabledecoderiii.delay/1e-12,4)).ljust(MIDL_COL_WIDTH) + "n/m".ljust(MIDL_COL_WIDTH) + "n/m".ljust(MIDL_COL_WIDTH) + "n/m".ljust(LAST_COL_WIDTH))

    print("  Power Breakdown: ".ljust(FIRS_COL_WIDTH) + "stage0".ljust(24)+ str(round(fpga_inst.RAM.configurabledecoderi.power/1e-6,4)).ljust(LAST_COL_WIDTH))
    if fpga_inst.RAM.cvalidobj2 !=0:
        print("  Power Breakdown: ".ljust(FIRS_COL_WIDTH) + "stage1".ljust(24)+ str(round(fpga_inst.RAM.configurabledecoder2ii.power/1e-6,4)).ljust(LAST_COL_WIDTH))
    if fpga_inst.RAM.cvalidobj1 !=0:    
        print("  Power Breakdown: ".ljust(FIRS_COL_WIDTH) + "stage1".ljust(24)+ str(round(fpga_inst.RAM.configurabledecoder3ii.power/1e-6,4)).ljust(LAST_COL_WIDTH))
    print("  Power Breakdown: ".ljust(FIRS_COL_WIDTH) + "stage2".ljust(24)+ str(round(fpga_inst.RAM.configurabledecoderiii.power/1e-6,4)).ljust(LAST_COL_WIDTH))


    # BRAM output crossbar:
    print_and_write(report_file, "  Output Crossbar".ljust(FIRS_COL_WIDTH) + str(round(fpga_inst.area_dict["pgateoutputcrossbar_sram"]/1e6,3)).ljust(MIDL_COL_WIDTH) + 
        str(round(fpga_inst.RAM.pgateoutputcrossbar.delay/1e-12,4)).ljust(MIDL_COL_WIDTH) + str(round(fpga_inst.RAM.pgateoutputcrossbar.tfall/1e-12,4)).ljust(MIDL_COL_WIDTH) + str(round(fpga_inst.RAM.pgateoutputcrossbar.trise/1e-12,4)).ljust(MIDL_COL_WIDTH) + str(fpga_inst.RAM.pgateoutputcrossbar.power/1e-6).ljust(LAST_COL_WIDTH))
    
    # reporting technology-specific part of the BRAM (sense amplifier, precharge/predischarge and write driver/bitline charge)
    if fpga_inst.RAM.memory_technology == "SRAM":
        print_and_write(report_file, "  sense amp".ljust(FIRS_COL_WIDTH) + str(round(fpga_inst.area_dict["samp_total"]/1e6,3)).ljust(MIDL_COL_WIDTH) + 
            str(round((fpga_inst.RAM.samp.delay + fpga_inst.RAM.samp_part2.delay)/1e-12,4)).ljust(MIDL_COL_WIDTH) + str(round(fpga_inst.RAM.samp.tfall/1e-12,4)).ljust(MIDL_COL_WIDTH) + 
            str(round(fpga_inst.RAM.samp.trise/1e-12,4)).ljust(MIDL_COL_WIDTH) + str(fpga_inst.RAM.samp.power/1e-6).ljust(LAST_COL_WIDTH))
    
        print_and_write(report_file, "  precharge".ljust(FIRS_COL_WIDTH) + str(round(fpga_inst.area_dict["precharge_total"]/1e6,3)).ljust(MIDL_COL_WIDTH) + 
            str(round(fpga_inst.RAM.precharge.delay/1e-12,4)).ljust(MIDL_COL_WIDTH) + str(round(fpga_inst.RAM.precharge.tfall/1e-12,4)).ljust(MIDL_COL_WIDTH) + 
            str(round(fpga_inst.RAM.precharge.trise/1e-12,4)).ljust(MIDL_COL_WIDTH) + str(fpga_inst.RAM.precharge.power/1e-6).ljust(LAST_COL_WIDTH))

        print_and_write(report_file, "  Write driver".ljust(FIRS_COL_WIDTH) + str(round(fpga_inst.area_dict["writedriver_total"]/1e6,3)).ljust(MIDL_COL_WIDTH) + 
            str(round(fpga_inst.RAM.writedriver.delay/1e-12,4)).ljust(MIDL_COL_WIDTH) + str(round(fpga_inst.RAM.writedriver.tfall/1e-12,4)).ljust(MIDL_COL_WIDTH) + 
            str(round(fpga_inst.RAM.writedriver.trise/1e-12,4)).ljust(MIDL_COL_WIDTH) + str(fpga_inst.RAM.writedriver.power/1e-6).ljust(LAST_COL_WIDTH))
    else:
        print_and_write(report_file, "  Sense Amp".ljust(FIRS_COL_WIDTH) + " ".ljust(MIDL_COL_WIDTH) + str(round(fpga_inst.RAM.mtjsamp.delay/1e-12,4)).ljust(MIDL_COL_WIDTH) + 
            str(round(fpga_inst.RAM.mtjsamp.tfall/1e-12,4)).ljust(MIDL_COL_WIDTH) + str(round(fpga_inst.RAM.mtjsamp.trise/1e-12,4)).ljust(MIDL_COL_WIDTH) + str(fpga_inst.RAM.mtjsamp.power/1e-6).ljust(LAST_COL_WIDTH))
    
        print_and_write(report_file, "  BL Charge".ljust(FIRS_COL_WIDTH) + " ".ljust(MIDL_COL_WIDTH) + str(round(fpga_inst.RAM.blcharging.delay/1e-12,4)).ljust(MIDL_COL_WIDTH) + 
            str(round(fpga_inst.RAM.blcharging.tfall/1e-12,4)).ljust(MIDL_COL_WIDTH) + str(round(fpga_inst.RAM.blcharging.trise/1e-12,4)).ljust(MIDL_COL_WIDTH) + 
            str(fpga_inst.RAM.blcharging.power/1e-6).ljust(LAST_COL_WIDTH))

        print_and_write(report_file, "  BL Discharge".ljust(FIRS_COL_WIDTH) + " ".ljust(MIDL_COL_WIDTH) + str(round(fpga_inst.RAM.bldischarging.delay/1e-12,4)).ljust(MIDL_COL_WIDTH) + 
            str(round(fpga_inst.RAM.bldischarging.tfall/1e-12,4)).ljust(MIDL_COL_WIDTH) + str(round(fpga_inst.RAM.bldischarging.trise/1e-12,4)).ljust(MIDL_COL_WIDTH) + 
            str(fpga_inst.RAM.bldischarging.power/1e-6).ljust(LAST_COL_WIDTH))
    
    # wordline driver:
    print_and_write(report_file, "  Wordline driver".ljust(FIRS_COL_WIDTH) + str(round(fpga_inst.area_dict["wordline_driver"]/1e6,3)).ljust(MIDL_COL_WIDTH) + 
        str(round(fpga_inst.RAM.wordlinedriver.delay/1e-12,4)).ljust(MIDL_COL_WIDTH) + str(round(fpga_inst.RAM.wordlinedriver.tfall/1e-12,4)).ljust(MIDL_COL_WIDTH) + 
        str(round(fpga_inst.RAM.wordlinedriver.trise/1e-12,4)).ljust(MIDL_COL_WIDTH) + str(fpga_inst.RAM.wordlinedriver.power/1e-6).ljust(LAST_COL_WIDTH))
    
    # Level shifter: This was measured outside COFFE by kosuke.
    print_and_write(report_file, "  Level Shifter".ljust(FIRS_COL_WIDTH) + str(round(fpga_inst.area_dict["level_shifter"]/1e6,3)).ljust(MIDL_COL_WIDTH) + str(round(32.3,4)).ljust(MIDL_COL_WIDTH) + 
        str(round(32.3,4)).ljust(MIDL_COL_WIDTH) + str(round(32.3,4)).ljust(MIDL_COL_WIDTH) + str(2.26e-7/1e-6).ljust(LAST_COL_WIDTH))

    print_and_write(report_file, "\n")


def print_power(report_file, fpga_inst):
    """ Print power per subcircuit """
    
    print("  SUBCIRCUIT POWER AT 250MHz (uW)")
    print("  --------------------------")

    for sb_mux in fpga_inst.sb_muxes:
        print("  " + sb_mux.name.ljust(22) + str(sb_mux.power/1e-6))
    # print("  " + fpga_inst.sb_mux.name.ljust(22) + str(fpga_inst.sb_mux.power/1e-6)) 
    print("  " + fpga_inst.cb_mux.name.ljust(22) + str(fpga_inst.cb_mux.power/1e-6)) 
    print("  " + fpga_inst.logic_cluster.local_mux.name.ljust(22) + str(fpga_inst.logic_cluster.local_mux.power/1e-6)) 
    print("  " + fpga_inst.logic_cluster.ble.local_output.name.ljust(22) + str(fpga_inst.logic_cluster.ble.local_output.power/1e-6)) 
    print("  " + fpga_inst.logic_cluster.ble.general_output.name.ljust(22) + str(fpga_inst.logic_cluster.ble.general_output.power/1e-6)) 

    # Figure out LUT power
    lut_input_names = list(fpga_inst.logic_cluster.ble.lut.input_drivers.keys())
    lut_input_names.sort()
    for input_name in lut_input_names:
        lut_input = fpga_inst.logic_cluster.ble.lut.input_drivers[input_name]
        path_power = lut_input.power
        driver_power = lut_input.driver.power
        not_driver_power = lut_input.not_driver.power
        print("  " + ("lut_" + input_name).ljust(22) + str((path_power + driver_power + not_driver_power)/1e-6))
        print("  " + ("  lut_" + input_name + "_data_path").ljust(22) + str(path_power/1e-6))
        print("  " + ("  lut_" + input_name + "_driver").ljust(22) + str(driver_power/1e-6))
        print("  " + ("  lut_" + input_name + "_driver_not").ljust(22) + str(not_driver_power/1e-6))

    print("")

    
def print_block_area(report_file, fpga_inst):
        """ Print physical area of important blocks (like SB, CB, LUT, etc.) in um^2 """
        
        scale_fac: float = 1e6

        tile = fpga_inst.area_dict["tile"] / scale_fac
        lut = fpga_inst.area_dict["lut_total"] / scale_fac
        ff = fpga_inst.area_dict["ff_total"] / scale_fac
        ble_output = fpga_inst.area_dict["ble_output_total"] / scale_fac
        local_mux = fpga_inst.local_mux.block_area / scale_fac
        cb = fpga_inst.cb_mux.block_area / scale_fac
        sb = fpga_inst.sb_mux.block_area / scale_fac
        cc = fpga_inst.area_dict["cc_area_total"] / scale_fac
        sanity_check = lut+ff+ble_output+local_mux+cb+sb


        empty_area = 0.0
        metal_pitch = fpga_inst.specs.gen_routing_metal_pitch
        metal_layers = fpga_inst.specs.gen_routing_metal_layers
        print_and_write(report_file, "  General routing metal pitch  = " + str(metal_pitch) + " nm")
        print_and_write(report_file, "  General routing metal layers  = " + str(metal_layers))
        if (metal_pitch > 0) and (metal_layers > 0):
            # TODO need to make this calculation for each wire type and it's own corresponding number of metal layers 
            # For now just hacking it and assuming all using same metal layer (works for stratix IV)
            num_tracks = int(sum(wire["num_tracks"] for wire in fpga_inst.specs.wire_types) / metal_layers) + 1 
            
            metal_dim = num_tracks * metal_pitch
            tile_width = fpga_inst.width_dict["tile"]
            tile_height = fpga_inst.lb_height
            print_and_write(report_file, "  Tile width  = " + str(round(tile_width,3)) + " nm")
            print_and_write(report_file, "  Tile height = " + str(round(tile_height,3)) + " nm")
            print_and_write(report_file, "  Width/Height needed by general routing metal = " + str(metal_dim) + " nm")
            if (tile_width < metal_dim) or (tile_height < metal_dim):
                print_and_write(report_file, "  Tile area is LIMITED by metal!")
                print_and_write(report_file, "  Tile area (Active) = " + str(round(tile,3)) + " um^2")
                tile_width = max(tile_width, metal_dim)
                tile_height = max(tile_height, metal_dim)
                empty_area = (tile_width * tile_height / 1e6) - tile
                tile = tile_width * tile_height / 1e6
                print_and_write(report_file, "  Tile area (Metal) = " + str(round(tile,3)) + " um^2")
                fpga_inst.area_dict["tile"] = tile_width * tile_height
            else:
                print_and_write(report_file, "  Tile area is NOT limited by metal!")
        print_and_write(report_file, "  ")



        if fpga_inst.specs.enable_bram_block == 1:
            ram = fpga_inst.area_dict["ram"]/1e6
            decod = fpga_inst.area_dict["decoder_total"]/1e6

            ramlocalmux = fpga_inst.area_dict["ram_local_mux_total"]/1e6

            ramcoldecode = fpga_inst.area_dict["columndecoder_sum"]/1e6

            ramconfdecode = (fpga_inst.area_dict["configurabledecoder"] * 2)/1e6

            ramoutputcbar = fpga_inst.area_dict["pgateoutputcrossbar_sram"] /1e6 

            if fpga_inst.RAM.memory_technology == "SRAM":

                prechargetotal = fpga_inst.area_dict["precharge_total"] /1e6 

                writedrivertotal = fpga_inst.area_dict["writedriver_total"] /1e6 

                samptotal = fpga_inst.area_dict["samp_total"] /1e6 
            else:
                cstotal = fpga_inst.area_dict["cs_total"] /1e6 

                writedrivertotal = fpga_inst.area_dict["writedriver_total"] /1e6 

                samptotal = fpga_inst.area_dict["samp_total"] /1e6 

            wordlinedrivera = fpga_inst.area_dict["wordline_total"] /1e6 

            levels = fpga_inst.area_dict["level_shifters"] /1e6 

            RAM_SB_TOTAL = fpga_inst.area_dict["RAM_SB"] / 1e6 
            RAM_CB_TOTAL = fpga_inst.area_dict["RAM_CB"] / 1e6 


            memcells = fpga_inst.area_dict["memorycell_total"] /1e6 
            if fpga_inst.RAM.memory_technology == "SRAM":
                ram_routing = ram - decod - ramlocalmux - ramcoldecode - ramconfdecode - ramoutputcbar - prechargetotal - writedrivertotal - samptotal - memcells - wordlinedrivera - levels
            else:
                ram_routing = ram - decod - ramlocalmux - ramcoldecode - ramconfdecode - ramoutputcbar - memcells - wordlinedrivera - writedrivertotal - samptotal - cstotal - levels

        print_and_write(report_file, "  TILE AREA CONTRIBUTIONS")
        print_and_write(report_file, "  -----------------------")
        print_and_write(report_file, "  Block".ljust(FIRS_COL_WIDTH) + "Total Area (um^2)".ljust(MIDL_COL_WIDTH) + "Fraction of total tile area")
        print_and_write(report_file, "  Tile".ljust(FIRS_COL_WIDTH) + str(round(tile,3)).ljust(MIDL_COL_WIDTH) + "100%")
        print_and_write(report_file, "  LUT".ljust(FIRS_COL_WIDTH) + str(round(lut,3)).ljust(MIDL_COL_WIDTH) + str(round(lut/tile*100,3)) + "%")
        print_and_write(report_file, "  FF".ljust(FIRS_COL_WIDTH) + str(round(ff,3)).ljust(MIDL_COL_WIDTH) + str(round(ff/tile*100,3)) + "%")
        print_and_write(report_file, "  Carry Chain".ljust(FIRS_COL_WIDTH) + str(round(cc,3)).ljust(MIDL_COL_WIDTH) + str(round(cc/tile*100,3)) + "%")
        print_and_write(report_file, "  BLE output".ljust(FIRS_COL_WIDTH) + str(round(ble_output,3)).ljust(MIDL_COL_WIDTH) + str(round(ble_output/tile*100,3)) + "%")
        print_and_write(report_file, "  Local mux".ljust(FIRS_COL_WIDTH) + str(round(local_mux,3)).ljust(MIDL_COL_WIDTH) + str(round(local_mux/tile*100,3)) + "%")
        print_and_write(report_file, "  Connection block".ljust(FIRS_COL_WIDTH) + str(round(cb,3)).ljust(MIDL_COL_WIDTH) + str(round(cb/tile*100,3)) + "%")
        print_and_write(report_file, "  Switch block".ljust(FIRS_COL_WIDTH) + str(round(sb,3)).ljust(MIDL_COL_WIDTH) + str(round(sb/tile*100,3)) + "%")
        
        print_and_write(report_file, "  Non-active".ljust(FIRS_COL_WIDTH) + str(round(empty_area,3)).ljust(MIDL_COL_WIDTH) + str(round(empty_area/tile*100,3)) + "%")
        print_and_write(report_file, "")
        if fpga_inst.specs.enable_bram_block == 1:
            print_and_write(report_file, "  RAM AREA CONTRIBUTIONS")
            print_and_write(report_file, "  -----------------------")
            print_and_write(report_file, "  Block".ljust(FIRS_COL_WIDTH) + "Total Area (um^2)".ljust(MIDL_COL_WIDTH) + "Fraction of RAM tile area")
            print_and_write(report_file, "  RAM".ljust(FIRS_COL_WIDTH) + str(round(ram,3)).ljust(MIDL_COL_WIDTH) + str(round(ram/ram*100,3)) + "%")
            print_and_write(report_file, "  RAM Local Mux".ljust(FIRS_COL_WIDTH) + str(round(ramlocalmux,3)).ljust(MIDL_COL_WIDTH) + str(round(ramlocalmux/ram*100,3)) + "%")
            print_and_write(report_file, "  Level Shifters".ljust(FIRS_COL_WIDTH) + str(round(levels,3)).ljust(MIDL_COL_WIDTH) + str(round(levels/ram*100,3)) + "%")
            print_and_write(report_file, "  Decoder".ljust(FIRS_COL_WIDTH) + str(round(decod,3)).ljust(MIDL_COL_WIDTH) + str(round(decod/ram*100,3)) + "%")
            print_and_write(report_file, "  WL driver".ljust(FIRS_COL_WIDTH) + str(round(wordlinedrivera,3)).ljust(MIDL_COL_WIDTH) + str(round(wordlinedrivera/ram*100,3)) + "%"            )
            print_and_write(report_file, "  Column Decoder".ljust(FIRS_COL_WIDTH) + str(round(ramcoldecode,3)).ljust(MIDL_COL_WIDTH) + str(round(ramcoldecode/ram*100,3)) + "%")
            print_and_write(report_file, "  Configurable Dec".ljust(FIRS_COL_WIDTH) + str(round(ramconfdecode,3)).ljust(MIDL_COL_WIDTH) + str(round(ramconfdecode/ram*100,3)) + "%")
            print_and_write(report_file, "  Output CrossBar".ljust(FIRS_COL_WIDTH) + str(round(ramoutputcbar,3)).ljust(MIDL_COL_WIDTH) + str(round(ramoutputcbar/ram*100,3)) + "%")
            if fpga_inst.RAM.memory_technology == "SRAM":
                print_and_write(report_file, "  Precharge Total".ljust(FIRS_COL_WIDTH) + str(round(prechargetotal,3)).ljust(MIDL_COL_WIDTH) + str(round(prechargetotal/ram*100,3)) + "%")
                print_and_write(report_file, "  Write Drivers".ljust(FIRS_COL_WIDTH) + str(round(writedrivertotal,3)).ljust(MIDL_COL_WIDTH) + str(round(writedrivertotal/ram*100,3)) + "%")
                print_and_write(report_file, "  Sense Amp Total ".ljust(FIRS_COL_WIDTH) + str(round(samptotal,3)).ljust(MIDL_COL_WIDTH) + str(round(samptotal/ram*100,3)) + "%")
            else:
                print_and_write(report_file, "  Column selectors".ljust(FIRS_COL_WIDTH) + str(round(cstotal,3)).ljust(MIDL_COL_WIDTH) + str(round(cstotal/ram*100,3)) + "%")
                print_and_write(report_file, "  Write Drivers".ljust(FIRS_COL_WIDTH) + str(round(writedrivertotal,3)).ljust(MIDL_COL_WIDTH) + str(round(writedrivertotal/ram*100,3)) + "%")
                print_and_write(report_file, "  Sense Amp Total ".ljust(FIRS_COL_WIDTH) + str(round(samptotal,3)).ljust(MIDL_COL_WIDTH) + str(round(samptotal/ram*100,3)) + "%")

            print_and_write(report_file, "  Memory Cells ".ljust(FIRS_COL_WIDTH) + str(round(memcells,3)).ljust(MIDL_COL_WIDTH) + str(round(memcells/ram*100,3)) + "%")
            print_and_write(report_file, "  RAM Routing".ljust(FIRS_COL_WIDTH) + str(round(ram_routing,3)).ljust(MIDL_COL_WIDTH) + str(round(ram_routing/ram*100,3)) + "%")
            print_and_write(report_file, "  RAM CB".ljust(FIRS_COL_WIDTH) + str(round(RAM_CB_TOTAL,3)).ljust(MIDL_COL_WIDTH) + str(round(RAM_CB_TOTAL/ram*100,3)) + "%")
            print_and_write(report_file, "  RAM SB".ljust(FIRS_COL_WIDTH) + str(round(RAM_SB_TOTAL,3)).ljust(MIDL_COL_WIDTH) + str(round(RAM_SB_TOTAL/ram*100,3)) + "%")
            print_and_write(report_file, "")
     

def print_hardblock_info(report_file, fpga_inst):
    print_and_write(report_file, "  HARDBLOCK INFORMATION")
    print_and_write(report_file, "  ---------------------")

    for hardblock in fpga_inst.hardblocklist:
        print_and_write(report_file, "  Name: " + hardblock.name)
        # The areas in area_dict and in the objects in fpga.py are in nm^2. But in this table,
        # we report areas in um^2. That's why we divide each value by 10^6.
        print_and_write(report_file, "  Core_area: " + str(hardblock.area/1e6))
        print_and_write(report_file, "  Local_mux_area: " + str(hardblock.parameters['num_gen_inputs'] * fpga_inst.area_dict[hardblock.mux.name]/1e6))
        print_and_write(report_file, "  Local_mux_area_with_sram: " + str(hardblock.parameters['num_gen_inputs'] * fpga_inst.area_dict[hardblock.mux.name + "_sram"]/1e6))
        if hardblock.parameters['num_dedicated_outputs'] > 0:
            print_and_write(report_file, "  Dedicated_output_routing_area: " + str(hardblock.parameters['num_dedicated_outputs'] * fpga_inst.area_dict[hardblock.name + "_ddriver"]/1e6))
        print_and_write(report_file, "  Total_area: " + str(fpga_inst.area_dict[hardblock.name + "_sram"]/1e6))
        print_and_write(report_file, "")


def print_vpr_delays(report_file, fpga_inst):

    print_and_write(report_file, "  VPR DELAYS")
    print_and_write(report_file, "  ----------")
    print_and_write(report_file, "  Path".ljust(VPR_DEL_COL_WIDTH) + "Delay (ps)")

    sb_mux_delays = [ f" {sb_mux.sp_name} Tdel (routing switch)".ljust(VPR_DEL_COL_WIDTH) + f"{sb_mux.delay}" for sb_mux in fpga_inst.sb_muxes]
    for sb_mux_delay in sb_mux_delays:
        print_and_write(report_file, sb_mux_delay)
    # print_and_write(report_file, "  Tdel (routing switch)".ljust(50) + str(fpga_inst.sb_mux.delay))

    cb_mux_delays = [ f" {cb_mux.sp_name} T_ipin_cblock (connection block mux)".ljust(VPR_DEL_COL_WIDTH) + f"{cb_mux.delay}" for cb_mux in fpga_inst.cb_muxes]
    for cb_mux_delay in cb_mux_delays:
        print_and_write(report_file, cb_mux_delay)
    local_mux_delays = [ f" {local_mux.sp_name} CLB input -> BLE input (local CLB routing)".ljust(VPR_DEL_COL_WIDTH) + f"{local_mux.delay}" for local_mux in fpga_inst.local_muxes]
    for local_mux_delay in local_mux_delays:
        print_and_write(report_file, local_mux_delay)
    ble_local_output_delays = [ f" {ble_local_output.sp_name} LUT output -> BLE input (local feedback)".ljust(VPR_DEL_COL_WIDTH) + f"{ble_local_output.delay}" for ble_local_output in fpga_inst.local_ble_outputs]
    for ble_local_output_delay in ble_local_output_delays:
        print_and_write(report_file, ble_local_output_delay)
    ble_gen_output_delays = [ f" {ble_gen_output.sp_name} LUT output -> CLB output (logic block output)".ljust(VPR_DEL_COL_WIDTH) + f"{ble_gen_output.delay}" for ble_gen_output in fpga_inst.general_ble_outputs]
    for ble_gen_output_delay in ble_gen_output_delays:
        print_and_write(report_file, ble_gen_output_delay)
    
    # Figure out LUT delays
    lut_input_names = list(fpga_inst.lut_inputs.keys())
    lut_input_names.sort()
    for input_name in lut_input_names:
        lut_input = fpga_inst.lut_inputs[input_name][0] #TODO add multi ckt support
        driver_delay = max(lut_input.driver.delay, lut_input.not_driver.delay)
        path_delay = lut_input.delay
        print_and_write(report_file, ("  lut_" + input_name).ljust(VPR_DEL_COL_WIDTH) + str(driver_delay + path_delay))
    
    if fpga_inst.specs.enable_bram_block == 1:
        print_and_write(report_file, "  RAM block frequency".ljust(VPR_DEL_COL_WIDTH) + str(fpga_inst.RAM.frequency))
        
    print_and_write(report_file, "")
 

def print_vpr_areas(report_file, fpga_inst):

    print_and_write(report_file, "  VPR AREAS")
    print_and_write(report_file, "  ----------")
    print_and_write(report_file, "  grid_logic_tile_area".ljust(50) + str(fpga_inst.area_dict["logic_cluster"] / fpga_inst.specs.min_width_tran_area))
    ipin_mux_size_keys = [key for key in list(fpga_inst.area_dict.keys()) if "ipin_mux_trans_size" in key]
    for ipin_mux_size_key in ipin_mux_size_keys:
        print_and_write(report_file, f"  {ipin_mux_size_key} (connection block mux)".ljust(50) + str(fpga_inst.area_dict[ipin_mux_size_key] / fpga_inst.specs.min_width_tran_area))
    switch_mux_size_keys = [key for key in list(fpga_inst.area_dict.keys()) if "switch_mux" in key]
    for switch_mux_size_key in switch_mux_size_keys:
        print_and_write(report_file, f"  {switch_mux_size_key} (routing switch)".ljust(50) + str(fpga_inst.area_dict[switch_mux_size_key] / fpga_inst.specs.min_width_tran_area))
    switch_buf_size_keys = [key for key in list(fpga_inst.area_dict.keys()) if "switch_buf" in key]
    for switch_buf_size_key in switch_buf_size_keys:
        print_and_write(report_file, f"  {switch_buf_size_key} (routing switch)".ljust(50) + str(fpga_inst.area_dict[switch_buf_size_key] / fpga_inst.specs.min_width_tran_area))
    print_and_write(report_file, "")


def sanatize_str_input_to_list(value):
    """Makes sure unneeded quotes arent included when a string of values is seperated by a space and saved into
    string seperated by spaces and surrouneded with quotes"""
    vals = (value.strip("\"")).split(" ")
    return vals

def check_hard_params(hard_params, run_options):
    """
    This function checks the hardblock/process parameters to make sure that all the parameters have been read in.
    Right now, this functions just checks really basic stuff like 
    checking for unset values
    """
    #These are optional parameters which have been determined to be optional for all run options
    optional_params = ["process_params_file","mode_signal","condensed_results_folder"]
    if(hard_params["partition_flag"] == False):
        optional_params.append("ptn_settings_file")
        #ungrouping regex is required to partition design
        optional_params.append("ungroup_regex")     
    if(not run_options.parallel_hb_flow and not run_options.parse_pll_hb_flow and not run_options.gen_hb_scripts):
        optional_params.append("parallel_hardblock_folder")
    if(not run_options.parallel_hb_flow):
        optional_params.append("mp_num_cores")
        optional_params.append("run_settings_file")
    # if(not run_options.parse_pll_hb_flow):
    #     optional_params.append("coffe_repo_path")
    

    #TODO make this sort of a documentation for each parameter
    for key,val in list(hard_params.items()):
        #Checks to see if value in parameter dict is unset, if its in the optional params list for this run type then it can be ignored
        if ((val == "" or val == -1 or val == -1.0 or val == []) and key not in optional_params):
            print(("param \"%s\" is unset, please go to your hardblock/process params file and set it" % (key)))
            sys.exit(1)
        elif(key == "pnr_tool" and val != "encounter" and val != "innovus" ):
            print("ERROR: pnr_tool must be set as either \"encounter\" or \"innovus\" ")
            sys.exit(1)
    if(hard_params["pnr_tool"] == "innovus" and hard_params["process_size"] == ""):
            print("param process_size is unset, please go to your hardblock/process params file and set it")
            sys.exit(1)

def load_run_params(filename):

    run_flow_stages = ["synth","pnr","sta"]
    per_flow_blocks = ["param_filters"]
    param_block_begin_str = "begin"
    begin_res = [re.compile(".*"+flow_stage+r"\s+"+param_block_begin_str+".*") for flow_stage in run_flow_stages]
    sub_begin_res = [re.compile(".*"+per_flow_block+r"\s+"+param_block_begin_str+".*") for per_flow_block in per_flow_blocks]
    end_re = re.compile(".*end.*")
    # end_res = [re.compile(".*"+flow_stage+"\s+"+param_block_end_str+".*") for flow_stage in run_flow_stages]
    fd = open(filename,"r")
    #read in file and get a list of all lines without comments
    run_params_text = fd.read()
    run_params_list = run_params_text.split("\n")
    run_params_clean = [line for line in run_params_list if not (line.startswith("#") or line == "")]
    
    run_params_dict = {}
    

    flow_str = ""
    per_flow_block_str = ""
    param_nest_lvl = 0

    for line in run_params_clean:
        skip_parse = 0
        for idx,begin_re in enumerate(begin_res):
            if begin_re.search(line):
                flow_str = run_flow_stages[idx]
                flow_tmp_dict = {}
                flow_tmp_dict[flow_str] = {}
                param_nest_lvl += 1
                skip_parse = 1
                break
        for idx,sub_begin_re in enumerate(sub_begin_res):
            if sub_begin_re.search(line):
                per_flow_block_str = per_flow_blocks[idx]
                flow_tmp_dict[flow_str][per_flow_block_str] = {}
                param_nest_lvl += 1
                skip_parse = 1
                break
        if(end_re.search(line)):
            param_nest_lvl -= 1
            if(param_nest_lvl == 0):
                run_params_dict[flow_str] = flow_tmp_dict[flow_str]
                flow_str = ""
            elif(param_nest_lvl == 1):
                per_flow_block_str = ""
            skip_parse = 1
        
        if(skip_parse):
            continue
        parsed_line = parse_ptn_param_line(line)

        if(flow_str != "" and per_flow_block_str != ""):
            if(not isinstance(parsed_line[1],list)):
                flow_tmp_dict[flow_str][per_flow_block_str][parsed_line[0]] = [parsed_line[1]]
            else:
                flow_tmp_dict[flow_str][per_flow_block_str][parsed_line[0]] = parsed_line[1]
        elif(flow_str != ""):
            flow_tmp_dict[flow_str][parsed_line[0]] = parsed_line[1]

    #need to make sure all elements in the dict are stored as list
    
    fd.close()
    return run_params_dict

def parse_ptn_param_line(line):
    # white_sp_re = re.compile("\s+")
    #This is a poor parser, just need it to work, when coffe is updated to python3 this can be done via yaml file
    split_line = line.split(":")
    #this list contains all characters which can legally bound ptn parameters
    valid_char_start_list = ["\"","["]
    valid_char_end_list = ["\"","]"]
    parsed_line = []
    # print(split_line)
    for line in split_line:
        read_char_flag = 0
        # t_line = white_sp_re.sub(string=line,repl="")
        clean_line = ""
        bounds_char= ""
        for char in line:
            #Works for parsing strings
            if(char in valid_char_start_list and not read_char_flag):
                bounds_char = valid_char_end_list[valid_char_start_list.index(char)]
                read_char_flag = 1
                continue
            elif(char == bounds_char and read_char_flag):
                read_char_flag = 0
                continue
            if(read_char_flag):
                clean_line = clean_line + char
        parsed_line.append(clean_line)
    # print(parsed_line)
    #if there are any lists in the parsed_line we can make them into a sublist for convenience
    updated_parsed_line = []
    #all characters matching below regex are removed from the line
    list_clean_re = re.compile(r"\[|\]|\s")
    gen_clean_re = re.compile("\"")
    for subline in parsed_line:
        #remove the hard brackets, quotes and spaces from the line
        #if a comma is in the subline, it is a list
        new_subline = gen_clean_re.sub(repl="",string=subline)
        if("," in subline):
            #seperate subline into list via comma delimiter
            new_subline = list_clean_re.sub(repl="",string=new_subline)
            new_subline = new_subline.split(",")            
        updated_parsed_line.append(new_subline)
    return updated_parsed_line

def load_ptn_params(filename):
    """
    Parse the user defined partition settings, these get read into a dict for each partition in the design
    """
    #init ptn data structure
    #parse the input file and create a ptn dict for each structure

    ptn_params = {
        "ptn_list" : [], #list of all partitions in design
        "scaling_array": [], #list of floorplan scales to be swept across
        "fp_init_dims": [], # two element list of  
        "fp_pin_spacing": ""
    }
    ptn_dict = {
        "inst_name": "",
        "mod_name": "",
        "fp_coords": []
    }
    top_settings_re = re.compile(r".*top_settings\s+begin.*")
    ptn_begin_re = re.compile(r".*ptn\s+begin.*")
    ptn_end_re = re.compile(r".*end.*")
    fd = open(os.path.expanduser(filename),"r")
    ptn_params_text = fd.read()
    ptn_params_list = ptn_params_text.split("\n")
    ptn_params_clean = [line for line in ptn_params_list if not (line.startswith("#") or line == "")]
    read_ptn_flag = 0    
    read_ptn_top_setting_flag = 0
    parsed_lines = []
    
    num_ptns = 0
    for line in ptn_params_clean:
        #raise flag if the ptn params are found
        if(ptn_begin_re.search(line)):
            read_ptn_flag = 1
            continue
        elif(ptn_end_re.search(line)):
            read_ptn_flag = 0
            read_ptn_top_setting_flag = 0
            num_ptns += 1
            continue
        elif(top_settings_re.search(line)):
            read_ptn_top_setting_flag = 1
            continue

        if(read_ptn_flag or read_ptn_top_setting_flag):
            parsed_line = parse_ptn_param_line(line)
            if(read_ptn_flag):
                parsed_lines.append(parsed_line)
                #this if statement handles top level settings (ie those applied to all ptns or the design fp)
            elif(read_ptn_top_setting_flag):
                if(len(parsed_line) > 1):
                    ptn_params[parsed_line[0]] = parsed_line[1]

    #we will have the same number
    #some bug in python2 or something not sure but you cant assign values to dict list elements in below list in regular way
    #ptn_params["ptn_list"][ptn_idx][key] = val

    ptn_idx = 0 
    key_cnt = 0
    tmp_dict = {}
    ptn_list = []
    for line in parsed_lines:
        #first argument is always dict_key
        key = line[0]
        val = line[1]
        #dont continue if key is not in dict
        if(key not in ptn_dict):
            print(("ERROR: Found invalid partition parameter (" + key + ") in " + filename))
            sys.exit(1)
        tmp_dict[key] = val
        key_cnt += 1 
        #If someone ever needs to do anything after all params have been read into a dict inst do it in below if statement
        if(key_cnt % len(list(ptn_dict.keys())) == 0):
            ptn_list.append(tmp_dict)
            #reset tmp dict
            tmp_dict = {}            
            ptn_idx += 1

    ptn_params["ptn_list"] = ptn_list
    fd.close()
    return ptn_params

def check_arch_params (arch_params, filename):
    """
    This function checks the architecture parameters to make sure that all the parameters specified 
    are compatible with COFFE. Right now, this functions just checks really basic stuff like 
    checking for negative values where there shoulnd't be or making sure the LUT size is supported
    etc. But in the future I think it might be a good idea to make this checker a little more 
    intelligent. For example, we might check things like Fc values that make no sense. Such as an
    Fc that is so small that you can't connect to wires, or something like that.
    """

    # TODO: Make these error messages more descriptive of that the problem is.

    if arch_params['W'] <= 0:
        print_error (str(arch_params['W']), "W", filename)
    if arch_params['L'] <= 0:
        print_error (str(arch_params['L']), "L", filename)
    if arch_params['Fs'] <= 0:
        print_error (str(arch_params['Fs']), "Fs", filename)
    if arch_params['N'] <= 0:
        print_error (str(arch_params['N']), "N", filename)
    # We only support 4-LUT, 5-LUT or 6-LUT
    if arch_params['K'] < 4 or  arch_params['K'] > 6:
        print_error (str(arch_params['K']), "K", filename)
    if arch_params['I'] <= 0:
        print_error (str(arch_params['I']), "I", filename)
    if arch_params['Fcin'] <= 0.0 or arch_params['Fcin'] > 1.0:
        print_error (str(arch_params['Fcin']), "Fcin", filename)
    if arch_params['Fcout'] <= 0.0 or arch_params['Fcout'] > 1.0 :
        print_error (str(arch_params['Fcout']), "Fcout", filename)
    if arch_params['Or'] <= 0:
        print_error (str(arch_params['Or']), "Or", filename)
    # We currently only support architectures that have local feedback routing. 
    # It might be a good idea to change COFFE such that you can specify an
    # architecture with no local feedback routing.
    if arch_params['Ofb'] <= 0:
        print_error (str(arch_params['Ofb']), "Ofb", filename)
    if arch_params['Fclocal'] <= 0.0 or arch_params['Fclocal'] > 1.0:
        print_error (str(arch_params['Fclocal']), "Fclocal", filename)
    # Rsel can 'a' the last LUT input. For example for a 6-LUT Rsel can be 'a' to 'f' or 'z' which means no Rsel.
    if arch_params['Rsel'] != 'z' and (arch_params['Rsel'] < 'a' or arch_params['Rsel'] > chr(arch_params['K']+96)):
        print_error (arch_params['Rsel'], "Fclocal", filename)
    # Rfb can be 'z' which means to Rfb. If not 'z', Rfb is a string of the letters of all the LUT inputs that are Rfb.
    if arch_params['Rfb'] == 'z':
        pass    
    elif len(arch_params['Rfb']) > arch_params['K']:
        print_error (arch_params['Rfb'], "Rfb", filename, "(you specified more Rfb LUT inputs than there are LUT inputs)")
    else:
        # Now, let's make sure all these characters are valid characters
        for character in arch_params['Rfb']:
            # The character has to be a valid LUT input
            if (character < 'a' or character > chr(arch_params['K']+96)):
                print_error (arch_params['Rfb'], "Rfb", filename, " (" + character + " is not a valid LUT input)")
            # The character should not appear twice
            elif arch_params['Rfb'].count(character) > 1:
                print_error (arch_params['Rfb'], "Rfb", filename, " (" + character + " appears more than once)")
    # only one or two FAs are allowed per ble
    if arch_params['FAs_per_flut'] > 2:
        print_error (str(arch_params['FAs_per_flut']), "FAs_per_flut", filename, "(number of FA per ble should be 2 or less)")
    # Currently, I only generate the circuit assuming we have a fracturable lut. It can easily be changed to support nonfracturable luts as well.
    if arch_params['enable_carry_chain'] == 1 and arch_params['use_fluts'] == False:
        print_error_not_compatable("carry chains", "non fracturable lut")           


    # Check process technology parameters
    if arch_params['transistor_type'] != 'bulk' and arch_params['transistor_type'] != 'finfet':
        print_error (arch_params['transistor_type'], "transistor_type", filename)
    if arch_params['switch_type'] != 'pass_transistor' and arch_params['switch_type'] != 'transmission_gate':
        print_error (arch_params['switch_type'], "switch_type", filename)
    if arch_params['vdd'] <= 0 :
        print_error (str(arch_params['vdd']), "vdd", filename)                     
    if arch_params['gate_length'] <= 0 :
        print_error (str(arch_params['gate_length']), "gate_length", filename)            
    if arch_params['rest_length_factor'] <= 0 :
        print_error (str(arch_params['rest_length_factor']), "rest_length_factor", filename) 
    if arch_params['min_tran_width'] <= 0 :
        print_error (str(arch_params['min_tran_width']), "min_tran_width", filename)            
    if arch_params['min_width_tran_area'] <= 0 :
        print_error (str(arch_params['min_width_tran_area']), "min_width_tran_area", filename)            
    if arch_params['sram_cell_area'] <= 0 :
        print_error (str(arch_params['sram_cell_area']), "sram_cell_area", filename)
    if arch_params['trans_diffusion_length'] <= 0 :
        print_error (str(arch_params['trans_diffusion_length']), "trans_diffusion_length", filename)  
    if arch_params['enable_bram_module'] == 1 and arch_params['use_finfet'] == True:
        print_error_not_compatable("finfet", "BRAM")           
    # if arch_params['use_finfet'] == True and arch_params['use_fluts'] == True:
    #    print_error_not_compatable("finfet", "flut")      
    # if arch_params['coffe_repo_path'].split("/")[-1] != "COFFE" or os.path.isdir(arch_params['coffe_repo_path']):
    #     print_error (arch_params['coffe_repo_path'],"coffe_repo_path",filename)


def print_error(value, argument, filename, msg = ""):
    print("ERROR: Invalid value (" + value + ") for " + argument + " in " + filename + " " + msg)
    sys.exit()


def print_error_not_compatable(value1, value2):
    print("ERROR: " + value1 + " and " + value2 + " simulations are not compatible.\n")
    sys.exit()    


def print_run_options(args, report_file_path):
    """ 
    This function prints the run options entered by the user
    when running COFFE, in the terminal and the report file  
    """

    report_file = open(report_file_path, 'w')
    report_file.write("Created " + str(datetime.datetime.now()) + "\n\n")
    
    print_and_write(report_file, "----------------------------------------------")
    print_and_write(report_file, "  RUN OPTIONS:")
    print_and_write(report_file, "----------------------------------------------" + "\n")
    if not args.no_sizing:
        print_and_write(report_file, "  Transistor sizing: on")
    else:
        print_and_write(report_file, "  Transistor sizing: off")
    
    if args.opt_type == "global":
        print_and_write(report_file, "  Optimization type: global")
    else:
        print_and_write(report_file, "  Optimization type: local")
    
    
    print_and_write(report_file, "  Number of top combos to re-ERF: " + str(args.re_erf))
    print_and_write(report_file, "  Area optimization weight: " + str(args.area_opt_weight))
    print_and_write(report_file, "  Delay optimization weight: " + str(args.delay_opt_weight))
    print_and_write(report_file, "  Maximum number of sizing iterations: " + str(args.max_iterations))
    print_and_write(report_file, "")
    print_and_write(report_file, "")

    report_file.close()



def print_architecture_params(arch_params_dict, report_file_path):

    report_file = open(report_file_path, 'a')

    print_and_write(report_file, "-------------------------------------------------")
    print_and_write(report_file, "  ARCHITECTURE PARAMETERS:")
    print_and_write(report_file, "-------------------------------------------------" + "\n")


    print_and_write(report_file, "  Number of BLEs per cluster (N): " + str(arch_params_dict['N']))
    print_and_write(report_file, "  LUT size (K): " + str(arch_params_dict['K']))

    if arch_params_dict['use_fluts'] == True:
        print_and_write(report_file, "  LUT fracturability level: 1")
        print_and_write(report_file, "  Number of adder bits per ALM: " + str(arch_params_dict['FAs_per_flut']))

    print_and_write(report_file, "  Channel width (W): " + str(arch_params_dict['W']))
    print_and_write(report_file, "  Wire segment length (L): " + str(arch_params_dict['L']))
    print_and_write(report_file, "  Number of cluster inputs (I): " + str(arch_params_dict['I']))
    print_and_write(report_file, "  Number of BLE outputs to general routing (Or): " + str(arch_params_dict['Or']))
    print_and_write(report_file, "  Number of BLE outputs to local routing (Ofb): " + str(arch_params_dict['Ofb']))
    print_and_write(report_file, "  Total number of cluster outputs (N*Or): " + str(arch_params_dict['N']*arch_params_dict['Or']))
    print_and_write(report_file, "  Switch block flexibility (Fs): " + str(arch_params_dict['Fs']))
    print_and_write(report_file, "  Cluster input flexibility (Fcin): " + str(arch_params_dict['Fcin']))
    print_and_write(report_file, "  Cluster output flexibility (Fcout): " + str(arch_params_dict['Fcout']))
    print_and_write(report_file, "  Local MUX population (Fclocal): " + str(arch_params_dict['Fclocal']))
    print_and_write(report_file, "  LUT input for register selection MUX (Rsel): " + str(arch_params_dict['Rsel']))
    print_and_write(report_file, "  LUT input(s) for register feedback MUX(es) (Rfb): " + str(arch_params_dict['Rfb']))
    print_and_write(report_file, "")
    
    print_and_write(report_file, "-------------------------------------------------")
    print_and_write(report_file, "  PROCESS TECHNOLOGY PARAMETERS:")
    print_and_write(report_file, "-------------------------------------------------" + "\n")

    print_and_write(report_file, "  transistor_type = " + arch_params_dict['transistor_type'])
    print_and_write(report_file, "  switch_type = " + arch_params_dict['switch_type'])
    print_and_write(report_file, "  vdd = " + str( arch_params_dict['vdd']))
    print_and_write(report_file, "  vsram = " + str( arch_params_dict['vsram']) )
    print_and_write(report_file, "  vsram_n = " + str( arch_params_dict['vsram_n']) )
    print_and_write(report_file, "  gate_length = " + str( arch_params_dict['gate_length']))
    print_and_write(report_file, "  min_tran_width = " + str( arch_params_dict['min_tran_width']) )
    print_and_write(report_file, "  min_width_tran_area = " + str( arch_params_dict['min_width_tran_area']) )
    print_and_write(report_file, "  sram_cell_area = " + str( arch_params_dict['sram_cell_area']) )
    print_and_write(report_file, "  model_path = " + str( arch_params_dict['model_path']) )
    print_and_write(report_file, "  model_library = " + str( arch_params_dict['model_library']) )
    print_and_write(report_file, "  metal = " + str( arch_params_dict['metal']) )
    print_and_write(report_file, "")
    print_and_write(report_file, "")

    report_file.close()


def extract_initial_tran_size(filename, use_tgate):
    """ Parse the initial sizes file and load values into dictionary. 
        Returns this dictionary.
        """
    
    transistor_sizes = {}

    sizes_file = open(filename, 'r')
    for line in sizes_file:
    
        # Ignore comment lines
        if line.startswith('#'):
            continue
        
        # Remove line feeds and spaces
        line = line.replace('\n', '')
        line = line.replace('\r', '')
        line = line.replace('\t', '')
        line = line.replace(' ', '')
        
        # Ignore empty lines
        if line == "":
            continue
        
        # Split lines at '='
        words = line.split('=')
        trans = words[0]
        size = words[1]

        transistor_sizes[trans] = float(size)

    sizes_file.close()

    return  transistor_sizes


def use_initial_tran_size(initial_sizes, fpga_inst, tran_sizing, use_tgate):

    print("Extracting initial transistor sizes from: " + initial_sizes)
    initial_tran_size = extract_initial_tran_size(initial_sizes, use_tgate)
    print("Setting transistor sizes to extracted values")
    tran_sizing.override_transistor_sizes(fpga_inst, initial_tran_size)
    for tran in initial_tran_size :
        fpga_inst.transistor_sizes[tran] = initial_tran_size[tran]
    print("Re-calculating area...")
    fpga_inst.update_area()
    print("Re-calculating wire lengths...")
    fpga_inst.update_wires()
    print("Re-calculating resistance and capacitance...")
    fpga_inst.update_wire_rc()
    print("")


def check_for_time():
    """ This finction should be used before each call for HSPICE it checks
        if the time is between 2:30 a.m and 3:30 a.m. since during this time
        it was found that the license doesn't work on my machine. So, to avoid
        program termination this function was written. If you're using COFFE on 
        a machine that doesn't have this problem you can comment this function 
        in the code """
    now = datetime.datetime.now()
    if (now.hour == 2 or now.hour == 3):
        print("-----------------------------------------------------------------")
        print("      Entered the check for time function @ " + str(now.hour) +":" + str(now.minute) + ":" + str(now.second))
        print("-----------------------------------------------------------------")
        print("")
       
    while (now.hour == 2 and now.minute >= 30) or (now.hour == 3 and now.minute < 30):
    #while (now.minute >= 20) and (now.minute < 25):
        print("\tI'm sleeping")
        time.sleep(60)
        now = datetime.datetime.now()
        if not ((now.hour == 2 and now.minute >= 30) or (now.hour == 3 and now.minute < 30)):
            print("\tExecution is resumed")

    now = datetime.datetime.now()
    if (now.hour == 2 or now.hour == 3):        
        print("-----------------------------------------------------------------")
        print("      Exited the check for time function  @ " + str(now.hour) +":" + str(now.minute) + ":" + str(now.second))
        print("-----------------------------------------------------------------")
        print("")         

def print_and_write(file, string):
    """
    This function takes a file name and a string, it prints the string to the 
    terminal and writes it to the file. Since this sequence is repeated a lot
    in the code this function is added to remove some redundent code. 
    Note: the file should be open for writing before calling this function
    """
    #TODO: check if the file is already open or not
    print(string)
    file.write(string + "\n")


def create_output_dir(arch_file_name, arch_out_folder):
    """
    This function creates the architecture folder and returns its name.
    It also deletes the content of the folder in case it's already created
    to avoid any errors in case of multiple runs on the same architecture file.
    If arch_out_folder is specified in the input params file, then that is
    used as the architecture folder, otherwise the folder containing the arch
    params file is used.
    """
    
    if arch_out_folder == "" or arch_out_folder == "None":
        arch_desc_words = arch_file_name.split('.')
        arch_folder = arch_desc_words[0]
    else:
        arch_folder = os.path.expanduser(arch_out_folder)

    if not os.path.exists(arch_folder):
        os.makedirs(arch_folder)
    else:
        # Delete contents of sub-directories
        # COFFE generates several 'intermediate results' files during sizing
        # so we delete them to avoid from having them pile up if we run COFFE
        # more than once.
        dir_contents = os.listdir(arch_folder)
        for content in dir_contents:
            if os.path.isdir(arch_folder + "/" + content):
                shutil.rmtree(arch_folder + "/" + content)

    return arch_folder  

def print_summary(arch_folder, fpga_inst, start_time):

    report_file = open(arch_folder + "/report.txt", 'a')
    report_file.write("\n")
    
    print_and_write(report_file, "|--------------------------------------------------------------------------------------------------|")
    print_and_write(report_file, "|    Area and Delay Report                                                                         |")
    print_and_write(report_file, "|--------------------------------------------------------------------------------------------------|")
    print_and_write(report_file, "")
    
    # Print area and delay per subcircuit
    print_area_and_delay(report_file, fpga_inst)
    
    # Print block areas
    print_block_area(report_file, fpga_inst)

    #Print hardblock information
    if len(fpga_inst.hardblocklist) > 0:
        print_hardblock_info(report_file, fpga_inst)
    
    # Print VPR delays (to be used to make architecture file)
    print_vpr_delays(report_file, fpga_inst)
    
    # Print VPR areas (to be used to make architecture file)
    print_vpr_areas(report_file, fpga_inst)
          
    # Print area and delay summary
    final_cost = fpga_inst.area_dict["tile"] * fpga_inst.delay_dict["rep_crit_path"]
    
    print_and_write(report_file, "  SUMMARY")
    print_and_write(report_file, "  -------")
    print_and_write(report_file, "  Tile Area                            " + str(round(fpga_inst.area_dict["tile"]/1e6, 2)) + " um^2")
    print_and_write(report_file, "  Representative Critical Path Delay   " + str(round(fpga_inst.delay_dict["rep_crit_path"] * 1e12, 2)) + " ps")
    print_and_write(report_file, "  Cost (area^" + str(fpga_inst.area_opt_weight) + " x delay^" + str(fpga_inst.delay_opt_weight) + ")              " 
           + str(round(final_cost,5)))
    
    print_and_write(report_file, "")
    print_and_write(report_file, "|--------------------------------------------------------------------------------------------------|")
    print_and_write(report_file, "")
    
    # Record end time
    total_end_time = time.time()
    total_time_elapsed = total_end_time - start_time
    total_hours_elapsed = int(total_time_elapsed/3600)
    total_minutes_elapsed = int((total_time_elapsed - 3600*total_hours_elapsed)/60)
    total_seconds_elapsed = int(total_time_elapsed - 3600*total_hours_elapsed - 60*total_minutes_elapsed)
    
    print_and_write(report_file, "Number of HSPICE simulations performed: " + str(fpga_inst.spice_interface.get_num_simulations_performed()))
    print_and_write(report_file, "Total time elapsed: " + str(total_hours_elapsed) + " hours " + str(total_minutes_elapsed) + " minutes " + str(total_seconds_elapsed) + " seconds\n") 
    
    report_file.write("\n")
    report_file.close() 
