"""App-owned Google Drive folder and verified uploads."""
from __future__ import annotations

import json
import hashlib
import os
import tempfile
import threading
from pathlib import Path

from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from rocket_league_clips.google_auth import AuthError

FOLDER_NAME = "Rocket League Clips"
FOLDER_MIME = "application/vnd.google-apps.folder"
FOLDER_MARKER = "rocket-league-clips-folder-v1"
_folder_lock = threading.RLock()


def settings_path() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "RocketLeagueClips" / "settings.json"


def read_settings(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("settings is not an object")
        return data
    except (OSError, ValueError) as exc:
        raise AuthError("The application settings could not be read; preserve the file and fix or restore it before retrying.") from exc


def write_settings(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_name = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as f:
            tmp_name = f.name
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    finally:
        if tmp_name and os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _is_folder(item: dict) -> bool:
    return item.get("id") and item.get("mimeType") == FOLDER_MIME and not item.get("trashed", False)


def ensure_folder(service, path: Path | None = None) -> str:
    with _folder_lock:
        return _ensure_folder(service, path)


def _ensure_folder(service, path: Path | None = None) -> str:
    path = path or settings_path()
    settings = read_settings(path)
    files = service.files()
    folder_id = settings.get("drive_folder_id")
    if folder_id:
        try:
            item = files.get(fileId=folder_id, fields="id,mimeType,trashed").execute()
            if _is_folder(item):
                return folder_id
        except HttpError as exc:
            if getattr(exc.resp, "status", None) not in (404, 410):
                raise
    # Search only for our app-created marker. drive.file does not expose all
    # pre-existing user folders, and matching by name alone is unsafe.
    query = "trashed = false and mimeType = '%s' and appProperties has { key='purpose' and value='%s' }" % (FOLDER_MIME, FOLDER_MARKER)
    response = files.list(q=query, spaces="drive", fields="files(id,mimeType,trashed)", pageSize=100).execute()
    folders = [item for item in response.get("files", []) if _is_folder(item)]
    if folders:
        folder_id = sorted(item["id"] for item in folders)[0]
    else:
        item = files.create(body={"name": FOLDER_NAME, "mimeType": FOLDER_MIME, "appProperties": {"purpose": FOLDER_MARKER}}, fields="id,mimeType,trashed").execute()
        if not _is_folder(item):
            raise AuthError("Google Drive did not return a valid folder ID.")
        folder_id = item["id"]
    settings["drive_folder_id"] = folder_id
    write_settings(path, settings)
    return folder_id


def file_md5(path: Path) -> str:
    with path.open("rb") as file:
        return hashlib.file_digest(file, "md5").hexdigest()


def _drive_query_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _find_existing_clip(files, folder_id: str, name: str, digest: str, size: int) -> str | None:
    """Find the same app-uploaded file after queue history was lost or replaced."""
    query = "trashed = false and '%s' in parents and name = '%s'" % (
        _drive_query_value(folder_id), _drive_query_value(name))
    page_token = None
    while True:
        response = files.list(q=query, spaces="drive", pageSize=100, pageToken=page_token,
                              fields="nextPageToken,files(id,name,size,md5Checksum,appProperties)").execute()
        for item in response.get("files", []):
            if (item.get("id") and item.get("name") == name and
                    item.get("md5Checksum") == digest and str(item.get("size")) == str(size) and
                    item.get("appProperties", {}).get("uploadKey")):
                return item["id"]
        page_token = response.get("nextPageToken")
        if not page_token:
            return None


def upload_and_verify(service, local_path: Path, folder_id: str, *, name: str | None = None, mime_type: str = "video/mp4", progress=None, upload_key: str | None = None, on_verified=None) -> str:
    if not folder_id:
        raise AuthError("A destination folder is required before uploading.")
    initial_stat = local_path.stat()
    digest = file_md5(local_path)
    files = service.files()
    if upload_key:
        # The generated UUID is restricted to hex and cannot alter the query.
        if len(upload_key) != 32 or any(c not in "0123456789abcdef" for c in upload_key):
            raise AuthError("Invalid upload identifier.")
        query = "trashed = false and '%s' in parents and appProperties has { key='uploadKey' and value='%s' }" % (_drive_query_value(folder_id), upload_key)
        existing = files.list(q=query, spaces="drive", fields="files(id)", pageSize=2).execute().get("files", [])
        if existing:
            file_id = verify_file(service, existing[0]["id"], folder_id, digest, initial_stat.st_size)
            _verify_unchanged(local_path, initial_stat)
            if on_verified: on_verified(digest)
            return file_id
        # Queue databases may be restored, replaced, or temporarily different.
        # A fresh queue UUID must not re-upload an identical named clip already
        # created by this app. A different name or bytes remains a new clip.
        existing_id = _find_existing_clip(files, folder_id, name or local_path.name, digest, initial_stat.st_size)
        if existing_id:
            file_id = verify_file(service, existing_id, folder_id, digest, initial_stat.st_size)
            _verify_unchanged(local_path, initial_stat)
            if on_verified: on_verified(digest)
            return file_id
    media = MediaFileUpload(str(local_path), mimetype=mime_type, chunksize=8 * 1024 * 1024, resumable=True)
    body = {"name": name or local_path.name, "parents": [folder_id]}
    if upload_key:
        body["appProperties"] = {"uploadKey": upload_key}
    request = files.create(body=body, media_body=media, fields="id,parents")
    result = None
    while result is None:
        status, result = request.next_chunk(num_retries=3)
        if status is not None and progress:
            progress(status.progress())
    file_id = result.get("id")
    if not file_id:
        raise AuthError("Google Drive did not return an uploaded file ID.")
    verify_file(service, file_id, folder_id, digest, initial_stat.st_size)
    _verify_unchanged(local_path, initial_stat)
    if on_verified: on_verified(digest)
    return file_id


def _verify_unchanged(path: Path, before) -> None:
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise AuthError("The local clip changed during upload; it has not been marked complete.")


def verify_file(service, file_id: str, folder_id: str, expected_md5: str | None = None, expected_size: int | None = None) -> str:
    verified = service.files().get(fileId=file_id, fields="id,parents,trashed,md5Checksum,size").execute()
    if verified.get("id") != file_id or folder_id not in verified.get("parents", []) or verified.get("trashed", False):
        raise AuthError("The uploaded file could not be verified in the destination folder.")
    if expected_md5 is not None and (verified.get("md5Checksum") != expected_md5 or str(verified.get("size")) != str(expected_size)):
        raise AuthError("The uploaded file's content did not match the local file; it has not been marked complete.")
    return file_id


def folder_url(folder_id: str) -> str:
    return "https://drive.google.com/drive/folders/" + folder_id
