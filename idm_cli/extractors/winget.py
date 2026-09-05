from __future__ import annotations

import platform
import re
import shlex
import subprocess


class WingetError(RuntimeError):
    """Raised when winget metadata cannot be extracted."""


def fetch_all_info(url: str) -> dict:
    """Extracts download info from a winget command by running winget show."""
    if platform.system() != "Windows":
        raise WingetError("Winget commands are only supported on Windows.")

    if not url.strip().lower().startswith("winget "):
        raise WingetError("Invalid winget command format.")

    parts = url.strip().split(None, 2)
    if len(parts) >= 3 and parts[1].lower() == "install":
        cmd = f"{parts[0]} show {parts[2]}"
    else:
        cmd = url.strip().replace("install", "show", 1)

    try:
        args = shlex.split(cmd, posix=False)
        if args[0].lower() != "winget":
            raise WingetError("Command must start with 'winget'")

        if "--accept-source-agreements" not in args:
            args.append("--accept-source-agreements")

        if args[1] != "show":
            raise WingetError("Only 'winget show' commands are supported.")

        result = subprocess.run(
            args,
            shell=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            raise WingetError(
                f"winget command failed. Ensure winget is installed and the package ID is correct.\nOutput: {result.stderr}"
            )

        match = re.search(
            r"Installer Url:\s*(https?://[^\s]+)", result.stdout, re.IGNORECASE
        )
        if not match:
            raise WingetError(
                "Could not extract Installer Url from winget output. It might not be available."
            )

        download_url = match.group(1)

        id_match = re.search(r"--id\s+([^\s]+)", url, re.IGNORECASE)
        if id_match:
            title = id_match.group(1)
        else:
            parts = url.split()
            if len(parts) > 2 and parts[1] == "install":
                title = parts[2].replace("--", "")
            else:
                title = "winget_download"

        safe_title = "".join([c for c in title if c.isalnum() or c in " -_."])

        ext = ""
        url_part = download_url.split("/")[-1].split("?")[0]
        if "." in url_part:
            ext = "." + url_part.split(".")[-1]
            if not safe_title.endswith(ext):
                safe_title += ext

        return {"title": safe_title, "url": download_url}

    except subprocess.TimeoutExpired:
        raise WingetError("winget command timed out after 30 seconds.") from None
    except WingetError:
        raise
    except (OSError, ValueError) as e:
        raise WingetError(f"Winget extractor error: {e!s}") from e


def get_video_resolutions(info: dict) -> list[dict]:
    return [
        {
            "resolution": "Direct File",
            "display_label": "Direct File",
            "format_id": "direct_file",
        }
    ]


def extract_urls(info: dict, video_format_id: str) -> dict:
    return {
        "video_url": info.get("url"),
        "audio_url": None,
        "headers": {},
        "title": info.get("title", "download"),
    }
