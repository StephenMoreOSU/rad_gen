import os, sys
from dataclasses import dataclass, make_dataclass
from dataclasses import field
import dataclasses
import json

import argparse
import yaml

from typing import List, Dict, Any, Tuple, Type, NamedTuple, Set, Optional

import pandas as pd
import numpy as np

import rad_gen as rg

import src.common.data_structs as rg_ds
import src.coffe.parsing as coffe_parse
import src.common.utils as rg_utils
import subprocess as sp

import multiprocessing as mp

@dataclass
class Test:
    # rad_gen_cli: rg_ds.RadGenCLI = None
    rad_gen_args: Any = None # Will be intialized as a dynamic dataclass
    test_name: str = None

@dataclass 
class TestSuite:
    """
        Contains various rg_ds.RadGenCLI options to invoke the tool with a variety of tests
    """

    # Rad Gen top config is assumed to be shared for tests
    top_config_path: str = None
    # TODO pass this from cli so users can specify which rad_gen_home they are using
    rad_gen_home: str = os.environ["RAD_GEN_HOME"] 
    unit_test_home: str = None
    golden_ref_path: str = None
    # input paths for subtools
    asic_dse_inputs: str = None
    coffe_inputs: str = None
    ic_3d_inputs: str = None

    # output paths for subtools
    asic_dse_outputs: str = None
    coffe_outputs: str = None
    ic_3d_outputs: str = None

    # Config Parse Init Tests
    config_parse_init_tests: List[Test] = None

    # ASIC DSE TESTS
    alu_tests: List[Test] = None
    sram_tests: List[Test] = None
    noc_tests: List[Test] = None

    asic_dse_sweep_tests: List[Test] = None 
    # Design Config files containing tool / tech info which is used across all tests
    sys_configs: List[str] = None
    
    # COFFE TESTS
    coffe_tests: List[Test] = None

    # IC 3D TESTS
    buff_dse_tests: List[Test] = None
    pdn_tests: List[Test] = None
    ic_3d_tests: List[Test] = None


    def __post_init__(self):
        ci_test_obj_dir_suffix = "ci_test"

        if self.top_config_path is None:
            self.top_config_path = os.path.expanduser(f"{self.rad_gen_home}/unit_tests/inputs/top_lvl_configs/rad_gen_config.yml")
            # Get top level information relevant for all tests
                # self.top_config_path = os.path.expanduser(f"{self.rad_gen_home}/unit_tests/top_lvl_configs/rad_gen_test_config.yml")
                # assert os.path.exists(self.top_config_path)
                # top_config_dict = rg_utils.parse_yml_config(self.top_config_path)
                # env_config_dict = rg_utils.parse_yml_config(top_config_dict["asic_dse"]["env_config_path"])
                # assert os.path.exists( os.path.expanduser(env_config_dict["env"]["rad_gen_home_path"]) )
                # self.rad_gen_home = os.path.expanduser(env_config_dict["env"]["rad_gen_home_path"])

        if self.unit_test_home is None:
            self.unit_test_home = os.path.expanduser(f"{self.rad_gen_home}/unit_tests")
        if self.golden_ref_path is None:
            self.golden_ref_path = os.path.expanduser(f"{self.unit_test_home}/golden_results")
        if self.asic_dse_inputs is None:
            self.asic_dse_inputs = os.path.expanduser(f"{self.rad_gen_home}/unit_tests/inputs/asic_dse")
        if self.coffe_inputs is None:
            self.coffe_inputs = os.path.expanduser(f"{self.rad_gen_home}/unit_tests/inputs/coffe")
        if self.ic_3d_inputs is None:
            self.ic_3d_inputs = os.path.expanduser(f"{self.rad_gen_home}/unit_tests/inputs/ic_3d")
        if self.asic_dse_outputs is None:
            self.asic_dse_outputs = os.path.expanduser(f"{self.rad_gen_home}/unit_tests/outputs/asic_dse")
        if self.coffe_outputs is None:
            self.coffe_outputs = os.path.expanduser(f"{self.rad_gen_home}/unit_tests/outputs/coffe")
        if self.ic_3d_outputs is None:
            self.ic_3d_outputs = os.path.expanduser(f"{self.rad_gen_home}/unit_tests/outputs/ic_3d")

        if self.sys_configs is None:
            # Load sys configs relevant to
            sys_configs = [
                f"{self.unit_test_home}/inputs/asic_dse/sys_configs/asap7.yml",
                f"{self.unit_test_home}/inputs/asic_dse/sys_configs/cadence_tools.yml"
            ]
            self.sys_configs = [ os.path.expanduser(p) for p in sys_configs] 


        # Get the cli arguments for rad gen from the definition in data_structs.py
        rg_cli = rg_ds.RadGenCLI()
        rg_cli_fields = rg_cli.get_dataclass_fields()

        
        # field_defs = [ (name, dtype, field(default_factory=lambda: default)) for name, dtype, default in zip(rg_cli_fields["keys"], rg_cli_fields["dtypes"], rg_cli_fields["defaults"]) ]
        # Create custom dataclass for RadGenArgs
        # RadGenArgs = make_dataclass(
        #     "RadGenArgs", 
        #     fields = field_defs, 
        #     bases = (rg_ds.RadGenCLI,)
        # )
        
        RadGenArgs = rg_ds.get_dyn_class(
            cls_name = "RadGenArgs",
            fields = rg_cli_fields,
            bases= (rg_ds.RadGenCLI,),
        )



        
        #  █████╗ ███████╗██╗ ██████╗    ██████╗ ███████╗███████╗
        # ██╔══██╗██╔════╝██║██╔════╝    ██╔══██╗██╔════╝██╔════╝
        # ███████║███████╗██║██║         ██║  ██║███████╗█████╗  
        # ██╔══██║╚════██║██║██║         ██║  ██║╚════██║██╔══╝  
        # ██║  ██║███████║██║╚██████╗    ██████╔╝███████║███████╗
        # ╚═╝  ╚═╝╚══════╝╚═╝ ╚═════╝    ╚═════╝ ╚══════╝╚══════╝
        
        asic_dse_cli = rg_ds.AsicDseCLI()
        asic_dse_fields = asic_dse_cli.get_dataclass_fields()
        # asic_dse_fields["keys"] += rg_cli_fields["keys"]
        # asic_dse_fields["dtypes"] += rg_cli_fields["dtypes"]
        # asic_dse_fields["defaults"] += rg_cli_fields["defaults"]

        # Make a custom dataclass for asic dse input arguments
        AsicDseArgs = rg_ds.get_dyn_class(
            cls_name = "AsicDseArgs",
            fields = asic_dse_fields,
            bases= (rg_ds.AsicDseCLI, ))
        

        # AsicDseArgs = make_dataclass(
        #     "AsicDseArgs", 
        #     fields = [ (name, dtype, field(default_factory=lambda: default)) for name, dtype, default in zip(asic_dse_fields["keys"], asic_dse_fields["dtypes"], asic_dse_fields["defaults"]) ], 
        #     bases = (rg_ds.AsicDseCLI,)
        # )

        if self.alu_tests is None:
            self.alu_tests = []

            #     _   _   _   _  __   ___    ___ ___   _____      _____ ___ ___   _____ ___ ___ _____ 
            #    /_\ | | | | | | \ \ / / |  / __|_ _| / __\ \    / / __| __| _ \ |_   _| __/ __|_   _|
            #   / _ \| |_| |_| |  \ V /| |__\__ \| |  \__ \\ \/\/ /| _|| _||  _/   | | | _|\__ \ | |  
            #  /_/ \_\____\___/    \_/ |____|___/___| |___/ \_/\_/ |___|___|_|     |_| |___|___/ |_|  

            alu_sweep_config = os.path.expanduser(f"{self.asic_dse_inputs}/sweeps/alu_sweep.yml")
            tool_env_conf_path = os.path.expanduser(f"{self.asic_dse_inputs}/sys_configs/env.yml")
            # Init the arguments we want to use for this test
            asic_dse_args = AsicDseArgs(
                # tool_env_conf_path = tool_env_conf_path,
                design_sweep_config = alu_sweep_config,
            )
            alu_sweep_args = RadGenArgs(
                override_outputs = True,
                project_name = "alu",
                # top_config_path = self.top_config_path,
                subtools = ["asic_dse"],
                subtool_args = asic_dse_args,
            )
            alu_sweep_test = Test(rad_gen_args = alu_sweep_args, test_name="alu_sweep")
            self.alu_tests.append(alu_sweep_test)
            
            #     _   _   _   _   _____      _____ ___ ___   ___  ___ ___ _  _ _____    __  _  _   _   __  __ __  __ ___ ___  __  
            #    /_\ | | | | | | / __\ \    / / __| __| _ \ | _ \/ _ \_ _| \| |_   _|  / / | || | /_\ |  \/  |  \/  | __| _ \ \ \ 
            #   / _ \| |_| |_| | \__ \\ \/\/ /| _|| _||  _/ |  _/ (_) | || .` | | |   | |  | __ |/ _ \| |\/| | |\/| | _||   /  | |
            #  /_/ \_\____\___/  |___/ \_/\_/ |___|___|_|   |_|  \___/___|_|\_| |_|   | |  |_||_/_/ \_\_|  |_|_|  |_|___|_|_\  | |

            
            alu_config = os.path.expanduser(f"{self.asic_dse_inputs}/alu/configs/alu_period_2.0.yaml")
            top_lvl_mod = "alu_ver"
            flow_mode = "hammer"
            asic_dse_args = AsicDseArgs(
                tool_env_conf_paths = [tool_env_conf_path],
                flow_conf_paths = self.sys_configs + [alu_config],
                top_lvl_module = top_lvl_mod,
                hdl_path = os.path.expanduser(f"{self.asic_dse_inputs}/alu/rtl"),
                stdcell_lib__pdk_name = "asap7",
            )
            alu_asic_flow_args = RadGenArgs(
                project_name = "alu",
                subtools = ["asic_dse"],
                subtool_args = asic_dse_args,
                manual_obj_dir = os.path.join(self.asic_dse_outputs, top_lvl_mod, f"{top_lvl_mod}_{flow_mode}_{ci_test_obj_dir_suffix}"),
            )
            alu_test = Test(rad_gen_args = alu_asic_flow_args, test_name = "alu_hammer_flow")
            self.alu_tests.append(alu_test)
            #     _   _   _   _   _____      _____ ___ ___   ___  ___ ___ _  _ _____    __   ___ _   _ ___ _____ ___  __  __   ___ _    _     __  
            #    /_\ | | | | | | / __\ \    / / __| __| _ \ | _ \/ _ \_ _| \| |_   _|  / /  / __| | | / __|_   _/ _ \|  \/  | | _ \ |  | |    \ \ 
            #   / _ \| |_| |_| | \__ \\ \/\/ /| _|| _||  _/ |  _/ (_) | || .` | | |   | |  | (__| |_| \__ \ | || (_) | |\/| | |  _/ |__| |__   | |
            #  /_/ \_\____\___/  |___/ \_/\_/ |___|___|_|   |_|  \___/___|_|\_| |_|   \ \   \___|\___/|___/ |_| \___/|_|  |_| |_| |____|____|  / /

            alu_config = os.path.expanduser(f"{self.asic_dse_inputs}/alu/configs/alu_custom_flow.yml")
            top_lvl_mod = "alu_ver"
            flow_mode = "custom"
            asic_dse_args = AsicDseArgs(
                run_mode = "parallel",
                flow_mode = flow_mode,
                tool_env_conf_paths = [tool_env_conf_path],
                flow_config_paths = [alu_config], # not supplying sys_configs as not needed in custom flow
                top_lvl_module = top_lvl_mod,
                manual_obj_dir = os.path.join(self.asic_dse_outputs, top_lvl_mod, f"{top_lvl_mod}_{flow_mode}_{ci_test_obj_dir_suffix}"),
                hdl_path = os.path.expanduser(f"{self.asic_dse_inputs}/alu/rtl"),
            )
            alu_asic_flow_args = RadGenArgs(
                project_name = "alu",
                subtools = ["asic_dse"],
                subtool_args = asic_dse_args,
            )
            alu_test = Test(rad_gen_args = alu_asic_flow_args, test_name = "alu_custom_flow")
            self.alu_tests.append(alu_test)

        if self.sram_tests is None:
            self.sram_tests = []
            #   ___ ___    _   __  __   ___ _____ ___ _____ ___ _  _ ___ ___    __  __   _   ___ ___  ___     ___ ___ _  _ 
            #  / __| _ \  /_\ |  \/  | / __|_   _|_ _|_   _/ __| || | __|   \  |  \/  | /_\ / __| _ \/ _ \   / __| __| \| |
            #  \__ \   / / _ \| |\/| | \__ \ | |  | |  | || (__| __ | _|| |) | | |\/| |/ _ \ (__|   / (_) | | (_ | _|| .` |
            #  |___/_|_\/_/ \_\_|  |_| |___/ |_| |___| |_| \___|_||_|___|___/  |_|  |_/_/ \_\___|_|_\\___/   \___|___|_|\_|
                                                                                                             
            sram_gen_config = os.path.expanduser(f"{self.asic_dse_inputs}/sweeps/sram_sweep.yml")
            asic_dse_args = AsicDseArgs(
                # tool_env_conf_path = tool_env_conf_path,
                design_sweep_config = sram_gen_config,
            )
            sram_gen_test = RadGenArgs(
                override_outputs = True,
                # top_config_path = self.top_config_path,
                subtools = ["asic_dse"],
                subtool_args = asic_dse_args,
            )

            sram_gen_test = Test(rad_gen_args=sram_gen_test, test_name="sram_gen")
            self.sram_tests.append(sram_gen_test)
            # The 128x32 single macro config should have been generated from the previous test execution
            
            #   ___ ___    _   __  __   ___ ___ _  _  ___ _    ___   __  __   _   ___ ___  ___  
            #  / __| _ \  /_\ |  \/  | / __|_ _| \| |/ __| |  | __| |  \/  | /_\ / __| _ \/ _ \ 
            #  \__ \   / / _ \| |\/| | \__ \| || .` | (_ | |__| _|  | |\/| |/ _ \ (__|   / (_) |
            #  |___/_|_\/_/ \_\_|  |_| |___/___|_|\_|\___|____|___| |_|  |_/_/ \_\___|_|_\\___/ 
                                                                                  
            sram_config = os.path.expanduser(f"{self.asic_dse_inputs}/sram/configs/sram_SRAM2RW128x32.yaml")
            top_lvl_mod = "sram_wrapper"
            alu_asic_flow_args = AsicDseArgs(
                # top_config_path = self.top_config_path,
                tool_env_conf_path = tool_env_conf_path,
                flow_config_paths = self.sys_configs + [sram_config],
                manual_obj_dir = os.path.join(self.asic_dse_outputs, top_lvl_mod, f"{top_lvl_mod}_{ci_test_obj_dir_suffix}"),
                sram_compiler = True,
                # Top level module Is used for logging so we don't want to pass to cli (the correct top level and other configs will be generated from previous test)
                top_lvl_module = top_lvl_mod,
            )
            single_sram_macro_test = RadGenArgs(
               subtools = ["asic_dse"],
               subtool_args = alu_asic_flow_args,
               no_use_arg_list = ["top_lvl_module"],
            )
            single_sram_macro_test = Test(rad_gen_args=single_sram_macro_test, test_name="sram_single_macro_hammer_flow")
            self.sram_tests.append(single_sram_macro_test)
            
            #   ___ ___    _   __  __   ___ _____ ___ _____ ___ _  _ ___ ___    __  __   _   ___ ___  ___  
            #  / __| _ \  /_\ |  \/  | / __|_   _|_ _|_   _/ __| || | __|   \  |  \/  | /_\ / __| _ \/ _ \ 
            #  \__ \   / / _ \| |\/| | \__ \ | |  | |  | || (__| __ | _|| |) | | |\/| |/ _ \ (__|   / (_) |
            #  |___/_|_\/_/ \_\_|  |_| |___/ |_| |___| |_| \___|_||_|___|___/  |_|  |_/_/ \_\___|_|_\\___/ 

            top_lvl_mod = "sram_macro_map_2x256x64"
            sram_compiled_macro_config = os.path.expanduser(f"{self.asic_dse_inputs}/sram/configs/compiler_outputs/sram_config__sram_macro_map_2x256x64.yaml" )
            asic_dse_args = AsicDseArgs(
                tool_env_conf_path = tool_env_conf_path,
                flow_config_paths = self.sys_configs + [sram_compiled_macro_config],
                manual_obj_dir = os.path.join(self.asic_dse_outputs, top_lvl_mod, f"{top_lvl_mod}_{ci_test_obj_dir_suffix}"),
                sram_compiler = True,
                top_lvl_module = top_lvl_mod,
            )
            sram_compiled_macro_test = RadGenArgs(
                # top_config_path=self.top_config_path,
                subtools = ["asic_dse"],
                subtool_args = asic_dse_args,
                no_use_arg_list = ["top_lvl_module"],
            )
            sram_compiled_macro_test = Test(rad_gen_args=sram_compiled_macro_test, test_name="sram_compiled_macro_hammer_flow")

            self.sram_tests.append(sram_compiled_macro_test)
        if self.noc_tests is None:
            self.noc_tests = []

            #   _  _  ___   ___   ___ _____ _      ___  _   ___    _   __  __   _____      _____ ___ ___    ___ ___ _  _ 
            #  | \| |/ _ \ / __| | _ \_   _| |    | _ \/_\ | _ \  /_\ |  \/  | / __\ \    / / __| __| _ \  / __| __| \| |
            #  | .` | (_) | (__  |   / | | | |__  |  _/ _ \|   / / _ \| |\/| | \__ \\ \/\/ /| _|| _||  _/ | (_ | _|| .` |
            #  |_|\_|\___/ \___| |_|_\ |_| |____| |_|/_/ \_\_|_\/_/ \_\_|  |_| |___/ \_/\_/ |___|___|_|    \___|___|_|\_|                                                                                               

            noc_sweep_config = os.path.expanduser(f"{self.asic_dse_inputs}/sweeps/noc_sweep.yml")
            asic_dse_args = AsicDseArgs(
                tool_env_conf_path = tool_env_conf_path,
                design_sweep_config = noc_sweep_config,
            )
            noc_sweep_test = RadGenArgs(
                project_name = "NoC",
                subtools = ["asic_dse"],
                subtool_args = asic_dse_args,
            )
            noc_sweep_test = Test(rad_gen_args=noc_sweep_test, test_name="noc_sweep")
            self.noc_tests.append(noc_sweep_test)
            # NoC SINGLE ASIC TEST [6]
            top_lvl_mod = "router_wrap_bk"
            noc_config = os.path.expanduser(f"{self.asic_dse_inputs}/NoC/configs/vcr_config_num_message_classes_5_buffer_size_20_num_nodes_per_router_1_num_dimensions_2_flit_data_width_124_num_vcs_5.yaml")
            asic_dse_args = AsicDseArgs(
                tool_env_conf_path = tool_env_conf_path,
                flow_config_paths = self.sys_configs + [noc_config],
                top_lvl_module = top_lvl_mod,
                hdl_path = os.path.expanduser(f"{self.asic_dse_inputs}/NoC/rtl/src"),
                manual_obj_dir=os.path.join(self.asic_dse_outputs, top_lvl_mod, f"{top_lvl_mod}_{ci_test_obj_dir_suffix}"),
            )
            
            noc_asic_test = RadGenArgs(
                # top_config_path = self.top_config_path,
                subtools = ["asic_dse"],
                subtool_args = asic_dse_args,
            )
            noc_asic_test = Test(rad_gen_args=noc_asic_test, test_name="noc_hammer_flow")
            self.noc_tests.append(noc_asic_test)

        if self.asic_dse_sweep_tests is None:
            self.asic_dse_sweep_tests = [alu_sweep_test, sram_gen_test, noc_sweep_test]

        
        #  ██████╗ ██████╗ ███████╗███████╗███████╗
        # ██╔════╝██╔═══██╗██╔════╝██╔════╝██╔════╝
        # ██║     ██║   ██║█████╗  █████╗  █████╗  
        # ██║     ██║   ██║██╔══╝  ██╔══╝  ██╔══╝  
        # ╚██████╗╚██████╔╝██║     ██║     ███████╗
        #  ╚═════╝ ╚═════╝ ╚═╝     ╚═╝     ╚══════╝

        coffe_cli = rg_ds.CoffeCLI()
        coffe_fields = coffe_cli.get_dataclass_fields()
        CoffeArgs = rg_ds.get_dyn_class(
            cls_name = "CoffeArgs",
            fields = coffe_fields,
            bases= (rg_ds.CoffeCLI,))

        if self.coffe_tests is None:
            self.coffe_tests = []

            #   ___ ___ _____ _ ___ ____  ___ _   _ _  _ ___ 
            #  | __| _ \_   _( )_  )__ / | _ \ | | | \| / __|
            #  | _||  _/ | | |/ / / |_ \ |   / |_| | .` \__ \
            #  |_| |_|   |_|   /___|___/ |_|_\\___/|_|\_|___/
            # fpga_arch_config = os.path.expanduser(f"{self.coffe_inputs}/fpt23/finfet_7nm_pt_asap7_L4_m6_rl_10.yaml")                    
            # coffe_cli_args = CoffeArgs(
            #     fpga_arch_conf_path = fpga_arch_config, 
            #     # hb_flows_conf_path = f"{self.coffe_inputs}/finfet_7nm_fabric_w_hbs/hb_flows.yml",
            #     max_iterations = 4,
            # )
        
            # 7nm with ALU + INV hardblocks this may take a while (5+ hrs) hehe
            fpga_arch_config = os.path.expanduser(f"{self.coffe_inputs}/finfet_7nm_fabric_w_hbs/finfet_7nm_fabric_w_hbs.yml")
            coffe_cli_args = CoffeArgs(
                fpga_arch_conf_path = fpga_arch_config, 
                # hb_flows_conf_path = f"{self.coffe_inputs}/finfet_7nm_fabric_w_hbs/hb_flows.yml",
                max_iterations = 1, # Low QoR but this is a unit test,
                area_opt_weight = 1,
                delay_opt_weight = 2
            )
            coffe_7nm_hb_test = RadGenArgs(
                top_config_path = self.top_config_path,
                subtools = ["coffe"],
                subtool_args = coffe_cli_args,
            )
            coffe_7nm_hb_test = Test(rad_gen_args=coffe_7nm_hb_test, test_name="coffe_custom_n_hb_flow")
            self.coffe_tests.append(coffe_7nm_hb_test)


        # ██╗ ██████╗    ██████╗ ██████╗ 
        # ██║██╔════╝    ╚════██╗██╔══██╗
        # ██║██║          █████╔╝██║  ██║
        # ██║██║          ╚═══██╗██║  ██║
        # ██║╚██████╗    ██████╔╝██████╔╝
        # ╚═╝ ╚═════╝    ╚═════╝ ╚═════╝ 
        
        ic_3d_cli = rg_ds.Ic3dCLI()
        ic_3d_fields = ic_3d_cli.get_dataclass_fields()
        # Make a custom dataclass for ic 3d input arguments
        # IC3DArgs = make_dataclass(
        #     "IC3DArgs", 
        #     fields = [ (name, dtype, field(default_factory=lambda: default)) for name, dtype, default in zip(ic_3d_fields["keys"], ic_3d_fields["dtypes"], ic_3d_fields["defaults"]) ], 
        #     bases = (rg_ds.Ic3dCLI,)
        # )
        IC3DArgs = rg_ds.get_dyn_class(
            cls_name = "Ic3dArgs",
            fields = ic_3d_fields,
            bases= (rg_ds.Ic3dCLI, ))
        

        if self.buff_dse_tests is None:
            self.buff_dse_tests = []
            # Buffer DSE Test
            input_config = os.path.expanduser(f"{self.ic_3d_inputs}/3D_ic_explore.yaml")
            ic_3d_cli_args = IC3DArgs(
                input_config_path = input_config,
                buffer_dse = True,
                use_latest_obj_dir = True
            )
            buffer_dse_test = RadGenArgs(
                subtools = ["ic_3d"],
                subtool_args = ic_3d_cli_args,
            )
            buffer_dse_test = Test(rad_gen_args=buffer_dse_test, test_name="buffer_dse")
            self.buff_dse_tests.append(buffer_dse_test)
            
            # Sensitivity Study Test
            # ic_3d_cli_args = rg_ds.Ic3dCLI(
            #     input_config_path = input_config,
            #     buffer_sens_study = True,
            # )
            # buffer_dse_test = rg_ds.RadGenCLI.cli_init(
            #     subtools = ["ic_3d"],
            #     subtool_args = ic_3d_cli_args,
            # )
            # buffer_dse_test = Test(rad_gen_args=buffer_dse_test, test_name="buffer_sens_study")
            # self.ic_3d_tests.append(buffer_dse_test)
        if self.pdn_tests is None:
            self.pdn_tests = []
            #PDN modeling Test
            ic_3d_cli_args = IC3DArgs(
                input_config_path = input_config,
                pdn_modeling = True,
            )
            pdn_test_cli = IC3DArgs(
                subtools = ["ic_3d"],
                subtool_args = ic_3d_cli_args,
            )
            pdn_test = Test(rad_gen_args=pdn_test_cli, test_name="pdn_modeling")
            self.pdn_tests.append(pdn_test)
        
        if self.config_parse_init_tests is None:
            # Careful this isn't copying these tests but putting references
            self.config_parse_init_tests = [
                *self.alu_tests,
                *self.sram_tests,
                *self.noc_tests,
                *self.coffe_tests,
                *self.buff_dse_tests,
                *self.pdn_tests
            ]
            # for test in self.config_parse_init_tests:
            #     test.rad_gen_args.just_config_init = True
            






