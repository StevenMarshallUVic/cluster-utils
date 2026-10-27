import argparse
import logging
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self, ClassVar

from cluster_utils import get_environment_default_log_level, init_logger
from cluster_utils._config import ClusterConfig
from cluster_utils._paths import ProjectPaths
from cluster_utils.data import ArrayJobData, Paths, SlurmParams, \
    SlurmJobType, SlurmDependencies, SlurmDependency, ArrayJobInstanceParams
from cluster_utils.utils import EnumAction, _RunnerStage, \
    run_subprocess_command, ArgParseable
from cluster_utils.workflow_utils import find_subclasses_in_script, ArgParser
from cluster_utils.workflow import FullWorkflow, LoginWorkflow, ComputeWorkflow, \
    SlurmJob

logger = init_logger(Path(__file__).name)


class _LoginParams(ArgParseable):
    account: str

    @classmethod
    def add_arguments(
            cls,
            parser: argparse.ArgumentParser,
            group: argparse._ArgumentGroup | None = None,
            prefix: str | None = None,
    ) -> None:
        group = group if group is not None else parser.add_argument_group(
            "Login Parameters",
            "Parameters used for login portion of Slurm job."
        )


@dataclass(frozen=True)
class _LoginRunner(ArgParser):
    """Abstract class that handles running the portion of a run that occurs
    in the background on a login node."""

    login_params: _LoginParams
    paths: Paths

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
        static_argument_sources: list[type[ArgParseable]] = [_LoginParams, Paths]
        for job in _LoginRunner.workflow().login_workflow.jobs():
            slurm_params_type: type[ArgParseable] = type(
                job.job_name().title(),
                (SlurmParams,),
                {"job": job}
            )
            static_argument_sources.append(slurm_params_type)
        return static_argument_sources

    def run(self) -> bool:
        """Perform login portion of run.

        Returns
        -------
        Whether login tasks were run successfully.
        """

        if not self.workflow().login_workflow.pre_initialize():
            return False
        if not self.initialize():
            return False
        if not self.workflow().login_workflow.post_initialize():
            return False

        if not self.workflow().login_workflow.pre_job_submission():
            return False
        if not self.submit_compute_jobs():
            logger.warning(
                "One or more compute jobs failed, skipping post processing."
            )
            return False
        if not self.workflow().login_workflow.post_job_submission():
            return False

        if not self.workflow().login_workflow.pre_post_process():
            return False
        if not self.post_process():
            return False
        if not self.workflow().login_workflow.post_post_process():
            return False

        return True

    def initialize(self) -> bool:
        """Perform general initialization for a run.

        Returns
        -------
        Whether initialization was successful.
        """

        # TODO: Move run initialization logic from Paths class to here
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

        job_to_slurm_id: dict[type[SlurmJob], int] = {}
        for job in self.workflow().login_workflow.jobs():
            depends: list[SlurmDependency] = []
            for depend_job, depend_type in job.job_dependencies().items():
                if depend_job not in job_to_slurm_id:
                    raise RuntimeError(
                        f"Trying to submit job '{job.job_name()}' "
                        f"before dependency '{depend_job.job_name()}'."
                    )
                depends.append(SlurmDependency(
                    depend_type,
                    tuple([job_to_slurm_id[depend_job]]),
                ))
            dependencies = SlurmDependencies(
                dependencies=tuple(depends),
                require_all_dependencies=job.require_all_dependencies(),
            ) if len(depends) > 0 else None

            match job.job_type():
                case SlurmJobType.ARRAY:
                    if not self.submit_array_job(
                        job,
                        dependencies=dependencies,
                    ):
                        logger.warning(
                            "Array job submission failed for '%s'.",
                            job.job_type,
                        )
                        return False
                case SlurmJobType.SINGLE:
                    if not self.submit_single_job(job):
                        logger.warning(
                            "Single job submission failed for '%s'.",
                            job.job_type,
                        )
                        return False
                case _:
                    raise NotImplementedError(
                        f"Unsupported slurm job type: '{job.job_type}'."
                    )
        return True

    def submit_array_job(
            self,
            job: type[SlurmJob],
            extra_job_wrap_args: list[str] | None = None,
            dependencies: SlurmDependencies | None = None,
    ) -> bool:
        """Submit a slurm array job to handle the compute portion of the job."""

        wrap_args = [
            subprocess.list2cmdline([arg]) for arg in [
                # TODO: Confirm this works
                f"cd {self.paths.project_dir} && cluster-run",
                "--paths-json",  self.paths.attempt_paths_json,
                "--project-dir",  self.paths.project_dir,
                "--python-module-path", self.paths.runner_module_path,
                "--runner-stage",  _RunnerStage.COMPUTE.name,
            ] + (extra_job_wrap_args if extra_job_wrap_args is not None else [])
            + (["--debug"] if logger.isEnabledFor(logging.DEBUG) else [])
        ]

        # TODO: Figure out better system for initializing
        args = SlurmParams.from_args_job_fallbacks().build_array_job_command(
            job,
            self.login_params.account,
            wrap_args,
            dependencies,
        )
        if args is None:
            logger.info(
                f"No jobs to run for {job.job_name}, "
                f"skipping array job submission!"
            )
            return True

        logger.info(f"Waiting for {job.job_name} slurm array job to complete...")
        success = run_subprocess_command(args, logger=logger)
        # success = run_subprocess_command(
        #     args=["bash"] + wrap_args,
        #     logger=logger,
        # )

        if success:
            logger.info(f"{job.job_name} slurm jobs completed!")
        else:
            logger.warning(f"One or more {job.job_name} slurm jobs failed.")
        return success

    def submit_single_job(self, job: SlurmJob) -> bool:
        """Submit a single slurm job to handle the compute portion of the job.
        """
        raise NotImplementedError()

    def post_process(self) -> bool:
        """Virtual method for performing post-processing after the compute
        stage completes.

        Returns
        -------
        Whether post-processing was successful.
        """
        return True

    @classmethod
    def from_custom_args(cls, args: argparse.Namespace, **kwargs) -> Self:
        if len(kwargs) > 0:
            raise ValueError(f"Unexpected keyword arguments: {kwargs}.")

        return cls(
            login_params=_LoginParams.from_args(args),
            paths=Paths.from_custom_args(args, cls.workflow().project_name),
        )


