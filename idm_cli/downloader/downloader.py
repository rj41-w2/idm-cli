"""
downloader/downloader.py
------------------------
Pure async download engine — no UI, no Rich, no console output.

Public API:
  download_file(session, url, dest_path, headers, num_chunks, progress_queue,
                task_id, pause_event, on_chunk_done)

All progress display is handled by ui/progress.py via the progress_queue.
"""

import asyncio
import json
import os

import aiofiles
import aiohttp

from idm_cli.config import logger

__all__ = ["download_file"]


async def _download_chunk(
    session: aiohttp.ClientSession,
    url: str,
    start: int,
    end: int,
    chunk_index: int,
    dest_path: str,
    headers: dict,
    progress_queue: asyncio.Queue,
    task_id,
    pause_event: asyncio.Event = None,
    chunk_progress: dict = None,
    chunk_lock: asyncio.Lock = None,
    on_success=None,
):
    max_retries = 10
    retry_count = 0
    progress_file = f"{dest_path}.progress.json"

    while retry_count < max_retries:
        try:
            existing_size = chunk_progress.get(str(chunk_index), 0) if chunk_progress else 0
            current_start = start + existing_size

            if end is not None and current_start > end:
                if on_success is not None:
                    on_success(chunk_index)
                return dest_path

            chunk_headers = headers.copy() if headers else {}
            if end is None:
                chunk_headers["Range"] = f"bytes={current_start}-"
            else:
                chunk_headers["Range"] = f"bytes={current_start}-{end}"
            chunk_headers["Accept-Encoding"] = "identity"

            async with session.get(url, headers=chunk_headers) as response:
                response.raise_for_status()

                if not os.path.exists(dest_path):
                    async with aiofiles.open(dest_path, "wb") as f:
                        pass

                async with aiofiles.open(dest_path, "r+b") as f:
                    await f.seek(current_start)

                    total_bytes = end - current_start + 1 if end else 0
                    buffer_size = 1024 * 1024
                    if total_bytes > 50 * 1024 * 1024:
                        buffer_size = 4 * 1024 * 1024
                    elif 0 < total_bytes < 5 * 1024 * 1024:
                        buffer_size = 256 * 1024

                    async for chunk in response.content.iter_chunked(buffer_size):
                        if pause_event is not None:
                            await pause_event.wait()
                        if not chunk:
                            break
                        await f.write(chunk)

                        if chunk_progress is not None:
                            if chunk_lock is not None:
                                async with chunk_lock:
                                    chunk_progress[str(chunk_index)] = (
                                        chunk_progress.get(str(chunk_index), 0) + len(chunk)
                                    )
                                    try:
                                        async with aiofiles.open(progress_file, "w") as pf:
                                            await pf.write(json.dumps(chunk_progress))
                                    except OSError as e:
                                        logger.debug(f"Failed to write progress: {e}")
                            else:
                                chunk_progress[str(chunk_index)] = (
                                    chunk_progress.get(str(chunk_index), 0) + len(chunk)
                                )
                                try:
                                    async with aiofiles.open(progress_file, "w") as pf:
                                        await pf.write(json.dumps(chunk_progress))
                                except OSError as e:
                                    logger.debug(f"Failed to write progress: {e}")

                        if progress_queue is not None and task_id is not None:
                            current_task_id = (
                                task_id[chunk_index]
                                if isinstance(task_id, list)
                                else task_id
                            )
                            await progress_queue.put(
                                {
                                    "task_id": current_task_id,
                                    "chunk_index": chunk_index,
                                    "bytes_downloaded": len(chunk),
                                }
                            )

            if on_success is not None:
                on_success(chunk_index)
            return dest_path

        except (
            aiohttp.ClientPayloadError,
            asyncio.TimeoutError,
            aiohttp.ClientConnectionError,
            aiohttp.ClientConnectorError,
        ) as e:
            retry_count += 1
            if retry_count >= max_retries:
                raise ConnectionError("Your poor internet connection. Try again.")
            logger.warning(f"Chunk {chunk_index} retry {retry_count}/{max_retries}: {e}")
            await asyncio.sleep(10)

        except aiohttp.ClientResponseError as e:
            # 403/410 = URL expired (YouTube pre-signed URLs have short TTL)
            # 5xx     = server-side error
            # Both are worth retrying
            if e.status in (403, 410) or e.status >= 500:
                retry_count += 1
                if retry_count >= max_retries:
                    if e.status in (403, 410):
                        raise ConnectionError(
                            f"Download URL expired (HTTP {e.status}). "
                            "Please paste the link again to get a fresh URL."
                        )
                    raise ConnectionError(f"Server error {e.status}. Try again.")
                logger.warning(
                    f"Chunk {chunk_index} retry {retry_count}/{max_retries}: HTTP {e.status}"
                )
                await asyncio.sleep(10)
                await asyncio.sleep(10)
            else:
                raise


