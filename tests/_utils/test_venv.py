"""Tests for venv module."""

import os

import pytest

from cluster_utils._paths import ProjectPaths
from cluster_utils._utils.venv import VenvCreator, PythonPackage, CLUSTER_UTILS_PACKAGE

VENV_ENV_VAR = "VIRTUAL_ENV"


class TestVenvCreator:
    def test_validate_requirements_installed(self):
        pkg1 = PythonPackage("foo", version="1.0")
        pkg2 = PythonPackage("bar", version="2.4")
        assert len(VenvCreator.find_missing_requirements(
            requirements=[],
            installed=[],
        )) == 0
        assert len(VenvCreator.find_missing_requirements(
            requirements=[pkg1],
            installed=[pkg1],
        )) == 0
        assert len(VenvCreator.find_missing_requirements(
            requirements=[pkg1, pkg1],
            installed=[pkg1],
        )) == 0
        assert len(VenvCreator.find_missing_requirements(
            requirements=[pkg1, pkg2],
            installed=[pkg1, pkg2],
        )) == 0
        assert len(VenvCreator.find_missing_requirements(
            requirements=[pkg1],
            installed=[pkg2],
        )) == 1
        assert len(VenvCreator.find_missing_requirements(
            requirements=[pkg1, pkg2],
            installed=[],
        )) == 2

    @pytest.mark.skip(reason="Temporarily skipped due to long runtime.")
    def test_venv_workflow(self, tmp_path):
        """Combined due to long runtime when initializing a venv for each test.
        """

        paths = ProjectPaths(tmp_path)
        requirements = [
            PythonPackage("six", version="1.16.0"),
            CLUSTER_UTILS_PACKAGE,
        ]
        venv = VenvCreator(
            paths,
            requirements=tuple(requirements),
        )

        # Test `initialize_base_venv()`
        venv.initialize_base_venv()
        assert paths.venv_dir.is_dir()
        assert paths.venv_bin_dir.is_dir()
        assert paths.venv_python.is_file()

        # Test `upgrade_pip()`
        previous_version = venv.current_pip_version
        venv.upgrade_pip()
        assert previous_version != venv.current_pip_version

        # Test `install_requirements()`
        # TODO: Test whether this package should always be installed even in fresh venv
        assert len(VenvCreator.find_missing_requirements(
            requirements=requirements,
            installed=venv.installed_packages,
        )) == len(requirements) - 1
        venv.install_requirements()
        assert len(VenvCreator.find_missing_requirements(
            requirements=requirements,
            installed=venv.installed_packages,
        )) == 0

        # Test `source_venv()`
        if VENV_ENV_VAR in os.environ:
            assert os.environ[VENV_ENV_VAR] != str(paths.venv_dir)
        assert not os.environ["PATH"].startswith(str(paths.venv_bin_dir))
        venv.source_venv()
        assert VENV_ENV_VAR in os.environ
        assert os.environ[VENV_ENV_VAR] == str(paths.venv_dir)
        assert os.environ["PATH"].startswith(str(paths.venv_bin_dir))
