import asyncio
import os
import sys
import time
import uuid
import typer
import signal
import shlex
import argparse
from typing import Optional
from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    DownloadColumn,
    TransferSpeedColumn
)
import pyfiglet
import questionary
from prompt_toolkit.lexers import Lexer

try:
    import msvcrt
except ImportError:
    msvcrt = None

from idm_cli.extractors import get_extractor
from idm_cli.downloader import download_file
from idm_cli.muxer import mux_audio_video, convert_to_mp3
from idm_cli.state import save_download, remove_download, get_incomplete_downloads
from idm_cli.update_checker import check_for_updates
from idm_cli import __version__
import json
import aiohttp

CHANGELOG = {
    "1.1.6": [
        "Replaced autocomplete with text prompt for improved user input handling.",
        "Enhanced update prompt for better user experience.",
        "Enhanced download_media function to accept media_type parameter and improved console output.",
        "Enhanced video info extraction for Facebook and Instagram, and improved error handling for FFmpeg in muxer."
    ]
}

def check_first_run():
    config_dir = os.path.expanduser("~/.idm_cli")
    os.makedirs(config_dir, exist_ok=True)
    config_file = os.path.join(config_dir, "config.json")
    
    last_version = "0.0.0"
    if os.path.exists(config_file):
        try:
            with open(config_file, "r") as f:
                last_version = json.load(f).get("last_version", "0.0.0")
        except Exception:
            pass

    if __version__ != last_version:
        if __version__ in CHANGELOG:
            console.print(f"\n[bold magenta]*** What's New in v{__version__} ***[/bold magenta]")
            for change in CHANGELOG[__version__]:
                console.print(f"  [cyan]*[/cyan] {change}")
            console.print()
        
        try:
            with open(config_file, "w") as f:
                json.dump({"last_version": __version__}, f)
        except Exception:
            pass


custom_style = questionary.Style([
    ('qmark', 'fg:cyan bold'),       
    ('question', 'bold'),               
    ('answer', 'fg:cyan bold'),      
    ('pointer', 'fg:cyan bold'),     
    ('highlighted', 'fg:cyan bold'), 
    ('flags', 'fg:white'),
])

class IDMLexer(Lexer):
    def lex_document(self, document):
        def get_line(lineno):
            line = document.lines[lineno]
            idx = line.find(" -")
            if idx != -1:
                return [('class:answer', line[:idx]), ('class:flags', line[idx:])]
            return [('class:answer', line)]
        return get_line

app = typer.Typer(help="IDM-CLI: A lightning-fast YouTube downloader.")
console = Console()

async def progress_listener(queue: asyncio.Queue, progress: Progress, pause_event: asyncio.Event = None, warning_state: dict = None):
    """Listens for progress updates from the downloader and updates the Rich progress bar."""
    while True:
        if warning_state and warning_state.get("show"):
            for task in progress.tasks:
                if "[WARNING: Press Ctrl+C again to cancel]" not in task.description:
                    progress.update(task.id, description=f"[bold yellow][WARNING: Press Ctrl+C again to cancel][/] {task.description}")
            warning_state["show"] = False

        if pause_event and msvcrt:
            if msvcrt.kbhit():
                key = msvcrt.getch().decode('utf-8', 'ignore').lower()
                if key == 'p' and pause_event.is_set():
                    pause_event.clear()
                    for task in progress.tasks:
                        if "Paused" not in task.description:
                            progress.update(task.id, description=f"[bold yellow]Paused[/] {task.description}")
                elif key == 'r' and not pause_event.is_set():
                    pause_event.set()
                    for task in progress.tasks:
                        if "Paused" in task.description:
                            new_desc = task.description.replace("[bold yellow]Paused[/] ", "")
                            progress.update(task.id, description=new_desc)
        
        try:
            update = await asyncio.wait_for(queue.get(), timeout=0.1)
        except asyncio.TimeoutError:
            continue
            
        if update is None:
            break  # Signal to stop
        
        task_id = update.get('task_id')
        if 'total_size' in update:
            progress.update(task_id, total=update['total_size'])
        elif 'bytes_downloaded' in update:
            progress.advance(task_id, advance=update['bytes_downloaded'])
            
        queue.task_done()

