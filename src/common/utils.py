from __future__ import annotations
from typing import List, Dict, Tuple, Set, Union, Any, Type, Callable, cast
import typing
import os, sys, yaml
import argparse
import datetime
import shutil

import logging

import importlib
import shapely as sh


from dataclasses import fields, field, asdict, is_dataclass, dataclass, MISSING
import dataclasses
import json

from pathlib import Path
import copy
import io


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

# Defining each task cli globally for easy access in other functions perfoming read actions
asic_dse_cli = rg_ds.AsicDseCLI()
coffe_cli = rg_ds.CoffeCLI()
ic_3d_cli = rg_ds.Ic3dCLI()
common_cli = rg_ds.RadGenCLI()


# ██╗      ██████╗  ██████╗  ██████╗ ██╗███╗   ██╗ ██████╗ 
# ██║     ██╔═══██╗██╔════╝ ██╔════╝ ██║████╗  ██║██╔════╝ 
# ██║     ██║   ██║██║  ███╗██║  ███╗██║██╔██╗ ██║██║  ███╗
# ██║     ██║   ██║██║   ██║██║   ██║██║██║╚██╗██║██║   ██║
# ███████╗╚██████╔╝╚██████╔╝╚██████╔╝██║██║ ╚████║╚██████╔╝
# ╚══════╝ ╚═════╝  ╚═════╝  ╚═════╝ ╚═╝╚═╝  ╚═══╝ ╚═════╝ 

def log_format_list(*args : Tuple[str]) -> str:
    """
    Args:
        args (Tuple[str]): A tuple of strings to be formatted into a log message
    
    Returns:
        A log message of format [{arg1}][{arg2}]...[{argN}]
    """
    # Format the extra arguments as [{arg1}][{arg2}]...[{argN}]
    if args:
        formatted_args = "".join([f"[{arg}]" for arg in args]) + ":"
    else:
        formatted_args = ":"
    return formatted_args

#  ██████╗ ███████╗███╗   ██╗███████╗██████╗  █████╗ ██╗         ██╗   ██╗████████╗██╗██╗     ███████╗
# ██╔════╝ ██╔════╝████╗  ██║██╔════╝██╔══██╗██╔══██╗██║         ██║   ██║╚══██╔══╝██║██║     ██╔════╝
# ██║  ███╗█████╗  ██╔██╗ ██║█████╗  ██████╔╝███████║██║         ██║   ██║   ██║   ██║██║     ███████╗
# ██║   ██║██╔══╝  ██║╚██╗██║██╔══╝  ██╔══██╗██╔══██║██║         ██║   ██║   ██║   ██║██║     ╚════██║
# ╚██████╔╝███████╗██║ ╚████║███████╗██║  ██║██║  ██║███████╗    ╚██████╔╝   ██║   ██║███████╗███████║
#  ╚═════╝ ╚══════╝╚═╝  ╚═══╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝     ╚═════╝    ╚═╝   ╚═╝╚══════╝╚══════╝


def compare_dataframes(df1_name: str, df1: pd.DataFrame, df2_name: str, df2: pd.DataFrame) -> pd.DataFrame:
    """
        Compare two dataframes and return a new dataframe with the percentage difference between the two dataframes.
        If a value is missing in one of the dataframes, the corresponding cell in the comparison dataframe will be marked as "Missing".

        Args:
            df1_name: The name of the first dataframe.
            df1: The first dataframe to compare.
            df2_name: The name of the second dataframe.
            df2: The second dataframe to compare.
        
        Returns:
            A new dataframe containing the percentage difference between the two dataframes.

    """
    # Ensure the dataframes have the same shape
    if df1.shape != df2.shape:
        raise ValueError("Dataframes must have the same shape for comparison")

    # Initialize an empty dataframe to store the comparisons
    comparisons = pd.DataFrame(index=df1.index, columns=df1.columns)

    for column in df1.columns:
        for row_id in df1.index:
            value1 = df1.iloc[row_id].at[column]
            value2 = df2.iloc[row_id].at[column]
            if isinstance(value1, (float, int )) and isinstance(value2, (float, int)):
                # Calculate the percentage difference for numerical columns
                comparisons.iloc[row_id].at[column] = ((value2 - value1) / value1) * 100
            elif not isinstance(value1, (float, int )) and isinstance(value2, (float, int)):
                comparisons.iloc[row_id].at[column] = f"{df1_name} Missing"
            elif isinstance(value1, (float, int )) and not isinstance(value2, (float, int )):
                comparisons.iloc[row_id].at[column] = f"{df2_name} Missing"
            else:
                # Covering case where neither is numeric data type, could just be strings
                if isinstance(value1, str) and isinstance(value2, str):
                    if value1 != value2:
                        comparisons.iloc[row_id].at[column] = f"{value1} != {value2}"
                    else:
                        comparisons.iloc[row_id].at[column] = value1
                # If they are the same just keep the string value

    return comparisons

def compare_dataframe_row(df1: pd.DataFrame, df2: pd.DataFrame, row_index: int):
    """
        Compare a row from two dataframes and return a new dataframe with the percentage difference between the two rows. 
        For large dataframes this function is not ideal as it creates a new dataframe for each row comparison.

        Args:
            df1: The first dataframe to compare.
            df2: The second dataframe to compare.
            row_index: The index of the row to compare.
        
        Returns:
            A new dataframe (with a single row) containing the percentage difference between the two rows.
    """
    # Select the specified rows from both DataFrames
    row1 = df1.loc[row_index]
    row2 = df2.loc[row_index]
    
    # Initialize an empty dictionary to store the comparisons
    comparisons = {}

    # Iterate through the columns
    for column in df1.columns:
        value1 = row1[column]
        value2 = row2[column]

        # Check if the column values are numerical
        if pd.api.types.is_numeric_dtype(df1[column]):
            # Calculate the percentage difference for numerical columns
            if pd.notna(value1) and pd.notna(value2):
                # If statement to fix strange bug where 0 turns to nan
                if value1 == value2:
                    percent_diff = 0.0
                else:
                    percent_diff = ((value2 - value1) / value1) * 100
                comparisons[column] = percent_diff
            else:
                # Handle cases where one or both values are missing
                comparisons[column] = "Missing-Values"
        else:
            # Mark string columns as different
            if value1 != value2:
                comparisons[column] = "Different"
            else:
                comparisons[column] = "Matching"
    
    # Convert the comparisons dictionary into a DataFrame
    comparison_df = pd.DataFrame.from_dict(comparisons, orient='index', columns=['Difference (%)'])
    
    return comparison_df

def compare_results(input_csv_path: str, ref_csv_path: str) -> pd.DataFrame:
    """
        Compares the results of an output csv generated by RAD-Gen and a reference csv, searched for in a specified directory

        Args:
            input_csv_path: The path to the input csv file.
            ref_csv_path: The path to the reference csv file.
        
        Returns:
            A new dataframe (with a single row) containing the percentage difference between the two rows.
    """
    # This will be slow as we are basically doing an O(n) search for each input but that's ok for now
    input_df = pd.read_csv(input_csv_path)
    output_df = pd.read_csv(ref_csv_path)
    comp_df = compare_dataframe_row(input_df, output_df, 0)
    
    return comp_df



def str_match_condition(cmp_key: str, filt_key: str) -> bool:
    """
        Returns True if filt_key is in search_key. 
        Function is used often in combination with get_unique_obj to get a single object from a list of keys.

        Args:
            cmp_key: key to look for substr in
            filt_key: substr to look for in cmp_key

        Returns:
            True if filt_key is in cmp_key, False otherwise
    """
    return filt_key in cmp_key


def get_unique_obj(objects: List[Any], condition: Callable = None, *args, **kwargs) -> Any:
    """
        Returns an object from a list that satisfies the callable condition
            if no objects satisfy this condition we throw error as it should exist
            if multiple objects satisfy this condition, we throw error as it should be unique
        If no condition is provided, the first object in the list is returned, then just checks to see that the list is of 1 elements

        Args:
            objects: list of objects to search through
            condition: callable condition to check for each object in objects
            *args: additional arguments to pass to condition
            **kwargs: additional keyword arguments to pass to condition

        Returns:
            The object that satisfies the condition

        Raises:
            ValueError: If no matching object is found, multiple matching objects are found, or no matching object is found
    """
    if condition is not None:
        matching_objs: List[Any] = [obj for obj in objects if condition(obj, *args, **kwargs)]
    else:
        matching_objs: List[Any] = objects
    if len(matching_objs) == 0:
        raise ValueError("ERROR: No matching object found")
    elif len(matching_objs) > 1:
        raise ValueError("ERROR: Multiple matching objects found")
    elif len(matching_objs) == 1:
        return matching_objs[0]
    else:
        raise ValueError("ERROR: No matching object found")    


def typecast_input_to_dataclass(input_value: dict, dataclass_type: Any) -> rg_ds.Dataclass:
    """
        Typecasts input_value to the corresponding dataclass_type.
        
        Args:
            input_value: The input dictionary for which each key corresponding to dataclass field names will by type casted to the corresponding dataclass field type.
            dataclass_type: The dataclass type to which the input_value key, values will be type casted.
        
        Returns:
            dataclass object with fields typecasted
    """
    dc_fields = fields(dataclass_type)
    output = {}

    for dc_field in dc_fields:
        field_name = dc_field.name
        field_type = dc_field.type

        if input_value.get(field_name) is None:
            output[field_name] = None
            continue
        # Perform typecasting based on field type
        # If the field is already of correct type, set it as is
        elif isinstance(input_value.get(field_name), eval(field_type)):
            output[field_name] = input_value.get(field_name)
        # If the field is not of correct type we typecast it
        else:
            try:
                output[field_name] = eval(field_type)(input_value.get(field_name))
            except (ValueError, TypeError):
                output[field_name] = None  # If typecasting fails, set to None
    
    return dataclass_type(**output)

class EnhancedJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if dataclasses.is_dataclass(obj):
            return dataclasses.asdict(obj)
        return super().default(obj)

def rec_convert_dataclass_to_dict(obj, key: str = None):
    """
        Converts a dict / dataclass of nested dicts / dataclasses into a dictionary object
    """
    # Checks if its a type we should skip
    skip_tup = (
        rg_ds.HammerDriver,
    )
    if isinstance(obj, skip_tup):
        return None
    elif dataclasses.is_dataclass(obj):
        try:
            # If there is a module that's not serializable we will convert manually instead
            return {k: rec_convert_dataclass_to_dict(v, k) for k, v in dataclasses.asdict(obj).items()}
        except: 
            # manually traversing the dataclass fields
            result = {}
            for field in dataclasses.fields(obj):
                field_val = getattr(obj, field.name)
                result[field.name] = rec_convert_dataclass_to_dict(field_val, field.name)
            return result

    elif isinstance(obj, list):
        return [rec_convert_dataclass_to_dict(i, key) for i in obj]
    elif isinstance(obj, dict):
        return {k: rec_convert_dataclass_to_dict(v, k) for k, v in obj.items()}
    # checks if instance is any primitive type, if its not then its a non dataclass class so we have to ignore for now
    elif not isinstance(obj, (str, int, float, bool)) and obj is not None:
        return None
    # Case for exporting paths so tests can be non system specific
    elif isinstance(obj, str) and key != None and 'path' in key:
        return obj.replace(os.path.expanduser('~'), '~')
    else:
        return obj

def dataclass_2_json(in_dataclass: Any, out_fpath: str):
    json_text = json.dumps(rec_convert_dataclass_to_dict(in_dataclass), cls=EnhancedJSONEncoder, indent=4)
    with open(out_fpath, "w") as f:
        f.write(json_text)


