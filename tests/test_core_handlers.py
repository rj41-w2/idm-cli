"""Offline tests for core.py and handlers.py fixes (FIX A–E)."""

from __future__ import annotations

import inspect
import os
from unittest.mock import patch

import pytest
import typer

from idm_cli.downloader.core import _available_path, _finalize_single_video
from idm_cli.downloader.handlers import (
    _acquire_lock,
    _is_daemon_running,
    handle_resume,
)

# ---------------------------------------------------------------------------
# FIX A — _finalize_single_video (shutil.move → os.replace, clean error)
# ---------------------------------------------------------------------------


def test_finalize_single_video_success(tmp_path):
    src = tmp_path / "video.mp4"
    src.write_bytes(b"video data")
    dst = tmp_path / "final.mp4"
    _finalize_single_video(str(src), str(dst))
    assert dst.read_bytes() == b"video data"
    assert not src.exists()


def test_finalize_single_video_oserror_raises_runtime(tmp_path):
    src = tmp_path / "video.mp4"
    src.write_bytes(b"data")
    dst = tmp_path / "final.mp4"
    with patch(
        "idm_cli.downloader.core.os.replace", side_effect=OSError("locked")
    ), patch(
        "idm_cli.downloader.core.shutil.move", side_effect=OSError("locked")
    ), pytest.raises(RuntimeError, match="Could not move downloaded file"):
        _finalize_single_video(str(src), str(dst))


def test_finalize_single_video_fallback_to_shutil_move(tmp_path):
    """os.replace fails (e.g. cross-device) but shutil.move succeeds."""
    src = tmp_path / "video.mp4"
    src.write_bytes(b"data")
    dst = tmp_path / "final.mp4"
    move_called = False

    def fake_move(s, d):
        nonlocal move_called
        move_called = True
        os.rename(s, d)

    with patch(
        "idm_cli.downloader.core.os.replace", side_effect=OSError("cross-device")
    ), patch("idm_cli.downloader.core.shutil.move", side_effect=fake_move):
        _finalize_single_video(str(src), str(dst))
    assert move_called
    assert dst.exists()


# ---------------------------------------------------------------------------
# FIX B — _available_path treats directories as occupied
# ---------------------------------------------------------------------------


def test_available_path_with_existing_file(tmp_path):
    base = tmp_path / "file.txt"
    base.write_text("old")
    result = _available_path(str(base))
    assert result == str(tmp_path / "file (1).txt")
    assert not os.path.exists(result)


def test_available_path_with_existing_directory(tmp_path):
    """A directory at the base path must be treated as taken, and the
    returned path must be a new non-existent file path."""
    base = tmp_path / "file.txt"
    base.mkdir()
    result = _available_path(str(base))
    assert result != str(base)
    assert not os.path.exists(result)
    # Should have produced "file (1).txt" since the base is a directory
    assert result == str(tmp_path / "file (1).txt")


def test_available_path_no_conflict(tmp_path):
    base = tmp_path / "new.txt"
    result = _available_path(str(base))
    assert result == str(base)


# ---------------------------------------------------------------------------
# FIX D — _is_daemon_running PID-reuse hardening
# ---------------------------------------------------------------------------


def test_is_daemon_running_no_lock_file(tmp_path):
    with patch("idm_cli.downloader.handlers.LOCK_FILE", str(tmp_path / "queue.lock")):
        assert _is_daemon_running() is False


def test_is_daemon_running_bogus_high_pid(tmp_path):
    """A very high PID that doesn't exist → False."""
    lock = tmp_path / "queue.lock"
    lock.write_text("99999999")
    with patch("idm_cli.downloader.handlers.LOCK_FILE", str(lock)):
        assert _is_daemon_running() is False


def test_is_daemon_running_pid_reuse_not_our_process(tmp_path):
    """PID exists but belongs to an unrelated process → False."""
    lock = tmp_path / "queue.lock"
    # Use a PID that almost certainly exists and is NOT our CLI:
    # on Linux, PID 1 is init/systemd, never a Python process.
    lock.write_text("1")
    with patch("idm_cli.downloader.handlers.LOCK_FILE", str(lock)):
        # On some systems PID 1 might be named "systemd" or "init" — neither
        # contains "python" or "idm", so this should be False.
        assert _is_daemon_running() is False


def test_is_daemon_running_pid_reuse_is_python(tmp_path):
    """PID exists and process name contains 'python' → True."""
    lock = tmp_path / "queue.lock"
    real_pid = os.getpid()
    # Write our own PID (always exists, and is a Python process).
    # Patch getpid to return a different value so the early-return
    # `pid == os.getpid()` doesn't fire.
    lock.write_text(str(real_pid))
    with patch("idm_cli.downloader.handlers.LOCK_FILE", str(lock)), patch(
        "idm_cli.downloader.handlers.os.getpid", return_value=real_pid + 1
    ):
        assert _is_daemon_running() is True


