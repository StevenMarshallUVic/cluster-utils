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
class GlobalConfig:
    workflow_script_rel_path: Path

    def get_workflow_script_path(self, project_dir: Path) -> Path:
        return (project_dir / self.workflow_script_rel_path).resolve()

    @classmethod
    def from_dict(cls, d: dict[str, Any]):
        instance = cls(
            workflow_script_rel_path=Path(d.pop("workflow-script")),
        )
        if len(d) != 0:
            raise ValueError(f"Remaining values: {d}.")

        return instance


@dataclass(frozen=True)
class EnvironmentConfig:
    modules: tuple[str, ...]
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
    global_config: GlobalConfig
    login_environment: EnvironmentConfig
    compute_environment: EnvironmentConfig

    @classmethod
    def from_dict(cls, d: dict[str, Any]):
        global_table = d.pop("global")
        login_table = d.pop("login")
        compute_table = d.pop("compute")
        instance = cls(
            global_config=GlobalConfig.from_dict(global_table),
            login_environment=EnvironmentConfig.from_dict(
                login_table.pop("environment")
            ),
            compute_environment=EnvironmentConfig.from_dict(
                compute_table.pop("environment")
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
