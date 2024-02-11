
from typing import List, Dict, Tuple, Set, Union, Any, Type, Callable
import os, sys, yaml
import argparse
import datetime
import shutil

import logging


import shapely as sh


from dataclasses import fields, field

from pathlib import Path
import copy


#Import hammer modules
import third_party.hammer.hammer.config as hammer_config
from third_party.hammer.hammer.vlsi.hammer_vlsi_impl import HammerVLSISettings 
from third_party.hammer.hammer.vlsi.driver import HammerDriver
import third_party.hammer.hammer.tech as hammer_tech
from third_party.hammer.hammer.config import load_config_from_string
from third_party.hammer.hammer.vlsi.cli_driver import dump_config_to_json_file


# RAD-Gen modules
import src.common.data_structs as rg_ds

# COFFE modules
import src.coffe.utils as coffe_utils

import csv
import re
import subprocess as sp 
import pandas as pd

# Common modules
from collections.abc import MutableMapping

# temporary imports from rad_gen main for testing ease

rad_gen_log_fd = "asic_dse.log"
log_verbosity = 2
cur_env = os.environ.copy()


# ██╗      ██████╗  ██████╗  ██████╗ ██╗███╗   ██╗ ██████╗ 
# ██║     ██╔═══██╗██╔════╝ ██╔════╝ ██║████╗  ██║██╔════╝ 
# ██║     ██║   ██║██║  ███╗██║  ███╗██║██╔██╗ ██║██║  ███╗
# ██║     ██║   ██║██║   ██║██║   ██║██║██║╚██╗██║██║   ██║
# ███████╗╚██████╔╝╚██████╔╝╚██████╔╝██║██║ ╚████║╚██████╔╝
# ╚══════╝ ╚═════╝  ╚═════╝  ╚═════╝ ╚═╝╚═╝  ╚═══╝ ╚═════╝ 

def log_format_list(*args : Tuple[str]) -> str:
    # Format the extra arguments as [{arg1}][{arg2}]...[{argN}]
    if args:
        formatted_args = "".join([f"[{arg}]" for arg in args]) + ":"
    else:
        formatted_args = ":"
    return formatted_args

# def custom_log(logger: logging.Logger, msg: str, *args):
#     # Format the extra arguments as [{arg1}][{arg2}]...[{argN}]
#     if args:
#         formatted_args = "".join([f"[{arg}]" for arg in args])
#     else:
#         formatted_args = ""
#     extra = {"formatted_args": formatted_args}
#     logger.debug(msg, extra=extra)

#  ██████╗ ███████╗███╗   ██╗███████╗██████╗  █████╗ ██╗         ██╗   ██╗████████╗██╗██╗     ███████╗
# ██╔════╝ ██╔════╝████╗  ██║██╔════╝██╔══██╗██╔══██╗██║         ██║   ██║╚══██╔══╝██║██║     ██╔════╝
# ██║  ███╗█████╗  ██╔██╗ ██║█████╗  ██████╔╝███████║██║         ██║   ██║   ██║   ██║██║     ███████╗
# ██║   ██║██╔══╝  ██║╚██╗██║██╔══╝  ██╔══██╗██╔══██║██║         ██║   ██║   ██║   ██║██║     ╚════██║
# ╚██████╔╝███████╗██║ ╚████║███████╗██║  ██║██║  ██║███████╗    ╚██████╔╝   ██║   ██║███████╗███████║
#  ╚═════╝ ╚══════╝╚═╝  ╚═══╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝     ╚═════╝    ╚═╝   ╚═╝╚══════╝╚══════╝

def format_csv_data(data: List[List[Any]]) -> List[List[str]]:
    # Specify the width for each column
    column_widths = [max(len(str(value)) for value in column) + 2 for column in zip(*data)]

    # Format the rows
    formatted_rows = []
    for row in data:
        formatted_row = [str(value).ljust(width) for value, width in zip(row, column_widths)]
        formatted_rows.append(formatted_row)

    return formatted_rows


def flatten(dictionary, parent_key='', separator='.'):
    """
        Turns a nested dictionary into a flattened one with seperator delimited keys
        Ex.
            - Input: {"a": {"b": 1, "c": 2}, "d": {"e": {"f": 3}}}
            - Output: {"a.b": 1, "a.c": 2, "d.e.f": 3}
    """
    items = []
    for key, value in dictionary.items():
        new_key = parent_key + separator + key if parent_key else key
        if isinstance(value, MutableMapping):
            items.extend(flatten(value, new_key, separator=separator).items())
        else:
            items.append((new_key, value))
    return dict(items)

def key_val_2_report(key: str, val: Any) -> Tuple[str, Any]:
    """
        Converts various datatypes defined in RAD-Gen to thier report formats for stdout or csv writing
    """
    ret_key = key
    if isinstance(val, float):
        ret_val = float(val)
    elif isinstance(val, rg_ds.SolderBumpInfo):
        # if solder bump info we just want to print out pitch
        ret_key = "ubump_pitch"
        ret_val = val.pitch
    elif isinstance(val, rg_ds.ProcessInfo):
        # if process info we just want the name of the process
        ret_key = "process"
        ret_val = val.name
    else:
        ret_val = val
    return ret_key, ret_val

def rad_gen_log(log_str: str, file: str):
    """
    Prints to a log file and the console depending on level of verbosity
    log codes:
    {
        "info"
        "debug"
        "error"
    }
    """
    if file == sys.stdout:
        print(f"{log_str}")
    else:
        fd = open(file, 'a')
        if(log_verbosity >= 0):
            print(f"{log_str}",file=fd)
            print(f"{log_str}")
        fd.close()


def write_csv_file(filename, formatted_data):
    """
    Write formatted data to a CSV file.

    Parameters:
    - filename (str): The name of the CSV file to be created or overwritten.
    - formatted_data (list): A list of lists containing formatted data.
      Each inner list represents a row, and its elements are left-aligned
      strings with specified widths.

    Example Usage:
    data = [
        ['Name', 'Age', 'City'],
        ['John Doe', 25, 'New York'],
        ['Jane Smith', 30, 'San Francisco'],
        ['Bob Johnson', 22, 'Chicago'],
    ]

    formatted_data = format_csv_data(data)
    write_csv_file('output.csv', formatted_data)
    """
    with open(filename, 'w', newline='') as csvfile:
        csv_writer = csv.writer(csvfile)
        csv_writer.writerows(formatted_data)

def are_lists_mutually_exclusive(lists: List[List[Any]]):
    return all(not set(lists[i]) & set(lists[j]) for i in range(len(lists)) for j in range(i + 1, len(lists)))

def write_dict_to_csv(csv_lines,csv_fname):
    csv_fd = open(f"{csv_fname}.csv","w")
    writer = csv.DictWriter(csv_fd, fieldnames=csv_lines[0].keys())
    writer.writeheader()
    for line in csv_lines:
        writer.writerow(line)
    csv_fd.close()


def check_for_valid_path(path):
    ret_val = False
    if os.path.exists(os.path.abspath(path)):
        ret_val = True
    else:
        rad_gen_log(f"ERROR: {path} does not exist", rad_gen_log_fd)
        raise FileNotFoundError(f"ERROR: {path} does not exist")
    return ret_val

def handle_error(fn, expected_vals: set=None):
    # for fn in funcs:
    if not fn() or (expected_vals is not None and fn() not in expected_vals):
        sys.exit(1)


def create_bordered_str(text: str = "", border_char: str = "#", total_len: int = 150) -> list:
    text = f"  {text}  "
    text_len = len(text)
    if(text_len > total_len):
        total_len = text_len + 10 
    border_size = (total_len - text_len) // 2
    return [ border_char * total_len, f"{border_char * border_size}{text}{border_char * border_size}", border_char * total_len]


def c_style_comment_rm(text):
    """ 
        This function removes c/c++ style comments from a file
        WARNING does not work for all cases (such as escaped characters and other edge cases of comments) but should work for most
    """
    def replacer(match):
        s = match.group(0)
        if s.startswith('/'):
            return " " # note: a space and not an empty string
        else:
            return s
    pattern = re.compile(
        r'//.*?$|/\*.*?\*/|\'(?:\\.|[^\\\'])*\'|"(?:\\.|[^\\"])*"',
        re.DOTALL | re.MULTILINE
    )
    return re.sub(pattern, replacer, text)


def rec_find_fpath(dir: str,fname: str) -> Union[str, None]:
    """
    Finds a file recursivley in a directory and returns the path to it
    """
    ret_val = None
    for root, dirs, files in os.walk(dir):
        if fname in files:
            ret_val = os.path.join(root, fname)
    return ret_val
                                                              
def pretty(d, indent=0):
   """
    Pretty prints a dictionary
   """
   for key, value in d.items():
      print('\t' * indent + str(key))
      if isinstance(value, dict):
         pretty(value, indent+1)
      else:
         print('\t' * (indent+1) + str(value))

def truncate(f, n):
    '''
        Truncates/pads a float f to n decimal places without rounding
    '''
    s = '{}'.format(f)
    if 'e' in s or 'E' in s:
        return '{0:.{1}f}'.format(f, n)
    i, p, d = s.partition('.')
    return '.'.join([i, (d+'0'*n)[:n]])

def flatten_mixed_list(input_list):
    """
        Flattens a list with mixed value Ex. ["hello", ["billy","bob"],[["johnson"]]] -> ["hello", "billy","bob","johnson"]
    """
    # Create flatten list lambda function
    flat_list = lambda input_list:[element for item in input_list for element in flat_list(item)] if type(input_list) is list else [input_list]
    # Call lambda function
    flattened_list = flat_list(input_list)
    return flattened_list

def run_shell_cmd(cmd_str,log_file):
    run_cmd = cmd_str + f" | tee {log_file}"
    rad_gen_log(f"Running: {run_cmd}",rad_gen_log_fd)
    sp.call(run_cmd,shell=True,executable='/bin/bash',env=cur_env)

def run_shell_cmd_no_logs(cmd_str: str, to_log: bool = True):
    if to_log:
        log_fd = rad_gen_log_fd
    else:
        log_fd = sys.stdout
    rad_gen_log(f"Running: {cmd_str}", log_fd)
    run_out = sp.Popen([cmd_str], executable='/bin/bash', env=cur_env, stderr=sp.PIPE, stdout=sp.PIPE, shell=True)
    run_stdout = ""
    for line in iter(run_out.stdout.readline, ""):
        if(run_out.poll() is None):
            run_stdout += line.decode("utf-8")
            if log_verbosity >= 2: 
                sys.stdout.buffer.write(line)
        else:
            break
    if log_verbosity >= 2: 
        _, run_stderr = run_out.communicate()
    else:
        run_stdout, run_stderr = run_out.communicate()
        run_stdout = run_stdout.decode("utf-8")
    run_stderr = run_stderr.decode("utf-8")
    return run_stdout, run_stderr

def run_shell_cmd_safe_no_logs(cmd_str: str):
    print(f"Running: {cmd_str}")
    ret_code = sp.call(cmd_str, executable='/bin/bash', env=cur_env, shell=True)
    return ret_code


