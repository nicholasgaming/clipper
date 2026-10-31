from unittest.mock import Mock

import pytest

from rocket_league_clips import drive
from rocket_league_clips.google_auth import AuthError


def test_creates_app_owned_folder_and_persists_id(tmp_path):
    service = Mock()
    service.files.return_value.list.return_value.execute.return_value = {"files": []}
    service.files.return_value.create.return_value.execute.return_value = {"id": "folder-1", "mimeType": drive.FOLDER_MIME}
    path = tmp_path / "settings.json"
    assert drive.ensure_folder(service, path) == "folder-1"
    assert drive.read_settings(path)["drive_folder_id"] == "folder-1"
    assert service.files.return_value.create.call_args.kwargs["body"]["appProperties"]["purpose"] == drive.FOLDER_MARKER


def test_reuses_existing_folder(tmp_path):
    path = tmp_path / "settings.json"
    drive.write_settings(path, {"drive_folder_id": "folder-1"})
    service = Mock()
    service.files.return_value.get.return_value.execute.return_value = {"id": "folder-1", "mimeType": drive.FOLDER_MIME}
    assert drive.ensure_folder(service, path) == "folder-1"
    service.files.return_value.create.assert_not_called()


def test_upload_requires_destination(tmp_path):
    with pytest.raises(AuthError, match="destination folder"):
        drive.upload_and_verify(Mock(), tmp_path / "file.mp4", "")


def test_upload_verifies_parent(tmp_path):
    local = tmp_path / "clip.mp4"
    local.write_bytes(b"test")
    service = Mock()
    service.files.return_value.create.return_value.next_chunk.return_value = (None, {"id": "file-1"})
    service.files.return_value.get.return_value.execute.return_value = {"id": "file-1", "parents": ["another-folder"]}
    with pytest.raises(AuthError, match="verified"):
        drive.upload_and_verify(service, local, "folder-1")


def test_verification_rejects_wrong_content():
    service = Mock()
    service.files.return_value.get.return_value.execute.return_value = {"id": "file-1", "parents": ["folder-1"], "md5Checksum": "wrong", "size": "4"}
    with pytest.raises(AuthError, match="content did not match"):
        drive.verify_file(service, "file-1", "folder-1", "expected", 4)


def test_new_queue_id_reuses_identical_named_app_clip(tmp_path):
    local = tmp_path / "RL_Clip_2026-10-29_22-13-13.mp4"
    local.write_bytes(b"old clip")
    digest = drive.file_md5(local)
    service = Mock()
    files = service.files.return_value
    files.list.return_value.execute.side_effect = [
        {"files": []},
        {"files": [{"id": "existing", "name": local.name, "size": str(local.stat().st_size),
                    "md5Checksum": digest, "appProperties": {"uploadKey": "older-key"}}]},
    ]
    files.get.return_value.execute.return_value = {"id": "existing", "parents": ["folder"],
                                                    "size": str(local.stat().st_size), "md5Checksum": digest}
    assert drive.upload_and_verify(service, local, "folder", upload_key="a" * 32) == "existing"
    files.create.assert_not_called()


def test_same_name_different_bytes_uploads_new_clip(tmp_path):
    local = tmp_path / "clip.mp4"
    local.write_bytes(b"new clip")
    digest = drive.file_md5(local)
    service = Mock()
    files = service.files.return_value
    files.list.return_value.execute.side_effect = [
        {"files": []},
        {"files": [{"id": "old", "name": local.name, "size": str(local.stat().st_size),
                    "md5Checksum": "different", "appProperties": {"uploadKey": "old-key"}}]},
    ]
    files.create.return_value.next_chunk.return_value = (None, {"id": "new"})
    files.get.return_value.execute.return_value = {"id": "new", "parents": ["folder"],
                                                    "size": str(local.stat().st_size), "md5Checksum": digest}
    assert drive.upload_and_verify(service, local, "folder", upload_key="b" * 32) == "new"
    files.create.assert_called_once()


def test_existing_clip_search_escapes_names_and_checks_all_pages():
    files = Mock()
    files.list.return_value.execute.side_effect = [
        {"files": [], "nextPageToken": "next"},
        {"files": [{"id": "match", "name": "it's\\here.mp4", "size": "4",
                    "md5Checksum": "digest", "appProperties": {"uploadKey": "key"}}]},
    ]
    assert drive._find_existing_clip(files, "folder", "it's\\here.mp4", "digest", 4) == "match"
    assert "it\\'s\\\\here.mp4" in files.list.call_args_list[0].kwargs["q"]
    assert files.list.call_args_list[1].kwargs["pageToken"] == "next"
