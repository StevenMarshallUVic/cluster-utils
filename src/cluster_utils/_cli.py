"""Handle running functions from command line.

NOTE: Must be backward compatible with python 3.9.25 for use on clusters.
"""

# Needed for backward compatibility of type hints using pipe operator
from __future__ import annotations
import argparse
import os
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

from cluster_utils import get_project_dir, init_logger, VENV_ENV_VAR
from cluster_utils._config import ClusterConfig, EnvironmentConfig
from cluster_utils._paths import ProjectPaths, VenvPaths, ComputePaths
from cluster_utils._utils import ON_CLUSTER
from cluster_utils._utils.venv import VenvCreator
from cluster_utils._utils import io, project_init
from cluster_utils.data import add_argument_to_parser
from cluster_utils.utils import PythonPackage

if ON_CLUSTER:
    from cluster_utils._utils.lmod import LmodModuleLoader

logger = init_logger(__name__)


def update(arguments: Iterable[str] | None = None) -> None:
    """Update package to latest version.

    Parameters
    ----------
    arguments
        (Optional) When provided, uses given args instead of command line args.
    """
    # TODO: Write tests

    parser = argparse.ArgumentParser(
        prog="Cluster Updater",
        description="Handles updating cluster-utils package to latest version.",
        add_help=True,
    )
    venv_arg = add_argument_to_parser(
        parser,
        None,
        None,
        "-v", "--venv",
        dest="venv",
        help="(Optional) Virtual environment to update package within. When "
             f"not provided, uses '{VENV_ENV_VAR}' environment variable.",
        type=Path,
        default=os.environ.get(VENV_ENV_VAR),
    )
    args = parser.parse_args(arguments)
    if args.venv is None:
        raise argparse.ArgumentError(
            venv_arg,
            f"Could not find '{VENV_ENV_VAR}' in environment. "
            "Must provide '--venv' flag."
        )

    VenvCreator(VenvPaths(args.venv)).install_requirements()


def initialize_project(arguments: Iterable[str] | None = None) -> None:
    """Command for initializing a project's file structure for use with
    the cluster-utils framework.

    Parameters
    ----------
    arguments
        (Optional) When provided, uses given args instead of command line args.
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
    """Command for submitting a run from a login node.

    Parameters
    ----------
    arguments
        (Optional) When provided, uses given args instead of command line args.
    """
    # TODO: Write tests

    paths = ProjectPaths(get_project_dir())

    logger.info("Updating package...")
    update(["--venv", str(paths.venv_paths.venv_dir)])

    if not is_project_paths_initialized(paths):
        raise RuntimeError(
            "Trying to perform run on project that has not been initialized. "
            "Run `cluster-init` first to initialize project file structure."
        )

    logger.info("Performing run...")
    config = ClusterConfig.from_toml(paths.cluster_config_toml)

    logger.info("Initializing run environment...")
    initialize_environment(config.login_environment, paths.venv_paths)

    logger.info("Passing execution to virtual environment in background...")
    sys.stdout.flush()
    log_fd = os.open(paths.log_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
    subprocess.Popen(
        _construct_runner_subprocess_args(paths),
        env=os.environ.copy(),
        stdout=log_fd,
        stderr=subprocess.STDOUT,
        close_fds=True,
    )
    os.close(log_fd)
    exit(0)


def perform_compute(arguments: Iterable[str] | None = None):
    """Command for performing compute logic on a compute node.

    Parameters
    ----------
    arguments
        (Optional) When provided, uses given args instead of command line args.
    """
    # TODO: Write tests

    parser = argparse.ArgumentParser(
        prog="Cluster Compute Launcher",
        description="Handles launching compute logic on compute node.",
        add_help=True,
    )
    slurm_tmp_dir_arg = add_argument_to_parser(
        parser,
        None,
        None,
        "--slurm-tmp-dir",
        dest="slurm_tmp_dir",
        help="(Optional) Path to directory allocated for slurm job. When not "
             f"provided, uses '{SLURM_TMP_DIR_ENV_VAR}' environment variable.",
        type=Path,
        default=os.environ.get(SLURM_TMP_DIR_ENV_VAR),
    )
    args = parser.parse_args(arguments)
    if args.slurm_tmp_dir is None:
        raise argparse.ArgumentError(
            slurm_tmp_dir_arg,
            f"Could not find '{SLURM_TMP_DIR_ENV_VAR}' in environment. "
            "Must provide '--slurm-tmp-dir' flag."
        )

    compute_paths = ComputePaths(args.slurm_tmp_dir)
    project_paths = ProjectPaths(get_project_dir())
    config = ClusterConfig.from_toml(project_paths.cluster_config_toml)

    logger.info("Initializing compute environment...")
    initialize_environment(
        config.login_environment,
        VenvPaths(compute_paths.venv_dir),
    )

    logger.info("Passing execution to virtual environment...")

    # Call runner script within venv
    subprocess.Popen(_construct_runner_subprocess_args(project_paths))


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


def initialize_environment(
        environment: EnvironmentConfig,
        venv_paths: VenvPaths,
) -> None:
    """Initialize environment using config.

    Initialization includes:
    - Loading modules (if on cluster)
    - Creating and initializing python virtual environment

    Parameters
    ----------
    environment
        Configuration to use when initializing environment.
    venv_paths
        Paths for virtual environment.
    """

    if ON_CLUSTER:
        LmodModuleLoader().purge_and_load_modules(environment.modules)

    requirements_file = environment.requirements_file
    venv = VenvCreator(
        paths=venv_paths,
        requirements=tuple(
            PythonPackage.from_requirements_txt(requirements_file)
        ) if (requirements_file and requirements_file.is_file())
        else tuple(),
    )
    venv.create_and_initialize_venv()


def _construct_runner_subprocess_args(project_paths: ProjectPaths):
    return [
        "python", "-m", "cluster_utils._cluster_runner",
        "--log-level", str(logger.getEffectiveLevel()),
        "--project-dir", project_paths.project_dir,
    ] + sys.argv[1:]
