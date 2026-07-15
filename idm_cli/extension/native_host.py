import sys
import json
import struct
import subprocess
import re
import os
import platform

ALLOWED_SCHEMES = ("http://", "https://", "www.")
ALLOWED_QUALITY = re.compile(r"^\d{3,4}p$")
ALLOWED_FILENAME = re.compile(r'^[^<>:"/\\|?*\x00-\x1f]{1,200}$')
MAX_MESSAGE_SIZE = 1024 * 1024

def is_valid_url(url: str) -> bool:
    lower = url.strip().lower()
    if not lower.startswith(ALLOWED_SCHEMES):
        return False
    if "javascript:" in lower or "data:" in lower or "file://" in lower:
        return False
    if len(url) > 2048:
        return False
    return True

def is_valid_quality(quality: str) -> bool:
    return bool(quality) and bool(ALLOWED_QUALITY.match(quality))

def is_valid_filename(filename: str) -> bool:
    if not filename or len(filename) > 200:
        return False
    if ".." in filename or "/" in filename or "\\" in filename:
        return False
    return bool(ALLOWED_FILENAME.match(filename))

def read_message():
    raw_length = sys.stdin.buffer.read(4)
    if len(raw_length) == 0:
        sys.exit(0)
    if len(raw_length) < 4:
        sys.exit(1)
    message_length = struct.unpack('I', raw_length)[0]
    if message_length > MAX_MESSAGE_SIZE:
        sys.exit(1)
    message = sys.stdin.buffer.read(message_length).decode('utf-8')
    return json.loads(message)

def send_message(message):
    encoded_message = json.dumps(message).encode('utf-8')
    sys.stdout.buffer.write(struct.pack('I', len(encoded_message)))
    sys.stdout.buffer.write(encoded_message)
    sys.stdout.buffer.flush()

def main():
    while True:
        try:
            message = read_message()
            action = message.get("action")
            url = message.get("url", "").strip()

            if not url:
                send_message({"status": "error", "message": "No URL provided"})
                continue

            if not is_valid_url(url):
                send_message({"status": "error", "message": "Invalid or unsafe URL."})
                continue

            if action == "fetch_qualities":
                try:
                    from idm_cli.extractors import get_extractor
                    extractor = get_extractor(url)
                    info = extractor.fetch_all_info(url)
                    resolutions = extractor.get_video_resolutions(info)
                    qualities = [r['resolution'] for r in resolutions] if resolutions else []
                    send_message({"qualities": qualities, "status": "success"})
                except Exception as e:
                    send_message({"status": "error", "message": str(e)})

            elif action == "download":
                quality = message.get("quality")
                filename_opt = message.get("filename")

                if quality and not is_valid_quality(quality):
                    send_message({"status": "error", "message": "Invalid quality parameter."})
                    continue

                if filename_opt and not is_valid_filename(filename_opt):
                    send_message({"status": "error", "message": "Invalid filename parameter."})
                    continue

                cmd = [sys.executable, '-m', 'idm_cli.ui.cli', '--', url, '-Q']
                if quality:
                    cmd.extend(['-q', quality])
                if filename_opt:
                    cmd.extend(['-f', filename_opt])
                
                result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if result.returncode != 0:
                    try:
                        from idm_cli.config import CONFIG_DIR
                        with open(os.path.join(CONFIG_DIR, "error.log"), "a") as f:
                            f.write(f"Failed to queue: {url}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}\n---\n")
                    except OSError:
                        pass
                
                from idm_cli.extension.daemon import is_daemon_running
                if not is_daemon_running():
                    worker_cmd = [sys.executable, '-m', 'idm_cli.ui.cli', 'start queue']
                    if platform.system() == "Windows":
                        subprocess.Popen(worker_cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
                    else:
                        subprocess.Popen(worker_cmd)
                    
                send_message({"status": "success"})
            else:
                send_message({"status": "error", "message": "Unknown action"})

        except json.JSONDecodeError:
            send_message({"status": "error", "message": "Invalid JSON message."})
        except Exception as e:
            send_message({"status": "error", "message": "An internal error occurred."})
            sys.exit(1)

if __name__ == '__main__':
    main()
