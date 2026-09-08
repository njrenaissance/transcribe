import pytest

from credentials import AzureCredentials, load_azure_credentials
from errors import CredentialError

_ENDPOINT_VAR = "AZURE_SPEECH_ENDPOINT"
_KEY_VAR = "AZURE_SPEECH_KEY"


def _set_env(monkeypatch, name: str, value: str | None) -> None:
    if value is None:
        monkeypatch.delenv(name, raising=False)
    else:
        monkeypatch.setenv(name, value)


@pytest.mark.unit
def test_load_azure_credentials_returns_credentials_when_both_present(monkeypatch):
    monkeypatch.setenv(_ENDPOINT_VAR, "https://example.cognitiveservices.azure.com")
    monkeypatch.setenv(_KEY_VAR, "secret-key")

    credentials = load_azure_credentials()

    assert credentials == AzureCredentials(endpoint="https://example.cognitiveservices.azure.com", key="secret-key")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("endpoint_value", "key_value", "expected_present", "expected_missing"),
    [
        pytest.param(None, "secret-key", _KEY_VAR, _ENDPOINT_VAR, id="endpoint_unset"),
        pytest.param("", "secret-key", _KEY_VAR, _ENDPOINT_VAR, id="endpoint_empty"),
        pytest.param("https://example.com", None, _ENDPOINT_VAR, _KEY_VAR, id="key_unset"),
        pytest.param("https://example.com", "", _ENDPOINT_VAR, _KEY_VAR, id="key_empty"),
    ],
)
def test_load_azure_credentials_raises_naming_only_the_missing_variable(
    monkeypatch, endpoint_value, key_value, expected_present, expected_missing
):
    _set_env(monkeypatch, _ENDPOINT_VAR, endpoint_value)
    _set_env(monkeypatch, _KEY_VAR, key_value)

    with pytest.raises(CredentialError) as exc_info:
        load_azure_credentials()

    message = str(exc_info.value)
    assert expected_missing in message
    assert expected_present not in message


@pytest.mark.unit
@pytest.mark.parametrize(
    ("endpoint_value", "key_value"),
    [
        pytest.param(None, None, id="both_unset"),
        pytest.param("", "", id="both_empty"),
    ],
)
def test_load_azure_credentials_raises_naming_both_when_both_missing(monkeypatch, endpoint_value, key_value):
    _set_env(monkeypatch, _ENDPOINT_VAR, endpoint_value)
    _set_env(monkeypatch, _KEY_VAR, key_value)

    with pytest.raises(CredentialError) as exc_info:
        load_azure_credentials()

    message = str(exc_info.value)
    assert _ENDPOINT_VAR in message
    assert _KEY_VAR in message
