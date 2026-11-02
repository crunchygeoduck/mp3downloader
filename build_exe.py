"""Build the Windows portable executable from staged packaging/tools files."""
from pathlib import Path
import os
import subprocess
import sys

root = Path(__file__).resolve().parent
import PySide6
qt = Path(PySide6.__file__).parent
environment = os.environ.copy()
# Do not accidentally collect DLLs from unrelated applications on the host PATH.
environment['PATH'] = os.pathsep.join([str(Path(sys.executable).parent),
    str(Path(os.environ['SystemRoot']) / 'System32'), os.environ['SystemRoot']])
for name in ('yt-dlp', 'ffmpeg', 'ffprobe', 'node'):
    if not (root / 'packaging' / 'tools' / (name + '.exe')).is_file():
        raise SystemExit(f'Missing packaging/tools/{name}.exe')
subprocess.run([
    sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
    '--onefile', '--windowed', '--name', 'YT-SC Downloader',
    '--icon', str(root / 'packaging' / 'app.ico'),
    '--add-data', str(root / 'packaging' / 'tools') + ':tools',
    '--add-data', str(root / 'packaging' / 'licenses') + ':licenses',
    '--add-data', str(root / 'README.md') + ':.',
    '--add-binary', str(qt / 'vcruntime140.dll') + ':.',
    '--add-binary', str(qt / 'vcruntime140_1.dll') + ':.',
    '--exclude-module', 'tkinter', '--exclude-module', 'PySide6.QtWebEngineCore',
    str(root / 'app.py'),
], cwd=root, env=environment, check=True)
