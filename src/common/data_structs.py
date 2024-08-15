# -*- coding: utf-8 -*-
"""
    Implementations for Data structures used across RAD-Gen
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, make_dataclass, MISSING, InitVar
import os, sys

import re
from typing import Pattern, Dict, List, Any, Tuple, Union, Generator, Optional, Callable, Type, ClassVar, Protocol
from datetime import datetime
import logging
from pathlib import Path
import shutil
import argparse

from collections import OrderedDict

from third_party.hammer.hammer.vlsi.driver import HammerDriver


# IC 3D imports
import shapely as sh
import plotly.graph_objects as go
import plotly.subplots as subplots
import plotly.express as px
import math
from itertools import combinations

import src.common.constants as consts

# Constants
CLI_HIER_KEY = "."
STRUCT_HIER_KEY = "__"


# ██████╗  █████╗ ██████╗        ██████╗ ███████╗███╗   ██╗
# ██╔══██╗██╔══██╗██╔══██╗      ██╔════╝ ██╔════╝████╗  ██║
# ██████╔╝███████║██║  ██║█████╗██║  ███╗█████╗  ██╔██╗ ██║
# ██╔══██╗██╔══██║██║  ██║╚════╝██║   ██║██╔══╝  ██║╚██╗██║
# ██║  ██║██║  ██║██████╔╝      ╚██████╔╝███████╗██║ ╚████║
# ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝        ╚═════╝ ╚══════╝╚═╝  ╚═══╝

class Dataclass(Protocol):
    """
        Idea from `https://stackoverflow.com/questions/54668000/type-hint-for-an-instance-of-a-non-specific-dataclass`
        Used as a way to type hint a dataclass instance without knowing the specific dataclass
    """
    # as already noted in comments, checking for this attribute is currently
    # the most reliable way to ascertain that something is a dataclass
    __dataclass_fields__: ClassVar[Dict[str, Any]] 

def create_timestamp(fmt_only_flag: bool = False) -> str:
    """
        Creates a timestamp string in below format

        Args:
            fmt_only_flag : If true will return the format string instead of the formatted timestamp
                Used for comparing timestamps when asserted
        
        Return:
            timestamp string in format "YYYY--MM--DD--HH--MM--SS--fff" OR
            format string "{year:04}--{month:02}--{day:02}--{hour:02}--{minute:02}--{second:02}--{milliseconds:03}"
    """
    now = datetime.now()

    # Format timestamp
    timestamp_format = "{year:04}--{month:02}--{day:02}--{hour:02}--{minute:02}--{second:02}--{milliseconds:03}"
    formatted_timestamp = timestamp_format.format(
        year=now.year,
        month=now.month,
        day=now.day,
        hour=now.hour,
        minute=now.minute,
        second=now.second,
        milliseconds=int(now.microsecond // 1e3),
    )
    dt_format = "%Y--%m--%d--%H--%M--%S--%f"

    retval = dt_format if fmt_only_flag else formatted_timestamp
    return retval



@dataclass
class ReportInfo:
    """
        Information relevant to report information and filenames 

        Attributes:
            report_dir : output directory dname which reports are sent to
            unparse_report_dir : subdir dname to report_dir for additional information 
                which parsers haven't been written for yet and should only be looked at manually
            gds_area_fname : fname of the gds area report file created by GDS export
            power_lookup : lookup dict to convert power units to a common unit, normalized at Watts
            power_display_unit : default unit to display in human readable fmt power info
            timing_display_unit : default unit to display in human readable fmt timing info
            area_display_unit : default unit to display in human readable fmt area info

        Todo:
            * move the gds area output report to a more asic flow specific data structure
            * <TAG><UNITS_REFAC> Refactor the power_lookup stuff to be standardized along with other units
    """
    # name out output directory reports are sent to
    report_dir: str = "reports"
    # subdir to report_dir for additional information which parsers haven't been written for yet
    unparse_report_dir: str = "unparse_reports"
    gds_area_fname : str = "gds_area.rpt"
    power_lookup : dict = field(default_factory = lambda: {
        "W": float(1),
        "mW": float(1e-3),
        "uW": float(1e-6),
        "nW": float(1e-9),
        "pW": float(1e-12)
    })
    power_display_unit = "mW"
    timing_display_unt = "ps"
    area_display_unit = "um^2"


@dataclass
class Regexes:
    """
        Stores all regexes used in various placed in RAD Gen, its more convenient to have them all in one place

        Attributes:
            wspace_re: regex to match any whitespace character
            find_params_re: regex to find all parameter declarations in a verilog file 
            find_defines_re: regex to find all `define declarations in a verilog file
            grab_bw_soft_bkt: regex to grab the value inside a bracket pair
            find_localparam_re: regex to find all localparam declarations in a verilog file
            first_eq_re: regex to find the first equals sign in a string
            find_soft_brkt_chars_re: regex to find all soft bracket characters in a string (not referenced)
            find_verilog_fn_re: regex to grab text between function in a verilog file (not referenced)
            grab_verilog_fn_args: regex to grab the arguments of a function in a verilog file (not referenced)
            find_verilog_fn_hdr: regex to find the header of a function in a verilog file (not referenced)
            decimal_re: regex to grab decimal or non decimal numbers in a string
            signed_dec_re: regex to grab signed decimal or non decimal numbers in a string
            sci_not_dec_re: regex to grab scientific notation decimal or non decimal numbers in a string
            inn_fp_grab_stdcell_density_re: regex to look for the '-stdcell_density_size' string and then grabbing the 6 floats after it (surrounded by curly braces)
            int_re: regex to grab integers in a string (not referenced)
            sp_grab_print_vals_re: regex to grab all the text generated from an HSPICE `.print` statement
            sp_del_grab_info_re: regex that grabs measure information from the output of an HSPICE simulation, gets the meas statement name, value, and units
            sp_grab_inv_pn_vals_re: regex that grabs parameter width values from output of HSPICE simulation
            sp_grab_tran_analysis_ub_str: regex to grab transient analysis information from an HSPICE simulation output file (not referenced)
            sp_grab_measure_re: line by line grabs either "measure" statements -> group 1 is name of parameter, group 2 is the value in scientific notation from output of HSPICE simulation
            sp_grab_param_re: grabs parameter name and values from output of HSPICE simulation
            sp_coffe_grab_params_re: grabs COFFE parameter name and values from output of HSPICE simulation, 
                for same desired functionality as `sp_grab_param_re` but COFFE specific
            coffe_key_w_spaces_rep_re: regex for parsing coffe output report

        Examples:
            find_params_re:
                >>> include_rtl = open(include_fpath).read()
                >>> clean_include_rtl = rg_utils.c_style_comment_rm(include_rtl)
                >>> for inc_line in clean_include_rtl.split("\n"):
                >>>     # Look for parameters
                >>>     if asic_dse.common.res.find_params_re.search(inc_line):
                >>>         # TODO this parameter re will not work if no whitespace between params
                >>>         clean_line = " ".join(asic_dse.common.res.wspace_re.split(inc_line)[1:]).replace(";","")
                >>>         # Get the parameter name and value
                >>>         param_name = clean_line.split("=")[0].replace(" ","")
                >>>         param_val = clean_line.split("=")[1].replace(" ","").replace("`","")
            find_defines_res & grab_bw_soft_bkt:
                >>> elif asic_dse.common.res.find_defines_re.search(inc_line):
                >>>         # TODO this define re will not work if no whitespace between params
                >>>         clean_line = " ".join(asic_dse.common.res.wspace_re.split(inc_line)[1:])
                >>>         # Get the define name and value
                >>>         define_name = asic_dse.common.res.wspace_re.split(clean_line)[0]
                >>> if asic_dse.common.res.grab_bw_soft_bkt.search(clean_line):
                >>>     define_val = asic_dse.common.res.grab_bw_soft_bkt.search(clean_line).group(0)
                >>> else:
                >>>     define_val = asic_dse.common.res.wspace_re.split(clean_line)[1].replace("`","")
            inn_fp_grab_stdcell_density_re:
                >>> inn_fp_cmd: str = r"create_floorplan -core_margins_by die -flip f -die_size_by_io_height max -site ${vlsi.technology.placement_site} -stdcell_density_size {1.0 0.7 10 10 10 10}"
                >>> stdcell_density_args: list[str] = asic_dse.common.res.inn_fp_grab_stdcell_density_re.search(inn_fp_cmd).group(0).strip().replace("{","").replace("}","").split()
        
        Todo:
            * Remove or integrate all of the marked (unreferenced) fields
    """
    wspace_re: Pattern = re.compile(r"\s+")
    find_params_re: Pattern = re.compile(r"parameter\s+\w+(\s|=)+.*;")
    find_defines_re: Pattern = re.compile(r"`define\s+\w+\s+.*")
    grab_bw_soft_bkt: Pattern = re.compile(r"\(.*\)")
    find_localparam_re: Pattern = re.compile(r"localparam\s+\w+(\s|=)+.*?;", re.MULTILINE|re.DOTALL)
    first_eq_re: Pattern = re.compile(r"\s=\s")

    find_soft_brkt_chars_re: Pattern = re.compile(r"\(|\)", re.MULTILINE) # TODO Figure out if this is needed no reference to this
    find_verilog_fn_re: Pattern = re.compile(r"function.*?function", re.MULTILINE|re.DOTALL) # TODO Figure out if this is needed no reference to this
    grab_verilog_fn_args: Pattern = re.compile(r"\(.*?\)", re.MULTILINE|re.DOTALL) # TODO Figure out if this is needed no reference to this
    find_verilog_fn_hdr: Pattern = re.compile(r"<=?") # TODO Figure out if this is needed no reference to this

    decimal_re: Pattern = re.compile(r"\d+\.{0,1}\d*", re.MULTILINE)
    signed_dec_re: Pattern = re.compile(r"\-{0,1}\d+\.{0,1}\d*", re.MULTILINE)
    sci_not_dec_re: Pattern = re.compile(r"\-{0,1}\d+\.{0,1}\d*[eE]{0,1}\-{0,1}\d+", re.MULTILINE)

    # Innovus command editing
    # looking for the '-stdcell_density_size' string and then grabbing the 6 floats after it (surrounded by curly braces)
    inn_fp_grab_stdcell_density_re: Pattern = re.compile(r"(?<=\-stdcell_density_size\s){(\d+\.{0,1}\d*\s)+(\d+\.{0,1}\d*)}")
    
    # IC 3D
    int_re: re.Pattern = re.compile(r"[0-9]+", re.MULTILINE) # TODO Figure out if this is needed no reference to this
    sp_del_grab_info_re: re.Pattern = re.compile(r"^.(?:(?P<var1>[^\s=]+)=\s*(?P<val1>-?[\d.]+)(?P<unit1>[a-z]+))?\s*(?:(?P<var2>[^\s=]+)=\s*(?P<val2>-?[\d.]+)(?P<unit2>[a-z]+))?\s*(?:(?P<var3>[^\s=]+)=\s*(?P<val3>-?[\d.]+)(?P<unit3>[a-z]+))?",re.MULTILINE)
    sp_grab_print_vals_re: re.Pattern = re.compile(r"^x.*?^y",re.DOTALL | re.MULTILINE) # Grabs all the text generated from an HSPICE `.print` statement
    sp_grab_inv_pn_vals_re: re.Pattern = re.compile(r"\s+\.param\s+(?P<name>inv_w[np]_\d+)\s+=\s+(?P<value>\d+\.\d+)\w*")
    # spice output file ".lis" regex matches
    sp_grab_tran_analysis_ub_str: str = r"\s*transient\s*analysis.*?\s*" # TODO Figure out if this is needed no reference to this
    sp_grab_tran_analysis_re: re.Pattern = re.compile(r"\s*transient\s*analysis.*?\s*\.title\s*", re.DOTALL)
    # line by line grabs either "measure" statements -> group 1 is name of parameter, group 2 is the value in scientific notation
    sp_grab_measure_re: re.Pattern = re.compile( r"\b(\w+)\s*=\s*(failed|not found|[-+]?\d*(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*(?:\w+)?(?=\s|$)" )
    # global grabs all ".param" statements -> group 1 is name of parameter, group 2 is the value in scientific notation
    sp_grab_param_re: re.Pattern = re.compile(r"\.param\s+([^\s=]+)\s*=\s*([+\-]?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)\s*\$")
    # Above grab_param_re didn't seem to work for coffe params
    sp_coffe_grab_params_re: re.Pattern = re.compile(r"^\s+(\d+):(\w+)\s+=\s*([+\-]?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)\s*$", re.MULTILINE)
    # COFFE parsing
    coffe_key_w_spaces_rep_re: re.Pattern = re.compile(r'^([^0-9]+)\s+([0-9.]+[eE]{0,1}[0-9-]+)$', re.MULTILINE)



@dataclass
class GeneralCLI:
    """
        Struct to contain all info related to all command line interface args used in RAD Gen
        The primitive data structure used in other tool or mode specific structs to define CLI args

        Attributes:
            key: key for the cli argument, will be translated to '--<key>' in the command line
            help_msg: help message for the cli argument
            datatype: datatype of the cli argument
            shortcut: optional shortcut for the cli argument, will be translated to '-<shortcut>' in the command line
            default_val: default value for the cli argument
            optional: flag to determine if the cli argument is optional
            nargs: optional argument to determine the number of arguments the cli argument can take
            choices: optional argument to determine the possible legal values for the datatype
            action: optional argument to determine the action to take when the cli argument is parsed
    """
    key: str
    help_msg: str
    datatype: Any = None
    shortcut: str = None
    default_val: Any = None
    optional: bool = False 
    nargs : str = None # optional
    choices: List[Any] = None # optional
    action: str = None # optional if datatype != bool

    def __post_init__(self):
        # Could add type checking below to make sure (datatype == bool) but not sure how to do in python 
        if self.action == "store_true":
            self.default_val = False

class DisplayablePath():
    """
        Class to display a directory structure path similar to the linux `tree` command
        From "https://stackoverflow.com/questions/9727673/list-directory-tree-structure-in-python"

        Examples:
            >>> paths_gen = DisplayablePath.make_tree(Path("<some_path>", criteria=lambda p: p.is_dir()))
            >>> path_strs = [gen.path.absolute() for gen in paths_gen]
        
    """

    display_filename_prefix_middle = '├──'
    display_filename_prefix_last = '└──'
    display_parent_prefix_middle = '    '
    display_parent_prefix_last = '│   '

    def __init__(self: 'DisplayablePath', path: Path, parent_path: Optional['DisplayablePath'], is_last: bool):
        self.path = Path(str(path))
        self.parent = parent_path
        self.is_last = is_last
        if self.parent:
            self.depth = self.parent.depth + 1
        else:
            self.depth = 0

    @property
    def displayname(self : 'DisplayablePath'):
        if self.path.is_dir():
            return self.path.name + '/'
        return self.path.name

    @classmethod
    def make_tree(cls: Type['DisplayablePath'], path: Path, parent: Optional['DisplayablePath'] = None, is_last: bool = False, criteria: Optional[Callable[[Any], bool]]=None) -> Generator['DisplayablePath', None, None]:
        path = Path(str(path))
        criteria = criteria or cls._default_criteria

        displayable_path = cls(path, parent, is_last)
        yield displayable_path

        children = sorted(
            [ 
                path for path in path.iterdir()
                    if criteria(path)
            ],
            key=lambda s: str(s).lower()
        )
        count = 1
        for path in children:
            is_last = count == len(children)
            if path.is_dir():
                yield from cls.make_tree(path,
                                         parent=displayable_path,
                                         is_last=is_last,
                                         criteria=criteria)
            else:
                yield cls(path, displayable_path, is_last)
            count += 1

    @classmethod
    def _default_criteria(cls, path: Path) -> bool:
        return True

    @property
    def displayname(self):
        if self.path.is_dir():
            return self.path.name + '/'
        return self.path.name

    def displayable(self):
        if self.parent is None:
            return self.displayname

        _filename_prefix = (self.display_filename_prefix_last
                            if self.is_last
                            else self.display_filename_prefix_middle)

        parts = ['{!s} {!s}'.format(_filename_prefix,
                                    self.displayname)]

        parent = self.parent
        while parent and parent.parent is not None:
            parts.append(self.display_parent_prefix_middle
                         if parent.is_last
                         else self.display_parent_prefix_last)
            parent = parent.parent

        return ''.join(reversed(parts))



class Tree:
    """
        Linux directory structure for building, creating, traversing, and managing directory trees in python

        Attributes:
            path: path to this specific dir
            basename: dir name
            subtrees: list of subtrees of this dir
            tag: tag for this dir, should be an string that to be used to search for this directory
            heir_tag: tag for this dir and all its parent directories, e.g. "<parent_tag>.<tree_tag>"
            is_leaf: flag to determine if this dir is a leaf of dir structure
            scan_dir: flag to determine if this dir should be scanned for existing subdirectories and added to the tree

        Todo:
            * Refactor to convert this to a dataclass
    """

    def __init__(
        self, 
        path: str, 
        subtrees: List['Tree'] = None, 
        tag: str = None, 
        scan_dir: bool = False
    ):
        """
            Constructor, initializes `is_leaf`, `tag`, and `hier_tag` fields if not passed as args
        """
        
        self.path : str | None = path
        self.basename : str | None = os.path.basename(path) if path else None
        self.subtrees : List['Tree'] | None = subtrees
        self.tag : str | None = tag
        self.heir_tag: str | None = tag
        self.is_leaf : bool = False
        self.scan_dir: bool = scan_dir # If true will scan the directory path and add any subdirectories to the tree

        # Set is_leaf flag
        if self.subtrees == None:
            self.is_leaf = True
        else:
            self.is_leaf = False    

        # if tag not provided just use dir name
        if self.tag == None:
            self.tag = self.basename
            self.heir_tag = self.tag

    def append_subtree(self, subtree: 'Tree') -> None:
        """
            Appends the `subtree` arg to the `subtrees` list of this tree.
            Updates appropriate data structures to reflect the new subtree.

            Args:
                subtree: Tree object to append to this tree
        """
        # update the subtree paths to reflect its new placement
        subtree.update_tree(parent = self)
        if self.subtrees:
            self.subtrees.append(subtree)
        else:
            # As it had no children we need to make it a non leaf
            self.is_leaf = False
            self.subtrees = [subtree]

    def rec_add_existing_subtrees(self) -> None:
        """
            Assuming the tree (`self`) has been constructed and directory exists.
            This finds all the subdirectories which also currently exist,
            even if they are not present in the tree, and will add them to the tree data structure (`self`)

            This fn is useful when you want to use a directory structure which may come from a third party.
            This way when you search for a tag you can use the structure currently defined but if for some reason it changes, 
            you would only need to update the tag being searched for rather than the entire Tree instantiation.
        """
        # Create subtrees and append them
        for subdir in os.listdir(self.path):
            # "." and "__" are ignore prefixes for existing dir scanning
            if os.path.isdir(os.path.join(self.path, subdir)) and \
                not subdir.startswith(".") and \
                not subdir.startswith("__"):
                self.append_subtree(Tree(subdir))

        # Now recursively call this function on all subtrees
        if self.subtrees:
            for subtree in self.subtrees:
                subtree.rec_add_existing_subtrees()
        else:
            self.is_leaf = True


    def update_tree_top_path(self, new_path: str, new_tag: str = None) -> None:
        """
            Updates the top level path of a tree and all its subtrees.
            Really only for use when we have a tree structure that repeated in multiple places, 
            but we want to change its name / tag for each instantiation of the common tree.

            Args:
                new_path: new path to set for the tree
                new_tag: new tag to set for the tree

        """
        self.path = new_path
        self.basename = os.path.basename(new_path)
        self.tag = new_tag if new_tag else self.basename

    def update_tree(self, parent: 'Tree' = None) -> None:
        """
            Updates a tree to reflect its new placement in the directory structure
            Could be done after adding a new subtree to an existing tree or changing the path of existing tree but keeping subtrees intact

            Args:
                parent: new parent base tree to update `self` off of.
        """

        # Only would pass in a parent if doing something like adding a subtree to existing tree
        if parent:
            if parent.path:
                self.path = os.path.join(parent.path, self.basename)

            if parent.heir_tag:
                self.heir_tag = f"{parent.heir_tag}.{self.tag}" if self.tag else parent.tag
        
        if self.scan_dir:
            self.rec_add_existing_subtrees()

        if self.subtrees and self.path:
            for subdir in self.subtrees:
                # Recursively goes down all depths
                self._update_subdir_paths(subdir, self.path, self.heir_tag)

    def _update_subdir_paths(self, dir: 'Tree', parent_path: str, parent_tag: str) -> None:
        """
            Recursively updates the paths of all subtrees of a tree

            Args:
                dir: Tree object to update the path of and all its subtrees
                parent_path: path of the parent directory
                parent_tag: hier_tag of the parent directory
        """
        if parent_path:
            dir.path = os.path.join(parent_path, dir.path)

        if parent_tag:
            dir.heir_tag = f"{parent_tag}.{dir.tag}" if dir.tag else parent_tag
        # before looking for subtrees do the scan dir functions
        if dir.scan_dir:
            dir.rec_add_existing_subtrees()

        if dir.subtrees:
            for subdir in dir.subtrees:
                self._update_subdir_paths(subdir, dir.path, dir.heir_tag)

    def display_tree(self):
        """
            Displays the tree structure in a similar format to the linux `tree` command
        """
        paths = DisplayablePath.make_tree(Path(self.path))
        for path in paths:
            print(path.displayable())

    def search_subtrees(
            self, 
            target_tag: str, 
            target_depth: int = None, 
            is_hier_tag: str = False
    ) -> List['Tree']:
        """
            Searches the tree for a specific tag and returns the subtree with that tag. 

            Args:
                target_tag: tag to search for in the tree 
                    if not `is_hier_tag` this directly matches a tag string of a directory or subdir in `self`
                    e.g. "dir_tag_string"
                    if `is_hier_tag` this is a substring search of the `heir_tag` of a directory or subdir in `self`
                    e.g. "path.to.hier_dir.tag_str"
                target_depth: depth to search for the tag in the tree, if None will search all depths
                is_hier_tag: flag to determine how search is performed based of `target_tag`

            Raises:
                Exception: if the target_tag is not found in the tree
                
            Returns:
                List of Tree objects, sorted by shortest distance to the root of the tree
            
            Examples:
                >>> sram_lib_conf_gen_fpath: str = project_tree.search_subtrees(f"sram_lib.configs.gen", is_hier_tag=True)[0].path
        """
        results: list = []
        self._search_subtrees(target_tag, target_depth, 0, is_hier_tag, results)
        if not results:
            raise Exception(f"Tag {target_tag} not found in tree")
        # Sort result by length of each of thier hier_tags (shortest first)
        results = sorted(results, key = lambda x: len(x.heir_tag.split(".")))
        return results

    def _search_subtrees(
            self, 
            target_tag: str, 
            target_depth: int, 
            current_depth: int, 
            is_hier_tag: bool, 
            result: List['Tree'],
    ) -> None:
        """
            Private recursive function to search a tree at the hierarchy of `current_depth` for a `target_tag`. Used in `search_subtrees`

            Args:
                target_tag: tag to search for in the tree
                target_depth: depth to search for the tag in the tree, if None will search all depths
                current_depth: current depth of the tree
                is_hier_tag: flag to determine how search is performed based of `target_tag`
                result: list to store the results of the search at this level of hierarchy
        """
        
        # set search tag
        found_tag = self.tag if not is_hier_tag else self.heir_tag
        
        # If we want to search all depths we set target depth to None
        if (target_depth == None or current_depth == target_depth):
            # For hier tags we do a substr search which is more useful
            if not is_hier_tag:
                if found_tag == target_tag:
                    result.append(self)
            else:
                if found_tag is None:
                    raise Exception(f"Found tag is None in tree, current results: {result}")
                elif target_tag in found_tag:
                    result.append(self)

        if self.subtrees and (target_depth == None or current_depth < target_depth):
            for subtree in self.subtrees:
                subtree._search_subtrees(target_tag, target_depth, current_depth + 1, is_hier_tag, result)
    
    def print_tree(self) -> None:
        """
            Prints the paths existing in the tree
        """
        if self.is_leaf:
            print(self.path)
            return
        
        for subtree in self.subtrees:
            subtree.print_tree()

    def create_tree(self) -> None:
        """
            Recursively creates the directory structure of the tree 
        """
        if self.is_leaf:
            os.makedirs(self.path, exist_ok = True)
            # print(self.path)
            return

        for subtree in self.subtrees:
            if not self.scan_dir:
                # Don't create tree on scan_dir
                subtree.create_tree()

    def append_tagged_subtree(self, tag: str, subtree: 'Tree', is_hier_tag: bool = False, mkdirs: bool = True):        
        """
            Appends a subtree to the tree at the location of the input tag.
            This updates the data structure and creates a new directory

            Args:
                tag: tag to search for in the tree to append the subtree to
                subtree: Tree object being appended to the tree that matches `tag`
                is_hier_tag: flag to determine if the tag is a hier_tag or not
                mkdirs: flag to determine if the directories should be created in the filesystem
        """
        # find subtree in question
        found_subtree: Tree = self.search_subtrees(tag, is_hier_tag = is_hier_tag)[0]
        # update the subtree paths to reflect its new placement
        subtree.update_tree(parent = found_subtree)
        if found_subtree:
            if found_subtree.subtrees:
                found_subtree.subtrees.append(subtree)
            else:
                # As it had no children we need to make it a non leaf
                found_subtree.is_leaf = False
                found_subtree.subtrees = [subtree]
            # Make the dirs
            if mkdirs:
                found_subtree.create_tree()
      

def add_arg(
        parser: argparse.ArgumentParser, 
        cli_opt: GeneralCLI,
) -> None:    
    """
        Adds an argument to an argparse parser based on the GeneralCLI object passed in

        Args:
            parser: argparse.ArgumentParser object to add the argument to
            cli_opt: GeneralCLI object containing the argument information to add to

        Examples:
            >>>     # Add common_cli command line args to the parser
            >>>     common_cli = rg_ds.RadGenCLI()
            >>>     for cli_arg in common_cli.cli_args:
            >>>         rg_ds.add_arg(parser, cli_arg)
    """
    # Create list to deal with optional shortcut
    arg_keys = []
    if cli_opt.shortcut != None:
        arg_keys.append(cli_opt.shortcut)
    arg_keys.append(f"--{cli_opt.key}")

    # Create dict to deal with optional nargs (and other arguments) 
    # TODO fix this breaking if trying to use a combination of arguments with the "store_true" action
    arg_dict = {
        "type" : cli_opt.datatype,
        "help" : cli_opt.help_msg,
        "default" : cli_opt.default_val,
        "nargs" : cli_opt.nargs,
        "choices" : cli_opt.choices,
    }
    # If arg values are None we remove them from the `parser.add_argument()` call
    del_keys = []
    for key in arg_dict.keys():
        if arg_dict[key] == None:
            del_keys.append(key)
    for key in del_keys:
        del arg_dict[key]

    if cli_opt.action == "store_true":
        parser.add_argument(*arg_keys, action = cli_opt.action, help = cli_opt.help_msg)
    else:
        if cli_opt.nargs != None:
            parser.add_argument(*arg_keys, **arg_dict)
        else:
            parser.add_argument(*arg_keys, **arg_dict)



@dataclass
class Common:
    """
        Dataclass to hold all common data structures used in RAD Gen regardless of mode of operation

        Attributes:
            just_config_init: flag to determine if the invocation of RAD Gen will just initialze data structures and not run the tools.
            override_outputs: flag to determine if the dpath / fpath outputs generated from this mode of operation will override existing files or create new ones
            manual_obj_dir: dname to manually specify the object directory for the current run
            obj_dir: The object directory dpath for the current run
            rad_gen_home_path: dpath to the RAD Gen home directory, should be equal to `os.env.get("RAD_GEN_HOME")`
            hammer_home_path: dpath to the Hammer home directory, should be equal to `os.env.get("HAMMER_HOME")`
            logger: logger object for RAD Gen
            verbosity: verbosity level for the logger & other outputs
            project_tree: Tree object to hold the project directory structure for the current run
            project_name: name of the RAD-Gen project
            res: Regexes object to hold all regexes used in RAD Gen
            report: ReportInfo object to hold report info used in RAD Gen

    """
    # All user input fields which exist in a dynamic dataclass, and originate from CommonCLI
    # TODO remove comment or integrate this
    # args: Any = None 

    # Args 
    # top_config_fpath: str = None
    just_config_init: bool = None
    override_outputs: bool = False # If true will override any files which already exist in the output directory
    manual_obj_dir: str = None # If set will use this as the object directory for the current run

    # Paths
    rad_gen_home_path: str = None
    hammer_home_path: str = None

    # Logging
    logger: logging.Logger = logging.getLogger(consts.LOGGER_NAME) # logger for RAD Gen
    
    # Verbosity level
    # 0 - Brief output
    # 1 - Brief output + I/O + command line access
    # 2 - Hammer and asic tool outputs will be printed to console 
    log_verbosity: int = 1 # verbosity level for log file 

    obj_dir : str = None # path to obj directory for current RAD Gen run
    
    # Input / Output directory structures
    project_tree: Tree = None
    project_name: str = None # Name of the RAD-Gen project
    
    # TODO figure out if this is needed
    # Sram Compiler Tree (put here because could be used for different tools)
    # sram_tree: Tree = None

    # TODO uncomment and integrate through flow
    # Name of the PDK we're "creating" for this run, because different subtools can manipulate the PDK, 
    # this name is more for the user to use a unique name that is the combination of thier input PDK parameters  
    # (maybe use metal stack, maybe use different tx for model cards and stdcells and do some scaling to match them up)
    # pdk_name: str = None

    # Global regex struct
    res: Regexes = field(default_factory = Regexes)

    # Global report info struct
    report: ReportInfo = field(default_factory = ReportInfo)


class MetaDataclass(type):
    """
        Meta class to create a dataclass dynamically from field_dtypes

        Attributes:
            fields_dtypes: dict of field names and their datatypes
            fields_defaults: dict of field names and their default values
    """
    fields_dtypes = {}
    fields_defaults = {}

    def __new__(cls, name, bases, namespace):
        """
            Args:
                cls: MetaDataclass object
                name: name of the class being defined
                bases: base classes for constructed class
                namespace: dict with methods and fields defined in class

            Todo:
                * Verify that are initialized in this function result in an equivalent dataclass object
        """
        # Add fields to the dataclass dynamically
        for field_name, field_type in cls.fields_dtypes.items():
            namespace[field_name] = field_type
        
        cls_obj = dataclass(super().__new__(cls, name, bases, namespace))
        return cls_obj


@dataclass 
class ParentCLI:
    """
        Base class for a CLI class for subtool in RAD Gen

        Attributes:
            cli_args: list of GeneralCLI objects to define the CLI args for the subtool
            _fields: dict of field names and their datatypes
            _defaults: dict of field names and their default values
    """
    cli_args: List[GeneralCLI] = None

    # Below are used for dynamic dataclass creation and initialization
    # Initialized in __post_init__
    _fields: Dict[str, Any] = None # key, datatype pairs for all fields in this dataclass
    _defaults: Dict[str, Any] = None # key, default_val pairs for all fields in this dataclass

    def __post_init__(self):
        """
            Verfies `cli_args` and initializes `_fields` and `_defaults` dicts

            Raises:
                Exception: if `cli_args` is None

        """
        if self.cli_args == None:
            raise Exception("No cli_args provided for CLI class")
        self._fields = dict(sorted( 
            {_field.key : _field.datatype for _field in self.cli_args}.items() 
        ))
        self._defaults = dict(sorted( 
            {_field.key : _field.default_val for _field in self.cli_args}.items()
        ))
    
    def get_dataclass_fields(self, is_cli: bool = False) -> Dict[str, List[Any]]:
        """
            Returns the dynamic (defined in _fields) and static (defined in dataclass) to instantiate the dynamic dataclass type object

            Args:
                is_cli: flag to determine if the fields are being used for a CLI or not (deprecated)

            Todo:
                * Fix or remove the is_cli functionality. Original intention was to only allow fields 
                    defined in `_fields` to be able to define the new dataclass rather than all of those contained in `self`

            Returns:
                Dict of lists with keys for 'keys' (field names), 'dtypes' (field datatypes), and 'defaults' (field default values) 
        """
        # To deal with problem of "." character being invalid for field names we replace it with double underscore here, has to be converted back to "." when cli args are written to console
        for key in self._fields.copy().keys():
            if CLI_HIER_KEY in key:
                self._fields[key.replace(CLI_HIER_KEY, STRUCT_HIER_KEY)] = self._fields.pop(key)
        # Adds the dynamic fields propegated from cli_args to the dataclass
        keys = []
        dtypes = []
        defaults = []
        for key, dtype in self._fields.items():
            keys.append(key)
            dtypes.append(dtype)
            # default key to hash dict is the hierarchical definition with the "." seperated syntax
            default_key: str = key.replace(STRUCT_HIER_KEY, CLI_HIER_KEY)
            defaults.append(self._defaults[default_key])

        # A behavior that is convenient is to be able to instantiate the dataclass with the same fields as the cli_args, which can store all operation modes for a subtool
        if not is_cli:
            # All statically defined fields in the original dataclass added here
            for field in fields(self):
                keys += [field.name]
                dtypes += [field.type]
                # If the field has a default factory we call it to get the default value
                defaults += [field.default_factory() if field.default == MISSING and field.default_factory != None else field.default]
            
        return {"keys" : [_key for _key in keys], "dtypes": [_dtype for _dtype in dtypes], "defaults": [_default for _default in defaults] }

def dyn_dataclass_init(self: MetaDataclass, **kwargs) -> None:
    """
        Dynamically initializes a dataclass with the provided keyword arguments
        When creating a new dynamic dataclass set the __init__ namespace key to this function
    """
    set_fields = []
    # Sets all fields from user input kwargs
    for field_name, field_value in kwargs.items():
        if field_name in self.__annotations__:
            setattr(self, field_name, field_value)
            set_fields.append(field_name)
    # If any fields not set by user input, set them to their default values
    for field_name, field_default_val in self.__dataclass_fields_defaults__.items():
        if field_name not in set_fields:
            setattr(self, field_name, field_default_val)

def get_dyn_class(cls_name: str, fields: Dict[str, List[Any]], bases: Tuple[Any] = None) -> Type[MetaDataclass]:
    """
        Creates a dynamic dataclass type object from the fields provided in the `fields` dict

        Args:
            cls_name: name of the class to create
            fields: dict of lists with keys for 'keys' (field names), 'dtypes' (field datatypes), and 'defaults' (field default values)
                generated from ParentCLI.get_dataclass_fields()
            bases: base classes for the new class

        Returns:
            Dynamic dataclass object with the fields defined in `fields`

        Todo:
            * Refactor to not set the fields_dtypes and fields_defaults in the MetaDataclass class itself. 
                Figure out how to do this in the __new__ function
                
    """
    fields_dtypes = dict(zip(fields["keys"], fields["dtypes"]))
    fields_defaults = dict(zip(fields["keys"], fields["defaults"]))
    
    MetaDataclass.fields_dtypes = fields_dtypes
    MetaDataclass.fields_defaults = fields_defaults
    
    # if no base classes just pass empty tuple
    bases_arg = () if bases == None else bases

    return MetaDataclass(cls_name, bases_arg, 
                       {"__annotations__": fields_dtypes, 
                        "__dataclass_fields_defaults__": fields_defaults, 
                        "__dataclass_fields__": fields_dtypes.keys(), 
                        "__init__": dyn_dataclass_init})
    

@dataclass
class RadGenCLI(ParentCLI):
    """
        Dataclass to hold all command line interface arguments for the RAD Gen tool
        Maps cli keys into the `Common` data structure fields. 

        Attributes:
            cli_args: list of GeneralCLI objects to define the CLI args that map to `Common`
            subtool_args: Options would be the cli classes for each subtool, TODO define this more clearly
            no_use_arg_list: list of arguments which should not be used in the command line interface when calling RAD-Gen
            
    """
    cli_args: List[GeneralCLI] = field(default_factory = lambda: [ 
        GeneralCLI(key = "subtools", shortcut="-st", datatype = str, nargs = "*", help_msg = "subtool to run"),
        GeneralCLI(key = "top_config_fpath", shortcut = "-tc", datatype = str, help_msg = "path to (optional) RAD-GEN top level config file"),
        GeneralCLI(key = "override_outputs", shortcut = "-l", datatype = bool, action = "store_true", help_msg = "Uses latest obj / work dir / file paths found in the respective output dirs, overriding existing files"),
        GeneralCLI(key = "manual_obj_dir", shortcut = "-o", datatype = str, help_msg = "Uses user specified obj dir"),
        GeneralCLI(key = "project_name", shortcut = "-n", datatype = str, help_msg = "Name of Project, this will be used to create a subdir in the 'projects' directory which will store all files related to inputs for VLSI flow. Needed if we want to output configurations or RTL and want to know where to put them"),
        GeneralCLI(key = "pdk_name", datatype = str, help_msg = "Naming convension for our current 'PDK' , the reason this can be different from stdcell_lib pdk name is because RAD-Gen allows mixing and matching of different stdcell libs, spice tx_models, and metal stacks with appropriate scaling. \
                   If using the asic_dse tool, then the below parameter will be overrided by the stdcell_lib name in the asic_dse config",
                   default_val = "custom_pdk"),
        GeneralCLI(key = "just_config_init", datatype = bool, action = "store_true", help_msg = "Flag to return initialized data structures for whatever subtool is used, without running anything")
        # TODO implement compile results flag here to apply to all tools
    ])

    subtool_args: Any = None # Options would be the cli classes for each subtool
    no_use_arg_list: List[str] = None # list of arguments which should not be used in the command line interface when calling RAD-Gen 

    def decode_dataclass_to_cli(self, cmd_str: str, _field: str, args_dict: Dict[str, str], obj: Any = None) -> str:
        """
            Decodes a dataclass field to a string that can be run from the command line to invoke RAD Gen

            Args:
                cmd_str: string to append decoded dataclass field to
                _field: field name to decode
                args_dict: dict equivalent of the cmd_str to store decoded fields
                obj: optional object to get field value from (default is self)
            
            Returns:
                cmd_str: string with the decoded field appended
                    e.g. "python3 rad_gen.py --<field1> <value1> ..."
            
        """
        if obj == None:
            obj = self
        val = getattr(obj, _field)
        # Convert data structure fields to format expected by the CLI
        _cli_field: str = _field.replace(STRUCT_HIER_KEY, CLI_HIER_KEY)
        # Make sure the value is not its default value or None / False (initial values)
        if val != None and val != False:
            # This dict is used to be able to do something like "import rad_gen" "rad_gen.main(**sys_args_dict)" to call rad gen from another python script
            # This in a different if statement as it sets up for the next if by converting value to str if its a list
            if isinstance(val, list):
                args_dict[_cli_field] = val.copy()
                val = " ".join(val)
            else:
                args_dict[_cli_field] = val
            # Be careful bools can be positivly evaluated as strings as well so this should be above the str eval
            if isinstance(val, bool):
                cmd_str += f" --{_cli_field}"
            elif isinstance(val, str) or isinstance(val, int) or isinstance(val, float):    
                cmd_str += f" --{_cli_field} {val}"
            else:
                raise Exception(f"Unsupported type for {_cli_field} in {obj}")
        return cmd_str

    def get_rad_gen_cli_cmd(self, rad_gen_home: str) -> Tuple[str, List[str], Dict[str, str]]:
        """
            Args:
                rad_gen_home: path to the RAD Gen home directory
            
            Returns:
                cmd_str: string to run from the command line to invoke RAD Gen
                sys_args: list of strings to run from the command line to invoke RAD Gen
                sys_args_dict: dict equivalent of the sys_args list
        """
        sys_args_dict = {}
        sys_args = []
        cmd_str = f"python3 {rad_gen_home}/rad_gen.py"
        _field: str
        for _field in self.__class__.__dataclass_fields__:
            # If the key is formatted coming from subtool Arg instantiation we need to convert it back to the CLI style keys
            _field_cli_key: str = _field.replace(STRUCT_HIER_KEY, CLI_HIER_KEY)
            # List of arguments derived from cli_args are the only ones we should use to call RAD-Gen
            # Also don't pass argument values if they are the defaults that already exist in the CLI defs
            cli_default = next((cli_field.default_val for cli_field in self.cli_args if cli_field.key == _field_cli_key), None) # This gets default value for the feild in question
            if _field_cli_key in [ cli_field.key for cli_field in self.cli_args ] and getattr(self, _field) != cli_default: #!= "no_use_arg_list":
                # no use arg list is used specifically to skip an otherwise valid argument in the cli call  
                if not ( self.no_use_arg_list != None and ( _field in self.no_use_arg_list ) ):
                    cmd_str = self.decode_dataclass_to_cli(cmd_str = cmd_str, _field = _field, args_dict = sys_args_dict)
        if self.subtool_args != None:
            for _field in self.subtool_args.__dataclass_fields__:
                # If the key is formatted coming from subtool Arg instantiation we need to convert it back to the CLI style keys
                _field_cli_key: str = _field.replace(STRUCT_HIER_KEY, CLI_HIER_KEY)

                cli_default = next((cli_field.default_val for cli_field in self.subtool_args.cli_args if cli_field.key == _field_cli_key), None) # This gets default value for the feild in question
                # List of arguments derived from subtool cli_args are the only ones we should use to call the subtool
                if _field_cli_key in [ _field.key for _field in self.subtool_args.cli_args ] and getattr(self.subtool_args, _field) != cli_default: # != "no_use_arg_list":
                    if not (self.no_use_arg_list != None and ( _field in self.no_use_arg_list ) ):
                        cmd_str = self.decode_dataclass_to_cli(obj = self.subtool_args, cmd_str = cmd_str, _field = _field, args_dict = sys_args_dict)
        sys_args = cmd_str.split(" ")[2:] # skip over the <python3 rad_gen.py>
        return cmd_str, sys_args, sys_args_dict
    


# RadGenCLI is definitions but we basically want to use it as a factory to create the dataclass which holds values for input args
rad_gen_cli = RadGenCLI()
RadGenArgs = get_dyn_class(
    cls_name = "RadGenArgs", 
    fields = rad_gen_cli.get_dataclass_fields(),
    bases = (RadGenCLI,))


#  █████╗ ███████╗██╗ ██████╗    ██████╗ ███████╗███████╗
# ██╔══██╗██╔════╝██║██╔════╝    ██╔══██╗██╔════╝██╔════╝
# ███████║███████╗██║██║         ██║  ██║███████╗█████╗  
# ██╔══██║╚════██║██║██║         ██║  ██║╚════██║██╔══╝  
# ██║  ██║███████║██║╚██████╗    ██████╔╝███████║███████╗
# ╚═╝  ╚═╝╚══════╝╚═╝ ╚═════╝    ╚═════╝ ╚══════╝╚══════╝


@dataclass
class AsicDseCLI(ParentCLI):
    """ 
        Definitions:
            primitive field: dataclass leafs if viewing dataclasses as trees
        
        Command line interface settings for asic-dse subtool 
        CLI definition corresponds to the 'AsicDSE' dataclass
        
        Arguments are grouped according to corresponding dataclass fields
        
        Certain args may not correspond to a single field but rather multiple, or they may act as 'control signals'
        meaning they may be used in an initialization function to set other dataclass fields. 

        The valid modes of operation for the AsicDSE subtool can be derived from the legal combinations of control signals + dataclass fields

        Ideally there should be at cli arg for each primitive field in 'AsicDSE' dataclass, 
        however, if the 'AsicDSE' dataclass has certain class objects that are difficult to map to a cli arg or group of args
        
        Such class objects can be missing in this class definition but for completeness and clarity,
        they should have a comment in this class definition explaining that they are missing.

        Todo:
            * Add functionality to merge user inputs coming from either `top_lvl_config`, parameter defined `config_fpath`, or `cli_args`
        
    """
    cli_args: List[GeneralCLI] = field(default_factory = lambda: [
        # BRANCHING / CONTROL SIGNAL
        #   Args that are mapped to multiple data struct entires or are used as control signals
        GeneralCLI(key = "tool_env_conf_fpaths", shortcut = "-e", datatype = str, nargs = "*", help_msg = "Path to hammer environment configuration file (used to specify industry tool paths + licenses)"),
        GeneralCLI(key = "sweep_conf_fpath", shortcut = "-s", datatype = str, help_msg = "Path to config file describing sweep tasks and containing design parameters to sweep"),
        GeneralCLI(key = "flow_conf_fpaths", shortcut = "-p", datatype = str, nargs = "*", help_msg = "Paths to flow config files, these can be either custom or hammer format"),
        GeneralCLI(key = "compile_results", shortcut = "-c", datatype = bool, action = "store_true", help_msg = "Flag to compile results related a specific asic flow or sweep depending on additional provided configs"),
        GeneralCLI(key = "top_lvl_module", shortcut = "-t", datatype = str, help_msg = "Top level module of design"),
        GeneralCLI(key = "hdl_dpath", shortcut = "-v", datatype = str, help_msg = "Path to directory containing hdl files"),

        # AsicDSE TOP LEVEL FIELDS
        # TODO rename with fpath convension
        GeneralCLI(key = "result_search_path", datatype = str, help_msg = "Path to output tree to search for results"),

        # RUN MODE
        GeneralCLI(key = "mode.vlsi.run", shortcut = "-r", datatype = str, choices = ["serial", "parallel", "gen_scripts"], default_val = "serial", help_msg = "Specify if flow is run in serial or parallel for sweeps"),
        # FLOW MODE
        GeneralCLI(key = "mode.vlsi.flow", shortcut = "-m", datatype = str, choices = ["hammer", "custom"], default_val = "hammer", help_msg = "Mode in which asic flow is run hammer or custom modes"),

        # Below are definitions for params nested in the hierarchy of AsicDSE dataclass
        # STANDARD CELL LIB
        GeneralCLI(key = "stdcell_lib.cds_lib", datatype = str, help_msg = "Name of cds lib for use with Cadence Virtuoso", default_val = "asap7_TechLib"),
        GeneralCLI(key = "stdcell_lib.pdk_rundir_path", datatype = str, help_msg = "Path to rundir of pdk being used for Cadence Virtuoso"),
        GeneralCLI(key = "stdcell_lib.sram_lib_path", datatype = str, help_msg = "Path to sram lib containing macro .lefs for running through ASIC CAD flow"),
        GeneralCLI(key = "stdcell_lib.pdk_name", datatype = str, help_msg = "Name of technology lib, this is what is searched for in either hammer or whatever other tool to find stuff like sram macros", default_val = "asap7"),
        # SCRIPTS
        # TODO move below cli arg to different structure which deals with arbitrarily defined filenames either created or ingested
        GeneralCLI(key = "scripts.virtuoso_setup_path", datatype = str, help_msg = "Path to env setup script for virtuoso environment"),
        GeneralCLI(key = "scripts.gds_to_area_fname", datatype = str, help_msg = "Filename for converting GDS to area and of output .csv file"),
        
        # COMMON ASIC FLOW
        GeneralCLI(key = "common_asic_flow.db_libs", datatype = str, nargs = "*", help_msg = "db libs used in synopsys tool interactions, directory names not paths"),
        
        # FLOW STAGES
        GeneralCLI(key = "common_asic_flow.flow_stages.build.run", shortcut = "-build", datatype = bool, action = "store_true", help_msg = "<UNDER DEV> Generates a makefile to manage flow dependencies and execution"),
        GeneralCLI(key = "common_asic_flow.flow_stages.build.tool", datatype = str, default_val= "hammer", help_msg = "<UNDER DEV>"),
        GeneralCLI(key = "common_asic_flow.flow_stages.build.tag", datatype = str, default_val= "build", help_msg = "<UNDER DEV>"),
        GeneralCLI(key = "common_asic_flow.flow_stages.sram.run", shortcut = "-sram", datatype = bool, action = "store_true", help_msg = "Flag that must be provided if sram macros exist in design (ASIC-DSE)"),
        GeneralCLI(key = "common_asic_flow.flow_stages.syn.run", shortcut = "-syn", datatype = bool, action = "store_true", help_msg = "Flag to run synthesis"),
        GeneralCLI(key = "common_asic_flow.flow_stages.par.run", shortcut = "-par", datatype = bool, action = "store_true", help_msg = "Flag to run place & route"),
        GeneralCLI(key = "common_asic_flow.flow_stages.pt.run", shortcut = "-pt", datatype = bool, action = "store_true", help_msg = "Flag to run primetime (timing & power)"),
        
        # HAMMER FLOW
        # TODO this should really be changed to HammerFlow as its hammer specific
        # TODO move this to the filename path or dir tree structure
        GeneralCLI(key = "hammer_flow.cli_driver_bpath", datatype = str, help_msg = "path to hammer driver executable"),
        # hammer_flow.hammer_driver is a class unable to be defined in CLI
        
        # DESIGN SWEEP(S) INFO
        # TODO allow for CLI alternative to initializing this data struct with a config file ('sweep_conf_fpath')

        # SRAM COMPILER
        # TODO remove or integrate below lines
        # Reason for not being integrated already is because they are set in factory default  
        # GeneralCLI(key = "sram_compiler_settings.rtl_out_dpath", datatype = str, help_msg = "Path to output directory for RTL files generated by SRAM compiler"),
        # GeneralCLI(key = "sram_compiler_settings.config_out_dpath", datatype = str, help_msg = "Path to output directory for config files generated by SRAM compiler"),
        # GeneralCLI(key = "sram_compiler_settings.scripts_out_dpath", datatype = str, help_msg = "Path to output directory for scripts generated by SRAM compiler"),

        # DESIGN OUT TREE
        # TODO implement CLI alternative or put into another catagory for uniformity

    ] )


# Use asic_dse_cli as factory for creating AsicDseArgs dataclass

asic_dse_cli = AsicDseCLI()
# Make a custom dataclass for asic dse input arguments
AsicDseArgs = get_dyn_class(
    cls_name = "AsicDseArgs",
    fields = asic_dse_cli.get_dataclass_fields(),
    bases= (AsicDseCLI, )
)


@dataclass
class VLSIMode:
    """ 
        Mode settings associated with running VLSI flow

        Attributes:
            run: what mode to run it in?
            flow: what flow backend to use?
            enable: Do we actually execute the ASIC flow tools?
            config_pre_proc: Do we need to preprocess the config file for the flow?
    """
    # specify if flow is run in serial or parallel for sweeps 
    run: str = None # choices: ["serial", "parallel", "gen_scripts"]
    # mode in which asic flow is run
    flow: str = None # choices: ["hammer", "custom"]
    enable: bool = None # run VLSI flow
    config_pre_proc: bool = None # Don't create a modified config file for this design

    def init(
            self, 
            sweep_conf_valid: bool,
            flow_conf_valid: bool,
            top_lvl_valid: bool,
    ):
        """
            Uses dependancies from inside + outside the dataclass to determine values for fields
            not defined as __post_init__ as I want to call it when I please
        """
        if flow_conf_valid and not sweep_conf_valid:
            self.enable = True
            if self.flow == "custom":
                self.config_pre_proc = True
            elif self.flow == "hammer":
                if top_lvl_valid:
                    self.config_pre_proc = True
                else:
                    self.config_pre_proc = False
        else:
            self.enable = False
            # We don't set config_pre_proc to false as its an invalid parameter to be set for this mode of operation
                

@dataclass 
class AsicDseMode:
    """ 
        The mode in which the ASIC-DSE subtool is running

        Attributes:
            sweep_gen: Are we in sweep mode?
            result_parse: Are we in result parse mode?
            vlsi: VLSIMode object for running VLSI flow 
    """
    sweep_gen: bool = False # run sweep config, header, script generation
    result_parse: bool = False # parse results 
    vlsi: VLSIMode = field(default_factory = VLSIMode) # modes for running VLSI flow

    def init(
            self,
            sweep_conf_valid: bool, 
            compile_results: bool,
    ) -> None:
        """
            Args:
                sweep_conf_valid: from higher level init function, are preconditions met to run in sweep mode?
                compile_results: is the compile_results flag set? 
        """
        # If in sweep mode
        if sweep_conf_valid:
            # If result flat not set we generate sweeps
            if not compile_results:
                self.sweep_gen = True
                self.result_parse = False
            else:
                self.sweep_gen = False
                self.result_parse = True


@dataclass
class SRAMCompilerSettings:
    """
        Paths related to SRAM compiler outputs

        Attributes:
            rtl_out_dpath: path to output directory for RTL files generated by SRAM compiler
            config_out_dpath: path to output directory for config files generated by SRAM compiler
            scripts_out_dpath: path to output directory for scripts generated by SRAM compiler
    """
    rtl_out_dpath: str = None 
    config_out_dpath: str = None 
    scripts_out_dpath: str = None
    
    def init(self, project_tree: Tree):
        """
            Initializes the paths for the SRAM compiler settings, based on initialized project tree
        """
        self.config_out_dpath = project_tree.search_subtrees(f"sram_lib.configs.gen", is_hier_tag=True)[0].path  
        self.rtl_out_dpath = project_tree.search_subtrees(f"sram_lib.rtl.gen", is_hier_tag=True)[0].path         
        self.scripts_out_dpath = project_tree.search_subtrees(f"sram_lib.scripts", is_hier_tag=True)[0].path


@dataclass
class StdCellLib:
    """
        Paths and PDK information for the current ASIC flow run
    """
    pdk_name: str = "asap7" # name of technology lib, this is what is searched for in either "hammer" or whatever other tool to find stuff like sram macros
    cds_lib: str = "asap7_TechLib" # name of technology library in cdslib directory, contains views for stdcells, etc needed in design
    sram_lib_path: str = None # path to PDK sram library containing sub dirs named lib, lef, gds with each SRAM.
    # Process settings in RADGen settings as we may need to perform post processing (ASAP7)
    pdk_rundir_path: str = None # path to PDK run directory which allows Cadence Virtuoso to run in it

    def init(self, project_tree: Tree):
        assert self.pdk_name != None
        self.sram_lib_path = project_tree.search_subtrees(
            f"hammer.technology.{self.pdk_name}.sram_compiler.memories",
            is_hier_tag=True
        )[0].path
        

@dataclass 
class SRAMSweepParams:
    """
        Parameters for generating SRAMs from a PDK macro library.

        Attributes:
            sram_rtl_template_fpath: path to RTL file which will be modified by SRAM scripts to generate SRAMs, its an SRAM instantiation (supporting dual and single ports with ifdefs) wrapped in registers
            mems:
                List of dicts each of which contain the following elements:
                    * rw_ports -> number of read/write ports
                    * w -> sram width
                    * d -> sram depth
            rw_ports: list of rw ports to attempt to wrappers for single sram macros if they exist
            widths: list of widths to attempt to wrappers for single sram macros if they exist
            depths: list of depths to attempt to wrappers for single sram macros if they exist
    """
    sram_rtl_template_fpath: str = None # path to RTL file which will be modified by SRAM scripts to generate SRAMs, its an SRAM instantiation (supporting dual and single ports with ifdefs) wrapped in registers
    mems: List[Dict[str, int]] = None # Contains sram information to be created from existing SRAM macros using mappers
    # parameters for explicit macro generation
    rw_ports: List[int] = None
    widths: List[int] = None
    depths: List[int] = None


@dataclass 
class VLSICustomMap():
    """
        Info about how to map "indirectly" defined VLSI parameters to the values which affect them in hammer

        Attributes:
            period: List of period values
            core_util: List of core utilization values
            effort: List of effort levels
    """
    period: List[str] = None # In format of "2 ns"
    core_util: List[float] = None # Target core utilization
    effort: List[str] = None # Target effort level for par tool in flow (as it takes the longest)

    def __post_init__(self):
        # Validation
        if self.effort:
            legal_vals = ["express", "standard", "extreme"]
            assert all(e in legal_vals for e in self.effort)
        
    # TODO implement these for hammer (already exist in custom_flow)
    # wire_selection: List[str] = None
    # metal_layers: List[int] = None

@dataclass
class VLSISweepParams(): 
    """
        Attributes:
            direct_map: Parameters which have a 1:1 mapping to those found in `hammer/config/default_types.yml`
                This means that if the parameter desired to sweep is a list[dict] (as it is with vlsi.inputs.clocks)
                then the data structure required as the input would be a list[list[dict]]
            custom_map: Parameters which are mapped via custom functionality that exists in `asic_dse.design_sweep()` function
    """
    # Parameters which have a 1:1 mapping to those found in `hammer/config/default_types.yml`
    # This means that if the parameter desired to sweep is a list[dict] (as it is with vlsi.inputs.clocks)
    #   then the data structure required as the input would be a list[list[dict]]

    direct_map: dict = None
    custom_map: VLSICustomMap = None
    
    # Clock ports of the top-level module.
    # Is a list of lists to support freq sweep for multiple clocks
    # clocks: List[CLKPort]

    # def __post_init__(self):
        # Assert that all clock period sweep lists are of equal length
        # assert len(set([ len(clock.periods) for clock in self.clocks ])) == 1
    

@dataclass
class RTLSweepParams():
    """
        Contains information for sweeping designs with RTL parameters

        Attributes:
            base_header_fpath: fpath containing RTL header file for parameter sweeping
            sweep: parameters to sweep, each [key, dict] pair contains the following elements:
                * key = name of parameter to sweep
                * dict elements:
                    * vals -> sweep values for parameter defined in "key"
                    * <arbirary_additional_param_values> -> sweep values of same length of "vals" for any additional parameters which need to be swept at the same time

    """
    base_header_fpath: str # fpath containing RTL header file for parameter sweeping
    sweep: dict 

# TODO add validators
@dataclass
class DesignSweepInfo:
    """
        Information specific to a single sweep of design parameters, this corresponds to a single design in sweep config file
        Required to do run any of the following tasks, for a design:
            * Sweep the clock freq across periods of ["0ns", "1ns", "2ns"] and generate configs + scripts
            * Generate SRAM RTL + configs + scripts
            * Sweep NoC parameters and generate configs + scripts

        Attributes:
            base_config_path: path to hammer config of design
            top_lvl_module: top level module of design
            hdl_dpath: path to directory containing hdl files for design
            type: options are "sram", "rtl" or "vlsi" TODO this could be instead determined by searching through parameters acceptable to hammer IR
            flow_threads: number of vlsi runs which will be executed via output script in parallel (in terms of sweep parameters)
            vlsi_params: # VLSI parameters to sweep
            sram_params: # Parameters to generate SRAM RTL + configs
            rtl_params: RTLSweepParams object
            type_info: contains either RTLSweepInfo or SRAMSweepInfo depending on sweep type
            tool_env_conf_fpaths: paths to hammer flow config files
            flow_conf_fpaths: paths to hammer env config files
    """
    base_config_path: str = None # path to hammer config of design
    top_lvl_module: str = None # top level module of design
    hdl_dpath: str = None # path to directory containing hdl files for design
    type: str = None # options are "sram", "rtl_params" or "vlsi_params" TODO this could be instead determined by searching through parameters acceptable to hammer IR
    flow_threads: int = 1 # number of vlsi runs which will be executed in parallel (in terms of sweep parameters)
    vlsi_params: VLSISweepParams = None # VLSI parameters to generate sweep configs, and scripts for
    sram_params: SRAMSweepParams = None # Parameters to generate SRAM RTL, configs, and scripts for
    rtl_params: RTLSweepParams = None # RTL parameters to sweep configs, and scripts for
    # Optional params for hammer env or hammer flow configs which are shared across design sweeps, required to generate run scripts.
    tool_env_conf_fpaths: List[str] = None # paths to hammer flow config files
    flow_conf_fpaths: List[str] = None # paths to hammer env config files

    def init(self, base_config: dict, project_tree: Tree) -> None:
        """
            Initializes:
                * `sram_params.sram_rtl_template_fpath`
                * `top_lvl_module`
            From control signals:
                * `self.type`
            From data dependancies:
                * `base_config`
                * `project_tree`
            
            Args: 
                base_config: dict containing a hierarchically parsed hammer config file
                project_tree: Tree object containing the project directory structure
        """
        if self.type == "vlsi" or self.type == "rtl":
            # Validation to ensure struct can operate in VLSI mode
            base_conf_input_files = base_config.get("synthesis.inputs.input_files")
            if not self.hdl_dpath:
                assert base_conf_input_files, "hdl_dpath must be provided if base config does not contain synthesis.inputs.input_files"
            if not self.top_lvl_module:
                base_conf_top_lvl_mod = base_config.get("synthesis.inputs.top_module")
                assert base_conf_top_lvl_mod, "top_lvl_module must be provided if base config does not contain synthesis.inputs.top_module"
                self.top_lvl_module = base_conf_top_lvl_mod
        elif self.type == "sram":
            self.sram_params.sram_rtl_template_fpath = os.path.join( 
                project_tree.search_subtrees("shared_resources.sram_lib.rtl.src", is_hier_tag = True)[0].path,
                "sram_template.sv"
            )


@dataclass
class ScriptInfo:
    """
        Filenames of various scripts used in RAD Gen

        Attributes:
            gds_to_area_fname: name for gds to area `.csh` and `.il` scripts
            virtuoso_setup_path: path to an (t)csh script that sets up a virtuoso environment when sourced
                acts as control signal for meathod of GDS conversion when using asap7 pdk

    """
    gds_to_area_fname: str = "get_area" # name for gds to area script & output csv file
    virtuoso_setup_path: str = None

@dataclass
class FlowStage:
    """
        In arbitrary tooling flow, information about a specific stage of the flow
        Currently only supported for ASIC flow.

        Attributes:
            tag: What stage of flow is this? TODO link to a list of legal tags
            exec_idx: Index of execution in flow
            run: Should this stage be run?
            tool: What tool should be used for this stage? TODO link to a list of legal tools
        
        Todo: 
            * Add verification for legal `tags`, and `tools`
    """
    tag: str  = None # What stage of flow is this? TODO link to a list of legal tags
    exec_idx: int = None # Index of execution in flow
    run: bool = None # Should this stage be run?
    tool: str = None # What tool should be used for this stage? TODO link to a list of legal tools

@dataclass
class FlowStages:
    """
        Stores the possible + default flow stages for a design through the ASIC VLSI flow
        
        Attributes:
            build: Flow stage that generates a makefile to manage flow dependencies and execution
            sram: Flow stage during VLSI ASIC flow required if using SRAM macros in design
            syn: Flow stage for synthesis
            par: Flow stage for place & route
            pt: Flow stage for primetime (static timing analysis & power)
    """
    build: FlowStage = field(
        default_factory = lambda: FlowStage(
            tag = "build", run = False, tool = "hammer")
    )
    sram: FlowStage = field(
        default_factory = lambda: FlowStage(
            tag = "sram", run = False, tool = "custom")
    )
    syn: FlowStage = field(
        default_factory = lambda: FlowStage(
            tag = "syn", run = False, tool = "cadence")
    )
    par: FlowStage = field(
        default_factory = lambda: FlowStage(
            tag = "par", run = False, tool = "cadence")
    )
    pt: FlowStage = field(
        default_factory = lambda: FlowStage(
            tag = "pt", run = False, tool = "synopsys")
    )

    def init(self, only_parse_flag: bool) -> None:
        """
            Initializes:
                * `syn.run`
                * `par.run`
                * `pt.run`
            From dependancies:
                * `only_parse_flag`
                * `syn.run`
                * `par.run`
                * `pt.run`

            Args:
                only_parse_flag: flag to only parse the design, not run any flow stages
        """
        run_all_flow: bool = not (
            self.syn.run or self.par.run or self.pt.run
        ) and not only_parse_flag
        if run_all_flow:
            self.syn.run = True
            self.par.run = True
            self.pt.run = True
        elif only_parse_flag:
            self.syn.run = False
            self.par.run = False
            self.pt.run = False
        

@dataclass 
class HammerFlow:
    """ 
        Holds Hammer specific settings for the VLSI ASIC flow

        Attributes:
            cli_driver_bpath: path to hammer driver executable
            hammer_driver: driver object used to wrap around and access the hammer database 
    """
    
    # Hammer Info
    cli_driver_bpath: str = None # path to hammer driver
    hammer_driver: HammerDriver = None # hammer settings

    def init(
            self,
            sweep_conf_fpath: str,
            flow: str,
            tool_env_conf_fpaths: List[str],
            flow_conf_fpaths: List[str], 
    ):
        """
            Initializes:
                * `hammer_driver`
                * `cli_driver_bpath`
            From dependancies:
                * `sweep_conf_fpath`
                * `flow`
                * `tool_env_conf_fpaths`
                * `flow_conf_fpaths`
            
            Args:
                sweep_conf_fpath: path to config file describing sweep tasks and containing design parameters to sweep
                flow: mode which hammer flow is run in, from `AsicDseMode.`
        """
        hammer_flow_enable: bool = (
            # Not in sweep mode
            sweep_conf_fpath == None and
            # We have a flow config
            flow_conf_fpaths != None and
            # We are in hammer flow mode
            flow == "hammer"
        )
        if hammer_flow_enable:
            if self.hammer_driver is None:
                # Make sure we are in the correct mode to initialize our hammer stuff
                # Initialize a Hammer Driver, this will deal with the defaults & will allow us to load & manipulate configs before running hammer flow
                driver_opts = HammerDriver.get_default_driver_options()
                # update values
                driver_opts = driver_opts._replace(environment_configs = tool_env_conf_fpaths)
                driver_opts = driver_opts._replace(project_configs = flow_conf_fpaths)
                self.hammer_driver = HammerDriver(driver_opts)

                # Instantiating a hammer driver class creates an obj_dir named "obj_dir" in the current directory, as a quick fix we will delete this directory after its created
                # TODO this should be fixed somewhere
                dummy_obj_dir_path = os.path.join(os.getcwd(),"obj_dir")
                try:
                    if os.path.exists(dummy_obj_dir_path):
                        # Please be careful changing things here, always scary when you're calling "rm -rf"
                        shutil.rmtree(dummy_obj_dir_path)
                except: 
                    # This operation can fail because of possibly running rad gen on multiple processes at the same time 
                    # Its not critical and just for clean up so we can ignore the error
                    pass
            if self.cli_driver_bpath is None:
                # the hammer-vlsi exec should point to default cli driver in hammer repo if everything installed correctly
                self.cli_driver_bpath = "hammer-vlsi"


@dataclass
class CommonAsicFlow:
    """
        Settings common to VLSI asic flow for all designs + backends

        Attributes:
            top_lvl_module: top level module of design
            hdl_dpath: path to root directory containing hdl src files
            flow_conf_fpaths: paths to flow config files, these can be either custom or hammer format
            tool_env_conf_fpaths: paths to hammer environment configuration file (used to specify industry tool paths + licenses)
            db_libs: db libs used in synopsys tool interactions, dnames
            flow_stages: flow stages
    """
    top_lvl_module: str = None # top level module of design
    hdl_dpath: str       = None # path to directory containing hdl files
    flow_conf_fpaths: List[str] = None # paths to flow config files, these can be either custom or hammer format
    # Path to environment configuration file (used to specify industry tool paths + licenses)
    tool_env_conf_fpaths: List[str] = None # In hammer format but is general enough to be used across modes
    # db libs used in synopsys tool interactions, directory names not paths
    db_libs: List[str] = None
    # Flow stages being run Ex. synthesis, place and route, primetime (timing + power), etc
    flow_stages: FlowStages = field(
        default_factory = lambda: FlowStages() # flow stages being run 
    )
    def init(self, pdk_name: str):
        """
            Initializes:
                * `db_libs`
            From control signals:
                * `pdk_name`
                * `self.flow_stages.sram.run`
                * `self.db_libs` 
            From data dependancies:
                * `pdk_name`
            
            Args:
                pdk_name: name of the PDK being used that determines the path to search for db libs
                    from `stdcell_lib.pdk_name`
        """
        if not self.db_libs and pdk_name is not None:
            if self.flow_stages.sram.run:
                self.db_libs = ["sram_db_libs", f"{pdk_name}_db_libs"]
            else:
                self.db_libs = [f"{pdk_name}_db_libs"]

    # Uncomment below block for dynamic instantiation of flow stages
    '''
    flow_stages: List[FlowStage] = field(
        default_factory = lambda: []
    ) # flow stages being run

    def custom_init(self, full_run: bool):
        """
            Similar to regular __post_init__ but we want to call it at a particular point in time
            rather than immediately after constructor
        """
        # Indexed by order of execution
        flow_stage_defaults = [
            FlowStage(tag = "build", run = False, tool = "hammer"),
            FlowStage(tag = "sram", run = False),
            FlowStage(tag = "syn", run = False, tool = "cadence"),
            FlowStage(tag = "par", run = False, tool = "cadence"),
            FlowStage(tag = "pt", run = False, tool = "synopsys")
        ]
        assert len(set([fs.tag for fs in self.flow_stages])) == len(self.flow_stages), "Flow stages must have unique tags"
        
        if full_run:
            # Which tags we enable in case of a 'full run'
            full_run_tags = ["syn", "par", "pt"]
            for def_fs in flow_stage_defaults:
                if def_fs.tag in full_run_tags:
                    def_fs.run = True
                # If the list of flow stages was initalized by user prior to calling this function
                # We should just set the run flag to true but not mess with other fields.
                
                # Used any to not get index error on empty list but should only have a single element
                if any([ fs.tag in full_run_tags for fs in self.flow_stages if fs.tag == def_fs.tag ]):
                    # Gets the index of the flow stage with the same tag as the default flow stage
                    self.flow_stages[ [ fs.tag for fs in self.flow_stages ].index(def_fs.tag) ].run = True
                else:
                    self.flow_stages.append(flow_stage)
        # if the flow_stages are empty list or None
        if not self.flow_stages:
            for flow_stage in flow_stage_defaults:
                self.flow_stages.append(flow_stage)
    '''    


@dataclass
class AsicDSE:
    """
        Data structure required to run the `asic_dse` subtool.

        Attributes:
            common: common settings for RAD Gen from `Common`
            mode: modes of operation in which asic_dse can be / is running
            stdcell_lib: technology information for the design
            scripts: script information for RAD Gen
            sweep_conf_fpath: path to sweep configuration file containing design parameters to sweep
            result_search_path: path which will look for various output obj directories to parse results from
            common_asic_flow: common asic flow settings for all designs
            asic_flow_settings: asic flow settings for single design
            custom_asic_flow_settings: custom asic flow settings
            design_sweep_info: sweep specific information for a single design
            sram_compiler_settings: paths related to SRAM compiler outputs
            design_out_tree: Tree for the design output directory structure        
    """
    common: Common # common settings for RAD Gen
    mode: AsicDseMode # mode in which asic_dse is running
    stdcell_lib: StdCellLib # technology information for the design
    scripts: ScriptInfo = None # script information for asic_dse
    sweep_conf_fpath: str = None # path to sweep configuration file containing design parameters to sweep
    result_search_path: str = None # path which will look for various output obj directories to parse results from
    common_asic_flow: CommonAsicFlow = None # common asic flow settings for all designs
    asic_flow_settings: HammerFlow = None # asic flow settings for single design
    custom_asic_flow_settings: Dict[str, Any] = None # custom asic flow settings
    design_sweep_info: DesignSweepInfo = None # sweep specific information for a single design
    sram_compiler_settings: SRAMCompilerSettings = None # paths related to SRAM compiler outputs
    # ASIC DSE dir structure collateral
    design_out_tree: Tree = None

#  ██████╗ ██████╗ ███████╗███████╗███████╗
# ██╔════╝██╔═══██╗██╔════╝██╔════╝██╔════╝
# ██║     ██║   ██║█████╗  █████╗  █████╗  
# ██║     ██║   ██║██╔══╝  ██╔══╝  ██╔══╝  
# ╚██████╗╚██████╔╝██║     ██║     ███████╗
#  ╚═════╝ ╚═════╝ ╚═╝     ╚═╝     ╚══════╝


@dataclass
class Hardblock:
    """
        Info required to describe a hardblock module in custom FPGA fabric during COFFE flow

        Attributes:
            asic_dse_cli: "asic_dse" subtool arguments for invoking the the ASIC stdcell flow for hardblock design
            name: name of the hardblock
            num_gen_inputs: number of inputs to the hard block from general programmable routing
            crossbar_population: population (%) of crossbar switches in the hard block local interconnect
            height: height of the hard block in logic clusters
            num_gen_outputs: number of outputs from the hard block to general programmable routing
            num_dedicated_outputs: number of outputs from the hard block to dedicated routing
            soft_logic_per_block: soft logic per hardblock in tiles
            area_scale_factor: factor by which the area is scaled to convert stdcell results to a process technology
            freq_scale_factor: factor by which the frequency is scaled to convert stdcell results to a process technology
            power_scale_factor: factor by which the power is scaled to convert stdcell results to a process technology
            input_usage: percentage of inputs used in the hard block
            num_crossbars: number of crossbars in the hard block
            crossbar_modelling: type of crossbar modelling to use choices are ["optimistic"]

    """
    # asic_dse_cli: AsicDseCLI 
    asic_dse_cli: AsicDseArgs

    # COFFE tx sizing hb settings
    name: str
    num_gen_inputs: int
    crossbar_population: float 
    height: int
    num_gen_outputs: int 
    num_dedicated_outputs: int
    soft_logic_per_block: float
    area_scale_factor: float
    freq_scale_factor: float
    power_scale_factor: float
    input_usage: float
    num_crossbars: int
    crossbar_modelling: str 


@dataclass
class CoffeCLI(ParentCLI):
    """
        Command line args for the "coffe" subtool, used for automatic transistor sizing for custom FPGA fabric
    """
    cli_args: List[GeneralCLI] = field(default_factory = lambda: [
        GeneralCLI(key = "fpga_arch_conf_path", shortcut = "-f", datatype = str, help_msg = "path to config file containing coffe FPGA arch information"),
        GeneralCLI(key = "hb_flows_conf_path", shortcut = "-hb", datatype = str, help_msg = "path to config file containing coffe hard block flows information"),
        GeneralCLI(key = "no_sizing", shortcut = "-ns", datatype = bool, action = "store_true", help_msg = "don't perform transistor sizing"),
        GeneralCLI(key = "opt_type", shortcut = "-ot", datatype = str, choices = ["global", "local"], default_val = "global", help_msg = "optimization type, options are \"global\" or \"local\""),
        GeneralCLI(key = "initial_sizes", shortcut = "-is", datatype = str, help_msg = "path to initial transistor sizes"),
        GeneralCLI(key = "re_erf", shortcut = "-re", datatype = int, default_val = 1, help_msg = "how many sizing combos to re-erf"),
        GeneralCLI(key = "area_opt_weight", shortcut = "-aw", datatype = int, default_val = 1, help_msg = "area optimization weight"),
        GeneralCLI(key = "delay_opt_weight", shortcut = "-dw", datatype = int, default_val = 1, help_msg = "delay optimization weight"),
        GeneralCLI(key = "max_iterations", shortcut = "-mi", datatype = int, default_val = 6, help_msg = "max FPGA sizing iterations"),
        GeneralCLI(key = "size_hb_interfaces", shortcut = "-sh", datatype = float, default_val = 0.0, help_msg = "perform transistor sizing only for hard block interfaces"),
        GeneralCLI(key = "quick_mode", shortcut = "-q", datatype = float, default_val = -1.0, help_msg = "minimum cost function improvement for resizing, Ex. could try 0.03 for 3% improvement"),
        GeneralCLI(key = "ctrl_comp_telemetry_fpath", shortcut = "-ct", datatype = str, help_msg = "path to control compare telemetry file"),
        # Additional Args for Refactor
        GeneralCLI(key = "rrg_data_dpath", shortcut = "-rrg", datatype = str, help_msg = "Path to directory containing parsed RRG output csvs"),
        GeneralCLI(key = "pass_through", shortcut = "-pass", datatype = bool, action = "store_true", help_msg = "Flag which enables pass-through mode for COFFE, this does NOT run spice simulations but allows the tool to be run to the end for debugging purposes" ),
        GeneralCLI(key = "ngspice", shortcut = "-ng", datatype = bool, action = "store_true", help_msg = "Flag which enables the use of ngspice over hspice" ),
        GeneralCLI(
            key = "checkpoint_dpaths", shortcut = "-ckpt", datatype = str, nargs = "*", 
            help_msg = "Paths to spice subckt sizing grid search iterations from previous COFFE runs. This allows the current run to skip the found iterations and run spice simulations for missing iterations"
        )
    ])

# Use CoffeCLI as factory for creating CoffeArgs dataclass
coffe_cli = CoffeCLI()
coffe_fields = coffe_cli.get_dataclass_fields()
CoffeArgs = get_dyn_class(
    cls_name = "CoffeArgs",
    fields = coffe_fields,
    bases= (CoffeCLI,)
)

@dataclass
class RoutingWireType:
    """
        General programmable wire type for FPGA fabric
    """
    name: str   = None # Identifier, should keep in line with RRG segment name
    len: int    = None # length in tiles
    freq: int   = None # frequency of wires in channel
    metal: int  = None # metal layer index
    id: int = None # Unique identifier
@dataclass
class FsInfo:
    """
        Fs described switch pattern entry
    """
    src: int # id of source general routing wires
    dst: int # id of destination general routing wires
    Fs: int # number of dst tracks the src can connect to from Switch Block 

@dataclass
class FPGAArchParams:
    """
        Input params to describe an FPGA custom architecture for COFFE flow

        Attributes:
            N: Num BLEs per cluster
            K: Num inputs per BLE
            wire_types: list of gen prog routing wires
            Fs_mtx: If using Fs to describe switch pattern rather than RRG we use these to get our switch block info
            Or: Num BLE outputs to general routing 
            Ofb: Num BLE outputs to local routing
            Fclocal: Population of local routing MUXes
            Rsel: Register select
            Rfb: Register feedback muxes
            use_fluts: Do we want to use fracturable Luts?
            independent_inputs: How many LUT inputs should be independant of one another? can be as large as K-1
            enable_carry_chain: Do we have a hard carry chain in our LBs?
            carry_chain_type: legal options 'skip' and 'ripple'
            FAs_per_flut: Number of Full Adders per fracturable LUT
            vdd: supply voltage
            vsram: SRAM supply voltage, also the boost voltage for pass transistor FPGAs
            vsram_n: SRAM ground voltage
            gate_length: gate length in nm
            rest_length_factor: This parameter controls the gate length of PMOS level-restorers. For example, setting this paramater 
                to 4 sets the gate length to 4x the value of 'gate_legnth'. Increasing the gate length weakens the 
                PMOS level-restorer, which is sometimes necessary to ensure proper switching.
            min_tran_width: For FinFETs, minimum transistor refers to the contact width of a single-fin transistor (nm).
                For Bulk I don't think this parameter is used 
                COFFE uses this when it calculates source/drain parasitic capacit
            trans_diffusion_length: Length of diffusion for a single-finger transistor (nm).
                COFFE uses this when it calculates source/drain parasitic capacitances.
            min_width_tran_area: Minimum-width transistor area (nm^2)
                Look in design rules, make me 1 fin, shortest gate, contact on both sides, no diffusion sharing, 1 space between next transistor
                Layout a single transistor pass DRC, look for sample layout
            sram_cell_area: SRAM area (in number of minimum width transistor areas)
            model_path: path to spice model file  Ex. /path/to/7nm_TT.l
            model_library: name of spice model library Ex. 7NM_FINFET_HP
            metal: R, C values for each metal layer
            gen_routing_metal_pitch: pitch of general routing metal layers (nm)
            gen_routing_metal_layers: number of metal layers used in gen routing
    """
    N: int                              = None # Num BLEs per cluster
    K: int                              = None # Num inputs per BLE
    wire_types: List[RoutingWireType]   = None # list of gen prog routing wires
    Fs_mtx: List[FsInfo]                = None # If using Fs to describe switch pattern rather than RRG we use these to get our switch block info
    Or: int                             = None # Num BLE outputs to general routing 
    Ofb: int                            = None # Num BLE outputs to local routing
    Fclocal: float                      = None # Population of local routing MUXes
    # Register select:
    # Defines whether the FF can accept it's input directly from a BLE input or not.
    # To turn register-select off, Rsel : z
    # To turn register select on, Rsel : <ble_input_name>
    # where <ble_input_name>  :  the name of the BLE input from which the FF can
    # accept its input (e.g. a, b, c, etc...).
    Rsel: str                           = None 
    # Register feedback muxes:
    # Defines which LUT inputs support register feedback.
    # Set Rfb to a string of LUT input names.
    # For example: 
    # Rfb : c tells COFFE to place a register feedback mux on LUT input C.
    # Rfb : cd tells COFFE to place a register feedback mux on both LUT inputs C and D.
    # Rfb : z tells COFFE that no LUT input should have register feedback muxes.
    Rfb: str                           = None
    use_fluts: bool                    = None # Do we want to use fracturable Luts?
    independent_inputs: int            = None # How many LUT inputs should be independant of one another? can be as large as K-1
    enable_carry_chain: bool           = None # Do we have a hard carry chain in our LBs?
    carry_chain_type: str              = None # legal options 'skip' and 'ripple'
    FAs_per_flut: int                  = None # Number of Full Adders per fracturable LUT
    
    # Voltage
    vdd: float                         = None # supply voltage
    vsram: float                       = None # SRAM supply voltage, also the boost voltage for pass transistor FPGAs
    vsram_n: float                     = None # SRAM ground voltage
    
    # Geometry & Areas
    gate_length: int | float           = None # gate length in nm
    
    # This parameter controls the gate length of PMOS level-restorers. For example, setting this paramater 
    # to 4 sets the gate length to 4x the value of 'gate_legnth'. Increasing the gate length weakens the 
    # PMOS level-restorer, which is sometimes necessary to ensure proper switching.
    rest_length_factor: int | float          = None
    
    # For FinFETs, minimum transistor refers to the contact width of a single-fin transistor (nm).
    # For Bulk I don't think this parameter is used 
    # COFFE uses this when it calculates source/drain parasitic capacitances.
    min_tran_width: int | float              = None
    
    # Length of diffusion for a single-finger transistor (nm).
    # COFFE uses this when it calculates source/drain parasitic capacitances.
    trans_diffusion_length: int | float      = None
  
    # Minimum-width transistor area (nm^2)
    # Look in design rules, make me 1 fin, shortest gate, contact on both sides, no diffusion sharing, 1 space between next transistor
    # Layout a single transistor pass DRC, look for sample layout
    min_width_tran_area: int | float         = None

    # SRAM area (in number of minimum width transistor areas)
    sram_cell_area: int                      = None

    # Spice parameters
    model_path: str                          = None # path to spice model file  Ex. /path/to/7nm_TT.l
    model_library: str                       = None # name of spice model library Ex. 7NM_FINFET_HP

    #######################################
    ##### Metal data
    ##### R in ohms/nm
    ##### C in fF/nm
    ##### format: metal : R,C
    ##### ex: metal : 0.054825,0.000175
    #######################################
    
    # If you wanted to, you could define more metal layers by adding more 'metal'
    # statements but, by default, COFFE would not use them because it only uses 2 layers.
    # The functionality of being able to add any number of metal layers is here to allow
    # you to investigate the use of more than 2 metal layers if you wanted to. However,
    # making use of more metal layers would require changes to the COFFE source code.
    metal: List[Tuple[float, float]] = None # R, C values for each metal layer

    gen_routing_metal_pitch: int = None # pitch of general routing metal layers (nm)
    gen_routing_metal_layers: int = None # number of metal layers used in gen routing




@dataclass
class Coffe:
    """
        Data structure to run the "coffe" subtool.

        Attributes:
            common: common settings for RAD Gen
            no_sizing: don't perform transistor sizing
            opt_type: optimization type, options are "global" or "local"
            initial_sizes: where to get initial transistor sizes options are "default" ... TODO find all valid options
            re_erf: how many sizing combos to re-erf
            area_opt_weight: area optimization weight
            delay_opt_weight: delay optimization weight
            max_iterations: max FPGA sizing iterations
            size_hb_interfaces: perform transistor sizing only for hard block interfaces
            quick_mode: minimum cost function improvement for resizing, could try 0.03 for 3% improvement
            fpga_arch_conf: FPGA architecture configuration dictionary
            ctrl_comp_telemetry_fpath: path to control compare telemetry file 
            rrg_data_dpath: Path to directory containing parsed RRG output csvs
            pass_through: Flag which enables pass-through mode for COFFE, this does NOT run spice simulations but allows the tool to be run to the end for debugging purposes
            checkpoint_dpaths: Paths to spice subckt sizing grid search iterations from previous COFFE runs. This allows the current run to skip the found iterations and run spice simulations for missing iterations
            arch_name: name of FPGA architecture
            hardblocks: Hard block flows configuration dictionary
    """
    common: Common # common settings for RAD Gen
    # args: CoffeArgs = None
    # TODO put coffe CLI in here
    ngspice: bool # use ngspice over default hspice
    no_sizing: bool # don't perform sizing
    opt_type: str # optimization type, options are "global" or "local"
    initial_sizes: str # where to get initial transistor sizes options are "default" ... TODO find all valid options
    re_erf: int # how many sizing combos to re-erf
    area_opt_weight: int # area optimization weight
    delay_opt_weight: int # delay optimization weight
    max_iterations: int # max FPGA sizing iterations
    size_hb_interfaces: float # perform transistor sizing only for hard block interfaces
    quick_mode : float # minimum cost function improvement for resizing, could try 0.03 for 3% improvement
    fpga_arch_conf: Dict[str, Any] # FPGA architecture configuration dictionary TODO define as dataclass
    ctrl_comp_telemetry_fpath: str # path to control compare telemetry file 
    # Args for COFFE updates FPL'24
    rrg_data_dpath: str # Path to directory containing parsed RRG output csvs
    pass_through: bool # Flag which enables pass-through mode for COFFE, this does NOT run spice simulations but allows the tool to be run to the end for debugging purposes
    checkpoint_dpaths: List[str] # Paths to spice subckt sizing grid search iterations from previous COFFE runs. This allows the current run to skip the found iterations and run spice simulations for missing iterations
    # NON cli args are below:
    arch_name: str # name of FPGA architecture
    hardblocks: List[Hardblock] = None # Hard block flows configuration dictionary


# ██╗ ██████╗    ██████╗ ██████╗ 
# ██║██╔════╝    ╚════██╗██╔══██╗
# ██║██║          █████╔╝██║  ██║
# ██║██║          ╚═══██╗██║  ██║
# ██║╚██████╗    ██████╔╝██████╔╝
# ╚═╝ ╚═════╝    ╚═════╝ ╚═════╝ 


@dataclass
class SpProcess:
    """
        This represents a spice run to be executed.
        From a title a spice directory will be created
    
        Attributes:
            title: title of the spice run, which will be same as basename for `sp_dir`
            top_sp_dir: parent directory to `sp_dir`
            sp_dir: directory where the spice run will be executed and files will be generated
            sp_file: path to the ".sp" spice file used for this simulation
            sp_outfile: path to the output file ".lis"
    """
    title: str
    top_sp_dir: str # path to top level spice directory
    sp_dir: str = None # path to sim working directory (contains .sp and output files )
    sp_file: str = None # path to sp file used for simulation ".sp" file
    sp_outfile: str = None # output file ".lis"

    def __post_init__(self):
        """
            Initializes:
                * `self.sp_dir`
                * `self.sp_file`
                * `self.sp_outfile`
            From data dependancies:
                * `self.title`
                * `self.top_sp_dir`

            Todo:
                * refactor dir / file names / paths to be consistent with "fpath" / "dname" ...
        """
        self.sp_dir = os.path.join(self.top_sp_dir,self.title)
        if not os.path.exists(self.sp_dir):
            os.makedirs(self.sp_dir)
        self.sp_file = os.path.join(self.sp_dir,self.title+".sp")
        self.sp_outfile = os.path.join(self.sp_dir,self.title+".lis")


@dataclass
class SpInfo:
    """
        Spice directory / file structure information for "ic_3d" subtool.

        Todo:
            * Update to use `Tree` struct instead of current custom meathod
        
    """
    top_dir: str = os.path.expanduser("~/rad_gen")
    sp_dir: str = os.path.join(top_dir,"spice_sim")
    sp_sim_title: str = "ubump_ic_driver"
    sp_sim_file: str = os.path.join(top_dir,sp_dir,sp_sim_title,"ubump_ic_driver.sp")
    sp_sim_outfile: str = os.path.join(top_dir,sp_dir,sp_sim_title,"ubump_ic_driver.lis")    
    subckt_lib_dir: str = os.path.join(sp_dir,"subckts")
    basic_subckts_file: str = os.path.join(subckt_lib_dir,"basic_subcircuits.l")
    subckts_file: str = os.path.join(subckt_lib_dir,"subcircuits.l")
    includes_dir: str = os.path.join(sp_dir,"includes")
    include_sp_file: str = os.path.join(includes_dir,"includes.l")
    process_data_file: str = os.path.join(includes_dir,"process_data.l")
    sweep_data_file: str = os.path.join(includes_dir,"sweep_data.l")
    model_dir: str = os.path.join(sp_dir,"models")
    model_file: str = os.path.join(model_dir,"7nm_TT.l")
    # Info for process and package sensitivity analysis
    process_package_dse : SpProcess = None
    def __post_init__(self):
        self.sp_dir = os.path.join(self.top_dir, "spice_sim")
        self.sp_sim_file: str = os.path.join(self.top_dir, self.sp_dir, self.sp_sim_title, "ubump_ic_driver.sp")
        self.sp_sim_outfile: str = os.path.join(self.top_dir, self.sp_dir, self.sp_sim_title, "ubump_ic_driver.lis")
        self.subckt_lib_dir = os.path.join(self.sp_dir, "subckts")
        self.basic_subckts_file = os.path.join(self.subckt_lib_dir, "basic_subcircuits.l")
        self.subckts_file = os.path.join(self.subckt_lib_dir, "subcircuits.l")
        self.includes_dir = os.path.join(self.sp_dir, "includes")
        self.include_sp_file = os.path.join(self.includes_dir, "includes.l")
        self.process_data_file = os.path.join(self.includes_dir, "process_data.l")
        self.sweep_data_file = os.path.join(self.includes_dir, "sweep_data.l")
        self.model_dir = os.path.join(self.sp_dir, "models")
        self.model_file = os.path.join(self.model_dir, "7nm_TT.l")
        self.process_package_dse = SpProcess(title="process_package_dse", top_sp_dir=self.sp_dir)


@dataclass
class SpSubCkt:
    """
        Information to represent / manipulate a spice subcircuit defined from a ".sp" netlist. 
        
        Attributes:
            * ports: dict of ports in the subcircuit containing the port name and index in which they are instantiated in spice
            * params: dict of spice parameters for the subcircuit
            * raw_sp_insts_lines: list of raw spice instance lines for the subcircuit (not referenced) TODO remove this
            * name: name of the spice subcircuit
            * element: element type of the subcircuit (cap, res, mfet, subckt, etc)
            * prefix: prefix for the subcircuit element type, e.g. "C" for capacitor, or "X" for subcircuit
            * insts: list of instances of the subcircuit
            * direct_conn_insts: flag that determines if inputs and outputs of subckt instances are connected directly to the subckt ports during init
        
        Examples:
            >>> print(self.ports)
            {'in': {'name': 'n_in', 'idx': 0}, 'out': {'name': 'n_out', 'idx': 1}}
            
    """

    ports: dict
    params: dict = field(default_factory=lambda: {})
    raw_sp_insts_lines: list = None
    # These params are to allow subcircuits and larger circuits to be created more easily out of them
    # port_defs: dict = None
    name: str = None
    # Element could be one of the following (cap, res, mfet, subckt, etc)
    element: str = "subckt"
    prefix: str = None
    insts: List[SpSubCktInst] = None
    direct_conn_insts: bool = False

    def print(self, summary: bool = False) -> str:
        """
            Prints the subcircuit information in a human readable format

            Args:
                summary: flag to print a summary of the subcircuit or a detailed view

        """
        msg_lines = []
        if summary:
            line = ""
            line += f" {self.name} " 
            #f".SUBCKT {self.name} " # {' '.join(self.ports)} "
            if self.params:
                line += ' '.join([f'{k}={v}' for k,v in self.params.items()])
            return [line]
        else:
            print(f"#"*80)
            print(f"SUBCKT: {self.name}")
            print(f"Ports: ")
            for key, _ in self.ports.items():
                print(f"{key:<10}",end="")
            print("")
            if self.params:
                print(f"Params")
                print(f"{'param':<10} : {'default_val':>10}")
                print(self.params)
                for key, val in self.params.items():
                    print(f"{key:<10} : {val:>10}")
            print(f"Insts: ")
            for inst in self.insts:
                print("-"*80)
                inst.print()
            return ""

    def connect_insts(self) -> None:
        """
            Modifies the `instances` of this object to connect their ports together in a chain of inputs and ouputs
            Connects the instances of the subckt together
        """
        for idx, inst in enumerate(self.insts):
            prev_tmp_int_node = f"n_{idx}"
            cur_tmp_int_node = f"n_{idx+1}"
            if idx == 0:
                # Connect inst input to subckt input
                inst.conns["in"] = self.ports["in"]["name"]
                inst.conns["out"] = cur_tmp_int_node
            elif idx == len(self.insts)-1:
                                # Connect inst input to subckt input
                inst.conns["in"] = prev_tmp_int_node
                inst.conns["out"] = self.ports["out"]["name"]
            else:
                inst.conns["in"] = prev_tmp_int_node
                inst.conns["out"] = cur_tmp_int_node
            
                # Connect las inst output to subckt output
    def __post_init__(self):
        """
            Initializes:
                * `self.prefix`
            From data dependancies:
                * `self.direct_conn_insts`
                * `self.element`
        """
        prefix_lut = {
            "cap" : "C",
            "res" : "R",
            "ind" : "L",
            "mnfet" : "M",
            "mpfet" : "M",
            "subckt" : "X",
            "v_src" : "V",
        }
        self.prefix = prefix_lut[self.element]
        if (self.direct_conn_insts == True):
            self.connect_insts()


@dataclass
class SpSubCktInst:
    """
        Information for instantiating a subcircuit in spice, could be in a subcircuit or a testbench

        Attributes:
            * subckt: subcircuit type of instantiatation
            * name: name of the instance
            * conns: dictionary of connections for the instance
            * parent_subckt: parent subcircuit of the instance
            * param_values: dictionary of parameter values for the instance

    """
    subckt: SpSubCkt
    name: str                                           # Name of instantiation ie X<inst_name> ... <ports> ... <subckt_name>
    conns: dict = field(default_factory = lambda: {})

    parent_subckt: SpSubCkt = None
    param_values: dict = None 
    

    # def find_top_subckt(self):
    #     """
    #     Finds the top level subckt for the current subckt instance
    #     """
    #     if self.parent_subckt == None:
    #         return self.subckt
    #     else:
    #         return self.parent_subckt.find_top_subckt()

    def print(self, summary: bool = False) -> str:
        """
            Prints the subcircuit information in a human readable format

            Args:
                summary: flag to print a summary of the subcircuit or a detailed view

        """
        if summary:
            line = ""
            line += f" {self.subckt.name:<20}" 
            if self.param_values:
                line += f'{" ":<20}'.join([f'{k:>10} = {v:<35}' for k,v in self.param_values.items()])
            # else:
            #     line += f"{'N/A':>10}{'N/A':>10}"
            return [line]
        else:
            print(f"\nINST: {self.name} of SUBCKT: {self.subckt.name}")
            print(f"Connected Nets: ")
            print(f"{'port':<10} --> {'node':>10}")
            for key, val in self.conns.items():
                print(f"{key:<10} --> {val:>10}")
            print(f"Param Values:")
            for key, val in self.param_values.items():
                print(f"{key:<10} = {val:>10}")


    def get_sp_str(self) -> str:
        """ 
            Generates the instance instantiation line for a spice subckt or testbench

            Returns:
                spice instance line in format compatable with spice simulators

            Raises:
                AssertionError: If not all connections are made in the instantiation
                
            Todo:
                * Fix to work for BUFFER DSE currently only used in COFFE 
        """
        # TODO FIX to make work for BUFFER DSE currently only used in COFFE
        subckt_inst_sublines = [
            f"{self.name}",
        ]
        # create list of connections of length of inst ports
        port_conns = [None]*len(self.subckt.ports)
        # iterate over connections and top level subckt io ports
        assert set(list(self.conns.keys())) == set(list(self.subckt.ports.keys())), print("Connections and ports do not match for subckt instantiation")
        for conn_key, conn_val in self.conns.items():
            for port_key, port_val in self.subckt.ports.items():
                if conn_key == port_key:
                    # create a connection at the right idx
                    # subckt_inst_sublines.append(conn_val)
                    # TODO FIXME this is a discrepency in definition of SpSubCkt.ports between what is done in BUFFER_DSE
                    # CRITICAL FIX
                    port_conns[port_val] = conn_val
                    break
        subckt_inst_sublines.extend(port_conns)
        param_strs = [f"{param}={val}" for param, val in self.param_values.items()]
        assert None not in subckt_inst_sublines, print("Not all connections made in instantiation:", *subckt_inst_sublines)
        
        # subckt or mfet
        if self.subckt.prefix == "X" or self.subckt.prefix == "M":
            subckt_inst_sublines = [*subckt_inst_sublines, self.subckt.name, *param_strs]
        else:
            subckt_inst_sublines = [*subckt_inst_sublines, *param_strs]
        return " ".join(subckt_inst_sublines)

    # initialize the param_values to those stored in the subckt params, if the user wants to override them they will specify them at creation of SpSubCktInst object
    def __post_init__(self):
        # <TODO CRITICAL> FIX THIS FOR IC 3D STUFF
        if self.param_values == None and self.subckt.params:
            self.param_values = self.subckt.params.copy()
        elif self.param_values == None:
            self.param_values = {}