def format_csv_data(data: List[List[Any]]) -> List[List[str]]:
    """
        Format csv data to be output as a string for a logger or to write to a csv using `write_csv_file` function

        Args: 
            data: List of lists containing the data to be formatted
        
        Returns:
            List of lists of strings containing the formatted data
    """
    # Specify the width for each column
    column_widths = [max(len(str(value)) for value in column) + 2 for column in zip(*data)]

    # Format the rows
    formatted_rows = []
    for row in data:
        formatted_row = [str(value).ljust(width) for value, width in zip(row, column_widths)]
        formatted_rows.append(formatted_row)

    return formatted_rows


# TODO deletion candidate as its not used
def flatten(dictionary, parent_key='', separator='.') -> dict:
    """
        Turns a nested dictionary into a flattened one with seperator delimited keys
        
        Examples:
            >>> dictionary = {"a": {"b": 1, "c": 2}, "d": {"e": {"f": 3}}}
            >>> flatten(dictionary)
            {"a.b": 1, "a.c": 2, "d.e.f": 3}
        
        Args:
            dictionary: The dictionary to flatten
            parent_key: Key of any parent dict field
            separator: The separator to use between keys

        Returns:
            A flattened dictionary with separator delimited heirarchy to replace a previous nested dict

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
        Used mainly in ic_3d.py for writing out reports
        
        Args:
            key: The key of the data to be converted
            val: The value of the data to be converted

        Returns:
            A tuple containing the key and value in the report format
            
        Todo:
            * Instead of using this function find some unified way to get from a k,v pair to a report format

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

def rad_gen_log(log_str: str, file: str) -> None:
    """
        Prints to a log file and the console depending on level of verbosity

        Args:
            log_str: The string to log
            file: The file path to log to
        
    """
    if file == sys.stdout:
        print(f"{log_str}")
    else:
        fd = open(file, 'a')
        if(log_verbosity >= 0):
            print(f"{log_str}",file=fd)
            print(f"{log_str}")
        fd.close()

# TODO deletion candidate as its not used
def are_lists_mutually_exclusive(lists: List[List[Any]]) -> bool:
    """
        Checks if input list of lists are mutually exclusive

        Args:
            lists: List of lists to check for mutual exclusivity between them

        Returns:
            True if all lists are mutually exclusive, False otherwise

    """
    return all(not set(lists[i]) & set(lists[j]) for i in range(len(lists)) for j in range(i + 1, len(lists)))

# TODO deletion candidate as its not used
def write_csv_file(filename: str, formatted_data: List[List[Any]]) -> None:
    """
    Write formatted data to a CSV file. 
    Uses format_csv_data to get formatted data.

    Examples:
        >>> data = [
            ['Name', 'Age', 'City'],
            ['John Doe', 25, 'New York'],
            ['Jane Smith', 30, 'San Francisco'],
            ['Bob Johnson', 22, 'Chicago'],
        ]
        >>> formatted_data = format_csv_data(data)
        >>> write_csv_file('output.csv', formatted_data)

    Args:
        filename: The name of the CSV file to be created or overwritten.
        formatted_data: A list of lists containing formatted data.
            Each inner list represents a row, and its elements are left-aligned
            strings with specified widths.

    """
    with open(filename, 'w', newline='') as csvfile:
        csv_writer = csv.writer(csvfile)
        csv_writer.writerows(formatted_data)

# TODO deletion candidate as its not used
def read_csv_up_to_row(file_path: str, row_index: int) -> List[Dict[str, Any]]:
    """
    Reads a CSV file up to a specified row index and returns the data as a list of dictionaries.

    Args:
        file_path: The path to the CSV file.
        row_index: The index of the last row to read (inclusive).

    Returns:
        A list of dictionaries of the rows read from the CSV file.
    """
    rows = []
    with open(file_path, newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        for i, row in enumerate(reader):
            if i > row_index:
                break
            rows.append(dict(row))
    return rows


def write_dict_to_csv(csv_lines: List[Dict[str, Any]], csv_fname: str) -> None:
    """
        Writes a list of dictionaries to a csv file (in current directory)

        Args:
            csv_lines: List of dictionaries to write to csv
            csv_fname: The name of the csv file to write to (without .csv extension)
        
        Todo:
            * change csv_fname to fpath and make it have to include .csv extension
    """
    csv_fd = open(f"{csv_fname}.csv","w")
    writer = csv.DictWriter(csv_fd, fieldnames=csv_lines[0].keys())
    writer.writeheader()
    for line in csv_lines:
        writer.writerow(line)
    csv_fd.close()

def write_single_dict_to_csv(in_dict: Dict[str, Any], fpath: str, fopen_opt: str) -> None:
    """
        Using a single dictionary, write the values to the specified csv

        Args:
            in_dict: Dictionary to write to csv
            fpath: The path to the csv file to write to
            fopen_opt: The file open mode
    """
    with open(fpath, fopen_opt) as csv_file:
        header = list(in_dict.keys())
        writer = csv.DictWriter(csv_file, fieldnames = header)
        # Check if the file is empty and write header if needed
        if csv_file.tell() == 0:
            writer.writeheader()
        writer.writerow(in_dict)



def read_csv_to_list(csv_fname: str) -> List[Dict[str, Any]]:
    """
        Reads a csv file into a list of dictionaries

        Args:
            csv_fname: The name of the csv file to read from
        
        Returns:
            A list of dictionaries containing the data from the csv
    """
    csv_fd = open(f"{csv_fname}","r")
    reader = csv.DictReader(csv_fd)
    csv_lines = []
    for line in reader:
        csv_lines.append(line)
    csv_fd.close()
    return csv_lines

def read_csv_to_list_w_dups(csv_fname: str, rep_suffix: str = "_rep") -> List[Dict[str, Any]]:
    """
        Reads a csv file into a list of dictionaries (possibly with duplicate headers)

        Args:
            csv_fname: The name of the csv file to read from
            rep_suffix: The suffix to add to duplicate headers
        
        Returns:
            A list of dictionaries containing the data from the csv
    """
    csv_lines = []
    with open(csv_fname, "r") as csv_fd:
        reader = csv.reader(csv_fd)
        headers = next(reader)  # Get the headers from the first row
        for row in reader:
            # Create a dictionary to store the data for this row
            row_data = {}
            for index, header in enumerate(headers):
                if header in row_data:
                    row_data[f"{header}_{rep_suffix}"] = row[index]
                # Skip csv entries that are blank
                elif header == "" and row_data == "":
                    continue
                else:
                    # If the header is not yet in the dictionary, add it with the corresponding value
                    row_data[header] = row[index]
            csv_lines.append(row_data)
    return csv_lines

def create_bordered_str(text: str = "", border_char: str = "#", total_len: int = 150) -> List[str]:
    """
        Creates a bordered string with text in the center

        Args:
            text: The text to be centered in the bordered string
            border_char: The character to use for the border
            total_len: The total (row-wise) length of the bordered string

        Returns:
            A list of strings (of len 3) containing the bordered string (top, middle, bottom)
    """
    text = f"  {text}  "
    text_len = len(text)
    if(text_len > total_len):
        total_len = text_len + 10 
    border_size = (total_len - text_len) // 2
    return [ border_char * total_len, f"{border_char * border_size}{text}{border_char * border_size}", border_char * total_len]


def c_style_comment_rm(text: str) -> str:
    """ 
        From "https://stackoverflow.com/questions/241327/remove-c-and-c-comments-using-python"
        This function removes C/C++ style comments from a file
        WARNING does not work for all cases (such as escaped characters and other edge cases of comments) but should work for most
        
        Args:
            text: The text to remove comments from
        
        Returns:
            The text with C/C++ style comments removed
    
        Todo:
            * Replace this function with an implementation from "https://stackoverflow.com/questions/2394017/remove-comments-from-c-c-code"
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


def rec_find_fpath(dir: str, fname: str) -> str | None:
    """
        Finds a file recursivley in a directory and returns the path to it
    
        Args:
            dir: The directory path to search in
            fname: The name of the file to search for

        Returns:
            The path to the file if found, None otherwise
    """
    ret_val = None
    for root, dirs, files in os.walk(dir):
        if fname in files:
            ret_val = os.path.join(root, fname)
    return ret_val

# TODO deletion candidate as its not used
def pretty(d: dict, indent: int = 0) -> None:
    """
        Pretty prints a dictionary

        Args:
            d: The dictionary to pretty print
            indent: The number of tabs to indent the dictionary
        
    """
    for key, value in d.items():
        print('\t' * indent + str(key))
        if isinstance(value, dict):
            pretty(value, indent+1)
        else:
            print('\t' * (indent+1) + str(value))

def truncate(f: float, n: int) -> str:
    """
        Truncates/pads a float f to n decimal places without rounding

        Args:
            f: The float to truncate
            n: The number of decimal places to truncate to
        
        Returns:
            The truncated float as a string
    """
    s = '{}'.format(f)
    if 'e' in s or 'E' in s:
        return '{0:.{1}f}'.format(f, n)
    i, p, d = s.partition('.')
    return '.'.join([i, (d+'0'*n)[:n]])

def flatten_mixed_list(input_list: list) -> list:
    """
        Flattens a list with mixed value
        Probably has less than optimal performance should not be used on extremely large lists

        Examples:
            >>> flatten_mixed_list(["hello", ["billy","bob"],[["johnson"]]])
            ["hello", "billy", "bob", "johnson"]
        
        Args:
            input_list: The list to flatten
        
        Returns:
            The flattened list
    """
    # Create flatten list lambda function
    flat_list = lambda input_list:[element for item in input_list for element in flat_list(item)] if type(input_list) is list else [input_list]
    # Call lambda function
    flattened_list = flat_list(input_list)
    return flattened_list

# TODO deletion candidate as its not used
def run_shell_cmd(cmd_str: str, log_file: str) -> None:
    """
        Runs a shell command and logs the output to a file using linux 'tee' cmd 
        
        Args:
            cmd_str: The shell command to run
            log_file: The file to log the output to
        
    """
    run_cmd = cmd_str + f" | tee {log_file}"
    rad_gen_log(f"Running: {run_cmd}", rad_gen_log_fd)
    sp.call(run_cmd, shell=True, executable='/bin/bash', env=cur_env)

def run_shell_cmd_no_logs(cmd_str: str, to_log: bool = True) -> Tuple[str, str]:
    """
        Runs a shell command and returns the stdout and stderr

        Args:
            cmd_str: The shell command to run
            to_log: Whether to log the command or not (to globally defined rad_gen_log_fd or stdout)
        
        Returns:
            A tuple containing the stdout and stderr of the command
        
        Todo:
            * Rename this function to reflect is usage as the general bash shell cmd wrapper function
            * Ensure that the shell=True is necessary as its a security vulnerability

    """
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

def run_shell_cmd_safe_no_logs(cmd_str: str) -> int:
    """
        Runs a shell command and returns the return code

        Args:
            cmd_str: The shell command to run
        
        Returns:
            The return code of the command (equivalent to echo $? in shell)

        Todo:
            * Ensure that the shell=True is necessary as its a security vulnerability
    """
    print(f"Running: {cmd_str}")
    ret_code = sp.call(cmd_str, executable='/bin/bash', env=cur_env, shell=True)
    return ret_code


def run_csh_cmd(cmd_str: str) -> None:
    """
        Runs a tcsh/csh command

        Args:
            cmd_str: The tcsh/csh command to run
    """
    rad_gen_log(f"Running: {cmd_str}", rad_gen_log_fd)
    sp.call(['csh', '-c', cmd_str])

    

