import os
import platform
import subprocess
import logging
import shutil
import zipfile
import aiohttp
import aiofiles
from idm_cli.ui.utils import console

logger = logging.getLogger(__name__)

_system = platform.system()
_is_windows = _system == "Windows"

def _ffmpeg_binary_name() -> str:
    return "ffmpeg.exe" if _is_windows else "ffmpeg"

def _ffmpeg_install_hint() -> str:
    if _is_windows:
        return "Run 'winget install ffmpeg' in your terminal to install it, then restart the app."
    elif _system == "Darwin":
        return "Run 'brew install ffmpeg' in your terminal to install it, then restart the app."
    else:
        return "Run 'sudo apt install ffmpeg' or 'sudo dnf install ffmpeg' in your terminal to install it, then restart the app."

def get_ffmpeg_path() -> str:
    sys_path = shutil.which("ffmpeg")
    if sys_path:
        return sys_path
    
    from idm_cli.config import CONFIG_DIR
    bin_name = _ffmpeg_binary_name()
    local_path = os.path.join(CONFIG_DIR, "bin", bin_name)
    if os.path.exists(local_path):
        return local_path
        
    return None

async def download_ffmpeg() -> str:
    from idm_cli.config import CONFIG_DIR
    if _is_windows:
        url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
    elif _system == "Darwin":
        url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-macos64-gpl.zip"
    else:
        url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz"

    bin_dir = os.path.join(CONFIG_DIR, "bin")
    os.makedirs(bin_dir, exist_ok=True)

    if _is_windows:
        archive_path = os.path.join(bin_dir, "ffmpeg.zip")
    else:
        archive_path = os.path.join(bin_dir, "ffmpeg.tar.xz")

    with console.status("[bold cyan]Downloading FFmpeg...", spinner="dots"):
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                resp.raise_for_status()
                async with aiofiles.open(archive_path, 'wb') as f:
                    async for chunk in resp.content.iter_chunked(1024 * 1024):
                        await f.write(chunk)

    bin_name = _ffmpeg_binary_name()

    with console.status("[bold cyan]Extracting FFmpeg...", spinner="dots"):
        if _is_windows:
            with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                for file_info in zip_ref.infolist():
                    if file_info.filename.endswith("ffmpeg.exe"):
                        with zip_ref.open(file_info) as source, open(os.path.join(bin_dir, bin_name), "wb") as target:
                            shutil.copyfileobj(source, target)
                        break
        else:
            import tarfile
            with tarfile.open(archive_path, 'r:xz') as tar_ref:
                for member in tar_ref.getmembers():
                    if member.name.endswith("ffmpeg") and not member.isdir():
                        member.name = bin_name
                        tar_ref.extract(member, bin_dir)
                        break
        try:
            os.remove(archive_path)
        except OSError:
            pass

    ffmpeg_path = os.path.join(bin_dir, bin_name)
    if not _is_windows:
        os.chmod(ffmpeg_path, 0o755)

    return ffmpeg_path

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

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    cmd = [
        ffmpeg_bin,
        "-y",
        "-i", video_path,
        "-i", audio_path,
        "-c", "copy",
        output_path
    ]

    try:
        logger.debug(f"Muxing {video_path} and {audio_path} into {output_path}")
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        logger.debug("Muxing successful. Deleting original files.")
        try:
            os.remove(video_path)
            os.remove(audio_path)
        except OSError as e:
            logger.warning(f"Failed to delete original files: {e}")
            
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg muxing failed: {e.stderr.decode('utf-8', errors='replace')}")
        raise RuntimeError(f"FFmpeg muxing failed: {e}")
    except FileNotFoundError:
        raise RuntimeError(f"FFmpeg is not installed! {_ffmpeg_install_hint()}")

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

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    cmd = [
        ffmpeg_bin,
        "-y",
        "-i", audio_path,
        "-q:a", "0",
        "-map", "a",
        output_path
    ]

    try:
        logger.debug(f"Converting {audio_path} into {output_path}")
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        logger.debug("Conversion successful. Deleting original file.")
        try:
            os.remove(audio_path)
        except OSError as e:
            logger.warning(f"Failed to delete original file: {e}")
            
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg conversion failed: {e.stderr.decode('utf-8', errors='replace')}")
        raise RuntimeError(f"FFmpeg conversion failed: {e}")
    except FileNotFoundError:
        raise RuntimeError(f"FFmpeg is not installed! {_ffmpeg_install_hint()}")
