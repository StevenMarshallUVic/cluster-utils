import logging
import os
from collections.abc import Iterable
from pathlib import Path

from cluster_utils._utils import LMOD_ENV_VAR, ON_CLUSTER

logger = logging.getLogger(__name__)


# if not ON_CLUSTER:
#     return

LMOD_INIT_DIR = Path(os.environ[LMOD_ENV_VAR]).parent.parent / "init"
if not LMOD_INIT_DIR.is_dir():
    raise NotADirectoryError(
        f"Lmod init directory not found at '{LMOD_INIT_DIR}'."
    )

sys.path.append(str(LMOD_INIT_DIR))
from env_modules_python import module


@dataclass(frozen=True)
class LmodModuleLoader:
    def load_modules(self, modules: Iterable[str], purge: bool = True) -> None:
        if purge:
            self.purge_modules()

        logger.info("Loading modules...")
        for module in modules:
            load_module(module)

    def purge_modules(self) -> None:
        module("purge")

    def load_module(self, module_name: str) -> None:
        module("load", module_name)
