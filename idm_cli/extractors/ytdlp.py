from __future__ import annotations

# Player clients ordered best-first. YouTube restricts which formats each client
# may see; the default android/ios pair often yields only 360p, while
# tv_embedded exposes the full ladder (1080p/720p/...). We try these in order and
# keep the result with the most usable video formats.
_PLAYER_CLIENTS = [
    ["tv_embedded"],
    ["android", "ios"],
    ["web_safari"],
    ["mweb"],
    ["tv"],
    ["web"],
]


def _extract_with_clients(url: str, ydl_opts: dict, clients: list[str]) -> dict:
    import yt_dlp

    opts = dict(ydl_opts)
    opts["extractor_args"] = {"youtube": {"player_client": list(clients)}}
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


def _video_format_count(info: dict) -> int:
    """Number of distinct usable video heights in the extracted info."""
    heights = {
        f.get("height")
        for f in info.get("formats", [])
        if f.get("height") and f.get("vcodec") not in (None, "none")
    }
    return len(heights)


def fetch_all_info(url: str) -> dict:
    """
    Extracts all info without downloading, without strict format filtering.

    Tries several YouTube player clients and returns the result that exposes the
    most video resolutions, so the user actually gets a quality choice instead of
    being silently limited to 360p.
    """
    ydl_opts = {
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "writesubtitles": False,
        "writeautomaticsub": False,
        "getcomments": False,
    }

    best_info = None
    best_count = -1
    last_error = None

    for clients in _PLAYER_CLIENTS:
        try:
            info = _extract_with_clients(url, ydl_opts, clients)
        except Exception as e:  # noqa: BLE001 - try the next client set
            last_error = e
            continue
        count = _video_format_count(info)
        if count > best_count:
            best_count = count
            best_info = info
        # A full ladder (many heights) is good enough — stop early.
        if best_count >= 3:
            break

    if best_info is not None:
        return best_info

    error_msg = str(last_error).lower() if last_error else ""
    if "bot" in error_msg or "cookie" in error_msg or "sign in" in error_msg:
        raise RuntimeError(
            "YouTube bot protection blocked the request. Configure authenticated "
            "yt-dlp access explicitly if the site requires login."
        ) from last_error
    if last_error is not None:
        raise last_error
    raise RuntimeError("Could not extract video information.")


def get_video_resolutions(info: dict) -> list[dict]:
    """
    Parse formats from info, filter out audio-only streams,
    group/deduplicate by resolution (e.g. '1080p', '720p'),
    and return list of dicts with 'resolution' and 'format_id', sorted highest to lowest.
    Only direct HTTP(S) formats are included — HLS/DASH manifests are skipped
    because we download raw bytes ourselves and cannot parse playlists.
    """
    # Protocols we can download directly with byte-range requests
    DIRECT_PROTOCOLS = {"https", "http"}

    formats = info.get("formats", [])
    resolutions = {}

    for fmt in formats:
        # skip audio-only
        if fmt.get("vcodec") in (None, "none"):
            continue

        height = fmt.get("height")
        if not height:
            continue

        # skip HLS/DASH manifests — we can't handle playlists
        proto = fmt.get("protocol", "")
        if proto not in DIRECT_PROTOCOLS:
            continue

        res_str = f"{height}p"
        fmt_id = fmt.get("format_id")

        filesize = fmt.get("filesize") or fmt.get("filesize_approx")
        if filesize:
            size_mb = filesize / 1024 / 1024
            display_label = f"{height}p ({size_mb:.1f} MB)"
        else:
            display_label = f"{height}p"

        if height not in resolutions:
            resolutions[height] = {
                "resolution": res_str,
                "display_label": display_label,
                "format_id": fmt_id,
                "pre_muxed": fmt.get("acodec") not in (None, "none"),
            }
        else:
            # Prefer pre-muxed (video+audio in one stream) if found
            if (
                fmt.get("acodec") not in (None, "none")
                and not resolutions[height]["pre_muxed"]
            ):
                resolutions[height] = {
                    "resolution": res_str,
                    "display_label": display_label,
                    "format_id": fmt_id,
                    "pre_muxed": True,
                }

    # Sort by height descending
    sorted_heights = sorted(resolutions.keys(), reverse=True)
    return [resolutions[h] for h in sorted_heights]


def extract_urls(info: dict, video_format_id: str) -> dict:
    """
    Find specific video format URL using video_format_id.
    Find best audio format URL (vcodec == 'none' and acodec != 'none').
    Extract http_headers and title.
    """
    title = info.get("title", "Unknown Title")
    headers = info.get("http_headers", {}).copy()

    formats = info.get("formats", [])
    video_url = None
    audio_url = None

    # Find video
    video_has_audio = False
    if video_format_id != "audio_only":
        for fmt in formats:
            if str(fmt.get("format_id")) == str(video_format_id):
                video_url = fmt.get("url")
                if fmt.get("http_headers"):
                    headers.update(fmt.get("http_headers"))
                video_has_audio = fmt.get("acodec") not in (None, "none")
                break

    # Find best audio ONLY if the video doesn't already have audio
    if not video_has_audio:
        audio_formats = [
            f
            for f in formats
            if f.get("vcodec") == "none"
            and f.get("acodec") not in (None, "none")
            and f.get("protocol") in {"http", "https"}
        ]
        if audio_formats:
            # Sort by audio bitrate if available
            audio_formats.sort(key=lambda x: x.get("abr", 0) or 0)
            best_audio = audio_formats[-1]
            audio_url = best_audio.get("url")
            if best_audio.get("http_headers"):
                headers.update(best_audio.get("http_headers"))

    return {
        "video_url": video_url,
        "audio_url": audio_url,
        "headers": headers,
        "title": title,
    }
