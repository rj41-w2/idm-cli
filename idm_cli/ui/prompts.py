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


def show_initializing(url: str) -> None:
    console.print(f"[bold yellow]Initializing download for:[/] {escape(url)}\n")


def show_resuming() -> None:
    console.print("[bold yellow]Found in resume list! Auto-resuming...[/]")


def show_queued(media_type: str = "") -> None:
    console.print("[bold green]Added to queue![/]")


def show_download_start(chunks: int) -> None:
    console.print(f"[bold green]*[/] Using {chunks} chunks per file.")
    console.print(
        "[bold cyan]Starting parallel downloads...[/]"
        " [dim](Press 'p' to pause, 'r' to resume)[/dim]\n"
    )


def show_download_cancelled() -> None:
    console.print(
        "\n[bold red]Download cancelled by user. "
        "Progress saved to resume later.[/bold red]"
    )


def show_success(media_type: str, final_dest: str) -> None:
    console.print("\n[bold green]✓[/] Downloads completed.")
    console.print(
        f"\n[bold green] Success! {escape(media_type)} saved as:[/] [bold white]{escape(final_dest)}[/]"
    )


def show_error(msg: str, label: str = "Error") -> None:
    console.print(f"[bold red]{escape(label)}:[/] {escape(msg)}")


# ── interactive prompts ────────────────────────────────────────────────────────


def ask_quality(
    resolutions: list[dict], loop_quality: str, format_id: str
) -> str | None:
    """
    Return the selected resolution string, or None if user cancelled.
    If loop_quality is set or only one resolution exists, auto-selects.
    """
    if loop_quality or len(resolutions) == 1:
        matched = next(
            (r for r in resolutions if r["resolution"] == loop_quality), None
        )
        return matched["resolution"] if matched else resolutions[0]["resolution"]

    choices = [r.get("display_label", r["resolution"]) for r in resolutions]
    prompt_text = (
        "Choose download option:"
        if format_id == "direct_file"
        else "Choose video quality:"
    )
    selected_display = questionary.select(
        prompt_text, choices=choices, style=custom_style
    ).ask(kbi_msg="")

    if not selected_display:
        console.print("[bold red]Cancelled by user[/bold red]")
        return None

    return next(
        r["resolution"]
        for r in resolutions
        if r.get("display_label", r["resolution"]) == selected_display
    )


def ask_ffmpeg_install(is_interactive: bool) -> str:
    """
    Return chosen install method: 'auto' | 'winget' | 'brew' | 'apt' | 'cancel'.
    Non-interactive mode always returns 'auto'.
    """
    if not is_interactive:
        return "auto"

    console.print(
        "[bold yellow]High quality video/audio processing requires FFmpeg.[/]"
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
            console.print("[bold green]FFmpeg installed successfully via winget![/]")
            console.print(
                "[bold yellow]Please restart your terminal/command prompt "
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
            console.print("[bold green]FFmpeg installed successfully via brew![/]")
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
            console.print("[bold green]FFmpeg installed successfully via apt![/]")
            raise typer.Exit(code=0)
        except typer.Exit:
            raise
        except (OSError, subprocess.SubprocessError) as e:
            show_error(str(e), "Failed to install via apt")
            return False

    # 'cancel'
    console.print(
        "[bold red]Cannot continue without FFmpeg. "
        "Please select a lower quality (like 360p)[/]"
    )
    return False


def show_queue_empty() -> None:
    console.print("[bold green]No videos in queue![/]")


def show_queue_item_start(title: str) -> None:
    console.print(f"[bold yellow]Starting queued download:[/] {escape(title)}\n")


def ask_resume_action(incomplete: dict) -> tuple[str, str] | None:
    """
    Show a questionary select with Resume/Delete choices for each incomplete download.
    Returns (action, task_id) where action is 'resume' or 'delete', or None if cancelled.
    """
    if not incomplete:
        console.print("[bold green]No incomplete downloads found![/]")
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
        console.print("[bold red]Cancelled by user[/bold red]")
        return None

    action, tid = result
    if action == "back":
        console.print("[bold cyan]Returning to main menu...[/bold cyan]")
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
