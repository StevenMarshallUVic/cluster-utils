"""Centralized path and resource management for the package."""
import os
from dataclasses import dataclass
from pathlib import Path
from importlib.resources import files, as_file
from importlib.resources.abc import Traversable

CLUSTER_CONFIG_TOML_NAME = "cluster_config.toml"


class SrcPaths:
    SRC_ROOT_DIR = files("cluster_utils")
    SCRIPTS_DIR = SRC_ROOT_DIR / "scripts"
    TEMPLATES_DIR = SRC_ROOT_DIR / "templates"

    @staticmethod
    def get_file_path(root_dir: Traversable, name: str) -> Path:
        """Safely retrieve filesystem path for an internal resource file."""

        with as_file(root_dir.joinpath(name)) as path:
            return path

    CLUSTER_CONFIG_TOML = get_file_path(TEMPLATES_DIR, CLUSTER_CONFIG_TOML_NAME)
    PREPROCESS_SCRIPT = get_file_path(SRC_ROOT_DIR, "_preprocess.py")


@dataclass(frozen=True)
class ProjectPaths:
    project_dir: Path

    ACCOUNT_TXT_NAME = ".account.txt"
    REQUIREMENTS_TXT_NAME = "requirements.txt"
    VENV_DIR_NAME = ".test_venv" # TODO: TEMP DEBUG
    # VENV_DIR_NAME = ".venv"

    @property
    def account_txt(self):
        return self.project_dir / self.ACCOUNT_TXT_NAME

    @property
    def cluster_config_toml(self):
        return self.project_dir / CLUSTER_CONFIG_TOML_NAME

    @property
    def requirements_file(self):
        return self.project_dir / self.REQUIREMENTS_TXT_NAME

    @property
    def venv_dir(self):
        return self.project_dir / self.VENV_DIR_NAME

    @property
    def venv_bin_dir(self):
        """Path to directory containing virtual environment executables.

        Correctly handles path differences between Windows and Unix systems.
        """

        return self.venv_dir / ("bin" if os.name != "nt" else "Scripts")

    @property
    def venv_python(self):
        """Path to virtual environment executable.

        Correctly handles path differences between Windows and Unix systems.
        """

        return self.venv_bin_dir / (
            "python" if os.name != "nt" else "python.exe"
        )
