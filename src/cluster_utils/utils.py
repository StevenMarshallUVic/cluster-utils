"""Utilities used when running jobs on a cluster."""

from __future__ import annotations
import argparse
import enum
import importlib.util
import inspect
import json
import logging
import subprocess
import sys
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, fields, MISSING, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Self

# TODO: Create helper method for generating prefix flags

class _RunnerStage(Enum):
    """Stages of cluster program."""

    LOGIN = auto()
    """Stage performed in the background on a cluster's login node."""
    COMPUTE = auto()
    """Stage performed on a cluster's compute node."""


def run_subprocess_command(
        args: str | Path | list[str | Path],
        logger: logging.Logger | None = None,
        output_logging_level: int = logging.DEBUG,
) -> bool:
    """

    Parameters
    ----------
    args
        Command to execute in the subprocess.
    logger
        (Optional) Logger to use for writing output.
        If not supplied, uses print to write output.
    output_logging_level
        Maximum logging level up to which command output should be written.
        For example, setting `output_logging_level=logging.INFO` will write the
        output of the command as long as the provided logger's level is INFO
        or lower.
        Does nothing if `logger` is not supplied.

    Returns
    -------
    bool
        Whether the subprocess command returned a 0 return code.
    """

    log_output = logger.isEnabledFor(output_logging_level) if logger else False
    with subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    ) as process:
        if process.stdout is not None and log_output:
            for line in process.stdout:
                print(line, end="")

        return_code = process.wait()
        if return_code != 0:
            log_message = f"Command failed with return code {return_code}."
            if process.stdout is not None and not log_output:
                log_message += " See console output below:"

            if logger:
                logger.error(log_message)
            else:
                print(log_message)

            if process.stdout is not None and not log_output:
                for line in process.stdout:
                    print(line, end="")

            return False
    return True


def find_subclasses_in_script[T](
        path: Path,
        target_class: type[T]
) -> list[T]:
    """Dynamically load a Python file and find classes that inherit from
    a target class.

    Parameters
    ----------
    path
        Python script to parse.
    target_class
        Class to search for.

    Returns
    -------
    list[type]
        All classes in file that inherit from the target class.
    """

    module_name = path.stem

    # Create a module specification from the file path
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module spec for '{path}.'")

    # Create module object based on the spec
    module = importlib.util.module_from_spec(spec)

    # Register in sys.modules so imports inside file resolve correctly
    sys.modules[module_name] = module

    # Execute file contents inside module context
    spec.loader.exec_module(module)

    # Inspect the module's contents
    subclasses = []
    for name, obj in inspect.getmembers(module, inspect.isclass):
        # Ensure it inherits from target, is not the target itself,
        # and was actually defined IN this file (ignores outside imports)
        if (
                issubclass(obj, target_class)
                and obj is not target_class
                and obj.__module__ == module_name
        ):
            subclasses.append(obj)

    return subclasses


@dataclass(frozen=True)
class PythonPackage:
    name: str
    version: str | None = None
    link: str | None = None

    @property
    def requirement_str(self):
        target = self.link or self.name

        if self.version is None:
            return target

        return f"{target}=={self.version}"

    @classmethod
    def from_requirements_txt(cls, file: Path) -> list[PythonPackage]:
        """Create instance with requirements parsed from requirements file.

        Parameters
        ----------
        file
            Path to requirements file.

        Raises
        ------
        FileNotFoundError
            If requirements file does not exist.
        """

        if not file.is_file():
            raise FileNotFoundError(
                f"Requirements file not found at '{file}'."
            )

        return [
            cls.from_requirement_str(line.strip())
            for line in file.read_text().splitlines()
        ]

    @classmethod
    def from_requirement_str(cls, requirement: str):
        if "==" in requirement:
            parts = requirement.split("==")
            return cls(parts[0].strip(), version=parts[1].strip())

        if " @ " in requirement:
            parts = requirement.split(" @ ")
            return cls(parts[0].strip(), link=parts[1].strip())

        raise NotImplementedError(
            f"Unsupported requirement format: '{requirement}'."
        )

    @classmethod
    def from_pip_list_cmd_output(cls, output: str) -> list[PythonPackage]:
        lines = output.splitlines()

        # 0-based character position of space between name and version columns
        col_split_index = lines[1].find(" ")

        return [
            cls(
                name=package_line[:col_split_index].strip(),
                version=package_line[col_split_index:].strip(),
            )
            for package_line in lines[2:] # Skip heading lines
        ]


