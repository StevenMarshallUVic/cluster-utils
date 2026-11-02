import subprocess
from pathlib import Path

from cluster_utils import init_logger

logger = init_logger(__name__)


def create_image_from_definition(definition: Path, image: Path) -> bool:
    """Create Apptainer image from an Apptainer definition file.

    Parameters
    ----------
    definition
        Apptainer definition file.
    image
        Where Apptainer image should be created.

    Returns
    -------
    bool
        Whether Apptainer image was created successfully.
    """

    if image.is_file():
        logger.info("Apptainer image already exists, skipping image creation.")
        return True

    if not definition.is_file():
        raise FileNotFoundError(
            f"Could not find Apptainer definition file at "
            f"'{definition}'."
        )

    process = subprocess.run(
        ["apptainer", "build", definition, image],
        check=True,
    )
    return process.returncode == 0
