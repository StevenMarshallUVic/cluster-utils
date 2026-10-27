"""Classes for running jobs on a cluster."""

from abc import abstractmethod, ABC
from dataclasses import dataclass

from cluster_utils.data import SlurmJob


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
    def pre_initialize() -> bool:
        return True

    @staticmethod
    @abstractmethod
    def transfer_input_to_run(input_path: Path, input_dir: Path) -> None:
        """Abstract method for handling the transfer of inputs to the run
        input directory.

        Parameters
        ----------
        input_path
            Path to input to handle transfer for.
        input_dir
            Run input directory to transfer to.
        """
        raise NotImplementedError()

    @staticmethod
    @abstractmethod
    def post_initialize() -> bool:
        return True

    @staticmethod
    @abstractmethod
    def pre_job_submission() -> bool:
        return True

    @staticmethod
    @abstractmethod
    def post_job_submission() -> bool:
        return True

    @staticmethod
    @abstractmethod
    def pre_post_process() -> bool:
        return True

    @staticmethod
    @abstractmethod
    def post_post_process() -> bool:
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
