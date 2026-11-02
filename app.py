"""Native desktop audio downloader with a sequential, cancellable queue."""
import codecs
import json
import math
import re
import shutil
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QPoint, QProcess, QProcessEnvironment, QSettings, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon, QPainter, QPixmap, QPolygon
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QProgressBar,
    QPushButton, QScrollArea, QSizePolicy, QSplitter, QVBoxLayout, QWidget)
from downloader import parse_links, download_command, preview_command, tool_path

PURPLE = '#6936cf'
STYLE = '''
QWidget { font-family: "Segoe UI"; font-size: 14px; color: #202027; }
QMainWindow, QWidget#base { background: #f6f6f9; }
QFrame#panel, QFrame#card { background: white; border: 1px solid #e4e3e9; border-radius: 12px; }
QFrame#drop { background: #fcfaff; border: 2px dashed #a98adc; border-radius: 12px; }
QLabel { background: transparent; border: none; }
QLabel#muted { color: #6b6774; font-size: 13px; }
QLabel#heading { font-size: 23px; font-weight: 650; }
QPushButton { background: white; border: 1px solid #dddbe3; border-radius: 8px; padding: 10px 13px; }
QPushButton:hover { background: #f2ecfc; border-color: #b598e3; }
QPushButton:pressed { background: #e8dcfa; }
QPushButton:focus, QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border: 2px solid #8e62dc; }
QPushButton:disabled { color: #aaa5b1; background: #f6f5f8; }
QPushButton#primary { color: white; background: #6936cf; border: 1px solid #6936cf; font-weight: 600; }
QPushButton#primary:hover { background: #7c48e0; }
QPushButton#primary:disabled { background: #ebe5f5; color: #80758e; border-color: #e1d9ec; }
QPushButton#trackMenu { background: #f0e9fc; color: #5424b3; border: 1px solid #d8c7f0; padding: 0; font-size: 30px; font-weight: 700; }
QPushButton#trackMenu:hover { background: #e3d5fa; border-color: #9566d8; }
QPushButton#trackMenu:focus { border: 2px solid #6936cf; }
QPushButton#quiet { color: #6936cf; border: none; background: transparent; padding: 7px; }
QLineEdit, QComboBox { background: white; border: 1px solid #dddbe3; border-radius: 7px; padding: 10px; }
QComboBox QAbstractItemView { background: white; selection-background-color: #ede4fc; selection-color: #202027; }
QPlainTextEdit#links { background: white; border: 1px solid #e1d5f3; border-radius: 7px; padding: 7px; }
QPlainTextEdit#console { background: #23262e; color: #dce5f0; border: none; border-radius: 8px; padding: 10px; font-family: Consolas; font-size: 12px; }
QProgressBar { background: #eae8ee; border: none; border-radius: 5px; min-height: 10px; max-height: 10px; }
QProgressBar::chunk { background: #6936cf; border-radius: 5px; }
QScrollArea { border: none; background: white; }
QWidget#queueContents { background: white; }
QScrollBar:vertical { background: #f5f3f8; width: 9px; margin: 0; }
QScrollBar::handle:vertical { background: #d5ccdf; min-height: 28px; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QMenu { background: white; border: 1px solid #e4e3e9; padding: 6px; }
QMenu::item { padding: 8px 20px; }
QMenu::item:selected { background: #f0e9fc; }
'''


def label(text, name=None):
    item = QLabel(text)
    item.setTextFormat(Qt.TextFormat.PlainText)
    if name:
        item.setObjectName(name)
    return item


def button(text, callback, name=None):
    item = QPushButton(text)
    item.setCursor(Qt.CursorShape.PointingHandCursor)
    item.clicked.connect(callback)
    if name:
        item.setObjectName(name)
    return item


def panel(layout):
    item = QFrame()
    item.setObjectName('panel')
    item.setLayout(layout)
    return item


