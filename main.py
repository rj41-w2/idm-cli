import asyncio
import os
import typer
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

from idm_cli.extractor import fetch_all_info, get_video_resolutions, extract_urls
from idm_cli.downloader import download_file
from idm_cli.muxer import mux_audio_video

app = typer.Typer(help="IDM-CLI: A lightning-fast YouTube downloader.")
console = Console()

async def progress_listener(queue: asyncio.Queue, progress: Progress):
    """Listens for progress updates from the downloader and updates the Rich progress bar."""
    while True:
        update = await queue.get()
        if update is None:
            break  # Signal to stop
        
        task_id = update.get('task_id')
        if 'total_size' in update:
            # Set total size dynamically without affecting current progress
            progress.update(task_id, total=update['total_size'])
        elif 'bytes_downloaded' in update:
            # Safely increment existing task's progress by the new delta.
            # We NEVER create a new progress bar task for retries, and we only `advance`
            # by newly downloaded bytes. This prevents any progress bar jumping or duplication.
            progress.advance(task_id, advance=update['bytes_downloaded'])
            
        queue.task_done()

async def download_media(video_url: str, audio_url: str, headers: dict, title: str):
    # Sanitize title for filename
    safe_title = "".join([c for c in title if c.isalpha() or c.isdigit() or c in ' -_']).rstrip()
    
    video_dest = f"{safe_title}_video.mp4"
    audio_dest = f"{safe_title}_audio.m4a"
    final_dest = f"{safe_title}.mp4"

    queue = asyncio.Queue()

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}", justify="right"),
        BarColumn(bar_width=None),
        "[progress.percentage]{task.percentage:>3.1f}%",
        "•",
        DownloadColumn(),
        "•",
        TransferSpeedColumn(),
        "•",
        TimeRemainingColumn(),
        console=console,
        expand=True
    ) as progress:
        
        # We don't know the exact size until we fetch headers, so we initialize with total=0
        # The downloader can update the total size, but since our downloader signature 
        # (based on prompt) just expects task_id and sends chunk sizes, we'll need the 
        # downloader to send the total size as a special message, or just let the downloader
        # fetch the size and maybe we can just advance.
        # Actually, let's update the downloader to send `(task_id, chunk_size, total_size)` 
        # so we can dynamically set the total. 
        # Wait, the downloader prompt was: `put progress updates (like chunk sizes downloaded) into the queue`.
        
        video_task_id = progress.add_task("[cyan]Downloading Video...", total=None)
        audio_task_id = progress.add_task("[magenta]Downloading Audio...", total=None)

        # Start the listener
        listener = asyncio.create_task(progress_listener(queue, progress))

        # Start downloads
        v_task = asyncio.create_task(download_file(video_url, video_dest, headers, 8, queue, video_task_id))
        a_task = asyncio.create_task(download_file(audio_url, audio_dest, headers, 8, queue, audio_task_id))

        await asyncio.gather(v_task, a_task)

        # Stop the listener
        await queue.put(None)
        await listener

    return video_dest, audio_dest, final_dest


@app.command()
def download(url: str, chunks: int = typer.Option(8, "--chunks", "-c", help="Number of concurrent chunks per file.")):
    """
    Download a YouTube video at maximum speed using parallel chunks.
    """
    # Print Banner
    banner = pyfiglet.figlet_format("IDM - CLI")
    console.print(f"[bold green]{banner}[/bold green]")
    console.print(f"[bold yellow]Initializing download for:[/] {url}\n")

    with console.status("[bold cyan]Fetching available resolutions...", spinner="dots"):
        try:
            info = fetch_all_info(url)
            resolutions = get_video_resolutions(info)
            title = info.get("title", "download")
        except Exception as e:
            console.print(f"[bold red]Error fetching info:[/] {e}")
            raise typer.Exit(code=1)

    if not resolutions:
        console.print("[bold red]No video resolutions found.[/]")
        raise typer.Exit(code=1)

    console.print(f"[bold green]✓[/] Fetched info for: [bold white]{title}[/]")

    choices = [r['resolution'] for r in resolutions]
    selected_res = questionary.select(
        "Choose video quality:",
        choices=choices
    ).ask()

    if not selected_res:
        console.print("[bold red]Download cancelled.[/]")
        raise typer.Exit(code=1)

    selected_format = next(r for r in resolutions if r['resolution'] == selected_res)

    with console.status(f"[bold cyan]Extracting URLs for {selected_res}...", spinner="dots"):
        try:
            extracted = extract_urls(info, selected_format['format_id'])
            video_url = extracted.get("video_url")
            audio_url = extracted.get("audio_url")
            headers = extracted.get("headers", {})
            title = extracted.get("title", "download")
        except Exception as e:
            console.print(f"[bold red]Error extracting URLs:[/] {e}")
            raise typer.Exit(code=1)

    console.print(f"[bold green]✓[/] Using {chunks} chunks per file.")
    console.print("[bold cyan]Starting parallel downloads...[/]\n")

    # Run async download
    try:
        video_dest, audio_dest, final_dest = asyncio.run(download_media(video_url, audio_url, headers, title))
    except Exception as e:
        console.print(f"[bold red]Download failed:[/] {e}")
        raise typer.Exit(code=1)

    console.print("\n[bold green]✓[/] Downloads completed.")
    console.print("[bold cyan]Muxing audio and video streams...[/]")

    with console.status("[bold magenta]Running FFmpeg...", spinner="bouncingBar"):
        try:
            mux_audio_video(video_dest, audio_dest, final_dest)
        except Exception as e:
            console.print(f"[bold red]Muxing failed:[/] {e}")
            raise typer.Exit(code=1)

    console.print(f"\n[bold green]🎉 Success! Video saved as:[/] [bold white]{final_dest}[/]")


if __name__ == "__main__":
    app()
