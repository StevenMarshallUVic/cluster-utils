import argparse
import os
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

from cluster_utils._paths import SrcPaths, ProjectPaths
from cluster_utils._utils import LmodModuleLoader, VenvCreator, ON_CLUSTER


def init_project(args: Iterable[str] | None = None) -> None:
    """Command for initializing a project's file structure for use with
    the cluster-utils framework.

    Parameters
    ----------
    args
        (Optional) When provided, uses the given args instead of command line
        arguments.
    """

    print("Initializing project...")
    parser = argparse.ArgumentParser(
        prog="Cluster Project Initialization",
        description="Handles initializing project for use with cluster-utils "
                    "framework.",
        add_help=True,
    )
    parser.add_argument(
        "-a", "--account",
        help="(Optional) Account to charge slurm usage to. "
             "If not provided, you will be required to specify an account "
             "each time you submit a run.",
        type=str,
        required=False,
    )
    parser.add_argument(
        "-d", "--project_dir",
        help="(Optional) Root directory of project to initialize. "
             "When not provided, defaults to current working directory.",
        type=Path,
        default=Path.cwd(),
        required=False,
    )
    parser.add_argument(
        "-f", "--force",
        help="(Optional) Whether to overwrite any existing files that conflict with "
             "files generated during initialization.",
        action=argparse.BooleanOptionalAction,
        default=False,
    )
    parser.add_argument(
        "--no-input",
        help="(Optional) Bypass any manual input prompts.",
        action="store_true",
    )
    args = parser.parse_args(args)
    no_input: bool = args.no_input

    # Prompt user to specify account if flag was not provided
    account: str | None = args.account if "account" in args else None
    if account is None and not no_input:
        manual_account = input(
            "What Digital Research Alliance of Canada account should "
            "usage be charged to (e.g. 'def-name')?"
            "\nAccount (leave blank to skip): "
        )
        if manual_account:
            account = manual_account

    project_paths = ProjectPaths(args.project_dir)
    existing_files = [
        p for p in [
            project_paths.cluster_config_toml,
            project_paths.account_txt,
        ]
        if p.exists()
    ]
    force: bool = args.force
    if existing_files:
        if force:
            print(
                "WARNING: One or more initialization files already exists "
                f"in this directory, overwriting: {existing_files}."
            )
        else:
            raise FileExistsError(
                "Error: One or more initialization files already exists in "
                f"this directory, skipping initialization: {existing_files}."
                "\nIf you want to overwrite these files, "
                "use the `-f`/`--force` flag."
            )

    # Copy config TOML to project directory
    project_paths.cluster_config_toml.write_text(
        SrcPaths.CLUSTER_CONFIG_TOML.read_text()
    )
    print(f"Default config created at '{project_paths.cluster_config_toml}'.")

    # Write account text file if value provided
    if account:
        project_paths.account_txt.write_text(account)
        print(f"Account file created at '{project_paths.account_txt}'.")

    if not is_project_paths_initialized(project_paths, account):
        raise Exception("Project directory structure failed to initialize.")

    print("Project successfully initialized!")


def perform_run(args: Iterable[str] | None = None):
    """Command for submitting a run.

    Parameters
    ----------
    args
        (Optional) When provided, uses the given args instead of command line
        arguments.
    """
    # TODO: Write tests
    # TODO: Test on cluster

    print("Initializing project...")
    parser = argparse.ArgumentParser(
        prog="Cluster Run Launcher",
        description="Handles launching a run on a cluster.",
        add_help=True,
    )
    parser.add_argument(
        "-a", "--account",
        help="(Optional) Account to charge slurm usage to. "
             "If not provided, will search for account file in project.",
        type=str,
        required=False,
    )
    parser.add_argument(
        "-d", "--project_dir",
        help="(Optional) Root directory of project to initialize. "
             "When not provided, defaults to current working directory.",
        type=Path,
        default=Path.cwd(),
        required=False,
    )
    args = parser.parse_args(args)
    paths = ProjectPaths(args.project_dir)

    print(f"[Orchestrator] Starting with system default: {sys.version.split()[0]}")

    # ==========================================
    # 1. PARSE CONFIGS (Using default Python)
    # ==========================================
    # (You can use json, yaml, or configparser here)
    simulation_script = SrcPaths.PREPROCESS_SCRIPT

    # ==========================================
    # 2. LOAD MODULES VIA LMOD
    # ==========================================
    if ON_CLUSTER:
        LmodModuleLoader().load_modules([
            "StdEnv/2026",
            "python/3.14.7",
            "apptainer/1.5.4",
        ])

        # ==========================================
        # 3. VERIFY NEW ENVIRONMENT IN SUBPROCESS
        # ==========================================
        # Because Lmod modified os.environ, "python" now points to the new version!
        new_version = subprocess.check_output(
            ["python", "--version"],
            text=True
        ).strip()
        print(f"[Orchestrator] Subprocess environment verified. 'python' is now: {new_version}")

    # ==========================================
    # 4. DYNAMIC VIRTUAL ENVIRONMENT MANAGEMENT
    # ==========================================
    VenvCreator(paths).create_and_initialize_venv()

    # ==========================================
    # 4. HAND OFF TO NEW PYTHON & SUBMIT SBATCH
    # ==========================================
    print(f"[Orchestrator] Executing {simulation_script} with the updated stack...")

    # Clean up the print buffer before swapping
    sys.stdout.flush()

    # Run a preprocessing python script natively using the new environment
    # It will inherit the loaded modules seamlessly
    os.execvp("python", ["python", simulation_script])


def is_project_paths_initialized(
        paths: ProjectPaths,
        account: str | None = None,
) -> bool:
    """Determine whether a project directory structure reflects a
    properly initialized project.

    Parameters
    ----------
    paths
        Paths for project.
    account
        Account that is expected to be found in account file.

    Returns
    -------
    bool
        Whether the project directory structure reflects a properly
        initialized project.
    """

    if not paths.cluster_config_toml.is_file():
        print(f"Could not find config at '{paths.cluster_config_toml}'.")
        return False

    if paths.account_txt.is_file():
        account_contents = paths.account_txt.read_text().strip()
        if account:
            if account_contents.strip() != account:
                print(
                    f"Expected account '{account}', "
                    f"got account '{account_contents}'."
                )
                return False
        elif len(account_contents) == 0:
            print(f"Empty account file at '{paths.account_txt}'.")
            return False

    return True


def is_project_dir_initialized(
        project_dir: Path,
        account: str | None = None,
) -> bool:
    """Determine whether a project directory structure reflects a
    properly initialized project.

    Parameters
    ----------
    project_dir
        Root directory of the project.
    account
        Account that is expected to be found in account file.

    Returns
    -------
    bool
        Whether the project directory structure reflects a properly
        initialized project.
    """

    return is_project_paths_initialized(ProjectPaths(project_dir), account)
