"""Interactive, real Google sign-in and Drive API verification."""
import sys

from rocket_league_clips.google_auth import AuthError, drive_service, get_credentials, verify_drive_access


def main() -> int:
    print("Clipper: Google Drive authentication test")
    print("If sign-in is needed, your browser will open. The local callback expires after five minutes.")
    try:
        credentials = get_credentials()
        verify_drive_access(drive_service(credentials))
    except AuthError as exc:
        print(f"Authentication test failed: {exc}", file=sys.stderr)
        return 1
    print("Success: Google authorization and an authenticated Drive API request both completed.")
    print("The token is stored in Windows Credential Manager for your Windows account.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
