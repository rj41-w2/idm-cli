from __future__ import annotations


def fetch_all_info(url: str) -> dict:
    """
    Extracts all info without downloading, without strict format filtering.
    """
    import yt_dlp

    ydl_opts = {
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "writesubtitles": False,
        "writeautomaticsub": False,
        "getcomments": False,
        "extractor_args": {"youtube": ["player_client=android,ios"]},
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception as e:
        error_msg = str(e).lower()
        if "bot" in error_msg or "cookie" in error_msg:
            # Bypass 1: Use alternative player clients (Android, iOS, TV)
            clients_to_try = ["android", "ios", "tv"]
            for client in clients_to_try:
                ydl_opts["extractor_args"] = {"youtube": [f"player_client={client}"]}
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        return ydl.extract_info(url, download=False)
                except Exception:  # noqa: BLE001,S112 - try the next extractor fallback
                    continue

            # Bypass 2: Local Browser Cookies
            ydl_opts.pop("extractor_args", None)

            for browser in ["chrome", "edge", "firefox", "brave", "opera"]:
                ydl_opts["cookiesfrombrowser"] = (browser,)
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        return ydl.extract_info(url, download=False)
                except Exception:  # noqa: BLE001,S112 - try the next browser fallback
                    continue

        raise RuntimeError(
            "YouTube bot protection blocked the request and bypass failed. Ensure your browser (Chrome/Edge) is FULLY CLOSED so cookies can be read, then try again."
        ) from e
        raise


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
        if fmt.get("vcodec") == "none":
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
                "pre_muxed": fmt.get("acodec") != "none",
            }
        else:
            # Prefer pre-muxed (video+audio in one stream) if found
            if fmt.get("acodec") != "none" and not resolutions[height]["pre_muxed"]:
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
                video_has_audio = fmt.get("acodec") != "none"
                break

    # Find best audio ONLY if the video doesn't already have audio
    if not video_has_audio:
        audio_formats = [
            f
            for f in formats
            if f.get("vcodec") == "none" and f.get("acodec") != "none"
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