# <TAG> <UNREFERENCED-TODO> see if this should be kept or deleted 
@dataclass
class TechInfo:
    """
        <TAG> <UNREFERENCED-TODO> see if this should be kept or deleted 
    """
    # beol info
    mlayer_ic_res_list : list = None
    mlayer_ic_cap_list : list = None
    via_res_list : list = None
    via_cap_list : list = None
    # not really a tech info but TODO move to a better data structure
    ubump_res: str = None
    ubump_cap: str = None

    num_mlayers = 9
    Mx_range = [0,4]
    My_range = [4,9]
    # rough estimate for single trans area in um^2
    min_width_trans_area = 0.0946
    # def __post_init__(self):
    #     for 
        # self.beol_info["via_info"]

@dataclass
class SpProcessData:
    """
        Used to represent spice process params required for simulating a particular process technology
    """
    global_nodes : dict
    voltage_info : dict
    geometry_info : dict
    driver_info : dict
    tech_info: dict


@dataclass
class DriverSpModel:
    """
        Common node / parameter definitions used in "ic_3d" subtool. 
        
        Todo:
            * <TAG> <REFACTOR-TODO> Integrate this data structure with COFFE or use COFFE methodology for defining these nodes and delete this data structure
    """
    global_in_node: str = "n_in"
    global_out_node: str = "n_out"
    v_supply_param: str = "supply_v" 
    gnd_node: str = "gnd"
    global_vdd_node : str = "vdd"
    dut_in_node : str = "n_dut_in"
    dut_vdd_node: str = "vdd_dut"
    dut_out_node : str = "n_dut_out"


