import logging
import os
from pathlib import Path

logger = logging.getLogger(Path(__file__).parent.name)

# Enable DEBUG mode by default if not running as package
if not "site-packages" in os.path.abspath(__file__):
    logging.basicConfig()
    logger.setLevel(logging.DEBUG)
else:
    logger.addHandler(logging.NullHandler())
