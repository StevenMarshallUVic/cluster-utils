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

CLUSTER_CONFIG_TOML_NAME = "cluster_config.toml"
CLUSTER_RUNNER_SCRIPT_NAME = "cluster_runner.py"


class SrcPaths:
    SCRIPTS_DIR = SRC_ROOT_DIR / "scripts"
    TEMPLATES_DIR = SRC_ROOT_DIR / "templates"

    RUNNER_SCRIPT = SRC_ROOT_DIR / "_runner.py"

    CLUSTER_CONFIG_TOML = TEMPLATES_DIR / CLUSTER_CONFIG_TOML_NAME
    CLUSTER_RUNNER_SCRIPT = TEMPLATES_DIR / CLUSTER_RUNNER_SCRIPT_NAME


@dataclass(frozen=True)
class ProjectPaths:
    project_dir: Path

    ACCOUNT_TXT_NAME = ".account.txt"
    LOG_FILE_NAME = "last_run.log"
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
    def cluster_runner_script(self):
        return self.src_dir / CLUSTER_RUNNER_SCRIPT_NAME

    @property
    def log_file(self):
        return self.project_dir / self.LOG_FILE_NAME

    @property
    def requirements_file(self):
        return self.project_dir / self.REQUIREMENTS_TXT_NAME

    @property
    def src_dir(self):
        return self.project_dir / "src"

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