class ClusterJsonEncoder(json.JSONEncoder, ABC):
    """JSON encoder for serializing and deserializing non-standard variables."""

    @classmethod
    def custom_encode(cls, item) -> Any | None:
        """Virtual method that can be overridden in child classes to add
        custom encoding logic.

        Parameters
        ----------
        item
            Item to attempt to encode.

        Returns
        -------
        Any
            Encoded item,
            or None if item was not supported by custom encoding logic.
        """
        return None

    @classmethod
    def custom_decode(cls, item) -> Any | None:
        """Virtual method that can be overridden in child classes to add
        custom decoding logic.

        Parameters
        ----------
        item
            Item to attempt to decode.

        Returns
        -------
        Any
            Decoded item,
            or None if item was not supported by custom decoding logic.
        """
        return None

    @classmethod
    def _encode(cls, item) -> Any:
        """Extra JSON encoding to add support for additional types.

        Parameters
        ----------
        item
            Item to encode.

        Returns
        -------
        Any
            Encoded item.
        """

        custom_encode = cls.custom_encode(item)
        if custom_encode is not None:
            return custom_encode

        if isinstance(item, Path):
            return {"__type__": "Path", "value": str(item)}
        if isinstance(item, _RunnerStage):
            return {"__type__": "RunnerStage", "value": str(item)}
        if isinstance(item, tuple):
            return {"__type__": "tuple", "value": [cls._encode(i) for i in item]}
        if isinstance(item, dict):
            return {k: cls._encode(v) for k, v in item.items()}
        if isinstance(item, list):
            return [cls._encode(i) for i in item]
        return item

    def iterencode(self, o: Any, _one_shot=False):
        return super().iterencode(self._encode(o), _one_shot=_one_shot)

    def encode(self, o: Any) -> str:
        return super().encode(self._encode(o))

    @classmethod
    def decode(cls, item):
        """Decode JSON using metadata added during custom encoding.

        Parameters
        ----------
        item
            Item to attempt to decode.

        Returns
        -------
        Any
            Decoded item.
        """

        if "__type__" in item:
            custom_decode = cls.custom_decode(item)
            if custom_decode is not None:
                return custom_decode

            default_decodings = {
                "Path": Path(item["value"]),
                "RunnerStage": _RunnerStage(item["value"]),
                "tuple": tuple(item["value"]),
            }
            default_decodings.get(item["__type__"], None)
            if default_decodings is not None:
                return default_decodings

            raise ValueError(
                f"Unexpected JSON custom type: '{item['__type__']}'"
            )
        return item


class EnumAction(argparse.Action):
    """Argparse action for handling Enums.
    https://stackoverflow.com/a/60750535/21695189
    """

    def __init__(self, **kwargs):
        # Pop off the type value
        enum_type = kwargs.pop("type", None)

        # Ensure an Enum subclass is provided
        if enum_type is None:
            raise ValueError(
                "'type' must be assigned an Enum when using EnumAction"
            )
        if not issubclass(enum_type, enum.Enum):
            raise TypeError("'type' must be an Enum when using EnumAction")

        # Generate choices from the Enum
        kwargs.setdefault("choices", tuple(e.name for e in enum_type))

        super(EnumAction, self).__init__(**kwargs)

        self._enum = enum_type

    def __call__(
            self,
            parser,
            namespace,
            values,
            option_string=None
    ):
        if not isinstance(values, str):
            return

        # Convert value back into an Enum
        value = self._enum[values]
        setattr(namespace, self.dest, value)


