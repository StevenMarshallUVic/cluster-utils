"""Perform and query I/O operations.

NOTE: Must be backward compatible with python 3.9.25 for use on clusters.
"""

from __future__ import annotations
import re
from collections.abc import Iterable
from pathlib import Path


def get_missing_files(files: Iterable[Path]) -> list[Path]:
    """Find files that do not exist.

    Parameters
    ----------
    files
        Files to check existence for.

    Returns
    -------
    list[Path]
        Files that do not exist.
    """
    return [file for file in files if not file.is_file()]


def get_existing_files(files: Iterable[Path]) -> list[Path]:
    """Find files that exist.

    Parameters
    ----------
    files
        Files to check existence for.

    Returns
    -------
    list[Path]
        Files that exist.
    """
    missing_files = get_missing_files(files)
    return [file for file in files if file not in missing_files]


def does_file_contain_exactly(
        file: Path,
        expected_contents: str,
        strip: bool = True,
) -> bool:
    """Whether the contents of a file exactly match a string.

    Parameters
    ----------
    file
        File to read and compare contents of.
    expected_contents
        Expected contents of file.
    strip
        Whether to call `str.strip()` on contents of file before comparing.

    Returns
    -------
    bool
        Whether the contents of the file exactly match the expected contents.

    Raises
    ------
    FileNotFoundError
        If file does not exist.
    """

    if not file.is_file():
        raise FileNotFoundError()

    contents = file.read_text()
    if strip:
        contents = contents.strip()

    return contents == expected_contents


def sanitize_name(
        name: str,
        replacement: str = "_",
        fallback: str | None = None,
) -> str:
    """Sanitize a string to allow for use as file/directory name.

    Parameters
    ----------
    name
        Name to sanitize.
    replacement
        What to replace invalid characters with.
    fallback
        Fallback name to use if sanitization results in an empty string.
        If None, raises error if sanitization results in an empty string.

    Returns
    -------
    str
        Sanitized name.
    """

    name = Path(name).name
    safe_name = re.sub(r"[^\w.-]", replacement, name).rstrip(". ").lstrip(" ")

    if fallback:
        return safe_name if safe_name else fallback

    if not safe_name:
        raise ValueError(
            f"Sanitization of name '{name}' resulted in empty string, "
            f"and no fallback specified."
        )

    return safe_name


def sanitize_path_name(
        path: Path,
        replacement: str = "_",
        fallback: str | None = None,
) -> Path:
    """Sanitize a path to allow for name to be used as file/directory.

    Parameters
    ----------
    path
        Path to sanitize.
    replacement
        What to replace invalid characters with.
    fallback
        Fallback name to use if sanitization results in an empty string.
        If None, raises error if sanitization results in an empty string.

    Returns
    -------
    Path
        Path with name sanitized.
    """
    sanitized_name = sanitize_name(path.name, replacement, fallback)
    if path.parent:
        return path.parent / sanitized_name

    return Path(sanitized_name)
