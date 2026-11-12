import argparse
import os
import shutil
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Self, ClassVar, Any

from cluster_utils import get_environment_default_log_level, init_logger, \
    SLURM_JOB_NAME_ENV_VAR, SLURM_TMP_DIR_ENV_VAR, PACKAGE_URL
from cluster_utils._config import ClusterConfig, WORKFLOW_SCRIPT_TOML_FIELD_NAME
from cluster_utils._paths import ComputePaths as CliComputePaths
from cluster_utils._paths import ProjectPaths as CliProjectPaths
from cluster_utils.utils.venv import VenvCreator, VenvPaths
from cluster_utils.data import ArrayJobData, LoginPaths, SlurmParams, \
    SlurmJobType, SlurmDependencies, SlurmDependency, ArrayJobInstanceParams, \
    SlurmJob, ComputePaths, ComputeNodePaths, RunPaths, AttemptPaths, \
    ProjectPaths
from cluster_utils.utils import EnumAction, RunnerStage, ArgParseable, \
    ON_CLUSTER, PythonPackage
from cluster_utils.workflow import FullWorkflow
from cluster_utils.workflow_utils import find_subclasses_in_script, ArgParser

logger = init_logger(Path(__file__).name)


@dataclass(frozen=True)
class _LoginRunner(ArgParser):
    """Abstract class that handles running the portion of a run that occurs
    in the background on a login node."""

    paths: LoginPaths
    job_name_to_slurm_params: dict[str, SlurmParams]

    full_workflow: ClassVar[type[FullWorkflow]]

    @staticmethod
    def parser_name() -> str:
        return "Login Runner"

    @staticmethod
    def parser_description() -> str:
        return ("Perform logic on login node of "
                "Digital Research Alliance of Canada cluster.")

    @staticmethod
    def static_argument_sources() -> list[type[ArgParseable]]:
        argument_sources: list[type[ArgParseable]] = [LoginPaths]
        for job in _LoginRunner.full_workflow.login_workflow().jobs():
            argument_sources.append(
                SlurmParams.create_subclass_from_job(job)
            )
        return argument_sources

    def run(self) -> bool:
        """Perform login portion of run.

        Returns
        -------
        Whether login tasks were run successfully.
        """

        workflow = self.full_workflow.login_workflow()

        logger.debug("Performing workflow pre-initialization...")
        if not workflow.pre_initialize(self.paths):
            return False
        logger.debug("Performing built-in initialization...")
        if not self.initialize():
            return False
        logger.debug("Performing workflow post-initialization...")
        if not workflow.post_initialize(self.paths):
            return False

        logger.debug("Performing workflow pre-compute job submission...")
        if not workflow.pre_job_submission(self.paths):
            return False
        logger.debug("Performing built-in compute job submission...")
        if not self.submit_compute_jobs():
            logger.warning(
                "One or more compute jobs failed, skipping post processing."
            )
            return False
        logger.debug("Performing workflow post-compute job submission...")
        if not workflow.post_job_submission(self.paths):
            return False

        logger.debug("Performing workflow pre-post-processing...")
        if not workflow.pre_post_process(self.paths):
            return False
        logger.debug("Performing built-in post-processing...")
        if not self.post_process():
            return False
        logger.debug("Performing workflow post-post-processing...")
        if not workflow.post_post_process(self.paths):
            return False

        return True

    def _build_package_wheel(self) -> bool:
        """Build wheel for this package, removing any existing wheels.

        Returns
        -------
        bool
            Whether wheel creation was successful.
        """

        # Delete previous instance if one exists
        if self.paths.run_paths.cluster_utils_wheel_dir.is_dir():
            shutil.rmtree(self.paths.run_paths.cluster_utils_wheel_dir)

        self.paths.run_paths.cluster_utils_wheel_dir.mkdir()
        VenvCreator.create_wheel(
            PACKAGE_URL,
            self.paths.run_paths.cluster_utils_wheel_dir
        )
        whl_file = self.paths.run_paths.cluster_utils_wheel
        return whl_file and whl_file.is_file()

    def _initialize_input_dir(self) -> bool:
        """Initialize input directory.

        Returns
        -------
        bool
            Whether input directory was successfully initialized.
        """

        logger.debug("Initializing input directory...")
        self.paths.run_paths.input_dir.mkdir(parents=True)

        logger.debug("Transferring inputs to input directory...")
        input_path = self.paths.run_paths.input_path
        if input_path is None:
            raise ValueError(
                "Input directory not initialized, input path required."
            )

        self.full_workflow.login_workflow().transfer_input_to_run(
            input_path,
            self.paths.run_paths,
        )

        logger.debug("Initializing run params directory...")
        self.paths.run_paths.params_dir.mkdir(parents=True)
        self.paths.project_paths.to_json(
            self.paths.run_paths.project_paths_json)
        self.paths.run_paths.to_json(self.paths.run_paths.run_paths_json)
        for name, params in self.job_name_to_slurm_params.items():
            params.to_json(
                self.paths.run_paths.build_slurm_params_json_path(name))

        logger.debug("Input directory initialized!")
        return True

    def initialize(self) -> bool:
        """Perform general initialization for a run.

        Returns
        -------
        Whether initialization was successful.
        """

        self.paths.initialize_run()
        if not self.paths.run_paths.input_dir.is_dir():
            if not self._initialize_input_dir():
                return False

        if not self._build_package_wheel():
            return False
        return True

    def submit_compute_jobs(self) -> bool:
        """Submit user-designed compute jobs.

        Returns
        -------
        bool
            Whether compute jobs completed successfully.
        """

        if len(self.full_workflow.login_workflow().jobs()) <= 0:
            logger.info("No jobs to submit!")
            return True

        logger.info(
            f"Performing attempt {self.paths.attempt_paths.attempt_index} "
            f"of run found at '{self.paths.run_paths.run_dir}'."
        )

        job_to_slurm_id: dict[type[SlurmJob], int | None] = {}
        for job in self.full_workflow.login_workflow().jobs():
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

        logger.debug(
            "Preparing array job submission for '%s' job.",
            job.job_name()
        )
        compute_job_args = job.compute_job_args()
        cli_project_paths = CliProjectPaths(self.paths.project_paths.project_dir)
        config = ClusterConfig.from_toml(cli_project_paths.cluster_config_toml)

        requirements_file = config.compute_environment.requirements_file
        venv = VenvCreator(
            VenvPaths(Path()),
            requirements=tuple(
                PythonPackage.from_requirements_txt(requirements_file)
            ) if (requirements_file and requirements_file.is_file())
            else tuple(),
        )
        wrap_args = [
            subprocess.list2cmdline([arg]) for arg in [
                "cd", f"${SLURM_TMP_DIR_ENV_VAR}",
                "&&", "module", "load", *config.compute_environment.modules,
                "&&", "virtualenv", "--no-download", f"${SLURM_TMP_DIR_ENV_VAR}/{CliComputePaths.VENV_NAME}",
                "&&", "source", f"${SLURM_TMP_DIR_ENV_VAR}/{CliComputePaths.VENV_NAME}/bin/activate",
                "&&", "pip", "install", "--no-index", "--upgrade", "pip",
                "&&", "pip", "install", "--no-index", self.paths.run_paths.cluster_utils_wheel, *[r.requirement_str for r in venv.requirements],
                "&&", "cluster-compute",
                "--project-dir",  self.paths.project_paths.project_dir,
                "--attempt-index", str(self.paths.attempt_paths.attempt_index),
                "--run-paths-json",  self.paths.run_paths.run_paths_json,
            ] + (compute_job_args if compute_job_args is not None else [])
        ]

        args = self.job_name_to_slurm_params[job.job_name()].build_array_job_command(
            self.paths,
            wrap_args,
            dependencies,
        )
        if args is None:
            logger.info(
                "No jobs to run for '%s', skipping array job submission!",
                job.job_name(),
            )
            return None

        if not ON_CLUSTER:
            logger.warning("Cannot run array job on non-cluster, skipping...")
            return None

        logger.info(
            "Waiting for '%s' array job to complete...",
            job.job_name(),
        )
        process = subprocess.run(
            args,
            capture_output=True,
            text=True,
        )

        job_id = int(process.stdout) if process.stdout else None
        if process.returncode == 0:
            logger.info("'%s' array jobs completed!", job.job_name())
        else:
            logger.warning(
                "One or more '%s' array jobs failed. Error code: %s",
                job.job_name(),
                process.returncode,
            )
            logger.debug("Job args: %s", args)
            logger.debug("stdout:\n%s",process.stdout)
            logger.debug("stderr:\n%s", process.stderr)

        return job_id

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

        paths = LoginPaths.from_custom_args(
            args,
            project_name=cls.full_workflow.project_name(),
        )

        job_name_to_inst = {}
        for job in cls.full_workflow.login_workflow().jobs():
            slurm_params_type = SlurmParams.create_subclass_from_job(job)
            if job.job_name() in job_name_to_inst:
                raise KeyError("Multiple SlurmJobs with same job_name.")

            # Use cached slurm params as fallbacks if present
            json_path = paths.run_paths.build_slurm_params_json_path(job.job_name())
            fallbacks: dict[str, Any] = asdict(
                SlurmParams.from_json(json_path)
            ) if json_path.is_file() else {}

            job_name_to_inst[job.job_name()] = slurm_params_type.from_args(
                args,
                **fallbacks
            )

        return cls(
            paths=paths,
            job_name_to_slurm_params=job_name_to_inst,
        )


