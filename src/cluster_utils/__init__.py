import logging
import os
from pathlib import Path

SRC_ROOT_DIR = Path(__file__).parent
# PACKAGE_NAME = SRC_ROOT_DIR.name
PACKAGE_NAME = "cam-cluster-utils"
# TODO: Replace with non-branch once merged
PACKAGE_URL = "git+https://github.com/StevenMarshallUVic/cluster-utils.git@automated"

root_logger = logging.getLogger()

DEV_LOG_LEVEL = logging.DEBUG
PROD_LOG_LEVEL = logging.INFO

VENV_ENV_VAR = "VIRTUAL_ENV"
SLURM_TMP_DIR_ENV_VAR = "SLURM_TMPDIR"
SLURM_JOB_NAME_ENV_VAR = "SLURM_JOB_NAME"
# TODO: Sort out entire project file structure to unify utils, streamline paths, etc


def get_project_dir() -> Path:
    """Get root directory of project that this package is installed in."""

    venv_dir = os.environ.get(VENV_ENV_VAR)
    if not venv_dir:
        raise RuntimeError(
            f"Could not find '{VENV_ENV_VAR}' in environment."
        )

    return Path(venv_dir).parent


def is_dev_environment() -> bool:
    return not "site-packages" in Path(__file__).absolute().parts


def get_environment_default_log_level() -> int:
    return DEV_LOG_LEVEL if is_dev_environment() else PROD_LOG_LEVEL


def init_logger(
        name: str,
        log_level: int = get_environment_default_log_level(),
) -> logging.Logger:
    """Create logger based on environment and root logger configuration.

    Parameters
    ----------
    name
        Name of logger.
    log_level
        (Optional) Logging level. Based on `logging` log levels.

    Returns
    -------
    logging.Logger
        Initialized logger.
    """

    if is_dev_environment():
        logging.basicConfig(level=log_level, force=True)
        logger = logging.getLogger(name)
        logger.setLevel(log_level)
        return logger

    if not root_logger.handlers:
        logging.basicConfig(level=log_level, force=True)
        logger = logging.getLogger(name)
        logger.setLevel(log_level)
        return logger

    logger = logging.getLogger(name)
    if logger.level == logging.NOTSET:
        logger.setLevel(root_logger.level)

    return logger