@dataclass(frozen=True)
class _ComputeRunner(ArgParser):
    """Abstract class that handles running the portion of a run that occurs
    on a cluster's compute node."""

    compute_dir: Path
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

    @property
    def compute_input_dir(self) -> Path:
        """Path to input directory on the compute node."""
        return self.compute_dir / "input"

    @property
    def compute_output_dir(self) -> Path:
        """Path to output directory on the compute node."""
        return self.compute_dir / "output"

    def run(self) -> bool:
        """Perform a compute run."""

        if not self._initialize_file_structure():
            return False

        return self.perform_computations()

    def _initialize_file_structure(self) -> bool:
        """Initialize compute file structure.

        Returns
        -------
        Whether initialization was successful.
        """

        logger.debug("Initializing compute node file structure...")
        if not self.compute_dir.is_dir():
            raise NotADirectoryError(
                f"Could not find compute dir at '{self.compute_dir}'."
            )

        # Initialize input dir
        self.compute_input_dir.mkdir()
        for path in self.job_data.input_paths:
            shutil.copy2(path, self.compute_input_dir)

        # Initialize output dir
        self.compute_output_dir.mkdir()

        # Perform custom initialization
        return self.initialize_compute_file_structure()

    def initialize_compute_file_structure(self) -> bool:
        """Virtual method to allow for performing additional initialization.

        Returns
        -------
        Whether initialization was successful.
        """
        return True

    def perform_computations(self) -> bool:
        """Abstract method for performing the compute logic on the compute node.

        Returns
        -------
        Whether compute logic was performed successful.
        """
        return True

    def call_function_on_inputs(
            self,
            func: Callable[[Path], Any],
            log_name: str | None = None
    ) -> None:
        """Helper method for calling a function on all inputs for compute job.

        Parameters
        ----------
        func
            Function to call for each input. Path to input file will be passed
            to the function.
        log_name
            Optional name to use in log message. Logging skipped if not
            provided.
        """

        input_files: list[Path] = sorted(self.compute_input_dir.iterdir())
        for input_index, input_file in enumerate(input_files, start=1):
            if log_name:
                logger.info(f"Performing {log_name} on {input_file.stem} "
                            f"({input_index}/{len(input_files)})...")
            func(input_file)

    @classmethod
    def from_custom_args(cls, args: argparse.Namespace, **kwargs) -> Self:
        if len(kwargs) > 0:
            raise ValueError(f"Unexpected kwargs: {kwargs}.")

        array_job_params = ArrayJobInstanceParams.from_args(args)
        paths = Paths.from_json(array_job_params.paths_json)
        job_data = ArrayJobData.from_json(
            ArrayJobData.build_json_path(
                paths.array_job_data_dir,
                array_job_params.array_job_index,
            )
        )
        return cls(
            compute_dir=array_job_params.compute_dir,
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
                return _ComputeRunner.from_args().run()
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
