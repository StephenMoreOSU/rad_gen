import os, sys
from dataclasses import dataclass
from dataclasses import field
import argparse
import yaml

from typing import List, Dict, Any, Tuple, Type, NamedTuple, Set, Optional

import pandas as pd
import numpy as np

# import rad_gen as rg

import src.common.data_structs as rg_ds
import src.coffe.parsing as coffe_parse
import src.common.utils as rg_utils
import subprocess as sp

import multiprocessing as mp

@dataclass
class Test:
    rad_gen_cli: rg_ds.RadGenCLI = None
    test_name: str = None

@dataclass 
class TestSuite:
    """
        Contains various rg_ds.RadGenCLI options to invoke the tool with a variety of tests
    """

    # Rad Gen top config is assumed to be shared for tests
    top_config_path: str = None
    # TODO pass this from cli so users can specify which rad_gen_home they are using
    rad_gen_home: str = "~/rad_gen"
    unit_test_home: str = None
    # input paths for subtools
    asic_dse_inputs: str = None
    coffe_inputs: str = None
    ic_3d_inputs: str = None

    # output paths for subtools
    asic_dse_outputs: str = None
    coffe_outputs: str = None
    ic_3d_outputs: str = None


    # ASIC DSE TESTS
    alu_tests: List[Test] = None
    sram_tests: List[Test] = None
    noc_tests: List[Test] = None
    # Design Config files containing tool / tech info which is used across all tests
    sys_configs: List[str] = None
    
    # COFFE TESTS
    coffe_tests: List[Test] = None

    # IC 3D TESTS
    ic_3d_tests: List[Test] = None


    def __post_init__(self):
        ci_test_obj_dir_suffix = "ci_test"

        if self.top_config_path is None:
            pass
            # Get top level information relevant for all tests
                # self.top_config_path = os.path.expanduser(f"{self.rad_gen_home}/unit_tests/top_lvl_configs/rad_gen_test_config.yml")
                # assert os.path.exists(self.top_config_path)
                # top_config_dict = rg_utils.parse_yml_config(self.top_config_path)
                # env_config_dict = rg_utils.parse_yml_config(top_config_dict["asic_dse"]["env_config_path"])
                # assert os.path.exists( os.path.expanduser(env_config_dict["env"]["rad_gen_home_path"]) )
                # self.rad_gen_home = os.path.expanduser(env_config_dict["env"]["rad_gen_home_path"])
                
        if self.unit_test_home is None:
            self.unit_test_home = os.path.expanduser(f"{self.rad_gen_home}/unit_tests")
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


        #  █████╗ ███████╗██╗ ██████╗    ██████╗ ███████╗███████╗
        # ██╔══██╗██╔════╝██║██╔════╝    ██╔══██╗██╔════╝██╔════╝
        # ███████║███████╗██║██║         ██║  ██║███████╗█████╗  
        # ██╔══██║╚════██║██║██║         ██║  ██║╚════██║██╔══╝  
        # ██║  ██║███████║██║╚██████╗    ██████╔╝███████║███████╗
        # ╚═╝  ╚═╝╚══════╝╚═╝ ╚═════╝    ╚═════╝ ╚══════╝╚══════╝
                                                       
        if self.alu_tests is None:
            self.alu_tests = []
            # ALU VLSI SWEEP TEST
            alu_sweep_config = os.path.expanduser(f"{self.asic_dse_inputs}/sweeps/alu_sweep.yml")
            env_config_path = os.path.expanduser(f"{self.asic_dse_inputs}/sys_configs/asic_dse_env.yml")
            asic_dse_cli = rg_ds.AsicDseCLI(
                env_config_path = env_config_path,
                design_sweep_config = alu_sweep_config,
            )
            alu_sweep_test = rg_ds.RadGenCLI(
                # top_config_path=self.top_config_path,
                subtools = ["asic_dse"],
                subtool_cli = asic_dse_cli,
            )
            alu_sweep_test = Test(rad_gen_cli=alu_sweep_test, test_name="alu_sweep")
            self.alu_tests.append(alu_sweep_test)
            # SINGLE ALU SWEEP TEST (HAMMER FLOW)
            alu_config = os.path.expanduser(f"{self.asic_dse_inputs}/alu/configs/alu_period_2.0.yaml")
            top_lvl_mod = "alu_ver"
            flow_mode = "hammer"
            asic_dse_cli = rg_ds.AsicDseCLI(
                flow_mode = flow_mode,
                env_config_path = env_config_path,
                flow_config_paths = self.sys_configs + [alu_config],
                top_lvl_module = top_lvl_mod,
                manual_obj_dir = os.path.join(self.asic_dse_outputs, top_lvl_mod, f"{top_lvl_mod}_{flow_mode}_{ci_test_obj_dir_suffix}"),
                hdl_path = os.path.expanduser(f"{self.asic_dse_inputs}/alu/rtl"),
            )
            alu_test = rg_ds.RadGenCLI(
                # top_config_path=self.top_config_path,
                subtools = ["asic_dse"],
                subtool_cli = asic_dse_cli,
            )
            alu_test = Test(rad_gen_cli=alu_test, test_name="alu_hammer_flow")

            self.alu_tests.append(alu_test)
            # SINGLE ALU SWEEP TEST (CUSTOM PARALLEL FLOW)
            alu_config = os.path.expanduser(f"{self.asic_dse_inputs}/alu/configs/alu_custom_flow.yml")
            top_lvl_mod = "alu_ver"
            flow_mode = "custom"
            asic_dse_cli = rg_ds.AsicDseCLI(
                run_mode = "parallel",
                flow_mode = flow_mode,
                env_config_path = env_config_path,
                flow_config_paths = [alu_config],
                top_lvl_module = top_lvl_mod,
                manual_obj_dir = os.path.join(self.asic_dse_outputs, top_lvl_mod, f"{top_lvl_mod}_{flow_mode}_{ci_test_obj_dir_suffix}"),
                hdl_path = os.path.expanduser(f"{self.asic_dse_inputs}/alu/rtl"),
            )
            alu_test = rg_ds.RadGenCLI(
                # top_config_path=self.top_config_path,
                subtools = ["asic_dse"],
                subtool_cli = asic_dse_cli,
            )
            alu_test = Test(rad_gen_cli=alu_test, test_name="alu_custom_flow")
            self.alu_tests.append(alu_test)

        if self.sram_tests is None:
            self.sram_tests = []
            # SRAM STITCHED & MACRO GENERATION TEST 
            sram_gen_config = os.path.expanduser(f"{self.asic_dse_inputs}/sweeps/sram_sweep.yml")
            asic_dse_cli = rg_ds.AsicDseCLI(
                env_config_path = env_config_path,
                design_sweep_config = sram_gen_config,
            )
            sram_gen_test = rg_ds.RadGenCLI(
                # top_config_path=self.top_config_path,
                subtools = ["asic_dse"],
                subtool_cli = asic_dse_cli,
            )
            sram_gen_test = Test(rad_gen_cli=sram_gen_test, test_name="sram_gen")
            self.sram_tests.append(sram_gen_test)
            # The 128x32 single macro config should have been generated from the previous test execution
            # SRAM SINGLE MACRO ASIC TEST
            sram_config = os.path.expanduser(f"{self.asic_dse_inputs}/sram/configs/sram_SRAM2RW128x32.yaml")
            top_lvl_mod = "sram_wrapper"
            asic_dse_cli = rg_ds.AsicDseCLI(
                # top_config_path = self.top_config_path,
                env_config_path = env_config_path,
                flow_config_paths = self.sys_configs + [sram_config],
                manual_obj_dir = os.path.join(self.asic_dse_outputs, top_lvl_mod, f"{top_lvl_mod}_{ci_test_obj_dir_suffix}"),
                sram_compiler = True,
                # Top level module Is used for logging so we don't want to pass to cli (the correct top level and other configs will be generated from previous test)
                top_lvl_module = top_lvl_mod,
            )
            single_sram_macro_test = rg_ds.RadGenCLI(
               subtools = ["asic_dse"],
               subtool_cli = asic_dse_cli,
               no_use_arg_list = ["top_lvl_module"],
            )
            single_sram_macro_test = Test(rad_gen_cli=single_sram_macro_test, test_name="sram_single_macro_hammer_flow")
            self.sram_tests.append(single_sram_macro_test)
            # SRAM SINGLE STICHED MACROS ASIC TEST 
            top_lvl_mod = "sram_macro_map_2x256x64"
            sram_compiled_macro_config = os.path.expanduser(f"{self.asic_dse_inputs}/sram/configs/compiler_outputs/sram_config__sram_macro_map_2x256x64.yaml" )
            asic_dse_cli = rg_ds.AsicDseCLI(
                env_config_path = env_config_path,
                flow_config_paths = self.sys_configs + [sram_compiled_macro_config],
                manual_obj_dir = os.path.join(self.asic_dse_outputs, top_lvl_mod, f"{top_lvl_mod}_{ci_test_obj_dir_suffix}"),
                sram_compiler = True,
                top_lvl_module = top_lvl_mod,
            )
            sram_compiled_macro_test = rg_ds.RadGenCLI(
                # top_config_path=self.top_config_path,
                subtools = ["asic_dse"],
                subtool_cli = asic_dse_cli,
                no_use_arg_list = ["top_lvl_module"],
            )
            sram_compiled_macro_test = Test(rad_gen_cli=sram_compiled_macro_test, test_name="sram_compiled_macro_hammer_flow")

            self.sram_tests.append(sram_compiled_macro_test)
        if self.noc_tests is None:
            self.noc_tests = []
            # NoC RTL PARAM SWEEP GEN TEST 
            noc_sweep_config = os.path.expanduser(f"{self.asic_dse_inputs}/sweeps/noc_sweep.yml")
            asic_dse_cli = rg_ds.AsicDseCLI(
                env_config_path = env_config_path,
                design_sweep_config = noc_sweep_config,
            )
            noc_sweep_test = rg_ds.RadGenCLI(
                subtools = ["asic_dse"],
                subtool_cli = asic_dse_cli,
            )
            noc_sweep_test = Test(rad_gen_cli=noc_sweep_test, test_name="noc_sweep")
            self.noc_tests.append(noc_sweep_test)
            # NoC SINGLE ASIC TEST [6]
            top_lvl_mod = "router_wrap_bk"
            noc_config = os.path.expanduser(f"{self.asic_dse_inputs}/NoC/configs/vcr_config_num_message_classes_5_buffer_size_20_num_nodes_per_router_1_num_dimensions_2_flit_data_width_124_num_vcs_5.yaml")
            asic_dse_cli = rg_ds.AsicDseCLI(
                env_config_path = env_config_path,
                flow_config_paths = self.sys_configs + [noc_config],
                top_lvl_module = top_lvl_mod,
                hdl_path = os.path.expanduser(f"{self.asic_dse_inputs}/NoC/rtl/src"),
                manual_obj_dir=os.path.join(self.asic_dse_outputs, top_lvl_mod, f"{top_lvl_mod}_{ci_test_obj_dir_suffix}"),
            )
            
            noc_asic_test = rg_ds.RadGenCLI(
                # top_config_path = self.top_config_path,
                subtools = ["asic_dse"],
                subtool_cli = asic_dse_cli,
            )
            noc_asic_test = Test(rad_gen_cli=noc_asic_test, test_name="noc_hammer_flow")
            self.noc_tests.append(noc_asic_test)

        
        #  ██████╗ ██████╗ ███████╗███████╗███████╗
        # ██╔════╝██╔═══██╗██╔════╝██╔════╝██╔════╝
        # ██║     ██║   ██║█████╗  █████╗  █████╗  
        # ██║     ██║   ██║██╔══╝  ██╔══╝  ██╔══╝  
        # ╚██████╗╚██████╔╝██║     ██║     ███████╗
        #  ╚═════╝ ╚═════╝ ╚═╝     ╚═╝     ╚══════╝

        if self.coffe_tests is None:
            self.coffe_tests = []
            # 7nm with ALU + INV hardblocks this may take a while (5+ hrs) hehe
            fpga_arch_config = os.path.expanduser(f"{self.coffe_inputs}/finfet_7nm_fabric_w_hbs/finfet_7nm_fabric_w_hbs.yml")
            coffe_cli_args = rg_ds.CoffeCLI(
                fpga_arch_conf_path = fpga_arch_config, 
                hb_flows_conf_path = f"{self.coffe_inputs}/finfet_7nm_fabric_w_hbs/hb_flows.yml",
                max_iterations = 1, # Low QoR but this is a unit test
            )
            coffe_7nm_hb_test = rg_ds.RadGenCLI(
                subtools = ["coffe"],
                subtool_cli = coffe_cli_args,
            )
            coffe_7nm_hb_test = Test(rad_gen_cli=coffe_7nm_hb_test, test_name="coffe_custom_n_hb_flow")
            self.coffe_tests.append(coffe_7nm_hb_test)


        # ██╗ ██████╗    ██████╗ ██████╗ 
        # ██║██╔════╝    ╚════██╗██╔══██╗
        # ██║██║          █████╔╝██║  ██║
        # ██║██║          ╚═══██╗██║  ██║
        # ██║╚██████╗    ██████╔╝██████╔╝
        # ╚═╝ ╚═════╝    ╚═════╝ ╚═════╝ 
                               
        if self.ic_3d_tests is None:
            self.ic_3d_tests = []
            # Buffer DSE Test
            input_config = os.path.expanduser(f"{self.ic_3d_inputs}/3D_ic_explore.yaml")
            ic_3d_cli_args = rg_ds.Ic3dCLI(
                input_config_path = input_config,
                buffer_dse = True
            )
            buffer_dse_test = rg_ds.RadGenCLI(
                subtools = ["ic_3d"],
                subtool_cli = ic_3d_cli_args,
            )
            buffer_dse_test = Test(rad_gen_cli=buffer_dse_test, test_name="buffer_dse")
            self.ic_3d_tests.append(buffer_dse_test)
            
            # Sensitivity Study Test
            ic_3d_cli_args = rg_ds.Ic3dCLI(
                input_config_path = input_config,
                buffer_sens_study = True,
            )
            buffer_dse_test = rg_ds.RadGenCLI(
                subtools = ["ic_3d"],
                subtool_cli = ic_3d_cli_args,
            )
            buffer_dse_test = Test(rad_gen_cli=buffer_dse_test, test_name="buffer_sens_study")
            self.ic_3d_tests.append(buffer_dse_test)

            # PDN modeling Test
            ic_3d_cli_args = rg_ds.Ic3dCLI(
                input_config_path = input_config,
                pdn_modeling = True,
            )
            buffer_dse_test = rg_ds.RadGenCLI(
                subtools = ["ic_3d"],
                subtool_cli = ic_3d_cli_args,
            )
            buffer_dse_test = Test(rad_gen_cli=buffer_dse_test, test_name="pdn_modeling")
            self.ic_3d_tests.append(buffer_dse_test)




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
    parser = argparse.ArgumentParser(description="RADGen CI Test Suite")
    parser.add_argument("-p", "--just_print",  help="Don't execute test just print commands to console, this parses & compares results if they already exist", action='store_true')

    return parser.parse_args()