def run_csh_cmd(cmd_str):
    rad_gen_log(f"Running: {cmd_str}",rad_gen_log_fd)
    sp.call(['csh', '-c', cmd_str])

    

def rec_get_flist_of_ext(design_dir_path,hdl_exts):
    """
    Takes in a path and recursively searches for all files of specified extension, returns dirs of those files and file paths in two lists
    """
    design_folder = os.path.expanduser(design_dir_path)
    design_files = [os.path.abspath(os.path.join(r,fn)) for r, _, fs in os.walk(design_folder) for fn in fs if fn.endswith(tuple(hdl_exts))]
    design_dirs = [os.path.abspath(r) for r, _, fs in os.walk(design_folder) for fn in fs if fn.endswith(tuple(hdl_exts))]
    design_dirs = list(dict.fromkeys(design_dirs))

    return design_files,design_dirs

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


def sanitize_config_depr(config_dict) -> dict:
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

def get_df_output_lines(df: pd.DataFrame) -> List[str]:
    max_col_lens = max([len(str(col)) for col in df.columns])
    row_strings = [0]
    for col in df.columns:
        for row_idx in df.index:
            if isinstance(df[col].iloc[row_idx], str):
                row_strings.append(len(df[col].iloc[row_idx]))
    cell_chars = max(max_col_lens, max(row_strings) )


    # cell_chars = 40
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


def find_newest_file(search_dir: str, file_fmt: str, is_dir = True):
    """
        Finds newest file corresponding to current design in the specified RAD-Gen output directory.
        The file_fmt string is used to determine what date time & naming convension we're using to compare
        - If no files found, None will be returned signaling that one must be created
    """

    # dir were looking for obj dirs in
    #search_dir = os.path.join(rad_gen_settings.env_settings.design_output_path, rad_gen_settings.asic_flow_settings.top_lvl_module)

    # find the newest obj_dir
    file_list = []
    for file in os.listdir(search_dir):
        dt_fmt_bool = False
        try:
            datetime.datetime.strptime(file, file_fmt)
            dt_fmt_bool = True
        except ValueError:
            pass
        if is_dir:
            if os.path.isdir(os.path.join(search_dir, file)) and dt_fmt_bool:
                file_list.append(os.path.join(search_dir, file))
        else:
            if os.path.isfile(os.path.join(search_dir, file)) and dt_fmt_bool:
                file_list.append(os.path.join(search_dir, file))
    date_times = [datetime.datetime.strptime(os.path.basename(date_string), file_fmt) for date_string in file_list]
    sorted_files = [file for _, file in sorted(zip(date_times, file_list), key=lambda x: x[0], reverse=True)]
    try:
        file_path = sorted_files[0]
    except:
        # rad_gen_log("Warning: no latest obj_dir found in design output directory, creating new one", rad_gen_log_fd)
        file_path = None
    return file_path

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

def handle_error(fn, expected_vals: set = None):
    # for fn in funcs:
    if not fn() or (expected_vals is not None and fn() not in expected_vals):
        sys.exit(1)


def clean_path(unsafe_path: str, validate_path: bool = True) -> str:
    """
        Takes in possibly unsafe path and returns a sanitized path
    """
    safe_path = os.path.realpath(os.path.expanduser(unsafe_path))
    # We want to turn off the path checker when loading in yaml files which may have invalid entries
    if validate_path:
        handle_error(lambda: check_for_valid_path(safe_path), {True : None})
    return safe_path

def traverse_nested_dict(in_dict: Dict[str, Any], callable_fn: Callable, *args, **kwargs) -> Dict[str, Any]:
    assert callable(callable_fn), "callable_fn must be a function"
    for k,v in in_dict.items():
        if isinstance(v, dict):
            in_dict[k] = traverse_nested_dict(v, callable_fn, *args, **kwargs)
        elif isinstance(v, list) and any(isinstance(ele, dict) for ele in v):
                in_dict[k] = []
                for ele in v:
                    if isinstance(ele, dict):
                        # Pass to the traverse_nested_dict function again, adding the "parent_key" to the dickt to give info to following function
                        in_dict[k].append(traverse_nested_dict(ele, callable_fn, *args, **dict(kwargs, parent_key=k) ))
                    else:
                        raise Exception("ERROR: Currently mixing dicts with non dicts in a list is not supported")
        else:
            # Callable function applies to each non dict element in nested dict
            in_dict[k] = callable_fn(k, v, *args, **kwargs)
    return in_dict

def sanitize_element(param: str, ele_val: Any, validate_paths: bool = True, *args, **kwargs) -> Any:
    # Here are the key matches which makes sanitizer think its a path
    # TODO there may be a better way to do but this way you just have to list all path related keys below
    path_keys = ["path", "sram_parameters", "file", "dir", "home"]
    inv_path_keys = ["meta", "use_latest_obj_dir", "manual_obj_dir"] # even if path keys are in param if negative keys are in param then its not a path
    # Special list for lists of dicts, we want to ignore any element with this key in the parent dict
    parent_inv_path_keys = ["placement_constraints"]
    # We check if the supplied inv path keys exist in our parent key as its expected to be heirarchical Ex.  "a.b.c"
    if "parent_key" in kwargs.keys() and any( parent_key in kwargs["parent_key"] for parent_key in parent_inv_path_keys):
        return ele_val
    is_param_path_lists = []
    # if isinstance(ele_val, str) or isinstance(ele_val, list):
    for path_key in path_keys:
        is_param_path_list = []
        for neg_key in inv_path_keys:
            if path_key in param and neg_key not in param:
                is_param_path_list.append(True)
            else:
                is_param_path_list.append(False)
        is_param_path_lists.append(all(is_param_path_list))
    if any( is_param_path_lists): #(path in param and neg not in param) for neg in inv_path_keys for path in path_keys ): # and neg not in param
        if isinstance(ele_val, list):
            ret_val = [clean_path(v, validate_paths) for v in ele_val]
        elif isinstance(ele_val, str):
            ret_val = clean_path(ele_val, validate_paths)
        else:
            raise ValueError(f"ERROR: (k, v) pair: ({param} {ele_val}) is wrong datatype for paths")
    else:
        ret_val = ele_val

    return ret_val

def sanitize_config(config_dict: Dict[str, Any], validate_paths: bool = True) -> dict:
    """
        Modifies values of a config file to do the following:
            - Expand relative paths to absolute paths
    """    

    return traverse_nested_dict(config_dict, sanitize_element, validate_paths)

def parse_config(conf_path: str, validate_paths: bool = True, sanitize: bool = True):
    is_yaml = None
    if conf_path.endswith(".yaml") or conf_path.endswith(".yml"):
        is_yaml = True
    elif conf_path.endswith(".json"):
        is_yaml = False
    else:
        raise ValueError(f"ERROR: config file {conf_path} is not a yaml or json file")

    loaded_config = load_config_from_string(Path(conf_path).read_text(), is_yaml=is_yaml, path=str(Path(conf_path).resolve().parent))
    if sanitize:
        conf_dict = sanitize_config( 
            loaded_config,
            validate_paths)
    else:
        conf_dict = loaded_config
        
    return conf_dict

def parse_yml_config(yaml_file: str, validate_paths: bool = True) -> dict:
    """
        Takes in possibly unsafe path and returns a sanitized config
    """
    safe_yaml_file = clean_path(yaml_file)
    with open(safe_yaml_file, 'r') as f:
        config = yaml.safe_load(f)
    
    return sanitize_config(config, validate_paths)

def find_common_root_dir(dpaths: List[str]) -> Union[None, List[str]]:
    """
        Finds the common root of a list of unsorted directories and makes sure they all exist in it and the common root was provided in the list
        Returns the common root if conditions are met, None otherwise 
    """

    common_root = os.path.commonpath(dpaths)
    # Check if all other paths are inside the upper most path (index 0)
    # If its not true then we return None to show that there is no common root dir in dpath list
    ret_val = None
    if all(os.path.relpath(path, common_root).startswith('..') is False for path in dpaths):
        if any(common_root == dpath for dpath in dpaths):
            ret_val = common_root
    return ret_val


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


def init_dataclass(dataclass_type: Type, input_yaml_config: dict, add_arg_config: dict = {}, validate_paths: bool = True) -> dict:
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
        # clean path and make sure it exists (if "path" keyword in field name)
        if "path" in field and field in dataclass_inputs:
            if isinstance(dataclass_inputs[field], list):
                for idx, path in enumerate(dataclass_inputs[field]):
                    dataclass_inputs[field][idx] = clean_path(path, validate_paths) 
            elif isinstance(dataclass_inputs[field], str):
                dataclass_inputs[field] = clean_path(dataclass_inputs[field], validate_paths) 
            else:
                pass
    # return created dataclass instance
    # The constructor below will fail if
    # - key in yaml != field name in dataclass 
    return dataclass_type(**dataclass_inputs)



def convert_namespace(in_namespace: argparse.Namespace) -> List[str]:
    """
        Converts a namespace to an arg list of cli strings (space seperated)
    """
    if in_namespace != None:
        arg_list = []
        for key, val in vars(in_namespace).items():
            if val != None and val != False:
                if isinstance(val, list):
                    arg_list.append(f"--{key}")
                    arg_list += val
                    # arg_list.append(" ".join(val))
                elif isinstance(val, bool) and val:
                    arg_list.append(f"--{key}")
                elif isinstance(val, str) or isinstance(val, int) or isinstance(val, float):
                    arg_list.append(f"--{key}")
                    arg_list.append(f"{val}")
    else:
        arg_list = None

    return arg_list



asic_dse_cli = rg_ds.AsicDseCLI()
coffe_cli = rg_ds.CoffeCLI()
ic_3d_cli = rg_ds.Ic3dCLI()
common_cli = rg_ds.RadGenCLI()


