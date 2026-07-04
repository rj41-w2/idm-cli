from idm_cli.utils import sanitize_filename

def test_sanitize_filename():
    assert sanitize_filename("test file.mp4") == "test file.mp4"
    assert sanitize_filename("invalid<>:\"/\\|?*name.mp4") == "invalidname.mp4"
