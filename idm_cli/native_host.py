import sys
import json
import struct
import subprocess

def read_message():
    raw_length = sys.stdin.buffer.read(4)
    if len(raw_length) == 0:
        sys.exit(0)
    message_length = struct.unpack('I', raw_length)[0]
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
            url = message.get("url")

            if not url:
                send_message({"status": "error", "message": "No URL provided"})
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
                cmd = ['cmd.exe', '/c', 'start', 'idm', url]
                if quality:
                    cmd.extend(['-q', quality])
                subprocess.Popen(cmd)
                send_message({"status": "success"})
            else:
                send_message({"status": "error", "message": "Unknown action"})

        except Exception as e:
            # For native messaging, if we crash or fail, we can optionally send an error back,
            # but Chrome might kill us before it's read.
            send_message({"status": "error", "message": str(e)})
            sys.exit(1)

if __name__ == '__main__':
    main()
