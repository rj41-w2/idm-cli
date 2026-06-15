import asyncio
import os
import sys
import time
import uuid
import typer
import signal
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

try:
    import msvcrt
except ImportError:
    msvcrt = None

from idm_cli.extractor import fetch_all_info, get_video_resolutions, extract_urls
from idm_cli.downloader import download_file
from idm_cli.muxer import mux_audio_video, convert_to_mp3
from idm_cli.state import save_download, remove_download, get_incomplete_downloads

custom_style = questionary.Style([
    ('qmark', 'fg:cyan bold'),       
    ('question', 'bold'),               
    ('answer', 'fg:cyan bold'),      
    ('pointer', 'fg:cyan bold'),     
    ('highlighted', 'fg:cyan bold'), 
])

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

async def download_media(video_url: str, audio_url: str, headers: dict, chunks: int, video_dest: str, audio_dest: str, pause_event: asyncio.Event, warning_state: dict = None):
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
        video_task_id = progress.add_task("[cyan]Video", total=None) if video_url else None
        audio_task_id = progress.add_task("[magenta]Audio", total=None)

        listener = asyncio.create_task(progress_listener(queue, progress, pause_event, warning_state))

        v_task = asyncio.create_task(download_file(video_url, video_dest, headers, chunks, queue, video_task_id, pause_event)) if video_url else None
        a_task = asyncio.create_task(download_file(audio_url, audio_dest, headers, chunks, queue, audio_task_id, pause_event))

        tasks_to_gather = [a_task]
        if v_task:
            tasks_to_gather.append(v_task)

        await asyncio.gather(*tasks_to_gather)

        await queue.put(None)
        await listener

