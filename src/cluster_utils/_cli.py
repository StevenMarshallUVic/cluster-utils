"""Handle running functions from command line.

NOTE: Must be backward compatible with python 3.9.25 for use on clusters.
"""

# Needed for backward compatibility of type hints using pipe operator
from __future__ import annotations
import argparse
import logging
import os
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

from cluster_utils import PACKAGE_NAME
from cluster_utils._config import ClusterConfig
from cluster_utils._paths import SrcPaths, ProjectPaths
from cluster_utils._utils import ON_CLUSTER
from cluster_utils._utils.venv import VenvCreator

if ON_CLUSTER:
    from cluster_utils._utils.lmod import LmodModuleLoader

logger = logging.getLogger(__name__)


def init_project(args: Iterable[str] | None = None) -> None:
    """Command for initializing a project's file structure for use with
    the cluster-utils framework.

    Parameters
    ----------
    args
        (Optional) When provided, uses the given args instead of command line
        arguments.
    """

    logger.info("Initializing project...")
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
        logger.warning(
            "`--account` flag not provided. "
            "Please specify Digital Research Alliance of Canada account to "
            "charge usage to (e.g. 'def-name')?"
        )
        manual_account = input(
            "INPUT: Account (leave blank to skip): "
        )
        if manual_account:
            account = manual_account

    project_paths = ProjectPaths(args.project_dir)
    files_to_check = [
        project_paths.cluster_config_toml,
        project_paths.cluster_runner_script,
    ]
    if account:
        files_to_check.append(project_paths.account_txt)

    existing_files = [p for p in files_to_check if p.exists()]
    force: bool = args.force
    if existing_files:
        existing_files_str = ", ".join([str(f) for f in existing_files])
        if force:
            logger.warning(
                "One or more initialization files already exists "
                "in this directory, overwriting: %s.",
                existing_files_str,
            )
        else:
            raise FileExistsError(
                "One or more initialization files already exists in "
                f"this directory, skipping initialization: {existing_files_str}."
                "\nIf you want to overwrite these files, "
                "use the `-f`/`--force` flag."
            )

    # Copy config TOML to project directory
    project_paths.cluster_config_toml.write_text(
        SrcPaths.CLUSTER_CONFIG_TOML.read_text()
    )
    logger.info(
        "Default config created at '%s'.",
        project_paths.cluster_config_toml,
    )

    # Copy script templates to project src directory
    project_paths.src_dir.mkdir(exist_ok=True)
    project_paths.cluster_runner_script.write_text(
        SrcPaths.CLUSTER_RUNNER_SCRIPT.read_text()
    )
    logger.info(
        "Default cluster runner script created at '%s'."
        "Modify template to implement custom logic.",
        project_paths.cluster_runner_script,
    )

    # Write account text file if value provided
    if account:
        project_paths.account_txt.write_text(account)
        logger.info(
            "Account file created at '%s'.",
            project_paths.account_txt
        )

    if not is_project_paths_initialized(project_paths, account):
        raise Exception("Project directory structure failed to initialize.")

    logger.info("Project successfully initialized!")


def perform_run(args: Iterable[str] | None = None):
    """Command for submitting a run.

    Parameters
    ----------
    args
        (Optional) When provided, uses the given args instead of command line
        arguments.
    """
    # TODO: Write tests

    logger.info("Performing run...")
    parser = argparse.ArgumentParser(
        prog="Cluster Run Launcher",
        description="Handles launching a run on a cluster.",
        add_help=True,
    )
    parser.add_argument(
        "-d", "--project-dir",
        help="(Optional) Root directory of project to initialize. "
             "When not provided, defaults to current working directory.",
        type=Path,
        default=Path.cwd(),
        required=False,
    )
    args, _ = parser.parse_known_args(args)

    # TODO: Create dataclass for storing runtime args?
    paths = ProjectPaths(args.project_dir)
    if not is_project_paths_initialized(paths):
        raise RuntimeError(
            "Trying to perform run on project that has not been initialized. "
            "Run `cluster-init` first to initialize project file structure."
        )

    config = ClusterConfig.from_toml(paths.cluster_config_toml)

    if ON_CLUSTER:
        LmodModuleLoader().load_modules(config.login_environment.modules)

    logger.info("Initializing run virtual environment...")
    VenvCreator(paths, config.login_environment).create_and_initialize_venv()

    logger.info("Passing execution to virtual environment in background...")

    # Run login script in background
    sys.stdout.flush()
    log_fd = os.open(paths.log_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
    subprocess.Popen(
        [
            "python", paths.cluster_runner_script,
            "--log-level", str(logging.getLogger(PACKAGE_NAME).getEffectiveLevel())
        ] + sys.argv[1:],
        env=os.environ.copy(),
        stdout=log_fd,
        stderr=subprocess.STDOUT,
        close_fds=True,
    )
    os.close(log_fd)
    exit(0)
    # os.execvp("python", ["python", paths.login_script])


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

    for file, log_name in {
        paths.cluster_config_toml: "config",
        paths.cluster_runner_script: "compute script",
    }.items():
        if not file.is_file():
            logger.warning(
                "Could not find %s at '%s'.",
                log_name,
                file,
            )
            return False

    if paths.account_txt.is_file():
        account_contents = paths.account_txt.read_text().strip()
        if account:
            if account_contents.strip() != account:
                logger.warning(
                    "Expected account '%s', got account '%s'.",
                    account,
                    account_contents,
                )
                return False
        elif len(account_contents) == 0:
            logger.warning(
                "Empty account file at '%s'.",
                paths.account_txt,
            )
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