# ---------------------------------------------------------------------------
# FIX D — _acquire_lock also hardened
# ---------------------------------------------------------------------------


def test_acquire_lock_bogus_pid_removes_stale_lock(tmp_path):
    """A stale lock with a bogus PID should be removed and lock acquired."""
    lock = tmp_path / "queue.lock"
    lock.write_text("99999999")
    with patch("idm_cli.downloader.handlers.LOCK_FILE", str(lock)):
        assert _acquire_lock() is True
        # Lock file should now contain our PID
        assert int(lock.read_text().strip()) == os.getpid()


def test_acquire_lock_existing_python_process(tmp_path):
    """Lock held by a live Python process → should return False."""
    lock = tmp_path / "queue.lock"
    # Write a PID that exists and is a Python process (our own)
    lock.write_text(str(os.getpid()))
    with patch("idm_cli.downloader.handlers.LOCK_FILE", str(lock)):
        # _acquire_lock reads the PID, calls _is_daemon_running_by_pid → True
        # because our process name contains "python", so it should return False.
        assert _acquire_lock() is False


# ---------------------------------------------------------------------------
# FIX E — handle_resume return annotation exists
# ---------------------------------------------------------------------------


def test_handle_resume_has_return_annotation():
    sig = inspect.signature(handle_resume)
    # The annotation should be present (not empty)
    assert sig.return_annotation is not inspect.Parameter.empty


# ---------------------------------------------------------------------------
# Regression: extractor is resolved ONCE (flaky probe must not break resume)
# ---------------------------------------------------------------------------


def test_process_download_resolves_extractor_once(tmp_path):
    """A flaky get_extractor() must not break extraction.

    Regression: core.py used to call get_extractor() twice (once for
    fetch_all_info, once for extract_urls). Because the direct-file probe is a
    flaky network call, the two calls could return different extractors, making
    a direct file fail with "did not provide a downloadable URL".

    This test patches get_extractor so the FIRST call returns the direct
    extractor and every later call returns yt-dlp (simulating a flaky probe),
    then drives a real local download and asserts it still succeeds.
    """
    import importlib
    import threading
    from functools import partial
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

    from idm_cli.downloader import core

    srv_dir = tmp_path / "srv"
    srv_dir.mkdir()
    payload = b"x" * (512 * 1024)
    (srv_dir / "f.bin").write_bytes(payload)

    handler = partial(SimpleHTTPRequestHandler, directory=str(srv_dir))
    handler.log_message = lambda *a, **k: None
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    direct = importlib.import_module("idm_cli.extractors.direct")
    ytdlp = importlib.import_module("idm_cli.extractors.ytdlp")
    calls = {"n": 0}

    def flaky(url):
        calls["n"] += 1
        return direct if calls["n"] == 1 else ytdlp

    downloads_dir = tmp_path / "dl"
    downloads_dir.mkdir()
    conf_dir = tmp_path / "conf"
    conf_dir.mkdir()

    url = f"http://localhost:{port}/f.bin"
    try:
        with patch.object(core, "get_extractor", flaky), patch(
            "idm_cli.config.CONFIG_DIR", str(conf_dir)
        ), patch("idm_cli.downloader.state.STATE_DIR", str(conf_dir)), patch(
            "idm_cli.downloader.state.STATE_FILE", str(conf_dir / "state.json")
        ), patch(
            "idm_cli.config.load_config",
            return_value={"download_dir": str(downloads_dir), "default_chunks": 4},
        ), pytest.raises(typer.Exit):
            # Non-interactive success raises typer.Exit(0).
            core.process_download(
                current_url=url,
                is_interactive=False,
                loop_quality="direct",
                loop_audio_only=False,
                loop_queue=False,
                loop_chunks=4,
                loop_filename=None,
            )
    finally:
        httpd.shutdown()

    # Extractor resolved exactly once → flaky second probe never happened.
    assert calls["n"] == 1
    out = downloads_dir / "f.bin"
    assert out.exists(), "download did not complete"
    assert out.stat().st_size == len(payload)


# ---------------------------------------------------------------------------
# Import safety
# ---------------------------------------------------------------------------


def test_imports_work():
    """Verify the names we need are importable."""
    from idm_cli.downloader.core import _available_path, _finalize_single_video  # noqa: F401
    from idm_cli.downloader.handlers import (  # noqa: F401
        _acquire_lock,
        _is_daemon_running,
        handle_resume,
    )
