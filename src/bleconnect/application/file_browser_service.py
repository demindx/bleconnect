"""Read-only file browsing use cases."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence

from .ports import SharedFile, SharedFilesPort


class FileBrowserService:
    """Expose listing and download operations over a read-only file port."""

    def __init__(self, files: SharedFilesPort) -> None:
        self._files = files

    async def list_directory(self, relative_path: str = "") -> Sequence[SharedFile]:
        return await self._files.list_files(relative_path)

    async def download(self, relative_path: str) -> AsyncIterator[bytes]:
        if not relative_path:
            raise ValueError("a file path is required")
        return self._files.read_file(relative_path)
