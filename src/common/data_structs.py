from dataclasses import dataclass, field, fields, make_dataclass, MISSING
import os, sys

import re
from typing import Pattern, Dict, List, Any, Tuple, Union, Generator, Optional, Callable, Type
from datetime import datetime
import logging
from pathlib import Path

import argparse



from vlsi.hammer.hammer.vlsi.driver import HammerDriver


# IC 3D imports
import shapely as sh
import plotly.graph_objects as go
import plotly.subplots as subplots
import plotly.express as px
import math
from itertools import combinations


# ██████╗  █████╗ ██████╗        ██████╗ ███████╗███╗   ██╗
# ██╔══██╗██╔══██╗██╔══██╗      ██╔════╝ ██╔════╝████╗  ██║
# ██████╔╝███████║██║  ██║█████╗██║  ███╗█████╗  ██╔██╗ ██║
# ██╔══██╗██╔══██║██║  ██║╚════╝██║   ██║██╔══╝  ██║╚██╗██║
# ██║  ██║██║  ██║██████╔╝      ╚██████╔╝███████╗██║ ╚████║
# ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝        ╚═════╝ ╚══════╝╚═╝  ╚═══╝

def create_timestamp(fmt_only_flag: bool = False) -> str:
    """
        Creates a timestamp string in below format
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
        milliseconds=int(now.microsecond // 1e3)
    )
    dt_format = "%Y--%m--%d--%H--%M--%S--%f"

    retval = dt_format if fmt_only_flag else formatted_timestamp
    return retval



@dataclass
class ReportInfo:
    """
        Information relevant to report information and filenames 
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
    """
    wspace_re: Pattern = re.compile(r"\s+")
    find_params_re: Pattern = re.compile(f"parameter\s+\w+(\s|=)+.*;")
    find_defines_re: Pattern = re.compile(f"`define\s+\w+\s+.*")
    grab_bw_soft_bkt: Pattern = re.compile(f"\(.*\)")
    
    find_localparam_re: Pattern = re.compile(f"localparam\s+\w+(\s|=)+.*?;",re.MULTILINE|re.DOTALL)
    first_eq_re: Pattern = re.compile("\s=\s")
    find_soft_brkt_chars_re: Pattern = re.compile(f"\(|\)", re.MULTILINE)

    find_verilog_fn_re: Pattern = re.compile(f"function.*?function", re.MULTILINE|re.DOTALL)
    grab_verilog_fn_args: Pattern = re.compile(f"\(.*?\)",re.MULTILINE|re.DOTALL)
    find_verilog_fn_hdr: Pattern = re.compile("<=?")

    decimal_re: Pattern = re.compile("\d+\.{0,1}\d*",re.MULTILINE)
    signed_dec_re: Pattern = re.compile("\-{0,1}\d+\.{0,1}\d*",re.MULTILINE)
    sci_not_dec_re: Pattern = re.compile("\-{0,1}\d+\.{0,1}\d*[eE]{0,1}\-{0,1}\d+",re.MULTILINE)

    # IC 3D
    int_re : re.Pattern = re.compile(r"[0-9]+", re.MULTILINE)
    sp_del_grab_info_re: re.Pattern = re.compile(r"^.(?:(?P<var1>[^\s=]+)=\s*(?P<val1>-?[\d.]+)(?P<unit1>[a-z]+))?\s*(?:(?P<var2>[^\s=]+)=\s*(?P<val2>-?[\d.]+)(?P<unit2>[a-z]+))?\s*(?:(?P<var3>[^\s=]+)=\s*(?P<val3>-?[\d.]+)(?P<unit3>[a-z]+))?",re.MULTILINE)
    sp_grab_print_vals_re: re.Pattern = re.compile(r"^x.*?^y",re.DOTALL | re.MULTILINE) 
    sp_grab_inv_pn_vals_re: re.Pattern = re.compile(r"\s+\.param\s+(?P<name>inv_w[np]_\d+)\s+=\s+(?P<value>\d+\.\d+)\w*")
    # spice output file ".lis" regex matches
    sp_grab_tran_analysis_ub_str: str = r"\s*transient\s*analysis.*?\s*"
    sp_grab_tran_analysis_re: re.Pattern = re.compile(r"\s*transient\s*analysis.*?\s*\.title\s*", re.DOTALL)
    # line by line grabs either "measure" statements -> group 1 is name of parameter, group 2 is the value in scientific notation
    sp_grab_measure_re: re.Pattern = re.compile( r"\b(\w+)\s*=\s*(failed|not found|[-+]?\d*(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*(?:\w+)?(?=\s|$)" )
    # global grabs all ".param" statements -> group 1 is name of parameter, group 2 is the value in scientific notation
    sp_grab_param_re: re.Pattern = re.compile(r"\.param\s+([^\s=]+)\s*=\s*([+\-]?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)\s*\$")

    # COFFE parsing
    coffe_key_w_spaces_rep_re: re.Pattern = re.compile(r'^([^0-9]+)\s+([0-9.]+[eE]{0,1}[0-9-]+)$', re.MULTILINE)



@dataclass
class GeneralCLI:
    """
        Struct to contain all info related to all command line interface args used in RAD Gen
        - If !optional && default_val == None -> Throw Exception "Required argument <arg> not provided"
        - All boolean args defaulted to False
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

