"""Classes for storing data used in jobs run on a cluster."""

from __future__ import annotations
import argparse
import os
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import auto, StrEnum
from math import ceil
from pathlib import Path
from typing import Any, ClassVar, cast, Self

from cluster_utils import init_logger, get_project_dir
from cluster_utils.utils import ArgParseable, JsonSerializable

logger = init_logger(Path(__file__).name)

SCRATCH_ENV_VAR = "SCRATCH"

PATHS_JSON_NAME = "paths.json"
SLURM_PARAMS_JSON_NAME = "slurm_params.json"


class SlurmJobType(StrEnum):
    SINGLE = auto()
    """Run the job as a single job."""
    ARRAY = auto()
    """Run the job as an array job."""


class SlurmDependencyType(StrEnum):
    AFTER = "after"
    """After the specified jobs start or are cancelled 
    and 'time' in minutes from job start or cancellation happens, 
    this job can begin execution. If no 'time' is given 
    then there is no delay after start or cancellation."""
    AFTER_ANY = "afterany"
    """This job can begin execution after the specified jobs have terminated. 
    This is the default dependency type."""
    AFTER_BURST_BUFFER = "afterburstbuffer"
    """This job can begin execution after the specified jobs have terminated 
    and any associated burst buffer stage out operations have completed."""
    AFTER_CORR = "aftercorr"
    """A task of this job array can begin execution 
    after the corresponding task ID in the specified job 
    has completed successfully (ran to completion with an exit code of zero). 
    If the specified job is not an array, this is treated the same as afterok.
    """
    AFTER_NOT_OK = "afternotok"
    """This job can begin execution after the specified jobs 
    have terminated in some failed state 
    (non-zero exit code, node failure, timed out, etc). 
    This job must be submitted while the specified job is still active 
    or within MinJobAge seconds after the specified job has ended. 
    If the dependent job ID is not found and is on the same cluster 
    as the job submission, the job is rejected. If the dependent job ID 
    is not found and is on a different cluster from the job submission, 
    the dependency is marked as failed."""
    AFTER_OK = "afterok"
    """This job can begin execution after the specified jobs have 
    successfully executed (ran to completion with an exit code of zero). 
    This job must be submitted while the specified job is still active 
    or within MinJobAge seconds after the specified job has ended. 
    If the dependent job ID is not found and is on the same cluster 
    as the job submission, the job is rejected. If the dependent job ID 
    is not found and is on a different cluster from the job submission, 
    the dependency is marked as failed."""
    SINGLETON = "singleton"
    """This job can begin execution after any previously launched jobs 
    sharing the same job name and user have terminated. 
    In other words, only one job by that name and owned by that user 
    can be running or suspended at any point in time."""


# noinspection incorrect-docstring,shadowing-builtins
def add_argument_to_parser(
        parser: argparse.ArgumentParser,
        group: argparse._ArgumentGroup | None = None,
        prefix: str | None = None,
        *name_or_flags,
        **kwargs,
 ) -> None:
    """Wrapper around argparse `add_argument()` method with support for
    the following optional functionality:
    - Add arguments to group
    - Add prefix to each name_or_flag (as long as flag starts with '--')

    For documentation of parameters not listed below,
    see `argparse.ArgumentParser.add_arguments()` method

    Parameters
    ----------
    parser
        Parser to add arguments to.
    group
        Optional argument group to add arguments to.
    prefix
        (Optional) Prefix to prepend to flags.
    """

    target = group if group is not None else parser
    if prefix:
        name_or_flags = [
            n[:2] + prefix + "-" + n[2:] if n.startswith("--")
            else prefix + "-" + n
            for n in name_or_flags
            if (n.startswith("--") or not n.startswith("-"))
        ]
    target.add_argument(
        *name_or_flags,
        **kwargs
    )


@dataclass(frozen=True)
class SlurmDependency:
    """Dependency for a Slurm job.

    Attributes
    ----------
    dependency_type
        What type of dependency to require.
        See `SlurmDependencyType` for explanations of types.
    job_ids
        Which job IDs this dependency applies to.
    """

    dependency_type: SlurmDependencyType
    job_ids: tuple[int, ...] | None

    def __post_init__(self):
        if (self.dependency_type == SlurmDependencyType.SINGLETON
                and self.job_ids is not None):
            raise ValueError(
                "`job_ids` not supported for singleton slurm dependency."
            )
        if (self.dependency_type != SlurmDependencyType.SINGLETON
                and self.job_ids is None):
            raise ValueError(
                "`job_ids` required for non-singleton slurm dependency."
            )

    def as_flag_value(self) -> str:
        if self.dependency_type == SlurmDependencyType.SINGLETON:
            return self.dependency_type

        if self.job_ids is None:
            raise ValueError(
                "`job_ids` required for non-singleton slurm dependency."
            )
        return (
            f"{self.dependency_type}:{':'.join([str(j) for j in self.job_ids])}"
        )


