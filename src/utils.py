
from typing import List, Dict, Tuple, Set, Union, Any, Type
import os, sys, yaml
import argparse
import datetime
import logging
import flatdict



#Import hammer modules
import vlsi.hammer.hammer.config as hammer_config
from vlsi.hammer.hammer.vlsi.hammer_vlsi_impl import HammerVLSISettings 
from vlsi.hammer.hammer.vlsi.driver import HammerDriver
import vlsi.hammer.hammer.tech as hammer_tech


# RAD-Gen modules
import src.data_structs as rg_ds

# COFFE modules
# import COFFE.coffe.utils as coffe_utilss

def find_newest_obj_dir(search_dir: str, obj_dir_fmt: str):
    """
        Finds newest object directory corresponding to current design in the specified RAD-Gen output directory.
        The obj_dir_fmt string is used to determine what date time & naming convension we're using to compare
        - If no obj dirs found, None will be returned signaling that one must be created
    """

    # dir were looking for obj dirs in
    #search_dir = os.path.join(rad_gen_settings.env_settings.design_output_path, rad_gen_settings.asic_flow_settings.top_lvl_module)

    # find the newest obj_dir
    obj_dir_list = []
    for file in os.listdir(search_dir):
        dt_fmt_bool = False
        try:
            datetime.datetime.strptime(file, obj_dir_fmt)
            dt_fmt_bool = True
        except ValueError:
            pass
        if os.path.isdir(os.path.join(search_dir, file)) and dt_fmt_bool:
            obj_dir_list.append(os.path.join(search_dir, file))
    date_times = [datetime.datetime.strptime(os.path.basename(date_string), obj_dir_fmt) for date_string in obj_dir_list]
    sorted_obj_dirs = [obj_dir for _, obj_dir in sorted(zip(date_times, obj_dir_list), key=lambda x: x[0], reverse=True)]
    try:
        obj_dir_path = sorted_obj_dirs[0]
    except:
        # rad_gen_log("Warning: no latest obj_dir found in design output directory, creating new one", rad_gen_log_fd)
        obj_dir_path = None
    return obj_dir_path


# This function parses the top-level configuration file, initialized appropriate data structures and returns them

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
    safe_yaml_file = clean_path(yaml_file)
    with open(safe_yaml_file, 'r') as f:
        config = yaml.safe_load(f)
    
    return sanitize_config(config)

def clean_path(unsafe_path: str) -> str:
    """
        Takes in possibly unsafe path and returns a sanitized path
    """
    safe_path = os.path.realpath(os.path.expanduser(unsafe_path))
    handle_error(lambda: check_for_valid_path(safe_path), {True : None})
    return safe_path

"""

    Idea is to have the following structure for each subtool:
      - Subtools are defined by programs which take CLI args and are partioned by functionlity which users may want to run individually
        - Ex. 
            ASIC FLOW

    Modes of Operation:
    COFFE:
        - FULL CUSTOM
        - FULL CUSTOM + ASIC FLOW (hammer / custom)
        - PARSE REPORTS
            - COFFE PARSING
            - ASIC PARSING (FROM ASIC-DSE)
        CLI:
            - FULL CUSTOM OPTS
    ASIC-DSE:
        - ASIC FLOW
            CLI:
                - CONFIG FILE (Optional if appropriate settings passed through CLI)
                - ASIC FLOW SETTINGS (each can be CLI or conf passed)
                        RUN OPT SETTINGS:
                            - CUSTOM / HAMMER
                            - PARALLEL / SERIAL
                            - PARSE / RUN
                        ASIC FLOW SETTINGS:
                            - TOP LVL MOD
                            - RTL SRC DIR
                            ... 
        - DSE:
            CLI:
                - CONFIG FILE (Optional if appropriate settings passed through CLI)
                - DSE SETTINGS (each can be CLI or conf passed)
                        RUN OPT SETTINGS:
                            - SRAM GEN / RTL GEN / ASIC CONFIG GEN (Hammer / maybe something else ?? not sure now)
                                - ASIC CONFIG GEN = VLSI or RTL param sweeps
    
    3D-IC:
        - BUFFER DSE
        - PDN Modeling
"""


