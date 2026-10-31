"""Persistent, single-worker upload queue; never deletes local clips."""
from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError

from rocket_league_clips.drive import ensure_folder, file_md5, upload_and_verify
from rocket_league_clips.google_auth import AuthError, AuthRequired, drive_service, get_credentials


class UploadQueue:
    def __init__(self, db_path: Path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS uploads (
                id TEXT PRIMARY KEY, local_path TEXT NOT NULL UNIQUE,
                state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                next_attempt REAL NOT NULL DEFAULT 0, progress REAL NOT NULL DEFAULT 0,
                drive_file_id TEXT, error TEXT, created REAL NOT NULL,
                file_size INTEGER, file_mtime_ns INTEGER, file_md5 TEXT, completed_at REAL, local_deleted_at REAL
            )""")
            columns = {row["name"] for row in db.execute("PRAGMA table_info(uploads)")}
            for name, kind in (("file_size", "INTEGER"), ("file_mtime_ns", "INTEGER"), ("file_md5", "TEXT"), ("completed_at", "REAL"), ("local_deleted_at", "REAL")):
                if name not in columns:
                    db.execute(f"ALTER TABLE uploads ADD COLUMN {name} {kind}")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def enqueue(self, path: Path) -> str:
        path = Path(path).resolve(strict=True)
        if not path.is_file():
            raise ValueError("Clip must be a local file")
        stat = path.stat()
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO uploads (id,local_path,state,created,file_size,file_mtime_ns) VALUES (?,?,'pending',?,?,?)", (uuid.uuid4().hex, str(path), time.time(), stat.st_size, stat.st_mtime_ns))
            return db.execute("SELECT id FROM uploads WHERE local_path=?", (str(path),)).fetchone()[0]

    def contains_path(self, path: Path) -> bool:
        with self.connect() as db:
            return db.execute("SELECT 1 FROM uploads WHERE local_path=?", (str(Path(path).resolve()),)).fetchone() is not None

    def recover(self) -> None:
        # Call once when the single application instance starts.
        with self.connect() as db:
            db.execute("UPDATE uploads SET state='pending', next_attempt=0, progress=0 WHERE state='uploading'")

    def claim(self):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM uploads WHERE state IN ('pending','failed','waiting_for_authentication') AND next_attempt<=? ORDER BY created LIMIT 1", (time.time(),)).fetchone()
            if row:
                db.execute("UPDATE uploads SET state='uploading', error=NULL WHERE id=?", (row["id"],))
            return dict(row) if row else None

    def progress(self, upload_id: str, value: float):
        with self.connect() as db:
            db.execute("UPDATE uploads SET progress=? WHERE id=? AND state='uploading'", (max(0, min(1, value)), upload_id))

    def complete(self, upload_id: str, file_id: str, digest: str | None = None):
        with self.connect() as db:
            db.execute("UPDATE uploads SET state='completed', progress=1, drive_file_id=?, file_md5=?, completed_at=?, error=NULL WHERE id=?", (file_id, digest, time.time(), upload_id))

    def fail(self, row, message: str, *, needs_auth: bool = False):
        attempts = row["attempts"] + 1
        delay = min(3600, 15 * (2 ** min(attempts - 1, 8)))
        state = "waiting_for_authentication" if needs_auth else "failed"
        with self.connect() as db:
            db.execute("UPDATE uploads SET state=?, attempts=?, next_attempt=?, error=?, progress=0 WHERE id=?", (state, attempts, time.time() + delay, message, row["id"]))

    def retry(self):
        with self.connect() as db:
            db.execute("UPDATE uploads SET state='pending',next_attempt=0,error=NULL WHERE state IN ('failed','waiting_for_authentication')")

    def list(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM uploads ORDER BY created")]

    def delete_completed_local_files(self, clip_root: Path, retention_days: int, *, verify_remote, created_since=0):
        """Delete unchanged files only after checking that their Drive copies still exist."""
        if retention_days < 0:
            raise ValueError("Retention must be non-negative")
        root = Path(clip_root).resolve(strict=True)
        with self.connect() as db:
            rows = [dict(row) for row in db.execute("SELECT * FROM uploads WHERE state='completed' AND drive_file_id IS NOT NULL AND completed_at IS NOT NULL AND local_deleted_at IS NULL AND file_size IS NOT NULL AND file_mtime_ns IS NOT NULL AND file_md5 IS NOT NULL AND completed_at<=? AND created>=?", (time.time() - retention_days * 86400, created_since))]
        failures = []
        for row in rows:
            path = Path(row["local_path"])
            try:
                if path.is_symlink() or path.resolve().parent != root or not path.name.startswith(("RL_Clip_", "Clipper_")) or not path.name.endswith(".mp4"):
                    continue
                stat = path.stat()
                if stat.st_size != row["file_size"] or stat.st_mtime_ns != row["file_mtime_ns"]:
                    continue
                if file_md5(path) != row["file_md5"]:
                    continue
                if not verify_remote(row):
                    failures.append(path.name)
                    continue
                after = path.stat()
                if (stat.st_size, stat.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    continue
                path.unlink()
                with self.connect() as db:
                    db.execute("UPDATE uploads SET local_deleted_at=? WHERE id=? AND state='completed'", (time.time(), row["id"]))
            except FileNotFoundError:
                continue
            except Exception:
                failures.append(path.name)
        return failures

    def process_one(self) -> bool:
        row = self.claim()
        if not row:
            return False
        try:
            credentials = get_credentials(allow_interactive=False)
            service = drive_service(credentials)
            folder = ensure_folder(service)
            verified = {}
            file_id = upload_and_verify(service, Path(row["local_path"]), folder, upload_key=row["id"], progress=lambda value: self.progress(row["id"], value), on_verified=lambda digest: verified.update(md5=digest))
            self.complete(row["id"], file_id, verified.get("md5"))
        except (AuthRequired, RefreshError):
            self.fail(row, "Google authorization or secure storage needs attention.", needs_auth=True)
        except AuthError:
            self.fail(row, "Google connection or secure storage needs attention; retrying later.")
        except HttpError as exc:
            status = getattr(exc.resp, "status", None)
            self.fail(row, f"Google Drive returned HTTP {status or 'unknown'}.", needs_auth=status == 401)
        except FileNotFoundError:
            self.fail(row, "Local clip is missing; restore it before retrying.")
        except Exception:
            self.fail(row, "Upload failed. Check the network and retry.")
        return True


class UploadWorker:
    def __init__(self, queue: UploadQueue):
        self.queue = queue
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name="drive-upload", daemon=True)

    def start(self):
        self.queue.recover()
        self.thread.start()

    def _run(self):
        while not self.stop_event.is_set():
            if not self.queue.process_one():
                self.stop_event.wait(5)

    def stop(self):
        self.stop_event.set()
