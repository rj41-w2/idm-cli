import contextlib
import json
from unittest.mock import patch

import pytest

from idm_cli.config import save_config
from idm_cli.downloader.downloader import _FALLBACK_UA, _download_chunk, download_file
from idm_cli.extractors.direct import extract_urls
from idm_cli.ui.utils import _is_public_host, is_valid_url


class _Response:
    def __init__(self, status_code=206, headers=None, body=b""):
        self.status_code = status_code
        self.headers = (
            headers if headers is not None else {"Content-Range": "bytes 0-2/3"}
        )
        self._body = body

    def raise_for_status(self):
        return None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def aiter_content(self, chunk_size=1024):
        if self._body:
            yield self._body

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


class _Session:
    def __init__(self, response):
        self.response = response

    def stream(self, *args, **kwargs):
        return self.response


class _FallbackSession:
    """Fake session: returns 403 on the first stream() call, then 206.

    Also records the headers passed to each stream() call so the test
    can assert that the fallback User-Agent was applied on the retry.
    """

    def __init__(self):
        self.headers_seen: list = []
        self._calls = 0

    def stream(self, *args, **kwargs):
        self.headers_seen.append(kwargs.get("headers", {}))
        self._calls += 1
        if self._calls == 1:
            return _Response(status_code=403, headers={})
        return _Response(status_code=206, body=b"abc")


def test_download_rejects_invalid_chunk_count():
    with pytest.raises(ValueError, match="between 1 and 32"):
        import asyncio

        asyncio.run(download_file(None, "https://example.com/file", "file", {}, 0))


def test_parallel_chunk_rejects_server_that_ignores_range(tmp_path):
    import asyncio

    response = _Response(status_code=200, headers={"Content-Length": "3"})
    with pytest.raises(ValueError, match="ignored byte range"):
        asyncio.run(
            _download_chunk(
                _Session(response),
                "https://example.com/file",
                0,
                2,
                0,
                str(tmp_path / "file"),
                {},
                None,
                None,
            )
        )


def test_url_validation_rejects_missing_host_and_accepts_https():
    assert is_valid_url("https://example.com/file")
    assert not is_valid_url("https://")
    assert not is_valid_url("javascript:alert(1)")


def test_is_valid_url_rejects_private_internal_hosts():
    assert not is_valid_url("http://localhost:8080")
    assert not is_valid_url("http://127.0.0.1/x")
    assert not is_valid_url("http://10.0.0.1")
    assert not is_valid_url("http://192.168.1.1")
    assert not is_valid_url("http://169.254.169.254/latest/meta-data")
    assert not is_valid_url("http://[::1]/")
    assert not is_valid_url("http://[fe80::1]/")
    assert not is_valid_url("http://[fc00::1]/")
    assert not is_valid_url("http://[::]/")
    assert not is_valid_url("http://0.0.0.0")
    assert not is_valid_url("http://172.16.0.1/file")


def test_is_valid_url_accepts_public_hosts():
    assert is_valid_url("https://example.com/file")
    assert is_valid_url("https://youtube.com/watch?v=123")
    assert is_valid_url("https://www.google.com")


def test_is_public_host_rejects_internal_hostnames():
    assert not _is_public_host("localhost")
    assert not _is_public_host("foo.localhost")
    assert not _is_public_host("foo.local")
    assert not _is_public_host("foo.internal")


def test_is_public_host_rejects_reserved_ips():
    assert not _is_public_host("127.0.0.1")
    assert not _is_public_host("10.0.0.1")
    assert not _is_public_host("172.16.0.1")
    assert not _is_public_host("192.168.1.1")
    assert not _is_public_host("169.254.169.254")
    assert not _is_public_host("0.0.0.0")
    assert not _is_public_host("::1")
    assert not _is_public_host("fe80::1")
    assert not _is_public_host("fc00::1")
    assert not _is_public_host("::")


def test_is_public_host_accepts_public_ips_and_hostnames():
    assert _is_public_host("8.8.8.8")
    assert _is_public_host("1.1.1.1")
    assert _is_public_host("example.com")
    assert _is_public_host("www.google.com")


