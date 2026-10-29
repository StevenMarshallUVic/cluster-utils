import argparse
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Self, ClassVar

from cluster_utils import get_environment_default_log_level, init_logger, \
    SLURM_JOB_NAME_ENV_VAR
from cluster_utils._config import ClusterConfig
from cluster_utils._paths import ProjectPaths
from cluster_utils.data import ArrayJobData, LoginPaths, SlurmParams, \
    SlurmJobType, SlurmDependencies, SlurmDependency, ArrayJobInstanceParams, \
    SlurmJob, ComputePaths, ComputeNodePaths
from cluster_utils.utils import EnumAction, _RunnerStage, \
    run_subprocess_command, ArgParseable
from cluster_utils.workflow import FullWorkflow
from cluster_utils.workflow_utils import find_subclasses_in_script, ArgParser

logger = init_logger(Path(__file__).name)


@dataclass(frozen=True)
class _LoginRunner(ArgParser):
    """Abstract class that handles running the portion of a run that occurs
    in the background on a login node."""

    paths: LoginPaths
    job_name_to_slurm_params: dict[str, SlurmParams]

    workflow: ClassVar[type[FullWorkflow]]

    @staticmethod
    def parser_name() -> str:
        return "Login Runner"

    @staticmethod
    def parser_description() -> str:
        return ("Perform logic on login node of "
                "Digital Research Alliance of Canada cluster.")

    @staticmethod
    def static_argument_sources() -> list[type[ArgParseable]]:
        static_argument_sources: list[type[ArgParseable]] = [LoginPaths]
        for job in _LoginRunner.workflow().login_workflow.jobs():
            static_argument_sources.append(
                SlurmParams.create_subclass_from_job(job)
            )
        return static_argument_sources

    def run(self) -> bool:
        """Perform login portion of run.

        Returns
        -------
        Whether login tasks were run successfully.
        """

        if not self.workflow().login_workflow.pre_initialize(self.paths):
            return False
        if not self.initialize():
            return False
        if not self.workflow().login_workflow.post_initialize(self.paths):
            return False

        if not self.workflow().login_workflow.pre_job_submission(self.paths):
            return False
        if not self.submit_compute_jobs():
            logger.warning(
                "One or more compute jobs failed, skipping post processing."
            )
            return False
        if not self.workflow().login_workflow.post_job_submission(self.paths):
            return False

        if not self.workflow().login_workflow.pre_post_process(self.paths):
            return False
        if not self.post_process():
            return False
        if not self.workflow().login_workflow.post_post_process(self.paths):
            return False

        return True

    def initialize(self) -> bool:
        """Perform general initialization for a run.

        Returns
        -------
        Whether initialization was successful.
        """

        self.paths.initialize_run()

        if not self.paths.run_paths.input_dir.is_dir():
            logger.debug("Initializing input directory...")
            self.paths.run_paths.input_dir.mkdir(parents=True)

            logger.debug("Transferring inputs to input directory...")
            input_path = self.paths.run_paths.input_path
            if input_path is None:
                raise ValueError(
                    "Input directory not initialized, input path required."
                )

            self.workflow().login_workflow.transfer_input_to_run(
                input_path,
                self.paths.run_paths,
            )
        return True

    def submit_compute_jobs(self) -> bool:
        """Submit user-designed compute jobs.

        Returns
        -------
        bool
            Whether compute jobs completed successfully.
        """

        if len(self.workflow().login_workflow.jobs()) <= 0:
            logger.info("No jobs to submit!")
            return True

        logger.info(
            f"Performing attempt {self.paths.attempt_paths.attempt_index} "
            f"of run found at '{self.paths.run_paths.run_dir}'."
        )

        job_to_slurm_id: dict[type[SlurmJob], int | None] = {}
        for job in self.workflow().login_workflow.jobs():
            depends: list[SlurmDependency] = []
            for depend_job, depend_type in job.job_dependencies().items():
                if depend_job not in job_to_slurm_id:
                    raise RuntimeError(
                        f"Trying to submit job '{job.job_name()}' "
                        f"before dependency '{depend_job.job_name()}'."
                    )
                # Skip adding dependency to jobs that did not run
                slurm_id = job_to_slurm_id[depend_job]
                if slurm_id is None:
                    continue

                depends.append(SlurmDependency(
                    depend_type,
                    tuple([slurm_id]),
                ))
            dependencies = SlurmDependencies(
                dependencies=tuple(depends),
                require_all_dependencies=job.require_all_dependencies(),
            ) if len(depends) > 0 else None

            match job.job_type():
                case SlurmJobType.ARRAY:
                    job_to_slurm_id[job] = self.submit_array_job(
                        job,
                        dependencies=dependencies,
                    )
                case SlurmJobType.SINGLE:
                    job_to_slurm_id[job] = self.submit_single_job(job)
                case _:
                    raise NotImplementedError(
                        f"Unsupported slurm job type: '{job.job_type}'."
                    )
        return True

    def submit_array_job(
            self,
            job: type[SlurmJob],
            dependencies: SlurmDependencies | None = None,
    ) -> int | None:
        """Submit a slurm array job to handle the compute portion of the job."""

        compute_job_args = job.compute_job_args()
        wrap_args = [
            subprocess.list2cmdline([arg]) for arg in [
                "cd", self.paths.project_paths.project_dir,
                "&&", "cluster-compute",
                "--paths-json",  self.paths.attempt_paths.paths_json,
                "--project-dir",  self.paths.project_paths.project_dir,
                "--runner-stage",  _RunnerStage.COMPUTE.name,
            ] + (compute_job_args if compute_job_args is not None else [])
        ]

        args = self.job_name_to_slurm_params[job.job_name()].build_array_job_command(
            self.paths,
            wrap_args,
            dependencies,
        )
        if args is None:
            logger.info(
                f"No jobs to run for {job.job_name()}, "
                f"skipping array job submission!"
            )
            return None

        logger.info(f"Waiting for {job.job_name()} slurm array job to complete...")
        success = run_subprocess_command(args, logger=logger)

        # TODO: Return slurm job ID

        if success:
            logger.info(f"{job.job_name()} slurm jobs completed!")
        else:
            logger.warning(f"One or more {job.job_name()} slurm jobs failed.")
        return success

    def submit_single_job(self, job: type[SlurmJob]) -> int:
        """Submit a single slurm job to handle the compute portion of the job.
        """
        raise NotImplementedError()

    def post_process(self) -> bool:
        """Performing post-processing after the compute stage completes.

        Returns
        -------
        Whether post-processing was successful.
        """
        return True

    @classmethod
    def from_custom_args(cls, args: argparse.Namespace, **kwargs) -> Self:
        if len(kwargs) > 0:
            raise ValueError(f"Unexpected keyword arguments: {kwargs}.")

        job_name_to_inst = {}
        for job in cls.workflow().login_workflow.jobs():
            slurm_params = SlurmParams.create_subclass_from_job(job)
            if job.job_name() in job_name_to_inst:
                raise KeyError("Multiple SlurmJobs with same job_name.")

            job_name_to_inst[job.job_name()] = slurm_params.from_args(args)

        return cls(
            paths=LoginPaths.from_custom_args(
                args,
                cls.workflow().project_name
            ),
            job_name_to_slurm_params=job_name_to_inst,
        )


