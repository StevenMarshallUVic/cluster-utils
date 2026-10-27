from cluster_utils.data import SlurmJob, SlurmDependencyType, SlurmJobType
from cluster_utils.workflow import FullWorkflow, LoginWorkflow, ComputeWorkflow


class TestJob(SlurmJob):
    @staticmethod
    def job_name() -> str:
        return "test"

    @staticmethod
    def default_batch_size() -> int:
        return 1

    @staticmethod
    def default_memory() -> str:
        return "1G"

    @staticmethod
    def default_time() -> str:
        return "01:00:00"

    @staticmethod
    def default_cpus_per_task() -> int:
        return 1

    @staticmethod
    def gpus() -> str | None:
        return None

    @staticmethod
    def job_type() -> SlurmJobType:
        return SlurmJobType.ARRAY

    @staticmethod
    def arg_prefix() -> str | None:
        return None

    @staticmethod
    def job_dependencies() -> dict[type[SlurmJob], SlurmDependencyType]:
        return {}

    @staticmethod
    def require_all_dependencies() -> bool:
        return True


class Login(LoginWorkflow):
    @staticmethod
    def jobs() -> list[type[SlurmJob]]:
        return [TestJob]

    @staticmethod
    def pre_initialize() -> bool:
        return True

    @staticmethod
    def transfer_input_to_run(input_path: Path, input_dir: Path) -> None:
        pass

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
