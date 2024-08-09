#!/bin/bash

rg_path_repl() {
    IN_FPATH=$1
    if [ -f "$IN_FPATH" ]; then
        echo "Replacing any paths containing $RAD_GEN_HOME in $IN_FPATH with \${RAD_GEN_HOME}"
        sed -i -e 's|\~|'$HOME'|g' -e 's|'$RAD_GEN_HOME'|\${RAD_GEN_HOME}|g' $IN_FPATH
    else
        echo "Invalid file path provided as \$1"
        exit 1
    fi
}

# Make sure RAD_GEN_HOME is set as env var
if [ -z "$RAD_GEN_HOME" ]; then
    echo "Please set the RAD_GEN_HOME environment variable"
    exit 1
fi

# Search for all configuration files in the a user specified directory
IN_PATH=${1:-na}

if [ -d "$IN_PATH" ]; then
    echo "Searching for configuration files (.yaml | .yml | .json) in $IN_PATH"
    find $IN_PATH -type f -name "*.yaml" -o -name "*.yml" -o -name "*.json" | while read -r FILE;
    do
        echo "Replacing any paths containing $RAD_GEN_HOME in $FILE with \${RAD_GEN_HOME}"
        rg_path_repl $FILE
    done
elif [ -f "$IN_PATH" ]; then
    echo "Replacing any paths containing $RAD_GEN_HOME in $IN_PATH with \${RAD_GEN_HOME}"
    rg_path_repl $IN_PATH
else
    echo "Please provide a valid directory path as \$1"
    exit 1
fi