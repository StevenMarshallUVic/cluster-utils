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

from cluster_utils import init_logger
from cluster_utils._utils import LMOD_ENV_VAR

logger = init_logger(__name__)

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

    def purge_and_load_modules(
            self,
            modules: Iterable[str],
            force_purge: bool = True,
    ) -> None:
        """Purge existing modules, and then load modules.

        Parameters
        ----------
        modules
            Modules to load.
        force_purge
            Whether to force all modules to be purged.
        """

        self.purge_modules(force_purge)
        self.load_modules(modules)

    def purge_modules(self, force: bool = True) -> None:
        """Purge existing modules.

        Parameters
        ----------
        force
            Whether to force all modules to be purged.
        """

        logger.debug("Purging modules...")
        args = ["purge"]
        if force:
            logger.info("Forcing all modules to be purged...")
            args.insert(0, "--force")

        module(*args)
        logger.debug("Modules purged.")

    def load_modules(self, modules: Iterable[str]) -> None:
        """Load multiple modules.

        Parameters
        ----------
        modules
            Modules to load.
        """

        logger.debug("Loading modules...")
        for module in modules:
            self.load_module(module)

    def load_module(self, module_name: str) -> None:
        """Load a module.

        Parameters
        ----------
        module_name
            Module to load.
        """

        logger.debug("Loading module '%s'...", module_name)
        module("load", module_name)

    def list_modules(self) -> None:
        """List all currently loaded modules."""

        module("list")
