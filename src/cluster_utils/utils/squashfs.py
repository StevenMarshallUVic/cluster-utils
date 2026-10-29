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
    subprocess.run(
        [
            "mksquashfs", source_dir, output_file,
            "-comp", compression,
            "-noappend"
        ],
        check=True
    )
    logger.info("SquashFS image created successfully!")
    return True
