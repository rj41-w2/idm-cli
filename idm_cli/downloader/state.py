import json
import os
import tempfile
import threading

from idm_cli.config import CONFIG_DIR

__all__ = ["get_incomplete_downloads", "remove_download", "save_download"]

STATE_DIR = CONFIG_DIR
STATE_FILE = os.path.join(STATE_DIR, "state.json")
_STATE_LOCK = threading.RLock()


def _ensure_dir():
    if not os.path.exists(STATE_DIR):
        os.makedirs(STATE_DIR, exist_ok=True)


def get_incomplete_downloads() -> dict:
    """Returns the parsed JSON of incomplete downloads."""
    with _STATE_LOCK:
        if not os.path.exists(STATE_FILE):
            return {}
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
            return state if isinstance(state, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}


def _write_state(state: dict) -> None:
    """Writes the state to the JSON file atomically."""
    _ensure_dir()
    # Write atomically using a temporary file in the same directory
    fd, temp_path = tempfile.mkstemp(dir=STATE_DIR, prefix="state_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=4)

        # Atomically replace the target file
        os.replace(temp_path, STATE_FILE)
    except Exception:
        # Clean up temp file on error
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise


def save_download(
    task_id: str,
    url: str,
    format_id: str,
    title: str,
    video_dest: str,
    audio_dest: str,
    final_dest: str,
    status: str = "interrupted",
) -> None:
    """Adds or updates a download in the JSON."""
    with _STATE_LOCK:
        state = get_incomplete_downloads()
        state[task_id] = {
            "url": url,
            "format_id": format_id,
            "title": title,
            "video_dest": video_dest,
            "audio_dest": audio_dest,
            "final_dest": final_dest,
            "status": status,
        }
        _write_state(state)


def remove_download(task_id: str) -> None:
    """Removes the entry from JSON upon completion."""
    with _STATE_LOCK:
        state = get_incomplete_downloads()
        if task_id in state:
            del state[task_id]
            _write_state(state)
