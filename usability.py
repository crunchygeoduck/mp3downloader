"""User-facing messages and release version handling."""
import re

VERSION = '1.1.0'
REPOSITORY = 'https://github.com/crunchygeoduck/mp3downloader'
RELEASES = REPOSITORY + '/releases/latest'
ISSUES = REPOSITORY + '/issues/new'
UPDATE_API = 'https://api.github.com/repos/crunchygeoduck/mp3downloader/releases/latest'
QUALITIES = ['320 kbps MP3', '256 kbps MP3', '192 kbps MP3', '128 kbps MP3', 'Best quality MP3']


def newer_release(payload):
    if not isinstance(payload, dict) or payload.get('draft') or payload.get('prerelease'):
        return None
    tag = payload.get('tag_name', '')
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)', tag) if isinstance(tag, str) else None
    if match and tuple(map(int, match.groups())) > tuple(map(int, VERSION.split('.'))):
        return tag
    return None


def friendly_error(details):
    text = details.lower()
    if any(term in text for term in ('no space left', 'disk full', 'not enough space')):
        return 'Your drive is full. Free some space or choose another save folder, then retry.'
    if any(term in text for term in ('permission denied', 'access is denied', 'read-only file system')):
        return 'Cannot write to the save folder. Check its permissions or choose another folder.'
    if any(term in text for term in ('private video', 'login required', 'sign in', 'sign-in', 'members-only', 'authentication', 'premium', 'subscription')):
        return 'This track requires sign-in or restricted access. Try a public or unlisted link you can access.'
    if any(term in text for term in ('timed out', 'name resolution', 'getaddrinfo', 'unable to connect', 'connection', 'network is unreachable')):
        return 'Could not connect. Check your internet connection and try Retry.'
    if any(term in text for term in ('429', 'too many requests', 'rate limit')):
        return 'The site is limiting requests. Wait a few minutes, then retry.'
    if any(term in text for term in ('not available in your country', 'geo restricted', 'geo-restricted')):
        return 'This track is unavailable in your region. Try another link.'
    if any(term in text for term in ('404', 'not found', 'video unavailable', 'has been removed', 'does not exist')):
        return 'This track could not be found. Open the original link to check it is still available.'
    if any(term in text for term in ('ffmpeg', 'ffprobe', 'postprocessing')):
        return 'Audio conversion failed. Check free disk space, then retry or download the latest app.'
    if any(term in text for term in ('403', 'forbidden', 'signature', 'requested format is not available')):
        return 'The site refused this download. Try again later or check for an app update.'
    if 'could not start downloader' in text:
        return 'The downloader could not start. Try reopening the app or downloading the latest release.'
    return 'Download failed. Try Retry or Check for updates. The log has technical details if you need help.'
