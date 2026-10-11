"""
downloader/core.py
------------------
Download orchestration — no UI, no console.print, no questionary.

All user-facing output is delegated to ui/prompts.py.
The async progress display is handled by ui/progress.py via run_with_progress().
"""

from __future__ import annotations

import asyncio
import os
import shutil
import uuid

import typer

from idm_cli.config import logger
from idm_cli.downloader.muxer import convert_to_mp3, mux_audio_video
from idm_cli.downloader.state import (
    get_incomplete_downloads,
    remove_download,
    save_download,
)
from idm_cli.extractors import get_extractor
from idm_cli.ui.prompts import (
    ask_ffmpeg_install,
    ask_quality,
    install_ffmpeg,
    setup_ctrl_c,
    show_download_cancelled,
    show_download_start,
    show_error,
    show_initializing,
    show_queued,
    show_resuming,
    show_success,
)
from idm_cli.ui.utils import console, sanitize_filename

__all__ = ["process_download", "run_download_and_mux"]


def _finalize_single_video(video_dest: str, final_dest: str) -> None:
    """Move a video-only download to its final destination.

    Uses os.replace first (atomic on same filesystem), falls back to
    shutil.move. Raises RuntimeError with a clean message on failure.
    """
    try:
        os.replace(video_dest, final_dest)
    except OSError:
        try:
            shutil.move(video_dest, final_dest)
        except OSError as e:
            raise RuntimeError(f"Could not move downloaded file to {final_dest}: {e}")


def _available_path(path: str) -> str:
    """Choose a non-destructive destination for a new download.

    Treats both files and directories as occupied so the returned path
    is always a valid, non-existent file target.
    """
    if not os.path.exists(path):
        return path
    stem, suffix = os.path.splitext(path)
    index = 1
    while os.path.exists(f"{stem} ({index}){suffix}"):
        index += 1
    return f"{stem} ({index}){suffix}"


def run_download_and_mux(
    video_url,
    audio_url,
    headers,
    chunks,
    video_dest,
    audio_dest,
    final_dest,
    media_type,
    pause_event,
    warning_state,
    title="",
):
    """Run the async download + mux pipeline synchronously."""
    from idm_cli.ui.progress import run_with_progress  # lazy — avoids circular

    asyncio.run(
        run_with_progress(
            video_url=video_url,
            audio_url=audio_url,
            headers=headers,
            chunks=chunks,
            video_dest=video_dest,
            audio_dest=audio_dest,
            pause_event=pause_event,
            warning_state=warning_state,
        )
    )

    if video_dest and audio_dest:
        mux_audio_video(video_dest, audio_dest, final_dest)
    elif audio_dest and not video_dest:
        convert_to_mp3(audio_dest, final_dest)
    elif video_dest and not audio_dest:
        _finalize_single_video(video_dest, final_dest)

    return True


