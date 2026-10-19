# noinspection protected-member
from cluster_utils import _config, _paths


# class TestClusterConfig:
#     # TODO: Rethink way config tests work
#     @property
#     def default_cluster_config(self) -> _config.ClusterConfig:
#         return _config.ClusterConfig(
#             environment=_config.EnvironmentConfig(
#                 modules=tuple(["python/3.14.7"])
#             ),
#         )

    # def test_cluster_config_creation_dict(self):
    #     # TODO: Rethink way config tests work
    #     config = _config.ClusterConfig.from_dict({
    #         "environment": {"modules": ["python/3.14.7"]}
    #     })
    #     assert config == self.default_cluster_config

    # def test_cluster_config_creation_toml(self):
    #     config = _config.ClusterConfig.from_toml(
    #         _paths.SrcPaths.CLUSTER_CONFIG_TOML
    #     )
    #     assert config == self.default_cluster_config