class DisplayablePath(object):

    # Usage Example:
    # paths_gen = DisplayablePath.make_tree(Path('/fs1/eecg/vaughn/morestep/rad_gen/unit_tests/outputs/coffe'), criteria=lambda p: p.is_dir())
    # path_strs = [gen.path.absolute() for gen in paths_gen]

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
    def make_tree(cls: Type['DisplayablePath'], root: Path, parent: Optional['DisplayablePath'] = None, is_last: bool = False, criteria: Optional[Callable[[Any], bool]]=None) -> Generator['DisplayablePath', None, None]:
        root = Path(str(root))
        criteria = criteria or cls._default_criteria

        displayable_root = cls(root, parent, is_last)
        yield displayable_root

        children = sorted(list(path
                               for path in root.iterdir()
                               if criteria(path)),
                          key=lambda s: str(s).lower())
        count = 1
        for path in children:
            is_last = count == len(children)
            if path.is_dir():
                yield from cls.make_tree(path,
                                         parent=displayable_root,
                                         is_last=is_last,
                                         criteria=criteria)
            else:
                yield cls(path, displayable_root, is_last)
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
        Linux directory structure for building directory trees and referencing them
    
        Tags for parent trees apply to subtrees like so:
            parent_tag/subtree_tag

        Tags:
            - obj : object directory
            - 
    """


    def __init__(self, root: str, subtrees: List['Tree'] = None, tag: str = None):
        self.root : Union[str, None] = root
        self.basename : Union[str, None] = os.path.basename(root) if root else None
        self.subtrees : Union[List['Tree'], None] = subtrees
        self.tag : Union[str, None] = tag
        self.is_leaf : bool = False
        
        if self.subtrees == None:
            self.is_leaf = True
        else:
            self.is_leaf = False
    
        if self.subtrees and root:
            for subdir in self.subtrees:
                # Recursively goes down all depths
                self.update_subdir_paths(subdir, self.root)

    def update_subdir_paths(self, dir, parent_path):
        if parent_path:
            dir.root = os.path.join(parent_path, dir.root)

        if dir.subtrees:
            for subdir in dir.subtrees:
                subdir.root = os.path.join(parent_path, subdir.root)
                self.update_subdir_paths(subdir, subdir.root)

    def display_tree(self):
        paths = DisplayablePath.make_tree(Path(self.root))
        for path in paths:
            print(path.displayable())

    def search_subtrees(self, target_tag: str, target_depth: int = None):
        result = []
        self._search_subtrees(target_tag, target_depth, 0, result)
        return result

    def _search_subtrees(self, target_tag, target_depth, current_depth, result):
        # If we want to search all depths we set target depth to None
        if (current_depth == target_depth or target_depth == None) and self.tag == target_tag:
            result.append(self)

        if self.subtrees and (current_depth < target_depth or target_depth == None):
            for subtree in self.subtrees:
                subtree._search_subtrees(target_tag, target_depth, current_depth + 1, result)


# Accessing the directory structure like a dictionary
def get_dir(directory: Tree, *keys):
    if not keys:
        return directory

    key_to_find = keys[0]
    if directory.subtrees:
        for subdir in directory.subtrees:
            if subdir.basename == key_to_find:
                return get_dir(subdir, *keys[1:])

    return None


def add_arg(parser: argparse.ArgumentParser, cli_opt: GeneralCLI):    
    # Create list to deal with optional shortcut
    key_keys = ["key", "shortcut"]
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

    # All user input fields which exist in a dynamic dataclass, and originate from CommonCLI
    args: Any = None 
    # Paths
    rad_gen_home_path: str = None
    hammer_home_path: str = None
    # openram_home_path: str = None
    # Logging
    log_fpath: str = f"rad-gen-{create_timestamp()}.log" # path to log file for current RAD Gen run
    logger: logging.Logger = logging.getLogger(log_fpath) # logger for RAD Gen
    # Verbosity level
    # 0 - Brief output
    # 1 - Brief output + I/O + command line access
    # 2 - Hammer and asic tool outputs will be printed to console 
    log_verbosity: int = 1 # verbosity level for log file 

    # obj_dir : str = None # path to obj directory for current RAD Gen run
    
    # Input / Output directory structures
    input_tree_top: Tree = None
    output_tree_top: Tree = None

    # ASIC-DSE
    # Directory structure for asic-dse hammer asic flow
    """
    input_dir_struct: dict = field(default_factory = lambda: {
        # Design configuration files
        "configs": {
            # Auto-generated configuration files from sweep
            "gen" : "gen",
            # Tmp directory for storing modified configuration files by user passing in top_lvl & hdl_path & original config 
            "mod" : "mod",
        },
        # Design RTL files
        "rtl" : {
            "gen" : "gen", # Auto-generated directories containing RTL
            "src" : "src", # Contains design RTL files
            "include": "include", # Contains design RTL header files
            "verif" : "verif", # verification related files
            "build" : "build", # build related files for this design
        }
    })
    """

    # Global regex struct
    res: Regexes = field(default_factory = Regexes)

    # Global report info struct
    report: ReportInfo = field(default_factory = ReportInfo)


class MetaDataclass(type):
    fields_dtypes = {}
    fields_defaults = {}

    def __new__(cls, name, bases, namespace):
        # Add fields to the dataclass dynamically
        for field_name, field_type in cls.fields_dtypes.items():
        # for field_name, field_type in namespace["__annotations__"].items():
            namespace[field_name] = field_type
        
        cls_obj = dataclass(super().__new__(cls, name, bases, namespace))
        return cls_obj




@dataclass 
class ParentCLI:
    cli_args: List[GeneralCLI] = None
    arg_definitions: List[Dict[str, Any]] = None

    # Below are used for dynamic dataclass creation and initialization
    _fields: Dict[str, Any] = None # key, datatype pairs for all fields in this dataclass
    _defaults: Dict[str, Any] = None # key, default_val pairs for all fields in this dataclass

    def __post_init__(self):
        # Post inits required for structs that use other struct values as inputs and cannot be clearly defined
        # Call factory defaults to generate the default values for the dataclass
        # for field in fields(self):
        #     if field.default_factory != MISSING:
        #         setattr(self, field.name, field.default_factory())
        # If cli_args still not generated we use the arg_definitions to generate them
        if self.cli_args == None:
            self.cli_args = [ GeneralCLI(**arg_dict) for arg_dict in self.arg_definitions ]
        self._fields = {_field.key : _field.datatype for _field in self.cli_args}
        self._defaults = {_field.key : _field.default_val for _field in self.cli_args}
    
    def get_dataclass_fields(self, is_cli: bool = False) -> Dict[str, List[Any]]:
        """
            Returns the dynamic (defined in _fields) and static (defined in dataclass) to instantiate the dynamic dataclass
        """
        # To deal with problem of "." character being invalid for field names we replace it with double underscore here, has to be converted back to "." when cli args are written to console
        for key in self._fields.copy().keys():
            if "." in key:
                self._fields[key.replace(".", "__")] = self._fields.pop(key)
        # Adds the dynamic fields propegated from cli_args to the dataclass
        keys = list(self._fields.keys())
        dtypes = list(self._fields.values())
        defaults = list(self._defaults.values())
        # A behavior that is convenient is to be able to instantiate the dataclass with the same fields as the cli_args, which can store all operation modes for a subtool
        if not is_cli:
            # All statically defined fields in the original dataclass added here
            for field in fields(self):
                keys += [field.name]
                dtypes += [field.type]
                # If the field has a default factory we call it to get the default value
                defaults += [field.default_factory() if field.default == MISSING and field.default_factory != None else field.default]
            
        return {"keys" : [_key for _key in keys], "dtypes": [_dtype for _dtype in dtypes], "defaults": [_default for _default in defaults] }

def dyn_dataclass_init(self, **kwargs):
    """
        Dynamically initializes a dataclass with the provided keyword arguments
        - When creating a new dynamic dataclass set the __init__ namespace key to this function
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
# fields: Dict[str, List[Any]],
def get_dyn_class(cls_name: str, fields: Dict[str, List[Any]],  bases: Tuple[Any] = None):
    fields_dtypes = dict(zip(fields["keys"], fields["dtypes"]))
    fields_defaults = dict(zip(fields["keys"], fields["defaults"]))
    
    MetaDataclass.fields_dtypes = fields_dtypes
    MetaDataclass.fields_defaults = fields_defaults
    
    # if no base classes just pass empty tuple
    bases_arg = () if bases == None else bases

    return MetaDataclass(cls_name, bases_arg, 
                       {"__annotations__": fields_dtypes, #+ base_fields["dtypes"], 
                        "__dataclass_fields_defaults__": fields_defaults, #+ base_fields["defaults"],
                        "__dataclass_fields__": fields_dtypes.keys(), #+ base_fields["keys"],
                        "__init__": dyn_dataclass_init})
    

