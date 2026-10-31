# Clipper

Clipper is an experimental Windows system-tray app for saving instant replays and recording longer videos from your screen, including gameplay from any game. Press a configurable shortcut (F8 by default) to save a replay locally and queue it for upload to your own Google Drive. It uses Windows Graphics Capture and Media Foundation for capture and FFmpeg to assemble clips.

> **Experimental:** Recording boundaries are approximate and the last seconds may be missing. Verify recordings before relying on them. A full replay is available only after the buffer fills.

**New here?** Follow the [step-by-step setup guide](SETUP.md), including Google Drive, optional student storage offers, and a ready-to-use prompt for Codex, Claude Code, or another AI assistant. AI assistants can also read [AGENTS.md](AGENTS.md) for project-specific guidance.

## Requirements

- 64-bit Windows 10 or 11 with a supported graphics adapter and a system tray.
- Python 3.12 or later and the .NET 10 SDK.
- FFmpeg and ffprobe in the same folder, with FFmpeg available on `PATH` (or installed through WinGet's Gyan.FFmpeg package).
- A Google account, a Google Cloud project and your own Desktop OAuth client for Google Drive. Credentials are **not** included in this repository.

## Set up Google Drive

1. Create or select a project in the [Google Cloud console](https://console.cloud.google.com/) and enable the Google Drive API.
2. Configure the OAuth consent screen under **Google Auth platform**. For a personal Google account, choose an external audience and add your Google account under **Audience → Test users** while the app is in testing.
3. Under **Clients**, create an OAuth client with application type **Desktop app**. Download its JSON file, rename it `credentials.json`, and place it in the project root alongside `run_app.py`. For a packaged build, place it beside `Clipper.exe` instead.
4. Open Clipper and select **Google Drive → Connect Drive**. Complete the browser sign-in with the test account and grant the requested access.

The app requests the `drive.file` scope and stores the resulting token in Windows Credential Manager. Keep your OAuth JSON and tokens private. Do not commit them or share them with the project. Google may expire test-user authorization and refresh tokens after seven days, requiring you to connect again. See Google's [Drive API Python quickstart](https://developers.google.com/workspace/drive/api/quickstart/python) and [test-user guidance](https://support.google.com/cloud/answer/15549945).

## Run from source

Open PowerShell in the downloaded or cloned project folder:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
dotnet publish .\native-capture\RocketLeagueCaptureEngine\RocketLeagueCaptureEngine.csproj -c Release -r win-x64 --self-contained true -o .\native-capture\RocketLeagueCaptureEngine\publish
.\.venv\Scripts\python.exe .\run_app.py
```

The first `dotnet publish` restores the native engine's NuGet dependencies. Start Clipper again by running the last command. Closing its window leaves it running in the tray; use the tray menu to exit. Launch at sign-in can be enabled in General settings.

## Use

- Wait for the replay buffer to fill, then press **F8** or choose **Save replay**. New installations save clips in `Videos\Clipper`; choose a different folder in General. Existing installations continue using their previous clips folder.
- Choose **Start recording** and **Stop recording** for a longer video. The start and stop boundaries are approximate and the last seconds may be missing.
- Use Recording to choose the display, resolution, frame rate, audio devices, replay duration and shortcut. Applying changes restarts capture and refills the replay buffer.
- Videos are queued for Google Drive. Uploads are verified against the destination, size and MD5. Interrupted uploads remain queued for retry.
- Choose or create your local clips folder under **General**, and rename the existing Google Drive upload folder under **Google Drive → Drive folder name**.
- **Automatic local cleanup is enabled for new uploads by default.** After a verified upload, Clipper checks remote and local file identity again before deleting the local copy. Turn this off in General if you want to keep local copies. The Google Drive page also provides a confirmation-gated cleanup action for previously uploaded videos; pending, changed or unverified files are kept.

## Build and test

After publishing the native engine as above, install the development tools and create a separate build:

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller pytest
.\.venv\Scripts\python.exe -m pytest -q tests
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --distpath dist\new-build --workpath build\new-build-work RocketLeagueClips.spec
```

The packaged executable is `dist\new-build\Clipper\Clipper.exe`. The build bundles the native engine and FFmpeg but does not bundle OAuth credentials. Add your own `credentials.json` beside the executable to enable Drive. Check the FFmpeg build's license before distributing binaries.

## Known limitations

- Replays end at the latest segment known to have closed before the shortcut. The final one or several seconds may be missing. Replay duration is measured on the encoded media timeline, which can diverge from wall time under load. Audio/video synchronization and long recordings need further testing.
- Windows may display a yellow capture border even when the app requests borderless capture.
- Capture performance, hardware encoding, display switching and continuity can vary with hardware, drivers, game mode and sleep/resume. Microphone speech capture needs further testing.
- Upload retries attempt to avoid duplicates, but interruptions and concurrent operations can still create them. Existing duplicates are not automatically deleted. Google Drive browser playback can differ from the original video.
- An abrupt exit may leave temporary segments or incomplete files. Review them before deleting anything.

## Privacy and local files

The project ignores local credentials, tokens, settings, upload databases, logs, recordings, test output, build products and virtual environments. Clipper stores its settings and queue under `%LOCALAPPDATA%\RocketLeagueClips`; Google tokens are stored in the current user's Windows Credential Manager. Saved videos and uploads are controlled by your settings.