@dataclass(frozen=True)
class JsonSerializable(ABC):
    """Interface for adding JSON serialization support to a dataclass."""

    @classmethod
    def json_encoder(cls) -> type[json.JSONEncoder]:
        """Virtual method that allows child classes to override default encoder.
        """
        return ClusterJsonEncoder

    def to_json(self, output_json: Path) -> None:
        """Write JSON file with all fields of dataclass serialized as a
        dictionary.

        Parameters
        ----------
        output_json
            Path to write JSON file to.
        """

        with open(output_json, "w") as json_file:
            json.dump(asdict(self), json_file, cls=self.json_encoder())

    @classmethod
    def from_json(cls, input_json: Path):
        """Create instance of dataclass with fields populated from JSON file.

        Parameters
        ----------
        input_json
            JSON file to read data from.
        """

        with open(input_json, "r") as json_file:
            # noinspection argument-list
            return cls(**json.load(
                json_file,
                object_hook=cls.json_encoder().decode,
            ))


@dataclass(frozen=True)
class ArgParseable(ABC):
    """Interface for adding argument parsing support to a dataclass."""

    @staticmethod
    def argument_prefix() -> str | None:
        """Virtual method for adding custom prefix to arguments."""
        return None

    @classmethod
    @abstractmethod
    def add_arguments(
            cls,
            parser: argparse.ArgumentParser,
            group: argparse._ArgumentGroup | None = None,
    ) -> None:
        """Abstract method for adding arguments to an argument parser."""
        raise NotImplementedError

    @classmethod
    def from_args(
            cls,
            args: argparse.Namespace,
            **fallbacks: Any,
    ):
        """Create instance of dataclass by populating fields from command line
        arguments, using fallback values if arguments are not provided.

        Parameters
        ----------
        args
            Command line arguments to parse.
        **fallbacks
            Keyword arguments of fallback values to be used for fields not
            supplied in `args`.

        Raises
        ------
        ValueError
            If a value was not found in `args`, a fallback was not supplied,
            and there was not a default value assigned for the field at the
            dataclass-level.
        """

        init_values: dict[str, Any] = {}
        for f in fields(cls):
            if not f.init:
                continue

            name = f.name

            # 1. Value from args if available and not None
            value = getattr(args, name, None)
            if value is not None:
                init_values[name] = value
                continue

            # 2. Fallback value
            if name in fallbacks:
                init_values[name] = fallbacks[name]
                continue

            # 3. Default value from dataclass
            if f.default is not MISSING:
                init_values[name] = f.default
                continue
            if f.default_factory is not MISSING:
                init_values[name] = f.default_factory()
                continue

            # 4. Required field missing`
            raise ValueError(f"Missing required value: {name}")

        # noinspection argument-list
        return cls(**init_values)


class ArgParser(ABC):
    @staticmethod
    @abstractmethod
    def parser_name() -> str:
        raise NotImplementedError()

    @staticmethod
    @abstractmethod
    def parser_description() -> str:
        raise NotImplementedError()

    @staticmethod
    @abstractmethod
    def argument_sources() -> list[type[ArgParseable]]:
        """Abstract property for specifying additional argument sources."""
        return []

    @classmethod
    @abstractmethod
    def from_custom_args(cls, args: argparse.Namespace) -> Self:
        raise NotImplementedError()

    @classmethod
    def from_args(cls) -> Self:
        """Create instance from command line arguments."""

        parser = argparse.ArgumentParser(
            prog=cls.parser_name(),
            description=cls.parser_description(),
            epilog="See README.md for more information.",
            conflict_handler="resolve",
        )
        for argument_source in cls.argument_sources():
            argument_source.add_arguments(parser)

        args, _ = parser.parse_known_args()
        return cls.from_custom_args(args)
