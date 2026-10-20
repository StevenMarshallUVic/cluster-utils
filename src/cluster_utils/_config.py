"""Configurations for a project.

NOTE: Must be backward compatible with python 3.9.25 for use on clusters.
"""

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
            "requirements-file",
            "",
        )
        if not isinstance(requirements_file, str):
            raise TypeError(
                f"'requirements-file' expected type str, "
                f"got {type(requirements_file)}"
            )

        instance = cls(
            modules=tuple(d.pop("modules")),
            requirements_file=Path(requirements_file),
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
        instance = cls(
            login_environment=EnvironmentConfig.from_dict(
                d.pop("login.environment")
            ),
            compute_environment=EnvironmentConfig.from_dict(
                d.pop("compute.environment")
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
