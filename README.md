# cluster-utils
Utilities for working with Digital Research Alliance of Canada clusters.

# TODO:
- [x] Create command line command that can be used to run job
- [x] Create command line command that can be used to initialize project
  - [x] Check project file structure to confirm that project has not already been initialized
    - [x] Include force argument to continue anyway with warning
- [x] Create TOML config file
  - [x] Create default config template that is copied to root of project directory when init command is run
  - [x] Field for modules to install
    - [x] Default is "python/3.12"

## Quickstart Guide
1. Run command `cluster-init` to initialize the project file structure.
   - Use `-h`/`--help` flag to see explanation of arguments.
2. Adjust `cluster_config.toml` for your given workflow.
3. Run command `cluster-run <args>` to submit a run.
   - Use `-h`/`--help` flag to see explanation of arguments.
