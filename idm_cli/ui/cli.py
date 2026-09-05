from __future__ import annotations

import argparse
import shlex
import time

import pyfiglet
import questionary
import typer
from rich.table import Table

from idm_cli import __version__
from idm_cli.config import load_config, logger
from idm_cli.downloader.core import process_download
from idm_cli.downloader.handlers import handle_queue, handle_resume
from idm_cli.ui.utils import (
    IDMLexer,
    check_first_run,
    console,
    custom_style,
    is_valid_url,
)
from idm_cli.update_checker import check_for_updates

global_config = load_config()

app = typer.Typer(help="IDM-CLI: A lightning-fast YouTube downloader.")


@app.command()
def download(
    url: str | None = typer.Argument(None, help="The Video URL to download."),
    chunks: int = typer.Option(
        global_config.get("default_chunks", 8),
        "--chunks",
        "-c",
        help="Number of concurrent chunks per file.",
    ),
    quality: str | None = typer.Option(
        None, "--quality", "-q", help="Video quality (e.g., 720p, 1080p)."
    ),
    audio_only: bool = typer.Option(
        False, "--audio-only", "-a", help="Download audio only."
    ),
    video_only: bool = typer.Option(
        False, "--video", "-v", help="Download video + audio (bypasses prompt)."
    ),
    queue: bool = typer.Option(
        False, "--queue", "-Q", help="Add to queue instead of downloading immediately."
    ),
    filename_opt: str | None = typer.Option(
        None, "--filename", "-f", help="Force output filename."
    ),
):
    """
    Download a YouTube video at maximum speed using parallel chunks.
    """
    banner_text = pyfiglet.figlet_format("IDM  CLI", font="standard")
    console.print(f"[bold cyan]{banner_text}[/bold cyan]")
    console.print(
        f"  [bold white]--- The Ultimate High-Speed CLI Downloader ---[/bold white] [dim white](v{__version__})[/dim white]"
    )
    console.print("  [dim white]      Type 'help' for available commands[/dim white]\n")

    check_first_run()

    try:
        check_for_updates()
    except Exception:  # noqa: BLE001 - update checks must never block downloads
        logger.debug("Update check failed", exc_info=True)

    if url and not url.strip().lower().startswith("winget ") and not is_valid_url(url):
        console.print(f"[bold red]Invalid or unsafe URL:[/] {url.strip()}")
        console.print("[dim white]Only HTTP/HTTPS URLs are allowed.[/dim white]")
        raise typer.Exit(code=1)

    is_interactive = url is None
    last_ctrl_c_time = 0
    show_warning = False

    while True:
        found_task_id = None
        loop_quality = quality
        loop_audio_only = audio_only
        loop_video_only = video_only
        loop_queue = queue
        loop_chunks = chunks
        loop_filename = filename_opt

        current_url = url
        if not current_url:
            prompt_str = "idm (Press again ctrl+c to exit) " if show_warning else "idm "
            try:
                current_url = questionary.text(
                    prompt_str, style=custom_style, lexer=IDMLexer()
                ).ask(kbi_msg="")
            except KeyboardInterrupt:
                current_url = None

            if current_url is None:
                if time.time() - last_ctrl_c_time <= 5:
                    console.print("[bold red]Cancelled by user[/bold red]")
                    raise typer.Exit()
                last_ctrl_c_time = time.time()
                show_warning = True
                continue
            else:
                show_warning = False

            current_url = current_url.strip()
            if not current_url:
                continue

        found_task_id = None

        if (
            is_interactive
            and current_url
            and current_url.strip().lower()
            not in ["help", "exit", "start queue", "queue start", "resume"]
            and not current_url.strip().lower().startswith("winget ")
        ):
            try:
                import platform as _platform

                parts = shlex.split(
                    current_url, posix=(_platform.system() != "Windows")
                )
                parser = argparse.ArgumentParser(add_help=False)
                parser.add_argument("-q", "--quality")
                parser.add_argument("-a", "--audio-only", action="store_true")
                parser.add_argument("-v", "--video", action="store_true")
                parser.add_argument("-Q", "--queue", action="store_true")
                parser.add_argument("-c", "--chunks", type=int)
                parser.add_argument("-f", "--filename", type=str)

                parsed_args, unknown = parser.parse_known_args(parts)
                loop_quality = parsed_args.quality or loop_quality
                loop_audio_only = parsed_args.audio_only or loop_audio_only
                loop_video_only = parsed_args.video or loop_video_only
                loop_queue = parsed_args.queue or loop_queue
                loop_chunks = parsed_args.chunks or loop_chunks
                loop_filename = parsed_args.filename or loop_filename

                urls = [u for u in unknown if not u.startswith("-")]
                if urls:
                    current_url = urls[0]
            except Exception:  # noqa: BLE001 - malformed interactive flags are ignored
                logger.debug("Could not parse interactive flags", exc_info=True)

        if is_interactive and current_url:
            lower = current_url.strip().lower()
            is_url = lower.startswith(("http://", "https://", "www."))
            is_known_cmd = lower in [
                "help",
                "exit",
                "start queue",
                "queue start",
                "resume",
            ]
            is_winget = lower.startswith("winget ")
            is_flag_only = lower.startswith("-")
            if not is_url and not is_known_cmd and not is_winget and not is_flag_only:
                console.print(f"[bold red]Unknown command:[/] {current_url.strip()}")
                console.print(
                    "[dim white]Type 'help' to see available commands.[/dim white]\n"
                )
                current_url = None
                continue

        fast_mode = (
            not is_interactive
            or loop_quality
            or loop_audio_only
            or loop_video_only
            or loop_queue
        )
        if fast_mode and not loop_quality and not loop_audio_only:
            loop_quality = global_config.get("default_quality", "720p")

        if current_url.strip().lower() == "help":
            table_cmds = Table(
                title="Available Commands",
                title_style="bold cyan",
                border_style="cyan",
                show_header=False,
                padding=(0, 2),
            )
            table_cmds.add_column("Command", style="cyan")
            table_cmds.add_column("Description", style="white")
            table_cmds.add_row("<URL>", "Paste any Video/File URL to download")
            table_cmds.add_row("resume", "Resume or delete an incomplete download")
            table_cmds.add_row("start queue", "Start downloading queued files")
            table_cmds.add_row("help", "Show this help menu")
            table_cmds.add_row("exit", "Exit the application")

            table_flags = Table(
                title="Fast Mode Flags (Skip Prompts)",
                title_style="bold cyan",
                border_style="cyan",
                show_header=False,
                padding=(0, 2),
            )
            table_flags.add_column("Flag", style="cyan")
            table_flags.add_column("Description", style="white")
            table_flags.add_row("-q <res>", "Set quality (e.g., -q 1080p, -q 720p)")
            table_flags.add_row("-a", "Audio Only (Convert to MP3)")
            table_flags.add_row("-Q", "Add directly to Queue instead of downloading")
            table_flags.add_row(
                "-c <num>", "Set number of parallel chunks (default: 8)"
            )

            console.print("\n")
            console.print(table_cmds)
            console.print()
            console.print(table_flags)
            console.print(
                "\n  [dim white]Example: https://youtube.com/... -q 1080p -Q[/dim white]\n"
            )
            if not is_interactive:
                raise typer.Exit()
            current_url = None
            continue

        if current_url.strip().lower() == "exit":
            console.print("[bold green]Goodbye![/bold green]")
            raise typer.Exit()

        if current_url.strip().lower() in ["start queue", "queue start"]:
            handle_queue(is_interactive, loop_chunks)
            current_url = None
            continue

        if current_url.strip().lower() == "resume":
            resume_result = handle_resume(is_interactive)
            if resume_result is None:
                continue

            found_task_id, found_task_data = resume_result
            process_download(
                current_url=found_task_data.get("url"),
                is_interactive=is_interactive,
                loop_quality=loop_quality,
                loop_audio_only=loop_audio_only,
                loop_queue=loop_queue,
                loop_chunks=loop_chunks,
                loop_filename=loop_filename,
                found_task_id=found_task_id,
                found_task_data=found_task_data,
            )
            current_url = None
            continue

        if (
            current_url
            and not current_url.strip().lower().startswith("winget ")
            and not is_valid_url(current_url)
        ):
            console.print(f"[bold red]Invalid or unsafe URL:[/] {current_url.strip()}")
            console.print("[dim white]Only HTTP/HTTPS URLs are allowed.[/dim white]\n")
            current_url = None
            continue

        process_download(
            current_url=current_url,
            is_interactive=is_interactive,
            loop_quality=loop_quality,
            loop_audio_only=loop_audio_only,
            loop_queue=loop_queue,
            loop_chunks=loop_chunks,
            loop_filename=loop_filename,
        )
        current_url = None


if __name__ == "__main__":
    app()
