# AGENTS.md

## Overview
Python (>=3.8) CLI download manager. Console script `idm` → `idm_cli.ui.cli:app` (Typer); `python -m idm_cli` is equivalent. Files are split into parallel byte-range chunks (1–32, default 8) via `curl-cffi` async sessions. Extraction is routed by `extractors/__init__.py:get_extractor()`: `winget ` prefix → winget extractor, a 2s HEAD probe with non-HTML Content-Type → direct, otherwise yt-dlp.

## Commands
- `pip install -e ".[dev]"`
- `ruff check .` and `ruff format --check .` (no Ruff config in repo — keep defaults)
- `pytest --cov=idm_cli --cov-report=term-missing` (pyproject sets `asyncio_mode = "auto"`, so async tests need no decorators; suite runs fully offline)
- CI runs the three commands above on ubuntu + windows with Python 3.8/3.11/3.13. Keep code 3.8-compatible: `from __future__ import annotations` before `X | Y` annotations; no `match`.

## Architecture
- Strict layering to avoid circular imports: `downloader/*` must NOT import `ui/*` at module level. `downloader/core.py` delegates all user output to `ui/prompts.py` and progress display to `ui/progress.py`, both imported lazily inside functions. `downloader/downloader.py` is a pure async chunk engine (no Rich/console). `core.py` is the orchestration hub (`process_download`).
- Extractors (`extractors/{direct,ytdlp,winget}.py`) are duck-typed modules exposing exactly `fetch_all_info(url) -> dict`, `get_video_resolutions(info) -> list[dict]`, `extract_urls(info, format_id) -> dict` (`video_url`/`audio_url`/`headers`/`title`). `core.py` falls back to the `direct` extractor if yt-dlp raises on fetch.
- The yt-dlp extractor only returns direct http(s) formats (`ytdlp.py:50`); HLS/DASH manifests are deliberately rejected.
- Resume/persistence: byte offsets in `<dest>.progress.json`; task metadata in `state.json` under the platformdirs config dir. State writes are atomic (mkstemp + `os.replace`) and cross-process file-locked; queue processing uses `queue.lock` + a psutil PID check.
- FFmpeg is required for muxing/mp3 and any non-pre-muxed format; auto-installs from BtbN GitHub releases (SHA-256 verified) into `CONFIG_DIR/bin`. `get_ffmpeg_path()` prefers PATH.
- Tests patch `state.STATE_DIR`/`STATE_FILE` and `config.CONFIG_FILE` via `unittest.mock.patch`; there is no `conftest.py`.

## Gotchas
- Servers that ignore `Range` (HTTP 200 instead of 206) raise `ValueError` ("ignored byte range") and the download falls back to a single chunk.
- `is_valid_url` accepts only http/https/www; non-URL input is rejected except `winget ...` commands (Windows-only, runs `winget show`).
- A fresh process auto-resumes any task whose saved URL matches input (`core.py:112`); changing saved paths/URLs or chunk limits breaks resumption.
- Chunk count is validated 1–32 in `downloader.py:219`; out-of-range raises.
- Update check and config/file access are designed to never crash the CLI; keep UI polish (rich markup) escaping user-supplied titles (`rich.markup.escape`).