@dataclass(frozen=True)
class SlurmDependencies:
    """Dependencies for a Slurm job.

    Attributes
    ----------
    dependencies
        Dependencies.
    require_all_dependencies
        When true, all dependencies must be satisfied.
        Otherwise, any dependency may be satisfied.
    """

    dependencies: tuple[SlurmDependency, ...]
    require_all_dependencies: bool = True

    def as_flag_value(self) -> str:
        """Create slurm dependency flag."""
        sep = "," if self.require_all_dependencies else "?"
        return sep.join([d.as_flag_value() for d in self.dependencies])


@dataclass
class SlurmJob(ABC):
    # TODO: Turn into class decorator?
    def __new__(cls, *args, **kwargs):
        raise TypeError(
            f"Class '{cls.__name__}' is static and cannot be instantiated."
        )

    @staticmethod
    @abstractmethod
    def job_name() -> str:
        """Name of Slurm job. Will be shown in slurm job displays."""
        pass

    @staticmethod
    @abstractmethod
    def default_batch_size() -> int:
        """Default number of inputs to batch together if an override is not
        provided on the command line.
        """
        pass

    @staticmethod
    @abstractmethod
    def default_memory() -> str:
        """Default RAM to allocate if an override is not
        provided on the command line.
        """
        pass

    @staticmethod
    @abstractmethod
    def default_time() -> str:
        """Default runtime to allocate if an override is not
        provided on the command line.
        """
        pass

    @staticmethod
    @abstractmethod
    def default_cpus_per_task() -> int:
        """Default number of CPUs to allocate if an override is not
        provided on the command line.
        """
        return 1

    @staticmethod
    @abstractmethod
    def gpus() -> str | None:
        """Optional number and type of GPUs to allocate."""
        return None

    @staticmethod
    @abstractmethod
    def job_type() -> SlurmJobType:
        """Type of slurm job to submit."""
        return SlurmJobType.ARRAY

    @staticmethod
    @abstractmethod
    def arg_prefix() -> str | None:
        """Optional prefix to add to command line arguments for slurm params.

        Helpful when defining more than one SlurmJob in project, allowing
        assignment of custom slurm params to each job type from command line.
        """
        return None

    @staticmethod
    @abstractmethod
    def job_dependencies() -> dict[type[SlurmJob], SlurmDependencyType]:
        """Mapping between jobs that this job depends on and the nature
        of the dependency.
        """
        return {}

    @staticmethod
    @abstractmethod
    def require_all_dependencies() -> bool:
        """When true, all dependencies must be satisfied.
        Otherwise, any dependency may be satisfied.
        """
        return True

    @staticmethod
    @abstractmethod
    def get_missing_output_input_files(
            run_paths: RunPaths,
    ) -> list[Path]:
        """Identify all input files that do not have a corresponding output
        file.

        Parameters
        ----------
        run_paths
            Path for the run.

        Returns
        -------
        list[Path]
            Paths to input files that need to be run through this job.
        """
        return run_paths.get_missing_output_input_files()


