import json
import os
import re
import time
import urllib.error
import urllib.request

from rich.console import Console

from idm_cli.config import logger


def _parse_ver(v):
    """Parse a version string into a comparable tuple of ints."""
    parts = re.split(r"[^0-9]+", v)
    return tuple(int(p) for p in parts if p.isdigit()) or (0,)


def check_for_updates():
    from idm_cli.config import CONFIG_DIR

    config_dir = CONFIG_DIR
    last_check_file = os.path.join(config_dir, "last_check.json")

    # Check last_check.json
    try:
        if os.path.exists(last_check_file):
            with open(last_check_file, "r") as f:
                data = json.load(f)
                last_check_time = data.get("last_check_time", 0)
                if time.time() - last_check_time < 86400:
                    return
    except (OSError, json.JSONDecodeError) as e:
        logger.debug(f"Failed to read last_check.json: {e}")

    # Fetch latest version from PyPI
    try:
        req = urllib.request.Request("https://pypi.org/pypi/idm-cli/json")
        with urllib.request.urlopen(req, timeout=3) as response:
            data = json.loads(response.read().decode("utf-8"))
            latest_version = data.get("info", {}).get("version")
    except (urllib.error.URLError, json.JSONDecodeError) as e:
        logger.debug(f"Update check network failed: {e}")
        return

    if not latest_version:
        return

    # Import __version__
    try:
        from idm_cli import __version__
    except ImportError:
        __version__ = "0.0.0"

    # Compare versions safely
    try:
        from packaging.version import parse

        is_newer = parse(latest_version) > parse(__version__)
    except ImportError:
        try:
            is_newer = _parse_ver(latest_version) > _parse_ver(__version__)
        except (ValueError, TypeError) as e:
            logger.debug(f"Version comparison fallback: {e}")
            is_newer = latest_version > __version__

    if is_newer:
        console = Console()
        console.print(
            f"\n[bold cyan]•[/] A new version of IDM-CLI ({latest_version}) is available!"
        )

        console.print(
            "\n[bold cyan]•[/] Please close this app and run the following command in your terminal to update:"
        )
        console.print("  [bold cyan]pip install --upgrade idm-cli[/bold cyan]\n")

    # Finally, write the current time.time() to last_check.json
    try:
        os.makedirs(config_dir, exist_ok=True)
        with open(last_check_file, "w") as f:
            json.dump({"last_check_time": time.time()}, f)
    except OSError as e:
        logger.warning(f"Failed to write last_check.json: {e}")
