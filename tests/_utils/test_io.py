import pytest

from cluster_utils._utils import io



def test_get_missing_files(tmp_path):
    missing_file = tmp_path / "missing_file.txt"
    missing_file2 = tmp_path / "other_missing_file.txt"
    real_file = tmp_path / "real.txt"
    real_file.touch()
    real_file2 = tmp_path / "real2.txt"
    real_file2.touch()

    assert len(io.get_missing_files([])) == 0
    assert len(io.get_missing_files([real_file])) == 0
    assert len(io.get_missing_files([missing_file])) == 1
    assert len(io.get_missing_files([missing_file, real_file])) == 1
    assert len(io.get_missing_files(
        [missing_file, missing_file2, real_file, real_file2]
    )) == 2


def test_get_existing_files(tmp_path):
    missing_file = tmp_path / "missing_file.txt"
    missing_file2 = tmp_path / "other_missing_file.txt"
    real_file = tmp_path / "real.txt"
    real_file.touch()
    real_file2 = tmp_path / "real2.txt"
    real_file2.touch()

    assert len(io.get_existing_files([])) == 0
    assert len(io.get_existing_files([missing_file])) == 0
    assert len(io.get_existing_files([real_file])) == 1
    assert len(io.get_existing_files([missing_file, real_file])) == 1
    assert len(io.get_existing_files(
        [missing_file, missing_file2, real_file, real_file2]
    )) == 2


def test_is_file_contents_exactly(tmp_path):
    target = "testing content123"
    target_strip = "strip content123\n "
    incorrect_target = "incorrect"

    file = tmp_path / "file.txt"
    file.write_text(target)
    strip_file = tmp_path / "strip.txt"
    strip_file.write_text(target_strip)

    assert io.does_file_contain_exactly(file, target)
    assert io.does_file_contain_exactly(strip_file, target_strip, False)
    assert not io.does_file_contain_exactly(file, incorrect_target)
    assert not io.does_file_contain_exactly(file, target_strip)
    assert not io.does_file_contain_exactly(strip_file, target_strip)

    missing_file = tmp_path / "missing_file.txt"
    with pytest.raises(FileNotFoundError):
        io.does_file_contain_exactly(missing_file, target)