@dataclass(frozen=True)
class SlurmParams(ArgParseable, JsonSerializable):
    """Base class for storing slurm parameters data.

    Attributes
    ----------
    batch_size
        How many inputs to batch into each slurm job.
    cpus_per_task
        How many CPUs to allocate for each slurm job.
    memory
        Amount of memory to allocate for each slurm job.
    time
        Amount of time to allocate for each slurm job.
    """

    DEFAULT_CPUS_PER_TASK = 1

    batch_size: int
    memory: str
    time: str
    cpus_per_task: int = DEFAULT_CPUS_PER_TASK
    gpus: str | None = None

    job: ClassVar[type[SlurmJob]]

    def build_array_job_command(
            self,
            paths: Paths,
            wrap_args: list[str],
            dependencies: SlurmDependencies | None = None,
    ) -> list[str] | None:
        """Submit a slurm array job to handle the compute portion of the job."""

        remaining_input_files = self.job.get_missing_output_input_files(
            paths.run_paths,
        )
        if len(remaining_input_files) <= 0:
            return None

        ArrayJobData.write_array_job_data(
            paths.attempt_paths.get_array_job_data_dir_for_job(self.job),
            remaining_input_files,
            self.batch_size,
        )
        max_array_index = ArrayJobData.find_greatest_array_job_index(
            paths.attempt_paths.get_array_job_data_dir_for_job(self.job),
        )
        if max_array_index is None:
            return None

        log_file = paths.get_job_log_file_path(self.job)
        args = [
            "sbatch",
            f"--job-name={self.job.job_name()}",
            f"--account={paths.project_paths.account}",
            f"--cpus-per-task={self.cpus_per_task}",
            f"--mem={self.memory}",
            f"--time={self.time}",
            f"--array=0-{max_array_index}",
            f"--output={log_file}",
            f"--error={log_file}",
            f"--wrap={' '.join(wrap_args)}",
            "--wait",
        ]
        if self.gpus is not None:
            args.append(f"--gpus={self.gpus}")
        if dependencies:
            # TODO: Test that this works
            args.append(f"--dependency={dependencies.as_flag_value()}")

        return args

    @classmethod
    def create_subclass_from_job(cls, job: type[SlurmJob]) -> type[SlurmParams]:
        return cast(
            type[SlurmParams],
            type(
                job.job_name().title(),
                (cls,),
                {"job": job}
            )
        )

    @classmethod
    def add_arguments(
            cls,
            parser: argparse.ArgumentParser,
            group: argparse._ArgumentGroup | None = None,
            prefix: str | None = None,
    ) -> None:
        group = group or parser.add_argument_group(
            "Slurm Parameters",
            "Parameters used for Slurm job submission."
        )
        add_argument_to_parser(
            parser,
            group,
            prefix,
            "--batch-size", "--batch",
            dest="batch_size",
            help="(Optional) How many inputs to batch into each slurm job. "
                 "When not supplied, uses default batch size.",
            type=int,
        )
        add_argument_to_parser(
            parser,
            group,
            prefix,
            "--cpus-per-task", "--cpus",
            dest="cpus_per_task",
            help="(Optional) How many CPUs to allocate for each slurm job. "
                 "When not supplied, uses default of "
                 f"{cls.DEFAULT_CPUS_PER_TASK}.",
            type=int,
            default=cls.DEFAULT_CPUS_PER_TASK,
        )
        add_argument_to_parser(
            parser,
            group,
            prefix,
            "--memory", "--mem",
            dest="memory",
            help="(Optional) Amount of memory to allocate for each slurm job. "
                 "When not supplied, uses default memory.",
            type=str,
        )
        add_argument_to_parser(
            parser,
            group,
            prefix,
            "--time",
            dest="time",
            help="(Optional) Amount of time to allocate for each slurm job. "
                 "When not supplied, uses default time.",
            type=str,
        )

    @classmethod
    def from_args(
            cls,
            args: argparse.Namespace,
            **fallbacks: Any,
    ):
        return super().from_args(
            args,
            batch_size=cls.job.default_batch_size(),
            memory=cls.job.default_memory(),
            time=cls.job.default_time(),
            cpus_per_task=cls.job.default_cpus_per_task(),
            gpus=cls.job.gpus(),
        )