@dataclass
class CommonCLI(ParentCLI):
    """
        Path related settings which could be relevant to multiple subtools
    """
    cli_args : List[GeneralCLI] = field(default_factory = lambda: [ 
        GeneralCLI(key = "subtools", shortcut="-st", datatype = str, nargs = "*", help_msg = "subtool to run"),
        GeneralCLI(key = "top_config_path", shortcut = "-tc", datatype = str, help_msg = "path to (optional) RAD-GEN top level config file"),
        GeneralCLI(key = "use_latest_obj_dir", shortcut = "-l", datatype = bool, action = "store_true", help_msg = "Uses latest obj / work dir found in the respective output dir"),
        GeneralCLI(key = "manual_obj_dir", shortcut = "-o", datatype = str, help_msg = "Uses user specified obj dir"),
        GeneralCLI(key = "input_tree_top_path", shortcut = "-itree", datatype = str, help_msg = "path to top level dir containing input designs"),
        GeneralCLI(key = "output_tree_top_path", shortcut = "-otree", datatype = str, help_msg = "path to top level dir which outputs will be produced into, will have a subdir for each subtool"),
    ])
    arg_definitions: List[Dict[str, Any]] = field(default_factory = lambda: [ 
        {"key": "use_latest_obj_dir", 
            "shortcut": "-l", "action": "store_true", "help_msg": "Uses latest obj / work dir found in the respective output dir"},
        
        {"key": "manual_obj_dir",
            "shortcut": "-o", "datatype": str, "help_msg": "Uses user specified obj dir"},
        
        {"key": "input_tree_top_path",
            "shortcut": "-itree", "datatype": str, "help_msg": "path to top level dir containing input designs"},

        {"key": "output_tree_top_path",
            "shortcut": "-otree", "datatype": str, "help_msg": "path to top level dir which outputs will be produced into, will have a subdir for each subtool"},
        
    ])

    """
        gen_log: bool = False # generate log file
        input_tree_top_path: str = None
        output_tree_top_path: str = None
    """

common_cli = CommonCLI()
# Make a custom dataclass for common input arguments
AsicDseArgs = get_dyn_class(
    cls_name = "AsicDseArgs",
    fields = common_cli.get_dataclass_fields(),
    bases= (CommonCLI, )
)


@dataclass
class RadGenCLI(ParentCLI):
    
    cli_args: List[GeneralCLI] = field(default_factory = lambda: [ 
        GeneralCLI(key = "subtools", shortcut="-st", datatype = str, nargs = "*", help_msg = "subtool to run"),
        GeneralCLI(key = "top_config_path", shortcut = "-tc", datatype = str, help_msg = "path to (optional) RAD-GEN top level config file"),
        GeneralCLI(key = "use_latest_obj_dir", shortcut = "-l", datatype = bool, action = "store_true", help_msg = "Uses latest obj / work dir found in the respective output dir"),
        GeneralCLI(key = "manual_obj_dir", shortcut = "-o", datatype = str, help_msg = "Uses user specified obj dir"),
        GeneralCLI(key = "input_tree_top_path", shortcut = "-itree", datatype = str, help_msg = "path to top level dir containing input designs", default_val = os.path.expanduser(f"{os.environ['RAD_GEN_HOME']}/unit_tests/inputs")),
        GeneralCLI(key = "output_tree_top_path", shortcut = "-otree", datatype = str, help_msg = "path to top level dir which outputs will be produced into, will have a subdir for each subtool", default_val = os.path.expanduser(f"{os.environ['RAD_GEN_HOME']}/unit_tests/outputs")),
    ])
    arg_definitions: List[Dict[str, Any]] = field(default_factory = lambda: [ 
        {"key": "top_config_path", 
            "shortcut": "-tc", "datatype": str, "help_msg": "path to (optional) RAD-GEN top level config file"},

        {"key": "subtools",
            "shortcut": "-st", "datatype": str, "nargs": "*", "help_msg": "subtool to run"},
    ])

    """
        top_config_path: str = None # Optional top config path that can be used to pass cli args to RAD Gen
        subtools: List[str] = None # Possible subtool strings: "ic_3d" , "asic_dse", "coffe"
    """
    subtool_args: Any = None # Options would be the cli classes for each subtool
    no_use_arg_list: List[str] = None # list of arguments which should not be used in the command line interface

    def decode_dataclass_to_cli(self, cmd_str: str, _field: str, args_dict: Dict[str, str], obj: Any = None): #-> Tuple[str, List[str]]:
        if obj == None:
            obj = self
        val = getattr(obj, _field)
        # Make sure the value is not its default value or None / False (initial values)
        if val != None and val != False:
            # This dict is used to be able to do something like "import rad_gen" "rad_gen.main(**sys_args_dict)" to call rad gen from another python script
            # This in a different if statement as it sets up for the next if by converting value to str if its a list
            if isinstance(val, list):
                args_dict[_field] = val.copy()
                val = " ".join(val)
            else:
                args_dict[_field] = val
            # Be careful bools can be positivly evaluated as strings as well so this should be above the str eval
            if isinstance(val, bool):
                cmd_str += f" --{_field}"
            elif isinstance(val, str) or isinstance(val, int) or isinstance(val, float):    
                cmd_str += f" --{_field} {val}"
            else:
                raise Exception(f"Unsupported type for {_field} in {obj}")
        return cmd_str

    def get_rad_gen_cli_cmd(self, rad_gen_home: str) -> Tuple[str, List[str], Dict[str, str]]:
        sys_args_dict = {}
        sys_args = []
        cmd_str = f"python3 {rad_gen_home}/rad_gen.py"
        for _field in self.__class__.__dataclass_fields__:
            # List of arguments derived from cli_args are the only ones we should use to call RAD-Gen
            # Also don't pass argument values if they are the defaults that already exist in the CLI defs
            cli_default = next((cli_field.default_val for cli_field in self.cli_args if cli_field.key == _field), None) # This gets default value for the feild in question
            if _field in [ cli_field.key for cli_field in self.cli_args ] and getattr(self, _field) != cli_default: #!= "no_use_arg_list":
                # no use arg list is used specifically to skip an otherwise valid argument in the cli call  
                if not ( self.no_use_arg_list != None and ( _field in self.no_use_arg_list ) ):
                    cmd_str = self.decode_dataclass_to_cli(cmd_str = cmd_str, _field = _field, args_dict = sys_args_dict)
        if self.subtool_args != None:
            for _field in self.subtool_args.__dataclass_fields__:
                cli_default = next((cli_field.default_val for cli_field in self.subtool_args.cli_args if cli_field.key == _field), None) # This gets default value for the feild in question
                # List of arguments derived from subtool cli_args are the only ones we should use to call the subtool
                if _field in [ _field.key for _field in self.subtool_args.cli_args ] and getattr(self.subtool_args, _field) != cli_default: # != "no_use_arg_list":
                    if not (self.no_use_arg_list != None and ( _field in self.no_use_arg_list ) ):
                        cmd_str = self.decode_dataclass_to_cli(obj = self.subtool_args, cmd_str = cmd_str, _field = _field, args_dict = sys_args_dict)
        sys_args = cmd_str.split(" ")[2:] # skip over the <python3 rad_gen.py>
        return cmd_str, sys_args, sys_args_dict
    
    # def __post_init__(self):
    #     # Post inits required for structs that use other struct values as inputs and cannot be clearly defined
    #     self.cli_args = [ GeneralCLI(**arg_dict) for arg_dict in self.arg_definitions ]


# RadGenCLI is definitions but we basically want to use it as a factory to create the dataclass which holds values for input args

rad_gen_cli = RadGenCLI()
RadGenArgs = get_dyn_class(
    cls_name = "RadGenArgs", 
    fields = rad_gen_cli.get_dataclass_fields(is_cli = True),
    bases = (CommonCLI,))


#  █████╗ ███████╗██╗ ██████╗    ██████╗ ███████╗███████╗
# ██╔══██╗██╔════╝██║██╔════╝    ██╔══██╗██╔════╝██╔════╝
# ███████║███████╗██║██║         ██║  ██║███████╗█████╗  
# ██╔══██║╚════██║██║██║         ██║  ██║╚════██║██╔══╝  
# ██║  ██║███████║██║╚██████╗    ██████╔╝███████║███████╗
# ╚═╝  ╚═╝╚══════╝╚═╝ ╚═════╝    ╚═════╝ ╚══════╝╚══════╝


