"""Classes for running jobs on a cluster."""

from abc import abstractmethod, ABC
from dataclasses import dataclass

from cluster_utils.data import SlurmDependencyType, SlurmJobType


@dataclass
class SlurmJob(ABC):
    @property
    @abstractmethod
    def job_name(self) -> str:
        """Name of Slurm job. Will be shown in slurm job displays."""
        pass

    @property
    @abstractmethod
    def default_batch_size(self) -> int:
        """Default number of inputs to batch together if an override is not
        provided on the command line.
        """
        pass

    @property
    @abstractmethod
    def default_memory(self) -> str:
        """Default RAM to allocate if an override is not
        provided on the command line.
        """
        pass

    @property
    @abstractmethod
    def default_time(self) -> str:
        """Default runtime to allocate if an override is not
        provided on the command line.
        """
        pass

    @property
    @abstractmethod
    def default_cpus_per_task(self) -> int:
        """Default number of CPUs to allocate if an override is not
        provided on the command line.
        """
        return 1

    @property
    @abstractmethod
    def gpus(self) -> str | None:
        """Optional number and type of GPUs to allocate."""
        return None

    @property
    @abstractmethod
    def job_type(self) -> SlurmJobType:
        """Type of slurm job to submit."""
        return SlurmJobType.ARRAY

    @property
    @abstractmethod
    def arg_prefix(self) -> str | None:
        """Optional prefix to add to command line arguments for slurm params.

        Helpful when defining more than one SlurmJob in project, allowing
        assignment of custom slurm params to each job type from command line.
        """
        return None

    @property
    @abstractmethod
    def job_dependencies(
            self
    ) -> dict[type[SlurmJob], SlurmDependencyType]:
        """Mapping between jobs that this job depends on and the nature
        of the dependency.
        """
        return {}


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
