#!/bin/bash

# Check if the input directory is provided
if [ -z "$1" ]; then
    echo "Usage: $0 <input_directory>"
    exit 1
fi

input_dir="$1"

echo "----------------------------------------------------------------------------------------------------------------------------------------------------------------"
# Use find to locate all CSV files recursively
find "$input_dir" -type f -name "*.csv" | while read -r report; do
    echo "report path: $report"
    echo ""
    column -s, -t < "$report" | less -#2 -N -S
echo "----------------------------------------------------------------------------------------------------------------------------------------------------------------"

done