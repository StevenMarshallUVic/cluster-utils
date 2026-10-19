import logging
import os
from pathlib import Path

PACKAGE_NAME = Path(__file__).parent.name

logger = logging.getLogger(PACKAGE_NAME)
root_logger = logging.getLogger()

DEV_LOG_LEVEL = logging.DEBUG
PROD_LOG_LEVEL = logging.INFO

def is_dev_environment() -> bool:
    return not "site-packages" in os.path.abspath(__file__)


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
