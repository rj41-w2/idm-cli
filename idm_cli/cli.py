import asyncio
import os
import uuid
import typer
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
from idm_cli.muxer import mux_audio_video
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

async def progress_listener(queue: asyncio.Queue, progress: Progress, pause_event: asyncio.Event = None):
    """Listens for progress updates from the downloader and updates the Rich progress bar."""
    while True:
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

async def download_media(video_url: str, audio_url: str, headers: dict, chunks: int, video_dest: str, audio_dest: str, pause_event: asyncio.Event):
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
        video_task_id = progress.add_task("[cyan]Video", total=None)
        audio_task_id = progress.add_task("[magenta]Audio", total=None)

        listener = asyncio.create_task(progress_listener(queue, progress, pause_event))

        v_task = asyncio.create_task(download_file(video_url, video_dest, headers, chunks, queue, video_task_id, pause_event))
        a_task = asyncio.create_task(download_file(audio_url, audio_dest, headers, chunks, queue, audio_task_id, pause_event))

        await asyncio.gather(v_task, a_task)

        await queue.put(None)
        await listener

@app.command()
def download(url: Optional[str] = typer.Argument(None, help="The YouTube URL to download."), chunks: int = typer.Option(8, "--chunks", "-c", help="Number of concurrent chunks per file.")):
    """
    Download a YouTube video at maximum speed using parallel chunks.
    """
    banner = pyfiglet.figlet_format("IDM  CLI")
    console.print(f"[bold green]{banner}[/bold green]")
    console.print("[bold cyan]--- The Ultimate High-Speed CLI Downloader ---[/bold cyan]\n")
    
    is_interactive = (url is None)
    
    while True:
        current_url = url
        if not current_url:
            current_url = questionary.text("idm ", style=custom_style).ask(kbi_msg="")
            if not current_url:
                console.print("[bold red]Cancelled by user[/bold red]")
                raise typer.Exit()
                
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
                
            selected = questionary.select("Select an action:", choices=choices, style=custom_style).ask(kbi_msg="")
            if not selected:
                console.print("[bold red]Cancelled by user[/bold red]")
                if not is_interactive:
                    raise typer.Exit(code=1)
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
        else:
            url_to_extract = current_url
            format_id = None
            task_id = str(uuid.uuid4())
            console.print(f"[bold yellow]Initializing download for:[/] {current_url}\n")

        with console.status("[bold cyan]Fetching metadata...", spinner="dots"):
            try:
                info = fetch_all_info(url_to_extract)
                title = info.get("title", "download") if format_id is None else title
                if format_id is None:
                    resolutions = get_video_resolutions(info)
            except Exception as e:
                console.print(f"[bold red]Error fetching info:[/] {e}")
                if not is_interactive:
                    raise typer.Exit(code=1)
                continue

        if format_id is None:
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
            video_dest = f"{safe_title}_video.mp4"
            audio_dest = f"{safe_title}_audio.m4a"
            final_dest = f"{safe_title}.mp4"

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
        save_download(task_id, url_to_extract, format_id, title, video_dest, audio_dest, final_dest)
        
        console.print(f"[bold green]✓[/] Using {chunks} chunks per file.")
        console.print("[bold cyan]Starting parallel downloads... (Press 'p' to pause, 'r' to resume)[/]\n")

        pause_event = asyncio.Event()
        pause_event.set()

        try:
            asyncio.run(download_media(video_url, audio_url, headers, chunks, video_dest, audio_dest, pause_event))
        except Exception as e:
            console.print(f"[bold red]Download failed:[/] {e}")
            if not is_interactive:
                raise typer.Exit(code=1)
            continue

        console.print("\n[bold green]✓[/] Downloads completed.")
        console.print("[bold cyan]Muxing audio and video streams...[/]")

        with console.status("[bold magenta]Running FFmpeg...", spinner="bouncingBar"):
            try:
                mux_audio_video(video_dest, audio_dest, final_dest)
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