def parse_rad_gen_top_cli_args(in_args: Union[argparse.Namespace, list] = None) -> Tuple[argparse.Namespace, Dict[str, Any]]:
    """ 
        Parses the top level RAD-Gen args
    """                     
    # converting namespace to list of cli arguments if we get namespace
    arg_list = convert_namespace(in_args) if isinstance(in_args, argparse.Namespace) else in_args

    parser = argparse.ArgumentParser(description="RAD-Gen top level CLI args")

    # TODO see if theres a better way to do this but for now we have to manually define which args go to which tool with a list of tags
    # Define general tags, assuming we only call a single tool each time we should be able to seperate them from the subtool being run

    gen_arg_keys = [
        "top_config_path",
        "subtools"
    ]

    # TOP LEVEL CONFIG ARG
    #parser.add_argument("-tc", "--top_config_path", help="path to RAD-GEN top level config file", type=str, default=None)
    # Subtool options are "coffe" "asic-dse" "3d-ic"
    #parser.add_argument("-st", "--subtools", help="subtool to run", nargs="*", type=str, default=None)
    
    # dict storing key value pairs for default values of each arg
    default_arg_vals = {}

    # Adding Common CLI args
    common_cli = rg_ds.RadGenCLI()
    default_arg_vals = {
        **default_arg_vals,
        **common_cli._defaults,
    }
    for cli_arg in common_cli.cli_args:
        rg_ds.add_arg(parser, cli_arg)
    
    
    # Common args for all subtools
    # parser.add_argument('-mo','--manual_obj_dir', help="uses user specified obj dir", type=str, default=None)
    # Optional arguments only used in the case of manual 
    # parser.add_argument('--input_tree_top_path', help="path to top level dir containing input designs", type=str, default=None)
    # parser.add_argument('--output_tree_top_path', help="path to top level dir which outputs will be produced into, will have a subdir for each subtool", type=str, default=None)

    if in_args == None and arg_list == None:
        parsed_args, remaining_args = parser.parse_known_args()
    else:
        parsed_args, remaining_args = parser.parse_known_args(args = arg_list, namespace = in_args)


    #     _   ___ ___ ___   ___  ___ ___     _   ___  ___ ___ 
    #    /_\ / __|_ _/ __| |   \/ __| __|   /_\ | _ \/ __/ __|
    #   / _ \\__ \| | (__  | |) \__ \ _|   / _ \|   / (_ \__ \
    #  /_/ \_\___/___\___| |___/|___/___| /_/ \_\_|_\\___|___/
    if "asic_dse" in parsed_args.subtools:
        # Adding ASIC DSE CLI args
        asic_dse_cli = rg_ds.AsicDseCLI()
        default_arg_vals = {
            **default_arg_vals,
            **asic_dse_cli._defaults,
        }
        for cli_arg in asic_dse_cli.cli_args:
            rg_ds.add_arg(parser, cli_arg)

        """
            default_arg_vals = {
                **default_arg_vals,
                "flow_mode": "hammer",
                "run_mode": "serial",
            }
            parser.add_argument('-r', '--run_mode', help="mode in which asic flow is run, either parallel or serial", type=str, choices=["parallel", "serial", "gen_scripts"], default="serial")
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
            parser.add_argument('-c', '--compile_results', help="flag to compile results related a specific asic flow or sweep depending on additional provided configs", action='store_true') 
            parser.add_argument('-syn', '--synthesis', help="flag runs synthesis on specified design", action='store_true') 
            parser.add_argument('-par', '--place_n_route', help="flag runs place & route on specified design", action='store_true') 
            parser.add_argument('-pt', '--primetime', help="flag runs primetime on specified design", action='store_true') 
            parser.add_argument('-sram', '--sram_compiler', help="flag enables srams to be run in design", action='store_true') 
            parser.add_argument('-make', '--make_build', help="flag enables make build system for asic flow", action='store_true') 
        """
        
    #   ___ ___  ___ ___ ___     _   ___  ___ ___ 
    #  / __/ _ \| __| __| __|   /_\ | _ \/ __/ __|
    # | (_| (_) | _|| _|| _|   / _ \|   / (_ \__ \
    #  \___\___/|_| |_| |___| /_/ \_\_|_\\___|___/

    if "coffe" in parsed_args.subtools:
        # Adding COFFE CLI args
        coffe_cli = rg_ds.CoffeCLI()
        default_arg_vals = {
            **default_arg_vals,
            **coffe_cli._defaults,
        }
        for cli_arg in coffe_cli.cli_args:
            rg_ds.add_arg(parser, cli_arg)
        """
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

            parser.add_argument('-f', '--fpga_arch_conf_path', help ="path to config file containing coffe FPGA arch information", type=str, default= None)
            parser.add_argument('-hb', '--hb_flows_conf_path', type=str, default=None, help="top level hardblock flows config file, this specifies all hardblocks and asic flows used")
            parser.add_argument('-n', '--no_sizing', help="don't perform transistor sizing", action='store_true')
            parser.add_argument('-o', '--opt_type', type=str, choices=["global", "local"], default = default_arg_vals["opt_type"], help="choose optimization type")
            parser.add_argument('-s', '--initial_sizes', type=str, default = default_arg_vals["initial_sizes"], help="path to initial transistor sizes")
            parser.add_argument('-m', '--re_erf', type=int, default = default_arg_vals["re_erf"], help = "choose how many sizing combos to re-erf")
            parser.add_argument('-a', '--area_opt_weight', type=int, default = default_arg_vals["area_opt_weight"], help="area optimization weight")
            parser.add_argument('-d', '--delay_opt_weight', type=int, default = default_arg_vals["delay_opt_weight"], help="delay optimization weight")
            parser.add_argument('-i', '--max_iterations', type=int, default = default_arg_vals["max_iterations"] ,help="max FPGA sizing iterations")
            parser.add_argument('-hi', '--size_hb_interfaces', type=float, default=default_arg_vals["size_hb_interfaces"], help="perform transistor sizing only for hard block interfaces")
            # quick mode is disabled by default. Try passing -q 0.03 for 3% minimum improvement
            parser.add_argument('-q', '--quick_mode', type=float, default=-1.0, help="minimum cost function improvement for resizing")
            
                    
            #arguments for ASIC flow TODO integrate some of these into the asic_dse tool, functionality already exists just needs to be connected
            # parser.add_argument('-ho',"--hardblock_only",help="run only a single hardblock through the asic flow", action='store_true',default=False)
            # parser.add_argument('-g',"--gen_hb_scripts",help="generates all hardblock scripts which can be run by a user",action='store_true',default=False)
            # parser.add_argument('-p',"--parallel_hb_flow",help="runs the hardblock flow for current parameter selection in a parallel fashion",action='store_true',default=False)
            # parser.add_argument('-r',"--parse_pll_hb_flow",help="parses the hardblock flow from previously generated results",action='store_true',default=False)
        """
    #   _______    ___ ___     _   ___  ___ ___ 
    #  |__ /   \  |_ _/ __|   /_\ | _ \/ __/ __|
    #   |_ \ |) |  | | (__   / _ \|   / (_ \__ \
    #  |___/___/  |___\___| /_/ \_\_|_\\___|___/
    if "ic_3d" in parsed_args.subtools:
        ic_3d_cli = rg_ds.Ic3dCLI()
        default_arg_vals = {
            **default_arg_vals,
            **ic_3d_cli._defaults,
        }
        for cli_arg in ic_3d_cli.cli_args:
            rg_ds.add_arg(parser, cli_arg)
        """
            parser.add_argument('-d', '--debug_spice', help="takes in directory(ies) named according to tile of spice sim, runs sim, opens waveforms and param settings for debugging", nargs="*", type=str, default= None)
            parser.add_argument('-p', '--pdn_modeling', help="performs pdn modeling", action="store_true")
            parser.add_argument('-b', '--buffer_dse', help="brute forces the user provided range of stage ratio and number of stages for buffer sizing", action="store_true")
            parser.add_argument('-s', '--buffer_sens_study', help="sweeps parameters for buffer chain wire load, plots results", action="store_true")
            parser.add_argument('-l', '--use_latest_obj_dir', help="for spice work dirs, old outputs are overriden rather than creating a new obj dir", action='store_true') 
            parser.add_argument('-c', '--input_config_path', help="top level input config file", type=str, default=None)
        """

    if in_args == None and arg_list == None:
        args = parser.parse_args()
    else:
        args = parser.parse_args(args = arg_list, namespace = in_args)
        
    # Default value dictionary for any arg that has a non None or False for default value
    # default_arg_vals = {**asic_dse_cli._defaults, **coffe_cli._defaults, **ic_3d_cli._defaults, **common_cli._defaults}
    # { k: v for k, v in vars(args).items() if v != None and v != False}

    return args, default_arg_vals


def merge_cli_and_config_args(cli: Dict[str, Any], config: Dict[str, Any], default: Dict[str, Any]) -> Dict[str, Any]:
    """
        Merges the cli and config args into a single dictionary
        - CLI args override config args
    """
    result_conf = {}
    if config == None:
        for k_conf, v_conf in cli.items():
            result_conf[k_conf] = v_conf
    elif cli == None:
        for k_conf, v_conf in config.items():
            result_conf[k_conf] = v_conf
    else:
        for k_cli, v_cli in cli.items():
            # We only want the parameters relevant to the subtool we're running (exclude top level args)
            # If one wanted to exclude other subtool args they could do it here
            # if user passed in top lvl conf file
            for k_conf, v_conf in config.items():
                if k_conf == k_cli:
                    # If the cli key is not a default value or None/False AND cli key is not in the cli default values dictionary then we will use the cli value
                    #if v_cli != None and v_cli != False and v_cli != default[k_cli]:
                    if v_cli != default[k_cli]:
                        result_conf[k_conf] = v_cli
                    else:
                        result_conf[k_conf] = v_conf
            # if the cli key was not loaded into result config 
            # meaning it didnt exist in config file, we use whatever value was in cli
            
            if k_cli not in result_conf.keys():
                result_conf[k_cli] = v_cli 
            
            # else:
            #     # if only cli args provided
            #     result_conf[k_cli] = v_cli
    return result_conf




def strip_hier(in_dict: Dict[str, Any], strip_tag: str = None) -> Dict[str, Any]:
    """
        Removes heirarchy from keys in a dictionary
        - If strip_tag is provided then only keys which contain the strip_tag will be stripped
    """
    strip_tag_re = re.compile(f".*{strip_tag}\.")
    out_dict = {}
    for k, v in in_dict.items():
        if strip_tag != None:
            if strip_tag in k:
                out_dict[strip_tag_re.sub("", k)] = v
            else:
                out_dict[k] = v
        else:
            out_dict[strip_tag_re.sub("", k)] = v            
    return out_dict


def modify_param_dict_keys_for_hier(in_dict: Dict[str, Any], subtool: str):
    """
        Takes in a dictionary and modifies its keys to add the subtool name to the hierarchy (and match a flattened input conf file)
    """
    global asic_dse_cli
    global coffe_cli
    global ic_3d_cli
    global common_cli
    for k in in_dict.copy().keys():
        for cli_arg in globals()[f"{subtool}_cli"].cli_args:
            if k == cli_arg.key:
                # replace old key name with new key name
                in_dict[f"{subtool}.{cli_arg.key}"] = in_dict.pop(k)



