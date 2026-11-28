"""Centralized path and resource management for the package.

NOTE: Must be backward compatible with python 3.9.25 for use on clusters.

Backward Compatibility Notes:
- It is better practice to use importlib to handle resolving paths between
  files in packages since it has support for complexities such as the package
  being zipped.
  - Due to clusters using python 3.9.25 as default, this module is not
    available in the standard library on clusters, so pathlib used instead.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from cluster_utils import SRC_ROOT_DIR

TEMPLATE_PREFIX = "template_"
PYPROJECT_TOML_NAME = "pyproject.toml"
CLUSTER_WORKFLOW_SCRIPT_NAME = "cluster_workflow.py"


class SrcPaths:
    TEMPLATES_DIR = SRC_ROOT_DIR / "templates"

    PYPROJECT_TOML = TEMPLATES_DIR / (TEMPLATE_PREFIX + PYPROJECT_TOML_NAME)
    CLUSTER_WORKFLOW_SCRIPT = TEMPLATES_DIR / (TEMPLATE_PREFIX + CLUSTER_WORKFLOW_SCRIPT_NAME)


@dataclass(frozen=True)
class VenvPaths:
    """Paths for a Python virtual environment.

    Attributes
    ----------
    venv_dir
        Root directory of virtual environment.
    """

    venv_dir: Path

    @property
    def venv_bin_dir(self) -> Path:
        """Path to directory containing virtual environment executables.

        Correctly handles path differences between Windows and Unix systems.
        """

        return self.venv_dir / ("bin" if os.name != "nt" else "Scripts")

    @property
    def venv_activate_script(self) -> Path:
        """Path to directory containing virtual environment executables.

        Correctly handles path differences between Windows and Unix systems.

        Warnings
        --------
        On Windows, currently only supports using
        Command Prompt (`activate.bat`).
        If using PowerShell, you should construct
        the path to `activate.ps1` yourself.
        """

        return (self.venv_bin_dir /
                ("activate" if os.name != "nt" else "activate.bat"))

    @property
    def venv_python(self) -> Path:
        """Path to virtual environment executable.

        Correctly handles path differences between Windows and Unix systems.
        """

        return self.venv_bin_dir / (
            "python" if os.name != "nt" else "python.exe"
        )


@dataclass(frozen=True)
class ProjectPaths:
    project_dir: Path

    LOG_FILE_NAME = "last_run.log"
    VENV_DIR_NAME = ".venv"

    @property
    def venv_paths(self) -> VenvPaths:
        return VenvPaths(self.project_dir / self.VENV_DIR_NAME)

    @property
    def template_paths(self) -> list[Path]:
        """Paths where each template is found within initialized project."""
        return list(self.src_path_to_template_path.values())

    @property
    def src_path_to_template_path(self) -> dict[Path, Path]:
        """Mapping between template source files and their corresponding
        locations within an initialized project."""
        return {
            SrcPaths.PYPROJECT_TOML: self.pyproject_toml,
            SrcPaths.CLUSTER_WORKFLOW_SCRIPT: self.cluster_workflow_script
        }

    @property
    def pyproject_toml(self) -> Path:
        """TOML file containing configuration options for the project."""
        return self.project_dir / PYPROJECT_TOML_NAME

    @property
    def cluster_workflow_script(self) -> Path:
        """Python script where project workflow can be designed."""
        return self.src_dir / CLUSTER_WORKFLOW_SCRIPT_NAME

    @property
    def log_file(self) -> Path:
        """Log file where log messages can be written to during runs."""
        # TODO: Figure out way to buffer log messages so this isn't needed
        return self.project_dir / self.LOG_FILE_NAME

    @property
    def src_dir(self) -> Path:
        """Root directory of source code for project."""
        return self.project_dir / "src"

    def create_src_dir(self) -> None:
        """Create src directory."""
        self.src_dir.mkdir(exist_ok=True)

    def copy_templates_to_project(self) -> None:
        """Copy all templates to their corresponding locations
        within a project.

        Notes
        -----
        Overwrites any previous templates that were already present in project.
        """

        if not self.src_dir.is_dir():
            self.create_src_dir()

        for src_path, template_path in self.src_path_to_template_path.items():
            template_path.write_text(
                src_path.read_text()
            )


@dataclass(frozen=True)
class ComputePaths:
    compute_dir: Path

    VENV_NAME = ".venv"

    @property
    def venv_dir(self) -> Path:
        return self.compute_dir / self.VENV_NAME
