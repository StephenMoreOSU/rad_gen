#!/bin/bash

# Adds a path to 
pathadd() {
    if [ -d "$1" ] && [[ ":$PYTHONPATH:" != *":$1:"* ]]; then
        PYTHONPATH="${PYTHONPATH:+"$PYTHONPATH:"}$1"
    fi
}

# set env vars for RAD-Gen
RAD_GEN_HOME=$PWD
VLSI_HOME=$PWD/vlsi
HAMMER_HOME=$VLSI_HOME/hammer

pathadd $RAD_GEN_HOME
# pathadd $RAD_GEN_HOME/src

# We need to add all of the hammer submodules to the PYTHONPATH
pathadd $HAMMER_HOME/hammer/technology
pathadd $HAMMER_HOME/hammer/vlsi

# For now for all the pdks we want to use we have to add their paths
# There are things like sram_compilers used in different pdks which have the same module name
# so maybe we can only have one on the path?
tech_plugins=("asap7")
for tech_plugin in "${tech_plugins[@]}"; do
    pathadd $HAMMER_HOME/hammer/technology/${tech_plugin}
done



################################ This is not needed anymore (to the best of my knowledge)  ##########################
### If for some reason the hammer plugins are not found and vendor specifics need be used uncomment below ###########
# vendor_plugins=("cadence" "mentor" "synopsys")
# for vendor_plugin in "${vendor_plugins[@]}"; do
#     pathadd $VLSI_HOME/hammer-${vendor_plugin}-plugins
# done

flow_stages=("sim" "synthesis" "par" "power" "timing" "lvs" "drc" "formal" "sram_generator")

for flow_stage in "${flow_stages[@]}"; do
    pathadd $HAMMER_HOME/hammer/${flow_stage}
done


## PYTHONPATH for COFFE
# pathadd $RAD_GEN_HOME/COFFE
# pathadd $RAD_GEN_HOME/COFFE/coffe



## Conda env setup
conda deactivate && conda activate rad-gen-env