def init_structs_top(args: argparse.Namespace, default_arg_vals: Dict[str, Any]) -> Dict[str, Any]:
    # ARGS CAN BE PASSED FROM CONFIG OR CLI
    # NOTE: CLI ARGS OVERRIDE CONFIG ARGS!

    top_conf = None
    if args.top_config_path is not None:
        #top_conf = parse_yml_config(args.top_config_path)
        top_conf = load_config_from_string(Path(args.top_config_path).read_text(), is_yaml=True, path=str(Path(args.top_config_path).resolve().parent))
    cli_dict = vars(args)
    # Convert the key names of cli_dict into heiarachical keys which will match the config file
    for conv_dict in [cli_dict, default_arg_vals]:
        for subtool_str in "coffe", "asic_dse", "ic_3d", "common":
            modify_param_dict_keys_for_hier(conv_dict, subtool_str)
    
    # Below currently parses the cli args and will always take the cli arg value over whats in the config file (if cli arg == None)
    # If cli_arg == default_cli_value && key exists in the config file -> then tool will use the config file instead of cli 

    # Comparing two input param dicts one coming from cli and one from config file for each tool
    subtool_confs = {}
    for subtool in cli_dict["common.subtools"]:
        """
            result_conf = {}
            for k_cli, v_cli in cli_dict.items():
                # We only want the parameters relevant to the subtool we're running (exclude top level args)
                # If one wanted to exclude other subtool args they could do it here
                # if user passed in top lvl conf file
                if args.top_config_path != None:
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
                else:
                    # if only cli args provided
                    result_conf[k_cli] = v_cli

            # init common structs for all subtools
        """
        # if top level config file was passed in and subtool is in top level config file
        if top_conf != None and subtool in [ key.split(".")[0] for key in top_conf.keys()]:
            # The dict concatenation is because the merrge function only takes a single level of a nested dict
            # result_conf = merge_cli_and_config_args(cli_dict, {**top_conf, **top_conf[subtool], **top_conf["common"]}, default_arg_vals)
            result_conf = merge_cli_and_config_args(cli_dict, top_conf, default_arg_vals)
        else:
            # In this case only using the cli args
            result_conf = cli_dict
        
        # Only passing in keys from common, removing heirarchy from keys to make things more clear in function
        common = init_common_structs(strip_hier(result_conf, strip_tag="common"))
            # { k.replace("common.","") : v for k,v in result_conf.items() if "common" in k})

        subtool_confs[subtool] = {
            "common": common,
            **result_conf,
        }
        
    # Before this function make sure all of the parameters have been defined in the dict with default values if not specified
    rad_gen_info = {}

    # Loop through subtool keys and call init function to return data structures
    # init functions are in the form init_<subtool>_structs
    for subtool in subtool_confs.keys():
        fn_to_call = getattr(sys.modules[__name__], f"init_{subtool}_structs", None)
        if callable(fn_to_call):
            # do the renaming of keys to take out the "<subtool>." portion of heirarchy, this is because by definition all keys that are passed in are only for the respective subtool
            # (subtools are independant of one another), and the common dataclass is passed through the "common" key
            rad_gen_info[subtool] = fn_to_call( {k.replace(f"{subtool}.","") : v for k,v in subtool_confs[subtool].items()} ) 
        else:
            raise ValueError(f"ERROR: {subtool} is not a valid subtool ('init_{subtool}_structs' is not a defined function)")
    return rad_gen_info
    

def init_hammer_config(conf_tree: rg_ds.Tree, conf_path: str) -> str:
    """
        This function is specifically to clean up the configs passed to hammer prior to initialization of the
        ASICFlowSettings data structure.
        Hammer only accepts absolute paths so we need to convert our paths with home dir to abspaths
    """
    # Generate the directories using the structure specifed in env
    # Use the path of the config file to determine where they are created
    # conf_dir = os.path.dirname(conf_path)
    # # Will use the structure contained in tag "config" and create its subdirs wherever user input config file(s) are located
    # conf_tree = design_input_tree.search_subtrees("config")[0]
    # for dir in conf_tree.subtrees:
    #     os.makedirs(os.path.join(conf_dir, dir.root), exist_ok=True)

    # Our yaml parsing function performs santization, there may be invalid paths so we don't want to look for them
    # conf_dict = parse_yml_config(conf_path, validate_paths = False)
    # conf_out_path = os.path.join(conf_dir, mod_dir, conf_name + "_pre_procd.yml" )
    # with open(conf_out_path, "w" ) as f:
    #     yaml.safe_dump(conf_dict, f, sort_keys = False)


    conf_fname = os.path.basename(os.path.splitext(conf_path)[0])
    conf_dict = parse_config(conf_path, validate_paths = False, sanitize = True)
    mod_confs_dpath = conf_tree.search_subtrees("mod")[0].path
    conf_out_fpath = os.path.join(mod_confs_dpath, conf_fname + "_pre_procd.json")
    dump_config_to_json_file(conf_out_fpath, conf_dict)
    
    return conf_out_fpath



def init_common_structs(common_conf: Dict[str, Any]) -> rg_ds.Common:
    common_inputs = copy.deepcopy(common_conf)
    rad_gen_home = os.environ.get("RAD_GEN_HOME")
    if rad_gen_home is None:
        raise RuntimeError("RAD_GEN_HOME environment variable not set, please source <rad_gen_top>/env_setup.sh")
    else:
        rad_gen_home = clean_path(rad_gen_home)
    common_inputs["rad_gen_home_path"] = rad_gen_home

    # This implies that hammer home must be set even when not running hammer, thats fine for now its assumed users have to recursivley clone repo
    # TODO if we want to change this we can just make hammer home optional 
    hammer_home = os.environ.get("HAMMER_HOME")
    if hammer_home is None:
        raise RuntimeError("HAMMER_HOME environment variable not set, please source <rad_gen_top>/env_setup.sh")
    else:
        hammer_home = clean_path(hammer_home)
    common_inputs["hammer_home_path"] = hammer_home

    common_inputs["log_fpath"] = os.path.join(rad_gen_home, "logs", "rad_gen.log")
    # For now on our output path fields we need to manually generate the directories and files specified
    # This ensures that our function to check for valid paths will not fail
    # TODO have the <_>Args dynamic dataclass have fields for each argument which specifies relevant information
    
    for out_path_key in ["log_fpath"]:
        os.makedirs(os.path.dirname(common_inputs[out_path_key]), exist_ok = True)
        # write to log to create empty file and not piss off the path checker
        fd = open(common_inputs[out_path_key], "w")
        fd.close()


    design_input_trees = {}
    design_output_trees = {}

    # Output dir structure for coffe flow, instantiated under <user_defined_design_name> dir under "coffe" in input tree
    coffe_output_tree_struct = {
        # Stores 
        "fpga_fabric_sizing" : "fpga_fabric_sizing"
    }

    """
        The idea of the below project tree dir structure is that we copy all the relevant files (yuck) into the project dir so we can access them easily
        - This allows for the user to specify files which may be located across many different places and they will all be condensed to a single place
            - It should check to make sure the files are not already in the project directory before copying them
            - Ideally the project tree should be a workspace that can be used for development of RTL or other stuff and that way there isnt a ton of copying
            
    """

    # For the below directory structures we have dicts with keys and values being the same
    # This is really for readability as when these directories are accessed further in the flow 
    # we will use the keys/dir names which are descriptive of thier purpose

    # TODO update the name of pdk_name to what we pass into hammer if using that mode of stdcell flow
    ## TODO PDK Tree implementation
    ## pdk_tree = rg_ds.Tree(f"{common_conf['pdk_name']}",
    ##     [
    ##         rg_ds.Tree("tx_models", tag="tx_model"), # Stores tx model files (.sp)
    ##     ]
    ## )

    if common_conf.get("project_name"):
        common_inputs["project_tree"] = rg_ds.Tree(
            rad_gen_home,
            [
                # Resources that could be shared across multiple tools are put here, this could be technology models, pdk collateral, sram_macros, etc      
                rg_ds.Tree("shared_resources",
                    [
                    
                        # The idea for this section is that Pdks come in many forms with different structures but most of the time we need a few specific files
                        # So for each new PDK a user will have to parse the directory structure and copy the files into this directory.

                        # I think this is going to be the easiest way to make sure that the stuff we need to use for various tools is findable
                        ## TODO PDK Tree implementation
                        ## rg_ds.Tree("pdks", 
                        ##     [
                        ##         copy.deepcopy(pdk_tree),
                        ##     ],
                        ##     tag="pdks"),
                        #Configs which different runs of subtools may need to share
                        rg_ds.Tree("configs"),
                        # Ex. for asic_dse regardless of design you may share the hammer config for cadence_tools or a specific pdk
                    ]
                ),
                rg_ds.Tree("projects",
                    # Whatever subtool is run will add to this tree (maybe creating directories in the configs/output/project dirs relevant to whatever its doing)
                    [
                        rg_ds.Tree(common_conf["project_name"],
                            [
                                rg_ds.Tree("outputs", tag = "outputs"),
                            ], tag = f"{common_conf['project_name']}"
                        )
                    ], tag = "projects"
                ),
                rg_ds.Tree("third_party", 
                    [  
                        rg_ds.Tree("hammer", scan_dir = True, tag = "hammer"),
                        rg_ds.Tree("pdks", scan_dir = True, tag = "pdks"),
                    ],tag = "third_party"
                ),
            ],
            tag = "top"
        )
    else:
        common_inputs["project_tree"] = rg_ds.Tree(
            rad_gen_home,
            [
                # Resources that could be shared across multiple tools are put here, this could be technology models, pdk collateral, sram_macros, etc      
                rg_ds.Tree("shared_resources", [
                    rg_ds.Tree("configs"),
                ]),
                rg_ds.Tree("projects"),
                rg_ds.Tree("third_party", 
                    [  
                        rg_ds.Tree("hammer", scan_dir = True, tag = "hammer"),
                        rg_ds.Tree("pdks", scan_dir = True, tag = "pdks"),
                    ],tag = "third_party"
                ),
            ],
            tag = "top"
        )

    common_inputs["project_tree"].update_tree()

    common_inputs["args"] = rg_ds.RadGenArgs(**common_conf)
    common = init_dataclass(rg_ds.Common, common_inputs)

    return common



