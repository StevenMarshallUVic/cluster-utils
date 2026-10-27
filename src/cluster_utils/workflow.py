"""Classes for running jobs on a cluster."""

from abc import abstractmethod, ABC
from dataclasses import dataclass


@dataclass
class LoginWorkflow(ABC):
    @property
    @abstractmethod
    def jobs(self) -> list[type[SlurmJob]]:
        """Jobs to run. Order determines order of jobs submitted."""
        raise NotImplementedError()

    @abstractmethod
    def pre_initialize(self) -> bool:
        return True

    @abstractmethod
    def post_initialize(self) -> bool:
        return True

    @abstractmethod
    def pre_job_submission(self) -> bool:
        return True

    @abstractmethod
    def post_job_submission(self) -> bool:
        return True

    @abstractmethod
    def pre_post_process(self) -> bool:
        return True

    @abstractmethod
    def post_post_process(self) -> bool:
        return True


@dataclass
class ComputeWorkflow(ABC):
    pass


@dataclass
class FullWorkflow(ABC):
    @property
    @abstractmethod
    def login_workflow(self) -> type[LoginWorkflow]:
        pass

    @property
    @abstractmethod
    def compute_workflow(self) -> type[ComputeWorkflow]:
        pass
