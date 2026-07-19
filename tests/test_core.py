import pytest
import os
import json
import tempfile
from unittest.mock import patch, MagicMock

# Test state.py
from idm_cli.downloader.state import save_download, get_incomplete_downloads, remove_download

def test_save_and_get_download(tmp_path):
    with patch('idm_cli.downloader.state.STATE_DIR', str(tmp_path)), \
         patch('idm_cli.downloader.state.STATE_FILE', str(tmp_path / 'state.json')):
        save_download("task1", "http://example.com", "direct_file", "test.txt", "/tmp/v", "/tmp/a", "/tmp/final")
        state = get_incomplete_downloads()
        assert "task1" in state
        assert state["task1"]["url"] == "http://example.com"
        assert state["task1"]["status"] == "interrupted"

def test_remove_download(tmp_path):
    with patch('idm_cli.downloader.state.STATE_DIR', str(tmp_path)), \
         patch('idm_cli.downloader.state.STATE_FILE', str(tmp_path / 'state.json')):
        save_download("task1", "http://example.com", "direct_file", "test.txt", "/tmp/v", "/tmp/a", "/tmp/final")
        remove_download("task1")
        state = get_incomplete_downloads()
        assert "task1" not in state

def test_get_empty_state(tmp_path):
    with patch('idm_cli.downloader.state.STATE_DIR', str(tmp_path)), \
         patch('idm_cli.downloader.state.STATE_FILE', str(tmp_path / 'state.json')):
        state = get_incomplete_downloads()
        assert state == {}

# Test config.py
from idm_cli.config import load_config

def test_load_config_returns_defaults():
    with patch('idm_cli.config.CONFIG_FILE', '/nonexistent/path/config.json'):
        config = load_config()
        assert "default_chunks" in config
        assert config["default_chunks"] == 8
        assert "default_quality" in config

# Test extractors
from idm_cli.extractors.direct import fetch_all_info, get_video_resolutions, extract_urls

def test_direct_fetch_all_info():
    info = fetch_all_info("https://example.com/file.zip")
    assert info["title"] == "file.zip"
    assert info["url"] == "https://example.com/file.zip"

def test_direct_get_video_resolutions():
    res = get_video_resolutions({})
    assert len(res) == 1
    assert res[0]["format_id"] == "direct_file"

def test_direct_extract_urls():
    info = {"url": "https://example.com/file.zip", "title": "file.zip"}
    urls = extract_urls(info, "direct_file")
    assert urls["video_url"] == "https://example.com/file.zip"
    assert urls["audio_url"] is None

# Test ui/utils.py
from idm_cli.ui.utils import is_valid_url, sanitize_filename

def test_is_valid_url():
    assert is_valid_url("https://youtube.com/watch?v=123") == True
    assert is_valid_url("javascript:alert(1)") == False
    assert is_valid_url("file:///etc/passwd") == False
    assert is_valid_url("not a url") == False

def test_sanitize_filename():
    result = sanitize_filename('My Video: "Test" <2024>')
    assert '<' not in result
    assert '>' not in result
    assert ':' not in result
    assert '"' not in result
