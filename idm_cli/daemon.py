import os
import psutil

LOCK_FILE = os.path.expanduser("~/.idm_cli/queue.lock")

def is_daemon_running() -> bool:
    if not os.path.exists(LOCK_FILE):
        return False
    try:
        with open(LOCK_FILE, "r") as f:
            pid = int(f.read().strip())
        return psutil.pid_exists(pid)
    except Exception:
        return False

def acquire_lock() -> bool:
    os.makedirs(os.path.dirname(LOCK_FILE), exist_ok=True)
    if is_daemon_running():
        return False
    try:
        with open(LOCK_FILE, "w") as f:
            f.write(str(os.getpid()))
        return True
    except Exception:
        return False

def release_lock():
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, "r") as f:
                pid = int(f.read().strip())
            if pid == os.getpid():
                os.remove(LOCK_FILE)
        except Exception:
            pass
