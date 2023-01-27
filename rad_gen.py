import argparse
import sys, os
import subprocess as sp
import shlex
import re

import json
import yaml

########################################## GENERAL UTILITIES ##########################################

def flatten_mixed_list(input_list):
    """
    Flattens a list with mixed value Ex. ["hello", ["billy","bob"],[["johnson"]]] -> ["hello", "billy","bob","johnson"]
    """
    flat_list = lambda input_list:[element for item in input_list for element in flat_list(item)] if type(input_list) is list else [input_list]
    flattened_list = flat_list(input_list)
    return flattened_list

def run_shell_cmd(cmd_str,log_file):
    run_cmd = cmd_str + f" | tee {log_file}"
    sp.call(run_cmd,shell=True,executable='/bin/bash',env=cur_env)

def rec_get_flist_of_ext(design_dir_path):
    hdl_exts = ['.v','.sv']
    hdl_exts = [f"({ext})" for ext in hdl_exts]

    design_files = []
    ext_str = ".*" + '|'.join(hdl_exts)
    ext_re = re.compile(ext_str)
    design_folder = os.path.expanduser(design_dir_path)
    design_files = [os.path.join(r,fn) for r, _, fs in os.walk(design_folder) for fn in fs if ext_re.search(fn)]

    return design_files

def file_write_ln(fd, line):
  """
  writes a line to a file with newline after
  """
  fd.write(line + "\n")

def edit_config_file(config_fpath, config_dict):
    """
    Super useful function which I have needed in multiple tools, take in a dict of key value pairs and replace them in a config file,
    will keep it to yaml specification for now.
    """
    #read in config file as text
    with open(config_fpath, 'r') as f:
        config_text = f.read()

    for key, value in config_dict.items():
        key_re = re.compile(f"{key}:.*",re.MULTILINE)
        
        if(isinstance(value,list)):
            val_str = "\", \"".join(value)
            repl_str = f"{key}: [{val_str}]"
        else:    
            repl_str = f"{key}: {value}"
        #replace relevant configs
        config_text = key_re.sub(repl=repl_str,string=config_text)        
    
    with open(config_fpath, 'w') as f:
        f.write(config_text)

########################################## GENERAL UTILITIES ##########################################

def write_lib_to_db_script(obj_dir):
    # create PT run-dir
    pt_outpath = os.path.join(obj_dir,"pt-rundir")
    if not os.path.isdir(pt_outpath) :
        os.mkdir(pt_outpath)
    lib_dir = os.path.join(obj_dir,"tech-asap7-cache/LIB/NLDM")

    file_lines = ["enable_write_lib_mode"]
    for lib in os.listdir(lib_dir):
        read_lib_cmd = "read_lib " + f"{os.path.join(lib_dir,lib)}"
        write_lib_cmd = "write_lib " + f"{os.path.splitext(lib)[0]} " + "-f db " + "-o " f"{os.path.splitext(os.path.join(lib_dir,lib))[0]}.db"
        file_lines.append(read_lib_cmd)
        file_lines.append(write_lib_cmd)

    
    fd = open(os.path.join(pt_outpath,"lib_to_db.tcl"),"w")
    for line in file_lines:
        file_write_ln(fd,line)
    file_write_ln(fd,"quit")
    fd.close()


########################################## PRIMETIME ##########################################

def write_pt_sdc(power_in_json_data, obj_dir):
    """
    Writes an sdc file in the format which will match the output of innovus par stage.
    """

    # create PT run-dir
    pt_outpath = os.path.join(obj_dir,"pt-rundir")
    if not os.path.isdir(pt_outpath) :
        os.mkdir(pt_outpath)

    dec_re = re.compile(r"\d+\.{0,1}\d*")
    clock_fac = 1.0
    if "us" in power_in_json_data["vlsi.inputs.clocks"][0]["period"]:
        clock_fac = 1e6 * clock_fac
    elif "ns" in power_in_json_data["vlsi.inputs.clocks"][0]["period"]:
        clock_fac = 1e3 * clock_fac
    elif "ps" in power_in_json_data["vlsi.inputs.clocks"][0]["period"]:
        clock_fac = 1.0 * clock_fac
    
    clk_period_ps = float(dec_re.search(power_in_json_data["vlsi.inputs.clocks"][0]["period"]).group(0)) * clock_fac

    file_lines = [
        "#"*68,
        "# Created by rad_gen.py for ASAP7 connection from Cadence Innovus par to Synopsys Primetime",
        "#"*68,
        "set sdc_version 2.0",
        "set_units -time ps -resistance kOhm -capacitance pF -voltage V -current mA",
        "create_clock [get_ports clk] -period " + f"{clk_period_ps} " + f"-waveform {{0.0 {clk_period_ps/2.0}}}",
    ]
    fname = "pt.sdc"
    fd = open(os.path.join(pt_outpath,fname),"w")
    for line in file_lines:
        file_write_ln(fd,line)
    fd.close()

