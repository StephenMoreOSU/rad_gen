#!/bin/bash

# Adds a path to the specified environment variable
# If the path is already in the environment variable, it will not be added again
pathadd() {
    local env_var="$1"
    local new_path="$2"

    if [ -d "$new_path" ] && [[ ":${!env_var}:" != *":$new_path:"* ]]; then
        export "$env_var=${!env_var:+"${!env_var}:"}$new_path"
    fi
}

# set env vars for RAD-Gen
export RAD_GEN_HOME=$PWD
export THIRD_PARTY_HOME=$RAD_GEN_HOME/third_party
export HAMMER_HOME=$THIRD_PARTY_HOME/hammer

pathadd "PYTHONPATH" "$RAD_GEN_HOME"
# pathadd $RAD_GEN_HOME/src

# We need to add all of the hammer submodules to the PYTHONPATH
hammer_submods=("technology" "vlsi")
for hammer_submod in "${hammer_submods[@]}"; do
    pathadd "PYTHONPATH" $HAMMER_HOME/hammer/${hammer_submod}
done

# For now for all the pdks we want to use we have to add their paths
# There are things like sram_compilers used in different pdks which have the same module name
# so maybe we can only have one on the path?
tech_plugins=("asap7")
for tech_plugin in "${tech_plugins[@]}"; do
    pathadd "PYTHONPATH" $HAMMER_HOME/hammer/technology/${tech_plugin}
done

flow_stages=("sim" "synthesis" "par" "power" "timing" "lvs" "drc" "formal" "sram_generator")

for flow_stage in "${flow_stages[@]}"; do
    pathadd "PYTHONPATH" $HAMMER_HOME/hammer/${flow_stage}
done

# Copy the newly set env to pytest.ini
${RAD_GEN_HOME}/scripts/cur_env_to_pytest.sh

## Conda env setup
which conda > /dev/null
if [ "$?" -eq "0" ]; then
    conda deactivate && conda activate rad-gen-env
else
    echo "Conda not found. Please install conda and try again"
    exit 1
fi

# Check if hammer already installed
python3 -m pip show hammer-vlsi > /dev/null
if [ "$?" -ne "0" ]; then
    # Install hammer as editable repo within conda env
    cd $HAMMER_HOME
    python3 -m pip install -e .
    cd - 
fi




################################ This is not needed anymore (to the best of my knowledge)  ##########################
### If for some reason the hammer plugins are not found and vendor specifics need be used uncomment below ###########
# vendor_plugins=("cadence" "mentor" "synopsys")
# for vendor_plugin in "${vendor_plugins[@]}"; do
#     pathadd $VLSI_HOME/hammer-${vendor_plugin}-plugins
# done

## PYTHONPATH for COFFE
# pathadd $RAD_GEN_HOME/COFFE
# pathadd $RAD_GEN_HOME/COFFE/coffe