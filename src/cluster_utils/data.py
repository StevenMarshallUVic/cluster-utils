import argparse
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from math import ceil
from pathlib import Path
from typing import Any

from cluster_utils.utils import ArgParseable, JsonSerializable, create_logger

logger = create_logger(__file__)


@dataclass(frozen=True)
class Input(ArgParseable, JsonSerializable):
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
    DEFAULT_CPUS_PER_TASK = 1

    account: str
    batch_size: int
    memory: str
    time: str

    cpus_per_task: int = DEFAULT_CPUS_PER_TASK

    @staticmethod
    def read_account_from_file(account_file: Path) -> str | None:
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
    project_dir: Path
    scratch_dir: Path
    run_dir: Path
    run_name: str
    current_attempt_index: int

    ATTEMPT_DIR_PREFIX = "attempt_"

    PATHS_JSON_NAME = "paths.json"
    SLURM_PARAMS_JSON_NAME = "slurm_params.json"

    @classmethod
    @abstractmethod
    def project_name(cls) -> str:
        pass

    #region Project Directory
    @property
    def account_file(self):
        return self.project_dir / ".account.txt"

    @property
    def src_module_path(self) -> str:
        return "src"

    @property
    def cluster_module_path(self) -> str:
        return f"{self.src_module_path}.cluster"

    @property
    def login_background_module_path(self) -> str:
        return f"{self.cluster_module_path}.login_background"

    @property
    def compute_module_path(self) -> str:
        return f"{self.cluster_module_path}.compute"
    #endregion

    #region Scratch Directory
    @property
    def scratch_project_dir(self) -> Path:
        return self.scratch_dir / self.project_name()

    @property
    def runs_root_dir(self) -> Path:
        return self.scratch_project_dir / "runs"

    @property
    def run_attempts_dir(self) -> Path:
        return self.run_dir / "attempts"

    @property
    def current_attempt_dir(self) -> Path:
        if self.current_attempt_index is None:
            raise ValueError("Current attempt index is not assigned.")

        return self.run_attempts_dir / f"{self.ATTEMPT_DIR_PREFIX}{self.current_attempt_index}"

    @property
    def logs_dir(self) -> Path:
        return self.current_attempt_dir / "logs"

    @property
    def login_background_log_file(self) -> Path:
        return self.logs_dir / f"{self.project_name()}-login.log"

    @property
    def compute_log_file(self) -> Path:
        return self.logs_dir / f"{self.project_name()}-compute-%A_%a.log"

    @property
    def attempt_array_job_data_dir(self) -> Path:
        return self.current_attempt_dir / "array_job_data"

    @property
    def attempt_params_dir(self) -> Path:
        return self.current_attempt_dir / "params"

    @property
    def attempt_paths_json(self) -> Path:
        return self.attempt_params_dir / self.PATHS_JSON_NAME

    @property
    def attempt_slurm_params_json(self) -> Path:
        return self.attempt_params_dir / self.SLURM_PARAMS_JSON_NAME

    @property
    def input_dir(self) -> Path:
        return self.run_dir / "input"

    @property
    def input_paths(self) -> list[Path]:
        return sorted(self.input_dir.iterdir())

    @property
    def run_params_dir(self) -> Path:
        return self.run_dir / ".params"

    @property
    def run_paths_json(self) -> Path:
        return self.run_params_dir / self.PATHS_JSON_NAME

    @property
    def run_slurm_params_json(self) -> Path:
        return self.run_params_dir / self.SLURM_PARAMS_JSON_NAME

    @property
    def output_dir(self) -> Path:
        return self.run_dir / "output"

    @property
    def results_dir(self) -> Path:
        return self.run_dir / "results"
    #endregion

    def initialize_run_foreground(self) -> None:
        if not self.run_dir.is_dir():
            self._initialize_run_dir()

        self._initialize_attempt_dir()

        logger.info(
            f"Performing attempt {self.current_attempt_index} of run "
            f"found at '{self.run_dir}'."
        )

    @abstractmethod
    def initialize_run_background(self, *args, **kwargs) -> None:
        pass

    def initialize_params_dirs(
            self,
            param_to_run_json_path: dict[ArgParseable, Path],
            param_to_attempt_json_path: dict[ArgParseable, Path],
    ) -> None:
        if self.current_attempt_index == 1:
            self.run_params_dir.mkdir(parents=True, exist_ok=True)
            for param, json_path in param_to_run_json_path.items():
                param.to_json(json_path)

        self.attempt_params_dir.mkdir(parents=True, exist_ok=True)
        for param, json_path in param_to_attempt_json_path.items():
            param.to_json(json_path)

    def write_missing_results_array_job_data(self, batch_size: int) -> list[Path]:
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
        self.run_dir.mkdir(parents=True, exist_ok=True)

    def _initialize_attempt_dir(self) -> None:
        self.run_attempts_dir.mkdir(parents=True, exist_ok=True)
        self.current_attempt_dir.mkdir(parents=True)
        self.logs_dir.mkdir(parents=True)

    @classmethod
    def construct_runs_root_dir(cls, scratch_dir: Path) -> Path:
        """Hacky way to bypass creating instance to get access to paths."""

        return scratch_dir / cls.project_name() / "runs"

    @classmethod
    def construct_attempts_dir(cls, run_dir: Path) -> Path:
        """Hacky way to bypass creating instance to get access to paths."""

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
    def from_previous_run_dir(cls, args: argparse.Namespace, run_dir: Path, **fallbacks: Any):
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
        runs_root_dir = cls.construct_runs_root_dir(scratch_dir)
        run_name = cls.generate_run_name(runs_root_dir, input_path)

        fallbacks["run_name"] = run_name
        fallbacks["run_dir"] = runs_root_dir / run_name

        arg_parseable: ArgParseable = super()
        return arg_parseable.from_args(
            args,
            **fallbacks,
            current_attempt_index=1,
        )

    @staticmethod
    def generate_run_name(runs_root_dir: Path, input_path: Path) -> str:
        run_name = input_path.stem
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
    array_job_index: int
    input_paths: tuple[Path, ...]

    @staticmethod
    def find_greatest_array_job_index(array_job_data_dir: Path) -> int:
        return max([
            int(file.stem) for file in array_job_data_dir.glob("*.json")
        ])

    @staticmethod
    def build_json_path(array_job_data_dir: Path, array_job_index: int) -> Path:
        return array_job_data_dir / f"{array_job_index}.json"

    @staticmethod
    def calculate_job_count(input_paths: list[Path], batch_size: int) -> int:
        return ceil(len(input_paths) / batch_size)

    @classmethod
    def write_array_job_data(
            cls,
            array_job_data_dir: Path,
            input_paths: list[Path],
            batch_size: int,
    ) -> list[Path]:
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
