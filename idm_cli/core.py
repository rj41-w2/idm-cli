import os
import asyncio
import uuid
import signal
import time
import shutil
import typer
import questionary
from idm_cli.state import save_download, remove_download, get_incomplete_downloads
from idm_cli.extractors import get_extractor
from idm_cli.downloader import download_media
from idm_cli.muxer import mux_audio_video, convert_to_mp3
from idm_cli.utils import console, custom_style

def process_download(
    current_url: str,
    is_interactive: bool,
    loop_quality: str,
    loop_audio_only: bool,
    loop_queue: bool,
    loop_chunks: int,
    loop_filename: str,
    found_task_id: str = None,
    found_task_data: dict = None
):
    url_to_extract = current_url
    title = ""
    format_id = None

    if not found_task_id:
        incomplete = get_incomplete_downloads()
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
            if loop_filename and not found_task_id:
                title = os.path.basename(loop_filename)
            
            if info.get("_type") == "playlist":
                console.print("\n[bold yellow]Currently, the feature to download album/playlist photos or videos is not added.[/]")
                if not is_interactive:
                    raise typer.Exit(code=0)
                return False

            resolutions = []
            if not found_task_id and format_id != "audio_only":
                resolutions = extractor.get_video_resolutions(info)
        except Exception as e:
            console.print(f"[bold red]Error fetching info:[/] {e}")
            if not is_interactive:
                raise typer.Exit(code=1)
            return False

    if not found_task_id:
        if format_id != "audio_only":
            if not resolutions:
                console.print("[bold red]No video resolutions found.[/]")
                if not is_interactive:
                    raise typer.Exit(code=1)
                return False

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
                    return False

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
            return False

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
            return False

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
        return False
    except Exception as e:
        console.print(f"[bold red]Download failed:[/] {e}")
        if not is_interactive:
            raise typer.Exit(code=1)
        return False
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
                shutil.move(video_dest, final_dest)
        except Exception as e:
            console.print(f"[bold red]Muxing failed:[/] {e}")
            if not is_interactive:
                raise typer.Exit(code=1)
            return False

    remove_download(task_id)
    console.print(f"\n[bold green] Success! {media_type} saved as:[/] [bold white]{final_dest}[/]")
    
    if not is_interactive:
        raise typer.Exit(code=0)
    return True
