<div align="center">

<h1>IDM-CLI</h1>

**A lightning-fast, cross-platform command-line download manager written in Python.**

*The official IDM asks you to pay after 30 days — IDM-CLI is 100% free, open-source, and yours to modify!*

[![PyPI version](https://img.shields.io/pypi/v/idm-cli?color=blue&label=pypi%20version)](https://pypi.org/project/idm-cli/)
[![Downloads](https://static.pepy.tech/badge/idm-cli)](https://pepy.tech/project/idm-cli)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](https://github.com/rj41-w2/idm-cli/blob/main/LICENSE)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)
[![Install](https://img.shields.io/badge/install-pip%20install%20idm--cli-brightgreen)](https://pypi.org/project/idm-cli/)

[Download via PyPI](https://pypi.org/project/idm-cli/) · [Report a Bug](https://github.com/rj41-w2/idm-cli/issues)

</div>

IDM-CLI splits files into multiple parallel chunks (default 8, up to 32) to maximize your internet speed. It supports downloading from **YouTube**, **Facebook**, **Instagram**, and any **Direct File URL** (`.exe`, `.zip`, `.pdf`, etc.).

## Features

- **Parallel Chunk Engine** — Splits downloads into multiple concurrent chunks using `aiohttp` async sessions to fully saturate your bandwidth.
- **Universal Downloader** — Paste any URL. yt-dlp handles 1000+ sites (YouTube, Facebook, Instagram, etc.), with automatic fallback to direct HTTP download for unsupported URLs.
- **Audio Only / MP3 Conversion** — Download videos as audio. IDM-CLI automatically grabs the best audio stream and uses FFmpeg to convert it to `.mp3`.
- **Smart Auto-Resume** — Internet dropped? Pressed `Ctrl+C`? No problem. IDM-CLI remembers the exact byte positions of all incomplete chunks. Paste the same link again to resume instantly.
- **Persistent Queue System** — Add multiple files to a queue with `-Q` and type `start queue` to download them all sequentially.
- **Interactive UI** — Modern terminal interface powered by `rich` and `questionary` with real-time speed, ETA, and progress bars. Press `p` to pause, `r` to resume.
- **Cross-Platform** — Works on Windows, macOS, and Linux with platform-specific FFmpeg handling.
- **Auto-Update Check** — Checks PyPI once a day and notifies you when a new version is available.

## Prerequisites

- **Python 3.8+**
- **FFmpeg** — Required for muxing video and audio streams, and converting to `.mp3`. IDM-CLI can auto-download it for you, or you can install it manually:
  - Windows: `winget install ffmpeg`
  - macOS: `brew install ffmpeg`
  - Linux: `sudo apt install ffmpeg`

## Installation

```bash
# From PyPI
pip install idm-cli

# From source
git clone https://github.com/rj41-w2/idm-cli.git
cd IDM-CLI
pip install -r requirements.txt
pip install -e .
```

## Usage

Run the app interactively:

```bash
idm
```

This opens a prompt where you can paste your link, select video quality, or queue the download.

### CLI Flags (Fast Mode)

Skip the interactive menus by passing arguments directly:

```bash
# Download a video at 1080p
idm "https://youtube.com/watch?v=..." -q 1080p -v

# Audio only (converts to MP3)
idm "https://youtube.com/watch?v=..." -a

# 16 parallel chunks for maximum speed
idm "https://example.com/largefile.zip" -c 16

# Add to queue
idm "https://facebook.com/..." -Q
```

| Flag | Description |
|------|-------------|
| `-q <resolution>` | Set video quality (e.g., `1080p`, `720p`) |
| `-a` | Audio only — download and convert to MP3 |
| `-v` | Download video + audio (bypasses quality prompt) |
| `-Q` | Add to queue instead of downloading immediately |
| `-c <num>` | Number of parallel chunks (default: 8) |
| `-f <filename>` | Force a custom output filename |

### Interactive Commands

| Command | Description |
|---------|-------------|
| `<URL>` | Download a video or file |
| `resume` | Resume or delete incomplete downloads |
| `start queue` | Process all queued downloads |
| `help` | Show available commands and flags |
| `exit` | Exit the application |

### Troubleshooting: Windows Device Guard

If you get `"idm.exe was blocked by your organization's Device Guard policy"`, run the Python module directly:

```bash
python -m idm_cli
```

## Architecture

```
idm_cli/
├── config.py                # Platform-aware config, logging, paths
├── update_checker.py        # PyPI version check
├── ui/
│   ├── cli.py               # Main interactive CLI
│   └── utils.py             # Console, progress listener, validators
├── downloader/
│   ├── core.py              # Download orchestration & FFmpeg setup
│   ├── downloader.py        # Async chunk download engine
│   ├── handlers.py          # Queue & resume handlers
│   ├── muxer.py             # FFmpeg mux/conversion
│   └── state.py             # Atomic JSON state persistence
├── extractors/
│   ├── ytdlp.py             # YouTube/social media extractor
│   ├── direct.py            # Direct HTTP file downloader
│   └── winget.py            # Windows Package Manager extractor
```

## Contributing

Contributions are welcome. Fork the repo, make your changes on a feature branch, and open a PR against `main`. Keep changes focused and follow the existing code style.

For bug reports and feature requests, [open an issue](https://github.com/rj41-w2/idm-cli/issues).

## License

This project is licensed under the [MIT License](LICENSE).