def init_asic_dse_structs(asic_dse_conf: Dict[str, Any]) -> rg_ds.AsicDSE:
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
    
    design_out_tree = rg_ds.Tree("top_lvl_module",
        [
            # Obj directories exist here
            rg_ds.Tree("obj_dirs", tag="obj_dirs"),
            # Guessing there should be a place to put high level reports / logs / scripts (by high level I mean not specific to a single obj dir)
            rg_ds.Tree("reports", tag="report"),
            rg_ds.Tree("scripts", tag="script"),
            rg_ds.Tree("logs", tag="logs"),
        ], tag="top_lvl_module"
    )
    
    configs_tree = rg_ds.Tree("configs", 
        [
            # rg_ds.Tree("pre_proc"),
            # once we have a top_lvl_module name we will put that tree here
            rg_ds.Tree("sweeps", tag="sweep"),
            rg_ds.Tree("gen", tag="gen"),
            rg_ds.Tree("mod", tag="mod"),
        ]
    )

    rtl_tree = rg_ds.Tree("rtl", 
        [
            rg_ds.Tree("gen", tag="gen"),
            rg_ds.Tree("src", tag="src"),
            rg_ds.Tree("include", tag="inc"),
            rg_ds.Tree("verif", tag="verif"),
            rg_ds.Tree("build", tag="build"),
        ]
    )

    # Create a copy of the conf tree with name configs to use for sram_compiler

    sram_tree = rg_ds.Tree("sram_lib", 
        [   
            copy.deepcopy(configs_tree),
            copy.deepcopy(rtl_tree),
            rg_ds.Tree("scripts"),
            rg_ds.Tree("macros"),
        ]
    )

    # Make tree defined directories
    asic_dse_conf["common"].project_tree.create_tree()


    # updating project tree from common
    if asic_dse_conf["common"].project_name != None:
        asic_dse_conf["common"].project_tree.append_tagged_subtree(f"{asic_dse_conf['common'].project_name}", copy.deepcopy(configs_tree), is_hier_tag = True) # append asic_dse specific conf tree to the project conf tree
        asic_dse_conf["common"].project_tree.append_tagged_subtree(f"{asic_dse_conf['common'].project_name}", rtl_tree, is_hier_tag = True) # add rtl to the project tree
    conf_tree_copy = copy.deepcopy(configs_tree)
    conf_tree_copy.update_tree_top_path(new_path = "asic_dse", new_tag = "asic_dse")
    asic_dse_conf["common"].project_tree.append_tagged_subtree("shared_resources.configs", conf_tree_copy, is_hier_tag = True) # append our shared configs tree to the project tree
    asic_dse_conf["common"].project_tree.append_tagged_subtree(f"shared_resources", copy.deepcopy(sram_tree), is_hier_tag = True) # append our pdk tree to the project tree


    """
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
        if "tech" in env_conf.keys():
            tech_info = init_dataclass(rg_ds.StdCellTechInfo, env_conf["tech"], {})
    """
    # tech_inputs = {k.replace("tech.",""):v for k,v in asic_dse_conf.items() if "tech." in k}
    stdcell_lib = init_dataclass(rg_ds.StdCellLib, strip_hier(asic_dse_conf, strip_tag="stdcell_lib"))
    scripts = init_dataclass(rg_ds.ScriptInfo, strip_hier(asic_dse_conf, strip_tag="scripts"))

    # Initialize optional parameters
    custom_asic_flow_settings = None
    
    common_asic_flow_inputs = {} # settings common to different modes of asic flow "hammer" vs "custom"
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
        common_asic_flow = rg_ds.CommonAsicFlow()
        # If a sweep file is specified with result compile flag, results across sweep points will be compiled
        if not asic_dse_conf["compile_results"]:
            mode_inputs["sweep_gen"] = True # generate config, rtl, etc related to sweep config
        else:
            mode_inputs["result_parse"] = True # parse results for each sweep point
        sweep_config = parse_config(asic_dse_conf["design_sweep_config"], validate_paths = True, sanitize = True)

        # sweep_config = parse_yml_config(asic_dse_conf["design_sweep_config"])

        high_lvl_inputs["sweep_config_path"] = asic_dse_conf["design_sweep_config"]
        
        for design in sweep_config["design_sweeps"]:
            sweep_type_inputs = {} # parameters for a specific type of sweep
            if design["type"] == "sram":
                # point the base_rtl_path to the default one in the project tree (will be overridden if another value provided in sweep config)
                sweep_type_inputs["sram_rtl_template_fpath"] = os.path.join ( 
                    asic_dse_conf["common"].project_tree.search_subtrees("shared_resources.sram_lib.rtl.src", is_hier_tag = True)[0].path,
                    "sram_template.sv"
                )
                sweep_type_info = init_dataclass(rg_ds.SRAMSweepInfo, design, sweep_type_inputs)
            else:                
                # If we are either doing RTL or VLSI sweep then we should copy over the source RTL to our project tree
                # Check to see if the RTL was passed in via CLI params
                # Priority of getting to RTL + HDL search Paths for RTL
                # 1. Conglomerated CLI/Conf ( asic_dse_conf["flow_conf_fpath"] ) -> sweep_config["base_config_path"] 
                if asic_dse_conf.get("flow_conf_paths") and len(asic_dse_conf["flow_conf_paths"]) == 1:
                    base_config = parse_config(asic_dse_conf["flow_conf_paths"][0])
                else:                
                    base_config = parse_config(design["base_config_path"])

                if asic_dse_conf.get("hdl_path"):
                    exts = ['.v','.sv','.vhd',".vhdl", ".vh", ".svh"]
                    _, hdl_search_paths = rec_get_flist_of_ext(asic_dse_conf.get("hdl_path"), exts)
                else:
                    hdl_search_paths = base_config.get("synthesis.inputs.hdl_search_paths")
                # Priority of Copying RTL from user inputs to project tree
                # 1. Search for RTL inside of user provided HDL search paths 
                #   a. Priority order: CLI -> base_config["synthesis.inputs.hdl_search_paths"] -> base_config["synthesis.inputs.input_files"] if equivalent files we do a diff to make sure they are the same, if not equal we copy them over
                # Priority of HDL search paths:
                # 1. Conglom CLI/Conf (asic_dse_conf["hdl_path"]) -> base_config["synthesis.inputs.hdl_search_paths"]
                if hdl_search_paths:
                    # Is assumed sanitized by the parse_config (ie path exists)
                    rtl_src_dpath = find_common_root_dir(hdl_search_paths)
                    rtl_dst_tree = asic_dse_conf["common"].project_tree.search_subtrees(f"{asic_dse_conf['common'].project_name}.rtl.src", is_hier_tag = True)[0]
                    rtl_dst_tree.scan_dir = True
                    rtl_dst_dpath = rtl_dst_tree.path
                    # Copy tree recursivley to project tree, just including all files assuming they will be part of the RTL we want, possibly could filter for specific files in the future
                    shutil.copytree(rtl_src_dpath, rtl_dst_dpath, dirs_exist_ok=True)
                    rtl_dst_tree.update_tree()

                    # rtl_dst_tree = rg_ds.Tree(rtl_dst_dpath, scan_dir = True)

                # Now get RTL from the synthesis input files, will look through the current RTL src path and if the files already exist will not copy them over
                rtl_src_fpaths = base_config.get("synthesis.inputs.input_files.input_file")
                if rtl_src_fpaths:
                    # Search for file recursivley
                    rtl_dst_tree = asic_dse_conf["common"].project_tree.search_subtrees(f"{asic_dse_conf['common'].project_name}.rtl.src", is_hier_tag = True)[0]
                    for fpath in rtl_src_fpaths:
                        # If we don't find a matching file in our rtl.src dir we will copy what exists in our conf over
                        if not rec_find_fpath(rtl_dst_tree.path, os.path.basename(fpath)):
                            shutil.copy(fpath, rtl_dst_tree.path)


                if design["type"] == "rtl_params":
                    sweep_type_info = init_dataclass(rg_ds.RTLSweepInfo, design, sweep_type_inputs)
                elif design["type"] == "vlsi_params":
                    sweep_type_info = init_dataclass(rg_ds.VLSISweepInfo, design, sweep_type_inputs)
            
            design_inputs = {}
            design_inputs["type_info"] = sweep_type_info
            # Pass in the parsed sweep config and strip out the "shared" hierarchy tags
            design_sweep_infos.append(init_dataclass(rg_ds.DesignSweepInfo, strip_hier({**design, **sweep_config} , strip_tag="shared"), design_inputs))

    # Currently only enabling VLSI mode when other modes turned off
    else:
        ################################################
        # \ \ / / |  / __|_ _| |  \/  |/ _ \|   \| __| #
        #  \ V /| |__\__ \| |  | |\/| | (_) | |) | _|  #
        #   \_/ |____|___/___| |_|  |_|\___/|___/|___| #
        ################################################
        # Initializes Data structures to be used for running stages in ASIC flow

        design_sweep_infos = None


        if asic_dse_conf["flow_conf_paths"] != None:

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
                assert len(asic_dse_conf["flow_conf_paths"]) == 1, "ERROR: Custom flow mode requires a single config file"
                custom_asic_flow_settings = load_hb_params(clean_path(asic_dse_conf["flow_conf_paths"][0]))
                top_lvl_module = custom_asic_flow_settings["top_level"]

            elif asic_dse_conf["flow_mode"] == "hammer":
                # search for conf tree below in our project_name dir
                proj_conf_tree = asic_dse_conf["common"].project_tree.search_subtrees(f"{asic_dse_conf['common'].project_name}.configs", is_hier_tag = True)[0] 
                # Before parsing asic flow config we should run them through pre processing to all input files
                for idx, conf_path in enumerate(asic_dse_conf["flow_conf_paths"]):
                    asic_dse_conf["flow_conf_paths"][idx] = init_hammer_config(proj_conf_tree, conf_path)
                # Search for the shared conf tree in the project tree
                shared_conf_tree = asic_dse_conf["common"].project_tree.search_subtrees("shared_resource.configs.asic_dse", is_hier_tag = True)[0]
                # Pre process & validate env config path
                for idx, conf_path in enumerate(asic_dse_conf["tool_env_conf_paths"]):
                    asic_dse_conf["tool_env_conf_paths"][idx] = init_hammer_config(shared_conf_tree, conf_path)


                # Initialize the hammer tree
                # asic_flow_settings_input["hammer_tree"] = rg_ds.Tree(  
                #     asic_dse_conf["common"].hammer_home_path,
                #     [
                #         rg_ds.Tree("asic_dse"),
                #         rg_ds.Tree("coffe"),
                #         rg_ds.Tree("ic_3d"),
                #     ]
                # )
                
                
                # Initialize a Hammer Driver, this will deal with the defaults & will allow us to load & manipulate configs before running hammer flow
                driver_opts = HammerDriver.get_default_driver_options()
                # update values
                driver_opts = driver_opts._replace(environment_configs = list(asic_dse_conf["tool_env_conf_paths"]))
                driver_opts = driver_opts._replace(project_configs = list(asic_dse_conf["flow_conf_paths"]))
                hammer_driver = HammerDriver(driver_opts)

                # Instantiating a hammer driver class creates an obj_dir named "obj_dir" in the current directory, as a quick fix we will delete this directory after its created
                # TODO this should be fixed somewhere

                dummy_obj_dir_path = os.path.join(os.getcwd(),"obj_dir")
                if os.path.isdir(dummy_obj_dir_path):
                    # Please be careful changing things here, always scary when you're calling "rm -rf"
                    shutil.rmtree(dummy_obj_dir_path)

                # if cli provides a top level module and hdl path, we will modify the provided design config file to use them
                if asic_dse_conf["top_lvl_module"] != None and asic_dse_conf["hdl_path"] != None:
                    vlsi_mode_inputs["config_pre_proc"] = True
                    top_lvl_module = asic_dse_conf["top_lvl_module"]
                    asic_flow_settings_input["hdl_path"] = asic_dse_conf["hdl_path"]
                else:
                    vlsi_mode_inputs["config_pre_proc"] = False
                    top_lvl_module = hammer_driver.database.get_setting("synthesis.inputs.top_module")

                # Create output directory for obj dirs to be created inside of
                out_dir = asic_dse_conf["common"].project_tree.search_subtrees(f"outputs.{top_lvl_module}.hammer.obj_dirs", is_hier_tag = True)[0].path
                #os.path.join(env_settings.design_output_path, asic_flow_settings_input["top_lvl_module"])
                obj_dir_fmt = f"{top_lvl_module}-{rg_ds.create_timestamp()}" # Still putting top level mod naming convension on obj_dirs because who knows where they will end up
                
                # Throw error if both obj_dir options are specified
                assert not (asic_dse_conf["common"].use_latest_obj_dir and asic_dse_conf["common"].manual_obj_dir != None), "ERROR: cannot use both latest obj dir and manual obj dir arguments for ASIC-DSE subtool"
                
                obj_dir_path = None
                # Users can specify a specific obj directory
                if asic_dse_conf["common"].manual_obj_dir != None:
                    obj_dir_path = os.path.realpath(os.path.expanduser(asic_dse_conf["common"].manual_obj_dir))
                # Or they can use the latest created obj dir
                elif asic_dse_conf["common"].use_latest_obj_dir:
                    if os.path.isdir(out_dir):
                        obj_dir_path = find_newest_obj_dir(search_dir = out_dir, obj_dir_fmt = f"{top_lvl_module}-{rg_ds.create_timestamp(fmt_only_flag = True)}")
                    else:
                        print( f"WARNING: No latest obj dirs found in {out_dir} of format {top_lvl_module}-{rg_ds.create_timestamp(fmt_only_flag = True)}")
                # If no value given or no obj dir found, we will create a new one
                if obj_dir_path == None:
                    obj_dir_path = os.path.join(out_dir,obj_dir_fmt)
                    print( f"WARNING: No obj dir specified or found, creating new one @: {obj_dir_path}")

                # TODO move directory creation / destruction to Tree class
                if not os.path.isdir(obj_dir_path):
                    os.makedirs(obj_dir_path)

                # rad_gen_log(f"Using obj_dir: {obj_dir_path}",rad_gen_log_fd)

                hammer_driver.obj_dir = obj_dir_path
                # At this point hammer driver should be fully initialized
                asic_flow_settings_input["hammer_driver"] = hammer_driver
                asic_flow_settings_input["obj_dir_path"] = obj_dir_path

                # if not specified the flow will run all the stages by defualt
                run_all_flow = not (asic_dse_conf["synthesis"] or asic_dse_conf["place_n_route"] or asic_dse_conf["primetime"]) and not asic_dse_conf["compile_results"]
                
                # TODO implement "flow_stages" element of ASICFlowSettings struct
                asic_flow_settings_input["make_build"] = asic_dse_conf["make_build"]
                asic_flow_settings_input["run_sram"] = asic_dse_conf["sram_compiler"]
                asic_flow_settings_input["run_syn"] = asic_dse_conf["synthesis"] or run_all_flow
                asic_flow_settings_input["run_par"] = asic_dse_conf["place_n_route"] or run_all_flow
                asic_flow_settings_input["run_pt"] = asic_dse_conf["primetime"] or run_all_flow

                asic_flow_settings_input["top_lvl_module"] = top_lvl_module
                # if "asic_flow" in env_conf.keys():
                #     config_file_input = env_conf["asic_flow"]
                # else:
                #     config_file_input = {}
                asic_flow_settings = init_dataclass(rg_ds.ASICFlowSettings, {}, asic_flow_settings_input, validate_paths = not vlsi_mode_inputs["config_pre_proc"] )
            
            # Perform all intiailizations which require "top_lvl_module" to be set (Common to both "custom" & "hammer")
            # high_lvl_inputs["top_lvl_module"] = top_lvl_module
            common_asic_flow_inputs["top_lvl_module"] = asic_flow_settings_input["top_lvl_module"] 
            common_asic_flow = rg_ds.init_dataclass(rg_ds.CommonAsicFlow, common_asic_flow_inputs)


            # Create copy of output tree (rename to top_lvl_module)
            design_out_tree_copy = copy.deepcopy(design_out_tree)
            design_out_tree_copy.update_tree_top_path(new_path = top_lvl_module, new_tag = top_lvl_module)
            # design_out_tree_copy.path = top_lvl_module
            # design_out_tree_copy.tag = top_lvl_module

            # Append to project tree
            asic_dse_conf["common"].project_tree.append_tagged_subtree(f"{asic_dse_conf['common'].project_name}.outputs", design_out_tree, is_hier_tag = True) # append our asic_dse outputs
            
            # create the tree for the vlsi outputs (its ok to call multiple times, or if dirs already exist)
            # asic_dse_conf["common"].project_tree.create_tree()

        else:
            print("ERROR: no flow config files provided, cannot run ASIC flow")

    # Initializations common to all modes of asic flow
    design_out_tree_copy = copy.deepcopy(design_out_tree) 
    high_lvl_inputs["design_out_tree"] = design_out_tree_copy
    
    # By default set the result search path to the design output path, possibly could be changed in later functions if needed
    #high_lvl_inputs["result_search_path"] = asic_dse_conf["common"].project_tree.search_subtrees(f'{asic_dse_conf["common"].project_name}.outputs', is_hier_tag = True)[0].path
    high_lvl_inputs["result_search_path"] = asic_dse_conf["common"].project_tree.search_subtrees(f'projects', is_hier_tag = True)[0].path

    # display project tree
    # asic_dse_conf["common"].project_tree.display_tree()

    vlsi_flow = init_dataclass(rg_ds.VLSIMode, vlsi_mode_inputs, {})
    rad_gen_mode = init_dataclass(rg_ds.RADGenMode, mode_inputs, {"vlsi_flow" : vlsi_flow})
    high_lvl_inputs = {
        **high_lvl_inputs,
        "mode": rad_gen_mode,
        "stdcell_lib": stdcell_lib,
        "scripts": scripts,
        "design_sweep_infos": design_sweep_infos,
        "asic_flow_settings": asic_flow_settings,
        "custom_asic_flow_settings": custom_asic_flow_settings,
        # "env_settings": env_settings,
        "common_asic_flow": common_asic_flow, 
        "common": asic_dse_conf["common"],
    }
    asic_dse = init_dataclass(rg_ds.AsicDSE, high_lvl_inputs, {})

    return asic_dse