def compare_dataframes(df1_name: str, df1: pd.DataFrame, df2_name: str, df2: pd.DataFrame):
    # Ensure the dataframes have the same shape
    if df1.shape != df2.shape:
        raise ValueError("Dataframes must have the same shape for comparison")

    # Initialize an empty dataframe to store the comparisons
    comparisons = pd.DataFrame(index=df1.index, columns=df1.columns)

    for column in df1.columns:
        for row_id in df1.index:
            value1 = df1.iloc[row_id].at[column]
            value2 = df2.iloc[row_id].at[column]
            # if pd.api.types.is_numeric_dtype(value1) and pd.api.types.is_numeric_dtype(value2):
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

        # Check if the column values are numerical
        # if pd.api.types.is_numeric_dtype(df1[column]):
        #     value1 = df1[column]
        #     value2 = df2[column]
        #     # Calculate the percentage difference for numerical columns
        #     comparisons[column] = ((value2 - value1) / value1) * 100
        #     comparisons[column] = comparisons[column].replace({np.nan: "Missing"})
        # else:
        #     diff_series = df1[column] == df2[column]
        #     # Mark string columns as different
        #     diff_series = diff_series.replace({True: "Equal", False: "Different"})

    return comparisons

def compare_dataframe_row(df1: pd.DataFrame, df2: pd.DataFrame, row_index: int):
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
                percent_diff = ((value2 - value1) / value1) * 100
                comparisons[column] = percent_diff
            else:
                # Handle cases where one or both values are missing
                comparisons[column] = "Missing Values"
        else:
            # Mark string columns as different
            if value1 != value2:
                comparisons[column] = "Different"
    
    # Convert the comparisons dictionary into a DataFrame
    comparison_df = pd.DataFrame.from_dict(comparisons, orient='index', columns=['Difference (%)'])
    
    return comparison_df

