import argparse
import logging
import shutil
import subprocess
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cluster_utils import get_environment_default_log_level
from cluster_utils._config import ClusterConfig
from cluster_utils._paths import ProjectPaths
from cluster_utils.data import ArrayJobData, Input, Paths, SlurmParams
from cluster_utils.utils import EnumAction, _RunnerStage, \
    run_subprocess_command
from cluster_utils.workflow_utils import find_subclasses_in_script, ArgParser
from cluster_utils.workflow import FullWorkflow

# TODO: Move logger creation to centralized location
logger = logging.getLogger(Path(__file__).name)


@dataclass(frozen=True)
class _LoginRunner(ArgParser, ABC):
    """Abstract class that handles running the portion of a run that occurs
    in the background on a login node."""

    paths: Paths
    inputs: Input

    @staticmethod
    def parser_name() -> str:
        return "Login Runner"

    @staticmethod
    def parser_description() -> str:
        return ("Perform logic on login node of "
                "Digital Research Alliance of Canada cluster.")

    def run(self) -> bool:
        """Perform login portion of run.

        Returns
        -------
        Whether login tasks were run successfully.
        """

        if not self.initialize():
            return False

        if not self.submit_compute_jobs():
            logger.warning(
                "One or more compute jobs failed, skipping post processing."
            )
            return False

        return self.post_process()

    def initialize(self) -> bool:
        """Virtual method for initializing a run.

        Returns
        -------
        Whether initialization was successful.
        """
        return True

    @abstractmethod
    def submit_compute_jobs(self) -> bool:
        """Virtual method for submitting compute jobs.

        Returns
        -------
        bool
            Whether compute jobs completed successfully.
        """
        raise NotImplementedError()

    def _build_array_job_command(
            self,
            account: str,
            job_name: str,
            array_job_data_dir: Path,
            log_file: Path,
            wrap_args: list[str],
            dependencies: SlurmDependencies | None = None,
            wait=True,
    ) -> list[str] | None:
        """Submit a slurm array job to handle the compute portion of the job."""
        # TODO: Add docstring (also copy to runner method)

        max_array_index = ArrayJobData.find_greatest_array_job_index(
            array_job_data_dir,
        )
        if max_array_index is None:
            return None

        args = [
            "sbatch",
            f"--job-name={job_name}",
            f"--account={account}",
            f"--cpus-per-task={self.cpus_per_task}",
            f"--mem={self.memory}",
            f"--time={self.time}",
            f"--array=0-{max_array_index}",
            f"--output={log_file}",
            f"--error={log_file}",
            f"--wrap={' '.join(wrap_args)}",
        ]
        if self.gpus is not None:
            args.append(f"--gpus={self.gpus}")
        if dependencies:
            # TODO: Test that this works
            args.append(f"--dependency={dependencies.as_flag_value()}")
        if wait:
            args.append("--wait")

        return args

    def submit_array_job(
            self,
            job_name: str,
            slurm_params: SlurmParams,
            array_job_data_dir: Path,
            log_file: Path,
            extra_job_wrap_args: list[str] | None = None,
            dependencies: SlurmDependencies | None = None,
            wait: bool = True,
    ) -> bool:
        """Submit a slurm array job to handle the compute portion of the job."""
        # TODO: Find way to remove params that are just passed to `build_array_job_command`.

        wrap_args = [
            subprocess.list2cmdline([arg]) for arg in [
                # TODO: Confirm this works
                f"cd {self.paths.project_dir} && cluster-run",
                "--paths-json",  self.paths.attempt_paths_json,
                "--project-dir",  self.paths.project_dir,
                "--python-module-path", self.paths.runner_module_path,
                "--runner-stage",  _RunnerStage.COMPUTE.name,
            ] + (extra_job_wrap_args if extra_job_wrap_args is not None else [])
            + (["--debug"] if logger.isEnabledFor(logging.DEBUG) else [])
        ]

        args = slurm_params.build_array_job_command(
            job_name,
            array_job_data_dir,
            log_file,
            wrap_args,
            dependencies,
            wait,
        )
        if args is None:
            logger.info(
                f"No jobs to run for {job_name}, "
                f"skipping array job submission!"
            )
            return True

        logger.info(f"Waiting for {job_name} slurm array job to complete...")
        success = run_subprocess_command(args, logger=logger)
        # success = run_subprocess_command(
        #     args=["bash"] + wrap_args,
        #     logger=logger,
        # )

        if success:
            logger.info(f"{job_name} slurm jobs completed!")
        else:
            logger.warning(f"One or more {job_name} slurm jobs failed.")
        return success

    def submit_single_job(self) -> None:
        """Submit a single slurm job to handle the compute portion of the job.
        """
        raise NotImplementedError()

    def post_process(self) -> bool:
        """Virtual method for performing post-processing after the compute
        stage completes.

        Returns
        -------
        Whether post-processing was successful.
        """
        return True