def init_dataclass(dataclass_type: Type, input_yaml_config: dict, add_arg_config: dict = {}) -> dict:
    """
        Initializes dictionary values for fields defined in input data structure, basically acts as sanitation for keywords defined in data class fields
        Returns a instantiation of the dataclass
    """
    dataclass_inputs = {}
    for field in dataclass_type.__dataclass_fields__:
        # if the field is read in from input yaml file
        if field in input_yaml_config.keys():
            dataclass_inputs[field] = input_yaml_config[field]
        # additional arg values for fields not defined in input yaml (defined in default_value_config[field])
        elif field in add_arg_config.keys():
            dataclass_inputs[field] = add_arg_config[field]
        if "path" in field and field in dataclass_inputs:
            if isinstance(dataclass_inputs[field], list):
                for idx, path in enumerate(dataclass_inputs[field]):
                    dataclass_inputs[field][idx] = os.path.realpath( os.path.expanduser(path) )
                    handle_error(lambda: check_for_valid_path(dataclass_inputs[field][idx]), {True : None})
            elif isinstance(dataclass_inputs[field], str):
                dataclass_inputs[field] = os.path.realpath( os.path.expanduser(dataclass_inputs[field]) )
                handle_error(lambda: check_for_valid_path(dataclass_inputs[field]), {True : None})
            else:
                pass
    # return created dataclass instance
    # The constructor below will fail if
    # - key in yaml != field name in dataclass 
    return dataclass_type(**dataclass_inputs)



def parse_rad_gen_top_cli_args() -> Tuple[argparse.Namespace, List[str], Dict[str, Any]]:
    """ 
        Parses the top level RAD-Gen args
    """                                   
    parser = argparse.ArgumentParser()

    # TODO see if theres a better way to do this but for now we have to manually define which args go to which tool with a list of tags
    # Define general tags, assuming we only call a single tool each time we should be able to seperate them from the subtool being run

    gen_arg_keys = [
        "top_config_path",
        "subtools"
    ]

    # TOP LEVEL CONFIG ARG
    parser.add_argument("-tc", "--top_config_path", help="path to RAD-GEN top level config file", type=str, default=None)
    # Subtool options are "coffe" "asic-dse" "3d-ic"
    parser.add_argument("-st", "--subtools", help="subtool to run", nargs="*", type=str, default=None)
    parsed_args, remaining_args = parser.parse_known_args()
    

    # Default value dictionary for any arg that has a non None or False for default value
    
    default_arg_vals = {}

    #     _   ___ ___ ___   ___  ___ ___     _   ___  ___ ___ 
    #    /_\ / __|_ _/ __| |   \/ __| __|   /_\ | _ \/ __/ __|
    #   / _ \\__ \| | (__  | |) \__ \ _|   / _ \|   / (_ \__ \
    #  /_/ \_\___/___\___| |___/|___/___| /_/ \_\_|_\\___|___/
    if "asic_dse" in parsed_args.subtools:
        
        default_arg_vals = {
            **default_arg_vals,
            "flow_mode": "hammer",
            "run_mode": "serial",
        }
        parser.add_argument('-r', '--run_mode', help="mode in which asic flow is run, either parallel or serial", type=str, choices=["parallel", "serial"], default="serial")
        parser.add_argument('-m', "--flow_mode", help="option for backend tool to generate scripts & run asic flow with", type=str, choices=["custom", "hammer"], default=default_arg_vals["flow_mode"])
        parser.add_argument('-e', "--env_config_path", help="path to asic-dse env config file", type=str, default=None)
        parser.add_argument('-t', '--top_lvl_module', help="name of top level design in HDL", type=str, default=None)
        parser.add_argument('-v', '--hdl_path', help="path to directory containing HDL files", type=str, default=None)
        parser.add_argument('-p', '--flow_config_paths', 
                            help="list of paths to hammer design specific config.yaml files",
                            nargs="*",
                            type=str,
                            default=None)
        parser.add_argument('-l', '--use_latest_obj_dir', help="uses latest obj dir found in rad_gen dir", action='store_true') 
        parser.add_argument('-o', '--manual_obj_dir', help="uses user specified obj dir", type=str, default=None)
        # parser.add_argument('-e', '--top_lvl_config', help="path to top level config file",  type=str, default=None)
        parser.add_argument('-s', '--design_sweep_config', help="path to config file containing design sweep parameters",  type=str, default=None)
        parser.add_argument('-c', '--compile_results', help="path to dir", action='store_true') 
        parser.add_argument('-syn', '--synthesis', help="flag runs synthesis on specified design", action='store_true') 
        parser.add_argument('-par', '--place_n_route', help="flag runs place & route on specified design", action='store_true') 
        parser.add_argument('-pt', '--primetime', help="flag runs primetime on specified design", action='store_true') 
        parser.add_argument('-sram', '--sram_compiler', help="flag enables srams to be run in design", action='store_true') 
        parser.add_argument('-make', '--make_build', help="flag enables make build system for asic flow", action='store_true') 

    #   ___ ___  ___ ___ ___     _   ___  ___ ___ 
    #  / __/ _ \| __| __| __|   /_\ | _ \/ __/ __|
    # | (_| (_) | _|| _|| _|   / _ \|   / (_ \__ \
    #  \___\___/|_| |_| |___| /_/ \_\_|_\\___|___/

    if "coffe" in parsed_args.subtools:
        default_arg_vals = {
            **default_arg_vals,
            "opt_type": "global",
            "initial_sizes": "default",
            "re_erf": 1,
            "area_opt_weight": 1,
            "delay_opt_weight": 1,
            "max_iterations": 6,
            "size_hb_interfaces": 0.0,
        }


        parser.add_argument('-a', '--fpga_arch_conf_path', help ="path to config file containing coffe FPGA arch information", type=str, default= None)
        parser.add_argument('-n', '--no_sizing', help="don't perform transistor sizing", action='store_true')
        parser.add_argument('-o', '--opt_type', type=str, choices=["global", "local"], default = default_arg_vals["opt_type"], help="choose optimization type")
        parser.add_argument('-s', '--initial_sizes', type=str, default = default_arg_vals["initial_sizes"], help="path to initial transistor sizes")
        parser.add_argument('-m', '--re_erf', type=int, default = default_arg_vals["re_erf"], help = "choose how many sizing combos to re-erf")
        parser.add_argument('-a', '--area_opt_weight', type=int, default = default_arg_vals["area_opt_weight"], help="area optimization weight")
        parser.add_argument('-d', '--delay_opt_weight', type=int, default = default_arg_vals["delay_opt_weight"], help="delay optimization weight")
        parser.add_argument('-i', '--max_iterations', type=int, default = default_arg_vals["max_iterations"] ,help="max FPGA sizing iterations")
        parser.add_argument('-hi', '--size_hb_interfaces', type=float, default=default_arg_vals["size_hb_interfaces"], help="perform transistor sizing only for hard block interfaces")
        #arguments for ASIC flow 
        parser.add_argument('-ho',"--hardblock_only",help="run only a single hardblock through the asic flow", action='store_true',default=False)
        parser.add_argument('-g',"--gen_hb_scripts",help="generates all hardblock scripts which can be run by a user",action='store_true',default=False)
        parser.add_argument('-p',"--parallel_hb_flow",help="runs the hardblock flow for current parameter selection in a parallel fashion",action='store_true',default=False)
        parser.add_argument('-r',"--parse_pll_hb_flow",help="parses the hardblock flow from previously generated results",action='store_true',default=False)

        # quick mode is disabled by default. Try passing -q 0.03 for 3% minimum improvement
        parser.add_argument('-q', '--quick_mode', type=float, default=-1.0, help="minimum cost function improvement for resizing")

    #   _______    ___ ___     _   ___  ___ ___ 
    #  |__ /   \  |_ _/ __|   /_\ | _ \/ __/ __|
    #   |_ \ |) |  | | (__   / _ \|   / (_ \__ \
    #  |___/___/  |___\___| /_/ \_\_|_\\___|___/
    if "ic_3d" in parsed_args.subtools:
        parser.add_argument('-p', '--plot_spice', help="takes the ubump output.lis file and plots single run values, is used for manual spice editing, does not write spice", action="store_true")
        parser.add_argument('-t', '--tsv_model', help="performs tsv modeling", action="store_true")
        parser.add_argument('-e', '--buffer_param_dse', help="sweeps parameters for buffer chain wire load, plots results", action="store_true")
        parser.add_argument('-c', '--input_config', help="top level input config file", type=str, default=None)
    
    args = parser.parse_args()
    return args, gen_arg_keys, default_arg_vals


