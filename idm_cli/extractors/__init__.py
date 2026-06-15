import importlib

def get_extractor(url: str):
    if "facebook.com" in url or "fb.watch" in url:
        return importlib.import_module("idm_cli.extractors.facebook")
    # Default to youtube (handles youtube, twitter, and generic sites mostly)
    return importlib.import_module("idm_cli.extractors.youtube")
