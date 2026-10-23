"""Handle interacting with Lmod module management program on cluster.

NOTE: Only import this script if you've confirmed that the script is being
        run on a cluster. Otherwise, script initialization will raise errors
        if Lmod is not installed on the system.
NOTE: Must be backward compatible with python 3.9.25 for use on clusters.
"""

from __future__ import annotations
import os
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from cluster_utils._utils import LMOD_ENV_VAR


LMOD_INIT_DIR = Path(os.environ[LMOD_ENV_VAR]).parent.parent / "init"
if not LMOD_INIT_DIR.is_dir():
    raise NotADirectoryError(
        f"Lmod init directory not found at '{LMOD_INIT_DIR}'."
    )

sys.path.append(str(LMOD_INIT_DIR))
from env_modules_python import module


@dataclass(frozen=True)
class LmodModuleLoader:
    """Handles loading modules using Lmod."""

    def purge_and_load_modules(self, modules: Iterable[str]) -> None:
        """Purge existing modules, and then load modules.

        Parameters
        ----------
        modules
            Modules to load.
        """

        self.purge_modules()
        self.load_modules(modules)

    def load_modules(self, modules: Iterable[str]) -> None:
        """Load multiple modules.

        Parameters
        ----------
        modules
            Modules to load.
        """

        for module in modules:
            self.load_module(module)

    def purge_modules(self) -> None:
        """Purge existing modules."""

        # TODO: Add support for forcing all modules to be purged ("-f" flag)
        module("purge")

    def load_module(self, module_name: str) -> None:
        """Load a module.

        Parameters
        ----------
        module_name
            Module to load.
        """
        module("load", module_name)
