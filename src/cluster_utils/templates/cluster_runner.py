"""Template for implementing custom logic for a run being performed on a
Digital Research Alliance of Canada cluster.
"""

import argparse
import logging
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Self

from cluster_utils import get_environment_default_log_level
from cluster_utils.runners import ClusterRunners, ComputeRunner, LoginRunner
from cluster_utils.utils import ArgParseable

logger = logging.getLogger(Path(__file__).stem)


@dataclass(frozen=True)
class CustomLoginRunner(LoginRunner):

    # TODO: Decide if this is necessary
    # [Required] Types to parse arguments for
    @staticmethod
    def additional_cmd_line_arguments() -> list[type[ArgParseable]]:
        return []

    # (Optional) Initialize run
    def initialize(self) -> bool:
        raise NotImplementedError()

    # [Required] Submit compute job
    def submit_compute_jobs(self) -> bool:
        raise NotImplementedError()

    # (Optional) Post-processing after compute jobs are complete
    def post_process(self) -> bool:
        raise NotImplementedError()

    # [Required] Create instance from command line arguments
    @classmethod
    def from_custom_args(cls, args: argparse.Namespace):
        raise NotImplementedError()


@dataclass(frozen=True)
class CustomComputeRunner(ComputeRunner):
    # (Optional) Additional compute file structure initialization
    def initialize_compute_file_structure(self) -> bool:
        raise NotImplementedError()

    # [Required] Compute node logic
    def perform_computations(self) -> bool:
        raise NotImplementedError()

    # (Optional) Additional compute runner initialization
    @classmethod
    def from_args(cls) -> Self:
        return cls(**asdict(super().from_args()))


@dataclass(frozen=True)
class CustomClusterRunners(ClusterRunners):
    @property
    def login_runner(self) -> LoginRunner:
        return CustomLoginRunner.from_args()

    @property
    def compute_runner(self) -> ComputeRunner:
        return CustomComputeRunner.from_args()


def main():
    parser = argparse.ArgumentParser(description="Logger Management")
    parser.add_argument(
        "--log-level",
        type=int,
        default=get_environment_default_log_level(),
        help="Numeric logging level passed from parent process."
    )
    args = parser.parse_args()
    logger.setLevel(args.log_level)

    CustomClusterRunners.from_args().run_stage()


if __name__ == "__main__":
    main()
