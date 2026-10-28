"""Create and manage Python virtual environments.

NOTE: Must be backward compatible with python 3.9.25 for use on clusters.
"""

from __future__ import annotations
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Iterable

from cluster_utils import PACKAGE_NAME, PACKAGE_URL
from cluster_utils._paths import ProjectPaths
from cluster_utils._utils import ON_CLUSTER
from cluster_utils.utils import PythonPackage

CLUSTER_UTILS_PACKAGE = PythonPackage(
    name=PACKAGE_NAME,
    link=PACKAGE_URL,
)


@dataclass(frozen=True)
class VenvCreator:
    """Handles creating Python virtual environments.

    Attributes
    ----------
    paths
        Paths for the project.
    requirements
        Python packages to install into virtual environment.
    """

    paths: ProjectPaths
    requirements: tuple[PythonPackage, ...] = tuple()

    _DEFAULT_REQUIREMENTS: tuple[PythonPackage] = tuple([
        CLUSTER_UTILS_PACKAGE,
    ])

    @property
    def active_python(self) -> str:
        """Which python executable to use."""
        return "python" if ON_CLUSTER else sys.executable

    @property
    def _pip_arguments(self) -> list[str]:
        """Subprocess arguments for running a pip command within environment.

        Raises
        ------
        FileNotFoundError
            If virtual environment executable is not found.
        """

        if not self.paths.venv_python.is_file():
            raise FileNotFoundError(
                f"Could not find venv executable at {self.paths.venv_python}"
            )

        install_cmd = [str(self.paths.venv_python), "-m", "pip"]
        if ON_CLUSTER:
            install_cmd.append("--no-index")

        return install_cmd

    @property
    def _all_requirements(self) -> list[PythonPackage]:
        """All python package requirements.

        Includes both requirements specified by user and defaults required
        for core package functionality.
        """

        return (
            list(self._DEFAULT_REQUIREMENTS)
            + list(self.requirements)
        )

    @property
    def _all_requirements_args(self) -> list[str]:
        """All required packages in a form that can be passed as arguments
        to subprocess."""

        return [r.requirement_str for r in self._all_requirements]

    @property
    def current_pip_version(self) -> str:
        """Current version of this environment's pip package."""

        process = subprocess.run(
            self._pip_arguments + ["--version"],
            capture_output=True,
            text=True,
            check=True
        )
        return process.stdout.strip()

    @property
    def installed_packages(self) -> list[PythonPackage]:
        """All currently installed packages."""

        process = subprocess.run(
            self._pip_arguments + ["list"],
            capture_output=True,
            text=True,
            check=True
        )
        return PythonPackage.from_pip_list_cmd_output(process.stdout.strip())

    def create_and_initialize_venv(self) -> None:
        """Perform full virtual environment setup.

        Raises
        ------
        RuntimeError
            If one or more requirements fail to install.
        """

        self.initialize_base_venv()
        self.upgrade_pip()
        self.install_requirements()
        missing_reqs = self.find_missing_requirements(
            self._all_requirements,
            self.installed_packages,
        )
        if missing_reqs:
            nl = "\n"
            raise RuntimeError(
                f"One or more requirements failed to install: "
                f"{nl}{nl.join([r.requirement_str for r in missing_reqs])}"
            )
        self.source_venv()

    def initialize_base_venv(self) -> None:
        """Generate base virtual environment."""

        if self.paths.venv_dir.is_dir():
            return

        subprocess.run(
            [self.active_python, "-m", "venv", self.paths.venv_dir],
            check=True
        )

    def upgrade_pip(self) -> None:
        """Upgrade pip to latest version."""

        subprocess.run(
            self._pip_arguments + ["install", "--upgrade", "pip"],
            check=True
        )

    def install_requirements(self) -> None:
        """Install python package requirements."""

        subprocess.run(
            self._pip_arguments + ["install"] + self._all_requirements_args,
            check=True
        )

    def source_venv(self) -> None:
        """Push virtual environment to head of PATH to mimic sourcing.

        Raises
        ------
        NotADirectoryError
            If virtual environment directories do not exist.
        """

        if not self.paths.venv_bin_dir.is_dir():
            raise NotADirectoryError(
                f"Could not find venv bin dir at '{self.paths.venv_bin_dir}'."
            )
        if not self.paths.venv_dir.is_dir():
            raise NotADirectoryError(
                f"Could not find venv dir at '{self.paths.venv_dir}'."
            )

        os.environ["PATH"] = str(
            self.paths.venv_bin_dir
        ) + os.pathsep + os.environ["PATH"]
        os.environ["VIRTUAL_ENV"] = str(self.paths.venv_dir)

    @staticmethod
    def find_missing_requirements(
            requirements: Iterable[PythonPackage],
            installed: Iterable[PythonPackage],
    ) -> list[PythonPackage]:
        """Validate that all requirements are installed in environment."""

        installed_name_to_package = {p.name: p for p in installed}
        missing_requirements = []
        for requirement in requirements:
            if (requirement.name not in installed_name_to_package
                    and requirement.name.replace("_", "-") not in installed_name_to_package):
                missing_requirements.append(requirement)

        return missing_requirements
