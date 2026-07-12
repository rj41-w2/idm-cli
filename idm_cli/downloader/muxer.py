import os
import subprocess
import logging
import shutil
import zipfile
import aiohttp
from idm_cli.ui.utils import console

logger = logging.getLogger(__name__)

def get_ffmpeg_path() -> str:
    sys_path = shutil.which("ffmpeg")
    if sys_path:
        return sys_path
    
    local_path = os.path.expanduser("~/.idm_cli/bin/ffmpeg.exe")
    if os.path.exists(local_path):
        return local_path
        
    return None

async def download_ffmpeg() -> str:
    url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
    bin_dir = os.path.expanduser("~/.idm_cli/bin")
    os.makedirs(bin_dir, exist_ok=True)
    zip_path = os.path.join(bin_dir, "ffmpeg.zip")
    
    from idm_cli.downloader.downloader import download_media
    import asyncio
    
    pause_event = asyncio.Event()
    pause_event.set()
    
    await download_media(
        video_url=url,
        audio_url=None,
        headers={},
        chunks=8,
        video_dest=zip_path,
        audio_dest="",
        pause_event=pause_event,
        warning_state=None,
        media_type="FFmpeg (Essentials)"
    )
                        
    with console.status("[bold cyan]Extracting FFmpeg...", spinner="dots"):
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            for file_info in zip_ref.infolist():
                if file_info.filename.endswith("ffmpeg.exe"):
                    with zip_ref.open(file_info) as source, open(os.path.join(bin_dir, "ffmpeg.exe"), "wb") as target:
                        shutil.copyfileobj(source, target)
                    break
        os.remove(zip_path)
    
    return os.path.join(bin_dir, "ffmpeg.exe")

def mux_audio_video(video_path: str, audio_path: str, output_path: str) -> None:
    """
    Muxes a video and audio file together into a single output file using ffmpeg.
    Copies the streams without re-encoding.
    Deletes the original video and audio files upon successful muxing.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    ffmpeg_bin = get_ffmpeg_path()
    if not ffmpeg_bin:
        raise RuntimeError("FFmpeg is not installed! Cannot mux files.")

    cmd = [
        ffmpeg_bin,
        "-y",  # Overwrite output file if it exists
        "-i", video_path,
        "-i", audio_path,
        "-c", "copy",
        output_path
    ]

    try:
        logger.info(f"Muxing {video_path} and {audio_path} into {output_path}")
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        logger.info("Muxing successful. Deleting original files.")
        try:
            os.remove(video_path)
            os.remove(audio_path)
        except OSError as e:
            logger.warning(f"Failed to delete original files: {e}")
            
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg muxing failed: {e.stderr.decode('utf-8', errors='replace')}")
        raise RuntimeError(f"FFmpeg muxing failed: {e}")
    except FileNotFoundError:
        raise RuntimeError("FFmpeg is not installed! Please run 'winget install ffmpeg' in your terminal to install it, then restart the app.")

def convert_to_mp3(audio_path: str, output_path: str) -> None:
    """
    Converts an audio file to mp3 using ffmpeg.
    Deletes the original audio file upon success.
    """
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    ffmpeg_bin = get_ffmpeg_path()
    if not ffmpeg_bin:
        raise RuntimeError("FFmpeg is not installed! Cannot convert audio.")

    cmd = [
        ffmpeg_bin,
        "-y",
        "-i", audio_path,
        "-q:a", "0",
        "-map", "a",
        output_path
    ]

    try:
        logger.info(f"Converting {audio_path} into {output_path}")
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        logger.info("Conversion successful. Deleting original file.")
        try:
            os.remove(audio_path)
        except OSError as e:
            logger.warning(f"Failed to delete original file: {e}")
            
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg conversion failed: {e.stderr.decode('utf-8', errors='replace')}")
        raise RuntimeError(f"FFmpeg conversion failed: {e}")
    except FileNotFoundError:
        raise RuntimeError("FFmpeg is not installed! Please run 'winget install ffmpeg' in your terminal to install it, then restart the app.")
