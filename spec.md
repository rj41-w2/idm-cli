# IDM-CLI Specification

## Goal
To provide a fast, reliable, and versatile command-line download manager for power users. It unifies downloading across multiple sources (direct HTTP, social media/video platforms, and package managers) into a single interactive CLI experience with robust resume and concurrent chunking capabilities.

## User scenarios
- When a user provides a video URL, they get an interactive prompt to select quality, followed by a fully downloaded and muxed media file with real-time progress.
- When a user downloads a large file via direct HTTP, they get accelerated speeds through parallel chunk downloading.
- When a download is interrupted (e.g., network drop or manual cancellation), they can restart the command and the download resumes exactly from where it left off without starting over.
- When a user runs the tool without arguments, they get an interactive menu to paste a link, choose extraction methods, and configure the download.

## Functional requirements
- Must support concurrent chunked downloading for HTTP sources using asynchronous requests.
- Must extract and download from social media and video platforms (via yt-dlp).
- Must support Winget package downloading.
- Must persist download state atomically to allow resuming incomplete chunked downloads.
- Must provide an interactive text-based user interface (TUI) for configuration and progress tracking.
- Must integrate with FFmpeg for media post-processing (muxing, format conversion).
- Must store configuration and state files in platform-aware user data directories.

## Edge cases & rules
- **Interrupted downloads:** Must seamlessly resume from the last saved `.part` state without corruption.
- **Missing dependencies:** If FFmpeg is missing at runtime, the tool must gracefully notify the user or offer to auto-download it.
- **Disk space full:** Must catch the IO error, pause the download, and save the current state without data loss.
- **Invalid URLs:** Must return a clear error message in the UI without crashing the application.
- **Rate limiting/Network errors:** Must handle HTTP 429 or connection drops gracefully with retries or clear messaging.

## Out of scope
- A Graphical User Interface (GUI) or browser extension integration.
- Background service or daemon mode (the application runs only when actively invoked).
- Complex account management or CAPTCHA solving for premium file hosters (relies on yt-dlp for supported sites).
- Torrent (BitTorrent) protocol support.

## Acceptance criteria
- [ ] A user can successfully download a large HTTP file using multiple concurrent connections.
- [ ] A user can download a video URL and have it properly muxed into a single media file.
- [ ] Killing the CLI process mid-download and restarting it resumes the file from the last completed chunk.
- [ ] The interactive UI correctly prompts for missing inputs and displays a real-time progress bar during downloads.