def rec_get_flist_of_ext(design_dir_path: str, hdl_exts: List[str]) -> tuple[List[str], ...]:
    """
        Takes in a path and recursively searches for all files of specified extension
        returns dirs of those files and file paths in two lists
        
        Examples:
            >>> rec_get_flist_of_ext("designs/asic", [".v",".sv"])
            (
                ["designs/asic/rtl/top.v","designs/asic/sim/tb.sv"],
                ["designs/asic/rtl","designs/asic/sim"],
            )
        
        Args:
            design_dir_path: The path to the directory to search
            hdl_exts: The list of file extensions to search for

        Returns:
            A tuple containing the list of file paths and the list of directories containing those files
        
            
    """
    design_folder = os.path.expanduser(design_dir_path)
    design_files = [os.path.abspath(os.path.join(r,fn)) for r, _, fs in os.walk(design_folder) for fn in fs if fn.endswith(tuple(hdl_exts))]
    design_dirs = [os.path.abspath(r) for r, _, fs in os.walk(design_folder) for fn in fs if fn.endswith(tuple(hdl_exts))]
    design_dirs = list(dict.fromkeys(design_dirs))

    return design_files, design_dirs

def file_write_ln(fd: io.TextIOBase, line: str) -> None:
    """
        Convience wrapper fn that writes a line to a file with newline after

        Args:
            fd: The file descriptor to write to
            line: The line to write
        
    """
    fd.write(line + "\n")


# TODO deletion candidate as its not used
def edit_yml_config_file(config_fpath: str, config_dict: dict):
    """
        Super useful function which I have needed in multiple tools, 
        take in a dict of key value pairs and replace them in a config file,
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

# TODO deletion candidate as its not used
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
    """
        From an input dataframe returns a list of strings that can be printed to the console in a human readable table format.
        The sizing of columns is adjusted automatically based on size of max string in col

        Args:
            df: The dataframe to output
        
        Returns:
            A list of strings of the dataframe in human readable format
    """
    max_col_lens = max([len(str(col)) for col in df.columns])
    row_strings = [0]
    for col in df.columns:
        for row_idx in df.index:
            if isinstance(df[col].iloc[row_idx], str):
                row_strings.append(len(df[col].iloc[row_idx]))
    
    cell_chars = max(max_col_lens, max(row_strings) )
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

# TODO deletion candidate as its not used
def find_newest_file(search_dir: str, file_fmt: str, is_dir = True) -> str | None:
    """
        Finds newest file corresponding to current design in the specified search_dir path.
        The file_fmt string is used to determine what date time & naming convension we're using to compare
        If no files found, None will be returned signaling that one must be created

        Args:
            search_dir: The directory path to search in
            file_fmt: The datetime file format to use to determine the newest file
            is_dir: Whether to search for directories or files
        
        Returns:
            Path to the newest file or None if no files found

        Todo:
            * This function is a superset of 'find_newest_obj_dir' so we could maybe replace that one with this
            * Use linux utilities to find the newest file in expected format (Ex. ls -t | head -n 1) instead of date time parsing
    """

    # dir were looking for obj dirs in
    #search_dir = os.path.join(rad_gen_settings.env_settings.design_output_path, rad_gen_settings.common_asic_flow.top_lvl_module)

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

def find_newest_obj_dir(search_dir: str, obj_dir_fmt: str) -> str | None:
    """
        Finds newest object directory corresponding to current design in the specified RAD-Gen output directory.
        The obj_dir_fmt string is used to determine what date time & naming convension we're using to compare
        If no obj dirs found, None will be returned signaling that one must be created

        Args:
            search_dir: The directory path to search in
            obj_dir_fmt: The datetime file format to use to determine the newest file
        
        Returns:
            Path to the newest file or None if no files found
    """

    # dir were looking for obj dirs in
    #search_dir = os.path.join(rad_gen_settings.env_settings.design_output_path, rad_gen_settings.common_asic_flow.top_lvl_module)

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

def check_for_valid_path(path: str) -> bool:
    """
        Takes in path and determines if it exists

        Args:
            path: The path to check for existence

        Returns:
            True if path exists, False otherwise
        
        Raises:
            FileNotFoundError: If the path does not exist
    """
    ret_val = False
    if os.path.exists(os.path.abspath(path)):
        ret_val = True
    else:
        raise FileNotFoundError(f"ERROR: {path} does not exist")
    return ret_val

def handle_error(fn: Callable, expected_vals: set = None) -> None:
    """
        Handles error for a function, runs function without args and checks if return value is in expected_vals

        Args:
            fn: The function to run
            expected_vals: The set of expected return values
        
        Raises:
            SystemExit: If the function returns False or a value not in expected_vals
    """
    # for fn in funcs:
    if not fn() or (expected_vals is not None and fn() not in expected_vals):
        sys.exit(1)


def clean_path(unsafe_path: str, validate_path: bool = True) -> str:
    """
        Takes in possibly unsafe path and returns a sanitized path

        Args:
            unsafe_path: The path to sanitize
            validate_path: Whether to validate the path or not
        
        Raises:
            FileNotFoundError: If the path does not exist

        Returns:
            The sanitized path
    """
    safe_path = os.path.expanduser(unsafe_path)
    # We want to turn off the path checker when loading in yaml files which may have invalid entries
    if validate_path:
        handle_error(lambda: check_for_valid_path(safe_path), {True : None})
    return safe_path

def traverse_nested_dict(in_dict: Dict[str, Any], callable_fn: Callable, *args, **kwargs) -> Dict[str, Any]:
    """
        Traverses a nested or un nested dict in depthwise fashion and applies a callable function to each element

        Args:
            in_dict: The dictionary to traverse
            callable_fn: The function to apply to each dict value
            *args: Additional arguments to pass to the callable function
            **kwargs: Additional keyword arguments to pass to the callable function
        
        Returns:
            The input dictionary modified by the callable function applied to each element

        Todo:
            * Currently modifies and returns input dict, in the future should probably just do one or the other
        
    """
    assert callable(callable_fn), "callable_fn must be a function"
    # iterate across dict
    for k,v in in_dict.items():
        # If we find a dict, just pass it to the function again
        if isinstance(v, dict):
            in_dict[k] = traverse_nested_dict(v, callable_fn, *args, **kwargs)
        # If this is a list of dict elements, we traverse it and pass each dict to the callable function
        elif isinstance(v, list) and any(isinstance(ele, dict) for ele in v):
                in_dict[k] = []
                for ele in v:
                    if isinstance(ele, dict):
                        # Pass to the traverse_nested_dict function again, adding the "parent_key" to the dict to give info to following function
                        in_dict[k].append(traverse_nested_dict(ele, callable_fn, *args, **dict(kwargs, parent_key=k) ))
                    else:
                        raise Exception("ERROR: Currently mixing dicts with non dicts in a list is not supported")
        else:
            # Callable function applies to each non dict element in nested dict
            in_dict[k] = callable_fn(k, v, *args, **kwargs)
    return in_dict

def sanitize_element(param: str, ele_val: Any, validate_paths: bool = True, *args, **kwargs) -> Any:
    """
        Takes in a key value pair of 'param' and 'ele_val' and returns a sanitized value depending on the options definied in this function.
        If any of the 'path_keys' are substrings to the param and none of the 'inv_path_keys' are substrings to the param
        then
            we assume that the value is a path and we should apply the path sanitization function on it
        fi 
        Other sanitization options could be put in this function to be applied to all configuration elements across coffe

        Args:
            param: The key of the dictionary element
            ele_val: The value of the dictionary element
            validate_paths: Whether to validate the path or not (check for existence)
            *args: Nothing (deletion candidate)
            **kwargs: if 'parent_key' in kwargs then we use it to see if we should return element value early rather than sanitize

        Returns:
            Either the sanitized element or the element value itself depending on options

        Todo:
            * Replace kwargs with parent_key argument, revise docs to make things more clear

    """
    # Here are the key matches which makes sanitizer think its a path
    # TODO there may be a better way to do but this way you just have to list all path related keys below
    path_keys = ["path", "sram_parameters", "file", "home"] # "dir" TODO check if removal breaks things
    # Even if path keys are in param if negative keys are in param then its not a path
    #   E.g. negative keys override positive keys 
    inv_path_keys = [
        "meta", "use_latest_obj_dir", "manual_obj_dir", 
        # Custom flow params
        "read_saif_file",
        "generate_activity_file",
    ]
    
    # Special list for lists of dicts, we want to ignore any element with this key in the parent dict
    parent_inv_path_keys = ["placement_constraints"]
    # We check if the supplied inv path keys exist in our parent key as its expected to be heirarchical Ex.  "a.b.c"
    if "parent_key" in kwargs.keys() and any(parent_key in kwargs["parent_key"] for parent_key in parent_inv_path_keys):
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
            - Expand relative & home paths to absolute paths
        
        Args:
            config_dict: The configuration dictionary to sanitize
            validate_paths: Whether to validate the path or not
        
        Returns:
            The sanitized configuration dictionary
    """    

    return traverse_nested_dict(config_dict, sanitize_element, validate_paths)

def parse_config(conf_path: str, validate_paths: bool = True, sanitize: bool = True) -> dict:
    """
        Parses a yaml or json config file and returns a sanitized dictionary of its values.
        This is the main function used to parse input configuration files for all tools in RAD-Gen.

        Args:
            conf_path: The path to the configuration file
            validate_paths: Whether to validate the path or not
            sanitize: Whether to sanitize the configuration or not
        
        Returns:
            A dictionary from the config fpath that could be sanitized and validated depending on options
        
        Raises:
            ValueError: If the conf fpath does not end in .yml | .yaml | .json
    """
    is_yaml = None
    if conf_path.endswith(".yaml") or conf_path.endswith(".yml"):
        is_yaml = True
    elif conf_path.endswith(".json"):
        is_yaml = False
    else:
        raise ValueError(f"ERROR: config file {conf_path} is not a yaml or json file")
    # In case the path of config itself is a userpath we expand it
    in_conf_fpath: str = os.path.expanduser(conf_path)
    # Because configurations contain env_vars for paths we need to expand them with whats in users env
    conf_text = Path(in_conf_fpath).read_text().replace("${RAD_GEN_HOME}", os.getenv("RAD_GEN_HOME"))
    loaded_config = load_config_from_string(conf_text, is_yaml=is_yaml, path=str(Path(in_conf_fpath).resolve().parent))
    if sanitize:
        conf_dict = sanitize_config( 
            loaded_config,
            validate_paths)
    else:
        conf_dict = loaded_config
        
    return conf_dict

def parse_json(json_fpath: str) -> dict:
    """
        For when parse_config function fails. 
        Only used for the hammer sram parameters json files as its wrapped in a list not a dict

        Args:
            json_fpath: The path to the json file
        
        Returns:
            The json file as a dictionary

    """
    in_json_fpath: str = clean_path(json_fpath)
    conf_text: str = Path(in_json_fpath).read_text().replace("${RAD_GEN_HOME}", os.getenv("RAD_GEN_HOME"))
    out_conf = json.loads(conf_text)

    return out_conf

# TODO depricate this function and use parse_config
def parse_yml_config(yaml_file: str, validate_paths: bool = True) -> dict:
    """
        Takes in possibly unsafe path and returns a sanitized config
    """
    safe_yaml_file = clean_path(yaml_file)
    with open(safe_yaml_file, 'r') as f:
        config = yaml.safe_load(f)
    
    return sanitize_config(config, validate_paths)