@dataclass
class SpVoltageSrc:
    """
        Data structure for specifying a voltage source 
        Only supportive of a pulse voltage source

        Attributes:
            name: (str) Name of voltage source
            sp_name: (str) Name of voltage source written to spice file
                Ex. if name = "IN" -> will be written out "VIN"
            out_node: (str) Node connecting to output of voltage source
            gnd_node: (str) Node connected to gnd
            type: (str) Type of voltage source 
                Ex. "PULSE" | "SINE" | "PWL" | "DC"
            init_volt: (Value) Initial voltage OR constant voltage for DC voltage src
            peak_volt: (Value) Peak voltage for pulse voltage src
            delay_time: (Value) Delay time for pulse voltage src
            rise_time: (Value) Rise time for pulse voltage src
            fall_time: (Value) Fall time for pulse voltage src
            pulse_width: (Value) Pulse width for pulse voltage src
            period: (Value) Period for pulse voltage src
        
        Todo:
            * <TAG> <REFACTOR-TODO> Delete this and use the one that exists with same name under 
                `src.coffe.data_structs`
    """
    name: str # name of voltage source, ex. if name = "IN" -> will be written as "VIN"
    out_node: str # node connecting to output of voltage source
    type: str # Type of voltage source (pulse, sine, etc)
    # All relevant params for pulse voltage src
    init_volt: str = None
    peak_volt: str = None
    delay_time: str = None
    rise_time: str = None
    fall_time: str = None
    pulse_width: str = None
    period: str = None


