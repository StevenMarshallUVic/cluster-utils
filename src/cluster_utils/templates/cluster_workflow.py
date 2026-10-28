from cluster_utils.data import SlurmJob, SlurmDependencyType, SlurmJobType
from cluster_utils.workflow import FullWorkflow, LoginWorkflow, ComputeWorkflow


class CustomFullWorkflow(FullWorkflow):
    @property
    def project_name(self) -> str:
        raise NotImplementedError("Must set 'project_name'.")

    @property
    def login_workflow(self) -> type[LoginWorkflow]:
        raise NotImplementedError(
            "Must create class inheriting from `LoginWorkflow` and assign."
        )

    @property
    def compute_workflow(self) -> type[ComputeWorkflow]:
        raise NotImplementedError(
            "Must create class inheriting from `ComputeWorkflow` and assign."
        )
