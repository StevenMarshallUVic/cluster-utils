"""Classes for storing data used in jobs run on a cluster."""

import argparse
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from math import ceil
from pathlib import Path
from typing import Any

from cluster_utils.utils import ArgParseable, JsonSerializable

logger = logging.getLogger(Path(__file__).name)


@dataclass(frozen=True)
class Input(ArgParseable, JsonSerializable):
    """Base class for storing input data.

    Attributes
    ----------
    input_path
        Path to file/directory containing input.
    """

    input_path: Path

    @staticmethod
    def add_arguments(
            parser: argparse.ArgumentParser,
            group: argparse._ArgumentGroup | None = None,
    ) -> None:
        target = group if group is not None else parser
        target.add_argument(
            "-i", "--input-path",
            help="Path to input(s). "
                 "See README.md for explanation of valid inputs.",
            type=Path,
        )


@dataclass(frozen=True)
class SlurmParams(ArgParseable, JsonSerializable):
    """Base class for storing slurm parameters data.

    Attributes
    ----------
    account
        Digital Research Alliance of Canada account to charge usage to.
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

    account: str
    batch_size: int
    memory: str
    time: str

    cpus_per_task: int = DEFAULT_CPUS_PER_TASK

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

    @staticmethod
    def add_arguments(
            parser: argparse.ArgumentParser,
            group: argparse._ArgumentGroup | None = None,
    ) -> None:
        group = parser.add_argument_group(
            "Slurm Parameters",
            "Parameters used for Slurm job submission."
        )
        group.add_argument(
            "--account",
            help=f"(Optional) Digital Research Alliance of Canada account to "
                 f"charge usage to. "
                 f"When not supplied, attempts to find value in account file.",
            type=str,
        )
        group.add_argument(
            "--batch-size", "--batch",
            help="(Optional) How many inputs to batch into each slurm job. "
                 "When not supplied, uses default batch size.",
            type=int,
        )
        group.add_argument(
            "--cpus-per-task", "--cpus",
            help="(Optional) How many CPUs to allocate for each slurm job. "
                 "When not supplied, uses default of "
                 f"{SlurmParams.DEFAULT_CPUS_PER_TASK}.",
            type=int,
            default=SlurmParams.DEFAULT_CPUS_PER_TASK,
        )
        group.add_argument(
            "--memory", "--mem",
            help="(Optional) Amount of memory to allocate for each slurm job. "
                 "When not supplied, uses default memory.",
            type=str,
        )
        group.add_argument(
            "--time",
            help="(Optional) Amount of time to allocate for each slurm job. "
                 "When not supplied, uses default time.",
            type=str,
        )


@dataclass(frozen=True)
class Paths(ArgParseable, JsonSerializable, ABC):
    """Base class for storing paths used in a run.

    Attributes
    ----------
    project_dir
        Path to root directory of project.
    scratch_dir
        Path to root directory of scratch file system for a user.
    run_dir
        Path to root directory of the current run.
    run_name
        Name of the current run.
    current_attempt_index
        1-based index of the current attempt.
    """

    project_dir: Path
    scratch_dir: Path
    run_dir: Path
    run_name: str
    current_attempt_index: int

    ATTEMPT_DIR_PREFIX = "attempt_"

    PATHS_JSON_NAME = "paths.json"
    SLURM_PARAMS_JSON_NAME = "slurm_params.json"

    #region Abstract Properties
    @classmethod
    @abstractmethod
    def project_name(cls) -> str:
        """Abstract method for specifying the name of the project."""
        pass

    @property
    @abstractmethod
    def runner_module_path(self) -> str:
        """Abstract property for specifying the module path to the runner
        script."""
        pass
    #endregion

    #region Project Directory
    @property
    def account_file(self):
        """Default path to the account file for this project."""
        return self.project_dir / ".account.txt"
    #endregion

    #region Scratch Directory
    @property
    def scratch_project_dir(self) -> Path:
        """Root directory where project files will be saved on the scratch file
        system."""
        return self.scratch_dir / self.project_name()

    @property
    def runs_root_dir(self) -> Path:
        """Root directory where runs will be saved."""
        return self.scratch_project_dir / "runs"

    @property
    def run_attempts_dir(self) -> Path:
        """Root directory where attempts for the current run will be saved."""
        return self.run_dir / "attempts"

    @property
    def current_attempt_dir(self) -> Path:
        """Directory of current attempt."""
        return (self.run_attempts_dir
                / f"{self.ATTEMPT_DIR_PREFIX}{self.current_attempt_index}")

    @property
    def logs_dir(self) -> Path:
        """Directory where log files will be written to for this attempt."""
        return self.current_attempt_dir / "logs"

    @property
    def login_background_log_file(self) -> Path:
        """Log file where background logging will be written to"""
        return self.logs_dir / f"{self.project_name()}-login.log"

    @property
    def compute_log_file(self) -> Path:
        """Log file where compute logging will be written to"""
        return self.logs_dir / f"{self.project_name()}-compute-%A_%a.log"

    @property
    def attempt_array_job_data_dir(self) -> Path:
        """Directory of array job data for the current attempt."""
        return self.current_attempt_dir / "array_job_data"

    @property
    def attempt_params_dir(self) -> Path:
        """Directory where parameter for the current attempt will be saved."""
        return self.current_attempt_dir / "params"

    @property
    def attempt_paths_json(self) -> Path:
        """JSON file to write path data for the current attempt to."""
        return self.attempt_params_dir / self.PATHS_JSON_NAME

    @property
    def attempt_slurm_params_json(self) -> Path:
        """JSON file to write slurm parameters for the current attempt to."""
        return self.attempt_params_dir / self.SLURM_PARAMS_JSON_NAME

    @property
    def input_dir(self) -> Path:
        """Directory containing input files for the current run."""
        return self.run_dir / "input"

    @property
    def input_paths(self) -> list[Path]:
        """Sorted list of all input paths in current run."""
        return sorted(self.input_dir.iterdir())

    @property
    def run_params_dir(self) -> Path:
        """Directory where parameters for the current run will be saved."""
        return self.run_dir / ".params"

    @property
    def run_paths_json(self) -> Path:
        """JSON file to write path data for the current run to."""
        return self.run_params_dir / self.PATHS_JSON_NAME

    @property
    def run_slurm_params_json(self) -> Path:
        """JSON file to write slurm parameters for the current attempt to."""
        return self.run_params_dir / self.SLURM_PARAMS_JSON_NAME

    @property
    def output_dir(self) -> Path:
        """Directory where output for the current run will be saved."""
        return self.run_dir / "output"

    @property
    def results_dir(self) -> Path:
        """Directory where results for the current run will be saved."""
        return self.run_dir / "results"
    #endregion

    def initialize_run_minimal(self) -> None:
        """Perform minimal run file structure initialization."""

        if not self.run_dir.is_dir():
            self._initialize_run_dir()

        self._initialize_attempt_dir()

        logger.info(
            f"Performing attempt {self.current_attempt_index} of run "
            f"found at '{self.run_dir}'."
        )

    @abstractmethod
    def initialize_run_full(self, *args, **kwargs) -> None:
        """Perform full run file structure initialization."""
        pass

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
            self.get_missing_output_input_files(".tsv"),
            batch_size,
        )

    def get_missing_output_input_files(
            self,
            file_suffix: str | None = None,
    ) -> list[Path]:
        """Get paths to input files that have not been processed yet.

        Parameters
        ----------
        file_suffix
            Suffix of output files, or None if output are directories.

        Returns
        -------
        list[Path]
            Paths to input files that do not currently have results.
        """

        completed_ids = list()
        if self.output_dir.is_dir():
            if file_suffix:
                completed_ids = [
                    path.stem for path in sorted(self.output_dir.iterdir())
                    if path.suffix == file_suffix and path.is_file()
                ]
            else:
                completed_ids = [
                    path.stem for path in sorted(self.output_dir.iterdir())
                    if path.is_dir()
                ]

        return sorted([
            input_path for input_path in sorted(self.input_paths)
            if input_path.stem not in completed_ids
        ])

    def _initialize_run_dir(self) -> None:
        """Initialize run directory."""
        self.run_dir.mkdir(parents=True, exist_ok=True)

    def _initialize_attempt_dir(self) -> None:
        """Initialize current attempt directory."""
        self.run_attempts_dir.mkdir(parents=True, exist_ok=True)
        self.current_attempt_dir.mkdir(parents=True)
        self.logs_dir.mkdir(parents=True)

    @classmethod
    def construct_runs_root_dir(cls, scratch_dir: Path) -> Path:
        """Hacky way to bypass creating instance to get access to paths.

        Parameters
        ----------
        scratch_dir
            Path to root directory of scratch file system.

        Returns
        -------
        Path
            Path to root directory where runs are saved.
        """

        return scratch_dir / cls.project_name() / "runs"

    @classmethod
    def construct_attempts_dir(cls, run_dir: Path) -> Path:
        """Hacky way to bypass creating instance to get access to paths.

        Parameters
        ----------
        run_dir
            Path to root directory where runs are saved.

        Returns
        -------
        Path
            Path to directory where attempts for the current run are saved.
        """

        return run_dir / "attempts"

    @classmethod
    def from_args(cls, args: argparse.Namespace, **fallbacks: Any):
        run_dir: Path | None = getattr(args, "run_dir", None)
        input_path: Path | None = getattr(args, "input_path", None)

        if (run_dir is None) == (input_path is None):
            raise ValueError(
                "Invalid command line arguments. "
                "Must supply exactly one of '--run-dir' and '--input-path'."
            )

        if run_dir is not None:
            if args.run_name:
                raise ValueError(
                    "Invalid command line arguments. "
                    "Cannot use '--run-name' when '--run-dir' is supplied."
                )
            if not run_dir.is_dir():
                raise NotADirectoryError(
                    "Path passed with '--run-dir' must be a path to a run that "
                    "was already created. Use '--input-path' to create run."
                )
            return cls.from_previous_run_dir(args, run_dir, **fallbacks)
        elif input_path is not None:
            if not args.scratch_dir:
                raise ValueError(
                    "Invalid command line arguments. "
                    "Must provide '--scratch-dir' when using '--input-path'."
                )
            return cls.from_input(
                args,
                input_path,
                args.scratch_dir,
                **fallbacks
            )
        else:
            raise ValueError(
                "Unexpected values for command line arguments. "
                f"'run-dir': {run_dir}, 'input-path': {input_path}."
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

        fallbacks["run_name"] = run_dir.stem

        arg_parseable: ArgParseable = super()
        return arg_parseable.from_args(
            args,
            **fallbacks,
            current_attempt_index=cls.calculate_next_attempt_index(
                cls.construct_attempts_dir(args.run_dir)
            ),
        )

    @classmethod
    def from_input(
            cls,
            args: argparse.Namespace,
            input_path: Path,
            scratch_dir: Path,
            **fallbacks: Any,
    ):
        """Create instance populated using data from an input path.

        Parameters
        ----------
        args
            Command line arguments to extract data from.
        input_path
            Path to input to use for run creation.
        scratch_dir
            Root directory of scratch file system.
        fallbacks
            Keyword arguments of fallbacks to use if arguments are not provided.
        """

        runs_root_dir = cls.construct_runs_root_dir(scratch_dir)
        args.run_name = cls.generate_run_name(
            runs_root_dir,
            input_path,
            getattr(args, "run_name", None),
        )
        fallbacks["run_dir"] = runs_root_dir / args.run_name

        arg_parseable: ArgParseable = super()
        return arg_parseable.from_args(
            args,
            **fallbacks,
            current_attempt_index=1,
        )

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

    @staticmethod
    def calculate_next_attempt_index(attempts_dir: Path) -> int:
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

        return max([
            int(d.stem.removeprefix(Paths.ATTEMPT_DIR_PREFIX))
            for d in attempts_dir.iterdir()
            if d.is_dir() and d.stem.startswith(Paths.ATTEMPT_DIR_PREFIX)
        ], default=0) + 1

    @staticmethod
    def add_arguments(
            parser: argparse.ArgumentParser,
            group: argparse._ArgumentGroup | None = None,
    ) -> None:
        group = parser.add_argument_group(
            "Run Parameters",
            "Parameters used for initializing run."
        )
        group.add_argument(
            "--scratch-dir",
            help="Path to scratch directory on cluster.",
            type=Path,
        )
        group.add_argument(
            "-r", "--run-dir",
            help="Path to directory where previous run was created. "
                 "Allows performing multiple attempts for one input dataset.",
            type=Path,
        )
        group.add_argument(
            "--project-dir",
            help="(Optional) Path to project directory. "
                 "When not supplied, inferred from relative file structure.",
            type=Path,
        )
        group.add_argument(
            "--run-name",
            help="(Optional) Custom name of run. "
                 "When not supplied, infers name from input. "
                 "Ignored when '--run-dir' is supplied.",
            type=str,
        )


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
    array_job_index
        Index of array job.
    """

    compute_dir: Path
    array_job_index: int

    @staticmethod
    def add_arguments(
            parser: argparse.ArgumentParser,
            group: argparse._ArgumentGroup | None = None,
    ) -> None:
        group = parser.add_argument_group(
            "Array Job Parameters",
            "Parameters used in the array job stage.",
        )
        group.add_argument(
            "--compute-dir",
            help="Root directory of compute node.",
            required=True,
            type=Path,
        )
        group.add_argument(
            "--array-job-index",
            help="0-based index of array job instance.",
            required=True,
            type=int,
        )