@dataclass
class SpLocalSimSettings:
    """
        Data structure for specifying local simulation settings for "ic_3d" subtool buffer design space exploration testbench
    
        Attributes:
            dut_in_vsrc: (SpVoltageSrc) voltage source for providing stimulus to the DUT
            target_freq: (int) target frequency in MHz
            target_period: (float) target period in ns
            sim_time: (float) Total simulation time in ns
            sim_prec: (float) Frequency of simulation sampling in ps
            prec_factor: (float) Factor to be applied to the simulation time to ensure that all the measure statments are captured
            sim_time_factor: (float) Factor to be applied to the simulation time to ensure that all the measure statments are captured
    
        Todo: 
            * <TAG> <REFACTOR-TODO> Determine if to delete this or integrate with COFFE counterpart
    """

    dut_in_vsrc: SpVoltageSrc # voltage source for providing stimulus to the DUT

    target_freq: int = None # freq in MHz
    target_period: float = None # period in ns

    # TODO make everything unitless (just use sci notation, if needs to be set to some unit standard to that where relevant)
    sim_time: float = None # Total simulation time in ns
    sim_prec: float = None # Frequency of simulation sampling in ps
    
    prec_factor: float = 0.001 # Will be used to determine sim precision as 
    sim_time_factor: float = 1.005 # Factor to be applied to the simulation time to ensure that all the measure statments are captured

    
    def __post_init__(self):
        if self.target_period is None and self.target_freq is not None:
            self.target_period = 1e3 / (self.target_freq) # convert from MHz to ns
        elif self.target_period is not None and self.target_freq is None:
            self.target_freq = 1e3 / (self.target_period)
        else:
            raise ValueError("ERROR: Either target period or target freq must be specified, you cannot specify both")
        if self.sim_prec is None:
            self.sim_prec = self.prec_factor * self.target_period * 1e3 # convert from ns to ps
        if self.sim_time is None:
            self.sim_time = self.sim_time_factor * self.target_period
        if self.dut_in_vsrc.pulse_width is None:
            self.dut_in_vsrc.pulse_width = f"{self.target_period / 2}n"
        if self.dut_in_vsrc.period is None:
            self.dut_in_vsrc.period = f"{self.target_period}n"


