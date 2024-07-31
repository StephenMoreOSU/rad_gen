#!/bin/bash

# Run this file to setup the python environment for RAD-Gen

# Python env setup
python3 -c 'import sys; assert sys.version_info >= (3,9)' > /dev/null
PY_VERSION_VALID=$?

python3 -m venv --help > /dev/null
VENV_EXISTS=$?

conda env list | grep rad-gen-env > /dev/null
CONDA_ENV_EXISTS=$?

ENV_INIT=0

# conda env creation
if [ "${CONDA_ENV_EXISTS}" != "0" ]; then
    conda env create -f ${RAD_GEN_HOME}/env.yml
    conda deactivate && conda activate rad-gen-env
    ENV_INIT=1
fi

# venv creation
if [ ! -d "${RAD_GEN_HOME}/rad-gen-venv" ] && [ "${VENV_EXISTS}" == "0" ] && [ "${ENV_INIT}" == "0" ]; then
    python3 -m venv ${RAD_GEN_HOME}/rad-gen-venv
    source ${RAD_GEN_HOME}/rad-gen-venv/bin/activate
    pip install -r ${RAD_GEN_HOME}/requirements.txt
    ENV_INIT=1
fi

# Check if hammer already installed
python3 -m pip show hammer-vlsi > /dev/null
HAMMER_INSTALLED=$?
# Install additional dependancies in new env
if [ "${HAMMER_INSTALLED}" != "0" ] && [ "${ENV_INIT}" == "1" ]; then
    # Install hammer as editable repo within conda env
    cd $HAMMER_HOME
    python3 -m pip install -e .
    cd - 
else
    echo "Conda not found. OR system python3 version < 3.9 OR venv module not installed"
    echo "Please install above dependancies and try again"
    exit 1
fi