def run_tests(args: argparse.Namespace, rad_gen_home: str, tests: List[Test], subtool: str, result_path: str = None, golden_ref_path: str = None):
    for idx, test in enumerate(tests):
        cmd_str, sys_args = test.rad_gen_cli.get_rad_gen_cli_cmd(rad_gen_home)        
        print(f"Running Test {test.test_name}: {cmd_str}")    
        if not args.just_print:   
            sp.call(" ".join(cmd_str.split(" ") + ["|", "tee", f"{test.test_name}_unit_test_{idx}.log"]), env=cur_env, shell=True)
        golden_ref_base_path = os.path.expanduser( os.path.join(rad_gen_home, "unit_tests", "golden_results", subtool) )
        out_csv_path = None
        # Parse result and compare
        if subtool == "asic_dse":
            # Path of the golden reference output file 
            golden_ref_path = os.path.join(golden_ref_base_path, f"{test.rad_gen_cli.subtool_cli.top_lvl_module}_flow_report.csv")
            
            # Only thing that generates results is the asic flow so make sure it ran it
            if test.rad_gen_cli.subtool_cli.flow_config_paths != None and len(test.rad_gen_cli.subtool_cli.flow_config_paths) > 0:
                out_csv_path = os.path.join(test.rad_gen_cli.subtool_cli.manual_obj_dir, "flow_report.csv")
            
            # If the flow actually produced a csv then compare it
            if out_csv_path != None and os.path.exists(out_csv_path):
                res_df = compare_results(out_csv_path, golden_ref_path)
                print(res_df)
            else:
                pass
                # print("Warning: Seems like you don't have any results for this unit test, maybe there was an error or you didn't run the test?")
        if subtool == "coffe":
            golden_ref_path = os.path.join(golden_ref_base_path, os.path.basename(os.path.splitext(test.rad_gen_cli.subtool_cli.fpga_arch_conf_path)[0]) + ".txt" )
            # print(golden_ref_path)
            # TODO remove hardcoding
            unit_test_report_path = os.path.expanduser("~/rad_gen/unit_tests/outputs/coffe/finfet_7nm_fabric_w_hbs/arch_out_dir/report.txt")
            # Make sure report was generated
            if os.path.isfile(golden_ref_path) and os.path.isfile(unit_test_report_path):
                unit_test_report_dict = coffe_parse.coffe_report_parser(rg_ds.Regexes(), unit_test_report_path)
                golden_report_dict = coffe_parse.coffe_report_parser(rg_ds.Regexes(), golden_ref_path)
                unit_test_dfs = []
                golden_report_dfs = []
                for u_v, g_v in zip(unit_test_report_dict.values(), golden_report_dict.values()):
                    if isinstance(u_v, list):
                        unit_test_dfs.append( pd.DataFrame(u_v) )
                    elif isinstance(u_v, dict):
                        unit_test_dfs.append( pd.DataFrame([u_v]))
                    
                    if isinstance(g_v, list):
                        golden_report_dfs.append( pd.DataFrame(g_v) )
                    elif isinstance(g_v, dict):
                        golden_report_dfs.append( pd.DataFrame([g_v]))

                for unit_df, golden_df in zip(unit_test_dfs, golden_report_dfs):
                    comp_df = compare_dataframes("test", unit_df, "golden", golden_df)
                    for l in rg_utils.get_df_output_lines(comp_df):
                        print(l)
            else:
                if not os.path.isfile(golden_ref_path):
                    print(f"Warning: Golden reference file {golden_ref_path} does not exist")
                if not os.path.isfile(unit_test_report_path):
                    print(f"Warning: Unit test report file {unit_test_report_path} does not exist, the test may have failed")
                




