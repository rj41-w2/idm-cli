import asyncio
import os
import aiohttp
import aiofiles

async def _download_chunk(session: aiohttp.ClientSession, url: str, start: int, end: int, chunk_index: int, dest_path: str, headers: dict, progress_queue: asyncio.Queue, task_id):
    chunk_headers = headers.copy() if headers else {}
    if end is None:
        chunk_headers['Range'] = f'bytes={start}-'
    else:
        chunk_headers['Range'] = f'bytes={start}-{end}'
    
    chunk_path = f"{dest_path}.part{chunk_index}"
    
    async with session.get(url, headers=chunk_headers) as response:
        response.raise_for_status()
        async with aiofiles.open(chunk_path, 'wb') as f:
            async for chunk in response.content.iter_chunked(1024 * 1024):
                if not chunk:
                    break
                await f.write(chunk)
                if progress_queue is not None and task_id is not None:
                    await progress_queue.put({
                        'task_id': task_id,
                        'chunk_index': chunk_index,
                        'bytes_downloaded': len(chunk)
                    })
    return chunk_path

async def download_file(url: str, dest_path: str, headers: dict, num_chunks: int = 8, progress_queue: asyncio.Queue = None, task_id = None):
    """
    Downloads a file in multiple chunks concurrently using aiohttp and aiofiles.
    """
    if headers is None:
        headers = {}
        
    async with aiohttp.ClientSession() as session:
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
            chunk_path = await _download_chunk(session, url, 0, None, 0, dest_path, headers, progress_queue, task_id)
            os.rename(chunk_path, dest_path)
            return

        if progress_queue is not None and task_id is not None:
            await progress_queue.put({
                'task_id': task_id,
                'total_size': file_size
            })

        chunk_size = file_size // num_chunks
        tasks = []
        for i in range(num_chunks):
            start = i * chunk_size
            end = file_size - 1 if i == num_chunks - 1 else (start + chunk_size - 1)
            tasks.append(
                _download_chunk(session, url, start, end, i, dest_path, headers, progress_queue, task_id)
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
