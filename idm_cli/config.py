import os
import json
import platform
import shutil
import logging
from logging.handlers import RotatingFileHandler
from platformdirs import user_data_dir, user_downloads_dir

APP_NAME = "idm-cli"
APP_AUTHOR = "idm-cli"
CONFIG_DIR = user_data_dir(APP_NAME, APP_AUTHOR)
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
LOG_FILE = os.path.join(CONFIG_DIR, "idm.log")

def _migrate_old_config():
    old_dir = os.path.expanduser("~/.idm_cli")
    if old_dir == CONFIG_DIR:
        return
    if not os.path.isdir(old_dir):
        return
    os.makedirs(CONFIG_DIR, exist_ok=True)
    for item in os.listdir(old_dir):
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

def setup_logging():
    _migrate_old_config()
    os.makedirs(CONFIG_DIR, exist_ok=True)
    logger = logging.getLogger("idm_cli")
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        handler = RotatingFileHandler(LOG_FILE, maxBytes=5*1024*1024, backupCount=2)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger

logger = setup_logging()

DEFAULT_CONFIG = {
    "default_chunks": 8,
    "default_quality": "720p",
    "download_dir": _get_default_download_dir(),
    "last_version": "0.0.0"
}

def load_config():
    config = DEFAULT_CONFIG.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                user_config = json.load(f)
                config.update(user_config)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to load config: {e}")
    return config

def save_config(config_data):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config_data, f, indent=4)
    except OSError as e:
        logger.error(f"Failed to save config: {e}")
