import time
import typer
import shlex
import argparse
import pyfiglet
import questionary
from typing import Optional

from idm_cli.update_checker import check_for_updates
from idm_cli import __version__
from idm_cli.utils import console, custom_style, IDMLexer, check_first_run
from idm_cli.extension import install_extension
from idm_cli.handlers import handle_queue, handle_resume
from idm_cli.core import process_download
from idm_cli.config import load_config

global_config = load_config()

app = typer.Typer(help="IDM-CLI: A lightning-fast YouTube downloader.")

@app.command()
def download(
    url: Optional[str] = typer.Argument(None, help="The Video URL to download."),
    chunks: int = typer.Option(global_config.get("default_chunks", 8), "--chunks", "-c", help="Number of concurrent chunks per file."),
    quality: Optional[str] = typer.Option(None, "--quality", "-q", help="Video quality (e.g., 720p, 1080p)."),
    audio_only: bool = typer.Option(False, "--audio-only", "-a", help="Download audio only."),
    video_only: bool = typer.Option(False, "--video", "-v", help="Download video + audio (bypasses prompt)."),
    queue: bool = typer.Option(False, "--queue", "-Q", help="Add to queue instead of downloading immediately."),
    filename_opt: Optional[str] = typer.Option(None, "--filename", "-f", help="Force output filename.")
):
    """
    Download a YouTube video at maximum speed using parallel chunks.
    """
    banner = pyfiglet.figlet_format("IDM  CLI")
    console.print(f"[bold green]{banner}[/bold green]")
    console.print(f"[bold cyan]--- The Ultimate High-Speed CLI Downloader --- [/bold cyan][dim cyan](v{__version__})[/dim cyan]")
    console.print("      Type 'help' for available commands\n", style="white")
    
    check_first_run()
    
    try:
        check_for_updates()
    except Exception:
        pass

    is_interactive = (url is None)
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
                current_url = questionary.text(prompt_str, style=custom_style, lexer=IDMLexer()).ask(kbi_msg="")
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

        if is_interactive and current_url and current_url.strip().lower() not in ["help", "exit", "start queue", "queue start", "resume", "install extension"] and not current_url.strip().lower().startswith("winget "):
            try:
                parts = shlex.split(current_url)
                parser = argparse.ArgumentParser(add_help=False)
                parser.add_argument('-q', '--quality')
                parser.add_argument('-a', '--audio-only', action='store_true')
                parser.add_argument('-v', '--video', action='store_true')
                parser.add_argument('-Q', '--queue', action='store_true')
                parser.add_argument('-c', '--chunks', type=int)
                parser.add_argument('-f', '--filename', type=str)
                
                parsed_args, unknown = parser.parse_known_args(parts)
                loop_quality = parsed_args.quality or loop_quality
                loop_audio_only = parsed_args.audio_only or loop_audio_only
                loop_video_only = parsed_args.video or loop_video_only
                loop_queue = parsed_args.queue or loop_queue
                loop_chunks = parsed_args.chunks or loop_chunks
                loop_filename = parsed_args.filename or loop_filename
                
                urls = [u for u in unknown if not u.startswith('-')]
                if urls:
                    current_url = urls[0]
            except Exception:
                pass

        fast_mode = not is_interactive or loop_quality or loop_audio_only or loop_video_only or loop_queue
        if fast_mode and not loop_quality and not loop_audio_only:
            loop_quality = global_config.get("default_quality", "720p")

        if current_url.strip().lower() == "help":
            console.print("\n[bold cyan] Available Commands:[/bold cyan]")
            console.print("  [bold green]<URL>[/bold green]         - Paste any Video/File URL to download")
            console.print("  [bold green]resume[/bold green]      - Resume or delete an incomplete download")
            console.print("  [bold green]start queue[/bold green] - Start downloading queued files")
            console.print("  [bold green]install extension[/bold green] - Guide to install Chrome/Edge extension")
            console.print("  [bold green]help[/bold green]        - Show this help menu")
            console.print("  [bold green]exit[/bold green]        - Exit the application")
            
            console.print("\n[bold magenta]Fast Mode Flags (Skip Prompts):[/bold magenta]")
            console.print("  [bold white]-q <res>[/bold white]    - Set quality (e.g., -q 1080p, -q 720p)")
            console.print("  [bold white]-a[/bold white]          - Audio Only (Convert to MP3)")
            console.print("  [bold white]-Q[/bold white]          - Add directly to Queue instead of downloading")
            console.print("  [bold white]-c <num>[/bold white]    - Set number of parallel chunks (default: 8)")
            console.print("\n  [dim italic]Example: https://youtube.com/... -q 1080p -Q[/dim italic]\n")
            if not is_interactive:
                raise typer.Exit()
            current_url = None
            continue
            
        if current_url.strip().lower() == "install extension":
            install_extension()
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
                current_url=found_task_data.get('url'),
                is_interactive=is_interactive,
                loop_quality=loop_quality,
                loop_audio_only=loop_audio_only,
                loop_queue=loop_queue,
                loop_chunks=loop_chunks,
                loop_filename=loop_filename,
                found_task_id=found_task_id,
                found_task_data=found_task_data
            )
            current_url = None
            continue
            
        process_download(
            current_url=current_url,
            is_interactive=is_interactive,
            loop_quality=loop_quality,
            loop_audio_only=loop_audio_only,
            loop_queue=loop_queue,
            loop_chunks=loop_chunks,
            loop_filename=loop_filename
        )
        current_url = None

if __name__ == "__main__":
    app()
