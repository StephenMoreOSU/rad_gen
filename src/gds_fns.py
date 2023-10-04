#!/usr/bin/python3

# Scale the final GDS by a factor of 4
# This is called by a tech hook that should be inserted post write_design

import sys, glob, os, re
from typing import List


# All functions in this file will take in [gds_tool, cell_list, gds_file]

            
# Args are [stdcells, gds_file, gds_function]
def main(argv: List[str]):
    stdcells = argv[0]
    gds_file = argv[1]
    gds_function = argv[2]
    try:
        # Prioritize gdstk
        gds_tool = __import__('gdstk')
    except ImportError:
        try:
            print("gdstk not found, falling back to gdspy...")
            gds_tool = __import__('gdspy')
        except ImportError:
            print('Check your gdspy installation!')
            sys.exit()

    print(f"Using {gds_tool.__name__} to get area results from {gds_file}...")

    cell_list = [line.rstrip() for line in open(stdcells, 'r')]

    fn_to_call = getattr(sys.modules[__name__], gds_function, None)
    if callable(fn_to_call):
       ret_val = fn_to_call(gds_tool, cell_list, gds_file)
    
    return ret_val

def get_area(gds_tool, cell_list, gds_file):
    # TODO implement with gdspy as well
    if gds_tool.__name__ == 'gdstk':
        total_area = 0.0
        # load gds
        gds_lib = gds_tool.read_gds(infile=gds_file)
        top_cell = None
        for cell in gds_lib.cells:
            if cell.name == "TOPCELL":
                top_cell = cell
                break            
        for e in top_cell.polygons:
              total_area += e.area()
            
        return total_area