@dataclass
class AsicDseCLI(ParentCLI):
    """ 
        Command line interface settings for asic-dse subtool
    """
    cli_args: List[GeneralCLI] = field(default_factory = lambda: [
        GeneralCLI(key = "tool_env_conf_path", shortcut = "-e", datatype = str, help_msg = "Path to hammer environment configuration file"),
        GeneralCLI(key = "design_sweep_config", shortcut = "-s", datatype = str, help_msg = "Path to design sweep config file"),
        # RUN MODE
        GeneralCLI(key = "run_mode", shortcut = "-r", datatype = str, choices = ["serial", "parallel", "gen_scripts"], default_val = "serial", help_msg = "Specify if flow is run in serial or parallel for sweeps"),
        # FLOW MODE
        GeneralCLI(key = "flow_mode", shortcut = "-m", datatype = str, choices = ["hammer", "custom"], default_val = "hammer", help_msg = "Mode in which asic flow is run hammer or custom modes"),
        GeneralCLI(key = "top_lvl_module", shortcut = "-t", datatype = str, help_msg = "Top level module of design"),
        GeneralCLI(key = "hdl_path", shortcut = "-v", datatype = str, help_msg = "Path to directory containing hdl files"),
        GeneralCLI(key = "flow_conf_paths", shortcut = "-p", datatype = str, nargs = "*", help_msg = "Paths to flow config files, these can be either custom or hammer format"),
        GeneralCLI(key = "project_name", shortcut = "-n", datatype = str, help_msg = "Name of Project, this will be used to create a subdir in the 'projects' directory which will store all files related to inputs for VLSI flow. Needed if we want to output configurations or RTL and want to know where to put them"),
        # GeneralCLI(key = "use_latest_obj_dir", shortcut = "-l", action = "store_true", help_msg = "Uses latest obj / work dir found in the respective output_design_files/<top_module> dir"),
        # GeneralCLI(key = "use_manual_obj_dir", shortcut = "-o", datatype = str, help_msg = "Uses user specified obj / work dir"),
        GeneralCLI(key = "compile_results", shortcut = "-c", datatype = bool, action = "store_true", help_msg = "Flag to compile results related a specific asic flow or sweep depending on additional provided configs"),
        GeneralCLI(key = "synthesis", shortcut = "-syn", datatype = bool, help_msg = "Flag to run synthesis"),
        GeneralCLI(key = "place_n_route", shortcut = "-par", datatype = bool, help_msg = "Flag to run place & route"),
        GeneralCLI(key = "primetime", shortcut = "-pt", datatype = bool, help_msg = "Flag to run primetime (timing & power)"),
        GeneralCLI(key = "sram_compiler", shortcut = "-sram", datatype = bool, help_msg = "Flag that must be provided if sram macros exist in design (ASIC-DSE)"),
        GeneralCLI(key = "make_build", shortcut = "-make", datatype = bool, help_msg = "<TAG> <UNDER DEV> Generates a makefile to manage flow dependencies and execution"),
        # Below are definitions for params nested in the hierarchy of AsicDSE dataclass
        GeneralCLI(key = "tech.name", datatype= str, help_msg = "Name of tech lib for use with Cadence Virtuoso", default_val = "asap7"),
        GeneralCLI(key = "tech.cds_lib", datatype= str, help_msg = "Name of cds lib for use with Cadence Virtuoso", default_val = "asap7_TechLib"),
        GeneralCLI(key = "tech.pdk_rundir_path", datatype= str, help_msg = "Path to rundir of pdk being used for Cadence Virtuoso"),


    ] )
    arg_definitions: List[Dict[str, Any]] = field(default_factory = lambda: [
        { "shortcut": "-e", "key": "env_config_path", "help_msg": "Path to hammer environment configuration file", "datatype": str },
        { "shortcut": "-s", "key": "design_sweep_config", "help_msg": "Path to design sweep config file", "datatype": str },
        # RUN MODE
        { "shortcut": "-r", "key": "run_mode", "help_msg": "Specify if flow is run in serial or parallel for sweeps", "datatype": str,
          "choices" : ["serial", "parallel", "gen_scripts"], "default_val" : "serial" },
        # FLOW MODE
        { "shortcut": "-m", "key": "flow_mode", "help_msg": "Mode in which asic flow is run hammer or custom modes", "datatype": str,
          "choices" : ["hammer", "custom"], "default_val" : "hammer" },
        { "shortcut": "-t", "key": "top_lvl_module", "help_msg": "Top level module of design", "datatype": str },
        { "shortcut": "-v", "key": "hdl_path", "help_msg": "Path to directory containing hdl files", "datatype": str },
        { "shortcut": "-p", "key": "flow_config_paths", "help_msg": "Paths to flow config files, these can be either custom or hammer format", "datatype": str, "nargs": "*" },
        # { "shortcut": "-l", "key": "use_latest_obj_dir", "help_msg": "Uses latest obj / work dir found in the respective output_design_files/<top_module> dir", "action" : "store_true" },
        # { "shortcut": "-o", "key": "manual_obj_dir", "help_msg": "Uses user specified obj / work dir", "datatype": str },
        { "shortcut": "-c", "key": "compile_results", "datatype": bool, "action" : "store_true", "help_msg": "Flag to compile results related a specific asic flow or sweep depending on additional provided configs" },
        { "shortcut": "-syn", "key": "synthesis", "datatype": bool, "help_msg": "Flag to run synthesis", "action" : "store_true" },
        { "shortcut": "-par", "key": "place_n_route", "datatype": bool, "help_msg": "Flag to run place & route", "action" : "store_true" },
        { "shortcut": "-pt", "key": "primetime", "datatype": bool, "help_msg": "Flag to run primetime (timing & power)", "action" : "store_true" },
        { "shortcut": "-sram", "key": "sram_compiler", "datatype": bool, "help_msg": "Flag that must be provided if sram macros exist in design (ASIC-DSE)", "action" : "store_true" },
        { "shortcut": "-make", "key": "make_build", "datatype": bool, "help_msg": "Flag that Generates a makefile to manage flow dependencies and execution", "action" : "store_true" },
    ])
    """
        env_config_path: str = None # path to hammer environment configuration file 
        design_sweep_config: str = None # Path to design sweep config file 
        run_mode: str = None # specify if flow is run in "serial" or "parallel" or "gen_scripts"
        flow_mode: str = None # mode in which asic flow is run "hammer" or "custom" modes
        top_lvl_module: str = None # top level module of design 
        hdl_path: str = None # path to directory containing hdl files 
        flow_config_paths: List[str] = None # Paths to flow config files, these can be either "custom" or "hammer" format
        use_latest_obj_dir: bool = False  # uses latest obj / work dir found in the respective output_design_files/<top_module> dir
        manual_obj_dir: str = None # uses user specified obj / work dir
        compile_results: bool = False # flag to compile results related a specific asic flow or sweep depending on additional provided configs
        synthesis: bool = False # flag to run synthesis
        place_n_route: bool = False #flag to run place & route
        primetime: bool = False # flag to run primetime (timing & power)
        sram_compiler: bool = False # flag that must be provided if sram macros exist in design
        make_build: bool = False # <TAG> <UNDER DEV> Generates a makefile to manage flow dependencies and execution
    """


# Use asic_dse_cli as factory for creating AsicDseArgs dataclass

