import os
import sqlite3
from unittest.mock import patch

from rocket_league_clips.upload_queue import UploadQueue
from rocket_league_clips.google_auth import AuthRequired
from rocket_league_clips.drive import file_md5


def test_enqueue_deduplicates_and_recovers_interrupted_upload(tmp_path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"clip")
    queue = UploadQueue(tmp_path / "queue.db")
    upload_id = queue.enqueue(clip)
    assert queue.enqueue(clip) == upload_id
    assert queue.contains_path(clip)
    assert queue.claim()["id"] == upload_id
    assert queue.list()[0]["state"] == "uploading"
    queue.recover()
    assert queue.claim()["id"] == upload_id
    assert clip.exists()


def test_completed_only_after_verified_upload_and_keeps_local_file(tmp_path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"clip")
    queue = UploadQueue(tmp_path / "queue.db")
    upload_id = queue.enqueue(clip)
    with patch("rocket_league_clips.upload_queue.get_credentials"), patch("rocket_league_clips.upload_queue.drive_service"), patch("rocket_league_clips.upload_queue.ensure_folder", return_value="folder"), patch("rocket_league_clips.upload_queue.upload_and_verify", return_value="file") as upload:
        assert queue.process_one()
    assert upload.call_args.kwargs["upload_key"] == upload_id
    assert queue.list()[0]["state"] == "completed"
    assert queue.list()[0]["drive_file_id"] == "file"
    assert clip.exists()


def test_network_failure_backoff_then_manual_retry(tmp_path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"clip")
    queue = UploadQueue(tmp_path / "queue.db")
    queue.enqueue(clip)
    with patch("rocket_league_clips.upload_queue.get_credentials", side_effect=OSError("offline")):
        queue.process_one()
    assert queue.list()[0]["state"] == "failed"
    assert queue.claim() is None
    queue.retry()
    assert queue.claim() is not None
    assert clip.exists()


def test_authentication_wait_is_retried_after_backoff(tmp_path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"clip")
    queue = UploadQueue(tmp_path / "queue.db")
    queue.enqueue(clip)
    with patch("rocket_league_clips.upload_queue.get_credentials", side_effect=AuthRequired("sign in")):
        queue.process_one()
    row = queue.list()[0]
    assert row["state"] == "waiting_for_authentication"
    assert queue.claim() is None
    with patch("rocket_league_clips.upload_queue.time.time", return_value=row["next_attempt"] + 1):
        assert queue.claim()["id"] == row["id"]


def test_database_connection_is_closed_after_use(tmp_path):
    path = tmp_path / "queue.db"
    queue = UploadQueue(path)
    queue.list()
    path.unlink()
    assert not path.exists()


def test_retention_deletes_only_unchanged_completed_clips(tmp_path):
    root = tmp_path / "clips"; root.mkdir()
    completed = root / "RL_Clip_completed.mp4"; completed.write_bytes(b"complete")
    pending = root / "RL_Clip_pending.mp4"; pending.write_bytes(b"pending")
    changed = root / "RL_Clip_changed.mp4"; changed.write_bytes(b"original")
    queue = UploadQueue(tmp_path / "queue.db")
    completed_id = queue.enqueue(completed); queue.enqueue(pending); changed_id = queue.enqueue(changed)
    queue.complete(completed_id, "verified-drive-id", file_md5(completed)); queue.complete(changed_id, "verified-drive-id-2", file_md5(changed))
    changed.write_bytes(b"different content")
    assert not queue.delete_completed_local_files(root, retention_days=0, verify_remote=lambda row: True)
    assert not completed.exists()
    assert pending.exists() and changed.exists()


def test_retention_checks_content_when_size_and_mtime_match(tmp_path):
    root = tmp_path / "clips"; root.mkdir()
    clip = root / "RL_Clip_changed.mp4"; clip.write_bytes(b"original")
    queue = UploadQueue(tmp_path / "queue.db")
    upload_id = queue.enqueue(clip); queue.complete(upload_id, "verified-drive-id", file_md5(clip))
    original = clip.stat()
    clip.write_bytes(b"modified")
    os.utime(clip, ns=(original.st_atime_ns, original.st_mtime_ns))
    queue.delete_completed_local_files(root, retention_days=0, verify_remote=lambda row: True)
    assert clip.exists()


def test_cleanup_requires_current_remote_verification_and_respects_cutoff(tmp_path):
    root = tmp_path / "clips"; root.mkdir()
    old = root / "RL_Clip_old.mp4"; old.write_bytes(b"old")
    new = root / "Clipper_Recording_new.mp4"; new.write_bytes(b"new")
    queue = UploadQueue(tmp_path / "queue.db")
    old_id = queue.enqueue(old)
    cutoff = __import__("time").time()
    new_id = queue.enqueue(new)
    queue.complete(old_id, "old-remote", file_md5(old))
    queue.complete(new_id, "new-remote", file_md5(new))
    assert queue.delete_completed_local_files(root, 0, verify_remote=lambda row: False, created_since=cutoff) == [new.name]
    assert old.exists() and new.exists()
    assert not queue.delete_completed_local_files(root, 0, verify_remote=lambda row: True, created_since=cutoff)
    assert old.exists() and not new.exists()


def test_existing_queue_database_is_migrated_without_losing_history(tmp_path):
    path = tmp_path / "queue.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE uploads (id TEXT PRIMARY KEY, local_path TEXT NOT NULL UNIQUE, state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, next_attempt REAL NOT NULL DEFAULT 0, progress REAL NOT NULL DEFAULT 0, drive_file_id TEXT, error TEXT, created REAL NOT NULL)")
        db.execute("INSERT INTO uploads (id, local_path, state, created) VALUES ('old', 'old.mp4', 'pending', 1)")
    queue = UploadQueue(path)
    assert queue.list()[0]["id"] == "old"
    assert "file_md5" in queue.list()[0]
