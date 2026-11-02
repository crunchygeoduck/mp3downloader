"""Small local YouTube and SoundCloud audio downloader. Launch with Start.cmd."""
from pathlib import Path
import shutil
import sys
from urllib.parse import urlparse, parse_qs

def parse_links(text):
    links = list(dict.fromkeys(text.split()))
    if not links:
        raise ValueError('Paste at least one YouTube video or SoundCloud track link.')
    for link in links:
        url = urlparse(link)
        host = (url.hostname or '').lower()
        valid_host = host in {'youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com', 'youtu.be'}
        parts = url.path.strip('/').split('/')
        is_video = (host == 'youtu.be' and len(parts) == 1 and bool(parts[0])) or (
            host != 'youtu.be' and (
            url.path == '/watch' and bool(parse_qs(url.query).get('v'))
            or len(parts) == 2 and parts[0] in {'shorts', 'live', 'embed'} and bool(parts[1])))
        is_track = (
            host in {'soundcloud.com', 'www.soundcloud.com', 'm.soundcloud.com'}
            and (len(parts) == 2 or (len(parts) == 3 and parts[2].startswith('s-') and len(parts[2]) > 2))
            and all(parts)
            and parts[0] not in {'discover', 'search', 'you', 'charts', 'stations'}
            and parts[1] not in {'sets', 'tracks', 'albums', 'reposts', 'likes', 'popular-tracks', 'followers', 'following', 'spotlight', 'comments'}
        )
        if url.scheme not in {'http', 'https'} or url.username or url.password or not ((valid_host and is_video) or is_track):
            raise ValueError('Use an individual YouTube video or full SoundCloud track link '
                             f'(soundcloud.com/artist/track), not a profile or playlist:\n{link}')
    return links


def python_executable():
    return str(Path(sys.executable).with_name('python.exe')) if sys.executable.lower().endswith('pythonw.exe') else sys.executable


def tool_path(name):
    if getattr(sys, 'frozen', False):
        path = Path(sys._MEIPASS) / 'tools' / (name + '.exe')
        return str(path) if path.is_file() else None
    return shutil.which(name)


def downloader_prefix():
    if getattr(sys, 'frozen', False):
        return [tool_path('yt-dlp') or str(Path(sys._MEIPASS) / 'tools' / 'yt-dlp.exe')]
    return [python_executable(), '-m', 'yt_dlp']


def runtime_options():
    node = tool_path('node')
    options = ['--js-runtimes', 'node:' + node if node else 'node']
    ffmpeg = tool_path('ffmpeg')
    if ffmpeg:
        options += ['--ffmpeg-location', str(Path(ffmpeg).parent)]
    return options


def preview_command(link):
    return downloader_prefix() + runtime_options() + ['--ignore-config', '--no-playlist',
            '--skip-download', '--dump-single-json', '--no-warnings', '--no-color',
            '--socket-timeout', '15', '--retries', '1', '--', link]


def download_command(link, folder, quality='0'):
    return downloader_prefix() + runtime_options() + ['--ignore-config', '--no-playlist', '--no-simulate',
            '--newline', '--no-color', '--progress', '--no-quiet',
            '--print', 'before_dl:APP_META:%()j', '--print', 'after_move:APP_FILE:%(filepath)s',
            '--progress-template', 'download:APP_PROGRESS:%(progress._percent_str)s',
            '--progress-delta', '0.3', '--windows-filenames', '--no-overwrites', '--socket-timeout', '30',
            '-f', 'bestaudio/best', '-x', '--audio-format', 'mp3',
            '--audio-quality', quality, '--embed-metadata',
            '-P', str(folder), '-o', '%(title).150B [%(id)s].%(ext)s', '--', link]
