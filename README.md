# IDM-CLI (Internet Download Manager CLI)

A lightning-fast, powerful, and universal command-line download manager written in Python. IDM-CLI splits files into multiple parallel chunks (default 8, up to 32) to maximize your internet speed. It seamlessly supports downloading from **YouTube**, **Facebook**, **Instagram**, and any **Direct File URL** (`.exe`, `.zip`, `.pdf`, etc.).

## 🚀 Features

- **Blazing Fast Speeds:** Splits downloads into multiple parallel chunks (like traditional IDM) to fully saturate your bandwidth.
- **Universal Downloader:** Paste any direct URL (e.g., a `.pdf` or `.exe`). The built-in smart HTTP `HEAD` detector automatically recognizes file types and routes them to the parallel engine.
- **Social Media Support:** Natively supports downloading from **YouTube**, **Facebook**, and **Instagram** via a modular extractor architecture. Auto-detects pre-muxed (SD/HD) vs separated streams. (Note: Instagram carousels are currently disabled to prevent DPAPI cookie issues).
- **Audio Only / MP3 Conversion:** Easily download videos as audio. IDM-CLI automatically grabs the best audio stream and uses `ffmpeg` to perfectly convert it to `.mp3`.
- **Smart Auto-Resume:** Internet dropped? Pressed `Ctrl+C`? No problem! IDM-CLI remembers the exact byte positions of all incomplete chunks. Paste the same link again to resume instantly.
- **Persistent Queue System (`-Q`):** Add multiple files or videos to a queue and type `start queue` to automatically download all of them sequentially in the background.
- **Pristine Downloads Folder:** All temporary chunks and raw media files are kept hidden in `~/.idm_cli/tmp/`. Only the fully assembled, 100% complete files are moved to your `~/Downloads` folder.
- **Smart Auto-Update:** Once a day, IDM-CLI automatically checks the PyPI database in the background. If a new version is available, it handles the `pip install --upgrade` process for you seamlessly!
- **Interactive UI:** A beautiful, responsive terminal interface powered by `rich` and `questionary` with real-time speed, ETA, and progress bars.
- **Pause & Play:** Press `p` to pause the active downloads without losing progress, and `r` to resume them.

## 🛠️ Prerequisites

- **Python 3.8+**
- **FFmpeg:** Required for muxing video and audio streams, and converting media to `.mp3`. Ensure `ffmpeg` is installed and added to your system's PATH. 
  - *Windows users can easily install it by running: `winget install ffmpeg` in their terminal.*

## 📦 Installation

Clone the repository and install the required dependencies:

```bash
git clone https://github.com/rj41-w2/idm-cli.git
cd IDM-CLI
pip install -r requirements.txt
```

*(Note: If you plan to publish this to PyPI, users will simply be able to run `pip install idm-cli`)*

## 💻 Usage

Run the app interactively by simply typing:
```bash
idm
```
This will open a prompt where you can paste your link, select video resolutions, or choose to queue the download.

### CLI Flags (Fast Mode)

Skip the interactive menus by passing arguments directly!

```bash
# Download a video with auto-selected 1080p quality
idm "https://youtube.com/watch?v=..." -q 1080p -v

# Download Audio Only (converts to MP3)
idm "https://youtube.com/watch?v=..." -a

# Use 16 parallel chunks for maximum speed (default is 8)
idm "https://example.com/largefile.zip" -c 16

# Add a video to the Queue without downloading it right now
idm "https://facebook.com/..." -Q
```

### Queue Management

To start downloading all items currently in your queue, simply type:
```bash
idm start queue
```
*(You can also just type `start queue` into the interactive `idm` prompt!)*

## ⚙️ Architecture Highlights

- **`downloader.py`:** The core asynchronous engine handling `aiohttp` range requests, chunk merging, and resume states.
- **`cli.py`:** The interactive orchestration layer utilizing `typer`, `rich`, and `questionary`.
- **`muxer.py`:** Safe abstraction over `subprocess` calls to `ffmpeg` for media stream merging.
- **`extractors/`:** Modular plugins (`youtube.py`, `facebook.py`, `instagram.py`, `direct.py`) for handling specialized metadata retrieval.

## 📄 License

This project is open-source and available under the MIT License.
