"""
ui/prompts.py
-------------
All user-facing prompts, messages and interactive choices that appear
during a download session:

  - show_initializing / show_resuming / show_queued / show_success / show_error
  - ask_quality         — questionary.select for video resolution
  - ask_ffmpeg_install  — questionary.select for FFmpeg install method
  - install_ffmpeg      — runs the chosen install method and prints status
  - setup_ctrl_c        — installs a double-Ctrl+C signal handler
  - show_download_start — "Using N chunks … Starting …" message

downloader/ modules must NOT import from here. core.py calls these helpers
and passes results back as plain Python values.
"""

from __future__ import annotations

import asyncio
import platform
import signal
import subprocess
import time

import questionary
import typer
from rich.markup import escape

from idm_cli.ui.utils import console, custom_style

__all__ = [
    "ask_ffmpeg_install",
    "ask_quality",
    "ask_resume_action",
    "install_ffmpeg",
    "setup_ctrl_c",
    "show_download_cancelled",
    "show_download_start",
    "show_error",
    "show_initializing",
    "show_queue_empty",
    "show_queue_item_start",
    "show_queued",
    "show_resuming",
    "show_success",
]


# ── status messages ────────────────────────────────────────────────────────────
#
# Only two colours are used across the whole UI: cyan (accent) and white (text).
# Meaning is carried by the leading glyph instead of by colour:
#   ✓  success        ✗  error/failure
#   •  neutral info   »  an action about to happen


def show_initializing(url: str) -> None:
    console.print(f"[bold cyan]»[/] Initializing download for: {escape(url)}\n")


def show_resuming() -> None:
    console.print("[bold cyan]»[/] Found in resume list! Auto-resuming...")


def show_queued(media_type: str = "") -> None:
    console.print("[bold cyan]✓[/] Added to queue!")


def show_download_start(chunks: int) -> None:
    console.print(f"[bold cyan]•[/] Using {chunks} chunks per file.")
    console.print(
        "[bold cyan]»[/] Starting parallel downloads..."
        " [dim](Press 'p' to pause, 'r' to resume)[/dim]\n"
    )


def show_download_cancelled() -> None:
    console.print(
        "\n[bold cyan]✗[/] Download cancelled by user. Progress saved to resume later."
    )


def show_success(media_type: str, final_dest: str) -> None:
    console.print("\n[bold cyan]✓[/] Downloads completed.")
    console.print(
        f"[bold cyan]✓[/] Success! {escape(media_type)} saved as: "
        f"[bold white]{escape(final_dest)}[/]"
    )


def show_error(msg: str, label: str = "Error") -> None:
    # Collapse to a single line and cap the length so a raw multi-line dump
    # (e.g. a stray ffmpeg traceback) can never flood the console.
    text = " ".join(str(msg).split())
    if len(text) > 300:
        text = text[:297] + "..."
    console.print(f"[bold cyan]✗[/] [bold cyan]{escape(label)}:[/] {escape(text)}")


# ── interactive prompts ────────────────────────────────────────────────────────


def ask_quality(
    resolutions: list[dict],
    loop_quality: str | None,
    format_id: str,
    default_quality: str = "",
) -> str | None:
    """
    Return the selected resolution string, or None if user cancelled.

    Prompts only when a real terminal is available and more than one
    resolution exists. When stdin is not a TTY (pipes, cron, CI) or only one
    resolution exists, auto-selects: loop_quality if given, else default_quality
    if it matches, else the first (highest) resolution.
    """
    import sys

    # Non-interactive (piped/cron/CI): never prompt — questionary would raise
    # EOFError on a non-tty stdin.
    if not sys.stdin.isatty() or loop_quality or len(resolutions) == 1:
        matched = next(
            (r for r in resolutions if r["resolution"] == loop_quality), None
        )
        if matched:
            return matched["resolution"]
        if default_quality:
            default_matched = next(
                (r for r in resolutions if r["resolution"] == default_quality), None
            )
            if default_matched:
                return default_matched["resolution"]
        return resolutions[0]["resolution"]

    # Interactive: put the configured default first and mark it.
    ordered = list(resolutions)
    if default_quality:
        ordered.sort(key=lambda r: r["resolution"] != default_quality)

    choices = []
    for r in ordered:
        label = r.get("display_label", r["resolution"])
        if default_quality and r["resolution"] == default_quality:
            label = f"{label}  (default)"
        choices.append(label)

    prompt_text = (
        "Choose download option:"
        if format_id == "direct_file"
        else "Choose video quality:"
    )
    selected_display = questionary.select(
        prompt_text, choices=choices, style=custom_style
    ).ask(kbi_msg="")

    if not selected_display:
        console.print("[bold cyan]✗[/] Cancelled by user")
        return None

    selected_display = selected_display.replace("  (default)", "")
    return next(
        r["resolution"]
        for r in ordered
        if r.get("display_label", r["resolution"]) == selected_display
        or r["resolution"] == selected_display
    )