class TrackCard(QFrame):
    def __init__(self, window, url, folder, quality):
        super().__init__()
        self.window, self.url, self.folder, self.quality = window, url, folder, quality
        self.state, self.file, self.cancelled = 'Queued', None, False
        self.setObjectName('card')
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 18, 16, 18)
        outer.setSpacing(12)
        layout = QHBoxLayout()
        outer.addLayout(layout)
        layout.setSpacing(16)
        self.art = button('SC' if 'soundcloud.com' in url else 'YT', self.play)
        self.art.setFixedSize(116, 116)
        self.art.setStyleSheet('background: #eee7fa; color: #6936cf; font-size: 25px; font-weight: 700; border: none; border-radius: 9px;')
        self.art.setToolTip('Open original track; play MP3 after download')
        self.art.setAccessibleName('Play track or open original')
        layout.addWidget(self.art)
        details = QVBoxLayout()
        details.setSpacing(9)
        self.title = label(url)
        self.title.setToolTip(url)
        self.title.setStyleSheet('font-size: 16px; font-weight: 600;')
        self.title.setWordWrap(True)
        self.title.setMinimumWidth(100)
        details.addWidget(self.title)
        self.subtitle = label(('SoundCloud' if 'soundcloud.com' in url else 'YouTube') + ' · ' + quality, 'muted')
        self.subtitle.setWordWrap(True)
        details.addWidget(self.subtitle)
        self.status = label('Queued')
        self.status.setWordWrap(True)
        self.status.setStyleSheet('color: #6936cf;')
        details.addWidget(self.status)
        progress_row = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setValue(0)
        progress_row.addWidget(self.progress, 1)
        self.percent = label('—', 'muted')
        self.percent.setFixedWidth(42)
        self.percent.setAlignment(Qt.AlignmentFlag.AlignRight)
        progress_row.addWidget(self.percent)
        details.addLayout(progress_row)
        card_actions = QHBoxLayout()
        self.download_button = button('Download', lambda: window.download_item(self), 'primary')
        self.cancel_button = button('Cancel', lambda: window.cancel_item(self))
        self.cancel_button.setToolTip('Cancel this item')
        self.remove_button = button('Remove from Queue', lambda: window.remove(self))
        self.remove_button.setToolTip('Remove this card without deleting files')
        self.remove_button.hide()
        card_actions.addWidget(self.download_button)
        card_actions.addWidget(self.cancel_button)
        card_actions.addWidget(self.remove_button)
        card_actions.addStretch()
        outer.addLayout(card_actions)
        layout.addLayout(details, 1)
        tools = QVBoxLayout()
        self.more = button('⋮', self.menu, 'trackMenu')
        self.more.setAccessibleName('Track options')
        self.more.setToolTip('Track options')
        self.more.setFixedSize(44, 44)
        tools.addWidget(self.more)
        tools.addStretch()
        layout.addLayout(tools)

    def set_state(self, state):
        self.state = state
        self.status.setText(state)
        self.download_button.setEnabled(state in {'Queued', 'Failed', 'Cancelled'})
        self.download_button.setText('Retry' if state in {'Failed', 'Cancelled'} else 'Download')
        self.cancel_button.setEnabled(state not in {'Complete', 'Failed', 'Cancelled', 'Cancelling…'})
        self.remove_button.setVisible(state == 'Cancelled')
        active = state in {'Fetching details…', 'Converting…', 'Cancelling…'}
        self.progress.setRange(0, 0 if active else 100)
        if active:
            self.percent.setText('…')
        if state in {'Complete', 'Failed', 'Cancelled'}:
            self.cancel_button.setEnabled(False)
            self.progress.setValue(100 if state == 'Complete' else 0)
            self.percent.setText('100%' if state == 'Complete' else '—')
            self.status.setStyleSheet('color: ' + ('#23774b' if state == 'Complete' else '#a33746' if state == 'Failed' else '#6b6774') + ';')
        self.window.update_count()

    def metadata(self, info):
        if not isinstance(info, dict):
            raise ValueError('Invalid track metadata')
        self.title.setText(str(info.get('title') or self.url))
        try:
            value = float(info.get('duration') or 0)
            seconds = int(value) if math.isfinite(value) and value > 0 else 0
        except (ValueError, TypeError, OverflowError):
            seconds = 0
        duration = (f'{seconds // 3600}:{seconds % 3600 // 60:02}:{seconds % 60:02}'
                    if seconds >= 3600 else f'{seconds // 60}:{seconds % 60:02}') if seconds else 'Unknown duration'
        source = 'SoundCloud' if 'soundcloud.com' in self.url else 'YouTube'
        self.subtitle.setText(f"{source} · {info.get('uploader') or 'Audio'} · {duration}\n{self.quality}")
        if isinstance(info.get('thumbnail'), str) and info['thumbnail']:
            self.window.fetch_art(self, info['thumbnail'])

    def play(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.file)) if self.file and Path(self.file).exists() else QUrl(self.url))

    def menu(self):
        menu = QMenu(self)
        menu.addAction('Open original link', lambda: QDesktopServices.openUrl(QUrl(self.url)))
        menu.addAction('Open download folder', lambda: self.window.open_folder(self.folder))
        menu.addAction('Copy link', lambda: QApplication.clipboard().setText(self.url))
        if self.state in {'Failed', 'Cancelled'}:
            menu.addAction('Retry', lambda: self.window.retry(self))
        if self.state in {'Complete', 'Failed', 'Cancelled', 'Queued', 'Waiting to download'}:
            menu.addAction('Remove from queue', lambda: self.window.remove(self))
        menu.exec(self.more.mapToGlobal(self.more.rect().bottomLeft()))


