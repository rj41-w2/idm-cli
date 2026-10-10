"""Offline tests for ui/progress.py and update_checker.py."""

import asyncio
import json
import urllib.error
from unittest.mock import patch

from rich.progress import Progress

from idm_cli.ui.progress import progress_listener

# ── progress_listener sentinel behaviour (FIX B) ──────────────────────────────


def test_progress_listener_sentinel_calls_task_done():
    """After the None sentinel, queue.unfinished_tasks must be 0."""
    asyncio.run(_test_sentinel())


async def _test_sentinel():
    queue = asyncio.Queue()
    progress = Progress()
    task_id = progress.add_task("test", total=10)

    # Put one real update then the sentinel
    queue.put_nowait({"task_id": task_id, "total_size": 10})
    queue.put_nowait(None)

    await asyncio.wait_for(progress_listener(queue, progress), timeout=5)

    # If task_done() was called for all items (including sentinel), join() returns
    await asyncio.wait_for(queue.join(), timeout=1)


def test_progress_listener_processes_updates():
    """Listener applies updates before the sentinel arrives."""
    asyncio.run(_test_updates())


async def _test_updates():
    queue = asyncio.Queue()
    progress = Progress()
    task_id = progress.add_task("test", total=None)

    queue.put_nowait({"task_id": task_id, "total_size": 100})
    queue.put_nowait({"task_id": task_id, "bytes_downloaded": 50})
    queue.put_nowait(None)

    await asyncio.wait_for(progress_listener(queue, progress), timeout=5)

    task = progress.tasks[0]
    assert task.total == 100
    assert task.completed == 50
    await asyncio.wait_for(queue.join(), timeout=1)


# ── update_checker version-comparison fallback ────────────────────────────────


def test_parse_ver_basic():
    """_parse_ver splits version strings into comparable tuples."""
    from idm_cli.update_checker import _parse_ver

    assert _parse_ver("1.2.3") == (1, 2, 3)
    assert _parse_ver("2.0.0") > _parse_ver("1.9.9")
    assert _parse_ver("1.0.0") > _parse_ver("1.0")
    assert _parse_ver("0.0.0") >= (0, 0)


# ── update_checker network-failure safety ─────────────────────────────────────


def test_check_for_updates_never_raises_on_network_failure(tmp_path, monkeypatch):
    """check_for_updates must not raise when urlopen fails."""
    monkeypatch.setattr("idm_cli.config.CONFIG_DIR", str(tmp_path))

    def _boom(*args, **kwargs):
        raise urllib.error.URLError("no network")

    with patch("urllib.request.urlopen", side_effect=_boom):
        from idm_cli.update_checker import check_for_updates

        check_for_updates()  # must not raise


def test_check_for_updates_no_cache_write_on_failure(tmp_path, monkeypatch):
    """last_check.json must NOT be written when the PyPI fetch fails."""
    monkeypatch.setattr("idm_cli.config.CONFIG_DIR", str(tmp_path))

    def _boom(*args, **kwargs):
        raise urllib.error.URLError("no network")

    with patch("urllib.request.urlopen", side_effect=_boom):
        from idm_cli.update_checker import check_for_updates

        check_for_updates()

    last_check_file = tmp_path / "last_check.json"
    assert not last_check_file.exists()


def test_check_for_updates_writes_cache_on_success(tmp_path, monkeypatch):
    """last_check.json IS written when the fetch succeeds and version is newer."""
    monkeypatch.setattr("idm_cli.config.CONFIG_DIR", str(tmp_path))

    class _FakeResponse:
        def read(self):
            return json.dumps({"info": {"version": "99.0.0"}}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    with patch("urllib.request.urlopen", return_value=_FakeResponse()):
        from idm_cli.update_checker import check_for_updates

        check_for_updates()

    last_check_file = tmp_path / "last_check.json"
    assert last_check_file.exists()
    data = json.loads(last_check_file.read_text())
    assert "last_check_time" in data
