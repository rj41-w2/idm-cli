# IDM-CLI — Project Specification

**Version:** 1.3.0
**Author:** Rehan

---

## What is IDM-CLI?

IDM-CLI is a command-line download manager for Windows, macOS, and Linux. The idea is simple — take the concept of IDM (Internet Download Manager) and bring it to the terminal. It downloads files by splitting them into multiple parallel chunks so you get maximum speed out of your internet connection.

It works with YouTube, Facebook, Instagram, and basically any direct file URL. There's also a Chrome/Edge extension that can intercept downloads in the browser and send them straight to IDM-CLI.

---

## How It Works

The core idea is parallel chunk downloading. When you download a file, IDM-CLI fetches the total file size using an HTTP `Range` request, then splits it into N chunks (default is 8). Each chunk is downloaded at the same time using `aiohttp` async sessions. Once all chunks finish, they're merged into the final file.

Each chunk tracks its own byte progress in a `.progress.json` sidecar file. So if the download gets interrupted — whether it's a network drop or a `Ctrl+C` — the app knows exactly where each chunk left off. Next time you paste the same URL, it picks up from there.

Buffer sizes are adaptive. For large chunks (over 50 MB), it uses 4 MB buffers. For small ones (under 5 MB), it drops to 256 KB. Everything in between uses 1 MB. This keeps memory usage reasonable without killing throughput.

There's a hard cap of 8 concurrent TCP connections per host. This is intentional — going beyond that tends to get you rate-limited or blocked by servers, especially YouTube.

---

## Supported Platforms

This runs on all three major platforms. Here's what changes between them:

| | Windows | macOS | Linux |
|---|---------|-------|-------|
| FFmpeg install option | `winget install ffmpeg` | `brew install ffmpeg` | `sudo apt install ffmpeg` |
| Native host script | `native_host.bat` | `native_host.sh` | `native_host.sh` |
| Browser extension registration | Windows Registry | Config folder copy | Config folder copy |
| Queue worker terminal | `CREATE_NEW_CONSOLE` | Direct `Popen` | Direct `Popen` |

Config directories follow platform conventions — `%LOCALAPPDATA%` on Windows, `~/Library/Application Support` on macOS, `~/.config` on Linux. All handled automatically by `platformdirs`.

---

## CLI Commands

There are six commands in interactive mode:

- **Paste a URL** — starts the download. You'll get a quality picker if it's a video.
- **`resume`** — shows a list of incomplete downloads. You can resume or delete each one.
- **`start queue`** — runs through all queued items one by one.
- **`install extension`** — walks you through setting up the Chrome/Edge extension.
- **`help`** — prints the command list and available flags.
- **`exit`** — quits. (Or hit `Ctrl+C` twice within 5 seconds.)

### Flags for Fast Mode

You can skip all the interactive prompts by passing flags:

```bash
idm "https://youtube.com/watch?v=..." -q 1080p -v    # 1080p video
idm "https://youtube.com/watch?v=..." -a              # audio only → MP3
idm "https://example.com/file.zip" -c 16              # 16 chunks
idm "https://facebook.com/..." -Q                     # add to queue
```

`-q` sets quality, `-a` is audio only, `-v` forces video+audio, `-c` sets chunk count, `-Q` queues instead of downloading, and `-f` overrides the output filename.

---

## Extractors

IDM-CLI uses a modular extractor system. When you paste a URL, it first does an HTTP `HEAD` request to check the `Content-Type`. If it's not `text/html`, it assumes it's a direct file and routes to the direct downloader. Otherwise, it falls through to `yt-dlp` which handles YouTube and most social media sites.

There's also a `winget` extractor for Windows — if you type `winget install <package>`, it runs `winget show` to grab the installer URL and downloads it through the parallel engine.

The `yt-dlp` extractor has a fallback chain for YouTube bot detection. It tries `android`, `ios`, and `tv` player clients first. If those fail, it attempts to read cookies from local browsers (Chrome, Edge, Firefox, Brave, Opera). The user needs to have the browser fully closed for cookie reading to work.

---

## Queue System

Queued downloads are stored in `state.json` inside the config directory. The format is straightforward — each entry has the URL, format ID, title, temp paths, final path, and status.

When you run `start queue`, the app acquires a file-based lock (using atomic `O_CREAT | O_EXCL` to prevent race conditions) and processes items one at a time. If the queue is already running in another instance, it tells you and exits.

---

## Browser Extension

The extension is a Manifest V3 Chrome/Edge extension. It does two things:

1. **Download interception** — listens to `chrome.downloads.onDeterminingFilename` and checks file extensions against a list of ~50 known types (mp4, zip, exe, pdf, etc.). If it matches, it cancels the browser download and sends the URL to IDM-CLI via Native Messaging.

2. **Context menu** — adds a "Download with IDM-CLI" right-click option on links, pages, videos, and audio.

The Native Messaging Host is a Python script that communicates with the browser over stdin/stdout using Chrome's length-prefixed JSON protocol. It validates incoming messages — checks URL schemes, quality format, filename safety, and rejects anything over 1 MB.

---

## FFmpeg Handling

FFmpeg is needed for two things: muxing separate video+audio streams into one file, and converting audio to MP3.

If FFmpeg isn't found on the system, IDM-CLI offers to download it automatically from GitHub (BtbN builds). On Windows it grabs the win64 zip, on macOS the macos64 zip, and on Linux the linux64 tar.xz. The binary is extracted to `<config>/bin/` and subsequent runs pick it up from there.

Alternatively, the user can install through their package manager (winget/brew/apt) via the interactive prompt.

---

## Error Handling

Network errors trigger automatic retries — up to 10 attempts per chunk with exponential backoff (capped at 30 seconds). If all retries fail, the user sees: `"Your poor internet connection. Try again."`

Unknown commands in the interactive prompt return: `"Unknown command: <input>"` with a hint to type `help`.

Progress files are cleaned up after successful downloads. Failed downloads keep their state so they can be resumed later.

---

## Security Measures (v1.3.0)

A few things were tightened up in this version:

- All `subprocess` calls use `shell=False`. No shell injection vectors.
- URLs are validated — only `http://` and `https://` are accepted. Schemes like `file://`, `javascript:`, `data:`, and `ftp://` are blocked.
- The native host validates all incoming parameters before passing them to the CLI.
- Queue lock files use atomic creation (`O_CREAT | O_EXCL`) to avoid race conditions.
- The browser extension no longer requests `host_permissions` — it only needs `contextMenus`, `nativeMessaging`, and `downloads`.

---

## Dependencies

The project relies on: `typer` and `rich` for the CLI interface, `questionary` for interactive prompts, `aiohttp` and `aiofiles` for async downloading, `yt-dlp` for metadata extraction, `psutil` for process management, `platformdirs` for cross-platform paths, and `pyfiglet` for the ASCII banner.

---



**Prerequisites:** Python 3.8+, FFmpeg (for video/audio processing)
