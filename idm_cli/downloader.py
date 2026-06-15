import asyncio
import os
import aiohttp
import aiofiles

async def _download_chunk(session: aiohttp.ClientSession, url: str, start: int, end: int, chunk_index: int, dest_path: str, headers: dict, progress_queue: asyncio.Queue, task_id, pause_event: asyncio.Event = None):
    chunk_path = f"{dest_path}.part{chunk_index}"
    max_retries = 5
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            # Determine how much of this chunk has already been downloaded (from prior failed attempts)
            existing_size = 0
            if os.path.exists(chunk_path):
                existing_size = os.path.getsize(chunk_path)
                
            current_start = start + existing_size
            
            # If we've already downloaded this entire chunk, return immediately
            if end is not None and current_start > end:
                return chunk_path
                
            chunk_headers = headers.copy() if headers else {}
            if end is None:
                chunk_headers['Range'] = f'bytes={current_start}-'
            else:
                chunk_headers['Range'] = f'bytes={current_start}-{end}'
            
            async with session.get(url, headers=chunk_headers) as response:
                response.raise_for_status()
                # Use append mode ('ab') to resume writing if we already have data, avoiding overwrite
                mode = 'ab' if existing_size > 0 else 'wb'
                async with aiofiles.open(chunk_path, mode) as f:
                    async for chunk in response.content.iter_chunked(1024 * 1024):
                        if pause_event is not None:
                            await pause_event.wait()
                        if not chunk:
                            break
                        await f.write(chunk)
                        if progress_queue is not None and task_id is not None:
                            # IMPORTANT BUG PREVENTION: 
                            # We ONLY report the newly downloaded bytes for this specific iteration.
                            # We DO NOT report `existing_size` because those bytes were already sent 
                            # to the progress queue during a previous attempt. 
                            # Using `progress.advance()` in main.py accumulates these safely, 
                            # preventing the progress bar from jumping, resetting, or duplicating.
                            await progress_queue.put({
                                'task_id': task_id,
                                'chunk_index': chunk_index,
                                'bytes_downloaded': len(chunk)
                            })
            return chunk_path
        except (aiohttp.client_exceptions.ClientPayloadError, asyncio.TimeoutError, aiohttp.client_exceptions.ClientError) as e:
            retry_count += 1
            if retry_count >= max_retries:
                raise Exception(f"Chunk {chunk_index} failed after {max_retries} retries: {e}")
            await asyncio.sleep(2 ** retry_count)

async def download_file(url: str, dest_path: str, headers: dict, num_chunks: int = 8, progress_queue: asyncio.Queue = None, task_id = None, pause_event: asyncio.Event = None):
    """
    Downloads a file in multiple chunks concurrently using aiohttp and aiofiles.
    """
    if os.path.exists(dest_path):
        file_size = os.path.getsize(dest_path)
        if progress_queue is not None and task_id is not None:
            await progress_queue.put({'task_id': task_id, 'total_size': file_size})
            await progress_queue.put({'task_id': task_id, 'bytes_downloaded': file_size})
        return

    if headers is None:
        headers = {}
        
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=None)) as session:
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
                # Use GET with Range bytes=0-0 to get total length from Content-Range
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
                
        if not file_size:
            # Fallback to single chunk download
            chunk_path = await _download_chunk(session, url, 0, None, 0, dest_path, headers, progress_queue, task_id, pause_event)
            os.rename(chunk_path, dest_path)
            return

        if progress_queue is not None and task_id is not None:
            await progress_queue.put({
                'task_id': task_id,
                'total_size': file_size
            })
            
            total_existing_size = 0
            for i in range(num_chunks):
                chunk_path = f"{dest_path}.part{i}"
                if os.path.exists(chunk_path):
                    total_existing_size += os.path.getsize(chunk_path)
            
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
                _download_chunk(session, url, start, end, i, dest_path, headers, progress_queue, task_id, pause_event)
            )
            
        chunk_paths = await asyncio.gather(*tasks)
        
        # Merge chunks
        async with aiofiles.open(dest_path, 'wb') as out_file:
            for chunk_path in chunk_paths:
                async with aiofiles.open(chunk_path, 'rb') as in_file:
                    while True:
                        data = await in_file.read(1024 * 1024)
                        if not data:
                            break
                        await out_file.write(data)
                os.remove(chunk_path)
