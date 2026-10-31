"""Desktop OAuth with tokens stored in the current Windows user's vault."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests
from google.auth.exceptions import RefreshError, TransportError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ("https://www.googleapis.com/auth/drive.file",)
SERVICE = "Rocket League Clips Google OAuth"


class AuthError(Exception):
    """An actionable error which never contains credential or token values."""


class AuthRequired(AuthError):
    """The user must authorize the application again."""


def default_credentials_path() -> Path:
    # A packaged application looks next to the executable, never in a temporary
    # PyInstaller extraction directory. Source runs use the project root.
    root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
    return root / "credentials.json"


def load_client_config(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8-sig") as file:
            data = json.load(file)
    except FileNotFoundError as exc:
        raise AuthError(f"Credentials file not found: {path}. Put your downloaded Desktop OAuth JSON there and name it credentials.json.") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AuthError("Cannot read credentials.json as valid JSON. Use the original downloaded Desktop OAuth client file.") from exc
    if not isinstance(data, dict) or not isinstance(data.get("installed"), dict):
        raise AuthError("credentials.json must contain an 'installed' Desktop OAuth client, not a web client.")
    client = data["installed"]
    for field in ("client_id", "client_secret", "auth_uri", "token_uri"):
        if not isinstance(client.get(field), str) or not client[field].strip():
            raise AuthError(f"Desktop OAuth credentials are missing the required {field} field.")
    for field in ("auth_uri", "token_uri"):
        if urlparse(client[field]).scheme != "https":
            raise AuthError(f"The OAuth {field} must use HTTPS.")
    redirects = client.get("redirect_uris")
    if not isinstance(redirects, list) or not any(
        isinstance(uri, str) and urlparse(uri).scheme == "http" and urlparse(uri).hostname in ("localhost", "127.0.0.1", "::1")
        for uri in redirects
    ):
        raise AuthError("The Desktop OAuth client must support a localhost redirect URI.")
    return data


def vault_account(config: dict) -> str:
    # Separate different OAuth clients without placing the client ID in logs.
    digest = hashlib.sha256(config["installed"]["client_id"].encode("utf-8")).hexdigest()
    return "desktop-" + digest


def windows_vault():
    if os.name != "nt":
        raise AuthError("Secure token storage requires Windows Credential Manager.")
    try:
        from keyring.backends.Windows import WinVaultKeyring
        return WinVaultKeyring()
    except Exception as exc:
        raise AuthError("Windows Credential Manager is unavailable. Install the project requirements and check that Credential Manager is enabled.") from exc


def load_saved_credentials(vault, account: str):
    try:
        value = vault.get_password(SERVICE, account)
    except Exception as exc:
        raise AuthError("Could not read the token from Windows Credential Manager.") from exc
    if not value:
        return None
    try:
        info = json.loads(value)
        creds = Credentials.from_authorized_user_info(info, scopes=SCOPES)
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise AuthError("The stored Google token is invalid. Remove the Google OAuth entry used by Clipper in Windows Credential Manager and sign in again.") from exc
    return creds


def save_credentials(vault, account: str, credentials: Credentials) -> None:
    if not credentials.refresh_token:
        raise AuthError("Google did not return a refresh token. Revoke this app's Google account access, then sign in again with offline access.")
    try:
        vault.set_password(SERVICE, account, credentials.to_json())
    except Exception as exc:
        raise AuthError("Could not save the token in Windows Credential Manager. Check that Credential Manager is enabled.") from exc


def get_credentials(path: Path | None = None, *, allow_interactive: bool = True):
    config = load_client_config(path or default_credentials_path())
    vault = windows_vault()
    account = vault_account(config)
    creds = load_saved_credentials(vault, account)
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            save_credentials(vault, account, creds)
        except RefreshError as exc:
            if getattr(exc, "retryable", False):
                raise AuthError("Google authorization refresh is temporarily unavailable. Try again later.") from exc
            if not allow_interactive:
                raise AuthRequired("Google authorization has expired or was revoked. Sign in again.") from exc
            creds = None
        except TransportError as exc:
            raise AuthError("Could not contact Google to refresh authorization. Check your internet connection and try again.") from exc
    if not creds or not creds.valid:
        if not allow_interactive:
            raise AuthRequired("Google authorization is required. Run test_google_auth.py to sign in.")
        try:
            flow = InstalledAppFlow.from_client_config(config, scopes=SCOPES)
            creds = flow.run_local_server(host="localhost", port=0, open_browser=True, authorization_prompt_message=None, access_type="offline", prompt="consent", timeout_seconds=300)
        except Exception as exc:
            raise AuthError("Google sign-in did not complete. Check your browser, test-user access, network connection, and OAuth configuration, then try again.") from exc
        save_credentials(vault, account, creds)
    return creds


def drive_service(credentials):
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def disconnect(path: Path | None = None) -> None:
    config = load_client_config(path or default_credentials_path())
    vault = windows_vault()
    account = vault_account(config)
    creds = load_saved_credentials(vault, account)
    if not creds:
        return
    token = creds.refresh_token or creds.token
    if token:
        try:
            response = requests.post("https://oauth2.googleapis.com/revoke", data={"token": token}, timeout=10)
            if response.status_code != 200:
                raise AuthError("Google could not revoke authorization. Check your connection and retry.")
        except requests.RequestException as exc:
            raise AuthError("Could not reach Google to revoke authorization. Check your connection and retry.") from exc
    try:
        vault.delete_password(SERVICE, account)
    except Exception as exc:
        raise AuthError("Google authorization was revoked, but the local token could not be removed from Credential Manager.") from exc


def verify_drive_access(service) -> None:
    try:
        # drive.file only exposes files the app can access. An empty list is OK.
        service.files().list(pageSize=1, fields="files(id)").execute()
    except HttpError as exc:
        status = getattr(exc.resp, "status", "unknown")
        raise AuthError(f"Google Drive API request failed (HTTP {status}). Check that the Drive API is enabled and your account is an OAuth test user.") from exc
    except Exception as exc:
        raise AuthError("Could not complete the Google Drive API request. Check your internet connection and try again.") from exc