def init_structs_top(args: argparse.Namespace, gen_arg_keys: List[str], default_arg_vals: Dict[str, Any]) -> Dict[str, Any]:
    # ARGS CAN BE PASSED FROM CONFIG OR CLI
    # NOTE: CLI ARGS OVERRIDE CONFIG ARGS!
    top_conf = {}
    if args.top_config_path is not None:
        top_conf = parse_yml_config(args.top_config_path)

    cli_dict = vars(args)

    # TODO include default values to be passed from the cli without overriding
    # Below currently parses the cli args and will always take the cli arg value over whats in the config file (if cli arg == None)
    # TODO add a way to say if cli_arg == default_cli_value && key exists in the config file -> then use the config file instead of cli 

    # Comparing two input param dicts one coming from cli and one from config file for each tool
    subtool_confs = {}
    for subtool in cli_dict["subtools"]:
        result_conf = {}
        for k_cli, v_cli in cli_dict.items():
            # We only want the parameters relevant to the subtool we're running (exclude top level args)
            # If one wanted to exclude other subtool args they could do it here
            if k_cli not in gen_arg_keys:
                for k_conf, v_conf in top_conf[subtool].items():
                    if k_conf == k_cli:
                        # If the cli key is not a default value or None/False AND cli key is not in the cli default values dictionary then we will use the cli value
                        if v_cli != None and v_cli != False and v_cli != default_arg_vals[k_cli]:
                            result_conf[k_conf] = v_cli
                        else:
                            result_conf[k_conf] = v_conf
                # if the cli key was not loaded into result config 
                # meaning it didnt exist in config file, we use whatever value was in cli
                if k_cli not in result_conf.keys():
                    result_conf[k_cli] = v_cli 
        subtool_confs[subtool] = result_conf

    # Before this function make sure all of the parameters have been defined in the dict with default values if not specified
    # TODO change the cli_dict to result dict wh
    rad_gen_info = {}
    # Loop through subtool keys and call init function to return data structures
    # init functions are in the form init_<subtool>_structs
    for subtool in subtool_confs.keys():
        fn_to_call = getattr(sys.modules[__name__], f"init_{subtool}_structs", None)
        if callable(fn_to_call):
            rad_gen_info[subtool] = fn_to_call(subtool_confs[subtool]) 
        else:
            raise ValueError(f"ERROR: {subtool} is not a valid subtool ('init_{subtool}_structs' is not a defined function)")
    return rad_gen_info
    

