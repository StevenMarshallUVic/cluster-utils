import logging
import os
import subprocess
import sys
from dataclasses import dataclass

from cluster_utils import PACKAGE_URL
from cluster_utils._paths import ProjectPaths
from cluster_utils._utils import ON_CLUSTER

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VenvCreator:
    paths: ProjectPaths

    @property
    def _active_python(self) -> str:
        """Which python executable to use."""
        return "python" if ON_CLUSTER else sys.executable

    @property
    def _pip_install_cmd(self) -> list[str]:
        """Command for performing an installation with pip."""

        if not self.paths.venv_python.is_file():
            raise FileNotFoundError(
                f"Could not find venv executable at {self.paths.venv_python}"
            )

        install_cmd = [str(self.paths.venv_python), "-m", "pip", "install"]
        if ON_CLUSTER:
            install_cmd.append("--no-index")

        return install_cmd

    def create_and_initialize_venv(self):
        """Perform full virtual environment setup."""

        self.initialize_base_venv()
        self.upgrade_pip()
        self.install_requirements()
        self.source_venv()

    def initialize_base_venv(self) -> None:
        """Generate base virtual environment at the given directory."""

        if self.paths.venv_dir.is_dir():
            logger.info(
                "Virtual environment already exists at '%s', "
                "skipping base venv initialization.",
                self.paths.venv_dir,
            )
            return

        logger.info(
            "Creating virtual environment at '%s'.",
            self.paths.venv_dir,
        )
        subprocess.run(
            [self._active_python, "-m", "venv", self.paths.venv_dir],
            check=True
        )

    def upgrade_pip(self) -> None:
        """Upgrade pip to latest version."""

        logger.info("Upgrading pip...")
        subprocess.run(
            self._pip_install_cmd + ["--upgrade", "pip"],
            check=True
        )

    def install_requirements(self) -> None:
        """Install python package requirements."""

        requirements = [
            PACKAGE_URL,
        ]
        if self.paths.requirements_file.is_file():
            extra_reqs = self.paths.requirements_file.read_text().splitlines()
            logger.info(
                "Found %s requirements in requirements  file!",
                len(extra_reqs)
            )
            requirements.extend(extra_reqs)
        else:
            logger.warning(
                "Requirements file not found at '%s'. "
                "Installing only base requirements.",
                self.paths.requirements_file,
            )

        logger.info(
            "Installing %s requirements...",
            len(requirements),
        )
        subprocess.run(
            self._pip_install_cmd + requirements,
            check=True
        )

    def source_venv(self) -> None:
        """Manually push venv to the head of PATH to mimic sourcing the venv."""

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