def find_common_root_dir(dpaths: List[str]) -> None | str:
    """
        Finds the common root of a list of unsorted directories and makes sure they all exist in it and the common root was provided in the list

        Args:
            dpaths: The list of directories to find the common root of
        
        Returns:
            The common root directory if it exists and is in the list, None otherwise
    """

    common_root = os.path.commonpath(dpaths)
    # Check if all other paths are inside the upper most path (index 0)
    # If its not true then we return None to show that there is no common root dir in dpath list
    ret_val = None
    if all(os.path.relpath(path, common_root).startswith('..') is False for path in dpaths):
        if any(common_root == dpath for dpath in dpaths):
            ret_val = common_root
    return ret_val




def init_field(
    in_config: dict,
    field: dataclasses.Field,
    field_type: Type,
    validate: bool,
) -> dict:
    field_name: str = field.name
    dataclass_inputs: dict = {}
    hier_dict = {k: v for k, v in in_config.items() if k.startswith(f"{field_name}{rg_ds.CLI_HIER_KEY}")}
    if field_name in in_config or hier_dict:
        # Another path for a hierarchical dataclass definition is a list of dictionaries (which will not be flattened)
        # This condition should be mutually exclusive with being a heirarchical key (as lists are not flattened)
        if typing.get_origin(field_type) == list and in_config.get(field_name) and all(isinstance(i, dict) for i in in_config[field_name]):
            # We should assert that all fields in the dataclass list are of the same type
            assert len(set(typing.get_args(field_type))) == 1
            # Field is a list of dictionaries
            element_type = typing.get_args(field_type)[0] # Get the type of elements in the list
            dataclass_inputs[field_name] = [
                init_dataclass(
                    dataclass_type = element_type, 
                    in_config = item, 
                    add_arg_config = {}, 
                    # module_lib = module_lib, 
                    validate_paths = validate
                ) for item in in_config[field_name]
            ]
        elif field_name in in_config:
            dataclass_inputs[field_name] = in_config[field_name]
        else:
            # Get a in config dict for the nested dataclass
            nested_config: dict = strip_hier(in_config, field_name)
            default_fac_config: dict
            if field.default_factory != MISSING:
                default_fac_config = dataclasses.asdict(field.default_factory())
            else:
                default_fac_config = {}

            ## Initialize the nested dataclass
            dataclass_inputs[field_name] = init_dataclass(
                dataclass_type = field_type, 
                in_config = nested_config, 
                add_arg_config = default_fac_config, 
                # module_lib = module_lib, 
                validate_paths = validate
            )
    return dataclass_inputs

def init_dataclass(
    dataclass_type: Type, 
    in_config: dict, 
    add_arg_config: dict = {}, 
    module_lib: Any = None, 
    validate_paths: bool = True
) -> Any:
    """
    Initializes a dataclass with values from the dataclasses internal initialization functions and input configuration dictionaries
    which have key value pairs mapped to dataclass fields. 
    Additionally performs path sanitization
    
    Extremely useful function as it allows for defined priority to merge args coming from different sources at different levels of priority
    
    There is a priority by which the dataclass is initialized (highest to lowest):
        1. in_config
        2. add_arg_config
        3. default_factory

    Args:
        dataclass_type: The dataclass type which is to be initialized
        in_config: The input configuration dictionary which contains the values for the dataclass fields
        add_arg_config: Additional argument configuration dictionary which contains values for the dataclass fields
            which may or may not be defined in the input configuration
        module_lib: The module library which contains the dataclass (and subdataclasses if any) in the dataclass_type.
            This is used to recursively initialize the dataclass and its subdataclasses so a precondition is that dataclasses 
            and thier subdataclasses are in the same python module. 
        hier_to_dicts: A boolean flag which determines if hierarchical keys in the input config dict should be converted to dictionaries
        validate_paths: A boolean flag which determines if paths in the dataclass should be validated to exist on the system

    Returns:
        dataclass instantiation with values from merge of data sources in priority order

    Raises:
        Exception: If a nested dataclass is found and the module_lib argument is not provided
    
    Todo:
        * should add sanitization for all required fields in this function
        * replace __dataclass_fields__ with fields() and make sure it gets same result
    """
    # For when a nested dataclass has an element of type `dict` we just return the input config
    dataclass_inputs = {}
    if not hasattr(dataclass_type, "__dataclass_fields__"):
        return in_config
    type_hints: Dict[str, Type[Any]] = typing.get_type_hints(dataclass_type)
    field: dataclasses.Field
    for field in dataclass_type.__dataclass_fields__.values():
        field_name = field.name
        field_type = type_hints[field.name]
        # Start with the factory default if it exists, will be overrided if higher priority assignment exists
        if field.default_factory != MISSING:
            dataclass_inputs[field_name] = field.default_factory()

        # Hierarchical keys in the input config dict, (we merge two input dicts in priority order)
        # hier_keys = {k: v for k, v in {**add_arg_config, **in_config}.items() if k.startswith(f"{field_name}{rg_ds.CLI_HIER_KEY}")}
        # If we find the field name hierarchically defined in either of the input configs
        #   AND the Non-hier key is not defined in either of input configs
        # if hier_keys and (field_name not in in_config and field_name not in add_arg_config):
        #     if not module_lib:
        #         raise Exception("ERROR: module_lib must be provided if a nested dataclass is found")
        #     # Get a in config dict for the nested dataclass
        #     nested_config: dict = {k.replace(f"{field_name}{rg_ds.CLI_HIER_KEY}",""): v for k, v in hier_keys.items()}
        #     # Get the type from the input module lib
        #     nested_dataclass_type = getattr(module_lib, field.type)
        #     default_fac_config: dict
        #     if field.default_factory != MISSING:
        #         default_fac_config = dataclasses.asdict(field.default_factory())
        #     else:
        #         default_fac_config = {}

        #     ## Initialize the nested dataclass
        #     dataclass_inputs[field_name] = init_dataclass(
        #         dataclass_type = nested_dataclass_type, 
        #         in_config = nested_config, 
        #         add_arg_config = default_fac_config, 
        #         module_lib = module_lib, 
        #         validate_paths = validate_paths
        #     )


        init_dict: dict = init_field(
            in_config, 
            field, 
            field_type, 
            validate_paths
        )
        # If the init dict is empty then there was no initialization done so we try again with the add_arg_config
        if not init_dict:
            init_dict = init_field(
                add_arg_config, 
                field, 
                field_type, 
                validate_paths
            )
        if init_dict.get(field_name):
            dataclass_inputs[field_name] = init_dict[field_name]

        # hier_keys_in_config = {k: v for k, v in in_config.items() if k.startswith(f"{field_name}{rg_ds.CLI_HIER_KEY}")}
        # if field_name in in_config or hier_keys_in_config:
        #     # Another path for a hierarchical dataclass definition is a list of dictionaries (which will not be flattened)
        #     # This condition should be mutually exclusive with being a heirarchical key (as lists are not flattened)
        #     if typing.get_origin(field_type) == list and in_config.get(field_name) and all(isinstance(i, dict) for i in in_config[field_name]):
        #         # We should assert that all fields in the dataclass list are of the same type
        #         assert len(set(typing.get_args(field_type))) == 1
        #         # Field is a list of dictionaries
        #         element_type = typing.get_args(field_type)[0] # Get the type of elements in the list
        #         dataclass_inputs[field_name] = [
        #             init_dataclass(
        #                 dataclass_type = element_type, 
        #                 in_config = item, 
        #                 add_arg_config = {}, 
        #                 module_lib = module_lib, 
        #                 validate_paths = validate_paths
        #             ) for item in in_config[field_name]
        #         ]
        #     elif field_name in in_config:
        #         dataclass_inputs[field_name] = in_config[field_name]
        #     else:
        #         # Get a in config dict for the nested dataclass
        #         nested_config: dict = strip_hier(in_config, field_name)
        #         default_fac_config: dict
        #         if field.default_factory != MISSING:
        #             default_fac_config = dataclasses.asdict(field.default_factory())
        #         else:
        #             default_fac_config = {}

        #         ## Initialize the nested dataclass
        #         dataclass_inputs[field_name] = init_dataclass(
        #             dataclass_type = field_type, 
        #             in_config = nested_config, 
        #             add_arg_config = default_fac_config, 
        #             module_lib = module_lib, 
        #             validate_paths = validate_paths
        #         )

        # elif field_name in add_arg_config:
        #     dataclass_inputs[field_name] = add_arg_config[field_name]
        
        # Clean path and ensure it exists (if "path" keyword in field name)
        if "path" in field_name and field_name in dataclass_inputs:
            if isinstance(dataclass_inputs[field_name], list):
                for idx, path in enumerate(dataclass_inputs[field_name]):
                    dataclass_inputs[field_name][idx] = clean_path(path, validate_paths)
            elif isinstance(dataclass_inputs[field_name], str):
                dataclass_inputs[field_name] = clean_path(dataclass_inputs[field_name], validate_paths)
            else:
                pass

    # Return created dataclass instance
    return dataclass_type(**dataclass_inputs)

