"""Azure Speech credential loading and validation."""

import os
from dataclasses import dataclass

from .errors import CredentialError

_ENDPOINT_VAR = "AZURE_SPEECH_ENDPOINT"
_KEY_VAR = "AZURE_SPEECH_KEY"


@dataclass(frozen=True)
class AzureCredentials:
    """Validated Azure Speech endpoint and key."""

    endpoint: str
    key: str


def load_azure_credentials() -> AzureCredentials:
    """Read and validate Azure Speech credentials from the environment.

    Raises:
        CredentialError: if `AZURE_SPEECH_ENDPOINT` and/or `AZURE_SPEECH_KEY`
            is unset or empty, naming every missing variable.
    """
    endpoint = os.environ.get(_ENDPOINT_VAR, "")
    key = os.environ.get(_KEY_VAR, "")

    missing = [name for name, value in ((_ENDPOINT_VAR, endpoint), (_KEY_VAR, key)) if not value]
    if missing:
        raise CredentialError(f"Missing required environment variable(s): {', '.join(missing)}")

    return AzureCredentials(endpoint=endpoint, key=key)