cur_env = os.environ.copy()

def main():
    global cur_env
    
    # num_cores = mp.cpu_count()
    # pool = mp.Pool(processes = num_cores)

    args = parse_args()
    test_suite = TestSuite()

    # tests_list = [
    #     (test_suite.alu_tests, "asic_dse"),
    #     (test_suite.sram_tests, "asic_dse"),
    #     (test_suite.noc_tests, "asic_dse"),
    #     (test_suite.coffe_tests, "coffe"),
    #     (test_suite.ic_3d_tests, "ic_3d"),
    # ]

    # results = [pool.apply_async(run_tests, (args, test_suite.rad_gen_home, tests, subtool)) for tests, subtool in tests_list]

    print("Running ALU tests\n")
    run_tests(args, test_suite.rad_gen_home, test_suite.alu_tests, "asic_dse")

    print("Running SRAM tests\n")
    run_tests(args, test_suite.rad_gen_home, test_suite.sram_tests, "asic_dse")

    print("Running NoC tests\n")
    run_tests(args, test_suite.rad_gen_home, test_suite.noc_tests, "asic_dse")

    print("Running COFFE tests\n")
    run_tests(args, test_suite.rad_gen_home, test_suite.coffe_tests, "coffe")
    
    print("Running IC 3D tests\n")
    run_tests(args, test_suite.rad_gen_home, test_suite.ic_3d_tests, "ic_3d")
    



if __name__ == "__main__":
    main()