import json
import logging
import os
import shutil
from logging.handlers import RotatingFileHandler

from platformdirs import user_data_dir, user_downloads_dir

__all__ = [
    "CONFIG_DIR",
    "CONFIG_FILE",
    "load_config",
    "logger",
    "mute_console_logging",
    "save_config",
    "setup_logging",
    "unmute_console_logging",
]

APP_NAME = "idm-cli"
APP_AUTHOR = "idm-cli"
CONFIG_DIR = user_data_dir(APP_NAME, APP_AUTHOR)
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
LOG_FILE = os.path.join(CONFIG_DIR, "idm.log")


def _migrate_old_config() -> None:
    old_dir = os.path.expanduser("~/.idm_cli")
    if old_dir == CONFIG_DIR:
        return
    if not os.path.isdir(old_dir):
        return
    os.makedirs(CONFIG_DIR, exist_ok=True)
    for item in os.listdir(old_dir):
        if item == "__pycache__":
            continue
        src = os.path.join(old_dir, item)
        dst = os.path.join(CONFIG_DIR, item)
        if not os.path.exists(dst):
            try:
                if os.path.isdir(src):
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)
            except OSError:
                pass


def _get_default_download_dir() -> str:
    return user_downloads_dir()


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("idm_cli")
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

        try:
            _migrate_old_config()
            os.makedirs(CONFIG_DIR, exist_ok=True)
            file_handler = RotatingFileHandler(
                LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=2, encoding="utf-8"
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except OSError:
            # Logging must never prevent the CLI from starting (for example in a
            # read-only home directory or a restricted CI environment).
            pass

        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.INFO)
        stream_handler.setFormatter(formatter)
        try:
            stream_handler.stream.reconfigure(errors="backslashreplace")
        except AttributeError:
            pass
        logger.addHandler(stream_handler)
    return logger


logger = setup_logging()

DEFAULT_CONFIG = {
    "default_chunks": 8,
    "default_quality": "720p",
    "download_dir": _get_default_download_dir(),
    "last_version": "0.0.0",
}


def load_config() -> dict:
    config = DEFAULT_CONFIG.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                user_config = json.load(f)
                if isinstance(user_config, dict):
                    config.update(user_config)
                else:
                    raise TypeError("config root must be an object")
        except (OSError, TypeError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to load config: {e}")
    chunks = config.get("default_chunks")
    if not isinstance(chunks, int) or not 1 <= chunks <= 32:
        config["default_chunks"] = DEFAULT_CONFIG["default_chunks"]
    if not isinstance(config.get("default_quality"), str):
        config["default_quality"] = DEFAULT_CONFIG["default_quality"]
    if (
        not isinstance(config.get("download_dir"), str)
        or not config["download_dir"].strip()
    ):
        config["download_dir"] = DEFAULT_CONFIG["download_dir"]
    return config


def save_config(config_data: dict) -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config_data, f, indent=4)
    except OSError as e:
        logger.error(f"Failed to save config: {e}")


def mute_console_logging() -> None:
    """Remove the StreamHandler from the logger so logs go to file only (used during active downloads)."""
    _logger = logging.getLogger("idm_cli")
    for handler in list(_logger.handlers):
        if isinstance(handler, logging.StreamHandler) and not isinstance(
            handler, RotatingFileHandler
        ):
            _logger.removeHandler(handler)


def unmute_console_logging() -> None:
    """Re-attach a StreamHandler if it was removed."""
    _logger = logging.getLogger("idm_cli")
    has_stream = any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler)
        for h in _logger.handlers
    )
    if not has_stream:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        try:
            stream_handler.stream.reconfigure(errors="backslashreplace")
        except AttributeError:
            pass
        _logger.addHandler(stream_handler)