def write_pt_timing_script(power_in_json_data, obj_dir,args):
    """
    writes the tcl script for timing analysis using Synopsys Design Compiler, tested under 2017 version
    This should look for setup/hold violations using the worst case (hold) and best case (setup) libs
    """

    # Make sure that the $STDCELLS env var is set and use it to find the .lib files to use for Primetime
    search_paths = "/CMC/tools/synopsys/syn_vN-2017.09/libraries/syn /CMC/tools/synopsys/syn_vN-2017.09/libraries/syn_ver /CMC/tools/synopsys/syn_vN-2017.09/libraries/sim_ver"
    
    db_dir =  os.path.join(os.getcwd(),"asap7_db_libs")
    target_libs = " ".join([os.path.join(db_dir,lib) for lib in os.listdir(db_dir) if lib.endswith(".db")])
    
    #default switching probability (TODO) find where this is and make it come from there
    switching_prob = "0.5"

    # create PT run-dir
    pt_outpath = os.path.join(obj_dir,"pt-rundir")
    if not os.path.isdir(pt_outpath) :
        os.mkdir(pt_outpath)

    # create reports dir
    report_path = os.path.join(pt_outpath,"reports")
    if not os.path.isdir(report_path) :
        os.mkdir(report_path)

    # get pnr output path (should be in this format)
    pnr_design_outpath = os.path.join(obj_dir,"par-rundir",f"{args.top_level}_FINAL")
    if not os.path.isdir(pnr_design_outpath) :
        print("Couldn't find output of pnr stage, Exiting...")
        sys.exit(1)


    # report timing / power commands
    report_timing_cmd = "report_timing > " + os.path.join(report_path,"timing.rpt")
    report_power_cmd = "report_power > " + os.path.join(report_path,"power.rpt")



    case_analysis_cmds = ["#MULTIMODAL ANALYSIS DISABLED"]
        
    #get switching activity and toggle rates from power_constraints tcl file
    power_constraints_fd = open(os.path.join(pnr_design_outpath,f"{args.top_level}_power_constraints.tcl"),"r")
    power_constraints_lines = power_constraints_fd.readlines()
    toggle_rate_var = "seq_activity"
    grab_opt_val_re = re.compile(f"(?<={toggle_rate_var}\s).*")
    toggle_rate = ""
    for line in power_constraints_lines:
        if "set_default_switching_activity" in line:
            toggle_rate = str(grab_opt_val_re.search(line).group(0))

    power_constraints_fd.close()
    print(toggle_rate)

    switching_activity_cmd = "set_switching_activity -static_probability " + switching_prob + " -toggle_rate " + toggle_rate + " -base_clock $my_clock_pin -type inputs"

    #backannotate into primetime
    #This part should be reported for all the modes in the design.
    file_lines = [
        "set sh_enable_page_mode true",
        "set search_path " + f"\"{search_paths}\"",
        "set my_top_level " + power_in_json_data["power.inputs.top_module"],
        "set my_clock_pin " + power_in_json_data["vlsi.inputs.clocks"][0]["name"],
        "set target_library " + f"\"{target_libs}\"",
        "set link_library " + "\"* $target_library\"",
        "read_verilog " + power_in_json_data["power.inputs.netlist"],
        "current_design $my_top_level",
        case_analysis_cmds,
        "link",
        #set clock constraints (this can be done by defining a clock or specifying an .sdc file)
        #read constraints file
        f"read_sdc -echo {pt_outpath}/pt.sdc",
        #Standard Parasitic Exchange Format. File format to save parasitic information extracted by the place and route tool.
        # Just taking index 0 which is the 100C corner for case of high power
        "read_parasitics -increment " + power_in_json_data["power.inputs.spefs"][0],
        report_timing_cmd,
        "set power_enable_analysis TRUE",
        "set power_analysis_mode \"averaged\"",
        switching_activity_cmd,
        report_power_cmd,
        "quit",
    ]
    file_lines = flatten_mixed_list(file_lines)

    fname = os.path.join(pt_outpath,"pt_analysis.tcl")
    fd = open(fname, "w")
    for line in file_lines:
        file_write_ln(fd,line)
    fd.close()

    return
########################################## PRIMETIME ##########################################


########################################## HAMMER UTILITIES ##########################################

def get_hammer_config(flow_stage_trans, args):
    #find flow stage transition, split up Ex. "syn-to-par"
    flow_from = flow_stage_trans.split("-")[0]
    flow_to = flow_stage_trans.split("-")[1]
    hammer_cmd = f"hammer-vlsi -e {args.env_path} -p {args.config_path} -p {obj_dir_path}/{flow_from}-rundir/{flow_from}-output.json -o {obj_dir_path}/{args.top_level}-{flow_stage_trans}.json --obj_dir {obj_dir_path} {flow_stage_trans}"
    run_shell_cmd(hammer_cmd,f"hammer_{flow_stage_trans}_{args.top_level}.log")
    #sp.run(["cp", "output.json", f"{obj_dir_path}/{args.top_level}_{flow_to}.json"])

