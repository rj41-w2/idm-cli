import asyncio
import os
import aiohttp
import aiofiles
import json
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeRemainingColumn,
    DownloadColumn,
    TransferSpeedColumn
)
from idm_cli.utils import console, progress_listener
from idm_cli.config import logger

async def _download_chunk(session: aiohttp.ClientSession, url: str, start: int, end: int, chunk_index: int, dest_path: str, headers: dict, progress_queue: asyncio.Queue, task_id, pause_event: asyncio.Event = None, chunk_progress: dict = None):
    max_retries = 5
    retry_count = 0
    progress_file = f"{dest_path}.progress.json"
    
    while retry_count < max_retries:
        try:
            existing_size = chunk_progress.get(str(chunk_index), 0) if chunk_progress else 0
            current_start = start + existing_size
            
            if end is not None and current_start > end:
                return dest_path
                
            chunk_headers = headers.copy() if headers else {}
            if end is None:
                chunk_headers['Range'] = f'bytes={current_start}-'
            else:
                chunk_headers['Range'] = f'bytes={current_start}-{end}'
            
            async with session.get(url, headers=chunk_headers) as response:
                response.raise_for_status()
                
                if not os.path.exists(dest_path):
                    async with aiofiles.open(dest_path, 'wb') as f:
                        pass
                
                async with aiofiles.open(dest_path, 'r+b') as f:
                    await f.seek(current_start)
                    
                    total_bytes = end - current_start + 1 if end else 0
                    buffer_size = 1024 * 1024
                    if total_bytes > 50 * 1024 * 1024:
                        buffer_size = 4 * 1024 * 1024
                    elif total_bytes > 0 and total_bytes < 5 * 1024 * 1024:
                        buffer_size = 256 * 1024
                        
                    async for chunk in response.content.iter_chunked(buffer_size):
                        if pause_event is not None:
                            await pause_event.wait()
                        if not chunk:
                            break
                        await f.write(chunk)
                        
                        if chunk_progress is not None:
                            chunk_progress[str(chunk_index)] = chunk_progress.get(str(chunk_index), 0) + len(chunk)
                            try:
                                async with aiofiles.open(progress_file, 'w') as pf:
                                    await pf.write(json.dumps(chunk_progress))
                            except OSError as e:
                                logger.debug(f"Failed to write progress: {e}")
                                
                        if progress_queue is not None and task_id is not None:
                            current_task_id = task_id[chunk_index] if isinstance(task_id, list) else task_id
                            await progress_queue.put({
                                'task_id': current_task_id,
                                'chunk_index': chunk_index,
                                'bytes_downloaded': len(chunk)
                            })
            return dest_path
        except (aiohttp.client_exceptions.ClientPayloadError, asyncio.TimeoutError, aiohttp.client_exceptions.ClientError) as e:
            retry_count += 1
            if retry_count >= max_retries:
                raise Exception(f"Chunk {chunk_index} failed after {max_retries} retries: {e}")
            await asyncio.sleep(2 ** retry_count)

