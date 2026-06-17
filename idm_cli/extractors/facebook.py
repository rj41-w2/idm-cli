import yt_dlp

def fetch_all_info(url: str) -> dict:
    """
    Fetches all video info from a Facebook URL using yt-dlp.
    """
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        
    desc = info.get("description")
    if desc and desc.strip():
        clean_desc = desc.strip().split('\n')[0]
        if clean_desc:
            info["title"] = clean_desc
            
    return info

def get_video_resolutions(info: dict) -> list[dict]:
    """
    Parses the formats from the info dict and returns a list of available resolutions.
    """
    resolutions_dict = {}
    formats = info.get('formats', [])
    
    for fmt in formats:
        if fmt.get('vcodec') == 'none':
            continue
            
        format_id = str(fmt.get('format_id', ''))
        height = fmt.get('height')
        
        if height:
            resolution = f"{height}p"
        else:
            resolution = format_id.upper() if format_id else 'UNKNOWN'
            
        if resolution not in resolutions_dict:
            resolutions_dict[resolution] = {
                'resolution': resolution,
                'format_id': format_id
            }
            
    def parse_res(r):
        res = r['resolution']
        if res.endswith('p') and res[:-1].isdigit():
            return int(res[:-1])
        if res == 'HD': return 720
        if res == 'SD': return 480
        return 0
        
    return sorted(list(resolutions_dict.values()), key=parse_res, reverse=True)

def extract_urls(info: dict, video_format_id: str) -> dict:
    """
    Given the info dict and a selected video format ID, returns the video URL,
    audio URL (if not pre-muxed), headers, and title.
    """
    formats = info.get('formats', [])
    
    video_url = None
    audio_url = None
    headers = {}
    
    if video_format_id != "audio_only":
        for fmt in formats:
            if str(fmt.get('format_id')) == str(video_format_id):
                video_url = fmt.get('url')
                headers = fmt.get('http_headers', {})
                
                is_premuxed = (fmt.get('acodec') != 'none')
                if is_premuxed:
                    audio_url = None
                else:
                    # Find the best audio-only stream
                    best_audio = None
                    for a_fmt in formats:
                        if a_fmt.get('vcodec') == 'none' and a_fmt.get('acodec') != 'none':
                            if not best_audio or (a_fmt.get('abr') or 0) > (best_audio.get('abr') or 0):
                                best_audio = a_fmt
                    if best_audio:
                        audio_url = best_audio.get('url')
                break

    if video_format_id == "audio_only":
        best_audio = None
        # First try to find pure audio stream
        for a_fmt in formats:
            if a_fmt.get('vcodec') == 'none' and a_fmt.get('acodec') != 'none':
                if not best_audio or (a_fmt.get('abr') or 0) > (best_audio.get('abr') or 0):
                    best_audio = a_fmt
                    
        # If no pure audio stream exists, grab the smallest pre-muxed video to extract audio from
        if not best_audio:
            premuxed = [f for f in formats if f.get('acodec') != 'none' and f.get('vcodec') != 'none']
            if premuxed:
                premuxed.sort(key=lambda x: (x.get('height') or 9999, x.get('tbr') or 9999))
                best_audio = premuxed[0]
                
        if best_audio:
            audio_url = best_audio.get('url')
            headers = best_audio.get('http_headers', {})

    return {
        'video_url': video_url,
        'audio_url': audio_url,
        'headers': headers,
        'title': info.get('title', 'Facebook Video')
    }
