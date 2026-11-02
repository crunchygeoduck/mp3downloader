# Build the Windows executable

The tested build uses 64-bit Python 3.12 on Windows, Qt/PySide6 6.12.0, PyInstaller 6.22.3, yt-dlp 2026.10.26, FFmpeg 8.1.1 full build from Gyan, and Node.js 24.14.1.

## Prepare

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
New-Item -ItemType Directory -Force packaging\tools
```

Place these Windows x64 executables in `packaging/tools`:

- `yt-dlp.exe` from the [2026.10.26 release](https://github.com/yt-dlp/yt-dlp/releases/tag/2026.10.26). Verify its SHA-256 against that release's `SHA2-256SUMS`.
- `ffmpeg.exe` and `ffprobe.exe` from [Gyan's FFmpeg builds](https://www.gyan.dev/ffmpeg/builds/).
- `node.exe` from the [Node.js 24.14.1 distribution](https://nodejs.org/dist/v24.14.1/).

The licenses for the bundled versions are checked in under `packaging/licenses`. Update these when updating tools. The large tool binaries are intentionally ignored by Git. For source-version tests, also make FFmpeg/ffprobe and Node available on PATH.

## Verify and build

```powershell
.\.venv\Scripts\python.exe -m unittest test_queue -v
.\.venv\Scripts\python.exe build_exe.py
```

The result is `dist/YT-SC Downloader.exe`. The builder uses a restricted PATH and explicitly bundles Qt's compatible Visual C++ runtimes to avoid collecting incompatible DLLs from unrelated software.

## Test the packaged executable

```powershell
& '.\dist\YT-SC Downloader.exe' --self-test "$PWD\test-output\packaged-check"
```

Wait for `result.json` in that output directory. This opt-in check starts the UI, verifies every bundled tool, serves a generated tone from a local HTTP server, converts it to 192 kbps MP3, and probes the result. It removes installed runtimes from PATH during the check. It also saves screenshots and the app log. A successful result contains `"ok": true`.

Setup.cmd updates the source environment only. To update a distributed executable, stage the new tools and rebuild it.
