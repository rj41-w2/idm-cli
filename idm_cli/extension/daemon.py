import os
import psutil
from idm_cli.config import CONFIG_DIR

LOCK_FILE = os.path.join(CONFIG_DIR, "queue.lock")

def is_daemon_running() -> bool:
    if not os.path.exists(LOCK_FILE):
        return False
    try:
        with open(LOCK_FILE, "r") as f:
            pid = int(f.read().strip())
        if pid == os.getpid():
            return False
        return psutil.pid_exists(pid)
    except (OSError, ValueError):
        return False

def acquire_lock() -> bool:
    os.makedirs(os.path.dirname(LOCK_FILE), exist_ok=True)
    if is_daemon_running():
        return False
    try:
        fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        try:
            os.write(fd, str(os.getpid()).encode())
        finally:
            os.close(fd)
        return True
    except FileExistsError:
        return False
    except OSError:
        return False

def release_lock():
    if not os.path.exists(LOCK_FILE):
        return
    try:
        with open(LOCK_FILE, "r") as f:
            pid = int(f.read().strip())
        if pid == os.getpid():
            os.remove(LOCK_FILE)
    except (OSError, ValueError):
        pass
