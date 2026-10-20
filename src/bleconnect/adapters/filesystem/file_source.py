"""Local filesystem FileSource adapter."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path


class LocalFileSource:
    """Stream one explicitly selected file from local storage."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path).expanduser().resolve(strict=True)
        if not self._path.is_file():
            raise IsADirectoryError(self._path)

    @property
    def name(self) -> str:
        return self._path.name

    @property
    def size(self) -> int:
        return self._path.stat().st_size

    async def read_chunks(self, chunk_size: int) -> AsyncIterator[bytes]:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        with self._path.open("rb") as source:
            while True:
                chunk = await asyncio.to_thread(source.read, chunk_size)
                if not chunk:
                    return
                yield chunk
