import os
import sys
import re


from typing import List, Dict, Any, Tuple, Union
import src.common.data_structs as rg_ds
import argparse





def parse_cli_args():
    parser = argparse.ArgumentParser(description="Simple SPICE netlist parser")
    parser.add_argument("-i","--input_sp_files", nargs="*", type=str, help="Paths to input spice files")
    return parser.parse_args()                        


def get_grab_text_re(upper_bound_re: str, lower_bound_re: str) -> re.Pattern:
    # grabs all text between upper_bound_re and lower_bound_re
    return re.compile(fr"{upper_bound_re}.*?{lower_bound_re}", re.IGNORECASE | re.DOTALL)

def get_name_re(name_str: str) -> re.Pattern:
    # returns a regex to put a the first \w+ match after a whitespace following name_str
    return re.compile(fr"{name_str}\s+(\w+)", re.IGNORECASE | re.MULTILINE)

# Regex definitions
# Grab the name of a spice library, name will be in 1st capture group
lib_name_re: re.Pattern = get_name_re(r"\.LIB") 
subckt_name_re: re.Pattern = get_name_re(r"\.SUBCKT")
# Parses the header of a subckt definition
# 1st capture group: subckt name
# 2nd capture group: port names
# 3rd capture group: param name default value pairs 
subckt_hdr_parse_re: re.Pattern = re.compile("\.SUBCKT\s+" + \
    "(\w+)\s+" + \
    "(\w+(?:\s+\w+)*)\s+" + \
    "((?:\w+=(?:\d+|\w+)\s*)+)?",
    re.IGNORECASE | re.MULTILINE
)

wspace_re: re.Pattern = re.compile(r"\s+")


param_delim: str = "="
first_occur_param_delim_re: re.Pattern = re.compile(f"{param_delim}.*?", re.IGNORECASE | re.MULTILINE)

# ASSUMES:
#   * "\n" at end of SUBCKT & ports definition
#   * parameters are defined without spaces after "=" delim unless moving onto next parameter
#       * Ex. "param1=1 param2=2" is valid, "param1= 1 param2=2" is not valid
def main():
    args = parse_cli_args()
    spice_fpaths = args.input_sp_files
    for fpath in spice_fpaths:
        with open(fpath, "r") as f:
            sp_text: str = f.read()
            # Grab the lib names
            lib_names: list = lib_name_re.findall(sp_text)
            for lib_name_grps in lib_names:
                # Grabbing lib name, if its a tuple, grab the first element, if its a string then it will be the only element
                # This is because of a weird behavior of re.findall where it returns
                #   a list of tuples if there are more than 1 capture groups else it returns a list of strings...
                lib_name: str = lib_name_grps if isinstance(lib_name_grps, str) else lib_name_grps[0]
                # Grabbing library text
                lib_grab_re: re.Pattern = get_grab_text_re(r"\.LIB", r"\.ENDL")
                libs_text: list = lib_grab_re.findall(sp_text)
                # Make sure its the only lib in the file
                if len(libs_text) > 1:
                    raise ValueError("Found multiple instances of lib {} in file {}".format(lib_name, fpath))
                lib_text: str = libs_text[0]
                # Grabbing lib subckts
                subckt_names: list = subckt_name_re.findall(lib_text)
                for subckt_name_grps in subckt_names:
                    subckt_name: str  = subckt_name_grps if isinstance(subckt_name_grps, str) else subckt_name_grps[0]
                    subckt_def_str: str = f"\.SUBCKT\s+{subckt_name}\s+"
                    subckt_grab_re: re.Pattern = get_grab_text_re(subckt_def_str, r"\.ENDS")
                    subckts_text: list = subckt_grab_re.findall(lib_text)
                    if len(subckts_text) > 1:
                        raise ValueError("Found multiple instances of subckt {} in file {}".format(subckt_name, fpath))
                    subckt_text: str = subckts_text[0]
                    
                    # Parsing Individual Subckts
                    
                    # Header parsing
                    subckt_lines: list = subckt_text.split("\n") # split up subckt into lines ()
                    header_grps: re.Match = subckt_hdr_parse_re.search(subckt_lines[0]) # Take line at index 0 header definition
                    # [0] is the whole match, [1] is first cap grp, etc ...
                    subckt_name: str = header_grps[1]
                    subckt_io_ports: list[str] = wspace_re.split(header_grps[2])
                    subckt_params: list[str] = wspace_re.split(header_grps[3]) if header_grps[3] else None
                    

                    # Instantiation Parsing
                    # Skipping header look at all lines of the subckt
                    for line in subckt_lines[1:]:
                        # Check if parameters exist in the instance
                        if param_delim in line:
                            # seperate instance + ports + subckt with param portion of the string
                            line_front, line_back = first_occur_param_delim_re.split(line, maxsplit=1)
                            # This regex doesn't finish the job we need to look at the last non wspace seperated word in line_front to get our first parameter name
                            front_words: list = wspace_re.split(line_front)
                            # first param name is the last word in line_front
                            # remove last word from front_words as its a param name
                            first_param_name: str = front_words.pop(-1)
                            # Now line back is just parameter stuff
                            line_back: str = f"{first_param_name}{param_delim}{line_back}"
                            # front_words = front_words[:-1]
                        else:
                            line_back = None
                            front_words = wspace_re.split(line)

                        # Above parameter logic is more important if wspaces exist in params
                        inst_subckt : str = front_words.pop(-1) # last word in front_words is subckt
                        inst_name: str = front_words.pop(0) # first word is name of instance
                        inst_ports: list[str] = front_words # remaining words are ports

                        inst_params: Dict[str, Any] = {}
                        if line_back:
                            # Parse the parameters
                            inst_param_pairs: list[str] = wspace_re.split(line_back)
                            for inst_param_pair in inst_param_pairs:
                                isnt_param_name, inst_param_val = inst_param_pair.split(param_delim)
                                inst_params[isnt_param_name] = inst_param_val
                        # At this point we should have all the information needed to create a subckt inst instance





            # For each lib name, grab all text inside of them
            # First use general regexes to grab lib definitions and subckt definitions
            

     




if __name__ == "__main__":
    main()