def compare_results(input_csv_path: str, ref_csv_path: str) -> pd.DataFrame:
    """
        Compares the results of an output csv generated by RAD-Gen and a reference csv, searched for in a specified directory
    """
    # This will be slow as we are basically doing an O(n) search for each input but that's ok for now
    input_df = pd.read_csv(input_csv_path)
    output_df = pd.read_csv(ref_csv_path)
    comp_df = compare_dataframe_row(input_df, output_df, 0)
    print(comp_df)


def dict_diff(d1, d2, path=""):
    """
    Compares two nested dictionaries
    """
    for k in d1:
        if k in d2:
            if isinstance(d1[k], dict):
                dict_diff(d1[k], d2[k], "%s -> %s" % (path, k) if path else k)
            elif isinstance(d1[k], float) and isinstance(d2[k],  float):
                if d1[k] != d2[k]:
                    percentage_diff = abs(d1[k] - d2[k]) / max(abs(d1[k]), abs(d2[k])) * 100
                    result = [
                        "%s: " % path,
                        " - %s : %s" % (k, d1[k]),
                        " + %s : %s" % (k, d2[k]),
                        " Percentage Difference: %.2f%%" % percentage_diff
                    ]
                    print("\n".join(result))
            else:
                if d1[k] != d2[k]:
                    result = ["%s: " % path, " - %s : %s" % (k, d1[k]), " + %s : %s" % (k, d2[k])]
                    print("\n".join(result))
        else:
            print("%s%s as key not in d2\n" % ("%s: " % path if path else "", k))