def test_direct_extractor_does_not_turn_audio_only_into_audio():
    extracted = extract_urls(
        {"url": "https://example.com/file.zip", "title": "file.zip"},
        "audio_only",
    )
    assert extracted["audio_url"] is None
    assert extracted["video_url"] == "https://example.com/file.zip"


# ── 403 fallback User-Agent ──────────────────────────────────────────────────


def test_download_chunk_retries_with_fallback_ua_on_403(tmp_path):
    """A 403 response triggers a retry with the fallback User-Agent (curl/8.0)."""
    import asyncio

    session = _FallbackSession()
    dest = str(tmp_path / "file")

    result = asyncio.run(
        _download_chunk(
            session,
            "https://example.com/file",
            0,
            2,
            0,
            dest,
            {},
            None,
            None,
        )
    )

    assert result == dest
    assert len(session.headers_seen) == 2
    # First attempt: no User-Agent override (uses session default)
    assert "User-Agent" not in session.headers_seen[0]
    # Retry: fallback UA applied
    assert session.headers_seen[1].get("User-Agent") == _FALLBACK_UA


def test_download_chunk_retries_with_fallback_ua_on_401(tmp_path):
    """A 401 response also triggers the fallback UA retry."""
    import asyncio

    class _UnauthorizedSession:
        def __init__(self):
            self.headers_seen: list = []
            self._calls = 0

        def stream(self, *args, **kwargs):
            self.headers_seen.append(kwargs.get("headers", {}))
            self._calls += 1
            if self._calls == 1:
                return _Response(status_code=401, headers={})
            return _Response(status_code=206, body=b"abc")

    session = _UnauthorizedSession()
    dest = str(tmp_path / "file")

    result = asyncio.run(
        _download_chunk(
            session,
            "https://example.com/file",
            0,
            2,
            0,
            dest,
            {},
            None,
            None,
        )
    )

    assert result == dest
    assert len(session.headers_seen) == 2
    assert session.headers_seen[1].get("User-Agent") == _FALLBACK_UA


# ── Corrupted resume metadata recovery ────────────────────────────────────────


def test_download_chunk_recovers_from_negative_progress(tmp_path):
    """A negative chunk_progress value is reset to 0 instead of raising."""
    import asyncio

    response = _Response(status_code=206, body=b"abc")
    dest = str(tmp_path / "file")

    result = asyncio.run(
        _download_chunk(
            _Session(response),
            "https://example.com/file",
            0,
            2,
            0,
            dest,
            {},
            None,
            None,
            chunk_progress={"0": -5},
        )
    )

    assert result == dest


def test_download_chunk_recovers_from_non_int_progress(tmp_path):
    """A non-int chunk_progress value is reset to 0 instead of raising."""
    import asyncio

    response = _Response(status_code=206, body=b"abc")
    dest = str(tmp_path / "file")

    result = asyncio.run(
        _download_chunk(
            _Session(response),
            "https://example.com/file",
            0,
            2,
            0,
            dest,
            {},
            None,
            None,
            chunk_progress={"0": "bad"},
        )
    )

    assert result == dest


# ── Bool chunk count rejection ────────────────────────────────────────────────


def test_download_file_rejects_bool_num_chunks():
    """download_file(None, url, dest, {}, True) must raise ValueError."""
    import asyncio

    with pytest.raises(ValueError, match="between 1 and 32"):
        asyncio.run(download_file(None, "https://example.com/file", "file", {}, True))


def test_download_file_rejects_false_num_chunks():
    """download_file(None, url, dest, {}, False) must raise ValueError."""
    import asyncio

    with pytest.raises(ValueError, match="between 1 and 32"):
        asyncio.run(download_file(None, "https://example.com/file", "file", {}, False))


def test_download_file_rejects_zero_num_chunks():
    """download_file(None, url, dest, {}, 0) must raise ValueError."""
    import asyncio

    with pytest.raises(ValueError, match="between 1 and 32"):
        asyncio.run(download_file(None, "https://example.com/file", "file", {}, 0))


