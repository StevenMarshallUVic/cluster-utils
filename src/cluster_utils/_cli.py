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
from cluster_utils._paths import ProjectPaths, VenvPaths
from cluster_utils.data import add_argument_to_parser
from cluster_utils.utils import PythonPackage, ON_CLUSTER
from cluster_utils.utils import io, project_init
from cluster_utils.utils.venv import VenvCreator

if ON_CLUSTER:
    from cluster_utils.utils.lmod import LmodModuleLoader

logger = init_logger(__name__)


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

    project_init_params = project_init.ProjectInitParams.from_args(args)
    project_init.initialize_project(project_init_params)


def update(arguments: Iterable[str] | None = None) -> None:
    """Update virtual environment to latest version.

    Parameters
    ----------
    arguments
        (Optional) When provided, uses given args instead of command line args.
    """
    # TODO: Write tests

    logger.info("Updating virtual environment...")
    parser = argparse.ArgumentParser(
        prog="Cluster Updater",
        description="Handles updating virtual environment.",
        add_help=True,
    )
    add_argument_to_parser(
        parser,
        None,
        None,
        "--project-dir",
        help="(Optional) Root directory of project to initialize. "
             "When not provided, infers project directory from relative "
             "file structure of python virtual environment.",
        type=Path,
        default=get_project_dir(),
        required=False,
    )
    args, _ = parser.parse_known_args(arguments)

    paths = ProjectPaths(args.project_dir)
    if not paths.cluster_config_toml.is_file():
        raise FileNotFoundError(
            f"Could not find config TOML at '{paths.cluster_config_toml}'. "
            "Have you run `cluster-init` on this project?"
        )

    config = ClusterConfig.from_toml(paths.cluster_config_toml)
    requirements_file = config.login_environment.requirements_file
    VenvCreator(
        paths=paths.venv_paths,
        requirements=tuple(
            PythonPackage.from_requirements_txt(requirements_file)
        ) if (requirements_file and requirements_file.is_file())
        else tuple(),
    ).create_and_initialize_venv()
    logger.info("Virtual environment updated!")


def perform_run(arguments: Iterable[str] | None = None):
    """Command for submitting a run from a login node.

    Parameters
    ----------
    arguments
        (Optional) When provided, uses given args instead of command line args.
    """
    # TODO: Write tests

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "-h", "--help",
        help="show this help message and exit",
        action="store_true",
    )
    args, _ = parser.parse_known_args(arguments)

    paths = ProjectPaths(get_project_dir())
    if args.help:
        from cluster_utils._cluster_runner import get_argument_sources_for_stage
        help_parser = argparse.ArgumentParser(
            prog="Cluster Run Launcher",
            description="Handles launching a run on a cluster.",
            add_help=True,
        )
        arg_sources = get_argument_sources_for_stage(
            arguments=["--project-dir", str(paths.project_dir)]
        )
        for arg_source in arg_sources:
            arg_source.add_arguments(help_parser)

        help_parser.parse_args(arguments)
        return

    if not is_project_paths_initialized(paths):
        raise RuntimeError(
            "Trying to perform run on project that has not been initialized. "
            "Run `cluster-init` first to initialize project file structure."
        )

    config = ClusterConfig.from_toml(paths.cluster_config_toml)
    if ON_CLUSTER:
        logger.info("Initializing modules...")
        LmodModuleLoader().purge_and_load_modules(
            config.login_environment.modules
        )

    logger.info("Passing execution to virtual environment in background...")
    sys.stdout.flush()
    log_fd = os.open(paths.log_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
    subprocess.Popen(
        [
            "nohup", "python", "-u", "-m", "cluster_utils._cluster_runner",
            "--log-level", str(logger.getEffectiveLevel()),
            "--project-dir", str(project_paths.project_dir),
        ] + sys.argv[1:],
        env=os.environ.copy(),
        stdout=log_fd,
        stderr=subprocess.STDOUT,
        close_fds=True,
    )
    os.close(log_fd)
    exit(0)


def perform_compute(arguments: Iterable[str] | None = None):
    """Command for performing compute logic on a compute node."""

    from cluster_utils._cluster_runner import main, _RunnerStage
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "-h", "--help",
        help="show this help message and exit",
        action="store_true",
    )
    args, _ = parser.parse_known_args(arguments)

    if args.help:
        from cluster_utils._cluster_runner import get_argument_sources_for_stage
        help_parser = argparse.ArgumentParser(
            prog="Cluster Compute Launcher",
            description="Handles performing a job on a compute node.",
            add_help=True,
        )
        # Simplifies case when user calls help from login node
        if "--project-dir" not in sys.argv[1:]:
            sys.argv += ["--project-dir", str(get_project_dir())]
        arg_sources = get_argument_sources_for_stage(
            stage=_RunnerStage.COMPUTE,
            arguments=sys.argv[1:]
        )
        for arg_source in arg_sources:
            arg_source.add_arguments(help_parser)

        help_parser.parse_args(arguments)
        return

    # TODO: Maybe remove main function since we can call any function we want?
    main(
        arguments=[
            "--runner-stage", _RunnerStage.COMPUTE.name,
            "--log-level", str(logger.getEffectiveLevel()),
        ] + sys.argv[1:],
    )


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