@dataclass 
class SpGlobalSimSettings:
    """
        Global spice simulation settings for all sims in "ic_3d" subtool.

        Attributes:
            unit_lookups: unit lookups for time and voltage
            unit_lookup_factors: unit lookup factors for time and voltage
            abs_unit_lookups: absolute unit lookups for time and voltage
            sp_options: spice options for simulation
            gnd_node: ground node
            vdd_node: VDD node
            vdd_param: VDD node parameter name

        Todos:
            * <TAG> <TODO-REFACTOR> move `gnd_node`, `vdd_node`, and `vdd_param` from here to
                a more appropriate location and common with COFFE
            * <TAG> <TODO-REFACTOR> integrate with COFFE or delete this data structure

    """
    # These unit lookups will set the default unit value of returned hspice sim plots
    # For below example 1ps will be the default time unit and 1mV will be the default voltage unit
    unit_lookups: dict = field(default_factory = lambda: {
        "time" : {
            "n" : 1e3,
            "p" : 1,
            "f" : 1e-3,
        },
        "voltage" : {
            "m": 1,
            "u": 1e-3,
            "n": 1e-6,
        }
    })
    # This defines the default units for various fields (ex. time in pS, voltage in mV, ...)
    unit_lookup_factors: dict = field(default_factory = lambda: {
        "time" : "p",
        "voltage": "m"
    })
    # unit lookups which are also in the spice format (in case they need to get back and forth)
    abs_unit_lookups: dict = field(default_factory = lambda: {
        "g": 1e9,
        "x": 1e6,
        "k": 1e3,
        " ": 1,
        "m": 1e-3,
        "u": 1e-6,
        "n": 1e-9,
        "p": 1e-12,
        "f": 1e-15,
        "a": 1e-18,
    })
    # below key value pairs are passed into spice simulation ".OPTION BRIEF=1 ..."
    sp_options: dict = field(default_factory = lambda: {
        "BRIEF": 1,
        "POST": 1,
        "INGOLD": 1,
        "NODE": 1,
        "LIST": 1,
    })

    # TODO both these two below nodes should be defined somewhere else and link to the function writing the include spice file (which sets these pins as global gnd and vdd)
    gnd_node: str = "gnd" # ground node
    vdd_node: str = "vdd" #VDD node
    vdd_param: str = "supply_v" #VDD node


    # bottom_die_inv_stages: int = 1 # This should be removed pray this inst being used somewhere  


