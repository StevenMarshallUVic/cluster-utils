"""Classes for running jobs on a cluster."""

from abc import abstractmethod, ABC
from dataclasses import dataclass
from pathlib import Path

from cluster_utils.data import SlurmJob, RunPaths, LoginPaths, ComputePaths
from cluster_utils.utils import staticclass


@staticclass
class LoginWorkflow(ABC):
    @classmethod
    @abstractmethod
    def jobs(cls) -> list[type[SlurmJob]]:
        """Jobs to run. Order determines order of jobs submitted."""
        raise NotImplementedError()

    @classmethod
    @abstractmethod
    def pre_initialize(cls, paths: LoginPaths) -> bool:
        return True

    @classmethod
    @abstractmethod
    def transfer_input_to_run(
            cls,
            input_path: Path,
            run_paths: RunPaths,
    ) -> bool:
        """Abstract method for handling the transfer of inputs to the run.

        Parameters
        ----------
        input_path
            Path to input to handle transfer for.
        run_paths
            Paths for run to transfer input to.
        """
        raise NotImplementedError()

    @classmethod
    @abstractmethod
    def post_initialize(cls, paths: LoginPaths) -> bool:
        return True

    @classmethod
    @abstractmethod
    def pre_job_submission(cls, paths: LoginPaths) -> bool:
        return True

    @classmethod
    @abstractmethod
    def post_job_submission(cls, paths: LoginPaths) -> bool:
        return True

    @classmethod
    @abstractmethod
    def pre_post_process(cls, paths: LoginPaths) -> bool:
        return True

    @classmethod
    @abstractmethod
    def post_post_process(cls, paths: LoginPaths) -> bool:
        return True


@staticclass
class ComputeWorkflow(ABC):
    @classmethod
    @abstractmethod
    def pre_initialize(cls, paths: ComputePaths) -> bool:
        return True

    @classmethod
    @abstractmethod
    def post_initialize(cls, paths: ComputePaths) -> bool:
        return True

    @classmethod
    @abstractmethod
    def pre_computation(cls, paths: ComputePaths) -> bool:
        return True

    @classmethod
    @abstractmethod
    def post_computation(cls, paths: ComputePaths) -> bool:
        return True

    @classmethod
    @abstractmethod
    def pre_post_process(cls, paths: ComputePaths) -> bool:
        return True

    @classmethod
    @abstractmethod
    def post_post_process(cls, paths: ComputePaths) -> bool:
        return True


@staticclass
class FullWorkflow(ABC):
    @classmethod
    @abstractmethod
    def project_name(cls) -> str:
        pass

    @classmethod
    @abstractmethod
    def login_workflow(cls) -> type[LoginWorkflow]:
        pass

    @classmethod
    @abstractmethod
    def compute_workflow(cls) -> type[ComputeWorkflow]:
        pass