def convert_namespace(in_namespace: argparse.Namespace) -> List[str] | None:
    """
        Converts a namespace to an arg list of cli strings (space seperated)
        This is used for being able to run rad_gen properly either from the command line or from a python script
        
        Args:
            in_namespace: The input namespace to convert
        
        Returns:
            A list of cli arguments as strings
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

def parse_rad_gen_top_cli_args(in_args: argparse.Namespace = None) -> Tuple[argparse.Namespace, Dict[str, Any]]:
    """ 
        Parses the top level RAD-Gen args

        Examples:
            # Below args should be valid for rad_gen but for this example they are generic
            >>> args: argparse.Namespace = (arg1 = "val1", arg2 = "val2", ...)
            OR
            >>> args = None
            >>> args, default_arg_vals = parse_rad_gen_top_cli_args(args)

        Args:
            in_args: The input namespace to parse (if None then args are taken from sys.argv[1:])
        
        Returns:
            The parsed namespace and the default argument values
    """                     
    # converting namespace to list of cli arguments if we get namespace
    assert isinstance(in_args, argparse.Namespace) or in_args == None, "ERROR: in_args must be a argparse.Namespace object or None"
    arg_list = convert_namespace(in_args) #if isinstance(in_args, argparse.Namespace) else in_args

    parser = argparse.ArgumentParser(description="RAD-Gen top level CLI args")

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
    
    if in_args == None and arg_list == None:
        parsed_args, remaining_args = parser.parse_known_args()
    else:
        parsed_args, remaining_args = parser.parse_known_args(args = arg_list, namespace = in_args)

    # Raise error if no subtool is specified
    if parsed_args.subtools is None:
        raise ValueError("No subtool specified, please specify a subtool to run, possible subtools are: 'coffe', 'asic-dse', '3d-ic'")

    #     _   ___ ___ ___   ___  ___ ___     _   ___  ___ ___ 
    #    /_\ / __|_ _/ __| |   \/ __| __|   /_\ | _ \/ __/ __|
    #   / _ \\__ \| | (__  | |) \__ \ _|   / _ \|   / (_ \__ \
    #  /_/ \_\___/___\___| |___/|___/___| /_/ \_\_|_\\___|___/

    #arguments for ASIC flow TODO integrate some of these into the asic_dse tool, functionality already exists just needs to be connected
    # parser.add_argument('-ho',"--hardblock_only",help="run only a single hardblock through the asic flow", action='store_true',default=False)
    # parser.add_argument('-g',"--gen_hb_scripts",help="generates all hardblock scripts which can be run by a user",action='store_true',default=False)
    # parser.add_argument('-p',"--parallel_hb_flow",help="runs the hardblock flow for current parameter selection in a parallel fashion",action='store_true',default=False)
    # parser.add_argument('-r',"--parse_pll_hb_flow",help="parses the hardblock flow from previously generated results",action='store_true',default=False)
    if "asic_dse" in parsed_args.subtools:
        # Adding ASIC DSE CLI args
        asic_dse_cli = rg_ds.AsicDseCLI()
        default_arg_vals = {
            **default_arg_vals,
            **asic_dse_cli._defaults,
        }
        for cli_arg in asic_dse_cli.cli_args:
            rg_ds.add_arg(parser, cli_arg)

        
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

    if in_args == None and arg_list == None:
        args = parser.parse_args()
    else:
        args = parser.parse_args(args = arg_list, namespace = in_args)
        
    # Default value dictionary for any arg that has a non None or False for default value
    # default_arg_vals = {**asic_dse_cli._defaults, **coffe_cli._defaults, **ic_3d_cli._defaults, **common_cli._defaults}
    # { k: v for k, v in vars(args).items() if v != None and v != False}

    return args, default_arg_vals

def max_depth(d: dict) -> int:
    """
        returns the level of nesting of a particular dict

        Args:
            d: The dictionary to find the max depth of
        
        Returns:
            The max depth of the dictionary
    """
    if isinstance(d, dict):
        return 1 + max((max_depth(value) for value in d.values()), default=0)
    else:
        return 0

def merge_cli_and_config_args(
    cli: Dict[str, Any],
    config: Dict[str, Any],
    default: Dict[str, Any],
) -> Dict[str, Any]:
    """
        Merges the cli and config args into a single dictionary
        This is used to take a top_level config file which is capable of describing all RAD-Gen functionality and merge it with cli defined options.
        That usage allows for users to have a large complex config file and be able to override some of the params with cli defined arguments (for convience)

        Args:
            cli: RAD-Gen args coming from CLI
            config: RAD-Gen args coming from top level conf file
            default: RAD-Gen args coming from the initialized default values (valid for any or no particular mode of operation)
        
        Returns:
            A dict of arguments merged in order of priority (cli > config > default)

        Todo:
            * Verify the functionality of this for edge cases of CLI / Config values
    """

    result_conf = {}
    if config == None:
        result_conf = copy.deepcopy(cli)
    elif cli == None:
        result_conf = copy.deepcopy(config)
    else:
        # The merging will only work if they are not nested dicts
        assert max_depth(cli) == 1 and max_depth(config) == 1, "ERROR: Merging only works for non nested dictionaries"
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
            
    return result_conf

def strip_hier(
    in_dict: Dict[str, Any], 
    strip_tag: str, 
    only_tagged_keys: bool = True
) -> Dict[str, Any]:
    """
        Removes heirarchy with <strip_tag> from keys in a dictionary

        Args:
            in_dict: The input dictionary to strip
            strip_tag: Which tag to remove from dict keys
            only_tagged_keys: Determines if keys without the strip tag will be put into the output dict
    
        Returns:
            The dictionary with the heirarchy removed from the keys
    """
    strip_tag_re = re.compile(f"^{strip_tag}\\.", re.MULTILINE)
    out_dict = {}
    for k, v in in_dict.items():
        # If the strip tag with a dot suffix is in the key
        if strip_tag_re.search(k):
            out_dict[strip_tag_re.sub("", k)] = v
        elif not only_tagged_keys:
            out_dict[k] = v
    return out_dict


def modify_param_dict_keys_for_hier(in_dict: Dict[str, Any], subtool: str) -> Dict[str, Any]:
    """
        Takes in a dictionary and modifies its keys to add the subtool name to the hierarchy (and match a flattened input conf file)

        Args:
            in_dict: The input dictionary to modify
            subtool: The subtool name to add to the hierarchy

        Returns:
            The modified dictionary with the subtool name added to the hierarchy
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
    return in_dict



def init_structs_top(args: argparse.Namespace, default_arg_vals: Dict[str, Any]) -> Dict[str, rg_ds.AsicDSE | rg_ds.Coffe | rg_ds.Ic3d]:
    """
        Initializes the data structures for all RAD-Gen
        
        Examples:
            >>> args, default_arg_vals = parse_rad_gen_top_cli_args(args)
            >>> rad_gen_info = init_structs_top(args, default_arg_vals)

        Args:
            args: The parsed argparse namespace created by parse_rad_gen_top_cli_args() function
            default_arg_vals: The default values for all the arguments derived from cli options
        
        Returns:
            A dictionary containing data structures for a RAD-Gen subtool
            For example if the output is stored in `rad_gen_info` then `list(rad_gen_info.keys())` would be ["coffe", "ic_3d", "asic_dse"]

        Todo:
            * There are functions scattered across rad_gen which expect there to only be a single subtool for each invocation of rad_gen. 
                We should have this function return a single subtool's data structure rather than a dict of data structures.
    """

    top_conf = None
    if args.top_config_fpath is not None:
        top_conf = parse_config(args.top_config_fpath, validate_paths = False, sanitize = True)
    cli_dict = vars(args)
    # Convert the key names of cli_dict into heiarachical keys which will match the config file
    # This notation is confusing as it seems like we are saving everything into the same variable but actually we are modifying both cli_dict and default_arg_vals seperately
    for conv_dict in [cli_dict, default_arg_vals]:
        for subtool_str in "coffe", "asic_dse", "ic_3d", "common":
            conv_dict = modify_param_dict_keys_for_hier(conv_dict, subtool_str)
    
    # Below currently parses the cli args and will always take the cli arg value over whats in the config file (if cli arg == None)
    # If cli_arg == default_cli_value && key exists in the config file -> then tool will use the config file instead of cli 

    # Comparing two input param dicts one coming from cli and one from config file for each tool
    subtool_confs = {}
    for subtool in cli_dict["common.subtools"]:
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

        subtool_confs[subtool] = {
            **result_conf,
        }
        
    # Before this function make sure all of the parameters have been defined in the dict with default values if not specified
    rad_gen_info = {}

    # Loop through subtool keys and call init function to return data structures
    # init functions are in the form init_<subtool>_structs
    for subtool in list(subtool_confs.keys()):
        fn_to_call = getattr(sys.modules[__name__], f"init_{subtool}_structs")
        if callable(fn_to_call):
            # do the renaming of keys to take out the "<subtool>." portion of heirarchy, this is because by definition all keys that are passed in are only for the respective subtool
            # (subtools are independant of one another), and the common dataclass is passed through the "common" key
            rad_gen_info[subtool] = fn_to_call( {k.replace(f"{subtool}.","") : v for k,v in subtool_confs[subtool].items()}, common ) 

            # Common assertions required for all subtools
            assert os.path.exists(rad_gen_info[subtool].common.obj_dir)
            
        else:
            raise ValueError(f"ERROR: {subtool} is not a valid subtool ('init_{subtool}_structs' is not a defined function)")
    return rad_gen_info
    

def init_hammer_config(conf_tree: rg_ds.Tree, conf_path: str) -> str:
    """
        This function is specifically to clean up the configs passed to hammer
        prior to initialization of the HammerFlow data structure.
        Hammer only accepts absolute paths so we need to convert our paths with home dir '~' to abspaths
        
        Args:
            conf_tree: The tree structure of the relevant 'configs' directory which we will use to search for other dpaths
            conf_path: Path to the configuration file that requires sanitization
        
        Returns:
            conf_out_fpath: The path to the new sanitized config file, capable of being passed into hammer
    """
    conf_fname = os.path.basename(os.path.splitext(conf_path)[0])
    conf_dict = parse_config(conf_path, validate_paths = False, sanitize = True)
    # only searching for the mod directory inside of the designs config tree ie this is ok
    mod_confs_dpath = conf_tree.search_subtrees("mod")[0].path
    conf_out_fpath = os.path.join(mod_confs_dpath, conf_fname + "_pre_procd.json")
    dump_config_to_json_file(conf_out_fpath, conf_dict)
    
    return conf_out_fpath

def init_common_structs(common_conf: Dict[str, Any]) -> rg_ds.Common:
    """
        Initializes the data structure common to all modes of RAD-Gen and stored within each subtool data structure

        Creates a project tree which can be used for downstream subtools.
        The idea of project tree dir structure is that we copy all the relevant files (yuck) into the project dir so we can access them easily
        This allows for the user to specify files which may be located across many different places and through a defined structure condense them to a single location
            * It should check to make sure the files are not already in the project directory before copying them
            * Ideally the project tree should be a workspace that can be used for development of RTL or other stuff and that way there isnt a ton of copying
            * Symbolic links should be used when possible to also reduce copying of files
        
        Args:
            common_conf: A dictionary that should contain keys mapped 1:1 to `rg_ds.Common` data structure fields

        Returns:
            The initialized `rg_ds.Common` data structure 

        Todo:
            * Implement + Integrate the PDK tree with the rest of the flow

    """
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

    # TODO connect log_fpath to the common dataclass logger
    common_inputs["log_fpath"] = os.path.join(rad_gen_home, "logs", "rad_gen.log")
    # For now on our output path fields we need to manually generate the directories and files specified
    # This ensures that our function to check for valid paths will not fail
    # TODO have the <_>Args dynamic dataclass have fields for each argument which specifies relevant information
    
    for out_path_key in ["log_fpath"]:
        os.makedirs(os.path.dirname(common_inputs[out_path_key]), exist_ok = True)
        # write to log to create empty file and not piss off the path checker
        fd = open(common_inputs[out_path_key], "w")
        fd.close()

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
                    
                        # The idea for this section is that PDK come in many forms with different structures but most of the time we need a few specific files depending on what we're doing
                        # So for each new PDK, a user will have to manually parse the directory structure and copy the files into this directory.

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
                    ],
                ),
                rg_ds.Tree("third_party", 
                    [  
                        rg_ds.Tree("hammer", scan_dir = True, tag = "hammer"),
                        rg_ds.Tree("pdks", scan_dir = True, tag = "pdks"),
                    ],
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
                    ],
                ),
            ],
            tag = "top"
        )

    common_inputs["project_tree"].update_tree()
    common = init_dataclass(rg_ds.Common, common_inputs)
    return common

