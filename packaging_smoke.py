"""Opt-in offline verification of a built executable: --self-test OUTPUT_DIR."""
import functools
import http.server
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import traceback


def run(directory):
    target = Path(directory).resolve()
    target.mkdir(parents=True, exist_ok=True)
    result = {}
    window = server = None
    try:
        # No installed Python, ffmpeg, or Node on PATH during the packaged test.
        os.environ['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32')
        from PySide6.QtWidgets import QApplication
        from app import App, STYLE, TrackCard
        from downloader import tool_path
        qt = QApplication.instance() or QApplication([])
        qt.setStyle('Fusion')
        qt.setStyleSheet(STYLE)
        window = App()
        window.show()
        qt.processEvents()
        window.grab().save(str(target / 'window.png'))
        for tool, flag in [('yt-dlp', '--version'), ('ffmpeg', '-version'), ('ffprobe', '-version'), ('node', '--version')]:
            output = subprocess.run([tool_path(tool), flag], capture_output=True, text=True,
                timeout=30, creationflags=subprocess.CREATE_NO_WINDOW, check=True)
            result[tool] = output.stdout.splitlines()[0]
        subprocess.run([tool_path('ffmpeg'), '-hide_banner', '-loglevel', 'error', '-y',
            '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1', str(target / 'sample.wav')],
            capture_output=True, check=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0),
            functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(target)))
        # Windowed executables have no stderr for the HTTP server's default logger.
        server.RequestHandlerClass = functools.partial(QuietHandler, directory=str(target))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        item = TrackCard(window, f'http://127.0.0.1:{server.server_port}/sample.wav', target / 'audio', '192 kbps MP3')
        window.items.append(item)
        window.cards.insertWidget(window.cards.count() - 1, item)
        item.download_button.click()
        deadline = time.monotonic() + 90
        while window.active and time.monotonic() < deadline:
            qt.processEvents()
            time.sleep(.01)
        assert item.state == 'Complete', window.log.toPlainText()
        assert item.file and Path(item.file).is_file()
        probe = subprocess.run([tool_path('ffprobe'), '-v', 'error', '-show_entries',
            'stream=codec_name,bit_rate', '-of', 'json', item.file], capture_output=True,
            text=True, timeout=15, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        stream = json.loads(probe.stdout)['streams'][0]
        assert stream['codec_name'] == 'mp3' and stream['bit_rate'] == '192000', stream
        result.update(ok=True, output=item.file, stream=stream)
        qt.processEvents()
        window.grab().save(str(target / 'completed.png'))
    except Exception:
        result.update(ok=False, error=traceback.format_exc())
    finally:
        if window:
            (target / 'app.log').write_text(window.log.toPlainText(), encoding='utf-8')
            window.close()
        if server:
            server.shutdown()
        (target / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return 0 if result.get('ok') else 1


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass
