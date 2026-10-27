from cluster_utils.data import SlurmJob
from cluster_utils.workflow import FullWorkflow, LoginWorkflow, ComputeWorkflow

class Login(LoginWorkflow):
    @staticmethod
    def jobs() -> list[type[SlurmJob]]:
        return []

    @staticmethod
    def pre_initialize() -> bool:
        return True

    @staticmethod
    def post_initialize() -> bool:
        return True

    @staticmethod
    def pre_job_submission() -> bool:
        return True

    @staticmethod
    def post_job_submission() -> bool:
        return True

    @staticmethod
    def pre_post_process() -> bool:
        return True

    @staticmethod
    def post_post_process() -> bool:
        return True


class Compute(ComputeWorkflow):
    pass


# TODO: Remove implementation after testing
class CustomFullWorkflow(FullWorkflow):
    @property
    def project_name(self) -> str:
        return "test_project"

    @property
    def login_workflow(self) -> type[LoginWorkflow]:
        return Login

    @property
    def compute_workflow(self) -> type[ComputeWorkflow]:
        return Compute
