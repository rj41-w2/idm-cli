import os
import subprocess
import logging

logger = logging.getLogger(__name__)

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

    cmd = [
        "ffmpeg",
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
