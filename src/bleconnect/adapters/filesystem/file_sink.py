"""Local filesystem FileSink adapter with safe names and atomic publishing."""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path

from ...application.ports import FileSink, FileSinkFactory

_MAX_NAME_BYTES = 255
_MIN_FREE_BYTES = 1024 * 1024


def sanitize_file_name(name: str) -> str:
    """Reduce a peer-supplied name to one safe path component."""
    if not isinstance(name, str):
        raise ValueError("file name must be a string")
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    base = "".join(
        character for character in base if character.isprintable()
    ).strip().strip(".")
    if not base:
        raise ValueError("file name is empty after sanitization")
    return _truncate_name(base)


def _truncate_name(name: str, limit: int = _MAX_NAME_BYTES) -> str:
    if len(name.encode("utf-8")) <= limit:
        return name

    stem, dot, extension = name.rpartition(".")
    if dot and 0 < len(extension) <= 20:
        suffix = "." + extension
        room = limit - len(suffix.encode("utf-8"))
        stem_bytes = stem.encode("utf-8")[:room]
        return stem_bytes.decode("utf-8", errors="ignore") + suffix

    return name.encode("utf-8")[:limit].decode("utf-8", errors="ignore")


def _unique_name(root: Path, name: str) -> str:
    def available(candidate: str) -> bool:
        return not (root / candidate).exists() and not (
            root / (candidate + ".part")
        ).exists()

    if available(name):
        return name

    stem, dot, extension = name.rpartition(".")
    if not dot:
        stem, extension = name, ""
    suffix = f".{extension}" if extension else ""
    for index in range(1, 10_000):
        candidate = f"{stem} ({index}){suffix}"
        if available(candidate):
            return candidate
    raise OSError("could not find a free destination name")


class LocalFileSink:
    """Write a received file to a temporary path and publish it atomically."""

    def __init__(self, destination: Path, temp_path: Path, size: int) -> None:
        self._destination = destination
        self._temp_path = temp_path
        self._size = size
        self._file = None
        self._written = 0
        self._finished = False

    async def write(self, data: bytes) -> None:
        if self._finished:
            raise OSError("file sink is already finished")
        if not data:
            return
        await asyncio.to_thread(self._write_sync, data)

    def _write_sync(self, data: bytes) -> None:
        if self._file is None:
            self._file = self._temp_path.open("wb")
        self._file.write(data)
        self._written += len(data)

    async def finish(self, sha256: str) -> None:
        if self._finished:
            raise OSError("file sink is already finished")
        if self._written != self._size:
            await self.abort()
            raise OSError("received size does not match the offer")
        await asyncio.to_thread(self._finish_sync)
        self._finished = True

    def _finish_sync(self) -> None:
        if self._file is None:
            self._file = self._temp_path.open("wb")
        self._file.flush()
        os.fsync(self._file.fileno())
        self._file.close()
        os.replace(self._temp_path, self._destination)

    async def abort(self) -> None:
        await asyncio.to_thread(self._abort_sync)

    def _abort_sync(self) -> None:
        if self._file is not None:
            try:
                self._file.close()
            except OSError:
                pass
            self._file = None
        try:
            self._temp_path.unlink()
        except FileNotFoundError:
            pass


class LocalFileSinkFactory:
    """Create sinks beneath one trusted download directory."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).expanduser()

    async def create(self, name: str, size: int) -> FileSink:
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise ValueError("file size is invalid")
        safe_name = sanitize_file_name(name)
        destination, temp_path = await asyncio.to_thread(
            self._prepare, safe_name, size
        )
        return LocalFileSink(destination, temp_path, size)

    def _prepare(self, name: str, size: int) -> tuple[Path, Path]:
        self._root.mkdir(parents=True, exist_ok=True)
        root = self._root.resolve(strict=True)
        free = shutil.disk_usage(root).free
        if free < size + _MIN_FREE_BYTES:
            raise OSError("not enough free disk space")

        unique = _unique_name(root, name)
        destination = root / unique
        try:
            destination.relative_to(root)
        except ValueError as exc:
            raise ValueError("destination escapes the download directory") from exc
        return destination, root / (unique + ".part")