########################## GENERAL PROCESS INFORMATION ###########################

@dataclass
class SpOptSettings:
    """
        Used to define an HSPICE `.opt` statement for a single param.
        
        Attributes:
            init: Initial value for the param
            range: Range of values for the param
            step: Step size for the param
        
        Todo:
            * <TAG><TODO-REFACTOR> Integrate with common spice data structure 
    """
    init: float
    range: List[float]
    step: float

    def __post_init__(self):
        """
            Verification that the range is valid for the initial value
        """
        if min(self.range) > self.init or max(self.range) < self.init:
            raise ValueError(f"Initial value {self.init} is not within range {self.range}")


@dataclass
class SpParam:
    """
        Describes a single spice parameter used in "ic_3d" subtool

        Attributes:
            name: name of the parameter
            suffix: unit suffix for the parameter
            value: value of the parameter
            opt_settings: optimization settings for the parameter

        Todo:
            * <TAG><TODO-REFACTOR> Integrate with common spice data structure 
    """
    # param name
    name: str
    # param unit (ex. f, p, etc)
    suffix: str = None
    # unit type (meters, farads, etc)
    # param val
    value: float = None
    # unit: str = None
    # sweep_vals: List[float] = None
    opt_settings: SpOptSettings = None
    # Opt param settings




@dataclass
class MlayerInfo:
    """
        Describes a Metal Layer in a process technology

        Attributes:
            * idx: Index of the metal layer in stack from lowest to highest
            * wire_res_per_um: Wire resistance per unit length in Ohms / um
            * wire_cap_per_um: Wire capacitance per unit length in fF / um
            * via_res: Via resistance in Ohms
            * via_cap: Via capacitance in fF
            * via_pitch: Via pitch in nm
            * pitch: Pitch in nm
            * t_barrier: Thickness of the barrier in nm
            * height: Height of the metal layer in nm
            * width: Width of the metal layer in nm
            * sp_params: Spice parameters for the metal layer

        Todo: 
            * Define and verify which direction the vias are going (for `via_res` and `via_cap`).
                By this I mean I'm forgetting if when we have a `MlayerInfo` object for metal layer 0, 
                is the associated via going from M0 -> M1? or POLY -> M0? I forget.
    """
    idx: int # LOWEST -> TOP
    wire_res_per_um: float # Ohm / um
    wire_cap_per_um: float # fF / um
    via_res: float # Ohm
    via_cap: float # fF
    via_pitch: float # nm
    pitch: float # nm
    t_barrier: float # nm
    height: float # nm
    width: float # nm
    # Spice Info for MLayer / Vias
    sp_params: dict = field(default_factory = lambda: {})
    def __post_init__(self):
        """
            Initializes:
                * `sp_params`
            From data dependancies:
                * `self.idx` 
                * `self.wire_res_per_um`
                * `self.wire_cap_per_um`
                * `self.via_res`
                * `self.via_cap`
        """

        # for each member of mlayer
        for sp_param in ["wire_res_per_um","wire_cap_per_um","via_res","via_cap"]:
            attr_val = getattr(self, sp_param)
            if "res" in sp_param:
                suffix = "" # Ohm no unit
            elif "cap" in sp_param:
                suffix = "f"
            self.sp_params[sp_param] = SpParam(
                name = f"mlayer_{self.idx}_{sp_param}",
                value = attr_val,
                suffix = suffix,
            ) 
        # print(f"mlayer {self.idx} sp params:")
        # for k,v in self.self.sp_params.items():
        #     print(f"{k}: {v}")


@dataclass
class ViaStackInfo:
    """
        Information for a stack of vias connecting two metal layers.

        Attributes:
            mlayer_range: List of two integers representing the metal layers the via stack connects
                e.g. [1, 5] to connect M1 -> M5
            res: Via stack resistance in Ohms
            cap: Via stack capacitance in fF
            height: Height of the via stack in nm
            avg_mlayer_cap_per_um: Average capacitance per unit length of the metal layers in fF / um
            sp_params: Spice parameters for the via stack
    """
    mlayer_range: List[int]
    res: float # Ohm
    height: float # nm
    avg_mlayer_cap_per_um: float # fF / um
    # Spice Info for Via Stack
    cap: float = None # fF
    sp_params: dict = field(default_factory = lambda: {})
    def __post_init__(self):
        """
            Initializes:
                * `cap`
                * `sp_params`
            From data dependancies:
                * `self.height`
                * `self.avg_mlayer_cap_per_um`
        """
        # This is a rough (conservative estimation for via capacitance, probably much lower than this)
        self.cap = (self.height * 1e-3) * (self.avg_mlayer_cap_per_um)
        for sp_param in ["res", "cap"]:
            attr_val = getattr(self, sp_param)
            if "res" in sp_param:
                suffix = ""
            elif "cap" in sp_param:
                suffix = "f"
            self.sp_params[sp_param] = SpParam(
                name = f"via_stack_{sp_param}_m{self.mlayer_range[0]}_to_{self.mlayer_range[1]}_to",
                value = attr_val,
                suffix = suffix,
            )


@dataclass
class TxGeometryInfo:
    """ 
        Geometry information for a single transistor of a process

        Attributes:
            min_tx_contact_width: Minimum width of the transistor contact in nm
            tx_diffusion_length: Diffusion length of the transistor in nm
            gate_length: Gate length of the transistor in nm
            min_width_tx_area: Minimum width of the transistor area in nm^2
            sp_params: Spice parameters for the transistor
    """
    # hfin: float # nm TODO figure out if this is needed
    min_tx_contact_width: float # nm
    tx_diffusion_length: float # nm
    gate_length: float # nm
    min_width_tx_area: float # nm^2
    sp_params: dict = field(default_factory = lambda: {})
    def __post_init__(self):
        """
            Initializes:
                * `sp_params`

        """
        sp_params = [field.name for field in fields(self) if field.name != "sp_params"]
        for sp_param in sp_params:
            attr_val = getattr(self, sp_param)
            suffix = "n"
            self.sp_params[sp_param] = SpParam(
                name = f"{sp_param}",
                value = attr_val,
                suffix = suffix,
            )

@dataclass
class ProcessInfo:
    """
        Represents a PDK with metal layer and Transistor geometry information

        Attributes:
            * name: Name of the process 
            * num_mlayers: Number of metal layers in the process
            * mlayers: List of MlayerInfo objects for each metal layer in the process
            * contact_poly_pitch: Pitch of the contact poly in nm
            * via_stack_infos: List of ViaStackInfo objects for each via stack in the process
            * tx_geom_info: TxGeometryInfo object for the process
    """
    name: str
    num_mlayers: int
    mlayers: List[MlayerInfo]
    contact_poly_pitch: float # nm
    via_stack_infos: List[ViaStackInfo]
    tx_geom_info: TxGeometryInfo


########################## GENERAL PROCESS INFORMATION ###########################


