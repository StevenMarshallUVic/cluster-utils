"""Template for implementing custom logic for a run being performed on a
Digital Research Alliance of Canada cluster.
"""

import argparse
import logging
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Self

from cluster_utils import get_environment_default_log_level
from cluster_utils.data import ArrayJobData, Input, Paths, SlurmParams
from cluster_utils.runners import ClusterRunners, ComputeRunner, LoginRunner
from cluster_utils.utils import ArgParseable

# TODO: Create global logger creation function
logger = logging.getLogger(Path(__file__).stem)


@dataclass(frozen=True)
class CustomInput(Input):
    """Custom inputs."""

    @classmethod
    def add_arguments(
            cls,
            parser: argparse.ArgumentParser,
            group: argparse._ArgumentGroup | None = None,
    ) -> None:
        if group is None:
            group = parser.add_argument_group(
                "Custom Input Parameters",
                ""
            )

        # (Optional) Add custom arguments here...

        Input.add_arguments(parser, group)


@dataclass(frozen=True)
class CustomPaths(Paths):
    """Custom paths."""

    # [Required] Name of project
    @classmethod
    def project_name(cls) -> str:
        raise NotImplementedError()

    # TODO: Determine if this is needed?
    @property
    def runner_module_path(self) -> str:
        raise NotImplementedError()

    def perform_custom_run_initialization(self, *args, **kwargs) -> None:
        raise NotImplementedError()


@dataclass(frozen=True)
class CustomSlurmParams(SlurmParams):
    """Custom slurm parameters."""

    # [Required] Override default slurm params here...

    # (Optional) Prefix to add to all command line arguments.
    #     Helpful when defining more than one custom SlurmParams.
    @staticmethod
    def argument_prefix() -> str | None:
        return None


@dataclass(frozen=True)
class CustomLoginRunner(LoginRunner):
    # [Required] Types to parse arguments for
    @staticmethod
    def argument_sources() -> list[type[ArgParseable]]:
        return [CustomInput, CustomPaths, CustomSlurmParams]

    def initialize(self) -> bool:
        self.paths.initialize_run()

        # TODO: Replace with simpler system that includes paths by default
        self.paths.initialize_params_dirs(
            {
                self.paths: self.paths.run_paths_json,
            },
            {
                self.paths: self.paths.attempt_paths_json,
            },
        )

        # (Optional) Add custom run initialization logic here...

        return True

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
    # [Required] Types to parse arguments for
    @staticmethod
    def argument_sources() -> list[type[ArgParseable]]:
        return [ArrayJobInstanceParams]

    # (Optional) Additional compute file structure initialization
    def initialize_compute_file_structure(self) -> bool:
        raise NotImplementedError()

    # [Required] Compute node logic
    def perform_computations(self) -> bool:
        raise NotImplementedError()

    # [Required] Create instance from command line arguments
    @classmethod
    def from_custom_args(cls, args: argparse.Namespace) -> Self:
        array_job_params = ArrayJobInstanceParams.from_args(args)
        paths = Paths.from_json(array_job_params.paths_json)
        job_data = ArrayJobData.from_json(
            ArrayJobData.build_json_path(
                paths.attempt_array_job_data_dir,
                array_job_params.array_job_index,
            )
        )

        return cls(
            compute_dir=array_job_params.compute_dir,
            job_data=job_data,
        )


@dataclass(frozen=True)
class CustomClusterRunners(ClusterRunners):
    @property
    def login_runner(self) -> LoginRunner:
        return CustomLoginRunner.from_args()

    @property
    def compute_runner(self) -> ComputeRunner:
        return CustomComputeRunner.from_args()


def main():
    # TODO: Move all runtime logic to private runner script and only use this file to access classes
    # TODO: Extract log level parsing to other script
    parser = argparse.ArgumentParser(description="Logger Management")
    parser.add_argument(
        "--log-level",
        type=int,
        default=get_environment_default_log_level(),
        help="Numeric logging level passed from parent process."
    )
    args, _ = parser.parse_known_args()
    logger.setLevel(args.log_level)

    CustomClusterRunners.from_args().run_stage()


if __name__ == "__main__":
    main()