@dataclass(frozen=True)
class _ComputeRunner(ArgParser):
    """Abstract class that handles running the portion of a run that occurs
    on a cluster's compute node."""

    paths: ComputePaths
    job_data: ArrayJobData

    @staticmethod
    def parser_name() -> str:
        return "Compute Runner"

    @staticmethod
    def parser_description() -> str:
        return ("Perform logic on compute node of "
                "Digital Research Alliance of Canada cluster.")

    @staticmethod
    def static_argument_sources() -> list[type[ArgParseable]]:
        return [ArrayJobInstanceParams]

    def _get_current_job(self, jobs: list[type[SlurmJob]]) -> type[SlurmJob]:
        job_name = os.getenv(SLURM_JOB_NAME_ENV_VAR)
        if job_name is None:
            raise RuntimeError(
                f"Could not find '{SLURM_JOB_NAME_ENV_VAR}' in environment. "
                "Are you sure this is being run on a compute node?"
            )

        job_name_to_job = {j.job_name(): j for j in jobs}
        if job_name not in job_name_to_job:
            raise KeyError(
                f"Could not find SlurmJob with name '{job_name}'. "
                f"Jobs: {list(job_name_to_job.keys())}"
            )

        return job_name_to_job[job_name]

    def run(self, full_workflow: type[FullWorkflow]) -> bool:
        """Perform a compute run."""

        job = self._get_current_job(full_workflow().login_workflow.jobs())

        if not job.pre_initialize(self.paths):
            return False
        if not self._initialize_file_structure():
            return False
        if not job.post_initialize(self.paths):
            return False

        if not job.perform_computations(self.paths):
            return False

        if not job.pre_post_process(self.paths):
            return False
        if not job.post_post_process(self.paths):
            return False

        return True

    def _initialize_file_structure(self) -> bool:
        """Initialize compute file structure.

        Returns
        -------
        Whether initialization was successful.
        """

        logger.debug("Initializing compute node file structure...")
        if not self.paths.compute_node_paths.compute_dir.is_dir():
            raise NotADirectoryError(
                f"Could not find compute dir at "
                f"'{self.paths.compute_node_paths.compute_dir}'."
            )

        # Initialize input dir
        self.paths.compute_node_paths.input_dir.mkdir()
        for path in self.job_data.input_paths:
            shutil.copy2(path, self.paths.compute_node_paths.input_dir)

        # Initialize output dir
        self.paths.compute_node_paths.output_dir.mkdir()
        return True

    @classmethod
    def from_custom_args(cls, args: argparse.Namespace, **kwargs) -> Self:
        if len(kwargs) > 0:
            raise ValueError(f"Unexpected kwargs: {kwargs}.")

        array_job_params = ArrayJobInstanceParams.from_args(args)
        login_paths = LoginPaths.from_json(array_job_params.paths_json)
        job_data = ArrayJobData.from_json(
            ArrayJobData.build_json_path(
                login_paths.array_job_data_root_dir,
                array_job_params.array_job_index,
            )
        )
        return cls(
            paths=ComputePaths(
                login_paths=login_paths,
                compute_node_paths=ComputeNodePaths(
                    array_job_params.compute_dir
                ),
            ),
            job_data=job_data,
        )


