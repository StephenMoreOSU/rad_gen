import argparse
import sys, os
import subprocess as sp
import shlex
import re

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

# def write_pt_timing_script(flow_settings,fname,mode_enabled,x,synth_output_path,pnr_output_path,rel_outputs=False):
#     """
#     writes the tcl script for timing analysis using Synopsys Design Compiler, tested under 2017 version
#     This should look for setup/hold violations using the worst case (hold) and best case (setup) libs
#     """
#     report_path = flow_settings["primetime_folder"] if (not rel_outputs) else os.path.join("..","reports")
#     report_path = os.path.abspath(report_path)

#     #TODO make this more general but this is how we see if the report output should have a string appended to it
#     if "ptn" in pnr_output_path.split("/")[-1]:
#         report_prefix = pnr_output_path.split("/")[-1]
#         report_timing_cmd = "report_timing > " + os.path.join(report_path,report_prefix+"_timing.rpt")
#         report_power_cmd = "report_power > " + os.path.join(report_path,report_prefix + "_power.rpt")
#     else:
#         report_timing_cmd = "report_timing > " + os.path.join(report_path,"timing.rpt")
#         report_power_cmd = "report_power > " + os.path.join(report_path,"power.rpt")



#     # if mode_enabled and x <2**len(flow_settings['mode_signal']):
#     # for y in range (0, len(flow_settings['mode_signal'])):
#         # file.write("set_case_analysis " + str((x >> y) & 1) + " " +  flow_settings['mode_signal'][y] + " \n")

#     if mode_enabled and x < 2**len(flow_settings['mode_signal']):
#         case_analysis_cmds = [" ".join(["set_case_analysis",str((x >> y) & 1),flow_settings['mode_signal'][y]]) for y in range(0,len(flow_settings["mode_signal"]))]
#     else:
#         case_analysis_cmds = ["#MULTIMODAL ANALYSIS DISABLED"]
#     #For power switching activity estimation
#     if flow_settings['generate_activity_file']:
#         switching_activity_cmd = "read_saif -input saif.saif -instance_name testbench/uut"
#     else:
#         switching_activity_cmd = "set_switching_activity -static_probability " + str(flow_settings['static_probability']) + " -toggle_rate " + str(flow_settings['toggle_rate']) + " -base_clock $my_clock_pin -type inputs"

#     # backannotate into primetime
#     # This part should be reported for all the modes in the design.
#     file_lines = [
#         "set sh_enable_page_mode true",
#         "set search_path " + flow_settings['search_path'],
#         "set my_top_level " + flow_settings['top_level'],
#         "set my_clock_pin " + flow_settings['clock_pin_name'],
#         "set target_library " + flow_settings['primetime_libs'],
#         "set link_library " + flow_settings['link_library'],
#         "read_verilog " + pnr_output_path + "/netlist.v",
#         "current_design $my_top_level",
#         case_analysis_cmds,
#         "link",
#         #read constraints file
#         "read_sdc -echo " + synth_output_path + "/synthesized.sdc",
#         #Standard Parasitic Exchange Format. File format to save parasitic information extracted by the place and route tool.
#         "read_parasitics -increment " + pnr_output_path + "/spef.spef",
#         report_timing_cmd,
#         "set power_enable_analysis TRUE",
#         "set power_analysis_mode \"averaged\"",
#         switching_activity_cmd,
#         report_power_cmd,
#         "quit",
#     ]
#     file_lines = flatten_mixed_list(file_lines)

#     fd = open(fname, "w")
#     for line in file_lines:
#         file_write_ln(fd,line)
#     fd.close()
#     fpath = os.path.join(os.getcwd(),fname)
#     return fpath,report_path


########################################## HAMMER UTILITIES ##########################################

def get_hammer_config(flow_stage_trans, args):
    #find flow stage transition, split up Ex. "syn-to-par"
    flow_from = flow_stage_trans.split("-")[0]
    hammer_cmd = f"hammer-vlsi -e {args.env_path} -p {args.config_path} -p {obj_dir_path}/{flow_from}-rundir/{flow_from}-output.json --obj_dir {obj_dir_path} {flow_stage_trans}"
    run_shell_cmd(hammer_cmd,f"hammer_{flow_stage_trans}_{args.top_level}.log")

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
    
    # config dict
    # this contains params we want to edit from cli options
    config_dict = {}

    design_files = rec_get_flist_of_ext(args.hdl_path)
    # this only works with a specific format of hammer config file but is fine for now (TODO)
    config_dict["inputs.input_files"] = design_files
    config_dict["inputs.top_module"] = args.top_level
    edit_config_file(args.config_path, config_dict)
    #run hammer stages
    run_hammer_stage("syn",args.config_path,args)
    get_hammer_config("syn-to-par",args)
    run_hammer_stage("par","output.json",args)

    sys.exit()    
    
    


if __name__ == '__main__':
    main()