"""Classes for running jobs on a cluster."""

from abc import abstractmethod, ABC
from dataclasses import dataclass
from pathlib import Path

from cluster_utils.data import SlurmJob, RunPaths


class LoginWorkflow(ABC):
    # TODO: Turn into class decorator?
    def __new__(cls, *args, **kwargs):
        raise TypeError(
            f"Class '{cls.__name__}' is static and cannot be instantiated."
        )

    @staticmethod
    @abstractmethod
    def jobs() -> list[type[SlurmJob]]:
        """Jobs to run. Order determines order of jobs submitted."""
        raise NotImplementedError()

    @staticmethod
    @abstractmethod
    def pre_initialize(run_paths: RunPaths) -> bool:
        return True

    @staticmethod
    @abstractmethod
    def transfer_input_to_run(input_path: Path, run_paths: RunPaths) -> bool:
        """Abstract method for handling the transfer of inputs to the run.

        Parameters
        ----------
        input_path
            Path to input to handle transfer for.
        run_paths
            Paths for run to transfer input to.
        """
        raise NotImplementedError()

    @staticmethod
    @abstractmethod
    def post_initialize(run_paths: RunPaths) -> bool:
        return True

    @staticmethod
    @abstractmethod
    def pre_job_submission(run_paths: RunPaths) -> bool:
        return True

    @staticmethod
    @abstractmethod
    def post_job_submission(run_paths: RunPaths) -> bool:
        return True

    @staticmethod
    @abstractmethod
    def pre_post_process(run_paths: RunPaths) -> bool:
        return True

    @staticmethod
    @abstractmethod
    def post_post_process(run_paths: RunPaths) -> bool:
        return True


@dataclass
class ComputeWorkflow(ABC):
    pass


@dataclass
class FullWorkflow(ABC):
    @property
    @abstractmethod
    def project_name(self) -> str:
        pass

    @property
    @abstractmethod
    def login_workflow(self) -> type[LoginWorkflow]:
        pass

    @property
    @abstractmethod
    def compute_workflow(self) -> type[ComputeWorkflow]:
        pass
