import os
import json
import logging
from logging.handlers import RotatingFileHandler

CONFIG_DIR = os.path.expanduser("~/.idm_cli")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
LOG_FILE = os.path.join(CONFIG_DIR, "idm.log")

def setup_logging():
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
    "download_dir": os.path.join(os.path.expanduser("~"), "Downloads"),
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