def process_download(
    current_url: str,
    is_interactive: bool,
    loop_quality: str,
    loop_audio_only: bool,
    loop_queue: bool,
    loop_chunks: int,
    loop_filename: str,
    found_task_id: str | None = None,
    found_task_data: dict | None = None,
):
    url_to_extract = current_url
    title = ""
    format_id = None

    # ── auto-resume check ──────────────────────────────────────────────────────
    if not found_task_id:
        incomplete = get_incomplete_downloads()
        for tid, data in incomplete.items():
            if data.get("url") == url_to_extract:
                found_task_id = tid
                found_task_data = data
                break

    if found_task_id:
        # Validate that saved temp files still exist before resuming.
        # If they were deleted, fall back to a fresh download.
        saved_video = found_task_data.get("video_dest", "")
        saved_audio = found_task_data.get("audio_dest", "")
        fmt = found_task_data.get("format_id", "")
        temp_missing = False
        if fmt != "direct_file":
            if saved_video and not os.path.exists(saved_video):
                temp_missing = True
            if saved_audio and not os.path.exists(saved_audio):
                temp_missing = True
        else:
            # direct_file: single temp file stored in video_dest
            if saved_video and not os.path.exists(saved_video):
                temp_missing = True
        if temp_missing:
            # Temp files gone — start fresh
            found_task_id = None
            found_task_data = None

    if found_task_id:
        show_resuming()
        task_id = found_task_id
        format_id = found_task_data["format_id"]
        video_dest = found_task_data["video_dest"]
        audio_dest = found_task_data["audio_dest"]
        final_dest = found_task_data["final_dest"]
        title = found_task_data["title"]
    else:
        format_id = None
        task_id = str(uuid.uuid4())
        show_initializing(current_url)
        if loop_audio_only:
            format_id = "audio_only"

    # ── fetch metadata ─────────────────────────────────────────────────────────
    extractor = None
    with console.status("[bold cyan]Fetching metadata...", spinner="dots"):
        try:
            # Resolve the extractor ONCE and reuse it for extract_urls() below.
            # Re-probing later can return a different extractor (the probe is a
            # flaky network call), which breaks extraction/resume.
            if (
                found_task_id
                and found_task_data
                and found_task_data.get("format_id") == "direct_file"
            ):
                # A saved direct_file task must resume with the direct extractor;
                # never re-probe (the probe may fail and route to yt-dlp).
                import importlib

                extractor = importlib.import_module("idm_cli.extractors.direct")
            else:
                extractor = get_extractor(url_to_extract)
            try:
                info = extractor.fetch_all_info(url_to_extract)
            except Exception:
                if extractor.__name__ == "idm_cli.extractors.ytdlp":
                    import importlib

                    extractor = importlib.import_module("idm_cli.extractors.direct")
                    info = extractor.fetch_all_info(url_to_extract)
                else:
                    raise

            title = info.get("title", "download") if not found_task_id else title
            if loop_filename and not found_task_id:
                title = os.path.basename(loop_filename)

            if info.get("_type") == "playlist":
                console.print(
                    "\n[bold cyan]•[/] Currently, the feature to download "
                    "album/playlist photos or videos is not added.[/]"
                )
                if not is_interactive:
                    raise typer.Exit(code=0)
                return False

            if (
                format_id == "audio_only"
                and extractor.__name__ != "idm_cli.extractors.ytdlp"
            ):
                raise ValueError(
                    "Audio-only conversion is supported for video sites, not direct files."
                )

            resolutions = []
            if not found_task_id and format_id != "audio_only":
                resolutions = extractor.get_video_resolutions(info)

        except (ValueError, TypeError, OSError) as e:
            logger.error(f"Error fetching info: {e}")
            show_error(str(e), "Error fetching info")
            if not is_interactive:
                raise typer.Exit(code=1)
            return False
        except Exception as e:  # noqa: BLE001 - convert extractor failures to CLI errors
            logger.error(f"Error fetching info: {e}")
            show_error(str(e))
            if not is_interactive:
                raise typer.Exit(code=1)
            return False

    # ── quality selection & ffmpeg check ──────────────────────────────────────
    if not found_task_id:
        if format_id != "audio_only":
            if not resolutions:
                show_error("No video resolutions found.")
                if not is_interactive:
                    raise typer.Exit(code=1)
                return False

            from rich.markup import escape

            console.print(
                f"[bold cyan]•[/] Fetched info for: [bold white]{escape(title)}[/]"
            )

            from idm_cli.config import load_config as _load_config

            default_quality = _load_config().get("default_quality", "720p")
            selected_res = ask_quality(
                resolutions, loop_quality, format_id, default_quality
            )
            if selected_res is None:
                if not is_interactive:
                    raise typer.Exit(code=1)
                return False

            selected_format = next(
                r for r in resolutions if r["resolution"] == selected_res
            )
            format_id = selected_format["format_id"]
            needs_ffmpeg = not selected_format.get("pre_muxed", True)
        else:
            needs_ffmpeg = format_id == "audio_only"

        safe_title = sanitize_filename(title)

        from idm_cli.config import CONFIG_DIR, _get_default_download_dir, load_config
        from idm_cli.downloader.muxer import get_ffmpeg_path

        if needs_ffmpeg and not get_ffmpeg_path():
            method = ask_ffmpeg_install(is_interactive)
            ok = install_ffmpeg(method, is_interactive)
            if not ok:
                if not is_interactive:
                    raise typer.Exit(code=1)
                return False

        config = load_config()
        downloads_dir = config.get("download_dir", _get_default_download_dir())
        os.makedirs(downloads_dir, exist_ok=True)

        tmp_dir = os.path.join(CONFIG_DIR, "tmp")
        os.makedirs(tmp_dir, exist_ok=True)
        tmp_stem = f"{safe_title}_{task_id}"

        if format_id == "direct_file":
            video_dest = os.path.join(tmp_dir, tmp_stem)
            audio_dest = ""
            final_dest = _available_path(os.path.join(downloads_dir, safe_title))
        elif format_id == "audio_only":
            video_dest = ""
            audio_dest = os.path.join(tmp_dir, f"{tmp_stem}_audio.m4a")
            final_dest = _available_path(
                os.path.join(downloads_dir, f"{safe_title}.mp3")
            )
        else:
            video_dest = os.path.join(tmp_dir, f"{tmp_stem}_video.mp4")
            audio_dest = os.path.join(tmp_dir, f"{tmp_stem}_audio.m4a")
            final_dest = _available_path(
                os.path.join(downloads_dir, f"{safe_title}.mp4")
            )

        if loop_queue:
            save_download(
                task_id,
                url_to_extract,
                format_id,
                title,
                video_dest,
                audio_dest,
                final_dest,
                status="queued",
            )
            show_queued()
            if not is_interactive:
                raise typer.Exit(code=0)
            return False

    # ── determine media_type label ─────────────────────────────────────────────
    if format_id == "direct_file":
        ext = os.path.splitext(final_dest)[1].replace(".", "").upper()
        media_type = f"{ext} File" if ext else "File"
    elif format_id == "audio_only":
        media_type = "Audio"
    else:
        media_type = "Video"

    # ── extract download URLs ──────────────────────────────────────────────────
    with console.status("[bold cyan]Extracting URLs...", spinner="dots"):
        try:
            # Reuse the extractor resolved during the metadata fetch — do NOT
            # re-probe. A second probe can return a different extractor and break
            # extraction (this was the resume failure for direct files).
            if extractor is None:
                extractor = get_extractor(url_to_extract)
            extracted = extractor.extract_urls(info, format_id)
            video_url = extracted.get("video_url")
            audio_url = extracted.get("audio_url")
            headers = extracted.get("headers", {})
            if not video_url:
                video_dest = ""
            if not audio_url:
                audio_dest = ""
            if not video_url and not audio_url:
                raise ValueError(
                    "The selected format did not provide a downloadable URL."
                )
        except (ValueError, TypeError, OSError) as e:
            logger.error(f"Error extracting URLs: {e}")
            show_error(str(e), "Error extracting URLs")
            if not is_interactive:
                raise typer.Exit(code=1)
            return False

    save_download(
        task_id,
        url_to_extract,
        format_id,
        title,
        video_dest,
        audio_dest,
        final_dest,
        status="interrupted",
    )

    show_download_start(loop_chunks)

    pause_event = asyncio.Event()
    pause_event.set()
    warning_state = {"show": False}

    restore_sigint = setup_ctrl_c(warning_state)

    try:
        run_download_and_mux(
            video_url,
            audio_url,
            headers,
            loop_chunks,
            video_dest,
            audio_dest,
            final_dest,
            media_type,
            pause_event,
            warning_state,
            title=title,
        )
    except KeyboardInterrupt:
        show_download_cancelled()
        return False
    except ConnectionError as e:
        show_error(str(e))
        if not is_interactive:
            raise typer.Exit(code=1)
        return False
    except (ValueError, TypeError, OSError) as e:
        logger.error(f"Download failed: {e}")
        show_error(str(e), "Download failed")
        if not is_interactive:
            raise typer.Exit(code=1)
        return False
    except Exception as e:  # noqa: BLE001 - keep the CLI from printing a traceback
        # Catch-all for unexpected errors (e.g. aiohttp.ClientResponseError that
        # escaped retry logic). Show a clean message instead of a traceback.
        logger.error(f"Unexpected download error: {e}")
        show_error(str(e), "Download failed")
        if not is_interactive:
            raise typer.Exit(code=1)
        return False
    finally:
        restore_sigint()

    show_success(media_type, final_dest)
    remove_download(task_id)

    if not is_interactive:
        raise typer.Exit(code=0)
    return True
