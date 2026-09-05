import json
import os
import tempfile
import threading
from contextlib import contextmanager

from idm_cli.config import CONFIG_DIR

__all__ = ["get_incomplete_downloads", "remove_download", "save_download"]

STATE_DIR = CONFIG_DIR
STATE_FILE = os.path.join(STATE_DIR, "state.json")
_STATE_LOCK = threading.RLock()


def _ensure_dir():
    if not os.path.exists(STATE_DIR):
        os.makedirs(STATE_DIR, exist_ok=True)


@contextmanager
def _process_lock():
    """Serialize state read/modify/write cycles across CLI processes."""
    lock_path = f"{STATE_FILE}.lock"
    _ensure_dir()
    with open(lock_path, "a+b") as lock_file:
        if os.name == "nt":
            import msvcrt

            lock_file.seek(0)
            lock_file.write(b"0")
            lock_file.flush()
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                lock_file.seek(0)
                try:
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    # Closing the handle releases the Windows byte-range lock.
                    pass
        else:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _read_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
        return state if isinstance(state, dict) else {}
    except (json.JSONDecodeError, OSError) as e:
        # Keep the damaged file for diagnostics instead of silently destroying it.
        import logging

        logging.getLogger("idm_cli").warning("Could not read download state: %s", e)
        return {}


def get_incomplete_downloads() -> dict:
    """Returns the parsed JSON of incomplete downloads."""
    with _STATE_LOCK, _process_lock():
        return _read_state()


def _write_state(state: dict) -> None:
    """Writes the state to the JSON file atomically."""
    _ensure_dir()
    # Write atomically using a temporary file in the same directory
    fd, temp_path = tempfile.mkstemp(dir=STATE_DIR, prefix="state_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=4)
            f.flush()
            os.fsync(f.fileno())

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
    with _STATE_LOCK, _process_lock():
        state = _read_state()
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
    with _STATE_LOCK, _process_lock():
        state = _read_state()
        if task_id in state:
            del state[task_id]
            _write_state(state)
