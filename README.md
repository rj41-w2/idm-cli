# IDM-CLI (Internet Download Manager CLI)

*Inspired by the official [Internet Download Manager (IDM)](https://www.internetdownloadmanager.com/)*

A lightning-fast, cross-platform command-line download manager written in Python. IDM-CLI splits files into multiple parallel chunks (default 8, up to 32) to maximize your internet speed. It supports downloading from **YouTube**, **Facebook**, **Instagram**, and any **Direct File URL** (`.exe`, `.zip`, `.pdf`, etc.).

## Features

- **Parallel Chunk Engine** — Splits downloads into multiple concurrent chunks using `aiohttp` async sessions to fully saturate your bandwidth.
- **Universal Downloader** — Paste any direct URL. A built-in HTTP `HEAD` detector automatically recognizes file types and routes them to the parallel engine.
- **Social Media Support** — Natively supports YouTube, Facebook, and Instagram via a modular extractor architecture with yt-dlp.
- **Audio Only / MP3 Conversion** — Download videos as audio. IDM-CLI automatically grabs the best audio stream and uses FFmpeg to convert it to `.mp3`.
- **Smart Auto-Resume** — Internet dropped? Pressed `Ctrl+C`? No problem. IDM-CLI remembers the exact byte positions of all incomplete chunks. Paste the same link again to resume instantly.
- **Persistent Queue System** — Add multiple files to a queue with `-Q` and type `start queue` to download them all sequentially.
- **Browser Extension Integration** — Chrome/Edge extension intercepts downloads and routes them directly into IDM-CLI via Native Messaging.
- **Interactive UI** — Modern terminal interface powered by `rich` and `questionary` with real-time speed, ETA, and progress bars. Press `p` to pause, `r` to resume.
- **Cross-Platform** — Works on Windows, macOS, and Linux with platform-specific FFmpeg handling and browser registration.
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
| `install extension` | Guide to install the browser extension |
| `help` | Show available commands and flags |
| `exit` | Exit the application |

### Browser Extension

IDM-CLI includes a Chrome/Edge extension that intercepts file downloads automatically. To install it:

```bash
idm
# then type:
install extension
```

Follow the on-screen guide to load the unpacked extension and link it to IDM-CLI.

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
└── extension/
    ├── extension.py         # Browser extension installer
    ├── native_host.py       # Native Messaging Host
    ├── daemon.py            # Queue daemon with PID lock
    └── browser_extension/   # Chrome/Edge extension source
```

## Contributing

Contributions are welcome — whether it's a bug fix, a new feature, or just improving the docs.

### Reporting Bugs

If you find a bug, [open an issue](https://github.com/rj41-w2/idm-cli/issues/new) with:

- A clear title and description of the problem
- Steps to reproduce the issue
- Your OS and Python version (`python --version`)
- The full error output if there is one

### Suggesting Features

Got an idea? [Open an issue](https://github.com/rj41-w2/idm-cli/issues/new) with the tag `enhancement` and describe:

- What you want to happen and why
- How it would work from the user's perspective
- Any alternatives you considered

### Submitting a Pull Request

1. **Fork** the repository from [github.com/rj41-w2/idm-cli](https://github.com/rj41-w2/idm-cli)

2. **Clone your fork** and set it up:
   ```bash
   git clone https://github.com/<your-username>/idm-cli.git
   cd IDM-CLI
   pip install -r requirements.txt
   pip install -e .
   ```

3. **Create a branch** for your change:
   ```bash
   git checkout -b fix/short-description
   ```

4. **Make your changes**, test them, and commit with a clear message:
   ```bash
   git commit -m "fix: describe the bug you fixed"
   ```

5. **Push** to your fork and open a Pull Request against `main`:
   ```bash
   git push origin fix/short-description
   ```

6. In your PR description, explain **what changed** and **why**. Link the issue if there is one.

### Guidelines

- Keep PRs focused on a single change. Don't mix unrelated fixes.
- Follow the existing code style — no comments unless absolutely necessary.
- Test your changes on at least one platform before submitting.
- If you're adding a feature, update the README and spec if needed.

## License

This project is licensed under the [MIT License](LICENSE).
