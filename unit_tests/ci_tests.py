import os, sys
from dataclasses import dataclass
from dataclasses import field
import argparse
import yaml

from typing import List, Dict, Any, Tuple, Type, NamedTuple, Set, Optional

import rad_gen as rg
import subprocess as sp

@dataclass
class RadGenCLI: 
    # Refrences @ rad_gen.py -> parse_cli_args()
    design_configs: List[str] = None
    design_sweep_config: str = None
    top_lvl_config: str = None
    top_lvl_module: str = None
    hdl_path: str = None
    compile_results: bool = False
    use_latest_obj_dir: bool = False 
    manual_obj_dir: bool = False
    synthesis: bool = False
    place_n_route: bool = False
    primetime: bool = False
    sram_compiler: bool = False
    make_build: bool = False

    def get_rad_gen_cli_cmd(self, rad_gen_home: str):
        sys_args = []
        cmd_str = f"python3 {rad_gen_home}/rad_gen.py"
        for _field in RadGenCLI.__dataclass_fields__:
            val = getattr(self, _field)
            if val != None and val != False:
                if isinstance(val, list):
                    sys_args += [f"--{_field}"] + val
                    val = " ".join(val)
                if isinstance(val, str):    
                    cmd_str += f" --{_field} {val}"
                    sys_args += [f"--{_field}", val]
                elif isinstance(val, bool):
                    cmd_str += f" --{_field}"
                    sys_args += [f"--{_field}"]
        return cmd_str, sys_args



