#!/bin/bash
# ------------------------------------------------------------------------------
# Initialize environment on compute node for compute stage.
#
# Command Line Arguments
# --project-dir
#     Path to root directory of project.
# --python-module-path
#     Module path to python file to run.
# --debug
#     Whether to include additional debug logging.
# ------------------------------------------------------------------------------

SCRIPT_NAME="${0##*/}"

# Enforce strict error-checking.
set -euo pipefail

declare project_dir
declare python_module_path
debug=false

# Save args for passing to python
args=("$@")

# Loop through command line arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --project-dir)
            project_dir="$2"
            shift 2;;
        --python-module-path)
            python_module_path="$2"
            shift 2;;
        --debug)
            debug=true
            shift;;
        *)
            shift;;
    esac
done

# Enforce required command line arguments
if [[ ! -v project_dir ]]; then
    echo "ERROR:${SCRIPT_NAME}:Missing required command line argument '--project-dir'." >&2
    exit 1
fi
if [[ ! -v python_module_path ]]; then
    echo "ERROR:${SCRIPT_NAME}:Missing required command line argument '--python-module-path'." >&2
    exit 1
fi

# Initialize modules
echo "INFO:${SCRIPT_NAME}:Initializing modules..."
if ! command -v module &> /dev/null; then
    echo "ERROR:${SCRIPT_NAME}:'module' command is not installed. Are you sure you're running this on a cluster?"
fi
if "$debug"; then
    module purge -q
    module load python/3.12
else
    module purge -q &> /dev/null
    module load python/3.12 &> /dev/null
fi

# Initialize virtual environment
venv_dir="${SLURM_TMPDIR}/.venv"
echo "INFO:${SCRIPT_NAME}:Initializing python virtual environment..."
if "$debug"; then
        virtualenv --no-download "$venv_dir"
        source "${venv_dir}/bin/activate"
        pip install --no-index --upgrade pip
        pip install --no-index --requirement "${project_dir}/requirements.txt"
    else
        virtualenv --no-download "$venv_dir" &> /dev/null
        source "${venv_dir}/bin/activate" &> /dev/null
        pip install --no-index --upgrade -qqq pip &> /dev/null
        pip install --no-index --requirement "${project_dir}/requirements.txt" &> /dev/null
    fi

pushd "$project_dir" &> /dev/null
# Pass command line arguments to python (last to allow for overriding defaults)
python -m "$python_module_path" \
    --compute-dir "$SLURM_TMPDIR" \
    --array-job-index "$SLURM_ARRAY_TASK_ID" \
    "${args[@]}"
popd &> /dev/null
