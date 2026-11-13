import subprocess

from cluster_utils import Cluster
from cluster_utils.utils import ON_CLUSTER


CLUSTER_TO_GPUS: frozendict[Cluster, tuple[str, ...]] = frozendict({
    Cluster.FIR: ("h100",),
    Cluster.NARVAL: ("a100",),
    Cluster.NIBI: ("h100",),
    Cluster.RORQUAL: ("h100",),
    Cluster.TRILLIUM: ("h100", "h200", "B200",),
    Cluster.KILLARNEY: ("l40s", "h100",),
    Cluster.TAMIA: ("h100", "h200",),
    Cluster.VULCAN: ("l40s",),
})


def get_scontrol_config() -> dict[str, str]:
    """Get config for the current Slurm environment.

    Returns
    -------
    dict[str, str]
        Mapping between config keys and values.
    """

    if not ON_CLUSTER:
        return {}

    process = subprocess.run(
        ["scontrol", "show", "config"],
        capture_output=True,
        text=True
    )
    if process.returncode != 0:
        raise RuntimeError(
            f"scontrol config retrieval failed with return code "
            f"{process.returncode}."
            f"\nStdout:\n{process.stdout}.\nStderr:\n{process.stderr}"
        )

    return {
        line.split("=")[0].strip(): line.split("=")[1].strip()
        for line in process.stdout.splitlines() if "=" in line
    }


def get_current_cluster_name() -> str | None:
    """Get the name of the current cluster.

    Returns
    -------
    str | None
        Name of the current cluster, or None if not on a cluster.
    """

    return get_scontrol_config().get("ClusterName")


def get_current_cluster() -> Cluster | None:
    """Get the current cluster.

    Returns
    -------
    Cluster | None
        The current cluster, or None if not on a cluster.
    """

    cluster_name = get_current_cluster_name()
    return Cluster(cluster_name) if cluster_name else None


def get_gpus_for_cluster(
        cluster: Cluster | None = get_current_cluster()
) -> tuple[str, ...]:
    """Get the available GPUs for a cluster.

    Parameters
    ----------
    cluster
        Cluster to get GPUs for.
        When not provided, finds current cluster.

    Returns
    -------
    tuple[str, ...]
        Available GPUs for the cluster.
    """

    if cluster is None:
        return tuple()

    return CLUSTER_TO_GPUS.get(cluster, tuple())
