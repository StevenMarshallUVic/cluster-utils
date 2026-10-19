import logging
import os
from pathlib import Path

logger = logging.getLogger(Path(__file__).parent.name)

# Set default logging levels based on whether package is installed
if "site-packages" in os.path.abspath(__file__):
    # Package is installed, set logging level if not set
    if logger.level == logging.NOTSET:
        logger.setLevel(logging.INFO)

    logger.addHandler(logging.NullHandler())
else:
    # This is local development environment, set logging level
    logging.basicConfig()
    logger.setLevel(logging.DEBUG)
