import pytest
from contextlib import chdir

# noinspection protected-member
from cluster_utils import _cli, _paths

TEST_ACCOUNT = "def-test"


def test_uninitialized_project_structure(tmp_path):
    """Test that an uninitialized project structure is considered
    uninitialized."""
    assert not _cli.is_project_dir_initialized(tmp_path)


class TestInitProject:
    def test_init_project_no_input(self, tmp_path):
        """Test project initialization when no inputs are passed."""

        _cli.initialize_project(["--project_dir", str(tmp_path), "--no-input"])
        assert _cli.is_project_dir_initialized(tmp_path)

    def test_init_project_no_args_account_input(
            self,
            tmp_path,
            monkeypatch
    ):
        """Test project initialization when no arguments are passed
        and account is passed using input().
        """

        # Pass values to input() prompts
        monkeypatch.setattr(
            "builtins.input",
            lambda _: next(iter([TEST_ACCOUNT]))
        )
        _cli.initialize_project(["--project_dir", str(tmp_path)])
        assert _cli.is_project_dir_initialized(tmp_path, TEST_ACCOUNT)

    def test_init_project_account_arg(self, tmp_path):
        """Test project initialization when an account is passed
        using args instead of input.
        """

        _cli.initialize_project([
            "--project_dir", str(tmp_path),
            "--account", TEST_ACCOUNT,
        ])
        assert _cli.is_project_dir_initialized(tmp_path, TEST_ACCOUNT)

    def test_init_project_already_initialized_error(self, tmp_path):
        """Ensure an error is raised when project initialization is
        performed on a directory that is already initialized.
        """

        args = [
            "--project_dir", str(tmp_path),
            "--account", TEST_ACCOUNT,
        ]
        _cli.initialize_project(args)
        with pytest.raises(FileExistsError):
            _cli.initialize_project(args)

    def test_init_project_force_initialized(self, tmp_path):
        """Test forcing the initialization of a directory that has
        already been initialized."""

        paths = _paths.ProjectPaths(tmp_path)
        paths.account_txt.write_text("def-incorrect")
        assert not _cli.is_project_paths_initialized(paths, TEST_ACCOUNT)

        _cli.initialize_project(arguments= [
            "--project_dir", str(tmp_path),
            "--account", TEST_ACCOUNT,
            "--force",
        ])
        assert _cli.is_project_paths_initialized(paths, TEST_ACCOUNT)
