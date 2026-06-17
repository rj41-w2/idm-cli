import yt_dlp

def fetch_all_info(url: str) -> dict:
    ydl_opts = {'quiet': True, 'no_warnings': True, 'extract_flat': False}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        
    desc = info.get("description")
    if desc and desc.strip():
        clean_desc = desc.strip().split('\n')[0]
        if clean_desc:
            info["title"] = clean_desc
            
    return info

def get_video_resolutions(info: dict) -> list[dict]:
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
        
    res_list = sorted(list(resolutions_dict.values()), key=parse_res, reverse=True)
    if not res_list:
        return [{"resolution": "Best Quality", "format_id": "best"}]
    return res_list

def extract_urls(info: dict, video_format_id: str) -> dict:
    formats = info.get('formats', [])
    
    video_url = info.get("url")
    audio_url = None
    headers = info.get("http_headers", {})
    
    if video_format_id == "best":
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
    elif video_format_id != "audio_only":
        for fmt in formats:
            if str(fmt.get('format_id')) == str(video_format_id):
                video_url = fmt.get('url')
                headers = fmt.get('http_headers', {})
                
                is_premuxed = (fmt.get('acodec') != 'none')
                if is_premuxed:
                    audio_url = None
                else:
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
        for a_fmt in formats:
            if a_fmt.get('vcodec') == 'none' and a_fmt.get('acodec') != 'none':
                if not best_audio or (a_fmt.get('abr') or 0) > (best_audio.get('abr') or 0):
                    best_audio = a_fmt
                    
        if not best_audio:
            premuxed = [f for f in formats if f.get('acodec') != 'none' and f.get('vcodec') != 'none']
            if premuxed:
                premuxed.sort(key=lambda x: (x.get('height') or 9999, x.get('tbr') or 9999))
                best_audio = premuxed[0]
                
        if best_audio:
            video_url = best_audio.get('url')
            audio_url = None
            headers = best_audio.get('http_headers', {})

    return {
        "video_url": video_url,
        "audio_url": audio_url,
        "headers": headers,
        "title": info.get('title', 'Instagram Video')
    }
