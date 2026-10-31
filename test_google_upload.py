"""Upload a small test file after real Google authorization."""
import os
import sys
import tempfile
from pathlib import Path

from googleapiclient.errors import HttpError

from rocket_league_clips.drive import ensure_folder, folder_url, upload_and_verify
from rocket_league_clips.google_auth import AuthError, drive_service, get_credentials


def main() -> int:
    temp_path = None
    try:
        credentials = get_credentials(allow_interactive=False)
        service = drive_service(credentials)
        folder_id = ensure_folder(service)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".txt", delete=False) as f:
            temp_path = Path(f.name)
            f.write("Clipper Google Drive upload test.\n")
        file_id = upload_and_verify(service, temp_path, folder_id, name="Clipper upload test.txt", mime_type="text/plain")
        print("Upload verified. File ID:", file_id)
        print("Folder:", folder_url(folder_id))
        print("The small test file remains in the Drive folder.")
        return 0
    except AuthError as exc:
        print("Upload test failed:", exc, file=sys.stderr)
    except HttpError as exc:
        print("Upload test failed: Google Drive returned HTTP", getattr(exc.resp, "status", "unknown"), file=sys.stderr)
    except Exception:
        print("Upload test failed. Check your connection, Drive permissions, and local settings, then retry.", file=sys.stderr)
    finally:
        if temp_path:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                print("Could not remove the local temporary test file:", temp_path, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
