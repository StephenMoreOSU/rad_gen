
import csv
from matplotlib import pyplot as plt
import copy
import src.common.utils as rg_utils
import os, sys 
import glob 
import numpy as np


def get_unique_default_colors(num_colors) -> list:
    prop_cycle = plt.rcParams['axes.prop_cycle']
    colors = prop_cycle.by_key()['color']
    
    # If num_colors is greater than the number of default colors, generate additional unique colors
    if num_colors > len(colors):
        additional_colors = plt.cm.tab10(range(num_colors - len(colors)))
        colors.extend(additional_colors)
    
    return colors[:num_colors]

def pie_plot_from_dict(in_dict: dict, out_fpath: str):
    # Get labels and sizes from dictionary
    labels = list(in_dict.keys())
    sizes = list(in_dict.values())

    # Create pie chart
    plt.figure(figsize=(8, 8))
    plt.pie(sizes, labels=labels, autopct='%1.1f%%')
    plt.title('Pie Chart')
    plt.savefig(out_fpath)

def pie_plot_fpga_state(csv_fpath: str, iter_key: int, cat: str):
    iter_cat_key =  f"{cat.upper()}_UPDATE_ITER"
    state_dicts = rg_utils.read_csv_to_list(csv_fpath)
    state_row = None
    for state_dict in state_dicts:
        if state_dict.get(iter_cat_key) == str(iter_key):
            state_row = copy.deepcopy(state_dict)
            del state_row["TAG"]
            for key in list(state_row.keys()):
                if "_ITER" in key:
                    del state_row[key]
            break
    
    if state_row:
        # Get labels and sizes from dictionary
        sizes = np.array([ float(val)/1e6 for val in state_row.values() ])
        percent = 100.*sizes/sizes.sum()
        y = list(state_row.keys())
        colors = get_unique_default_colors(len(y))
        labels = ['{0} - {1:1.2f} %'.format(i,j) for i, j in zip(y, percent) ]
        
        plt.figure(figsize=(10, 6))
        patches, texts = plt.pie(sizes, colors=colors) #, labels=labels, autopct='%1.1f%%')
        
        # sort_legend = True
        # if sort_legend:
        #     patches, labels, dummy = zip(*sorted(zip(patches, labels, y),
        #                                         key=lambda sizes: sizes[2],
        #                                         reverse=True))
        plt.legend(patches, labels, loc='upper left', bbox_to_anchor=(-0.4, 1.),
           fontsize=8)
        # Create pie chart
        plt.title(f'{cat.upper()} Pie Chart')
        out_fpath = os.path.join(
            os.path.dirname(csv_fpath),
            f"{os.path.splitext(os.path.basename(csv_fpath))[0]}_iter_{iter_key}.png"
        )
        plt.tight_layout()
        plt.savefig(out_fpath)
    else:
        return None

def main():
    rad_gen_home = os.path.expanduser("~/Documents/rad_gen")
    coffe_unit_test_outputs = os.path.join(
        rad_gen_home,
        "unit_tests/outputs/coffe/finfet_7nm_fabric_w_hbs"
    )
    ctrl_outdir = os.path.join(
        coffe_unit_test_outputs,
        "arch_out_COFFE_CONTROL_TEST"
    )
    dut_outdir = os.path.join(
        coffe_unit_test_outputs,
        "arch_out_dir_stratix_iv_rrg"
    )
    csv_outdir = os.path.join(dut_outdir, "debug")
    csv_files = [y for x in os.walk(csv_outdir) for y in glob.glob(os.path.join(x[0], '*.csv'))]
    # for csv_file in glob.glob(f"{csv_outdir}/*.csv", recursive=True):
    for csv_file in csv_files:
        if "area" in os.path.basename(csv_file):
            cat = "area"
        elif "delay" in os.path.basename(csv_file):
            cat = "delay"
        elif "wire_length" in os.path.basename(csv_file):
            cat = "wire_length"
        else:
            continue
        iter_key = 0
        print(csv_file)
        ret_val = pie_plot_fpga_state(csv_file, iter_key, cat)
        while ret_val is not None:
            iter_key += 1
            ret_val = pie_plot_fpga_state(csv_file, iter_key, cat)


if __name__ == "__main__":
    main()