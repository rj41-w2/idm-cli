import os
import json
import asyncio
from rich.console import Console
from rich.progress import Progress
import questionary
from prompt_toolkit.lexers import Lexer
from idm_cli import __version__

def sanitize_filename(title: str) -> str:
    return "".join([c for c in title if c.isalpha() or c.isdigit() or c in ' -_.']).rstrip()[:60].strip()

try:
    import msvcrt
except ImportError:
    msvcrt = None

import sys
try:
    import select
    import termios
    import tty
except ImportError:
    pass

def check_key_press():
    if sys.platform == 'win32':
        if msvcrt and msvcrt.kbhit():
            return msvcrt.getch().decode('utf-8', 'ignore').lower()
    else:
        if 'select' in sys.modules and 'termios' in sys.modules and 'tty' in sys.modules:
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setcbreak(sys.stdin.fileno())
                dr, dw, de = select.select([sys.stdin], [], [], 0)
                if dr:
                    return sys.stdin.read(1).lower()
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return None

console = Console()

CHANGELOG = {
    "1.2.2": [
        "Fixed an issue where resuming a download could result in a corrupted video file.",
        "Switched FFmpeg automatic download to high-speed GitHub releases (BtbN builds) for maximum bandwidth.",
        "Added a new option to seamlessly install FFmpeg via winget for Windows users.",
        "Improved downloader stability by automatically recovering from YouTube network throttling or silent disconnects."
    ]
}

def check_first_run():
    from idm_cli.config import load_config, save_config
    config = load_config()
    last_version = config.get("last_version", "0.0.0")

    if __version__ != last_version:
        if __version__ in CHANGELOG:
            console.print(f"\n[bold cyan]*** What's New in v{__version__} ***[/bold cyan]")
            for change in CHANGELOG[__version__]:
                console.print(f"  [bold cyan]*[/bold cyan] {change}")
            console.print()
        
        config["last_version"] = __version__
        save_config(config)


custom_style = questionary.Style([
    ('qmark', 'fg:cyan bold'),       
    ('question', 'bold white'),               
    ('answer', 'fg:cyan bold'),      
    ('pointer', 'fg:cyan bold'),     
    ('highlighted', 'fg:cyan bold'), 
    ('flags', 'fg:darkgray'),
])

class IDMLexer(Lexer):
    def lex_document(self, document):
        def get_line(lineno):
            line = document.lines[lineno]
            idx = line.find(" -")
            if idx != -1:
                return [('class:answer', line[:idx]), ('class:flags', line[idx:])]
            return [('class:answer', line)]
        return get_line

async def progress_listener(queue: asyncio.Queue, progress: Progress, pause_event: asyncio.Event = None, warning_state: dict = None):
    """Listens for progress updates from the downloader and updates the Rich progress bar."""
    while True:
        if warning_state and warning_state.get("show"):
            for task in progress.tasks:
                if "[WARNING: Press Ctrl+C again to cancel]" not in task.description:
                    progress.update(task.id, description=f"[bold yellow][WARNING: Press Ctrl+C again to cancel][/] {task.description}")
            warning_state["show"] = False

        if pause_event:
            key = check_key_press()
            if key:
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
