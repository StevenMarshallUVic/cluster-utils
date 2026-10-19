import logging
import os
from pathlib import Path

logger = logging.getLogger(Path(__file__).parent.name)
root_logger = logging.getLogger()

DEV_LOG_LEVEL = logging.DEBUG
PROD_LOG_LEVEL = logging.INFO

# Set default logging levels based on whether package is installed
if "site-packages" in os.path.abspath(__file__):
    print("Logger level = ", logger.level)
    print("Root logger level = ", root_logger.level)
    # Package is installed, set logging level if not set by installed project
    if not root_logger.handlers:
        print("No root logger handlers, using basicConfig")
        logging.basicConfig()

    print("Logger level = ", logger.level)
    print("Root logger level = ", root_logger.level)
    if logger.level == logging.NOTSET:
        if root_logger.level != logging.NOTSET:
            logger.setLevel(root_logger.level)
        else:
            logger.setLevel(PROD_LOG_LEVEL)

else:
    # This is local development environment, set logging level
    logging.basicConfig()
    logger.setLevel(DEV_LOG_LEVEL)