def ask_ffmpeg_install(is_interactive: bool) -> str:
    """
    Return chosen install method: 'auto' | 'winget' | 'brew' | 'apt' | 'cancel'.
    Non-interactive mode always returns 'auto'.
    """
    if not is_interactive:
        return "auto"

    console.print(
        "[bold cyan]•[/] High quality video/audio processing requires FFmpeg."
    )

    _sys = platform.system()
    choices = [
        questionary.Choice("Download automatically (approx 168MB, High-Speed)", "auto"),
        questionary.Choice("Cancel download", "cancel"),
    ]
    if _sys == "Windows":
        choices.insert(
            1,
            questionary.Choice(
                "Install via winget (Windows Package Manager, approx 131MB download)",
                "winget",
            ),
        )
    elif _sys == "Darwin":
        choices.insert(
            1, questionary.Choice("Install via brew (Homebrew, macOS)", "brew")
        )
    else:
        choices.insert(
            1, questionary.Choice("Install via apt (Linux Package Manager)", "apt")
        )

    return questionary.select(
        "How do you want to install FFmpeg?", choices=choices
    ).ask()


def install_ffmpeg(method: str, is_interactive: bool) -> bool:
    """
    Run the chosen FFmpeg install method.
    Returns True on success, False on failure.
    Raises typer.Exit on success for winget/brew/apt (requires terminal restart).
    """
    from idm_cli.downloader.muxer import download_ffmpeg  # lazy — avoids circular

    if method == "auto":
        try:
            asyncio.run(download_ffmpeg())
            return True
        except Exception as e:  # noqa: BLE001 - downloader libraries use varied errors
            show_error(str(e), "Failed to download FFmpeg")
            return False

    if method == "winget":
        try:
            with console.status(
                "[bold cyan]Installing FFmpeg via winget...", spinner="dots"
            ):
                subprocess.run(
                    [
                        "winget",
                        "install",
                        "ffmpeg",
                        "--accept-package-agreements",
                        "--accept-source-agreements",
                    ],
                    check=True,
                    shell=False,
                    timeout=120,
                )
            console.print("[bold cyan]✓[/] FFmpeg installed successfully via winget!")
            console.print(
                "[bold cyan]•[/] Please restart your terminal/command prompt "
                "to apply the PATH changes and run your command again.[/]"
            )
            raise typer.Exit(code=0)
        except typer.Exit:
            raise
        except (OSError, subprocess.SubprocessError) as e:
            show_error(str(e), "Failed to install via winget")
            return False

    if method == "brew":
        try:
            with console.status(
                "[bold cyan]Installing FFmpeg via brew...", spinner="dots"
            ):
                subprocess.run(
                    ["brew", "install", "ffmpeg"],
                    check=True,
                    shell=False,
                    timeout=120,
                )
            console.print("[bold cyan]✓[/] FFmpeg installed successfully via brew!")
            raise typer.Exit(code=0)
        except typer.Exit:
            raise
        except (OSError, subprocess.SubprocessError) as e:
            show_error(str(e), "Failed to install via brew")
            return False

    if method == "apt":
        try:
            with console.status(
                "[bold cyan]Installing FFmpeg via apt...", spinner="dots"
            ):
                subprocess.run(
                    ["sudo", "apt", "install", "-y", "ffmpeg"],
                    check=True,
                    shell=False,
                    timeout=120,
                )
            console.print("[bold cyan]✓[/] FFmpeg installed successfully via apt!")
            raise typer.Exit(code=0)
        except typer.Exit:
            raise
        except (OSError, subprocess.SubprocessError) as e:
            show_error(str(e), "Failed to install via apt")
            return False

    # 'cancel'
    console.print(
        "[bold cyan]✗[/] Cannot continue without FFmpeg. "
        "Please select a lower quality (like 360p)[/]"
    )
    return False


def show_queue_empty() -> None:
    console.print("[bold cyan]•[/] No videos in queue!")


def show_queue_item_start(title: str) -> None:
    console.print(f"[bold cyan]»[/] Starting queued download: {escape(title)}\n")


def ask_resume_action(incomplete: dict) -> tuple[str, str] | None:
    """
    Show a questionary select with Resume/Delete choices for each incomplete download.
    Returns (action, task_id) where action is 'resume' or 'delete', or None if cancelled.
    """
    if not incomplete:
        console.print("[bold cyan]•[/] No incomplete downloads found!")
        return None

    choices = []
    for tid, data in incomplete.items():
        title = str(data.get("title", tid))
        choices.append(questionary.Choice(f"[Resume] {title}", value=("resume", tid)))
        choices.append(questionary.Choice(f"[Delete] {title}", value=("delete", tid)))
    choices.append(questionary.Choice("[Back to Main]", value=("back", None)))

    result = questionary.select(
        "Select an action:", choices=choices, style=custom_style
    ).ask(kbi_msg="")

    if not result:
        console.print("[bold cyan]✗[/] Cancelled by user")
        return None

    action, tid = result
    if action == "back":
        console.print("[bold cyan]»[/] Returning to main menu...")
        return None

    return action, tid


# ── Ctrl+C double-press handler ────────────────────────────────────────────────


def setup_ctrl_c(warning_state: dict):
    """
    Install a SIGINT handler that requires two Ctrl+C presses within 5 s to cancel.
    First press sets warning_state['show'] = True (displayed in progress UI).
    Returns a restore function — call it in a finally block.
    """
    last_press = [0.0]
    original = signal.getsignal(signal.SIGINT)

    def _handler(signum, frame):
        if time.time() - last_press[0] <= 5:
            signal.signal(signal.SIGINT, original)
            raise KeyboardInterrupt
        warning_state["show"] = True
        last_press[0] = time.time()

    signal.signal(signal.SIGINT, _handler)

    def restore():
        signal.signal(signal.SIGINT, original)

    return restore