@dataclass(frozen=True)
class ProjectPaths(ArgParseable, JsonSerializable):
    """

    Attributes
    ----------
    project_name
        Name of the project.
    project_dir
        Path to root directory of project.
    scratch_dir
        Path to root directory of scratch file system for a user.
    """

    account: str
    project_name: str
    project_dir: Path
    scratch_dir: Path

    ACCOUNT_TXT_NAME = ".account.txt"

    # TODO: Confirm this can be removed
    # @property
    # @abstractmethod
    # def runner_module_path(self) -> str:
    #     """Abstract property for specifying the module path to the runner
    #     script."""
    #     pass

    @property
    def account_file(self):
        """Default path to the account file for this project."""
        return self.construct_account_file_path(self.project_dir)

    @property
    def src_dir(self) -> Path:
        """Source directory of project."""
        return self.project_dir / "src"

    # TODO: Confirm this can be removed
    @property
    def cluster_compute_shell_script(self) -> Path:
        """Path to shell script for initializing environment on compute node."""
        return self.src_dir / "compute.sh"

    @property
    def scratch_project_dir(self) -> Path:
        """Root directory where project files will be saved on the scratch file
        system."""
        return self.scratch_dir / self.project_name

    @property
    def runs_root_dir(self) -> Path:
        """Root directory where runs will be saved."""
        return self.scratch_project_dir / "runs"

    @classmethod
    def construct_account_file_path(cls, project_sir: Path) -> Path:
        return project_sir / cls.ACCOUNT_TXT_NAME

    @staticmethod
    def read_account_from_file(account_file: Path) -> str | None:
        """Parse an account from a plain-text file containing the account.

        Parameters
        ----------
        account_file
            Path to a plain-text file containing an account.

        Returns
        -------
        str | None
            The account if the file exists, or None if not.
        """

        if not account_file.is_file():
            return None

        account = open(account_file).read().strip()
        return account

    @classmethod
    def add_arguments(
            cls,
            parser: argparse.ArgumentParser,
            group: argparse._ArgumentGroup | None = None,
            prefix: str | None = None,
    ) -> None:
        add_argument_to_parser(
            parser,
            group,
            prefix,
            "--account",
            help=f"(Optional) Digital Research Alliance of Canada account to "
                 f"charge usage to. "
                 f"When not supplied, attempts to find value in account file.",
            type=str,
        )
        add_argument_to_parser(
            parser,
            group,
            prefix,
            "--project-dir",
            dest="project_dir",
            help="(Optional) Path to project directory. "
                 "When not supplied, inferred from relative file structure.",
            type=Path,
            default=get_project_dir(),
        )
        add_argument_to_parser(
            parser,
            group,
            prefix,
            "--scratch-dir",
            dest="scratch_dir",
            help="(Optional) Path to scratch directory on cluster. "
                 "When not supplied, retrieved from environment.",
            type=Path,
            default=os.getenv(SCRATCH_ENV_VAR),
        )

    @classmethod
    def from_custom_args(
            cls,
            args: argparse.Namespace,
            **fallbacks: Any,
    ):
        account = getattr(args, "account", None)
        if not account:
            project_dir = getattr(args, "project_dir")
            account = cls.read_account_from_file(
                cls.construct_account_file_path(project_dir)
            )
            if not account:
                raise RuntimeError(
                    "Account file not found. "
                    "'--account' flag must be provided."
                )

        if not args.scratch_dir:
            raise argparse.ArgumentError(
                None,
                f"Could not find '{SCRATCH_ENV_VAR}' in environment. "
                "Must provide '--scratch-dir' when using '--input-path'."
            )

        return cls.from_args(args, account=account, **fallbacks)

