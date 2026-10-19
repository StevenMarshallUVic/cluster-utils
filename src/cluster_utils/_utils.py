import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from cluster_utils._paths import ProjectPaths

LMOD_ENV_VAR = "LMOD_CMD"
ON_CLUSTER = LMOD_ENV_VAR in os.environ


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

        if self.paths.venv_dir.is_dir():
            print(
                f"Found existing virtual environment at {self.paths.venv_dir}. "
                f"Skipping creation."
            )
            return

        self.initialize_base_venv()
        self.upgrade_pip()
        self.install_requirements()
        self.source_venv()

    def initialize_base_venv(self) -> None:
        """Generate base virtual environment at the given directory."""

        if self.paths.venv_dir.is_dir():
            print(
                f"Virtual environment already exists at {self.paths.venv_dir}, "
                f"skipping base venv initialization."
            )
            return

        print(f"Creating virtual environment at: {self.paths.venv_dir}")
        subprocess.run(
            [self._active_python, "-m", "venv", self.paths.venv_dir],
            check=True
        )

    def upgrade_pip(self) -> None:
        """Upgrade pip to latest version."""

        print("Upgrading pip...")
        subprocess.run(
            self._pip_install_cmd + ["--upgrade", "pip"],
            check=True
        )

    def install_requirements(self) -> None:
        """Install python package requirements."""

        if not self.paths.requirements_file.is_file():
            print(
                f"[Warning] {self.paths.requirements_file} not found. "
                f"Skipping dependency installation."
            )
            return

        print(f"Installing requirements from {self.paths.requirements_file}...")
        subprocess.run(
            self._pip_install_cmd + ["-r", self.paths.requirements_file],
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


@dataclass(frozen=True)
class LmodModuleLoader:
    @property
    def lmod_init(self) -> Path:
        return Path(
            os.environ[LMOD_ENV_VAR]
        ).parent.parent / "init" / "env_modules_python.py"

    def __post_init__(self):
        if not self.lmod_init.is_file():
            raise RuntimeError(
                f"Lmod Python initialization script not found at "
                f"'{self.lmod_init}'."
            )

        exec(open(self.lmod_init).read())

    def load_modules(self, modules: list[str], purge: bool = True) -> None:
        if purge:
            self.purge_modules()

        print(f"Loading modules...")
        for module in modules:
            load_module(module)

    def purge_modules(self) -> None:
        module("purge")

    def load_module(self, module_name: str) -> None:
        module("load", module_name)
