import subprocess
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from cluster_utils.data import ArrayJobData, Paths, SlurmParams
from cluster_utils.utils import create_logger, run_subprocess_command


logger = create_logger(__file__)


class LoginForegroundRunner(ABC):
    @property
    @abstractmethod
    def paths(self) -> Paths:
        pass

    def run_foreground(self):
        self._initialize_foreground()
        self._run_in_background()

    @abstractmethod
    def _initialize_foreground(self):
        pass

    def _run_in_background(self):
        # sys.executable to use current python environment
        command = [
            sys.executable,
            "-m", self.paths.login_background_module_path,
            "--paths-json", self.paths.attempt_paths_json,
        ]

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
    paths: Paths
    slurm_params: SlurmParams

    @property
    @abstractmethod
    def is_array_job(self) -> bool:
        pass

    @property
    @abstractmethod
    def slurm_job_name(self) -> str:
        return f"{self.paths.project_name().lower()}-compute"

    @property
    def extra_job_wrap_args(self) -> list[str]:
        return []

    def run_background(self):
        self._initialize_background()
        if self.is_array_job:
            self._submit_array_job()
        else:
            self._submit_single_job()
        self._post_process_background()

    def _initialize_background(self) -> None:
        pass

    def _submit_array_job(self) -> None:
        wrap_args = " ".join(subprocess.list2cmdline([arg]) for arg in [
            self.paths.cluster_compute_shell_script,
            "--paths-json", self.paths.attempt_paths_json,
            "--project-dir", self.paths.project_dir,
            "--python-module-path", self.paths.compute_module_path,
        ] + self.extra_job_wrap_args)

        logger.info("Waiting for slurm array job to complete...")
        run_subprocess_command([
            "sbatch",
            f"--job-name={self.slurm_job_name}",
            f"--account={self.slurm_params.read_account_from_file(
                self.paths.account_file
            )}",
            f"--cpus-per-task={self.slurm_params.cpus_per_task}",
            f"--mem={self.slurm_params.memory}",
            f"--time={self.slurm_params.time}",
            f"--array=0-{ArrayJobData.find_greatest_array_job_index(
                self.paths.attempt_array_job_data_dir,
            )}",
            f"--output={self.paths.compute_log_file}",
            f"--error={self.paths.compute_log_file}",
            "--wait",
            f"--wrap={wrap_args}",
        ])

        logger.info("Slurm jobs completed!")

    def _submit_single_job(self) -> None:
        raise NotImplementedError()

    def _post_process_background(self) -> None:
        pass


@dataclass(frozen=True)
class ComputeRunner(ABC):
    compute_dir: Path
    job_data: ArrayJobData

    @property
    def compute_input_dir(self):
        return self.compute_dir / "input"

    @property
    def compute_output_dir(self):
        return self.compute_dir / "output"

    @abstractmethod
    def perform_compute(self):
        pass