@dataclass 
class TestSuite:
    """
        Contains various RADGenCLI options to invoke the tool with a variety of tests
    """
    # ALU ASIC FLOW TEST
    # - SYN 
    # - PAR
    # - PT
    alu_tests: List[RadGenCLI] = None
    sram_tests: List[RadGenCLI] = None
    noc_tests: List[RadGenCLI] = None
    # Design Config files containing tool / tech info which is used across all tests
    sys_configs: List[str] = None
    # Rad Gen top config is assumed to be shared for tests
    top_config_path: str = None
    # TODO pass this from cli so users can specify which rad_gen_home they are using
    rad_gen_home: str = "~/rad_gen"

    def __post_init__(self):
        if self.top_config_path is None:
            self.top_config_path = os.path.expanduser(f"{self.rad_gen_home}/unit_tests/rad_gen_config.yml")
            assert os.path.exists(self.top_config_path)
            top_config_dict = yaml.safe_load(open(self.top_config_path, "r"))
            assert os.path.exists( os.path.expanduser(top_config_dict["env"]["rad_gen_home_path"]) )
            self.rad_gen_home = os.path.expanduser(top_config_dict["env"]["rad_gen_home_path"])
                
        if self.sys_configs is None:
            sys_configs = [
                f"{self.rad_gen_home}/system_configs/asap7.yml",
                f"{self.rad_gen_home}/system_configs/cadence_tools.yml"
            ]
            self.sys_configs = [ os.path.expanduser(p) for p in sys_configs] 
        if self.alu_tests is None:
            self.alu_tests = []
            # ALU ASIC TEST [1]
            alu_config = os.path.expanduser(f"{self.rad_gen_home}/input_designs/alu/configs/alu.yml")
            alu_test = RadGenCLI(
                top_lvl_config=self.top_config_path,
                design_configs= self.sys_configs + [alu_config],
                top_lvl_module="alu_ver",
                use_latest_obj_dir=True,
                hdl_path=os.path.expanduser(f"{self.rad_gen_home}/input_designs/alu/rtl/src"),
            )
            self.alu_tests.append(alu_test)
        if self.sram_tests is None:
            self.sram_tests = []
            # SRAM STITCHED & MACRO GENERATION TEST [2]
            sram_gen_config = os.path.expanduser(f"{self.rad_gen_home}/unit_tests/sweeps/sram_sweep.yml")
            sram_gen_test = RadGenCLI(
                top_lvl_config=self.top_config_path,
                design_sweep_config = sram_gen_config,
            )
            self.sram_tests.append(sram_gen_test)
            # The 128x32 single macro config should have been generated from the previous test execution
            sram_config = os.path.expanduser(f"{self.rad_gen_home}/input_designs/sram/configs/sram_config_SRAM2RW128x32.yaml")
            # SRAM SINGLE MACRO ASIC TEST [3]
            single_sram_macro_test = RadGenCLI(
                top_lvl_config = self.top_config_path,
                design_configs = self.sys_configs + [sram_config],
                use_latest_obj_dir = True,
                sram_compiler = True,
            )
            self.sram_tests.append(single_sram_macro_test)
            # TODO put in the test for SRAM MACRO / STICHED ASIC RUNS (generated from stage [2])
            # SRAM SINGLE STICHED MACROS ASIC TEST [4]
            sram_compiled_macro_config = os.path.expanduser(f"{self.rad_gen_home}/input_designs/sram/configs/compiler_outputs/sram_config__sram_macro_map_2x256x64.yaml" )
            sram_compiled_macro_test = RadGenCLI(
                top_lvl_config=self.top_config_path,
                design_configs= self.sys_configs + [sram_compiled_macro_config],
                use_latest_obj_dir=True,
                sram_compiler=True,
            )
            self.sram_tests.append(sram_compiled_macro_test)
        if self.noc_tests is None:
            self.noc_tests = []
            # NoC RTL PARAM SWEEP GEN TEST [5]
            noc_sweep_config = os.path.expanduser(f"{self.rad_gen_home}/unit_tests/sweeps/noc_sweep.yml")
            noc_sweep_test = RadGenCLI(
                top_lvl_config=self.top_config_path,
                design_sweep_config = noc_sweep_config,
            )
            self.noc_tests.append(noc_sweep_test)
            # NoC SINGLE ASIC TEST [6]
            noc_config = os.path.expanduser(f"{self.rad_gen_home}/input_designs/NoC/configs/vcr_config_num_message_classes_5_buffer_size_80_num_nodes_per_router_1_num_dimensions_2_flit_data_width_196_num_vcs_5.yaml")
            noc_sweep_test = RadGenCLI(
                top_lvl_config = self.top_config_path,
                design_configs = self.sys_configs + [noc_config],
                top_lvl_module = "router_wrap_bk",
                hdl_path = os.path.expanduser(f"{self.rad_gen_home}/input_designs/NoC/src"),
                use_latest_obj_dir = True,
            )
            self.noc_tests.append(noc_sweep_test)

            

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RADGen CI Test Suite")
    parser.add_argument("-p", "--just_print",  help="Don't execute test just print commands to console", action='store_true')
    return parser.parse_args()

def main():

    cur_env = os.environ.copy()
    
    args = parse_args()
    test_suite = TestSuite()
    

    print("Running ALU tests")
    for idx, test in enumerate(test_suite.alu_tests):
        cmd_str, sys_args = test.get_rad_gen_cli_cmd(test_suite.rad_gen_home)        
        print(f"Running: {cmd_str}")    
        if not args.just_print:   
            sp.call(" ".join(cmd_str.split(" ") + ["|", "tee", f"alu_unit_test_{idx}.log"]), env=cur_env, shell=True)
    
    print("Running SRAM tests")
    for idx, test in enumerate(test_suite.sram_tests):
        cmd_str, sys_args = test.get_rad_gen_cli_cmd(test_suite.rad_gen_home)        
        print(f"Running: {cmd_str}")        
        if not args.just_print:   
            sp.call(" ".join(cmd_str.split(" ") + ["|", "tee", f"sram_unit_test_{idx}.log"]), env=cur_env, shell=True)

    print("Running NoC tests")
    for idx, test in enumerate(test_suite.noc_tests):
        cmd_str, sys_args = test.get_rad_gen_cli_cmd(test_suite.rad_gen_home)        
        print(f"Running: {cmd_str}")        
        if not args.just_print:   
            sp.call(" ".join(cmd_str.split(" ") + ["|", "tee", f"noc_unit_test_{idx}.log"]), env=cur_env, shell=True)




if __name__ == "__main__":
    main()