async def download_file(
    session: aiohttp.ClientSession,
    url: str,
    dest_path: str,
    headers: dict,
    num_chunks: int = 8,
    progress_queue: asyncio.Queue = None,
    task_id=None,
    pause_event: asyncio.Event = None,
    on_chunk_done=None,
):
    """
    Download a file in parallel chunks.
    Progress updates are sent to progress_queue as dicts:
      {'task_id': ..., 'total_size': N}
      {'task_id': ..., 'bytes_downloaded': N}
    on_chunk_done(chunk_index) is called when a chunk completes successfully.
    """
    progress_file = f"{dest_path}.progress.json"
    chunk_progress = {}

    # ── already fully downloaded? ──────────────────────────────────────────────
    if os.path.exists(dest_path) and not os.path.exists(progress_file):
        local_size = os.path.getsize(dest_path)
        server_size = None
        try:
            async with session.head(
                url, headers=headers or {}, allow_redirects=True
            ) as response:
                response.raise_for_status()
                cl = response.headers.get("Content-Length")
                if cl:
                    server_size = int(cl)
        except aiohttp.ClientError:
            pass

        if server_size is not None and local_size != server_size:
            logger.debug(
                f"File exists but size mismatch "
                f"(local={local_size}, server={server_size}), restarting"
            )
            try:
                os.remove(dest_path)
            except OSError:
                pass
        else:
            # File is complete — report full progress immediately
            if progress_queue is not None and task_id is not None:
                if isinstance(task_id, list):
                    chunk_size_est = local_size // num_chunks
                    for i in range(num_chunks):
                        end = (
                            local_size - 1
                            if i == num_chunks - 1
                            else (i * chunk_size_est + chunk_size_est - 1)
                        )
                        c_size = end - i * chunk_size_est + 1
                        await progress_queue.put({"task_id": task_id[i], "total_size": c_size})
                        await progress_queue.put({"task_id": task_id[i], "bytes_downloaded": c_size})
                else:
                    await progress_queue.put({"task_id": task_id, "total_size": local_size})
                    await progress_queue.put({"task_id": task_id, "bytes_downloaded": local_size})
            return

    # ── load partial progress ──────────────────────────────────────────────────
    if os.path.exists(progress_file):
        try:
            async with aiofiles.open(progress_file, "r") as f:
                content = await f.read()
                if content:
                    chunk_progress = json.loads(content)
        except (OSError, json.JSONDecodeError) as e:
            logger.debug(f"Failed to read progress: {e}")
            chunk_progress = {}

    if headers is None:
        headers = {}

    # ── probe file size ────────────────────────────────────────────────────────
    file_size = None

    try:
        range_headers = headers.copy()
        range_headers["Range"] = "bytes=0-0"
        range_headers["Accept-Encoding"] = "identity"
        async with session.get(url, headers=range_headers, allow_redirects=True) as response:
            response.raise_for_status()
            content_range = response.headers.get("Content-Range")
            if content_range and "/" in content_range:
                file_size = int(content_range.split("/")[-1])
            else:
                cl = response.headers.get("Content-Length")
                if cl:
                    file_size = int(cl)
    except aiohttp.ClientError:
        pass

    if not file_size:
        try:
            async with session.head(url, headers=headers, allow_redirects=True) as response:
                response.raise_for_status()
                cl = response.headers.get("Content-Length")
                if cl:
                    file_size = int(cl)
        except aiohttp.ClientError:
            pass

    # ── invalidate stale partial progress ─────────────────────────────────────
    if file_size and chunk_progress:
        total_existing = sum(chunk_progress.values())
        file_size_changed = (
            os.path.exists(dest_path) and os.path.getsize(dest_path) != file_size
        )
        if total_existing > file_size or file_size_changed:
            chunk_progress = {}
            for path in (progress_file, dest_path):
                if os.path.exists(path):
                    try:
                        os.remove(path)
                    except OSError:
                        pass

    # ── pre-allocate file ──────────────────────────────────────────────────────
    if file_size and not os.path.exists(dest_path):
        async with aiofiles.open(dest_path, "wb") as f:
            await f.truncate(file_size)
        async with aiofiles.open(progress_file, "w") as pf:
            await pf.write("{}")

    # ── fallback: no Content-Range/Content-Length → single chunk ──────────────
    if not file_size:
        await _download_chunk(
            session, url, 0, None, 0, dest_path, headers,
            progress_queue, task_id, pause_event, chunk_progress,
        )
        if os.path.exists(progress_file):
            try:
                os.remove(progress_file)
            except OSError:
                pass
        return

    # ── report sizes to progress queue ────────────────────────────────────────
    if progress_queue is not None and task_id is not None:
        if isinstance(task_id, list):
            chunk_size_est = file_size // num_chunks
            for i in range(num_chunks):
                start = i * chunk_size_est
                end = (
                    file_size - 1
                    if i == num_chunks - 1
                    else start + chunk_size_est - 1
                )
                c_size = end - start + 1
                await progress_queue.put({"task_id": task_id[i], "total_size": c_size})
                existing = chunk_progress.get(str(i), 0)
                if existing > 0:
                    await progress_queue.put(
                        {"task_id": task_id[i], "bytes_downloaded": existing}
                    )
        else:
            await progress_queue.put({"task_id": task_id, "total_size": file_size})
            total_existing = sum(chunk_progress.values())
            if total_existing > 0:
                await progress_queue.put(
                    {"task_id": task_id, "bytes_downloaded": total_existing}
                )

    # ── parallel chunk download ────────────────────────────────────────────────
    chunk_size = file_size // num_chunks
    chunk_lock = asyncio.Lock()
    tasks = []
    for i in range(num_chunks):
        start = i * chunk_size
        end = file_size - 1 if i == num_chunks - 1 else start + chunk_size - 1
        tasks.append(
            _download_chunk(
                session, url, start, end, i, dest_path, headers,
                progress_queue, task_id, pause_event, chunk_progress,
                chunk_lock, on_success=on_chunk_done,
            )
        )

    await asyncio.gather(*tasks)

    if os.path.exists(progress_file):
        try:
            os.remove(progress_file)
        except OSError as e:
            logger.debug(f"Failed to remove progress file: {e}")
