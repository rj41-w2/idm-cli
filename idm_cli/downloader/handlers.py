"""
downloader/handlers.py
----------------------
Queue and resume handlers — no direct UI output.
All console/questionary calls go through ui/prompts.py.
"""

from __future__ import annotations

import asyncio
import os

import psutil
import typer
from rich.markup import escape

from idm_cli.config import CONFIG_DIR, logger
from idm_cli.downloader.core import run_download_and_mux
from idm_cli.downloader.paths import validate_download_paths
from idm_cli.downloader.state import get_incomplete_downloads, remove_download
from idm_cli.extractors import get_extractor

__all__ = ["handle_queue", "handle_resume"]

LOCK_FILE = os.path.join(CONFIG_DIR, "queue.lock")


# ── queue lock helpers ─────────────────────────────────────────────────────────


def _is_daemon_running_by_pid(pid: int) -> bool:
    """Check whether *pid* belongs to one of our CLI processes."""
    if not psutil.pid_exists(pid):
        return False
    try:
        name = psutil.Process(pid).name()
        return "python" in name.lower() or "idm" in name.lower()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return False


def _is_daemon_running() -> bool:
    if not os.path.exists(LOCK_FILE):
        return False
    try:
        with open(LOCK_FILE, "r") as f:
            pid = int(f.read().strip())
        if pid == os.getpid():
            return False
        if not psutil.pid_exists(pid):
            return False
        # PID exists — verify it is actually our CLI to avoid false
        # positives from PID reuse by unrelated processes.
        try:
            name = psutil.Process(pid).name()
            return "python" in name.lower() or "idm" in name.lower()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return False
    except (OSError, ValueError):
        return False


def _acquire_lock() -> bool:
    os.makedirs(os.path.dirname(LOCK_FILE), exist_ok=True)
    try:
        fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        try:
            os.write(fd, str(os.getpid()).encode())
        finally:
            os.close(fd)
        return True
    except FileExistsError:
        try:
            with open(LOCK_FILE, "r") as f:
                pid = int(f.read().strip())
            if _is_daemon_running_by_pid(pid):
                return False
        except (OSError, ValueError):
            pass
        try:
            os.remove(LOCK_FILE)
        except OSError:
            pass
        return _acquire_lock()


def _release_lock() -> None:
    if not os.path.exists(LOCK_FILE):
        return
    try:
        with open(LOCK_FILE, "r") as f:
            pid = int(f.read().strip())
        if pid == os.getpid():
            os.remove(LOCK_FILE)
    except (OSError, ValueError):
        pass


# ── queue handler ──────────────────────────────────────────────────────────────


def handle_queue(is_interactive: bool, loop_chunks: int) -> None:
    # Lazy import to avoid downloader/* importing ui/* at module level
    # (see idm_cli/AGENTS.md layering rule).
    from idm_cli.ui.prompts import (
        show_error,
        show_queue_empty,
        show_queue_item_start,
        show_success,
    )
    from idm_cli.ui.utils import console

    if not _acquire_lock():
        show_error("Queue daemon is already running!")
        if not is_interactive:
            raise typer.Exit(code=1)
        return

    try:
        while True:
            incomplete = get_incomplete_downloads()
            queued = {
                tid: data
                for tid, data in incomplete.items()
                if data.get("status") == "queued"
            }
            if not queued:
                show_queue_empty()
                break

            tid, data = next(iter(queued.items()))
            show_queue_item_start(data["title"])

            url_to_extract = data["url"]
            format_id = data["format_id"]
            video_dest = data["video_dest"]
            audio_dest = data["audio_dest"]
            final_dest = data["final_dest"]

            with console.status("[bold cyan]Fetching metadata...", spinner="dots"):
                try:
                    # A queued direct_file must use the direct extractor; never
                    # re-probe (the probe is flaky and may route to yt-dlp).
                    if format_id == "direct_file":
                        import importlib

                        extractor = importlib.import_module("idm_cli.extractors.direct")
                    else:
                        extractor = get_extractor(url_to_extract)
                    info = extractor.fetch_all_info(url_to_extract)
                except Exception as e:  # noqa: BLE001 - queue must continue safely
                    logger.error(f"Error fetching info: {e}")
                    show_error(str(e), "Error fetching info")
                    remove_download(tid)
                    continue

            if format_id == "direct_file":
                ext = os.path.splitext(final_dest)[1].replace(".", "").upper()
                media_type = f"{ext} File" if ext else "File"
            elif format_id == "audio_only":
                media_type = "Audio"
            else:
                media_type = "Video"

            with console.status("[bold cyan]Extracting URLs...", spinner="dots"):
                try:
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
                            "The queued format did not provide a downloadable URL."
                        )
                except Exception as e:  # noqa: BLE001 - queue must continue safely
                    logger.error(f"Error extracting URLs: {e}")
                    show_error(str(e), "Error extracting URLs")
                    remove_download(tid)
                    continue

            pause_event = asyncio.Event()
            pause_event.set()
            warning_state = {"show": False}

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
                )
                remove_download(tid)
                show_success(media_type, final_dest)
            except KeyboardInterrupt:
                break
            except ConnectionError as e:
                show_error(str(e))
                logger.error(f"Connection failed for {data['title']}: {e}")
                break
            except Exception as e:  # noqa: BLE001 - keep the queue daemon alive
                logger.error(f"Download failed: {e}")
                show_error(str(e), "Download failed")
                remove_download(tid)
    finally:
        _release_lock()

    if not is_interactive:
        raise typer.Exit(code=0)


# ── resume handler ─────────────────────────────────────────────────────────────


def handle_resume(is_interactive: bool) -> tuple[str, dict] | None:
    """
    Returns (task_id, task_data) tuple if user chose to resume,
    or None if cancelled / deleted / no downloads.
    """
    # Lazy import to avoid downloader/* importing ui/* at module level
    # (see idm_cli/AGENTS.md layering rule).
    from idm_cli.ui.prompts import ask_resume_action, show_error
    from idm_cli.ui.utils import console

    incomplete = get_incomplete_downloads()
    result = ask_resume_action(incomplete)

    if result is None:
        if not incomplete and not is_interactive:
            raise typer.Exit(code=1)
        return None

    action, tid = result
    task_data = incomplete[tid]
    try:
        validate_download_paths(
            task_data["video_dest"], task_data["audio_dest"], task_data["final_dest"]
        )
    except (ValueError, OSError, RuntimeError) as e:
        show_error(str(e), "Unsafe saved download")
        if not is_interactive:
            raise typer.Exit(code=1)
        return None

    if action == "delete":
        remove_download(tid)
        for path in (task_data["video_dest"], task_data["audio_dest"]):
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
            if path:
                progress_file = f"{path}.progress.json"
                if os.path.exists(progress_file):
                    try:
                        os.remove(progress_file)
                    except OSError:
                        pass
        console.print(f"[bold cyan]✗[/] Deleted: {escape(str(task_data['title']))}")
        if not is_interactive:
            raise typer.Exit(code=0)
        return None

    # action == "resume"
    console.print(
        f"[bold cyan]»[/] Resuming download for: {escape(str(task_data['title']))}\n"
    )
    return tid, task_data