@dataclass(frozen=True)
class RunPaths(ArgParseable, JsonSerializable):
    """

    Attributes
    ----------
    run_name
        Name of the current run.
    run_dir
        Path to root directory of the current run.
    input_path
        Path to input to perform run on.
    """

    run_name: str
    run_dir: Path
    input_path: Path | None = None

    @property
    def input_dir(self) -> Path:
        """Directory containing input files for the current run."""
        return self.run_dir / "input"

    @property
    def output_dir(self) -> Path:
        """Directory where output for the current run will be saved."""
        return self.run_dir / "output"

    @property
    def results_dir(self) -> Path:
        """Directory where results for the current run will be saved."""
        return self.run_dir / "results"

    @property
    def params_dir(self) -> Path:
        """Directory where parameters for the current run will be saved."""
        return self.run_dir / ".params"

    @property
    def paths_json(self) -> Path:
        """JSON file to write path data for the current run to."""
        return self.params_dir / PATHS_JSON_NAME

    @property
    def slurm_params_json(self) -> Path:
        """JSON file to write slurm parameters for the current run to."""
        return self.params_dir / SLURM_PARAMS_JSON_NAME

    @property
    def attempts_dir(self) -> Path:
        """Root directory where attempts for the current run will be saved."""
        return self.run_dir / "attempts"

    def initialize_run_dir(self) -> None:
        """Initialize run directory."""
        self.run_dir.mkdir(parents=True, exist_ok=True)

    def get_missing_output_input_files(
            self,
            input_dir: Path | None = None,
            output_dir: Path | None = None,
            output_name_suffix: str | None = None,
            output_file_extension: str | None = None,
    ) -> list[Path]:
        """Get paths to input files that have not been processed yet.

        Parameters
        ----------
        input_dir
            (Optional) Path to input directory.
            When not supplied, defaults to root input directory for the run.
        output_dir
            (Optional) Path to output directory.
            When not supplied, defaults to root output directory for the run.
        output_name_suffix
            (Optional) Suffix at the end of an output file's name,
            but before the first file extension, if any.
        output_file_extension
            (Optional) Extension of output files.
            Treats outputs as directories if None (default).

        Returns
        -------
        list[Path]
            Paths to input files that do not currently have results.
        """

        if input_dir is None:
            input_dir = self.input_dir
        if output_dir is None:
            output_dir = self.output_dir

        completed_ids = list()
        if output_dir.is_dir():
            for path in sorted(output_dir.iterdir()):
                if output_file_extension:
                    if not path.is_file():
                        continue

                    path_id = path.stem \
                        if len(path.suffixes) == 0 \
                        else path.name.split(path.suffixes[0])[0]
                    if (output_name_suffix
                            and not path_id.endswith(output_name_suffix)):
                        continue

                    file_extension = path.name.removeprefix(path_id)
                    if file_extension != output_file_extension:
                        continue

                    completed_ids.append(path_id)
                else:
                    if not path.is_dir():
                        continue

                    if (output_name_suffix
                            and not path.name.endswith(output_name_suffix)):
                        continue

                    completed_ids.append(path.stem)

        incomplete_paths = []
        for input_path in sorted(input_dir.iterdir()):
            input_id = input_path.stem \
                if len(input_path.suffixes) == 0 \
                else input_path.name.split(input_path.suffixes[0])[0]

            if input_id not in completed_ids:
                incomplete_paths.append(input_path)
        return sorted(incomplete_paths)

    def initialize_input_dir(self) -> None:
        """Create input directory and populate with input."""

        if self.input_dir.is_dir():
            return

        logger.debug("Initializing input directory...")
        self.input_dir.mkdir(parents=True)
        logger.debug("Transferring inputs to input directory...")
        self.transfer_input_to_run(self.input_path, self.input_dir)

    def initialize_output_dir(self) -> None:
        """Create output directory."""

        logger.debug("Initializing output directory...")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def generate_run_name(
            runs_root_dir: Path,
            input_path: Path,
            custom_run_name: str | None = None
    ) -> str:
        """Generate unique run name.
        Appends the current datetime to the generated run name if a run with
        that name already exists.

        Parameters
        ----------
        runs_root_dir
            Root directory where runs are saved.
        input_path
            Path to input for this run.
        custom_run_name
            Custom name to use for run.

        Returns
        -------
        str
            Unique run name.

        Raises
        ------
        IsADirectoryError
            If run directory with datetime appended already exists.
        """

        run_name = input_path.stem \
            if custom_run_name is None else custom_run_name
        run_dir = runs_root_dir / run_name
        if run_dir.is_dir():
            logger.warning(f"Run directory already exists at '{run_dir}'. "
                           f"Adding datetime to run name.")
            run_name = f"{run_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            run_dir = runs_root_dir / run_name
            if run_dir.is_dir():
                raise IsADirectoryError(
                    f"Run directory already exists at '{run_dir}'."
                )

        return run_name

    @classmethod
    def add_arguments(
            cls,
            parser: argparse.ArgumentParser,
            group: argparse._ArgumentGroup | None = None,
            prefix: str | None = None,
    ) -> None:
        group = group or parser.add_argument_group(
            "Run Paths",
            "Paths for a run.",
        )
        input_or_run_group = group.add_mutually_exclusive_group(required=True)
        add_argument_to_parser(
            parser,
            input_or_run_group,
            prefix,
            "-i", "--input-path",
            dest="input_path",
            help="Path to input(s). "
                 "See README.md for explanation of valid inputs.",
            type=Path,
        )
        add_argument_to_parser(
            parser,
            input_or_run_group,
            prefix,
            "-r", "--run-dir",
            dest="run_dir",
            help="Path to directory where previous run was created. "
                 "Allows performing multiple attempts for one input dataset.",
            type=Path,
        )
        add_argument_to_parser(
            parser,
            group,
            prefix,
            "--run-name",
            dest="run_name",
            help="(Optional) Custom name to use for new run. "
                 "When not supplied, infers name from input. "
                 "Only valid when '--input-path' is supplied.",
            type=str,
        )

    @classmethod
    def from_previous_run_dir(
            cls,
            args: argparse.Namespace,
            run_dir: Path,
            **fallbacks: Any
    ):
        """Create instance populated using data from a previous run.

        Parameters
        ----------
        args
            Command line arguments to extract data from.
        run_dir
            Path to directory of run to extract data from.
        fallbacks
            Keyword arguments of fallbacks to use if arguments are not provided.
        """

        run_dir = run_dir.resolve()
        fallbacks["run_name"] = run_dir.stem

        arg_parseable: ArgParseable = super()
        return arg_parseable.from_args(
            args,
            **fallbacks,
        )

    @classmethod
    def from_input(
            cls,
            args: argparse.Namespace,
            input_path: Path,
            runs_root_dir: Path,
            **fallbacks: Any,
    ):
        """Create instance populated using data from an input path.

        Parameters
        ----------
        args
            Command line arguments to extract data from.
        input_path
            Path to input to use for run creation.
        runs_root_dir
            Root directory where data for runs are stored.
        fallbacks
            Keyword arguments of fallbacks to use if arguments are not provided.
        """

        run_name = cls.generate_run_name(
            runs_root_dir,
            input_path,
            getattr(args, "run_name", None),
        )
        args.run_name = run_name
        fallbacks["run_name"] = run_name
        fallbacks["run_dir"] = runs_root_dir / run_name

        arg_parseable: ArgParseable = super()
        return arg_parseable.from_args(
            args,
            **fallbacks,
        )

    @classmethod
    def from_custom_args(
            cls,
            args: argparse.Namespace,
            runs_root_dir: Path,
            **fallbacks: Any,
    ):
        run_dir: Path | None = getattr(args, "run_dir", None)
        input_path: Path | None = getattr(args, "input_path", None)

        if (run_dir is None) == (input_path is None):
            raise argparse.ArgumentError(
                None,
                "Must supply exactly one of '--run-dir' or '--input-path'."
            )

        if run_dir is not None:
            if args.run_name:
                raise argparse.ArgumentError(
                    None,
                    "Cannot use '--run-name' when '--run-dir' is supplied."
                )
            if not run_dir.is_dir():
                raise argparse.ArgumentError(
                    None,
                    "Path passed with '--run-dir' must be a path to a "
                    "run that was already created. "
                    "Use '--input-path' to create run."
                )
            return cls.from_previous_run_dir(args, run_dir, **fallbacks)

        if input_path is not None:
            return cls.from_input(args, input_path, runs_root_dir, **fallbacks)

        raise ValueError(
            "Unexpected values for command line arguments. "
            f"'run-dir': {run_dir}, 'input-path': {input_path}."
        )


