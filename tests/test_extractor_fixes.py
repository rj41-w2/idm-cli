"""Regression tests for extractor and UI fixes."""

import contextlib
from unittest.mock import MagicMock, patch

import pytest

from idm_cli.extractors.winget import WingetError, fetch_all_info
from idm_cli.extractors.ytdlp import (
    _video_format_count,
    extract_urls,
    get_video_resolutions,
)
from idm_cli.extractors.ytdlp import (
    fetch_all_info as ytdlp_fetch_all_info,
)
from idm_cli.ui.utils import check_key_press

# ── yt-dlp player-client selection (full resolution ladder) ───────────────────


def test_video_format_count_counts_distinct_heights():
    info = {
        "formats": [
            {"height": 1080, "vcodec": "avc1"},
            {"height": 720, "vcodec": "avc1"},
            {"height": 720, "vcodec": "vp9"},  # duplicate height
            {"height": 360, "vcodec": "avc1"},
            {"height": 360, "vcodec": "none"},  # audio-only, excluded
            {"height": None, "vcodec": "avc1"},  # no height, excluded
        ]
    }
    assert _video_format_count(info) == 3


def test_fetch_all_info_picks_client_with_most_resolutions():
    """fetch_all_info must keep the client that exposes the most resolutions.

    Regression: the old code tried ['android','ios'] first and returned it even
    when it only exposed 360p, silently limiting users to one quality.
    """
    limited = {
        "title": "t",
        "formats": [{"height": 360, "vcodec": "avc1", "protocol": "https"}],
    }
    full = {
        "title": "t",
        "formats": [
            {"height": h, "vcodec": "avc1", "protocol": "https"}
            for h in (1080, 720, 480, 360, 240, 144)
        ],
    }

    def fake_extract(url, ydl_opts, clients):
        # The best client (tv_embedded) returns the full ladder; others 360p.
        if clients == ["tv_embedded"]:
            return full
        return limited

    with patch(
        "idm_cli.extractors.ytdlp._extract_with_clients", side_effect=fake_extract
    ):
        info = ytdlp_fetch_all_info("https://youtu.be/x")

    assert len(get_video_resolutions(info)) == 6


def test_fetch_all_info_raises_bot_error_when_all_clients_fail():
    """If every client fails with a bot error, a clear RuntimeError is raised."""
    with patch(
        "idm_cli.extractors.ytdlp._extract_with_clients",
        side_effect=RuntimeError("Sign in to confirm you're not a bot"),
    ), pytest.raises(RuntimeError, match="bot protection"):
        ytdlp_fetch_all_info("https://youtu.be/x")


# ── yt-dlp extractor fixes ────────────────────────────────────────────────────


def test_ytdlp_video_only_format_is_not_pre_muxed():
    """A video-only format (acodec None) must have pre_muxed == False."""
    info = {
        "formats": [
            {
                "format_id": "v720",
                "vcodec": "avc1.64001f",
                "acodec": None,
                "protocol": "https",
                "height": 720,
                "url": "https://example.com/v720.mp4",
            }
        ]
    }
    resolutions = get_video_resolutions(info)
    assert len(resolutions) == 1
    assert resolutions[0]["format_id"] == "v720"
    assert resolutions[0]["pre_muxed"] is False


def test_ytdlp_audio_only_format_excluded_from_resolutions():
    """An audio-only format (vcodec None) must be excluded from resolutions."""
    info = {
        "formats": [
            {
                "format_id": "a128",
                "vcodec": None,
                "acodec": "opus",
                "protocol": "https",
                "height": None,
                "url": "https://example.com/a128.opus",
            },
            {
                "format_id": "v720",
                "vcodec": "avc1.64001f",
                "acodec": "mp4a.40.2",
                "protocol": "https",
                "height": 720,
                "url": "https://example.com/v720.mp4",
            },
        ]
    }
    resolutions = get_video_resolutions(info)
    assert len(resolutions) == 1
    assert resolutions[0]["format_id"] == "v720"


def test_ytdlp_extract_urls_picks_audio_when_video_has_none():
    """When the chosen video has no audio, extract_urls picks the best audio format."""
    info = {
        "title": "Test Video",
        "http_headers": {"User-Agent": "test"},
        "formats": [
            {
                "format_id": "v720",
                "vcodec": "avc1.64001f",
                "acodec": None,
                "protocol": "https",
                "height": 720,
                "url": "https://example.com/v720.mp4",
            },
            {
                "format_id": "a128",
                "vcodec": "none",
                "acodec": "opus",
                "protocol": "https",
                "height": None,
                "url": "https://example.com/a128.opus",
            },
        ],
    }
    result = extract_urls(info, "v720")
    assert result["video_url"] == "https://example.com/v720.mp4"
    assert result["audio_url"] == "https://example.com/a128.opus"
    assert result["title"] == "Test Video"


# ── winget extractor fixes ────────────────────────────────────────────────────


def test_winget_install_command_yields_correct_title():
    """'winget install --id <pkg>' yields a title containing the package ID."""
    fake_result = MagicMock()
    fake_result.returncode = 0
    fake_result.stdout = "Installer Url: https://example.com/setup.exe\n"
    fake_result.stderr = ""

    with patch(
        "idm_cli.extractors.winget.platform.system", return_value="Windows"
    ), patch("idm_cli.extractors.winget.subprocess.run", return_value=fake_result):
        info = fetch_all_info("winget install --id Microsoft.PowerToys")

    assert "Microsoft.PowerToys" in info["title"]
    assert info["url"] == "https://example.com/setup.exe"


def test_winget_search_command_raises_error():
    """'winget search install' raises WingetError — not corrupted into 'winget search show'."""
    with contextlib.ExitStack() as stack:
        stack.enter_context(
            patch("idm_cli.extractors.winget.platform.system", return_value="Windows")
        )
        stack.enter_context(
            pytest.raises(
                WingetError, match="Only 'winget show' commands are supported"
            )
        )
        fetch_all_info("winget search install")


def test_winget_raises_on_non_windows():
    """fetch_all_info raises WingetError on non-Windows platforms."""
    with contextlib.ExitStack() as stack:
        stack.enter_context(
            patch("idm_cli.extractors.winget.platform.system", return_value="Linux")
        )
        stack.enter_context(
            pytest.raises(WingetError, match="only supported on Windows")
        )
        fetch_all_info("winget install --id Microsoft.PowerToys")


# ── UI fixes ──────────────────────────────────────────────────────────────────


def test_check_key_press_returns_none_for_non_tty():
    """check_key_press returns None when stdin is not a TTY (no crash)."""
    fake_stdin = MagicMock()
    fake_stdin.isatty.return_value = False
    fake_stdin.fileno.return_value = 0

    with patch("sys.stdin", fake_stdin):
        result = check_key_press()

    assert result is None
