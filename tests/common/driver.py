from __future__ import annotations
import os, sys

from typing import Any

import argparse
import rad_gen as rg
import src.common.data_structs as rg_ds

def run_rad_gen(rg_args: rg_ds.RadGenArgs, rg_home: str, just_print: bool = False) -> Any | None:
    cmd_str, sys_args, sys_kwargs = rg_args.get_rad_gen_cli_cmd(rg_home)
    print(f"Running: {cmd_str}")
    ret_val = None
    if not just_print:
        args_ns = argparse.Namespace(**sys_kwargs) 
        ret_val = rg.main(args_ns) 
    return ret_val
    
