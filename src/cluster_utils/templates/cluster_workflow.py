from cluster_utils.data import SlurmJob
from cluster_utils.workflow import FullWorkflow, LoginWorkflow, ComputeWorkflow

class Login(LoginWorkflow):

    @property
    def jobs(self) -> list[type[SlurmJob]]:
        return []

    def pre_initialize(self) -> bool:
        return True

    def post_initialize(self) -> bool:
        return True

    def pre_job_submission(self) -> bool:
        return True

    def post_job_submission(self) -> bool:
        return True

    def pre_post_process(self) -> bool:
        return True

    def post_post_process(self) -> bool:
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
