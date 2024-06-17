#!/bin/bash

# WARNING: This function deletes everything in the previous pytest.ini after the 'env =' string

# Function to escape special characters in environment variable values
escape_value() {
  echo "$1" #| sed 's/\\/\\\\/g; s/"/\\"/g'
}

# Temporary file to store the modified pytest.ini
tmp_file=$(mktemp)

# Copy the existing pytest.ini up to the 'env =' line into the temporary file
sed '/^env =/q' ${RAD_GEN_HOME}/pytest.ini > "$tmp_file"

# Append environment variables to pytest.ini in the required format
printenv | while IFS='=' read -r name value; do
  echo "    $name=$(escape_value "$value")" >> "$tmp_file"
done

# Special stuff for pythonpath
# Echo our pythonpath replacing abspaths w relative ones (relative to RAD_GEN_HOME)
pypath=$(echo $PYTHONPATH | sed -e 's|:|   |g' | sed -e 's|'$RAD_GEN_HOME/'||g')
echo "pythonpath = ${pypath}" >> "$tmp_file"

# Replace the original pytest.ini with the modified one
mv "$tmp_file" ${RAD_GEN_HOME}/pytest.ini