@dataclass(frozen=True)
class AttemptPaths:
    """Paths for a run attempt.

    Attributes
    ----------
    attempt_index
        1-based index of the current attempt.
    attempt_dir
        Directory of current attempt.
    """

    attempt_index: int
    attempt_dir: Path

    ATTEMPT_DIR_PREFIX = "attempt_"

    @property
    def logs_dir(self) -> Path:
        """Directory where log files will be written to for this attempt."""
        return self.attempt_dir / "logs"

    @property
    def login_background_log_file(self) -> Path:
        """Log file where background logging will be written to."""
        return self.logs_dir / f"{self.project_name}-login.log"

    @property
    def compute_log_file(self) -> Path:
        """Log file where compute logging will be written to."""
        return self.logs_dir / f"{self.project_name}-compute-%A_%a.log"

    @property
    def array_job_data_root_dir(self) -> Path:
        """Directory of array job data for the current attempt."""
        return self.attempt_dir / "array_job_data"

    @property
    def params_dir(self) -> Path:
        """Directory where parameter for the current attempt will be saved."""
        return self.attempt_dir / "params"

    @property
    def paths_json(self) -> Path:
        """JSON file to write path data for the current attempt to."""
        return self.params_dir / PATHS_JSON_NAME

    @property
    def slurm_params_json(self) -> Path:
        """JSON file to write slurm parameters for the current attempt to."""
        return self.params_dir / SLURM_PARAMS_JSON_NAME

    def get_array_job_data_dir_for_job(self, job: type[SlurmJob]) -> Path:
        return self.array_job_data_root_dir / job.job_name()

    def get_job_log_file_path(self, job: type[SlurmJob]) -> Path:
        match job.job_type():
            case SlurmJobType.ARRAY:
                return self.logs_dir / f"{job.job_name}-%A_%a.log.log"
            case SlurmJobType.SINGLE:
                return self.logs_dir / f"{job.job_name}.log"
            case _:
                raise NotImplementedError(
                    f"Unsupported slurm job type: '{job.job_type()}'."
                )

    def initialize_attempt_dir(self) -> None:
        """Initialize current attempt directory."""

        self.attempt_dir.mkdir(parents=True)
        self.logs_dir.mkdir(parents=True)

    @classmethod
    def calculate_next_attempt_index(cls, attempts_dir: Path) -> int:
        """Calculate the next attempt index based on the names of directories
        already found in `attempts_dir`.

        Parameters
        ----------
        attempts_dir
            Root directory where attempts for a run are saved.

        Returns
        -------
        int
            Next attempt index.
        """

        if not attempts_dir.is_dir():
            return 1

        return max([
            int(d.stem.removeprefix(cls.ATTEMPT_DIR_PREFIX))
            for d in attempts_dir.iterdir()
            if d.is_dir() and d.stem.startswith(cls.ATTEMPT_DIR_PREFIX)
        ], default=0) + 1

    @classmethod
    def from_next_attempt_dir(cls, attempts_dir: Path) -> Self:
        attempt_index = cls.calculate_next_attempt_index(attempts_dir)
        attempt_dir_name = f"{cls.ATTEMPT_DIR_PREFIX}{attempt_index}"
        return cls(
            attempt_index=attempt_index,
            attempt_dir=attempts_dir / attempt_dir_name,
        )


