import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Self, Any


@dataclass(frozen=True)
class EnvironmentConfig:
    modules: tuple[str]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Self:
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
    def from_dict(cls, d: dict[str, Any]) -> Self:
        instance = cls(
            environment=EnvironmentConfig.from_dict(d.pop("environment")),
        )
        if len(d) != 0:
            raise ValueError(f"Remaining values: {d}.")

        return instance

    @classmethod
    def from_toml(cls, toml: Path) -> Self:
        if not toml.is_file():
            raise FileNotFoundError(
                f"Cluster config TOML not found at '{toml}'"
            )

        with open(toml, "rb") as f:
            return cls.from_dict(tomllib.load(f))
