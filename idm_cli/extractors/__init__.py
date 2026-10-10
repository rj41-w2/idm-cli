import importlib
import types
import urllib.request

from idm_cli.config import logger

_PROBE_TIMEOUT = 5
_PROBE_HEADERS = {"User-Agent": "Mozilla/5.0"}


def _probe_is_direct(url: str) -> bool:
    """Return True if *url* looks like a direct (non-HTML) file.

    Tries a HEAD probe first, then falls back to a ranged GET. Both attempts
    use a short timeout; any failure is treated as "not direct" so the caller
    falls back to yt-dlp. The probe is inherently flaky over real networks, so
    callers must NOT depend on it being stable across calls (see core.py).
    """
    for method in ("HEAD", "GET"):
        try:
            headers = dict(_PROBE_HEADERS)
            if method == "GET":
                # Ask for a single byte so we do not download the whole file.
                headers["Range"] = "bytes=0-0"
            req = urllib.request.Request(url, method=method, headers=headers)
            with urllib.request.urlopen(req, timeout=_PROBE_TIMEOUT) as response:
                content_type = response.headers.get("Content-Type", "")
                if content_type and "text/html" not in content_type:
                    return True
        except Exception:  # noqa: BLE001 - probe failures fall back to yt-dlp
            logger.debug("Direct extractor probe (%s) failed", method, exc_info=True)
    return False


def get_extractor(url: str) -> types.ModuleType:
    if url.strip().startswith("winget "):
        return importlib.import_module("idm_cli.extractors.winget")

    if _probe_is_direct(url):
        return importlib.import_module("idm_cli.extractors.direct")

    return importlib.import_module("idm_cli.extractors.ytdlp")