async def download_file(session: aiohttp.ClientSession, url: str, dest_path: str, headers: dict, num_chunks: int = 8, progress_queue: asyncio.Queue = None, task_id = None, pause_event: asyncio.Event = None):
    """
    Downloads a file in multiple chunks concurrently using aiohttp and aiofiles.
    """
    progress_file = f"{dest_path}.progress.json"
    chunk_progress = {}
    
    if os.path.exists(dest_path) and not os.path.exists(progress_file):
        file_size = os.path.getsize(dest_path)
        if progress_queue is not None and task_id is not None:
            if isinstance(task_id, list):
                chunk_size_est = file_size // num_chunks
                for i in range(num_chunks):
                    end = file_size - 1 if i == num_chunks - 1 else ((i * chunk_size_est) + chunk_size_est - 1)
                    c_size = end - (i * chunk_size_est) + 1
                    await progress_queue.put({'task_id': task_id[i], 'total_size': c_size})
                    await progress_queue.put({'task_id': task_id[i], 'bytes_downloaded': c_size})
            else:
                await progress_queue.put({'task_id': task_id, 'total_size': file_size})
                await progress_queue.put({'task_id': task_id, 'bytes_downloaded': file_size})
        return

    if os.path.exists(progress_file):
        try:
            async with aiofiles.open(progress_file, 'r') as f:
                content = await f.read()
                if content:
                    chunk_progress = json.loads(content)
        except (OSError, json.JSONDecodeError) as e:
            logger.debug(f"Failed to read progress: {e}")
            chunk_progress = {}

    if headers is None:
        headers = {}
        
    file_size = None
    
    try:
        async with session.head(url, headers=headers, allow_redirects=True) as response:
            content_length = response.headers.get('Content-Length')
            if content_length:
                file_size = int(content_length)
    except aiohttp.ClientError:
        pass
        
    if not file_size:
        try:
            range_headers = headers.copy()
            range_headers['Range'] = 'bytes=0-0'
            async with session.get(url, headers=range_headers, allow_redirects=True) as response:
                content_range = response.headers.get('Content-Range')
                if content_range and '/' in content_range:
                    file_size = int(content_range.split('/')[-1])
                else:
                    content_length = response.headers.get('Content-Length')
                    if content_length:
                        file_size = int(content_length)
        except aiohttp.ClientError:
            pass
            
    if file_size and not os.path.exists(dest_path):
        async with aiofiles.open(dest_path, 'wb') as f:
            await f.truncate(file_size)
        async with aiofiles.open(progress_file, 'w') as pf:
            await pf.write("{}")
            
    if not file_size:
        # Fallback to single chunk download
        await _download_chunk(session, url, 0, None, 0, dest_path, headers, progress_queue, task_id, pause_event, chunk_progress)
        if os.path.exists(progress_file):
            try:
                os.remove(progress_file)
            except OSError:
                pass
        return

    if progress_queue is not None and task_id is not None:
        if isinstance(task_id, list):
            chunk_size_est = file_size // num_chunks
            for i in range(num_chunks):
                start = i * chunk_size_est
                end = file_size - 1 if i == num_chunks - 1 else (start + chunk_size_est - 1)
                c_size = end - start + 1
                await progress_queue.put({
                    'task_id': task_id[i],
                    'total_size': c_size
                })
                existing = chunk_progress.get(str(i), 0)
                if existing > 0:
                    await progress_queue.put({
                        'task_id': task_id[i],
                        'bytes_downloaded': existing
                    })
        else:
            await progress_queue.put({
                'task_id': task_id,
                'total_size': file_size
            })
            
            total_existing_size = sum(chunk_progress.values())
            
            if total_existing_size > 0:
                await progress_queue.put({
                    'task_id': task_id,
                    'bytes_downloaded': total_existing_size
                })

    chunk_size = file_size // num_chunks
    tasks = []
    for i in range(num_chunks):
        start = i * chunk_size
        end = file_size - 1 if i == num_chunks - 1 else (start + chunk_size - 1)
        tasks.append(
            _download_chunk(session, url, start, end, i, dest_path, headers, progress_queue, task_id, pause_event, chunk_progress)
        )
        
    await asyncio.gather(*tasks)
    
    if os.path.exists(progress_file):
        try:
            os.remove(progress_file)
        except OSError as e:
            logger.debug(f"Failed to remove progress file: {e}")

async def download_media(video_url: str, audio_url: str, headers: dict, chunks: int, video_dest: str, audio_dest: str, pause_event: asyncio.Event, warning_state: dict = None, media_type: str = "Video"):
    queue = asyncio.Queue()

    with Progress(
        SpinnerColumn("dots12"),
        TextColumn("[bold blue]{task.description}", justify="right"),
        BarColumn(bar_width=40, complete_style="cyan", finished_style="bold green", pulse_style="bold white"),
        "[progress.percentage]{task.percentage:>3.1f}%",
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console
    ) as progress:
        video_task_ids = []
        if video_url:
            for i in range(chunks):
                video_task_ids.append(progress.add_task(f"[cyan]{media_type} Chunk {i+1}/{chunks}", total=None))
        else:
            video_task_ids = None

        audio_task_id = progress.add_task("[cyan]Audio", total=None) if audio_url else None

        listener = asyncio.create_task(progress_listener(queue, progress, pause_event, warning_state))

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=None), connector=aiohttp.TCPConnector(limit=0)) as session:
            v_task = asyncio.create_task(download_file(session, video_url, video_dest, headers, chunks, queue, video_task_ids, pause_event)) if video_url else None
            a_task = asyncio.create_task(download_file(session, audio_url, audio_dest, headers, chunks, queue, audio_task_id, pause_event)) if audio_url else None
    
            tasks_to_gather = []
            if a_task:
                tasks_to_gather.append(a_task)
            if v_task:
                tasks_to_gather.append(v_task)
    
            await asyncio.gather(*tasks_to_gather)

        await queue.put(None)
        await listener
