import os

LMOD_ENV_VAR = "LMOD_CMD"
ON_CLUSTER = LMOD_ENV_VAR in os.environ