def run_hammer_stage(flow_stage, config_path, args):
    print(f"Running hammer with input config: {config_path}...")
    hammer_cmd = f"hammer-vlsi -e {args.env_path} -p {config_path} --obj_dir {obj_dir_path} {flow_stage}"
    run_shell_cmd(hammer_cmd,f"hammer_{flow_stage}_{args.top_level}.log")
########################################## HAMMER UTILITIES ##########################################

def main():
    global cur_env
    global obj_dir_path


    obj_dir_path = "obj_dir"
    parser = argparse.ArgumentParser()
    parser.add_argument('-t', '--top_level', help="name of top level design in HDL", type=str, default='')
    parser.add_argument('-v', '--hdl_path', help="path to directory containing HDL files", type=str, default='')
    parser.add_argument('-e', '--env_path', help="path to hammer env.yaml file", type=str, default='')
    parser.add_argument('-p', '--config_path', help="path to hammer design specific config.yaml file", type=str, default='')
    
    args = parser.parse_args()


    # Make sure HAMMER env vars are set
    if 'HAMMER_HOME' not in os.environ:
        print('Error: HAMMER_HOME environment variable not set!')
        print("Please set HAMMER_HOME to the root of the HAMMER repository, and run 'source $HAMMER_HOME/sourceme.sh'")
        sys.exit(1)


    cur_env = os.environ.copy()
    

    design_files = rec_get_flist_of_ext(args.hdl_path)
    
    with open(args.config_path, 'r') as yml_file:
        design_config = yaml.load(yml_file, Loader=yaml.FullLoader)

    design_config["synthesis"]["inputs.input_files"] = design_files
    design_config["synthesis"]["inputs.top_module"] = args.top_level
    #init top level placement constraints
    design_config["vlsi.inputs"]["placement_constraints"][0]["path"] = args.top_level

    modified_config_path = os.path.splitext(args.config_path)[0]+"_mod.yaml"
    with open(modified_config_path, 'w') as yml_file:
        yaml.dump(design_config, yml_file) 
    #default to 70% utilization (TODO)
    
    # config dict
    # this contains params we want to edit from cli options
    # config_dict = {}

    # this only works with a specific format of hammer config file but is fine for now (TODO)
    # config_dict["inputs.input_files"] = design_files
    # config_dict["inputs.top_module"] = args.top_level
    # edit_config_file(args.config_path, config_dict)

    #run hammer stages
    run_hammer_stage("syn",modified_config_path,args)
    get_hammer_config("syn-to-par",args)
    run_hammer_stage("par",os.path.join(obj_dir_path,f"{args.top_level}-syn-to-par.json"),args)
    get_hammer_config("par-to-power",args)
    
    
    #get params from par-to-power.json file
    json_fd = open(os.path.join(obj_dir_path,f"{args.top_level}-par-to-power.json"),"r")
    par_to_power_data = json.load(json_fd)
    json_fd.close()
    #get params from syn-to-par.json file
    json_fd = open(os.path.join(obj_dir_path,f"{args.top_level}-syn-to-par.json"),"r")
    syn_to_par_data = json.load(json_fd)
    json_fd.close()

    write_pt_sdc(par_to_power_data,os.path.join(os.getcwd(),obj_dir_path))

    #now use the pnr output to run primetime

    ################################ LIB TO DB CONVERSION ################################
    #prepare lib files to be read in from pt, means we need to unzip them in asap7 cache
    #asap7_std_cell_lib_cache = os.path.join(obj_dir_path,"tech-asap7-cache/LIB/NLDM")
    # for lib_file in os.listdir(asap7_std_cell_lib_cache):
        # if(lib_file.endswith(".gz")):
            # sp.run(["gunzip",os.path.join(asap7_std_cell_lib_cache,lib_file)])
    #write_lib_to_db_script(os.path.join(os.getcwd(),obj_dir_path))
    ################################ LIB TO DB CONVERSION ################################
    

    write_pt_timing_script(par_to_power_data,os.path.join(os.getcwd(),obj_dir_path),args)
    cwd = os.getcwd()
    os.chdir(os.path.join(os.getcwd(),obj_dir_path,"pt-rundir"))
    run_shell_cmd("dc_shell-t -f pt_analysis.tcl","pt.log")
    os.chdir(cwd)
    ################################ LIB TO DB CONVERSION ################################
    # re zip the after primetime
    # for lib_file in os.listdir(asap7_std_cell_lib_cache):
    #     sp.run(["gunzip",os.path.join(asap7_std_cell_lib_cache,lib_file)])
    ################################ LIB TO DB CONVERSION ################################

    sys.exit()    
    
    


if __name__ == '__main__':
    main()