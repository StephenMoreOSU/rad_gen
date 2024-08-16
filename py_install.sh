#!/bin/bash

PKG_MGR=${1:-"conda"}

if [ "${PKG_MGR}" != "conda" ] && [ "${PKG_MGR}" != "venv" ]; then
    echo "usage ./py_install.sh conda or ./py_install.sh venv"
    return 1
fi

# Run this file to setup the python environment for RAD-Gen

# Python env setup
python3 -c 'import sys; assert sys.version_info >= (3,9)' > /dev/null
PY_VERSION_VALID=$?

python3 -m venv --help > /dev/null
VENV_EXISTS=$?

conda env list | grep rad-gen-env > /dev/null
CONDA_ENV_EXISTS=$?

ENV_INIT=1 # error code


if [ "${PKG_MGR}" == "conda" ]; then
    # conda env creation
    if [ "${CONDA_ENV_EXISTS}" != "0" ]; then
        conda env create -f ${RAD_GEN_HOME}/env.yml && \
            conda deactivate && \
            conda activate rad-gen-env
        ENV_INIT=$?
    fi
elif [ "${PKG_MGR}" == "venv" ]; then
    # exit if venv module not found
    if [ "${VENV_EXISTS}" != "0" ]; then
        echo "venv module not found. Please install python3 venv"
        return 1
    fi
    # venv creation
    if [ -d "${RAD_GEN_HOME}/rad-gen-venv" ]; then
        while true; do
            read -p "Found existing rad-gen-venv do you wish to override it? [Yy/Nn]:" yn
            case $yn in
                [Yy]* ) break;;
                [Nn]* ) return 1;;
                * ) echo "Please answer yes or no.";;
            esac
        done
    fi
    if [ "${VENV_EXISTS}" == "0" ] && [ "${ENV_INIT}" == "1" ]; then
        # Create venv
        python3 -m venv ${RAD_GEN_HOME}/rad-gen-venv && \
            source ${RAD_GEN_HOME}/rad-gen-venv/bin/activate && \
            pip install -r ${RAD_GEN_HOME}/requirements.txt
        ENV_INIT=$?
    elif [ -f "${RAD_GEN_HOME}/rad-gen-venv/bin/activate" ]; then
        source ${RAD_GEN_HOME}/rad-gen-venv/bin/activate
        ENV_INIT=$?
    fi
fi

# Check if hammer already installed
python3 -m pip show hammer-vlsi > /dev/null
HAMMER_INSTALLED=$?
# Install additional dependancies in new env
if [ "${HAMMER_INSTALLED}" != "0" ] && [ "${ENV_INIT}" == "0" ]; then
    # Check if dir is empty, means subrepos not initialized...
    if [ -z "$( ls -A $HAMMER_HOME )" ]; then
        git submodule init
        git submodule update
    fi
    # Install hammer as editable repo within conda env
    cd $HAMMER_HOME
    python3 -m pip install -e .
    cd - > /dev/null
else
    echo "Conda not found. OR system python3 version < 3.9 OR venv module not installed"
    echo "Please install above dependancies and try again"
    return 1
fi