def init_asic_obj_dir(
        common: rg_ds.Common,
        out_tree: rg_ds.Tree = None,
        top_lvl_module: str = None,
        sweep_flag: bool = False,
        sram_gen_flag: bool = False,
) -> str:
    """
        Initializes and creates the asic output obj dpath based on options specified in `common` and `top_lvl_module`
        Args:
            common: The common data structure
            top_lvl_module: The top level module name
        
        Returns:
            Path to the newly created obj directory
    """
    # Create output directory for obj dirs to be created inside
    if not out_tree and top_lvl_module:
        out_tree: rg_ds.Tree = common.project_tree.search_subtrees(f"outputs.{top_lvl_module}.obj_dirs", is_hier_tag = True)[0]
    
    out_dir = out_tree.path
    assert os.path.isdir(out_tree.path), f"ERROR: {out_tree.path} is not a valid directory"
    if sweep_flag:    
        obj_base_dname = f"{top_lvl_module}-sweep-{rg_ds.create_timestamp()}"
        obj_dir_fmt = f"{top_lvl_module}-sweep-{rg_ds.create_timestamp(fmt_only_flag = True)}"
    elif sram_gen_flag:
        obj_base_dname =f"sram_gen-{rg_ds.create_timestamp()}"
        obj_dir_fmt = f"sram_gen-{rg_ds.create_timestamp(fmt_only_flag = True)}"
    else:
        obj_base_dname = f"{top_lvl_module}-{rg_ds.create_timestamp()}" # Still putting top level mod naming convension on obj_dirs because who knows where they will end up
        obj_dir_fmt = f"{top_lvl_module}-{rg_ds.create_timestamp(fmt_only_flag = True)}"
        
    # Throw error if both obj_dir options are specified
    assert not (common.override_outputs and common.manual_obj_dir != None), "ERROR: cannot use both latest obj dir and manual obj dir arguments for ASIC-DSE subtool"
    
    obj_dir_path = None
    # Users can specify a specific obj directory
    if common.manual_obj_dir != None:
        obj_dir_path = os.path.abspath(os.path.expanduser(common.manual_obj_dir))
        # if this does not exist create it now
        os.makedirs(obj_dir_path, exist_ok = True)
    # Or they can use the latest created obj dir
    elif common.override_outputs:
        if os.path.isdir(out_dir):
            obj_dir_path = find_newest_obj_dir(search_dir = out_dir, obj_dir_fmt = obj_dir_fmt)
        else:
            print( f"WARNING: No latest obj dirs found in {out_dir} of format {obj_dir_fmt}")
    # If no value given or no obj dir found, we will create a new one
    if obj_dir_path == None:
        obj_dir_path = os.path.join(out_dir, obj_base_dname)
        print( f"WARNING: No obj dir specified or found, creating new one @: {obj_dir_path}")

    # This could be either at the same path as next variable or at manual specified location
    obj_dname = os.path.basename(obj_dir_path)
    # This will always be at consistent project path
    project_obj_dpath = os.path.join(out_dir, obj_dname)
    
    if common.manual_obj_dir:
        # Check to see if symlink already points to the correct location
        if os.path.islink(project_obj_dpath) and os.readlink(project_obj_dpath) == obj_dir_path:
            rad_gen_log(f"Symlink already exists @ {project_obj_dpath}", rad_gen_log_fd)
        else:
            os.symlink(obj_dir_path, project_obj_dpath)
    # If we don't specify a manual obj directory we can directly append our new obj directory to the project tree to create it + add to data structure
    # Won't create it if symlink already exists
    obj_tree = rg_ds.Tree(
        path = os.path.basename(obj_dir_path),
        subtrees = [
            rg_ds.Tree("reports", tag="report"), # Reports specific to each obj dir (each asic flow run)
        ],
        tag = "cur_obj_dir" # NAMING CONVENTION FOR OUR ACTIVE OBJ DIRECTORY
    )
    common.project_tree.append_tagged_subtree(
        # f"{common.project_name}.outputs.{top_lvl_module}.obj_dirs",
        out_tree.heir_tag, 
        obj_tree,
        is_hier_tag = True,
        mkdirs = True,
    )
    return obj_dir_path


def get_hammer_flow_conf(common: rg_ds.Common, flow_stages: rg_ds.FlowStages, asic_dse_conf: dict) -> dict:
    """
        Modifies and creates new config files in 'flow_conf_fpaths' and 'tool_env_conf_fpaths' 
        Then updates the `asic_dse_conf` keys to reflect new modified fpaths

        Args:
            common: Initialized common  
            flow_stages: Initialized flow_stages 
            asic_dse_conf: Dictionary representing merged config args from CLI / config file / defaults
        
        Returns:
            The modified `asic_dse_conf` dictionary with updated fpaths
    """
    # If we are in SRAM compiler mode, this means we are only running srams through the flow and thier configs should be at below path
    proj_conf_tree: rg_ds.Tree
    if flow_stages.sram.run:
        proj_conf_tree = common.project_tree.search_subtrees("shared_resources.sram_lib.configs", is_hier_tag = True)[0] 
    else:
        # search for conf tree below in our project_name dir
        proj_conf_tree = common.project_tree.search_subtrees(f"{common.project_name}.configs", is_hier_tag = True)[0] 
    # Before parsing asic flow config we should run them through pre processing to all input files
    for idx, conf_path in enumerate(asic_dse_conf["flow_conf_fpaths"]):
        asic_dse_conf["flow_conf_fpaths"][idx] = init_hammer_config(proj_conf_tree, conf_path)
    # Search for the shared conf tree in the project tree
    shared_conf_tree = common.project_tree.search_subtrees("shared_resources.configs.asic_dse", is_hier_tag = True)[0]
    # Pre process & validate env config path
    for idx, conf_path in enumerate(asic_dse_conf["tool_env_conf_fpaths"]):
        asic_dse_conf["tool_env_conf_fpaths"][idx] = init_hammer_config(shared_conf_tree, conf_path)
    
    return asic_dse_conf


