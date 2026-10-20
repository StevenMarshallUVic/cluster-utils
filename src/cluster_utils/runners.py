"""Classes for running jobs on a cluster."""

import argparse
import logging
import shutil
import subprocess
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self

from cluster_utils.data import ArrayJobData, Paths, SlurmParams
from cluster_utils.utils import EnumAction, _RunnerStage, \
    run_subprocess_command, log_args_help, ArgParseable

logger = logging.getLogger(Path(__file__).name)


@dataclass(frozen=True)
class LoginRunner(ABC):
    """Abstract class that handles running the portion of a run that occurs
    in the background on a login node."""

    # TODO: Figure out best way to handle this variable
    paths: Paths

    @staticmethod
    @abstractmethod
    def additional_cmd_line_arguments() -> list[type[ArgParseable]]:
        """Abstract property for specifying additional argument sources."""
        return []

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

    def _submit_array_job(
            self,
            job_name: str,
            slurm_params: SlurmParams,
            array_job_data_dir: Path,
            log_file: Path,
            extra_job_wrap_args: list[str] | None = None,
            wait=True,
    ) -> bool:
        """Submit a slurm array job to handle the compute portion of the job."""

        max_array_index: int | None = ArrayJobData.find_greatest_array_job_index(
            array_job_data_dir,
        )
        if max_array_index is None:
            logger.info(
                f"No jobs to run for {job_name}, "
                f"skipping array job submission!"
            )
            return True

        # TODO: Create class for storing data and building slurm command
        wrap_args = [
            subprocess.list2cmdline([arg]) for arg in [
                self.paths.cluster_compute_shell_script,
                "--paths-json",  self.paths.attempt_paths_json,
                "--project-dir",  self.paths.project_dir,
                "--python-module-path", self.paths.runner_module_path,
                "--runner-stage",  _RunnerStage.COMPUTE.name,
            ] + (extra_job_wrap_args if extra_job_wrap_args is not None else [])
            + (["--debug"] if logger.isEnabledFor(logging.DEBUG) else [])
        ]

        args = [
            "sbatch",
            f"--job-name={job_name}",
            f"--account={slurm_params.read_account_from_file(
                self.paths.account_file
            )}",
            f"--cpus-per-task={slurm_params.cpus_per_task}",
            f"--mem={slurm_params.memory}",
            f"--time={slurm_params.time}",
            f"--array=0-{max_array_index}",
            f"--output={log_file}",
            f"--error={log_file}",
            f"--wrap={' '.join(wrap_args)}",
        ]
        if wait:
            args.append("--wait")

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

    def _submit_single_job(self) -> None:
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

    @classmethod
    @abstractmethod
    def from_custom_args(cls, args: argparse.Namespace) -> Self:
        raise NotImplementedError()

    @classmethod
    def from_args(cls) -> Self:
        """Create instance from command line arguments."""

        parser = argparse.ArgumentParser(
            prog="Login Runner",
            description="Perform logic on login node of Digital Research Alliance of Canada cluster.",
            epilog="See README.md for more information.",
            conflict_handler="resolve",
            add_help=False,
        )
        parser.add_argument(
            "-h", "--help",
            action="store_true",
            help="show this help message and exit"
        )
        args, _ = parser.parse_known_args()
        if args.help:
            log_args_help(
                parser,
                cls.additional_cmd_line_arguments(),
            )
            exit(0)

        for argument_source in cls.additional_cmd_line_arguments():
            argument_source.add_arguments(parser)

        args, _ = parser.parse_known_args()
        return cls.from_custom_args(args)


@dataclass(frozen=True)
class ComputeRunner(ABC):
    """Abstract class that handles running the portion of a run that occurs
    on a cluster's compute node."""

    compute_dir: Path
    job_data: ArrayJobData

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

    @classmethod
    def from_args(cls) -> Self:
        """Create instance from command line arguments."""

        parser = argparse.ArgumentParser(
            prog="Cluster Runner",
            description="Perform logic on compute node of Digital Research Alliance of Canada cluster.",
            epilog="See README.md for more information.",
            conflict_handler="resolve",
        )
        ArrayJobInstanceParams.add_arguments(parser)
        args, _ = parser.parse_known_args()

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
class ClusterRunners(ABC):
    """Manager class for orchestrating which stage to run."""

    _stage: _RunnerStage

    @property
    @abstractmethod
    def login_runner(self) -> LoginRunner:
        """Abstract property for specifying which login runner to use."""
        pass

    @property
    @abstractmethod
    def compute_runner(self) -> ComputeRunner:
        """Abstract property for specifying which compute runner to use."""
        pass

    def run_stage(self) -> bool:
        """Perform stage of program.

        Returns
        -------
        Whether stage was run successfully.
        """

        match self._stage:
            case _RunnerStage.LOGIN:
                return self.login_runner.run()
            case _RunnerStage.COMPUTE:
                return self.compute_runner.run()
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