asic_dse_cli = AsicDseCLI()
asic_dse_fields = asic_dse_cli.get_dataclass_fields()
# Make a custom dataclass for asic dse input arguments
AsicDseArgs = get_dyn_class(
    cls_name = "AsicDseArgs",
    fields = asic_dse_fields,
    bases= (AsicDseCLI, )
)


"""
@dataclass
class AsicDse(metaclass = AsicDseMeta):
    # cli args will be added to this dataclass from the cli_init function
    @classmethod
    def cli_init(cls, args: List[GeneralCLI], **kwargs):
        # Create a dictionary with field names and values
        field_dict = {field.key: field.default_val for field in args}

        # Add provided keyword arguments to the dictionary
        field_dict.update(kwargs)

        # Create an instance of AsicDseCLI with the combined field values
        return cls(**field_dict)
"""






@dataclass
class VLSIMode:
    """ 
        Mode settings associated with running VLSI flow
    """
    run_mode: str = None # specify if flow is run in serial or parallel for sweeps 
    flow_mode: str = None # mode in which asic flow is run "hammer" or "custom" modes
    enable: bool = False # run VLSI flow
    config_pre_proc: bool = False # Don't create a modified config file for this design

@dataclass 
class RADGenMode:
    """ 
    The mode in which the RADGen tool is running
    Ex. 
     - Sweep mode
     - Single design mode
    """
    sweep_gen: bool = False # run sweep config, header, script generation
    result_parse: bool = False # parse results 
    vlsi_flow: VLSIMode = field(default_factory = VLSIMode)# modes for running VLSI flow


@dataclass
class SRAMCompilerSettings:
    """
        Paths related to SRAM compiler outputs
        If not specified in the top level config file, will use default output structure (sent to rad gen input designs directory)
    """
    rtl_out_path: str = None # os.path.expanduser("~/rad_gen/input_designs/sram/rtl/compiler_outputs")
    config_out_path: str = None #os.path.expanduser("~/rad_gen/input_designs/sram/configs/compiler_outputs")
    


@dataclass
class StdCellTechInfo:
    """
        Paths and PDK information for the current rad gen run
    """
    name: str = "asap7" # name of technology lib
    cds_lib: str = "asap7_TechLib" # name of technology library in cdslib directory, contains views for stdcells, etc needed in design
    sram_lib_path: str = None # path to PDK sram library containing sub dirs named lib, lef, gds with each SRAM.
    # Process settings in RADGen settings as we may need to perform post processing (ASAP7)
    pdk_rundir_path: str = None # path to PDK run directory which allows Cadence Virtuoso to run in it


@dataclass
class VLSISweepInfo:
    params: Dict #[Dict[str, Any]] 
    

@dataclass 
class SRAMSweepInfo:
    base_rtl_path: str # path to RTL file which will be modified by SRAM scripts to generate SRAMs, its an SRAM instantiation (supporting dual and single ports with ifdefs) wrapped in registers
    """
        List of dicts each of which contain the following elements:
        - rw_ports -> number of read/write ports
        - w -> sram width
        - d -> sram depth
    """
    mems: List[Dict[str, int]] # Contains sram information to be created from existing SRAM macros using mappers
    # parameters for explicit macro generation
    rw_ports: List[int]
    widths: List[int]
    depths: List[int]

@dataclass
class RTLSweepInfo:
    """
        Contains information for sweeping designs 
    """
    base_header_path: str # path to  containing RTL header file for parameter sweeping
    """
        parameters to sweep, each [key, dict] pair contains the following elements:
        - key = name of parameter to sweep
        - dict elements:
            - vals -> sweep values for parameter defined in "key"
            - <arbirary_additional_param_values> -> sweep values of same length of "vals" for any additional parameters which need to be swept at the same time
    """
    params: Dict #[Dict[str, Any]] 

# TODO add validators
@dataclass
class DesignSweepInfo:
    """
        Information specific to a single sweep of design parameters, this corresponds to a single design in sweep config file
        Ex. If sweeping clock freq in terms of [0, 1, 2] this struct contains information about that sweep
    """
    top_lvl_module: str # top level module of design
    base_config_path: str # path to hammer config of design
    rtl_dir_path: str # path to directory containing rtl files for design, files can be in subdirectories
    type: str = None # options are "sram", "rtl_params" or "vlsi_params" TODO this could be instead determined by searching through parameters acceptable to hammer IR
    flow_threads: int = 1 # number of vlsi runs which will be executed in parallel (in terms of sweep parameters)
    type_info: Any = None # contains either RTLSweepInfo or SRAMSweepInfo depending on sweep type


@dataclass
class ScriptInfo:
    """
        Filenames of various scripts used in RAD Gen
    """
    gds_to_area_fname: str = "get_area" # name for gds to area script & output csv file
    virtuoso_setup_path: str = None



@dataclass 
class ASICFlowSettings:
    """ 
        ASIC flow related design specific settings relevant the following catagories:
        - paths
        - flow stage information
    """
    

    # Directory structure for hammer repo 
    hammer_tech_path: str = None 
    # Moved to here
    hammer_env_paths: List[str] = None # paths to hammer environment file containing absolute paths to asic tools and licenses
    # Hammer Driver Path
    hammer_cli_driver_path: str = None # path to hammer driver
    hammer_driver: HammerDriver = None # hammer settings
    # Replace design_config with hammer_driver 
    #design_config : Dict[str, Any] = None # Hammer IR parsable configuration info
    
    # Paths
    hdl_path: str = None # path to directory containing hdl files
    config_path: str = None # path to hammer IR parsable configuration file
    top_lvl_module: str = None # top level module of design
    obj_dir_path: str = None # hammer object directory containing subdir for each flow stage
    
    # use_latest_obj_dir: bool # looks for the most recently created obj directory associated with design (TODO & design parameters) and use this for the asic run
    # manual_obj_dir: str # specify a specific obj directory to use for the asic run (existing or non-existing)
    # Stages being run
    run_sram: bool = False
    run_syn: bool = False
    run_par: bool = False
    run_pt: bool = False
    make_build: bool = False # Use the Hammer provided make build to manage asic flow execution
    # flow stages
    flow_stages: dict = field(default_factory = lambda: {
        "sram": {
            "name": "sram",
            "run": False,
        },
        "syn": {
            "name": "syn",
            "run": False,
            "tool": "cadence",
        },
        "par": {
            "name": "par",
            "run": False,
            "tool": "cadence",
        },
        "pt": {
            "name": "pt",
            "run": False,
            "tool": "synopsys",
        },
    })

    def __post_init__(self):
        if self.hammer_cli_driver_path is None:
            # the hammer-vlsi exec should point to default cli driver in hammer repo if everything installed correctly
            self.hammer_cli_driver_path = "hammer-vlsi"
        # else: 
        #     self.hammer_cli_driver_path = f"python3 {self.hammer_cli_driver_path}"