########################## PDN MODELING ###########################
@dataclass
class GridCoord:
    """
        Grid Coordinate for a 2D space
    """
    x: float
    y: float

@dataclass
class RectBB:
    """
        Rectangular bounding box object used to represent an object in 2D space like a TSV

        Attributes:
            p1: bottom left corner of the bounding box      <TAG><TODO-VERIFY-COMMENT>
            p2: top right corner of the bounding box        <TAG><TODO-VERIFY-COMMENT>
            bb: shapely polygon object representing the bounding box
            label: label for what this BB represents
    """
    p1 : GridCoord
    p2 : GridCoord
    # label for what this BB represents
    bb : sh.Polygon
    # tsv_grid -> "TSV" "KoZ"
    # C4_grid -> "PWR" "GND" "IO"
    label : str

@dataclass
class GridPlacement:
    """
        Used for representing a grid of objects in a 2D grid space. e.g. TSVs, C4 bumps, etc

        Attributes:
            start_coord: GridCoord object representing the bottom left corner of the grid in plane
            h: horizontal distance in um for each TSV
            v: vertical distance in um for each TSV
            s_h: horizontal distance between tsvs in um
            s_v: vertical distance between tsvs in um
            dims: List of two integers representing the dimensions of the grid. e.g. [10, 10] for a 10x10 grid
            grid: list of list of Rectangle objects indexed by [col][row]
            tag: tag for what this grid is representing
            area: area of the grid in um^2 (unsure if used or where its set) <TAG><TODO-VERIFY-COMMENT>
            bb_poly: shapely Polygon object representing the bounding box of the whole grid
    """
    start_coord: GridCoord
    # vertical and horizontal distance in um for each TSV
    h: float 
    v: float
    # vertical and horizontal distance bw tsvs in um 
    s_h: float
    s_v: float
    dims: List[int]
    # grid start and end in um
    grid: List[List[RectBB]] = None
    # fig: go.Figure = go.Figure()
    tag: str = None # used to identify what this grid is for
    area: float = None # area of the grid in um^2
    bb_poly: sh.Polygon = None # Polygon containing a bounding box for the grid (xmin, ymin, xmax, ymax)
    def __post_init__(self) -> None:
        """
            Initializes:
                * `self.grid`
                * `self.bb_poly`
        """
        self.grid = [[None]*self.dims[1] for _ in range(self.dims[0])]
        for col in range(self.dims[0]):
            for row in range(self.dims[1]):
                self.grid[col][row] = RectBB(
                    p1 = GridCoord(
                        x = self.start_coord.x + col*(self.s_h),
                        y = self.start_coord.y + row*(self.s_v),
                    ),
                    p2 = GridCoord(
                        x = self.start_coord.x + col*(self.s_h) + self.h,
                        y = self.start_coord.y + row*(self.s_v) + self.v,
                    ),
                    bb = sh.box(
                        xmin = self.start_coord.x + col*(self.s_h),
                        ymin = self.start_coord.y + row*(self.s_v),
                        xmax = self.start_coord.x + col*(self.s_h) + self.h,
                        ymax = self.start_coord.y + row*(self.s_v) + self.v,
                    ),
                    label = None,
                )
        poly_bbs = [ rect.bb for rows in self.grid for rect in rows ]
        self.bb_poly = sh.Polygon(
            [
                (min(x for x,_,_,_ in [poly.bounds for poly in poly_bbs]), min(y for _,y,_,_ in [poly.bounds for poly in poly_bbs])), # BL pos (xmin, ymin)
                (min(x for x,_,_,_ in [poly.bounds for poly in poly_bbs]), max(y for _,_,_,y in [poly.bounds for poly in poly_bbs])), # TL pos (xmin, ymax)
                (max(x for _,_,x,_ in [poly.bounds for poly in poly_bbs]), max(y for _,_,_,y in [poly.bounds for poly in poly_bbs])), # TR pos (xmax, ymax)
                (max(x for _,_,x,_ in [poly.bounds for poly in poly_bbs]), max(y for _,y,_,_ in [poly.bounds for poly in poly_bbs])) # BR pos (xmax, ymin)
            ]
        )
    def gen_fig(self, 
        fig: go.Figure, 
        fill_color: str, 
        opacity: str, 
        label_filt: str = None, 
        layer: str = "above", 
        line_color: str = "black"
    ) -> None:
        """
            Generates a plotly figure of the grid. Modifies the input `fig` argument

            Args:
                fig: Plotly figure object to add the grid to
                fill_color: Fill color for the grid
                opacity: Opacity of the grid
                label_filt: Filter for the label of the grid
                layer: Layer to plot the grid on
                line_color: Line color for
            
        """
        for col in range(self.dims[0]):
            for row in range(self.dims[1]):
                if label_filt is None or self.grid[col][row].label == label_filt:
                    fig.add_shape(
                        type="rect",
                        x0 = self.grid[col][row].bb.bounds[0],
                        y0 = self.grid[col][row].bb.bounds[1],
                        x1 = self.grid[col][row].bb.bounds[2],
                        y1 = self.grid[col][row].bb.bounds[3],
                        line = dict(
                            color = line_color,
                            width = 1,
                        ),
                        opacity = opacity,
                        fillcolor = fill_color,
                        layer = layer,
                    )


@dataclass
class SingleTSVInfo:
    """
        Information for a single TSV

        Attributes:
            height: Height of the TSV in um
            diameter: Diameter of the TSV in um
            pitch: Pitch of the TSV grid in um
            resistivity: Resistivity of the TSV in Ohm * um
            keepout_zone: Keepout zone of the TSV in um
            area: Area of the TSV in um^2
            resistance: Resistance of the TSV in Ohm
    """
    height: int #um
    diameter: int #um
    pitch: int #um
    resistivity: float # Ohm * um
    keepout_zone: float #um (adds to diameter)
    area: float = None # um^2
    resistance: float = None # Ohm
    def __post_init__(self):
        """
            Initializes:
                * `self.area`
            Data dependancies:
                * `self.diameter`
        """
        self.area = (self.diameter**2)
        # self.resistance = self.resistivity * self.height / (self.diameter**2)


@dataclass
class PolyPlacements:
    """
        This dataclass is used for representing a list of polygons in a 2D space
    
        Attributes:
            rects: List of RectBB objects representing the polygons
            tag: tag for what this grid is representing
            area: area of the grid in um^2 (unsure if used or where its set) <TAG><TODO-VERIFY-COMMENT>
            bb_poly: shapely Polygon object representing the bounding box of the whole grid
    
    """
    # grid start and end in um
    rects: List[RectBB] = None
    tag: str = None # used to identify what this grid is for
    area: float = None # area of the grid in um^2
    bb_poly: sh.Polygon = None # Polygon containing a bounding box for the grid (xmin, ymin, xmax, ymax)

    def gen_fig(
            self, 
            fig: go.Figure, 
            fill_color: str, 
            opacity: str, 
            label_filt: str = None, 
            layer: str = "above", 
            line_color: str = "black"
    ) -> None:
        """
            Generates a plotly figure of the grid. Modifies the input `fig` argument

            Args:
                fig: Plotly figure object to add the grid to
                fill_color: Fill color for the grid
                opacity: Opacity of the grid
                label_filt: Filter for the label of the grid
                layer: Layer to plot the grid on
                line_color: Line color for
        """
        for rect in self.rects:
            if label_filt is None or rect.label == label_filt:
                fig.add_shape(
                    type="rect",
                    x0 = rect.bb.bounds[0],
                    y0 = rect.bb.bounds[1],
                    x1 = rect.bb.bounds[2],
                    y1 = rect.bb.bounds[3],
                    line = dict(
                        color = line_color,
                        width = 1,
                    ),
                    opacity = opacity,
                    fillcolor = fill_color,
                    layer = layer,
                )

@dataclass
# per C4 bump TSV info
class TSVInfo:
    """
        Information for the TSV grid

        Attributes:
            * single_tsv: SingleTSVInfo object for a single TSV
            * placement_setting: mode of operation for the TSV grid ("dense" or "checkerboard")
            * koz_grid: GridPlacement object for the KoZ grid, need to figure out if this is used <TAG><TODO-VERIFY-COMMENT>
            * tsv_grid: GridPlacement object for the TSV grid, need to figure out if this is used <TAG><TODO-VERIFY-COMMENT>
            * tsv_rect_placements: PolyPlacements object for the TSV grid, figure out where this is used
            * koz_rect_placements: PolyPlacements object for the KoZ grid, figure out where this is used
            * dims: List of two integers representing the dimensions of the grid. e.g. [10, 10] for a 10x10 grid
            * area_bounds: List of two floats representing the maximum x and y bounds of the grid in um
            * resistance: Resistance of the TSV grid in Ohms

    """
    single_tsv: SingleTSVInfo
    placement_setting: str # "dense" or "checkerboard"
    koz_grid: GridPlacement
    # koz_area: float # um^2
    # koz_bb_poly: sh.Polygon # polygon containing KoZ bounding box surrounding grid
    tsv_grid: GridPlacement
    # list of tsv relevant polygons (this is a way to more easily access the polygons rather than being forced to conform to grid)
    tsv_rect_placements: PolyPlacements = None
    koz_rect_placements: PolyPlacements = None
    # 
    dims: List[int] = None # [x, y] dimensions of grid
    area_bounds: List[float] = None # [xmax, ymax]
    # tsv_area: float # um^2
    # tsv_bb_poly: sh.Polygon # polygon containing TSV bounding box surrounding grid
    # for grid of TSVs
    resistance: float = None # Ohm
    
    def calc_resistance(self) -> float:
        return self.single_tsv.resistance / len(self.tsv_rect_placements.rects)



@dataclass
class SingleC4Info:
    """
        Information for a single C4 bump

        Attributes:
            height: Height of the C4 bump in um
            diameter: Diameter of the C4 bump in um
            pitch: Pitch of the C4 grid in um
            area: Area of the C4 bump in um^2
            resistance: Resistance of the C4 bump in Ohms
    """
    height: int #um
    diameter: int #um
    pitch: int #um 
    area : float # um^2
    resistance: float = None
    def __post_init__(self):
        self.area = (self.diameter**2)

@dataclass
class C4Info:
    """
        Information for the C4 grid. C4 bumps connect the package to interposer.

        Attributes:
            single_c4: Information for a single C4 bump
            placement_setting: mode of operation for the C4 grid ("dense" or "checkerboard")
            margin: Margin between edge of device and start of C4 grid in um
            grid: GridPlacement object for the C4 grid
            max_c4_placements: PolyPlacements object containing the maximum number of C4s for a given die area
            max_c4_dims: List of two integers representing the max dimensions for a given die area
            pdn_dims: List of two integers representing the dimensions of the power deliver network on C4 bumps 
    """
    single_c4: SingleC4Info
    placement_setting: str # "dense" or "checkerboard"
    # margin between edge of device and start of C4 grid
    margin : int #um
    grid: GridPlacement # grid of C4s
    max_c4_placements: PolyPlacements = None # list of PolyPlacements containing max C4s for each device size
    max_c4_dims: List[int] = None # dimensions of C4 bumps based on device size
    # Used for calculating the FPGA floorplan
    pdn_dims: List[int] = None 


################## REPEAT OF C4 INFO FOR UBUMPS ##################
################## TODO update to use a single metal bump class ##################

@dataclass
class SolderBumpInfo:
    height: float
    diameter: float
    pitch: float
    res : float
    cap : float
    area : float = None
    bump_per_sq_um : float = None
    # for ubump "ubump" for c4 "c4", etc
    tag : str = None
    sp_params : dict = field(default_factory = lambda: {})
    def __post_init__(self): 
        # square area
        self.area = (self.diameter**2)
        # initialze sp params
        for sp_param in ["res","cap"]:
            attr_val = getattr(self, sp_param)
            if "res" in sp_param:
                suffix = "" # Ohm no unit
            elif "cap" in sp_param:
                suffix = "f"
            self.sp_params[sp_param] = SpParam(
                name = f"{self.tag}_{sp_param}",
                value = attr_val,
                suffix = suffix,
            )


@dataclass
class SingleUbumpInfo:
    height: float
    diameter: float
    pitch: float
    # resistivity: float 
    resistance: float = None
    area: float = None
    def __post_init__(self): 
        self.area = (self.diameter**2)
        # self.resistance = self.resistivity * self.height / (self.diameter**2)
@dataclass
class UbumpInfo:
    single_ubump: SingleUbumpInfo
    margin : float #um
    grid: GridPlacement #
    max_dims: List[int] = None #
################## REPEAT OF C4 INFO FOR UBUMPS ##################


@dataclass
class PwrRailInfo:
    # contains the percentage of each metal layer which pdn occupies
    # pitch_fac: float # pitch factor for power gnd rails
    mlayer_dist: List[float] # should be of length num_mlayers
    num_mlayers: int


@dataclass
class PDNSimSettings:
    plot_settings: dict = field(default_factory = lambda: {
        "tsv_grid" : False,
        "c4_grid" : False,
        "power_region": False,
        "pdn_sens_study": False,
    })


######################## GENERATING FPGA SECTOR FLOORPLAN ########################
@dataclass
class Coord:
    """
        Integer coordinate point
    """
    x: int
    y: int

@dataclass
class BlockRegion:
    """
        Region of a block in a sector

        Attributes:
            resource_tag: what type of resource does this represent in the fpga fabric options are ["dsp", "bram", "lb", "io", "gnd", "pwr"]
            pwr_region_coord: Coord object representing the power region coordinate <TAG><TODO-VERIFY-COMMENT>
            sector_coord: Coord object representing the sector coordinate <TAG><TODO-VERIFY-COMMENT>
    """
    resource_tag: str # "dsp", "bram", "lb", "io", "gnd", "pwr"
    pwr_region_coord: Coord # coord in grid of power regions
    sector_coord: Coord 

# TODO deletion candidate
# @dataclass
# class PwrRegion:
#     # abs_dims: List[float] # [width, height]
#     # Grid of LB sized regions occupied by various types of blocks
#     blocks: List[List[BlockRegion]] = None


@dataclass 
class SectorInfo:
    """
        Information for a sector in the FPGA fabric
        
        Attributes:
            width: width of the sector in LB tiles
            height: height of the sector in LB tiles
            bram_cols: number of BRAM columns in the sector
            dsp_cols: number of DSP columns in the sector
            sector_grid: 2D list of BlockRegion objects representing the sector grid

        Todo:
            * Figure out what sector refers to
            * Integrate into FPGA floorplan generator
    """
    # All below are calculated from floorplan and TSVs
    width: int = None # in LB tiles
    height: int = None # in LB tiles
    bram_cols: int = None
    dsp_cols: int = None
    abs_area: float = None # um^2
    sector_grid: List[List[BlockRegion]] = None
    # pwr_regions: List[List[PwrRegion]] = None

@dataclass
class FPGAResource:
    """
        Information for a resource in the FPGA fabric. e.g. LBs, DSPs, BRAMs

        Attributes:
            total_num: Total number of this type of resource in the FPGA
            abs_area: Absolute area of the resource in um^2
            rel_area: Relative area of the resource in LBs
            abs_width: Absolute width of the resource in um
            abs_height: Absolute height of the resource in um
    """
    total_num: int
    abs_area: float # um^2
    rel_area: int # area in LBs (assume aspect ratio of W / L = Area / 1)
    abs_width: float = None # um
    abs_height: float = None # um 

@dataclass
class FPGAInfo:
    """
        Information for the FPGA fabric

        Attributes:
            sector_info: SectorInfo object for the FPGA
            sector_dims: List of two integers representing the dimensions of the FPGA in sectors. e.g. [10, 10] for a 10x10 FPGA
            lbs: FPGAResource object for the LBs in the FPGA
            dsps: FPGAResource object for the DSPs in the FPGA
            brams: FPGAResource object for the BRAMs in the FPGA
            grid_height: Height of the FPGA in LB tiles
            grid_width: Width of the FPGA in LB tiles

    """
    sector_info: SectorInfo
    sector_dims: List[int] # [x, y] number of sectors
    lbs: FPGAResource 
    dsps: FPGAResource
    brams: FPGAResource
    # calculated below
    grid_height: int = None
    grid_width: int = None




def get_total_poly_area(boxes: List[sh.Polygon]) -> float:
    """ 
        Get total area of polygons, subtracts overlap area bw two bboxes (if any)

        Args:
            boxes: List of shapely Polygon objects representing the boxes

        Returns:
            total_coverage_area: Total area of the boxes in the list
    """
    # Create polygons for each rectangle
    polygons = [sh.Polygon(box.exterior.coords) for box in boxes]
    # Compute the total area of all polygons
    total_area = sum(poly.area for poly in polygons)
    # Compute the area of intersection between each pair of rectangles,
    # skipping pairs that have already been checked
    intersection_area = 0
    checked_pairs = set()
    for box1, box2 in combinations(range(len(boxes)), 2):
        if (box1, box2) in checked_pairs or (box2, box1) in checked_pairs:
            continue
        if polygons[box1].intersects(polygons[box2]):
            intersection_area += polygons[box1].intersection(polygons[box2]).area
        checked_pairs.add((box1, box2))
    # Subtract the area of intersection to get the total area covered by boxes
    total_coverage_area = total_area - intersection_area
    # print(f"total area: {total_area}, intersection area: {intersection_area}, total coverage area: {total_coverage_area}")
    return total_coverage_area


