import yt_dlp

def extract_info(url: str) -> dict:
    """
    Extracts the best video-only and audio-only URLs, along with required
    HTTP headers and title from a given YouTube URL using yt-dlp.
    """
    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'noplaylist': True,
        'quiet': True,
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        
    title = info.get('title', 'Unknown Title')
    
    video_url = None
    audio_url = None
    headers = info.get('http_headers', {}).copy()
    
    # yt-dlp usually populates 'requested_formats' when multiple formats
    # (like video and audio separately) are requested.
    if 'requested_formats' in info:
        for fmt in info['requested_formats']:
            fmt_headers = fmt.get('http_headers', {})
            
            if fmt.get('vcodec') != 'none':
                video_url = fmt.get('url')
                headers.update(fmt_headers)
                
            if fmt.get('acodec') != 'none' and fmt.get('vcodec') == 'none':
                audio_url = fmt.get('url')
                headers.update(fmt_headers)
    else:
        # Fallback: A single format containing both video and audio
        video_url = info.get('url')
        if info.get('http_headers'):
            headers.update(info.get('http_headers'))
            
    return {
        'video_url': video_url,
        'audio_url': audio_url,
        'headers': headers,
        'title': title
    }
