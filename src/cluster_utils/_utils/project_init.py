"""Handles initializing a project's file structure for use with this package.

NOTE: Must be backward compatible with python 3.9.25 for use on clusters.
"""

from __future__ import annotations
import argparse
import logging
from dataclasses import dataclass, replace
from pathlib import Path

from cluster_utils import get_project_dir
from cluster_utils.utils import ArgParseable
from cluster_utils._paths import ProjectPaths
from cluster_utils._utils import io

ACCOUNT_FLAG = "--account"

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProjectInitParams(ArgParseable):
    project_dir: Path
    account: str | None = None
    force: bool = False
    no_input: bool = False

    @property
    def project_paths(self):
        return ProjectPaths(self.project_dir)

    def relative_to_project(self, path: Path):
        return self.project_dir.name / path.relative_to(self.project_dir)

    @classmethod
    def add_arguments(
            cls,
            parser: argparse.ArgumentParser,
            group: argparse._ArgumentGroup | None = None
    ) -> None:
        parser.add_argument(
            "-a", ACCOUNT_FLAG,
            help="(Optional) Account to charge slurm usage to. "
                 "If not provided, you will be required to specify an account "
                 "each time you submit a run.",
            type=str,
            required=False,
        )
        parser.add_argument(
            "--project_dir",
            help="(Optional) Root directory of project to initialize. "
                 "When not provided, infers project directory from environment.",
            type=Path,
            default=get_project_dir(),
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


def _update_init_from_user_input(init: ProjectInitParams) -> ProjectInitParams:
    """Update initialization parameters with manual user input.

    Parameters
    ----------
    init
        Parameters to update.

    Returns
    -------
    ProjectInitParams
        Parameters with their values updated from user input.
    """

    if init.no_input:
        return init

    account = init.account
    if account is None:
        logger.warning(
            f"`{ACCOUNT_FLAG}` flag not provided. "
            "Please specify Digital Research Alliance of Canada account "
            "to charge usage to (e.g. 'def-name')?"
        )
        user_account = input(
            "INPUT: Account (leave blank to skip): "
        )
        if user_account:
            account = user_account

    return replace(init, account=account)


def _check_for_existing_template_files(
        init: ProjectInitParams,
        log_separator: str = "\n\t- ",
        add_separator_to_start: bool = True,
) -> None:
    """Check whether any template files already exist.

    Parameters
    ----------
    init
        Parameters to check template files for.

    Raises
    ------
    FileExistsError
        If one or more template files already exists,
        and `init.force` is False.
    """

    files_to_check = init.project_paths.template_paths
    if init.account:
        files_to_check.append(init.project_paths.account_txt)

    existing_files = io.get_existing_files(files_to_check)
    if existing_files:
        existing_log_str = log_separator.join([
            str(init.relative_to_project(f)) for f in existing_files
        ])
        if add_separator_to_start:
            existing_log_str = log_separator + existing_log_str
        if init.force:
            logger.warning(
                "One or more initialization files already exists "
                "in this directory, overwriting: %s.",
                existing_log_str,
            )
        else:
            raise FileExistsError(
                "One or more initialization files already exists in "
                f"this directory, skipping initialization: "
                f"{existing_log_str}."
                "\nIf you want to overwrite these files, "
                "use the `-f`/`--force` flag."
            )


def _write_project_files(init: ProjectInitParams) -> None:
    init.project_paths.copy_templates_to_project()
    logger.info(
        "Config created at '%s'.",
        init.relative_to_project(init.project_paths.cluster_config_toml),
    )
    logger.info(
        "Cluster runner script created at '%s'. "
        "Modify template to implement custom logic.",
        init.relative_to_project(init.project_paths.cluster_runner_script),
    )
    if init.account:
        init.project_paths.write_account(init.account)
        logger.info(
            "Account file created at '%s'.",
            init.relative_to_project(init.project_paths.account_txt),
        )


def initialize_project(init: ProjectInitParams) -> None:
    """Initializing a project's file structure for use with
    the cluster-utils framework.
    """

    _check_for_existing_template_files(init)

    logger.info("Initializing project...")
    init = _update_init_from_user_input(init)
    _write_project_files(init)
    logger.info("Project successfully initialized!")