def init_asic_dse_structs(asic_dse_conf: Dict[str, Any]) -> rg_ds.HighLvlSettings:
    """
        Initializes the data structures used by the ASIC DSE flow:
        ASIC-DSE:
            CLI:
                - CONFIG FILE (Optional if appropriate settings passed through CLI)
                - DSE SETTINGS (each can be CLI or conf passed)
                        RUN OPT SETTINGS:
                            - SRAM GEN / RTL GEN / ASIC CONFIG GEN (Hammer / maybe something else ?? not sure now)
                                - ASIC CONFIG GEN = VLSI or RTL param sweeps
    """ 

    # For each CLI / config input we need to check that it exists in dict and is not None
    if asic_dse_conf["env_config_path"] != None:
        env_conf = parse_yml_config(asic_dse_conf["env_config_path"])
    else:
        raise ValueError(f"ASIC-DSE env config file not provided from {asic_dse_conf['env_config_path']}")
    
    script_info_inputs = env_conf["scripts"] if "scripts" in env_conf.keys() else {}
    scripts_info = init_dataclass(rg_ds.ScriptInfo, script_info_inputs)

    # create additional dicts for argument passed information
    env_inputs = {
        # TODO change in EnvSettings to be env_config_path
        "env_config_path": asic_dse_conf["env_config_path"],
        "scripts_info": scripts_info,
    }
    env_settings = init_dataclass(rg_ds.EnvSettings, env_conf["env"], env_inputs)

    # TODO we should get tech info from another place, but for determining ASAP7 rundir is kinda hard
    tech_info = init_dataclass(rg_ds.TechInfo, env_conf["tech"], {})

    asic_flow_settings_input = {} # asic flow settings
    mode_inputs = {} # Set appropriate tool modes
    vlsi_mode_inputs = {} # vlsi flow modes
    high_lvl_inputs = {} # high level setting parameters (associated with a single invocation of rad_gen from cmd line)
    design_sweep_infos = [] # list of design sweep info objects
    if asic_dse_conf["design_sweep_config"] != None:
        ######################################################
        #  _____      _____ ___ ___   __  __  ___  ___  ___  #
        # / __\ \    / / __| __| _ \ |  \/  |/ _ \|   \| __| #
        # \__ \\ \/\/ /| _|| _||  _/ | |\/| | (_) | |) | _|  #
        # |___/ \_/\_/ |___|___|_|   |_|  |_|\___/|___/|___| #
        ######################################################                               
        asic_flow_settings = rg_ds.ASICFlowSettings() 
        # If a sweep file is specified with result compile flag, results across sweep points will be compiled
        if not asic_dse_conf["compile_results"]:
            mode_inputs["sweep_gen"] = True # generate config, rtl, etc related to sweep config
        else:
            mode_inputs["result_parse"] = True # parse results for each sweep point
        
        sweep_config = parse_yml_config(asic_dse_conf["design_sweep_config"])

        high_lvl_inputs["sweep_config_path"] = asic_dse_conf["design_sweep_config"]
        # By default set the result search path to the design output path, possibly could be changed in later functions if needed
        high_lvl_inputs["result_search_path"] = env_settings.design_output_path

        for design in sweep_config["designs"]:
            sweep_type_inputs = {} # parameters for a specific type of sweep
            if design["type"] == "sram":
                sweep_type_info = init_dataclass(rg_ds.SRAMSweepInfo, design, sweep_type_inputs)
            elif design["type"] == "rtl_params":
                sweep_type_info = init_dataclass(rg_ds.RTLSweepInfo, design, sweep_type_inputs)
            elif design["type"] == "vlsi_params":
                sweep_type_info = init_dataclass(rg_ds.VLSISweepInfo, design, sweep_type_inputs)
            
            design_inputs = {}
            design_inputs["type_info"] = sweep_type_info
            design_sweep_infos.append(init_dataclass(rg_ds.DesignSweepInfo, design, design_inputs))
    # Currently only enabling VLSI mode when other modes turned off
    else:
        ################################################
        # \ \ / / |  / __|_ _| |  \/  |/ _ \|   \| __| #
        #  \ V /| |__\__ \| |  | |\/| | (_) | |) | _|  #
        #   \_/ |____|___/___| |_|  |_|\___/|___/|___| #
        ################################################
        # Initializes Data structures to be used for running stages in ASIC flow

        design_sweep_infos = None
        
        if asic_dse_conf["flow_config_paths"] != None:
            # enable asic flow to be run
            vlsi_mode_inputs["enable"] = True
            vlsi_mode_inputs["flow_mode"] = asic_dse_conf["flow_mode"]
            vlsi_mode_inputs["run_mode"] = asic_dse_conf["run_mode"]
    
            if asic_dse_conf["flow_mode"] == "custom":
                asic_flow_settings = None
                # Don't want any preprocessing on custom flow
                vlsi_mode_inputs["config_pre_proc"] = False

                print("WARNING: Custom flow mode requires the following tools:")
                print("\tSynthesis: Snyopsys Design Compiler")
                print("\tPlace & Route: Cadence Encounter OR Innovus")
                print("\tTiming & Power: Synopsys PrimeTime")
                # If custom flow is enabled there should only be a single config file
                assert len(asic_dse_conf["flow_config_paths"]) == 1, "ERROR: Custom flow mode requires a single config file"
                custom_asic_flow_settings = load_params(clean_path(asic_dse_conf["flow_config_paths"][0]))

            elif asic_dse_conf["flow_mode"] == "hammer":
                custom_asic_flow_settings = None

                # Initialize a Hammer Driver, this will deal with the defaults & will allow us to load & manipulate configs before running hammer flow
                driver_opts = HammerDriver.get_default_driver_options()
                # update values
                driver_opts = driver_opts._replace(environment_configs = list(env_settings.env_paths))
                driver_opts = driver_opts._replace(project_configs = list(asic_dse_conf["flow_config_paths"]))
                hammer_driver = HammerDriver(driver_opts)

                # if cli provides a top level module and hdl path, we will modify the provided design config file to use them
                if asic_dse_conf["top_lvl_module"] != None and asic_dse_conf["hdl_path"] != None:
                    vlsi_mode_inputs["config_pre_proc"] = True
                    asic_flow_settings_input["top_lvl_module"] = asic_dse_conf["top_lvl_module"]
                    asic_flow_settings_input["hdl_path"] = asic_dse_conf["hdl_path"]
                else:
                    vlsi_mode_inputs["config_pre_proc"] = False
                    asic_flow_settings_input["top_lvl_module"] = hammer_driver.database.get_setting("synthesis.inputs.top_module")
                
                # Create output directory for obj dirs to be created inside of
                out_dir = os.path.join(env_settings.design_output_path, asic_flow_settings_input["top_lvl_module"])
                obj_dir_fmt = f"{asic_flow_settings_input['top_lvl_module']}-{rg_ds.create_timestamp()}"
                
                # TODO restrict input to only accept one of below two options
                obj_dir_path = None
                # Users can specify a specific obj directory
                if asic_dse_conf["manual_obj_dir"] != None:
                    obj_dir_path = os.path.realpath(os.path.expanduser(asic_dse_conf["manual_obj_dir"]))
                # Or they can use the latest created obj dir
                elif asic_dse_conf["use_latest_obj_dir"]:
                    if os.path.isdir(out_dir):
                        obj_dir_path = find_newest_obj_dir(search_dir = out_dir, obj_dir_fmt = f"{asic_flow_settings_input['top_lvl_module']}-{rg_ds.create_timestamp(fmt_only_flag = True)}")
                # If no value given or no obj dir found, we will create a new one
                if obj_dir_path == None:
                    obj_dir_path = os.path.join(out_dir,obj_dir_fmt)

                if not os.path.isdir(obj_dir_path):
                    os.makedirs(obj_dir_path)

                # rad_gen_log(f"Using obj_dir: {obj_dir_path}",rad_gen_log_fd)

                hammer_driver.obj_dir = obj_dir_path
                # At this point hammer driver should be fully initialized
                asic_flow_settings_input["hammer_driver"] = hammer_driver
                asic_flow_settings_input["obj_dir_path"] = obj_dir_path

                # if not specified the flow will run all the stages by defualt
                run_all_flow = not (asic_dse_conf["synthesis"] or asic_dse_conf["place_n_route"] or asic_dse_conf["primetime"]) and not asic_dse_conf["compile_results"]
                
                asic_flow_settings_input["make_build"] = asic_dse_conf["make_build"]
                asic_flow_settings_input["run_sram"] = asic_dse_conf["sram_compiler"]
                asic_flow_settings_input["run_syn"] = asic_dse_conf["synthesis"] or run_all_flow
                asic_flow_settings_input["run_par"] = asic_dse_conf["place_n_route"] or run_all_flow
                asic_flow_settings_input["run_pt"] = asic_dse_conf["primetime"] or run_all_flow
                # TODO implement "flow_stages" element of ASICFlowSettings struct
                if "asic_flow" in env_conf.keys():
                    config_file_input = env_conf["asic_flow"]
                else:
                    config_file_input = {}
                asic_flow_settings = init_dataclass(rg_ds.ASICFlowSettings, config_file_input, asic_flow_settings_input)

        else:
            print("ERROR: no flow config files provided, cannot run ASIC flow")

    vlsi_flow = init_dataclass(rg_ds.VLSIMode, vlsi_mode_inputs, {})
    rad_gen_mode = init_dataclass(rg_ds.RADGenMode, mode_inputs, {"vlsi_flow" : vlsi_flow})
    high_lvl_inputs = {
        **high_lvl_inputs,
        "mode": rad_gen_mode,
        "tech_info": tech_info,
        "design_sweep_infos": design_sweep_infos,
        "asic_flow_settings": asic_flow_settings,
        "custom_asic_flow_settings": custom_asic_flow_settings,
        "env_settings": env_settings,
    }
    high_lvl_settings = init_dataclass(rg_ds.HighLvlSettings, high_lvl_inputs, {})

    return high_lvl_settings


