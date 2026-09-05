"""
ui/utils.py
-----------
Shared UI utilities:
  - console         Rich Console instance
  - custom_style    questionary style
  - IDMLexer        prompt_toolkit lexer for the interactive prompt
  - check_key_press non-blocking keyboard read (p/r for pause/resume)
  - check_first_run changelog display on version upgrade
  - is_valid_url    URL safety check
  - sanitize_filename safe filename from title
"""

import asyncio
import sys
from urllib.parse import urlsplit

import questionary
from prompt_toolkit.lexers import Lexer
from rich.console import Console
from rich.progress import Progress

from idm_cli import __version__

__all__ = [
    "IDMLexer",
    "check_first_run",
    "check_key_press",
    "console",
    "custom_style",
    "is_valid_url",
    "sanitize_filename",
]

ALLOWED_SCHEMES = ("http://", "https://", "www.")
BLOCKED_KEYWORDS = ("javascript:", "data:", "file://", "ftp://")


def is_valid_url(url: str) -> bool:
    lower = url.strip().lower()
    if not lower.startswith(ALLOWED_SCHEMES) or len(url) > 2048:
        return False
    for kw in BLOCKED_KEYWORDS:
        if lower.startswith(kw):
            return False
    candidate = url.strip()
    if lower.startswith("www."):
        candidate = f"https://{candidate}"
    try:
        parsed = urlsplit(candidate)
        return parsed.scheme in {"http", "https"} and bool(parsed.hostname)
    except ValueError:
        return False


def sanitize_filename(title: str) -> str:
    safe = "".join(c for c in title if c not in r'<>:"/\|?*')
    safe = safe.strip(". ")
    return (safe[:60] or "download").strip()


# ── non-blocking key press (used by progress_listener for p/r) ────────────────

try:
    import msvcrt
except ImportError:
    msvcrt = None

try:
    import select
    import termios
    import tty
except ImportError:
    pass


def check_key_press():
    if sys.platform == "win32":
        if msvcrt and msvcrt.kbhit():
            return msvcrt.getch().decode("utf-8", "ignore").lower()
    else:
        if (
            "select" in sys.modules
            and "termios" in sys.modules
            and "tty" in sys.modules
        ):
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setcbreak(sys.stdin.fileno())
                dr, _dw, _de = select.select([sys.stdin], [], [], 0)
                if dr:
                    return sys.stdin.read(1).lower()
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return None


# ── Rich console ───────────────────────────────────────────────────────────────

console = Console()

# ── changelog / first-run notice ──────────────────────────────────────────────

CHANGELOG = {
    "1.3.0": [
        "Critical security fix: patched command injection vulnerability in winget extractor.",
        "Added URL validation to block unsafe schemes (file://, javascript:, data://, ftp://).",
        "Fixed race condition in download queue lock mechanism.",
        "Added timeouts to all subprocess calls for better stability.",
        "Removed machine-specific config file from repository tracking.",
    ],
    "1.2.2": [
        "Fixed an issue where resuming a download could result in a corrupted video file.",
        "Switched FFmpeg automatic download to high-speed GitHub releases (BtbN builds) for maximum bandwidth.",
        "Added a new option to seamlessly install FFmpeg via winget for Windows users.",
        "Improved downloader stability by automatically recovering from YouTube network throttling or silent disconnects.",
    ],
}


def check_first_run() -> None:
    from idm_cli.config import load_config, save_config

    config = load_config()
    last_version = config.get("last_version", "0.0.0")

    if __version__ != last_version:
        if __version__ in CHANGELOG:
            console.print(
                f"\n[bold cyan]*** What's New in v{__version__} ***[/bold cyan]"
            )
            for change in CHANGELOG[__version__]:
                console.print(f"  [bold cyan]*[/bold cyan] {change}")
            console.print()

        config["last_version"] = __version__
        save_config(config)


# ── questionary style ──────────────────────────────────────────────────────────

custom_style = questionary.Style(
    [
        ("qmark", "fg:cyan bold"),
        ("question", "bold white"),
        ("answer", "fg:cyan bold"),
        ("pointer", "fg:cyan bold"),
        ("highlighted", "fg:cyan bold"),
        ("flags", "fg:darkgray"),
    ]
)


# ── prompt_toolkit lexer for the interactive prompt ───────────────────────────


class IDMLexer(Lexer):
    def lex_document(self, document):
        def get_line(lineno):
            line = document.lines[lineno]
            idx = line.find(" -")
            if idx != -1:
                return [("class:answer", line[:idx]), ("class:flags", line[idx:])]
            return [("class:answer", line)]

        return get_line


# ── progress_listener is in ui/progress.py ────────────────────────────────────
# Kept here as a re-export for backwards compatibility with any external callers.


async def progress_listener(
    queue: asyncio.Queue,
    progress: Progress,
    pause_event=None,
    warning_state=None,
) -> None:
    from idm_cli.ui.progress import progress_listener as _pl

    await _pl(queue, progress, pause_event, warning_state)
