from __future__ import annotations

import argparse
import importlib.util
import inspect
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Self

from cluster_utils.utils import ArgParseable


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

    print("target:", target_class)
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
        print(name, obj) # TODO: Temp debug
        if not issubclass(obj, target_class):
            print(obj, "is not target subclass.")
            continue
        if obj is target_class:
            print(obj, "is exactly target class")
            continue
        if obj.__module__ != module_name:
            print(obj, "is not the target module.")
            continue

        print(name, obj, "passed all checks!")
        # Ensure it inherits from target, is not the target itself,
        # and was actually defined IN this file (ignores outside imports)
        if (
                issubclass(obj, target_class)
                and obj is not target_class
                and obj.__module__ == module_name
        ):
            subclasses.append(obj)

    return subclasses


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
