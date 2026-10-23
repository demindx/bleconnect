import asyncio
import json

import pytest

from bleconnect.ipc import IpcError, JsonLineServer, request, request_sync


async def _handler(method: str, params: dict) -> dict:
    if method == "echo":
        return {"value": params.get("value")}
    if method == "fail":
        raise IpcError("nope", "request failed")
    raise IpcError("unknown", method)


def test_ipc_round_trip_and_permissions(tmp_path) -> None:
    async def scenario() -> None:
        path = tmp_path / "daemon.sock"
        server = JsonLineServer(path, _handler)
        await server.start()
        try:
            assert await request(path, "echo", {"value": 7}) == {"value": 7}
            with pytest.raises(IpcError) as error:
                await request(path, "fail")
            assert error.value.code == "nope"
            result = await asyncio.to_thread(
                request_sync, path, "echo", {"value": 9}
            )
            assert result == {"value": 9}
            assert path.stat().st_mode & 0o777 == 0o600
        finally:
            await server.close()
        assert not path.exists()

    asyncio.run(scenario())


def test_ipc_rejects_malformed_json(tmp_path) -> None:
    async def scenario() -> None:
        path = tmp_path / "daemon.sock"
        server = JsonLineServer(path, _handler)
        await server.start()
        try:
            reader, writer = await asyncio.open_unix_connection(str(path))
            writer.write(b"not json\n")
            await writer.drain()
            response = json.loads(await asyncio.wait_for(reader.readline(), 1))
            assert response["ok"] is False
            writer.close()
            await writer.wait_closed()
        finally:
            await server.close()

    asyncio.run(scenario())


def test_ipc_broadcast_event(tmp_path) -> None:
    async def scenario() -> None:
        path = tmp_path / "daemon.sock"
        server = JsonLineServer(path, _handler)
        await server.start()
        try:
            reader, writer = await asyncio.open_unix_connection(str(path))
            await asyncio.sleep(0.05)
            await server.broadcast("state.changed", {"x": 1})
            event = json.loads(await asyncio.wait_for(reader.readline(), 1))
            assert event == {"event": "state.changed", "data": {"x": 1}}
            writer.close()
            await writer.wait_closed()
        finally:
            await server.close()

    asyncio.run(scenario())
