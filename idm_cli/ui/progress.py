"""
ui/progress.py
--------------
All Rich terminal UI for active downloads:
  - Progress bars (video + audio)
  - Live panel with retry status
  - Pause / Ctrl+C warning display
  - progress_listener coroutine (queue -> progress bar updates)

downloader/ modules must NOT import Rich/UI from here.
download_file is called directly via lazy import to avoid circular deps.
"""

from __future__ import annotations

import asyncio
import re as _re

from rich.console import Group
from rich.live import Live
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.text import Text

from idm_cli.config import logger, mute_console_logging, unmute_console_logging
from idm_cli.ui.utils import check_key_press, console

__all__ = ["progress_listener", "run_with_progress"]


async def progress_listener(
    queue: asyncio.Queue,
    progress: Progress,
    pause_event: asyncio.Event | None = None,
    warning_state: dict | None = None,
) -> None:
    """Drain the progress-update queue and advance the Rich progress bars."""
    while True:
        if pause_event:
            key = check_key_press()
            if key:
                if key == "p" and pause_event.is_set():
                    pause_event.clear()
                    for task in progress.tasks:
                        if "Paused" not in task.description:
                            progress.update(
                                task.id,
                                description=f"[bold yellow]Paused[/] {task.description}",
                            )
                elif key == "r" and not pause_event.is_set():
                    pause_event.set()
                    for task in progress.tasks:
                        if "Paused" in task.description:
                            new_desc = task.description.replace(
                                "[bold yellow]Paused[/] ", ""
                            )
                            progress.update(task.id, description=new_desc)

        try:
            update = await asyncio.wait_for(queue.get(), timeout=0.1)
        except asyncio.TimeoutError:
            continue

        if update is None:
            break  # sentinel — download finished

        task_id = update.get("task_id")
        if "total_size" in update:
            progress.update(task_id, total=update["total_size"])
        elif "bytes_downloaded" in update:
            progress.advance(task_id, advance=update["bytes_downloaded"])

        queue.task_done()


async def run_with_progress(
    *,
    video_url: str,
    audio_url: str,
    headers: dict,
    chunks: int,
    video_dest: str,
    audio_dest: str,
    pause_event: asyncio.Event,
    warning_state: dict,
) -> None:
    """
    Run parallel downloads with a full Rich Live progress display.
    Lazy-imports download_file to avoid circular imports.
    """
    from idm_cli.downloader.downloader import (
        download_file,
        make_session,
    )  # lazy — avoids circular

    queue: asyncio.Queue = asyncio.Queue()

    # ── retry state ────────────────────────────────────────────────────────────
    retry_state: dict = {"chunks": {}}  # {str(chunk_idx): (retry_num, retry_max)}

    original_warning = logger.warning

    def _capture_warning(msg, *args, **kwargs):
        m = _re.search(r"Chunk\s+(\d+)\s+retry\s+(\d+)/(\d+)", str(msg))
        if m:
            retry_state["chunks"][m.group(1)] = (int(m.group(2)), int(m.group(3)))
        original_warning(msg, *args, **kwargs)

    logger.warning = _capture_warning

    def _on_chunk_done(chunk_index: int) -> None:
        retry_state["chunks"].pop(str(chunk_index), None)

    mute_console_logging()

    try:
        # ── progress bars ──────────────────────────────────────────────────────
        progress = Progress(
            SpinnerColumn("dots12"),
            TextColumn("[bold cyan]{task.description:<8}", justify="left"),
            BarColumn(
                bar_width=38,
                complete_style="cyan",
                finished_style="bold green",
                pulse_style="bold white",
            ),
            TextColumn("[progress.percentage]{task.percentage:>5.1f}%"),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=console,
            expand=False,
        )

        video_task_id = progress.add_task("Video", total=None) if video_url else None
        audio_task_id = progress.add_task("Audio", total=None) if audio_url else None

        # ── live display builder ───────────────────────────────────────────────
        def _build_display() -> Group:
            rows: list = [progress]

            if retry_state["chunks"]:
                max_retry, max_of = max(
                    retry_state["chunks"].values(), key=lambda x: x[0]
                )
                chunk_ids = ", ".join(sorted(retry_state["chunks"].keys(), key=int))
                rows.append(
                    Text.from_markup(
                        f" [bold yellow]⚠ chunk {chunk_ids} retry {max_retry}/{max_of}[/]"
                    )
                )

            if warning_state.get("show"):
                rows.append(
                    Text.from_markup(
                        "[bold yellow]⚠  Press Ctrl+C again within 5 s to cancel[/]"
                    )
                )

            return Group(*rows)

        # ── live loop ──────────────────────────────────────────────────────────
        results: list = []
        with Live(_build_display(), console=console, refresh_per_second=10) as live:

            async def _refresh_loop() -> None:
                while True:
                    live.update(_build_display())
                    await asyncio.sleep(0.1)

            refresh_task = asyncio.create_task(_refresh_loop())
            listener = asyncio.create_task(
                progress_listener(queue, progress, pause_event, warning_state)
            )

            async with make_session() as session:
                v_task = (
                    asyncio.create_task(
                        download_file(
                            session,
                            video_url,
                            video_dest,
                            headers,
                            chunks,
                            queue,
                            video_task_id,
                            pause_event,
                            on_chunk_done=_on_chunk_done,
                        )
                    )
                    if video_url
                    else None
                )
                a_task = (
                    asyncio.create_task(
                        download_file(
                            session,
                            audio_url,
                            audio_dest,
                            headers,
                            chunks,
                            queue,
                            audio_task_id,
                            pause_event,
                            on_chunk_done=_on_chunk_done,
                        )
                    )
                    if audio_url
                    else None
                )

                results = await asyncio.gather(
                    *[t for t in (v_task, a_task) if t is not None],
                    return_exceptions=True,
                )

            await queue.put(None)
            await listener
            refresh_task.cancel()
            try:
                await refresh_task
            except asyncio.CancelledError:
                pass

        # Re-raise the first real exception after Live has closed cleanly
        for r in results:
            if isinstance(r, BaseException):
                raise r

    finally:
        logger.warning = original_warning
        unmute_console_logging()
