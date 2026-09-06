# Changelog

All notable changes to IDM-CLI are documented here.

## [1.3.3] - 2026-09-06

### Fixed

- Validate ranged HTTP responses and received byte counts to prevent corrupted downloads.
- Prevent existing files from being treated as complete when the server cannot be checked.
- Avoid buffering an entire file during range capability detection.
- Validate resume metadata and make state updates safe across processes.
- Prevent direct-file audio-only downloads from reporting a false success.
- Handle small-file chunk partitioning and non-TTY input safely.
- Prevent temporary-file collisions and accidental output overwrites.
- Make FFmpeg post-processing output atomic.
- Harden filenames and escape user-controlled terminal output.
- Stop implicit browser-cookie access during yt-dlp fallback.

### Security

- Verify downloaded FFmpeg archives against the SHA-256 digest published by GitHub Releases.
- Added a security reporting policy in `SECURITY.md`.

### Tests and CI

- Added regression tests for configuration validation, filename safety, and direct extractors.
- Added coverage reporting to GitHub Actions.

## [1.3.0]

### Added

- URL validation for HTTP/HTTPS sources.
- Atomic download state persistence.
- Queue locking and safer Winget command execution.
- Improved retry handling and resume support.

### Security

- Removed unsafe command execution paths and machine-specific configuration from the repository.

## [1.2.2]

### Fixed

- Improved resume reliability after interrupted downloads.
- Improved recovery from throttling and silent network disconnects.
- Added faster automatic FFmpeg download support.
- Added Winget-based FFmpeg installation on Windows.
