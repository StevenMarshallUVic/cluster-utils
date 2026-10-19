import logging
import os
from pathlib import Path

logger = logging.getLogger(Path(__file__).parent.name)
root_logger = logging.getLogger()

DEV_LOG_LEVEL = logging.DEBUG
PROD_LOG_LEVEL = logging.INFO

# Set default logging levels based on whether package is installed
if "site-packages" in os.path.abspath(__file__):
    if not root_logger.handlers:
        if logger.level == logging.NOTSET:
            logger.setLevel(logging.INFO)

        logging.basicConfig(level=logger.level, force=True)
    else:
        if logger.level == logging.NOTSET:
            logger.setLevel(root_logger.level)

else:
    # This is local development environment, set logging level
    logging.basicConfig()
    logger.setLevel(DEV_LOG_LEVEL)