async def download_media(video_url: str, audio_url: str, headers: dict, chunks: int, video_dest: str, audio_dest: str, pause_event: asyncio.Event, warning_state: dict = None, media_type: str = "Video"):
    queue = asyncio.Queue()

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}", justify="right"),
        BarColumn(bar_width=40),
        "[progress.percentage]{task.percentage:>3.1f}%",
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console
    ) as progress:
        video_task_id = progress.add_task(f"[cyan]{media_type}", total=None) if video_url else None
        audio_task_id = progress.add_task("[magenta]Audio", total=None) if audio_url else None

        listener = asyncio.create_task(progress_listener(queue, progress, pause_event, warning_state))

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=None)) as session:
            v_task = asyncio.create_task(download_file(session, video_url, video_dest, headers, chunks, queue, video_task_id, pause_event)) if video_url else None
            a_task = asyncio.create_task(download_file(session, audio_url, audio_dest, headers, chunks, queue, audio_task_id, pause_event)) if audio_url else None
    
            tasks_to_gather = []
            if a_task:
                tasks_to_gather.append(a_task)
            if v_task:
                tasks_to_gather.append(v_task)
    
            await asyncio.gather(*tasks_to_gather)

        await queue.put(None)
        await listener

@app.command()
def download(
    url: Optional[str] = typer.Argument(None, help="The Video URL to download."),
    chunks: int = typer.Option(8, "--chunks", "-c", help="Number of concurrent chunks per file."),
    quality: Optional[str] = typer.Option(None, "--quality", "-q", help="Video quality (e.g., 720p, 1080p)."),
    audio_only: bool = typer.Option(False, "--audio-only", "-a", help="Download audio only."),
    video_only: bool = typer.Option(False, "--video", "-v", help="Download video + audio (bypasses prompt)."),
    queue: bool = typer.Option(False, "--queue", "-Q", help="Add to queue instead of downloading immediately.")
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

        if is_interactive and current_url and current_url.strip().lower() not in ["help", "exit", "start queue", "queue start", "resume"]:
            try:
                parts = shlex.split(current_url)
                parser = argparse.ArgumentParser(add_help=False)
                parser.add_argument('-q', '--quality')
                parser.add_argument('-a', '--audio-only', action='store_true')
                parser.add_argument('-v', '--video', action='store_true')
                parser.add_argument('-Q', '--queue', action='store_true')
                parser.add_argument('-c', '--chunks', type=int)
                
                parsed_args, unknown = parser.parse_known_args(parts)
                loop_quality = parsed_args.quality or loop_quality
                loop_audio_only = parsed_args.audio_only or loop_audio_only
                loop_video_only = parsed_args.video or loop_video_only
                loop_queue = parsed_args.queue or loop_queue
                loop_chunks = parsed_args.chunks or loop_chunks
                
                urls = [u for u in unknown if not u.startswith('-')]
                if urls:
                    current_url = urls[0]
            except Exception:
                pass

        fast_mode = not is_interactive or loop_quality or loop_audio_only or loop_video_only or loop_queue
        if fast_mode and not loop_quality and not loop_audio_only:
            loop_quality = "720p"

        if current_url.strip().lower() == "help":
            console.print("\n[bold cyan] Available Commands:[/bold cyan]")
            console.print("  [bold green]<URL>[/bold green]         - Paste any Video/File URL to download")
            console.print("  [bold green]resume[/bold green]      - Resume or delete an incomplete download")
            console.print("  [bold green]start queue[/bold green] - Start downloading queued files")
            console.print("  [bold green]help[/bold green]        - Show this help menu")
            console.print("  [bold green]exit[/bold green]        - Exit the application")
            
            console.print("\n[bold magenta]Fast Mode Flags (Skip Prompts):[/bold magenta]")
            console.print("  [bold white]-q <res>[/bold white]    - Set quality (e.g., -q 1080p, -q 720p)")
            console.print("  [bold white]-a[/bold white]          - Audio Only (Convert to MP3)")
            console.print("  [bold white]-Q[/bold white]          - Add directly to Queue instead of downloading")
            console.print("  [bold white]-c <num>[/bold white]    - Set number of parallel chunks (default: 8)")
            console.print("\n  [dim italic]Example: https://youtube.com/... -q 1080p -Q[/dim italic]\n")
            continue
            
        if current_url.strip().lower() == "exit":
            console.print("[bold green]Goodbye![/bold green]")
            raise typer.Exit()

        if current_url.strip().lower() in ["start queue", "queue start"]:
            incomplete = get_incomplete_downloads()
            queued = {tid: data for tid, data in incomplete.items() if data.get("status") == "queued"}
            if not queued:
                console.print("[bold green]No videos in queue![/]")
                if not is_interactive:
                    raise typer.Exit(code=0)
                current_url = None
                continue
                
            for tid, data in queued.items():
                console.print(f"[bold yellow]Starting queued download:[/] {data['title']}\n")
                url_to_extract = data['url']
                format_id = data['format_id']
                video_dest = data['video_dest']
                audio_dest = data['audio_dest']
                final_dest = data['final_dest']
                title = data['title']
                
                with console.status("[bold cyan]Fetching metadata...", spinner="dots"):
                    try:
                        extractor = get_extractor(url_to_extract)
                        info = extractor.fetch_all_info(url_to_extract)
                    except Exception as e:
                        console.print(f"[bold red]Error fetching info:[/] {e}")
                        continue
                
                if format_id == "direct_file":
                    ext = os.path.splitext(final_dest)[1].replace(".", "").upper()
                    media_type = f"{ext} File" if ext else "File"
                elif format_id == "audio_only":
                    media_type = "Audio"
                else:
                    media_type = "Video"
                    
                with console.status(f"[bold cyan]Extracting URLs...", spinner="dots"):
                    try:
                        extractor = get_extractor(url_to_extract)
                        extracted = extractor.extract_urls(info, format_id)
                        video_url = extracted.get("video_url")
                        audio_url = extracted.get("audio_url")
                        headers = extracted.get("headers", {})
                        if not video_url: video_dest = ""
                        if not audio_url: audio_dest = ""
                    except Exception as e:
                        console.print(f"[bold red]Error extracting URLs:[/] {e}")
                        continue

                pause_event = asyncio.Event()
                pause_event.set()
                warning_state = {"show": False}
                
                try:
                    asyncio.run(download_media(video_url, audio_url, headers, loop_chunks, video_dest, audio_dest, pause_event, warning_state, media_type))
                    with console.status("[bold magenta]Running FFmpeg...", spinner="bouncingBar"):
                        if video_dest and audio_dest:
                            mux_audio_video(video_dest, audio_dest, final_dest)
                        elif audio_dest and not video_dest:
                            convert_to_mp3(audio_dest, final_dest)
                        elif video_dest and not audio_dest:
                            import shutil
                            shutil.move(video_dest, final_dest)
                    remove_download(tid)
                    console.print(f"\n[bold green]Success! {media_type} saved as:[/] [bold white]{final_dest}[/]")
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    console.print(f"[bold red]Download failed:[/] {e}")
            if not is_interactive:
                raise typer.Exit(code=0)
            current_url = None
            continue
                
        if current_url.strip().lower() == "resume":
            incomplete = get_incomplete_downloads()
            if not incomplete:
                console.print("[bold green]No incomplete downloads found![/]")
                if not is_interactive:
                    raise typer.Exit(code=1)
                continue
                
            choices = []
            for tid, data in incomplete.items():
                choices.append(f"[Resume] {data['title']}")
                choices.append(f"[Delete] {data['title']}")
            choices.append("[Back to Main]")
                
            selected = questionary.select("Select an action:", choices=choices, style=custom_style).ask(kbi_msg="")
            if not selected:
                console.print("[bold red]Cancelled by user[/bold red]")
                if not is_interactive:
                    raise typer.Exit(code=1)
                continue
                
            if selected == "[Back to Main]":
                console.print("[bold cyan]Returning to main menu...[/bold cyan]")
                continue
                
            action = "Resume" if selected.startswith("[Resume]") else "Delete"
            title_selected = selected.split("] ", 1)[1]
            
            task_id = None
            task_data = None
            for tid, data in incomplete.items():
                if data['title'] == title_selected:
                    task_id = tid
                    task_data = data
                    break
                    
            if action == "Delete":
                remove_download(task_id)
                # Remove any partial files if they exist
                if os.path.exists(task_data['video_dest']): os.remove(task_data['video_dest'])
                if os.path.exists(task_data['audio_dest']): os.remove(task_data['audio_dest'])
                for i in range(32): # Clean parts up to 32 chunks
                    v_part = f"{task_data['video_dest']}.part{i}"
                    a_part = f"{task_data['audio_dest']}.part{i}"
                    if os.path.exists(v_part): os.remove(v_part)
                    if os.path.exists(a_part): os.remove(a_part)
                console.print(f"[bold red]Deleted:[/] {title_selected}")
                if not is_interactive:
                    raise typer.Exit(code=0)
                continue
                
            console.print(f"[bold yellow]Resuming download for:[/] {title_selected}\n")
            url_to_extract = task_data['url']
            format_id = task_data['format_id']
            video_dest = task_data['video_dest']
            audio_dest = task_data['audio_dest']
            final_dest = task_data['final_dest']
            title = task_data['title']
            found_task_id = task_id
        else:
            url_to_extract = current_url
            incomplete = get_incomplete_downloads()
            
            found_task_data = None
            
            for tid, data in incomplete.items():
                if data.get('url') == url_to_extract:
                    found_task_id = tid
                    found_task_data = data
                    break
                    
            if found_task_id:
                console.print("[bold yellow]Found in resume list! Auto-resuming...[/]")
                task_id = found_task_id
                format_id = found_task_data['format_id']
                video_dest = found_task_data['video_dest']
                audio_dest = found_task_data['audio_dest']
                final_dest = found_task_data['final_dest']
                title = found_task_data['title']
            else:
                format_id = None
                task_id = str(uuid.uuid4())
                console.print(f"[bold yellow]Initializing download for:[/] {current_url}\n")
                
                if loop_audio_only:
                    format_id = "audio_only"

        with console.status("[bold cyan]Fetching metadata...", spinner="dots"):
            try:
                extractor = get_extractor(url_to_extract)
                info = extractor.fetch_all_info(url_to_extract)
                title = info.get("title", "download") if not found_task_id else title
                
                if info.get("_type") == "playlist":
                    console.print("\n[bold yellow]Currently, the feature to download album/playlist photos or videos is not added.[/]")
                    current_url = None
                    if not is_interactive:
                        raise typer.Exit(code=0)
                    continue

                if not found_task_id and format_id != "audio_only":
                    resolutions = extractor.get_video_resolutions(info)
            except Exception as e:
                console.print(f"[bold red]Error fetching info:[/] {e}")
                if not is_interactive:
                    raise typer.Exit(code=1)
                continue

        if not found_task_id:
            if format_id != "audio_only":
                if not resolutions:
                    console.print("[bold red]No video resolutions found.[/]")
                    if not is_interactive:
                        raise typer.Exit(code=1)
                    continue

                console.print(f"[bold green]*[/] Fetched info for: [bold white]{title}[/]")
                
                if loop_quality or len(resolutions) == 1:
                    matched = next((r for r in resolutions if r['resolution'] == loop_quality), None)
                    if matched:
                        selected_res = matched['resolution']
                    else:
                        selected_res = resolutions[0]['resolution']
                else:
                    choices = [r['resolution'] for r in resolutions]
                    prompt_text = "Choose video quality:" if format_id != "direct_file" else "Choose download option:"
                    selected_res = questionary.select(prompt_text, choices=choices, style=custom_style).ask(kbi_msg="")
                    if not selected_res:
                        console.print("[bold red]Cancelled by user[/bold red]")
                        if not is_interactive:
                            raise typer.Exit(code=1)
                        continue

                selected_format = next(r for r in resolutions if r['resolution'] == selected_res)
                format_id = selected_format['format_id']
            
            safe_title = "".join([c for c in title if c.isalpha() or c.isdigit() or c in ' -_.']).rstrip()[:60].strip()
            downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
            os.makedirs(downloads_dir, exist_ok=True)
            
            tmp_dir = os.path.expanduser("~/.idm_cli/tmp")
            os.makedirs(tmp_dir, exist_ok=True)
            
            if format_id == "direct_file":
                video_dest = os.path.join(tmp_dir, safe_title)
                audio_dest = ""
                final_dest = os.path.join(downloads_dir, safe_title)
            elif format_id == "audio_only":
                video_dest = ""
                audio_dest = os.path.join(tmp_dir, f"{safe_title}_audio.m4a")
                final_dest = os.path.join(downloads_dir, f"{safe_title}.mp3")
            else:
                video_dest = os.path.join(tmp_dir, f"{safe_title}_video.mp4")
                audio_dest = os.path.join(tmp_dir, f"{safe_title}_audio.m4a")
                final_dest = os.path.join(downloads_dir, f"{safe_title}.mp4")

            if loop_queue:
                save_download(task_id, url_to_extract, format_id, title, video_dest, audio_dest, final_dest, status="queued")
                console.print("[bold green]Added to queue![/]")
                if not is_interactive:
                    raise typer.Exit(code=0)
                continue

        if format_id == "direct_file":
            ext = os.path.splitext(final_dest)[1].replace(".", "").upper()
            media_type = f"{ext} File" if ext else "File"
        elif format_id == "audio_only":
            media_type = "Audio"
        else:
            media_type = "Video"


        with console.status(f"[bold cyan]Extracting URLs...", spinner="dots"):
            try:
                extractor = get_extractor(url_to_extract)
                extracted = extractor.extract_urls(info, format_id)
                video_url = extracted.get("video_url")
                audio_url = extracted.get("audio_url")
                headers = extracted.get("headers", {})
                if not video_url: video_dest = ""
                if not audio_url: audio_dest = ""
            except Exception as e:
                console.print(f"[bold red]Error extracting URLs:[/] {e}")
                if not is_interactive:
                    raise typer.Exit(code=1)
                continue

        # Save state before downloading
        save_download(task_id, url_to_extract, format_id, title, video_dest, audio_dest, final_dest, status="interrupted")
        
        console.print(f"[bold green]*[/] Using {loop_chunks} chunks per file.")
        console.print("[bold cyan]Starting parallel downloads... (Press 'p' to pause, 'r' to resume)[/]\n")

        pause_event = asyncio.Event()
        pause_event.set()

        last_dl_ctrl_c = 0.0
        original_sigint = signal.getsignal(signal.SIGINT)
        warning_state = {"show": False}

        def custom_handler(signum, frame):
            nonlocal last_dl_ctrl_c
            if time.time() - last_dl_ctrl_c <= 5:
                signal.signal(signal.SIGINT, original_sigint)
                os.kill(os.getpid(), signal.SIGINT)
            else:
                warning_state["show"] = True
                last_dl_ctrl_c = time.time()

        signal.signal(signal.SIGINT, custom_handler)

        try:
            asyncio.run(download_media(video_url, audio_url, headers, loop_chunks, video_dest, audio_dest, pause_event, warning_state, media_type))
        except KeyboardInterrupt:
            console.print("\n[bold red]Download cancelled by user. Progress saved to resume later.[/bold red]")
            continue
        except Exception as e:
            console.print(f"[bold red]Download failed:[/] {e}")
            if not is_interactive:
                raise typer.Exit(code=1)
            continue
        finally:
            signal.signal(signal.SIGINT, original_sigint)

        console.print("\n[bold green]✓[/] Downloads completed.")
        console.print("[bold cyan]Muxing audio and video streams...[/]")

        with console.status("[bold magenta]Running FFmpeg...", spinner="bouncingBar"):
            try:
                if video_dest and audio_dest:
                    mux_audio_video(video_dest, audio_dest, final_dest)
                elif audio_dest and not video_dest:
                    convert_to_mp3(audio_dest, final_dest)
                elif video_dest and not audio_dest:
                    import shutil
                    shutil.move(video_dest, final_dest)
            except Exception as e:
                console.print(f"[bold red]Muxing failed:[/] {e}")
                if not is_interactive:
                    raise typer.Exit(code=1)
                continue

        remove_download(task_id)
        console.print(f"\n[bold green] Success! {media_type} saved as:[/] [bold white]{final_dest}[/]")
        
        if not is_interactive:
            raise typer.Exit(code=0)
        url = None

if __name__ == "__main__":
    app()