# TODO remove this data structure, moving all its contents to AsicFlowSettings and Common
@dataclass
class EnvSettings:
    """ 
        Settings which are specific to a user of the RAD Gen tool including the following:
        - paths specified to system running RAD Gen
        - log settings
        - directory structures for inputs and outputs
    """
    # RAD-Gen
    rad_gen_home_path: str # path to top level rad gen repo 
    # Hammer
    hammer_home_path: str  # path to hammer repository
    env_paths: List[str] # paths to hammer environment file containing absolute paths to asic tools and licenses

    # OpenRAM 
    # openram_path: str  # path to openram repository
    
    # Top level input # TODO remove this, deprecated config path
    top_lvl_config_path: str = None # high level rad gen configuration file path
    
    # Name of directory which stores parameter sweep headers
    # param_sweep_hdr_dir: str = "param_sweep_hdrs" TODO remove this and use input_dir_structure defined below (gen)
    
    # Verbosity level
    # 0 - Brief output
    # 1 - Brief output + I/O + command line access
    # 2 - Hammer and asic tool outputs will be printed to console    
    logger: logging.Logger = logging.getLogger(f"rad-gen-{create_timestamp()}") # logger for RAD Gen
    log_file: str = f"rad-gen-{create_timestamp()}.log" # path to log file for current RAD Gen run
    log_verbosity: int = 1 # verbosity level for log file 
    
    # Input and output directory structure, these are initialized with design specific paths
    design_input_path: str = None # path to directory which inputs will be read from. Ex ~/rad_gen/input_designs
    design_output_path: str = None # path to directory which object directories will be created. Ex ~/rad_gen/output_designs
    hammer_tech_path: str = None # path to hammer technology directory containing tech files

    # Directory structure for auto-dse hammer asic flow
    input_dir_struct: dict = field(default_factory = lambda: {
        # Design configuration files
        "configs": {
            # Auto-generated configuration files from sweep
            "gen" : "gen",
            # Tmp directory for storing modified configuration files by user passing in top_lvl & hdl_path & original config 
            "mod" : "mod",
        },
        # Design RTL files
        "rtl" : {
            "gen" : "gen", # Auto-generated directories containing RTL
            "src" : "src", # Contains design RTL files
            "include": "include", # Contains design RTL header files
            "verif" : "verif", # verification related files
            "build" : "build", # build related files for this design
        }
    })

    # Regex Info
    res: Regexes = field(default_factory = Regexes)
    # Sript path information
    scripts_info: ScriptInfo = None
    # Report information
    report_info: ReportInfo = field(default_factory = ReportInfo)

    def __post_init__(self):
        # Assign defaults for input and output design dir, these will be overridden if specified in top level yaml file
        if self.design_input_path is None:
            self.design_input_path = os.path.join(self.rad_gen_home_path, "input_designs") 
        if self.design_output_path is None:
            self.design_output_path = os.path.join(self.rad_gen_home_path, "output_designs")
        if self.hammer_tech_path is None:
            self.hammer_tech_path = os.path.join(self.hammer_home_path, "hammer", "technology")


@dataclass
class AsicDSE:
    """
        These settings are applicable to a single execution of the RAD Gen tool from command line 

        Settings which are used by users for higher level data preperation such as following:
        - Preparing designs to be swept via RTL/VLSI parameters
        - Using the SRAM mapper
    """
    common: Common # common settings for RAD Gen
    # env_settings: EnvSettings # env settings relative to paths and filenames for RAD Gen
    mode: RADGenMode # mode in which RAD Gen is running
    tech: StdCellTechInfo # technology information for the design
    scripts: ScriptInfo = None # script information for RAD Gen
    project_name: str = None # name of project, this will be used to create a subdir in the 'projects' directory which will store all files related to inputs for VLSI flow. Needed if we want to output configurations or RTL and want to know where to put them
    sweep_config_path: str = None # path to sweep configuration file containing design parameters to sweep
    result_search_path: str = None # path which will look for various output obj directories to parse results from
    asic_flow_settings: ASICFlowSettings = None # asic flow settings for single design
    custom_asic_flow_settings: Dict[str, Any] = None # custom asic flow settings
    design_sweep_infos: List[DesignSweepInfo] = None # sweep specific information for a single design
    sram_compiler_settings: SRAMCompilerSettings = None
    def __post_init__(self):
        # Post inits required for structs that use other struct values as inputs and cannot be clearly defined
        self.tech_info.sram_lib_path = os.path.join(self.env_settings.hammer_tech_path, self.tech_info.name, "sram_compiler", "memories")
        if self.sram_compiler_settings is None:
            self.sram_compiler_settings = SRAMCompilerSettings()
            self.sram_compiler_settings.config_out_path = os.path.join(self.env_settings.design_input_path, "sram", "configs", "compiler_outputs")
            self.sram_compiler_settings.rtl_out_path = os.path.join(self.env_settings.design_input_path, "sram", "rtl", "compiler_outputs")
        if self.asic_flow_settings.hammer_tech_path is None:
            self.asic_flow_settings.hammer_tech_path = os.path.join(self.common.hammer_home_path, "hammer", "technology")
        # elif self.sram_compiler_settings.config_out_path == None and self.sram_compiler_settings.rtl_out_path != None:
        #     self.sram_compiler_settings.config_out_path = os.path.join(self.env_settings.design_input_path, "sram", "configs", "compiler_outputs")
        # elif self.sram_compiler_settings.rtl_out_path == None and self.sram_compiler_settings.config_out_path != None:
        #     self.sram_compiler_settings.rtl_out_path = os.path.join(self.env_settings.design_input_path, "sram", "rtl", "compiler_outputs")



#  ██████╗ ██████╗ ███████╗███████╗███████╗
# ██╔════╝██╔═══██╗██╔════╝██╔════╝██╔════╝
# ██║     ██║   ██║█████╗  █████╗  █████╗  
# ██║     ██║   ██║██╔══╝  ██╔══╝  ██╔══╝  
# ╚██████╗╚██████╔╝██║     ██║     ███████╗
#  ╚═════╝ ╚═════╝ ╚═╝     ╚═╝     ╚══════╝


