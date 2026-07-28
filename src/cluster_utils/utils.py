import argparse
import enum
import json
import logging
import subprocess
import sys
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, fields, MISSING
from pathlib import Path
from typing import Any


def create_logger(file: str, level: int | str = logging.DEBUG) -> logging.Logger:
    logging.basicConfig(level=level, stream=sys.stdout)
    _logger = logging.getLogger(Path(file).name)
    _logger.setLevel(level)
    return _logger


def run_subprocess_command(
        args: str | Path | list[str | Path],
        logger: logging.Logger | None = None,
) -> bool:
    log_output = logger.isEnabledFor(logging.DEBUG) if logger else False
    with subprocess.Popen(
        args,
        stdout=subprocess.PIPE if log_output else subprocess.DEVNULL,
        stderr=subprocess.STDOUT if log_output else subprocess.DEVNULL,
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
                logger.warning(log_message)
            else:
                print(log_message)

            if process.stdout is not None and not log_output:
                print(process.stdout)

            return False
    return True


class ClusterJsonEncoder(json.JSONEncoder, ABC):
    """JSON encoder for serializing non-standard variables."""

    @classmethod
    def custom_encode(cls, item) -> Any:
        return None

    @classmethod
    def custom_decode(cls, item) -> Any:
        return None

    @classmethod
    def _transform(cls, item):
        custom_encode = cls.custom_encode(item)
        if custom_encode is not None:
            return custom_encode

        if isinstance(item, Path):
            return {"__type__": "Path", "value": str(item)}
        if isinstance(item, tuple):
            return {"__type__": "tuple", "value": [cls._transform(i) for i in item]}
        if isinstance(item, dict):
            return {k: cls._transform(v) for k, v in item.items()}
        if isinstance(item, list):
            return [cls._transform(i) for i in item]
        return item

    def iterencode(self, o: Any, _one_shot=False):
        return super().iterencode(self._transform(o), _one_shot=_one_shot)

    def encode(self, o: Any) -> str:
        return super().encode(_transform(o))

    @classmethod
    def decode(cls, item):
        """Custom hook to reconstruct variables from JSON dictionaries."""
        if "__type__" in item:
            custom_decode = cls.custom_decode(item)
            if custom_decode is not None:
                return custom_decode

            match item["__type__"]:
                case "Path":
                    return Path(item["value"])
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
                "type must be assigned an Enum when using EnumAction")
        if not issubclass(enum_type, enum.Enum):
            raise TypeError("type must be an Enum when using EnumAction")

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
    @classmethod
    def json_encoder(cls) -> type[json.JSONEncoder] | None:
        return ClusterJsonEncoder

    def to_json(self, output_json: Path) -> None:
        with open(output_json, "w") as json_file:
            json.dump(asdict(self), json_file, cls=self.json_encoder())

    @classmethod
    def from_json(cls, input_json: Path):
        with open(input_json, "r") as json_file:
            # noinspection argument-list
            return cls(**json.load(
                json_file,
                object_hook=cls.json_encoder().decode,
            ))


@dataclass(frozen=True)
class ArgParseable(ABC):
    """
    Base class for dataclasses that can be constructed from argparse.Namespace.

    Subclasses must:
    - Be a dataclass
    - Implement argument_parser()
    """

    @staticmethod
    @abstractmethod
    def add_arguments(
            parser: argparse.ArgumentParser,
            group: argparse._ArgumentGroup | None = None,
    ) -> None:
        raise NotImplementedError

    @classmethod
    def from_args(
            cls,
            args: argparse.Namespace,
            **fallbacks: Any,
    ):
        """
        Generic constructor that:
        - Uses args.<field> if present and not None
        - Otherwise falls back to provided keyword arguments
        - Otherwise uses dataclass defaults
        - Raises if required fields are missing
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
