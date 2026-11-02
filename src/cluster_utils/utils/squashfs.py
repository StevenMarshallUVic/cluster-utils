"""Methods for interacting with SquashFS.

For more information, see SquashFS documentation at:
https://docs.kernel.org/filesystems/squashfs.html
"""

import shutil
import subprocess
from enum import StrEnum
from pathlib import Path

from cluster_utils import init_logger

logger = init_logger(__name__)

MKSQUASHFS_COMMAND = "mksquashfs"
SQUASHFUSE_COMMAND = "squashfuse"


class SquashFSCompressionType(StrEnum):
    """Compression algorithms supported by SquashFS."""

    GZIP = "gzip"
    LZO = "lzo"
    LZ4 = "lz4"
    XZ = "xz"
    ZLIB = "zlib"
    ZSTD = "zstd"


def create_squashfs(
        source_dir: Path,
        output_file: Path,
        compression: SquashFSCompressionType = SquashFSCompressionType.GZIP,
) -> bool:
    """Creates a SquashFS filesystem image from a source directory.

    Parameters
    ----------
    source_dir
        Directory to compress.
    output_file
        Where to write created .squashfs file.
    compression
        Compression algorithm to use.

    Returns
    -------
    bool
        Whether SquashFS file was created successfully.
    """

    if not shutil.which(MKSQUASHFS_COMMAND):
        raise EnvironmentError(
            f"Command '{MKSQUASHFS_COMMAND}' not found. "
            f"Are you sure it's installed?"
        )

    logger.info("Creating SquashFS image at '%s'...", output_file)
    process = subprocess.run(
        [
            MKSQUASHFS_COMMAND, source_dir, output_file,
            "-comp", compression,
            "-noappend"
        ],
        check=True
    )
    if process.returncode == 0:
        logger.info("SquashFS image created successfully!")
        return True
    else:
        logger.warning(
            f"SquashFS image creation failed with error code "
            f"{process.returncode}."
        )
        return False


def squashfuse_mount(squashfs_image: Path, mount_dir: Path):
    """Mount a SquashFS filesystem image to a directory using squashfuse.

    Parameters
    ----------
    squashfs_image
        Image to mount.
    mount_dir
        Where to mount image to.

    Returns
    -------
    bool
        Whether image was successfully mounted.
    """

    if not squashfs_image.is_file():
        raise FileNotFoundError(
            "Cannot mount SquashFS image that does not exist."
        )

    if not shutil.which(MKSQUASHFS_COMMAND):
        raise EnvironmentError(
            f"Command '{MKSQUASHFS_COMMAND}' not found. "
            f"Are you sure it's installed?"
        )

    mount_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Mounting SquashFS image to '%s'...", mount_dir)
    process = subprocess.run(
        [
            SQUASHFUSE_COMMAND, squashfs_image, mount_dir,
        ],
        check=True
    )
    if process.returncode == 0:
        logger.info("SquashFS image created successfully!")
        return True
    else:
        logger.warning(f"SquashFS image creation failed with error code {process.returncode}.")
        return False
