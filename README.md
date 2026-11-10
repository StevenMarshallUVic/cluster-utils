# cluster-utils
Utilities for working with Digital Research Alliance of Canada clusters.

## Quickstart Guide
1. Create virtual environment.
   - On cluster: 
     - `module load StdEnv/2026 python/3.15.2 && virtualenv --no-download .venv && source .venv/bin/activate`
2. Install this repository as a python package:
    - `pip install git+https://github.com/StevenMarshallUVic/cluster-utils.git`
3. Run command `cluster-init` to initialize the project file structure.
   - Use `-h`/`--help` flag to see explanation of arguments.
4. Adjust `cluster_config.toml` and `src/cluster_workflow.py` to implement your given workflow.
5. Run command `cluster-update` while virtual environment is sourced to install login python package requirements specified in `cluster_config.toml`.
6. Run command `cluster-run <args>` to submit a run.
   - Use `-h`/`--help` flag to see explanation of arguments.
