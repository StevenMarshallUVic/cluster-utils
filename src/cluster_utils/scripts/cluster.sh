#!/bin/bash
# ------------------------------------------------------------------------------
# Wrapper script for initializing run on a cluster.
#
# Use the '-h'/`--help` flag for information on accepted arguments.
#   See README.md for explanation of arguments.
# ------------------------------------------------------------------------------

# Enforce strict error-checking
set -euo pipefail

# Get root directory (directory this script is in)
ROOT_DIR="$(dirname "$(readlink -f "${BASH_SOURCE[0]}" 2>/dev/null||echo "$0")")"; readonly ROOT_DIR
SCRIPT_NAME="${0##*/}"

debug=false

# Save args for passing to python
args=("$@")

# Loop through command line arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --debug)
            debug=true
            shift;;
        *)
            shift;;
    esac
done

# Initialize modules
echo "INFO:${SCRIPT_NAME}:Initializing modules..."
if ! command -v module &> /dev/null; then
    echo "ERROR:${SCRIPT_NAME}:'module' command is not installed. Are you sure you're running this on a cluster?"
    exit 1
fi
if "$debug"; then
    module purge -q
    module load python/3.12
else
    module purge -q &> /dev/null
    module load python/3.12 &> /dev/null
fi

# Initialize virtual environment
venv_dir="${ROOT_DIR}/.venv"
echo "INFO:${SCRIPT_NAME}:Initializing python virtual environment..."
if "$debug"; then
    if [[ ! -d "$venv_dir" ]]; then
        virtualenv --no-download "$venv_dir"
    fi
    source "${venv_dir}/bin/activate"
    pip install --no-index --upgrade pip
    pip install --no-index --requirement "${ROOT_DIR}/requirements.txt"
else
    if [[ ! -d "$venv_dir" ]]; then
        virtualenv --no-download "$venv_dir" &> /dev/null
        source "${venv_dir}/bin/activate" &> /dev/null
        pip install --no-index --upgrade -qqq pip &> /dev/null
        pip install --no-index --requirement "${ROOT_DIR}/requirements.txt" &> /dev/null
    else
        source "${venv_dir}/bin/activate"
    fi
fi


pushd "$ROOT_DIR" &> /dev/null
# Pass command line arguments to python (last to allow for overriding defaults)
python -m src.cluster \
    --project-dir "${ROOT_DIR}" \
    --scratch-dir "${SCRATCH}" \
    "${args[@]}"
popd &> /dev/null
