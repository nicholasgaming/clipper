# Set up Clipper

This guide walks you through running Clipper on Windows and connecting your own Google Drive. You can follow it yourself or ask an AI coding assistant, such as Codex or Claude Code, to help. Clipper records your selected display, so it can capture gameplay from many different games.

> Clipper is experimental. Replay boundaries are approximate, and the last few seconds can be missing. Try it with a recording you can afford to lose before relying on it.

## 1. Get the project and prerequisites

1. Download the source from [the Clipper GitHub repository](https://github.com/nicholasgaming/clipper) using **Code → Download ZIP**, then extract it; or clone it with Git:

   ```powershell
   git clone https://github.com/nicholasgaming/clipper.git
   cd clipper
   ```

2. Install the following if you don't already have them:
   - [Python](https://www.python.org/downloads/windows/) 3.12 or newer. During installation, enable the Python launcher and add Python to PATH if offered.
   - [.NET SDK 10](https://dotnet.microsoft.com/download/dotnet/10.0), for the Windows capture engine.
   - A Windows [FFmpeg](https://ffmpeg.org/download.html) build containing both `ffmpeg.exe` and `ffprobe.exe`. Put its `bin` directory on your PATH, or install the `Gyan.FFmpeg` package with Windows Package Manager.
3. Open a **new PowerShell window** in the extracted `clipper` folder. You can right-click the folder in File Explorer and choose **Open in Terminal**.
4. Check the tools:

   ```powershell
   py -3 --version
   dotnet --version
   ffmpeg -version
   ffprobe -version
   ```

   The Python version should be 3.12 or newer and the .NET SDK should be version 10. If a command is not found, check the installation and PATH, then open a new terminal. Clipper can also find a Gyan.FFmpeg WinGet installation in its standard package location even if `ffmpeg` is not on PATH.

## 2. Optional: check Google storage and student offers

Clipper can record locally without connecting Drive; uploads wait until Drive is connected. Your Google account's storage is shared by Drive, Gmail and Google Photos, so videos use some of the space available to all three. Google's standard free account includes up to **15 GB total**. You do not need a paid Google plan to use Clipper.

**Student offer checked October 31, 2026:** Google offers eligible higher-education students a **12-month Google AI Plus trial with 400 GB of total storage** in many supported regions outside the United States. In the U.S., eligible students may instead receive a **12-month Google AI Pro trial with 5 TB**. The plan includes Google AI features as well as cloud storage. The current offer must be redeemed by **December 31, 2026**; countries, eligibility and terms can change. Google has other paid storage and AI plans, including a **5 TB Google AI Pro** tier in supported markets. [Google's student announcement](https://blog.google/innovation-and-ai/products/gemini-app/student-offer-google-ai/) and [Google One plans](https://one.google.com/about/plans) have details.

To check whether you qualify:

1. Visit [Google's student offers](https://one.google.com/ai-student) and sign in to your personal Google account. Use the same account you intend to connect to Clipper.
2. Check the offer shown for your location and institution. Google generally requires eligible higher-education enrollment, age 18 or older, and student verification through SheerID. See the [eligibility details](https://support.google.com/googleone/answer/17422238).
3. Review the actual storage, duration, price and conditions shown on your account before accepting. Google generally requires a valid payment method. Unless cancelled before the trial ends, it normally converts to a paid plan, except where local law requires additional consent. See the [student offer terms](https://one.google.com/offer/studentoffer8).
4. If you already have a Google One plan, review Google's switching rules and your current subscription before changing anything. Your available offer and storage can differ by country and account. Set a reminder before the renewal date if you don't want the paid plan.

If you cancel and your account is over its remaining storage limit, Google says you cannot add new files until you free space or obtain more storage. Plan where to keep your clips before the trial ends.

This offer is provided by Google, not Clipper. The AI assistant helping with setup should leave student verification, subscriptions and payment decisions to you.

## 3. Create your own Google Drive credentials

A Google Cloud project and a **Desktop app OAuth client** are needed for Drive uploads. Each person should use their own client; this repository does not contain one. You can continue with local recording and connect Drive later.

1. Open the [Google Cloud console](https://console.cloud.google.com/) and create or select a project.
2. In **APIs & Services → Library**, find and enable **Google Drive API** for that project.
3. Open **Google Auth platform** and configure the consent screen. Choose **External** for a personal Google account, fill in the required app and contact information, and add the Google account you will use to **Audience → Test users** while the app is in testing.
4. Under **Clients**, create an OAuth client and choose **Desktop app** as its application type. Download the client JSON and rename it `credentials.json`.
5. Put `credentials.json` in the project folder next to `run_app.py`. If you build a packaged application, put your own file next to `Clipper.exe` instead.
6. Keep this JSON private. Do not paste it into a chat, commit it, or upload it to GitHub. The app uses the `drive.file` scope and stores its Google authorization token in Windows Credential Manager.

For Google's current console instructions, see the [Google Drive Python quickstart](https://developers.google.com/workspace/drive/api/quickstart/python). OAuth apps in testing may require you to sign in again after seven days.

## 4. Install and start Clipper

Run these commands in PowerShell from the project folder:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
dotnet publish .\native-capture\RocketLeagueCaptureEngine\RocketLeagueCaptureEngine.csproj -c Release -r win-x64 --self-contained true -o .\native-capture\RocketLeagueCaptureEngine\publish
.\.venv\Scripts\python.exe .\run_app.py
```

The first native build downloads its NuGet dependencies. After that, use the last command to start Clipper again. Its window can be closed while the app continues running in the system tray; choose **Exit** from the tray menu to stop it. You can enable startup with Windows under **General**.

To connect Drive, select **Google Drive → Connect Drive**, then complete the Google sign-in and consent in your browser. Use the same account for which you enabled the student offer, if applicable. If you haven't set up credentials, recordings remain local and uploads wait for authorization.

## 5. Save your first clip

1. In **Recording**, select the display and audio device you want. Choose the replay length, shortcut, frame rate and resolution, then select **Apply changes** if you made changes.
2. Wait for the replay buffer to fill. Start a game on the selected display, then press **F8** or click **Save replay**. A notification reports whether the clip was saved.
3. Open **Local clips** in the sidebar and play the file. New installations use `Videos\Clipper` unless you choose a different folder. Older installations keep their previous folder.
4. If Drive is connected, check **Google Drive → Upload activity** for its upload status. An upload is verified before it is marked complete.
5. Check **General → Free up space automatically**. This is enabled for new uploads by default and removes a local video after its Drive upload and local identity have been verified. Turn it off if you want to keep local copies. If uploads are not verified, the app keeps the local files.

For longer recordings, use **Start recording** and **Stop recording** on the Capture page. Both replay and longer-recording boundaries are approximate.

## Ask an AI assistant to help

Open the downloaded project folder in Codex, Claude Code, or another coding assistant with access to your Windows computer. You can paste this request:

> Help me set up Clipper on this Windows PC. Read `AGENTS.md` and `SETUP.md`, check my prerequisites, guide me through creating my own Google Drive OAuth client, build the native capture engine, and help me test a short replay. Ask me to handle Google sign-in, student verification, and subscription choices myself. Never share or commit credentials or tokens.

An assistant can check commands, explain errors, help install missing prerequisites and build the project. You remain in control of Google sign-in, the downloaded OAuth file, verification and any payment or subscription choices. Follow your assistant's own permissions and approval prompts.

## Troubleshooting

- **A command is not found:** Check the prerequisite installation and PATH, then reopen PowerShell. For FFmpeg, verify both `ffmpeg.exe` and `ffprobe.exe` are available.
- **Credentials file not found:** Put your own Desktop OAuth JSON at the location in step 3 and name it exactly `credentials.json`. A web-client JSON is not accepted.
- **Google sign-in fails or expires:** Confirm the Drive API is enabled for the correct project and that your personal Google account is listed as a test user. Testing credentials can expire after seven days; reconnect from the Google Drive page.
- **No clip yet:** Make sure capture is running, the selected display is correct, and the replay buffer has had time to fill. Check Clipper's status and notifications.
- **Not enough storage:** Check both the local clips drive and your Google account's shared Drive/Gmail/Photos storage. Review pending uploads before making space.

The [README](README.md) includes build and test commands and the full list of known limitations.