@app.command()
def download(url: Optional[str] = typer.Argument(None, help="The YouTube URL to download."), chunks: int = typer.Option(8, "--chunks", "-c", help="Number of concurrent chunks per file.")):
    """
    Download a YouTube video at maximum speed using parallel chunks.
    """
    banner = pyfiglet.figlet_format("IDM  CLI")
    console.print(f"[bold green]{banner}[/bold green]")
    console.print("[bold cyan]--- The Ultimate High-Speed CLI Downloader ---[/bold cyan]")
    console.print("Type 'help' for available commands\n", style="white")
    
    is_interactive = (url is None)
    last_ctrl_c_time = 0
    show_warning = False
    
    while True:
        current_url = url
        if not current_url:
            prompt_str = "idm (Press again ctrl+c to exit) " if show_warning else "idm "
            current_url = questionary.text(prompt_str, style=custom_style).ask(kbi_msg="")
            if current_url is None:
                if time.time() - last_ctrl_c_time <= 5:
                    console.print("[bold red]Cancelled by user[/bold red]")
                    raise typer.Exit()
                else:
                    last_ctrl_c_time = time.time()
                    show_warning = True
                    continue
            elif not current_url.strip():
                continue
        
        last_ctrl_c_time = 0
        show_warning = False
        found_task_id = None
        if current_url.strip().lower() == "help":
            console.print("\n[bold cyan]Available Commands:[/bold cyan]")
            console.print("  [bold green]<URL>[/bold green]    - Paste a YouTube URL to download")
            console.print("  [bold green]resume[/bold green] - Resume or delete an incomplete download")
            console.print("  [bold green]start queue[/bold green] - Start downloading queued videos")
            console.print("  [bold green]help[/bold green]   - Show this help menu")
            console.print("  [bold green]exit[/bold green]   - Exit the application\n")
            continue
            
        if current_url.strip().lower() == "exit":
            console.print("[bold green]Goodbye![/bold green]")
            raise typer.Exit()

        if current_url.strip().lower() in ["start queue", "queue start"]:
            incomplete = get_incomplete_downloads()
            queued = {tid: data for tid, data in incomplete.items() if data.get("status") == "queued"}
            if not queued:
                console.print("[bold green]No videos in queue![/]")
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
                        info = fetch_all_info(url_to_extract)
                    except Exception as e:
                        console.print(f"[bold red]Error fetching info:[/] {e}")
                        continue
                
                with console.status(f"[bold cyan]Extracting URLs...", spinner="dots"):
                    try:
                        extracted = extract_urls(info, format_id)
                        video_url = extracted.get("video_url")
                        audio_url = extracted.get("audio_url")
                        headers = extracted.get("headers", {})
                    except Exception as e:
                        console.print(f"[bold red]Error extracting URLs:[/] {e}")
                        continue

                pause_event = asyncio.Event()
                pause_event.set()
                warning_state = {"show": False}
                
                try:
                    asyncio.run(download_media(video_url, audio_url, headers, chunks, video_dest, audio_dest, pause_event, warning_state))
                    with console.status("[bold magenta]Running FFmpeg...", spinner="bouncingBar"):
                        if video_dest:
                            mux_audio_video(video_dest, audio_dest, final_dest)
                        else:
                            convert_to_mp3(audio_dest, final_dest)
                    remove_download(tid)
                    console.print(f"\n[bold green]🎉 Success! Video saved as:[/] [bold white]{final_dest}[/]")
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    console.print(f"[bold red]Download failed:[/] {e}")
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
                
                dl_type = questionary.select("Download type:", choices=["Video + Audio", "Audio Only"], style=custom_style).ask(kbi_msg="")
                if not dl_type:
                    console.print("[bold red]Cancelled by user[/bold red]")
                    if not is_interactive:
                        raise typer.Exit(code=1)
                    continue
                if dl_type == "Audio Only":
                    format_id = "audio_only"

        with console.status("[bold cyan]Fetching metadata...", spinner="dots"):
            try:
                info = fetch_all_info(url_to_extract)
                title = info.get("title", "download") if not found_task_id else title
                if not found_task_id and format_id != "audio_only":
                    resolutions = get_video_resolutions(info)
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

                console.print(f"[bold green]✓[/] Fetched info for: [bold white]{title}[/]")
                choices = [r['resolution'] for r in resolutions]
                selected_res = questionary.select("Choose video quality:", choices=choices, style=custom_style).ask(kbi_msg="")
                if not selected_res:
                    console.print("[bold red]Cancelled by user[/bold red]")
                    if not is_interactive:
                        raise typer.Exit(code=1)
                    continue

                selected_format = next(r for r in resolutions if r['resolution'] == selected_res)
                format_id = selected_format['format_id']
            
            safe_title = "".join([c for c in title if c.isalpha() or c.isdigit() or c in ' -_']).rstrip()
            if format_id == "audio_only":
                video_dest = ""
                audio_dest = f"{safe_title}_audio.m4a"
                final_dest = f"{safe_title}.mp3"
            else:
                video_dest = f"{safe_title}_video.mp4"
                audio_dest = f"{safe_title}_audio.m4a"
                final_dest = f"{safe_title}.mp4"

            action = questionary.select("Action:", choices=["Download Now", "Add to Queue"], style=custom_style).ask(kbi_msg="")
            if not action:
                console.print("[bold red]Cancelled by user[/bold red]")
                continue
            if action == "Add to Queue":
                save_download(task_id, url_to_extract, format_id, title, video_dest, audio_dest, final_dest, status="queued")
                console.print("[bold green]Added to queue![/]")
                continue

        with console.status(f"[bold cyan]Extracting URLs...", spinner="dots"):
            try:
                extracted = extract_urls(info, format_id)
                video_url = extracted.get("video_url")
                audio_url = extracted.get("audio_url")
                headers = extracted.get("headers", {})
            except Exception as e:
                console.print(f"[bold red]Error extracting URLs:[/] {e}")
                if not is_interactive:
                    raise typer.Exit(code=1)
                continue

        # Save state before downloading
        save_download(task_id, url_to_extract, format_id, title, video_dest, audio_dest, final_dest, status="interrupted")
        
        console.print(f"[bold green]✓[/] Using {chunks} chunks per file.")
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
            asyncio.run(download_media(video_url, audio_url, headers, chunks, video_dest, audio_dest, pause_event, warning_state))
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
                if video_dest:
                    mux_audio_video(video_dest, audio_dest, final_dest)
                else:
                    convert_to_mp3(audio_dest, final_dest)
            except Exception as e:
                console.print(f"[bold red]Muxing failed:[/] {e}")
                if not is_interactive:
                    raise typer.Exit(code=1)
                continue

        remove_download(task_id)
        console.print(f"\n[bold green]🎉 Success! Video saved as:[/] [bold white]{final_dest}[/]")
        
        if not is_interactive:
            break
        url = None

if __name__ == "__main__":
    app()
