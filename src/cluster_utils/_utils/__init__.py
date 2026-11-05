import os

LMOD_ENV_VAR = "LMOD_CMD"
ON_CLUSTER = LMOD_ENV_VAR in os.environ


def staticclass(cls):
    """Decorator to make a class static by preventing instantiation."""

    def __new__(new_cls, *args, **kwargs):
        raise TypeError(
            f"Class {cls.__name__} is static and cannot be instantiated.")

    cls.__new__ = __new__
    return cls
