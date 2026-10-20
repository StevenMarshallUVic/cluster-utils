"""Configurations for a project.

NOTE: Must be backward compatible with python 3.9.25 for use on clusters.
"""

from __future__ import annotations
try:
    import tomllib
except ModuleNotFoundError:
    # noinspection protected-member
    import pip._vendor.tomli as tomllib

from dataclasses import dataclass
from pathlib import Path
# Cannot import Self due to cluster defaulting to python 3.9
from typing import Any


@dataclass(frozen=True)
class EnvironmentConfig:
    modules: tuple[str]
    requirements_file: Path | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]):
        requirements_file: str = d.pop(
            "python-requirements",
            "",
        )
        if not isinstance(requirements_file, str):
            raise TypeError(
                f"'python-requirements' expected type str, "
                f"got {type(requirements_file)}"
            )

        instance = cls(
            modules=tuple(d.pop("modules")),
            requirements_file=Path(requirements_file) \
                if requirements_file != "" else None,
        )
        if len(d) != 0:
            raise ValueError(f"Remaining values: {d}.")

        return instance


@dataclass(frozen=True)
class ClusterConfig:
    login_environment: EnvironmentConfig
    compute_environment: EnvironmentConfig

    @classmethod
    def from_dict(cls, d: dict[str, Any]):
        login = d.pop("login")
        compute = d.pop("compute")
        instance = cls(
            login_environment=EnvironmentConfig.from_dict(
                login.pop("environment")
            ),
            compute_environment=EnvironmentConfig.from_dict(
                compute.pop("environment")
            ),
        )
        if len(d) != 0:
            raise ValueError(f"Remaining values: {d}.")

        return instance

    @classmethod
    def from_toml(cls, toml: Path):
        if not toml.is_file():
            raise FileNotFoundError(
                f"Cluster config TOML not found at '{toml}'"
            )

        return cls.from_dict(tomllib.loads(toml.read_text()))
