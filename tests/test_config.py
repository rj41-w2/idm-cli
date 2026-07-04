import os
import json
from idm_cli.config import load_config, save_config, DEFAULT_CONFIG

def test_load_default_config(tmp_path, monkeypatch):
    monkeypatch.setattr("idm_cli.config.CONFIG_FILE", str(tmp_path / "config.json"))
    config = load_config()
    assert config["default_chunks"] == DEFAULT_CONFIG["default_chunks"]

def test_save_and_load_config(tmp_path, monkeypatch):
    monkeypatch.setattr("idm_cli.config.CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr("idm_cli.config.CONFIG_FILE", str(tmp_path / "config.json"))
    
    custom_config = {"default_chunks": 4, "default_quality": "1080p"}
    save_config(custom_config)
    
    loaded = load_config()
    assert loaded["default_chunks"] == 4
    assert loaded["default_quality"] == "1080p"
