"""Utilities used when running jobs on a cluster."""

from __future__ import annotations
import argparse
import enum
import json
import logging
import subprocess
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, fields, MISSING
from enum import StrEnum, auto
from pathlib import Path
from typing import Any


class _RunnerStage(StrEnum):
    """Stages of cluster program."""

    FOREGROUND = auto()
    """Stage performed on the main thread of the running job."""
    BACKGROUND = auto()
    """Stage performed in a background process."""
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


def log_args_help(
        template_parser: argparse.ArgumentParser,
        arg_parseables: list[type[ArgParseable]],
) -> None:
    """Write argparse help.

    Parameters
    ----------
    template_parser
        Parser to copy help description for.
    arg_parseables
        Arguments to add to help log message.
    """

    help_parser = argparse.ArgumentParser(
        prog=template_parser.prog,
        usage=template_parser.usage,
        description=template_parser.description,
        epilog=template_parser.epilog,
        formatter_class=template_parser.formatter_class,
        prefix_chars=template_parser.prefix_chars,
        fromfile_prefix_chars=template_parser.fromfile_prefix_chars,
        argument_default=template_parser.argument_default,
        conflict_handler=template_parser.conflict_handler,
        allow_abbrev=template_parser.allow_abbrev,
        exit_on_error=template_parser.exit_on_error,
        add_help=True,
    )
    for arg_parseable in arg_parseables:
        arg_parseable.add_arguments(help_parser)

    help_parser.parse_args()


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

            match item["__type__"]:
                case "Path":
                    return Path(item["value"])
                case "RunnerStage":
                    return _RunnerStage(item["value"])
                case "tuple":
                    return tuple(item["value"])
                case _:
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