def parse_args() -> argparse.Namespace:
    top_lvl_parser = argparse.ArgumentParser(description="RADGen CI Test Suite")
    top_lvl_parser.add_argument("-p", "--just_print",  help="Don't execute test just print commands to console, this parses & compares results if they already exist", action='store_true')
    #subtools_group = top_lvl_parser.add_argument_group("Subtool Selection", "Select which subtools to run tests for")
    top_lvl_parser.add_argument("-conf", "--config_parse_init",  help="Run Configuration Parsing / Init Tests", action='store_true')
    top_lvl_parser.add_argument("-ic_3d", "--ic_3d",  help="Run IC 3D tests", action='store_true')
    top_lvl_parser.add_argument("-coffe", "--coffe",  help="Run COFFE test", action='store_true')
    top_lvl_parser.add_argument("-asic", "--asic_dse",  help="Run ASIC DSE tests", action='store_true')
    top_lvl_parser.add_argument("-alu", "--alu",  help="Run ALU tests", action='store_true')
    top_lvl_parser.add_argument("-sram", "--sram",  help="Run SRAM tests", action='store_true')
    top_lvl_parser.add_argument("-noc", "--noc",  help="Run NoC tests", action='store_true')
    top_lvl_parser.add_argument_group("Subtool Tests", "Select which subtool tests to run")
    top_lvl_parser.add_argument("-pdn", "--pdn_modeling",  help="Run PDN modeling test", action='store_true')
    top_lvl_parser.add_argument("-buff_dse", "--buff_dse_modeling",  help="Run Buff DSE test", action='store_true')
    top_lvl_parser.add_argument("-asic_dse_sweeps", "--asic_dse_sweeps",  help="Run ASIC DSE sweeps test", action='store_true')
    return top_lvl_parser.parse_args()


class EnhancedJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if dataclasses.is_dataclass(obj):
            return dataclasses.asdict(obj)
        return super().default(obj)

def rec_convert_dataclass_to_dict(obj):
    """
        Converts a dict / dataclass of nested dicts / dataclasses into a dictionary object
    """
    if dataclasses.is_dataclass(obj):
        return {k: rec_convert_dataclass_to_dict(v) for k, v in dataclasses.asdict(obj).items()}
    elif isinstance(obj, list):
        return [rec_convert_dataclass_to_dict(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: rec_convert_dataclass_to_dict(v) for k, v in obj.items()}
    # checks if instance is any primitive type, if its not then its a non dataclass class so we have to ignore for now
    elif not isinstance(obj, (str, int, float, bool)) and obj is not None:
        return None
    else:
        return obj




def run_tests(args: argparse.Namespace, rad_gen_home: str, tests: List[Test], subtool: str, result_path: str = None, golden_ref_path: str = None):
    golden_ref_base_path = os.path.expanduser( os.path.join(rad_gen_home, "unit_tests", "golden_results", subtool) )
    
    for idx, test in enumerate(tests):
        cmd_str, sys_args, sys_args_dict = test.rad_gen_args.get_rad_gen_cli_cmd(rad_gen_home)        
        print(f"Running Test {test.test_name}: {cmd_str}\n")
        if not args.just_print:   
            # sp.call(" ".join(cmd_str.split(" ") + ["|", "tee", f"{test.test_name}_unit_test_{idx}.log"]), env=cur_env, shell=True)
            rad_gen_args = argparse.Namespace(**sys_args_dict)
            ret_val = rg.main(rad_gen_args)
            if sys_args_dict.get("just_config_init"):
                # Now we compare the return value from the config initialization with some golden reference for this test
                json_text = json.dumps(rec_convert_dataclass_to_dict(ret_val), cls=EnhancedJSONEncoder, indent=4)
                with open(os.path.join(golden_ref_base_path, f"{test.test_name}_init.json"), "w") as f:
                    f.write(json_text)
                exit()
        
        out_csv_path = None
        # Parse result and compare
        # if subtool == "asic_dse":
        #     # Path of the golden reference output file 
        #     golden_ref_path = os.path.join(golden_ref_base_path, f"{test.rad_gen_args.subtool_args.top_lvl_module}_flow_report.csv")
            
        #     # Only thing that generates results is the asic flow so make sure it ran it
        #     if test.rad_gen_args.subtool_args.flow_config_paths != None and len(test.rad_gen_args.subtool_args.flow_config_paths) > 0:
        #         out_csv_path = os.path.join(test.rad_gen_args.subtool_args.manual_obj_dir, "flow_report.csv")
            
        #     # If the flow actually produced a csv then compare it
        #     if out_csv_path != None and os.path.exists(out_csv_path):
        #         res_df = compare_results(out_csv_path, golden_ref_path)
        #         print(res_df)
        #     else:
        #         pass
        #         # print("Warning: Seems like you don't have any results for this unit test, maybe there was an error or you didn't run the test?")
        # if subtool == "coffe":
        #     golden_ref_path = os.path.join(golden_ref_base_path, os.path.basename(os.path.splitext(test.rad_gen_args.subtool_args.fpga_arch_conf_path)[0]) + ".txt" )
        #     # print(golden_ref_path)
        #     # TODO remove hardcoding
        #     unit_test_report_path = os.path.expanduser("~/rad_gen/unit_tests/outputs/coffe/finfet_7nm_fabric_w_hbs/arch_out_dir/report.txt")
        #     # Make sure report was generated
        #     if os.path.isfile(golden_ref_path) and os.path.isfile(unit_test_report_path):
        #         unit_test_report_dict = coffe_parse.coffe_report_parser(rg_ds.Regexes(), unit_test_report_path)
        #         golden_report_dict = coffe_parse.coffe_report_parser(rg_ds.Regexes(), golden_ref_path)
        #         unit_test_dfs = []
        #         golden_report_dfs = []
        #         for u_v, g_v in zip(unit_test_report_dict.values(), golden_report_dict.values()):
        #             if isinstance(u_v, list):
        #                 unit_test_dfs.append( pd.DataFrame(u_v) )
        #             elif isinstance(u_v, dict):
        #                 unit_test_dfs.append( pd.DataFrame([u_v]))
                    
        #             if isinstance(g_v, list):
        #                 golden_report_dfs.append( pd.DataFrame(g_v) )
        #             elif isinstance(g_v, dict):
        #                 golden_report_dfs.append( pd.DataFrame([g_v]))

        #         for unit_df, golden_df in zip(unit_test_dfs, golden_report_dfs):
        #             comp_df = compare_dataframes("test", unit_df, "golden", golden_df)
        #             for l in rg_utils.get_df_output_lines(comp_df):
        #                 print(l)
        #     else:
        #         if not os.path.isfile(golden_ref_path):
        #             print(f"Warning: Golden reference file {golden_ref_path} does not exist")
        #         if not os.path.isfile(unit_test_report_path):
        #             print(f"Warning: Unit test report file {unit_test_report_path} does not exist, the test may have failed")
        # if subtool == "ic_3d":
        #     # Path of the golden reference output file 
        #     golden_ref_path = os.path.join(golden_ref_base_path, "buffer_summary_report.csv")
        #     out_csv_path = os.path.join(rad_gen_home, "ic_3d_reports", "buffer_summary_report.csv")
            
        #     # If the flow actually produced a csv then compare it
        #     if os.path.exists(out_csv_path):
        #         res_df = compare_results(out_csv_path, golden_ref_path)
        #         print(res_df)
        #     else:
        #         pass




cur_env = os.environ.copy()

def main():
    global cur_env
    
    args = parse_args()
    test_suite = TestSuite()




    # if args.config_parse_init:
    #     print("Running Configuration Parsing / Init Tests\n")
    #     run_tests(args, test_suite.rad_gen_home, test_suite.config_parse_init_tests, "config_parse_init", golden_ref_path = test_suite.golden_ref_path)

    # and not args.buff_dse_modeling
    run_all = True if not args.asic_dse and not args.coffe and not args.ic_3d else False

    # ASIC DSE SWEEP TESTS
    if args.asic_dse_sweeps:
        print("Running ASIC DSE sweeps tests\n")
        run_tests(args, test_suite.rad_gen_home, test_suite.asic_dse_sweep_tests, "asic_dse")
    if args.alu:
        print("Running ALU tests\n")
        run_tests(args, test_suite.rad_gen_home, test_suite.alu_tests, "asic_dse")
    if args.sram:
        print("Running SRAM tests\n")
        run_tests(args, test_suite.rad_gen_home, test_suite.sram_tests, "asic_dse")
    if args.noc:
        print("Running NoC tests\n")
        run_tests(args, test_suite.rad_gen_home, test_suite.noc_tests, "asic_dse")



    # if run_all or args.alu:

    #     else:
    #         print("Running ALU tests\n")
    #         run_tests(args, test_suite.rad_gen_home, test_suite.alu_tests, "asic_dse")



    #     print("Running SRAM tests\n")
    #     run_tests(args, test_suite.rad_gen_home, test_suite.sram_tests, "asic_dse")

    #     print("Running NoC tests\n")
    #     run_tests(args, test_suite.rad_gen_home, test_suite.noc_tests, "asic_dse")

    if run_all or args.coffe:
        print("Running COFFE tests\n")
        run_tests(args, test_suite.rad_gen_home, test_suite.coffe_tests, "coffe")
    
    # if run_all or args.pdn_modeling:
    #     print("Running PDN modeling tests\n")
    #     run_tests(args, test_suite.rad_gen_home, test_suite.pdn_tests, "ic_3d")
        
    if run_all or args.ic_3d:
        print("Running Buffer DSE tests\n")
        run_tests(args, test_suite.rad_gen_home, test_suite.buff_dse_tests, "ic_3d")

    # print("Running IC 3D tests\n")
    # run_tests(args, test_suite.rad_gen_home, test_suite.ic_3d_tests, "ic_3d")
    



if __name__ == "__main__":
    main()