@dataclass(frozen=True)
class Paths(ArgParseable, JsonSerializable):
    """Paths used in a run.

    Attributes
    ----------
    project_paths
        Paths for a project.
    run_paths
        Paths for a run.
    attempt_paths
        Paths for an attempt of a run.
    """

    project_paths: ProjectPaths
    run_paths: RunPaths
    attempt_paths: AttemptPaths

    def initialize_run(self) -> None:
        """Perform run file structure initialization.

        Built-in run initialization includes:
            - Run directory creation
            - Attempt directory creation
            - Input directory creation
            - Output directory creation
        """

        self.run_paths.initialize_run_dir()
        self.run_paths.initialize_input_dir()
        self.run_paths.initialize_output_dir()
        self.attempt_paths.initialize_attempt_dir()

        logger.info(
            f"Performing attempt {self.current_attempt_index} of run "
            f"found at '{self.run_dir}'."
        )

    # TODO: Figure out if this is still needed?
    # TODO: Figure out where to call this
    def initialize_params_dirs(
            self,
            param_to_run_json_path: dict[JsonSerializable, Path],
            param_to_attempt_json_path: dict[JsonSerializable, Path],
    ) -> None:
        """Write param JSON files."""

        if self.current_attempt_index == 1:
            self.run_params_dir.mkdir(parents=True, exist_ok=True)
            for param, json_path in param_to_run_json_path.items():
                param.to_json(json_path)

        self.attempt_params_dir.mkdir(parents=True, exist_ok=True)
        for param, json_path in param_to_attempt_json_path.items():
            param.to_json(json_path)

    # TODO: Figure out if this is still needed?
    def write_missing_results_array_job_data(
            self,
            batch_size: int
    ) -> list[Path]:
        """Write array job data for current attempt based on inputs that are
        still missing an associated output file.

        Parameters
        ----------
        batch_size
            Number of input files to batch together into each array job.
        """

        return ArrayJobData.write_array_job_data(
            self.attempt_array_job_data_dir,
            self.run_paths.get_missing_output_input_files(file_extension=".tsv"),
            batch_size,
        )

    @staticmethod
    def compress_and_delete_dir(
            compress_dir: Path,
            fmt: str = "zip"
    ) -> Path | None:
        """Compress a directory and then delete the uncompressed directory.

        Parameters
        ----------
        compress_dir
            Directory to compress.
        fmt
            Format to compress to.

        Returns
        -------
        Path
            Path to compressed file.
        """

        shutil.make_archive(
            base_name=str(compress_dir.with_suffix("")),
            format=fmt,
            root_dir=compress_dir,
        )
        zip_path = compress_dir.with_suffix(f".{fmt}")
        if zip_path.is_file():
            shutil.rmtree(compress_dir)
        else:
            logger.warning(f"Could not find {fmt} file at '{zip_path}'.")
            return None

        return zip_path

    @classmethod
    def add_arguments(
            cls,
            parser: argparse.ArgumentParser,
            group: argparse._ArgumentGroup | None = None,
            prefix: str | None = None,
    ) -> None:
        ProjectPaths.add_arguments(parser, group, prefix)
        RunPaths.add_arguments(parser, group, prefix)

    @classmethod
    def from_custom_args(
            cls,
            args: argparse.Namespace,
            project_name: str,
            **fallbacks: Any
    ):
        project_paths = ProjectPaths.from_custom_args(
            args,
            project_name=project_name,
            **fallbacks
        )
        run_paths = RunPaths.from_custom_args(
            args,
            project_paths.runs_root_dir,
            **fallbacks
        )
        attempt_paths = AttemptPaths.from_next_attempt_dir(run_paths.attempts_dir)
        return cls(project_paths, run_paths, attempt_paths)