def init_asic_dse_structs(asic_dse_conf: Dict[str, Any], common: rg_ds.Common) -> rg_ds.AsicDSE:
    """
        Initializes the AsicDSE data structure to be used for the asic_dse subtool. 

        Args:
            asic_dse_conf: The dictionary containing all the ASIC-DSE configurations
            common: Initialized data structure common to all subtools in RAD-Gen

        Returns:
            Initialized AsicDSE data structure which can be used to legally execute any mode of operation in the asic_dse subtool.
    
        Todo:
            * Get each `init` function for dataclasses to output a list of strings of all the fields that were set by inputs derived from `init` args or dataclass `self` values.
                * Then use this list of stings to ensure that no non `None` set fields are being overridden by the `init` function 
                    Or just print out a warning message that says they are being overridden.
            * For all combinations of data structure values that are not valid, throw an error.
                * Validation can be done after the final `AsicDSE` data structure is created to not get too confused by the 
                    intermediate states that some data structure values can have during the course of `init_asic_dse_structs` function.
    """
    
    design_out_tree = rg_ds.Tree("top_lvl_module",
        [
            # Obj directories exist here
            rg_ds.Tree("obj_dirs", tag="obj_dirs"),
            # Below Trees are a place to put high level reports / logs / scripts (by high level I mean not specific to a single obj dir)
            rg_ds.Tree("reports", tag="report"),
            rg_ds.Tree("scripts", tag="script"),
            rg_ds.Tree("logs", tag="logs"),
        ], tag="top_lvl_module"
    )
    
    configs_tree = rg_ds.Tree("configs", 
        [
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
            rg_ds.Tree("obj_dirs")
        ]
    )

    # Make tree defined directories
    common.project_tree.create_tree()

    # updating project tree from common
    if common.project_name != None:
        # This would happen in the case of running in the rtl generation mode (i.e. sram compiler), as there isn't a single top lvl module name to use
        common.project_tree.append_tagged_subtree(f"{common.project_name}", copy.deepcopy(configs_tree), is_hier_tag = True) # append asic_dse specific conf tree to the project conf tree
        common.project_tree.append_tagged_subtree(f"{common.project_name}", rtl_tree, is_hier_tag = True) # add rtl to the project tree
    conf_tree_copy = copy.deepcopy(configs_tree)
    conf_tree_copy.update_tree_top_path(new_path = "asic_dse", new_tag = "asic_dse")
    common.project_tree.append_tagged_subtree("shared_resources.configs", conf_tree_copy, is_hier_tag = True) # append our shared configs tree to the project tree
    common.project_tree.append_tagged_subtree(f"shared_resources", copy.deepcopy(sram_tree), is_hier_tag = True) # append our pdk tree to the project tree

    # Init meathod from heirarchical cli / configs to dataclasses
    stdcell_lib: rg_ds.StdCellLib = init_dataclass(
        rg_ds.StdCellLib, 
        strip_hier(asic_dse_conf, strip_tag="stdcell_lib")
    )
    stdcell_lib.init(common.project_tree)

    sram_compiler: rg_ds.SRAMCompilerSettings = init_dataclass(
        rg_ds.SRAMCompilerSettings, 
        strip_hier(asic_dse_conf, strip_tag="sram_compiler_settings")
    )
    sram_compiler.init(common.project_tree)

    scripts: rg_ds.ScriptInfo = init_dataclass(
        rg_ds.ScriptInfo, 
        strip_hier(asic_dse_conf, strip_tag="scripts")
    )
    compile_results_flag: bool = asic_dse_conf["compile_results"] # CTRL SIGNAL
    
    common_asic_flow: rg_ds.CommonAsicFlow = init_dataclass(
        rg_ds.CommonAsicFlow, 
        {
            **strip_hier(asic_dse_conf, strip_tag="common_asic_flow"),
            "top_lvl_module" : asic_dse_conf.get("top_lvl_module"),
            "hdl_dpath" : asic_dse_conf.get("hdl_dpath"),
        },
        module_lib = rg_ds,
    )
    common_asic_flow.init(stdcell_lib.pdk_name)
    common_asic_flow.flow_stages.init(compile_results_flag)
    
    # Control signals
    top_lvl_valid: bool = (
        common_asic_flow.top_lvl_module != None and 
        common_asic_flow.hdl_dpath != None
    )
    sweep_conf_valid: bool = asic_dse_conf["sweep_conf_fpath"] != None
    flow_conf_valid: bool = asic_dse_conf["flow_conf_fpaths"] != None


    asic_dse_mode: rg_ds.AsicDseMode = init_dataclass(
        rg_ds.AsicDseMode, 
        strip_hier(asic_dse_conf, strip_tag="mode"),
        module_lib = rg_ds, 
    )
    # Perform post init operations to set fields requiring external / internal dependancies
    asic_dse_mode.init(
        sweep_conf_valid,
        compile_results_flag,
    )
    asic_dse_mode.vlsi.init(
        sweep_conf_valid,
        flow_conf_valid,
        top_lvl_valid,
    )

    # Assert valid combinations
    # Cannot run both sweep and flow confs at the same time
    assert not (asic_dse_conf.get("sweep_conf_fpath") == None and asic_dse_conf.get("flow_conf_fpaths") == None), "ERROR: No task can be run from given user parameters"
    # If not using sram compiler (doesn't need a project dir) make sure user provides a project directory
    assert not (common.project_name == None and not common_asic_flow.flow_stages.sram.run and flow_conf_valid), "ERROR: Project name must be specified if not running SRAM compiler" 
        
    # assert not (common.project_name == None and not common_asic_flow.flow_stages.sram.run), "ERROR: Project name must be specified if not running SRAM compiler"

    asic_dse_inputs: dict = {} # asic dse parameters
    design_sweep_infos: List[rg_ds.DesignSweepInfo] = [] # List of sweeps to generate 
    custom_asic_flow_settings: dict = None # TODO get rid of this with updated custom flow init
    #   _____      _____ ___ ___    ___ ___ _  _ 
    #  / __\ \    / / __| __| _ \  / __| __| \| |
    #  \__ \\ \/\/ /| _|| _||  _/ | (_ | _|| .` |
    #  |___/ \_/\_/ |___|___|_|    \___|___|_|\_|

    if asic_dse_mode.sweep_gen:
        sweep_conf: dict = parse_config(
            asic_dse_conf.get("sweep_conf_fpath"), 
            validate_paths = True, 
            sanitize = True
        )
    else:
        sweep_conf = {}
    
    design_sweep_info: rg_ds.DesignSweepInfo = init_dataclass(
        rg_ds.DesignSweepInfo, 
        strip_hier(asic_dse_conf, strip_tag="design_sweep_info"),
        sweep_conf,
        module_lib = rg_ds,
    )
    # Only reason I'm passing this in rather than parsing from inside init function is to prevent circular import
    # TODO change this
    if asic_dse_mode.sweep_gen:
        base_config = parse_config(design_sweep_info.base_config_path, validate_paths=True, sanitize=True)
        design_sweep_info.init(
            base_config,
            common.project_tree,
        )
    if design_sweep_info.type == "rtl":
        # If doing RTL sweep we have to unflatten the portion of the config describing RTL params
        # TODO remove this + refactor and unify config file formats
        procd_params = [] 
        for rtl_param, sweep_vals in copy.deepcopy(design_sweep_info.rtl_params.sweep).items():
            top_hier_key = str(rtl_param).split(".")[0]
            if top_hier_key in procd_params:
                del design_sweep_info.rtl_params.sweep[rtl_param]
                continue
            # if hierarchy is found (param is a dict originally)
            if "." in rtl_param:
                design_sweep_info.rtl_params.sweep[top_hier_key] = strip_hier(design_sweep_info.rtl_params.sweep, top_hier_key)
                del design_sweep_info.rtl_params.sweep[rtl_param]
                procd_params.append(top_hier_key)
            
    # Logic to initialize project tree and copy over RTL files
    if design_sweep_info.type != "sram":
        if design_sweep_info.hdl_dpath:
            exts = ['.v','.sv','.vhd',".vhdl", ".vh", ".svh"]
            _, hdl_search_paths = rec_get_flist_of_ext(design_sweep_info.hdl_dpath, exts)
            if hdl_search_paths:
                # Is assumed sanitized by the parse_config (ie path exists)
                rtl_src_dpath = find_common_root_dir(hdl_search_paths)
                rtl_dst_tree: rg_ds.Tree = common.project_tree.search_subtrees(f"{common.project_name}.rtl.src", is_hier_tag = True)[0]
                rtl_dst_tree.scan_dir = True
                rtl_dst_dpath = rtl_dst_tree.path
                # Copy tree recursivley to project tree, just including all files assuming they will be part of the RTL we want, possibly could filter for specific files in the future
                shutil.copytree(rtl_src_dpath, rtl_dst_dpath, dirs_exist_ok=True)
                rtl_dst_tree.update_tree()
            else:
                # Our RTL is coming from the base config input_files
                rtl_dst_tree = common.project_tree.search_subtrees(f"{common.project_name}.rtl.src", is_hier_tag = True)[0]
                for fpath in base_config.get("synthesis.inputs.input_files"):
                    # If we don't find a matching file in our rtl.src dir we will copy what exists in our conf over
                    if not rec_find_fpath(rtl_dst_tree.path, os.path.basename(fpath)):
                        shutil.copy(fpath, rtl_dst_tree.path)

    # For each design sweep info

    # TODO this section needs refactoring and requires converting the format of sweep config files to allow for an easy nested init
    # if asic_dse_mode.sweep_gen:
    #     asic_dse_inputs["sweep_conf_fpath"] = asic_dse_conf["sweep_conf_fpath"]
        
    #     sweep_config = parse_config(asic_dse_conf["sweep_conf_fpath"], validate_paths = True, sanitize = True)
    #     # For related functionality we need to assert that there is only 1 design in the sweep conf_fpath 
    #     # assert len(sweep_config["design_sweeps"]) == 1, "ERROR: Only 1 design per sweep is supported at this time"

    #     # Strip out any field that is not part of sweep
    #     design = strip_hier(sweep_config, "sweep")
    #     # Make the 'params' field a dictionary s.t. it won't be mistaken as 
    #     sweep_type_inputs = {} # parameters for a specific type of sweep
    #     if design.get("type") == "sram":
    #         # point the base_rtl_path to the default one in the project tree (will be overridden if another value provided in sweep config)
    #         sweep_type_inputs["sram_rtl_template_fpath"] = os.path.join( 
    #             common.project_tree.search_subtrees("shared_resources.sram_lib.rtl.src", is_hier_tag = True)[0].path,
    #             "sram_template.sv"
    #         )
    #         sweep_type_info = init_dataclass(rg_ds.SRAMSweepInfo, design, sweep_type_inputs)
    #     else:
    #         # If we are either doing RTL or VLSI sweep then we should copy over the source RTL to our project tree
    #         # Check to see if the RTL was passed in via CLI params
    #         # Priority of getting to RTL + HDL search Paths for RTL
    #         # 1. Conglomerated CLI/Conf ( asic_dse_conf["flow_conf_fpath"] ) -> sweep_config["base_config_path"] 
    #         if asic_dse_conf.get("flow_conf_fpaths") and len(asic_dse_conf["flow_conf_fpaths"]) == 1:
    #             base_config = parse_config(asic_dse_conf.get("flow_conf_fpaths")[0])
    #         else:                
    #             base_config = parse_config(design.get("base_config_path"))
            
    #         # If any HDL files currently exist in base config they will be here
    #         base_conf_input_files = base_config.get("synthesis.inputs.input_files")

    #         #if HDL path coming from CLI
    #         if common_asic_flow.hdl_path:
    #             exts = ['.v','.sv','.vhd',".vhdl", ".vh", ".svh"]
    #             _, hdl_search_paths = rec_get_flist_of_ext(common_asic_flow.hdl_path, exts)
    #         else:
    #             sw_conf_hdl_paths = design.get("hdl_dpath")
    #             if sw_conf_hdl_paths:
    #                 hdl_search_paths = sw_conf_hdl_paths
    #             elif base_conf_input_files:
    #                 hdl_search_paths = None
    #             else:
    #                 # <TAG> <VALIDATION>
    #                 raise Exception("ERROR: No method of initializing source HDL files provided")
            
    #         # Priority of Copying RTL from user inputs to project tree
    #         # 1. Search for RTL inside of user provided HDL search paths 
    #         #   a. Priority order: CLI -> base_config["synthesis.inputs.hdl_search_paths"] -> base_config["synthesis.inputs.input_files"] if equivalent files we do a diff to make sure they are the same, if not equal we copy them over
    #         # Priority of HDL search paths:
    #         # 1. Conglom CLI/Conf (common_asic_flow.hdl_path) -> base_config["synthesis.inputs.hdl_search_paths"]
    #         if hdl_search_paths:
    #             # Is assumed sanitized by the parse_config (ie path exists)
    #             rtl_src_dpath = find_common_root_dir(hdl_search_paths)
    #             # update the common_asic_flow.hdl_path with newly found common root RTL directory
    #             common_asic_flow.hdl_path = rtl_src_dpath

    #             rtl_dst_tree: rg_ds.Tree = common.project_tree.search_subtrees(f"{common.project_name}.rtl.src", is_hier_tag = True)[0]
    #             rtl_dst_tree.scan_dir = True
    #             rtl_dst_dpath = rtl_dst_tree.path
    #             # Copy tree recursivley to project tree, just including all files assuming they will be part of the RTL we want, possibly could filter for specific files in the future
    #             shutil.copytree(rtl_src_dpath, rtl_dst_dpath, dirs_exist_ok=True)
    #             rtl_dst_tree.update_tree()
    #         else:
    #             # Our RTL is coming from the base config input_files
    #             rtl_dst_tree = common.project_tree.search_subtrees(f"{common.project_name}.rtl.src", is_hier_tag = True)[0]
    #             for fpath in base_conf_input_files:
    #                 # If we don't find a matching file in our rtl.src dir we will copy what exists in our conf over
    #                 if not rec_find_fpath(rtl_dst_tree.path, os.path.basename(fpath)):
    #                     shutil.copy(fpath, rtl_dst_tree.path)

    #         # Setting Top Lvl if unset or invalid in common asic flow
    #         if not common_asic_flow.top_lvl_module:
    #             # update value in common to reflect correct top lvl
    #             # First we try to get the top module from the base config file (if it exists)
    #             # Try to get the top_lvl_module of design either from the base config file or the sweep config file (if either exist)
    #             base_conf_top_lvl_mod: str = base_config.get("synthesis.inputs.top_module")
    #             sweep_top_lvl_mod: str = design.get("top_lvl_module")
    #             # If top_lvl_module is specified in both the base config and sweep config files we need to make sure they are the same
    #             if base_conf_top_lvl_mod and sweep_top_lvl_mod:
    #                 if base_conf_top_lvl_mod != sweep_top_lvl_mod:
    #                     # <TAG> <VALIDATION>
    #                     print("ERROR: Top level module mismatch between base config and sweep config, sweep top lvl module can only be specified from one of these locations")
    #                     sys.exit(1)
    #                 else:
    #                     # If they are the same we can set the top_lvl_module to either one
    #                     common_asic_flow.top_lvl_module = base_conf_top_lvl_mod
    #             # If only the sweep config file has the top_lvl_module we set it to that
    #             elif sweep_top_lvl_mod:
    #                 common_asic_flow.top_lvl_module = sweep_top_lvl_mod
    #             # If only the base config file has the top_lvl_module we set it to that
    #             elif base_conf_top_lvl_mod:
    #                 common_asic_flow.top_lvl_module = base_conf_top_lvl_mod
    #             # If neither exist we throw an error
    #             else:
    #                 # <TAG> <VALIDATION>
    #                 print("ERROR: Top level module not specified in either the base config or sweep config file")
    #                 sys.exit(1)
            
    #         # if common_asic_flow.top_lvl_module and common_asic_flow.hdl_path:
                

    #         # If the base config does not have 'synthesis.inputs.top_module' or 'synthesis.inputs.input_files' set
    #         #    we force the sweep file to specify them, ideally we could also specify them from cli args as well (but things get complicated)
    #         # validate_keys: List[str] = ["synthesis.inputs.top_module", f"synthesis.inputs.input_files"]
    #         # # If key is empty list | None | unspecified in conf file (shorthand)
    #         # required_keys: List[str] = [ key for key in validate_keys if not base_config.get(key) ]
    #         # for key in required_keys:
    #         #     if getattr(design_sweep, key) == None:
    #         #         raise ValueError(f"{key} must be set in either {design_sweep.base_config_path} or {asic_dse.sweep_conf_fpath}")

    #         if design.get("type") == "rtl_params":
    #             sweep_type_info = init_dataclass(rg_ds.RTLSweepInfo, design, sweep_type_inputs)
    #         # elif design["type"] == "vlsi_params":
    #         #     sweep_type_info = init_dataclass(rg_ds.VLSISweepInfo, design, sweep_type_inputs)
            
    #         design_inputs = {}
    #         # design_inputs["type_info"] = sweep_type_info

    #         # Pass in the parsed sweep config and strip out the "shared" hierarchy tags
    #         design_sweep_infos.append(
    #             init_dataclass(
    #                 rg_ds.DesignSweepInfo, 
    #                 {**design, **strip_hier(sweep_config, strip_tag="shared")},
    #                 design_inputs,
    #                 rg_ds
    #             )
    #         )

    #  __   ___    ___ ___   ___ _    _____      _____ 
    #  \ \ / / |  / __|_ _| | __| |  / _ \ \    / / __|
    #   \ V /| |__\__ \| |  | _|| |_| (_) \ \/\/ /\__ \
    #    \_/ |____|___/___| |_| |____\___/ \_/\_/ |___/

    if asic_dse_mode.vlsi.enable:
        custom_asic_flow_settings: dict
        # Hammer Flow
        if asic_dse_mode.vlsi.flow == "hammer":
            custom_asic_flow_settings = None
            asic_dse_conf = get_hammer_flow_conf(common, common_asic_flow.flow_stages, asic_dse_conf)
        # Custom Flow
        # TODO move to a defined dataclass 
        elif asic_dse_mode.vlsi.flow == "custom":
            # Currently gating custom flow to provide top level module through CLI or config file
            if top_lvl_valid:
                print("WARNING: Custom flow mode requires the following tools:")
                print("\tSynthesis: Snyopsys Design Compiler")
                print("\tPlace & Route: Cadence Encounter OR Innovus")
                print("\tTiming & Power: Synopsys PrimeTime")
                # If custom flow is enabled there should only be a single config file
                assert len(asic_dse_conf["flow_conf_fpaths"]) == 1, "ERROR: Custom flow mode requires a single config file"
                custom_asic_flow_settings = load_hb_params(clean_path(asic_dse_conf["flow_conf_fpaths"][0]))
                assert len(custom_asic_flow_settings["asic_hardblock_params"]["hardblocks"]) == 1, "ERROR: Custom flow mode requires a single hardblock"
                # TODO either change the custom flow format or assert that there is only a single hardblock in there,
                # Currently the file format allows multiple hardblocks to be speified (from COFFE) but in the task of the ASIC flow, we only allow a single design
                # Kinda tricky though because the support for multiple hardblocks exists past this point but to also allow for user CLI we would also have
                # to allow multiple hardblocks to be specified which seems a bit weird at this point
            else:
                print("ERROR: input top_lvl_module or hdl_path invalid for custom flow")
                sys.exit(1)
    
    # Hammer Flow
    hammer_flow: rg_ds.HammerFlow = init_dataclass(
        rg_ds.HammerFlow,
        strip_hier(asic_dse_conf, strip_tag="hammer_flow"),
    )
    hammer_flow.init(
        asic_dse_conf["sweep_conf_fpath"],
        asic_dse_mode.vlsi.flow,
        asic_dse_conf["tool_env_conf_fpaths"],
        asic_dse_conf["flow_conf_fpaths"],
    )


    # Vars that could come from different sources
    out_tree_name: str = None
    # Top level module init
    if asic_dse_mode.vlsi.enable:
        if asic_dse_mode.vlsi.flow == "hammer":
            if not top_lvl_valid:
                # update value in common asic flow to reflect the correct top lvl
                common_asic_flow.top_lvl_module = hammer_flow.hammer_driver.database.get_setting("synthesis.inputs.top_module")
        elif asic_dse_mode.vlsi.flow == "custom":
            if not top_lvl_valid:
                print("ERROR: input top_lvl_module or hdl_path invalid for custom flow")
                sys.exit(1)

        # Assertions that have to be valid by this point
        assert common_asic_flow.top_lvl_module != None, "ERROR: top_lvl_module is None"
        out_tree_name = common_asic_flow.top_lvl_module
    elif asic_dse_mode.sweep_gen:
        if design_sweep_info.type != "sram":
            assert design_sweep_info.top_lvl_module != None, "ERROR: top_lvl_module is None"
            out_tree_name = design_sweep_info.top_lvl_module
    
    # Its ok for the common_asic_flow.hdl_path to be None if all files are already specified in the design config file
    # modify the project tree after top level module is found
    
    # Design out tree init
    if common.project_name != None and out_tree_name != None:
        design_out_tree_copy = copy.deepcopy(design_out_tree)
        design_out_tree_copy.update_tree_top_path(new_path = out_tree_name, new_tag = out_tree_name)
        # Append to project tree
        common.project_tree.append_tagged_subtree(f"{common.project_name}.outputs", design_out_tree_copy, is_hier_tag = True) # append our asic_dse outputs
        asic_dse_inputs["design_out_tree"] = design_out_tree_copy


    # Object dir init (requires above project tree initialization)
    if asic_dse_mode.vlsi.enable:
        obj_dir_path: str = init_asic_obj_dir(
            common = common, 
            top_lvl_module = common_asic_flow.top_lvl_module
        )
        # update value in common to reflect correct obj dir
        common.obj_dir = obj_dir_path
        if asic_dse_mode.vlsi.flow == "hammer":
            hammer_flow.hammer_driver.obj_dir = obj_dir_path # TODO use the common.obj through flow instead of this 
    elif asic_dse_mode.sweep_gen:
        obj_dir_path: str
        if design_sweep_info.type == "sram":

            # TODO push this back into the init_asic_obj_dir function
            # case in which we are generating srams, there is no output tree so we have some custom logic to determine obj directory
            # out_dir = common.project_tree.search_subtrees("shared_resources.sram_lib.obj_dirs", is_hier_tag = True)[0].path
            obj_dir_path: str = init_asic_obj_dir(
                common = common,
                out_tree = common.project_tree.search_subtrees(
                    "shared_resources.sram_lib.obj_dirs", 
                    is_hier_tag = True
                )[0],
                sram_gen_flag = True,
            )
            # if common.manual_obj_dir:
            #     obj_dir_path = common.manual_obj_dir
            # else:
            #     obj_dir_path = os.path.join(out_dir, f"sram_gen-{rg_ds.create_timestamp()}")
            #     os.makedirs(obj_dir_path, exist_ok = True)
            
            # obj_dname = os.path.basename(obj_dir_path)
            # # This will always be at consistent project path
            # project_obj_dpath = os.path.join(out_dir, obj_dname)
            # if common.manual_obj_dir:
            #     # Check to see if symlink already points to the correct location
            #     if os.path.islink(project_obj_dpath) and os.readlink(project_obj_dpath) == obj_dir_path:
            #         rad_gen_log(f"Symlink already exists @ {project_obj_dpath}", rad_gen_log_fd)
            #     else:
            #         os.symlink(obj_dir_path, project_obj_dpath)
        else:
            obj_dir_path: str = init_asic_obj_dir(
                common = common, 
                top_lvl_module = design_sweep_info.top_lvl_module, 
                sweep_flag = True
            )
        # update value in common to reflect correct obj dir
        common.obj_dir = obj_dir_path

    # By default set the result search path to the design output path, possibly could be changed in later functions if needed
    asic_dse_inputs["result_search_path"] = common.project_tree.search_subtrees(f'projects', is_hier_tag = True)[0].path

    # display project tree
    # common.project_tree.display_tree()

    asic_dse_inputs = {
        **asic_dse_inputs,
        "mode": asic_dse_mode,
        "stdcell_lib": stdcell_lib,
        "scripts": scripts,
        "design_sweep_info": design_sweep_info,
        "asic_flow_settings": hammer_flow,
        "custom_asic_flow_settings": custom_asic_flow_settings,
        "common_asic_flow": common_asic_flow, 
        "common": common,
        "sram_compiler_settings": sram_compiler,
    }
    asic_dse = init_dataclass(rg_ds.AsicDSE, asic_dse_inputs, asic_dse_conf)
    return asic_dse

