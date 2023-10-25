import os, sys
import pandas as pd
import re

from typing import Dict, Any

import src.common.data_structs as rg_ds
import src.common.utils as rg_utils

def coffe_report_parser(res: rg_ds.Regexes, report_path: str) -> Dict[str, Any]:
    with open(report_path, 'r') as f:
        report_text = f.read()
    # subckt PPA parsing
    subckt_PPA_parse = False
    subckt_ppa_parse_headers = ["Subcircuit", "Area (um^2)", "Delay (ps)", "tfall (ps)", "trise (ps)", "Power at 250MHz (uW)"]
    subckt_PPA_rows = []

    # Tile Area parsing
    tile_area_parse = False
    tile_area_parse_headers = ["Block", "Total Area (um^2)", "Fraction of total tile area"]
    tile_area_rows = []

    # VPR Delays parsing
    # TODO change the output in coffe to remove whitespace between keys (Unfinished as is)
    vpr_delay_parse = False
    vpr_delay_headers = ["Path", "Delay (ps)"]
    vpr_delay_rows = []



    # The following parsers are single row of data spread across multiple lines
    # seperator_re = re.compile(r"[-]*")
    
    # Hardblock info parsing
    hardblock_parse = False
    hardblock_info_header = "HARDBLOCK INFORMATION"
    hardblock_info_row = {}

    # VPR Area parsing
    # TODO change the output in coffe to remove whitespace between keys (Unfinished as is)
    vpr_area_parse = False
    vpr_area_header = "VPR AREAS"
    vpr_area_row = {}
    
    # Summary parsing
    summary_parse = False
    summary_header = "SUMMARY"
    summary_row = {}



    # line used for multi line parsing rememberance
    prev_line = ""
    for line in report_text.split('\n'):
        # Flags & increments which are set and apply to the next line
        if all([hdr in line for hdr in subckt_ppa_parse_headers]):
            subckt_PPA_parse = True
            continue
        if all([hdr in line for hdr in tile_area_parse_headers]):
            tile_area_parse = True
            continue
        if all([hdr in line for hdr in vpr_delay_headers]):
            vpr_delay_parse = True
            continue
        

        # INFO: only works if there is a single line seperating the section title
        if hardblock_info_header in prev_line:
            hardblock_parse = True
            prev_line = ""
            continue
        if vpr_area_header in prev_line:
            vpr_area_parse = True
            prev_line = ""
            continue
        if summary_header in prev_line:
            summary_parse = True
            prev_line = ""
            continue


        # VPR Area Parse
        if vpr_area_parse:
            line_vals = res.coffe_key_w_spaces_rep_re.findall(line)
            # single row ie must have two values for key val pair
            if len(line_vals) == 0 or ( len(line_vals) > 0 and len(line_vals[0]) != 2 ):
                vpr_area_parse = False
                continue
            else:
                key, val = line_vals[0]
                vpr_area_row[key.strip()] = float(val)


                

        # Hardblock info parse
        if hardblock_parse:
            if len(line.split(":")) != 2:
                hardblock_parse = False
                continue
            key = line.split(":")[0].strip()
            val = res.wspace_re.sub(repl="", string = line.split(":")[1])
            if "Name" not in key:
                hardblock_info_row[key] = float(val)
            else:
                hardblock_info_row[key] = str(val)

        # Summary Parse
        if summary_parse:
            # Keys seperated with whitespace so have to use manual naming, didn't want to do this for VPR cus too many keys, just better to update report gen
            if "Tile Area" in line:
                summary_row["Tile Area (um^2)"] = float(res.decimal_re.findall(line)[0])
            elif "Representative Critical Path Delay" in line:
                summary_row["CPD (ps)"] = float(res.decimal_re.findall(line)[0]) 
            # Assuming cost to be last entry 
            # TODO change this its hacky
            elif "Cost (area^1 x delay^1)" in line:
                summary_row["Cost"] = float(res.decimal_re.findall(line)[0])
                summary_parse = False
                continue 

            

        # VPR Delay parse
        if vpr_delay_parse:
            # captures two groups, so returns a list of 2 ele tuples
            line_vals = res.coffe_key_w_spaces_rep_re.findall(line)
            if len(line_vals) == 0 or ( len(line_vals) > 0 and len(line_vals[0]) != len(vpr_delay_headers) ):
                vpr_delay_parse = False
                continue
            else:
                line_vals = line_vals[0]
                vpr_delay_row = {}
                # Change below line_vals[0] if there are more than two groups captured
                for val, header in zip(line_vals, vpr_delay_headers):
                    if header == "Path":
                        vpr_delay_row[header] = val.strip()
                    elif val != "n/a":
                        vpr_delay_row[header] = float(val)
                    else:
                        vpr_delay_row[header] = str(val)
                vpr_delay_rows.append(vpr_delay_row)


        
        # Tile Area parse
        if tile_area_parse:
            line_vals = [ele for ele in res.wspace_re.split(line) if ele != ""]
            if len(line_vals) != len(tile_area_parse_headers):
                tile_area_parse = False
                continue
            else:
                tile_area_row = {}
                for val, header in zip(line_vals, tile_area_parse_headers):
                    if header == "Block":
                        tile_area_row[header] = str(val)
                    elif header == "Total Area (um^2)":
                        tile_area_row[header] = float(val)
                    elif header == "Fraction of total tile area":
                        tile_area_row[header] = float(res.decimal_re.findall(val)[0])
                    else:
                        raise ValueError(f"Unexpected header {header} encountered in tile area parsing")
                tile_area_rows.append(tile_area_row)
        

        # Subcircuit PPA parse
        if subckt_PPA_parse:
            line_vals = [ele for ele in res.wspace_re.split(line) if ele != ""]
            if len(line_vals) != len(subckt_ppa_parse_headers):
                subckt_PPA_parse = False
                continue
            else:
                subckt_PPA_row = {}
                for val, header in zip(line_vals, subckt_ppa_parse_headers):
                    if header != "Subcircuit" and val != "n/a":
                        subckt_PPA_row[header] = float(val)
                    else:
                        subckt_PPA_row[header] = str(val)
                subckt_PPA_rows.append(subckt_PPA_row)

        # Save previous line
        prev_line = line

    # format return dict
    ret_dict = {
        "subckt_PPA": subckt_PPA_rows,
        "tile_area": tile_area_rows,
        "vpr_delay": vpr_delay_rows,
        "vpr_area": vpr_area_row,
        "hardblock_info": hardblock_info_row,
        "summary": summary_row
    }
    # Prints to console 
    # rg_utils.pretty(ret_dict, 4)

    return ret_dict


    
    



if __name__ == "__main__":
    coffe_report_parser(rg_ds.Regexes(),os.path.expanduser("~/rad_gen/unit_tests/golden_results/coffe/finfet_7nm_fabric_w_hbs.txt"))
