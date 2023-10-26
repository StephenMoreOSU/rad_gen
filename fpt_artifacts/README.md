# FPT’23 Artifact Evaluation

# Environment Setup

Environment :

- HSPICE Version H-2013.03-SP1 32-BIT
- Debian 11 Linux kernel 5.10.0-26-amd64
- Conda 22.9.0

********Note: If it’s easier we can offer temporary access to our server which already has the environment setup********

********The below commands are executed sequentially in the order presented (top to bottom)********

## Clone Repo

```bash
# From home directory
cd ~
git clone --recurse-submodules git@github.com:StephenMoreOSU/rad_gen.git
cd rad_gen
```

## Tools Setup

```bash
# If on different machine source script to setup Hspice env
# If on UofT server: run 'source /fs1/eecg/vaughn/morestep/hw_sw_flows/scripts/setup_all_tools.sh'

conda env create -f env.yaml
# This env_setup.sh will activate conda env
source env_setup.sh
# To setup hammer subrepo python libs install as editable package
cd ~/rad_gen/vlsi/hammer
python3 -m pip install -e .
```







## Generating Fig 6. a & b Results

**Note: To add ESD area to results just add 1.048 um^2 to each area result**

```bash
# Change to the directory with all input configurations required to generate artifacts
cd ~/rad_gen/fpt_artifacts

# For Die to Die Area / Delay Buffer Modeling (Figure 6a):

# CSV Outputs for above command will be written to ~/rad_gen/fpt_artifacts/ic_3d_reports/buffer_summary_report.csv
# NOTE this file will be overridden each time you run rad_gen with the -b flag from this directory
# Human readable outputs will be send to stdout

# Generates the Full ESD (20fF) Buffer delay results, It generates all ubump pitches but figure only shows 1um pitch
python3 ../rad_gen.py -st ic_3d -b -c inputs/buffer_sizing_20f_esd.yaml | tee buffer_sizing_20f_esd.log

# Generates the No ESD Buffer delay results, It generates all ubump pitches but figure only shows 1um pitch
python3 ../rad_gen.py -st ic_3d -b -c inputs/buffer_sizing_no_esd.yaml | tee buffer_sizing_no_esd.log

# For PDN modeling (Figure 6b):
# Ouputs will be at stdout (at the bottom of log file for % of base die area)

# Generates the % of base die Taken from TSVs for 10mV IR drop Target (Green bars figure 6b)
python3 ../rad_gen.py -st ic_3d -p -c inputs/pdn_modeling_10mV_ir_homogenous.yaml | tee pdn_modeling_10mV_ir_homogenous.log

# Generates the % of base die Taken from TSVs for 10mV IR drop Target (Red bars figure 6b)
python3 ../rad_gen.py -st ic_3d -p -c inputs/pdn_modeling_20mV_ir_homogenous.yaml | tee pdn_modeling_20mV_ir_homogenous.log
```

## Generating Figures for Die to Die Delay Area Results

```bash
# There should be a vis.py file in ~/rad_gen/fpt_artifacts/ic_3d_reports
cd ~/rad_gen/fpt_artifacts/ic_3d_reports 

# To reproduce a similar plot to Fig. 6 (ie only use ubump pitch == 1um and n_stages == 2) run
python3 vis.py -f

# This will produce plots for buffers with subplot rows split across numbers of buffer stages for all ubumps
python3 vis.py
```

<!-- **Example output figure:**

![Untitled](FPT%E2%80%9923%20Artifact%20Evaluation%2015741af2adaa48bd9ced15385d8da70d/Untitled.png) -->





## Generating Fig 3. a & b Results

### WARNING: Each script below takes around 10-20 hours each to run 

```bash

# Results for each of these runs will show up in stdout and at ~/rad_gen/fpt_artifacts/coffe_outputs/<fabric_parameter_defined_dir>/arch_out_dir/reports.txt

# For pass gate m6 d = 1 results
python3 ../rad_gen.py -st coffe -f inputs/finfet_7nm_pt_asap7_L4_m6_rl_10.yaml -i 4 -d 1 -a 1 | tee fpga_fabric_sizing_pass_gate_m6_d1.log

# For pass gate m6 d = 2 results
python3 ../rad_gen.py -st coffe -f inputs/finfet_7nm_pt_asap7_L4_m6_rl_10.yaml -i 4 -d 2 -a 1 | tee fpga_fabric_sizing_pass_gate_m6_d2.log

# For pass gate m8 d = 1 results
python3 ../rad_gen.py -st coffe -f inputs/finfet_7nm_pt_asap7_L4_m8_rl_10.yaml -i 4 -d 1 -a 1 | tee fpga_fabric_sizing_pass_gate_m8_d1.log

# For pass gate m8 d = 2 results
python3 ../rad_gen.py -st coffe -f inputs/finfet_7nm_pt_asap7_L4_m8_rl_10.yaml -i 4 -d 2 -a 1 | tee fpga_fabric_sizing_pass_gate_m8_d2.log

# For transmission gate m6 d = 1 results
python3 ../rad_gen.py -st coffe -f inputs/finfet_7nm_tg_asap7_L4_m6_rl_5.yaml -i 4 -d 1 -a 1 | tee fpga_fabric_sizing_transmission_gate_m6_d1.log

# For transmission gate m6 d = 2 results
python3 ../rad_gen.py -st coffe -f inputs/finfet_7nm_tg_asap7_L4_m6_rl_5.yaml -i 4 -d 2 -a 1 | tee fpga_fabric_sizing_transmission_gate_m6_d2.log

# For transmission gate m8 d = 1 results
python3 ../rad_gen.py -st coffe -f inputs/finfet_7nm_tg_asap7_L4_m8_rl_5.yaml -i 4 -d 1 -a 1 | tee fpga_fabric_sizing_transmission_gate_m8_d1.log

# For transmission gate m8 d = 2 results
python3 ../rad_gen.py -st coffe -f inputs/finfet_7nm_tg_asap7_L4_m8_rl_5.yaml -i 4 -d 2 -a 1 | tee fpga_fabric_sizing_transmission_gate_m8_d2.log

```