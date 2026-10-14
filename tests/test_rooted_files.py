import asyncio

import pytest

from bleconnect.adapters.filesystem.rooted_files import RootedFiles


def test_lists_and_streams_files_under_root(tmp_path) -> None:
    (tmp_path / "folder").mkdir()
    (tmp_path / "folder" / "note.txt").write_bytes(b"hello")
    files = RootedFiles(tmp_path)

    async def scenario() -> None:
        entries = await files.list_files()
        assert entries[0].path == "folder"
        assert entries[0].is_directory
        chunks = await files.read_file("folder/note.txt")
        assert b"".join([chunk async for chunk in chunks]) == b"hello"

    asyncio.run(scenario())


@pytest.mark.parametrize("path", ["../outside", "/etc/passwd", "folder\\file"])
def test_rejects_invalid_paths(tmp_path, path: str) -> None:
    (tmp_path / "folder").mkdir()
    files = RootedFiles(tmp_path)

    async def scenario() -> None:
        with pytest.raises(ValueError):
            await files.read_file(path)

    asyncio.run(scenario())


def test_rejects_symlink_escaping_root(tmp_path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("outside")
    (tmp_path / "escape.txt").symlink_to(outside)
    files = RootedFiles(tmp_path)

    async def scenario() -> None:
        assert await files.list_files() == []
        with pytest.raises(ValueError):
            await files.read_file("escape.txt")

    try:
        asyncio.run(scenario())
    finally:
        outside.unlink()