@dataclass
class Hardblock:
    asic_dse_cli: AsicDseCLI 
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
    cli_args: List[GeneralCLI] = field(default_factory = lambda: [
        GeneralCLI(key = "fpga_arch_conf_path", shortcut = "-f", datatype = str, help_msg = "path to config file containing coffe FPGA arch information"),
        GeneralCLI(key = "hb_flows_conf_path", shortcut = "-hb", datatype = str, help_msg = "path to config file containing coffe hard block flows information"),
        GeneralCLI(key = "no_sizing", shortcut = "-ns", datatype = bool, action = "store_true", help_msg = "don't perform sizing"),
        GeneralCLI(key = "opt_type", shortcut = "-ot", datatype = str, choices = ["global", "local"], default_val = "global", help_msg = "optimization type, options are \"global\" or \"local\""),
        GeneralCLI(key = "initial_sizes", shortcut = "-is", datatype = str, help_msg = "path to initial transistor sizes"),
        GeneralCLI(key = "re_erf", shortcut = "-re", datatype = int, default_val = 1, help_msg = "how many sizing combos to re-erf"),
        GeneralCLI(key = "area_opt_weight", shortcut = "-aw", datatype = int, default_val = 1, help_msg = "area optimization weight"),
        GeneralCLI(key = "delay_opt_weight", shortcut = "-dw", datatype = int, default_val = 1, help_msg = "delay optimization weight"),
        GeneralCLI(key = "max_iterations", shortcut = "-mi", datatype = int, default_val = 6, help_msg = "max FPGA sizing iterations"),
        GeneralCLI(key = "size_hb_interfaces", shortcut = "-sh", datatype = float, default_val = 0.0, help_msg = "perform transistor sizing only for hard block interfaces"),
        GeneralCLI(key = "quick_mode", shortcut = "-q", datatype = float, default_val = -1.0, help_msg = "minimum cost function improvement for resizing, Ex. could try 0.03 for 3% improvement"),
    ])
    arg_definitions: List[Dict[str, Any]] = field(default_factory = lambda: [
        # FPGA ARCH CONFIG PATH
        {"key" : "fpga_arch_conf_path", 
         "shortcut" : "-f",  "help_msg" : "path to config file containing coffe FPGA arch information", "datatype" : str},
        # HARDBLOCK FLOW CONFIG PATH
        {"key" : "hb_flows_conf_path", 
         "shortcut" : "-hb", "help_msg" : "path to config file containing coffe hard block flows information", "datatype" : str},

        {"key" : "no_sizing",
         "shortcut" : "-ns", "help_msg" : "don't perform sizing", "action" : "store_true"},
        
        {"key" : "opt_type", "default_val" : "global",
         "shortcut" : "-ot", "help_msg" : "optimization type, options are \"global\" or \"local\"", "datatype" : str, "choices" : ["global", "local"]},
        
        {"key" : "initial_sizes", "default_val" : "default", 
         "shortcut" : "-is", "help_msg" : "path to initial transistor sizes", "datatype" : str},

        {"key" : "re_erf", "default_val" : 1,
         "shortcut" : "-re", "help_msg" : "how many sizing combos to re-erf", "datatype" : int},

        {"key" : "area_opt_weight", "default_val" : 1,
         "shortcut" : "-aw", "help_msg" : "area optimization weight", "datatype" : int},

        {"key" : "delay_opt_weight", "default_val" : 1,
         "shortcut" : "-dw", "help_msg" : "delay optimization weight", "datatype" : int},

        {"key" : "max_iterations", "default_val" : 6,
         "shortcut" : "-mi", "help_msg" : "max FPGA sizing iterations", "datatype" : int},

        {"key" : "size_hb_interfaces", "default_val": 0.0,
         "shortcut" : "-sh", "help_msg" : "perform transistor sizing only for hard block interfaces", "datatype" : float},

        {"key" : "quick_mode", "default_val": -1.0, 
         "shortcut" : "-q",  "help_msg" : "minimum cost function improvement for resizing, Ex. could try 0.03 for 3% improvement", "datatype" : float},
    ])



    """
        no_sizing: bool = None # don't perform sizing
        opt_type: str = None # optimization type, options are "global" or "local"
        initial_sizes: str = None # where to get initial transistor sizes options are "default" ... TODO find all valid options
        re_erf: int = None # how many sizing combos to re-erf
        area_opt_weight: int = None # area optimization weight
        delay_opt_weight: int = None # delay optimization weight
        max_iterations: int = None # max FPGA sizing iterations
        size_hb_interfaces: float = None # perform transistor sizing only for hard block interfaces
        quick_mode : float = None # minimum cost function improvement for resizing, could try 0.03 for 3% improvement
        fpga_arch_conf_path: Dict[str, Any] = None # FPGA architecture configuration dictionary TODO define as dataclass
        hb_flows_conf_path: Dict[str, Any] = None # Hard block flows configuration dictionary TODO define as dataclass
    """

# Use CoffeCLI as factory for creating CoffeArgs dataclass

coffe_cli = CoffeCLI()
coffe_fields = coffe_cli.get_dataclass_fields()
CoffeArgs = get_dyn_class(
    cls_name = "CoffeArgs",
    fields = coffe_fields,
    bases= (CoffeCLI,)
)



@dataclass
class Coffe:
    args: CoffeArgs
    """
        # TODO put coffe CLI in here
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
    """

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
    This represents a spice run which will be done
    From a title a spice directory will be created
    """
    title: str
    top_sp_dir: str # path to top level spice directory
    sp_dir: str = None # path to sim working directory (contains .sp and output files )
    sp_file: str = None # path to sp file used for simulation ".sp" file
    sp_outfile: str = None # output file ".lis"

    def __post_init__(self):
        self.sp_dir = os.path.join(self.top_sp_dir,self.title)
        if not os.path.exists(self.sp_dir):
            os.makedirs(self.sp_dir)
        self.sp_file = os.path.join(self.sp_dir,self.title+".sp")
        self.sp_outfile = os.path.join(self.sp_dir,self.title+".lis")


@dataclass
class SpInfo:
    """Spice subckt generation info"""
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
        self.process_package_dse = SpProcess(title="process_package_dse", top_sp_dir=self.sp_dir)


@dataclass
class SpSubCkt:
    """Spice subckt generation info"""

    ports: dict
    params: dict = field(default_factory=lambda: {})
    raw_sp_insts_lines: list = None
    # These params are to allow subcircuits and larger circuits to be created more easily out of them
    # port_defs: dict = None
    name: str = None
    # Element could be one of the following (cap, res, mfet, subckt, etc)
    element: str = "subckt"
    prefix: str = None
    insts: list = None
    direct_conn_insts: bool = False

    def connect_insts(self):
        """
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
    subckt: SpSubCkt
    name: str
    conns: dict = field(default_factory = lambda: {})
    param_values: dict = None 
    
    # initialize the param_values to those stored in the subckt params, if the user wants to override them they will specify them at creation of SpSubCktInst object
    def __post_init__(self):
        if self.param_values == None:
            self.param_values = self.subckt.params.copy()

@dataclass
class TechInfo:
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
    global_nodes : dict
    voltage_info : dict
    geometry_info : dict
    driver_info : dict
    tech_info: dict

@dataclass
class DriverSpModel:
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


    bottom_die_inv_stages: int = 1 # This should be removed pray this inst being used somewhere  


########################## GENERAL PROCESS INFORMATION ###########################

@dataclass
class SpOptSettings:
    init: float
    range: List[float]
    step: float

    def __post_init__(self):
        if min(self.range) > self.init or max(self.range) < self.init:
            raise ValueError(f"Initial value {self.init} is not within range {self.range}")


@dataclass
class SpParam:
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
    mlayer_range: List[int]
    res: float # Ohm
    height: float # nm
    avg_mlayer_cap_per_um: float # fF / um
    # Spice Info for Via Stack
    cap: float = None # fF
    sp_params: dict = field(default_factory = lambda: {})
    def __post_init__(self):
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
    """ Geometry information for a single transistor of process """
    # hfin: float # nm
    min_tx_contact_width: float # nm
    tx_diffusion_length: float # nm
    gate_length: float # nm
    min_width_tx_area: float # nm^2
    sp_params: dict = field(default_factory = lambda: {})
    def __post_init__(self):
        sp_params = [field.name for field in fields(self) if field.name != "sp_params"]
        #sp_params = [ "min_tx_contact_width", "tx_diffusion_length", "gate_length", "hfin"]
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
    x: float
    y: float

@dataclass
class RectBB:
    p1 : GridCoord
    p2 : GridCoord
    # label for what this BB represents
    bb : sh.box
    # tsv_grid -> "TSV" "KoZ"
    # C4_grid -> "PWR" "GND" "IO"
    label : str

@dataclass
class GridPlacement:
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
    # def update_grid()
    def __post_init__(self) -> None:
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
    def gen_fig(self, fig: go.Figure, fill_color: str, opacity: str, label_filt: str = None, layer: str = "above", line_color: str = "black") -> None:
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
    height: int #um
    diameter: int #um
    pitch: int #um
    resistivity: float # Ohm * um
    keepout_zone: float #um (adds to diameter)
    area: float = None # um^2
    resistance: float = None # Ohm
    def __post_init__(self):
        self.area = (self.diameter**2)
        # self.resistance = self.resistivity * self.height / (self.diameter**2)


