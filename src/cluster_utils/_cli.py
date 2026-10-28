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

from cluster_utils import PACKAGE_NAME, get_project_dir, init_logger, \
    VIRTUAL_ENV_ENV_VAR
from cluster_utils._config import ClusterConfig
from cluster_utils._paths import ProjectPaths, SrcPaths, VenvPaths
from cluster_utils._utils import ON_CLUSTER
from cluster_utils._utils.venv import VenvCreator
from cluster_utils._utils import io, project_init
from cluster_utils.utils import PythonPackage

if ON_CLUSTER:
    from cluster_utils._utils.lmod import LmodModuleLoader

logger = init_logger(__name__)


def initialize_project(arguments: Iterable[str] | None = None) -> None:
    """Command for initializing a project's file structure for use with
    the cluster-utils framework.

    Parameters
    ----------
    arguments
        (Optional) When provided, uses the given args instead of command line
        arguments.
    """

    parser = argparse.ArgumentParser(
        prog="Cluster Project Initialization",
        description="Handles initializing project for use with cluster-utils "
                    "framework.",
        add_help=True,
    )
    project_init.ProjectInitParams.add_arguments(parser)
    args = parser.parse_args(arguments)

    project_init.initialize_project(
        project_init.ProjectInitParams.from_args(args)
    )


def perform_run(arguments: Iterable[str] | None = None):
    """Command for submitting a run.

    Parameters
    ----------
    arguments
        (Optional) When provided, uses the given args instead of command line
        arguments.
    """
    # TODO: Write tests
    # TODO: Abstract out into functions

    logger.info("Performing run...")
    paths = ProjectPaths(get_project_dir())
    if not is_project_paths_initialized(paths):
        raise RuntimeError(
            "Trying to perform run on project that has not been initialized. "
            "Run `cluster-init` first to initialize project file structure."
        )

    config = ClusterConfig.from_toml(paths.cluster_config_toml)

    # TODO: Add branch for loading compute module if on compute node
    if ON_CLUSTER:
        LmodModuleLoader().purge_and_load_modules(config.login_environment.modules)

    # TODO: Add branch for creating venv on compute node if on compute node
    logger.info("Initializing run virtual environment...")
    requirements_file = config.login_environment.requirements_file
    venv = VenvCreator(
        paths=paths.venv_paths,
        requirements=tuple(
            PythonPackage.from_requirements_txt(requirements_file)
        ),
    ) if (requirements_file and requirements_file.is_file()) \
        else VenvCreator(paths.venv_paths)
    venv.create_and_initialize_venv()

    logger.info("Passing execution to virtual environment in background...")
    # Build command line arguments
    arguments = [
        "python", SrcPaths.RUNNER_SCRIPT,
        "--log-level", str(logging.getLogger(PACKAGE_NAME).getEffectiveLevel()),
        "--project-dir", paths.project_dir,
    ] + sys.argv[1:]

    # Run login script in background
    sys.stdout.flush()
    log_fd = os.open(paths.log_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
    subprocess.Popen(
        arguments,
        env=os.environ.copy(),
        stdout=log_fd,
        stderr=subprocess.STDOUT,
        close_fds=True,
    )
    os.close(log_fd)
    exit(0)
    # os.execvp("python", ["python", paths.login_script])


def update(arguments: Iterable[str] | None = None):
    parser = argparse.ArgumentParser(
        prog="Cluster Updater",
        description="Handles updating cluster-utils package to latest version.",
        add_help=True,
    )
    venv_arg = parser.add_argument(
        "-v", "--venv",
        dest="venv",
        help="Virtual environment to update package within.",
        type=Path,
        default=os.environ.get(VIRTUAL_ENV_ENV_VAR),
    )
    args = parser.parse_args(arguments)
    if args.venv is None:
        raise argparse.ArgumentError(
            venv_arg,
            f"Could not find {VIRTUAL_ENV_ENV_VAR} in environment. "
            f"Must provide '--venv' flag."
        )

    VenvCreator(VenvPaths(args.venv)).install_requirements()


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

    missing_template_files = io.get_missing_files(paths.template_paths)
    if len(missing_template_files) > 0:
        for missing_template_file in missing_template_files:
            logger.warning(
                "Could not find file at '%s'.",
                missing_template_file,
            )
        return False

    if account:
        if not paths.account_txt.is_file():
            logger.warning(
                "Account file not found at '%s'.",
                paths.account_txt,
            )
            return False

        if not io.does_file_contain_exactly(paths.account_txt, account):
            logger.warning(
                "Account file expected to contain '%s', found '%s'.",
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
