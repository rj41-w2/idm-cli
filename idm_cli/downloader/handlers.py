import os
import asyncio
import shutil
import typer
import questionary
from idm_cli.downloader.state import get_incomplete_downloads, remove_download
from idm_cli.extractors import get_extractor
from idm_cli.downloader.downloader import download_media
from idm_cli.downloader.muxer import mux_audio_video, convert_to_mp3
from idm_cli.ui.utils import console, custom_style
from idm_cli.extension.daemon import acquire_lock, release_lock
from idm_cli.config import logger

def handle_queue(is_interactive: bool, loop_chunks: int):
    if not acquire_lock():
        console.print("[bold red]Queue daemon is already running![/]")
        if not is_interactive:
            raise typer.Exit(code=1)
        return
    
    try:
        while True:
            incomplete = get_incomplete_downloads()
            queued = {tid: data for tid, data in incomplete.items() if data.get("status") == "queued"}
            if not queued:
                console.print("[bold green]No videos in queue![/]")
                break
                
            tid, data = list(queued.items())[0]
            console.print(f"[bold yellow]Starting queued download:[/] {data['title']}\n")
            url_to_extract = data['url']
            format_id = data['format_id']
            video_dest = data['video_dest']
            audio_dest = data['audio_dest']
            final_dest = data['final_dest']
            
            with console.status("[bold cyan]Fetching metadata...", spinner="dots"):
                try:
                    extractor = get_extractor(url_to_extract)
                    info = extractor.fetch_all_info(url_to_extract)
                except (ValueError, TypeError, OSError) as e:
                    logger.error(f"Error fetching info: {e}")
                    console.print(f"[bold red]Error fetching info:[/] {e}")
                    remove_download(tid)
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
                except (ValueError, TypeError, OSError) as e:
                    logger.error(f"Error extracting URLs: {e}")
                    console.print(f"[bold red]Error extracting URLs:[/] {e}")
                    remove_download(tid)
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
                        shutil.move(video_dest, final_dest)
                remove_download(tid)
                console.print(f"\n[bold green]Success! {media_type} saved as:[/] [bold white]{final_dest}[/]")
            except KeyboardInterrupt:
                break
            except (ValueError, TypeError, OSError) as e:
                logger.error(f"Download failed: {e}")
                console.print(f"[bold red]Download failed:[/] {e}")
                remove_download(tid)
    finally:
        release_lock()
        
    if not is_interactive:
        raise typer.Exit(code=0)

def handle_resume(is_interactive: bool):
    incomplete = get_incomplete_downloads()
    if not incomplete:
        console.print("[bold green]No incomplete downloads found![/]")
        if not is_interactive:
            raise typer.Exit(code=1)
        return None
        
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
        return None
        
    if selected == "[Back to Main]":
        console.print("[bold cyan]Returning to main menu...[/bold cyan]")
        return None
        
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
        if os.path.exists(task_data['video_dest']): os.remove(task_data['video_dest'])
        if os.path.exists(task_data['audio_dest']): os.remove(task_data['audio_dest'])
        for i in range(32):
            v_part = f"{task_data['video_dest']}.part{i}"
            a_part = f"{task_data['audio_dest']}.part{i}"
            if os.path.exists(v_part): os.remove(v_part)
            if os.path.exists(a_part): os.remove(a_part)
        console.print(f"[bold red]Deleted:[/] {title_selected}")
        if not is_interactive:
            raise typer.Exit(code=0)
        return None
        
    console.print(f"[bold yellow]Resuming download for:[/] {title_selected}\n")
    return task_id, task_data
