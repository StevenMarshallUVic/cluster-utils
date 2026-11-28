from cluster_utils.data import SlurmJob, SlurmDependencyType, SlurmJobType
from cluster_utils.workflow import FullWorkflow, LoginWorkflow, ComputeWorkflow


class CustomFullWorkflow(FullWorkflow):
    @classmethod
    def project_name(cls) -> str:
        raise NotImplementedError("Must set 'project_name'.")

    @classmethod
    def login_workflow(cls) -> type[LoginWorkflow]:
        raise NotImplementedError(
            "Must create class inheriting from `LoginWorkflow` "
            "and assign type."
        )

    @classmethod
    def compute_workflow(cls) -> type[ComputeWorkflow]:
        raise NotImplementedError(
            "Must create class inheriting from `ComputeWorkflow` "
            "and assign type."
        )