def test_download_file_rejects_33_num_chunks():
    """download_file(None, url, dest, {}, 33) must raise ValueError."""
    import asyncio

    with pytest.raises(ValueError, match="between 1 and 32"):
        asyncio.run(download_file(None, "https://example.com/file", "file", {}, 33))


def test_download_file_accepts_boundary_chunk_counts():
    """download_file accepts 1 and 32 chunks (boundary values)."""
    import asyncio

    # These should not raise — they pass validation
    # (they will fail later due to None session, but that's fine)
    for n in (1, 32):
        try:
            asyncio.run(download_file(None, "https://example.com/file", "file", {}, n))
        except ValueError:
            pytest.fail(f"download_file rejected valid chunk count {n}")
        except (AttributeError, TypeError):
            pass  # Other errors (e.g. None session) are expected


# ── Atomic save_config ────────────────────────────────────────────────────────


def test_save_config_is_atomic(tmp_path):
    """save_config writes atomically: no leftover temp files after success."""
    config_file = tmp_path / "config.json"

    with patch("idm_cli.config.CONFIG_FILE", str(config_file)):
        save_config({"default_chunks": 4})

    # File must exist and contain the value
    assert config_file.exists()
    data = json.loads(config_file.read_text(encoding="utf-8"))
    assert data["default_chunks"] == 4

    # No leftover temp files
    leftovers = list(tmp_path.glob("config_*.json"))
    assert leftovers == []


def test_save_config_no_leftover_on_error(tmp_path):
    """save_config logs (never raises) on write failure and leaves no temp file."""
    config_file = tmp_path / "config.json"

    # Force the atomic os.replace to fail; keep CONFIG_DIR in tmp_path so the
    # temp file (created via mkstemp) also lands there and can be inspected.
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch("idm_cli.config.CONFIG_DIR", str(tmp_path)))
        stack.enter_context(patch("idm_cli.config.CONFIG_FILE", str(config_file)))
        stack.enter_context(
            patch("idm_cli.config.os.replace", side_effect=OSError("boom"))
        )
        # save_config swallows OSError and logs it — must not propagate.
        save_config({"default_chunks": 4})

    # No leftover temp files
    leftovers = list(tmp_path.glob("config_*.json"))
    assert leftovers == []


# ── Quality prompt behaviour ──────────────────────────────────────────────────

_RES = [
    {"resolution": "1080p", "display_label": "1080p", "format_id": "137"},
    {"resolution": "720p", "display_label": "720p", "format_id": "136"},
    {"resolution": "360p", "display_label": "360p", "format_id": "18"},
]


def test_ask_quality_autoselects_on_non_tty():
    """On a non-TTY stdin, ask_quality never prompts (would raise EOFError)."""
    from idm_cli.ui.prompts import ask_quality

    with patch("sys.stdin.isatty", return_value=False):
        # No explicit quality → configured default wins
        assert ask_quality(_RES, None, "video", "720p") == "720p"
        assert ask_quality(_RES, None, "video", "1080p") == "1080p"
        # Unknown default → highest resolution
        assert ask_quality(_RES, None, "video", "nope") == "1080p"
        # Explicit quality always wins
        assert ask_quality(_RES, "360p", "video", "720p") == "360p"


def test_ask_quality_autoselects_single_resolution():
    """A single resolution is auto-selected without prompting."""
    from idm_cli.ui.prompts import ask_quality

    with patch("sys.stdin.isatty", return_value=False):
        assert ask_quality([_RES[1]], None, "video", "720p") == "720p"


def test_ask_quality_prompts_on_tty(monkeypatch):
    """On a TTY with multiple resolutions, the user is prompted."""
    from idm_cli.ui import prompts

    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    captured = {}

    class _Q:
        def ask(self, **kwargs):
            return "1080p"

    def fake_select(prompt, choices=None, style=None):
        captured["choices"] = choices
        return _Q()

    monkeypatch.setattr(prompts.questionary, "select", fake_select)

    result = prompts.ask_quality(_RES, None, "video", "720p")
    assert result == "1080p"
    # The configured default is listed first and marked.
    assert captured["choices"][0] == "720p  (default)"
