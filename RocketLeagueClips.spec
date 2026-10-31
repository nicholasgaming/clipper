# PyInstaller one-folder build. The OAuth client JSON and tokens are never bundled.
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files
from rocket_league_clips.capture import find_ffmpeg

ffmpeg = Path(find_ffmpeg())
ffprobe = ffmpeg.with_name("ffprobe.exe")
license_file = ffmpeg.parent.parent / "LICENSE"
datas = collect_data_files("googleapiclient.discovery_cache.documents")
native_engine = Path("native-capture/RocketLeagueCaptureEngine/publish").resolve()
if not (native_engine / "RocketLeagueCaptureEngine.exe").is_file():
    raise RuntimeError("Publish the native capture engine before packaging the app.")
datas.append((str(native_engine), "native-capture"))
if license_file.exists():
    datas.append((str(license_file), "ffmpeg-license"))

a = Analysis(
    ["run_app.py"],
    pathex=[],
    binaries=[(str(ffmpeg), "."), (str(ffprobe), ".")],
    datas=datas,
    hiddenimports=["keyring.backends.Windows"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
# The build host has a Poppler directory on PATH with a different ICU ABI.
# Qt expects Windows' own icuuc.dll; bundling Poppler's copy breaks QtCore.
a.binaries = [item for item in a.binaries if "poppler\\library\\bin" not in item[1].lower()]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Clipper", console=False, icon="assets/clipper.ico")
coll = COLLECT(exe, a.binaries, a.datas, name="Clipper")
