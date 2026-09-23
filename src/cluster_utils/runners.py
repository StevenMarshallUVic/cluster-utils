"""Classes for running jobs on a cluster."""

import argparse
import logging
import shutil
import subprocess
import sys
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cluster_utils.data import ArrayJobData, Paths, SlurmParams
from cluster_utils.utils import EnumAction, _RunnerStage, run_subprocess_command

logger = logging.getLogger(Path(__file__).name)


class LoginForegroundRunner(ABC):
    """Abstract class that handles running the portion of a run that occurs
    on the main thread."""

    @property
    @abstractmethod
    def paths(self) -> Paths:
        """Abstract method for specifying Paths class or subclass."""
        pass

    def run_foreground(self) -> bool:
        """Perform foreground portion of run."""

        if not self._initialize_foreground():
            return False

        return self._run_in_background()

    @abstractmethod
    def _initialize_foreground(self) -> bool:
        """Abstract method for initializing a run in the foreground.

        Returns
        -------
        Whether initialization was successful.
        """
        return True

    def _run_in_background(self) -> bool:
        """Perform rest of run in the background.

        Returns
        -------
        Whether run was successfully submitted to background.
        """

        # sys.executable to use current python environment
        command = [
            sys.executable,
            "-m", self.paths.runner_module_path,
            "--paths-json", self.paths.attempt_paths_json,
            "--runner-stage", _RunnerStage.BACKGROUND.name,
        ]
        if logger.isEnabledFor(logging.DEBUG):
            command.append("--debug")

        logger.info("Performing run in background. Logs can be found at "
                    f"'{self.paths.login_background_log_file}'.")
        with open(self.paths.login_background_log_file, "w") as log_file:
            # Run as background task
            process = subprocess.Popen(
                command,
                stdout=log_file,
                stderr=log_file,
                start_new_session=True
            )

            return process.wait() == 0


@dataclass(frozen=True)
class LoginBackgroundRunner(ABC):
    """Abstract class that handles running the portion of a run that occurs
    in the background."""

    paths: Paths

    def run_background(self) -> bool:
        """Perform background portion of run.

        Returns
        -------
        Whether background processes were run successfully.
        """

        if not self._initialize_background():
            return False

        if not self._submit_compute_jobs():
            logger.warning(
                "One or more compute jobs failed, skipping post processing."
            )
            return False

        return self._post_process_background()

    def _initialize_background(self) -> bool:
        """Virtual method for initializing a run in the background.

        Returns
        -------
        Whether initialization was successful.
        """
        return True

    @abstractmethod
    def _submit_compute_jobs(self) -> bool:
        """Virtual method for submitting compute jobs.

        Returns
        -------
        bool
            Whether compute jobs completed successfully.
        """
        pass

    def _submit_array_job(
            self,
            job_name: str,
            slurm_params: SlurmParams,
            array_job_data_dir: Path,
            log_file: Path,
            extra_job_wrap_args: list[str] | None = None,
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

        wrap_args = " ".join(subprocess.list2cmdline([arg]) for arg in [
            self.paths.cluster_compute_shell_script,
            "--paths-json", self.paths.attempt_paths_json,
            "--project-dir", self.paths.project_dir,
            "--python-module-path", self.paths.runner_module_path,
            "--runner-stage", _RunnerStage.COMPUTE.name,
        ] + (extra_job_wrap_args if extra_job_wrap_args is not None else []))
        if logger.isEnabledFor(logging.DEBUG):
            wrap_args += " --debug"

        logger.info(f"Waiting for {job_name} slurm array job to complete...")
        success = run_subprocess_command(
            args=[
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
                "--wait",
                f"--wrap={wrap_args}",
            ],
            logger=logger,
        )

        if success:
            logger.info(f"{job_name} slurm jobs completed!")
        else:
            logger.warning(f"One or more {job_name} slurm jobs failed.")

        return success

    def _submit_single_job(self) -> None:
        """Submit a single slurm job to handle the compute portion of the job.
        """
        raise NotImplementedError()

    def _post_process_background(self) -> bool:
        """Virtual method for performing post-processing in the background
        after the compute stage completes.

        Returns
        -------
        Whether post-processing was successful.
        """
        return True


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

    def run_compute(self) -> bool:
        """Perform a compute run."""

        if not self._initialize_compute_file_structure():
            return False

        return self.perform_compute()

    def _initialize_compute_file_structure(self) -> bool:
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
    def perform_compute(self) -> bool:
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
class ClusterRunners(ABC):
    """Manager class for orchestrating which stage to run."""

    _stage: _RunnerStage

    @property
    @abstractmethod
    def login_foreground_runner(self) -> LoginForegroundRunner:
        """Abstract property for specifying which foreground runner to use."""
        pass

    @property
    @abstractmethod
    def login_background_runner(self) -> LoginBackgroundRunner:
        """Abstract property for specifying which background runner to use."""
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
            case _RunnerStage.FOREGROUND:
                return self.login_foreground_runner.run_foreground()
            case _RunnerStage.BACKGROUND:
                return self.login_background_runner.run_background()
            case _RunnerStage.COMPUTE:
                return self.compute_runner.run_compute()
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
            default=_RunnerStage.FOREGROUND,
            action=EnumAction,
        )
        args, _ = parser.parse_known_args()

        return cls(_stage=args.runner_stage)
