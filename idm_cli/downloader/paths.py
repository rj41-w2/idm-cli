"""Validate paths loaded from download state before filesystem access.

State files describe downloads; they do not grant access to arbitrary files.
The current application configuration supplies the trusted directory roots.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

from idm_cli import config


def _validate_file(path: str, root: Path) -> Path:
    if not isinstance(path, str) or not path or "\x00" in path:
        raise ValueError("Invalid saved download path.")
    candidate = Path(path)
    if not candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("Download paths must be absolute and cannot contain '..'.")
    # Only immediate children of the configured directory are accepted.
    if candidate.parent != root:
        raise ValueError("Download path is outside its configured directory.")
    if candidate.is_symlink():
        raise ValueError("Download paths cannot be symbolic links.")
    try:
        info = candidate.stat()
    except FileNotFoundError:
        return candidate
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError("Download paths must be regular files without hard links.")
    return candidate


def download_temp_directory() -> Path:
    """Return the app's temp directory, rejecting symlinks and NTFS junctions."""
    config_root = Path(os.path.abspath(config.CONFIG_DIR))
    temp_root = config_root / "tmp"
    if temp_root.resolve() != config_root.resolve() / "tmp":
        raise ValueError(
            "The download temporary directory cannot be a symbolic link or junction."
        )
    return temp_root


def validate_download_paths(video_dest: str, audio_dest: str, final_dest: str) -> None:
    """Reject unsafe media, progress and FFmpeg work paths as one operation.

    Validate the complete set before a caller deletes or writes any member.
    The configured download directory may itself be a user-selected symlink;
    individual files and the application's temporary directory may not be.
    """
    temp_root = download_temp_directory()
    output_root = Path(os.path.abspath(config.load_config()["download_dir"]))
    paths = []
    for path in (video_dest, audio_dest):
        if not isinstance(path, str) or "\x00" in path:
            raise ValueError("Invalid saved download path.")
        if path:
            paths.append(_validate_file(path, temp_root))
            paths.append(_validate_file(f"{path}.progress.json", temp_root))
    if not paths:
        raise ValueError("A download must have at least one temporary media path.")
    output = _validate_file(final_dest, output_root)
    paths.append(output)
    paths.append(
        _validate_file(
            f"{final_dest}.part{os.path.splitext(final_dest)[1]}", output_root
        )
    )
    if len(set(paths)) != len(paths):
        raise ValueError("Download input, output and progress paths must be distinct.")
