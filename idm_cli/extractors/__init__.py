import importlib
import urllib.request

def get_extractor(url: str):
    if "facebook.com" in url or "fb.watch" in url:
        return importlib.import_module("idm_cli.extractors.facebook")
    
    try:
        req = urllib.request.Request(url, method='HEAD', headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3) as response:
            content_type = response.headers.get('Content-Type', '')
            if content_type and 'text/html' not in content_type:
                return importlib.import_module("idm_cli.extractors.direct")
    except Exception:
        pass

    # Default to youtube (handles youtube, twitter, and generic sites mostly)
    return importlib.import_module("idm_cli.extractors.youtube")
