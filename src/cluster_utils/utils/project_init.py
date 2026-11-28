"""Handles initializing a project's file structure for use with this package.

NOTE: Must be backward compatible with python 3.9.25 for use on clusters.
"""

from __future__ import annotations
import argparse
import logging
from dataclasses import dataclass, replace
from pathlib import Path

from cluster_utils import get_project_dir
from cluster_utils.data import add_argument_to_parser
from cluster_utils.utils import ArgParseable
from cluster_utils._paths import ProjectPaths
from cluster_utils.utils import io

ACCOUNT_FLAG = "--account"

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProjectInitParams(ArgParseable):
    project_dir: Path
    force: bool = False

    @property
    def project_paths(self) -> ProjectPaths:
        return ProjectPaths(self.project_dir)

    def relative_to_project(self, path: Path) -> Path:
        return self.project_dir.name / path.relative_to(self.project_dir)

    @classmethod
    def add_arguments(
            cls,
            parser: argparse.ArgumentParser,
            group: argparse._ArgumentGroup | None = None,
            prefix: str | None = None,
    ) -> None:
        add_argument_to_parser(
            parser,
            group,
            prefix,
            "--project-dir",
            help="(Optional) Root directory of project to initialize. "
                 "When not provided, infers project directory from relative "
                 "file structure of python virtual environment.",
            type=Path,
            default=get_project_dir(),
            required=False,
        )
        add_argument_to_parser(
            parser,
            group,
            prefix,
            "-f", "--force",
            help="(Optional) Whether to overwrite any existing files that conflict with "
                 "files generated during initialization.",
            action=argparse.BooleanOptionalAction,
            default=False,
        )


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

    existing_files = io.get_existing_files(init.project_paths.template_paths)
    if len(existing_files) == 0:
        return

    existing_log_str = log_separator.join([
        str(init.relative_to_project(f)) for f in existing_files
    ])
    if add_separator_to_start:
        existing_log_str = log_separator + existing_log_str
    if init.force:
        logger.warning(
            "One or more initialization files already exists "
            "in project, overwriting: %s.",
            existing_log_str,
        )
    else:
        raise FileExistsError(
            "One or more initialization files already exists in "
            f"project, skipping initialization: "
            f"{existing_log_str}."
            "\nIf you want to overwrite these files, "
            "use the `-f`/`--force` flag."
        )


def _write_project_files(init: ProjectInitParams) -> None:
    init.project_paths.copy_templates_to_project()
    logger.info(
        "Config created at '%s'.",
        init.relative_to_project(init.project_paths.pyproject_toml),
    )
    logger.info(
        "Workflow script created at '%s'. "
        "Modify template to implement custom logic.",
        init.relative_to_project(
            init.project_paths.cluster_workflow_script
        ),
    )


def initialize_project(init: ProjectInitParams) -> None:
    """Initializing a project's file structure for use with
    the cluster-utils framework.
    """

    logger.debug("Checking for existing template files...")
    _check_for_existing_template_files(init)
    logger.debug("Existing template files checked!")

    logger.info("Writing project files...")
    _write_project_files(init)
    logger.info("Project files written!")
