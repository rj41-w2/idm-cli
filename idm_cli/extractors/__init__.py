import importlib
import types
import urllib.request

from idm_cli.config import logger


def get_extractor(url: str) -> types.ModuleType:
    if url.strip().startswith("winget "):
        return importlib.import_module("idm_cli.extractors.winget")

    try:
        req = urllib.request.Request(
            url, method="HEAD", headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=2) as response:
            content_type = response.headers.get("Content-Type", "")
            if content_type and "text/html" not in content_type:
                return importlib.import_module("idm_cli.extractors.direct")
    except Exception:  # noqa: BLE001 - probe failures fall back to yt-dlp
        logger.debug("Direct extractor probe failed", exc_info=True)

    return importlib.import_module("idm_cli.extractors.ytdlp")
