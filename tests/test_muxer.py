"""Offline tests for muxer.py fixes.

Covers:
  - the temp output file keeps the real extension (ffmpeg infers the container
    from the extension, so "<out>.mp4.part" used to fail with exit 234)
  - ffmpeg failures raise a SHORT, user-friendly RuntimeError (no raw stderr)
  - a failed mux leaves no temp file behind
"""

from __future__ import annotations

import os
import subprocess
from unittest.mock import patch

import pytest

from idm_cli.downloader import muxer


def _touch(path):
    with open(path, "wb") as f:
        f.write(b"x")
    return path


def test_mux_uses_extension_preserving_temp_file(tmp_path):
    """The ffmpeg output arg must end with the real extension (.mp4), not .part."""
    video = _touch(tmp_path / "v.mp4")
    audio = _touch(tmp_path / "a.m4a")
    out = tmp_path / "final.mp4"

    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        # Emulate ffmpeg writing the output file.
        with open(cmd[-1], "wb") as f:
            f.write(b"muxed")
        return subprocess.CompletedProcess(cmd, 0)

    with patch.object(muxer, "get_ffmpeg_path", return_value="/usr/bin/ffmpeg"), patch(
        "idm_cli.downloader.muxer.subprocess.run", side_effect=fake_run
    ):
        muxer.mux_audio_video(str(video), str(audio), str(out))

    out_arg = captured["cmd"][-1]
    assert out_arg.endswith(".mp4"), f"bad ffmpeg output arg: {out_arg}"
    assert out_arg != f"{out}.part"
    assert out.exists()


def test_mux_failure_raises_short_message(tmp_path):
    """A failed ffmpeg run must raise a concise message, not the raw stderr dump."""
    video = _touch(tmp_path / "v.mp4")
    audio = _touch(tmp_path / "a.m4a")
    out = tmp_path / "final.mp4"

    long_stderr = (
        b"ffmpeg version 8.0.1 Copyright (c) 2000-2025\n"
        + b"configuration: --prefix=/usr --extra-version=x\n" * 50
        + b"[AVFormatContext] Unable to choose an output format for 'x.mp4.part'\n"
        + b"Error opening output files: Invalid argument\n"
    )

    def fake_run(cmd, **kwargs):
        raise subprocess.CalledProcessError(234, cmd, output=b"", stderr=long_stderr)

    with patch.object(muxer, "get_ffmpeg_path", return_value="/usr/bin/ffmpeg"), patch(
        "idm_cli.downloader.muxer.subprocess.run", side_effect=fake_run
    ), pytest.raises(RuntimeError) as exc:
        muxer.mux_audio_video(str(video), str(audio), str(out))

    msg = str(exc.value)
    assert len(msg) < 200, f"error message too long: {msg}"
    assert "ffmpeg version" not in msg
    assert "configuration:" not in msg
    assert "Invalid argument" in msg or "Unable to" in msg


def test_mux_failure_leaves_no_temp_file(tmp_path):
    """On failure the extension-preserving temp file must be cleaned up."""
    video = _touch(tmp_path / "v.mp4")
    audio = _touch(tmp_path / "a.m4a")
    out = tmp_path / "final.mp4"

    def fake_run(cmd, **kwargs):
        # Simulate a partial output file being created before the failure.
        with open(cmd[-1], "wb") as f:
            f.write(b"partial")
        raise subprocess.CalledProcessError(234, cmd, output=b"", stderr=b"boom")

    with patch.object(muxer, "get_ffmpeg_path", return_value="/usr/bin/ffmpeg"), patch(
        "idm_cli.downloader.muxer.subprocess.run", side_effect=fake_run
    ), pytest.raises(RuntimeError):
        muxer.mux_audio_video(str(video), str(audio), str(out))

    leftovers = [f for f in os.listdir(tmp_path) if f.startswith("final.mp4.part")]
    assert leftovers == [], f"temp files left behind: {leftovers}"


def test_convert_to_mp3_uses_extension_preserving_temp_file(tmp_path):
    """convert_to_mp3 must also keep the .mp3 extension for ffmpeg."""
    audio = _touch(tmp_path / "a.m4a")
    out = tmp_path / "final.mp3"

    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        with open(cmd[-1], "wb") as f:
            f.write(b"mp3")
        return subprocess.CompletedProcess(cmd, 0)

    with patch.object(muxer, "get_ffmpeg_path", return_value="/usr/bin/ffmpeg"), patch(
        "idm_cli.downloader.muxer.subprocess.run", side_effect=fake_run
    ):
        muxer.convert_to_mp3(str(audio), str(out))

    assert captured["cmd"][-1].endswith(".mp3")
    assert out.exists()
