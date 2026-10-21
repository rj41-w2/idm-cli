"""Exercise caller cancellation at the download and display cleanup boundaries."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from idm_cli.downloader import downloader
from idm_cli.ui import progress


@pytest.mark.parametrize(
    "mode",
    ["success", "download_cancel", "cleanup_cancel", "download_error", "refresh_error"],
)
async def test_run_with_progress_cleanup_preserves_outcome(mode):
    download_started = asyncio.Event()
    never = asyncio.Event()
    real_create_task = asyncio.create_task
    children = []
    session_closed = False
    original_warning = progress.logger.warning
    live = MagicMock()
    if mode == "refresh_error":
        live.__enter__.return_value.update.side_effect = RuntimeError("refresh failed")

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            nonlocal session_closed
            session_closed = True
            return False

    async def fake_download(*args, **kwargs):
        download_started.set()
        if mode == "download_cancel":
            await never.wait()
        if mode == "download_error":
            raise ValueError("download failed")

    class RefreshTask(asyncio.Task):
        cancellation_scheduled = False

        def cancel(self, *args, **kwargs):
            if mode == "cleanup_cancel" and not self.cancellation_scheduled:
                self.cancellation_scheduled = True
                # Deliver caller cancellation once cleanup starts awaiting the
                # refresh task. Its real coroutine and sleep run unchanged.
                asyncio.get_running_loop().call_soon(parent.cancel)
            return super().cancel(*args, **kwargs)

    def create_child(coro):
        child = (
            RefreshTask(coro)
            if coro.cr_code.co_name == "_refresh_loop"
            else real_create_task(coro)
        )
        children.append(child)
        return child

    with patch.object(downloader, "make_session", return_value=Session()), patch.object(
        downloader, "download_file", side_effect=fake_download
    ), patch.object(progress, "Live", return_value=live), patch.object(
        asyncio, "create_task", side_effect=create_child
    ), patch.object(progress, "mute_console_logging") as mute, patch.object(
        progress, "unmute_console_logging"
    ) as unmute:
        parent = real_create_task(
            progress.run_with_progress(
                video_url="https://example.com/video",
                audio_url=None,
                headers={},
                chunks=1,
                video_dest="unused",
                audio_dest="",
                pause_event=None,
                warning_state={},
            )
        )
        if mode == "download_cancel":
            await asyncio.wait_for(download_started.wait(), timeout=2)
            parent.cancel()
        if mode in ("download_cancel", "cleanup_cancel"):
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(parent, timeout=2)
            assert parent.cancelled()
        elif mode == "download_error":
            with pytest.raises(ValueError, match="download failed"):
                await asyncio.wait_for(parent, timeout=2)
        elif mode == "refresh_error":
            with pytest.raises(RuntimeError, match="refresh failed"):
                await asyncio.wait_for(parent, timeout=2)
        else:
            assert await asyncio.wait_for(parent, timeout=2) is None
        mute.assert_called_once_with()
        unmute.assert_called_once_with()
    assert session_closed
    live.__exit__.assert_called_once()
    assert children and all(child.done() for child in children)
    assert progress.logger.warning == original_warning