@dataclass(frozen=True)
class _ComputeRunner(ArgParser, ABC):
    """Abstract class that handles running the portion of a run that occurs
    on a cluster's compute node."""

    compute_dir: Path
    job_data: ArrayJobData

    @staticmethod
    def parser_name() -> str:
        return "Compute Runner"

    @staticmethod
    def parser_description() -> str:
        return ("Perform logic on compute node of "
                "Digital Research Alliance of Canada cluster.")

    @property
    def compute_input_dir(self) -> Path:
        """Path to input directory on the compute node."""
        return self.compute_dir / "input"

    @property
    def compute_output_dir(self) -> Path:
        """Path to output directory on the compute node."""
        return self.compute_dir / "output"

    def run(self) -> bool:
        """Perform a compute run."""

        if not self._initialize_file_structure():
            return False

        return self.perform_computations()

    def _initialize_file_structure(self) -> bool:
        """Initialize compute file structure.

        Returns
        -------
        Whether initialization was successful.
        """

        logger.debug("Initializing compute node file structure...")
        if not self.compute_dir.is_dir():
            raise NotADirectoryError(
                f"Could not find compute dir at '{self.compute_dir}'."
            )

        # Initialize input dir
        self.compute_input_dir.mkdir()
        for path in self.job_data.input_paths:
            shutil.copy2(path, self.compute_input_dir)

        # Initialize output dir
        self.compute_output_dir.mkdir()

        # Perform custom initialization
        return self.initialize_compute_file_structure()

    def initialize_compute_file_structure(self) -> bool:
        """Virtual method to allow for performing additional initialization.

        Returns
        -------
        Whether initialization was successful.
        """
        return True

    @abstractmethod
    def perform_computations(self) -> bool:
        """Abstract method for performing the compute logic on the compute node.

        Returns
        -------
        Whether compute logic was performed successful.
        """
        return True

    def call_function_on_inputs(
            self,
            func: Callable[[Path], Any],
            log_name: str | None = None
    ) -> None:
        """Helper method for calling a function on all inputs for compute job.

        Parameters
        ----------
        func
            Function to call for each input. Path to input file will be passed
            to the function.
        log_name
            Optional name to use in log message. Logging skipped if not
            provided.
        """

        input_files: list[Path] = sorted(self.compute_input_dir.iterdir())
        for input_index, input_file in enumerate(input_files, start=1):
            if log_name:
                logger.info(f"Performing {log_name} on {input_file.stem} "
                            f"({input_index}/{len(input_files)})...")
            func(input_file)


@dataclass(frozen=True)
class _ClusterRunners:
    """Manager class for orchestrating which stage to run."""

    _stage: _RunnerStage

    def run_stage(self) -> bool:
        """Perform stage of program.

        Returns
        -------
        Whether stage was run successfully.
        """

        match self._stage:
            case _RunnerStage.LOGIN:
                return _LoginRunner.from_args().run()
            case _RunnerStage.COMPUTE:
                return _ComputeRunner.from_args().run()
            case _:
                raise ValueError(f"Unsupported runner stage: {stage}.")

    @classmethod
    def from_args(cls):
        """Create an instance populated with command line arguments."""

        parser = argparse.ArgumentParser(
            prog="Cluster Runners",
            description="Handles running the different stages of a program on "
                        "a cluster.",
            add_help=False,
        )
        parser.add_argument(
            "--runner-stage",
            help="Stage to perform for runner. Only for internal use.",
            type=_RunnerStage,
            default=_RunnerStage.LOGIN,
            action=EnumAction,
        )
        args, _ = parser.parse_known_args()

        return cls(_stage=args.runner_stage)


def _find_user_workflow_class(workflow_script: Path) -> type[FullWorkflow]:
    # TODO: Replace hardcoded debug field name
    toml_field_name = "workflow-script"
    target_type: type = FullWorkflow
    if not workflow_script.is_file():
        raise FileNotFoundError(
            f"Could not find workflow script at '{workflow_script}'."
            f"Update config TOML `{toml_field_name}` to point to "
            f"your workflow script."
        )
    subclasses: list[type[FullWorkflow]] = find_subclasses_in_script(
        workflow_script,
        target_type,
    )
    if len(subclasses) != 1:
        raise RuntimeError(
            f"Could not find subclass of `{target_type}` in workflow script at "
            f"'{workflow_script}'. Define a class in workflow script that "
            f"inherits from `{target_type}`.")

    return subclasses[0]


def main():
    # TODO: Extract log level parsing to other script
    parser = argparse.ArgumentParser(description="Logger Management")
    parser.add_argument(
        "--log-level",
        type=int,
        default=get_environment_default_log_level(),
        help="Numeric logging level passed from parent process."
    )
    parser.add_argument(
        "--project-dir",
        type=Path,
        help="Path to root directory of project."
    )
    args, _ = parser.parse_known_args()

    logger.setLevel(args.log_level)
    paths = ProjectPaths(args.project_dir)
    config = ClusterConfig.from_toml(paths.cluster_config_toml)

    workflow_class = _find_user_workflow_class(
        (paths.project_dir / config.global_config.workflow_script_rel_path).resolve()
    )
    # TODO: Call runners using entrypoint
    # _ClusterRunners.from_args().run_stage()


if __name__ == "__main__":
    main()