@dataclass(frozen=True)
class ArrayJobData(JsonSerializable):
    """Base class for storing data for an array job.

    Attributes
    ----------
    array_job_index
        Index of current array job.
    input_paths
        Paths to inputs to process in job.
    """
    array_job_index: int
    input_paths: tuple[Path, ...]

    @staticmethod
    def find_greatest_array_job_index(array_job_data_dir: Path) -> int | None:
        """Find the greatest array job index in a directory.

        Parameters
        ----------
        array_job_data_dir
            Directory containing array job data.

        Returns
        -------
        int
            Greatest array job index.
        """
        return max(
            [int(file.stem) for file in array_job_data_dir.glob("*.json")],
            default=None,
        )

    @staticmethod
    def build_json_path(array_job_data_dir: Path, array_job_index: int) -> Path:
        """Build array job data JSON path.

        Parameters
        ----------
        array_job_data_dir
            Directory containing array job data.
        array_job_index
            Index of array job.

        Returns
        -------
            Path to array job data JSON.
        """

        return array_job_data_dir / f"{array_job_index}.json"

    @staticmethod
    def calculate_job_count(input_paths: list[Path], batch_size: int) -> int:
        """Calculate the number of jobs that will be needed to to process all
        inputs split among jobs of size `batch_size`.

        Parameters
        ----------
        input_paths
            Inputs to process.
        batch_size
            Number of inputs to batch together into each job.

        Returns
        -------
        int
            Number of jobs that will be needed to process all inputs.
        """
        return ceil(len(input_paths) / batch_size)

    @classmethod
    def write_array_job_data(
            cls,
            array_job_data_dir: Path,
            input_paths: list[Path],
            batch_size: int,
    ) -> list[Path]:
        """Write array job data JSON files.

        Parameters
        ----------
        array_job_data_dir
            Directory to write array job data to.
        input_paths
            Inputs to batch together into array jobs.
        batch_size
            Number of inputs to batch together into each job.

        Returns
        -------
        list[Path]
            Paths to array job data JSON files.
        """

        if batch_size is None or batch_size < 1:
            raise ValueError(
                f"`batch_size` must be at least 1. Got value: {batch_size}."
            )

        # Populate job array data directory
        array_job_data_jsons = []
        for array_job_index in range(
                0,
                cls.calculate_job_count(input_paths, batch_size)
        ):
            array_job_data_dir.mkdir(parents=True, exist_ok=True)

            job_data = cls(
                array_job_index=array_job_index,
                input_paths=tuple(input_paths[
                    (array_job_index * batch_size)
                    :min(
                        ((array_job_index + 1) * batch_size),
                        len(input_paths)
                    )
                ]),
            )

            json_path = cls.build_json_path(
                array_job_data_dir,
                array_job_index
            )
            job_data.to_json(json_path)
            array_job_data_jsons.append(json_path)
        return array_job_data_jsons


@dataclass(frozen=True)
class ArrayJobInstanceParams(ArgParseable):
    """Base class for storing data about an array job instance.

    Attributes
    ----------
    compute_dir
        Path to root directory of compute node.
    paths_json
        Path to JSON file with path data for attempt.
    array_job_index
        Index of array job.
    """

    compute_dir: Path
    paths_json: Path
    array_job_index: int

    @classmethod
    def add_arguments(
            cls,
            parser: argparse.ArgumentParser,
            group: argparse._ArgumentGroup | None = None,
            prefix: str | None = None,
    ) -> None:
        group = group or parser.add_argument_group(
            "Array Job Parameters",
            "Parameters used in the array job stage.",
        )
        add_argument_to_parser(
            parser,
            group,
            prefix,
            "--compute-dir",
            dest="compute_dir",
            help="Root directory of compute node.",
            required=True,
            type=Path,
        )
        add_argument_to_parser(
            parser,
            group,
            prefix,
            "--array-job-index",
            dest="array_job_index",
            help="0-based index of array job instance.",
            required=True,
            type=int,
        )
        add_argument_to_parser(
            parser,
            group,
            prefix,
            "--paths-json",
            dest="paths_json",
            help="Path to JSON file containing paths for attempt.",
            required=True,
            type=Path,
        )
