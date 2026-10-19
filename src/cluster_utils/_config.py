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

    @classmethod
    def from_dict(cls, d: dict[str, Any]):
        instance = cls(
            modules=tuple(d.pop("modules")),
        )
        if len(d) != 0:
            raise ValueError(f"Remaining values: {d}.")

        return instance


@dataclass(frozen=True)
class ClusterConfig:
    environment: EnvironmentConfig

    @classmethod
    def from_dict(cls, d: dict[str, Any]):
        instance = cls(
            environment=EnvironmentConfig.from_dict(d.pop("environment")),
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
