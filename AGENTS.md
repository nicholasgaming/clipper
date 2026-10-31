# Guidance for AI coding assistants

Clipper is an experimental Windows screen-recording and instant-replay app for games and other display content. Follow [SETUP.md](SETUP.md) for the human walkthrough and [README.md](README.md) for architecture, build and limitations.

When helping a user set it up:

- Check the actual platform and available tools first. The capture engine requires Windows, Python 3.12+, .NET SDK 10, and FFmpeg/ffprobe. Explain any missing prerequisites and help install them within the user's instructions and your own tool permissions.
- Use the user's own Google Cloud project and Desktop OAuth client. Guide the user through Google Cloud setup, browser sign-in and consent; let them handle authentication, student verification and subscription or payment decisions.
- Treat `credentials.json`, OAuth client secrets, tokens, Google account data and local recordings as private. Do not ask the user to paste secrets into chat, print their contents, commit them, or upload them to a repository. Keep existing `.gitignore` protections.
- Build the native engine and run the app using the commands in SETUP.md. Do not overwrite existing installations or credentials when preparing a packaged build.
- Explain the replay timing limitation and automatic deletion after verified upload. Help the user check their settings and test an expendable clip; don't claim a recording or upload worked unless it was actually verified.
- Google's student trials, regions, storage amounts, dates and billing terms may change. Link to the official student offer and let the user check the current eligibility and terms. Do not claim everyone gets a free plan or enroll on their behalf.
- Preserve existing clips, settings, Google credentials and upload queue when making changes. Legacy internal names identify existing data and do not limit which games Clipper can capture.
