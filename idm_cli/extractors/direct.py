from __future__ import annotations


def fetch_all_info(url: str) -> dict:
    """Extracts a filename from the URL and returns info."""
    filename = url.split("/")[-1].split("?")[0]
    if not filename:
        filename = "file_download"
    return {"title": filename, "url": url}


def get_video_resolutions(info: dict) -> list[dict]:
    """Returns a dummy resolution for direct files."""
    return [
        {
            "resolution": "Direct File",
            "display_label": "Direct File",
            "format_id": "direct_file",
        }
    ]


def extract_urls(info: dict, video_format_id: str) -> dict:
    """Extracts download URLs."""
    return {
        "video_url": info.get("url"),
        "audio_url": None,
        "headers": {},
        "title": info.get("title", "download"),
    }
