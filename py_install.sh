#!/bin/bash

PKG_MGR=${1:-"conda"}

if [ "${PKG_MGR}" != "conda" ] && [ "${PKG_MGR}" != "venv" ]; then
    echo "usage source py_install.sh conda or source py_install.sh venv"
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


if [ "${PKG_MGR}" = "conda" ]; then
    # conda env creation
    if [ "${CONDA_ENV_EXISTS}" != "0" ]; then
        conda env create -f "${RAD_GEN_HOME}/conda_env/env.yml" || return
            if [ -n "$CONDA_DEFAULT_ENV" ]; then
                conda deactivate || return
            fi
            conda activate rad-gen-env
        ENV_INIT=1
    fi
elif [ "${PKG_MGR}" = "venv" ]; then
    # exit if venv module not found
    if [ "${VENV_EXISTS}" != "0" ]; then
        echo "venv module not found. Please install python3 venv"
        return 1
    fi
    # venv creation
    if [ -d "${RAD_GEN_HOME}/rad-gen-venv" ]; then
        echo "Found existing rad-gen-venv do you wish to override it? [Yy/Nn]:"
        read yn
        while true; do
            case $yn in
                [Yy]* ) break;;
                [Nn]* ) return 1;;
                * ) echo "Please answer yes or no.";;
            esac
        done
    fi
    if [ "${VENV_EXISTS}" = "0" ] && [ "${ENV_INIT}" = "1" ]; then
        # Create venv
        python3 -m venv ${RAD_GEN_HOME}/rad-gen-venv && \
            source ${RAD_GEN_HOME}/rad-gen-venv/bin/activate && \
            pip install -r ${RAD_GEN_HOME}/requirements.txt
        ENV_INIT=1
    elif [ -f "${RAD_GEN_HOME}/rad-gen-venv/bin/activate" ]; then
        source ${RAD_GEN_HOME}/rad-gen-venv/bin/activate
        ENV_INIT=1
    fi
fi

# Check if hammer already installed
pip show hammer-vlsi > /dev/null
HAMMER_NOT_INSTALLED=$?
# Install additional dependancies in new env
if [ "${HAMMER_NOT_INSTALLED}" = "1" ] && [ "$ENV_INIT" = "1" ]; then
    # Check if dir is empty, means subrepos not initialized...
    if [ -z "$( ls -A $HAMMER_HOME )" ]; then
        git submodule init
        git submodule update
    fi
    # Install hammer as editable repo within conda env
    cd $HAMMER_HOME
    pip install -e .
    cd - > /dev/null
else
    echo "Conda not found. OR system python3 version < 3.9 OR venv module not installed"
    echo "Please install above dependancies and try again"
    return 1
fi

if [ ! -d $VTR_HOME/build ] && ["$ENV_INIT" = "1"]; then
	cd $VTR_HOME
	git submodule update --init --recursive .
	pip install -r requirements.txt
	cd - > /dev/null
else
    echo "Conda not found. OR system python3 version < 3.9 OR venv module not installed"
    echo "Please install above dependancies and try again"
    return 1
fi
