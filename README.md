# YouTube & SoundCloud to MP3

A small local Windows app. Everything downloads and converts on your computer.

## Portable Windows executable

Download **YT-SC Downloader.exe** from the [latest release](https://github.com/crunchygeoduck/mp3downloader/releases/latest), then double-click it. This single-file Windows x64 build includes Python, Qt, yt-dlp, FFmpeg/ffprobe, and Node.js. No installation or administrator access is required. Startup can take a little longer while bundled tools are extracted to a temporary folder. Downloads are saved to your selected folder, and folder/quality preferences are remembered.

The executable is an unsigned local build. To update its bundled downloader, rebuild the executable; Setup.cmd updates only the source version.

See [BUILDING.md](BUILDING.md) to build the executable or run the packaging check. Source code and tests live in this repository; large executable downloads are attached to Releases.

## Use

1. Open **YT-SC Downloader.exe**, or use **Start.cmd** after setting up the source version.
2. Paste individual YouTube video or SoundCloud track links, one per line. You can mix both services in the same batch.
3. Choose MP3 quality and a folder, or keep `Downloads\YouTube MP3`.
4. Click **Add to Queue** to save the links for later, or **Download Now** to download the entered links. Use **Download All** above the queue to start all currently queued items.
5. Click **Open folder** to find your files.

Public and unlisted YouTube videos and publicly accessible SoundCloud tracks are supported. For SoundCloud, use the full track URL (`https://soundcloud.com/artist/track`); open shortened share links in your browser and copy the full track URL first. Links with share query parameters are accepted. Tracks requiring sign-in or a subscription are not supported; some tracks may only offer a preview.

Profile and playlist links are rejected; a YouTube video URL containing a playlist downloads only that video. Cancel stops the download/conversion; temporary partial files may remain and can be resumed on retry. Existing MP3 files are not overwritten. MP3 conversion cannot improve the original audio quality.

## Queue controls

- Paste from clipboard or drag links into the window, then add them to the queue. Adding links never starts them automatically. Each item retains its chosen folder and quality.
- Adding a link fetches its title, artwork, uploader, and duration in the background without downloading audio. Preview lookups run one at a time; if a lookup fails, the card stays queued and can still be downloaded.
- **Download Now** starts only the entered links. Each card has **Download** and **Cancel** buttons; failed or cancelled cards offer **Retry**. If another download is running, requested tracks wait their turn.
- **Download All** starts the current queued items sequentially. Links added afterward stay queued until you choose to download them.
- Choose 128, 192, 256, or 320 kbps MP3, or best quality (variable bitrate). Folder and quality are remembered between launches.
- Track cards show title, uploader, duration, artwork when available, and download progress. Conversion uses an activity indicator because yt-dlp does not expose reliable conversion percentages.
- Click artwork to open the source, or play the downloaded MP3 in your default audio player when complete.
- Use Cancel on a card to cancel that track, or Cancel all to stop active and queued tracks. Closing the app cancels remaining work.
- After cancellation finishes, **Remove from Queue** appears beside Cancel. It removes the card without deleting files; Retry remains available if you change your mind.
- The ⋮ menu offers the source link, download folder, copy link, retry for failed/cancelled tracks, and removal from the queue. Clear finished removes cards, not files.
- Clear or collapse the log console; drag the divider above it to resize it.
- The queue is kept only for the current session. Existing MP3s are preserved; to download a different quality, choose a different folder or remove the old file first.

## Setup and updates

For the source version, run **Setup.cmd** to install or update the downloader. It installs dependencies in this project's `.venv` directory.

For another Windows computer, install Python 3.10+, FFmpeg (with ffprobe), and Node.js 22+ on PATH, then run Setup.cmd. Setup installs the Qt interface (PySide6 Essentials) and downloader. No browser cookies or account credentials are read by this app.

Run the regression tests with `.venv\Scripts\python.exe -m unittest test_queue -v`.

Only download audio you own or have permission to download. Third-party components retain their own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
