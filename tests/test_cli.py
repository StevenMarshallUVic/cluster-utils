import pytest

# noinspection protected-member
from cluster_utils import _cli


def test_uninitialized_project_structure(tmp_path):
    """Test that an uninitialized project structure is considered
    uninitialized."""
    assert not _cli.is_project_dir_initialized(tmp_path)


class TestInitProject:
    def test_init_project(self, tmp_path):
        """Test project initialization when no inputs are passed."""

        _cli.initialize_project(["--project-dir", str(tmp_path)])
        assert _cli.is_project_dir_initialized(tmp_path)

    def test_init_project_already_initialized_error(self, tmp_path):
        """Ensure an error is raised when project initialization is
        performed on a directory that is already initialized.
        """

        args = ["--project-dir", str(tmp_path)]
        _cli.initialize_project(args)
        with pytest.raises(FileExistsError):
            _cli.initialize_project(args)

    def test_init_project_force_initialized(self, tmp_path):
        """Test forcing the initialization of a directory that has
        already been initialized."""

        assert not _cli.is_project_dir_initialized(tmp_path)

        args = ["--project-dir", str(tmp_path)]
        _cli.initialize_project(args)
        assert _cli.is_project_dir_initialized(tmp_path)

        _cli.initialize_project(args + ["--force"])
        assert _cli.is_project_dir_initialized(tmp_path)