def init_coffe_structs(coffe_conf: Dict[str, Any]):
    # Add coffe specific trees to common
    # coffe_conf["common"].project_tree.append_tagged_subtree("config", rg_ds.Tree("coffe", tag="coffe.config"))
    
    fpga_arch_conf = load_arch_params(clean_path(coffe_conf["fpga_arch_conf_path"]))
    # coffe_conf["common"].project_tree.append_tagged_subtree("output", rg_ds.Tree(os.path.basename(os.path.splitext(fpga_arch_conf["arch_out_folder"])[0]), tag="coffe.output"))


    if "hb_flows_conf_path" in coffe_conf.keys() and coffe_conf["hb_flows_conf_path"] != None:
        hb_flows_conf =  parse_yml_config(coffe_conf["hb_flows_conf_path"])
        ###################### SETTING UP ASIC TOOL ARGS FOR HARDBLOCKS ######################
        # Build up the cli args used for calling the asic-dse tool
        asic_dse_cli_args_base = {}        

        # Asic flow args (non design specific) that can be passed from hb_flows_conf
        for k, v in hb_flows_conf.items():
            # if key is not hardblocks, then it should be part of asic_dse cli args
            if k != "hardblocks":
                asic_dse_cli_args_base[k] = v

        hardblocks = []
        # if user did not specify any hardblocks in config then don't use any
        if "hardblocks" in hb_flows_conf.keys():
            hb_confs = [ parse_yml_config(hb_flow_conf["hb_config_path"]) for hb_flow_conf in hb_flows_conf["hardblocks"] ]
            for hb_conf in hb_confs:
                # pray this is pass by copy not reference
                asic_dse_cli_args = { **asic_dse_cli_args_base }
                asic_dse_cli_args["flow_conf_paths"] = hb_conf["flow_conf_paths"]
                asic_dse_cli = init_dataclass(rg_ds.AsicDseCLI, asic_dse_cli_args)
                hb_inputs = {
                    "asic_dse_cli": asic_dse_cli
                }
                hardblocks.append( init_dataclass(rg_ds.Hardblock, hb_conf, hb_inputs) )
        else:
            hardblocks = None
    else:
        hardblocks = None
    ###################### SETTING UP ASIC TOOL ARGS FOR HARDBLOCKS ######################
    # At this point we have dicts representing asic_dse cli args we need to run for each fpga hardblock    
    coffe_inputs = {
        # Get arch name from the input arch filename
        "arch_name" : os.path.basename(os.path.splitext(coffe_conf["fpga_arch_conf_path"])[0]),
        "fpga_arch_conf": fpga_arch_conf,
        "hardblocks": hardblocks,
    }
    coffe_info = init_dataclass(rg_ds.Coffe, coffe_conf, coffe_inputs)
    return coffe_info