@dataclass
class PolyPlacements:
    """
        This dataclass is used for representing a list of polygons in a 2D space
    """
    # grid start and end in um
    rects: List[RectBB] = None
    tag: str = None # used to identify what this grid is for
    area: float = None # area of the grid in um^2
    bb_poly: sh.Polygon = None # Polygon containing a bounding box for the grid (xmin, ymin, xmax, ymax)

    def gen_fig(self, fig: go.Figure, fill_color: str, opacity: str, label_filt: str = None, layer: str = "above", line_color: str = "black") -> None:
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
    height: int #um
    diameter: int #um
    pitch: int #um 
    area : float # um^2
    resistance: float = None
    def __post_init__(self):
        self.area = (self.diameter**2)

@dataclass
class C4Info:
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
    x: int
    y: int

@dataclass
class BlockRegion:
    resource_tag: str # "dsp", "bram", "lb", "io", "gnd", "pwr"
    pwr_region_coord: Coord # coord in grid of power regions
    sector_coord: Coord 

# @dataclass
# class PwrRegion:
#     # abs_dims: List[float] # [width, height]
#     # Grid of LB sized regions occupied by various types of blocks
#     blocks: List[List[BlockRegion]] = None


@dataclass 
class SectorInfo:
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
    total_num: int
    abs_area: float # um^2
    rel_area: int # area in LBs (assume aspect ratio of W / L = Area / 1)
    abs_width: float = None # um
    abs_height: float = None # um 

@dataclass
class FPGAInfo:
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


@dataclass
class TSVGridPlacement:
    start_coord: GridCoord
    # vertical and horizontal distance in um for each TSV
    tsv_h: float 
    tsv_v: float
    # vertical and horizontal distance bw tsvs in um 
    tsv_s_h: float
    tsv_s_v: float
    dim: int
    # grid start and end in um
    tsv_grid : List[RectBB] = None
    def __post_init__(self):
        self.tsv_grid = [[None]*self.dim for _ in range(self.dim)]
        for col in range(self.dim):
            for row in range(self.dim):
                # bb of tsv coords 
                self.tsv_grid[col][row] = RectBB(
                    p1 = GridCoord(
                        x = self.start_coord.x + col*(self.tsv_s_h),
                        y = self.start_coord.y + row*(self.tsv_s_v),
                    ),
                    p2 = GridCoord(
                        x = self.start_coord.x + col*(self.tsv_s_h) + self.tsv_h,
                        y = self.start_coord.y + row*(self.tsv_s_v) + self.tsv_v,
                    ),
                )

@dataclass
class PDNModelingInfo:
    r_script_path: str = os.path.expanduser("~/3D_ICs/fpga21-scaled-tech/rc_calculations/custom_calc_resistance.py")
    c_script_path: str = os.path.expanduser("~/3D_ICs/fpga21-scaled-tech/rc_calculations/custom_calc_capacitance.py")

pdn_modeling_info = PDNModelingInfo()

########################## PDN MODELING ###########################





@dataclass
class TxSizing:
    opt_mode: str = None  # possible modes are "P", "NP" and "N" if one of those strings is included then the sizing for the respective PMOS / NMOS will be optimized by hspice
    opt_goal: str = None # options are "tpd" (propegation delay) or "diff" (match the rising and falling propegation delays)
    pmos_sz: int = None
    nmos_sz: int = None
    p_opt_params: dict = None
    n_opt_params: dict = None
    iters: int = None






@dataclass
class SpTestingModel:




    # Design Info
    insts :  List[SpSubCktInst] # All nodes inside of the spice sim
    vsrcs: List[SpVoltageSrc]  = None # We create a basic voltage source for each instantiation to measure their power

    # Node definitions
    dut_in_node: str = "n_in" # input node (connected to non inst stimulus
    dut_out_node: str = "n_out" # output node (hanging or connected to non inst stimulus)
    
    # Simulation Info
    opt_params: List[SpParam] = None # List of all optimization parameters used in simulation
    static_params: List[SpParam] = None # List of all static parameters used in simulation
    sim_settings: SpLocalSimSettings = None # Simulation settings
    # target_freq: int = 1000 # freq in MHz
    # target_period: float = None # period in ns
    # voltage_src: SpVoltageSrc = None # voltage source for simulation
    
    # FIELDS WHICH ARE ONLY HERE TO WORK WITH OLD FUNCTIONS THAT I DESIRE TO GET RID OF 
    target_freq: int = None # freq in MHz

    def __post_init__(self):
        if self.sim_settings != None:
            if self.sim_settings.dut_in_vsrc.out_node is None:
                self.sim_settings.dut_in_vsrc.out_node = self.dut_in_node

    

 






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
    wn_param : str = "inv_Wn"
    wp_param : str = "inv_Wp"


@dataclass
class SpSubCktLibs:
    atomic_subckts: dict = None #= field(default_factory = lambda: sp_subckt_atomic_lib)
    basic_subckts: dict = None #= field(default_factory = lambda: basic_subckts)
    subckts: dict = None #= field(default_factory = lambda: subckts)

""" Here defines the top class used for buffer exploration """
@dataclass
class SRAMInfo:
    width: float # um
    height: float # um
    area: float = None # um^2
    def __post_init__(self):
        self.area = self.width * self.height

"""
    height: float
    diameter: float
    pitch: float
    res : float
    cap : float
"""

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
    """ Contains information about the Whole Design """
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
        GeneralCLI(key = "debug_spice", shortcut = "-ds" , datatype = str, nargs = "*", help_msg = "takes in directory(ies) named according to tile of spice sim, runs sim, opens waveforms and param settings for debugging"),
        GeneralCLI(key = "pdn_modeling", shortcut = "-pm", datatype = bool, action = "store_true", help_msg = "runs the PDN modeling flow"),
        GeneralCLI(key = "buffer_dse", shortcut = "-bd", datatype = bool, action = "store_true", help_msg = "runs the buffer DSE flow"),
        GeneralCLI(key = "buffer_sens_study", shortcut = "-bs", datatype = bool, action = "store_true", help_msg = "runs the buffer sensitivity study flow (sweeps parameters for buffer chain wire load, plots results)"),
    ])
    arg_definitions: dict = field(default_factory = lambda: [ 
        {"key": "input_config_path", 
            "shortcut" : "-ic" ,"type": str, "help": "path to ic_3d subtool specific configuration file"},

        {"key": "debug_spice",
            "shortcut" : "-ds" ,"type": str, "nargs": "*", "help": "takes in directory(ies) named according to tile of spice sim, runs sim, opens waveforms and param settings for debugging"},
        
        {"key": "pdn_modeling",
            "shortcut" : "-pm", "action": "store_true", "help": "runs the PDN modeling flow"},
        
        {"key": "buffer_dse", 
            "shortcut" : "-bd", "action": "store_true", "help": "runs the buffer DSE flow"},
        
        {"key": "buffer_sens_study",
            "shortcut" : "-bs", "action": "store_true", "help": "runs the buffer sensitivity study flow (sweeps parameters for buffer chain wire load, plots results)"},

        # {"key": "use_latest_obj_dir",
            # "shortcut" : "-l", "action": "store_true", "help": "uses the latest directory in the output folder rather than creating a new one"},
    ])

    """
        input_config_path: str = None # path to input configuration file
        debug_spice: bool = False # plot spice waveforms
        pdn_modeling: bool = False
        buffer_dse: bool = False
        buffer_sens_study: bool = False
        # This arg is for the WIP buffer DSE flow, one can use it by uncommenting the command in ic_3d.py or wait a little bit
        use_latest_obj_dir: bool = False # Uses the latest directory in the output folder rather than creating a new one
    """

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
    # CLI arguments (for modes)
    # cli_args: Ic3dCLI
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