def init_coffe_structs(coffe_conf: Dict[str, Any]):
    pass



def init_3d_ic_structs(ic_3d_conf: Dict[str, Any]):
    pass



# COMMENTED BELOW RUN_OPTS (args) as they are not used
def load_params(filename): #,run_options):
    # This is the dictionary of parameters we expect to find
    #No defaults for ptn or run settings
    hard_params = {
        'name': "",
        'num_gen_inputs': -1,
        'crossbar_population': -1.0,
        'height': -1,
        'num_gen_outputs': -1,
        'num_crossbars': -1,
        'crossbar_modelling': "",
        'num_dedicated_outputs': -1,
        'soft_logic_per_block': -1.0,
        'area_scale_factor': -1.0,
        'freq_scale_factor': -1.0,
        'power_scale_factor': -1.0,
        'input_usage': -1.0,
        # Flow Settings:
        'design_folder': "",
        'design_language': '',
        'clock_pin_name': "",
        'top_level': "",
        'synth_folder': "",
        'show_warnings': False,
        'synthesis_only': False,
        'read_saif_file': False,
        'static_probability': -1.0,
        'toggle_rate': -1,
        'target_libraries': [],
        'lef_files': [],
        'best_case_libs': [],
        'standard_libs': [],
        'worst_case_libs': [],
        'power_ring_width': -1.0,
        'power_ring_spacing': -1.0,
        'height_to_width_ratio': -1.0,
        #sweep params
        'clock_period': [],
        'wire_selection' : [],
        'metal_layers': [],
        'core_utilization': [],
        'mode_signal': [],  
        #
        'space_around_core': -1,
        'pr_folder': "",
        'primetime_libs': [],
        'primetime_folder': "" ,
        'delay_cost_exp': 1.0,
        'area_cost_exp': 1.0,
        'metal_layer_names': [],
        'power_ring_metal_layer_names' : [],
        'map_file': '',
        'gnd_net': '',
        'gnd_pin': '',
        'pwr_net': '',
        'pwr_pin': '',
        'tilehi_tielo_cells_between_power_gnd': True,
        'inv_footprint': '',
        'buf_footprint': '',
        'delay_footprint': '',
        'filler_cell_names': [],
        'generate_activity_file': False,
        'core_site_name':'',
        'process_lib_paths': [],
        'process_params_file': "",
        'pnr_tool': "",
        'process_size': -1,
        'ptn_settings_file': "",
        'partition_flag': False,
        'ungroup_regex': "",
        'mp_num_cores': -1,
        'parallel_hardblock_folder': "",
        'condensed_results_folder': "",
        'coffe_repo_path': "~/COFFE",
        'hb_run_params': {},
        'ptn_params': {}
    }
    
    #top level param types
    param_type_names = ["fpga_arch_params","asic_hardblock_params"]
    hb_sub_param_type_names = ["hb_run_params", "ptn_params"]
    #get values from yaml file
    with open(filename, 'r') as file:
        param_dict = yaml.safe_load(file)

    # FPGA PARAMS
    # #check to see if the input settings file is a subset of defualt params
    # for key in arch_params.keys():
    #     if(key not in param_dict["fpga_arch_params"].keys()):
    #         #assign default value if key not found 
    #         param_dict["fpga_arch_params"][key] = arch_params[key]

    if("asic_hardblock_params" in param_dict.keys()):
        #check to see if the input settings file is a subset of defualt hb params
        for key in hard_params.keys():
            for hb_idx, hb_params in enumerate(param_dict["asic_hardblock_params"]["hardblocks"]):
                if(key not in hb_params.keys()):
                    #assign default value if key not found 
                    param_dict["asic_hardblock_params"]["hardblocks"][hb_idx][key] = hard_params[key]
    #load defaults into unspecified values
    for k,v in param_dict.items():
        #if key exists in arch_dict
        if(k in param_type_names):
            for k1,v1 in v.items():
                #parse arch params
                # if(k1 in arch_params):
                #     if(v1 == None):
                #         v[k1] = arch_params[k1]
                #parse hb params
                if(k1 == "hardblocks"):
                    # for each hardblock in the design
                    for hb_idx, hb in enumerate(v[k1]):
                        for k2,v2 in hb.items():
                            if(k2 in hard_params):
                                #if the value in yaml dict is empty, assign defualt val from above dict 
                                if(v2 == None):
                                    v[k1][hb_idx][k2] = hard_params[k2]
                elif(k1 in hb_sub_param_type_names):
                    pass
                else:
                    print("ERROR: Found invalid parameter (" + k1 + ") in " + filename)
                    sys.exit()

    if("asic_hardblock_params" in param_dict.keys()):
        for hb_param in param_dict["asic_hardblock_params"]["hardblocks"]:
            for param,value in zip(list(hb_param),list(hb_param.values())):
                ## TODO HARDBLOCK STUFF
                if param == 'name':
                    hb_param['name'] = str(value)
                elif param == 'num_gen_inputs':
                    hb_param['num_gen_inputs'] = int(value)
                elif param == 'crossbar_population':
                    hb_param['crossbar_population'] = float(value)
                elif param == 'height':
                    hb_param['height'] = int(value)
                elif param == 'num_gen_outputs':
                    hb_param['num_gen_outputs'] = int(value)
                elif param == 'num_dedicated_outputs':
                    hb_param['num_dedicated_outputs'] = int(value)
                elif param == 'soft_logic_per_block':
                    hb_param['soft_logic_per_block'] = float(value)
                elif param == 'area_scale_factor':
                    hb_param['area_scale_factor'] = float(value)
                elif param == 'freq_scale_factor':
                    hb_param['freq_scale_factor'] = float(value)
                elif param == 'power_scale_factor':
                    hb_param['power_scale_factor'] = float(value)  
                elif param == 'input_usage':
                    hb_param['input_usage'] = float(value)  
                elif param == 'delay_cost_exp':
                    hb_param['delay_cost_exp'] = float(value)  
                elif param == 'area_cost_exp':
                    hb_param['area_cost_exp'] = float(value)              
                #flow parameters:
                elif param == 'design_folder':
                    hb_param['design_folder'] = str(value)
                elif param == 'design_language':
                    hb_param['design_language'] = str(value)
                elif param == 'clock_pin_name':
                    hb_param['clock_pin_name'] = str(value)
                #STR CONVERTED LIST
                elif param == 'clock_period':
                    hb_param['clock_period'] = [str(v) for v in value]
                elif param == 'core_utilization':
                    hb_param['core_utilization'] = [str(v) for v in value]
                elif param == 'filler_cell_names':
                    hb_param['filler_cell_names'] = [str(v) for v in value]
                elif param == 'metal_layer_names':
                    hb_param['metal_layer_names'] = [str(v) for v in value]
                elif param == 'metal_layers':
                    hb_param['metal_layers'] = [str(v) for v in value]
                elif param == 'wire_selection':
                    hb_param['wire_selection'] = [str(v) for v in value]
                ##########################
                elif param == 'map_file':
                    hb_param['map_file'] = value.strip()
                elif param == 'tilehi_tielo_cells_between_power_gnd':
                    hb_param['tilehi_tielo_cells_between_power_gnd'] = bool(value)
                elif param == 'generate_activity_file':
                    hb_param['generate_activity_file'] = bool(value)
                elif param == 'crossbar_modelling':
                    hb_param['crossbar_modelling'] = str(value)
                elif param == 'num_crossbars':
                    hb_param['num_crossbars'] = int(value)
                elif param == 'top_level':
                    hb_param['top_level'] = str(value)
                elif param == 'synth_folder':
                    hb_param['synth_folder'] = str(value)
                elif param == 'show_warnings':
                    hb_param['show_warnings'] = bool(value)
                elif param == 'synthesis_only':
                    hb_param['synthesis_only'] = bool(value)
                elif param == 'read_saif_file':
                    hb_param['read_saif_file'] = bool(value)
                elif param == 'static_probability':
                    hb_param['static_probability'] = str(value)
                elif param == 'toggle_rate':
                    hb_param['toggle_rate'] = str(value)
                elif param == 'power_ring_width':
                    hb_param['power_ring_width'] = str(value)
                elif param == 'power_ring_spacing':
                    hb_param['power_ring_spacing'] = str(value)
                elif param == 'height_to_width_ratio':
                    hb_param['height_to_width_ratio'] = str(value)
                elif param == 'space_around_core':
                    hb_param['space_around_core'] = str(value)
                elif param == 'pr_folder':
                    hb_param['pr_folder'] = str(value)
                elif param == 'primetime_folder':
                    hb_param['primetime_folder'] = str(value)
                elif param == 'mode_signal':
                    hb_param['mode_signal'] = (value)
                elif param == "process_params_file":
                    hb_param["process_params_file"] = str(value)
                elif param == "pnr_tool":
                    hb_param["pnr_tool"] = str(value)
                elif param == "partition_flag":
                    hb_param["partition_flag"] = bool(value)
                elif param == "ptn_settings_file":
                    hb_param["ptn_settings_file"] = str(value)
                elif param == "ungroup_regex":
                    hb_param["ungroup_regex"] = str(value)
                elif param == "mp_num_cores":
                    hb_param["mp_num_cores"] = int(value)
                elif param == "parallel_hardblock_folder":
                    hb_param["parallel_hardblock_folder"] = os.path.expanduser(str(value))
                elif param == "run_settings_file":
                    hb_param["run_settings_file"] = os.path.expanduser(str(value))
                elif param == "condensed_results_folder":
                    hb_param["condensed_results_folder"] = os.path.expanduser(str(value))
                elif param == "coffe_repo_path":
                    hb_param["coffe_repo_path"] = os.path.expanduser(str(value))
                #To allow for the legacy way of inputting process specific params I'll keep these in (the only reason for having a seperate file is for understandability)
                if param == "process_lib_paths":
                    hb_param["process_lib_paths"] = (value)
                elif param == "primetime_libs":
                    hb_param["primetime_libs"] = (value)
                elif param == 'target_libraries':
                    hb_param['target_libraries'] = (value)
                elif param == 'lef_files':
                    hb_param['lef_files'] = (value)
                elif param == 'best_case_libs':
                    hb_param['best_case_libs'] = (value)
                elif param == 'standard_libs':
                    hb_param['standard_libs'] = (value)
                elif param == 'worst_case_libs':
                    hb_param['worst_case_libs'] = (value)
                elif param == 'core_site_name':
                    hb_param['core_site_name'] = str(value)
                elif param == 'inv_footprint':
                    hb_param['inv_footprint'] = value.strip()
                elif param == 'buf_footprint':
                    hb_param['buf_footprint'] = value.strip()
                elif param == 'delay_footprint':
                    hb_param['delay_footprint'] = value.strip()
                elif param == 'power_ring_metal_layer_names':
                    hb_param['power_ring_metal_layer_names'] = (value)
                elif param == 'gnd_net':
                    hb_param['gnd_net'] = value.strip()
                elif param == 'gnd_pin':
                    hb_param['gnd_pin'] = value.strip()
                elif param == 'pwr_net':
                    hb_param['pwr_net'] = value.strip()
                elif param == 'pwr_pin':
                    hb_param['pwr_pin'] = value.strip()
                elif param == "process_size":
                    hb_param["process_size"] = str(value)
                
            input_param_options = {
                "period" : "float",
                "wiremdl" : "str",
                "mlayer" : "int",
                "util" : "float",
                "dimlen" : "float",
                "mode" : "int"
            }
            hb_param["input_param_options"] = input_param_options
            # COMMENTING OUT FOR INTEGRATION TODO FIX 
            # check_hard_params(hb_param,run_options)
    return param_dict    