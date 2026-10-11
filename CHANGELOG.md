# Changelog

All notable changes to IDM-CLI are documented here.

## [Unreleased]

### Added

- README "Security" section documenting what IDM-CLI does and does not protect
  against (it is a download manager, not an antivirus).

### Changed

- **UI palette reduced to two colours (cyan + white).** Status meaning is now
  carried by a leading glyph instead of colour: `✓` success, `✗` error/cancel,
  `•` neutral info, `»` an action starting, `‖` paused.
- **Version is now single-sourced.** `pyproject.toml` reads `__version__` from
  `idm_cli/__init__.py` instead of repeating it, so the package and the
  metadata can no longer disagree.

### Added

- **Automated releases.** Pushing a `v*` tag runs `.github/workflows/release.yml`,
  which builds, validates, and publishes to PyPI via Trusted Publishing (OIDC).
  The workflow refuses to publish when the tag and the packaged version differ.

## [1.3.4] - 2026-10-11

### Fixed

- **Downloads failed with HTTP 403** on servers that reject the impersonated
  Chrome User-Agent: chunks now retry with a fallback User-Agent.
- **Resume broke for direct files**: the extractor was resolved twice, and the
  flaky network probe could return a different extractor the second time
  ("did not provide a downloadable URL"). The extractor is now resolved once and
  reused; saved direct-file tasks never re-probe.
- **FFmpeg muxing failed (exit 234)**: the temp output kept a `.part` extension,
  so ffmpeg could not infer the container format. The temp file now preserves
  the real extension and is renamed atomically.
- **Quality menu never appeared**: the default YouTube player clients exposed
  only 360p, so a single "resolution" auto-selected silently. The extractor now
  tries several clients and keeps the one with the most resolutions
  (1080p/720p/... when available).
- **Non-TTY crash**: `check_key_press()` raised `termios.error` (not an
  `OSError`) when stdin was a pipe/file, killing downloads in scripts/CI.
- Corrupted resume metadata no longer aborts the download; it resets the chunk.
- `0`-byte files and `bool` chunk counts are handled correctly.

### Changed

- Interactive runs now prompt for quality whenever a real terminal is available
  (previously `idm <url>` silently used the configured default). The configured
  default is marked `(default)` and pre-selected; `-q`/`-a` still skip the prompt.
- FFmpeg failures now show a short, single-line message; the full ffmpeg output
  goes to the log file only.

### Security

- SSRF: `is_valid_url()` now rejects private/loopback/link-local/reserved hosts
  (localhost, 127.0.0.1, 10/8, 192.168/16, 169.254.169.254, IPv6 equivalents).
- Rich markup injection: user- and metadata-controlled strings are escaped.

### Tests and CI

- Test suite grew from 15 to 69 tests (muxer, progress, extractors, core/handlers,
  quality-prompt behaviour, SSRF, muxing regressions).

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
