#!/bin/bash

# Make sure RAD_GEN_HOME is set as env var
if [ -z "$RAD_GEN_HOME" ]; then
    echo "Please set the RAD_GEN_HOME environment variable"
    exit 1
fi

# Search for all configuration files in the a user specified directory
SEARCH_DPATH=${1:-na}
# PATH_2_ENV_VARS=${2:-na} # Flag telling script if we are moving from abs paths to env vars or the other way around

if [ -d "$SEARCH_DPATH" ]; then
    echo "Searching for configuration files (.yaml | .yml | .json) in $SEARCH_DPATH"
    find $SEARCH_DPATH -type f -name "*.yaml" -o -name "*.yml" -o -name "*.json" | while read -r FILE; do
        echo "Replacing any paths containing $RAD_GEN_HOME in $FILE with \${RAD_GEN_HOME}"
        sed -i -e 's|\~|'$HOME'|g' -e 's|'$RAD_GEN_HOME'|\${RAD_GEN_HOME}|g' $FILE
    done

else
    echo "Please provide a valid directory path as \$1"
    exit 1
fi