import pytest

from idm_cli.downloader.downloader import _download_chunk, download_file
from idm_cli.extractors.direct import extract_urls
from idm_cli.ui.utils import is_valid_url


class _Response:
    def __init__(self, status_code=206, headers=None):
        self.status_code = status_code
        self.headers = headers or {"Content-Range": "bytes 0-2/3"}

    def raise_for_status(self):
        return None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


class _Session:
    def __init__(self, response):
        self.response = response

    def stream(self, *args, **kwargs):
        return self.response


def test_download_rejects_invalid_chunk_count():
    with pytest.raises(ValueError, match="between 1 and 32"):
        import asyncio

        asyncio.run(download_file(None, "https://example.com/file", "file", {}, 0))


def test_parallel_chunk_rejects_server_that_ignores_range(tmp_path):
    import asyncio

    response = _Response(status_code=200, headers={"Content-Length": "3"})
    with pytest.raises(ValueError, match="ignored byte range"):
        asyncio.run(
            _download_chunk(
                _Session(response),
                "https://example.com/file",
                0,
                2,
                0,
                str(tmp_path / "file"),
                {},
                None,
                None,
            )
        )


def test_url_validation_rejects_missing_host_and_accepts_https():
    assert is_valid_url("https://example.com/file")
    assert not is_valid_url("https://")
    assert not is_valid_url("javascript:alert(1)")


def test_direct_extractor_does_not_turn_audio_only_into_audio():
    extracted = extract_urls(
        {"url": "https://example.com/file.zip", "title": "file.zip"},
        "audio_only",
    )
    assert extracted["audio_url"] is None
    assert extracted["video_url"] == "https://example.com/file.zip"
