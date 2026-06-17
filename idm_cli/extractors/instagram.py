import yt_dlp

def fetch_all_info(url: str) -> dict:
    ydl_opts = {'quiet': True, 'no_warnings': True, 'extract_flat': False}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)

def get_video_resolutions(info: dict) -> list[dict]:
    return [{"resolution": "Best Quality", "format_id": "best"}]

def extract_urls(info: dict, video_format_id: str) -> dict:
    video_url = info.get("url")
    audio_url = None
    formats = info.get("formats", [])

    if video_format_id == "audio_only":
        audio_only_url = None
        for f in formats:
            if f.get("acodec") != "none" and f.get("vcodec") == "none":
                audio_only_url = f.get("url")
                break
        
        if audio_only_url:
            video_url = audio_only_url
        elif not video_url and formats:
            # Fallback to the best available format to extract audio from
            video_url = formats[-1].get("url")
    else:
        requested_formats = info.get("requested_formats", [])
        if requested_formats and len(requested_formats) >= 2:
            video_url = requested_formats[0].get("url")
            audio_url = requested_formats[1].get("url")
        else:
            if not video_url and formats:
                video_formats = [f for f in formats if f.get('vcodec') != 'none']
                if video_formats:
                    best_video = video_formats[-1]
                    video_url = best_video.get("url")
                    if best_video.get("acodec") == "none":
                        audio_formats = [f for f in formats if f.get('vcodec') == 'none' and f.get('acodec') != 'none']
                        if audio_formats:
                            audio_formats.sort(key=lambda x: x.get('abr', 0) or 0)
                            audio_url = audio_formats[-1].get('url')

    return {
        "video_url": video_url,
        "audio_url": audio_url,
        "headers": info.get("http_headers", {})
    }
