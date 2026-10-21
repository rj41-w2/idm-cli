"""Regression tests for paths loaded from untrusted download state."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from idm_cli import config
from idm_cli.downloader import core, handlers, state
from idm_cli.downloader.paths import validate_download_paths


@pytest.fixture
def download_paths(tmp_path, monkeypatch):
    app = tmp_path / "app"
    temp = app / "tmp"
    output = tmp_path / "downloads"
    temp.mkdir(parents=True)
    output.mkdir()
    monkeypatch.setattr(config, "CONFIG_DIR", str(app))
    monkeypatch.setattr(config, "load_config", lambda: {"download_dir": str(output)})
    monkeypatch.setattr(state, "STATE_DIR", str(app))
    monkeypatch.setattr(state, "STATE_FILE", str(app / "state.json"))
    return str(temp / "video"), str(temp / "audio"), str(output / "final.bin")


def task(paths):
    return {
        "url": "https://example.com/file",
        "format_id": "direct_file",
        "title": "file",
        "video_dest": paths[0],
        "audio_dest": paths[1],
        "final_dest": paths[2],
        "status": "interrupted",
    }


def test_valid_saved_download_round_trip(download_paths):
    data = task(download_paths)
    state.save_download("task", **data)
    assert state.get_incomplete_downloads() == {"task": data}


@pytest.mark.parametrize("field", ["video_dest", "audio_dest", "final_dest"])
def test_state_rejects_paths_outside_roots(download_paths, tmp_path, field):
    victim = tmp_path / "unrelated.txt"
    victim.write_text("keep me")
    bad = task(download_paths)
    bad[field] = str(victim)
    good = task(download_paths)
    with open(state.STATE_FILE, "w") as f:
        json.dump({"bad": bad, "good": good}, f)
    assert state.get_incomplete_downloads() == {"good": good}
    assert victim.read_text() == "keep me"


@pytest.mark.parametrize("kind", ["relative", "traversal", "directory", "nul"])
def test_invalid_temp_paths_rejected(download_paths, kind):
    video, audio, final = download_paths
    invalid = {
        "relative": "video",
        "traversal": str(Path(video).parent / ".." / "video"),
        "directory": str(Path(video).parent),
        "nul": video + "\x00",
    }[kind]
    with pytest.raises(ValueError):
        validate_download_paths(invalid, audio, final)


@pytest.mark.parametrize("target", ["video", "progress", "output", "work", "tempdir"])
def test_symlinks_rejected(download_paths, tmp_path, target):
    video, audio, final = download_paths
    victim = tmp_path / "victim"
    victim.write_text("keep me")
    link = {
        "video": Path(video),
        "progress": Path(video + ".progress.json"),
        "output": Path(final),
        "work": Path(final + ".part.bin"),
        "tempdir": Path(video).parent,
    }[target]
    if target == "tempdir":
        link.rmdir()
    try:
        link.symlink_to(
            victim.parent if target == "tempdir" else victim,
            target_is_directory=target == "tempdir",
        )
    except OSError:
        pytest.skip("Creating symlinks requires OS privileges on this platform")
    with pytest.raises(ValueError, match="symbolic"):
        validate_download_paths(video, audio, final)
    assert victim.read_text() == "keep me"


def test_hard_link_rejected(download_paths, tmp_path):
    import os

    video, audio, final = download_paths
    victim = tmp_path / "victim"
    victim.write_text("keep me")
    os.link(victim, video)
    with pytest.raises(ValueError, match="hard links"):
        validate_download_paths(video, audio, final)
    assert victim.read_text() == "keep me"


def test_delete_validates_all_paths_before_removing_any(download_paths, tmp_path):
    video, _audio, final = download_paths
    Path(video).write_text("partial")
    victim = tmp_path / "victim"
    victim.write_text("keep me")
    data = task((video, str(victim), final))
    with patch.object(
        handlers, "get_incomplete_downloads", return_value={"task": data}
    ), patch.object(
        handlers, "ask_resume_action", return_value=("delete", "task")
    ), patch.object(handlers, "remove_download") as remove:
        assert handlers.handle_resume(True) is None
        remove.assert_not_called()
    assert Path(video).read_text() == "partial"
    assert victim.read_text() == "keep me"


def test_pipeline_rejects_unsafe_destination_before_download(download_paths, tmp_path):
    video, audio, _ = download_paths
    victim = tmp_path / "victim"
    victim.write_text("keep me")
    with patch("idm_cli.ui.progress.run_with_progress") as run, pytest.raises(
        ValueError
    ):
        core.run_download_and_mux(
            "https://example.com",
            None,
            {},
            1,
            video,
            audio,
            str(victim),
            "File",
            None,
            {},
        )
    run.assert_not_called()
    assert victim.read_text() == "keep me"


def test_explicit_resume_rejects_unsafe_state_before_extraction(
    download_paths, tmp_path
):
    data = task(download_paths)
    data["video_dest"] = str(tmp_path / "outside")
    with patch.object(core, "get_extractor") as extract:
        assert (
            core.process_download(
                data["url"], True, "", False, False, 1, "", "task", data
            )
            is False
        )
    extract.assert_not_called()


@pytest.mark.parametrize("mode", ["video", "audio", "mux"])
def test_pipeline_accepts_valid_paths_for_each_mode(download_paths, mode, caplog):
    video, audio, final = download_paths
    with patch(
        "idm_cli.ui.progress.run_with_progress", new_callable=AsyncMock
    ) as run, patch.object(core, "_finalize_single_video") as finalize, patch.object(
        core, "convert_to_mp3"
    ) as convert, patch.object(core, "mux_audio_video") as mux:
        assert core.run_download_and_mux(
            "http://example.com/video" if mode != "audio" else None,
            "https://example.com/audio" if mode != "video" else None,
            {},
            1,
            video if mode != "audio" else "",
            audio if mode != "video" else "",
            final,
            "File",
            None,
            {},
        )
    run.assert_awaited_once()
    assert finalize.call_count == (mode == "video")
    assert convert.call_count == (mode == "audio")
    assert mux.call_count == (mode == "mux")
    assert ("unencrypted HTTP" in caplog.text) == (mode != "audio")
