import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from rocket_league_clips import google_auth as auth


def config():
    return {"installed": {"client_id": "example-id", "client_secret": "example-secret", "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": "https://oauth2.googleapis.com/token", "redirect_uris": ["http://localhost"]}}


def write_config(tmp_path: Path, data):
    path = tmp_path / "credentials.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_valid_desktop_config(tmp_path):
    assert auth.load_client_config(write_config(tmp_path, config())) == config()


@pytest.mark.parametrize("data", [{"web": {}}, {"installed": {}}, {"installed": {**config()["installed"], "redirect_uris": ["https://example.com"]}}])
def test_rejects_invalid_configs_without_revealing_secrets(tmp_path, data):
    with pytest.raises(auth.AuthError) as error:
        auth.load_client_config(write_config(tmp_path, data))
    assert "example-secret" not in str(error.value)


def test_missing_credentials_is_actionable(tmp_path):
    with pytest.raises(auth.AuthError, match="Credentials file not found"):
        auth.load_client_config(tmp_path / "missing.json")


def test_missing_refresh_token_is_not_saved():
    vault = Mock()
    with pytest.raises(auth.AuthError, match="refresh token"):
        auth.save_credentials(vault, "account", Mock(refresh_token=None))
    vault.set_password.assert_not_called()


def test_noninteractive_does_not_launch_browser(tmp_path):
    vault = Mock()
    vault.get_password.return_value = None
    with patch.object(auth, "windows_vault", return_value=vault), patch.object(auth.InstalledAppFlow, "from_client_config") as flow:
        with pytest.raises(auth.AuthError, match="authorization is required"):
            auth.get_credentials(write_config(tmp_path, config()), allow_interactive=False)
    flow.assert_not_called()


def test_drive_request_uses_minimum_file_scope():
    assert auth.SCOPES == ("https://www.googleapis.com/auth/drive.file",)
    service = Mock()
    auth.verify_drive_access(service)
    service.files.return_value.list.assert_called_once_with(pageSize=1, fields="files(id)")
    service.files.return_value.list.return_value.execute.assert_called_once()


def test_disconnect_does_not_delete_token_if_revocation_fails(tmp_path):
    vault = Mock()
    creds = Mock(refresh_token="private", token="private")
    with patch.object(auth, "windows_vault", return_value=vault), patch.object(auth, "load_saved_credentials", return_value=creds), patch.object(auth.requests, "post", return_value=Mock(status_code=503)):
        with pytest.raises(auth.AuthError, match="could not revoke"):
            auth.disconnect(write_config(tmp_path, config()))
    vault.delete_password.assert_not_called()
