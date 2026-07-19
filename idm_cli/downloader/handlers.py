import os
import asyncio
import shutil
import typer
import questionary
import psutil
from idm_cli.downloader.state import get_incomplete_downloads, remove_download
from idm_cli.extractors import get_extractor
from idm_cli.downloader.core import run_download_and_mux
from idm_cli.ui.utils import console, custom_style
from idm_cli.config import logger, CONFIG_DIR

LOCK_FILE = os.path.join(CONFIG_DIR, "queue.lock")

def _is_daemon_running() -> bool:
    if not os.path.exists(LOCK_FILE):
        return False
    try:
        with open(LOCK_FILE, "r") as f:
            pid = int(f.read().strip())
        if pid == os.getpid():
            return False
        return psutil.pid_exists(pid)
    except (OSError, ValueError):
        return False

def _acquire_lock() -> bool:
    os.makedirs(os.path.dirname(LOCK_FILE), exist_ok=True)
    try:
        fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        try:
            os.write(fd, str(os.getpid()).encode())
        finally:
            os.close(fd)
        return True
    except FileExistsError:
        try:
            with open(LOCK_FILE, "r") as f:
                pid = int(f.read().strip())
            if psutil.pid_exists(pid):
                return False
        except (OSError, ValueError):
            pass
        try:
            os.remove(LOCK_FILE)
        except OSError:
            pass
        return _acquire_lock()

def _release_lock():
    if not os.path.exists(LOCK_FILE):
        return
    try:
        with open(LOCK_FILE, "r") as f:
            pid = int(f.read().strip())
        if pid == os.getpid():
            os.remove(LOCK_FILE)
    except (OSError, ValueError):
        pass

def handle_queue(is_interactive: bool, loop_chunks: int):
    if not _acquire_lock():
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
                run_download_and_mux(video_url, audio_url, headers, loop_chunks, video_dest, audio_dest, final_dest, media_type, pause_event, warning_state)
                remove_download(tid)
                console.print(f"\n[bold green]Success! {media_type} saved as:[/] [bold white]{final_dest}[/]")
            except KeyboardInterrupt:
                break
            except ConnectionError as e:
                console.print(f"\n[bold red]{e}[/]")
                logger.error(f"Connection failed for {data['title']}: {e}")
                break
            except (ValueError, TypeError, OSError) as e:
                logger.error(f"Download failed: {e}")
                console.print(f"[bold red]Download failed:[/] {e}")
                remove_download(tid)
    finally:
        _release_lock()
        
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
        v_progress = f"{task_data['video_dest']}.progress.json"
        a_progress = f"{task_data['audio_dest']}.progress.json"
        if os.path.exists(v_progress): os.remove(v_progress)
        if os.path.exists(a_progress): os.remove(a_progress)
        console.print(f"[bold red]Deleted:[/] {title_selected}")
        if not is_interactive:
            raise typer.Exit(code=0)
        return None
        
    console.print(f"[bold yellow]Resuming download for:[/] {title_selected}\n")
    return task_id, task_data