class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.items, self.active, self.process = [], None, None
        self.buffer, self.closing = '', False
        self.preview_pending = []
        self.preview_process = None
        self.preview_item = None
        self.preview_timeout_ms = 45000
        self.settings = QSettings('LocalAudioTools', 'YTSCDownloader')
        self.network = QNetworkAccessManager(self)
        self.setWindowTitle('YT & SC Downloader')
        self.resize(1140, 760)
        self.setMinimumSize(950, 740)
        self.setAcceptDrops(True)
        icon = QPixmap(32, 32)
        icon.fill(QColor(PURPLE))
        painter = QPainter(icon)
        painter.setPen(Qt.GlobalColor.white)
        painter.setFont(QFont('Segoe UI', 20))
        painter.drawText(icon.rect(), Qt.AlignmentFlag.AlignCenter, '↓')
        painter.end()
        self.setWindowIcon(QIcon(icon))
        base = QWidget()
        base.setObjectName('base')
        self.setCentralWidget(base)
        outer = QVBoxLayout(base)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)
        self.split = QSplitter(Qt.Orientation.Vertical)
        outer.addWidget(self.split)
        top = QWidget()
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(14)
        self.split.addWidget(top)
        left = QVBoxLayout()
        left.setContentsMargins(20, 20, 20, 20)
        left.setSpacing(12)
        controls = panel(left)
        controls.setFixedWidth(420)
        top_layout.addWidget(controls)
        drop = QFrame()
        drop.setObjectName('drop')
        drop.setMinimumHeight(232)
        drop_layout = QVBoxLayout(drop)
        arrow = label('↓')
        arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        arrow.setStyleSheet('color: #6936cf; font-size: 32px; font-weight: 500;')
        drop_layout.addWidget(arrow)
        heading = label('Paste YouTube or SoundCloud links')
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setStyleSheet('font-size: 16px; font-weight: 600;')
        drop_layout.addWidget(heading)
        hint = label('or drag & drop links anywhere', 'muted')
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_layout.addWidget(hint)
        self.links = QPlainTextEdit()
        self.links.setObjectName('links')
        self.links.setPlaceholderText('https://…\nOne link per line')
        self.links.setAccessibleName('YouTube and SoundCloud links')
        self.links.setFixedHeight(72)
        drop_layout.addWidget(self.links)
        paste = button('Paste from clipboard', self.paste, 'quiet')
        drop_layout.addWidget(paste)
        left.addWidget(drop)
        left.addWidget(label('Quality'))
        self.quality = QComboBox()
        self.quality.addItems(['320 kbps MP3', '256 kbps MP3', '192 kbps MP3', '128 kbps MP3', 'Best quality MP3'])
        self.quality.setCurrentText(self.settings.value('quality', '320 kbps MP3'))
        self.quality.setAccessibleName('MP3 quality')
        left.addWidget(self.quality)
        left.addWidget(label('Save to'))
        folder_row = QHBoxLayout()
        self.folder = QLineEdit(self.settings.value('folder', str(Path.home() / 'Downloads' / 'YouTube MP3')))
        self.folder.setAccessibleName('Save folder')
        folder_row.addWidget(self.folder, 1)
        folder_row.addWidget(button('Browse', self.browse))
        left.addLayout(folder_row)
        enqueue_actions = QHBoxLayout()
        self.add_button = button('Add to Queue', lambda: self.add_links())
        self.download_now_button = button('Download Now', lambda: self.add_links(download=True), 'primary')
        enqueue_actions.addWidget(self.add_button)
        enqueue_actions.addWidget(self.download_now_button)
        left.addLayout(enqueue_actions)
        actions = QHBoxLayout()
        self.cancel_all_button = button('×   Cancel all', self.cancel_all)
        self.cancel_all_button.setEnabled(False)
        actions.addWidget(self.cancel_all_button)
        actions.addWidget(button('Open folder', lambda: self.open_folder()))
        left.addLayout(actions)
        left.addStretch()
        right = QVBoxLayout()
        right.setContentsMargins(20, 20, 20, 20)
        header = QHBoxLayout()
        self.count = label('Queue (0)', 'heading')
        header.addWidget(self.count)
        header.addStretch()
        self.download_all_button = button('Download All', self.download_all, 'primary')
        self.download_all_button.setEnabled(False)
        header.addWidget(self.download_all_button)
        header.addWidget(button('Clear finished', self.clear_finished, 'quiet'))
        right.addLayout(header)
        self.summary = label('Ready for your next track', 'muted')
        right.addWidget(self.summary)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        contents = QWidget()
        contents.setObjectName('queueContents')
        self.cards = QVBoxLayout(contents)
        self.cards.setContentsMargins(0, 12, 4, 0)
        self.cards.setSpacing(12)
        self.empty = label('Your audio, one queue.\n\nAdd a YouTube video or SoundCloud track\nto get started.', 'muted')
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setMinimumHeight(260)
        self.cards.addWidget(self.empty)
        self.cards.addStretch()
        scroll.setWidget(contents)
        right.addWidget(scroll, 1)
        top_layout.addWidget(panel(right), 1)
        console_layout = QVBoxLayout()
        console_layout.setContentsMargins(14, 10, 14, 14)
        console_header = QHBoxLayout()
        console_header.addWidget(label('Log Console'))
        self.log_hint = label('Ready', 'muted')
        console_header.addWidget(self.log_hint, 1)
        console_header.addWidget(button('Clear log', lambda: self.log.clear(), 'quiet'))
        self.toggle = button('Collapse', self.toggle_log, 'quiet')
        console_header.addWidget(self.toggle)
        console_layout.addLayout(console_header)
        self.log = QPlainTextEdit()
        self.log.setObjectName('console')
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(3000)
        self.log.setMinimumHeight(90)
        console_layout.addWidget(self.log)
        self.console_panel = panel(console_layout)
        self.split.addWidget(self.console_panel)
        self.split.setSizes([510, 190])
        self.split.setChildrenCollapsible(False)
        self.write_log('Ready. Add YouTube videos or full SoundCloud track links.')

    def paste(self):
        text = QApplication.clipboard().text().strip()
        if text:
            self.links.appendPlainText(text)
            self.links.setFocus()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        mime = event.mimeData()
        text = '\n'.join(url.toString() for url in mime.urls()) if mime.hasUrls() else mime.text()
        self.links.appendPlainText(text.strip())
        event.acceptProposedAction()

    def browse(self):
        path = QFileDialog.getExistingDirectory(self, 'Save MP3 files to', self.folder.text())
        if path:
            self.folder.setText(path)

    def open_folder(self, path=None):
        try:
            folder = Path(path or self.folder.text()).expanduser()
            folder.mkdir(parents=True, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder.resolve())))
        except OSError as exc:
            QMessageBox.warning(self, 'Cannot open folder', str(exc))

    def add_links(self, download=False):
        try:
            links = parse_links(self.links.toPlainText())
            if not self.folder.text().strip():
                raise ValueError('Choose a save folder.')
            folder = Path(self.folder.text()).expanduser().resolve()
            folder.mkdir(parents=True, exist_ok=True)
            for tool in ('ffmpeg', 'ffprobe', 'node'):
                if not tool_path(tool):
                    raise ValueError(f'{tool} is missing. See README.md.')
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, 'Check your links or folder', str(exc))
            return
        self.settings.setValue('folder', str(folder))
        self.settings.setValue('quality', self.quality.currentText())
        for url in links:
            existing = next((item for item in self.items if item.url == url and item.state not in {'Complete', 'Failed', 'Cancelled'}), None)
            if existing:
                self.write_log('Already queued: ' + url)
                if download and existing.state == 'Queued':
                    existing.set_state('Waiting to download')
                continue
            item = TrackCard(self, url, folder, self.quality.currentText())
            self.items.append(item)
            self.cards.insertWidget(self.cards.count() - 1, item)
            if download:
                item.set_state('Waiting to download')
            self.write_log('Added: ' + url)
            if not download:
                self.preview_pending.append(item)
                item.status.setText('Queued · loading preview…')
        self.links.clear()
        self.update_count()
        self.start_next()
        self.start_preview()

    def start_preview(self):
        if self.preview_process or self.closing:
            return
        while self.preview_pending:
            item = self.preview_pending.pop(0)
            if item in self.items and item.state == 'Queued':
                break
        else:
            return
        proc = QProcess(self)
        self.preview_process, self.preview_item = proc, item
        env = QProcessEnvironment.systemEnvironment()
        env.insert('PYTHONIOENCODING', 'utf-8')
        proc.setProcessEnvironment(env)
        timer = QTimer(proc)
        timer.setSingleShot(True)
        timer.timeout.connect(proc.kill)

        def finish(code, *_):
            if self.preview_process is not proc:
                return
            timer.stop()
            if item in self.items and item.state == 'Queued' and self.preview_item is item:
                try:
                    if code != 0:
                        raise ValueError('Preview lookup failed')
                    info = json.loads(bytes(proc.readAllStandardOutput()).decode('utf-8'))
                    if not isinstance(info, dict):
                        raise ValueError('Invalid preview metadata')
                    item.metadata(info)
                    item.status.setText('Queued')
                except (ValueError, TypeError):
                    item.status.setText('Queued · preview unavailable')
                    self.write_log('Preview unavailable; you can still download: ' + item.url)
            self.preview_process = self.preview_item = None
            proc.deleteLater()
            QTimer.singleShot(0, self.start_preview)

        proc.finished.connect(finish)
        proc.errorOccurred.connect(lambda error: finish(-1) if error == QProcess.ProcessError.FailedToStart else None)
        command = preview_command(item.url)
        proc.start(command[0], command[1:])
        timer.start(self.preview_timeout_ms)

    def cancel_preview(self, item):
        self.preview_pending = [pending for pending in self.preview_pending if pending is not item]
        if self.preview_item is item and self.preview_process:
            self.preview_item = None
            self.preview_process.kill()

    def download_item(self, item):
        if item.state in {'Failed', 'Cancelled'}:
            self.retry(item)
        elif item.state == 'Queued':
            item.set_state('Waiting to download')
            self.start_next()

    def download_all(self):
        # Only release the current queue; links added later stay queued.
        for item in self.items:
            if item.state == 'Queued':
                item.set_state('Waiting to download')
        self.start_next()

    def update_count(self):
        self.count.setText(f'Queue ({len(self.items)})')
        pending = sum(item.state not in {'Complete', 'Failed', 'Cancelled'} for item in self.items)
        done = sum(item.state == 'Complete' for item in self.items)
        self.summary.setText(f'{pending} remaining · {done} completed' if self.items else 'Ready for your next track')
        self.empty.setVisible(not self.items)
        self.cancel_all_button.setEnabled(pending > 0)
        self.download_all_button.setEnabled(any(item.state == 'Queued' for item in self.items))

    def start_next(self):
        if self.active or self.closing:
            return
        item = next((i for i in self.items if i.state == 'Waiting to download'), None)
        if not item:
            self.log_hint.setText('Queued tracks ready to download' if any(i.state == 'Queued' for i in self.items) else 'Queue finished' if self.items else 'Ready')
            return
        self.active = item
        self.cancel_preview(item)
        item.set_state('Fetching details…')
        quality = '0' if item.quality.startswith('Best') else item.quality.split()[0] + 'K'
        command = download_command(item.url, item.folder, quality)
        self.buffer = ''
        self.decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
        proc = QProcess(self)
        self.process = proc
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        env = QProcessEnvironment.systemEnvironment()
        env.insert('PYTHONIOENCODING', 'utf-8')
        proc.setProcessEnvironment(env)
        proc.readyReadStandardOutput.connect(self.read_output)
        proc.finished.connect(self.finished)
        proc.errorOccurred.connect(self.process_error)
        # A cancel can arrive while QProcess is still starting, before it has a PID.
        proc.started.connect(lambda: self.stop_download(proc) if item.cancelled else None)
        proc.start(command[0], command[1:])
        self.log_hint.setText('Downloading and converting…')

    def process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.write_log('Could not start downloader: ' + self.process.errorString())
            self.finished(-1, QProcess.ExitStatus.CrashExit)

    def read_output(self):
        if not self.process:
            return
        self.buffer += self.decoder.decode(bytes(self.process.readAllStandardOutput()))
        while '\n' in self.buffer:
            line, self.buffer = self.buffer.split('\n', 1)
            self.handle_line(line.strip())

    def handle_line(self, line):
        item = self.active
        if not line or not item:
            return
        if line.startswith('APP_META:'):
            try:
                item.metadata(json.loads(line[9:]))
                self.write_log('Track: ' + item.title.text())
            except (ValueError, TypeError):
                self.write_log('Metadata could not be displayed.')
        elif line.startswith('APP_FILE:'):
            item.file = line[9:]
            self.write_log('Saved: ' + item.file)
        elif line.startswith('APP_PROGRESS:'):
            match = re.search(r'(\d+(?:\.\d+)?)%', line)
            if not item.cancelled:
                item.set_state('Downloading…')
                if match:
                    value = min(100, int(float(match.group(1))))
                    item.progress.setValue(value)
                    item.percent.setText(f'{value}%')
                else:
                    item.progress.setRange(0, 0)
                    item.percent.setText('…')
        else:
            self.write_log(line)
            if '[ExtractAudio]' in line and not item.cancelled:
                item.set_state('Converting…')

    def finished(self, code, exit_status):
        if not self.active:
            return
        self.read_output()
        if self.buffer:
            self.handle_line(self.buffer.strip())
        item = self.active
        state = 'Cancelled' if item.cancelled else 'Complete' if code == 0 else 'Failed'
        item.set_state(state)
        if state == 'Failed':
            item.status.setText('Failed — see log or retry from ⋮')
        self.write_log(state + ': ' + item.title.text())
        proc = self.process
        self.process = None
        self.active = None
        proc.deleteLater()
        if self.closing:
            self.close()
        else:
            QTimer.singleShot(0, self.start_next)

    def cancel_item(self, item):
        self.cancel_preview(item)
        if item.state in {'Queued', 'Waiting to download'}:
            item.cancelled = True
            item.set_state('Cancelled')
        elif item is self.active and not item.cancelled:
            item.cancelled = True
            item.set_state('Cancelling…')
            self.stop_download(self.process)

    def stop_download(self, proc):
        if proc is not self.process or proc.state() != QProcess.ProcessState.Running:
            return
        try:
            # Terminate ffmpeg children as well as the downloader.
            killer = subprocess.Popen(['taskkill', '/PID', str(proc.processId()), '/T', '/F'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW)
            # Reap the helper off the UI thread, including during window shutdown.
            def reap():
                try:
                    killer.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    killer.kill()
                    killer.wait()
            threading.Thread(target=reap, daemon=True).start()
        except OSError as exc:
            self.write_log(f'Could not run taskkill; stopping downloader directly: {exc}')
            proc.kill()
        # Do not leave the card stuck if taskkill fails or exits without killing it.
        QTimer.singleShot(3000, lambda: proc.kill() if self.process is proc else None)

    def cancel_all(self):
        for item in self.items:
            self.cancel_item(item)

    def retry(self, item):
        if item not in self.items or item.state not in {'Failed', 'Cancelled'}:
            return
        item.cancelled = False
        item.file = None
        item.cancel_button.setEnabled(True)
        item.status.setStyleSheet('color: #6936cf;')
        item.progress.setValue(0)
        item.set_state('Waiting to download')
        self.start_next()

    def remove(self, item):
        if item is self.active or item not in self.items:
            return
        self.cancel_preview(item)
        self.items.remove(item)
        self.cards.removeWidget(item)
        item.hide()
        item.deleteLater()
        self.update_count()

    def clear_finished(self):
        for item in list(self.items):
            if item.state in {'Complete', 'Failed', 'Cancelled'}:
                self.remove(item)

    def fetch_art(self, item, url):
        if QUrl(url).scheme() not in {'https', 'http'}:
            return
        request = QNetworkRequest(QUrl(url))
        request.setTransferTimeout(10000)
        reply = self.network.get(request)
        def ready():
            if item in self.items and reply.error() == reply.NetworkError.NoError:
                pixmap = QPixmap()
                if pixmap.loadFromData(bytes(reply.readAll())):
                    crop = pixmap.scaled(116, 116, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
                    crop = crop.copy((crop.width() - 116) // 2, (crop.height() - 116) // 2, 116, 116)
                    painter = QPainter(crop)
                    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                    painter.setPen(Qt.GlobalColor.white)
                    painter.setBrush(QColor(20, 16, 30, 170))
                    painter.drawEllipse(39, 39, 38, 38)
                    painter.setBrush(Qt.GlobalColor.white)
                    painter.drawPolygon(QPolygon([QPoint(54, 48), QPoint(54, 68), QPoint(68, 58)]))
                    painter.end()
                    item.art.setText('')
                    item.art.setIcon(QIcon(crop))
                    item.art.setIconSize(item.art.size())
            reply.deleteLater()
        reply.finished.connect(ready)

    def write_log(self, text):
        self.log.appendPlainText(f'[{datetime.now():%H:%M:%S}] {text}')

    def toggle_log(self):
        visible = not self.log.isVisible()
        self.log.setVisible(visible)
        self.toggle.setText('Collapse' if visible else 'Expand')
        self.console_panel.setMaximumHeight(16777215 if visible else 64)
        if visible:
            self.split.setSizes([510, 190])

    def closeEvent(self, event):
        self.closing = True
        self.preview_pending.clear()
        if self.preview_process:
            self.preview_item = None
            self.preview_process.kill()
            self.preview_process.waitForFinished(1000)
        if self.active:
            self.cancel_all()
            event.ignore()
        else:
            event.accept()


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--self-test':
        from packaging_smoke import run
        sys.exit(run(sys.argv[2]))
    application = QApplication(sys.argv)
    application.setStyle('Fusion')
    application.setStyleSheet(STYLE)
    window = App()
    window.show()
    sys.exit(application.exec())