@dataclass(frozen=True)
class _ClusterRunners:
    """Manager class for orchestrating which stage to run."""

    _workflow_class: type[FullWorkflow]
    _stage: _RunnerStage

    def run_stage(self) -> bool:
        """Perform stage of program.

        Returns
        -------
        Whether stage was run successfully.
        """

        match self._stage:
            case _RunnerStage.LOGIN:
                _LoginRunner.workflow = self._workflow_class
                return _LoginRunner.from_args().run()
            case _RunnerStage.COMPUTE:
                return _ComputeRunner.from_args().run(self._workflow_class)
            case _:
                raise ValueError(f"Unsupported runner stage: {stage}.")

    @classmethod
    def from_args(cls, **kwargs):
        """Create an instance populated with command line arguments."""

        parser = argparse.ArgumentParser(
            prog="Cluster Runners",
            description="Handles running the different stages of a program on "
                        "a cluster.",
            add_help=False,
        )
        parser.add_argument(
            "--runner-stage",
            help="Stage to perform for runner. Only for internal use.",
            type=_RunnerStage,
            default=_RunnerStage.LOGIN,
            action=EnumAction,
        )
        args, _ = parser.parse_known_args()

        return cls(_stage=args.runner_stage, **kwargs)


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Cluster Runner")
    parser.add_argument(
        "--log-level",
        type=int,
        default=get_environment_default_log_level(),
        help="Argparse logging level to use."
    )
    parser.add_argument(
        "--project-dir",
        type=Path,
        help="Path to root directory of project.",
        required=True,
    )
    return parser


def _find_user_workflow_class(workflow_script: Path) -> type[FullWorkflow]:
    # TODO: Replace hardcoded debug field name
    toml_field_name = "workflow-script"
    target_type: type = FullWorkflow
    if not workflow_script.is_file():
        raise FileNotFoundError(
            f"Could not find workflow script at '{workflow_script}'."
            f"Update config TOML `{toml_field_name}` to point to "
            f"your workflow script."
        )
    subclasses: list[type[FullWorkflow]] = find_subclasses_in_script(
        workflow_script,
        target_type,
    )
    if len(subclasses) != 1:
        raise RuntimeError(
            f"Could not find subclass of `{target_type}` in workflow script at "
            f"'{workflow_script}'. Define a class in workflow script that "
            f"inherits from `{target_type}`.")

    return subclasses[0]


def main():
    args, _ = _build_argument_parser().parse_known_args()
    logger.setLevel(args.log_level)

    paths = ProjectPaths(args.project_dir)
    config = ClusterConfig.from_toml(paths.cluster_config_toml)

    workflow_class = _find_user_workflow_class(
        config.global_config.get_workflow_script_path(paths.project_dir)
    )
    _ClusterRunners.from_args(_workflow_class=workflow_class).run_stage()


if __name__ == "__main__":
    main()
