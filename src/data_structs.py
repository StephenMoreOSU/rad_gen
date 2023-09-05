from dataclasses import dataclass, field
import os, sys

import re
from typing import Pattern, Dict, List, Any
from datetime import datetime

from vlsi.hammer.hammer.vlsi.driver import HammerDriver

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
class VLSIMode:
    """ 
        Mode settings associated with running VLSI flow
    """
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
class TechInfo:
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
class PrimeTime:
    """
        PrimeTime settings
    """
    search_paths: List[str]
    


# @dataclass
# class HammerSettings:
#     """
#         Settings specific to running hammer tool
#     """
#     database: hammer_config.HammerDatabase = None # hammer database



@dataclass 
class ASICFlowSettings:
    """ 
        ASIC flow related design specific settings relevant the following catagories:
        - paths
        - flow stage information
    """
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


@dataclass
class ScriptInfo:
    """
        Filenames of various scripts used in RAD Gen
    """
    gds_to_area_fname: str = "get_area" # name for gds to area script & output csv file
    virtuoso_setup_path: str = None

@dataclass
class ReportInfo:
    """
        Information relevant to report information and filenames 
    """
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
    sci_not_dec_re: Pattern = re.compile("\-{0,1}\d+\.{0,1}\d*e{0,1}\-{0,1}\d+",re.MULTILINE)


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
    
    # Top level input
    top_lvl_config_path: str = None # high level rad gen configuration file path
    
    # Name of directory which stores parameter sweep headers
    # param_sweep_hdr_dir: str = "param_sweep_hdrs" TODO remove this and use input_dir_structure defined below (gen)
    
    # Verbosity level
    # 0 - Brief output
    # 1 - Brief output + I/O + command line access
    # 2 - Hammer and asic tool outputs will be printed to console    
    log_file: str = f"rad-gen-{create_timestamp()}.log" # path to log file for current RAD Gen run
    log_verbosity: int = 1 # verbosity level for log file 
    
    # Input and output directory structure, these are initialized with design specific paths
    design_input_path: str = None # path to directory which inputs will be read from. Ex ~/rad_gen/input_designs
    design_output_path: str = None # path to directory which object directories will be created. Ex ~/rad_gen/output_designs

    hammer_tech_path: str = None # path to hammer technology directory containing tech files

    input_design_dir_structure: dict = field(default_factory = lambda: {
        # Design configuration files
        "configs": {
            # Auto-generated configuration files from sweep
            "gen" : {},
            # Tmp directory for storing modified configuration files by user passing in top_lvl & hdl_path & original config 
            "mod" : {}
        },
        # Design RTL files
        "rtl" : {
            "gen" : {}, # Auto-generated directories containing RTL
            "src" : {}, # Contains design RTL files
            "include": {}, # Contains design RTL header files
            "verif" : {}, # verification related files
            "build" : {}, # build related files for this design
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
class HighLvlSettings:
    """
        These settings are applicable to a single execution of the RAD Gen tool from command line 

        Settings which are used by users for higher level data preperation such as following:
        - Preparing designs to be swept via RTL/VLSI parameters
        - Using the SRAM mapper
    """
    env_settings: EnvSettings # env settings relative to paths and filenames for RAD Gen
    mode: RADGenMode # mode in which RAD Gen is running
    tech_info: TechInfo # technology information for the design
    sweep_config_path: str = None # path to sweep configuration file containing design parameters to sweep
    result_search_path: str = None # path which will look for various output obj directories to parse results from
    #param_sweep_hdr_dir: str = None # directory containing RTL header files for parameter sweeping
    asic_flow_settings: ASICFlowSettings = None # asic flow settings for single design
    design_sweep_infos: List[DesignSweepInfo] = None # sweep specific information for a single design
    sram_compiler_settings: SRAMCompilerSettings = None
    def __post_init__(self):
        # Post inits required for structs that use other struct values as inputs and cannot be clearly defined
        self.tech_info.sram_lib_path = os.path.join(self.env_settings.hammer_tech_path, self.tech_info.name, "sram_compiler", "memories")
        if self.sram_compiler_settings is None:
            self.sram_compiler_settings = SRAMCompilerSettings()
            self.sram_compiler_settings.config_out_path = os.path.join(self.env_settings.design_input_path, "sram", "configs", "compiler_outputs")
            self.sram_compiler_settings.rtl_out_path = os.path.join(self.env_settings.design_input_path, "sram", "rtl", "compiler_outputs")
        elif self.sram_compiler_settings.config_out_path == None:
            self.sram_compiler_settings.config_out_path = os.path.join(self.env_settings.design_input_path, "sram", "configs", "compiler_outputs")
        elif self.sram_compiler_settings.rtl_out_path == None:
            self.sram_compiler_settings.rtl_out_path = os.path.join(self.env_settings.design_input_path, "sram", "rtl", "compiler_outputs")
