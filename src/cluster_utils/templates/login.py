"""Custom logic to execute on login node before submitting jobs to slurm."""

import argparse
import logging
import sys

from cluster_utils import get_environment_default_log_level

logger = logging.getLogger(__name__)


def main():
    # 1. Set up argparse to capture the incoming log level
    parser = argparse.ArgumentParser(description="Background Worker Process")
    parser.add_argument(
        "--log-level",
        type=int,
        default=get_environment_default_log_level(),
        help="Numeric logging level passed from parent process."
    )
    args = parser.parse_args()
    logger.setLevel(args.log_level)

    logger.info("Performing login logic using '%s'.", sys.version)
    logger.info("Test preprocessing complete :)")


if __name__ == "__main__":
    main()
