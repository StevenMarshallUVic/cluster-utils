"""Classes for running jobs on a cluster."""

import argparse
import logging
import subprocess
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

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

    def run_foreground(self) -> None:
        """Perform foreground portion of run."""

        self._initialize_foreground()
        self._run_in_background()

    @abstractmethod
    def _initialize_foreground(self) -> None:
        """Abstract method for initializing a run in the foreground."""

        pass

    def _run_in_background(self) -> None:
        """Perform rest of run in the background."""

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
            subprocess.Popen(
                command,
                stdout=log_file,
                stderr=log_file,
                start_new_session=True
            )


@dataclass(frozen=True)
class LoginBackgroundRunner(ABC):
    """Abstract class that handles running the portion of a run that occurs
    in the background."""

    paths: Paths

    def run_background(self):
        """Perform background portion of run."""

        self._initialize_background()
        self._submit_compute_jobs()
        self._post_process_background()

    def _initialize_background(self) -> None:
        """Virtual method for initializing a run in the background."""
        pass

    @abstractmethod
    def _submit_compute_jobs(self):
        """Virtual method for submitting compute jobs."""
        pass

    def _submit_array_job(
            self,
            job_name: str,
            slurm_params: SlurmParams,
            array_job_data_dir: Path,
            log_file: Path,
            extra_job_wrap_args: list[str] | None = None,
    ) -> None:
        """Submit a slurm array job to handle the compute portion of the job."""

        max_array_index: int | None = ArrayJobData.find_greatest_array_job_index(
            array_job_data_dir,
        )
        if max_array_index is None:
            logger.info("No jobs to run, skipping array job submission!")
            return

        wrap_args = " ".join(subprocess.list2cmdline([arg]) for arg in [
            self.paths.cluster_compute_shell_script,
            "--paths-json", self.paths.attempt_paths_json,
            "--project-dir", self.paths.project_dir,
            "--python-module-path", self.paths.runner_module_path,
            "--runner-stage", _RunnerStage.COMPUTE.name,
        ] + (extra_job_wrap_args if extra_job_wrap_args is not None else []))
        if logger.isEnabledFor(logging.DEBUG):
            wrap_args += " --debug"

        logger.info("Waiting for slurm array job to complete...")
        run_subprocess_command(
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

        logger.info("Slurm jobs completed!")

    def _submit_single_job(self) -> None:
        """Submit a single slurm job to handle the compute portion of the job.
        """
        raise NotImplementedError()

    def _post_process_background(self) -> None:
        """Virtual method for performing post-processing in the background
        after the compute stage completes."""
        pass


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

    @abstractmethod
    def perform_compute(self):
        """Abstract method for performing the compute logic on the compute node.
        """
        pass


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

    def run_stage(self):
        """Perform stage of program."""
        match self._stage:
            case _RunnerStage.FOREGROUND:
                self.login_foreground_runner.run_foreground()
            case _RunnerStage.BACKGROUND:
                self.login_background_runner.run_background()
            case _RunnerStage.COMPUTE:
                self.compute_runner.perform_compute()
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