@dataclass
class DesignPDN:
    """
        Information relevant to the design of the power delivery network

        Attributes:
            floorplan: shapely Polygon object representing the floorplan of the design
            power_budget: Power budget of the design in W
            process_info: PDK information
            supply_voltage: Supply voltage of the design in V TODO should move into unified structure
            ir_drop_budget: IR drop budget of the design in mV
            fpga_info: FPGAInfo object for the FPGA
            tsv_info: TSV Grid info
            c4_info: C4 Grid info
            ubump_info: Micro bump Grid info
            pwr_rail_info: PDN Power rail
            pwr_region_dims: List of two integers representing the dimensions of the power regions. e.g. [10, 10] for a 10x10 grid 
            resistance_target: Target resistance of the PDN in mOhm
            current_per_tx: Current per transistor in A
            num_txs: number of transistors in the total design


    """
    ################ USER INPUTTED VALUES ################
    # Polygon containing the floorplan of the design (top and bottom die assumed to be the same)
    floorplan: sh.Polygon
    # Design Power Load (How many W power is the design taking in)
    power_budget: float # W
    #### COULD GO UNDER PROCESS PARAMS ####
    # Design Power Supply Voltage 
    process_info: ProcessInfo
    supply_voltage: float # V
    ir_drop_budget: float # mV
    fpga_info: FPGAInfo
    ################ GENERATED VALUES ################
    tsv_info: TSVInfo
    c4_info: C4Info
    ubump_info: UbumpInfo
    pwr_rail_info: PwrRailInfo
    pwr_region_dims: List[float] = None # [x, y] number of pwr regions
    resistance_target: float = None # mOhm 
    current_per_tx: float = None # A
    num_txs: int = None



    def init_placement(self, grid_pls: List[GridPlacement], area_inter: bool) -> PolyPlacements:
        """
            Initializes the placement of the grid

            Args:
                grid_pls: List of GridPlacement objects representing the grid
                area_inter: Boolean flag to determine if area is calculated with or without intersection
            
            Returns:
                pps: PolyPlacements object representing the placement of the grid
        """
        rects = [ rect for grid_pl in grid_pls for rows in grid_pl.grid for rect in rows ]
        polys = [ rect.bb for grid_pl in grid_pls for rows in grid_pl.grid for rect in rows ]
        if area_inter:
            area = get_total_poly_area(polys)
        else:
            area = sum(poly.area for poly in polys)
        bb_poly = sh.Polygon(
            [
                (min(x for x,_,_,_ in [poly.bounds for poly in polys]), min(y for _,y,_,_ in [poly.bounds for poly in polys])), # BL pos (xmin, ymin)
                (min(x for x,_,_,_ in [poly.bounds for poly in polys]), max(y for _,_,_,y in [poly.bounds for poly in polys])), # TL pos (xmin, ymax)
                (max(x for _,_,x,_ in [poly.bounds for poly in polys]), max(y for _,_,_,y in [poly.bounds for poly in polys])), # TR pos (xmax, ymax)
                (max(x for _,_,x,_ in [poly.bounds for poly in polys]), max(y for _,y,_,_ in [poly.bounds for poly in polys])) # BR pos (xmax, ymin)
            ]
        )
        # make sure the inputted placement is all of the same tag
        assert all(grid_pl.tag == grid_pls[0].tag for grid_pl in grid_pls)
        
        pps = PolyPlacements(
            rects = rects,
            bb_poly = bb_poly,
            area = area,
            # assumi
            tag = grid_pls[0].tag,
        )
        return pps

    def design_pdn_post_init(self) -> None:
        if self.c4_info.placement_setting == "dense":
            ######################################### MAX C4 GRID PLACEMENT INIT #########################################
            self.c4_info.max_c4_dims = [
                math.floor(((self.floorplan.bounds[2] - self.floorplan.bounds[0]) - self.c4_info.margin*2 + self.c4_info.single_c4.diameter) / self.c4_info.single_c4.pitch),
                math.floor(((self.floorplan.bounds[3] - self.floorplan.bounds[1]) - self.c4_info.margin*2 + self.c4_info.single_c4.diameter) / self.c4_info.single_c4.pitch) 
            ] 
            self.ubump_info.max_dims = [
                math.floor(((self.floorplan.bounds[2] - self.floorplan.bounds[0]) - self.ubump_info.margin*2 + self.ubump_info.single_ubump.diameter) / self.ubump_info.single_ubump.pitch),
                math.floor(((self.floorplan.bounds[3] - self.floorplan.bounds[1]) - self.ubump_info.margin*2 + self.ubump_info.single_ubump.diameter) / self.ubump_info.single_ubump.pitch) 
            ]
            c4_grid_placement = GridPlacement(
                start_coord=GridCoord(self.c4_info.margin,self.c4_info.margin),
                h=self.c4_info.single_c4.diameter,
                v=self.c4_info.single_c4.diameter,
                s_h=self.c4_info.single_c4.pitch,
                s_v=self.c4_info.single_c4.pitch,
                dims=self.c4_info.max_c4_dims,
                tag="C4"
            )
            self.c4_info.max_c4_placements = self.init_placement([c4_grid_placement], area_inter=False)
        elif self.c4_info.placement_setting == "checkerboard":
            ######################################### MAX C4 GRID PLACEMENT INIT #########################################
            self.c4_info.max_c4_dims = [
                math.floor(((self.floorplan.bounds[2] - self.floorplan.bounds[0]) - self.c4_info.margin*2 + self.c4_info.single_c4.diameter) / self.c4_info.single_c4.pitch * 2),
                math.floor(((self.floorplan.bounds[3] - self.floorplan.bounds[1]) - self.c4_info.margin*2 + self.c4_info.single_c4.diameter) / self.c4_info.single_c4.pitch * 2) 
            ] 
            self.ubump_info.max_dims = [
                math.floor(((self.floorplan.bounds[2] - self.floorplan.bounds[0]) - self.ubump_info.margin*2 + self.ubump_info.single_ubump.diameter) / self.ubump_info.single_ubump.pitch * 2),
                math.floor(((self.floorplan.bounds[3] - self.floorplan.bounds[1]) - self.ubump_info.margin*2 + self.ubump_info.single_ubump.diameter) / self.ubump_info.single_ubump.pitch * 2) 
            ] 
            # Setting MAX C4 Grid
            c4_outer_grid = GridPlacement(
                start_coord=GridCoord(self.c4_info.margin,self.c4_info.margin),
                h=self.c4_info.single_c4.diameter,
                v=self.c4_info.single_c4.diameter,
                s_h=self.c4_info.single_c4.pitch*2,
                s_v=self.c4_info.single_c4.pitch*2,
                dims=self.c4_info.max_c4_dims,
                tag="C4"
            )
            c4_inner_grid = GridPlacement(
                start_coord=GridCoord(self.c4_info.margin + self.c4_info.single_c4.pitch, self.c4_info.margin + self.c4_info.single_c4.pitch),
                h=self.c4_info.single_c4.diameter,
                v=self.c4_info.single_c4.diameter,
                s_h=self.c4_info.single_c4.pitch*2,
                s_v=self.c4_info.single_c4.pitch*2,
                dims=self.c4_info.max_c4_dims-1,
                tag="C4"
            )
            self.c4_info.max_c4_placements = self.init_placement([c4_outer_grid, c4_inner_grid], area_inter=False)
        
        # get resistance target
        self.resistance_target = (self.power_budget / self.supply_voltage) / self.ir_drop_budget
        # get num txs in design
        self.num_txs = math.floor(self.floorplan.area / (self.process_info.tx_geom_info.min_width_tx_area*1e-6))
        self.current_per_tx = (self.power_budget / self.supply_voltage) / self.num_txs

    def update(self) -> None:
        self.design_pdn_post_init()

    def __post_init__(self):
        self.design_pdn_post_init()


# TODO deletion candidate
# @dataclass
# class TSVGridPlacement:
#     start_coord: GridCoord
#     # vertical and horizontal distance in um for each TSV
#     tsv_h: float 
#     tsv_v: float
#     # vertical and horizontal distance bw tsvs in um 
#     tsv_s_h: float
#     tsv_s_v: float
#     dim: int
#     # grid start and end in um
#     tsv_grid : List[RectBB] = None
#     def __post_init__(self):
#         self.tsv_grid = [[None]*self.dim for _ in range(self.dim)]
#         for col in range(self.dim):
#             for row in range(self.dim):
#                 # bb of tsv coords 
#                 self.tsv_grid[col][row] = RectBB(
#                     p1 = GridCoord(
#                         x = self.start_coord.x + col*(self.tsv_s_h),
#                         y = self.start_coord.y + row*(self.tsv_s_v),
#                     ),
#                     p2 = GridCoord(
#                         x = self.start_coord.x + col*(self.tsv_s_h) + self.tsv_h,
#                         y = self.start_coord.y + row*(self.tsv_s_v) + self.tsv_v,
#                     ),
#                 )

@dataclass
class PDNModelingInfo:
    """
        Script paths to call `fpga21-scaled-tech` repo for RC calculations

        Todo:
            * Delete this structure and get these paths through trees
    """
    r_script_path: str = os.path.expanduser("~/3D_ICs/fpga21-scaled-tech/rc_calculations/custom_calc_resistance.py")
    c_script_path: str = os.path.expanduser("~/3D_ICs/fpga21-scaled-tech/rc_calculations/custom_calc_capacitance.py")

pdn_modeling_info = PDNModelingInfo()

########################## PDN MODELING ###########################





@dataclass
class TxSizing:
    """
        Buffer DSE transistor sizing information & HSPICE optimization

        Attributes:
            opt_mode: which transistor to optimize in a buffer design options are ["P", "NP", "N"]
            opt_goal: optimization goal options are ["tpd", "diff"] for (propegation delay) and (match the rising and falling propegation delays), respectively.
            pmos_sz: PMOS transistor size in fins
            nmos_sz: NMOS transistor size in fins
            p_opt_params: dict containing "init", "step", and "range" for optimization
            n_opt_params: dict containing "init", "step", and "range" for optimization
            iters: max iterations for optimization
    """
    opt_mode: str = None  # possible modes are "P", "NP" and "N" if one of those strings is included then the sizing for the respective PMOS / NMOS will be optimized by hspice
    opt_goal: str = None # options are "tpd" (propegation delay) or "diff" (match the rising and falling propegation delays)
    pmos_sz: int = None
    nmos_sz: int = None
    p_opt_params: dict = None
    n_opt_params: dict = None
    iters: int = None



@dataclass
class SpTestingModel:
    """
        Spice testbench object currently used for buffer_dse in "ic_3d" subtool

        Attributes:
            insts: List of SpSubCktInst objects representing the nodes inside the spice simulation
            vsrcs: List of SpVoltageSrc objects representing the voltage sources for the simulation
            dut_in_node: string representing the input node of the DUT
            dut_out_node: string representing the output node of the DUT
            opt_params: List of SpParam objects representing the optimization parameters used in the simulation
            static_params: List of SpParam objects representing the static parameters used in the simulation
            sim_settings: SpLocalSimSettings object representing the simulation settings
            target_freq: target frequency in MHz
    """
    # Design Info
    insts :  List[SpSubCktInst] # All nodes inside of the spice sim
    vsrcs: List[SpVoltageSrc]  = None # We create a basic voltage source for each instantiation to measure their power

    # Node definitions
    dut_in_node: str = "n_in" # input node (connected to non inst stimulus)
    dut_out_node: str = "n_out" # output node (hanging or connected to non inst stimulus)
    
    # Simulation Info
    opt_params: List[SpParam] = None # List of all optimization parameters used in simulation
    static_params: List[SpParam] = None # List of all static parameters used in simulation
    sim_settings: SpLocalSimSettings = None # Simulation settings
    # target_period: float = None # period in ns
    # voltage_src: SpVoltageSrc = None # voltage source for simulation
    
    # FIELDS WHICH ARE ONLY HERE TO WORK WITH OLD FUNCTIONS THAT I DESIRE TO GET RID OF 
    target_freq: int = None # freq in MHz

    def __post_init__(self):
        if self.sim_settings != None:
            if self.sim_settings.dut_in_vsrc.out_node is None:
                self.sim_settings.dut_in_vsrc.out_node = self.dut_in_node

    # TODO deletion candidate
    # sim_prec: int # samples in ps
    # Params swept in sp simulation
    # sweep_mlayer_trav_dist: SpParam = None # um
    # sweep_ubump_factor: SpParam = None # unitless
    # sweep_via_factor: int = None # unitless
    # sweep_mlayer_cap_per_um: SpParam = None # f/um
    # sweep_mlayer_res_per_um: SpParam = None # Ohm/um

    # sp_params : dict = field(default_factory = lambda: {})
    # def __post_init__(self): 
    #     # initialze sp params
    #     for sp_param in ["sweep_mlayer_trav_dist","sweep_ubump_factor"]:
    #         attr_val = getattr(self, sp_param)
    #         suffix = ""
    #         self.sp_params[sp_param] = SpParam(
    #             name = f"{sp_param}",
    #             value = attr_val,
    #             suffix = suffix,
    #         )

@dataclass
class SpPNOptModel:
    """
        inverter NP default parameter names.

        Todo:
            * Delete this struct, integrate into something else
    """
    wn_param : str = "inv_Wn"
    wp_param : str = "inv_Wp"


@dataclass
class SpSubCktLibs:
    """
        "ic_3d" subtool way of accessing spice subcircuit libraries

        Todo:
            * Delete this and use COFFE methodology to get subckt libraries
    """
    atomic_subckts: Dict[str, SpSubCkt] = None #= field(default_factory = lambda: sp_subckt_atomic_lib)
    basic_subckts: Dict[str, SpSubCkt] = None #= field(default_factory = lambda: basic_subckts)
    subckts: Dict[str, SpSubCkt] = None #= field(default_factory = lambda: subckts)

""" Here defines the top class used for buffer exploration """
@dataclass
class SRAMInfo:
    """
        BRAM geometry information used in BUFFER-DSE in "ic_3d" 
    """
    width: float # um
    height: float # um
    area: float = None # um^2
    def __post_init__(self):
        self.area = self.width * self.height


@dataclass
class PackageInfo:
    """
    Contains information about the package
    Ubumps / C4s / TSVs Etc ... 
    """
    ubump_info: SolderBumpInfo
    esd_rc_params: dict 
    # c4_info: SolderBumpInfo
    # tsv_info: TSVInfo


@dataclass
class HwModuleInfo:
    """
        Contains information about the HW Module
    """
    name: str
    area: float
    width: float
    height: float

@dataclass
class NoCInfo:
    area: float # um^2
    rtl_params: dict # RTL parameters

    lbs_per_router: float = None
    noc_lb_grid_sz: int = None
    noc_ubump_area: float = None

    max_num_ubumps: int = None
    needed_num_ubumps: int = None

    needed_lb_grid_sz: int = None
    add_wire_len: float = None

    def __post_init__(self):
        # Check if the RTL parameters are valid
        assert "flit_width" in self.rtl_params.keys()

    def calc_noc_info(self, lb_info: HwModuleInfo, ubump_pitch: float) -> None:
        self.lbs_per_router = math.ceil(self.area / lb_info.area)
        self.noc_lb_grid_sz = math.ceil(math.sqrt(self.lbs_per_router))
        self.noc_ubump_area = (math.ceil(math.sqrt(self.lbs_per_router))**2) * lb_info.area

        self.max_num_ubumps = math.floor((1/ubump_pitch**2) * self.noc_ubump_area)
        self.needed_num_ubumps = 2 * self.rtl_params["flit_width"]
        self.needed_lb_grid_sz = math.ceil(math.sqrt(self.needed_num_ubumps*(ubump_pitch**2)/lb_info.area))

        self.add_wire_len = max(math.ceil((math.ceil(math.sqrt(self.needed_num_ubumps * (ubump_pitch**2) / lb_info.area)) \
            - math.ceil(math.sqrt(self.lbs_per_router)) ) / 2) * (lb_info.width + lb_info.height), 0) 
        
@dataclass
class DesignInfo:
    """ 
        Contains information about the whole design relevant to the Buffer DSE mode in "ic_3d" subtool 
    """
    # Process information
    process_info: ProcessInfo

    # Circuit Library
    subckt_libs: SpSubCktLibs

    # Design Component Info
    srams: List[SRAMInfo]
    logic_block: HwModuleInfo

    # Buffer DSE information
    shape_nstages: int = None # num stages of the shape buffer, this is used to make the input signal coming from voltage source to be more realistic
    dut_buffer_nstages: int = None # num stages of the buffer driving the load we are testing, this is the buffer we are performing DSE on
    sink_die_nstages: int = None # number of stages of the buffer on an opposite die, which our load driver is sending signal to 
    total_nstages: int = None

    stage_ratio: int = None 

    # TODO remove this
    bot_die_nstages: int = 1

    nocs: List[NoCInfo] = None
    # Buffer related params 
    max_macro_dist: float = None # maximum distance a wire may have to traverse across a die before going to inter die connection (based on size of SRAM macros)
    add_wlen: float = None # Any additional wire length that could be added to this path between the two dies (pre ubump)

    # Package Info 
    package_info: PackageInfo = None

    # Additional Wire Length Calculation
    # lbs_per_router: float = None
    # noc_lb_grid: float = None
    # noc_ubump_area: float = None
    buffer_routing_mlayer_idx: int = None
    # add_wire_len: float = None
    def calc_add_wlen(self):
        for noc in self.nocs:
            noc.calc_noc_info(self.logic_block, self.package_info.ubump_info.pitch)

    def __post_init__(self):
        # self.total_nstages = self.shape_nstages + self.load_driver_nstages + self.sink_die_nstages
        # Find largest Macro in design, will have to route at least half the largest dimension on top metal layer
        self.max_macro_dist = max([sram.width/2 + sram.height/2 for sram in self.srams])  
        if self.add_wlen == None:
            self.add_wlen = 0


@dataclass
class Ic3dCLI(ParentCLI):
    """
        CLI arguments for IC-3D tool
    """
    cli_args: List[GeneralCLI] = field(default_factory = lambda: [
        GeneralCLI(key = "input_config_path", shortcut = "-ic" , datatype = str, help_msg = "path to ic_3d subtool specific configuration file"),
        GeneralCLI(key = "debug_spice", shortcut = "-ds" , datatype = str, nargs = "*", help_msg = "takes in path(s) named according to tile of spice sim, runs sim, opens waveforms and param settings for debugging"),
        GeneralCLI(key = "pdn_modeling", shortcut = "-pm", datatype = bool, action = "store_true", help_msg = "runs the PDN modeling flow"),
        GeneralCLI(key = "buffer_dse", shortcut = "-bd", datatype = bool, action = "store_true", help_msg = "runs the buffer DSE flow"),
        GeneralCLI(key = "buffer_sens_study", shortcut = "-bs", datatype = bool, action = "store_true", help_msg = "runs the buffer sensitivity study flow (sweeps parameters for buffer chain wire load, plots results)"),
    ])

# Use factory to create Args dataclass

ic_3d_cli = Ic3dCLI()
ic_3d_fields = ic_3d_cli.get_dataclass_fields()
IC3DArgs = get_dyn_class(
    cls_name = "IC3DArgs",
    fields = ic_3d_fields,
    bases= (Ic3dCLI,)
)


@dataclass
class Ic3d:
    # data common to RAD Gen
    common: Common # common settings for RAD Gen
    
    # CLI arguments (for modes)
    args: IC3DArgs

    # Buffer DSE specific data 
    # Should go into design info tbh TODO
    esd_rc_params: Dict[str, Any]
    add_wlens: List[float]

    # Buffer DSE input params
    stage_range: List[int] # range of buffer stages
    fanout_range: List[int] # range of buffer fanouts
    cost_fx_exps: Dict[str, int] # cost function weights
    tx_sizing: TxSizing # sizing info for transistors in buffer

    # Globals in 3D IC (should not be globals TODO)
    spice_info: SpInfo
    process_data: SpProcessData
    driver_model_info: DriverSpModel
    pn_opt_model: SpPNOptModel
    
    res: Regexes
    sp_sim_settings: SpGlobalSimSettings 
    design_info: DesignInfo
    process_infos: List[ProcessInfo]
    ubump_infos: List[SolderBumpInfo]

    # PDN specific data
    pdn_sim_settings: PDNSimSettings 
    design_pdn: DesignPDN



# To basically add forward declarations
if __name__ == "__main__":
    pass