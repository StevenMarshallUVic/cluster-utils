import logging
import os
from pathlib import Path

SRC_ROOT_DIR = Path(__file__).parent
# PACKAGE_NAME = SRC_ROOT_DIR.name
PACKAGE_NAME = "cam-cluster-utils"
# TODO: Replace with non-branch once merged
PACKAGE_URL = "git+https://github.com/StevenMarshallUVic/cluster-utils.git@automated"

logger = logging.getLogger(PACKAGE_NAME)
root_logger = logging.getLogger()

DEV_LOG_LEVEL = logging.DEBUG
PROD_LOG_LEVEL = logging.INFO

# TODO: Sort out entire project file structure to unify utils, streamline paths, etc


def get_project_dir() -> Path:
    """Get root directory of project that this package is installed in."""

    venv_dir = os.environ.get("VIRTUAL_ENV")
    if not venv_dir:
        raise RuntimeError(f"Could not find 'VIRTUAL_ENV' in environment.")

    return Path(venv_dir).parent


def is_dev_environment() -> bool:
    return not "site-packages" in Path(__file__).absolute().parts


def get_environment_default_log_level() -> int:
    return DEV_LOG_LEVEL if is_dev_environment() else PROD_LOG_LEVEL


# Set default logging levels based on whether package is installed
if is_dev_environment():
    # This is local development environment, set logging level
    logging.basicConfig()
    logger.setLevel(DEV_LOG_LEVEL)
else:
    if not root_logger.handlers:
        if logger.level == logging.NOTSET:
            logger.setLevel(PROD_LOG_LEVEL)

        logging.basicConfig(level=logger.level, force=True)
    else:
        if logger.level == logging.NOTSET:
            logger.setLevel(root_logger.level)
