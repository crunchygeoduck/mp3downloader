# Third-party components

The portable build includes the following independent projects. Their copyrights and licenses remain with their respective authors. License texts staged with this build are in [packaging/licenses](packaging/licenses).

| Component | Bundled version | Project / source | License information |
| --- | --- | --- | --- |
| Python | 3.12 | https://www.python.org/downloads/source/ | https://docs.python.org/3/license.html |
| Qt / PySide6 / Shiboken | 6.12.0 | https://code.qt.io/ | LGPL v3; see Qt-LGPL-3.0.txt and upstream license notices |
| yt-dlp | 2026.10.26 | https://github.com/yt-dlp/yt-dlp/tree/2026.10.26 | See yt-dlp-LICENSE.txt and yt-dlp-THIRD-PARTY.txt for standalone executable dependencies |
| FFmpeg / ffprobe | 8.1.1 full build | https://www.gyan.dev/ffmpeg/builds/ and https://ffmpeg.org/download.html | GPL build; see FFmpeg-LICENSE.txt, build provider's configuration and source information |
| Node.js | 24.14.1 | https://nodejs.org/dist/v24.14.1/ | See Node-LICENSE.txt, including bundled dependency notices |
| PyInstaller bootloader | 6.22.3 | https://github.com/pyinstaller/pyinstaller/tree/v6.22.3 | GPL with bootloader exception; https://pyinstaller.org/en/stable/license.html |

The application source and build script are provided so the UI can be rebuilt against replacement Qt libraries. Third-party executable components are staged independently in `packaging/tools` during a build. These notices do not grant a new license to any third-party component.