def init_coffe_structs(coffe_conf: Dict[str, Any], common: rg_ds.Common) -> rg_ds.Coffe:
    """
        Initializes the Coffe data structure to be used for the coffe subtool.

        Args:
            coffe_conf: The dictionary containing all the COFFE configurations
            common: Initialized data structure common to all subtools in RAD-Gen

        Returns:
            Initialized Coffe data structure which can be used to legally execute any mode of operation in the coffe subtool.
    """

    # Add coffe specific trees to common
    # coffe_conf["common"].project_tree.append_tagged_subtree("config", rg_ds.Tree("coffe", tag="coffe.config"))
    fpga_arch_conf_str = Path(clean_path(coffe_conf["fpga_arch_conf_path"])).read_text().replace("${RAD_GEN_HOME}", os.getenv("RAD_GEN_HOME"))
    param_dict = yaml.safe_load(fpga_arch_conf_str)
    fpga_arch_conf = load_arch_params(clean_path(coffe_conf["fpga_arch_conf_path"]), param_dict)
    
    # Set common obj dir
    common.obj_dir = clean_path(coffe_conf["fpga_arch_conf_path"])

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
                asic_dse_cli_args["flow_conf_fpaths"] = hb_conf["flow_conf_fpaths"]
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
        "common": common,
    }
    coffe_info = init_dataclass(rg_ds.Coffe, coffe_inputs, coffe_conf)
    return coffe_info



def init_ic_3d_structs(ic_3d_conf: Dict[str, Any], common: rg_ds.Common) -> rg_ds.Ic3d:
    """
        Initializes the IC3D data structure to be used for the ic_3d subtool.

        Args:
            ic_3d_conf: The dictionary containing all the IC3D configurations
            common: Initialized data structure common to all subtools in RAD-Gen
        
        Returns: 
            Initialized IC3D data structure which can be used to legally execute any mode of operation in the ic_3d subtool.

    """

    # Add ic_3d specific trees to common

    # ic_3d_conf["common"].project_tree.append_tagged_subtree("config", rg_ds.Tree("ic_3d", tag="ic_3d.config"))
    # output_subtrees = [
    #     rg_ds.Tree("includes", tag="inc"),
    #     rg_ds.Tree("obj_dirs", tag="obj_dirs"),
    #     rg_ds.Tree("subckts", tag="subckt"),
    #     rg_ds.Tree("reports", tag="report"),
    #     rg_ds.Tree("scripts", tag="script"),
    # ]
    # for output_subtree in output_subtrees:
    #     ic_3d_conf["common"].project_tree.append_tagged_subtree("output", output_subtree)

    # arg_inputs = {}
    # for k, v in ic_3d_conf.items():
    #     if k in rg_ds.IC3DArgs.__dataclass_fields__:
    #         arg_inputs[k] = v

    args = init_dataclass(rg_ds.IC3DArgs, ic_3d_conf)
    
    # TODO update almost all the parsing in this function
    ic_3d_conf = { 
        **ic_3d_conf,
        **parse_yml_config(ic_3d_conf["input_config_path"])
    }

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

    # Directory structure info
    sp_info = rg_ds.SpInfo(
        top_dir = common.rad_gen_home_path
    )

    # Set common object directory
    common.obj_dir = sp_info.sp_dir

    ic3d_inputs = {
        "common": common,
        "args": args,
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
        "spice_info": sp_info,
        "process_data": process_data,
        "driver_model_info": rg_ds.DriverSpModel(),
        "pn_opt_model": rg_ds.SpPNOptModel(),
        "res": rg_ds.Regexes(),
        "sp_sim_settings": rg_ds.SpGlobalSimSettings(),
        # PDN STUFF
        "pdn_sim_settings": pdn_sim_settings,
        "design_pdn": design_pdn,
    }

    ic_3d_info = init_dataclass(rg_ds.Ic3d, ic3d_inputs)
    return ic_3d_info


def write_out_script(lines: List[str], fpath: str, shebang: str = "#!/bin/bash") -> None:
    """
        Takes list of lines for a script, prepends a header onto it and writes it out to the specified path

        Args:
            lines: List of strings which are line of code in our outputted script
            fpath: Path to the file we want to write the script to
            shebang: The shebang line for the script (which shell are we using)
            
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
def load_arch_params(filename: str, param_dict: dict) -> dict: #,run_options):
    """
        Load COFFE FPGA architecture parameters from a file. 
        This takes in user defined parameters and initializes fields to default values if they are unset.

        Args:
            filename: Path to the file containing the FPGA architecture parameters
            param_dict: Dictionary containing the FPGA architecture parameters (read in from filename)

        Returns:
            Initialized architectural parameters to be loaded into the rg_ds.Coffe struct
    """
    
    # This is the dictionary of parameters we expect to find
    #No defaults for ptn or run settings
    arch_params = {
        'W': -1,
        'L': -1,
        'wire_types': [],
        'rr_graph_fpath': "",
        # 'sb_conn' : {},
        'Fs_mtx' : {},
        'sb_muxes': {},
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
    assert param_dict is not None
    #get values from yaml file
    # with open(filename, 'r') as file:
    #     param_dict = yaml.safe_load(file)

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
        elif param == 'rr_graph_fpath':
            param_dict["fpga_arch_params"]['rr_graph_fpath'] = str(value)
        # elif param == 'sb_conn':
        #     # Dict of sb connectivity params
        #     param_dict["fpga_arch_params"]["sb_conn"] = value
        elif param == "sb_muxes":
            # list of dicts
            param_dict["fpga_arch_params"]["sb_muxes"] = value
        elif param == "Fs_mtx":
            # list of dicts
            param_dict["fpga_arch_params"]["Fs_mtx"] = value
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
def load_hb_params(filename: str) -> dict: #,run_options):
    """
        Loads parameters from specified filename to be used in the custom ASIC flow for ASIC-DSE or COFFE
        
        Args:
            filename: Path to the file containing the ASIC hardblock parameters
        
        Returns:
            Dictionary containing the ASIC hardblock parameters
    """
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