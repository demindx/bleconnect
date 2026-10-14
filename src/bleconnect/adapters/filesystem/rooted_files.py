"""Read-only filesystem adapter restricted to a user-selected root."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from pathlib import Path, PurePosixPath

from ...application.ports import SharedFile


class RootedFiles:
    """List and stream files without allowing paths outside ``root``."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).expanduser().resolve(strict=True)
        if not self._root.is_dir():
            raise NotADirectoryError(self._root)

    def _resolve(self, relative_path: str) -> Path:
        if "\\" in relative_path:
            raise ValueError("file paths must use POSIX separators")
        relative = PurePosixPath(relative_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("path must stay inside the shared root")
        candidate = self._root.joinpath(*relative.parts).resolve(strict=True)
        try:
            candidate.relative_to(self._root)
        except ValueError as exc:
            raise ValueError("path must stay inside the shared root") from exc
        return candidate

    async def list_files(self, relative_path: str = "") -> Sequence[SharedFile]:
        directory = self._root if relative_path in ("", ".") else self._resolve(relative_path)
        if not directory.is_dir():
            raise NotADirectoryError(relative_path)
        entries: list[SharedFile] = []
        for child in sorted(directory.iterdir(), key=lambda item: item.name.casefold()):
            try:
                resolved = child.resolve(strict=True)
                resolved.relative_to(self._root)
            except (OSError, ValueError):
                continue
            if resolved.is_symlink():
                continue
            info = resolved.stat()
            if resolved.is_file() or resolved.is_dir():
                entries.append(
                    SharedFile(
                        path=resolved.relative_to(self._root).as_posix(),
                        size=info.st_size if resolved.is_file() else 0,
                        modified_ns=info.st_mtime_ns,
                        is_directory=resolved.is_dir(),
                    )
                )
        return entries

    async def read_file(self, relative_path: str) -> AsyncIterator[bytes]:
        file_path = self._resolve(relative_path)
        if not file_path.is_file():
            raise IsADirectoryError(relative_path)

        async def chunks() -> AsyncIterator[bytes]:
            with file_path.open("rb") as source:
                while chunk := source.read(64 * 1024):
                    yield chunk

        return chunks()
