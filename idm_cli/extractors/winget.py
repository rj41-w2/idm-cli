import subprocess
import re
import platform

def fetch_all_info(url: str) -> dict:
    """Extracts download info from a winget command by running winget show."""
    if platform.system() != "Windows":
        raise Exception("Winget commands are only supported on Windows.")
        
    cmd = url.replace("install", "show").strip()
    
    try:
        # We add --accept-source-agreements in case it's a first run
        if "--accept-source-agreements" not in cmd:
            cmd += " --accept-source-agreements"
            
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding='utf-8')
        if result.returncode != 0:
            raise Exception(f"winget command failed. Ensure winget is installed and the package ID is correct.\nOutput: {result.stderr}")
        
        # Regex to find Installer Url: https://...
        match = re.search(r"Installer Url:\s*(https?://[^\s]+)", result.stdout, re.IGNORECASE)
        if not match:
            raise Exception("Could not extract Installer Url from winget output. It might not be available.")
            
        download_url = match.group(1)
        
        # Extract title from --id or fallback
        id_match = re.search(r"--id\s+([^\s]+)", url, re.IGNORECASE)
        if id_match:
            title = id_match.group(1)
        else:
            # Try to grab the first word after 'winget install' if no --id is specified
            parts = url.split()
            if len(parts) > 2 and parts[1] == "install":
                title = parts[2].replace("--", "")
            else:
                title = "winget_download"
                
        # To avoid invalid filename characters
        safe_title = "".join([c for c in title if c.isalnum() or c in ' -_.'])
        
        # Determine the file extension from the download URL if possible
        ext = ""
        url_part = download_url.split('/')[-1].split('?')[0]
        if '.' in url_part:
            ext = "." + url_part.split('.')[-1]
            if not safe_title.endswith(ext):
                safe_title += ext
                
        return {"title": safe_title, "url": download_url}
        
    except Exception as e:
        raise Exception(f"Winget extractor error: {str(e)}")

def get_video_resolutions(info: dict) -> list[dict]:
    return [{"resolution": "Direct File", "format_id": "direct_file"}]

def extract_urls(info: dict, video_format_id: str) -> dict:
    return {
        "video_url": info.get("url"),
        "audio_url": None,
        "headers": {},
        "title": info.get("title", "download")
    }
