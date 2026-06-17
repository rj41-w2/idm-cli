import os
import json
import time
import urllib.request
import subprocess
import sys
import questionary
from rich.console import Console

def check_for_updates():
    config_dir = os.path.expanduser("~/.idm_cli")
    last_check_file = os.path.join(config_dir, "last_check.json")

    # Check last_check.json
    try:
        if os.path.exists(last_check_file):
            with open(last_check_file, "r") as f:
                data = json.load(f)
                last_check_time = data.get("last_check_time", 0)
                if time.time() - last_check_time < 86400:
                    return
    except Exception:
        pass

    # Fetch latest version from PyPI
    try:
        req = urllib.request.Request("https://pypi.org/pypi/idm-cli/json")
        with urllib.request.urlopen(req, timeout=3) as response:
            data = json.loads(response.read().decode("utf-8"))
            latest_version = data.get("info", {}).get("version")
    except Exception:
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
        # Fallback to tuple or string comparison
        try:
            is_newer = tuple(map(int, latest_version.split("."))) > tuple(map(int, __version__.split(".")))
        except Exception:
            is_newer = latest_version > __version__

    if is_newer:
        console = Console()
        console.print(f"\n[bold yellow]A new version of IDM-CLI ({latest_version}) is available![/bold yellow]")
        
        console.print("\n[bold cyan]Please close this app and run the following command in your terminal to update:[/bold cyan]")
        console.print("  [bold green]pip install --upgrade idm-cli[/bold green]\n")

    # Finally, write the current time.time() to last_check.json
    try:
        os.makedirs(config_dir, exist_ok=True)
        with open(last_check_file, "w") as f:
            json.dump({"last_check_time": time.time()}, f)
    except Exception:
        pass