def init_ic_3d_structs(ic_3d_conf: Dict[str, Any]):

    # Add ic_3d specific trees to common
    ic_3d_conf["common"].project_tree.append_tagged_subtree("config", rg_ds.Tree("ic_3d", tag="ic_3d.config"))
    output_subtrees = [
        rg_ds.Tree("includes", tag="inc"),
        rg_ds.Tree("obj_dirs", tag="obj_dirs"),
        rg_ds.Tree("subckts", tag="subckt"),
        rg_ds.Tree("reports", tag="report"),
        rg_ds.Tree("scripts", tag="script"),
    ]
    for output_subtree in output_subtrees:
        ic_3d_conf["common"].project_tree.append_tagged_subtree("output", output_subtree)

    cli_arg_inputs = {}
    for k, v in ic_3d_conf.items():
        if k in rg_ds.Ic3dCLI.__dataclass_fields__:
            cli_arg_inputs[k] = v
    cli_args = init_dataclass(rg_ds.Ic3dCLI, cli_arg_inputs)

    # TODO update almost all the parsing in this function
    ic_3d_conf = parse_yml_config(ic_3d_conf["input_config_path"])
    # check that inputs are in proper format (all metal layer lists are of same length)
    for process_info in ic_3d_conf["process_infos"]:
        if not (all(length == process_info["mlayers"] for length in [len(v) for v in process_info["mlayer_lists"].values()])\
                and all(length == process_info["mlayers"] for length in [len(v) for v in process_info["via_lists"].values()])
                # and len(ic_3d_conf["design_info"]["pwr_rail_info"]["mlayer_dist"]) == process_info["mlayers"]
                ):
            raise ValueError("All metal layer and via lists must be of the same length (mlayers)")
    # Load in process information from yaml
    process_infos = [
        rg_ds.ProcessInfo(
            name=process_info["name"],
            num_mlayers=process_info["mlayers"],
            contact_poly_pitch=process_info["contact_poly_pitch"],
            mlayers=[
                rg_ds.MlayerInfo(
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
                rg_ds.ViaStackInfo(
                    mlayer_range = via_stack["mlayer_range"],
                    res = via_stack["res"],
                    height = via_stack["height"],
                    # Using the average of the metal layer cap per um for the layers used in via stack (this would assume parallel plate cap as much as metal layers so divide by 2)
                    # This should be a conservative estimate with a bit too much capacitance
                    avg_mlayer_cap_per_um = (sum(process_info["mlayer_lists"]["wire_cap_per_um"][via_stack["mlayer_range"][0]:via_stack["mlayer_range"][1]])/len(process_info["mlayer_lists"]["wire_cap_per_um"][via_stack["mlayer_range"][0]:via_stack["mlayer_range"][1]]))*0.5,
                )
                for via_stack in process_info["via_stacks"]
            ],
            tx_geom_info = rg_ds.TxGeometryInfo( 
                min_tx_contact_width = float(process_info["geometry_info"]["min_tx_contact_width"]),
                tx_diffusion_length = float(process_info["geometry_info"]["tx_diffusion_length"]),
                gate_length = float(process_info["geometry_info"]["gate_length"]),
                min_width_tx_area = float(process_info["geometry_info"]["min_width_tx_area"]),
            )
        ) for process_info in ic_3d_conf["process_infos"]
    ]
    

    stage_range = [i for i in range(*ic_3d_conf["d2d_buffer_dse"]["stage_range"])]
    fanout_range = [i for i in range(*ic_3d_conf["d2d_buffer_dse"]["stage_ratio_range"])]
    cost_fx_exps = {
        "delay": ic_3d_conf["d2d_buffer_dse"]["cost_fx_exps"]["delay"],
        "area": ic_3d_conf["d2d_buffer_dse"]["cost_fx_exps"]["area"],
        "power": ic_3d_conf["d2d_buffer_dse"]["cost_fx_exps"]["power"],
    }
    
    # check that inputs are in proper format (all metal layer lists are of same length)
    if not (all(length == len(ic_3d_conf["package_info"]["ubump"]["sweeps"]["pitch"]) for length in [len(v) for v in ic_3d_conf["package_info"]["ubump"]["sweeps"].values()])):
        raise ValueError("All ubump parameter lists must have the same length")
    
    ubump_infos = [
        rg_ds.SolderBumpInfo(
            pitch=ic_3d_conf["package_info"]["ubump"]["sweeps"]["pitch"][idx],
            diameter=float(ic_3d_conf["package_info"]["ubump"]["sweeps"]["pitch"][idx])/2,
            height=ic_3d_conf["package_info"]["ubump"]["sweeps"]["height"][idx],
            cap=ic_3d_conf["package_info"]["ubump"]["sweeps"]["cap"][idx],
            res=ic_3d_conf["package_info"]["ubump"]["sweeps"]["res"][idx],
            tag="ubump",
        ) for idx in range(len(ic_3d_conf["package_info"]["ubump"]["sweeps"]["pitch"]))
    ]


    design_info = rg_ds.DesignInfo(
        srams=[
            rg_ds.SRAMInfo(
                width=float(macro_info["dims"][0]),
                height=float(macro_info["dims"][1]),
            ) for macro_info in ic_3d_conf["design_info"]["macro_infos"]
        ],
        # nocs = [
        #     NoCInfo(
        #         area = float(noc_info["area"]),
        #         rtl_params = noc_info["rtl_params"],
        #         # flit_width = int(noc_info["flit_width"])
        #     ) for noc_info in ic_3d_conf["design_info"]["noc_infos"]
        # ],
        logic_block = rg_ds.HwModuleInfo(
            name = "logic_block",
            area = float(ic_3d_conf["design_info"]["logic_block_info"]["area"]),
            width = float(ic_3d_conf["design_info"]["logic_block_info"]["dims"][0]),
            height = float(ic_3d_conf["design_info"]["logic_block_info"]["dims"][1]),
        ),
        process_info=process_info,
        subckt_libs=rg_ds.SpSubCktLibs(),
        bot_die_nstages = 1,
        buffer_routing_mlayer_idx = int(ic_3d_conf["design_info"]["buffer_routing_mlayer_idx"]),
    )

    esd_rc_params = ic_3d_conf["design_info"]["esd_load_rc_wire_params"]
    if "add_wire_lengths" in ic_3d_conf["design_info"].keys():
        add_wlens = ic_3d_conf["design_info"]["add_wire_lengths"]
    else:
        add_wlens = [0]

    # Other Spice Setup stuff
    # These should be set as defined values rather than k,v pairs so each can be easily accessed from elsewhere
    process_data = rg_ds.SpProcessData(
        global_nodes = {
            "gnd": "gnd",
            "vdd": "vdd"
        },
        voltage_info = {
            "supply_v": "0.7"
        },
        driver_info = {
            # **{
            #     key : val
            #     for stage_idx in range(10)
            #     for key, val in {
            #         f"init_Wn_{stage_idx}" : "1",
            #         f"init_Wp_{stage_idx}" : "2"
            #     }.items()
            # },
            "dvr_ic_in_res" : "1m",
            "dvr_ic_in_cap" : "0.001f",
        },
        geometry_info = None, # These are set later
        tech_info = None # These are set later
    )


    

    # PDN Setup stuff
    design_dims = [float(dim) for dim in ic_3d_conf["design_info"]["dims"]]

    pdn_sim_settings = rg_ds.PDNSimSettings()
    pdn_sim_settings.plot_settings["tsv_grid"] = ic_3d_conf["pdn_sim_settings"]["plot"]["tsv_grid"]
    pdn_sim_settings.plot_settings["c4_grid"] = ic_3d_conf["pdn_sim_settings"]["plot"]["c4_grid"]
    pdn_sim_settings.plot_settings["power_region"] = ic_3d_conf["pdn_sim_settings"]["plot"]["power_region"]
    pdn_sim_settings.plot_settings["pdn_sens_study"] = ic_3d_conf["pdn_sim_settings"]["plot"]["pdn_sens_study"]

    
    design_pdn = rg_ds.DesignPDN(
        floorplan=sh.Polygon([(0,0), (0, design_dims[1]), (design_dims[0], design_dims[1]), (design_dims[0], 0)]),
        power_budget=float(ic_3d_conf["design_info"]["power_budget"]), #W
        process_info=process_infos[0], # TODO update this to support multi process in same run 
        supply_voltage=float(ic_3d_conf["design_info"]["supply_voltage"]), #V
        ir_drop_budget=float(ic_3d_conf["design_info"]["ir_drop_budget"]), #mV 
        fpga_info=rg_ds.FPGAInfo(
            sector_info=rg_ds.SectorInfo(), # unitized SectorInfo class to be calculated from floorplan and resource info
            sector_dims = ic_3d_conf["design_info"]["fpga_info"]["sector_dims"],
            lbs = rg_ds.FPGAResource(
                total_num = int(ic_3d_conf["design_info"]["fpga_info"]["lbs"]["total_num"]),
                abs_area = float(ic_3d_conf["design_info"]["fpga_info"]["lbs"]["abs_area"]),
                rel_area = int(ic_3d_conf["design_info"]["fpga_info"]["lbs"]["rel_area"]),
                abs_width = float(ic_3d_conf["design_info"]["fpga_info"]["lbs"]["abs_width"]),
                abs_height = float(ic_3d_conf["design_info"]["fpga_info"]["lbs"]["abs_height"]),
            ),
            dsps = rg_ds.FPGAResource(
                total_num = int(ic_3d_conf["design_info"]["fpga_info"]["dsps"]["total_num"]),
                abs_area = float(ic_3d_conf["design_info"]["fpga_info"]["dsps"]["abs_area"]),
                rel_area = int(ic_3d_conf["design_info"]["fpga_info"]["dsps"]["rel_area"]),
            ),
            brams = rg_ds.FPGAResource(
                total_num = int(ic_3d_conf["design_info"]["fpga_info"]["brams"]["total_num"]),
                abs_area = float(ic_3d_conf["design_info"]["fpga_info"]["brams"]["abs_area"]),
                rel_area = int(ic_3d_conf["design_info"]["fpga_info"]["brams"]["rel_area"]),
            )
        ),
        pwr_rail_info=rg_ds.PwrRailInfo(
            # pitch_fac=float(ic_3d_conf["design_info"]["pwr_rail_info"]["pitch_fac"]),
            mlayer_dist = [float(ic_3d_conf["design_info"]["pwr_rail_info"]["mlayer_dist"]["bot"]),float(ic_3d_conf["design_info"]["pwr_rail_info"]["mlayer_dist"]["top"])],
            num_mlayers = int(ic_3d_conf["design_info"]["pwr_rail_info"]["num_mlayers"]),
        ),
        tsv_info=rg_ds.TSVInfo(
            single_tsv=rg_ds.SingleTSVInfo(
                height=int(ic_3d_conf["package_info"]["tsv"]["height"]), #um
                diameter=int(ic_3d_conf["package_info"]["tsv"]["diameter"]), #um
                pitch=int(ic_3d_conf["package_info"]["tsv"]["pitch"]), #um
                resistivity=float(ic_3d_conf["package_info"]["tsv"]["resistivity"]), #Ohm*um (1.72e-8 * 1e6)
                keepout_zone=float(ic_3d_conf["package_info"]["tsv"]["keepout_zone"]), # um     
                resistance=float(ic_3d_conf["package_info"]["tsv"]["resistance"]), #Ohm
            ),
            area_bounds = ic_3d_conf["design_info"]["pwr_placement"]["tsv_area_bounds"],
            placement_setting = ic_3d_conf["design_info"]["pwr_placement"]["tsv_grid"],
            koz_grid=None,
            tsv_grid=None,
        ),
        c4_info=rg_ds.C4Info(
            rg_ds.SingleC4Info(
                height=int(ic_3d_conf["package_info"]["c4"]["height"]), #um
                diameter=int(ic_3d_conf["package_info"]["c4"]["diameter"]), #um
                pitch=int(ic_3d_conf["package_info"]["c4"]["pitch"]), #um
                resistance=float(ic_3d_conf["package_info"]["c4"]["resistance"]), #Ohm
                area=None,
            ),                
            placement_setting = ic_3d_conf["design_info"]["pwr_placement"]["c4_grid"],
            margin=int(ic_3d_conf["package_info"]["c4"]["margin"]), #um
            grid=None,       
        ),
        ubump_info=rg_ds.UbumpInfo(
            single_ubump=rg_ds.SingleUbumpInfo(
                height=float(ic_3d_conf["package_info"]["ubump"]["height"]), #um
                diameter=float(ic_3d_conf["package_info"]["ubump"]["diameter"]), #um
                pitch=float(ic_3d_conf["package_info"]["ubump"]["pitch"]), #um
                # resistivity=float(ic_3d_conf["package_info"]["ubump"]["resistivity"]), #Ohm*um (1.72e-8 * 1e6)    
            ),
            margin=float(ic_3d_conf["package_info"]["ubump"]["margin"]),
            grid=None,
        )
    )
    
    tx_sizing = rg_ds.TxSizing(
        opt_mode = ic_3d_conf["d2d_buffer_dse"]["tx_sizing"]["opt_mode"],
        pmos_sz= ic_3d_conf["d2d_buffer_dse"]["tx_sizing"]["pmos_sz"],
        nmos_sz= ic_3d_conf["d2d_buffer_dse"]["tx_sizing"]["nmos_sz"],
    )    


    ic3d_inputs = {
        # BUFFER DSE STUFF
        "design_info": design_info,
        "process_infos": process_infos,
        "ubump_infos": ubump_infos,
        # TODO put these into design info
        "esd_rc_params": esd_rc_params,
        "add_wlens" : add_wlens,
        # TODO put these somewhere better
        "stage_range": stage_range,
        "fanout_range": fanout_range,
        "cost_fx_exps": cost_fx_exps,
        "tx_sizing": tx_sizing,
        
        # previous globals from 3D IC TODO fix this to take required params from top conf
        # remove all these bs dataclasses I don't need
        "spice_info": rg_ds.SpInfo(),
        "process_data": process_data,
        "driver_model_info": rg_ds.DriverSpModel(),
        "pn_opt_model": rg_ds.SpPNOptModel(),
        "res": rg_ds.Regexes(),
        "sp_sim_settings": rg_ds.SpGlobalSimSettings(),
        # PDN STUFF
        "pdn_sim_settings": pdn_sim_settings,
        "design_pdn": design_pdn,
        "cli_args": cli_args,
    }



    ic_3d_info = init_dataclass(rg_ds.Ic3d, ic3d_inputs)
    return ic_3d_info


def write_out_script(lines: List[str], fpath: str, shebang: str = "#!/bin/bash"):
    """
        Takes list of lines for a script, prepends a header onto it and writes it out to the specified path
    """
    rad_gen_log("\n".join([shebang] + create_bordered_str("Autogenerated Sweep Script")),rad_gen_log_fd)
    rad_gen_log("\n".join(lines), rad_gen_log_fd)

    lines = create_bordered_str("Autogenerated Sweep Script") + lines
    open(fpath, 'w').close()
    for line in lines:
        # clear whatever exists in the file
        # Write line by line to file
        with open(fpath , "a") as fd:
            file_write_ln(fd, line)
    # Run permissions cmd to make script executable
    permission_cmd = f"chmod +x {fpath}"
    run_shell_cmd_no_logs(permission_cmd)


# COMMENTED BELOW RUN_OPTS (args) as they are not used
def load_arch_params(filename): #,run_options):
    # This is the dictionary of parameters we expect to find
    #No defaults for ptn or run settings
    arch_params = {
        'W': -1,
        'L': -1,
        'wire_types': [],
        'Fs': -1,
        'N': -1,
        'K': -1,
        'I': -1,
        'Fcin': -1.0,
        'Fcout': -1.0,
        'Or': -1,
        'Ofb': -1,
        'Fclocal': -1.0,
        'Rsel': "",
        'Rfb': "",
        'transistor_type': "",
        'switch_type': "",
        'use_tgate': False,
        'use_finfet': False,
        'memory_technology': "SRAM",
        'enable_bram_module': 0,
        'ram_local_mux_size': 25,
        'read_to_write_ratio': 1.0,
        'vdd': -1.0,
        'vsram': -1.0,
        'vsram_n': -1.0,
        'vclmp': 0.653,
        'vref': 0.627,
        'vdd_low_power': 0.95,
        'number_of_banks': 1,
        'gate_length': -1,
        'rest_length_factor': -1,
        'min_tran_width': -1,
        'min_width_tran_area': -1,
        'sram_cell_area': -1,
        'trans_diffusion_length' : -1,
        'model_path': "",
        'model_library': "",
        'metal' : [],
        'row_decoder_bits': 8,
        'col_decoder_bits': 1,
        'conf_decoder_bits' : 5,
        'sense_dv': 0.3,
        'worst_read_current': 1e-6,
        'SRAM_nominal_current': 1.29e-5,
        'MTJ_Rlow_nominal': 2500,
        'MTJ_Rhigh_nominal': 6250,
        'MTJ_Rlow_worstcase': 3060,
        'MTJ_Rhigh_worstcase': 4840,
        'use_fluts': False,
        'independent_inputs': 0,
        'enable_carry_chain': 0,
        'carry_chain_type': "ripple",
        'FAs_per_flut':2,
        'arch_out_folder': "None",
        'gen_routing_metal_pitch': 0.0,
        'gen_routing_metal_layers': 0,
    }
    
    #top level param types
    param_type_names = ["fpga_arch_params","asic_hardblock_params"]
    hb_sub_param_type_names = ["hb_run_params", "ptn_params"]
    #get values from yaml file
    with open(filename, 'r') as file:
        param_dict = yaml.safe_load(file)

    #check to see if the input settings file is a subset of defualt params
    for key in arch_params.keys():
        if(key not in param_dict["fpga_arch_params"].keys()):
            #assign default value if key not found 
            param_dict["fpga_arch_params"][key] = arch_params[key]

    #load defaults into unspecified values
    for k,v in param_dict.items():
        #if key exists in arch_dict
        if(k in param_type_names):
            for k1,v1 in v.items():
                #parse arch params
                if(k1 in arch_params):
                    if(v1 == None):
                        v[k1] = arch_params[k1]
                else:
                    print("ERROR: Found invalid parameter (" + k1 + ") in " + filename)
                    sys.exit()

    # TODO make this cleaner, should probably just have a data structure containing all expected data types for all params
    for param,value in zip(list(param_dict["fpga_arch_params"]),list(param_dict["fpga_arch_params"].values())):
        #architecture parameters
        if param == 'W':
            param_dict["fpga_arch_params"]['W'] = int(value)
        elif param == 'L':
            param_dict["fpga_arch_params"]['L'] = int(value)
        elif param == 'wire_types':
            # should be a list of dicts
            tmp_list = []
            for wire_type in param_dict["fpga_arch_params"]["wire_types"]:
                tmp_list.append(
                    wire_type
                )
            param_dict["fpga_arch_params"]["wire_types"] = tmp_list
        elif param == 'Fs':
            param_dict["fpga_arch_params"]['Fs'] = int(value)
        elif param == 'N':
            param_dict["fpga_arch_params"]['N'] = int(value)
        elif param == 'K':
            param_dict["fpga_arch_params"]['K'] = int(value)
        elif param == 'I':
            param_dict["fpga_arch_params"]['I'] = int(value)
        elif param == 'Fcin':
            param_dict["fpga_arch_params"]['Fcin'] = float(value)
        elif param == 'Fcout':
            param_dict["fpga_arch_params"]['Fcout'] = float(value) 
        elif param == 'Or':
            param_dict["fpga_arch_params"]['Or'] = int(value)
        elif param == 'Ofb':
            param_dict["fpga_arch_params"]['Ofb'] = int(value)
        elif param == 'Fclocal':
            param_dict["fpga_arch_params"]['Fclocal'] = float(value)
        elif param == 'Rsel':
            param_dict["fpga_arch_params"]['Rsel'] = str(value)
        elif param == 'Rfb':
            param_dict["fpga_arch_params"]['Rfb'] = str(value)
        elif param == 'row_decoder_bits':
            param_dict["fpga_arch_params"]['row_decoder_bits'] = int(value)
        elif param == 'col_decoder_bits':
            param_dict["fpga_arch_params"]['col_decoder_bits'] = int(value)
        elif param == 'number_of_banks':
            param_dict["fpga_arch_params"]['number_of_banks'] = int(value)
        elif param == 'conf_decoder_bits':
            param_dict["fpga_arch_params"]['conf_decoder_bits'] = int(value) 
        #process technology parameters
        elif param == 'transistor_type':
            param_dict["fpga_arch_params"]['transistor_type'] = str(value)
            if value == 'finfet':
                param_dict["fpga_arch_params"]['use_finfet'] = True
        elif param == 'switch_type':  
            param_dict["fpga_arch_params"]['switch_type'] = str(value)        
            if value == 'transmission_gate':
                param_dict["fpga_arch_params"]['use_tgate'] = True
        elif param == 'memory_technology':
            param_dict["fpga_arch_params"]['memory_technology'] = str(value)
        elif param == 'vdd':
            param_dict["fpga_arch_params"]['vdd'] = float(value)
        elif param == 'vsram':
            param_dict["fpga_arch_params"]['vsram'] = float(value)
        elif param == 'vsram_n':
            param_dict["fpga_arch_params"]['vsram_n'] = float(value)
        elif param == 'gate_length':
            param_dict["fpga_arch_params"]['gate_length'] = int(value)
        elif param == 'sense_dv':
            param_dict["fpga_arch_params"]['sense_dv'] = float(value)
        elif param == 'vdd_low_power':
            param_dict["fpga_arch_params"]['vdd_low_power'] = float(value)
        elif param == 'vclmp':
            param_dict["fpga_arch_params"]['vclmp'] = float(value)
        elif param == 'read_to_write_ratio':
            param_dict["fpga_arch_params"]['read_to_write_ratio'] = float(value)
        elif param == 'enable_bram_module':
            param_dict["fpga_arch_params"]['enable_bram_module'] = int(value)
        elif param == 'ram_local_mux_size':
            param_dict["fpga_arch_params"]['ram_local_mux_size'] = int(value)
        elif param == 'use_fluts':
            param_dict["fpga_arch_params"]['use_fluts'] = bool(value)
        elif param == 'independent_inputs':
            param_dict["fpga_arch_params"]['independent_inputs'] = int(value)
        elif param == 'enable_carry_chain':
            param_dict["fpga_arch_params"]['enable_carry_chain'] = int(value)
        elif param == 'carry_chain_type':
            param_dict["fpga_arch_params"]['carry_chain_type'] = value
        elif param == 'FAs_per_flut':
            param_dict["fpga_arch_params"]['FAs_per_flut'] = int(value)
        elif param == 'vref':
            param_dict["fpga_arch_params"]['ref'] = float(value)
        elif param == 'worst_read_current':
            param_dict["fpga_arch_params"]['worst_read_current'] = float(value)
        elif param == 'SRAM_nominal_current':
            param_dict["fpga_arch_params"]['SRAM_nominal_current'] = float(value)
        elif param == 'MTJ_Rlow_nominal':
            param_dict["fpga_arch_params"]['MTJ_Rlow_nominal'] = float(value)
        elif param == 'MTJ_Rhigh_nominal':
            param_dict["fpga_arch_params"]['MTJ_Rhigh_nominal'] = float(value)
        elif param == 'MTJ_Rlow_worstcase':
            param_dict["fpga_arch_params"]['MTJ_Rlow_worstcase'] = float(value)
        elif param == 'MTJ_Rhigh_worstcase':
            param_dict["fpga_arch_params"]['MTJ_Rhigh_worstcase'] = float(value)          
        elif param == 'rest_length_factor':
            param_dict["fpga_arch_params"]['rest_length_factor'] = int(value)
        elif param == 'min_tran_width':
            param_dict["fpga_arch_params"]['min_tran_width'] = int(value)
        elif param == 'min_width_tran_area':
            param_dict["fpga_arch_params"]['min_width_tran_area'] = int(value)
        elif param == 'sram_cell_area':
            param_dict["fpga_arch_params"]['sram_cell_area'] = float(value)
        elif param == 'trans_diffusion_length':
            param_dict["fpga_arch_params"]['trans_diffusion_length'] = float(value)
        elif param == 'model_path':
            param_dict["fpga_arch_params"]['model_path'] = os.path.abspath(value)
        elif param == 'metal':
            tmp_list = []
            for rc_vals in param_dict["fpga_arch_params"]["metal"]:
                tmp_list.append(tuple(rc_vals))
            param_dict["fpga_arch_params"]['metal'] = tmp_list
        elif param == 'model_library':
            param_dict["fpga_arch_params"]['model_library'] = str(value)
        elif param == 'arch_out_folder':
            param_dict["fpga_arch_params"]['arch_out_folder'] = str(value)
        elif param == 'gen_routing_metal_pitch':
            param_dict["fpga_arch_params"]['gen_routing_metal_pitch'] = float(value)
        elif param == 'gen_routing_metal_layers':
            param_dict["fpga_arch_params"]['gen_routing_metal_layers'] = int(value)
    
    # Check architecture parameters to make sure that they are valid
    coffe_utils.check_arch_params(param_dict["fpga_arch_params"], filename)
    return param_dict    

# COMMENTED BELOW RUN_OPTS (args) as they are not used
def load_hb_params(filename): #,run_options):
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