@dataclass(frozen=True)
class _ComputeRunner(ArgParser):
    """Abstract class that handles running the portion of a run that occurs
    on a cluster's compute node."""

    paths: ComputePaths
    job_data: ArrayJobData

    full_workflow: ClassVar[type[FullWorkflow]]

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

    @classmethod
    def _get_current_job(cls) -> type[SlurmJob]:
        job_name = os.getenv(SLURM_JOB_NAME_ENV_VAR)
        if job_name is None:
            raise RuntimeError(
                f"Could not find '{SLURM_JOB_NAME_ENV_VAR}' in environment. "
                "Are you sure this is being run on a compute node?"
            )

        job_name_to_job = {
            j.job_name(): j
            for j in cls.full_workflow.login_workflow().jobs()
        }
        if job_name not in job_name_to_job:
            raise KeyError(
                f"Could not find SlurmJob with name '{job_name}'. "
                f"Jobs: {list(job_name_to_job.keys())}"
            )

        return job_name_to_job[job_name]

    def run(self) -> bool:
        """Perform a compute run."""

        compute_workflow = self.full_workflow.compute_workflow()
        job = self._get_current_job()

        logger.debug("Performing workflow pre-initialization...")
        if not compute_workflow.pre_initialize(self.paths):
            return False
        logger.debug("Performing job pre-initialization...")
        if not job.pre_initialize(self.paths):
            return False
        logger.debug("Performing built-in initialization...")
        if not self._initialize_file_structure():
            return False
        logger.debug("Performing workflow post-initialization...")
        if not compute_workflow.post_initialize(self.paths):
            return False
        logger.debug("Performing job post-initialization...")
        if not job.post_initialize(self.paths):
            return False

        logger.debug("Performing workflow pre-computation...")
        if not compute_workflow.pre_computation(self.paths):
            return False
        logger.debug("Performing job computations...")
        if not job.perform_computations(self.paths):
            return False
        logger.debug("Performing workflow post-computation...")
        if not compute_workflow.post_computation(self.paths):
            return False

        logger.debug("Performing workflow pre-post-process...")
        if not compute_workflow.pre_post_process(self.paths):
            return False
        logger.debug("Performing job pre-post-process...")
        if not job.pre_post_process(self.paths):
            return False
        logger.debug("Performing workflow post-post-process...")
        if not compute_workflow.post_post_process(self.paths):
            return False
        logger.debug("Performing job post-post-process...")
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

        # Validate that all inputs are now found on compute node
        if len(self.paths.compute_node_paths.inputs) != len(self.job_data.input_paths):
            raise RuntimeError(
                f"Expected {len(self.job_data.input_paths)} "
                f"inputs in compute input dir, "
                f"found {len(self.paths.compute_node_paths.inputs)}. "
                f"Expected inputs: "
                f"{[p.name for p in self.job_data.input_paths]}, "
                f"inputs found: "
                f"{[p.name for p in self.paths.compute_node_paths.inputs]}."
            )

        # Initialize output dir
        self.paths.compute_node_paths.output_dir.mkdir()
        return True

    @classmethod
    def from_custom_args(cls, args: argparse.Namespace, **kwargs) -> Self:
        if len(kwargs) > 0:
            raise ValueError(f"Unexpected kwargs: {kwargs}.")

        array_job_params = ArrayJobInstanceParams.from_args(args)
        run_paths: RunPaths = RunPaths.from_json(array_job_params.run_paths_json)
        login_paths = LoginPaths(
            project_paths=ProjectPaths.from_json(run_paths.project_paths_json),
            run_paths=run_paths,
            attempt_paths=AttemptPaths.from_attempt_index(
                run_paths.attempts_dir,
                array_job_params.attempt_index,
            )
        )

        job_data = ArrayJobData.from_json(
            ArrayJobData.build_json_path(
                login_paths.attempt_paths.get_array_job_data_dir_for_job(
                    cls._get_current_job()
                ),
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
    _stage: RunnerStage

    def run_stage(self) -> bool:
        """Perform stage of program.

        Returns
        -------
        Whether stage was run successfully.
        """

        # TODO: Find better solution for static class variable hacks
        match self._stage:
            case RunnerStage.LOGIN:
                logger.info("Running login stage...")
                _LoginRunner.full_workflow = self._workflow_class
                return _LoginRunner.from_args().run()
            case RunnerStage.COMPUTE:
                logger.info("Running compute stage...")
                _ComputeRunner.full_workflow = self._workflow_class
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
            type=RunnerStage,
            default=RunnerStage.LOGIN,
            action=EnumAction,
        )
        args, _ = parser.parse_known_args()

        return cls(_stage=args.runner_stage, **kwargs)


def _build_argument_parser() -> argparse.ArgumentParser:
    """Create argument parser for cluster runner.

    Returns
    -------
    argparse.ArgumentParser
        Created argument parser.
    """

    parser = argparse.ArgumentParser(
        description="Cluster Runner",
        add_help=False,
    )
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
    """Find user-defined FullWorkflow class definition in workflow script.

    Parameters
    ----------
    workflow_script
        Workflow script to find FullWorkflow class definition within.

    Returns
    -------
    type[FullWorkflow]
        User-defined FullWorkflow class definition from workflow script.
    """

    target_type: type = FullWorkflow
    if not workflow_script.is_file():
        raise FileNotFoundError(
            f"Could not find workflow script at '{workflow_script}'."
            f"Update config TOML `{WORKFLOW_SCRIPT_TOML_FIELD_NAME}` "
            f"to point to your workflow script."
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


def _find_user_workflow_class_from_args(
        arguments: Iterable[str] | None = None,
) -> type[FullWorkflow]:
    """Get the user-defined FullWorkflow class definition using config TOML.

    Parameters
    ----------
    arguments
        Arguments to parse.

    Returns
    -------
    type[FullWorkflow]
        User-defined FullWorkflow class definition.
    """

    args, _ = _build_argument_parser().parse_known_args(arguments)
    paths = CliProjectPaths(args.project_dir)
    if not paths.cluster_config_toml.is_file():
        raise FileNotFoundError(
            f"Could not find config TOML at '{paths.cluster_config_toml}'. "
            "Have you run `cluster-init` on this project?"
        )
    config = ClusterConfig.from_toml(paths.cluster_config_toml)

    return _find_user_workflow_class(
        config.global_config.get_workflow_script_path(paths.project_dir)
    )


def get_argument_sources_for_stage(
        stage: RunnerStage = RunnerStage.LOGIN,
        arguments: Iterable[str] | None = None,
) -> list[type[ArgParseable]]:
    """Get classes of command line argument sources for the given stage.

    Parameters
    ----------
    stage
        Stage to get argument sources for.
    arguments
        Arguments to parse when finding workflow class.

    Returns
    -------
    list[type[ArgParseable]]
        Argument sources for the given stage.
    """

    workflow_class = _find_user_workflow_class_from_args(arguments)
    match stage:
        case RunnerStage.LOGIN:
            _LoginRunner.full_workflow = workflow_class
            return _LoginRunner.static_argument_sources()
        case RunnerStage.COMPUTE:
            _ComputeRunner.full_workflow = workflow_class
            return _ComputeRunner.static_argument_sources()
        case _:
            raise ValueError(f"Unsupported runner stage: {stage}.")


# TODO: Maybe remove main function and split into separate modules
#  since we can call any class/function we want from cli?
def main(arguments: Iterable[str] | None = None) -> None:
    """Perform a stage of a run on a cluster.

    Parameters
    ----------
    arguments
        (Optional) When provided, uses given args instead of command line args.
    """

    args, _ = _build_argument_parser().parse_known_args(arguments)
    logger.setLevel(args.log_level)
    logger.debug("Arguments parsed!")

    if not _ClusterRunners.from_args(
        _workflow_class=_find_user_workflow_class_from_args(arguments),
    ).run_stage():
        logger.warning(
            "Something went wrong during running of stage."
            "See logs for details."
        )
        exit(1)


if __name__ == "__main__":
    main()
